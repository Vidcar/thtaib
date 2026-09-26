"""Native LocalShellBackend with application-owned Windows process lifetime."""
from __future__ import annotations

import sys
from collections.abc import Callable

from deepagents.backends import LocalShellBackend
from deepagents.backends.protocol import ExecuteResponse

from workbench_backend.errors import HarnessError
from workbench_backend.process_tree import run_windows_command


class OwnedLocalShellBackend(LocalShellBackend):
    def __init__(self, *args, cancel_requested: Callable[[], bool] | None = None, **kwargs):
        self._cancel_requested = cancel_requested
        super().__init__(*args, **kwargs)

    def execute(self, command: str, *, timeout: int | None = None) -> ExecuteResponse:
        if sys.platform != "win32":
            return super().execute(command, timeout=timeout)
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
        truncated = len(output) > self._max_output_bytes
        if truncated:
            output = output[:self._max_output_bytes] + f"\n\n... Output truncated at {self._max_output_bytes} bytes."
        if result.returncode:
            output = f"{output.rstrip()}\n\nExit code: {result.returncode}"
        return ExecuteResponse(output=output, exit_code=result.returncode, truncated=truncated)
