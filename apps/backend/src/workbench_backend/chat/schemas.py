"""Chat conversation records. Displayed history is not the working project."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from workbench_backend.agents.schemas import AgentRun


class ChatMessage(BaseModel):
    role: Literal["user", "assistant", "system"]
    content: str
    at: str
    run_id: str | None = None


class ChatConversationCreateRequest(BaseModel):
    deployment_id: str
    project_path: str | None = None
    workspace_id: str | None = None
    profile_id: str | None = None


class ChatStartRequest(BaseModel):
    task: str
    deployment_id: str | None = None
    profile_id: str | None = None
    project_path: str | None = None
    workspace_id: str | None = None
    presented_tools: list[str] | None = None


class ChatTranscriptReplaceRequest(BaseModel):
    messages: list[ChatMessage] = Field(default_factory=list)


class ChatConversation(BaseModel):
    id: str
    deployment_id: str
    profile_id: str | None = None
    project_path: str
    workspace_id: str | None = None
    transcript: list[ChatMessage] = Field(default_factory=list)
    current_run_id: str | None = None
    run_ids: list[str] = Field(default_factory=list)
    history_replaced: bool = False
    harness: Literal["deepagents"] = "deepagents"
    second_agent_loop: Literal[False] = False
    source_surface: Literal["chat"] = "chat"
    created_at: str
    updated_at: str


class ChatConversationView(ChatConversation):
    current_run: AgentRun | None = None
    events: list[dict[str, Any]] = Field(default_factory=list)
    note: str = (
        "Debug-quality Chat. The embedded Deep Agents harness owns model/tool "
        "iteration. Transcript is displayed history, not the working project."
    )
