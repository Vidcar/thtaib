import { useEffect, useRef, useState } from "react";
import { api } from "./api";
import { Icon } from "./Icon";
import { MenuPopover } from "./MenuPopover";
import { Notice } from "./Notice";
import { ResponseSettingsEditor } from "./ResponseSettingsEditor";
import { errorMessage } from "./errors";
import { useSetupPreview } from "./effectiveSettings";
import { workspaceApi } from "./workspaceApi";
import type { BundleConfigurationOptions, Deployment, ModelBundle, RunProfile } from "./types";
import type { SetupConfiguration } from "./workspaceApi";
import "./ChatModelControls.css";

const thinkingFields = new Set(["reasoning", "reasoning_effort", "reasoning_format"]);
function thinkingSettings(configuration: SetupConfiguration): Record<string, unknown> {
  return Object.fromEntries(Object.entries(configuration.per_request_overrides ?? {}).filter(([key]) => thinkingFields.has(key)));
}
function modelChoiceConfiguration(configuration: SetupConfiguration, profile: RunProfile | null, connected: Deployment | null): SetupConfiguration {
  return { ...configuration, model_configuration_id: profile?.id ?? null, deployment_id: connected?.id ?? null,
    profile_id: null, bundle_id: null, inherit_deployment_settings: null, startup_overrides: {}, per_request_overrides: {} };
}

export interface ChatModelControlsProps {
  bundles?: ModelBundle[];
  deployments: Deployment[];
  profiles: RunProfile[];
  selectedDeploymentId: string;
  selectedConfigurationId?: string;
  configuration: SetupConfiguration;
  projectId?: string | null;
  agentSetupVersionId?: string | null;
  conversationId?: string | null;
  disabled?: boolean;
  runtimeBusy?: boolean;
  onApply: (configuration: SetupConfiguration) => void | Promise<void>;
  onReloaded: () => Promise<void>;
}

export function ChatModelControls({ bundles, deployments, profiles, selectedDeploymentId, selectedConfigurationId, configuration, projectId = null, agentSetupVersionId = null, conversationId = null, disabled = false, onApply, onReloaded }: ChatModelControlsProps) {
  const [fallbackBundles, setFallbackBundles] = useState<ModelBundle[]>([]);
  useEffect(() => {
    if (bundles) return;
    let cancelled = false;
    void api.bundles().then(items => { if (!cancelled) setFallbackBundles(items); }).catch(() => {});
    return () => { cancelled = true; };
  }, [bundles]);
  const availableBundles = bundles ?? fallbackBundles;
  const [thinking, setThinking] = useState(() => thinkingSettings(configuration));
  const [busy, setBusy] = useState(false);
  const [loadingChoice, setLoadingChoice] = useState("");
  const [error, setError] = useState("");
  const pending = useRef(false);
  const owner = useRef({ key: `${conversationId}:${projectId}:${agentSetupVersionId}`, generation: 0 });
  const ownerKey = `${conversationId}:${projectId}:${agentSetupVersionId}`;
  if (owner.current.key !== ownerKey) owner.current = { key: ownerKey, generation: owner.current.generation + 1 };
  const currentGeneration = owner.current.generation;
  const latest = useRef({ configuration, onApply, onReloaded });
  latest.current = { configuration, onApply, onReloaded };
  const incomingThinking = JSON.stringify(thinkingSettings(configuration));
  useEffect(() => { setThinking(JSON.parse(incomingThinking) as Record<string, unknown>); setError(""); }, [incomingThinking, conversationId]);

  const selectedProfile = profiles.find(item => item.id === (configuration.model_configuration_id ?? selectedConfigurationId));
  const selectedDeployment = deployments.find(item => item.id === selectedDeploymentId);
  const selectedBundleId = selectedProfile?.bundle_id ?? selectedDeployment?.bundle_id;
  const selectedBundle = availableBundles.find(item => item.id === selectedBundleId);
  const selectedName = selectedBundle?.display_name ?? selectedDeployment?.display_name.replace(/^(managed|connected):/, "") ?? "Choose model";
  const exactBinding = !selectedProfile || selectedDeployment?.profile_id === selectedProfile.id;
  const selectedLoaded = exactBinding && selectedDeployment?.status === "running" && selectedDeployment.health?.healthy;
  const selectedState = loadingChoice ? "Loading…"
    : !exactBinding ? "Choose configuration"
      : selectedDeployment?.status === "failed" ? "Needs attention"
        : selectedDeployment?.status === "unhealthy" || selectedDeployment?.health?.healthy === false ? "Unhealthy"
          : selectedDeployment?.status === "starting" ? "Loading…"
            : selectedLoaded ? "Loaded" : selectedBundleId ? "Loads on Send" : selectedDeployment?.status ?? "";
  const variants = profiles.filter(item => item.bundle_id === selectedBundleId);
  const preview = useSetupPreview({ ...configuration, per_request_overrides: { ...(configuration.per_request_overrides ?? {}), ...thinking } }, projectId, agentSetupVersionId);
  const facts = preview.data?.effective_values ?? {};
  const optionKey = `${selectedBundleId ?? ""}:${selectedDeployment?.id ?? ""}`;
  const [optionsResult, setOptionsResult] = useState<{ key: string; data: BundleConfigurationOptions } | null>(null);
  useEffect(() => {
    if (!selectedBundleId) return;
    let cancelled = false;
    void api.modelConfiguration(selectedBundleId, selectedDeployment?.id).then(data => {
      if (!cancelled) setOptionsResult({ key: optionKey, data });
    }).catch(failure => { if (!cancelled) setError(errorMessage(failure)); });
    return () => { cancelled = true; };
  }, [optionKey, selectedBundleId, selectedDeployment?.id]);
  const options = optionsResult?.key === optionKey ? optionsResult.data : null;

  function preferredConfiguration(bundle: ModelBundle): RunProfile | undefined {
    return profiles.find(item => item.id === bundle.default_configuration_id)
      ?? profiles.find(item => item.bundle_id === bundle.id && item.id === selectedProfile?.id)
      ?? profiles.find(item => item.bundle_id === bundle.id);
  }

  const connectedChoices = deployments.filter(item => item.scope === "connected");
  const compatibilityChoices = [
    ...profiles.filter(item => availableBundles.some(bundle => bundle.id === item.bundle_id && bundle.disk_matches)).map(item => ({ key: item.id, profile: item, connected: null })),
    ...connectedChoices.map(item => ({ key: item.id, profile: null, connected: item })),
  ];
  const compatibilityKey = JSON.stringify([conversationId, agentSetupVersionId, configuration, compatibilityChoices.map(item => item.key)]);
  const [incompatibleChoices, setIncompatibleChoices] = useState<Record<string, string>>({});
  useEffect(() => {
    if (!conversationId) { setIncompatibleChoices({}); return; }
    let cancelled = false;
    void Promise.all(compatibilityChoices.map(async item => {
      try {
        const readiness = await workspaceApi.chatReadiness(conversationId, modelChoiceConfiguration(configuration, item.profile, item.connected), agentSetupVersionId);
        return [item.key, readiness.status === "incompatible" ? readiness.issues[0]?.message ?? "This model cannot continue this chat." : ""] as const;
      } catch { return [item.key, ""] as const; }
    })).then(items => { if (!cancelled) setIncompatibleChoices(Object.fromEntries(items)); });
    return () => { cancelled = true; };
  }, [compatibilityKey]);

  async function applyChoice(profile: RunProfile | null, connected: Deployment | null, close: () => void) {
    if (pending.current) return;
    pending.current = true;
    setBusy(true); setLoadingChoice(profile?.id ?? connected?.id ?? ""); setError("");
    try {
      const candidate = modelChoiceConfiguration(latest.current.configuration, profile, connected);
      if (conversationId) {
        const readiness = await workspaceApi.chatReadiness(conversationId, candidate, agentSetupVersionId);
        if (readiness.status === "incompatible") throw new Error(readiness.issues[0]?.message ?? "This model cannot continue this chat.");
      }
      const loaded = profile?.bundle_id ? await api.startManaged(profile.bundle_id, profile.id, {}) : null;
      if (loaded && (!loaded.health?.healthy || loaded.status !== "running")) throw new Error(loaded.error ?? "Model did not become ready.");
      if (owner.current.generation !== currentGeneration) return;
      const currentChoice = modelChoiceConfiguration(latest.current.configuration, profile, connected);
      await latest.current.onApply({ ...currentChoice, deployment_id: loaded?.id ?? connected?.id ?? null });
      await latest.current.onReloaded();
      if (owner.current.generation === currentGeneration) close();
    } catch (failure) {
      if (owner.current.generation === currentGeneration) setError(errorMessage(failure));
      await latest.current.onReloaded().catch(() => {});
    } finally {
      pending.current = false; setBusy(false); setLoadingChoice("");
    }
  }

  async function applyThinking(close: () => void) {
    if (pending.current) return;
    pending.current = true; setBusy(true); setError("");
    try {
      const existing = latest.current.configuration.per_request_overrides ?? {};
      const next = Object.fromEntries(Object.entries(existing).filter(([key]) => !thinkingFields.has(key)));
      await latest.current.onApply({ ...latest.current.configuration, per_request_overrides: { ...next, ...thinking } });
      if (owner.current.generation === currentGeneration) close();
    } catch (failure) {
      if (owner.current.generation === currentGeneration) setError(errorMessage(failure));
    } finally { pending.current = false; setBusy(false); }
  }

  return <MenuPopover label={`Chat model: ${selectedName}`} className="chat-model-controls" panelClassName="chat-model-controls-panel" trigger={<><Icon name="models" size={16} /><span className="chat-model-controls-model">{selectedName}</span><small className="chat-model-status">{selectedState}</small></>} disabled={disabled}>
    {close => <>
      <div className="chat-model-choice-list" role="group" aria-label="Installed models">
        {availableBundles.filter(item => item.status === "ready" || item.disk_matches).map(bundle => {
          const profile = preferredConfiguration(bundle);
          const reason = profile ? incompatibleChoices[profile.id] : "";
          return <button type="button" className="chat-model-choice" key={bundle.id} disabled={busy || !profile || !bundle.disk_matches || Boolean(reason)} aria-pressed={bundle.id === selectedBundleId} title={reason || (!profile ? "Configure this model in Models first" : !bundle.disk_matches ? "Check this model's files in Models" : bundle.display_name)} onClick={() => { if (profile) void applyChoice(profile, null, close); }}><strong>{bundle.display_name}</strong><span>{reason ? "Incompatible" : loadingChoice === profile?.id ? "Loading…" : bundle.id === selectedBundleId ? selectedState : deployments.some(item => item.bundle_id === bundle.id && item.profile_id === profile?.id && item.status === "running" && item.health?.healthy) ? "Loaded" : "Not loaded"}</span></button>;
        })}
        {connectedChoices.map(item => <button type="button" className="chat-model-choice" key={item.id} disabled={busy || Boolean(incompatibleChoices[item.id])} aria-pressed={item.id === selectedDeploymentId} title={incompatibleChoices[item.id] || undefined} onClick={() => void applyChoice(null, item, close)}><strong>{item.display_name.replace(/^connected:/, "")}</strong><span>{incompatibleChoices[item.id] ? "Incompatible" : `Connected · ${item.health?.healthy ? "Ready" : "Unavailable"}`}</span></button>)}
        {!availableBundles.length && !deployments.length ? <p className="hint">Add a model in Models to start chatting.</p> : null}
      </div>
      {selectedBundle && variants.length > 1 ? <label className="chat-variant-choice">Configuration<select aria-label="Model configuration" value={selectedProfile?.id ?? ""} disabled={busy} onChange={event => { const profile = variants.find(item => item.id === event.target.value); if (profile && !incompatibleChoices[profile.id]) void applyChoice(profile, null, close); }}><option value="" disabled>Choose configuration</option>{variants.map(item => <option key={item.id} value={item.id} disabled={Boolean(incompatibleChoices[item.id])} title={incompatibleChoices[item.id] || undefined}>{item.display_name}{item.id === selectedBundle.default_configuration_id ? " · default" : ""}{incompatibleChoices[item.id] ? " · incompatible" : ""}</option>)}</select></label> : null}
      <div className="chat-thinking-controls"><ResponseSettingsEditor value={thinking} onChange={setThinking} options={options} facts={facts} disabled={busy || preview.loading} /></div>
      {error || preview.error ? <Notice tone="error">{error || preview.error}</Notice> : null}
      {JSON.stringify(thinking) !== incomingThinking ? <div className="actions chat-model-controls-actions"><button type="button" className="primary-button" disabled={busy || preview.loading || Boolean(preview.error)} onClick={() => void applyThinking(close)}>{busy ? "Applying…" : "Apply thinking"}</button></div> : null}
    </>}
  </MenuPopover>;
}
