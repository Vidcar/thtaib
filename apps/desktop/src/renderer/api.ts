import {
  applyConversationEvent,
  applyRunEvent,
  subscribeWorkbenchEvents,
} from "./sse";
import type { RunStreamEnvelope } from "./sse";
import type {
  AgentRun,
  ChatConversation,
  ChatMessage,
  ContextCapture,
  Deployment,
  EngineMeasurement,
  ImportJob,
  InspectReport,
  LabCase,
  LabRestore,
  LabResult,
  KnowledgeActor,
  KnowledgeConfig,
  KnowledgeEntry,
  KnowledgeKind,
  KnowledgeScope,
  KnowledgeVersion,
  LabToolMode,
  LabWorkspace,
  ModelBundle,
  PathsInfo,
  RedactionMode,
  RunProfile,
  RuntimeManifest,
  SettingsBags,
} from "./types";

export const DEFAULT_GPU_STARTUP = {
  ctx_size: 65536,
  n_gpu_layers: -1,
  flash_attn: "on",
} as const;

export const DEFAULT_EMBEDDING_STARTUP = {
  embedding: "on",
  pooling: "last",
} as const;

function backendUrl(): string {
  return window.workbench?.backendUrl ?? "http://127.0.0.1:8000";
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  // Electron main injects X-Workbench-Local-Token. The renderer must not.
  const response = await fetch(`${backendUrl()}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
  });
  const body = (await response.json().catch(() => ({}))) as T & { error?: string; code?: string };
  if (!response.ok) {
    throw new Error(body.error ?? `${response.status} ${path}`);
  }
  return body;
}

export const api = {
  health: () => request<{ status: string; product: string; surface: string }>("/health"),
  paths: () => request<PathsInfo>("/v1/paths"),
  bundles: () => request<ModelBundle[]>("/v1/bundles"),
  importLocal: (source_path: string, display_name?: string) =>
    request<ImportJob>("/v1/imports/local", {
      method: "POST",
      body: JSON.stringify({ source_path, display_name }),
    }),
  importHf: (repo_id: string, revision: string) =>
    request<ImportJob>("/v1/imports/huggingface", {
      method: "POST",
      body: JSON.stringify({ repo_id, revision }),
    }),
  inspect: (bundleId: string) => request<InspectReport>(`/v1/bundles/${bundleId}/inspect`),
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
  runtime: () => request<RuntimeManifest | null>("/v1/runtime"),
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
  attachConnected: (endpoint: string, display_name?: string, startup?: object) =>
    request<Deployment>("/v1/deployments/connected", {
      method: "POST",
      body: JSON.stringify({ endpoint, display_name, startup }),
    }),
  stop: (id: string) => request<Deployment>(`/v1/deployments/${id}/stop`, { method: "POST" }),
  detach: (id: string) => request<Deployment>(`/v1/deployments/${id}/detach`, { method: "POST" }),
  healthOf: (id: string) => request<Deployment>(`/v1/deployments/${id}/health`),
  agentTools: () => request<{ enabled: string[] }>("/v1/agent-tools"),
  startAgentRun: (
    deployment_id: string,
    task: string,
    presented_tools?: string[],
    workspace_id?: string,
    project_path?: string,
    embedding_deployment_id?: string,
  ) =>
    request<AgentRun>("/v1/agent-runs", {
      method: "POST",
      body: JSON.stringify({
        deployment_id,
        task,
        presented_tools,
        workspace_id,
        project_path,
        embedding_deployment_id,
      }),
    }),
  agentRun: (id: string) => request<AgentRun>(`/v1/agent-runs/${id}`),
  cancelAgentRun: (id: string) => request<AgentRun>(`/v1/agent-runs/${id}/cancel`, { method: "POST" }),
  decideAgentRunInterrupt: (id: string, type: "approve" | "reject") =>
    request<AgentRun>(`/v1/agent-runs/${id}/interrupt-decision`, {
      method: "POST",
      body: JSON.stringify({ decisions: [{ type }] }),
    }),
  createChatConversation: (payload: {
    deployment_id: string;
    profile_id?: string;
    project_path?: string;
    workspace_id?: string;
    memory_version_refs?: string[];
    skill_version_refs?: string[];
    protected_instruction_version_refs?: string[];
    knowledge_version_refs?: string[];
    embedding_deployment_id?: string;
    retrieval_project_paths?: string[];
  }) =>
    request<ChatConversation>("/v1/chat/conversations", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  chatConversations: () => request<ChatConversation[]>("/v1/chat/conversations"),
  chatConversation: (id: string) => request<ChatConversation>(`/v1/chat/conversations/${id}`),
  startChat: (
    id: string,
    payload: {
      task: string;
      presented_tools?: string[];
      deployment_id?: string;
      profile_id?: string;
      project_path?: string;
      workspace_id?: string;
      memory_version_refs?: string[];
      skill_version_refs?: string[];
      protected_instruction_version_refs?: string[];
      knowledge_version_refs?: string[];
      embedding_deployment_id?: string;
      retrieval_project_paths?: string[];
    },
  ) =>
    request<ChatConversation>(`/v1/chat/conversations/${id}/start`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  cancelChat: (id: string) =>
    request<ChatConversation>(`/v1/chat/conversations/${id}/cancel`, { method: "POST" }),
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
    provenance: { actor: KnowledgeActor; run_id?: string; note?: string };
  }) =>
    request<KnowledgeEntry>("/v1/knowledge/entries", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  editKnowledgeEntry: (id: string, content: string, base_version: string, actor: KnowledgeActor) =>
    request<KnowledgeEntry>(`/v1/knowledge/entries/${id}/edit`, {
      method: "POST",
      body: JSON.stringify({ content, base_version, provenance: { actor } }),
    }),
  revertKnowledgeEntry: (id: string, target_version_id: string, base_version: string, actor: KnowledgeActor) =>
    request<KnowledgeEntry>(`/v1/knowledge/entries/${id}/revert`, {
      method: "POST",
      body: JSON.stringify({ target_version_id, base_version, provenance: { actor } }),
    }),
  knowledgeVersions: (id: string) => request<KnowledgeVersion[]>(`/v1/knowledge/entries/${id}/versions`),
  createContextCapture: (content: string) =>
    request<ContextCapture>("/v1/knowledge/captures", {
      method: "POST",
      body: JSON.stringify({ content, source: "debug-panel" }),
    }),
  subscribeAgentRun: (
    runId: string,
    signal: AbortSignal,
    onRun: (run: AgentRun) => void,
  ) =>
    subscribeWorkbenchEvents<AgentRun>({
      runId,
      signal,
      apply: applyRunEvent,
      onRecord: onRun,
    }),
  subscribeChatConversation: (
    conversationId: string,
    signal: AbortSignal,
    onConversation: (conversation: ChatConversation) => void,
  ) =>
    subscribeWorkbenchEvents<ChatConversation>({
      conversationId,
      signal,
      apply: applyConversationEvent,
      onRecord: onConversation,
    }),
};

export type { RunStreamEnvelope };
