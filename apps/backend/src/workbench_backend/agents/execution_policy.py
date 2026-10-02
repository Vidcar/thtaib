"""One operation's dispatch authority, shared by its inline children and review."""
from __future__ import annotations

import asyncio
import threading
from contextvars import ContextVar
from contextlib import contextmanager
from typing import Any

from workbench_backend.errors import HarnessError


class ToolReservationReleased(Exception):
    """A superseded file call is leaving the shared dispatch id for its owner."""


PLAN_TOOLS = frozenset({"ls", "read_file", "glob", "grep", "read_attachment", "read_reference", "read_tool_result", "find_tools", "search_knowledge", "write_todos", "ask_user", "echo", "time_now", "task"})
PLAN_INSTRUCTIONS = "Plan mode: investigate and produce a plan. Read-only tools, questions and the checklist are available. Do not modify files, run shell commands, save memory or perform external actions. Switching Access does not permit implementation in Plan mode."
CURRENT_TOOL_CALL: ContextVar[str] = ContextVar("workbench_current_tool_call", default="")


def plan_tool_names(connection_snapshots=()) -> set[str]:
    """Permit only locally owned public readers, never remote effect annotations.

    Callers must still intersect this eligibility with the accepted selection.
    Dispatch keeps the connection's frozen schema/version and live checks.
    """
    from workbench_backend.connections.service import namespaced
    allowed = set(PLAN_TOOLS)
    for connection in connection_snapshots:
        if connection.kind != "public_web" or connection.transport != "builtin":
            continue
        for tool in connection.tools:
            if tool.remote_name in {"search_web", "read_web_page"} and tool.name == namespaced(connection.id, tool.remote_name):
                allowed.add(tool.name)
    return allowed


def require_setup_capabilities(configuration, *, project_bound: bool, presented_tools: list[str] | None) -> None:
    """Requirements remain restrictions after Plan and parent-tool intersection."""
    if configuration.requires_project and not project_bound:
        raise HarnessError("This agent setup requires a project folder.", code="setup_project_required", status_code=409)
    if configuration.requires_host_shell and (not project_bound or presented_tools is not None and "execute" not in presented_tools):
        raise HarnessError("This agent setup requires the host-shell tool in a project. Select it explicitly before running.", code="setup_shell_required", status_code=409)


class ExecutionControl:
    def __init__(self, root: Any, publish=None, cancelled=None):
        self.root = root
        self.publish = publish or (lambda: None)
        self.cancelled = cancelled or (lambda: False)
        self._lock = threading.RLock()
        self._calls = set(root.dispatched_tool_ids)
        self._completed = set(root.completed_tool_ids)
        self._inflight: set[str] = set()
        self._passive: set[str] = set()
        self._active_models = 0
        self._settled = threading.Condition(self._lock)
        self._model_locks: dict[str, asyncio.Lock] = {}

    def take_browser_control(self) -> None:
        with self._lock:
            self._require_not_cancelled(self.root)
            if self.root.browser_control == "agent":
                self.root.browser_revision += 1
                self.root.browser_control = "taking_control"
                self.publish()

    def wait_for_browser_settle(self) -> None:
        # Delegation waits own no model or external action. The child's calls
        # carry the same authority and are counted individually.
        with self._settled:
            while self._active_models or self._inflight.difference(self._passive):
                self._settled.wait(timeout=0.2)
                self._require_not_cancelled(self.root)
            self._require_not_cancelled(self.root)
            if self.root.status not in {"completed", "failed"} and self.root.browser_control != "agent":
                self.root.browser_control = "user"
                self.publish()

    def return_browser_control(self, observation: str) -> None:
        with self._settled:
            self._require_not_cancelled(self.root)
            self.root.browser_observation = observation[:32000]
            self.root.browser_control = "agent"
            self.publish()
            self._settled.notify_all()

    def invalidate_browser_state(self, observation: str) -> None:
        """Replace page evidence without changing task or approval ownership."""
        with self._lock:
            self.root.browser_revision += 1
            self.root.browser_observation = observation[:32000]
            self.publish()

    def wait_for_browser_return(self) -> bool:
        with self._settled:
            while self.root.browser_control != "agent":
                if self.cancelled() or self.root.status in {"cancel_requested", "cancelled"}:
                    return False
                self._settled.wait(timeout=0.2)
            return not self.cancelled() and self.root.status not in {"cancel_requested", "cancelled"}

    def _pause_dispatch(self, run: Any, identity: str) -> None:
        """A native graph boundary, before any dispatch reservation or effect.

        Persist the boundary so node replay consumes the same interrupt even
        after Return to agent has released the shared authority.
        """
        from langgraph.types import interrupt
        remembered = list(self.root.browser_pause_dispatches.get(identity, []))
        for revision in remembered:
            interrupt({"kind": "browser_control", "thread_id": self.root.thread_id,
                "revision": revision})
        if self.root.browser_control != "agent":
            remembered.append(self.root.browser_revision)
            self.root.browser_pause_dispatches[identity] = remembered
            self.publish()
            interrupt({"kind": "browser_control", "thread_id": self.root.thread_id,
                "revision": remembered[-1]})
        self.require_dispatch(run)
        if identity in self.root.browser_pause_dispatches:
            self.root.browser_pause_dispatches.pop(identity)
            self.publish()

    @contextmanager
    def model_dispatch(self, run: Any, *, purpose: str = "work", resumable: bool = True):
        with self._lock:
            self.require_dispatch(run)
            if resumable:
                self._pause_dispatch(run, f"{run.id}:model:{purpose}")
            else:
                # Compilation is outside a graph task, so there is no native
                # checkpoint boundary yet. Its optional probe still shares the
                # same dispatch/drain authority and cannot start during takeover.
                while self.root.browser_control != "agent":
                    self._settled.wait(timeout=0.2)
                    self.require_dispatch(run)
            revision = self.root.browser_revision
            self._active_models += 1
        try:
            yield revision
        finally:
            with self._settled:
                self._active_models -= 1
                self._settled.notify_all()

    def observe_model_response(self, run: Any, response: Any, revision: int) -> None:
        from workbench_backend.browser.service import BROWSER_TOOL_NAMES
        with self._lock:
            changed = False
            for message in getattr(response, "result", []):
                for call in getattr(message, "tool_calls", []):
                    if call.get("name") in BROWSER_TOOL_NAMES and call.get("id"):
                        self.root.browser_tool_proposals[f"{run.id}:{call['id']}"] = revision
                        changed = True
            if changed:
                self.publish()

    def stale_browser_action(self, run: Any, call_id: str, name: str) -> bool:
        # Fresh observations are safe, but an old proposed mutation must be
        # reconsidered by the model against the page after human control.
        from workbench_backend.browser.service import BROWSER_READ_TOOLS, BROWSER_TOOL_NAMES
        if name not in BROWSER_TOOL_NAMES:
            return False
        if name in BROWSER_READ_TOOLS:
            return False
        with self._lock:
            return self.root.browser_tool_proposals.get(f"{run.id}:{call_id}",
                self.root.browser_revision) < self.root.browser_revision

    def _require_not_cancelled(self, run: Any) -> None:
        if self.cancelled() or self.root.status in {"cancel_requested", "cancelled"} or run.status in {"cancel_requested", "cancelled"}:
            raise HarnessError("This run is stopping; no further model or tool call was dispatched.", code="run_cancelling", status_code=409)

    def require_dispatch(self, run: Any) -> None:
        self._require_not_cancelled(run)
        with self._lock:
            if any(item.outcome == "uncertain" and not item.evidence.get("acknowledged_at")
                   for item in self.root.tool_outcomes.values()):
                raise HarnessError("An action has unconfirmed effects. Inspect and acknowledge it before continuing; it will not be repeated automatically.",
                    code="effects_unconfirmed", status_code=409)

    def tool_call_inflight(self, run: Any, call_id: str) -> bool:
        with self._lock:
            return f"{run.id}:{call_id}" in self._inflight

    def reserve_tool(self, run: Any, call_id: str, name: str = "") -> None:
        with self._lock:
            self.require_dispatch(run)
            identity = f"{run.id}:{call_id}"
            self._pause_dispatch(run, identity)
            if identity in self._inflight:
                raise HarnessError("A repeated tool-call identity was not executed again.",
                    code="duplicate_tool_call", status_code=409, details={"inflight": True})
            if identity in self._completed:
                raise HarnessError("A repeated tool-call identity was not executed again.", code="duplicate_tool_call", status_code=409)
            if identity in self._calls:
                self._inflight.add(identity)
                if name == "task":
                    self._passive.add(identity)
                return
            limit = self.root.budgets.max_tool_calls if self.root.budgets else None
            if limit is not None and self.root.dispatched_tool_calls >= limit:
                self.root.stop_reason = "tool_budget_exhausted"
                raise HarnessError("The selected tool-call budget was reached. Results are retained; no further tool was dispatched.", code="tool_budget_exhausted", status_code=409)
            self._calls.add(identity)
            self._inflight.add(identity)
            if name == "task":
                self._passive.add(identity)
            self.root.dispatched_tool_ids.append(identity)
            self.root.dispatched_tool_calls += 1
            if run is not self.root:
                run.dispatched_tool_calls += 1
            self.publish()

    def reopen_completed_tool(self, run: Any, call_id: str) -> None:
        """Let a later file attempt reserve an id an older attempt already finished."""
        with self._lock:
            self._completed.discard(f"{run.id}:{call_id}")

    @contextmanager
    def tool_dispatch(self, run, call_id, name=""):
        from langgraph.errors import GraphInterrupt
        self.reserve_tool(run, call_id, name)
        identity = f"{run.id}:{call_id}"
        completed = True
        try:
            yield not self.stale_browser_action(run, call_id, name)
        except (GraphInterrupt, ToolReservationReleased):
            # Approval resumes this id. A superseded file call leaves it for the owner.
            completed = False
            raise
        finally:
            with self._lock:
                self._inflight.discard(identity)
                self._passive.discard(identity)
                if completed:
                    self._completed.add(identity)
                    self.root.completed_tool_ids.append(identity)
                    self.publish()
                self._settled.notify_all()

    def model_lock(self, deployment_id: str) -> asyncio.Lock:
        # All owned graphs execute on the shared checkpoint loop.
        return self._model_locks.setdefault(deployment_id, asyncio.Lock())

    def record_tool_outcome(self, run, outcome) -> None:
        with self._lock:
            run.tool_outcomes[outcome.call_id] = outcome
            if run is not self.root:
                self.root.tool_outcomes[f"{run.id}:{outcome.call_id}"] = outcome
            self.publish()
