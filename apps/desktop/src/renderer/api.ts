import type {
  Deployment,
  ImportJob,
  InspectReport,
  ModelBundle,
  PathsInfo,
  RunProfile,
  RuntimeManifest,
  SettingsBags,
} from "./types";

function backendUrl(): string {
  return window.workbench?.backendUrl ?? "http://127.0.0.1:8000";
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
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
      body: JSON.stringify({ bundle_id, profile_id, startup: startup ?? {}, auto_start: true }),
    }),
  attachConnected: (endpoint: string, display_name?: string) =>
    request<Deployment>("/v1/deployments/connected", {
      method: "POST",
      body: JSON.stringify({ endpoint, display_name }),
    }),
  stop: (id: string) => request<Deployment>(`/v1/deployments/${id}/stop`, { method: "POST" }),
  detach: (id: string) => request<Deployment>(`/v1/deployments/${id}/detach`, { method: "POST" }),
  healthOf: (id: string) => request<Deployment>(`/v1/deployments/${id}/health`),
};
