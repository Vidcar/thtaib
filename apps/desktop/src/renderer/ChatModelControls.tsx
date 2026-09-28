import { useEffect, useRef, useState } from "react";
import { api } from "./api";
import { Icon } from "./Icon";
import { MenuPopover } from "./MenuPopover";
import { Notice } from "./Notice";
import { HoverHelp } from "./HoverHelp";
import { errorMessage } from "./errors";
import { defaultSettingDisplay, useSetupPreview } from "./effectiveSettings";
import { workspaceApi } from "./workspaceApi";
import type { BundleConfigurationOptions, Deployment, ModelBundle, RunProfile } from "./types";
import type { SetupConfiguration } from "./workspaceApi";
import "./ChatModelControls.css";

const thinkingFields = new Set(["reasoning", "reasoning_effort"]);
type ModelOverride = { model_configuration_id?: string | null; startup_overrides?: Record<string, unknown> | null; per_request_overrides?: Record<string, unknown> | null };
function thinkingSettings(configuration: SetupConfiguration): Record<string, unknown> {
  return Object.fromEntries(Object.entries(configuration.per_request_overrides ?? {}).filter(([key]) => thinkingFields.has(key)));
}
function remembered(configuration: SetupConfiguration): Record<string, ModelOverride> {
  return (configuration as SetupConfiguration & { model_overrides?: Record<string, ModelOverride> }).model_overrides ?? {};
}
export function chatTuningCandidate(configuration: SetupConfiguration, thinking: Record<string, unknown>, context: number | null): SetupConfiguration {
  const startup = { ...(configuration.startup_overrides ?? {}) };
  if (context === null) delete startup.ctx_size; else startup.ctx_size = context;
  const requests = Object.fromEntries(Object.entries(configuration.per_request_overrides ?? {}).filter(([key]) => !thinkingFields.has(key)));
  return { ...configuration, startup_overrides: startup, per_request_overrides: { ...requests, ...thinking } };
}
function modelDescription(bundle?: ModelBundle): string {
  if (!bundle) return "";
  const filename = bundle.primary_path?.split(/[\\/]/).at(-1) ?? bundle.files?.find(file => file.role === "primary_weights")?.path.split(/[\\/]/).at(-1) ?? "";
  const variant = /low[-_]mtp/i.test(filename) ? "LOW-MTP" : /(?:^|[-_.])mtp(?:[-_.]|$)/i.test(filename) ? "MTP" : "";
  return [bundle.quantization, variant, filename].filter(Boolean).join(" · ");
}
function modelChoiceConfiguration(configuration: SetupConfiguration, profile: RunProfile | null, connected: Deployment | null): SetupConfiguration {
  const key = profile?.bundle_id ?? connected?.id ?? "";
  const sameChoice = profile ? profile.id === (configuration.model_configuration_id ?? configuration.profile_id) : connected?.id === configuration.deployment_id;
  const saved = sameChoice ? { startup_overrides: configuration.startup_overrides, per_request_overrides: configuration.per_request_overrides } : remembered(configuration)[key];
  const modelOverrides: Record<string, ModelOverride> = key ? { ...remembered(configuration), [key]: { ...saved, model_configuration_id: profile?.id ?? null } } : remembered(configuration);
  return { ...configuration, model_configuration_id: profile?.id ?? null, deployment_id: connected?.id ?? null,
    profile_id: null, bundle_id: null, inherit_deployment_settings: null,
    model_overrides: modelOverrides,
    startup_overrides: saved?.startup_overrides ?? {}, per_request_overrides: saved?.per_request_overrides ?? {} };
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
  fixedModel?: boolean;
  onManageAgent?: () => void;
  openRequest?: number;
  onApply: (configuration: SetupConfiguration) => void | Promise<void>;
  onReloaded: () => Promise<void>;
}

export function ChatModelControls({ bundles, deployments, profiles, selectedDeploymentId, selectedConfigurationId, configuration, projectId = null, agentSetupVersionId = null, conversationId = null, disabled = false, runtimeBusy = false, fixedModel = false, onManageAgent, openRequest, onApply, onReloaded }: ChatModelControlsProps) {
  const [fallbackBundles, setFallbackBundles] = useState<ModelBundle[]>([]);
  const [pickerOpen, setPickerOpen] = useState(false);
  const [tuningOpen, setTuningOpen] = useState(false);
  const [search, setSearch] = useState("");
  const [expanded, setExpanded] = useState<string | null>(null);
  const [highlighted, setHighlighted] = useState(0);
  const choicesRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (bundles || !pickerOpen) return;
    let cancelled = false;
    void api.bundles().then(items => { if (!cancelled) setFallbackBundles(items); }).catch(() => {});
    return () => { cancelled = true; };
  }, [bundles, pickerOpen]);
  const availableBundles = bundles ?? fallbackBundles;
  const [thinking, setThinking] = useState(() => thinkingSettings(configuration));
  const [context, setContext] = useState<number | null>(() => typeof configuration.startup_overrides?.ctx_size === "number" ? configuration.startup_overrides.ctx_size : null);
  const [busy, setBusy] = useState(false);
  const [loadingChoice, setLoadingChoice] = useState("");
  const [error, setError] = useState("");
  const pending = useRef(false);
  const ownerKey = [conversationId, projectId, agentSetupVersionId, configuration.model_configuration_id ?? selectedConfigurationId].join(":");
  const owner = useRef({ key: ownerKey, generation: 0 });
  if (owner.current.key !== ownerKey) owner.current = { key: ownerKey, generation: owner.current.generation + 1 };
  const currentGeneration = owner.current.generation;
  const latest = useRef({ configuration, onApply, onReloaded, runtimeBusy });
  latest.current = { configuration, onApply, onReloaded, runtimeBusy };
  const incomingThinking = JSON.stringify(thinkingSettings(configuration));
  const incomingContext = typeof configuration.startup_overrides?.ctx_size === "number" ? configuration.startup_overrides.ctx_size : null;
  useEffect(() => { setThinking(JSON.parse(incomingThinking) as Record<string, unknown>); setContext(incomingContext); setError(""); }, [incomingThinking, incomingContext, conversationId, selectedConfigurationId]);

  const selectedProfile = profiles.find(item => item.id === (configuration.model_configuration_id ?? selectedConfigurationId));
  const selectedDeployment = deployments.find(item => item.id === selectedDeploymentId);
  const selectedBundleId = selectedProfile?.bundle_id ?? selectedDeployment?.bundle_id;
  const selectedBundle = availableBundles.find(item => item.id === selectedBundleId);
  const selectedName = selectedBundle?.display_name ?? selectedDeployment?.display_name.replace(/^(managed|connected):/, "") ?? "Choose model";
  const runtimeRevision = JSON.stringify(deployments.map(item => [item.id, item.profile_id, item.status, item.health?.healthy, item.settings?.startup?.requested]));
  const residency = useSetupPreview(configuration, projectId, agentSetupVersionId, "conversation", runtimeRevision, Boolean(selectedProfile || selectedDeployment));
  function observed(profile: RunProfile | null, connected: Deployment | null) {
    const selected = profile ? profile.id === selectedProfile?.id : connected?.id === selectedDeployment?.id;
    const candidates = deployments.filter(item => profile && item.profile_id === profile.id && item.bundle_id === profile.bundle_id);
    const exact = selected && !residency.loading && !residency.error ? deployments.find(item => item.id === residency.data?.configuration.deployment_id) : null;
    const deployment = exact ?? connected ?? candidates.find(item => item.status === "running" && item.health?.healthy) ?? candidates.find(item => item.status === "starting") ?? candidates.find(item => item.status === "failed" || item.status === "unhealthy");
    if (loadingChoice && loadingChoice === (profile?.id ?? connected?.id) || deployment?.status === "starting") return { tone: "loading", label: "Loading" };
    if (deployment?.status === "failed" || deployment?.status === "unhealthy" || deployment?.health?.healthy === false) return { tone: "attention", label: "Needs attention" };
    if (selected && residency.loading) return { tone: "idle", label: "Checking model settings" };
    if (selected && residency.error) return { tone: "attention", label: "Readiness not verified" };
    if (exact?.status === "running" && exact.health?.healthy) return { tone: "ready", label: "Ready" };
    if (deployment?.status === "running" && deployment.health?.healthy) return { tone: "idle", label: selected ? "Settings not loaded" : "Loaded" };
    return { tone: "idle", label: "Idle" };
  }
  const selectedState = observed(selectedProfile ?? null, selectedDeployment?.scope === "connected" ? selectedDeployment : null);
  const previewConfiguration = chatTuningCandidate(configuration, thinking, context);
  const preview = useSetupPreview(previewConfiguration, projectId, agentSetupVersionId, "conversation", "", tuningOpen);
  const facts = preview.data?.effective_values ?? {};
  const optionKey = [selectedBundleId, selectedDeployment?.id].join(":");
  const [optionsResult, setOptionsResult] = useState<{ key: string; data: BundleConfigurationOptions } | null>(null);
  useEffect(() => {
    if (!tuningOpen || (!selectedBundleId && !selectedDeployment?.id)) return;
    let cancelled = false;
    const request = selectedBundleId ? api.modelConfiguration(selectedBundleId, selectedDeployment?.id)
      : api.deploymentConfiguration(selectedDeployment!.id);
    void request.then(data => { if (!cancelled) setOptionsResult({ key: optionKey, data }); }).catch(failure => { if (!cancelled) setError(errorMessage(failure)); });
    return () => { cancelled = true; };
  }, [tuningOpen, optionKey, selectedBundleId, selectedDeployment?.id]);
  const options = optionsResult?.key === optionKey ? optionsResult.data : null;
  function preferredConfiguration(bundle: ModelBundle): RunProfile | undefined {
    return profiles.find(item => item.bundle_id === bundle.id && item.id === selectedProfile?.id)
      ?? profiles.find(item => item.bundle_id === bundle.id && item.id === remembered(configuration)[bundle.id]?.model_configuration_id)
      ?? profiles.find(item => item.id === bundle.default_configuration_id)
      ?? profiles.find(item => item.bundle_id === bundle.id);
  }
  const connectedChoices = deployments.filter(item => item.scope === "connected");
  const compatibilityContext = JSON.stringify([conversationId, projectId, agentSetupVersionId, configuration]);
  const [incompatibleResult, setIncompatibleResult] = useState<{ context: string; reasons: Record<string, string> }>({ context: "", reasons: {} });
  const incompatibleChoices = incompatibleResult.context === compatibilityContext ? incompatibleResult.reasons : {};

  async function applyChoice(profile: RunProfile | null, connected: Deployment | null, close: () => void) {
    if (pending.current || fixedModel) return;
    const choiceKey = profile?.id ?? connected?.id ?? "";
    if (incompatibleChoices[choiceKey]) { setError(incompatibleChoices[choiceKey]); return; }
    const exactHealthyChoice = profile
      ? selectedProfile?.id === profile.id && selectedDeployment?.id === residency.data?.configuration.deployment_id && selectedState.tone === "ready"
      : connected?.id === selectedDeployment?.id && selectedState.tone === "ready";
    if (exactHealthyChoice) { close(); return; }
    pending.current = true;
    setBusy(true); setLoadingChoice(latest.current.runtimeBusy ? "" : choiceKey); setError("");
    let loadAttempted = false;
    const candidate = modelChoiceConfiguration(latest.current.configuration, profile, connected);
    try {
      if (conversationId) {
        const readiness = await workspaceApi.chatReadiness(conversationId, candidate, agentSetupVersionId)
          .catch(failure => { throw new Error("Compatibility unknown. " + errorMessage(failure) + " Try again."); });
        if (readiness.status === "incompatible") {
          const reason = readiness.issues[0]?.message ?? "This model cannot continue this chat.";
          setIncompatibleResult(current => ({ context: compatibilityContext, reasons: { ...(current.context === compatibilityContext ? current.reasons : {}), [choiceKey]: reason } }));
          throw new Error(reason);
        }
      }
      if (owner.current.generation !== currentGeneration) return;
      const resolved = await workspaceApi.resolveSetup(projectId, agentSetupVersionId, candidate);
      if (owner.current.generation !== currentGeneration) return;
      const exactDeployment = deployments.find(item => item.id === resolved.configuration.deployment_id);
      loadAttempted = Boolean(profile?.bundle_id) && !latest.current.runtimeBusy && !(exactDeployment?.status === "running" && exactDeployment.health?.healthy);
      const loaded = loadAttempted ? await api.startManaged(profile!.bundle_id!, profile!.id, candidate.startup_overrides ?? {}) : null;
      if (loaded && (!loaded.health?.healthy || loaded.status !== "running")) throw new Error(loaded.error ?? "Model did not become ready.");
      if (owner.current.generation !== currentGeneration) return;
      await latest.current.onApply({ ...candidate, deployment_id: loaded?.id ?? connected?.id ?? (latest.current.runtimeBusy ? null : exactDeployment?.id ?? null) });
      if (loadAttempted) await latest.current.onReloaded();
      if (owner.current.generation === currentGeneration) close();
    } catch (failure) {
      if (owner.current.generation === currentGeneration && loadAttempted) {
        await Promise.resolve(latest.current.onApply(candidate)).catch(() => {});
      }
      if (owner.current.generation === currentGeneration) setError((loadAttempted ? (profile?.display_name ?? connected?.display_name ?? "Model") + " · " : "") + errorMessage(failure));
      if (loadAttempted) await latest.current.onReloaded().catch(() => {});
    } finally { pending.current = false; setBusy(false); setLoadingChoice(""); }
  }

  async function applyTuning(close: () => void) {
    if (pending.current || preview.loading || preview.error || !preview.data || (context !== null && (!Number.isInteger(context) || context < 1))) return;
    pending.current = true; setBusy(true); setError("");
    let attempted: SetupConfiguration | null = null;
    try {
      const current = latest.current.configuration;
      const next = chatTuningCandidate(current, thinking, context);
      const startup = next.startup_overrides ?? {};
      attempted = next;
      const key = selectedBundleId ?? selectedDeployment?.id;
      if (key) Object.assign(next, { model_overrides: { ...remembered(current), [key]: { model_configuration_id: selectedProfile?.id ?? null, startup_overrides: startup, per_request_overrides: next.per_request_overrides } } });
      if (incomingContext !== context && !latest.current.runtimeBusy && selectedProfile?.bundle_id) {
        const loaded = await api.startManaged(selectedProfile.bundle_id, selectedProfile.id, startup);
        if (!loaded.health?.healthy || loaded.status !== "running") throw new Error(loaded.error ?? "Model did not become ready.");
        next.deployment_id = loaded.id;
        if (owner.current.generation !== currentGeneration) return;
        await latest.current.onReloaded();
      }
      if (owner.current.generation !== currentGeneration) return;
      await latest.current.onApply(next);
      close();
    } catch (failure) {
      if (owner.current.generation === currentGeneration && attempted) await Promise.resolve(latest.current.onApply(attempted)).catch(() => {});
      if (owner.current.generation === currentGeneration) setError(errorMessage(failure));
      await latest.current.onReloaded().catch(() => {});
    }
    finally { pending.current = false; setBusy(false); }
  }

  function choiceRow(profile: RunProfile | null, connected: Deployment | null, label: string, close: () => void, className = "chat-model-choice", description = "") {
    const key = profile?.id ?? connected?.id ?? label;
    const state = observed(profile, connected);
    const reason = incompatibleChoices[key];
    const index = visibleKeys.indexOf(className.includes("chat-model-variant") ? `${key}:variant` : key);
    return <button id={`chat-model-option-${index}`} type="button" role="option" aria-selected={profile ? selectedProfile?.id === profile.id : connected?.id === selectedDeploymentId} data-highlighted={index === highlighted} className={className} key={key} disabled={busy || fixedModel || Boolean(reason) || (!profile && !connected)} aria-pressed={profile ? selectedProfile?.id === profile.id : connected?.id === selectedDeploymentId} title={[label, description, reason || state.label].filter(Boolean).join(" · ")} onPointerMove={() => setHighlighted(index)} onClick={() => void applyChoice(profile, connected, close)}><span className="chat-model-choice-name"><strong>{label}</strong>{description ? <small>{description}</small> : null}</span><span className={"model-state-dot is-" + (reason ? "attention" : state.tone)} aria-label={reason || state.label} /></button>;
  }
  const baseContext = facts["startup.ctx_size"]?.inherited_value;
  const contextSupported = Boolean(selectedProfile?.bundle_id) && options?.context_size.supported !== false;
  const modes = options?.per_request_defaults.reasoning;
  const efforts = options?.per_request_defaults.reasoning_effort;
  const tuningChanged = JSON.stringify(thinking) !== incomingThinking || context !== incomingContext;
  const defaults = (key: string, target: "configuration" | "model" = "configuration") => defaultSettingDisplay(facts["per_request." + key], target, key);
  const contextDefault = defaultSettingDisplay(facts["startup.ctx_size"], "configuration", "ctx_size");
  const term = search.trim().toLocaleLowerCase();
  const visibleBundles = availableBundles.filter(item => (item.status === "ready" || item.disk_matches) && [item.display_name, modelDescription(item), ...profiles.filter(profile => profile.bundle_id === item.id).map(profile => profile.display_name)].join(" ").toLocaleLowerCase().includes(term));
  const visibleConnected = connectedChoices.filter(item => item.display_name.toLocaleLowerCase().includes(term));
  const visibleKeys = [...visibleBundles.flatMap(bundle => [preferredConfiguration(bundle)?.id ?? bundle.id, ...(expanded === bundle.id ? profiles.filter(profile => profile.bundle_id === bundle.id).map(profile => `${profile.id}:variant`) : [])]), ...visibleConnected.map(item => item.id)];
  const visibleKeySignature = visibleKeys.join("|");
  useEffect(() => {
    if (!pickerOpen) return;
    const selected = visibleKeys.indexOf(selectedProfile?.id ?? selectedDeployment?.id ?? "");
    setHighlighted(selected >= 0 ? selected : 0);
  }, [pickerOpen, search, expanded, visibleKeySignature]);
  useEffect(() => { choicesRef.current?.querySelector<HTMLElement>(`#chat-model-option-${highlighted}`)?.scrollIntoView?.({ block: "nearest" }); }, [highlighted, search, expanded, pickerOpen]);
  return <>
    <MenuPopover label={"Chat model: " + selectedName} className="chat-model-controls" panelClassName="chat-model-controls-panel" trigger={<><Icon name="models" size={16} /><span className="chat-model-controls-model" title={[selectedName, modelDescription(selectedBundle), selectedProfile?.display_name].filter(Boolean).join(" · ")}>{selectedName}{selectedProfile ? <small> · {selectedProfile.display_name}</small> : null}</span><span className={"model-state-dot is-" + selectedState.tone} title={selectedState.label} /><span className="sr-only chat-model-status">{selectedState.label}</span></>} disabled={disabled} openRequest={openRequest} onOpenChange={setPickerOpen}>
      {close => <>
        {fixedModel ? <div className="actions"><span>Assigned by agent</span><button type="button" onClick={onManageAgent}>Change in Agents</button></div> : null}
        <input aria-label="Search models" placeholder="Search models" value={search} aria-controls="chat-model-choices" aria-activedescendant={visibleKeys.length ? `chat-model-option-${Math.min(highlighted, visibleKeys.length - 1)}` : undefined} onChange={event => setSearch(event.target.value)} onKeyDown={event => {
          if (event.key === "ArrowDown" || event.key === "ArrowUp" || event.key === "Home" || event.key === "End") { event.preventDefault(); setHighlighted(current => event.key === "Home" ? 0 : event.key === "End" ? Math.max(0, visibleKeys.length - 1) : Math.max(0, Math.min(visibleKeys.length - 1, current + (event.key === "ArrowDown" ? 1 : -1)))); }
          else if (event.key === "Enter") { event.preventDefault(); choicesRef.current?.querySelector<HTMLButtonElement>(`#chat-model-option-${highlighted}:not(:disabled)`)?.click(); }
        }} />
        <div id="chat-model-choices" ref={choicesRef} className="chat-model-choice-list" role="listbox" aria-label="Installed models" onKeyDown={event => {
          if (event.key !== "ArrowDown" && event.key !== "ArrowUp") return;
          event.preventDefault(); const next = Math.max(0, Math.min(visibleKeys.length - 1, highlighted + (event.key === "ArrowDown" ? 1 : -1))); setHighlighted(next); choicesRef.current?.querySelector<HTMLButtonElement>(`#chat-model-option-${next}:not(:disabled)`)?.focus();
        }}>
          {visibleBundles.map(bundle => {
            const profile = preferredConfiguration(bundle);
            const variants = profiles.filter(item => item.bundle_id === bundle.id);
            return <div key={bundle.id} className="chat-model-row"><div className="chat-model-primary">{choiceRow(profile ?? null, null, bundle.display_name, close, "chat-model-choice", [modelDescription(bundle), profile?.display_name].filter(Boolean).join(" · "))}{variants.length > 1 ? <button type="button" className="icon-button" aria-label={"Configurations for " + bundle.display_name} aria-expanded={expanded === bundle.id} title="Configurations" onClick={() => setExpanded(value => value === bundle.id ? null : bundle.id)}>{expanded === bundle.id ? "▾" : "▸"}</button> : null}</div>{expanded === bundle.id ? <div className="chat-model-variants">{variants.map(item => choiceRow(item, null, item.display_name, close, "chat-model-choice chat-model-variant", modelDescription(bundle)))}</div> : null}</div>;
          })}
          {visibleConnected.map(item => choiceRow(null, item, item.display_name.replace(/^connected:/, ""), close, "chat-model-choice", "Connected server"))}
          {!visibleKeys.length && (availableBundles.length || connectedChoices.length) ? <p className="hint">No models match this search.</p> : null}
          {!availableBundles.length && !deployments.length ? <p className="hint">Add a model in Models.</p> : null}
        </div>
        {error ? <Notice tone="error">{error}</Notice> : null}
      </>}
    </MenuPopover>
    <MenuPopover label="Tune model" trigger={<Icon name="tune" size={16} />} className="chat-tuning" panelClassName="chat-model-controls-panel chat-tuning-panel" disabled={disabled || (!selectedProfile && !selectedDeployment)} onOpenChange={setTuningOpen}>
      {close => <>
        {modes?.supported ? <label>Thinking<select aria-label="Thinking" disabled={busy} title={thinking.reasoning == null ? defaults("reasoning").title : undefined} value={String(thinking.reasoning ?? "")} onChange={event => { const next = { ...thinking }; if (event.target.value) next.reasoning = event.target.value; else delete next.reasoning; setThinking(next); }}><option value="">{defaults("reasoning").value} · {defaults("reasoning").source}</option>{(modes.options?.length ? modes.options : [{ value: "on", label: "On" }, { value: "off", label: "Off" }]).map(item => <option key={String(item.value)} value={String(item.value)}>{item.value === "auto" ? defaults("reasoning", "model").value + " · " + defaults("reasoning", "model").source : item.label}</option>)}</select><small>{thinking.reasoning == null ? defaults("reasoning").source : "This chat"}</small></label> : options ? <span className="hint">Thinking {modes?.supported === false ? "unavailable" : "unverified"}</span> : null}
        {efforts?.supported ? <label>Effort<select aria-label="Thinking level" disabled={busy || thinking.reasoning === "off"} title={thinking.reasoning_effort == null ? defaults("reasoning_effort").title : undefined} value={String(thinking.reasoning_effort ?? "")} onChange={event => { const next = { ...thinking }; if (event.target.value) next.reasoning_effort = event.target.value; else delete next.reasoning_effort; setThinking(next); }}><option value="">{defaults("reasoning_effort").value} · {defaults("reasoning_effort").source}</option>{efforts.options.map(item => <option key={String(item.value)} value={String(item.value)}>{item.value === "default" ? defaults("reasoning_effort", "model").value + " · " + defaults("reasoning_effort", "model").source : item.label}</option>)}</select><small>{thinking.reasoning_effort == null ? defaults("reasoning_effort").source : "This chat"}</small></label> : null}
        <label>Context <HoverHelp title="Context">Changing an owned model's context reloads it when safe. Queued inputs keep their saved settings. Clear the value to follow its configuration.</HoverHelp><input aria-label="Chat context" type="number" min={1} max={options?.context_size.maximum ?? undefined} step={1} value={context ?? ""} placeholder={typeof baseContext === "number" ? String(baseContext) : contextDefault.value} title={context === null ? contextDefault.title : undefined} disabled={busy || !contextSupported} onChange={event => setContext(event.target.value ? Number(event.target.value) : null)} /><small>{context === null ? contextDefault.source : "This chat"}{preview.loading ? " · Checking…" : ""}</small></label>
        {!contextSupported ? <span className="hint">{selectedDeployment?.scope === "connected" ? "Context is managed by this connection." : "Context control unavailable."}</span> : null}
        {error || preview.error ? <Notice tone="error">{error || preview.error}</Notice> : null}
        <div className="actions chat-model-controls-actions"><button type="button" className="primary-button" disabled={!tuningChanged || busy || preview.loading || !preview.data || Boolean(preview.error) || (context !== null && (!Number.isInteger(context) || context < 1))} onClick={() => void applyTuning(close)}>{busy ? "Applying…" : "Apply"}</button></div>
      </>}
    </MenuPopover>
  </>;
}
