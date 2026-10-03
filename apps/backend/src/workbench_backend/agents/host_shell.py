"""Host action approval policy for the embedded Deep Agents harness.

Uses ``LocalShellBackend``, ``permissions=``, and ``interrupt_on=``. The
framework pauses selected ``execute`` calls in Ask mode; the application persists native
interrupts and surfaces them through shared Chat.

Sources consulted for pinned Deep Agents:

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
from langchain_core.tools import ToolException

from workbench_backend.agents.harness_backend import host_shell_requested
from workbench_backend.agents.memory_skills import knowledge_routes_selected
from workbench_backend.state.preferences import HOST_COMMAND_ACTIONS, chat_confirmation_thread, is_host_command_action, matched_permission_snapshot, resolved_starting_folder
from workbench_backend.agents.schemas import (
    AgentRun,
    CapabilitySetupRequest,
    InterruptDecision,
    PendingInterrupt,
    PendingInterruptAction,
    ToolMode,
    UserQuestion,
)
from pydantic import ValidationError

SKILLS_WRITE_DENY_PATHS = ("/skills/**",)
OWNED_RESULT_WRITE_DENY_PATHS = ("/large_tool_results/owned/**",)

# These names belong to Workbench-owned adapters. Target inspection and
# screenshot capture are read operations once the browser/window scope is
# granted; actions still pass through the existing exact-argument Ask flow.
VISUAL_ACTION_TOOLS = frozenset({
    "browser_navigate", "browser_navigate_back", "browser_tabs",
    "browser_click", "browser_hover", "browser_press_key", "browser_type",
    "browser_select_option", "browser_fill_form", "browser_resize",
    "browser_handle_dialog", "desktop_invoke", "desktop_set_value",
    "browser_drag", "browser_file_upload", "browser_mouse_move_xy", "browser_mouse_click_xy",
    "browser_mouse_drag_xy", "browser_mouse_down", "browser_mouse_up", "browser_mouse_wheel",
    "desktop_send_keys", "start_preview", "stop_preview",
    "browser_emulate_media", "start_command", "stop_command",
    "apply_edits", "execute_skill_script", "list_connection_resources", "read_connection_resource",
})

HOST_SHELL_NOTE = (
    "Host shell has no isolation. Commands run through Deep Agents "
    "LocalShellBackend. A project command starts in that project. A command "
    "without a project starts in the resolved user profile. Commands inherit "
    "the backend process environment. permissions= apply only to routed filesystem "
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
    rules: list[FilesystemPermission] = [FilesystemPermission(
        operations=["write"], paths=list(OWNED_RESULT_WRITE_DENY_PATHS), mode="deny")]
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

    The first This computer command in a chat pauses in Ask and in Full access.
    After this chat confirms, Full access proceeds and Ask matches the exact command
    and resolved starting folder. A typed question always pauses.
    """

    mode = run.approval_mode if run.approval_mode in {"ask", "full_access"} else "ask"
    auto_external = mode == "full_access"
    try:
        starting_folder = resolved_starting_folder(run)
    except ValueError:
        starting_folder = ""

    def shell_confirmed() -> bool:
        thread_id = chat_confirmation_thread(run)
        check = getattr(grants, "host_shell_confirmed", None) if grants is not None else None
        return bool(thread_id and check and check(thread_id))

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

    def requires_approval(request: ToolCallRequest, name="execute") -> bool:
        call = request.tool_call
        args = call.get("args", {}) if isinstance(call, dict) else getattr(call, "args", {})
        if not is_host_command_action(name, args):
            return False if auto_external else not saved_permission(name, args, request)
        thread_id = chat_confirmation_thread(run)
        # A chat shows one card before any stored grant, including Full access.
        if thread_id and not shell_confirmed():
            return True
        if auto_external and (shell_confirmed() or (not thread_id and run.project_path)):
            return False
        if saved_permission(name, args, request):
            return False
        return True

    result = {
        name: {
            "allowed_decisions": ["approve", "reject"],
            "when": lambda request, name=name: requires_approval(request, name),
            "description": (lambda call, state, runtime:
                f"This computer command (no isolation). Approve to run on this machine starting in {starting_folder}."
                if is_host_command_action("start_preview", call.get("args", {}))
                else "Preview this exact project HTML entry. Approval does not enable host commands."
            ) if name == "start_preview" else (
                "This computer command (no isolation). Approve to run on this machine "
                f"starting in {starting_folder}."
            ),
        }
        for name in HOST_COMMAND_ACTIONS.intersection(run.presented_tools)
        if name != "execute" or host_shell_requested(run)
    }
    if "ask_user" in run.presented_tools:
        result["ask_user"] = {
            "allowed_decisions": ["respond", "reject"],
            "description": "Answer this task question. Answering does not grant access to any other tool.",
        }
    for name in ("write_file", "edit_file", "delete"):
        if name not in run.presented_tools:
            continue
        def file_approval(request: ToolCallRequest, name=name) -> bool:
            call = request.tool_call
            args = call.get("args", {}) if isinstance(call, dict) else getattr(call, "args", {})
            if auto_external:
                return False
            return not saved_permission(name, args, request)
        result[name] = {"allowed_decisions": ["approve", "reject"], "when": file_approval,
            "description": "Permanently delete this exact project target and its subtree. There is no recycle bin or automatic undo. Review the target before allowing deletion."
                if name == "delete" else "Change a file in this project. Review the exact source and destination before allowing it."}
    for name in (VISUAL_ACTION_TOOLS - HOST_COMMAND_ACTIONS).intersection(run.presented_tools):
        def visual_approval(request: ToolCallRequest, name=name) -> bool:
            call = request.tool_call
            args = call.get("args", {}) if isinstance(call, dict) else getattr(call, "args", {})
            # Listing tabs does not navigate or mutate the browser. Other tab
            # actions can open, select, or close tabs.
            if name == "browser_tabs" and isinstance(args, dict) and args.get("action") == "list":
                return False
            if name == "apply_edits" and isinstance(args, dict) and args.get("base_sha256") is None:
                return False
            if auto_external:
                return False
            return not saved_permission(name, args, request)
        result[name] = {
            "allowed_decisions": ["approve", "reject"],
            "when": visual_approval,
            "description": "Use this selected operation with these exact inputs. Approval does not enable other operations.",
        }
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


def recheck_saved_authorization(run: AgentRun, name: str, args: dict, call_id: str, grants: Any) -> None:
    """Recheck the particular saved grant immediately before an effect.

    A newly added or broader grant must not substitute for the one recorded
    by the native approval predicate. Explicit once approvals have no saved
    grant and continue through their own native resume authority.
    """
    if run.tool_authorizations.get(call_id) != "saved_permission":
        return
    snapshot = run.tool_authorization_grants.get(call_id)
    if snapshot is None or grants is None or grants.matching_grant_by_id(run, name, args, snapshot.id) is None:
        raise ToolException("The saved permission used for this action was revoked or no longer matches. No action ran. Retry to request current approval.")


def approval_mode_instructions(mode: str, *, compact: bool = False) -> str:
    """Explain the same per-turn policy enforced by the tool approval gates."""

    if compact:
        policy = (
            "Full access. The first This computer command in this chat pauses. Later selected commands proceed."
            if mode == "full_access"
            else "Ask. Selected actions pause unless this chat confirmed This computer and a saved matching permission allows them."
        )
        return f"Access for this turn: {policy} The application handles access decisions. Task questions still need an answer. Access cannot enable unselected tools or automatic memory saving."
    if mode == "full_access":
        policy = (
            "Access for this turn: Full access. Selected file mutations and external tools "
            "proceed under this mode without a permission card. The first This computer command in this chat still pauses. "
            "Later commands in this chat proceed. "
        )
    else:
        policy = (
            "Access for this turn: Ask. Selected file mutations, shell commands, and external tools pause unless a saved matching grant allows them. "
            "This computer needs this chat's own confirmation first, then the exact command and resolved starting folder. "
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
    if value.get("kind") == "browser_control":
        return PendingInterrupt(kind="browser_control", environment="browser_control",
            note="The browser is under your control. Return to agent in the Browser tab to continue.")
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
        setup = None
        if value.get("kind") == "capability_setup" and isinstance(item.get("setup"), dict):
            try:
                setup = CapabilitySetupRequest.model_validate(item["setup"])
            except ValidationError:
                return None
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
                setup=setup,
            )
        )
    if not actions:
        return None
    if value.get("kind") == "capability_setup" and all(action.setup is not None for action in actions):
        return PendingInterrupt(action_requests=actions, kind="capability_setup", environment="capability_setup",
            note="Repair the selected feature, then continue; setup does not grant additional access.")
    if all(is_host_command_action(action.name, action.args) for action in actions):
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
        if action.setup is not None:
            if decision.type == "respond" and decision.message != "continue":
                raise ValueError("Setup requires Continue or Skip")
            if decision.type not in {"respond", "reject"}:
                raise ValueError("Setup cannot grant access")
            if decision.type == "respond" and action.setup.requires_new_input:
                raise ValueError("This change requires a new input with the updated selection")
        elif action.name == "ask_user":
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
    if isinstance(value, dict) and (value.get("action_requests") or value.get("kind") == "browser_control"):
        return value
    return None
