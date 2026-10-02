"""Checkpoint branching is no longer offered. Retry and Edit rewind the same chat."""

from typing import Literal

from pydantic import BaseModel, ConfigDict

from workbench_backend.errors import ChatError
from workbench_backend.inference.ids import utc_now
from workbench_backend.state.checkpointer import checkpoint_history


class BranchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_run_id: str
    mode: Literal["continue", "retry", "edit", "regenerate"] = "continue"
    edited_task: str | None = None
    acknowledge_repeated_effects: bool = False


class ReplyActions(BaseModel):
    branch_available: bool
    retry_available: bool
    regenerate_available: bool = False
    branch_reason: str | None = None
    retry_reason: str | None = None
    regenerate_reason: str | None = None


class ChatBranches:

    def __init__(self, chat):
        self.chat = chat

    def actions(self, conversation_id: str, run_id: str) -> ReplyActions:
        self._source(conversation_id, run_id)
        reason = "Branching is not offered."
        return ReplyActions(
            branch_available=False, retry_available=False, regenerate_available=False,
            branch_reason=reason, retry_reason=reason, regenerate_reason=reason,
        )

    def create(self, conversation_id: str, request: BranchRequest):
        del conversation_id, request
        raise ChatError("Branching is not offered.", code="branch_unavailable", status_code=409)

    def _source(self, conversation_id, run_id):
        conversation = self.chat._require(conversation_id)
        if run_id not in conversation.run_ids:
            raise ChatError("This reply does not belong to the conversation.", code="branch_source_missing", status_code=404)
        return conversation, self.chat.harness.get_run_operational(run_id)


def update_branch_head(store, conversation, run, checkpoints_db):
    """Record the newest retained checkpoint as this conversation's branch head."""

    checkpoint_id = latest_retained_checkpoint_id(checkpoints_db, run)
    if not checkpoint_id or conversation.branch_head_checkpoint_id == checkpoint_id:
        return conversation
    updated = conversation.model_copy(deep=True)
    updated.branch_head_checkpoint_id = checkpoint_id
    updated.updated_at = utc_now()
    return store.put(updated)


def latest_retained_checkpoint_id(checkpoints_db, run) -> str | None:
    retained = set(run.checkpoint_ids)
    if not run.thread_id or not retained:
        return None
    for saved in checkpoint_history(checkpoints_db, {"configurable": {"thread_id": run.thread_id, "checkpoint_ns": ""}}):
        ident = saved.config["configurable"]["checkpoint_id"]
        if ident in retained:
            return ident
    return None
