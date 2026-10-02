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
    project = ["ls", "read_file", "write_file", "edit_file", "glob", "grep"]
    file_pins = ["ls", "read_file", "edit_file", "write_file"]
    reviewer = ["ls", "read_file", "glob", "grep", "read_attachment", "ask_user", "write_todos"]
    trusted_reads = [*reviewer, "read_tool_result"]
    trusted_tools = [*trusted_reads, "write_file", "edit_file", "execute"]
    browser = ["ask_user", "read_tool_result", "browser_navigate", "browser_navigate_back", "browser_tabs", "browser_snapshot",
        "browser_find", "browser_click", "browser_hover", "browser_press_key", "browser_type",
        "browser_select_option", "browser_fill_form", "browser_resize", "browser_console_messages",
        "browser_network_requests", "browser_network_request", "browser_emulate_media",
        "browser_take_screenshot", "browser_wait_for", "browser_handle_dialog"]
    desktop = ["ask_user", "read_tool_result", "desktop_list_windows", "desktop_inspect", "desktop_search", "desktop_wait",
        "desktop_invoke", "desktop_set_value", "desktop_send_keys", "desktop_screenshot"]
    trusted_role = "Implement and verify explicitly trusted local project work."
    specs = [
        ("general", "General", "Finish the requested result.",
            "Finish the requested result in the bound project. A send needs that folder. Use a tool result or a page structure before claiming a file, a page, or a headline. For a page or a game, write the project files, start the preview, and read the page. For news, open the page and quote the page structure. Ask only when a missing choice changes the result. Hand a separable check to the matching helper and use the helper's evidence.",
            [*project, "execute", "start_preview", "stop_preview", "preview_status", "browser_navigate", "browser_snapshot", "browser_find", "write_todos", "ask_user", "read_tool_result"],
            file_pins, [], False, False, "work", "ask", "off",
            "Use Ask in Chat. Helpers are chosen after they are saved. This draft does not select skills."),
        ("guarded-project-builder", "Guarded project builder", "Change only the requested project files.",
            "Change only the requested project files. Run the check that applies. Report the command result or the file you read. Do not widen the task.",
            [*project, "execute", "write_todos", "ask_user"], file_pins, [], True, True,
            "work", "ask", "off", "Use Ask in Chat. Project file changes can be granted separately in Settings; commands still require their own approval."),
        ("trusted-project-builder", "Trusted project builder", trusted_role,
            trusted_role + " Preserve unrelated work and report only observed evidence.",
            trusted_tools, ["glob", "grep", "edit_file", "write_file", "execute"],
            ["project-change", "failure-diagnosis", "windows-execution", "verify-delivery"], True, True,
            "work", "full_access", "off", "Choose Full access deliberately in Chat only for trusted work. Commands run on the real host with inherited environment; the project folder is not a sandbox."),
        ("read-only-reviewer", "Read-only reviewer", "Report what is in the files.",
            "Report what is in the files. Do not edit them.",
            reviewer, ["ls", "read_file"], [], True, False,
            "plan", "ask", "off", "Use Plan in Chat. This draft selects source reading only: it cannot run tests, edit files, start previews or contact integrations."),
        ("browser-validator", "Browser validator", "Open the requested page.",
            "Open the requested page. Read headlines and links from the page structure. Use a screenshot only as a picture, not as the source of the words.",
            browser, ["browser_navigate", "browser_snapshot"], [], False, False,
            "work", "ask", "off", "Use Ask and select Browser in Chat. Screenshots require verified image reading. Add preview tools only when an owned local server is needed; uploads remain unselected."),
        ("evidence-researcher", "Evidence researcher", "Quote the page or the file you actually read.",
            "Quote the page or the file you actually read. Say when a line was not opened.",
            [*reviewer, "read_tool_result", "browser_navigate", "browser_snapshot", "browser_find"],
            ["read_attachment", "read_tool_result"], [], False, False,
            "work", "ask", "off", "Use Ask in Chat. Page tools stay discoverable until needed. This draft does not select a public-web connection."),
        ("windows-validator", "Windows validator", "Inspect the named window.",
            "Inspect the named window. Do not operate other windows.",
            desktop, ["desktop_inspect"], [], False, False,
            "work", "ask", "selected", "Use Ask and choose the current live window in Chat. Saving this agent supplies no window grant; screenshots require verified image reading."),
    ]
    return [AgentSetupTemplate(id=slug, name=name, role=role,
        configuration=SetupConfiguration(instructions=instructions,
            presented_tools=tools, connection_ids=[], helper_agent_ids=[], memory_entry_ids=[],
            skill_entry_ids=[installed[str((PACK_ROOT / skill).resolve())] for skill in skills
                if str((PACK_ROOT / skill).resolve()) in installed], protected_instruction_entry_ids=[],
            inherit_deployment_settings=True, review=ReviewConfiguration(enabled=False),
            requires_project=requires_project, requires_host_shell=requires_shell,
            input_policy=AgentInputPolicy(tool_loading="when_needed", pinned_tools=pins)),
        recommended_skills=skills, suggested_chat_mode=mode, suggested_chat_access=access,
        suggested_desktop_access=desktop_access, note=note)
        for slug, name, role, instructions, tools, pins, skills, requires_project, requires_shell, mode, access, desktop_access, note in specs]
