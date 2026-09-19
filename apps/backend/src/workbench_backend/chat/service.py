"""Thin Chat coordination. Starts the existing embedded harness only."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from workbench_backend.agents.harness import HarnessService
from workbench_backend.agents.schemas import AgentRun, AgentStartRequest
from workbench_backend.chat.schemas import (
    ChatConversation,
    ChatConversationCreateRequest,
    ChatConversationView,
    ChatMessage,
    ChatStartRequest,
    ChatTranscriptReplaceRequest,
)
from workbench_backend.chat.store import ChatStore
from workbench_backend.errors import ChatError, HarnessError
from workbench_backend.inference.ids import new_id, utc_now
from workbench_backend.inference.service import ModelManager
from workbench_backend.lab.service import LabService
from workbench_backend.paths import WorkbenchPaths
from workbench_backend.state.migrate import open_application_store
from workbench_backend.state.store import ApplicationStore

CHAT_SYSTEM_PROMPT = (
    "You are the Local AI Workbench Chat surface. Complete the user's task "
    "using the embedded Deep Agents harness. Filesystem tools target the bound "
    "project workspace, not conversation history. Do not invent durable "
    "knowledge or retrieval."
)


class ChatService:
    def __init__(
        self,
        manager_provider: Callable[[], ModelManager],
        harness_provider: Callable[[], HarnessService],
        lab_provider: Callable[[], LabService],
        app_store: ApplicationStore | None = None,
    ) -> None:
        self._manager_provider = manager_provider
        self._harness_provider = harness_provider
        self._lab_provider = lab_provider
        self._app_store = app_store

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
        now = utc_now()
        conversation = ChatConversation(
            id=new_id("chat"),
            deployment_id=request.deployment_id,
            profile_id=profile_id,
            project_path=str(project_path),
            workspace_id=workspace_id,
            created_at=now,
            updated_at=now,
        )
        return self._view(self.store.put(conversation))

    def list_conversations(self) -> list[ChatConversationView]:
        return [self._view(item) for item in self.store.list_conversations()]

    def get(self, conversation_id: str) -> ChatConversationView:
        return self._view(self._require(conversation_id), persist=True)

    def start(self, conversation_id: str, request: ChatStartRequest) -> ChatConversationView:
        conversation = self._require(conversation_id)
        if request.deployment_id:
            self.manager.get_deployment(request.deployment_id)
            conversation.deployment_id = request.deployment_id
        if request.profile_id is not None:
            conversation.profile_id = self._bind_profile(request.profile_id)
        if request.project_path or request.workspace_id:
            workspace_id, project_path = self._resolve_project(request.workspace_id, request.project_path)
            conversation.workspace_id = workspace_id
            conversation.project_path = str(project_path)
        if conversation.current_run_id:
            current = self.harness.get_run(conversation.current_run_id)
            if current.status.value in {"queued", "running"}:
                raise ChatError(
                    "A Chat turn is already running on this conversation.",
                    code="chat_turn_active",
                    status_code=409,
                )
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
                    system_prompt=CHAT_SYSTEM_PROMPT,
                    workspace_id=conversation.workspace_id,
                    project_path=conversation.project_path,
                    profile_id=conversation.profile_id,
                    source_surface="chat",
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

    def replace_transcript(
        self,
        conversation_id: str,
        request: ChatTranscriptReplaceRequest,
    ) -> ChatConversationView:
        """Replace displayed history only. Project files are not touched (STATE-002)."""

        conversation = self._require(conversation_id)
        conversation.transcript = list(request.messages)
        conversation.history_replaced = True
        conversation.updated_at = utc_now()
        return self._view(self.store.put(conversation))

    def _require(self, conversation_id: str) -> ChatConversation:
        conversation = self.store.get(conversation_id)
        if conversation is None:
            raise ChatError("Unknown Chat conversation", code="chat_missing", status_code=404)
        return conversation

    def _bind_profile(self, profile_id: str | None) -> str | None:
        if not profile_id:
            return None
        return self.manager.get_profile(profile_id).id

    def _resolve_project(
        self,
        workspace_id: str | None,
        project_path: str | None,
    ) -> tuple[str | None, Path]:
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
            raise ChatError(
                "Chat requires a project workspace path (STATE-002).",
                code="project_required",
                status_code=400,
            )
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
        return ChatConversationView(
            **conversation.model_dump(),
            current_run=current,
            events=events,
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
