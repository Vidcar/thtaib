"""Chat conversation records. Displayed history is not the working project."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field
from workbench_backend.inference.user_content import UserContentBlock
from workbench_backend.agents.structured import OutputSchemaRequest

from workbench_backend.agents.schemas import AgentRun, InterruptDecisionRequest

# Re-export so Chat routes can accept the same HITL payload as agent-runs.
ChatInterruptDecisionRequest = InterruptDecisionRequest


class ChatMessage(BaseModel):
    id: str | None = None
    role: Literal["user", "assistant", "system"]
    content: str
    # Display archives also retain upstream assistant reasoning/tool blocks.
    # Execution input remains separately validated by ChatStartRequest.
    content_blocks: list[dict[str, Any]] | None = None
    at: str
    run_id: str | None = None


class ChatConversationCreateRequest(BaseModel):
    deployment_id: str
    project_path: str | None = None
    workspace_id: str | None = None
    profile_id: str | None = None
    inherit_deployment_settings: bool = True
    memory_version_refs: list[str] = Field(default_factory=list)
    skill_version_refs: list[str] = Field(default_factory=list)
    protected_instruction_version_refs: list[str] = Field(default_factory=list)
    knowledge_version_refs: list[str] = Field(default_factory=list)
    embedding_deployment_id: str | None = None
    retrieval_project_paths: list[str] = Field(default_factory=list)


class ChatStartRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    task: str
    input_message_id: str | None = Field(default=None, min_length=1, max_length=200)
    content_blocks: list[UserContentBlock] | None = Field(default=None, max_length=32)
    output_schema: OutputSchemaRequest | None = None
    deployment_id: str | None = None
    profile_id: str | None = None
    inherit_deployment_settings: bool = True
    project_path: str | None = None
    workspace_id: str | None = None
    presented_tools: list[str] | None = None
    memory_version_refs: list[str] | None = None
    skill_version_refs: list[str] | None = None
    protected_instruction_version_refs: list[str] | None = None
    knowledge_version_refs: list[str] | None = None
    embedding_deployment_id: str | None = None
    retrieval_project_paths: list[str] | None = None


class ChatTranscriptReplaceRequest(BaseModel):
    messages: list[ChatMessage] = Field(default_factory=list)


class ChatDeployHealth(BaseModel):
    """Chat-facing deploy/connection honesty (Issue #78). Not OQ-012 traces."""

    deployment_id: str
    deployment_status: str
    healthy: bool | None = None
    code: Literal["deploy_unhealthy", "deploy_unreachable", "deploy_missing"] | None = None
    message: str | None = None
    detail: str | None = None
    note: str = (
        "Live Chat completion requires a healthy managed/connected llama.cpp. "
        "Harness model_requests and thread reuse prove continuity only — not "
        "live assistant completion. David-PC UAT must check deploy health "
        "before treating a reply as live proof."
    )


class ChatContinuity(BaseModel):
    """Documented conversation ↔ thread ↔ run linkage (Issue #56)."""

    conversation_id: str
    thread_id: str
    run_ids: list[str] = Field(default_factory=list)
    current_run_id: str | None = None
    transcript_is_harness_context: Literal[False] = False
    history_edit_effect: Literal["display_only"] = "display_only"
    model_switch_effect: Literal["same_thread_new_run"] = "same_thread_new_run"
    fresh_conversation_effect: Literal["new_thread_retain_project_and_knowledge"] = (
        "new_thread_retain_project_and_knowledge"
    )
    note: str = (
        "Follow-ups reuse conversation.thread_id on the embedded harness "
        "checkpointer. Displayed transcript is not the execution context. "
        "History edits do not restore or delete project files and do not "
        "rewrite the LangGraph thread. A model/profile change applies to the "
        "next run on the same thread. A fresh conversation allocates a new "
        "thread; project files and permitted durable knowledge stay."
    )


class ChatConversation(BaseModel):
    id: str
    deployment_id: str
    profile_id: str | None = None
    inherit_deployment_settings: bool = True
    project_path: str | None = None
    workspace_id: str | None = None
    thread_id: str | None = None
    transcript: list[ChatMessage] = Field(default_factory=list)
    current_run_id: str | None = None
    run_ids: list[str] = Field(default_factory=list)
    history_replaced: bool = False
    harness: Literal["deepagents"] = "deepagents"
    second_agent_loop: Literal[False] = False
    source_surface: Literal["chat"] = "chat"
    memory_version_refs: list[str] = Field(default_factory=list)
    skill_version_refs: list[str] = Field(default_factory=list)
    protected_instruction_version_refs: list[str] = Field(default_factory=list)
    embedding_deployment_id: str | None = None
    retrieval_project_paths: list[str] = Field(default_factory=list)
    created_at: str
    updated_at: str


class ChatConversationView(ChatConversation):
    current_run: AgentRun | None = None
    events: list[dict[str, Any]] = Field(default_factory=list)
    continuity: ChatContinuity | None = None
    deploy_health: ChatDeployHealth | None = None
    filesystem_tools_available: bool = False
    shell_tools_available: bool = False
    enabled_tools: list[str] = Field(default_factory=list)
    note: str = (
        "Debug-quality Chat. The embedded Deep Agents harness owns model/tool "
        "iteration. Follow-ups resume conversation.thread_id. Transcript is "
        "displayed history, not the working project and not harness context. "
        "A project folder is optional; filesystem and host-shell tools are "
        "unavailable without one. Host-shell execute pauses on Deep Agents "
        "interrupt_on; this is not a durable Approvals inbox (OQ-011)."
    )
