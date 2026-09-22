from fastapi import APIRouter, Request
from workbench_backend.chat.branches import BranchRequest, ChatBranches, ReplyActions
from workbench_backend.chat.schemas import ChatConversationView

router = APIRouter(prefix="/v1/chat/conversations")


@router.get("/{conversation_id}/replies/{run_id}/actions")
def actions(request: Request, conversation_id: str, run_id: str) -> ReplyActions:
    return ChatBranches(request.app.state.chat).actions(conversation_id, run_id)


@router.post("/{conversation_id}/branches")
def branch(request: Request, conversation_id: str, body: BranchRequest) -> ChatConversationView:
    return ChatBranches(request.app.state.chat).create(conversation_id, body)
