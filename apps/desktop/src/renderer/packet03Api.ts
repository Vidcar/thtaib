import { api, backendUrl } from "./api";
import type { PresentationSettings } from "./types";
import type { components } from "../generated/shared-contracts/openapi";

export async function packet03Request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${backendUrl()}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
  });
  const body = (await response.json().catch(() => ({}))) as T & {
    detail?: { message?: string; code?: string } | string;
    error?: string;
  };
  if (!response.ok) {
    const detail = body.detail;
    const message = typeof detail === "object" && detail?.message ? detail.message : typeof detail === "string" ? detail : body.error;
    throw new Error(message ?? `${response.status} ${path}`);
  }
  return body;
}

export type RetainedAssetOrigin = "upload" | "verified_output";
export type RetainedAssetScope = "session" | "project";
export type AssetContentKind = "text" | "code";
export type RetainedAssetSourceStatus = "retained_only" | "unchanged" | "changed" | "missing" | "unavailable";

export interface RetainedAsset {
  id: string;
  origin: RetainedAssetOrigin;
  scope: RetainedAssetScope;
  session_id: string;
  project_path: string | null;
  access_scope: string;
  storage: "application.sqlite";
  filename: string;
  content_type: string;
  content_kind: AssetContentKind;
  encoding: "utf-8";
  size_bytes: number;
  sha256: string;
  observed_at: string;
  source_run_id: string | null;
  source_tool_call_id: string | null;
  source_tool_name: string | null;
  mutable_reference: string | null;
  observation: string | null;
  deleted_at: string | null;
}

export interface RetainedAssetPreview {
  id: string;
  filename: string;
  content_type: string;
  size_bytes: number;
  sha256: string;
  preview: string;
  truncated: boolean;
  source_status: RetainedAssetSourceStatus;
}

export interface RetainedAssetContent {
  id: string;
  filename: string;
  content_type: string;
  encoding: "utf-8";
  text: string;
  sha256: string;
  size_bytes: number;
  source_status: RetainedAssetSourceStatus;
}

export interface RetainedAssetDeletionPreview {
  requested_asset_ids: string[];
  affected_asset_ids: string[];
  preserved_asset_ids: string[];
  affected_sessions: string[];
  retained_sessions: string[];
  affected_runs: string[];
  retained_runs: string[];
  affected_projects: string[];
  retained_projects: string[];
  affected_branches: string[];
  retained_branches: string[];
  affected_cases: string[];
  retained_cases: string[];
  note: string;
}

export type RetainedAssetReuseResult = components["schemas"]["TextContentBlock"][];

export interface RetainedUploadRequest {
  session_id: string;
  filename: string;
  content_type: string;
  content_kind: AssetContentKind;
  content_base64: string;
}

export interface PermissionGrant {
  id: string;
  scope: "session" | "always";
  thread_id: string | null;
  project_path: string | null;
  action: string;
  arguments: Record<string, unknown>;
  created_at: string;
  source_run_id: string;
}

export interface BackupExternalReference {
  kind: "project" | "model" | "runtime" | "credential";
  path: string | null;
  id: string | null;
  included: false;
  missing: boolean;
}

export interface BackupManifest {
  format: "local-ai-workbench-backup";
  format_version: 1;
  product_version: string;
  backup_id: string;
  created_at: string;
  files: Array<{ path: string; sha256: string; size_bytes: number }>;
  directories: string[];
  included_roots: string[];
  external_references: BackupExternalReference[];
  checkpoint_versions: Record<string, string>;
  credentials_excluded: true;
  no_effect_replay: true;
  note: string;
}

export interface BackupCreateResult {
  archive_path: string;
  manifest: BackupManifest;
}

export interface BackupRestoreResult {
  destination_root: string;
  manifest: BackupManifest;
  missing_dependencies: BackupExternalReference[];
  activated: false;
  no_effect_replay: true;
}

export interface AttentionItem {
  run_id: string;
  conversation_id: string | null;
  title: string;
  kind: "approval" | "question" | "failure" | string;
  identity: string;
}

export const packet03Api = {
  assets: (filters: { sessionId?: string; projectPath?: string; origin?: RetainedAssetOrigin; includeDeleted?: boolean } = {}) => {
    const params = new URLSearchParams();
    if (filters.sessionId) params.set("session_id", filters.sessionId);
    if (filters.projectPath) params.set("project_path", filters.projectPath);
    if (filters.origin) params.set("origin", filters.origin);
    if (filters.includeDeleted) params.set("include_deleted", "true");
    const query = params.toString();
    return packet03Request<RetainedAsset[]>(`/v1/assets${query ? `?${query}` : ""}`);
  },
  uploadAsset: (payload: RetainedUploadRequest) =>
    packet03Request<RetainedAsset>("/v1/assets/uploads", { method: "POST", body: JSON.stringify(payload) }),
  previewAsset: (assetId: string, filters: { sessionId?: string; projectPath?: string } = {}) => {
    const params = new URLSearchParams();
    if (filters.sessionId) params.set("session_id", filters.sessionId);
    if (filters.projectPath) params.set("project_path", filters.projectPath);
    const query = params.toString();
    return packet03Request<RetainedAssetPreview>(`/v1/assets/${encodeURIComponent(assetId)}/preview${query ? `?${query}` : ""}`);
  },
  contentAsset: (assetId: string, filters: { sessionId?: string; projectPath?: string } = {}) => {
    const params = new URLSearchParams();
    if (filters.sessionId) params.set("session_id", filters.sessionId);
    if (filters.projectPath) params.set("project_path", filters.projectPath);
    const query = params.toString();
    return packet03Request<RetainedAssetContent>(`/v1/assets/${encodeURIComponent(assetId)}/content${query ? `?${query}` : ""}`);
  },
  reuseAssets: (payload: { asset_ids: string[]; session_id?: string | null; project_path?: string | null; allow_cross_session_reuse?: boolean; max_chars?: number }) =>
    packet03Request<RetainedAssetReuseResult>("/v1/assets/reuse", { method: "POST", body: JSON.stringify(payload) }),
  deleteAssetPreview: (assetIds: string[]) =>
    packet03Request<RetainedAssetDeletionPreview>("/v1/assets/delete-preview", { method: "POST", body: JSON.stringify({ asset_ids: assetIds }) }),
  deleteAssets: (assetIds: string[]) =>
    packet03Request<RetainedAssetDeletionPreview>("/v1/assets/delete", { method: "POST", body: JSON.stringify({ asset_ids: assetIds }) }),
  presentation: () => api.presentationSettings(),
  savePresentation: (payload: Partial<PresentationSettings>) => api.updatePresentationSettings(payload),
  grants: () => packet03Request<PermissionGrant[]>("/v1/settings/grants"),
  revokeGrant: (grantId: string) => packet03Request<{ revoked: true }>(`/v1/settings/grants/${encodeURIComponent(grantId)}`, { method: "DELETE" }),
  createBackup: (destination: string) =>
    packet03Request<BackupCreateResult>("/v1/backups", { method: "POST", body: JSON.stringify({ destination }) }),
  restoreBackup: (archivePath: string, destinationRoot: string) =>
    packet03Request<BackupRestoreResult>("/v1/backups/restore", {
      method: "POST",
      body: JSON.stringify({ archive_path: archivePath, destination_root: destinationRoot }),
    }),
  attention: () => packet03Request<AttentionItem[]>("/v1/desktop/attention"),
  activeWork: () => packet03Request<{ active_run_ids: string[] }>("/v1/desktop/work"),
};
