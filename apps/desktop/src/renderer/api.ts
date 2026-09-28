import type { SchemaBundleProjectors, SchemaCapabilityEvidence, SchemaCapabilityProbeReport, SchemaHubRepository, SchemaChatConversationCreateRequest, SchemaChatStartRequest } from "../generated/shared-contracts/openapi";
import type {
  AgentRun,
  AgentRunOperational,
  BundleConfigurationOptions,
  ChatConversation,
  ChatMessage,
  ContextCapture,
  Deployment,
  DeletePreview,
  DeploymentProfileChanges,
  EngineMeasurement,
  ImportJob,
  InspectReport,
  LabCase,
  LabRestore,
  LabResult,
  KnowledgeConfig,
  KnowledgeEntry,
  KnowledgeKind,
  KnowledgeScope,
  KnowledgeVersion,
  LabToolMode,
  LabWorkspace,
  ModelBundle,
  ModelCard,
  ModelStorageSummary,
  PathsInfo,
  PresentationSettings,
  RedactionMode,
  RunProfile,
  ResponseRecipeOrigin,
  RuntimeManifest,
  ManagedModelsRuntime,
  SettingsBags,
  ChatSearchResult,
  BrowserRuntimeStatus,
  BrowserSessionStatus,
  BrowserActionRequest,
  BrowserLiveEvent,
  WindowRuntimeStatus,
  TestWindow,
  WindowAccessStatus,
  DesktopAccess,
} from "./types";

export const DEFAULT_GPU_STARTUP = {
  n_gpu_layers: "auto",
  fit: "on",
  flash_attn: "auto",
  parallel: 4,
  kv_unified: true,
} as const;

export const DEFAULT_EMBEDDING_STARTUP = {
  embedding: "on",
  pooling: "last",
} as const;

export function backendUrl(): string {
  return window.workbench?.backendUrl ?? "http://127.0.0.1:8000";
}

export class ApiError extends Error {
  constructor(message: string, readonly status: number, readonly code?: string) {
    super(message);
    this.name = "ApiError";
  }
}

export function readApiFailure(body: unknown): { message?: string; code?: string } {
  if (!body || typeof body !== "object") {
    return {};
  }
  const record = body as { error?: unknown; code?: unknown; detail?: unknown };
  const topCode = typeof record.code === "string" && record.code ? record.code : undefined;
  const topError = typeof record.error === "string" && record.error ? record.error : undefined;
  const detail = record.detail;
  if (typeof detail === "string" && detail) {
    return { message: detail, code: topCode };
  }
  if (detail && typeof detail === "object") {
    const nested = detail as { message?: unknown; code?: unknown };
    const message = typeof nested.message === "string" && nested.message ? nested.message : topError;
    const code = typeof nested.code === "string" && nested.code ? nested.code : topCode;
    return { message, code };
  }
  return { message: topError, code: topCode };
}

export async function request<T>(path: string, init?: RequestInit): Promise<T> {
  // Electron main injects X-Workbench-Local-Token. The renderer must not.
  const response = await fetch(`${backendUrl()}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
  });
  const body = (await response.json().catch(() => ({}))) as T;
  if (!response.ok) {
    const failure = readApiFailure(body);
    throw new ApiError(failure.message ?? `${response.status} ${path}`, response.status, failure.code);
  }
  return body;
}

/** The trusted main frame adds authentication to this fetch, as to normal requests. */
export async function streamBrowserEvents(threadId: string, onEvent: (event: BrowserLiveEvent) => void, signal: AbortSignal): Promise<void> {
  const path = `/v1/browser/sessions/${encodeURIComponent(threadId)}/events`;
  const response = await fetch(`${backendUrl()}${path}`, { signal, cache: "no-store", headers: { Accept: "text/event-stream" } });
  if (!response.ok) {
    const failure = readApiFailure(await response.json().catch(() => ({})));
    throw new ApiError(failure.message ?? `Browser connection failed (${response.status}).`, response.status, failure.code);
  }
  if (!response.body) throw new Error("The browser live connection is unavailable.");
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffered = "";
  try {
    while (!signal.aborted) {
      const { value, done } = await reader.read();
      if (done) break;
      buffered = (buffered + decoder.decode(value, { stream: true })).replace(/\r\n/g, "\n");
      if (buffered.length > 8_000_000) throw new Error("The browser live message exceeded its size limit.");
      let end: number;
      while ((end = buffered.indexOf("\n\n")) >= 0) {
        const block = buffered.slice(0, end);
        buffered = buffered.slice(end + 2);
        const lines = block.split("\n");
        const type = lines.find(line => line.startsWith("event:"))?.slice(6).trim();
        if (type !== "state" && type !== "frame") continue;
        const data = JSON.parse(lines.filter(line => line.startsWith("data:")).map(line => line.slice(5).trimStart()).join("\n"));
        onEvent({ type, data } as BrowserLiveEvent);
      }
    }
  } finally { await reader.cancel().catch(() => {}); reader.releaseLock(); }
}

// Settings and Chat share one ordered writer. Reads which straddle a write
// rehydrate afterward, so a late initial load cannot replace the saved values.
let presentationWrite: Promise<unknown> = Promise.resolve();
let presentationRevision = 0;
async function readPresentation(): Promise<PresentationSettings> {
  for (;;) {
    const revision = presentationRevision;
    await presentationWrite;
    const value = await request<PresentationSettings>("/v1/settings/presentation");
    if (revision === presentationRevision) return value;
  }
}
function writePresentation(payload: Partial<PresentationSettings>): Promise<PresentationSettings> {
  presentationRevision += 1;
  const body = JSON.stringify(payload);
  const result = presentationWrite.then(() => request<PresentationSettings>("/v1/settings/presentation", { method: "PATCH", body }));
  presentationWrite = result.catch(() => undefined);
  return result;
}

const chatListFlights = new Map<string, Promise<ChatConversation[]>>();

export const api = {
  health: () => request<{ status: string; product: string; surface: string }>("/health"),
  presentationSettings: readPresentation,
  updatePresentationSettings: writePresentation,
  paths: () => request<PathsInfo>("/v1/paths"),
  bundles: () => request<ModelBundle[]>("/v1/bundles"),
  imports: () => request<ImportJob[]>("/v1/imports"),
  modelStorage: () => request<ModelStorageSummary>("/v1/models/storage"),
  setModelStorage: (path: string) => request<ModelStorageSummary>("/v1/models/storage", { method: "PUT", body: JSON.stringify({ path }) }),
  cleanupModelStorage: () => request<{ removed: string[] }>("/v1/models/storage/cleanup", { method: "POST" }),
  verifyModel: (id: string) => request<ModelBundle>(`/v1/bundles/${id}`),
  repairModel: (id: string) => request<ImportJob>(`/v1/bundles/${id}/repair`, { method: "POST" }),
  cancelImport: (id: string) => request<ImportJob>(`/v1/imports/${id}/cancel`, { method: "POST" }),
  retryImport: (id: string) => request<ImportJob>(`/v1/imports/${id}/retry`, { method: "POST" }),
  discardImport: (id: string) => request<ImportJob>(`/v1/imports/${id}/discard`, { method: "POST" }),
  importLocal: (source_path: string, display_name?: string, copy_files = true) =>
    request<ImportJob>("/v1/imports/local", {
      method: "POST",
      body: JSON.stringify({ source_path, display_name, copy_files }),
    }),
  searchHf: (query: string) => request<Array<{ repo_id: string; downloads: number | null; likes: number | null }>>(`/v1/models/huggingface/search?q=${encodeURIComponent(query)}&limit=20`),
  inspectHf: (repo_id: string, revision = "main") =>
    request<SchemaHubRepository>("/v1/models/huggingface/inspect", {
      method: "POST",
      body: JSON.stringify({ repo_id, revision }),
    }),
  importHf: (repo_id: string, revision: string, allow_patterns: string[], recipe_ids: string[] = [], default_recipe_id: string | null = null, initial?: { startup: Record<string, unknown>; per_request?: Record<string, unknown>; recipe_id?: string | null }) =>
    request<ImportJob>("/v1/imports/huggingface", {
      method: "POST",
      body: JSON.stringify({ repo_id, revision, allow_patterns, recipe_ids, default_recipe_id, ...(initial ? { initial_startup: initial.startup, ...(initial.recipe_id ? { initial_recipe_id: initial.recipe_id, initial_per_request: initial.per_request ?? {} } : initial.per_request ? { initial_per_request: initial.per_request } : {}) } : {}) }),
    }),
  refreshResponseRecipes: (bundleId: string, restore_hidden = false) => request<ModelBundle>(`/v1/bundles/${bundleId}/response-recipes/refresh`, { method: "POST", body: JSON.stringify({ restore_hidden }) }),
  setResponseRecipeVisibility: (bundleId: string, recipeId: string, visible: boolean) => request<ModelBundle>(`/v1/bundles/${bundleId}/response-recipes/${encodeURIComponent(recipeId)}/visibility`, { method: "PUT", body: JSON.stringify({ visible }) }),
  modelCard: (bundleId: string) => request<ModelCard>(`/v1/bundles/${encodeURIComponent(bundleId)}/model-card`),
  createRecipeConfigurations: (bundleId: string, recipe_ids: string[], default_recipe_id: string | null = null) =>
    request<{ bundle: ModelBundle; configurations: RunProfile[] }>(`/v1/bundles/${bundleId}/response-recipes/configurations`, {
      method: "POST",
      body: JSON.stringify({ recipe_ids, default_recipe_id }),
    }),
  inspect: (bundleId: string) => request<InspectReport>(`/v1/bundles/${bundleId}/inspect`),
  modelConfiguration: (bundleId: string, deploymentId?: string, refresh = false, selection?: { configuration_id?: string | null; startup?: Record<string, unknown> }) => selection
    ? request<BundleConfigurationOptions>(`/v1/bundles/${bundleId}/configuration-options`, { method: "POST", body: JSON.stringify({ ...selection, deployment_id: deploymentId ?? null, refresh }) })
    : request<BundleConfigurationOptions>(`/v1/bundles/${bundleId}/configuration-options?refresh=${refresh}${deploymentId ? `&deployment_id=${encodeURIComponent(deploymentId)}` : ""}`),
  deploymentConfiguration: (deploymentId: string) => request<BundleConfigurationOptions>(`/v1/deployments/${deploymentId}/configuration-options`),
  modelProjectors: (id: string) => request<SchemaBundleProjectors>(`/v1/bundles/${id}/projectors`),
  selectModelProjector: (id: string, path: string | null) => request<ModelBundle>(`/v1/bundles/${id}/projector`, { method: "PUT", body: JSON.stringify({ path }) }),
  selectModelChatTemplate: (id: string, origin: "gguf" | "repository" | "publisher") => request<ModelBundle>(`/v1/bundles/${id}/chat-template`, { method: "PUT", body: JSON.stringify({ origin }) }),
  capabilityProbe: (id: string, capability: string) => request<SchemaCapabilityEvidence>(`/v1/compatibility/deployments/${id}/probes`, { method: "POST", body: JSON.stringify({ capability }) }),
  capabilityStatus: (id: string) => request<SchemaCapabilityProbeReport>(`/v1/compatibility/deployments/${id}/probes`),
  previewSettings: (startup: object, per_request: object, agent: object) =>
    request<SettingsBags>("/v1/settings/preview", {
      method: "POST",
      body: JSON.stringify({ startup, per_request, agent }),
    }),
  createProfile: (payload: {
    display_name: string;
    bundle_id?: string;
    startup: object;
    per_request: object;
    agent: object;
  }) =>
    request<RunProfile>("/v1/profiles", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  profiles: () => request<RunProfile[]>("/v1/profiles"),
  deletionPreview: (kind: "bundle" | "profile", id: string, permanent = false) => request<DeletePreview>(`/v1/${kind === "bundle" ? "bundles" : "profiles"}/${id}/delete-preview${kind === "bundle" && permanent ? "?permanent=true" : ""}`),
  deleteModelRecord: (kind: "bundle" | "profile", id: string, permanent = false) => request<DeletePreview>(`/v1/${kind === "bundle" ? "bundles" : "profiles"}/${id}${kind === "bundle" && permanent ? "?permanent=true" : ""}`, { method: "DELETE" }),
  deploymentProfileChanges: (id: string) => request<DeploymentProfileChanges>(`/v1/deployments/${id}/profile-changes`),
  updateProfile: (id: string, payload: { display_name: string; bundle_id: string | null; startup: object; per_request: object; agent: object; expected_revision?: number }) =>
    request<RunProfile>(`/v1/profiles/${id}`, { method: "PUT", body: JSON.stringify(payload) }),
  renameProfile: (id: string, display_name: string) => request<RunProfile>(`/v1/profiles/${id}/rename`, { method: "POST", body: JSON.stringify({ display_name }) }),
  duplicateProfile: (id: string) => request<RunProfile>(`/v1/profiles/${id}/duplicate`, { method: "POST", body: "{}" }),
  start: (id: string) => request<Deployment>(`/v1/deployments/${id}/start`, { method: "POST" }),
  reload: (id: string) => request<Deployment>(`/v1/deployments/${id}/reload`, { method: "POST" }),
  reconfigure: (id: string, payload: { startup: Record<string, unknown>; replace_startup?: boolean; model_configuration_id?: string | null; expected_configuration_revision?: number; expected_updated_at?: string; conversation_id?: string | null }) => request<Deployment>(`/v1/deployments/${id}/reconfigure`, { method: "POST", body: JSON.stringify(payload) }),
  modelConfigurations: (bundleId: string) => request<RunProfile[]>(`/v1/bundles/${bundleId}/configurations`),
  saveModelConfiguration: (bundleId: string, payload: { display_name: string; startup: object; per_request: object; recipe_origin?: ResponseRecipeOrigin | null; configuration_id?: string; expected_revision?: number; make_default?: boolean }) => request<RunProfile>(`/v1/bundles/${bundleId}/configurations`, { method: "POST", body: JSON.stringify(payload) }),
  setDefaultConfiguration: (bundleId: string, configuration_id: string) => request<ModelBundle>(`/v1/bundles/${bundleId}/default-configuration`, { method: "PUT", body: JSON.stringify({ configuration_id }) }),
  smoke: (id: string) => request<{ ok: boolean; detail: string | null }>(`/v1/deployments/${id}/smoke`, { method: "POST" }),
  deploymentLogs: (id: string) => request<{ text: string; available: boolean }>(`/v1/deployments/${id}/logs`),
  runtime: () => request<RuntimeManifest | null>("/v1/runtime"),
  managedModelsRuntime: () => request<ManagedModelsRuntime>("/v1/runtime/models"),
  setManagedModelsRuntime: (max_loaded_models: number) => request<ManagedModelsRuntime>("/v1/runtime/models", { method: "PUT", body: JSON.stringify({ max_loaded_models }) }),
  pinRuntime: () => request<RuntimeManifest>("/v1/runtime/pin", { method: "POST", body: "{}" }),
  deployments: () => request<Deployment[]>("/v1/deployments"),
  startManaged: (bundle_id: string, profile_id?: string, startup?: object) =>
    request<Deployment>("/v1/deployments/managed", {
      method: "POST",
      body: JSON.stringify({
        bundle_id,
        profile_id,
        startup: startup ?? { ...DEFAULT_GPU_STARTUP },
        auto_start: true,
      }),
    }),
  prepareManaged: (bundle_id: string, profile_id: string | undefined, startup: object) =>
    request<Deployment>("/v1/deployments/managed", { method: "POST", body: JSON.stringify({ bundle_id, profile_id, startup, auto_start: false }) }),
  attachConnected: (endpoint: string, display_name?: string, startup?: object) =>
    request<Deployment>("/v1/deployments/connected", {
      method: "POST",
      body: JSON.stringify({ endpoint, display_name, startup }),
    }),
  stop: (id: string) => request<Deployment>(`/v1/deployments/${id}/stop`, { method: "POST" }),
  detach: (id: string) => request<Deployment>(`/v1/deployments/${id}/detach`, { method: "POST" }),
  healthOf: (id: string) => request<Deployment>(`/v1/deployments/${id}/health`),
  agentTools: () => request<{ enabled: string[]; tools?: Array<{ id: string; name: string; description: string; available?: boolean; unavailable_reason?: string | null }> }>("/v1/agent-tools"),
  browserRuntime: () => request<BrowserRuntimeStatus>("/v1/browser/runtime"),
  installBrowserRuntime: () => request<BrowserRuntimeStatus>("/v1/browser/runtime/install", { method: "POST", body: "{}" }),
  browserSession: (threadId: string) => request<BrowserSessionStatus>(`/v1/browser/sessions/${encodeURIComponent(threadId)}`),
  startBrowserSession: (threadId: string) => request<BrowserSessionStatus>(`/v1/browser/sessions/${encodeURIComponent(threadId)}/start`, { method: "POST", body: "{}" }),
  controlBrowserSession: (threadId: string, action: "take" | "return") => request<BrowserSessionStatus>(`/v1/browser/sessions/${encodeURIComponent(threadId)}/control`, { method: "POST", body: JSON.stringify({ action }) }),
  browserAction: (threadId: string, action: BrowserActionRequest) => request<BrowserSessionStatus>(`/v1/browser/sessions/${encodeURIComponent(threadId)}/actions`, { method: "POST", body: JSON.stringify(action) }),
  resetBrowserSession: (threadId: string) => request<BrowserSessionStatus>(`/v1/browser/sessions/${encodeURIComponent(threadId)}/reset`, { method: "POST", body: JSON.stringify({ confirmed: true }) }),
  closeBrowserSession: (threadId: string) => request<BrowserSessionStatus>(`/v1/browser/sessions/${encodeURIComponent(threadId)}`, { method: "DELETE" }),
  windowRuntime: () => request<WindowRuntimeStatus>("/v1/window-testing/runtime"),
  installWindowRuntime: () => request<WindowRuntimeStatus>("/v1/window-testing/runtime/install", { method: "POST", body: "{}" }),
  testWindows: () => request<TestWindow[]>("/v1/window-testing/windows"),
  windowAccess: (conversationId: string) => request<WindowAccessStatus>(`/v1/window-testing/conversations/${encodeURIComponent(conversationId)}/scope`),
  setWindowAccess: (conversationId: string, scope: DesktopAccess, hwnd?: number) => request<WindowAccessStatus>(`/v1/window-testing/conversations/${encodeURIComponent(conversationId)}/scope`, { method: "PUT", body: JSON.stringify({ scope, ...(hwnd ? { hwnd } : {}) }) }),
  startAgentRun: (
    deployment_id: string,
    task: string,
    presented_tools?: string[],
    workspace_id?: string,
    project_path?: string,
    embedding_deployment_id?: string,
    configuration?: import("./workspaceApi").SetupConfiguration,
  ) =>
    request<AgentRun>("/v1/agent-runs", {
      method: "POST",
        body: JSON.stringify({
          ...configuration,
          deployment_id,
        task,
        presented_tools,
        workspace_id,
        project_path,
        embedding_deployment_id,
      }),
    }),
  agentRun: (id: string) => request<AgentRunOperational>(`/v1/agent-runs/${id}?view=operational`),
  cancelAgentRun: (id: string) => request<AgentRun>(`/v1/agent-runs/${id}/cancel`, { method: "POST" }),
  decideAgentRunInterrupt: (id: string, type: "approve" | "reject") =>
    request<AgentRun>(`/v1/agent-runs/${id}/interrupt-decision`, {
      method: "POST",
      body: JSON.stringify({ decisions: [{ type }] }),
    }),
  registerAgentInteractionThread: (payload: { source_surface: "agent"; run_id?: string } | { source_surface: "chat"; conversation_id: string }) =>
    request<{ thread_id: string }>("/v1/agent-interaction/threads", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  createChatConversation: (payload: Omit<SchemaChatConversationCreateRequest, "inherit_deployment_settings"> & { inherit_deployment_settings?: boolean }) =>
    request<ChatConversation>("/v1/chat/conversations", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  chatConversations: (includeArchived = false) => {
    const key = includeArchived ? "archived" : "open";
    const existing = chatListFlights.get(key);
    if (existing) return existing;
    const flight = request<ChatConversation[]>(`/v1/chat/conversations?include_archived=${includeArchived ? "true" : "false"}`)
      .finally(() => { if (chatListFlights.get(key) === flight) chatListFlights.delete(key); });
    chatListFlights.set(key, flight);
    return flight;
  },
  searchChatConversations: (query: string, includeArchived = false) =>
    request<ChatSearchResult[]>(`/v1/chat/conversations/search?q=${encodeURIComponent(query)}&include_archived=${includeArchived ? "true" : "false"}`),
  chatConversation: (id: string) => request<ChatConversation>(`/v1/chat/conversations/${id}`),
  renameChatConversation: (id: string, title: string) =>
    request<ChatConversation>(`/v1/chat/conversations/${id}`, { method: "PATCH", body: JSON.stringify({ title }) }),
  archiveChatConversation: (id: string, archived = true) =>
    request<ChatConversation>(`/v1/chat/conversations/${id}/archive`, { method: "POST", body: JSON.stringify({ archived }) }),
  reopenChatConversation: (id: string) =>
    request<ChatConversation>(`/v1/chat/conversations/${id}/reopen`, { method: "POST", body: "{}" }),
  updateChatDraft: (id: string, payload: { content: string; attachment_ids?: string[]; expected_revision?: number | null; intended_config?: Record<string, unknown> }) =>
    request<ChatConversation>(`/v1/chat/conversations/${id}/draft`, { method: "PUT", body: JSON.stringify(payload) }),
  startChat: (
    id: string,
    payload: Omit<SchemaChatStartRequest, "inherit_deployment_settings"> & { inherit_deployment_settings?: boolean },
  ) =>
    request<ChatConversation>(`/v1/chat/conversations/${id}/start`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  enqueueChatTurn: (
    id: string,
    payload: Omit<SchemaChatStartRequest, "inherit_deployment_settings"> & { inherit_deployment_settings?: boolean },
  ) =>
    request<ChatConversation>(`/v1/chat/conversations/${id}/queue`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  cancelChat: (id: string, inputMessageId?: string) =>
    request<ChatConversation>(`/v1/chat/conversations/${id}/cancel`, {
      method: "POST",
      body: inputMessageId ? JSON.stringify({ input_message_id: inputMessageId }) : undefined,
    }),
  decideChatInterrupt: (id: string, type: "approve" | "reject") =>
    request<ChatConversation>(`/v1/chat/conversations/${id}/interrupt-decision`, {
      method: "POST",
      body: JSON.stringify({ decisions: [{ type }] }),
    }),
  replaceChatTranscript: (id: string, messages: ChatMessage[]) =>
    request<ChatConversation>(`/v1/chat/conversations/${id}/transcript`, {
      method: "PUT",
      body: JSON.stringify({ messages }),
    }),
  createWorkspace: (display_name: string, files: Record<string, string>) =>
    request<LabWorkspace>("/v1/lab/workspaces", {
      method: "POST",
      body: JSON.stringify({ display_name, files }),
    }),
  workspaces: () => request<LabWorkspace[]>("/v1/lab/workspaces"),
  workspaceFiles: (id: string) => request<{ files: Record<string, string> }>(`/v1/lab/workspaces/${id}/files`),
  writeWorkspaceFiles: (id: string, files: Record<string, string>) =>
    request<{ workspace: LabWorkspace; files: Record<string, string> }>(`/v1/lab/workspaces/${id}/files`, {
      method: "PUT",
      body: JSON.stringify({ files }),
    }),
  captureCase: (workspace_id: string, run_id?: string) =>
    request<LabCase>("/v1/lab/cases/capture", {
      method: "POST",
      body: JSON.stringify({ workspace_id, run_id }),
    }),
  labCases: () => request<LabCase[]>("/v1/lab/cases"),
  restoreCase: (id: string) => request<LabRestore>(`/v1/lab/cases/${id}/restore`, { method: "POST" }),
  rerunCase: (id: string, tool_mode: LabToolMode, workspace_id: string) =>
    request<LabResult>(`/v1/lab/cases/${id}/rerun`, {
      method: "POST",
      body: JSON.stringify({ tool_mode, workspace_id }),
    }),
  labResult: (id: string) => request<LabResult>(`/v1/lab/results/${id}`),
  measureEngine: (deployment_id?: string) =>
    request<EngineMeasurement>("/v1/lab/engine-measurements", {
      method: "POST",
      body: JSON.stringify({ deployment_id }),
    }),
  knowledgeConfig: () => request<KnowledgeConfig>("/v1/knowledge/config"),
  updateKnowledgeConfig: (payload: {
    context_captures?: { retention_seconds?: number | null; redaction_mode?: RedactionMode };
    scope_policies?: Partial<Record<KnowledgeScope, { automatic_agent_writes: boolean }>>;
  }) =>
    request<KnowledgeConfig>("/v1/knowledge/config", {
      method: "PUT",
      body: JSON.stringify(payload),
    }),
  knowledgeEntries: () => request<KnowledgeEntry[]>("/v1/knowledge/entries"),
  createKnowledgeEntry: (payload: {
    scope: KnowledgeScope;
    kind: KnowledgeKind;
    content: string;
    scope_id?: string;
    display_name?: string;
  }) =>
    request<KnowledgeEntry>("/v1/knowledge/entries", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  editKnowledgeEntry: (id: string, content: string, base_version: string) =>
    request<KnowledgeEntry>(`/v1/knowledge/entries/${id}/edit`, {
      method: "POST",
      body: JSON.stringify({ content, base_version }),
    }),
  revertKnowledgeEntry: (id: string, target_version_id: string, base_version: string) =>
    request<KnowledgeEntry>(`/v1/knowledge/entries/${id}/revert`, {
      method: "POST",
      body: JSON.stringify({ target_version_id, base_version }),
    }),
  knowledgeVersions: (id: string) => request<KnowledgeVersion[]>(`/v1/knowledge/entries/${id}/versions`),
  knowledgeVersion: (id: string) => request<KnowledgeVersion>(`/v1/knowledge/versions/${id}`),
  createContextCapture: (content: string) =>
    request<ContextCapture>("/v1/knowledge/captures", {
      method: "POST",
      body: JSON.stringify({ content, source: "desktop" }),
    }),
};
