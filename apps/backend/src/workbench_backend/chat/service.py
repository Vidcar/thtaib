"""Thin Chat coordination. Starts the existing embedded harness only."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from workbench_backend.agents.harness import HarnessService
from workbench_backend.agents.schemas import AgentRun, AgentStartRequest, InterruptDecisionRequest
from workbench_backend.agents.tools import enabled_for_project
from workbench_backend.chat.deploy_health import report_chat_deploy_health
from workbench_backend.chat.schemas import (
    ChatContinuity,
    ChatConversation,
    ChatConversationCreateRequest,
    ChatConversationView,
    ChatMessage,
    ChatStartRequest,
    ChatTranscriptReplaceRequest,
)
from workbench_backend.chat.store import ChatStore
from workbench_backend.contracts.lifecycle import is_run_lifecycle_live
from workbench_backend.errors import ChatError, HarnessError
from workbench_backend.inference.ids import new_id, utc_now
from workbench_backend.inference.service import ModelManager
from workbench_backend.knowledge.schemas import KnowledgeRefs
from workbench_backend.knowledge.service import KnowledgeService
from workbench_backend.lab.service import LabService
from workbench_backend.paths import WorkbenchPaths
from workbench_backend.state.migrate import open_application_store
from workbench_backend.state.store import ApplicationStore

CHAT_SYSTEM_PROMPT = (
    "You are the Local AI Workbench Chat surface. Complete the user's task "
    "using the embedded Deep Agents harness. Filesystem tools target the bound "
    "project workspace, not conversation history. The host shell execute tool "
    "runs on this machine in the project working directory with no isolation; "
    "dangerous commands pause for approval. Do not invent durable knowledge "
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
    ) -> None:
        self._manager_provider = manager_provider
        self._harness_provider = harness_provider
        self._lab_provider = lab_provider
        self._app_store = app_store
        self._knowledge_provider = knowledge_provider

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
        conversation = ChatConversation(
            id=new_id("chat"),
            deployment_id=request.deployment_id,
            profile_id=profile_id,
            project_path=str(project_path) if project_path is not None else None,
            workspace_id=workspace_id,
            thread_id=new_id("thread"),
            memory_version_refs=refs.memory_version_refs,
            skill_version_refs=refs.skill_version_refs,
            protected_instruction_version_refs=refs.protected_instruction_version_refs,
            created_at=now,
            updated_at=now,
        )
        return self._view(self.store.put(conversation))

    def list_conversations(self) -> list[ChatConversationView]:
        views: list[ChatConversationView] = []
        for item in self.store.list_conversations():
            self._persist_thread_if_missing(item)
            views.append(self._view(item))
        return views

    def get(self, conversation_id: str) -> ChatConversationView:
        conversation = self._require(conversation_id)
        self._persist_thread_if_missing(conversation)
        return self._view(conversation, persist=True)

    def start(self, conversation_id: str, request: ChatStartRequest) -> ChatConversationView:
        conversation = self._require(conversation_id)
        if request.deployment_id:
            self.manager.get_deployment(request.deployment_id)
            conversation.deployment_id = request.deployment_id
        if request.profile_id is not None:
            conversation.profile_id = self._bind_profile(request.profile_id)
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
        if request.project_path or request.workspace_id:
            workspace_id, project_path = self._resolve_project(request.workspace_id, request.project_path)
            conversation.workspace_id = workspace_id
            conversation.project_path = str(project_path) if project_path is not None else None
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
        self._ensure_thread(conversation)
        task = request.task.strip()
        if not task:
            raise ChatError("Compose text is required.", code="task_required", status_code=400)
        now = utc_now()
        conversation.history_replaced = False
        conversation.transcript.append(ChatMessage(role="user", content=task, at=now))
        try:
            started = self.harness.start(
                AgentStartRequest(
                    deployment_id=conversation.deployment_id,
                    task=task,
                    presented_tools=request.presented_tools,
                    system_prompt=(
                        CHAT_SYSTEM_PROMPT
                        if conversation.project_path
                        else CHAT_SYSTEM_PROMPT_WITHOUT_PROJECT
                    ),
                    workspace_id=conversation.workspace_id,
                    project_path=conversation.project_path,
                    profile_id=conversation.profile_id,
                    source_surface="chat",
                    thread_id=conversation.thread_id,
                    memory_version_refs=conversation.memory_version_refs,
                    skill_version_refs=conversation.skill_version_refs,
                    protected_instruction_version_refs=conversation.protected_instruction_version_refs,
                )
            )
        except HarnessError:
            conversation.updated_at = utc_now()
            self.store.put(conversation)
            raise
        conversation.current_run_id = started.id
        conversation.run_ids.append(started.id)
        conversation.updated_at = utc_now()
        self.store.put(conversation)
        return self._view(conversation)

    def cancel(self, conversation_id: str) -> ChatConversationView:
        conversation = self._require(conversation_id)
        if not conversation.current_run_id:
            raise ChatError("No active Chat run to cancel.", code="chat_run_missing", status_code=409)
        self.harness.cancel(conversation.current_run_id)
        conversation.updated_at = utc_now()
        return self._view(self.store.put(conversation), persist=True)

    def resume_interrupt(
        self,
        conversation_id: str,
        request: InterruptDecisionRequest,
    ) -> ChatConversationView:
        conversation = self._require(conversation_id)
        if not conversation.current_run_id:
            raise ChatError(
                "No active Chat run for a host-shell interrupt decision.",
                code="chat_run_missing",
                status_code=409,
            )
        self.harness.resume_interrupt(conversation.current_run_id, request)
        conversation.updated_at = utc_now()
        return self._view(self.store.put(conversation), persist=True)

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

        conversation = self._require(conversation_id)
        self._ensure_thread(conversation)
        conversation.transcript = list(request.messages)
        conversation.history_replaced = True
        conversation.updated_at = utc_now()
        return self._view(self.store.put(conversation))

    def _require(self, conversation_id: str) -> ChatConversation:
        conversation = self.store.get(conversation_id)
        if conversation is None:
            raise ChatError("Unknown Chat conversation", code="chat_missing", status_code=404)
        return conversation

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

    def _view(self, conversation: ChatConversation, *, persist: bool = False) -> ChatConversationView:
        current: AgentRun | None = None
        events: list[dict[str, object]] = []
        if conversation.current_run_id:
            try:
                current = self.harness.get_run(conversation.current_run_id)
            except HarnessError:
                current = None
            if current is not None:
                events = [event.model_dump(mode="json") for event in current.events]
                if self._maybe_append_assistant(conversation, current) and persist:
                    self.store.put(conversation)
        thread_id = conversation.thread_id or ""
        deployment = self.manager.get_deployment(conversation.deployment_id)
        return ChatConversationView(
            **conversation.model_dump(),
            current_run=current,
            events=events,
            continuity=ChatContinuity(
                conversation_id=conversation.id,
                thread_id=thread_id,
                run_ids=list(conversation.run_ids),
                current_run_id=conversation.current_run_id,
            ),
            deploy_health=report_chat_deploy_health(deployment, current),
            filesystem_tools_available=bool(conversation.project_path),
            shell_tools_available=bool(conversation.project_path),
            enabled_tools=enabled_for_project(bool(conversation.project_path)),
        )

    def _maybe_append_assistant(self, conversation: ChatConversation, run: AgentRun) -> bool:
        if conversation.history_replaced:
            return False
        if run.status.value not in {"completed", "failed", "cancelled"}:
            return False
        if any(item.run_id == run.id and item.role == "assistant" for item in conversation.transcript):
            return False
        text = _assistant_text(run)
        if not text:
            return False
        conversation.transcript.append(
            ChatMessage(role="assistant", content=text, at=run.finished_at or utc_now(), run_id=run.id)
        )
        conversation.updated_at = utc_now()
        return True


def _assistant_text(run: AgentRun) -> str | None:
    for event in reversed(run.events):
        if event.kind != "assistant_message":
            continue
        content = event.detail.get("content")
        if isinstance(content, str) and content.strip():
            return content
    return None
