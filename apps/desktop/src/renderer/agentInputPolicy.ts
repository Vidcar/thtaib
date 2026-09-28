export type ReferenceLoading = "off" | "when_needed" | "always";
export interface AgentInputPolicy {
  version?: 1;
  tool_loading?: "when_needed" | "always";
  pinned_tools?: string[];
  reference_loading?: Record<string, ReferenceLoading>;
  excluded_sources?: string[];
  instruction_override?: string | null;
}
export interface AgentInputSource {
  id: string;
  title: string;
  kind: string;
  origin: string;
  reason: string;
  mode: string;
  estimated_tokens?: number | null;
  token_counting_method?: string;
  content?: string | null;
  path?: string | null;
  required?: boolean;
  editable?: boolean;
  available?: boolean;
  history_hint?: string | null;
  version_id?: string | null;
  entry_id?: string | null;
  tool_name?: string | null;
  observed?: boolean;
  required_tools?: string[];
  required_connections?: string[];
  requires_project?: boolean;
}
export interface AgentInputPreview {
  policy: AgentInputPolicy;
  sources: AgentInputSource[];
  estimated_input_tokens?: number | null;
  token_counting_method: string;
  prepared?: boolean;
  note?: string;
}
export interface CapabilitySetupRequest {
  version: 1;
  capability: string;
  id: string;
  tool_names: string[];
  code: string;
  message: string;
  action: string;
  target: "settings" | "browser" | "windows" | "agent" | "knowledge" | "project" | "context";
  target_id?: string | null;
  requires_new_input: boolean;
}

export function referenceMode(policy: AgentInputPolicy | null | undefined, source: AgentInputSource): ReferenceLoading {
  return source.entry_id && policy?.reference_loading?.[source.entry_id] || (source.mode === "off" || source.mode === "always" ? source.mode : "when_needed");
}

export function setReferenceMode(policy: AgentInputPolicy, entryId: string, mode: ReferenceLoading): AgentInputPolicy {
  return { ...policy, version: 1, reference_loading: { ...policy.reference_loading, [entryId]: mode } };
}

export function excludeInputSource(policy: AgentInputPolicy, sourceId: string, excluded: boolean): AgentInputPolicy {
  const sources = policy.excluded_sources ?? [];
  return { ...policy, version: 1, excluded_sources: excluded ? [...new Set([...sources, sourceId])] : sources.filter(id => id !== sourceId) };
}
