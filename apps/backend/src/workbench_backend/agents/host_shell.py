"""Windows host shell policy on Deep Agents 0.7.15 (ENV-001 / OQ-003).

Uses ``LocalShellBackend``, ``permissions=``, and ``interrupt_on=``. The
framework pauses dangerous ``execute`` calls; the application persists native
interrupts and surfaces them through shared Chat.

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

from workbench_backend.errors import HarnessError

import re
from typing import Any

from deepagents import FilesystemPermission
from langchain.agents.middleware import ToolCallRequest

from workbench_backend.agents.harness_backend import host_shell_requested
from workbench_backend.agents.memory_skills import knowledge_routes_selected
from workbench_backend.agents.schemas import (
    AgentRun,
    InterruptDecision,
    PendingInterrupt,
    PendingInterruptAction,
    ToolMode,
)

# Compound / redirect / substitution forms are never auto-allowed, even when
# the first token is a read-only command.
_UNSAFE_META = re.compile(r"[;&|`$><\n\r%!^()\"'{}\[\]*?~\\]")

_NO_ARG_COMMANDS = frozenset({"pwd", "whoami", "hostname", "ver"})
_SAFE_ECHO_FLAGS = frozenset({"on", "off"})
_SAFE_DIR_FLAGS = frozenset({"/b", "/a"})
_SAFE_LS_FLAGS = frozenset({"-a", "-l", "-la", "-al"})
_SAFE_LOOKUP_FLAGS = frozenset({"/q"})
_SAFE_GIT_STATUS_FLAGS = frozenset({"--short", "-s", "--porcelain", "--porcelain=v1"})
_SAFE_GIT_LOG_FLAGS = frozenset({"--oneline", "--decorate", "--graph"})
_SAFE_GIT_BRANCH_FLAGS = frozenset({"--show-current", "-a", "--all", "-r", "--remotes"})
_SAFE_GIT_DIFF_FLAGS = frozenset(
    {
        "--stat",
        "--name-only",
        "--name-status",
        "--cached",
        "--staged",
        "--check",
        "--no-ext-diff",
        "--no-textconv",
    }
)
_SAFE_GIT_SHOW_FLAGS = frozenset(
    {"--stat", "--name-only", "--name-status", "--no-ext-diff", "--no-textconv"}
)
_SAFE_GIT_REV_PARSE_FLAGS = frozenset({"--show-toplevel", "--is-inside-work-tree", "--abbrev-ref"})

# Routed prefixes the composite already isolates. Deny a unused subtree so
# ``permissions=`` is real without blocking harness scratch writes.
PERMISSION_DENY_PATHS = (
    "/large_tool_results/denied/**",
    "/conversation_history/denied/**",
    "/retrieved/denied/**",
)
SKILLS_WRITE_DENY_PATHS = ("/skills/**",)

HOST_SHELL_NOTE = (
    "Host shell has no isolation. Commands run through Deep Agents "
    "LocalShellBackend with the bound project as cwd and inherit the backend "
    "process environment. permissions= apply only to routed filesystem "
    "prefixes while the default backend is a sandbox. Access or an explicit "
    "saved permission controls execution; the application persists native interrupts and "
    "surfaces them through shared Chat."
)


def is_dangerous_shell_command(command: str) -> bool:
    """True when ``execute`` must pause for approval.

    Only explicitly understood command/argument forms are auto-allowed.
    Quotes, expansions, unknown options and ambiguous forms need approval.
    """

    stripped = command.strip() if isinstance(command, str) else ""
    if not stripped:
        return True
    if _UNSAFE_META.search(stripped):
        return True
    if not re.fullmatch(r"[A-Za-z0-9_./:=+ \t-]+", stripped):
        return True
    tokens = _split_command(stripped)
    if not tokens:
        return True
    head = tokens[0]
    if "/" in head or "\\" in head:
        return True
    args = tokens[1:]
    if head in _NO_ARG_COMMANDS:
        return bool(args)
    if head == "echo":
        return not _safe_echo_args(args)
    if head in {"dir", "ls"}:
        return not _safe_list_args(args, _SAFE_DIR_FLAGS if head == "dir" else _SAFE_LS_FLAGS)
    if head == "type":
        return not _safe_read_file_args(args)
    if head in {"where", "which"}:
        return not _safe_lookup_args(args)
    if head == "git":
        return not _is_safe_git_command(args)
    return True


def _split_command(command: str) -> list[str]:
    # Quote/escape/expansion forms were rejected above. Do not pretend that
    # shlex understands both cmd.exe and POSIX shell quoting semantics.
    return command.split()


def _is_safe_git_command(args: list[str]) -> bool:
    if not args:
        return False
    subcommand = args[0]
    rest = args[1:]
    if subcommand == "status":
        return _only_allowed_flags(rest, _SAFE_GIT_STATUS_FLAGS)
    if subcommand == "log":
        return _safe_git_log_args(rest)
    if subcommand == "branch":
        return _only_allowed_flags(rest, _SAFE_GIT_BRANCH_FLAGS)
    if subcommand == "diff":
        return _safe_git_path_args(
            rest,
            _SAFE_GIT_DIFF_FLAGS,
            required_flags=frozenset({"--no-ext-diff", "--no-textconv"}),
        )
    if subcommand == "show":
        return _safe_git_path_args(
            rest,
            _SAFE_GIT_SHOW_FLAGS,
            required_flags=frozenset({"--no-ext-diff", "--no-textconv"}),
        )
    if subcommand == "rev-parse":
        return _only_allowed_flags(rest, _SAFE_GIT_REV_PARSE_FLAGS)
    return False


def _only_allowed_flags(args: list[str], allowed: frozenset[str]) -> bool:
    return all(arg in allowed for arg in args)


def _safe_echo_args(args: list[str]) -> bool:
    if not args:
        return True
    if len(args) == 1 and args[0].lower() in _SAFE_ECHO_FLAGS:
        return True
    return all(_is_plain_word(arg) for arg in args)


def _safe_list_args(args: list[str], allowed: frozenset[str]) -> bool:
    paths = 0
    for arg in args:
        lower = arg.lower()
        if lower in allowed:
            continue
        if arg.startswith("-") or arg.startswith("/"):
            return False
        if _looks_unsafe_path_arg(arg):
            return False
        paths += 1
    return paths <= 1


def _safe_read_file_args(args: list[str]) -> bool:
    return bool(args) and all(
        not arg.startswith("-") and not arg.startswith("/") and not _looks_unsafe_path_arg(arg)
        for arg in args
    )


def _safe_lookup_args(args: list[str]) -> bool:
    if not args:
        return False
    for arg in args:
        lower = arg.lower()
        if lower in _SAFE_LOOKUP_FLAGS:
            continue
        if arg.startswith("-") or arg.startswith("/") or not _is_plain_word(arg):
            return False
    return True


def _safe_git_log_args(args: list[str]) -> bool:
    index = 0
    while index < len(args):
        arg = args[index]
        if arg in _SAFE_GIT_LOG_FLAGS:
            index += 1
            continue
        if arg in {"-n", "--max-count"}:
            if index + 1 >= len(args) or not args[index + 1].isdigit():
                return False
            index += 2
            continue
        if arg.startswith("-n") and arg[2:].isdigit():
            index += 1
            continue
        return False
    return True


def _safe_git_path_args(
    args: list[str],
    allowed_flags: frozenset[str],
    *,
    required_flags: frozenset[str] = frozenset(),
) -> bool:
    path_mode = False
    seen_flags: set[str] = set()
    for arg in args:
        if arg == "--":
            path_mode = True
            continue
        if not path_mode and arg.startswith("-"):
            if arg not in allowed_flags:
                return False
            seen_flags.add(arg)
            continue
        if arg.startswith("-") or _looks_unsafe_path_arg(arg):
            return False
    if not required_flags.issubset(seen_flags):
        return False
    return True


def _looks_unsafe_path_arg(arg: str) -> bool:
    return (
        not arg
        or arg.startswith("/")
        or "\\" in arg
        or ":" in arg
        or ".." in arg.split("/")
    )


def _is_plain_word(arg: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z0-9_.:-]+", arg))


def execute_requires_approval(request: ToolCallRequest) -> bool:
    """``interrupt_on`` ``when`` predicate: True pauses, False auto-approves."""

    call = request.tool_call
    args = call.get("args") if isinstance(call, dict) else getattr(call, "args", {})
    command = args.get("command") if isinstance(args, dict) else None
    return is_dangerous_shell_command(command if isinstance(command, str) else "")


def filesystem_permissions_for_run(run: AgentRun) -> list[FilesystemPermission] | None:
    """Route-scoped allow/deny rules, or none when no routed backend is attached.

    ``/skills/**`` writes are denied whenever selected skills are materialized,
    including project-less and recorded-tool knowledge runs. Unused-subtree
    denies stay on live project backends. Rules stay on routed prefixes so
    a sandbox default (``LocalShellBackend``) is not given project-wide
    ``permissions=``.
    """

    recorded = run.tool_mode is ToolMode.recorded_tool
    knowledge_routes = knowledge_routes_selected(
        run.memory_version_refs,
        run.skill_version_refs,
    )
    if recorded and not knowledge_routes:
        return None
    rules: list[FilesystemPermission] = []
    if not recorded and run.project_path:
        rules.append(
            FilesystemPermission(
                operations=["write"],
                paths=list(PERMISSION_DENY_PATHS),
                mode="deny",
            )
        )
    if run.skill_version_refs:
        rules.append(
            FilesystemPermission(
                operations=["write"],
                paths=list(SKILLS_WRITE_DENY_PATHS),
                mode="deny",
            )
        )
    return rules or None


def interrupt_on_for_run(run: AgentRun, grants: Any = None) -> dict[str, bool | dict[str, Any]] | None:
    """HITL config for protected tools. The run's approval mode chooses which pauses remain.

    Ask keeps every pause. Approve for me permits recoverable project text changes.
    Full access also lets a selected shell command and external tool proceed.
    A typed question and a memory proposal are not decided here.
    """

    mode = run.approval_mode if run.approval_mode in {"ask", "approve_for_me", "full_access"} else "ask"
    auto_file = mode in {"approve_for_me", "full_access"}
    auto_external = mode == "full_access"

    def saved_permission(name, args, request):
        if grants is None or not grants.matches(run, name, args):
            return False
        call = request.tool_call
        ident = call.get("id") if isinstance(call, dict) else getattr(call, "id", None)
        if ident:
            run.tool_authorizations[ident] = "saved_permission"
        return True

    def requires_approval(request: ToolCallRequest) -> bool:
        call = request.tool_call
        args = call.get("args", {}) if isinstance(call, dict) else getattr(call, "args", {})
        if auto_external:
            return False
        if saved_permission("execute", args, request):
            return False
        return True

    result = {
        "execute": {
            "allowed_decisions": ["approve", "reject"],
            "when": requires_approval,
            "description": (
                "Host shell command (no isolation). Approve to run on this machine "
                "in the bound project working directory."
            ),
        }
    } if host_shell_requested(run) else {}
    for name in ("write_file", "edit_file", "rename_file", "delete_file"):
        if name not in run.presented_tools:
            continue
        def file_approval(request: ToolCallRequest, name=name) -> bool:
            call = request.tool_call
            args = call.get("args", {}) if isinstance(call, dict) else getattr(call, "args", {})
            if auto_external:
                return False
            if auto_file and reversible_file_request(run, name, args):
                ident = call.get("id") if isinstance(call, dict) else getattr(call, "id", None)
                if ident:
                    run.tool_authorizations[ident] = "recoverable_edit"
                return False
            return not saved_permission(name, args, request)
        result[name] = {"allowed_decisions": ["approve", "reject"], "when": file_approval,
            "description": "Change a file in this project. Review the exact source and destination before allowing it."}
    for connection in run.connection_snapshots:
        if connection.kind != "mcp":
            continue
        for selected in connection.tools:
            name = selected.name
            if name not in run.presented_tools:
                continue
            def external_approval(request: ToolCallRequest, name=name) -> bool:
                if auto_external:
                    return False
                call = request.tool_call
                args = call.get("args", {}) if isinstance(call, dict) else getattr(call, "args", {})
                return not saved_permission(name, args, request)
            result[name] = {"allowed_decisions": ["approve", "reject"], "when": external_approval,
                "description": f"Use {selected.remote_name} through {connection.name}. Review the exact inputs before allowing this external action."}
    return result or None


def approval_mode_instructions(mode: str) -> str:
    """Explain the same per-turn policy enforced by the tool approval gates."""

    if mode == "full_access":
        policy = (
            "Access for this turn: Full access. Selected file mutations, shell commands, "
            "and external tools proceed under this mode without a permission card. "
        )
    elif mode == "approve_for_me":
        policy = (
            "Access for this turn: Approve for me. Selected reversible project text edits proceed "
            "without a permission card when a complete recovery image can be recorded. Shell commands, other file mutations and external tools "
            "still pause unless a saved matching grant allows them. "
        )
    else:
        policy = (
            "Access for this turn: Ask. Selected file mutations, shell commands, and external tools pause unless a saved matching grant allows them. "
        )
    return policy + (
        "Use selected tools directly to carry out the person's task; the application "
        "handles any required permission decision. Do not duplicate that decision with "
        "a separate chat question. Ask for missing task choices when necessary. "
        "Questions still require the person's answer in every mode. Access does not "
        "enable unselected tools, expand the authorized task, bypass tool restrictions, "
        "or permit automatic memory saving."
    )


def reversible_file_request(run: AgentRun, name: str, args: dict[str, Any]) -> bool:
    """Auto-approval requires the same complete images as the file recorder."""
    from pathlib import Path
    from workbench_backend.agents.file_changes import file_image, project_file, TEXT_LIMIT
    if not run.project_path:
        return False
    try:
        source = project_file(Path(run.project_path), str(args.get("file_path", "")))
        before = file_image(source)
        if before.exists and before.text is None:
            return False
        if name == "write_file":
            text = args.get("content")
            return isinstance(text, str) and len(text.encode("utf-8")) <= TEXT_LIMIT
        if name == "edit_file":
            old, new = args.get("old_string"), args.get("new_string")
            if before.text is None or not isinstance(old, str) or not old or not isinstance(new, str):
                return False
            result = before.text.replace(old, new, -1 if args.get("replace_all") else 1)
            return len(result.encode("utf-8")) <= TEXT_LIMIT
        if name == "rename_file":
            return before.exists and not project_file(Path(run.project_path), str(args.get("destination", ""))).exists()
        return name == "delete_file" and before.exists
    except (OSError, ValueError, HarnessError):
        return False


def pending_interrupt_from_raw(raw: Any) -> PendingInterrupt | None:
    """Normalize a LangGraph / HITL interrupt value into the run record."""

    value = _interrupt_value(raw)
    if value is None:
        return None
    if value.get("kind") == "ask_user":
        return PendingInterrupt(kind="ask_user", question=value.get("question"), environment="user_input", note="A user answer is required. This is not a permission approval.")
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
    if all(action.name == "execute" for action in actions):
        return PendingInterrupt(action_requests=actions)
    return PendingInterrupt(action_requests=actions, environment="tool_actions",
        note="Review each selected action and its exact inputs. Approval does not grant other tools or allow automatic memory saving.")


def reject_decisions_for(pending: PendingInterrupt) -> list[dict[str, str]]:
    if pending.kind == "ask_user":
        return [{"type": "user_answer", "cancelled": "true"}]
    return [
        {
            "type": "reject",
            "message": "Run cancelled before this action was approved.",
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
    if isinstance(value, dict) and (value.get("action_requests") or value.get("kind") == "ask_user"):
        return value
    return None
