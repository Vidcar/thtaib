"""Authenticated browser viewing and typed controls for the owning Chat."""
from __future__ import annotations

import asyncio
import json
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from workbench_backend.agents.setup_schemas import SetupConfiguration
from workbench_backend.browser.schemas import BrowserActionRequest, BrowserControlRequest, BrowserResetRequest, BrowserRuntimeStatus, BrowserSessionStatus
from workbench_backend.browser.service import BROWSER_TOOL_NAMES
from workbench_backend.contracts.lifecycle import is_run_lifecycle_live
from workbench_backend.errors import HarnessError
from workbench_backend.state.checkpointer import submit_checkpoint_task

router = APIRouter(prefix="/v1/browser")

def _owner(request: Request, thread_id: str, *, selected: bool = False):
    conversation = request.app.state.assets.session_for_thread(thread_id)
    if conversation is None:
        raise HarnessError("Browser chat not found.", code="browser_chat_not_found", status_code=404)
    if selected:
        run = request.app.state.app_store.get_run(conversation.current_run_id) if conversation.current_run_id else None
        if run and is_run_lifecycle_live(run.status):
            tools, mode = run.presented_tools, run.work_mode
        else:
            values = conversation.setup_overrides.model_dump(exclude_none=True)
            values.update(work_mode=conversation.work_mode)
            if conversation.presented_tools is not None:
                values["presented_tools"] = conversation.presented_tools
            resolved = request.app.state.setups.resolve(project_id=conversation.project_id,
                agent_setup_version_id=conversation.agent_setup_version_id,
                overrides=SetupConfiguration.model_validate(values), validate=False, read_only=True)
            tools, mode = resolved.configuration.presented_tools or [], resolved.configuration.work_mode
        if mode != "work" or not set(tools) & set(BROWSER_TOOL_NAMES):
            raise HarnessError("Enable Browser in this chat's Work tools first.", code="browser_not_selected", status_code=403)
    return conversation

async def _on_owner_loop(request: Request, coroutine):
    return await asyncio.wrap_future(submit_checkpoint_task(request.app.state.manager.paths.checkpoints_db, coroutine))

@router.get("/runtime", response_model=BrowserRuntimeStatus)
def runtime_status(request: Request):
    return request.app.state.browser.runtime.status()

@router.post("/runtime/install", response_model=BrowserRuntimeStatus)
async def install_runtime(request: Request):
    return await asyncio.to_thread(request.app.state.browser.runtime.install)

@router.get("/sessions/{thread_id}", response_model=BrowserSessionStatus)
def session_status(request: Request, thread_id: str):
    _owner(request, thread_id)
    return request.app.state.browser.status(thread_id)

@router.post("/sessions/{thread_id}/start", response_model=BrowserSessionStatus)
async def start_session(request: Request, thread_id: str):
    _owner(request, thread_id, selected=True)
    return await _on_owner_loop(request, request.app.state.browser.start(thread_id))

@router.post("/sessions/{thread_id}/control", response_model=BrowserSessionStatus)
async def control_session(request: Request, thread_id: str, body: BrowserControlRequest):
    _owner(request, thread_id, selected=body.action == "take")
    return await _on_owner_loop(request, request.app.state.browser.control(thread_id, body.action, request.app.state.harness))

@router.post("/sessions/{thread_id}/actions", response_model=BrowserSessionStatus)
async def browser_action(request: Request, thread_id: str, body: BrowserActionRequest):
    _owner(request, thread_id, selected=True)
    return await _on_owner_loop(request, request.app.state.browser.manual_action(thread_id, body))

@router.post("/sessions/{thread_id}/reset", response_model=BrowserSessionStatus)
async def reset_session(request: Request, thread_id: str, body: BrowserResetRequest):
    _owner(request, thread_id)
    return await _on_owner_loop(request, request.app.state.browser.reset(thread_id))

@router.delete("/sessions/{thread_id}", response_model=BrowserSessionStatus)
async def close_session(request: Request, thread_id: str):
    _owner(request, thread_id)
    await _on_owner_loop(request, request.app.state.browser.close_session(thread_id))
    return request.app.state.browser.status(thread_id)

@router.get("/sessions/{thread_id}/events")
async def browser_events(request: Request, thread_id: str):
    _owner(request, thread_id)
    browser = request.app.state.browser
    async def events():
        last_state = None
        last_seq = 0
        subscribed_session = None
        try:
            while not await request.is_disconnected():
                _owner(request, thread_id)
                status = browser.status(thread_id)
                if status["session_id"] != subscribed_session:
                    await _on_owner_loop(request, browser.view_subscription(thread_id, True))
                    subscribed_session = status["session_id"]
                    last_seq = 0
                result = await _on_owner_loop(request, browser.poll_view(thread_id, last_seq))
                encoded = json.dumps(result["state"], ensure_ascii=False)
                if encoded != last_state:
                    yield f"event: state\ndata: {encoded}\n\n"
                    last_state = encoded
                frame = result.get("frame")
                if frame:
                    last_seq = frame["seq"]
                    yield f"event: frame\ndata: {json.dumps(frame)}\n\n"
                await asyncio.sleep(0.1)
        finally:
            await _on_owner_loop(request, browser.view_subscription(thread_id, False))
    return StreamingResponse(events(), media_type="text/event-stream", headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})
