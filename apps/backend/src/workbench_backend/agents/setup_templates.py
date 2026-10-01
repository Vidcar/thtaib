"""Reviewable setup drafts; templates cannot change Chat access or create grants."""
from __future__ import annotations

from pydantic import BaseModel
from typing import Literal

from workbench_backend.agents.setup_schemas import AgentInputPolicy, SetupConfiguration, ReviewConfiguration
from workbench_backend.knowledge.bundled_skills import PACK_ROOT


class AgentSetupTemplate(BaseModel):
    id: str
    name: str
    role: str
    configuration: SetupConfiguration
    recommended_skills: list[str]
    suggested_chat_mode: Literal["work", "plan"] = "work"
    suggested_chat_access: Literal["ask", "full_access"] = "ask"
    suggested_desktop_access: Literal["off", "selected"] = "off"
    note: str


def setup_templates(knowledge) -> list[AgentSetupTemplate]:
    installed = {entry.package_source: entry.id for entry in knowledge.list_entries()
        if entry.kind == "skill" and entry.scope == "user" and entry.enabled}
    reads = ["ls", "read_file", "glob", "grep", "read_attachment", "read_tool_result", "ask_user", "write_todos"]
    builder = [*reads, "write_file", "edit_file", "execute"]
    browser = ["ask_user", "read_tool_result", "browser_navigate", "browser_navigate_back", "browser_tabs", "browser_snapshot",
        "browser_find", "browser_click", "browser_hover", "browser_press_key", "browser_type",
        "browser_select_option", "browser_fill_form", "browser_resize", "browser_console_messages",
        "browser_network_requests", "browser_network_request", "browser_emulate_media",
        "browser_take_screenshot", "browser_wait_for", "browser_handle_dialog"]
    desktop = ["ask_user", "read_tool_result", "desktop_list_windows", "desktop_inspect", "desktop_search", "desktop_wait",
        "desktop_invoke", "desktop_set_value", "desktop_send_keys", "desktop_screenshot"]
    specs = [
        ("guarded-project-builder", "Guarded project builder", "Implement and verify bounded local project work.", builder,
            ["glob", "grep", "edit_file", "write_file", "execute"],
            ["project-change", "failure-diagnosis", "windows-execution", "verify-delivery"],
            "work", "ask", "off", "Use Ask in Chat. Project file changes can be granted separately in Settings; commands still require their own approval."),
        ("trusted-project-builder", "Trusted project builder", "Implement and verify explicitly trusted local project work.", builder,
            ["glob", "grep", "edit_file", "write_file", "execute"],
            ["project-change", "failure-diagnosis", "windows-execution", "verify-delivery"],
            "work", "full_access", "off", "Choose Full access deliberately in Chat only for trusted work. Commands run on the real host with inherited environment; the project folder is not a sandbox."),
        ("read-only-reviewer", "Read-only reviewer", "Review concrete changes and existing evidence without executing or modifying the project.", reads,
            ["glob", "grep", "read_tool_result"], ["project-change", "failure-diagnosis", "verify-delivery"],
            "plan", "ask", "off", "Use Plan in Chat. This draft selects source reading only: it cannot run tests, edit files, start previews or contact integrations."),
        ("browser-validator", "Browser validator", "Test a selected web flow with fresh targets and visual evidence.", browser,
            ["browser_snapshot", "browser_find", "browser_wait_for", "read_tool_result"], ["browser-validation", "failure-diagnosis", "verify-delivery"],
            "work", "ask", "off", "Use Ask and select Browser in Chat. Screenshots require verified image reading. Add preview tools only when an owned local server is needed; uploads remain unselected."),
        ("evidence-researcher", "Evidence researcher", "Read selected documents and public sources with precise citations and coverage.", reads,
            ["read_attachment", "read_tool_result"], ["evidence-research"],
            "plan", "ask", "off", "Use Plan in Chat. Select the actual public-web connection in the editor when web sources are needed; no account connection is added by this template."),
        ("windows-validator", "Windows validator", "Inspect and test a live selected Windows application without expanding its scope.", desktop,
            ["desktop_list_windows", "desktop_inspect", "desktop_search", "read_tool_result"], ["desktop-validation", "failure-diagnosis", "verify-delivery"],
            "work", "ask", "selected", "Use Ask and choose the current live window in Chat. Saving this agent supplies no window grant; screenshots require verified image reading."),
    ]
    return [AgentSetupTemplate(id=slug, name=name, role=role,
        configuration=SetupConfiguration(instructions=role + " Preserve unrelated work and report only observed evidence.",
            presented_tools=tools, connection_ids=[], helper_agent_ids=[], memory_entry_ids=[],
            skill_entry_ids=[installed[str((PACK_ROOT / skill).resolve())] for skill in skills
                if str((PACK_ROOT / skill).resolve()) in installed], protected_instruction_entry_ids=[],
            inherit_deployment_settings=True, review=ReviewConfiguration(enabled=False),
            requires_project=slug in {"guarded-project-builder", "trusted-project-builder", "read-only-reviewer"},
            requires_host_shell=slug in {"guarded-project-builder", "trusted-project-builder"},
            input_policy=AgentInputPolicy(tool_loading="when_needed", pinned_tools=pins)),
        recommended_skills=skills, suggested_chat_mode=mode, suggested_chat_access=access,
        suggested_desktop_access=desktop_access, note=note)
        for slug, name, role, tools, pins, skills, mode, access, desktop_access, note in specs]
