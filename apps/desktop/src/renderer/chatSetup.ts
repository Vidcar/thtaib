import type { SetupConfiguration } from "./workspaceApi";

export interface ChatWorkspaceLaunch { id: string; projectId?: string | null; agentSetupVersionId?: string | null }

export const chatSetupFields = ["deployment_id", "model_configuration_id", "profile_id", "inherit_deployment_settings", "startup_overrides", "embedding_deployment_id", "presented_tools", "approval_mode", "per_request_overrides", "memory_version_refs", "skill_version_refs", "protected_instruction_version_refs", "knowledge_version_refs", "connection_ids", "instructions", "work_mode", "desktop_access", "helper_agent_ids", "review"] as const;

export const browserToolNames = ["browser_navigate", "browser_navigate_back", "browser_tabs", "browser_snapshot", "browser_find", "browser_click", "browser_hover", "browser_press_key", "browser_type", "browser_select_option", "browser_fill_form", "browser_resize", "browser_console_messages", "browser_network_requests", "browser_take_screenshot", "browser_wait_for", "browser_handle_dialog"] as const;
export const desktopToolNames = ["desktop_list_windows", "desktop_inspect", "desktop_search", "desktop_wait", "desktop_invoke", "desktop_set_value", "desktop_send_keys", "desktop_screenshot"] as const;
export const previewToolNames = ["start_preview", "stop_preview", "preview_status"] as const;
export const optionalVisualToolNames = new Set<string>([...browserToolNames, ...desktopToolNames, ...previewToolNames]);
// Keep this preview of the next turn in step with the backend's PLAN_TOOLS.
const planToolNames = new Set(["ls", "read_file", "glob", "grep", "read_attachment", "search_knowledge", "web_search", "write_todos", "ask_user", "echo", "time_now", "task"]);

export function effectiveNextTurnTools(selected: string[], workMode: "work" | "plan"): string[] {
  return workMode === "plan" ? selected.filter(name => planToolNames.has(name)) : selected;
}

export function defaultNextTurnTools(catalogue: string[], projectBound: boolean, hasKnowledgeRoutes: boolean, hasAttachments: boolean): string[] {
  const fileTools = new Set(["read_file", "ls", "glob", "grep", "write_file", "edit_file"]);
  return catalogue.filter(name => !optionalVisualToolNames.has(name) && name !== "execute" &&
    (name !== "read_attachment" || hasAttachments) &&
    (!fileTools.has(name) || projectBound || (hasKnowledgeRoutes && (name === "read_file" || name === "ls"))));
}

export function withBrowserTools(current: string[], enabled: boolean, projectBound: boolean, hasKnowledgeRoutes: boolean): string[] {
  const selected = new Set(current.filter(name => !browserToolNames.some(browserName => browserName === name)));
  if (enabled) {
    browserToolNames.forEach(name => selected.add(name));
    if (projectBound) previewToolNames.forEach(name => selected.add(name));
  } else {
    previewToolNames.forEach(name => selected.delete(name));
    if (!projectBound && !hasKnowledgeRoutes && !desktopToolNames.some(name => selected.has(name))) selected.delete("read_file");
  }
  return [...selected];
}

export function withDesktopTools(current: string[], enabled: boolean, projectBound: boolean, hasKnowledgeRoutes: boolean): string[] {
  const selected = new Set(current.filter(name => !desktopToolNames.some(desktopName => desktopName === name)));
  if (enabled) {
    desktopToolNames.forEach(name => selected.add(name));
  } else if (!projectBound && !hasKnowledgeRoutes && !browserToolNames.some(name => selected.has(name))) {
    selected.delete("read_file");
  }
  return [...selected];
}

// The backend resolves omitted fields from the immutable selected setup. Empty
// lists are deliberate overrides; serializing every control's default would
// erase a saved setup's tools, knowledge and response settings.
export function sparseChatSetup(values: Record<string, unknown>, edited: ReadonlySet<string>, layered: boolean): Record<string, unknown> {
  return Object.fromEntries(Object.entries(values).filter(([key]) => !layered || edited.has(key) || key === "workspace_id"));
}

export function setupOverrides(values: Record<string, unknown>): SetupConfiguration {
  return Object.fromEntries(Object.entries(values).filter(([key]) => (chatSetupFields as readonly string[]).includes(key) && key !== "knowledge_version_refs")) as SetupConfiguration;
}
