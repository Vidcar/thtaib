import { useEffect, useRef, useState } from "react";
import { api } from "./api";
import { Icon } from "./Icon";
import { MenuPopover } from "./MenuPopover";
import { Notice } from "./Notice";
import { SettingRow } from "./CompactControls";
import { ContextSlider, tokenLabel } from "./ModelControls";
import { ResponseSettingsEditor } from "./ResponseSettingsEditor";
import { ModelHardwareEstimate } from "./ModelHardwareEstimate";
import { mergedStartup } from "./deploymentSettings";
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
function modelFilename(bundle?: ModelBundle): string {
  return bundle?.primary_path?.split(/[\\/]/).at(-1) ?? bundle?.files?.find(file => file.role === "primary_weights")?.path.split(/[\\/]/).at(-1) ?? "";
}
function modelDescription(bundle?: ModelBundle): string {
  if (!bundle) return "";
  const filename = modelFilename(bundle);
  const variant = /low[-_]mtp/i.test(filename) ? "LOW-MTP" : /(?:^|[-_.])mtp(?:[-_.]|$)/i.test(filename) ? "MTP" : "";
  return [bundle.quantization, variant].filter(Boolean).join(" · ");
}
function modelName(bundle: ModelBundle): string {
  const repositoryName = bundle.display_name === bundle.source?.repo_id;
  if (!repositoryName && !/\.gguf$/i.test(bundle.display_name)) return bundle.display_name;
  const name = repositoryName ? bundle.display_name.split("/").at(-1)! : bundle.display_name;
  return name.replace(/[._ -]gguf$/i, "").replace(/[-_]+/g, " ").replace(/\b[a-z]/g, letter => letter.toUpperCase());
}
function modelLabel(bundle: ModelBundle, bundles: ModelBundle[]): string {
  const name = modelName(bundle);
  const siblings = bundles.filter(item => modelName(item) === name && modelDescription(item) === modelDescription(bundle));
  if (siblings.length < 2) return name;
  const publisher = bundle.source?.repo_id?.split("/")[0];
  const uniquePublisher = publisher && siblings.filter(item => item.source?.repo_id?.split("/")[0] === publisher).length === 1;
  return `${name} · ${uniquePublisher ? publisher : `Install ${siblings.indexOf(bundle) + 1}`}`;
}
function modelDetails(bundle?: ModelBundle): string {
  return bundle ? [bundle.display_name, modelDescription(bundle), modelFilename(bundle)].filter(Boolean).join(" · ") : "";
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
  const [highlighted, setHighlighted] = useState(0);
  const choicesRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (bundles || !pickerOpen) return;
    let cancelled = false;
    void api.bundles().then(items => { if (!cancelled) setFallbackBundles(items); }).catch((failure: unknown) => { if (!cancelled) setError(errorMessage(failure)); });
    return () => { cancelled = true; };
  }, [bundles, pickerOpen]);
  const availableBundles = bundles ?? fallbackBundles;
  const [thinking, setThinking] = useState(() => thinkingSettings(configuration));
  const [context, setContext] = useState<number | null>(() => typeof configuration.startup_overrides?.ctx_size === "number" ? configuration.startup_overrides.ctx_size : null);
  const [busy, setBusy] = useState(false);
  const [loadingChoice, setLoadingChoice] = useState("");
  const [error, setError] = useState("");
  const contextDrafts = useRef(new Map<string, { context: number | null; base: number | null }>());
  const pending = useRef(false);
  const ownerKey = [conversationId, projectId, agentSetupVersionId, configuration.model_configuration_id ?? selectedConfigurationId].join(":");
  const owner = useRef({ key: ownerKey, generation: 0 });
  if (owner.current.key !== ownerKey) owner.current = { key: ownerKey, generation: owner.current.generation + 1 };
  const currentGeneration = owner.current.generation;
  const latest = useRef({ configuration, onApply, onReloaded, runtimeBusy });
  latest.current = { configuration, onApply, onReloaded, runtimeBusy };
  const incomingThinking = JSON.stringify(thinkingSettings(configuration));
  const incomingContext = typeof configuration.startup_overrides?.ctx_size === "number" ? configuration.startup_overrides.ctx_size : null;
  useEffect(() => {
    setThinking(JSON.parse(incomingThinking) as Record<string, unknown>);
    const draft = contextDrafts.current.get(ownerKey);
    const next = draft && draft.context !== draft.base ? draft.context : incomingContext;
    contextDrafts.current.set(ownerKey, { context: next, base: incomingContext }); setContext(next); setError("");
  }, [incomingThinking, incomingContext, ownerKey]);
  function stageContext(next: number | null) { contextDrafts.current.set(ownerKey, { context: next, base: incomingContext }); setContext(next); setError(""); }

  const selectedProfile = profiles.find(item => item.id === (configuration.model_configuration_id ?? selectedConfigurationId));
  const selectedDeployment = deployments.find(item => item.id === selectedDeploymentId);
  const selectedBundleId = selectedProfile?.bundle_id ?? selectedDeployment?.bundle_id;
  const selectedBundle = availableBundles.find(item => item.id === selectedBundleId);
  const selectedName = selectedBundle ? modelLabel(selectedBundle, availableBundles) : selectedDeployment?.display_name.replace(/^(managed|connected):/, "") ?? "Choose model";
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
  const optionStartup = JSON.stringify(previewConfiguration.startup_overrides ?? {});
  const optionOwnerKey = JSON.stringify([selectedBundleId, selectedProfile?.id, selectedProfile?.revision, selectedDeployment?.id]);
  const optionKey = JSON.stringify([optionOwnerKey, optionStartup]);
  const [optionsResult, setOptionsResult] = useState<{ key: string; ownerKey: string; data: BundleConfigurationOptions } | null>(null);
  useEffect(() => {
    if (!tuningOpen || (!selectedBundleId && !selectedDeployment?.id)) return;
    let cancelled = false;
    const request = selectedBundleId ? api.modelConfiguration(selectedBundleId, selectedDeployment?.id, false, { configuration_id: selectedProfile?.id, startup: JSON.parse(optionStartup) as Record<string, unknown> })
      : api.deploymentConfiguration(selectedDeployment!.id);
    void request.then(data => { if (!cancelled) setOptionsResult({ key: optionKey, ownerKey: optionOwnerKey, data }); }).catch(failure => { if (!cancelled) setError(errorMessage(failure)); });
    return () => { cancelled = true; };
  }, [tuningOpen, optionKey, selectedBundleId, selectedDeployment?.id]);
  const options = optionsResult?.ownerKey === optionOwnerKey ? optionsResult.data : null;
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
      const loaded = loadAttempted ? await api.applyChatStartupOverrides(profile!.bundle_id!, profile!.id, candidate.startup_overrides ?? {}) : null;
      if (loaded && (!loaded.health?.healthy || loaded.status !== "running")) throw new Error(loaded.error ?? "Model did not become ready.");
      if (owner.current.generation !== currentGeneration) return;
      await latest.current.onApply({ ...candidate, deployment_id: loaded?.id ?? connected?.id ?? (latest.current.runtimeBusy ? null : exactDeployment?.id ?? null) });
      if (loadAttempted) await latest.current.onReloaded();
      if (owner.current.generation === currentGeneration) close();
    } catch (failure) {
      const parts = [errorMessage(failure)];
      if (owner.current.generation === currentGeneration && loadAttempted) {
        try {
          await latest.current.onApply(candidate);
        } catch (applyFailure) {
          parts.push(errorMessage(applyFailure));
        }
      }
      if (loadAttempted) {
        try {
          await latest.current.onReloaded();
        } catch (refreshFailure) {
          parts.push(errorMessage(refreshFailure));
        }
      }
      if (owner.current.generation === currentGeneration) setError((loadAttempted ? (profile?.display_name ?? connected?.display_name ?? "Model") + " · " : "") + parts.filter(Boolean).join(" "));
    } finally { pending.current = false; setBusy(false); setLoadingChoice(""); }
  }

  async function applyThinking(nextThinking: Record<string, unknown>) {
    if (pending.current) return;
    pending.current = true; setBusy(true); setThinking(nextThinking); setError("");
    try {
      const current = latest.current.configuration;
      const currentContext = typeof current.startup_overrides?.ctx_size === "number" ? current.startup_overrides.ctx_size : null;
      const next = chatTuningCandidate(current, nextThinking, currentContext);
      const key = selectedBundleId ?? selectedDeployment?.id;
      if (key) Object.assign(next, { model_overrides: { ...remembered(current), [key]: { model_configuration_id: selectedProfile?.id ?? null, startup_overrides: next.startup_overrides, per_request_overrides: next.per_request_overrides } } });
      await latest.current.onApply(next);
    } catch (failure) { if (owner.current.generation === currentGeneration) { setThinking(thinkingSettings(latest.current.configuration)); setError(errorMessage(failure)); } }
    finally { pending.current = false; setBusy(false); }
  }
  async function applyTuning(close: () => void) {
    if (pending.current || preview.loading || preview.error || !preview.data || (context !== null && (!Number.isInteger(context) || context < 0))) return;
    pending.current = true; setBusy(true); setError("");
    try {
      const current = latest.current.configuration;
      const next = chatTuningCandidate(current, thinking, context);
      const startup = next.startup_overrides ?? {};
      const key = selectedBundleId ?? selectedDeployment?.id;
      if (key) Object.assign(next, { model_overrides: { ...remembered(current), [key]: { model_configuration_id: selectedProfile?.id ?? null, startup_overrides: startup, per_request_overrides: next.per_request_overrides } } });
      if (!latest.current.runtimeBusy && selectedProfile?.bundle_id) {
        const loaded = await api.applyChatStartupOverrides(selectedProfile.bundle_id, selectedProfile.id, startup);
        if (!loaded.health?.healthy || loaded.status !== "running") throw new Error(loaded.error ?? "Model did not become ready.");
        next.deployment_id = loaded.id;
        if (owner.current.generation !== currentGeneration) return;
        await latest.current.onReloaded();
      }
      if (owner.current.generation !== currentGeneration) return;
      await latest.current.onApply(next);
      contextDrafts.current.set(ownerKey, { context, base: context });
      close();
    } catch (failure) {
      const parts = [errorMessage(failure)];
      try {
        await latest.current.onReloaded();
      } catch (refreshFailure) {
        parts.push(errorMessage(refreshFailure));
      }
      if (owner.current.generation === currentGeneration) setError(parts.filter(Boolean).join(" "));
    }
    finally { pending.current = false; setBusy(false); }
  }

  function choiceRow(profile: RunProfile | null, connected: Deployment | null, label: string, close: () => void, className = "chat-model-choice", description = "", details = description) {
    const key = profile?.id ?? connected?.id ?? label;
    const state = observed(profile, connected);
    const reason = incompatibleChoices[key];
    const variant = className.includes("chat-model-variant");
    const selected = profile ? selectedProfile?.id === profile.id : connected?.id === selectedDeploymentId;
    const index = visibleKeys.indexOf(variant ? `${key}:variant` : key);
    const status = <span className={"model-state-dot is-" + (reason ? "attention" : state.tone)} aria-label={reason || state.label} />;
    return <button id={`chat-model-option-${index}`} type="button" role="option" aria-selected={selected} data-highlighted={index === highlighted} className={className} key={key} disabled={busy || fixedModel || Boolean(reason) || (!profile && !connected)} aria-pressed={selected} title={[label, details, reason || state.label].filter(Boolean).join(" · ")} onPointerMove={() => setHighlighted(index)} onClick={() => void applyChoice(profile, connected, close)}>
      {!variant ? status : null}
      <span className="chat-model-choice-name"><strong>{label}</strong></span>
      {description ? <span className="chat-model-quantization">{description}</span> : null}
      {variant && (reason || state.tone === "loading" || state.tone === "attention") ? status : variant && selected ? <Icon name="check" size={14} /> : null}
    </button>;
  }
  const baseContext = facts["startup.ctx_size"]?.inherited_value;
  const contextSupported = Boolean(selectedProfile?.bundle_id) && options?.context_size.supported !== false;
  const tuningChanged = context !== incomingContext;
  const contextDefault = defaultSettingDisplay(facts["startup.ctx_size"], "configuration", "ctx_size");
  const thinkingFacts = residency.data?.effective_values ?? facts;
  const loadedContext = selectedDeployment?.server_props?.n_ctx;
  const selectedContext = typeof baseContext === "number" ? baseContext : selectedProfile?.bags.startup.requested.ctx_size;
  const contextMaximum = options?.context_size.maximum;
  const capacityLabel = (size: unknown) => size === 0 ? contextMaximum ? `Full · ${tokenLabel(contextMaximum)} tokens` : "Full model capacity" : typeof size === "number" && size > 0 ? `${tokenLabel(size)} tokens` : "Auto";
  const displayedContext = context === 0 ? contextMaximum ?? null : context ?? (selectedContext === 0 ? contextMaximum ?? null : typeof selectedContext === "number" ? selectedContext : null);
  const needsReload = tuningChanged || !runtimeBusy && selectedState.tone !== "ready";
  const term = search.trim().toLocaleLowerCase();
  const visibleBundles = availableBundles.filter(item => (item.status === "ready" || item.disk_matches) && [modelLabel(item, availableBundles), modelDetails(item), ...profiles.filter(profile => profile.bundle_id === item.id).map(profile => profile.display_name)].join(" ").toLocaleLowerCase().includes(term));
  const visibleConnected = connectedChoices.filter(item => item.display_name.toLocaleLowerCase().includes(term));
  const visibleKeys = [...visibleBundles.flatMap(bundle => {
    const variants = profiles.filter(profile => profile.bundle_id === bundle.id);
    return [preferredConfiguration(bundle)?.id ?? bundle.id, ...(variants.length > 1 ? variants.map(profile => `${profile.id}:variant`) : [])];
  }), ...visibleConnected.map(item => item.id)];
  const visibleKeySignature = visibleKeys.join("|");
  useEffect(() => {
    if (!pickerOpen) return;
    const selected = visibleKeys.indexOf(selectedProfile?.id ?? selectedDeployment?.id ?? "");
    setHighlighted(selected >= 0 ? selected : 0);
  }, [pickerOpen, search, visibleKeySignature]);
  useEffect(() => { choicesRef.current?.querySelector<HTMLElement>(`#chat-model-option-${highlighted}`)?.scrollIntoView?.({ block: "nearest" }); }, [highlighted, search, pickerOpen]);
  return <>
    <MenuPopover label={"Chat model: " + selectedName} className="chat-model-controls" panelClassName="chat-model-controls-panel" trigger={<><Icon name="models" size={16} /><span className="chat-model-controls-model" title={[modelDetails(selectedBundle) || selectedName, selectedProfile?.display_name].filter(Boolean).join(" · ")}>{selectedName}</span>{modelDescription(selectedBundle) ? <span className="chat-model-quantization">{modelDescription(selectedBundle)}</span> : null}<span className={"model-state-dot is-" + selectedState.tone} title={selectedState.label} /><span className="sr-only chat-model-status">{selectedState.label}</span></>} disabled={disabled} openRequest={openRequest} onOpenChange={setPickerOpen}>
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
            return <div key={bundle.id} className="chat-model-row">
              <div className="chat-model-primary">{choiceRow(profile ?? null, null, modelLabel(bundle, availableBundles), close, "chat-model-choice", modelDescription(bundle), [modelDetails(bundle), profile?.display_name].filter(Boolean).join(" · "))}</div>
              {variants.length > 1 ? <div className="chat-model-variants" role="group" aria-label={"Settings for " + modelLabel(bundle, availableBundles)}>{variants.map(item => choiceRow(item, null, item.display_name, close, "chat-model-choice chat-model-variant", "", modelDetails(bundle)))}</div> : null}
            </div>;
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
        <div className="chat-tuning-body">
        <header className="chat-tuning-heading"><strong>This chat</strong></header>
        <div className="setting-rows chat-thinking-settings">
          <ResponseSettingsEditor part="thinking-only" layout="models" value={thinking} facts={facts} presentationFacts={thinkingFacts} options={options} loading={preview.loading} disabled={busy} onChange={next => void applyThinking(next)} />
        </div>
        <section className="chat-capacity-settings" aria-label="Context">
          <SettingRow layout="models" label="Context" help={<>Total shared context in tokens. Apply this chat's settings changes loading settings; current and queued work keep their accepted settings.<code>{options?.context_size.flag ?? "--ctx-size"}</code></>} provenance={context === null ? contextDefault.source : "This chat"} onReset={context !== null && !busy ? () => stageContext(null) : undefined} resetLabel="Reset" resetTitle={contextDefault.title}>
            <ContextSlider label="Chat context" value={displayedContext} maximum={contextMaximum ?? null} disabled={busy || !contextSupported} onChange={stageContext} />
          </SettingRow>
          <dl className="chat-capacity-state"><div><dt>Selected</dt><dd>{capacityLabel(incomingContext ?? selectedContext)}</dd></div><div><dt title="Maximum tokens for one request on the loaded model. Simultaneous requests share its context pool.">Loaded per request</dt><dd>{loadedContext == null ? "Not reported" : capacityLabel(loadedContext)}</dd></div>{tuningChanged || runtimeBusy && incomingContext !== null && incomingContext !== loadedContext ? <div data-pending="true"><dt>Pending</dt><dd>{capacityLabel(context ?? selectedContext)}</dd></div> : null}</dl>
          {contextSupported && selectedProfile && context !== null && Number.isSafeInteger(context) && context >= 0 ? <ModelHardwareEstimate active={tuningOpen} selection={{ bundle_id: selectedBundleId, startup: mergedStartup(selectedProfile.bags.startup.requested, previewConfiguration.startup_overrides ?? {}) }} /> : null}
          {!contextSupported ? <span className="hint">{selectedDeployment?.scope === "connected" ? "Context is managed by this connection." : "Context control unavailable."}</span> : null}
        </section>
        {error || preview.error ? <Notice tone="error">{error || preview.error}</Notice> : null}
        </div>
        <div className="actions chat-model-controls-actions"><button type="button" className="primary-button" disabled={!contextSupported || !needsReload || busy || preview.loading || !preview.data || Boolean(preview.error) || (context !== null && (!Number.isInteger(context) || context < 0))} onClick={() => void applyTuning(close)}>{busy ? "Applying…" : runtimeBusy ? "Stage for next message" : "Apply this chat's settings"}</button></div>
      </>}
    </MenuPopover>
  </>;
}
