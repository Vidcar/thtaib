import type { AgentInputPolicy } from "./agentInputPolicy";
import type { ApprovalMode } from "./ApprovalModeControl";
import type { DesktopAccess, KnowledgeEntry } from "./types";
import type { SetupConfiguration } from "./workspaceApi";

export interface ChatWorkspaceLaunch { id: string; projectId?: string | null; agentSetupVersionId?: string | null }

export const chatSetupFields = ["input_policy", "deployment_id", "model_configuration_id", "profile_id", "inherit_deployment_settings", "startup_overrides", "embedding_deployment_id", "presented_tools", "approval_mode", "per_request_overrides", "memory_version_refs", "skill_version_refs", "protected_instruction_version_refs", "knowledge_version_refs", "connection_ids", "instructions", "work_mode", "desktop_access", "helper_agent_ids", "review", "agent_setup_id", "memory_entry_ids", "skill_entry_ids", "protected_instruction_entry_ids", "shortcut_ids", "project_file_refs", "inherited_model_configuration", "model_overrides"] as const;

export const browserToolNames = ["browser_navigate", "browser_navigate_back", "browser_tabs", "browser_snapshot", "browser_find", "browser_click", "browser_hover", "browser_press_key", "browser_type", "browser_select_option", "browser_fill_form", "browser_resize", "browser_console_messages", "browser_network_requests", "browser_take_screenshot", "browser_wait_for", "browser_handle_dialog", "browser_drag", "browser_mouse_move_xy", "browser_mouse_click_xy", "browser_mouse_drag_xy", "browser_mouse_down", "browser_mouse_up", "browser_mouse_wheel", "browser_file_upload"] as const;
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

function knowledgePayload(entries: Pick<KnowledgeEntry, "id" | "kind" | "current_version_id">[], selectedVersionIds: string[]) {
  const selected = entries.filter((entry) => selectedVersionIds.includes(entry.current_version_id));
  const memoryVersionRefs = selected
    .filter((entry) => entry.kind === "memory")
    .map((entry) => entry.current_version_id);
  const skillVersionRefs = selected
    .filter((entry) => entry.kind === "skill")
    .map((entry) => entry.current_version_id);
  const protectedInstructionVersionRefs = selected
    .filter((entry) => entry.kind === "protected_instruction")
    .map((entry) => entry.current_version_id);
  return {
    // The backend resolves kinds for earlier explicit versions too. Omitting
    // them here would silently replace a selected memory when Knowledge updates.
    knowledge_version_refs: [...selectedVersionIds],
    memory_version_refs: memoryVersionRefs,
    skill_version_refs: skillVersionRefs,
    protected_instruction_version_refs: protectedInstructionVersionRefs,
  };
}

export interface ChatConfigurationInput {
  hasApplicationDefaults: boolean;
  projectId: string | null;
  agentSetupVersionId: string | null;
  agentSetupId: string | null;
  conversationAgentSetupVersionId?: string | null;
  conversationProjectId?: string | null;
  conversationWorkspaceId?: string | null;
  knowledgeEntries: Pick<KnowledgeEntry, "id" | "kind" | "current_version_id">[];
  selectedKnowledgeIds: string[];
  editedFields: ReadonlySet<string>;
  deploymentId: string;
  profileId: string;
  startupOverrides: Record<string, unknown>;
  embeddingDeploymentId: string;
  selectedTools: string[] | null;
  desktopAccess: DesktopAccess;
  approvalMode: ApprovalMode;
  perRequestOverrides: Record<string, unknown>;
  workMode: "work" | "plan";
  helperAgentIds: string[];
  review: { enabled: boolean; criteria: string; max_revisions: 2 };
  inputPolicy: AgentInputPolicy | null;
  localInstructions: string | null;
  modelOverrides: NonNullable<SetupConfiguration["model_overrides"]>;
  inheritedModelConfiguration: SetupConfiguration | null;
  contextEntryIds: string[];
  contextKinds: Record<string, "memory" | "instruction">;
  messageSkillIds: string[];
  shortcutIds: string[];
  projectFileRefs: string[];
  documentAssetIds: string[] | null;
  projectPath: string;
}

export function buildChatConfiguration(input: ChatConfigurationInput): Record<string, unknown> {
  const layered = Boolean(input.hasApplicationDefaults || input.projectId || input.agentSetupVersionId || input.conversationAgentSetupVersionId || input.conversationProjectId);
  const selectedKnowledge = knowledgePayload(input.knowledgeEntries, input.selectedKnowledgeIds);
  const values = sparseChatSetup({
    deployment_id: input.deploymentId,
    model_configuration_id: input.profileId || null,
    startup_overrides: input.startupOverrides,
    embedding_deployment_id: input.embeddingDeploymentId || null,
    ...(input.editedFields.has("presented_tools") ? { presented_tools: input.selectedTools } : {}),
    ...(input.editedFields.has("desktop_access") ? { desktop_access: input.desktopAccess } : {}),
    ...(input.editedFields.has("approval_mode") ? { approval_mode: input.approvalMode } : {}),
    per_request_overrides: input.perRequestOverrides,
    work_mode: input.workMode,
    helper_agent_ids: input.helperAgentIds,
    review: input.review,
    ...(input.inputPolicy ? { input_policy: input.inputPolicy } : {}),
    ...(input.localInstructions !== null ? { instructions: input.localInstructions } : {}),
    ...selectedKnowledge,
  }, input.editedFields, layered);
  // Editable intent names records; backend admission owns the exact versions.
  delete values.knowledge_version_refs; delete values.memory_version_refs; delete values.skill_version_refs; delete values.protected_instruction_version_refs;
  return { ...values, model_overrides: input.modelOverrides, inherited_model_configuration: input.inheritedModelConfiguration,
    memory_entry_ids: input.contextEntryIds.filter(id => input.contextKinds[id] !== "instruction" && !input.knowledgeEntries.some(item => item.id === id && item.kind === "protected_instruction")),
    protected_instruction_entry_ids: input.contextEntryIds.filter(id => input.contextKinds[id] === "instruction" || input.knowledgeEntries.some(item => item.id === id && item.kind === "protected_instruction")),
    skill_entry_ids: input.messageSkillIds, shortcut_ids: input.shortcutIds, project_file_refs: input.projectFileRefs,
    ...(input.documentAssetIds !== null ? { document_asset_ids: input.documentAssetIds } : {}), ...(input.projectId ? { project_id: input.projectId } : {}),
    ...(input.agentSetupId ? { agent_setup_id: input.agentSetupId } : input.agentSetupVersionId ? { agent_setup_version_id: input.agentSetupVersionId } : { agent_setup_id: null }),
    ...(!input.projectId ? { project_path: input.projectPath.trim() || null } : {}),
    ...(!input.projectId || input.conversationWorkspaceId ? { workspace_id: input.conversationWorkspaceId ?? null } : {}) };
}

export function executionConfiguration(configuration: Record<string, unknown>): Record<string, unknown> {
  const { model_overrides: _models, inherited_model_configuration: _inherited, ...selection } = configuration;
  return selection;
}

export function creationConfiguration(configuration: Record<string, unknown>): Record<string, unknown> {
  const { shortcut_ids: _shortcuts, project_file_refs: _files, document_asset_ids: _documents, ...selection } = executionConfiguration(configuration);
  return selection;
}
