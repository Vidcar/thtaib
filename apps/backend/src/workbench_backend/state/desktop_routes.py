"""Desktop attention and deliberate shutdown of work owned by this backend."""
import time
import hashlib
import json

from fastapi import APIRouter, Request, BackgroundTasks
from pydantic import BaseModel

from workbench_backend.contracts.lifecycle import is_run_lifecycle_live
from workbench_backend.errors import WorkbenchError

router = APIRouter(prefix="/v1/desktop")


class AttentionItem(BaseModel):
    run_id: str
    conversation_id: str | None
    title: str
    kind: str
    identity: str
    notified: bool = False


def _conversation_for_run(conversations, run_id: str):
    current = next((conversation for conversation in conversations if conversation.current_run_id == run_id), None)
    if current is not None:
        return current
    return next((conversation for conversation in conversations if run_id in conversation.run_ids), None)


@router.get("/attention")
def attention(request: Request) -> list[AttentionItem]:
    state = request.app.state
    conversations = state.chat.store.list_conversations(include_archived=True)
    wanted = {"failed", "queued", "running", "cancel_requested"}
    if state.preferences.preferences().success_notifications:
        wanted.add("completed")
    items = []
    for run_id, _status in state.app_store.run_ids_with_status(wanted):
        run = state.app_store.get_run(run_id)
        if run is None:
            continue
        kind = "question" if run.pending_interrupt and run.pending_interrupt.kind == "ask_user" else "approval" if run.pending_interrupt else "failure" if run.status == "failed" else "success" if run.status == "completed" and state.preferences.preferences().success_notifications else None
        if kind is None or run.status == "cancel_requested":
            continue
        owner = _conversation_for_run(conversations, run.id)
        if run.source_surface == "chat" and owner is None:
            continue
        fingerprint = run.pending_interrupt.interrupt_id if run.pending_interrupt else hashlib.sha256(
            json.dumps({"checkpoints": sorted(run.checkpoint_ids), "finished": run.finished_at}, sort_keys=True).encode()).hexdigest()[:24]
        identity = f"{run.id}:{kind}:{fingerprint}"
        if state.preferences.attention_hidden(identity, run.id):
            continue
        items.append(AttentionItem(run_id=run.id, conversation_id=owner.id if owner else None,
            title=owner.title or "Chat" if owner else "Agent run", kind=kind,
            identity=identity, notified=state.preferences.notification_sent(identity)))
    return items


@router.post("/attention/{identity}/dismiss")
def dismiss_attention(request: Request, identity: str) -> dict:
    request.app.state.preferences.dismiss_attention(identity)
    return {"dismissed": True}


@router.post("/attention/{identity}/claim")
def claim_notification(request: Request, identity: str) -> dict:
    if not any(item.identity == identity for item in attention(request)):
        raise WorkbenchError("This attention item is no longer current.", code="attention_stale", status_code=409)
    return {"claimed": request.app.state.preferences.notification_claim(identity)}


@router.get("/work")
def active_work(request: Request) -> dict:
    state = request.app.state
    runs = [run.id for run in state.harness.list_runs() if is_run_lifecycle_live(run.status)]
    imports = [job.id for job in state.manager.imports.list_jobs() if job.status.value in {"pending", "running", "stopping"}]
    return {"active_run_ids": runs, "active_import_ids": imports}


@router.post("/stop-owned-work")
def stop_owned_work(request: Request, background_tasks: BackgroundTasks) -> dict:
    state = request.app.state
    state.maintenance_gate.begin("desktop_quit")
    try:
        for conversation in state.chat.store.list_conversations(include_archived=True):
            with state.chat.store.conversation_lock(conversation.id):
                state.chat._pause_queue(state.chat._require(conversation.id), "cancelled")
        live = [run for run in state.harness.list_runs() if is_run_lifecycle_live(run.status)]
        for run in live:
            state.harness.cancel(run.id)
        imports = [job for job in state.manager.imports.list_jobs() if job.status.value in {"pending", "running", "stopping"}]
        for job in imports:
            state.manager.imports.cancel_job(job.id)
        deadline = time.monotonic() + 15
        while (any(is_run_lifecycle_live(state.harness.get_run(run.id).status) for run in live)
               or any(job.status.value in {"pending", "running", "stopping"} for job in state.manager.imports.list_jobs())):
            if time.monotonic() >= deadline:
                raise WorkbenchError("Some work has not confirmed stopping. Keep the app open and inspect its status.", code="shutdown_pending", status_code=409)
            time.sleep(0.05)
        for deployment in state.manager.list_deployments():
            if deployment.scope == "managed" and deployment.status == "running":
                state.manager.stop_deployment(deployment.id)
    except Exception:
        state.maintenance_gate.end()
        raise
    shutdown = getattr(state, "shutdown_backend", None)
    if callable(shutdown):
        background_tasks.add_task(shutdown)
    else:
        state.maintenance_gate.end()
    return {"stopped": True, "connected_engines": "left running"}
