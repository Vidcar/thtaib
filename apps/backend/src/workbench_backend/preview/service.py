"""A bounded project preview server tied to a saved conversation.

The agent chooses an argv and loopback port, but Workbench owns the process,
health check, output log and cleanup. Approval is enforced by harness HITL.
"""

from __future__ import annotations

import asyncio
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
from pathlib import Path, PureWindowsPath
from typing import Any, Annotated
from urllib.parse import quote

from langchain_core.tools import BaseTool, ToolException, tool
from pydantic import BaseModel, ConfigDict, Field, model_validator

from workbench_backend.agents.harness_backend import canonical_root, sanitize_thread_id
from workbench_backend.errors import HarnessError
from workbench_backend.inference.ids import utc_now
from workbench_backend.paths import WorkbenchPaths
from workbench_backend.process_tree import WindowsJob as _WindowsJob, stop_process_tree as _kill_tree
from workbench_backend.agents.tool_results import OwnedToolResults, read_bounded_log, bounded_content_payload

PREVIEW_TOOL_NAMES = ("start_preview", "stop_preview", "preview_status")
PREVIEW_IDLE_SECONDS = 30 * 60
_MAX_LOG_CHARS = 4_000
_THREAD_ID = re.compile(r"^[A-Za-z0-9_.-]{1,120}$")


class PreviewStartInput(BaseModel):
    model_config = ConfigDict(extra="forbid", json_schema_extra={"oneOf": [
        {"required": ["entry_path"], "not": {"anyOf": [{"required": ["command"]}, {"required": ["port"]}]}},
        {"required": ["command", "port"], "not": {"required": ["entry_path"]}}]})
    command: list[Annotated[str, Field(min_length=1, max_length=4096, pattern=r"^[^\x00]+$")]] | None = Field(default=None, min_length=1, max_length=40, description="Executable plus argv, no shell syntax. Host execution has no sandbox; intentionally bind the server to loopback.")
    port: int | None = Field(default=None, ge=1024, le=65535)
    entry_path: str | None = Field(default=None, min_length=1, max_length=2048, description="Existing relative project HTML file. Choose this or command+port.")

    @model_validator(mode="after")
    def one_mode(self):
        if self.entry_path is not None:
            if self.command is not None or self.port is not None:
                raise ValueError("Provide entry_path, or command and port, not both.")
        elif self.command is None or self.port is None:
            raise ValueError("Provide entry_path, or command and port.")
        return self


def _key(thread_id: str | None) -> str:
    if not thread_id or not _THREAD_ID.fullmatch(thread_id):
        raise HarnessError("A project preview requires a saved conversation.", code="preview_thread_required", status_code=409)
    return sanitize_thread_id(thread_id)


def _localhost_health(port: int, token: str | None = None) -> bool:
    """Probe only the owned loopback port; never follow a site's redirect."""
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=1)
    try:
        connection.request("GET", f"/.__workbench_health_{token}" if token else "/")
        response = connection.getresponse()
        response.read(1)
        return response.getheader("X-Workbench-Preview") == token if token else True
    except (OSError, http.client.HTTPException):
        return False
    finally:
        connection.close()


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
    kind: str = "command"
    entry_path: str | None = None
    health_token: str | None = None
    stop_pending: bool = False

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}/" + quote(self.entry_path or "", safe="/")


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
                if self.stop(key):
                    preview = None
            stop_pending = bool(preview and preview.stop_pending)
        return {
            "thread_id": key,
            "state": "lost" if stop_pending else "active" if alive else ("lost" if self._marker(key).exists() else "closed"),
            "stop_pending": stop_pending,
            "error": "The preview stop is unconfirmed. Retry Stop before starting another preview or deleting this chat." if stop_pending else None,
            "url": preview.url if alive and preview else None,
            "kind": preview.kind if alive and preview else None,
            "entry_path": preview.entry_path if alive and preview else None,
            "port": preview.port if alive and preview else None,
            "pid": preview.process.pid if alive and preview else None,
            "launch_id": preview.launch_id if preview else self._last_log_launch(key),
        }

    def _last_log_launch(self, key: str) -> str | None:
        try:
            with (self._log_root / f"{key}.log").open("rb") as handle:
                first = handle.read(200).decode("utf-8", errors="replace")
            matched = re.match(r"Workbench preview launch ([a-f0-9]{32})", first)
            return matched.group(1) if matched else None
        except OSError:
            return None

    def inspect(self, thread_id: str, *, run=None) -> dict[str, Any]:
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
            with self._lock:
                owner = self._owned.get(key)
                token = owner.health_token if owner else None
            healthy = _localhost_health(status["port"], token)
        log_result = None
        if run is not None and log_path.is_file():
            text, coverage = read_bounded_log(log_path)
            log_result = OwnedToolResults(self.paths, run).retain(text,
                source={"tool": "preview_status", "launch_id": status.get("launch_id"),
                    "thread_id": key, **coverage})
        return {**status, "healthy": healthy, "readiness": "http_responsive" if healthy else ("http_unresponsive" if healthy is False else "not_running"),
            "recent_log": log_tail, **({"retained_log": log_result} if log_result else {}),
            "notice": "HTTP responsiveness does not establish that the intended UI works. A command's loopback health probe does not enforce its listen address."}

    def _refresh_idle(self, preview: _Preview) -> None:
        if preview.timer:
            preview.timer.cancel()
        preview.timer = threading.Timer(self.idle_seconds, self.stop, args=(preview.thread_id,))
        preview.timer.daemon = True
        preview.timer.start()

    def start_static(self, thread_id: str, project_path: str, entry_path: str) -> dict[str, Any]:
        """Serve an existing project HTML page through the ordinary preview owner."""
        key = _key(thread_id)
        project = Path(project_path).resolve()
        try:
            supplied = PureWindowsPath(entry_path)
            if (not entry_path or "\x00" in entry_path or supplied.drive or supplied.root
                    or ".." in supplied.parts or ":" in entry_path
                    or any(PureWindowsPath(part).is_reserved() for part in supplied.parts)):
                raise ValueError("Use a relative HTML path")
            target = (project / entry_path.replace("\\", "/")).resolve()
            canonical_root(target).relative_to(canonical_root(project))
            if target.suffix.lower() not in {".html", ".htm"} or not target.is_file():
                raise ValueError("HTML file unavailable")
            # Keep the requested spelling for relative asset URLs; containment
            # above still resolves junctions and links before granting access.
            entry = PureWindowsPath(entry_path).as_posix()
        except (ValueError, OSError) as exc:
            raise HarnessError("Choose an existing HTML file inside this project.", code="preview_entry_invalid", status_code=409) from exc
        with self._lock:
            existing = self._owned.get(key)
            if existing and existing.stop_pending:
                raise HarnessError("The preview stop is unconfirmed. Retry Stop before starting another preview.", code="preview_stop_unconfirmed", status_code=409)
            if existing and existing.process.poll() is None:
                if existing.kind != "static" or canonical_root(existing.project_path) != canonical_root(project):
                    raise HarnessError("Stop this conversation's current preview before starting a static page.", code="preview_already_running", status_code=409)
                existing.entry_path = entry
                self._refresh_idle(existing)
                return self.status(key)
            with socket.socket() as probe:
                probe.bind(("127.0.0.1", 0))
                port = probe.getsockname()[1]
            token = uuid.uuid4().hex
            command = [sys.executable, str(Path(__file__).with_name("static_server.py")), str(project), str(port), token]
        return self.start(key, str(project), command, port, kind="static", entry_path=entry, health_token=token)

    def start(self, thread_id: str, project_path: str, command: list[str], port: int, *,
              kind: str = "command", entry_path: str | None = None, health_token: str | None = None) -> dict[str, Any]:
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
            if existing and existing.stop_pending:
                raise HarnessError("The preview stop is unconfirmed. Retry Stop before starting another preview.", code="preview_stop_unconfirmed", status_code=409)
            if existing and existing.process.poll() is None:
                if canonical_root(existing.project_path) != canonical_root(project) or existing.command != tuple(argv) or existing.port != port:
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
            launch_id = uuid.uuid4().hex
            if log_path.is_file():
                previous = self._last_log_launch(key) or uuid.uuid4().hex
                log_path.replace(self._log_root / f"{key}-{previous}.log")
            log_file = log_path.open("wb", buffering=0)
            log_file.write(f"Workbench preview launch {launch_id}\n".encode("utf-8"))
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
                job=job, launch_id=launch_id, kind=kind, entry_path=entry_path, health_token=health_token)
            marker = self._marker(key)
            try:
                marker.write_text(json.dumps({"pid": process.pid, "port": port, "launch_id": launch_id, "started_at": utc_now()}), encoding="utf-8")
            except BaseException:
                _kill_tree(process, job)
                log_file.close()
                raise
            self._owned[key] = preview
            self._refresh_idle(preview)
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            if process.poll() is not None:
                self.stop(key)
                raise HarnessError("The preview command exited before its page became ready. Check the preview log.", code="preview_exited", status_code=409)
            if _localhost_health(port, health_token):
                return {**self.status(key), "log": str(log_path),
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
            preview = self._owned.get(key)
            if preview is None:
                # A recovered marker is an unknown former process. Never kill a
                # PID from disk, which may now belong to a different program.
                return not self._marker(key).exists()
            if preview.timer:
                preview.timer.cancel()
            preview.stop_pending = True
            stopped = _kill_tree(preview.process, preview.job, retain_job_on_failure=True)
            if stopped:
                self._owned.pop(key, None)
                preview.log_file.close()
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

        @tool("start_preview", args_schema=PreviewStartInput)
        async def start_preview(command: list[str] | None = None, port: int | None = None, entry_path: str | None = None) -> str:
            """Preview project HTML with entry_path='relative/page.html'; the returned exact HTTP URL supports relative assets. Or provide command (executable plus argv) and port for a development server, with the project as cwd. Choose one mode. Workbench owns and stops the process. No shell syntax."""
            if entry_path is not None:
                if command is not None or port is not None:
                    raise ToolException("Provide entry_path, or command and port, not both.")
                launch = asyncio.create_task(asyncio.to_thread(self.start_static, run.thread_id, run.project_path, entry_path))
            else:
                if command is None or port is None:
                    raise ToolException("Provide entry_path for an HTML file, or command and port for a development server.")
                launch = asyncio.create_task(asyncio.to_thread(self.start, run.thread_id, run.project_path, command, port))
            try:
                info = await asyncio.shield(launch)
                return json.dumps({"state": "active", "launch_id": info.get("launch_id") or info.get("_launch_id"),
                    "url": info["url"], "kind": info.get("kind"), "readiness": "http_responsive",
                    "notice": "Project preview is ready at " + info["url"] + ". Use browser_navigate to test it. HTTP responsiveness is not UI validation."})
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
                if exc.code == "preview_stop_unconfirmed":
                    raise
                observed = await asyncio.to_thread(self.inspect, run.thread_id, run=run)
                raise ToolException(f"{exc.code}: {exc.message}\nPreview evidence: " + json.dumps(bounded_content_payload(observed, "recent_log", limit=11_500, tail=True), ensure_ascii=False)) from exc

        @tool("stop_preview")
        async def stop_preview() -> str:
            """Stop this conversation's owned project preview process tree."""
            if not await asyncio.to_thread(self.stop, run.thread_id):
                raise HarnessError("The preview process did not confirm stopping; inspect its status before another launch.", code="preview_stop_unconfirmed", status_code=409)
            return "Project preview stopped."

        @tool("preview_status")
        async def preview_status() -> str:
            """Inspect the owned project's preview state, localhost health, and recent bounded log output."""
            observed = await asyncio.to_thread(self.inspect, run.thread_id, run=run)
            return json.dumps(bounded_content_payload(observed, "recent_log", tail=True), ensure_ascii=False)

        if "start_preview" in selected:
            result.append(start_preview)
        if "stop_preview" in selected:
            result.append(stop_preview)
        if "preview_status" in selected:
            result.append(preview_status)
        return [item.model_copy(update={"handle_tool_error": True}) for item in result]

    def shutdown(self) -> None:
        with self._lock:
            keys = list(self._owned)
        for key in keys:
            self.stop(key)
