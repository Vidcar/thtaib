import { useEffect, useMemo, useState } from "react";

import { api } from "./api";
import { Icon } from "./Icon";
import { HoverHelp } from "./HoverHelp";
import { tokenLabel } from "./ModelControls";
import { StatusBadge } from "./StatusBadge";
import type { Deployment, RunProfile } from "./types";
import "./ChatModelControls.css";

export interface ThinkingEffortOption {
  value: string;
  label: string;
}

interface ConfigurationOptionsWithPerRequest {
  per_request_defaults?: Record<string, { options?: Array<{ value: unknown; label: string }>; supported?: boolean | null; accepted_values?: string[] | null }>;
}

interface ThinkingEffortOptionsState {
  options: ThinkingEffortOption[];
  modes: ThinkingEffortOption[];
  effortSupported?: boolean | null;
  modeSupported?: boolean | null;
  acceptedEfforts?: string[] | null;
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
    () => selectedDeployment?.applied_startup ?? selectedDeployment?.settings?.startup?.applied ?? {},
    [selectedDeployment],
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
  const requestEffort = stringSetting(perRequestOverrides.reasoning_effort) ?? stringSetting(basePerRequest.reasoning_effort) ?? "default";
  const loadedEffort = stringSetting(effectiveStartup.reasoning_effort) ?? "default";
  const effectiveEffort = requestEffort === "default" ? loadedEffort : requestEffort;
  const thinking = thinkingControl(effectiveEffort, selectedDeployment, selectedProfile, fetchedThinkingOptions);
  const unavailableProfile = selectedProfileId && selectedProfileId !== "!none" && !selectedProfile;
  const rawThinkingMode = stringSetting(perRequestOverrides.reasoning) ?? stringSetting(basePerRequest.reasoning) ?? "auto";
  const thinkingMode = rawThinkingMode === "auto" ? "default" : rawThinkingMode;
  const supportedThinkingMode = fetchedThinkingOptions.modes.some(option => option.value === thinkingMode);
  const effortMismatch = !fetchedThinkingOptions.loading && unsupportedEffort(effectiveEffort, fetchedThinkingOptions);
  const loadedEffortMismatch = !fetchedThinkingOptions.loading && unsupportedEffort(loadedEffort, fetchedThinkingOptions);
  const modeMismatch = !fetchedThinkingOptions.loading && thinkingMode !== "default" && (
    fetchedThinkingOptions.modeSupported === false || (fetchedThinkingOptions.modes.length > 0 && !supportedThinkingMode)
  );
  const needsLoadedFix = effortMismatch && loadedEffortMismatch;
  const canResetThinking = (effortMismatch && !loadedEffortMismatch) || modeMismatch;

  return (
    <details className="chat-model-controls">
      <summary className="chat-model-controls-trigger" aria-label={`Chat model settings: ${modelName}`}>
        <span className="chat-model-controls-icon" aria-hidden="true">
          <Icon name="models" size={16} />
        </span>
        <span className="chat-model-controls-main">
          <span className="chat-model-controls-model">{modelName}</span>
          {!effortMismatch && !modeMismatch && thinking.supported ? <span className="thinking-chip">{thinking.label === "Model default" ? "Default" : thinking.label}</span> : !effortMismatch && supportedThinkingMode && thinkingMode !== "default" ? <span className="thinking-chip">Thinking {thinkingMode}</span> : null}
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
              <option value="">Saved setup</option>
              <option value="!none">No preset</option>
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
            <dt>Loaded thinking budget</dt>
            <dd>{reasoning.budgetLabel}</dd>
          </div>
          <div>
            <dt>Endpoint</dt>
            <dd>{selectedDeployment?.scope === "managed" ? "Local managed model" : selectedDeployment?.endpoint ?? "Not selected"}</dd>
          </div>
        </dl>

        {fetchedThinkingOptions.modes.length ? <label>
          <span>Thinking <HoverHelp title="About thinking">Applies to your next message. Active and queued messages keep their settings.</HoverHelp></span>
          <select aria-label="Thinking mode for this message" value={supportedThinkingMode ? thinkingMode : "default"} disabled={disabled} onChange={event => onPerRequestOverridesChange(updateOverride(perRequestOverrides, "reasoning", event.target.value === "default" ? "auto" : event.target.value))}>
            {fetchedThinkingOptions.modes.map(mode => <option key={mode.value} value={mode.value}>{mode.label}</option>)}
          </select>
        </label> : null}
        {thinking.supported || fetchedThinkingOptions.loading ? (
        <div className="chat-model-controls-thinking" aria-label="Saved thinking setup">
          <div className="chat-model-controls-thinking-head">
            <span>Thinking effort<HoverHelp title="About thinking effort">These levels come from this model's template. Applies to the next message, without changing active or queued work.</HoverHelp></span>
            <strong>{effortMismatch ? "Unsupported setting" : thinking.label}</strong>
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
              onPerRequestOverridesChange(updateOverride(perRequestOverrides, "reasoning_effort", next || "default"));
            }}
          />
          <div className="chat-model-controls-efforts" aria-hidden="true">
            {thinking.options.length > 0
              ? thinking.options.map((item) => <span key={item.value}>{item.label}</span>)
              : <span>{fetchedThinkingOptions.loading ? "Loading" : "Unavailable"}</span>}
          </div>
        </div>
        ) : null}
        {canResetThinking ? <div className="chat-model-controls-note">
          <span>Thinking settings don't match this model <HoverHelp title="Thinking settings mismatch">A saved preset or message setting uses thinking options this model doesn't support. Use the model default for this message; other settings stay unchanged.</HoverHelp></span>
          <button type="button" className="ghost" aria-label="Use model default thinking" disabled={disabled} onClick={() => onPerRequestOverridesChange({
            ...perRequestOverrides,
            ...(effortMismatch && !loadedEffortMismatch ? { reasoning_effort: "default" } : {}),
            ...(modeMismatch ? { reasoning: "auto" } : {}),
          })}>Use model default</button>
        </div> : null}
        {needsLoadedFix ? <span className="chat-model-controls-note">Loaded thinking needs attention <HoverHelp title="Loaded thinking mismatch">The loaded model has an unsupported thinking effort. Choose a supported level here, or open Models, change its load settings, and reload it. A message reset cannot change loaded settings.</HoverHelp></span> : null}
        {!thinking.supported && !fetchedThinkingOptions.loading && !fetchedThinkingOptions.modes.length ? <span className="chat-model-controls-note">Model-controlled thinking <HoverHelp title="Thinking availability">{thinking.reason}</HoverHelp></span> : null}
        <span className="chat-model-controls-note">Next message settings <HoverHelp title="About saved setups">Saved response settings and instructions apply together. No preset skips both. Loaded model settings stay unchanged.</HoverHelp></span>
      </div>
    </details>
  );
}

export function useThinkingEffortOptions(deployment: Deployment | null, providedOptions: ThinkingEffortOption[] = []): ThinkingEffortOptionsState {
  const [fetched, setFetched] = useState<ThinkingEffortOption[]>([]);
  const [modes, setModes] = useState<ThinkingEffortOption[]>([]);
  const [capabilities, setCapabilities] = useState<Pick<ThinkingEffortOptionsState, "effortSupported" | "modeSupported" | "acceptedEfforts">>({});
  const [loading, setLoading] = useState(false);
  const bundleId = deployment?.bundle_id ?? "";
  const deploymentId = deployment?.id ?? "";
  const provided = useMemo(() => normalizeEffortOptions(providedOptions), [providedOptions]);

  useEffect(() => {
    setCapabilities({});
    if (provided.length > 0) {
      setFetched([]);
      setModes([]);
      setLoading(false);
      return;
    }
    if (!bundleId) {
      setFetched([]);
      setModes([]);
      setLoading(false);
      return;
    }
    let cancelled = false;
    setFetched([]);
    setModes([]);
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
        const modeDescriptor = (report as ConfigurationOptionsWithPerRequest).per_request_defaults?.reasoning;
        const modeOptions = modeDescriptor?.options ?? [];
        setModes(normalizeEffortOptions(modeOptions.flatMap(option => typeof option.value === "string" ? [{ value: option.value === "auto" ? "default" : option.value, label: option.label }] : [])));
        setCapabilities({ effortSupported: descriptor?.supported, modeSupported: modeDescriptor?.supported, acceptedEfforts: descriptor?.accepted_values });
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

  return { ...capabilities, options: provided.length > 0 ? provided : fetched, modes, loading: provided.length > 0 ? false : loading };
}

function unsupportedEffort(value: string, capabilities: ThinkingEffortOptionsState): boolean {
  return value !== "default" && (capabilities.effortSupported === false || (
    Array.isArray(capabilities.acceptedEfforts) && !capabilities.acceptedEfforts.includes(value)
  ));
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
  value: string,
  deployment: Deployment | null,
  profile: RunProfile | null,
  capabilities: ThinkingEffortOptionsState,
): { supported: boolean; label: string; index: number; options: ThinkingEffortOption[]; reason: string } {
  const loadingOptions = capabilities.loading;
  const unsupported = [
    ...(profile?.bags.per_request.unsupported ?? []),
    ...(deployment?.settings?.per_request?.unsupported ?? []),
    ...(profile?.bags.per_request.retired.map((item) => item.key) ?? []),
    ...(deployment?.settings?.per_request?.retired.map((item) => item.key) ?? []),
  ];
  const normalizedOptions = normalizeEffortOptions(capabilities.options);
  if (capabilities.acceptedEfforts?.includes(value) && !normalizedOptions.some(option => option.value === value)) {
    normalizedOptions.push({ value, label: effortLabel(value, normalizedOptions) });
  }
  const hasReportedOptions = normalizedOptions.length > 0;
  const supported = !loadingOptions && hasReportedOptions && !unsupported.includes("reasoning_effort");
  const normalized = normalizedOptions.some((option) => option.value === value) ? value : normalizedOptions[0]?.value ?? "";
  return {
    supported,
    label: loadingOptions ? "Loading options" : supported ? effortLabel(value, normalizedOptions) : "Unavailable",
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
  return options.find((option) => option.value === value)?.label ?? `${value.slice(0, 1).toUpperCase()}${value.slice(1)}`;
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
