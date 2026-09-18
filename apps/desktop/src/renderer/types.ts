export type WorkbenchSurface = "managed-inference";

export type WorkbenchTab = "models" | "deployments";

export interface PathsInfo {
  root: string;
  models: string;
  runtimes: string;
  state: string;
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
