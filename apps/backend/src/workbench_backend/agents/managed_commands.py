"""Optional nonblocking commands owned by one accepted run.

Uses the shared process-tree boundary and existing external-effect ledger.
This is an operation lifecycle, never a second agent scheduler. Active commands
are stopped when their run finishes, cancels, times out or the owner shuts down.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import shutil
import subprocess
import sys
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Annotated, Callable

from langchain_core.tools import BaseTool, ToolException, tool
from pydantic import Field

from workbench_backend.agents.harness_backend import sanitize_thread_id
from workbench_backend.agents.tool_results import OwnedToolResults, bounded_content_payload, read_bounded_log, result_owner
from workbench_backend.errors import HarnessError
from workbench_backend.inference.ids import utc_now
from workbench_backend.process_tree import WindowsJob, stop_process_tree
from workbench_backend.state.effects import EffectService, DispatchEffectRequest, AcknowledgeEffectRequest, ReconcileEffectRequest
from workbench_backend.state.schemas import ExternalEffectOutcome

COMMAND_TOOL_NAMES = ("start_command", "command_status", "stop_command")


@dataclass
class _Command:
    id: str
    run: Any
    process: subprocess.Popen
    job: WindowsJob | None
    log_file: Any
    log_path: Path
    deadline: float
    cancel_requested: Callable[[], bool]
    effect_id: str | None = None
    state: str = "running"
    exit_code: int | None = None
    retained: dict | None = None
    error: str | None = None
    lock: threading.RLock = field(default_factory=threading.RLock)
    settled: threading.Event = field(default_factory=threading.Event)


class ManagedCommandService:
    def __init__(self, paths, *, app_store=None):
        self.paths = paths
        self.effects = EffectService(app_store) if app_store is not None else None
        self._commands: dict[str, _Command] = {}
        self._lock = threading.RLock()
        self._closing = False

    def _lookup(self, run, command_id: str) -> _Command | None:
        with self._lock:
            command = self._commands.get(command_id)
        if command is not None and result_owner(command.run) != result_owner(run):
            raise ToolException("This command belongs to another conversation or helper.")
        return command

    def _persist(self, command: _Command, evidence: dict) -> None:
        if self.effects and command.effect_id:
            if evidence.get("process_stop_confirmed"):
                self.effects.reconcile(command.effect_id, ReconcileEffectRequest(evidence=evidence))
            else:
                record = self.effects.get_effect(command.effect_id)
                self.effects.store.put_effect(record.model_copy(update={"outcome": ExternalEffectOutcome.unknown,
                    "unresolved": True, "evidence": evidence, "note": "The owned command stop remains unconfirmed. It was not replayed."}))

    def start(self, run, command: list[str], timeout_seconds: int = 300,
              *, cancel_requested: Callable[[], bool] | None = None) -> dict:
        if run.project_path:
            if not Path(run.project_path).is_dir():
                raise ToolException("An available bound project is required for managed commands.")
            cwd = run.project_path
        else:
            cwd = str(Path.home().resolve())
        if not 1 <= timeout_seconds <= 86400 or not 1 <= len(command) <= 40 or any(not isinstance(arg, str) or not arg or len(arg) > 4096 or "\x00" in arg for arg in command):
            raise ToolException("Provide executable argv (1–40 bounded arguments) and a 1–86400 second timeout.")
        executable = command[0] if Path(command[0]).is_absolute() else shutil.which(command[0])
        if executable is None or not Path(executable).is_file():
            raise ToolException("The command executable is unavailable.")
        cancel = cancel_requested or (lambda: str(getattr(run, "status", "")) in {"cancel_requested", "cancelled"})
        if cancel():
            raise HarnessError("This run is cancelling; the command was not launched.", code="run_cancelling", status_code=409)
        identity = uuid.uuid4().hex
        log_root = self.paths.logs / "commands" / sanitize_thread_id(result_owner(run))
        log_root.mkdir(parents=True, exist_ok=True)
        log_path = log_root / (identity + ".log")
        with self._lock:
            if self._closing:
                raise ToolException("The command owner is shutting down.")
            if sum(item.state == "running" and result_owner(item.run) == result_owner(run) for item in self._commands.values()) >= 4:
                raise ToolException("Four commands are already active for this owner; inspect or stop one first.")
            effect = self.effects.dispatch(DispatchEffectRequest(run_id=run.id, adapter_id="managed-command", operation="start_command",
                payload={"command_id": identity, "owner": result_owner(run), "command_sha256": hashlib.sha256(json.dumps(command).encode()).hexdigest(),
                    "timeout_seconds": timeout_seconds})) if self.effects else None
            log = log_path.open("wb", buffering=0)
            process = None
            job = None
            try:
                flags = (subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW | 0x00000004) if sys.platform == "win32" else 0
                process = subprocess.Popen([str(executable), *command[1:]], cwd=cwd,
                    env=dict(os.environ), stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                    shell=False, creationflags=flags, start_new_session=sys.platform != "win32")
                if sys.platform == "win32":
                    job = WindowsJob.attach_suspended(process)
                owned = _Command(identity, run, process, job, log, log_path, time.monotonic() + timeout_seconds, cancel,
                    effect_id=effect.id if effect else None)
                self._commands[identity] = owned
                if effect:
                    self.effects.acknowledge(effect.id, AcknowledgeEffectRequest(evidence={"command_id": identity, "state": "running", "pid": process.pid, "started_at": utc_now()}))
                threading.Thread(target=self._watch, args=(owned,), name="workbench-command-" + identity[:8], daemon=True).start()
            except BaseException:
                stopped = stop_process_tree(process, job) if process else True
                log.close()
                if effect:
                    if stopped:
                        self.effects.reconcile(effect.id, ReconcileEffectRequest(evidence={"command_id": identity, "state": "launch_failed", "process_stop_confirmed": True}))
                    else:
                        self.effects.recover(effect.id)
                if not stopped:
                    raise HarnessError("The failed command launch could not confirm its process tree stopped.", code="command_stop_unconfirmed", status_code=409) from None
                raise
        return {"command_id": identity, "state": "running", "pid": process.pid, "timeout_seconds": timeout_seconds,
            "notice": "The command belongs to this accepted run. Inspect command_status; run completion/cancellation stops active commands."}

    def _watch(self, command: _Command) -> None:
        while not command.settled.wait(.05):
            if command.cancel_requested():
                self._finish(command, "cancelled", 130)
                return
            if time.monotonic() >= command.deadline:
                self._finish(command, "timed_out", 124)
                return
            if (code := command.process.poll()) is not None:
                self._finish(command, "completed", code)
                return

    def _finish(self, command: _Command, state: str, code: int | None = None) -> None:
        with command.lock:
            if command.settled.is_set():
                return
            try:
                stopped = stop_process_tree(command.process, command.job)
                command.job = None
                command.log_file.close()
                command.state = state if stopped else "uncertain"
                command.exit_code = code if code is not None else command.process.returncode
                try:
                    text, coverage = read_bounded_log(command.log_path)
                    command.retained = OwnedToolResults(self.paths, command.run).retain(text, source={"tool": "command_status", "command_id": command.id,
                        "state": command.state, "exit_code": command.exit_code, **coverage})
                except (OSError, ToolException):
                    command.error = "The process settled but its output could not be retained. Check local storage."
                evidence = {"command_id": command.id, "state": command.state, "exit_code": command.exit_code,
                    "process_stop_confirmed": stopped, "retained_result": command.retained, "output_error": command.error}
                self._persist(command, evidence)
            except BaseException:
                command.state = "uncertain"
                command.error = "The command owner could not confirm cleanup or record its result. Inspect its effects before continuing."
                command.log_file.close()
            finally:
                command.settled.set()

    def status(self, run, command_id: str, *, wait_seconds: float = 0) -> dict:
        if not 0 <= wait_seconds <= 10:
            raise ToolException("Wait for 0–10 seconds per status call.")
        command = self._lookup(run, command_id)
        if command is None:
            if self.effects:
                record = next((item for item in self.effects.list_effects() if item.adapter_id == "managed-command"
                    and item.payload.get("command_id") == command_id and item.payload.get("owner") == result_owner(run)), None)
                if record:
                    known = dict(record.evidence or {})
                    if known.get("state") not in {"running", None}:
                        return known
                    return {"command_id": command_id, "state": "lost", "process_stop_confirmed": False,
                        "notice": "The backend no longer owns this command. Its outcome is unknown; a historical PID is not targeted and the command was not replayed."}
            raise ToolException("This command is unavailable or belongs to another owner.")
        if wait_seconds:
            command.settled.wait(min(10, max(0, wait_seconds)))
        with command.lock:
            try:
                text, coverage = read_bounded_log(command.log_path)
                retained = command.retained or OwnedToolResults(self.paths, run).retain(text, source={"tool": "command_status", "command_id": command.id,
                    "state": command.state, "exit_code": command.exit_code, **coverage})
            except (OSError, ToolException):
                text, retained = "Output is unavailable; check local storage.", command.retained
            return bounded_content_payload({"command_id": command.id, "state": command.state, "pid": command.process.pid if command.state == "running" else None,
                "exit_code": command.exit_code, "process_stop_confirmed": command.settled.is_set() and command.state != "uncertain",
                "preview": text, "retained_result": retained, "output_error": command.error}, "preview", tail=True)

    def stop(self, run, command_id: str) -> dict:
        command = self._lookup(run, command_id)
        if command is None:
            status = self.status(run, command_id)
            if status.get("state") == "lost":
                raise HarnessError(status["notice"], code="command_outcome_unknown", status_code=409)
            return status
        self._finish(command, "stopped")
        if command.state == "uncertain":
            raise HarnessError("The command's owned process tree could not be confirmed stopped. Its outcome is uncertain.", code="command_stop_unconfirmed", status_code=409)
        return self.status(run, command_id)

    def stop_run(self, run_id: str) -> None:
        with self._lock:
            targets = [command for command in self._commands.values() if command.run.id == run_id and not command.settled.is_set()]
        self._stop_all(targets)

    def shutdown(self) -> None:
        with self._lock:
            self._closing = True
            targets = list(self._commands.values())
        self._stop_all([command for command in targets if not command.settled.is_set()])

    def _stop_all(self, targets: list[_Command]) -> None:
        errors = []
        for command in targets:
            try:
                self.stop(command.run, command.id)
            except Exception:
                errors.append(command.id)
        if errors:
            raise HarnessError("Cleanup attempted every owned command, but these stops remain unconfirmed: " + ", ".join(errors),
                code="command_stop_unconfirmed", status_code=409)

    def tools_for_run(self, run, *, cancel_requested=None) -> list[BaseTool]:
        if run.work_mode != "work" or getattr(run, "tool_mode", None) == "recorded-tool":
            return []
        @tool("start_command")
        async def start_command(command: Annotated[list[Annotated[str, Field(min_length=1, max_length=4096, pattern=r"^[^\x00]+$")]], Field(min_length=1, max_length=40)],
                                timeout_seconds: Annotated[int, Field(ge=1, le=86400, description="Owned job timeout in seconds, independent of a whole-task budget.")] = 300) -> str:
            """Launch executable argv in this run's starting folder without shell syntax or isolation. Return an owned command identity; status and stop use that exact identity. Active jobs are stopped when the run ends."""
            launch = asyncio.create_task(asyncio.to_thread(self.start, run, command, timeout_seconds, cancel_requested=cancel_requested))
            try:
                return json.dumps(await asyncio.shield(launch), ensure_ascii=False)
            except asyncio.CancelledError:
                async def settle():
                    try:
                        created = await launch
                    except Exception:
                        return
                    await asyncio.to_thread(self.stop, run, created["command_id"])
                cleanup = asyncio.create_task(settle())
                while not cleanup.done():
                    try:
                        await asyncio.shield(cleanup)
                    except asyncio.CancelledError:
                        continue
                cleanup.result()
                raise
        @tool("command_status")
        async def command_status(command_id: str, wait_seconds: Annotated[float, Field(ge=0, le=10)] = 0) -> str:
            """Inspect an owned command's state, exit status and retained output. Optionally wait up to 10 seconds for it to settle; no command is replayed."""
            return json.dumps(await asyncio.to_thread(self.status, run, command_id, wait_seconds=wait_seconds), ensure_ascii=False)
        @tool("stop_command")
        async def stop_command(command_id: str) -> str:
            """Stop this owner's command and descendants by stable identity. A lost or unconfirmed stop is an error, never success or a historical-PID kill."""
            return json.dumps(await asyncio.to_thread(self.stop, run, command_id), ensure_ascii=False)
        return [candidate for candidate in (start_command, command_status, stop_command) if candidate.name in run.presented_tools]
