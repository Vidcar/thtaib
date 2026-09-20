"""Windows host shell policy on Deep Agents 0.7.15 (ENV-001 / OQ-003).

Uses ``LocalShellBackend``, ``permissions=``, and ``interrupt_on=``. The
framework pauses dangerous ``execute`` calls; this module does not invent a
second approvals inbox (OQ-011).

Sources consulted 2026-09-19 for pinned ``deepagents==0.7.15``:

- https://docs.langchain.com/oss/python/deepagents/backends
- https://docs.langchain.com/oss/python/deepagents/human-in-the-loop
- https://docs.langchain.com/oss/python/deepagents/permissions
- installed ``deepagents/backends/local_shell.py``
- installed ``deepagents/middleware/filesystem.py``
  (``supports_execution`` + ``_all_paths_scoped_to_routes``)

``FilesystemMiddleware`` refuses project-wide ``permissions=`` when the
composite default is a sandbox (``LocalShellBackend``). Rules must be scoped
to routed prefixes. ``interrupt_on`` is the human gate for ``execute``.
"""

from __future__ import annotations

import re
from typing import Any

from deepagents import FilesystemPermission
from langchain.agents.middleware import ToolCallRequest

from workbench_backend.agents.harness_backend import (
    RESERVED_FRAMEWORK_PREFIXES,
    host_shell_requested,
)
from workbench_backend.agents.schemas import (
    AgentRun,
    InterruptDecision,
    PendingInterrupt,
    PendingInterruptAction,
    ToolMode,
)

# Compound / redirect / substitution forms are never auto-allowed, even when
# the first token is a read-only command.
_UNSAFE_META = re.compile(r"[;&|`$><\n]|&&|\|\|")

_SAFE_COMMANDS = frozenset(
    {
        "echo",
        "dir",
        "ls",
        "pwd",
        "whoami",
        "hostname",
        "ver",
        "type",
        "where",
        "which",
        "get-childitem",
        "get-location",
        "get-content",
        "get-help",
    }
)
_SAFE_GIT_SUBCOMMANDS = frozenset({"status", "log", "diff", "branch", "show", "rev-parse"})

# Routed prefixes the composite already isolates. Deny a unused subtree so
# ``permissions=`` is real without blocking harness scratch writes.
PERMISSION_DENY_PATHS = (
    "/large_tool_results/denied/**",
    "/conversation_history/denied/**",
    "/retrieved/denied/**",
)

HOST_SHELL_NOTE = (
    "Host shell has no isolation. Commands run through Deep Agents "
    "LocalShellBackend with the bound project as cwd and inherit the backend "
    "process environment. permissions= apply only to routed filesystem "
    "prefixes while the default backend is a sandbox. interrupt_on pauses "
    "dangerous execute calls. This is not a durable Approvals inbox (OQ-011)."
)


def is_dangerous_shell_command(command: str) -> bool:
    """True when ``execute`` must pause for approval.

    Auto-allow is a small read-only prefix list without shell metacharacters.
    Everything else interrupts, including empty commands.
    """

    stripped = command.strip() if isinstance(command, str) else ""
    if not stripped:
        return True
    if _UNSAFE_META.search(stripped):
        return True
    tokens = stripped.split()
    head = tokens[0].lower().rstrip("/\\")
    if "/" in head or "\\" in head:
        return True
    if head in _SAFE_COMMANDS:
        return False
    if head == "git" and len(tokens) >= 2 and tokens[1].lower() in _SAFE_GIT_SUBCOMMANDS:
        return False
    return True


def execute_requires_approval(request: ToolCallRequest) -> bool:
    """``interrupt_on`` ``when`` predicate: True pauses, False auto-approves."""

    call = request.tool_call
    args = call.get("args") if isinstance(call, dict) else getattr(call, "args", {})
    command = args.get("command") if isinstance(args, dict) else None
    return is_dangerous_shell_command(command if isinstance(command, str) else "")


def filesystem_permissions_for_run(run: AgentRun) -> list[FilesystemPermission] | None:
    """Route-scoped allow/deny rules, or none when there is no live project backend."""

    if run.tool_mode is ToolMode.recorded_tool or not run.project_path:
        return None
    return [
        FilesystemPermission(
            operations=["write"],
            paths=list(PERMISSION_DENY_PATHS),
            mode="deny",
        )
    ]


def interrupt_on_for_run(run: AgentRun) -> dict[str, bool | dict[str, Any]] | None:
    """HITL config for ``execute`` whenever LocalShellBackend is attached."""

    if not host_shell_requested(run):
        return None
    return {
        "execute": {
            "allowed_decisions": ["approve", "reject"],
            "when": execute_requires_approval,
            "description": (
                "Host shell command (no isolation). Approve to run on this machine "
                "in the bound project working directory."
            ),
        }
    }


def reserved_prefixes() -> tuple[str, ...]:
    return RESERVED_FRAMEWORK_PREFIXES


def pending_interrupt_from_raw(raw: Any) -> PendingInterrupt | None:
    """Normalize a LangGraph / HITL interrupt value into the run record."""

    value = _interrupt_value(raw)
    if value is None:
        return None
    requests = value.get("action_requests")
    reviews = value.get("review_configs")
    if not isinstance(requests, list) or not requests:
        return None
    review_map: dict[str, list[str]] = {}
    if isinstance(reviews, list):
        for item in reviews:
            if not isinstance(item, dict):
                continue
            name = item.get("action_name")
            allowed = item.get("allowed_decisions")
            if isinstance(name, str) and isinstance(allowed, list):
                review_map[name] = [str(entry) for entry in allowed]
    actions: list[PendingInterruptAction] = []
    for item in requests:
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        if not isinstance(name, str) or not name:
            continue
        args = item.get("args")
        description = item.get("description")
        actions.append(
            PendingInterruptAction(
                name=name,
                args=args if isinstance(args, dict) else {},
                description=description if isinstance(description, str) else None,
                allowed_decisions=review_map.get(name, ["approve", "reject"]),
            )
        )
    if not actions:
        return None
    return PendingInterrupt(action_requests=actions)


def reject_decisions_for(pending: PendingInterrupt) -> list[dict[str, str]]:
    return [
        {
            "type": "reject",
            "message": "Run cancelled before the host-shell command was approved.",
        }
        for _ in pending.action_requests
    ]


def validated_decision_payloads(
    pending: PendingInterrupt,
    decisions: list[InterruptDecision],
) -> list[dict[str, str]]:
    if len(decisions) != len(pending.action_requests):
        raise ValueError("interrupt_decision_count")
    payloads: list[dict[str, str]] = []
    for action, decision in zip(pending.action_requests, decisions, strict=True):
        if decision.type not in action.allowed_decisions:
            raise ValueError("interrupt_decision_not_allowed")
        payload: dict[str, str] = {"type": decision.type}
        if decision.message:
            payload["message"] = decision.message
        elif decision.type == "reject":
            payload["message"] = (
                "User rejected this host-shell command. The tool was not executed. "
                "Do not retry unless the user asks."
            )
        payloads.append(payload)
    return payloads


def _interrupt_value(raw: Any) -> dict[str, Any] | None:
    if raw is None:
        return None
    if isinstance(raw, (list, tuple)):
        for item in raw:
            found = _interrupt_value(item)
            if found is not None:
                return found
        return None
    value = getattr(raw, "value", raw)
    if isinstance(value, dict) and value.get("action_requests"):
        return value
    return None
