import { useEffect, useMemo, useState } from "react";

import { api } from "./api";
import { tokenLabel } from "./ModelControls";
import { StatusBadge } from "./StatusBadge";
import type { Deployment, RunProfile } from "./types";
import "./ChatModelControls.css";

export interface ThinkingEffortOption {
  value: string;
  label: string;
}

interface ConfigurationOptionsWithPerRequest {
  per_request_defaults?: Record<string, { options?: Array<{ value: unknown; label: string }> }>;
}

interface ThinkingEffortOptionsState {
  options: ThinkingEffortOption[];
  loading: boolean;
}

export interface ChatModelControlsProps {
  deployments: Deployment[];
  profiles: RunProfile[];
  selectedDeploymentId: string;
  selectedProfileId: string;
  inheritDeploymentSettings: boolean;
  perRequestOverrides?: Record<string, unknown>;
  thinkingEffortOptions?: ThinkingEffortOption[];
  disabled?: boolean;
  locked?: boolean;
  missingDeploymentLabel?: string;
  onDeploymentChange: (deploymentId: string) => void;
  onProfileChange: (profileId: string) => void;
  onInheritDeploymentSettingsChange: (inherit: boolean) => void;
  onPerRequestOverridesChange: (overrides: Record<string, unknown>) => void;
}

export function ChatModelControls(props: ChatModelControlsProps) {
  const {
    deployments,
    profiles,
    selectedDeploymentId,
    selectedProfileId,
    inheritDeploymentSettings,
    perRequestOverrides = {},
    thinkingEffortOptions = [],
    disabled = false,
    locked = false,
    missingDeploymentLabel = "Connection unavailable",
    onDeploymentChange,
    onProfileChange,
    onInheritDeploymentSettingsChange,
    onPerRequestOverridesChange,
  } = props;
  const selectedDeployment = deployments.find((deployment) => deployment.id === selectedDeploymentId) ?? null;
  const selectedProfile = profiles.find((profile) => profile.id === selectedProfileId) ?? null;
  const effectiveStartup = useMemo(
    () => startupSettings(selectedDeployment, selectedProfile, inheritDeploymentSettings),
    [inheritDeploymentSettings, selectedDeployment, selectedProfile],
  );
  const basePerRequest = useMemo(
    () => perRequestSettings(selectedDeployment, selectedProfile, inheritDeploymentSettings),
    [inheritDeploymentSettings, selectedDeployment, selectedProfile],
  );
  const fetchedThinkingOptions = useThinkingEffortOptions(selectedDeployment, thinkingEffortOptions);
  const modelName = selectedDeployment ? deploymentName(selectedDeployment) : missingDeploymentLabel;
  const summary = selectedDeployment ? deploymentSummary(selectedDeployment) : "Choose a model";
  const presetName = selectedProfileId === "!none"
    ? "No preset"
    : selectedProfile?.display_name ?? (selectedProfileId ? "Preset unavailable" : "Saved setup");
  const context = selectedDeployment?.server_props?.n_ctx ?? numericSetting(effectiveStartup.ctx_size);
  const reasoning = reasoningSummary(effectiveStartup);
  const thinking = thinkingControl(basePerRequest, perRequestOverrides, selectedDeployment, selectedProfile, inheritDeploymentSettings, fetchedThinkingOptions.options, fetchedThinkingOptions.loading);
  const unavailableProfile = selectedProfileId && selectedProfileId !== "!none" && !selectedProfile;

  return (
    <details className="chat-model-controls">
      <summary className="chat-model-controls-trigger" aria-label={`Chat model settings: ${modelName}`}>
        <span className="chat-model-controls-icon" aria-hidden="true">
          <svg viewBox="0 0 20 20" focusable="false">
            <path d="M4 6.5C4 5.1 6.7 4 10 4s6 1.1 6 2.5S13.3 9 10 9 4 7.9 4 6.5Zm0 3.5c1.1 1 3.3 1.6 6 1.6s4.9-.6 6-1.6v3.5C16 14.9 13.3 16 10 16s-6-1.1-6-2.5V10Zm0-2c1.1 1 3.3 1.6 6 1.6s4.9-.6 6-1.6v.5c0 1.4-2.7 2.5-6 2.5S4 10.4 4 9V8Z" />
          </svg>
        </span>
        <span className="chat-model-controls-main">
          <span className="chat-model-controls-model">{modelName}</span>
          <span className="chat-model-controls-subtitle">{summary} / {presetName}</span>
        </span>
        {selectedDeployment ? <StatusBadge label={deploymentStatusLabel(selectedDeployment)} tone={deploymentTone(selectedDeployment)} /> : null}
      </summary>

      <div className="chat-model-controls-panel" role="group" aria-label="Model and preset controls">
        <div className="chat-model-controls-grid">
          <label>
            Model
            <select value={selectedDeploymentId} disabled={disabled || locked} onChange={(event) => onDeploymentChange(event.target.value)}>
              {selectedDeploymentId && !selectedDeployment ? <option value={selectedDeploymentId}>{missingDeploymentLabel}</option> : null}
              {deployments.length === 0 ? <option value="">No model available</option> : null}
              {deployments.map((deployment) => (
                <option key={deployment.id} value={deployment.id}>{deploymentOptionLabel(deployment)}</option>
              ))}
            </select>
          </label>

          <label>
            Preset
            <select value={selectedProfileId} disabled={disabled || locked} onChange={(event) => {
              const next = event.target.value;
              onProfileChange(next);
              onInheritDeploymentSettingsChange(next !== "!none");
            }}>
              <option value="">Use saved setup settings</option>
              <option value="!none">No preset - ignore saved response settings and instructions</option>
              {unavailableProfile ? <option value={selectedProfileId}>Preset unavailable</option> : null}
              {profiles.map((profile) => (
                <option key={profile.id} value={profile.id}>{profile.display_name}</option>
              ))}
            </select>
          </label>
        </div>

        <dl className="chat-model-controls-facts">
          <div>
            <dt>Context</dt>
            <dd>{context ? `${tokenLabel(context)} tokens${selectedDeployment?.server_props?.n_ctx ? " reported by server" : " from setup"}` : "Not reported yet"}</dd>
          </div>
          <div>
            <dt>Thinking</dt>
            <dd>{reasoning.label}</dd>
          </div>
          <div>
            <dt>Endpoint</dt>
            <dd>{selectedDeployment?.scope === "managed" ? "Local managed model" : selectedDeployment?.endpoint ?? "Not selected"}</dd>
          </div>
        </dl>

        <div className="chat-model-controls-thinking" aria-label="Saved thinking setup">
          <div className="chat-model-controls-thinking-head">
            <span>Thinking effort</span>
            <strong>{thinking.label}</strong>
          </div>
          <input
            aria-label="Thinking effort for this message"
            type="range"
            min="0"
            max={Math.max(0, thinking.options.length - 1)}
            step="1"
            value={thinking.index}
            disabled={disabled || !thinking.supported}
            onChange={(event) => {
              const next = thinking.options[Number(event.target.value)]?.value ?? thinking.options[0]?.value ?? "";
              onPerRequestOverridesChange(updateOverride(perRequestOverrides, "reasoning_effort", next === "" || next === "default" ? null : next));
            }}
          />
          <div className="chat-model-controls-efforts" aria-hidden="true">
            {thinking.options.length > 0
              ? thinking.options.map((item) => <span key={item.value}>{item.label}</span>)
              : <span>{fetchedThinkingOptions.loading ? "Loading" : "Unavailable"}</span>}
          </div>
          <p className="chat-model-controls-note">
            {thinking.supported
              ? "Thinking effort is sent with the next Chat request. It does not change active or already queued work."
              : thinking.reason}
            {" "}Startup thinking budget: {reasoning.budgetLabel}.
          </p>
        </div>
      </div>
    </details>
  );
}

export function useThinkingEffortOptions(deployment: Deployment | null, providedOptions: ThinkingEffortOption[] = []): ThinkingEffortOptionsState {
  const [fetched, setFetched] = useState<ThinkingEffortOption[]>([]);
  const [loading, setLoading] = useState(false);
  const bundleId = deployment?.bundle_id ?? "";
  const deploymentId = deployment?.id ?? "";
  const provided = useMemo(() => normalizeEffortOptions(providedOptions), [providedOptions]);

  useEffect(() => {
    if (provided.length > 0) {
      setFetched([]);
      setLoading(false);
      return;
    }
    if (!bundleId) {
      setFetched([]);
      setLoading(false);
      return;
    }
    let cancelled = false;
    setFetched([]);
    setLoading(true);
    void api.modelConfiguration(bundleId, deploymentId || undefined)
      .then((report) => {
        if (cancelled) {
          return;
        }
        const descriptor = (report as ConfigurationOptionsWithPerRequest).per_request_defaults?.reasoning_effort;
        const options = normalizeEffortOptions((descriptor?.options ?? []).flatMap((option) => (
          typeof option.value === "string" ? [{ value: option.value, label: option.label }] : []
        )));
        setFetched(options);
      })
      .catch(() => {
        if (!cancelled) {
          setFetched([]);
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [bundleId, deploymentId, provided.length]);

  return { options: provided.length > 0 ? provided : fetched, loading: provided.length > 0 ? false : loading };
}

function startupSettings(deployment: Deployment | null, profile: RunProfile | null, inheritDeploymentSettings: boolean): Record<string, unknown> {
  if (profile) {
    return profile.bags.startup.applied ?? profile.bags.startup.requested ?? {};
  }
  if (!inheritDeploymentSettings) {
    return {};
  }
  return deployment?.settings?.startup?.applied ?? deployment?.applied_startup ?? {};
}

function perRequestSettings(deployment: Deployment | null, profile: RunProfile | null, inheritDeploymentSettings: boolean): Record<string, unknown> {
  if (profile) {
    return profile.bags.per_request.applied ?? profile.bags.per_request.requested ?? {};
  }
  if (!inheritDeploymentSettings) {
    return {};
  }
  return deployment?.settings?.per_request?.applied ?? {};
}

function deploymentName(deployment: Deployment): string {
  return deployment.display_name.replace(/^(managed|connected):/, "");
}

function deploymentSummary(deployment: Deployment): string {
  if (deployment.status === "running") {
    return deployment.server_props?.n_ctx ? `${tokenLabel(deployment.server_props.n_ctx)} context` : "Ready";
  }
  if (deployment.scope === "managed" && deployment.status === "stopped") {
    return "Loads when sent";
  }
  if (deployment.status === "starting") {
    return "Loading";
  }
  return deployment.status || "Not ready";
}

function deploymentStatusLabel(deployment: Deployment): string {
  if (deployment.status === "running") {
    return "Ready";
  }
  if (deployment.scope === "managed" && deployment.status === "stopped") {
    return "Loads when sent";
  }
  if (deployment.status === "starting") {
    return "Loading";
  }
  return "Not ready";
}

function deploymentTone(deployment: Deployment): "neutral" | "live" | "warn" | "danger" {
  if (deployment.status === "running") {
    return "live";
  }
  if (deployment.scope === "managed" && deployment.status === "stopped") {
    return "neutral";
  }
  if (deployment.status === "starting") {
    return "warn";
  }
  return "danger";
}

function deploymentOptionLabel(deployment: Deployment): string {
  return `${deploymentName(deployment)} / ${deploymentStatusLabel(deployment)}`;
}

function reasoningSummary(settings: Record<string, unknown>): { label: string; budgetLabel: string } {
  const mode = stringSetting(settings.reasoning);
  const effort = stringSetting(settings.reasoning_effort);
  const format = stringSetting(settings.reasoning_format);
  const budget = numericSetting(settings.reasoning_budget);
  const enabled = mode && mode !== "off" && mode !== "none";
  if (!enabled && !effort && budget == null && !format) {
    return { label: "Model default", budgetLabel: "Default" };
  }
  const parts = [
    mode ? `mode ${mode}` : null,
    effort && effort !== "default" ? `effort ${effort}` : null,
    format && format !== "auto" ? `format ${format}` : null,
  ].filter(Boolean);
  return {
    label: parts.length ? parts.join(" / ") : "Model default",
    budgetLabel: budget == null ? "Default" : budget < 0 ? "Unrestricted" : `${tokenLabel(budget)} tokens`,
  };
}

function thinkingControl(
  basePerRequest: Record<string, unknown>,
  overrides: Record<string, unknown>,
  deployment: Deployment | null,
  profile: RunProfile | null,
  inheritDeploymentSettings: boolean,
  options: ThinkingEffortOption[],
  loadingOptions: boolean,
): { supported: boolean; label: string; index: number; options: ThinkingEffortOption[]; reason: string } {
  const unsupported = [
    ...(profile?.bags.per_request.unsupported ?? []),
    ...(deployment?.settings?.per_request?.unsupported ?? []),
    ...(profile?.bags.per_request.retired.map((item) => item.key) ?? []),
    ...(deployment?.settings?.per_request?.retired.map((item) => item.key) ?? []),
  ];
  const normalizedOptions = normalizeEffortOptions(options);
  const hasReportedOptions = normalizedOptions.length > 0;
  const supported = !loadingOptions && hasReportedOptions && !unsupported.includes("reasoning_effort");
  const value = stringSetting(overrides.reasoning_effort)
    ?? stringSetting(basePerRequest.reasoning_effort)
    ?? (inheritDeploymentSettings ? stringSetting(deployment?.settings?.per_request?.applied?.reasoning_effort) : null)
    ?? "default";
  const normalized = normalizedOptions.some((option) => option.value === value) ? value : normalizedOptions[0]?.value ?? "";
  return {
    supported,
    label: loadingOptions ? "Loading options" : supported ? effortLabel(normalized, normalizedOptions) : "Unavailable",
    index: Math.max(0, normalizedOptions.findIndex((option) => option.value === normalized)),
    options: normalizedOptions,
    reason: loadingOptions
      ? "Reading supported per-message thinking effort options for this setup."
      : hasReportedOptions
      ? "This selected setup reports that per-message thinking effort is unavailable. Change the preset or model setup to use it."
      : "This setup has no reported per-message thinking effort options.",
  };
}

function normalizeEffortOptions(options: ThinkingEffortOption[]): ThinkingEffortOption[] {
  const seen = new Set<string>();
  return options
    .map((option) => ({ value: option.value.trim(), label: option.label.trim() || option.value.trim() }))
    .filter((option) => {
      if (!option.value || seen.has(option.value)) {
        return false;
      }
      seen.add(option.value);
      return true;
    });
}

function effortLabel(value: string, options: ThinkingEffortOption[]): string {
  if (value === "default") {
    return "Model default";
  }
  return options.find((option) => option.value === value)?.label ?? value;
}

function updateOverride(overrides: Record<string, unknown>, key: string, value: unknown): Record<string, unknown> {
  const next = { ...overrides };
  if (value == null || value === "") {
    delete next[key];
  } else {
    next[key] = value;
  }
  return next;
}

function stringSetting(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function numericSetting(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value;
  }
  if (typeof value === "string" && value.trim() && Number.isFinite(Number(value))) {
    return Number(value);
  }
  return null;
}
