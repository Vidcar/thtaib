"""One operation's dispatch authority, shared by its inline children and review."""
from __future__ import annotations

import asyncio
import threading
from contextvars import ContextVar
from contextlib import contextmanager
from typing import Any

from workbench_backend.errors import HarnessError


PLAN_TOOLS = frozenset({"ls", "read_file", "glob", "grep", "read_attachment", "search_knowledge", "web_search", "write_todos", "ask_user", "echo", "time_now", "task"})
PLAN_INSTRUCTIONS = "Plan mode: investigate and produce a plan. Read-only tools, questions and the checklist are available. Do not modify files, run shell commands, save memory or perform external actions. Switching Access does not permit implementation in Plan mode."
CURRENT_TOOL_CALL: ContextVar[str] = ContextVar("workbench_current_tool_call", default="")


def require_setup_capabilities(configuration, *, project_bound: bool, presented_tools: list[str] | None) -> None:
    """Requirements remain restrictions after Plan and parent-tool intersection."""
    if configuration.requires_project and not project_bound:
        raise HarnessError("This agent setup requires a project folder.", code="setup_project_required", status_code=409)
    if configuration.requires_host_shell and (not project_bound or presented_tools is not None and "execute" not in presented_tools):
        raise HarnessError("This agent setup requires the host-shell tool in a project. Select it explicitly before running.", code="setup_shell_required", status_code=409)


class ExecutionControl:
    def __init__(self, root: Any, publish=None):
        self.root = root
        self.publish = publish or (lambda: None)
        self._lock = threading.RLock()
        self._calls = set(root.dispatched_tool_ids)
        self._completed = set(root.completed_tool_ids)
        self._inflight: set[str] = set()
        self._model_locks: dict[str, asyncio.Lock] = {}

    def require_dispatch(self, run: Any) -> None:
        if self.root.status in {"cancel_requested", "cancelled"} or run.status in {"cancel_requested", "cancelled"}:
            raise HarnessError("This run is stopping; no further model or tool call was dispatched.", code="run_cancelling", status_code=409)

    def reserve_tool(self, run: Any, call_id: str) -> None:
        with self._lock:
            self.require_dispatch(run)
            identity = f"{run.id}:{call_id}"
            if identity in self._completed or identity in self._inflight:
                raise HarnessError("A repeated tool-call identity was not executed again.", code="duplicate_tool_call", status_code=409)
            if identity in self._calls:
                self._inflight.add(identity)
                return
            limit = self.root.budgets.max_tool_calls if self.root.budgets else None
            if limit is not None and self.root.dispatched_tool_calls >= limit:
                self.root.stop_reason = "tool_budget_exhausted"
                raise HarnessError("The selected tool-call budget was reached. Results are retained; no further tool was dispatched.", code="tool_budget_exhausted", status_code=409)
            self._calls.add(identity)
            self._inflight.add(identity)
            self.root.dispatched_tool_ids.append(identity)
            self.root.dispatched_tool_calls += 1
            if run is not self.root:
                run.dispatched_tool_calls += 1
            self.publish()

    @contextmanager
    def tool_dispatch(self, run, call_id):
        from langgraph.errors import GraphInterrupt
        self.reserve_tool(run, call_id)
        identity = f"{run.id}:{call_id}"
        completed = True
        try:
            yield
        except GraphInterrupt:
            # Native approval resumes the same action identity and reservation.
            completed = False
            raise
        finally:
            with self._lock:
                self._inflight.discard(identity)
                if completed:
                    self._completed.add(identity)
                    self.root.completed_tool_ids.append(identity)
                    self.publish()

    def model_lock(self, deployment_id: str) -> asyncio.Lock:
        # All owned graphs execute on the shared checkpoint loop.
        return self._model_locks.setdefault(deployment_id, asyncio.Lock())
