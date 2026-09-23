"""Thin Chat coordination. Starts the existing embedded harness only."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
import threading

from workbench_backend.agents.harness import HarnessService
from workbench_backend.agents.schemas import AgentRun, AgentStartRequest, InterruptDecisionRequest
from workbench_backend.agents.tools import enabled_for_project, resolve_presented_tools
from workbench_backend.agents.setup_service import SetupService, configuration_from_request, cleared_configuration_fields
from workbench_backend.agents.setup_schemas import ProjectCreateRequest, SetupConfiguration, ReviewConfiguration, FrozenExecutionSelection, ResolvedSetupSelection
from workbench_backend.agents.helpers import freeze_helpers, freeze_settings
from contextlib import ExitStack
from workbench_backend.assets.schemas import RetainedAssetReuseRequest
from workbench_backend.assets.service import RetainedAssetService
from workbench_backend.chat.deploy_health import report_chat_deploy_health
from workbench_backend.chat.schemas import (
    ChatDeployHealth,
    ChatCancelRequest,
    ChatContinuity,
    ChatConversation,
    ChatConversationCreateRequest,
    ChatConversationArchiveRequest,
    ChatConversationUpdateRequest,
    ChatConversationView,
    ChatDraft,
    ChatDraftUpdateRequest,
    ChatMessage,
    ChatQueueItem,
    ChatQueueItemUpdateRequest,
    ChatQueueResumeRequest,
    ChatSearchResult,
    ChatStartRequest,
    ChatTranscriptReplaceRequest,
)
from workbench_backend.chat.store import ChatStore
from workbench_backend.contracts.lifecycle import is_run_lifecycle_live
from workbench_backend.errors import ChatError, HarnessError, ManagerError
from workbench_backend.inference.ids import new_id, utc_now
from workbench_backend.inference.service import ModelManager
from workbench_backend.knowledge.schemas import KnowledgeRefs
from workbench_backend.knowledge.service import KnowledgeService
from workbench_backend.lab.service import LabService
from workbench_backend.paths import WorkbenchPaths
from workbench_backend.state.checkpointer import checkpoint_history
from workbench_backend.state.migrate import open_application_store
from workbench_backend.state.store import ApplicationStore

CHAT_SYSTEM_PROMPT = (
    "You are the Local AI Workbench Chat surface. Complete the user's task "
    "using the embedded Deep Agents harness. Filesystem tools target the bound "
    "project workspace, not conversation history. Use project-relative paths "
    "such as hello.txt with read_file, write_file and edit_file; you do not "
    "need to discover the operating-system working directory for a file task. "
    "Prefer these file tools over shell commands for reading and editing files. "
    "The host shell execute tool "
    "runs on this machine in the project working directory with no isolation; "
    "the application's per-turn Access policy controls permission decisions. Do not invent durable knowledge "
    "or retrieval."
)
CHAT_SYSTEM_PROMPT_WITHOUT_PROJECT = (
    "You are the Local AI Workbench Chat surface. Complete the user's task "
    "using the embedded Deep Agents harness. This conversation has no project "
    "folder. Filesystem and host-shell tools are unavailable. Use visibility "
    "tools only. Do not invent a project directory, a home-directory cwd, or "
    "durable knowledge."
)


class ChatService:
    def __init__(
        self,
        manager_provider: Callable[[], ModelManager],
        harness_provider: Callable[[], HarnessService],
        lab_provider: Callable[[], LabService],
        app_store: ApplicationStore | None = None,
        knowledge_provider: Callable[[], KnowledgeService] | None = None,
        assets_provider: Callable[[], RetainedAssetService] | None = None,
    ) -> None:
        self._manager_provider = manager_provider
        self._harness_provider = harness_provider
        self._lab_provider = lab_provider
        self._app_store = app_store
        self._knowledge_provider = knowledge_provider
        self._assets_provider = assets_provider
        self._asset_service: RetainedAssetService | None = None
        self._submission_cancel_lock = threading.RLock()
        self._submission_cancel_events: dict[tuple[str, str | None, str], threading.Event] = {}
        self._pending_steer: dict[str, str] = {}

    @property
    def manager(self) -> ModelManager:
        return self._manager_provider()

    @property
    def harness(self) -> HarnessService:
        return self._harness_provider()

    @property
    def lab(self) -> LabService:
        return self._lab_provider()

    @property
    def knowledge(self) -> KnowledgeService:
        if self._knowledge_provider is None:
            raise ChatError(
                "Knowledge version refs require the application-owned knowledge store.",
                code="knowledge_store_missing",
                status_code=409,
            )
        return self._knowledge_provider()

    @property
    def assets(self) -> RetainedAssetService:
        if self._assets_provider is not None:
            return self._assets_provider()
        if self._asset_service is None:
            self._asset_service = RetainedAssetService(self.app_store)
        return self._asset_service

    @property
    def paths(self) -> WorkbenchPaths:
        return self.manager.paths.ensure()

    @property
    def app_store(self) -> ApplicationStore:
        if self._app_store is None:
            self._app_store = open_application_store(self.paths)
        return self._app_store

    @property
    def store(self) -> ChatStore:
        return ChatStore(self.app_store)

    def create(self, request: ChatConversationCreateRequest) -> ChatConversationView:
        if request.profile_id:
            self._bind_profile(request.profile_id)
        selections = self._setups()
        project = selections.get_project(request.project_id, require_active=True) if request.project_id else None
        if project:
            if request.workspace_id or request.project_path and Path(request.project_path).resolve() != Path(project.path).resolve():
                raise ChatError("The selected folder does not match this project.", code="project_mismatch", status_code=409)
            request = request.model_copy(update={"project_path": project.path})
        elif request.project_path and not request.workspace_id:
            project = selections.create_project(ProjectCreateRequest(path=request.project_path))
        overrides = configuration_from_request(request)
        cleared_fields = cleared_configuration_fields(request)
        selection = selections.resolve(project_id=project.id if project else None, agent_setup_version_id=request.agent_setup_version_id, overrides=overrides, override_cleared_fields=cleared_fields, validate=bool(project or request.agent_setup_version_id), prepare_model=True)
        request = request.model_copy(update={k: v for k, v in selection.configuration.model_dump(exclude_none=True).items() if k in type(request).model_fields})
        if not request.deployment_id:
            raise ChatError("Choose a model or an agent with a model before starting Chat.", code="setup_deployment_required", status_code=400)
        workspace_id, project_path = self._resolve_project(request.workspace_id, request.project_path)
        profile_id = self._bind_profile(request.profile_id)
        self.manager.get_deployment(request.deployment_id)
        refs = self._bind_knowledge(
            memory_version_refs=request.memory_version_refs,
            skill_version_refs=request.skill_version_refs,
            protected_instruction_version_refs=request.protected_instruction_version_refs,
            knowledge_version_refs=request.knowledge_version_refs,
        )
        now = utc_now()
        project_text = str(project_path) if project_path is not None else None
        conversation = ChatConversation(
            id=new_id("chat"),
            title=request.title,
            area_kind="project" if project_text else "general",
            area_id=project.id if project else workspace_id or project_text or "general",
            area_label=project.name if project else project_path.name if project_path is not None else "General",
            area_project_path=project_text,
            area_workspace_id=workspace_id,
            deployment_id=request.deployment_id,
            project_id=project.id if project else None,
            agent_setup_version_id=request.agent_setup_version_id,
            setup_overrides=overrides,
            setup_cleared_fields=cleared_fields,
            presented_tools=selection.configuration.presented_tools,
            approval_mode=selection.configuration.approval_mode or "ask",
            work_mode=selection.configuration.work_mode or "work",
            helper_agent_ids=selection.configuration.helper_agent_ids or [],
            review=selection.configuration.review or {},
            model_configuration_id=selection.configuration.model_configuration_id,
            startup_overrides=selection.configuration.startup_overrides,
            connection_ids=selection.configuration.connection_ids,
            per_request_overrides=selection.configuration.per_request_overrides,
            profile_id=profile_id,
            inherit_deployment_settings=request.inherit_deployment_settings,
            project_path=project_text,
            workspace_id=workspace_id,
            thread_id=new_id("thread"),
            memory_version_refs=refs.memory_version_refs,
            skill_version_refs=refs.skill_version_refs,
            protected_instruction_version_refs=refs.protected_instruction_version_refs,
            embedding_deployment_id=request.embedding_deployment_id,
            retrieval_project_paths=list(request.retrieval_project_paths),
            created_at=now,
            updated_at=now,
        )
        return self._view(self.store.put(conversation))

    def list_conversations(self, *, include_archived: bool = False) -> list[ChatConversationView]:
        """Sidebar catalogue. Does not load runs, reconcile, or the token log."""

        views = []
        for item in self.store.list_conversations(include_archived=include_archived):
            # Deletion and archive can race the initial catalogue snapshot.
            # The store read is atomic and does not wait for a conversation's
            # model-start admission lock or load runs/token history.
            current = self.store.get(item.id)
            if current is None or (current.archived and not include_archived):
                continue
            views.append(self._light_view(current, include_transcript=False))
        return views

    def search(self, query: str, *, include_archived: bool = False) -> list[ChatSearchResult]:
        return [
            ChatSearchResult(conversation=conversation, matched_messages=messages)
            for conversation, messages in self.store.search(query, include_archived=include_archived)
        ]

    def get(self, conversation_id: str) -> ChatConversationView:
        with self.store.conversation_lock(conversation_id):
            conversation = self._require(conversation_id)
            self._persist_thread_if_missing(conversation)
        return self._view(conversation, persist=True)

    def start(self, conversation_id: str, request: ChatStartRequest) -> ChatConversationView:
        task = request.task.strip()
        if not task and not request.content_blocks and not request.attachment_ids:
            raise ChatError("Compose text is required.", code="task_required", status_code=400)
        with self.store.conversation_lock(conversation_id):
            conversation = self._require(conversation_id)
            conversation, _terminal = self._reconcile_terminal_assistant(conversation)
            if conversation.current_run_id:
                try:
                    current = self.harness.get_run(conversation.current_run_id)
                except HarnessError:
                    current = None
                if current is not None and is_run_lifecycle_live(current.status):
                    raise ChatError(
                        "A Chat turn is already live on this conversation.",
                        code="chat_turn_active",
                        status_code=409,
                    )
                # Completion persists outside the conversation admission lock.
                # Once the harness confirms terminal state, reconcile against
                # fresh durable history before constructing the next turn.
                # Do not hold the store lock across harness calls: completion
                # takes the harness lock before the store lock.
                conversation = self._require(conversation_id)
                if current is not None:
                    if conversation.history_replaced:
                        updated = conversation.model_copy(deep=True)
                        updated.current_run_id = None
                        updated.updated_at = utc_now()
                        conversation = self.store.put(updated)
                    else:
                        conversation, _terminal = self._reconcile_terminal_assistant(conversation, current)
            return self._view(self._dispatch_request(conversation, request))

    def enqueue(self, conversation_id: str, request: ChatStartRequest) -> ChatConversationView:
        task = request.task.strip()
        if not task and not request.content_blocks and not request.attachment_ids:
            raise ChatError("Compose text is required.", code="task_required", status_code=400)
        with self.store.conversation_lock(conversation_id):
            conversation = self._require(conversation_id)
            queued = self._append_queue_item(conversation, request)
            return self._view(queued)

    def resume_queue(
        self,
        conversation_id: str,
        request: ChatQueueResumeRequest,
    ) -> ChatConversationView:
        with self.store.conversation_lock(conversation_id):
            conversation = self._require(conversation_id)
            conversation = self._recover_dispatching_queue(conversation)
            if request.resume_paused:
                conversation = self._unpause_queue(conversation, request)
            return self._view(self._dispatch_next_queued(conversation))

    def rename(self, conversation_id: str, request: ChatConversationUpdateRequest) -> ChatConversationView:
        with self.store.conversation_lock(conversation_id):
            conversation = self._require(conversation_id).model_copy(deep=True)
            conversation.title = request.title.strip()
            return self._view(self.app_store.update_conversation(conversation))

    def archive(
        self,
        conversation_id: str,
        request: ChatConversationArchiveRequest,
    ) -> ChatConversationView:
        with self.store.conversation_lock(conversation_id):
            conversation = self._require(conversation_id).model_copy(deep=True)
            conversation.archived = request.archived
            conversation.archived_at = utc_now() if request.archived else None
            return self._view(self.app_store.update_conversation(conversation))

    def update_draft(self, conversation_id: str, request: ChatDraftUpdateRequest) -> ChatConversationView:
        with self.store.conversation_lock(conversation_id):
            with self.app_store._lock:
                conversation = self._require(conversation_id).model_copy(deep=True)
                self.assets.require_active_assets(
                    list(request.attachment_ids),
                    session_id=conversation.id,
                    project_path=conversation.project_path,
                )
                current_revision = conversation.draft.revision if conversation.draft else 0
                if request.expected_revision is not None and request.expected_revision != current_revision:
                    raise ChatError(
                        "The Chat draft changed before this update.",
                        code="draft_revision_conflict",
                        status_code=409,
                    )
                conversation.draft = ChatDraft(
                    content=request.content,
                    content_blocks=request.content_blocks,
                    attachment_ids=list(request.attachment_ids),
                    intended_config=dict(request.intended_config),
                    revision=current_revision + 1,
                    updated_at=utc_now(),
                )
                updated = self.app_store.update_conversation(conversation)
            return self._view(updated)

    def update_queue_item(
        self,
        conversation_id: str,
        item_id: str,
        request: ChatQueueItemUpdateRequest,
    ) -> ChatConversationView:
        with self.store.conversation_lock(conversation_id):
            with self.app_store._lock:
                conversation = self._require(conversation_id).model_copy(deep=True)
                if request.attachment_ids is not None:
                    self.assets.require_active_assets(
                        list(request.attachment_ids),
                        session_id=conversation.id,
                        project_path=conversation.project_path,
                    )
                item = next((entry for entry in conversation.queue if entry.id == item_id), None)
                if item is None:
                    raise ChatError("Unknown queued Chat turn.", code="queue_item_missing", status_code=404)
                if item.status == "dispatching":
                    raise ChatError("A dispatching Chat turn cannot be edited.", code="queue_item_dispatching", status_code=409)
                if request.task is not None:
                    item.task = request.task
                if request.input_message_id is not None:
                    item.input_message_id = request.input_message_id
                if request.content_blocks is not None:
                    item.content_blocks = request.content_blocks
                if request.attachment_ids is not None:
                    item.attachment_ids = list(request.attachment_ids)
                if request.output_schema is not None:
                    item.output_schema = request.output_schema
                if request.intended_config is not None:
                    merged_config = dict(item.intended_config)
                    merged_config.update(dict(request.intended_config))
                    item.intended_config = merged_config
                    intended_request = self._request_from_queue_item(item)
                    self._reject_session_area_change(conversation, intended_request)
                    item.intended_config = self._resolved_config(conversation, intended_request)
                    item.instruction_layers = self._instruction_snapshot(conversation, intended_request)
                    item.helper_snapshots = freeze_helpers(self._setups(), item.intended_config.get("helper_agent_ids", []), project_id=conversation.project_id,
                        parent_configuration=SetupConfiguration.model_validate({key: value for key, value in item.intended_config.items() if key in SetupConfiguration.model_fields}))
                    item.execution_snapshot = self._execution_snapshot(item, conversation.project_id)
                item.updated_at = utc_now()
                with ExitStack() as reservations:
                    for deployment_id, profile_id in [(item.intended_config.get("deployment_id"), item.intended_config.get("profile_id")),
                            *((helper.configuration.deployment_id, helper.configuration.profile_id) for helper in item.helper_snapshots or [])]:
                        if deployment_id:
                            reservations.enter_context(self.manager.reserve_deployment(deployment_id, profile_id=profile_id))
                    updated = self.app_store.update_conversation(conversation)
            return self._view(updated)

    def steer_queue_item(self, conversation_id: str, item_id: str) -> ChatConversationView:
        """Course-correct the live turn with one queued message.

        Deep Agents 0.7 has no mid-stream inject. Stop the current model or
        tool step, keep the transcript, and send this message on the same thread.
        """

        cancel_run_id: str | None = None
        with self.store.conversation_lock(conversation_id):
            conversation = self._require(conversation_id).model_copy(deep=True)
            item = next((entry for entry in conversation.queue if entry.id == item_id), None)
            if item is None:
                raise ChatError("Unknown queued Chat turn.", code="queue_item_missing", status_code=404)
            if item.status == "dispatching":
                raise ChatError("A dispatching Chat turn cannot be steered.", code="queue_item_dispatching", status_code=409)
            if item.pause_reason == "dispatch_uncertain":
                raise ChatError(
                    "Review the uncertain dispatch before steering this turn.",
                    code="steer_needs_review",
                    status_code=409,
                )
            now = utc_now()
            item.status = "queued"
            item.pause_reason = None
            item.pause_error = None
            item.pause_error_code = None
            item.updated_at = now
            conversation.queue = [item, *[entry for entry in conversation.queue if entry.id != item.id]]
            conversation.updated_at = now
            live = False
            if conversation.current_run_id:
                try:
                    current = self.harness.get_run(conversation.current_run_id)
                except HarnessError:
                    current = None
                live = current is not None and is_run_lifecycle_live(current.status)
            saved = self.store.put(conversation)
            if live:
                self._pending_steer[conversation.id] = item.id
                cancel_run_id = conversation.current_run_id
            else:
                self._pending_steer.pop(conversation.id, None)
                saved = self._dispatch_next_queued(saved)
        if cancel_run_id:
            self.harness.cancel(cancel_run_id)
            with self.store.conversation_lock(conversation_id):
                return self._view(self._require(conversation_id))
        return self._view(saved)

    def remove_queue_item(self, conversation_id: str, item_id: str) -> ChatConversationView:
        with self.store.conversation_lock(conversation_id):
            conversation = self._require(conversation_id).model_copy(deep=True)
            queue = [item for item in conversation.queue if item.id != item_id]
            if len(queue) == len(conversation.queue):
                raise ChatError("Unknown queued Chat turn.", code="queue_item_missing", status_code=404)
            conversation.queue = queue
            return self._view(self.app_store.update_conversation(conversation))

    def observe_terminal_run(self, run: AgentRun) -> None:
        """Reconcile terminal Chat output and advance/pause queued work.

        Call this from an app-level coordinator after the harness releases its
        run lock. It intentionally does not run from inside harness persistence.
        """

        if run.source_surface != "chat" or run.status.value not in {"completed", "failed", "cancelled"}:
            return
        for item in self.store.list_conversations(include_archived=True):
            if item.current_run_id != run.id:
                continue
            with self.store.conversation_lock(item.id):
                conversation = self._require(item.id)
                if conversation.current_run_id != run.id:
                    return
                conversation = self._accept_dispatching_run(conversation, run)
                conversation, terminal = self._reconcile_terminal_assistant(conversation, run)
                if terminal == "completed":
                    self._pending_steer.pop(conversation.id, None)
                    conversation = self._complete_queue_item(conversation, run.id)
                    self._dispatch_next_queued(conversation)
                elif terminal in {"failed", "cancelled"}:
                    steer_id = self._pending_steer.pop(conversation.id, None)
                    conversation = self._complete_queue_item(conversation, run.id)
                    if steer_id:
                        self._dispatch_steered(conversation, steer_id)
                    else:
                        self._pause_queue(conversation, terminal)
            return

    def reconcile_saved_queue_on_startup(self, *, pending_only: bool = False) -> int:
        """Reconcile saved Chat queues without replaying uncertain work."""

        reconciled = 0
        for item in self.store.list_conversations(include_archived=True):
            with self.store.conversation_lock(item.id):
                conversation = self._require(item.id)
                if (pending_only and not conversation.queue and
                        not self.app_store.pending_chat_submission_cancels(conversation.id)):
                    continue
                before = conversation.model_dump_json()
                conversation = self._recover_dispatching_queue(conversation)
                conversation = self._resolve_orphan_pending_cancellations(conversation)
                if conversation.current_run_id:
                    try:
                        current = self.harness.get_run(conversation.current_run_id)
                    except HarnessError:
                        current = None
                    if current is not None and current.status.value in {"completed", "failed", "cancelled"}:
                        conversation = self._accept_dispatching_run(conversation, current)
                        conversation, terminal = self._reconcile_terminal_assistant(conversation, current)
                        conversation = self._complete_queue_item(conversation, current.id)
                        if terminal in {"failed", "cancelled"}:
                            conversation = self._pause_queue(conversation, terminal)
                if conversation.model_dump_json() != before:
                    reconciled += 1
        return reconciled

    def dispatch_idle_queued(self, conversation_id: str | None = None) -> int:
        """Dispatch queued work for idle conversations when the app coordinator allows it."""

        candidates = (
            [self._require(conversation_id)]
            if conversation_id is not None
            else self.store.list_conversations(include_archived=True)
        )
        dispatched = 0
        for item in candidates:
            with self.store.conversation_lock(item.id):
                conversation = self._require(item.id) if conversation_id is not None else self.store.get(item.id)
                if conversation is None:
                    continue
                before_run_ids = set(conversation.run_ids)
                conversation = self._recover_dispatching_queue(conversation)
                updated = self._dispatch_next_queued(conversation)
                if set(updated.run_ids) != before_run_ids:
                    dispatched += 1
        return dispatched

    def cancel(
        self,
        conversation_id: str,
        request: ChatCancelRequest | None = None,
    ) -> ChatConversationView:
        input_message_id = request.input_message_id if request is not None else None
        if input_message_id:
            conversation = self._require(conversation_id)
            self._request_submission_cancel(conversation, input_message_id)
            conversation = self._require(conversation_id)
            matched_run_id: str | None = None
            for message in reversed(conversation.transcript):
                if message.role == "user" and message.id == input_message_id:
                    matched_run_id = message.run_id
                    break
            if matched_run_id is not None:
                self.app_store.request_chat_submission_cancel(
                    conversation_id,
                    input_message_id,
                    run_id=matched_run_id,
                )
                self.harness.cancel(matched_run_id)
            updated = self._pause_matching_dispatch(conversation.id, input_message_id) or conversation
            return self._view(updated)
        with self.store.conversation_lock(conversation_id):
            conversation = self._require(conversation_id)
            if not conversation.current_run_id:
                raise ChatError("No active Chat run to cancel.", code="chat_run_missing", status_code=409)
            self.harness.cancel(conversation.current_run_id)
            fresh = self._require(conversation_id)
        return self._view(fresh, persist=True)

    def resume_interrupt(
        self,
        conversation_id: str,
        request: InterruptDecisionRequest,
    ) -> ChatConversationView:
        with self.store.conversation_lock(conversation_id):
            conversation = self._require(conversation_id)
            if not conversation.current_run_id:
                raise ChatError(
                    "No active Chat run for a host-shell interrupt decision.",
                    code="chat_run_missing",
                    status_code=409,
                )
            self.harness.resume_interrupt(
                conversation.current_run_id,
                request,
                require_interrupt_identity=True,
            )
            fresh = self._require(conversation_id)
        return self._view(fresh, persist=True)

    def replace_transcript(
        self,
        conversation_id: str,
        request: ChatTranscriptReplaceRequest,
    ) -> ChatConversationView:
        """Replace displayed history only.

        Project files, durable knowledge, and the LangGraph thread are not
        touched (STATE-002 / Issue #56). Edited transcript is not replayed
        into the harness.
        """

        with self.store.conversation_lock(conversation_id):
            conversation = self._require(conversation_id)
            self._ensure_thread(conversation)
            conversation.transcript = list(request.messages)
            conversation.history_replaced = True
            conversation.updated_at = utc_now()
            return self._view(self.store.put(conversation))

    def _submission_cancel_key(
        self,
        conversation_id: str,
        thread_id: str | None,
        input_message_id: str,
    ) -> tuple[str, str | None, str]:
        return (conversation_id, thread_id, input_message_id)

    def _register_submission_cancel_event(
        self,
        conversation_id: str,
        thread_id: str | None,
        input_message_id: str,
    ) -> threading.Event:
        key = self._submission_cancel_key(conversation_id, thread_id, input_message_id)
        with self._submission_cancel_lock:
            event = self._submission_cancel_events.get(key)
            if event is None:
                event = threading.Event()
                self._submission_cancel_events[key] = event
            if self.app_store.chat_submission_cancel_known(conversation_id, input_message_id):
                event.set()
            return event

    def _request_submission_cancel(
        self,
        conversation: ChatConversation,
        input_message_id: str,
    ) -> None:
        key = self._submission_cancel_key(conversation.id, conversation.thread_id, input_message_id)
        with self._submission_cancel_lock:
            self.app_store.request_chat_submission_cancel(conversation.id, input_message_id)
            event = self._submission_cancel_events.get(key)
            if event is not None:
                event.set()

    def _clear_submission_cancel_event(
        self,
        conversation_id: str,
        thread_id: str | None,
        input_message_id: str,
    ) -> None:
        key = self._submission_cancel_key(conversation_id, thread_id, input_message_id)
        with self._submission_cancel_lock:
            self._submission_cancel_events.pop(key, None)

    def _dispatch_request(
        self,
        conversation: ChatConversation,
        request: ChatStartRequest,
        *,
        queue_item: ChatQueueItem | None = None,
    ) -> ChatConversation:
        next_conversation = conversation.model_copy(deep=True)
        self._reject_session_area_change(next_conversation, request)
        frozen = queue_item.execution_snapshot if queue_item is not None else None
        if frozen is None:
            self._apply_start_configuration(next_conversation, request)
        else:
            # Queue records were admitted by this application. Reuse their
            # resolved values; current mutable defaults affect future messages.
            for key, value in queue_item.intended_config.items():
                if key in type(next_conversation).model_fields:
                    if key == "review":
                        value = ReviewConfiguration.model_validate(value)
                    setattr(next_conversation, key, value)
        self._preflight_start_request(next_conversation, request)
        self._ensure_thread(next_conversation)
        now = utc_now()
        next_conversation.history_replaced = False
        input_message_id = self._dispatch_input_message_id(request, queue_item)
        content_blocks = self._content_blocks_with_attachments(next_conversation, request)
        submission = self._submission_record(next_conversation, request, content_blocks,
            intended_config=queue_item.intended_config if frozen is not None else None)
        existing_message = next(
            (message for message in next_conversation.transcript if message.role == "user" and message.id == input_message_id),
            None,
        )
        if existing_message is not None:
            if self._message_submission_record(existing_message) != submission:
                raise ChatError(
                    "This input identity already belongs to a different Chat submission. Generate a new input id for edited work.",
                    code="submission_identity_conflict",
                    status_code=409,
                )
        else:
            transcript_blocks = [block.model_dump(mode="json") for block in content_blocks] if content_blocks else []
            transcript_blocks.append({"type": "workbench_submission", "submission": submission})
            next_conversation.transcript.append(
                ChatMessage(
                    id=input_message_id,
                    role="user",
                    content=request.task.strip(),
                    content_blocks=transcript_blocks,
                    attachment_ids=list(request.attachment_ids),
                    at=now,
                )
            )
        if queue_item is not None:
            for item in next_conversation.queue:
                if item.id == queue_item.id:
                    item.status = "dispatching"
                    item.pause_reason = None
                    item.pause_error_code = None
                    item.pause_error = None
                    item.input_message_id = input_message_id
                    item.frozen_config = dict(queue_item.intended_config) if frozen is not None else self._resolved_config(next_conversation, request)
                    item.updated_at = now
                    break
        next_conversation.updated_at = now
        next_conversation = self.store.put(next_conversation)

        accepted = self._find_chat_run_by_input(next_conversation, input_message_id)
        if accepted is None:
            cancel_event = self._register_submission_cancel_event(
                next_conversation.id,
                next_conversation.thread_id,
                input_message_id,
            )
            try:
                self.harness.register_start_cancel_guard(
                    next_conversation.thread_id,
                    input_message_id,
                    cancel_event,
                )
                accepted = self.harness.start(
                    AgentStartRequest(
                        deployment_id=next_conversation.deployment_id,
                        task=request.task.strip(),
                        input_message_id=input_message_id,
                        content_blocks=content_blocks or None,
                        retained_asset_ids=list(request.attachment_ids),
                        output_schema=request.output_schema,
                        presented_tools=next_conversation.presented_tools,
                        approval_mode=next_conversation.approval_mode,
                        work_mode=next_conversation.work_mode,
                        helper_agent_ids=next_conversation.helper_agent_ids,
                        review=next_conversation.review,
                        model_configuration_id=next_conversation.model_configuration_id,
                        startup_overrides=next_conversation.startup_overrides,
                        system_prompt=(
                            CHAT_SYSTEM_PROMPT
                            if next_conversation.project_path
                            else CHAT_SYSTEM_PROMPT_WITHOUT_PROJECT
                        ),
                        workspace_id=next_conversation.workspace_id,
                        project_id=next_conversation.project_id,
                        agent_setup_version_id=next_conversation.agent_setup_version_id,
                        connection_ids=next_conversation.connection_ids,
                        instructions=next_conversation.setup_overrides.instructions,
                        project_path=next_conversation.project_path,
                        profile_id=next_conversation.profile_id,
                        inherit_deployment_settings=next_conversation.inherit_deployment_settings,
                        per_request_overrides=next_conversation.per_request_overrides,
                        source_surface="chat",
                        thread_id=next_conversation.thread_id,
                        memory_version_refs=next_conversation.memory_version_refs,
                        skill_version_refs=next_conversation.skill_version_refs,
                        protected_instruction_version_refs=next_conversation.protected_instruction_version_refs,
                        embedding_deployment_id=next_conversation.embedding_deployment_id,
                        retrieval_project_paths=list(next_conversation.retrieval_project_paths),
                    ),
                    **({"instruction_snapshot": queue_item.instruction_layers} if queue_item is not None and queue_item.instruction_layers is not None else {}),
                    **({"helper_snapshot": queue_item.helper_snapshots} if queue_item is not None and queue_item.helper_snapshots is not None else {}),
                    **({"execution_snapshot": frozen} if frozen is not None else {}),
                )
            except (HarnessError, ManagerError) as exc:
                recovered = self._find_chat_run_by_input(next_conversation, input_message_id)
                if recovered is not None:
                    accepted = recovered
                elif queue_item is not None:
                    self.app_store.resolve_chat_submission_cancel(next_conversation.id, input_message_id)
                    return self._pause_dispatching_item(
                        next_conversation,
                        queue_item.id,
                        "failed",
                        error_code=getattr(exc, "code", None),
                        error=str(exc),
                    )
                else:
                    self.app_store.resolve_chat_submission_cancel(next_conversation.id, input_message_id)
                    raise
            except Exception:
                recovered = self._find_chat_run_by_input(next_conversation, input_message_id)
                if recovered is not None:
                    accepted = recovered
                elif queue_item is not None:
                    return self._pause_dispatching_item(
                        next_conversation,
                        queue_item.id,
                        "dispatch_uncertain",
                        error_code="dispatch_uncertain",
                        error="Dispatch failed before Chat could confirm whether a run was accepted.",
                    )
                else:
                    raise
            finally:
                self.harness.clear_start_cancel_guard(next_conversation.thread_id, input_message_id)
                if accepted is not None:
                    # Keep the Event registered until the accepted run has
                    # been durably linked below. Stop may still arrive in the
                    # acceptance commit window before the transcript has a
                    # run_id to cancel by.
                    pass
                else:
                    self._clear_submission_cancel_event(
                        next_conversation.id,
                        next_conversation.thread_id,
                        input_message_id,
                    )
        assert accepted is not None
        next_conversation = self._accept_dispatched_run(
            next_conversation,
            accepted,
            input_message_id,
            draft_revision=request.draft_revision if queue_item is None else None,
        )
        if self.app_store.chat_submission_cancel_requested(next_conversation.id, input_message_id):
            self.app_store.request_chat_submission_cancel(
                next_conversation.id,
                input_message_id,
                run_id=accepted.id,
            )
            self.harness.cancel(accepted.id)
        self._clear_submission_cancel_event(
            next_conversation.id,
            next_conversation.thread_id,
            input_message_id,
        )
        return next_conversation

    def _append_queue_item(
        self,
        conversation: ChatConversation,
        request: ChatStartRequest,
    ) -> ChatConversation:
        with self.manager.reserve_deployment(request.deployment_id or conversation.deployment_id,
                profile_id=request.profile_id or conversation.profile_id):
            return self._append_queue_item_reserved(conversation, request)

    def _append_queue_item_reserved(self, conversation: ChatConversation, request: ChatStartRequest) -> ChatConversation:
        with self.app_store._lock:
            queued = conversation.model_copy(deep=True)
            self.assets.require_active_assets(
                list(request.attachment_ids),
                session_id=queued.id,
                project_path=queued.project_path,
            )
            self._reject_session_area_change(queued, request)
            now = utc_now()
            content_blocks = [
                block.model_dump(mode="json") for block in request.content_blocks
            ] if request.content_blocks else None
            output_schema = request.output_schema.model_dump(mode="json") if request.output_schema else None
            intended_config = self._intended_config(queued, request)
            existing_input_id = request.input_message_id.strip() if request.input_message_id else None
            if existing_input_id:
                for existing in queued.queue:
                    if existing.input_message_id != existing_input_id:
                        continue
                    if self._queue_submission_matches(existing, request, content_blocks, output_schema, intended_config):
                        return self.store.put(queued)
                    raise ChatError(
                        "This input identity already belongs to a different queued Chat submission. Generate a new input id for edited work.",
                        code="submission_identity_conflict",
                        status_code=409,
                    )
            item = ChatQueueItem(
                id=new_id("queue"),
                task=request.task.strip(),
                input_message_id=request.input_message_id,
                content_blocks=content_blocks,
                attachment_ids=list(request.attachment_ids),
                output_schema=output_schema,
                intended_config=intended_config,
                helper_snapshots=freeze_helpers(self._setups(), intended_config.get("helper_agent_ids", []), project_id=queued.project_id,
                    parent_configuration=SetupConfiguration.model_validate({key: value for key, value in intended_config.items() if key in SetupConfiguration.model_fields})),
                instruction_layers=self._instruction_snapshot(queued, request),
                created_at=now,
                updated_at=now,
            )
            item.execution_snapshot = self._execution_snapshot(item, queued.project_id)
            queued.queue.append(item)
            self.app_store._clear_chat_draft_if_revision_locked(queued, request.draft_revision, now)
            queued.updated_at = now
            with ExitStack() as reservations:
                for deployment_id, profile_id in [(intended_config.get("deployment_id"), intended_config.get("profile_id")),
                        *((helper.configuration.deployment_id, helper.configuration.profile_id) for helper in item.helper_snapshots or [])]:
                    if deployment_id:
                        reservations.enter_context(self.manager.reserve_deployment(deployment_id, profile_id=profile_id))
                return self.store.put(queued)

    def _dispatch_steered(self, conversation: ChatConversation, item_id: str) -> ChatConversation:
        steered = conversation.model_copy(deep=True)
        item = next((entry for entry in steered.queue if entry.id == item_id), None)
        if item is None or item.status == "dispatching":
            return self._pause_queue(conversation, "cancelled")
        now = utc_now()
        item.status = "queued"
        item.pause_reason = None
        item.pause_error = None
        item.pause_error_code = None
        item.updated_at = now
        steered.queue = [item, *[entry for entry in steered.queue if entry.id != item.id]]
        steered.updated_at = now
        return self._dispatch_next_queued(self.store.put(steered))

    def _dispatch_next_queued(self, conversation: ChatConversation) -> ChatConversation:
        if not conversation.queue or conversation.queue[0].status != "queued":
            return conversation
        if conversation.current_run_id:
            try:
                current = self.harness.get_run(conversation.current_run_id)
            except HarnessError:
                current = None
            if current is not None and is_run_lifecycle_live(current.status):
                return conversation
        next_item = conversation.queue[0]
        request = self._request_from_queue_item(next_item)
        return self._dispatch_request(conversation, request, queue_item=next_item)

    def _recover_dispatching_queue(self, conversation: ChatConversation) -> ChatConversation:
        dispatching = next((item for item in conversation.queue if item.status == "dispatching"), None)
        if dispatching is None:
            return conversation
        if dispatching.run_id:
            try:
                run = self.harness.get_run(dispatching.run_id)
            except HarnessError:
                run = None
            if run is not None:
                recovered = self._accept_dispatching_run(conversation, run)
                if is_run_lifecycle_live(run.status):
                    return recovered
                recovered, terminal = self._reconcile_terminal_assistant(recovered, run)
                recovered = self._complete_queue_item(recovered, run.id)
                if terminal in {"failed", "cancelled"}:
                    return self._pause_queue(recovered, terminal)
                return recovered
        if dispatching.input_message_id:
            run = self._find_chat_run_by_input(conversation, dispatching.input_message_id)
            if run is not None:
                recovered = self._accept_dispatched_run(conversation, run, dispatching.input_message_id)
                if is_run_lifecycle_live(run.status):
                    return recovered
                recovered, terminal = self._reconcile_terminal_assistant(recovered, run)
                recovered = self._complete_queue_item(recovered, run.id)
                if terminal in {"failed", "cancelled"}:
                    return self._pause_queue(recovered, terminal)
                return recovered
        uncertain = conversation.model_copy(deep=True)
        dispatching = next((item for item in uncertain.queue if item.status == "dispatching"), None)
        if dispatching is None:
            return conversation
        dispatching.status = "paused"
        dispatching.pause_reason = "dispatch_uncertain"
        dispatching.pause_error_code = "dispatch_uncertain"
        dispatching.pause_error = "Chat could not confirm whether the queued turn was accepted before restart."
        dispatching.updated_at = utc_now()
        uncertain.updated_at = utc_now()
        return self.store.put(uncertain)

    def _resolve_orphan_pending_cancellations(self, conversation: ChatConversation) -> ChatConversation:
        for input_message_id in self.app_store.pending_chat_submission_cancels(conversation.id):
            run = self._find_chat_run_by_input(conversation, input_message_id)
            if run is not None and is_run_lifecycle_live(run.status):
                continue
            self.app_store.resolve_chat_submission_cancel(conversation.id, input_message_id)
        return self._require(conversation.id)

    def _accept_dispatching_run(self, conversation: ChatConversation, run: AgentRun) -> ChatConversation:
        dispatching = next(
            (item for item in conversation.queue if item.status == "dispatching" and item.run_id == run.id),
            None,
        )
        if dispatching is None:
            return conversation
        accepted = conversation.model_copy(deep=True)
        if run.id not in accepted.run_ids:
            accepted.run_ids.append(run.id)
        accepted.current_run_id = run.id
        for message in reversed(accepted.transcript):
            if message.role == "user" and message.id == dispatching.input_message_id and message.run_id is None:
                message.run_id = run.id
                break
        if accepted == conversation:
            return conversation
        accepted.updated_at = utc_now()
        return self.store.put(accepted)

    def _accept_dispatched_run(
        self,
        conversation: ChatConversation,
        run: AgentRun,
        input_message_id: str | None,
        *,
        draft_revision: int | None = None,
    ) -> ChatConversation:
        accepted = self.app_store.accept_chat_dispatched_run(
            conversation.id,
            run.id,
            input_message_id,
            draft_revision=draft_revision,
        )
        return accepted or conversation

    def _pause_dispatching_item(
        self,
        conversation: ChatConversation,
        item_id: str,
        reason: str,
        *,
        error_code: str | None = None,
        error: str | None = None,
    ) -> ChatConversation:
        paused = conversation.model_copy(deep=True)
        for item in paused.queue:
            if item.id == item_id and item.status == "dispatching":
                item.status = "paused"
                item.pause_reason = reason  # type: ignore[assignment]
                item.pause_error_code = error_code
                item.pause_error = error
                item.updated_at = utc_now()
                break
        paused.updated_at = utc_now()
        return self.store.put(paused)

    def _pause_matching_dispatch(
        self,
        conversation_id: str,
        input_message_id: str,
    ) -> ChatConversation | None:
        return self.app_store.pause_chat_submission_queue_item(conversation_id, input_message_id)

    def _dispatch_input_message_id(
        self,
        request: ChatStartRequest,
        queue_item: ChatQueueItem | None,
    ) -> str:
        if request.input_message_id:
            return request.input_message_id
        if queue_item is not None:
            return queue_item.input_message_id or f"{queue_item.id}:input"
        return new_id("msg")

    def _submission_record(
        self,
        conversation: ChatConversation,
        request: ChatStartRequest,
        content_blocks: list[object],
        *, intended_config: dict[str, object] | None = None,
    ) -> dict[str, object]:
        return {
            "task": request.task.strip(),
            "draft_revision": request.draft_revision,
            "content_blocks": [block.model_dump(mode="json") for block in content_blocks] if content_blocks else None,
            "attachment_ids": list(request.attachment_ids),
            "output_schema": request.output_schema.model_dump(mode="json") if request.output_schema else None,
            "intended_config": intended_config if intended_config is not None else self._resolved_config(conversation, request),
        }

    def _message_submission_record(self, message: ChatMessage) -> dict[str, object]:
        blocks = message.content_blocks or []
        for block in reversed(blocks):
            if isinstance(block, dict) and block.get("type") == "workbench_submission":
                submission = block.get("submission")
                if isinstance(submission, dict):
                    return submission
        return {
            "task": message.content,
            "draft_revision": None,
            "content_blocks": message.content_blocks,
            "attachment_ids": list(message.attachment_ids),
            "output_schema": None,
            "intended_config": {},
        }

    def _queue_submission_matches(
        self,
        item: ChatQueueItem,
        request: ChatStartRequest,
        content_blocks: list[dict[str, object]] | None,
        output_schema: dict[str, object] | None,
        intended_config: dict[str, object],
    ) -> bool:
        return (
            item.task == request.task.strip()
            and (item.content_blocks or None) == content_blocks
            and item.attachment_ids == list(request.attachment_ids)
            and item.output_schema == output_schema
            and item.intended_config == intended_config
        )

    def _preflight_start_request(
        self,
        conversation: ChatConversation,
        request: ChatStartRequest,
    ) -> None:
        try:
            self.manager.get_deployment(conversation.deployment_id)
        except ManagerError as exc:
            if exc.code != "deployment_missing":
                raise
            raise ChatError(
                "The Chat conversation is bound to a deployment that is no longer available. "
                "Select a deployment to continue.",
                code="deploy_missing",
                status_code=409,
                details={"deployment_id": conversation.deployment_id},
            ) from exc
        connection_snapshots = self.harness.connections.snapshot(conversation.connection_ids, tools_enabled=conversation.presented_tools != [])
        _presented, denied, filesystem_blocked, shell_blocked = resolve_presented_tools(
            conversation.presented_tools,
            project_bound=conversation.project_path is not None,
            external_names=[tool.name for connection in connection_snapshots for tool in connection.tools],
            attachment_available=bool(request.attachment_ids),
            knowledge_routes=bool(
                conversation.memory_version_refs
                or conversation.skill_version_refs
                or conversation.protected_instruction_version_refs
            ),
        )
        if conversation.embedding_deployment_id:
            from workbench_backend.agents.retrieval import SEARCH_KNOWLEDGE_TOOL_NAME
            denied = [name for name in denied if name != SEARCH_KNOWLEDGE_TOOL_NAME]
        if denied:
            raise ChatError(
                f"Tools are not in the enabled catalogue: {', '.join(denied)}",
                code="tool_denied",
                status_code=400,
                details={"tools": denied},
            )
        if filesystem_blocked:
            raise ChatError(
                "Filesystem tools require a bound project folder.",
                code="filesystem_requires_project",
                status_code=400,
                details={"tools": filesystem_blocked},
            )
        if shell_blocked:
            raise ChatError(
                "The host shell requires a bound project folder as cwd. A home-directory default is not invented.",
                code="shell_requires_project",
                status_code=400,
                details={"tools": shell_blocked},
            )

    def _find_chat_run_by_input(
        self,
        conversation: ChatConversation,
        input_message_id: str | None,
    ) -> AgentRun | None:
        if not input_message_id or not conversation.thread_id:
            return None
        for run in self.harness.list_runs():
            if (
                run.source_surface == "chat"
                and run.thread_id == conversation.thread_id
                and run.input_message_id == input_message_id
            ):
                return run
        return None

    def _complete_queue_item(self, conversation: ChatConversation, run_id: str) -> ChatConversation:
        if not any(item.run_id == run_id for item in conversation.queue):
            return conversation
        completed = conversation.model_copy(deep=True)
        completed.queue = [item for item in completed.queue if item.run_id != run_id]
        completed.updated_at = utc_now()
        return self.store.put(completed)

    def _unpause_queue(
        self,
        conversation: ChatConversation,
        request: ChatQueueResumeRequest,
    ) -> ChatConversation:
        if not any(item.status == "paused" for item in conversation.queue):
            return conversation
        uncertain = [
            item
            for item in conversation.queue
            if item.status == "paused" and item.pause_reason == "dispatch_uncertain"
        ]
        if uncertain and not request.acknowledge_uncertain_effects:
            raise ChatError(
                "A queued turn paused because Chat could not confirm whether it already ran. "
                "Review it, then retry with acknowledge_uncertain_effects=true if you accept the repeat-effects risk.",
                code="queue_uncertain_ack_required",
                status_code=409,
                details={"queue_item_ids": [item.id for item in uncertain]},
            )
        resumed = conversation.model_copy(deep=True)
        for item in resumed.queue:
            if item.status == "paused":
                item.status = "queued"
                item.pause_reason = None
                item.pause_error_code = None
                item.pause_error = None
                item.updated_at = utc_now()
        resumed.updated_at = utc_now()
        return self.store.put(resumed)

    def _request_from_queue_item(self, item: ChatQueueItem) -> ChatStartRequest:
        payload = {"task": item.task, **item.intended_config}
        if item.input_message_id is not None:
            payload["input_message_id"] = item.input_message_id
        if item.content_blocks is not None:
            payload["content_blocks"] = item.content_blocks
        if item.attachment_ids:
            payload["attachment_ids"] = item.attachment_ids
        if item.output_schema is not None:
            payload["output_schema"] = item.output_schema
        return ChatStartRequest.model_validate(payload)

    def _content_blocks_with_attachments(
        self,
        conversation: ChatConversation,
        request: ChatStartRequest,
    ) -> list[object]:
        blocks: list[object] = list(request.content_blocks or [])
        if request.attachment_ids:
            deployment = self.manager.get_deployment(conversation.deployment_id)
            capacity = deployment.server_props.n_ctx if deployment.server_props else None
            # Reserve room for instructions, tool schemas, history and the answer.
            # The existing context guard still verifies the complete model request.
            max_chars = min(1_000_000, max(1500, int(capacity * 1.2) - len(request.task))) if capacity else 24000
            selected_tools = request.presented_tools if "presented_tools" in request.model_fields_set else conversation.presented_tools
            asset_blocks = self.assets.current_user_content(
                RetainedAssetReuseRequest(
                    asset_ids=list(request.attachment_ids),
                    session_id=conversation.id,
                    project_path=conversation.project_path,
                    max_chars=max_chars,
                ),
                allow_scoped_read=selected_tools is None or "read_attachment" in selected_tools,
            )
            blocks.extend(asset_blocks)
        if len(blocks) > 32:
            raise ChatError(
                "Current-user content is limited to 32 blocks. Remove attachments or content blocks.",
                code="content_block_limit",
                status_code=413,
            )
        return blocks

    def _apply_start_configuration(
        self,
        conversation: ChatConversation,
        request: ChatStartRequest,
    ) -> None:
        fields_set = request.model_fields_set
        if request.profile_id:
            self._bind_profile(request.profile_id)
        if not request.deployment_id and "agent_setup_version_id" not in fields_set and self.manager.store.get_deployment(conversation.deployment_id) is None:
            raise ChatError("The Chat conversation's model setup is no longer available. Select a model to continue.", code="deploy_missing", status_code=409, details={"deployment_id": conversation.deployment_id})
        has_layered_setup = bool(conversation.project_id or conversation.agent_setup_version_id or "agent_setup_version_id" in fields_set or request.model_configuration_id or conversation.model_configuration_id or self.app_store.get_setup_defaults().model_dump(exclude_none=True))
        if not has_layered_setup and "instructions" in fields_set:
            conversation.setup_overrides = conversation.setup_overrides.model_copy(update={"instructions": request.instructions})
        if not has_layered_setup and "approval_mode" in fields_set and request.approval_mode:
            # Keep explicit access choices when application defaults later add
            # a setup layer to an existing General conversation.
            conversation.setup_overrides = conversation.setup_overrides.model_copy(update={"approval_mode": request.approval_mode})
        if not has_layered_setup:
            additions = {key: getattr(request, key) for key in ("work_mode", "helper_agent_ids", "review", "model_configuration_id", "startup_overrides") if key in fields_set and getattr(request, key) is not None}
            conversation.setup_overrides = conversation.setup_overrides.model_copy(update=additions)
            resets = {key for key in fields_set if key in SetupConfiguration.model_fields and getattr(request, key) is None}
            conversation.setup_overrides = SetupConfiguration.model_validate({key: value for key, value in conversation.setup_overrides.model_dump(exclude_none=True).items() if key not in resets})
            defaults = {'work_mode': 'work', 'helper_agent_ids': [], 'review': ReviewConfiguration(), 'approval_mode': 'ask'}
            for key in resets:
                if key in defaults:
                    setattr(conversation, key, defaults[key])
        if has_layered_setup:
            if "agent_setup_version_id" in fields_set and request.agent_setup_version_id != conversation.agent_setup_version_id:
                conversation.agent_setup_version_id = request.agent_setup_version_id
                conversation.setup_overrides = SetupConfiguration()
                conversation.setup_cleared_fields = []
            explicit = configuration_from_request(request).model_dump(exclude_none=True)
            overrides = conversation.setup_overrides.model_dump(exclude_none=True) | explicit
            for key in fields_set:
                if key in SetupConfiguration.model_fields and getattr(request, key) is None:
                    overrides.pop(key, None)
            if "profile_id" in fields_set and request.profile_id is None:
                overrides.pop("profile_id", None)
            conversation.setup_overrides = SetupConfiguration.model_validate(overrides)
            for key in ("profile_id", "embedding_deployment_id"):
                if key in fields_set:
                    conversation.setup_cleared_fields = [field for field in conversation.setup_cleared_fields if field != key]
                    if getattr(request, key) is None:
                        conversation.setup_cleared_fields.append(key)
            selection = self._setups().resolve(project_id=conversation.project_id, agent_setup_version_id=conversation.agent_setup_version_id, overrides=conversation.setup_overrides, override_cleared_fields=conversation.setup_cleared_fields, prepare_model=True)
            values = selection.configuration.model_dump(exclude_none=True)
            values.update({field: None for field in conversation.setup_cleared_fields})
            for key in ("memory_version_refs", "skill_version_refs", "protected_instruction_version_refs"):
                values.setdefault(key, [])
            values.setdefault("profile_id", None)
            values.setdefault("model_configuration_id", None)
            values.setdefault("startup_overrides", None)
            values.setdefault("presented_tools", None)
            # An inherited empty mode means Ask, including when leaving a
            # Full access setup. Never carry the old setup's authority forward.
            values.setdefault("approval_mode", "ask")
            values.setdefault("connection_ids", None)
            values.setdefault("per_request_overrides", None)
            values.setdefault("work_mode", "work")
            values.setdefault("helper_agent_ids", [])
            values["review"] = selection.configuration.review or ReviewConfiguration()
            request = request.model_copy(update={key: value for key, value in values.items() if key in type(request).model_fields})
            fields_set = request.model_fields_set
        if "presented_tools" in fields_set:
            conversation.presented_tools = request.presented_tools
        if "approval_mode" in fields_set and request.approval_mode:
            conversation.approval_mode = request.approval_mode
        if "connection_ids" in fields_set:
            conversation.connection_ids = request.connection_ids
        if "per_request_overrides" in fields_set:
            conversation.per_request_overrides = request.per_request_overrides
        for key in ("work_mode", "helper_agent_ids", "review", "model_configuration_id", "startup_overrides"):
            if key in fields_set and (getattr(request, key) is not None or key in {"model_configuration_id", "startup_overrides"}):
                setattr(conversation, key, getattr(request, key))
        if request.deployment_id:
            self.manager.get_deployment(request.deployment_id)
            conversation.deployment_id = request.deployment_id
        if "profile_id" in fields_set:
            conversation.profile_id = self._bind_profile(request.profile_id)
        if "inherit_deployment_settings" in fields_set:
            conversation.inherit_deployment_settings = request.inherit_deployment_settings
        if (
            request.memory_version_refs is not None
            or request.skill_version_refs is not None
            or request.protected_instruction_version_refs is not None
            or request.knowledge_version_refs is not None
        ):
            refs = self._bind_knowledge(
                memory_version_refs=request.memory_version_refs
                if request.memory_version_refs is not None
                else conversation.memory_version_refs,
                skill_version_refs=request.skill_version_refs
                if request.skill_version_refs is not None
                else conversation.skill_version_refs,
                protected_instruction_version_refs=(
                    request.protected_instruction_version_refs
                    if request.protected_instruction_version_refs is not None
                    else conversation.protected_instruction_version_refs
                ),
                knowledge_version_refs=request.knowledge_version_refs or [],
            )
            conversation.memory_version_refs = refs.memory_version_refs
            conversation.skill_version_refs = refs.skill_version_refs
            conversation.protected_instruction_version_refs = refs.protected_instruction_version_refs
        if "embedding_deployment_id" in fields_set:
            conversation.embedding_deployment_id = request.embedding_deployment_id
        if "retrieval_project_paths" in fields_set:
            conversation.retrieval_project_paths = list(request.retrieval_project_paths or [])

    def _reject_session_area_change(
        self,
        conversation: ChatConversation,
        request: ChatStartRequest,
    ) -> None:
        fields_set = request.model_fields_set
        if "project_id" in fields_set and request.project_id != conversation.project_id:
            raise ChatError("A Chat conversation cannot move to another project. Start a new chat in that area.", code="session_area_immutable", status_code=409)
        if "project_path" not in fields_set and "workspace_id" not in fields_set:
            return
        workspace_id, project_path = self._resolve_project(request.workspace_id, request.project_path)
        project_text = str(project_path) if project_path is not None else None
        if project_text != conversation.project_path or workspace_id != conversation.workspace_id:
            raise ChatError(
                "A Chat conversation cannot be moved between General and project areas. Start a new chat in the target area.",
                code="session_area_immutable",
                status_code=409,
                details={
                    "area_kind": conversation.area_kind,
                    "area_project_path": conversation.area_project_path,
                    "area_workspace_id": conversation.area_workspace_id,
                    "project_path": conversation.project_path,
                    "workspace_id": conversation.workspace_id,
                },
            )

    def _intended_config(self, conversation: ChatConversation, request: ChatStartRequest) -> dict[str, object]:
        return self._resolved_config(conversation, request)

    def _resolved_config(self, conversation: ChatConversation, request: ChatStartRequest) -> dict[str, object]:
        clone = conversation.model_copy(deep=True)
        self._apply_start_configuration(clone, request)
        return {
            "deployment_id": clone.deployment_id,
            "project_id": clone.project_id,
            "agent_setup_version_id": clone.agent_setup_version_id,
            "connection_ids": clone.connection_ids,
            "instructions": clone.setup_overrides.instructions,
            "profile_id": clone.profile_id,
            "inherit_deployment_settings": clone.inherit_deployment_settings,
            "per_request_overrides": clone.per_request_overrides,
            "project_path": clone.project_path,
            "workspace_id": clone.workspace_id,
            "presented_tools": clone.presented_tools,
            "approval_mode": clone.approval_mode,
            "work_mode": clone.work_mode,
            "helper_agent_ids": clone.helper_agent_ids,
            "review": clone.review.model_dump(mode="json"),
            "model_configuration_id": clone.model_configuration_id,
            "startup_overrides": clone.startup_overrides,
            "attachment_ids": list(request.attachment_ids),
            "memory_version_refs": list(clone.memory_version_refs),
            "skill_version_refs": list(clone.skill_version_refs),
            "protected_instruction_version_refs": list(clone.protected_instruction_version_refs),
            "embedding_deployment_id": clone.embedding_deployment_id,
            "retrieval_project_paths": list(clone.retrieval_project_paths),
        }

    def _require(self, conversation_id: str) -> ChatConversation:
        conversation = self.store.get(conversation_id)
        if conversation is None:
            raise ChatError("Unknown Chat conversation", code="chat_missing", status_code=404)
        return conversation

    def _setups(self) -> SetupService:
        return SetupService(self.app_store, self.manager, self._knowledge_provider() if self._knowledge_provider else None, connection_available=self.harness.connections.available, connection_tools=lambda ident: [tool.name for tool in self.harness.connections.get(ident).tools])

    def _instruction_snapshot(self, conversation: ChatConversation, request: ChatStartRequest):
        clone = conversation.model_copy(deep=True)
        self._apply_start_configuration(clone, request)
        return self._setups().resolve(project_id=clone.project_id, agent_setup_version_id=clone.agent_setup_version_id, overrides=clone.setup_overrides, override_cleared_fields=clone.setup_cleared_fields).instruction_layers

    def _execution_snapshot(self, item: ChatQueueItem, project_id: str | None):
        configuration = SetupConfiguration.model_validate({key: value for key, value in item.intended_config.items() if key in SetupConfiguration.model_fields})
        version_id = item.intended_config.get("agent_setup_version_id")
        version = self._setups().get_version(version_id) if version_id else None
        selection = ResolvedSetupSelection(project_id=project_id, agent_setup_id=version.setup_id if version else None,
            agent_setup_version_id=version_id, configuration=configuration, instruction_layers=item.instruction_layers or [])
        return FrozenExecutionSelection(selection=selection, settings=freeze_settings(self.manager, configuration))

    def _ensure_thread(self, conversation: ChatConversation) -> str:
        """Stable LangGraph thread for this conversation. Legacy rows get one."""

        if conversation.thread_id:
            return conversation.thread_id
        conversation.thread_id = new_id("thread")
        return conversation.thread_id

    def _persist_thread_if_missing(self, conversation: ChatConversation) -> None:
        if conversation.thread_id:
            return
        self._ensure_thread(conversation)
        conversation.updated_at = utc_now()
        self.store.put(conversation)

    def _bind_profile(self, profile_id: str | None) -> str | None:
        if not profile_id:
            return None
        return self.manager.get_profile(profile_id).id

    def _bind_knowledge(
        self,
        *,
        memory_version_refs: list[str] | None,
        skill_version_refs: list[str] | None,
        protected_instruction_version_refs: list[str] | None,
        knowledge_version_refs: list[str] | None,
    ) -> KnowledgeRefs:
        requested = (
            memory_version_refs
            or skill_version_refs
            or protected_instruction_version_refs
            or knowledge_version_refs
        )
        if not requested:
            return KnowledgeRefs()
        return self.knowledge.resolve_refs(
            memory_version_refs=memory_version_refs,
            skill_version_refs=skill_version_refs,
            protected_instruction_version_refs=protected_instruction_version_refs,
            knowledge_version_refs=knowledge_version_refs,
        )

    def _resolve_project(
        self,
        workspace_id: str | None,
        project_path: str | None,
    ) -> tuple[str | None, Path | None]:
        if workspace_id:
            workspace = self.lab.get_workspace(workspace_id)
            resolved = Path(workspace.path).expanduser().resolve()
            if project_path:
                given = Path(project_path).expanduser().resolve()
                if given != resolved:
                    raise ChatError(
                        "project_path does not match the selected workspace path.",
                        code="project_mismatch",
                        status_code=400,
                    )
            if not resolved.is_dir():
                raise ChatError(
                    "Workspace project directory is missing.",
                    code="project_missing",
                    status_code=409,
                )
            return workspace.id, resolved
        if not project_path or not project_path.strip():
            return None, None
        resolved = Path(project_path).expanduser().resolve()
        if not resolved.is_dir():
            raise ChatError(
                "Project workspace path is not a directory.",
                code="project_missing",
                status_code=400,
            )
        return None, resolved

    def _light_view(self, conversation: ChatConversation, *, include_transcript: bool) -> ChatConversationView:
        shown = conversation if include_transcript else conversation.model_copy(update={"transcript": []})
        try:
            deployment = self.manager.get_deployment(conversation.deployment_id)
            deploy_health = report_chat_deploy_health(deployment, None)
        except ManagerError as exc:
            if exc.code != "deployment_missing":
                raise
            deploy_health = ChatDeployHealth(
                deployment_id=conversation.deployment_id,
                deployment_status="missing",
                healthy=False,
                code="deploy_missing",
                message=(
                    "The deployment bound to this conversation is no longer available. "
                    "Select a deployment to continue."
                ),
                detail="The bound deployment record was not found.",
            )
        return ChatConversationView(
            **shown.model_dump(),
            current_run=None,
            events=[],
            pending_cancel_input_ids=self.app_store.pending_chat_submission_cancels(conversation.id),
            continuity=ChatContinuity(
                conversation_id=conversation.id,
                thread_id=conversation.thread_id or "",
                run_ids=list(conversation.run_ids),
                current_run_id=conversation.current_run_id,
            ),
            deploy_health=deploy_health,
            filesystem_tools_available=bool(conversation.project_path),
            shell_tools_available=bool(conversation.project_path),
            enabled_tools=enabled_for_project(bool(conversation.project_path)),
        )

    def _view(self, conversation: ChatConversation, *, persist: bool = False) -> ChatConversationView:
        current: AgentRun | None = None
        events: list[dict[str, object]] = []
        current_run_id = conversation.current_run_id
        if current_run_id:
            try:
                current = self.harness.get_run(current_run_id)
            except HarnessError:
                current = None
            if current is not None:
                events = [event.model_dump(mode="json") for event in current.events]
                if persist:
                    conversation, _terminal = self._reconcile_terminal_assistant(conversation, current)
                    if conversation.current_run_id != current_run_id:
                        current = None
                        events = []
                        if conversation.current_run_id:
                            try:
                                current = self.harness.get_run(conversation.current_run_id)
                            except HarnessError:
                                current = None
                            if current is not None:
                                events = [event.model_dump(mode="json") for event in current.events]
        thread_id = conversation.thread_id or ""
        try:
            deployment = self.manager.get_deployment(conversation.deployment_id)
            deploy_health = report_chat_deploy_health(deployment, current)
        except ManagerError as exc:
            if exc.code != "deployment_missing":
                raise
            deploy_health = ChatDeployHealth(
                deployment_id=conversation.deployment_id,
                deployment_status="missing",
                healthy=False,
                code="deploy_missing",
                message=(
                    "The deployment bound to this conversation is no longer available. "
                    "Select a deployment to continue."
                ),
                detail="The bound deployment record was not found.",
            )
        return ChatConversationView(
            **conversation.model_dump(),
            current_run=current,
            events=events,
            pending_cancel_input_ids=self.app_store.pending_chat_submission_cancels(conversation.id),
            continuity=ChatContinuity(
                conversation_id=conversation.id,
                thread_id=thread_id,
                run_ids=list(conversation.run_ids),
                current_run_id=conversation.current_run_id,
            ),
            deploy_health=deploy_health,
            filesystem_tools_available=bool(conversation.project_path),
            shell_tools_available=bool(conversation.project_path),
            enabled_tools=enabled_for_project(bool(conversation.project_path)),
        )

    def _reconcile_terminal_assistant(
        self,
        conversation: ChatConversation,
        run: AgentRun | None = None,
    ) -> tuple[ChatConversation, str | None]:
        if not conversation.current_run_id:
            return conversation, None
        if run is None:
            try:
                run = self.harness.get_run(conversation.current_run_id)
            except HarnessError:
                return conversation, None
        if run.status.value not in {"completed", "failed", "cancelled"}:
            return conversation, None
        input_message_id = getattr(run, "input_message_id", None)
        if input_message_id:
            self.app_store.resolve_chat_submission_cancel(
                conversation.id,
                input_message_id,
                run_id=run.id,
            )
        conversation = self._update_branch_head(conversation, run)
        message = self._assistant_message(conversation, run)
        if message is None:
            return conversation, run.status.value
        updated = self.store.append_message_once(conversation.id, message, run_id=run.id)
        return updated or conversation, run.status.value

    def _update_branch_head(self, conversation: ChatConversation, run: AgentRun) -> ChatConversation:
        checkpoint_id = self._latest_retained_checkpoint_id(run)
        if not checkpoint_id or conversation.branch_head_checkpoint_id == checkpoint_id:
            return conversation
        updated = conversation.model_copy(deep=True)
        updated.branch_head_checkpoint_id = checkpoint_id
        updated.updated_at = utc_now()
        return self.store.put(updated)

    def _latest_retained_checkpoint_id(self, run: AgentRun) -> str | None:
        retained = set(run.checkpoint_ids)
        if not run.thread_id or not retained:
            return None
        for saved in checkpoint_history(self.manager.paths.checkpoints_db, {"configurable": {"thread_id": run.thread_id, "checkpoint_ns": ""}}):
            ident = saved.config["configurable"]["checkpoint_id"]
            if ident in retained:
                return ident
        return None

    def _pause_queue(self, conversation: ChatConversation, reason: str) -> ChatConversation:
        if not any(item.status == "queued" for item in conversation.queue):
            return conversation
        paused = conversation.model_copy(deep=True)
        for item in paused.queue:
                if item.status == "queued":
                    item.status = "paused"
                    item.pause_reason = "failed" if reason == "failed" else "cancelled"
                    item.pause_error_code = reason
                    item.pause_error = f"Queue paused because the previous turn {reason}."
                    item.updated_at = utc_now()
        paused.updated_at = utc_now()
        return self.store.put(paused)

    def _assistant_message(self, conversation: ChatConversation, run: AgentRun) -> ChatMessage | None:
        if conversation.history_replaced:
            return None
        if run.status.value not in {"completed", "failed", "cancelled"}:
            return None
        if any(item.run_id == run.id and item.role == "assistant" for item in conversation.transcript):
            return None
        latest = next((event.detail for event in reversed(run.events) if event.kind == "assistant_message"), {})
        text = latest.get("content") if isinstance(latest.get("content"), str) else ""
        blocks = latest.get("content_blocks") or None
        if not text and not blocks:
            return None
        return ChatMessage(id=latest.get("message_id"), role="assistant", content=text or "", content_blocks=blocks,
                           at=run.finished_at or utc_now(), run_id=run.id)
