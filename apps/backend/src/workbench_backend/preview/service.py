"""A bounded project preview server tied to a saved conversation.

The agent chooses an argv and loopback port, but Workbench owns the process,
health check, output log and cleanup. Approval is enforced by harness HITL.
"""

from __future__ import annotations

import asyncio
import ctypes
import http.client
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import psutil
from langchain_core.tools import BaseTool, ToolException, tool

from workbench_backend.agents.harness_backend import sanitize_thread_id
from workbench_backend.errors import HarnessError
from workbench_backend.inference.ids import utc_now
from workbench_backend.paths import WorkbenchPaths

PREVIEW_TOOL_NAMES = ("start_preview", "stop_preview", "preview_status")
PREVIEW_IDLE_SECONDS = 30 * 60
_MAX_LOG_CHARS = 4_000
_THREAD_ID = re.compile(r"^[A-Za-z0-9_.-]{1,120}$")


def _key(thread_id: str | None) -> str:
    if not thread_id or not _THREAD_ID.fullmatch(thread_id):
        raise HarnessError("A project preview requires a saved conversation.", code="preview_thread_required", status_code=409)
    return sanitize_thread_id(thread_id)


def _localhost_health(port: int) -> bool:
    """Probe only the owned loopback port; never follow a site's redirect."""
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=1)
    try:
        connection.request("GET", "/")
        response = connection.getresponse()
        response.read(1)
        return True  # Any HTTP response proves the local listener is present.
    except (OSError, http.client.HTTPException):
        return False
    finally:
        connection.close()


class _WindowsJob:
    """Own a Windows process tree even if its launcher exits first."""

    def __init__(self, handle: int):
        self.handle = handle

    @classmethod
    def attach_suspended(cls, process: subprocess.Popen) -> "_WindowsJob":
        from ctypes import wintypes

        class _BasicLimits(ctypes.Structure):
            _fields_ = [
                ("per_process_user_time", ctypes.c_int64),
                ("per_job_user_time", ctypes.c_int64),
                ("limit_flags", wintypes.DWORD),
                ("minimum_working_set", ctypes.c_size_t),
                ("maximum_working_set", ctypes.c_size_t),
                ("active_process_limit", wintypes.DWORD),
                ("affinity", ctypes.c_size_t),
                ("priority_class", wintypes.DWORD),
                ("scheduling_class", wintypes.DWORD),
            ]

        class _IoCounters(ctypes.Structure):
            _fields_ = [(name, ctypes.c_uint64) for name in (
                "read_operations", "write_operations", "other_operations",
                "read_bytes", "write_bytes", "other_bytes",
            )]

        class _ExtendedLimits(ctypes.Structure):
            _fields_ = [
                ("basic", _BasicLimits), ("io", _IoCounters),
                ("process_memory_limit", ctypes.c_size_t),
                ("job_memory_limit", ctypes.c_size_t),
                ("peak_process_memory_used", ctypes.c_size_t),
                ("peak_job_memory_used", ctypes.c_size_t),
            ]

        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
        kernel.CreateJobObjectW.restype = wintypes.HANDLE
        kernel.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
        kernel.SetInformationJobObject.restype = wintypes.BOOL
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        kernel.AssignProcessToJobObject.restype = wintypes.BOOL
        kernel.OpenThread.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenThread.restype = wintypes.HANDLE
        kernel.ResumeThread.argtypes = [wintypes.HANDLE]
        kernel.ResumeThread.restype = wintypes.DWORD
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel.CloseHandle.restype = wintypes.BOOL
        handle = kernel.CreateJobObjectW(None, None)
        if not handle:
            raise OSError(ctypes.get_last_error(), "Could not create preview process job")
        job = cls(handle)
        process_handle = None
        thread_handle = None
        try:
            limits = _ExtendedLimits()
            limits.basic.limit_flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
            if not kernel.SetInformationJobObject(handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
                raise OSError(ctypes.get_last_error(), "Could not configure preview process job")
            process_handle = kernel.OpenProcess(0x0101, False, process.pid)  # SET_QUOTA | TERMINATE
            if not process_handle or not kernel.AssignProcessToJobObject(handle, process_handle):
                raise OSError(ctypes.get_last_error(), "Could not attach preview to its process job")
            # CREATE_SUSPENDED prevents the command from spawning a child before
            # the job owns it. A suspended new process has one initial thread.
            thread_ids = [thread.id for thread in psutil.Process(process.pid).threads()]
            if len(thread_ids) != 1:
                raise OSError("Preview process did not have one suspended startup thread")
            thread_handle = kernel.OpenThread(0x0002, False, thread_ids[0])  # THREAD_SUSPEND_RESUME
            if not thread_handle or kernel.ResumeThread(thread_handle) == 0xFFFFFFFF:
                raise OSError(ctypes.get_last_error(), "Could not resume preview process")
            return job
        except BaseException:
            job.stop()
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=3)
            raise
        finally:
            if thread_handle:
                kernel.CloseHandle(thread_handle)
            if process_handle:
                kernel.CloseHandle(process_handle)

    def stop(self) -> bool:
        if not self.handle:
            return True
        from ctypes import wintypes
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
        kernel.TerminateJobObject.restype = wintypes.BOOL
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel.CloseHandle.restype = wintypes.BOOL
        stopped = bool(kernel.TerminateJobObject(self.handle, 1))
        closed = bool(kernel.CloseHandle(self.handle))
        self.handle = 0
        return stopped and closed


def _kill_tree(process: subprocess.Popen, job: _WindowsJob | None = None) -> bool:
    """Stop descendants before their parent so a package runner cannot orphan a server."""
    if job is not None:
        stopped = job.stop()
        if process.poll() is None and not stopped:
            process.terminate()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            return False
        return stopped
    try:
        parent = psutil.Process(process.pid)
        descendants = parent.children(recursive=True)
        for child in reversed(descendants):
            child.terminate()
        parent.terminate()
        _, alive = psutil.wait_procs([*descendants, parent], timeout=3)
        for child in alive:
            child.kill()
        _, alive = psutil.wait_procs(alive, timeout=3)
        if not alive:
            process.wait(timeout=3)
        return not alive
    except psutil.NoSuchProcess:
        process.poll()
        return True
    except (psutil.AccessDenied, OSError):
        return False


@dataclass
class _Preview:
    thread_id: str
    project_path: Path
    command: tuple[str, ...]
    port: int
    process: subprocess.Popen
    log_file: Any
    job: _WindowsJob | None = None
    timer: threading.Timer | None = None
    launch_id: str = ""


class PreviewService:
    def __init__(self, paths: WorkbenchPaths, *, idle_seconds: int = PREVIEW_IDLE_SECONDS):
        self.paths = paths
        self.idle_seconds = idle_seconds
        self._lock = threading.RLock()
        self._owned: dict[str, _Preview] = {}
        self._state_root = paths.state / "previews"
        self._log_root = paths.logs / "previews"

    def _marker(self, key: str) -> Path:
        return self._state_root / f"{key}.json"

    def status(self, thread_id: str) -> dict[str, Any]:
        key = _key(thread_id)
        with self._lock:
            preview = self._owned.get(key)
            alive = bool(preview and preview.process.poll() is None)
            if preview and not alive:
                self._owned.pop(key, None)
                if preview.timer:
                    preview.timer.cancel()
                _kill_tree(preview.process, preview.job)
                preview.log_file.close()
        return {
            "thread_id": key,
            "state": "active" if alive else ("lost" if self._marker(key).exists() else "closed"),
            "url": f"http://127.0.0.1:{preview.port}/" if alive and preview else None,
            "port": preview.port if alive and preview else None,
            "pid": preview.process.pid if alive and preview else None,
        }

    def inspect(self, thread_id: str) -> dict[str, Any]:
        """Read current ownership, HTTP health, and a bounded local log tail."""
        key = _key(thread_id)
        status = self.status(key)
        log_path = self._log_root / f"{key}.log"
        try:
            with log_path.open("rb") as handle:
                handle.seek(0, os.SEEK_END)
                handle.seek(max(0, handle.tell() - 8_000), os.SEEK_SET)
                log_tail = handle.read(8_000).decode("utf-8", errors="replace")[-_MAX_LOG_CHARS:]
        except OSError:
            log_tail = ""
        healthy: bool | None = None
        if status["state"] == "active" and status["port"]:
            healthy = _localhost_health(status["port"])
        return {**status, "healthy": healthy, "recent_log": log_tail}

    def _refresh_idle(self, preview: _Preview) -> None:
        if preview.timer:
            preview.timer.cancel()
        preview.timer = threading.Timer(self.idle_seconds, self.stop, args=(preview.thread_id,))
        preview.timer.daemon = True
        preview.timer.start()

    def start(self, thread_id: str, project_path: str, command: list[str], port: int) -> dict[str, Any]:
        key = _key(thread_id)
        project = Path(project_path).resolve()
        if not project.is_dir():
            raise HarnessError("The project folder for this preview is unavailable.", code="preview_project_missing", status_code=409)
        if not 1024 <= port <= 65535:
            raise HarnessError("Choose a local preview port from 1024 to 65535.", code="preview_port_invalid", status_code=409)
        if not 1 <= len(command) <= 40 or any(not isinstance(item, str) or not item or len(item) > 4096 or "\x00" in item for item in command):
            raise HarnessError("Choose an executable and a short list of arguments for the preview.", code="preview_command_invalid", status_code=409)
        resolved_executable = shutil.which(command[0]) if not Path(command[0]).is_absolute() else command[0]
        if not resolved_executable or not Path(resolved_executable).is_file():
            raise HarnessError("The preview executable is unavailable.", code="preview_executable_missing", status_code=409)
        argv = [str(resolved_executable), *command[1:]]
        with self._lock:
            existing = self._owned.get(key)
            if existing and existing.process.poll() is None:
                if existing.project_path != project or existing.command != tuple(argv) or existing.port != port:
                    raise HarnessError("Stop this conversation's preview before changing its command or port.", code="preview_already_running", status_code=409)
                self._refresh_idle(existing)
                return self.status(key)
            if self._marker(key).exists():
                raise HarnessError("A previous preview process was lost. Stop or reset it before starting another.", code="preview_session_lost", status_code=409)
            # Refuse an occupied port rather than claiming another process's page.
            with socket.socket() as probe:
                try:
                    probe.bind(("127.0.0.1", port))
                except OSError as exc:
                    raise HarnessError("That local preview port is already in use.", code="preview_port_busy", status_code=409) from exc
            self._state_root.mkdir(parents=True, exist_ok=True)
            self._log_root.mkdir(parents=True, exist_ok=True)
            log_path = self._log_root / f"{key}.log"
            log_file = log_path.open("ab", buffering=0)
            flags = (subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW | 0x00000004) if sys.platform == "win32" else 0
            process = None
            job = None
            try:
                process = subprocess.Popen(
                    argv, cwd=project, stdin=subprocess.DEVNULL, stdout=log_file,
                    stderr=subprocess.STDOUT, shell=False, creationflags=flags,
                    start_new_session=sys.platform != "win32",
                )
                if sys.platform == "win32":
                    job = _WindowsJob.attach_suspended(process)
            except BaseException:
                if process is not None:
                    _kill_tree(process, job)
                log_file.close()
                raise
            preview = _Preview(key, project, tuple(argv), port, process, log_file,
                job=job, launch_id=uuid.uuid4().hex)
            marker = self._marker(key)
            marker.write_text(json.dumps({"pid": process.pid, "port": port, "started_at": utc_now()}), encoding="utf-8")
            self._owned[key] = preview
            self._refresh_idle(preview)
        url = f"http://127.0.0.1:{port}/"
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            if process.poll() is not None:
                self.stop(key)
                raise HarnessError("The preview command exited before its page became ready. Check the preview log.", code="preview_exited", status_code=409)
            if _localhost_health(port):
                return {"state": "active", "url": url, "port": port, "log": str(log_path),
                    "_launch_id": preview.launch_id}
            time.sleep(0.2)
        stopped = self.stop(key)
        raise HarnessError(
            "The preview did not become ready on its selected local port. Check the command and preview log."
            if stopped else "The preview did not become ready and its process could not be confirmed stopped.",
            code="preview_not_ready" if stopped else "preview_stop_unconfirmed", status_code=409,
        )

    def stop(self, thread_id: str) -> bool:
        key = _key(thread_id)
        with self._lock:
            preview = self._owned.pop(key, None)
            if preview is None:
                # A recovered marker is an unknown former process. Never kill a
                # PID from disk, which may now belong to a different program.
                return not self._marker(key).exists()
            if preview.timer:
                preview.timer.cancel()
            stopped = _kill_tree(preview.process, preview.job)
            preview.log_file.close()
            if stopped:
                self._marker(key).unlink(missing_ok=True)
            return stopped

    def stop_if_launch(self, thread_id: str, launch_id: str) -> bool:
        """Cancel only the process created by one interrupted start call."""
        key = _key(thread_id)
        with self._lock:
            preview = self._owned.get(key)
            if preview is None or preview.launch_id != launch_id:
                return False
            return self.stop(key)

    def reset_lost(self, thread_id: str) -> dict[str, Any]:
        """Acknowledge an unrecoverable prior preview without guessing at PID ownership."""
        key = _key(thread_id)
        with self._lock:
            if key in self._owned:
                raise HarnessError("Stop the active preview before resetting its status.", code="preview_active", status_code=409)
            self._marker(key).unlink(missing_ok=True)
        return self.status(key)

    def tools_for_run(self, run) -> list[BaseTool]:
        if not run.project_path or run.work_mode != "work" or getattr(run, "tool_mode", None) == "recorded-tool":
            return []
        selected = set(run.presented_tools)
        result: list[BaseTool] = []

        @tool("start_preview")
        async def start_preview(command: list[str], port: int) -> str:
            """Start an owned project web preview from an executable and argv on a selected localhost port. The project folder is the cwd."""
            launch = asyncio.create_task(asyncio.to_thread(self.start,
                run.thread_id, run.project_path, command, port))
            try:
                info = await asyncio.shield(launch)
                return f"Project preview is ready at {info['url']}. Use browser_navigate to test it."
            except asyncio.CancelledError:
                async def finish_and_stop() -> None:
                    try:
                        completed = await launch
                    except Exception:
                        return  # start() has already stopped or marked uncertainty.
                    if launch_id := completed.get("_launch_id"):
                        await asyncio.to_thread(self.stop_if_launch, run.thread_id, launch_id)

                cleanup = asyncio.create_task(finish_and_stop())
                while not cleanup.done():
                    try:
                        await asyncio.shield(cleanup)
                    except asyncio.CancelledError:
                        continue
                raise
            except HarnessError as exc:
                raise ToolException(f"{exc.code}: {exc.message}") from exc

        @tool("stop_preview")
        async def stop_preview() -> str:
            """Stop this conversation's owned project preview process tree."""
            if not await asyncio.to_thread(self.stop, run.thread_id):
                raise ToolException("The preview process did not confirm stopping; inspect its status before another launch.")
            return "Project preview stopped."

        @tool("preview_status")
        async def preview_status() -> str:
            """Inspect the owned project's preview state, localhost health, and recent bounded log output."""
            return json.dumps(await asyncio.to_thread(self.inspect, run.thread_id),
                ensure_ascii=False)

        if "start_preview" in selected:
            result.append(start_preview)
        if "stop_preview" in selected:
            result.append(stop_preview)
        if "preview_status" in selected:
            result.append(preview_status)
        return result

    def shutdown(self) -> None:
        with self._lock:
            keys = list(self._owned)
        for key in keys:
            self.stop(key)
