"""Native LocalShellBackend with application-owned Windows process lifetime."""
from __future__ import annotations

import sys
import hashlib
import copy
from collections.abc import Callable

from deepagents.backends import LocalShellBackend
from deepagents.backends.protocol import ExecuteResponse

from workbench_backend.errors import HarnessError
from workbench_backend.process_tree import run_windows_command
from workbench_backend.agents.tool_results import bounded_preview, preview_with_result, PREVIEW_BYTES


class OwnedLocalShellBackend(LocalShellBackend):
    def __init__(self, *args, cancel_requested: Callable[[], bool] | None = None, result_retainer=None, **kwargs):
        self._cancel_requested = cancel_requested
        self._result_retainer = result_retainer
        super().__init__(*args, **kwargs)

    def execute(self, command: str, *, timeout: int | None = None) -> ExecuteResponse:
        if sys.platform != "win32":
            # Keep the pinned native non-Windows process semantics. Its
            # preview truncation must not run before application retention.
            acquisition = copy.copy(self)
            acquisition._max_output_bytes = sys.maxsize
            result = LocalShellBackend.execute(acquisition, command, timeout=timeout)
            return self._present(command, result.output, result.exit_code,
                timeout if timeout is not None else self._default_timeout)
        if not command or not isinstance(command, str):
            return ExecuteResponse(output="Error: Command must be a non-empty string.", exit_code=1, truncated=False)
        effective_timeout = timeout if timeout is not None else self._default_timeout
        if effective_timeout <= 0:
            raise ValueError(f"timeout must be positive, got {effective_timeout}")
        try:
            result = run_windows_command(command, cwd=self.cwd, env=self._env, timeout=effective_timeout,
                cancel_requested=self._cancel_requested)
        except HarnessError:
            # Unconfirmed effects retain the project reservation; never turn
            # uncertain ownership into an ordinary tool failure.
            raise
        except OSError as exc:
            return ExecuteResponse(output=f"Error executing command ({type(exc).__name__}): {exc}", exit_code=1, truncated=False)
        parts = [result.stdout] if result.stdout else []
        if result.stderr:
            parts.extend(f"[stderr] {line}" for line in result.stderr.strip().split("\n"))
        output = "\n".join(parts) if parts else "<no output>"
        if result.returncode:
            output = f"{output.rstrip()}\n\nExit code: {result.returncode}"
        return self._present(command, output, result.returncode, effective_timeout)

    def _present(self, command, output, exit_code, effective_timeout):
        preview_limit = min(self._max_output_bytes, PREVIEW_BYTES)
        truncated = len(output.encode("utf-8")) > preview_limit
        if truncated:
            retained = self._result_retainer(output, source={"tool": "execute", "command_sha256": hashlib.sha256(command.encode("utf-8")).hexdigest(),
                "exit_code": exit_code, "timeout_seconds": effective_timeout}) if self._result_retainer else None
            if retained:
                output = preview_with_result(output, retained, tail=True, limit=preview_limit - 40)
            else:
                output = bounded_preview(output, max(0, preview_limit - 100), tail=True)
                output += "\nOutput preview is bounded in UTF-8 bytes. Full retention is unavailable for this standalone backend."
        return ExecuteResponse(output=output, exit_code=exit_code, truncated=truncated)
