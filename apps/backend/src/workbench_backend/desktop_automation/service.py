"""Narrow WinApp CLI adapter for authorized conversation window testing.

Only authenticated application code may set a scope. Agent tools cannot select
their own scope, launch WinApp commands, or choose screenshot output paths.
Every target operation resolves a current HWND/PID/process-start identity.
"""

from __future__ import annotations

import ctypes
import json
import os
import subprocess
import threading
import uuid
from dataclasses import asdict, dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Callable

import psutil
from langchain_core.tools import BaseTool, ToolException, tool
from PIL import Image, UnidentifiedImageError

from workbench_backend.agents.execution_policy import CURRENT_TOOL_CALL
from workbench_backend.agents.harness_backend import harness_scratch_root
from workbench_backend.agents.schemas import AgentRun, ToolMode
from workbench_backend.assets.extraction import MAX_IMAGE_BYTES
from workbench_backend.desktop_automation.runtime import WinAppCliRuntime, WinAppRuntimeError
from workbench_backend.paths import WorkbenchPaths

_MAX_IMAGE_PIXELS = 32_000_000
_MAX_UI_OUTPUT_BYTES = 192_000
_MAX_WINDOWS = 200
DESKTOP_TOOL_NAMES = (
    "desktop_list_windows", "desktop_inspect", "desktop_search", "desktop_wait",
    "desktop_invoke", "desktop_set_value", "desktop_send_keys", "desktop_screenshot",
)


class DesktopAccessScope(str, Enum):
    off = "off"
    selected = "selected"
    all = "all"


class DesktopAutomationError(RuntimeError):
    def __init__(self, message: str, *, code: str = "desktop_unavailable") -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class WindowIdentity:
    hwnd: int
    process_id: int
    process_created_at: float


@dataclass(frozen=True)
class DesktopWindow:
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

    @property
    def identity(self) -> WindowIdentity:
        return WindowIdentity(self.hwnd, self.process_id, self.process_created_at)

    def public_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class DesktopCapture:
    path: Path
    thread_id: str
    window: DesktopWindow
    selector: str | None
    mode: str | None
    width: int
    height: int


@dataclass(frozen=True)
class _ScopeState:
    scope: DesktopAccessScope
    selected: WindowIdentity | None = None


def _windows_identity(hwnd: int) -> WindowIdentity:
    if os.name != "nt":
        raise DesktopAutomationError("Windows window testing is available only on Windows.")
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.IsWindow.argtypes = [wintypes.HWND]
    user32.IsWindow.restype = wintypes.BOOL
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user32.GetWindowThreadProcessId.restype = wintypes.DWORD
    if not user32.IsWindow(hwnd):
        raise DesktopAutomationError("The selected window has closed.", code="desktop_window_changed")
    pid = wintypes.DWORD()
    if not user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid)) or not pid.value:
        raise DesktopAutomationError("The selected window could not be identified.", code="desktop_window_changed")
    try:
        created_at = psutil.Process(pid.value).create_time()
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess) as exc:
        raise DesktopAutomationError("The selected window's process is unavailable.", code="desktop_window_changed") from exc
    return WindowIdentity(hwnd=hwnd, process_id=pid.value, process_created_at=created_at)


def _bounded_string(value: str, *, limit: int, label: str) -> str:
    if not value or len(value) > limit or "\x00" in value:
        raise DesktopAutomationError(f"{label} must contain 1 to {limit} characters.", code="desktop_invalid_arguments")
    return value


class DesktopAutomationService:
    """Optional worker with in-memory, revocable scope per Chat thread.

    `capture_sink` is the retained-asset service's `register_capture` method.
    Its signature is `(run, source_path, *, source_tool_name,
    source_tool_call_id, target, controlled_root) -> (asset, virtual_path)`.
    """

    def __init__(
        self,
        paths: WorkbenchPaths,
        *,
        runtime: WinAppCliRuntime | None = None,
        capture_sink: Callable[..., tuple[Any, str]] | None = None,
        identity_lookup: Callable[[int], WindowIdentity] | None = None,
        command_runner: Callable[[list[str], int], Any] | None = None,
    ) -> None:
        self.paths = paths
        self.runtime = runtime or WinAppCliRuntime(paths)
        self.capture_sink = capture_sink
        self._identity_lookup = identity_lookup or _windows_identity
        self._command_runner = command_runner
        self._scopes: dict[str, _ScopeState] = {}
        self._lock = threading.RLock()

    def available(self) -> bool:
        return self.runtime.available()

    def install(self) -> Path:
        """Called by authenticated setup, never by an agent invocation."""
        return self.runtime.install()

    def picker_windows(self) -> list[DesktopWindow]:
        """Discover target choices for an authenticated window picker."""
        return self._windows()

    def set_scope(self, thread_id: str, scope: DesktopAccessScope | str, hwnd: int | None = None) -> None:
        """Set the exact live selection or broad grant from authenticated UI code."""
        _bounded_string(thread_id, limit=200, label="Conversation thread ID")
        try:
            chosen = DesktopAccessScope(scope)
        except ValueError as exc:
            raise DesktopAutomationError("Unknown desktop access scope.", code="desktop_invalid_arguments") from exc
        if chosen is DesktopAccessScope.off:
            if hwnd is not None:
                raise DesktopAutomationError("Off does not accept a window.", code="desktop_invalid_arguments")
            self.clear_scope(thread_id)
            return
        if chosen is DesktopAccessScope.all:
            if hwnd is not None:
                raise DesktopAutomationError("All windows does not select a window.", code="desktop_invalid_arguments")
            self.runtime.command_path()
            with self._lock:
                self._scopes[thread_id] = _ScopeState(scope=chosen)
            return
        if not isinstance(hwnd, int) or isinstance(hwnd, bool) or hwnd <= 0:
            raise DesktopAutomationError("Choose an open window first.", code="desktop_invalid_arguments")
        window = self._find_window(hwnd)
        with self._lock:
            self._scopes[thread_id] = _ScopeState(scope=chosen, selected=window.identity)

    def clear_scope(self, thread_id: str) -> None:
        with self._lock:
            self._scopes.pop(thread_id, None)

    def scope_for_thread(self, thread_id: str) -> tuple[DesktopAccessScope, WindowIdentity | None]:
        with self._lock:
            state = self._scopes.get(thread_id, _ScopeState(DesktopAccessScope.off))
        return state.scope, state.selected

    def snapshot_grant(self, thread_id: str, desired: DesktopAccessScope | str) -> tuple[DesktopAccessScope, WindowIdentity | None]:
        """Read the live grant used by both Chat preflight and turn admission.

        Saved access is intent, not a grant. Checking the selected window's
        current identity here makes a reopened conversation actionable before
        any model is loaded or a message is committed.
        """
        try:
            requested = DesktopAccessScope(desired)
        except ValueError as exc:
            raise DesktopAutomationError("Unknown desktop access scope.", code="desktop_invalid_arguments") from exc
        current, identity = self.scope_for_thread(thread_id)
        if requested is DesktopAccessScope.off or current is DesktopAccessScope.off:
            raise DesktopAutomationError("Choose a window or explicitly grant All windows for this conversation.",
                code="desktop_grant_required")
        if current is DesktopAccessScope.selected:
            if identity is None:
                raise DesktopAutomationError("Choose a window again.", code="desktop_window_required")
            window = self._find_window(identity.hwnd)
            if window.identity != identity:
                raise DesktopAutomationError("The selected window changed; choose it again.",
                    code="desktop_window_changed")
            return DesktopAccessScope.selected, identity
        if requested is DesktopAccessScope.selected:
            raise DesktopAutomationError("Choose a specific window for Selected window access.",
                code="desktop_window_required")
        return DesktopAccessScope.all, None

    def list_windows(self, thread_id: str, *, _bound: _ScopeState | None = None) -> list[DesktopWindow]:
        scope, selected = self._effective_scope(thread_id, _bound)
        if scope is DesktopAccessScope.off:
            raise DesktopAutomationError("Windows access is off for this conversation.", code="desktop_access_off")
        if scope is DesktopAccessScope.selected:
            if selected is None:
                raise DesktopAutomationError("Choose a window first.", code="desktop_window_required")
            window = self._find_window(selected.hwnd)
            if window.identity != selected:
                raise DesktopAutomationError("The selected window changed; choose it again.", code="desktop_window_changed")
            return [window]
        return self._windows()

    def inspect(self, thread_id: str, *, hwnd: int | None = None, depth: int = 3,
                interactive: bool = False, selector: str | None = None,
                _bound: _ScopeState | None = None) -> dict[str, Any]:
        if not 1 <= depth <= 6:
            raise DesktopAutomationError("Inspection depth must be between 1 and 6.", code="desktop_invalid_arguments")
        args = ["inspect"]
        if selector is not None:
            args.append(_bounded_string(selector, limit=160, label="Selector"))
        args.extend(["--depth", str(depth)])
        if interactive:
            args.append("--interactive")
        return self._target_call(thread_id, hwnd, args, timeout=20, bound=_bound)

    def search(self, thread_id: str, selector: str, *, hwnd: int | None = None,
               max_results: int = 20, _bound: _ScopeState | None = None) -> dict[str, Any]:
        if not 1 <= max_results <= 50:
            raise DesktopAutomationError("Search limit must be between 1 and 50.", code="desktop_invalid_arguments")
        return self._target_call(thread_id, hwnd, ["search", _bounded_string(selector, limit=160, label="Selector"),
            "--max", str(max_results)], timeout=20, allow_nonzero=True, bound=_bound)

    def wait(self, thread_id: str, selector: str, *, hwnd: int | None = None,
             timeout_ms: int = 5_000, value: str | None = None, gone: bool = False,
             _bound: _ScopeState | None = None) -> dict[str, Any]:
        if not 100 <= timeout_ms <= 10_000:
            raise DesktopAutomationError("Wait duration must be 100 to 10000 ms.", code="desktop_invalid_arguments")
        args = ["wait-for", _bounded_string(selector, limit=160, label="Selector"), "--timeout", str(timeout_ms)]
        if value is not None:
            args.extend(["--value", _bounded_string(value, limit=2_000, label="Expected value")])
        if gone:
            args.append("--gone")
        return self._target_call(thread_id, hwnd, args, timeout=timeout_ms // 1_000 + 10,
            allow_nonzero=True, bound=_bound)

    def invoke(self, thread_id: str, selector: str, *, hwnd: int | None = None,
               _bound: _ScopeState | None = None) -> dict[str, Any]:
        return self._target_call(thread_id, hwnd,
            ["invoke", _bounded_string(selector, limit=160, label="Selector")], timeout=20, bound=_bound)

    def set_value(self, thread_id: str, selector: str, value: str, *, hwnd: int | None = None,
                  _bound: _ScopeState | None = None) -> dict[str, Any]:
        if len(value) > 4_000 or "\x00" in value:
            raise DesktopAutomationError("Value exceeds 4000 characters.", code="desktop_invalid_arguments")
        return self._target_call(thread_id, hwnd,
            ["set-value", _bounded_string(selector, limit=160, label="Selector"), value],
            timeout=20, bound=_bound)

    def send_keys(self, thread_id: str, keys: str, *, hwnd: int | None = None,
                  target: str | None = None, _bound: _ScopeState | None = None) -> dict[str, Any]:
        args = ["send-keys", _bounded_string(keys, limit=500, label="Keys")]
        if target:
            args.extend(["--target", _bounded_string(target, limit=160, label="Target")])
        # Omit --via send-input and --allow-system-keys; the command stays
        # targeted to the selected HWND rather than a global input shortcut.
        return self._target_call(thread_id, hwnd, args, timeout=20, bound=_bound)

    def screenshot(self, thread_id: str, *, hwnd: int | None = None,
                   selector: str | None = None, _bound: _ScopeState | None = None) -> DesktopCapture:
        window = self._authorize_window(thread_id, hwnd, bound=_bound)
        capture_dir = harness_scratch_root(self.paths, thread_id) / "captures"
        capture_dir.mkdir(parents=True, exist_ok=True)
        output = (capture_dir / f"desktop-{uuid.uuid4().hex}.png").resolve()
        if not output.is_relative_to(capture_dir.resolve()):
            raise DesktopAutomationError("Capture output is outside the owned directory.", code="desktop_invalid_output")
        args = ["screenshot"]
        if selector is not None:
            args.append(_bounded_string(selector, limit=160, label="Selector"))
        args.extend(["-w", str(window.hwnd), "--output", str(output)])
        verified = False
        try:
            result = self._run_cli(args, timeout=40)
            if self._identity_lookup(window.hwnd) != window.identity:
                raise DesktopAutomationError("The target changed during capture; image was discarded.", code="desktop_window_changed")
            if not output.is_file() or output.is_symlink() or output.stat().st_size > MAX_IMAGE_BYTES:
                raise DesktopAutomationError("The screenshot was missing or exceeded the image limit.", code="desktop_invalid_output")
            with Image.open(output) as image:
                width, height = image.size
                if image.format != "PNG" or width * height > _MAX_IMAGE_PIXELS:
                    raise DesktopAutomationError("The screenshot format or dimensions are unsupported.", code="desktop_invalid_output")
                image.verify()
            verified = True
            return DesktopCapture(
                path=output, thread_id=thread_id, window=window, selector=selector,
                mode=result.get("mode") if isinstance(result, dict) and isinstance(result.get("mode"), str) else None,
                width=width, height=height,
            )
        except (OSError, UnidentifiedImageError, ValueError) as exc:
            raise DesktopAutomationError("The screenshot could not be verified.", code="desktop_invalid_output") from exc
        finally:
            # Failed or rejected captures must never become retained artifacts.
            if not verified and (output.is_file() or output.is_symlink()):
                output.unlink(missing_ok=True)

    def tools_for_run(self, run: AgentRun) -> list[BaseTool]:
        """Build fixed tools for one Work-mode Chat run; each call rechecks scope."""
        if run.work_mode != "work" or not run.thread_id or run.tool_mode is not ToolMode.live_tool:
            return []
        thread_id = run.thread_id
        try:
            run_scope = DesktopAccessScope(getattr(run, "desktop_access", "off"))
        except ValueError:
            return []
        if run_scope is DesktopAccessScope.off:
            return []
        selected_data = getattr(run, "desktop_window", None)
        selected_identity = None
        if isinstance(selected_data, dict):
            try:
                selected_identity = WindowIdentity(
                    hwnd=int(selected_data["hwnd"]),
                    process_id=int(selected_data["process_id"]),
                    process_created_at=float(selected_data["process_created_at"]),
                )
            except (KeyError, TypeError, ValueError):
                return []
        if run_scope is DesktopAccessScope.selected and selected_identity is None:
            return []
        bound = _ScopeState(run_scope, selected_identity)
        try:
            effective_scope, _ = self._effective_scope(thread_id, bound)
        except DesktopAutomationError:
            return []
        if effective_scope is DesktopAccessScope.off:
            return []
        service = self

        def result_of(action: Callable[[], Any]) -> str:
            try:
                return json.dumps(action(), ensure_ascii=False, separators=(",", ":"))
            except (DesktopAutomationError, WinAppRuntimeError) as exc:
                code = exc.code if isinstance(exc, DesktopAutomationError) else "desktop_unavailable"
                raise ToolException(f"{code}: {exc}") from exc

        @tool("desktop_list_windows")
        def desktop_list_windows() -> str:
            """List authorized Windows app windows; Selected mode returns only the chosen window."""
            return result_of(lambda: {
                "scope": service._effective_scope(thread_id, bound)[0].value,
                "windows": [window.public_dict() for window in service.list_windows(thread_id, _bound=bound)],
            })

        @tool("desktop_inspect")
        def desktop_inspect(hwnd: int | None = None, depth: int = 3,
                            interactive: bool = False, selector: str | None = None) -> str:
            """Read the target window's accessibility tree. In All windows mode, supply an HWND."""
            return result_of(lambda: service.inspect(thread_id, hwnd=hwnd, depth=depth,
                interactive=interactive, selector=selector, _bound=bound))

        @tool("desktop_search")
        def desktop_search(selector: str, hwnd: int | None = None, max_results: int = 20) -> str:
            """Find an accessibility element in an authorized window."""
            return result_of(lambda: service.search(thread_id, selector, hwnd=hwnd,
                max_results=max_results, _bound=bound))

        @tool("desktop_wait")
        def desktop_wait(selector: str, hwnd: int | None = None, timeout_ms: int = 5_000,
                         value: str | None = None, gone: bool = False) -> str:
            """Wait for an accessibility element or value in an authorized window."""
            return result_of(lambda: service.wait(thread_id, selector, hwnd=hwnd,
                timeout_ms=timeout_ms, value=value, gone=gone, _bound=bound))

        @tool("desktop_invoke")
        def desktop_invoke(selector: str, hwnd: int | None = None) -> str:
            """Invoke an accessibility control in an authorized window; Access may require approval."""
            return result_of(lambda: service.invoke(thread_id, selector, hwnd=hwnd, _bound=bound))

        @tool("desktop_set_value")
        def desktop_set_value(selector: str, value: str, hwnd: int | None = None) -> str:
            """Set an accessible field's value in an authorized window; Access may require approval."""
            return result_of(lambda: service.set_value(thread_id, selector, value,
                hwnd=hwnd, _bound=bound))

        @tool("desktop_send_keys")
        def desktop_send_keys(keys: str, hwnd: int | None = None, target: str | None = None) -> str:
            """Send target-window keys without global system-key input; Access may require approval."""
            return result_of(lambda: service.send_keys(thread_id, keys, hwnd=hwnd,
                target=target, _bound=bound))

        @tool("desktop_screenshot")
        def desktop_screenshot(hwnd: int | None = None, selector: str | None = None) -> str:
            """Capture an authorized window as a retained PNG; returns a read_file path, not image bytes."""
            def capture() -> dict[str, Any]:
                if service.capture_sink is None:
                    raise DesktopAutomationError("Capture storage is unavailable.", code="desktop_capture_unavailable")
                shot = service.screenshot(thread_id, hwnd=hwnd, selector=selector, _bound=bound)
                try:
                    try:
                        _asset, virtual_path = service.capture_sink(
                            run, shot.path, source_tool_name="desktop_screenshot",
                            source_tool_call_id=CURRENT_TOOL_CALL.get() or None,
                            target=f"HWND {shot.window.hwnd}, PID {shot.window.process_id}, {shot.window.process_name}: {shot.window.title}",
                            controlled_root=shot.path.parent,
                        )
                    except Exception as exc:
                        raise DesktopAutomationError("The screenshot could not be retained.",
                            code="desktop_capture_unavailable") from exc
                finally:
                    shot.path.unlink(missing_ok=True)
                return {
                    "path": virtual_path,
                    "window": shot.window.public_dict(),
                    "width": shot.width,
                    "height": shot.height,
                    "capture_mode": shot.mode,
                }
            return result_of(capture)

        selected = [desktop_list_windows, desktop_inspect, desktop_search, desktop_wait,
                    desktop_invoke, desktop_set_value, desktop_send_keys, desktop_screenshot]
        for item in selected:
            item.handle_tool_error = True
        return selected

    def _target_call(self, thread_id: str, hwnd: int | None, args: list[str], *,
                     timeout: int, allow_nonzero: bool = False,
                     bound: _ScopeState | None = None) -> dict[str, Any]:
        window = self._authorize_window(thread_id, hwnd, bound=bound)
        result = self._run_cli([*args, "-w", str(window.hwnd)], timeout=timeout,
            allow_nonzero=allow_nonzero)
        if self._identity_lookup(window.hwnd) != window.identity:
            raise DesktopAutomationError(
                "The window changed during this action; its result may be uncertain. Choose it again.",
                code="desktop_effect_uncertain",
            )
        if not isinstance(result, dict):
            raise DesktopAutomationError("The WinApp CLI returned an unexpected result.", code="desktop_worker_error")
        return result

    def _authorize_window(self, thread_id: str, hwnd: int | None,
                          *, bound: _ScopeState | None = None) -> DesktopWindow:
        scope, selected = self._effective_scope(thread_id, bound)
        if scope is DesktopAccessScope.off:
            raise DesktopAutomationError("Windows access is off for this conversation.", code="desktop_access_off")
        if scope is DesktopAccessScope.selected:
            if selected is None:
                raise DesktopAutomationError("Choose a window first.", code="desktop_window_required")
            if hwnd is not None and hwnd != selected.hwnd:
                raise DesktopAutomationError("That window is outside the selected-window grant.", code="desktop_scope_denied")
            hwnd = selected.hwnd
        elif not isinstance(hwnd, int) or isinstance(hwnd, bool) or hwnd <= 0:
            raise DesktopAutomationError("All windows mode requires an HWND from the current window list.",
                code="desktop_window_required")
        window = self._find_window(hwnd)
        if scope is DesktopAccessScope.selected and window.identity != selected:
            raise DesktopAutomationError("The selected window changed; choose it again.", code="desktop_window_changed")
        return window

    def _effective_scope(self, thread_id: str,
                         bound: _ScopeState | None = None) -> tuple[DesktopAccessScope, WindowIdentity | None]:
        thread_scope, thread_selected = self.scope_for_thread(thread_id)
        if bound is None:
            return thread_scope, thread_selected
        if thread_scope is DesktopAccessScope.off or bound.scope is DesktopAccessScope.off:
            return DesktopAccessScope.off, None
        if thread_scope is DesktopAccessScope.selected and bound.scope is DesktopAccessScope.selected:
            if thread_selected != bound.selected:
                raise DesktopAutomationError("The selected window grant changed during this run.",
                    code="desktop_scope_denied")
            return DesktopAccessScope.selected, thread_selected
        if thread_scope is DesktopAccessScope.selected:
            return DesktopAccessScope.selected, thread_selected
        if bound.scope is DesktopAccessScope.selected:
            if bound.selected is None:
                raise DesktopAutomationError("This run has no selected window identity.",
                    code="desktop_scope_denied")
            return DesktopAccessScope.selected, bound.selected
        return DesktopAccessScope.all, None

    def _find_window(self, hwnd: int) -> DesktopWindow:
        window = next((candidate for candidate in self._windows() if candidate.hwnd == hwnd), None)
        if window is None:
            raise DesktopAutomationError("The window is not in the current visible window list.", code="desktop_window_changed")
        return window

    def _windows(self) -> list[DesktopWindow]:
        raw = self._run_cli(["list-windows"], timeout=20)
        if not isinstance(raw, list) or len(raw) > _MAX_WINDOWS:
            raise DesktopAutomationError("The window list is unavailable or too large.", code="desktop_worker_error")
        windows: list[DesktopWindow] = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            try:
                hwnd = int(item["hwnd"])
                pid = int(item["processId"])
                width = int(item.get("width", 0))
                height = int(item.get("height", 0))
            except (KeyError, ValueError, TypeError):
                continue
            if hwnd <= 0 or pid <= 0 or width < 64 or height < 64:
                continue
            try:
                identity = self._identity_lookup(hwnd)
            except DesktopAutomationError:
                continue
            if identity.process_id != pid:
                continue
            windows.append(DesktopWindow(
                hwnd=hwnd, process_id=pid, process_name=str(item.get("processName") or ""),
                title=str(item.get("title") or ""), width=width, height=height,
                owner_hwnd=int(item.get("ownerHwnd") or 0),
                class_name=str(item.get("className") or ""),
                is_foreground=bool(item.get("isForeground")),
                process_created_at=identity.process_created_at,
            ))
        return windows

    def _run_cli(self, args: list[str], *, timeout: int,
                 allow_nonzero: bool = False) -> Any:
        if self._command_runner is not None:
            completed = self._command_runner(["ui", *args, "--json"], timeout)
        else:
            try:
                executable = self.runtime.command_path()
                completed = subprocess.run(
                    [str(executable), "ui", *args, "--json"],
                    capture_output=True, text=True, encoding="utf-8", errors="replace",
                    timeout=timeout, check=False,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                    cwd=self.paths.root,
                    env={**os.environ, "WINAPP_CLI_TELEMETRY_OPTOUT": "1"},
                )
            except WinAppRuntimeError:
                raise
            except subprocess.TimeoutExpired as exc:
                raise DesktopAutomationError(
                    "The Windows action timed out; its effect is uncertain. Inspect the window before retrying.",
                    code="desktop_effect_uncertain",
                ) from exc
            except OSError as exc:
                raise DesktopAutomationError("The WinApp CLI worker could not be started.", code="desktop_worker_error") from exc
        stdout = str(completed.stdout or "")
        stderr = str(completed.stderr or "")
        if len(stdout.encode("utf-8")) > _MAX_UI_OUTPUT_BYTES or len(stderr.encode("utf-8")) > 4_000:
            raise DesktopAutomationError("The UI result is too large; use a narrower selector or depth.",
                code="desktop_result_too_large")
        try:
            payload = json.loads(stdout)
        except json.JSONDecodeError as exc:
            raise DesktopAutomationError("The WinApp CLI returned invalid JSON.", code="desktop_worker_error") from exc
        if completed.returncode != 0 and not allow_nonzero:
            detail = payload.get("message") or payload.get("error") if isinstance(payload, dict) else None
            detail = str(detail or stderr or "The Windows action failed.")[:500]
            raise DesktopAutomationError(detail, code="desktop_worker_error")
        return payload
