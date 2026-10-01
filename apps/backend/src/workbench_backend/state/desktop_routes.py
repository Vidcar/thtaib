"""Desktop attention and deliberate shutdown of work owned by this backend."""
import time
import hashlib
import json

from fastapi import APIRouter, Request, BackgroundTasks
from pydantic import BaseModel

from workbench_backend.contracts.lifecycle import LIVE_RUN_LIFECYCLE_STATUSES, is_run_lifecycle_live
from workbench_backend.errors import WorkbenchError
from workbench_backend.state.maintenance import MaintenanceError
from workbench_backend.state.checkpointer import submit_checkpoint_task

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
    success_notifications = state.preferences.preferences().success_notifications
    if success_notifications:
        wanted.add("completed")
    items = []
    for run in state.app_store.list_run_attention(wanted):
        pending = run.pending_interrupt
        kind = (
            "question" if pending and "ask_user" in pending.action_names
            else "approval" if pending
            else "failure" if run.status == "failed"
            else "success" if run.status == "completed" and success_notifications
            else None
        )
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
    runs = [run.id for run in state.harness.list_run_lifecycle(statuses=set(LIVE_RUN_LIFECYCLE_STATUSES), details=False)]
    lab = getattr(state, "lab_workbench", None)
    if lab is not None:
        runs.extend(run.id for run in lab.list_runs() if run.status in {"queued", "running", "stopping"})
    imports = [job.id for job in state.manager.imports.list_jobs() if job.status.value in {"pending", "running", "stopping"}]
    return {"active_run_ids": runs, "active_import_ids": imports}


@router.post("/stop-owned-work")
def stop_owned_work(request: Request, background_tasks: BackgroundTasks) -> dict:
    state = request.app.state
    try:
        state.maintenance_gate.begin("desktop_quit")
    except MaintenanceError as exc:
        # Failed admission belongs to the existing maintenance owner. Do not
        # release its gate or signal the server to shut down.
        raise WorkbenchError(str(exc), code=exc.code, status_code=409) from exc
    try:
        lab = getattr(state, "lab_workbench", None)
        if lab is not None:
            lab.leave()
        for conversation in state.chat.store.list_conversations(include_archived=True):
            with state.chat.store.conversation_lock(conversation.id):
                state.chat._pause_queue(state.chat._require(conversation.id), "cancelled")
        live = state.harness.list_run_lifecycle(statuses=set(LIVE_RUN_LIFECYCLE_STATUSES), details=False)
        for run in live:
            state.harness.cancel(run.id)
        imports = [job for job in state.manager.imports.list_jobs() if job.status.value in {"pending", "running", "stopping"}]
        for job in imports:
            state.manager.imports.cancel_job(job.id)
        deadline = time.monotonic() + 15
        while (any(is_run_lifecycle_live(state.harness.get_run_lifecycle(run.id, details=False).status) for run in live)
               or lab is not None and any(run.status in {"queued", "running", "stopping"} for run in lab.list_runs())
               or any(job.status.value in {"pending", "running", "stopping"} for job in state.manager.imports.list_jobs())):
            if time.monotonic() >= deadline:
                raise WorkbenchError("Some work has not confirmed stopping. Keep the app open and inspect its status.", code="shutdown_pending", status_code=409)
            time.sleep(0.05)
        # A terminal record can precede worker/client/checkpoint cleanup. The
        # harness join is reusable after a failed Quit; it does not close its
        # store or disable future admission when maintenance is released.
        try:
            state.harness.close(timeout=max(0.0, deadline - time.monotonic()))
        except RuntimeError as exc:
            raise WorkbenchError("Some work has not confirmed stopping. Keep the app open and inspect its status.", code="shutdown_pending", status_code=409) from exc
        # Maintenance has drained the coordinator and prevents new dispatch.
        # Settle accepted terminal queue rows using the existing recovery owner;
        # unresolved dispatch/effect evidence remains paused and durable.
        state.chat.reconcile_saved_queue_on_startup(pending_only=True)
        state.manager.stop_owned_deployments_for_quit()
        browser = getattr(state, "browser", None)
        if browser is not None:
            submit_checkpoint_task(state.manager.paths.checkpoints_db, browser.shutdown()).result(timeout=30)
    except Exception:
        state.maintenance_gate.end()
        raise
    shutdown = getattr(state, "shutdown_backend", None)
    if callable(shutdown):
        background_tasks.add_task(shutdown)
    else:
        state.maintenance_gate.end()
    return {"stopped": True, "connected_engines": "left running"}
