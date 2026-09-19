export type WorkbenchSurface = "managed-inference";

export type WorkbenchTab = "models" | "deployments" | "agent-run" | "lab";

export interface PathsInfo {
  root: string;
  models: string;
  runtimes: string;
  state: string;
  cases: string;
  snapshots: string;
  workspaces: string;
  windows_layout: string;
}

export interface BundleFile {
  role: "primary_weights" | "shard" | "companion";
  name: string;
  path: string;
  sha256: string;
  size_bytes: number;
}

export interface ModelBundle {
  id: string;
  display_name: string;
  quantization: string | null;
  source: {
    kind: "huggingface" | "local";
    repo_id: string | null;
    requested_revision: string | null;
    resolved_revision: string | null;
    original_path: string | null;
  };
  files: BundleFile[];
  shards: BundleFile[];
  companions: BundleFile[];
  primary_path: string | null;
  disk_matches: boolean;
  status: string;
}

export interface ImportJob {
  id: string;
  kind: string;
  status: string;
  bundle_id: string | null;
  error: string | null;
}

export interface SettingsBag {
  requested: Record<string, unknown>;
  applied: Record<string, unknown>;
  unsupported: string[];
  overridden: Array<{ key: string; requested: unknown; applied: unknown; reason: string }>;
  unverified: string[];
}

export interface SettingsBags {
  startup: SettingsBag;
  per_request: SettingsBag;
  agent: SettingsBag;
}

export interface RunProfile {
  id: string;
  display_name: string;
  bundle_id: string | null;
  bags: SettingsBags;
}

export interface Deployment {
  id: string;
  display_name: string;
  scope: "managed" | "connected";
  status: string;
  bundle_id: string | null;
  endpoint: string | null;
  applied_startup: Record<string, unknown>;
  settings: SettingsBags;
  health: { healthy: boolean; detail: string | null } | null;
  resource_usage: { available: boolean; cpu_percent: number | null; rss_bytes: number | null; reason: string | null } | null;
  error: string | null;
}

export interface RuntimeManifest {
  platform: string;
  release_tag: string;
  executable: string;
  path_fallback: "unsupported";
  status: "ready" | "failed" | "interrupted";
  error: string | null;
}

export type LabToolMode = "live-tool" | "recorded-tool";

export interface LabWorkspace {
  id: string;
  display_name: string;
  path: string;
  origin: "created" | "restored";
  parent_workspace_id: string | null;
  snapshot_id: string | null;
  case_id: string | null;
}

export interface LabCase {
  id: string;
  snapshot_id: string;
  source_run_id: string | null;
  source_workspace_id: string;
  task: string;
  deployment_id: string | null;
  profile_id: string | null;
  exclusions: Array<{ path: string; reason: string }>;
  environment_restore: "not_this_milestone";
  environment_exclusions: string[];
  dependency_versions: Record<string, string>;
  tool_fixtures: Array<Record<string, unknown>>;
  snapshot_path: string;
}

export interface LabRestore {
  workspace: LabWorkspace;
  case_id: string;
  parent_workspace_id: string;
  parent_unchanged: boolean;
  branch: { kind: string; parent_workspace_id: string; child_workspace_id: string };
  deviations: string[];
}

export interface LabResult {
  id: string;
  case_id: string;
  workspace_id: string;
  agent_run_id: string;
  tool_mode: LabToolMode;
  tool_mode_label: string;
  recorded_is_not_live_proof: boolean;
  evaluation_kind: "task_evaluation";
  harness: "deepagents";
  second_agent_loop: false;
  applied_config: Record<string, unknown>;
  evidence: Record<string, unknown>;
  judgement: Record<string, unknown>;
  deviations: string[];
  parent_workspace_unchanged: boolean;
}

export interface EngineMeasurement {
  id: string;
  kind: "engine_measurement";
  engine: "llama-bench";
  available: boolean;
  success: boolean;
  reason: string | null;
  scores: Record<string, string> | null;
  note: string;
}

export interface AgentRun {
  id: string;
  status: "queued" | "running" | "completed" | "cancelled" | "failed";
  deployment_id: string;
  task: string;
  enabled_tools: string[];
  presented_tools: string[];
  events: Array<{ at: string; kind: string; detail: Record<string, unknown> }>;
  model_requests: Array<{
    at: string;
    instructions: string | null;
    presented_tools: string[];
    available_tools: string[];
    capture_gaps: string[];
    http_payload: Record<string, unknown> | null;
  }>;
  completion: {
    evidence: {
      executable_checks: Array<{ name: string; passed: boolean; detail: string | null }>;
      expected_artifacts: Array<{ name: string; present: boolean; detail: string | null }>;
    };
    judgement: { model_review: string | null; note: string };
  } | null;
  stop_reason: string | null;
  error: string | null;
  budgets: { max_steps: number | null; max_tool_calls: number | null } | null;
  knowledge: "none";
  harness: "deepagents";
}

export interface InspectReport {
  bundle_id: string;
  file_path: string;
  sha256: string;
  reader_mode: "r";
  metadata_edited: false;
  name: string | null;
  architecture: string | null;
  fields: Record<string, unknown>;
  tensors: Array<{ name: string; shape: number[]; tensor_type: string }>;
}
