import { useEffect, useState } from "react";
import { errorMessage } from "./errors";
import { workspaceApi, type ResolvedSetupSelection, type SetupConfiguration } from "./workspaceApi";

export interface EffectiveSetting {
  value?: unknown;
  source: string;
  source_id?: string | null;
  inherited: boolean;
  known: boolean;
  requires_reload: boolean;
  unavailable_reason?: string | null;
  requested_override?: unknown;
  default_value?: unknown;
  default_source?: string | null;
  supported?: boolean | null;
  inherited_value?: unknown;
  inherited_source?: string | null;
}
export type SetupPreview = ResolvedSetupSelection & { effective_values?: Record<string, EffectiveSetting> };

export function settingValue(value: unknown): string {
  if (value == null) return "Not reported";
  if (Array.isArray(value)) return value.length ? `${value.length} selected` : "None";
  if (typeof value === "boolean") return value ? "On" : "Off";
  if (typeof value === "number" && Number.isFinite(value)) return Number.isInteger(value) ? String(value) : String(Number(value.toPrecision(6)));
  const labels: Record<string, string> = { ask: "Ask for approval", approve_for_me: "Approve for me", full_access: "Full access", on: "On", off: "Off", low: "Low", medium: "Medium", high: "High", xhigh: "Xhigh", auto: "Automatic" };
  return labels[String(value)] ?? String(value);
}

export function settingSource(source?: string | null): string {
  const labels: Record<string, string> = {
    server_template: "Model default", gguf_template: "Model default", server_properties: "Server reported",
    loaded_template_settings: "Loaded template", loaded_startup: "Loaded settings", workbench_default: "Workbench default",
    pinned_runtime_default: "Runtime default", gguf_metadata: "Model metadata", runtime_observation: "Runtime reported",
    automatic_fit: "Automatic fit", backend_recommendation: "Recommended", unavailable: "Unavailable",
  };
  return source ? labels[source] ?? source : "Default not reported";
}

/** Preview the same resolution used at submission; never show a previous selection's facts. */
export function useSetupPreview(value: SetupConfiguration, projectId: string | null = null, agentId: string | null = null, scope: "application" | "project" | "agent" | "conversation" = "conversation") {
  const serialized = JSON.stringify(value);
  const key = `${scope}:${projectId}:${agentId}:${serialized}`;
  const [result, setResult] = useState<{ key: string; data: SetupPreview | null; error: string }>({ key: "", data: null, error: "" });
  useEffect(() => {
    let cancelled = false;
    void workspaceApi.resolveSetup(projectId, agentId, JSON.parse(serialized) as SetupConfiguration, scope).then(data => {
      if (!cancelled) setResult({ key, data, error: "" });
    }).catch(failure => { if (!cancelled) setResult({ key, data: null, error: errorMessage(failure) }); });
    return () => { cancelled = true; };
  }, [key, serialized, projectId, agentId, scope]);
  return result.key === key ? { ...result, loading: false } : { key, data: null, error: "", loading: true };
}
