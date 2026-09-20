import { isRunLifecycleLive, type RunLifecycleStatus } from "./sharedContracts";

export type WorkbenchSurface = "managed-inference";

export type WorkbenchTab = "chat" | "models" | "knowledge" | "agent-run" | "lab";

export interface PathsInfo {
  root: string;
  models: string;
  runtimes: string;
  state: string;
  cases: string;
  snapshots: string;
  workspaces: string;
  knowledge: string;
  logs: string;
  application_db: string;
  checkpoints_db: string;
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
  unsupported_notes?: Array<{ key: string; requested: unknown; applied: unknown; reason: string }>;
  overridden: Array<{ key: string; requested: unknown; applied: unknown; reason: string }>;
  unverified: string[];
  retired: Array<{ key: string; requested: unknown; applied: unknown; reason: string }>;
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
  server_props: {
    fetched: string;
    source_url: string;
    build_info: string | null;
    model_alias: string | null;
    model_path: string | null;
    n_ctx: number | null;
    total_slots: number | null;
    modalities: Record<string, boolean>;
    chat_template_caps: Record<string, boolean>;
    chat_template: string | null;
    bos_token: string | null;
    eos_token: string | null;
    default_generation_settings?: { params?: Record<string, unknown>; [key: string]: unknown };
  } | null;
  error: string | null;
}

export function isDeclaredEmbedder(deployment: Deployment): boolean {
  return String(deployment.applied_startup?.embedding ?? "").toLowerCase() === "on";
}

export interface RuntimeManifest {
  platform: string;
  flavor?: string;
  release_tag: string;
  executable: string;
  path_fallback: "unsupported";
  status: "ready" | "failed" | "interrupted";
  error: string | null;
  companion_asset_name?: string | null;
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
  snapshot_kind?: "starting" | "checkpoint" | "final";
  input_origin?: "starting_snapshot" | "capture_time_workspace";
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
  memory_version_refs: string[];
  skill_version_refs: string[];
  protected_instruction_version_refs: string[];
  knowledge: "none" | "application_owned";
}

export interface LabRestore {
  workspace: LabWorkspace;
  case_id: string;
  parent_workspace_id: string;
  parent_unchanged: boolean;
  branch: { kind: string; parent_workspace_id: string; child_workspace_id: string };
  deviations: string[];
  snapshot_kind?: "starting" | "checkpoint" | "final";
  input_origin?: "starting_snapshot" | "capture_time_workspace";
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

export type KnowledgeScope = "user" | "agent" | "project";
export type KnowledgeKind = "memory" | "skill" | "protected_instruction";
export type KnowledgeActor = "human" | "api_maintainer" | "agent";
export type RedactionMode = "retain" | "redact_secrets" | "discard";

export type AgentRunStatus = RunLifecycleStatus;
export const isAgentRunLive = isRunLifecycleLive;

export interface AgentRun {
  id: string;
  status: AgentRunStatus;
  deployment_id: string;
  task: string;
  enabled_tools: string[];
  presented_tools: string[];
  events: Array<{ at: string; kind: string; detail: Record<string, unknown> }>;
  model_requests: Array<{
    at: string;
    request_prepared?: boolean;
    transport_attempted?: boolean;
    transport_attempt_count?: number;
    response_observed?: boolean;
    handler_returned?: boolean;
    failure?: Record<string, unknown> | null;
    http_payloads?: Array<Record<string, unknown>>;
    instructions: string | null;
    presented_tools: string[];
    available_tools: string[];
    capture_gaps: string[];
    retrieved_material?: string[];
    http_payload: Record<string, unknown> | null;
    generation_settings?: Record<string, unknown>;
    memory_versions?: string[];
    skill_versions?: string[];
    loaded_knowledge?: Array<{
      version_id: string;
      kind: KnowledgeKind;
      content_digest: string;
      content_available: boolean;
    }>;
    selected_profile_id?: string | null;
    applied_per_request?: Record<string, unknown>;
    startup_mismatches?: Array<{ key: string; selected: unknown; loaded: unknown }>;
  }>;
  effective_setup?: {
    selected_profile_id: string | null;
    selected_deployment_id: string;
    selected_embedding_deployment_id?: string | null;
    selected_memory_version_ids: string[];
    selected_skill_version_ids: string[];
    selected_protected_instruction_version_ids: string[];
    loaded_deployment_id: string;
    loaded_embedding_deployment_id?: string | null;
    loaded_embedding_endpoint?: string | null;
    loaded_startup: Record<string, unknown>;
    loaded_knowledge: Array<{
      version_id: string;
      kind: KnowledgeKind;
      content_digest: string;
      content_available: boolean;
    }>;
    materialized_knowledge?: Array<{
      version_id: string;
      kind: KnowledgeKind;
      path: string;
    }>;
    bags: SettingsBags;
    startup_mismatches: Array<{ key: string; selected: unknown; loaded: unknown }>;
    unsupported: Record<string, string[]>;
    retired?: Record<string, Array<{ key: string; requested: unknown; applied: unknown; reason: string }>>;
    system_prompt: string;
    gaps: string[];
    retrieval_requested?: boolean;
    retrieval_presented?: boolean;
    retrieval_corpus_documents?: number;
    knowledge_binding: "none" | "application_owned";
  } | null;
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
  knowledge: "none" | "application_owned";
  memory_version_refs: string[];
  skill_version_refs: string[];
  protected_instruction_version_refs: string[];
  embedding_deployment_id?: string | null;
  retrieval_project_paths?: string[];
  retrieved_material?: string[];
  harness: "deepagents";
  project_path?: string | null;
  profile_id?: string | null;
  source_surface?: "agent-run" | "chat" | "lab";
  thread_id?: string | null;
  checkpoint_ids?: string[];
  related_files?: Array<{ path: string; kind: "project_root" | "written_file" | "artifact" }>;
  starting_snapshot_id?: string | null;
  host_shell?: HostShellFacts;
  pending_interrupt?: PendingInterrupt | null;
}

export interface HostShellFacts {
  available: boolean;
  environment: "windows_host_shell";
  isolation: "none";
  cwd: string | null;
  inherit_env: boolean;
  note: string;
}

export interface PendingInterruptAction {
  name: string;
  args: Record<string, unknown>;
  description: string | null;
  allowed_decisions: string[];
}

export interface PendingInterrupt {
  kind: "deepagents_interrupt_on";
  environment: "windows_host_shell";
  isolation: "none";
  note: string;
  action_requests: PendingInterruptAction[];
}

export function visiblePendingInterrupt(run: AgentRun | null | undefined): PendingInterrupt | null {
  if (!run) {
    return null;
  }
  if (run.pending_interrupt) {
    return run.pending_interrupt;
  }
  for (let index = run.events.length - 1; index >= 0; index -= 1) {
    const event = run.events[index];
    if (event.kind === "interrupt_resolved") {
      return null;
    }
    if (event.kind === "interrupt") {
      return event.detail as unknown as PendingInterrupt;
    }
  }
  return null;
}

export interface ChatMessage {
  role: "user" | "assistant" | "system";
  content: string;
  at: string;
  run_id: string | null;
}

export interface ChatDeployHealth {
  deployment_id: string;
  deployment_status: string;
  healthy: boolean | null;
  code: "deploy_unhealthy" | "deploy_unreachable" | "deploy_missing" | null;
  message: string | null;
  detail: string | null;
  note: string;
}

export interface ChatContinuity {
  conversation_id: string;
  thread_id: string;
  run_ids: string[];
  current_run_id: string | null;
  transcript_is_harness_context: false;
  history_edit_effect: "display_only";
  model_switch_effect: "same_thread_new_run";
  fresh_conversation_effect: "new_thread_retain_project_and_knowledge";
  note: string;
}

export interface ChatConversation {
  id: string;
  deployment_id: string;
  profile_id: string | null;
  project_path: string | null;
  workspace_id: string | null;
  thread_id: string | null;
  transcript: ChatMessage[];
  current_run_id: string | null;
  run_ids: string[];
  history_replaced: boolean;
  harness: "deepagents";
  second_agent_loop: false;
  source_surface: "chat";
  memory_version_refs?: string[];
  skill_version_refs?: string[];
  protected_instruction_version_refs?: string[];
  embedding_deployment_id?: string | null;
  retrieval_project_paths?: string[];
  current_run: AgentRun | null;
  events: Array<{ at: string; kind: string; detail: Record<string, unknown> }>;
  continuity?: ChatContinuity | null;
  deploy_health?: ChatDeployHealth | null;
  filesystem_tools_available?: boolean;
  shell_tools_available?: boolean;
  enabled_tools?: string[];
  created_at: string;
  updated_at: string;
}

export interface KnowledgeProvenance {
  actor: KnowledgeActor;
  run_id: string | null;
  note: string | null;
}

export interface KnowledgeEntry {
  id: string;
  scope: KnowledgeScope;
  scope_id: string | null;
  kind: KnowledgeKind;
  display_name: string | null;
  current_version_id: string;
  content: string;
  provenance: KnowledgeProvenance;
  previous_version_id: string | null;
  reverted_from_version_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface KnowledgeVersion {
  id: string;
  entry_id: string;
  content: string;
  previous_version_id: string | null;
  reverted_from_version_id: string | null;
  created_at: string;
  provenance: KnowledgeProvenance;
}

export interface KnowledgeConfig {
  context_captures: {
    retention_seconds: number | null;
    redaction_mode: RedactionMode;
  };
  scope_policies: Record<KnowledgeScope, { automatic_agent_writes: boolean }>;
  not_rag: true;
  note: string;
}

export interface ContextCapture {
  id: string;
  created_at: string;
  expires_at: string | null;
  redaction_mode: RedactionMode;
  content: string | null;
  retained: boolean;
  redacted: boolean;
  discarded: boolean;
  expired: boolean;
  redacted_fields: string[];
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

export interface RuntimeControlDescriptor {
  key: string;
  flag: string;
  label: string;
  description: string;
  source: string;
  applied: string | number | boolean | null;
  observed: string | number | boolean | null;
  maximum: number | null;
  recommended?: number | null;
  options: Array<{ value: string | number | boolean | null; label: string; description?: string }>;
}

export interface BundleConfigurationOptions {
  bundle_id: string;
  deployment_id: string | null;
  context_size: RuntimeControlDescriptor;
  gpu_layers: RuntimeControlDescriptor;
  startup_defaults: Record<string, RuntimeControlDescriptor>;
  metadata: Record<string, unknown>;
}
