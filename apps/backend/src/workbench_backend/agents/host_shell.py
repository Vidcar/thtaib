"""Windows host shell policy on Deep Agents 0.7.18.

Uses ``LocalShellBackend``, ``permissions=``, and ``interrupt_on=``. The
framework pauses selected ``execute`` calls in Ask mode; the application persists native
interrupts and surfaces them through shared Chat.

Sources consulted for pinned ``deepagents==0.7.18``:

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

from typing import Any

from deepagents import FilesystemPermission
from langchain.agents.middleware import ToolCallRequest

from workbench_backend.agents.harness_backend import host_shell_requested
from workbench_backend.agents.memory_skills import knowledge_routes_selected
from workbench_backend.state.preferences import matched_permission_snapshot
from workbench_backend.agents.schemas import (
    AgentRun,
    InterruptDecision,
    PendingInterrupt,
    PendingInterruptAction,
    ToolMode,
    UserQuestion,
)
from pydantic import ValidationError

SKILLS_WRITE_DENY_PATHS = ("/skills/**",)

HOST_SHELL_NOTE = (
    "Host shell has no isolation. Commands run through Deep Agents "
    "LocalShellBackend with the bound project as cwd and inherit the backend "
    "process environment. permissions= apply only to routed filesystem "
    "prefixes while the default backend is a sandbox. Access or an explicit "
    "saved permission controls execution; the application persists native interrupts and "
    "surfaces them through shared Chat."
)


def filesystem_permissions_for_run(run: AgentRun) -> list[FilesystemPermission] | None:
    """Route-scoped allow/deny rules, or none when no routed backend is attached.

    ``/skills/**`` writes are denied whenever selected skills are materialized,
    including project-less and recorded-tool knowledge runs. Rules stay on routed prefixes so
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

    Ask pauses selected side-effecting tools. Full access permits them.
    A typed question always pauses in either mode.
    """

    mode = run.approval_mode if run.approval_mode in {"ask", "full_access"} else "ask"
    auto_external = mode == "full_access"

    def saved_permission(name, args, request):
        matched = grants.matching_grant(run, name, args) if grants is not None else None
        if matched is None:
            return False
        call = request.tool_call
        ident = call.get("id") if isinstance(call, dict) else getattr(call, "id", None)
        if ident:
            run.tool_authorizations[ident] = "saved_permission"
            run.tool_authorization_grants[ident] = matched_permission_snapshot(matched, run)
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
    if "ask_user" in run.presented_tools:
        result["ask_user"] = {
            "allowed_decisions": ["respond", "reject"],
            "description": "Answer this task question. Answering does not grant access to any other tool.",
        }
    for name in ("write_file", "edit_file"):
        if name not in run.presented_tools:
            continue
        def file_approval(request: ToolCallRequest, name=name) -> bool:
            call = request.tool_call
            args = call.get("args", {}) if isinstance(call, dict) else getattr(call, "args", {})
            if auto_external:
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
        question = None
        if name == "ask_user" and isinstance(args, dict):
            try:
                question = UserQuestion.model_validate({**args, "choices": args.get("choices") or []})
                if question.answer_type == "choice" and not question.choices:
                    question = None
            except ValidationError:
                pass
        actions.append(
            PendingInterruptAction(
                name=name,
                args=args if isinstance(args, dict) else {},
                description=description if isinstance(description, str) else None,
                allowed_decisions=review_map.get(name, ["respond", "reject"] if name == "ask_user" else ["approve", "reject"]),
                question=question,
            )
        )
    if not actions:
        return None
    if all(action.name == "execute" for action in actions):
        return PendingInterrupt(action_requests=actions)
    if all(action.name == "ask_user" for action in actions):
        return PendingInterrupt(action_requests=actions, environment="user_input",
            note="Answer each question or cancel it.")
    return PendingInterrupt(action_requests=actions, environment="tool_actions",
        note="Review each selected action and its exact inputs. Approval does not grant other tools or allow automatic memory saving.")


def reject_decisions_for(pending: PendingInterrupt) -> list[dict[str, str]]:
    return [
        {
            "type": "reject",
            "message": (
                "The user cancelled this question. Do not repeat it unless asked."
                if action.name == "ask_user"
                else "Run cancelled before this action was approved."
            ),
        }
        for action in pending.action_requests
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
        if decision.type != "approve" and decision.scope != "once":
            raise ValueError("Only approvals can save permission grants")
        if action.name == "ask_user":
            if decision.type == "respond":
                question = action.question
                if question is None:
                    raise ValueError("This question is invalid; reject it so the assistant can retry")
                answer = decision.message
                if not isinstance(answer, str) or not answer.strip() or len(answer) > 32000:
                    raise ValueError("An answer is required")
                if question.answer_type == "choice" and answer not in question.choices:
                    raise ValueError("Choose one of the offered answers")
                if question.answer_type in {"file", "folder"}:
                    from pathlib import Path
                    chosen = Path(answer).expanduser()
                    if not chosen.is_absolute() or not (chosen.is_file() if question.answer_type == "file" else chosen.is_dir()):
                        raise ValueError("Select an existing absolute file or folder path")
            elif decision.type != "reject":
                raise ValueError("Questions require a response or rejection")
        elif decision.type == "respond":
            raise ValueError("Only questions can receive an answer")
        payload: dict[str, str] = {"type": decision.type}
        if decision.message:
            payload["message"] = decision.message
        elif decision.type == "reject":
            payload["message"] = (
                "The user cancelled this question. Do not repeat it unless asked."
                if action.name == "ask_user"
                else "User rejected this action. The tool was not executed. Do not retry unless the user asks."
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
