import { isRunLifecycleLive, type RunLifecycleStatus } from "./sharedContracts";
import type { MatchedPermissionGrant } from "./packet03Api";
import type {
  SchemaAgentRun,
  SchemaChatDraft,
  SchemaChatQueueItem,
  SchemaChatSearchResult,
} from "../generated/shared-contracts/openapi";

export type WorkbenchSurface = "managed-inference";

export type WorkbenchTab = "chat" | "projects" | "agents" | "models" | "knowledge" | "agent-run" | "lab" | "library" | "settings" | "attention";

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

export interface ResponseRecipe {
  id: string;
  name: string;
  section: string;
  per_request: Record<string, number>;
  reasoning: "on" | "off" | "preserve";
  source_repo_id: string;
  source_revision: string;
  card_sha256: string;
  notes?: string[];
}

export interface ModelCard {
  bundle_id: string;
  repo_id: string;
  revision: string;
  sha256: string;
  markdown: string;
  origin: "saved" | "fetched";
}

export interface ResponseRecipeOrigin {
  recipe_id: string;
  name: string;
  source_repo_id: string;
  source_revision: string;
  card_sha256: string;
  section: string;
}

export interface ModelBundle {
  id: string;
  default_configuration_id?: string | null;
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
  huggingface_configuration?: {
    source_repo_id: string | null;
    source_revision: string | null;
    source_verified: boolean;
    source_note: string | null;
    template_origin: "gguf" | "repository" | "publisher" | "none";
    template_file: string | null;
    template_differs: boolean;
    template_compatible: boolean | null;
    generation_defaults: Record<string, unknown>;
    response_recipes?: ResponseRecipe[];
    metadata_refreshed_at?: string | null;
    unsupported: Record<string, string>;
  } | null;
}

export interface ImportJob {
  id: string;
  kind: string;
  status: string;
  bundle_id: string | null;
  error: string | null;
  configuration_error?: string | null;
  recipe_ids?: string[];
  default_recipe_id?: string | null;
  display_name?: string | null;
  repo_id?: string | null;
  requested_revision?: string | null;
  resolved_revision?: string | null;
  progress?: { stage: string; message: string | null; files_done: number; files_total: number | null; bytes_done: number; bytes_total: number | null };
}

export interface ModelStorageSummary {
  install_root: string;
  future_install_root: string;
  managed_bytes: number;
  staging_bytes: number;
  cache_bytes: number;
  metadata_bytes: number;
  reclaimable_bytes: number;
  capacity_bytes: number | null;
  available_bytes: number | null;
  locations: Array<{ kind: string; path: string; bytes: number; removable: boolean; reference_count: number }>;
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

export type PresentationTheme = "system" | "light" | "dark";

export interface PresentationSettings {
  theme: PresentationTheme;
  detailed_streams: boolean;
  attention_notifications: boolean;
  success_notifications: boolean;
}

export interface RunProfile {
  id: string;
  revision?: number;
  display_name: string;
  bundle_id: string | null;
  bundle_name?: string | null;
  recipe_origin?: ResponseRecipeOrigin | null;
  bags: SettingsBags;
}

export interface DeletePreview {
  target_kind: "profile" | "bundle";
  target_id: string;
  blockers: Array<{ kind: string; id: string; label: string | null; live: boolean }>;
  consumers: Array<{ kind: string; id: string; label: string | null; live: boolean; retained: boolean }>;
  files: Array<{ path: string; size_bytes: number; removable: boolean; reason: string | null }>;
  removable_bytes: number;
  retained: string[];
}

export interface DeploymentProfileChanges {
  deployment_id: string;
  profile_id: string | null;
  has_pending_startup_changes: boolean;
  pending_startup: Record<string, { active: unknown; profile: unknown }>;
  has_pending_per_request_changes: boolean;
  has_pending_agent_changes: boolean;
}

export interface Deployment {
  id: string;
  updated_at?: string;
  display_name: string;
  scope: "managed" | "connected";
  status: string;
  bundle_id: string | null;
  profile_id?: string | null;
  endpoint: string | null;
  applied_startup: Record<string, unknown>;
  requested_startup?: Record<string, unknown>;
  startup_overrides?: Record<string, unknown>;
  loaded_chat_template_origin?: "publisher" | "repository" | null;
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

export interface ManagedModelsRuntime {
  max_loaded_models: number;
  loaded_deployment_ids: string[];
  loading_deployment_ids: string[];
  router_status: "stopped" | "running" | "unhealthy";
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

export type UserContentBlock =
  | { type: "text"; text: string }
  | { type: "image_url"; image_url: { url: string; detail?: "auto" | "low" | "high" } };

export interface ContextObservation {
  schema_version: number;
  capacity_tokens: number | null;
  capacity_source: "server_props.n_ctx" | "unknown";
  output_reservation_tokens: number;
  estimated_input_tokens: number;
  margin_tokens: number;
  fits: boolean | null;
  counting_method: string;
  summarization_path: "deepagents-upstream";
  notes: string[];
}

export interface StructuredOutputResult {
  schema_version: number;
  requested_schema_version: number;
  schema_name: string;
  requested_json_schema: Record<string, unknown>;
  strategy: "provider" | "tool" | null;
  validation_status: "not_requested" | "valid" | "missing" | "invalid";
  result: unknown;
  error: string | null;
  note: string;
}

export interface AgentRun {
  id: string;
  child_runs?: Array<{ run_id: string; agent_id: string; version_id: string; name: string; namespace: string[]; tool_call_id?: string; status: string; error?: string }>;
  tool_authorizations?: Record<string, string>;
  tool_authorization_grants?: Record<string, MatchedPermissionGrant>;
  review_observation?: { enabled: boolean; max_revisions: number; status: string; evidence_scope?: string; evaluations: Array<{ iteration?: number; grading_run_id?: string; result?: unknown; explanation?: string; criteria?: Array<{ name: string; passed: boolean; gap?: string }> }> };
  input_message_id?: string | null;
  status: AgentRunStatus;
  finalization_phase?: SchemaAgentRun["finalization_phase"];
  settled_status?: SchemaAgentRun["settled_status"];
  settled_stop_reason?: SchemaAgentRun["settled_stop_reason"];
  deployment_id: string;
  task: string;
  content_blocks?: UserContentBlock[] | null;
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
  context_observation?: ContextObservation | null;
  generation_observation?: import("../generated/shared-contracts/openapi").SchemaGenerationObservation | null;
  structured_output?: StructuredOutputResult | null;
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
  question?: UserQuestion | null;
}

export interface UserQuestion {
  prompt: string;
  answer_type: "text" | "choice" | "file" | "folder";
  choices: string[];
}

export interface PendingInterrupt {
  interrupt_id?: string | null;
  namespace?: string[];
  identity?: string | null;
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
  id?: string | null;
  role: "user" | "assistant" | "system";
  content: string;
  content_blocks?: UserContentBlock[] | null;
  attachment_ids?: string[];
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

export type ChatDraft = SchemaChatDraft;
export type ChatQueueItem = SchemaChatQueueItem;
export type ChatSearchResult = SchemaChatSearchResult;

export interface ChatConversation {
  project_id?: string | null;
  agent_setup_version_id?: string | null;
  setup_overrides?: import("./workspaceApi").SetupConfiguration;
  id: string;
  title?: string | null;
  display_title?: string;
  archived?: boolean;
  archived_at?: string | null;
  area_kind?: "general" | "project";
  area_id?: string | null;
  area_label?: string | null;
  area_project_path?: string | null;
  area_workspace_id?: string | null;
  deployment_id: string;
  profile_id: string | null;
  inherit_deployment_settings?: boolean;
  project_path: string | null;
  workspace_id: string | null;
  thread_id: string | null;
  transcript: ChatMessage[];
  current_run_id: string | null;
  run_ids: string[];
  source_checkpoint_id?: string | null;
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
  pending_cancel_input_ids?: string[];
  draft?: ChatDraft | null;
  queue?: ChatQueueItem[];
  events: Array<{ at: string; kind: string; detail: Record<string, unknown> }>;
  continuity?: ChatContinuity | null;
  deploy_health?: ChatDeployHealth | null;
  filesystem_tools_available?: boolean;
  shell_tools_available?: boolean;
  approval_mode?: "ask" | "full_access";
  desktop_access?: "off" | "selected" | "all";
  enabled_tools?: string[];
  created_at: string;
  updated_at: string;
}

export type DesktopAccess = "off" | "selected" | "all";

export interface BrowserRuntimeStatus {
  supported: boolean;
  installed: boolean;
  node_version: string;
  playwright_mcp_version: string;
  reason: string | null;
}

export interface BrowserSessionStatus {
  thread_id: string;
  state: "active" | "lost" | "closed";
  worker: BrowserRuntimeStatus;
}

export interface WindowRuntimeStatus {
  available?: boolean;
  installed?: boolean;
  version?: string;
  reason?: string | null;
}

export interface TestWindow {
  hwnd: number;
  title: string;
  process_name: string;
  process_id: number;
  width?: number;
  height?: number;
}

export interface WindowAccessStatus {
  scope: DesktopAccess;
  hwnd?: number | null;
  selected_window?: TestWindow | null;
  stale?: boolean;
}

export interface KnowledgeProvenance {
  actor: KnowledgeActor;
  run_id: string | null;
  note: string | null;
}

export interface KnowledgeEntry {
  resources?: Array<{ path: string; sha256: string; size_bytes: number }>;
  package_source?: string | null;
  active?: boolean;
  enabled?: boolean;
  scope_bound?: boolean;
  scope_label?: string | null;
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
  resources?: Array<{ path: string; sha256: string; size_bytes: number }>;
  id: string;
  entry_id: string;
  content: string;
  previous_version_id: string | null;
  reverted_from_version_id: string | null;
  created_at: string;
  provenance: KnowledgeProvenance;
}

export interface KnowledgeConfig {
  automatic_save_policies?: Array<{ scope: KnowledgeScope; scope_id?: string | null; automatic_agent_writes: boolean }>;
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
  default_value?: unknown;
  default_source?: string | null;
  maximum: number | null;
  recommended?: number | null;
  supported?: boolean | null;
  accepted_values?: string[] | null;
  options: Array<{ value: string | number | boolean | null; label: string; description?: string }>;
}

export interface BundleConfigurationOptions {
  bundle_id: string | null;
  deployment_id: string | null;
  context_size: RuntimeControlDescriptor;
  gpu_layers: RuntimeControlDescriptor;
  startup_defaults: Record<string, RuntimeControlDescriptor>;
  per_request_defaults: Record<string, RuntimeControlDescriptor>;
  metadata: Record<string, unknown>;
}
