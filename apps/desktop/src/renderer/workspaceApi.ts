import { request } from "./api";
import type { AgentInputPolicy, AgentInputPreview, AgentInputSource } from "./agentInputPolicy";
import type { SchemaAgentSetupView, SchemaAgentSetupVersion, SchemaProjectRecord, SchemaProjectFiles, SchemaResolvedSetupSelection, SchemaSetupConfiguration } from "../generated/shared-contracts/openapi";

export type ProjectRecord = SchemaProjectRecord;
export type ProjectFiles = SchemaProjectFiles;
export type AgentSetup = SchemaAgentSetupView;
export type AgentSetupVersion = SchemaAgentSetupVersion;
export type SetupConfiguration = Omit<SchemaSetupConfiguration, "input_policy" | "inherited_model_configuration"> & {
  input_policy?: AgentInputPolicy | null;
  desktop_access?: "off" | "selected" | "all" | null;
  agent_setup_id?: string | null;
  memory_entry_ids?: string[] | null;
  skill_entry_ids?: string[] | null;
  protected_instruction_entry_ids?: string[] | null;
  inherited_model_configuration?: SetupConfiguration | null;
  model_overrides?: Record<string, { startup_overrides?: Record<string, unknown> | null; per_request_overrides?: Record<string, unknown> | null }>;
  shortcut_ids?: string[];
  project_file_refs?: string[];
};
export type ResolvedSetupSelection = Omit<SchemaResolvedSetupSelection, "configuration" | "input_sources"> & { configuration: SetupConfiguration; input_sources?: AgentInputSource[] };
export interface InputPreviewContext { attachment_ids?: string[]; document_asset_ids?: string[]; shortcut_ids?: string[]; project_file_refs?: string[] }
export interface ChatReadiness {
  status: "ready" | "needs_action" | "incompatible" | "unverified";
  can_send: boolean;
  issues: Array<{ code: string; message: string; action?: string | null }>;
  selection: ResolvedSetupSelection | null;
  input_preview?: AgentInputPreview | null;
}
function projectKnowledge(value: SetupConfiguration): SetupConfiguration {
  const fields = ["input_policy", "memory_version_refs", "skill_version_refs", "memory_entry_ids", "skill_entry_ids", "embedding_deployment_id"] as const;
  return Object.fromEntries(fields.filter(key => Object.hasOwn(value, key)).map(key => [key, value[key]])) as SetupConfiguration;
}

export const workspaceApi = {
  projects: (includeInactive = false) => request<ProjectRecord[]>(`/v1/projects${includeInactive ? "?include_inactive=true" : ""}`),
  createProject: (path: string, name?: string, defaults: SetupConfiguration = {}) => request<ProjectRecord>("/v1/projects", { method: "POST", body: JSON.stringify({ path, name, defaults: projectKnowledge(defaults) }) }),
  updateProject: (id: string, payload: { name?: string; defaults?: SetupConfiguration }) => request<ProjectRecord>(`/v1/projects/${id}`, { method: "PATCH", body: JSON.stringify({ ...payload, ...(payload.defaults ? { defaults: projectKnowledge(payload.defaults) } : {}) }) }),
  removeProject: (id: string) => request<ProjectRecord>(`/v1/projects/${id}`, { method: "DELETE" }),
  projectFiles: (id: string, path = "") => request<ProjectFiles>(`/v1/projects/${id}/files?path=${encodeURIComponent(path)}`),
  agentSetups: (includeInactive = false) => request<AgentSetup[]>(`/v1/agent-setups${includeInactive ? "?include_inactive=true" : ""}`),
  createAgentSetup: (payload: { name: string; role?: string | null; configuration: SetupConfiguration }) => request<AgentSetup>("/v1/agent-setups", { method: "POST", body: JSON.stringify(payload) }),
  updateAgentSetup: (id: string, payload: { name: string; role?: string | null; configuration: SetupConfiguration; base_version: string }) => request<AgentSetup>(`/v1/agent-setups/${id}`, { method: "PATCH", body: JSON.stringify(payload) }),
  duplicateAgentSetup: (id: string) => request<AgentSetup>(`/v1/agent-setups/${id}/duplicate`, { method: "POST", body: "{}" }),
  removeAgentSetup: (id: string) => request<AgentSetup>(`/v1/agent-setups/${id}`, { method: "DELETE" }),
  agentSetupVersions: (id: string) => request<AgentSetupVersion[]>(`/v1/agent-setups/${id}/versions`),
  resolveSetup: (project_id: string | null, agent_setup_version_id: string | null, overrides: SetupConfiguration = {}, editing_layer: "application" | "project" | "agent" | "conversation" = "conversation", include_input_content = false) => {
    const { agent_setup_id, inherited_model_configuration: _inherited, model_overrides: _models, shortcut_ids: _shortcuts, project_file_refs: _files, ...wire } = overrides;
    return request<ResolvedSetupSelection>("/v1/setup-resolution", { method: "POST", body: JSON.stringify({ project_id, agent_setup_version_id, agent_setup_id, overrides: wire, editing_layer, include_input_content }) });
  },
  chatReadiness: (conversationId: string, overrides: SetupConfiguration = {}, agent_setup_version_id?: string | null, include_input_content = false, context: InputPreviewContext = {}) => {
    const { agent_setup_id, inherited_model_configuration: _inherited, model_overrides: _models, shortcut_ids: _shortcuts, project_file_refs: _files, ...wire } = overrides;
    return request<ChatReadiness>(`/v1/chat/conversations/${conversationId}/readiness`, { method: "POST", body: JSON.stringify({ overrides: wire, ...(agent_setup_id !== undefined ? { agent_setup_id } : {}), ...(agent_setup_version_id !== undefined ? { agent_setup_version_id } : {}), shortcut_ids: _shortcuts, project_file_refs: _files, ...context, include_input_content }) });
  },
  shortcuts: () => request<Array<{ id: string; version: string; name: string; description: string; prompt: string }>>("/v1/chat/shortcuts"),
};
