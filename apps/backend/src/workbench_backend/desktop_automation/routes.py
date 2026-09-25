"""Authenticated setup endpoints for optional Windows window testing."""

from __future__ import annotations

import asyncio
from typing import Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field

from workbench_backend.desktop_automation.runtime import WINAPP_VERSION, WinAppRuntimeError
from workbench_backend.desktop_automation.service import (
    DesktopAccessScope,
    DesktopAutomationError,
    DesktopAutomationService,
    DesktopWindow,
)
from workbench_backend.errors import WorkbenchError

router = APIRouter(prefix="/v1/window-testing")


class DesktopRuntimeStatus(BaseModel):
    available: bool
    version: str = WINAPP_VERSION
    reason: str | None = None


class DesktopWindowView(BaseModel):
    hwnd: int
    process_id: int
    process_name: str
    title: str
    width: int
    height: int
    owner_hwnd: int
    class_name: str
    is_foreground: bool
    process_created_at: float


class DesktopScopeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scope: Literal["off", "selected", "all"]
    hwnd: int | None = Field(default=None, gt=0)


class DesktopScopeView(BaseModel):
    scope: Literal["off", "selected", "all"]
    selected_window: DesktopWindowView | None = None
    stale: bool = False


def _service(request: Request) -> DesktopAutomationService:
    return request.app.state.desktop_automation


def _thread_id(request: Request, conversation_id: str) -> str:
    store = request.app.state.chat.store
    with store.conversation_lock(conversation_id):
        conversation = store.get(conversation_id)
    if conversation is None:
        raise WorkbenchError("Unknown Chat conversation.", code="chat_missing", status_code=404)
    if not conversation.thread_id:
        raise WorkbenchError("This conversation has no active thread.",
            code="desktop_thread_missing", status_code=409)
    return conversation.thread_id


def _window_view(window: DesktopWindow) -> DesktopWindowView:
    return DesktopWindowView.model_validate(window.public_dict())


def _worker_error(exc: DesktopAutomationError | WinAppRuntimeError) -> WorkbenchError:
    if isinstance(exc, DesktopAutomationError):
        return WorkbenchError(str(exc), code=exc.code,
            status_code=400 if exc.code == "desktop_invalid_arguments" else 409)
    return WorkbenchError(str(exc), code="desktop_runtime_unavailable", status_code=409)


def _runtime_status(service: DesktopAutomationService) -> DesktopRuntimeStatus:
    try:
        service.runtime.command_path()
    except WinAppRuntimeError as exc:
        return DesktopRuntimeStatus(available=False, reason=str(exc))
    return DesktopRuntimeStatus(available=True)


def _scope_view(service: DesktopAutomationService, thread_id: str) -> DesktopScopeView:
    scope, _selected = service.scope_for_thread(thread_id)
    if scope is not DesktopAccessScope.selected:
        return DesktopScopeView(scope=scope.value)
    try:
        windows = service.list_windows(thread_id)
    except (DesktopAutomationError, WinAppRuntimeError):
        return DesktopScopeView(scope="selected", stale=True)
    return DesktopScopeView(scope="selected", selected_window=_window_view(windows[0]))


@router.get("/runtime", response_model=DesktopRuntimeStatus)
def runtime_status(request: Request) -> DesktopRuntimeStatus:
    return _runtime_status(_service(request))


@router.post("/runtime/install", response_model=DesktopRuntimeStatus)
async def install_runtime(request: Request) -> DesktopRuntimeStatus:
    service = _service(request)
    try:
        await asyncio.to_thread(service.install)
    except (DesktopAutomationError, WinAppRuntimeError) as exc:
        raise _worker_error(exc) from exc
    return _runtime_status(service)


@router.get("/windows", response_model=list[DesktopWindowView])
def picker_windows(request: Request) -> list[DesktopWindowView]:
    try:
        service = _service(request)
        service.runtime.command_path()
        return [_window_view(window) for window in service.picker_windows()]
    except (DesktopAutomationError, WinAppRuntimeError) as exc:
        raise _worker_error(exc) from exc


@router.get("/conversations/{conversation_id}/scope", response_model=DesktopScopeView)
def conversation_scope(request: Request, conversation_id: str) -> DesktopScopeView:
    thread_id = _thread_id(request, conversation_id)
    return _scope_view(_service(request), thread_id)


@router.put("/conversations/{conversation_id}/scope", response_model=DesktopScopeView)
def set_conversation_scope(request: Request, conversation_id: str,
                           body: DesktopScopeRequest) -> DesktopScopeView:
    thread_id = _thread_id(request, conversation_id)
    service = _service(request)
    try:
        if body.scope != "off":
            service.runtime.command_path()
        service.set_scope(thread_id, body.scope, body.hwnd)
    except (DesktopAutomationError, WinAppRuntimeError) as exc:
        raise _worker_error(exc) from exc
    return _scope_view(service, thread_id)
