import type { SetupConfiguration } from "./workspaceApi";

export interface ChatWorkspaceLaunch { id: string; projectId?: string | null; agentSetupVersionId?: string | null }

export const chatSetupFields = ["deployment_id", "model_configuration_id", "profile_id", "inherit_deployment_settings", "startup_overrides", "embedding_deployment_id", "presented_tools", "approval_mode", "per_request_overrides", "memory_version_refs", "skill_version_refs", "protected_instruction_version_refs", "knowledge_version_refs", "connection_ids", "instructions", "work_mode", "helper_agent_ids", "review"] as const;

// The backend resolves omitted fields from the immutable selected setup. Empty
// lists are deliberate overrides; serializing every control's default would
// erase a saved setup's tools, knowledge and response settings.
export function sparseChatSetup(values: Record<string, unknown>, edited: ReadonlySet<string>, layered: boolean): Record<string, unknown> {
  return Object.fromEntries(Object.entries(values).filter(([key]) => !layered || edited.has(key) || key === "workspace_id"));
}

export function setupOverrides(values: Record<string, unknown>): SetupConfiguration {
  return Object.fromEntries(Object.entries(values).filter(([key]) => (chatSetupFields as readonly string[]).includes(key) && key !== "knowledge_version_refs")) as SetupConfiguration;
}
