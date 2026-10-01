"""Durable tool effects evidence, independent of graph dispatch settlement."""
from __future__ import annotations

import hashlib
from typing import Any

from langchain_core.messages import ToolMessage
from langgraph.types import Command
from workbench_backend.agents.schemas import RunFailure, ToolMode, ToolOutcome
from workbench_backend.inference.ids import utc_now
from workbench_backend.errors import HarnessError

READ_ONLY_TOOLS = frozenset({"ls", "read_file", "glob", "grep", "read_attachment", "search_knowledge",
    "web_search", "time_now", "echo", "write_todos", "ask_user", "browser_snapshot", "browser_take_screenshot",
    "read_tool_result", "read_reference", "list_connection_resources", "read_connection_resource", "command_status"})


def file_evidence(run: Any, name: str, args: dict) -> dict:
    """Capture bounded target fingerprints before writes; never widen file access."""
    if getattr(run, "tool_mode", None) == ToolMode.recorded_tool:
        return {}
    path = args.get("file_path")
    if name not in {"write_file", "edit_file", "apply_edits"} or not run.project_path or not isinstance(path, str):
        return {}
    from workbench_backend.agents.harness_backend import resolve_project_tool_path, is_reserved_framework_path
    if is_reserved_framework_path(path):
        return {}
    try:
        resolved = resolve_project_tool_path(run.project_path, path)
        exists = resolved.exists()
        evidence = {"path": path, "before_exists": exists}
        before = None
        if exists and resolved.is_file() and resolved.stat().st_size <= 4_000_000:
            before = resolved.read_bytes()
            evidence["before_sha256"] = hashlib.sha256(before).hexdigest()
        expected = args.get("content") if name == "write_file" else None
        if name == "edit_file" and before is not None:
            text = before.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")
            old, new = args.get("old_string"), args.get("new_string")
            if isinstance(old, str):
                old = old.replace("\r\n", "\n").replace("\r", "\n")
            if isinstance(new, str):
                new = new.replace("\r\n", "\n").replace("\r", "\n")
            if isinstance(old, str) and old and isinstance(new, str) and (text.count(old) == 1 or args.get("replace_all") and old in text):
                expected = text.replace(old, new)
        if name == "apply_edits" and before is not None and args.get("base_sha256") == evidence.get("before_sha256"):
            from workbench_backend.agents.file_operations import ExactEdit, edited_original
            expected, _ = edited_original(before.decode("utf-8"), [ExactEdit.model_validate(edit) for edit in args.get("edits", [])])
        if isinstance(expected, str):
            evidence["expected_sha256"] = hashlib.sha256(expected.encode("utf-8")).hexdigest()
        return evidence
    except (OSError, ValueError, UnicodeError, HarnessError):
        return {}


def result_outcome(call_id: str, name: str, result: Any, evidence: dict | None = None,
                   *, process_stopped: bool | None = None) -> ToolOutcome:
    if isinstance(result, Command) and isinstance(result.update, dict):
        result = next((message for message in result.update.get("messages", [])
                       if isinstance(message, ToolMessage) and message.tool_call_id == call_id), result)
    # Native execute reports successful delivery separately from command exit.
    # Its artifact is structured evidence; never infer exit from output text.
    artifact = result.artifact if isinstance(result, ToolMessage) else None
    exit_code = artifact.get("exit_code") if name in {"execute", "execute_skill_script"} and isinstance(artifact, dict) else None
    command_failed = isinstance(exit_code, int) and not isinstance(exit_code, bool) and exit_code != 0
    interrupted_command = command_failed and exit_code in {124, 130}
    error = isinstance(result, ToolMessage) and (result.status == "error" or command_failed)
    content = result.content if isinstance(result, ToolMessage) else None
    settled_evidence = {**(evidence or {}), **({"exit_code": exit_code} if isinstance(exit_code, int) and not isinstance(exit_code, bool) else {})}
    deletion_uncertain = name == "delete" and settled_evidence.get("expected_absent") and (
        settled_evidence.get("after_inspected") is False
        or settled_evidence.get("after_exists") is True and (not error or any(
            settled_evidence.get(f"after_{key}") != settled_evidence.get(f"before_{key}") for key in ("entries", "files", "bytes"))))
    if name in {"execute", "execute_skill_script"} and process_stopped is not None and "exit_code" in settled_evidence:
        # Supplied by the application-owned backend contract, never inferred
        # from a command's output text or a recorded fixture.
        settled_evidence["process_stopped"] = process_stopped
    return ToolOutcome(call_id=call_id, name=name, outcome="uncertain" if interrupted_command or deletion_uncertain else "failed" if error else "succeeded",
        failure_category="runtime" if deletion_uncertain else ("cancelled" if exit_code == 130 else "runtime") if interrupted_command else "tool" if error else None,
        recovery_action="inspect_effects" if interrupted_command or deletion_uncertain else "continue" if error else "none",
        detail=("The command was interrupted. Its changes may be partial even when its processes have stopped. Inspect before continuing or repeating it."
                if interrupted_command else "Deletion effects may be partial or unconfirmed. Inspect the remaining target before repeating deletion."
                if deletion_uncertain else str(content)[:8000] if error else None), result=content,
        result_metadata={key: value for key, value in result.additional_kwargs.items() if key.startswith(("read_file_", "capture_"))} if isinstance(result, ToolMessage) else {},
        evidence=settled_evidence, updated_at=utc_now())


def reconcile_effects(run: Any) -> None:
    """Inspect interrupted targets. A matching file proves state, never replay."""
    from workbench_backend.agents.harness_backend import resolve_project_tool_path
    for call_id, item in list(run.tool_outcomes.items()):
        if item.outcome not in {"running", "uncertain"}:
            continue
        update = {"outcome": "uncertain", "failure_category": "runtime", "recovery_action": "ask",
            "detail": "The action started but its effects could not be confirmed. Inspect before repeating it.", "updated_at": utc_now()}
        if item.name in READ_ONLY_TOOLS:
            update.update(outcome="failed", recovery_action="continue", detail="The read did not return a result; it can be retried.")
        elif item.name in {"execute", "execute_skill_script"} and item.evidence.get("exit_code") in {124, 130}:
            update.update(failure_category="cancelled" if item.evidence["exit_code"] == 130 else "runtime",
                recovery_action="inspect_effects",
                detail="The command was interrupted. Its changes may be partial even when its processes have stopped. Inspect before continuing or repeating it.")
        elif getattr(run, "tool_mode", None) != ToolMode.recorded_tool and run.project_path and item.evidence.get("path"):
            try:
                path = resolve_project_tool_path(run.project_path, item.evidence["path"])
                content = path.read_bytes() if path.is_file() and path.stat().st_size <= 4_000_000 else None
                digest = hashlib.sha256(content).hexdigest() if content is not None else None
                if item.name == "delete" and item.evidence.get("expected_absent") and not path.exists():
                    update.update(outcome="succeeded", failure_category=None, recovery_action="none",
                        detail="The requested project target is absent (verified after interruption).", result="The deletion target is absent.")
                elif digest is not None and digest == item.evidence.get("expected_sha256"):
                    update.update(outcome="succeeded", failure_category=None, recovery_action="none",
                        detail="Confirmed by inspecting the file after interruption.",
                        result="The file now contains the exact requested content (verified after interruption).")
                elif (digest is not None and digest == item.evidence.get("before_sha256")) or (not path.exists() and item.evidence.get("before_exists") is False):
                    update.update(outcome="failed", recovery_action="continue", detail="The target is unchanged; the requested file effect was not applied.",
                        result="The file was inspected after interruption and is unchanged. The action may be requested again.")
            except (OSError, ValueError):
                pass
        run.tool_outcomes[call_id] = item.model_copy(update=update)


def failure_for_run(run: Any, *, code: str | None = None) -> RunFailure | None:
    uncertain = any(item.outcome == "uncertain" and not item.evidence.get("acknowledged_at") for item in run.tool_outcomes.values())
    if uncertain:
        return RunFailure(category="uncertain_effects", code="effects_unconfirmed", message=run.error or
            "Some actions started but their effects could not be confirmed. Inspect before continuing.", recovery_action="inspect_effects")
    if not run.error and getattr(run.status, "value", run.status) != "cancelled":
        return None
    code = code or run.stop_reason or "run_failed"
    category, action = "runtime", "continue"
    if code in {"context_capacity_exceeded", "tool_budget_exhausted", "response_limit_reached"}:
        category, action = "capacity", "change_limit"
    elif code in {"interaction_persistence_failed", "checkpoint_linkage_failed"}:
        category, action = "persistence", "continue"
    elif code.startswith(("setup_", "deploy_", "model_", "context_")):
        category, action = "setup", "correct_setup"
    elif code == "cancelled":
        category = "cancelled"
    return RunFailure(category=category, code=code, message=run.error or "The run was stopped. Completed results are retained.", recovery_action=action)
