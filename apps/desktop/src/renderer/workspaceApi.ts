import { request } from "./api";
import type { SchemaAgentSetupView, SchemaAgentSetupVersion, SchemaProjectRecord, SchemaProjectFiles, SchemaResolvedSetupSelection, SchemaSetupConfiguration } from "../generated/shared-contracts/openapi";

export type ProjectRecord = SchemaProjectRecord;
export type ProjectFiles = SchemaProjectFiles;
export type AgentSetup = SchemaAgentSetupView;
export type AgentSetupVersion = SchemaAgentSetupVersion;
export type SetupConfiguration = SchemaSetupConfiguration & { desktop_access?: "off" | "selected" | "all" | null };
export type ResolvedSetupSelection = SchemaResolvedSetupSelection;
export interface ChatReadiness {
  status: "ready" | "needs_action" | "incompatible" | "unverified";
  can_send: boolean;
  issues: Array<{ code: string; message: string; action?: string | null }>;
  selection: ResolvedSetupSelection | null;
}
function projectKnowledge(value: SetupConfiguration): SetupConfiguration {
  const fields = ["memory_version_refs", "skill_version_refs", "embedding_deployment_id"] as const;
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
  resolveSetup: (project_id: string | null, agent_setup_version_id: string | null, overrides: SetupConfiguration = {}, editing_layer: "application" | "project" | "agent" | "conversation" = "conversation") => request<ResolvedSetupSelection>("/v1/setup-resolution", { method: "POST", body: JSON.stringify({ project_id, agent_setup_version_id, overrides, editing_layer }) }),
  chatReadiness: (conversationId: string, overrides: SetupConfiguration = {}, agent_setup_version_id?: string | null) => request<ChatReadiness>(`/v1/chat/conversations/${conversationId}/readiness`, { method: "POST", body: JSON.stringify({ overrides, ...(agent_setup_version_id !== undefined ? { agent_setup_version_id } : {}) }) }),
};
