"""Explicit setup and session controls for the owned browser worker."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Request

from workbench_backend.state.checkpointer import submit_checkpoint_task

router = APIRouter(prefix="/v1/browser")


@router.get("/runtime")
def runtime_status(request: Request):
    return request.app.state.browser.runtime.status()


@router.post("/runtime/install")
async def install_runtime(request: Request):
    return await asyncio.to_thread(request.app.state.browser.runtime.install)


@router.get("/sessions/{thread_id}")
def session_status(request: Request, thread_id: str):
    return request.app.state.browser.status(thread_id)


@router.post("/sessions/{thread_id}/reset")
async def reset_session(request: Request, thread_id: str):
    future = submit_checkpoint_task(request.app.state.manager.paths.checkpoints_db, request.app.state.browser.reset(thread_id))
    return await asyncio.wrap_future(future)


@router.delete("/sessions/{thread_id}")
async def close_session(request: Request, thread_id: str):
    future = submit_checkpoint_task(request.app.state.manager.paths.checkpoints_db, request.app.state.browser.close_session(thread_id))
    await asyncio.wrap_future(future)
    return request.app.state.browser.status(thread_id)
