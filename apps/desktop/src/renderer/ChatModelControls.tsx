import { useEffect, useRef, useState } from "react";
import { api } from "./api";
import { Icon } from "./Icon";
import { MenuPopover } from "./MenuPopover";
import { Notice } from "./Notice";
import { SettingRow } from "./CompactControls";
import { ContextSlider } from "./ModelControls";
import { ResponseSettingsEditor } from "./ResponseSettingsEditor";
import { mergedStartup } from "./deploymentSettings";
import { formatBytes } from "./display";
import { errorMessage } from "./errors";
import { defaultSettingDisplay, useSetupPreview } from "./effectiveSettings";
import { estimateModel } from "./modelEstimateApi";
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
  selectionGeneration?: number;
  disabled?: boolean;
  runtimeBusy?: boolean;
  fixedModel?: boolean;
  onManageAgent?: () => void;
  openRequest?: number;
  onApply: (configuration: SetupConfiguration) => void | Promise<void>;
  onReloaded: () => Promise<void>;
  onBusyChange?: (busy: boolean) => void;
}

export function ChatModelControls({ bundles, deployments, profiles, selectedDeploymentId, selectedConfigurationId, configuration, projectId = null, agentSetupVersionId = null, conversationId = null, selectionGeneration = 0, disabled = false, runtimeBusy = false, fixedModel = false, onManageAgent, openRequest, onApply, onReloaded, onBusyChange }: ChatModelControlsProps) {
  const [fallbackBundles, setFallbackBundles] = useState<ModelBundle[]>([]);
  const [pickerOpen, setPickerOpen] = useState(false);
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
  const [memory, setMemory] = useState("Unknown");
  const contextDrafts = useRef(new Map<string, { context: number | null; base: number | null }>());
  const pending = useRef<object | null>(null);
  const thinkingPending = useRef<object | null>(null);
  const contextQueued = useRef<{ value: number | null } | null>(null);
  const acceptedThinking = useRef(thinkingSettings(configuration));
  const scopeKey = [selectionGeneration, conversationId, projectId, agentSetupVersionId].join(":");
  const ownerKey = [scopeKey, configuration.model_configuration_id ?? selectedConfigurationId].join(":");
  const contextDraftKey = [conversationId, projectId, agentSetupVersionId, configuration.model_configuration_id ?? selectedConfigurationId].join(":");
  const owner = useRef({ key: ownerKey, generation: 0 });
  if (owner.current.key !== ownerKey) owner.current = { key: ownerKey, generation: owner.current.generation + 1 };
  const currentGeneration = owner.current.generation;
  useEffect(() => {
    pending.current = null; thinkingPending.current = null; contextQueued.current = null; setBusy(false); setLoadingChoice("");
    return () => { pending.current = null; contextQueued.current = null; };
  }, [scopeKey]);
  useEffect(() => { onBusyChange?.(busy); return () => onBusyChange?.(false); }, [busy, onBusyChange]);
  function ownsOperation(operation: object) { return pending.current === operation && owner.current.generation === currentGeneration; }
  function finishOperation(operation: object) {
    if (pending.current !== operation) return;
    const queued = contextQueued.current;
    contextQueued.current = null;
    pending.current = null; setBusy(false); setLoadingChoice("");
    if (queued) void commitContext(queued.value);
  }
  const latest = useRef({ configuration, onApply, onReloaded, runtimeBusy, selectedProfile: undefined as RunProfile | undefined, selectedDeployment: undefined as Deployment | undefined, selectedBundleId: undefined as string | undefined });
  const incomingThinking = JSON.stringify(thinkingSettings(configuration));
  const incomingContext = typeof configuration.startup_overrides?.ctx_size === "number" ? configuration.startup_overrides.ctx_size : null;
  useEffect(() => {
    const nextThinking = JSON.parse(incomingThinking) as Record<string, unknown>;
    acceptedThinking.current = nextThinking;
    setThinking(nextThinking);
    const draft = contextDrafts.current.get(contextDraftKey);
    const next = draft && draft.context !== draft.base ? draft.context : incomingContext;
    contextDrafts.current.set(contextDraftKey, { context: next, base: incomingContext }); setContext(next); setError("");
  }, [incomingThinking, incomingContext, contextDraftKey]);
  function stageContext(next: number | null) { contextDrafts.current.set(contextDraftKey, { context: next, base: incomingContext }); setContext(next); setError(""); }

  const selectedProfile = profiles.find(item => item.id === (configuration.model_configuration_id ?? selectedConfigurationId));
  const selectedDeployment = deployments.find(item => item.id === selectedDeploymentId);
  const selectedBundleId = selectedProfile?.bundle_id ?? selectedDeployment?.bundle_id ?? undefined;
  const selectedBundle = availableBundles.find(item => item.id === selectedBundleId);
  const selectedName = selectedBundle ? modelLabel(selectedBundle, availableBundles) : selectedDeployment?.display_name.replace(/^(managed|connected):/, "") ?? "Choose model";
  const savedRevision = `${selectedProfile?.id ?? ""}:${selectedProfile?.revision ?? 0}`;
  const runtimeRevision = JSON.stringify([savedRevision, deployments.map(item => [item.id, item.profile_id, item.status, item.health?.healthy, item.settings?.startup?.requested])]);
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
  latest.current = { configuration, onApply, onReloaded, runtimeBusy, selectedProfile, selectedDeployment, selectedBundleId };
  const previewConfiguration = chatTuningCandidate(configuration, thinking, context);
  const preview = useSetupPreview(previewConfiguration, projectId, agentSetupVersionId, "conversation", savedRevision, pickerOpen);
  const facts = preview.data?.effective_values ?? {};
  const optionStartup = JSON.stringify(previewConfiguration.startup_overrides ?? {});
  const optionOwnerKey = JSON.stringify([selectedBundleId, selectedProfile?.id, selectedProfile?.revision, selectedDeployment?.id]);
  const optionKey = JSON.stringify([optionOwnerKey, optionStartup]);
  const [optionsResult, setOptionsResult] = useState<{ key: string; ownerKey: string; data: BundleConfigurationOptions } | null>(null);
  useEffect(() => {
    if (!pickerOpen || (!selectedBundleId && !selectedDeployment?.id)) return;
    let cancelled = false;
    const request = selectedBundleId ? api.modelConfiguration(selectedBundleId, selectedDeployment?.id, false, { configuration_id: selectedProfile?.id, startup: JSON.parse(optionStartup) as Record<string, unknown> })
      : api.deploymentConfiguration(selectedDeployment!.id);
    void request.then(data => { if (!cancelled) setOptionsResult({ key: optionKey, ownerKey: optionOwnerKey, data }); }).catch(failure => { if (!cancelled) setError(errorMessage(failure)); });
    return () => { cancelled = true; };
  }, [pickerOpen, optionKey, selectedBundleId, selectedDeployment?.id]);
  const options = optionsResult?.ownerKey === optionOwnerKey ? optionsResult.data : null;
  function preferredConfiguration(bundle: ModelBundle): RunProfile | undefined {
    return profiles.find(item => item.bundle_id === bundle.id && item.id === selectedProfile?.id)
      ?? profiles.find(item => item.bundle_id === bundle.id && item.id === remembered(configuration)[bundle.id]?.model_configuration_id)
      ?? profiles.find(item => item.id === bundle.default_configuration_id)
;
  }
  const connectedChoices = deployments.filter(item => item.scope === "connected");
  const compatibilityContext = JSON.stringify([conversationId, projectId, agentSetupVersionId, configuration]);
  const [incompatibleResult, setIncompatibleResult] = useState<{ context: string; reasons: Record<string, string> }>({ context: "", reasons: {} });
  const incompatibleChoices = incompatibleResult.context === compatibilityContext ? incompatibleResult.reasons : {};

  async function applyChoice(profile: RunProfile | null, connected: Deployment | null, close: () => void) {
    if (pending.current || disabled || fixedModel) return;
    const choiceKey = profile?.id ?? connected?.id ?? "";
    if (incompatibleChoices[choiceKey]) { setError(incompatibleChoices[choiceKey]); return; }
    const exactHealthyChoice = profile
      ? selectedProfile?.id === profile.id && selectedDeployment?.id === residency.data?.configuration.deployment_id && selectedState.tone === "ready"
      : connected?.id === selectedDeployment?.id && selectedState.tone === "ready";
    if (exactHealthyChoice) { close(); return; }
    const operation = {}; pending.current = operation;
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
      if (!ownsOperation(operation)) return;
      const resolved = await workspaceApi.resolveSetup(projectId, agentSetupVersionId, candidate);
      if (!ownsOperation(operation)) return;
      const exactDeployment = deployments.find(item => item.id === resolved.configuration.deployment_id);
      loadAttempted = Boolean(profile?.bundle_id) && !latest.current.runtimeBusy && !(exactDeployment?.status === "running" && exactDeployment.health?.healthy);
      const loaded = loadAttempted ? await api.applyChatStartupOverrides(profile!.bundle_id!, profile!.id, candidate.startup_overrides ?? {}) : null;
      if (loaded && (!loaded.health?.healthy || loaded.status !== "running")) throw new Error(loaded.error ?? "Model did not become ready.");
      if (!ownsOperation(operation)) return;
      await latest.current.onApply({ ...candidate, deployment_id: loaded?.id ?? connected?.id ?? (latest.current.runtimeBusy ? null : exactDeployment?.id ?? null) });
      // Acceptance may publish the chosen profile before this callback returns.
      // Close for that one expected transition, never for later navigation.
      const acceptedOwnerKey = [scopeKey, candidate.model_configuration_id ?? selectedConfigurationId].join(":");
      if (pending.current === operation && (owner.current.generation === currentGeneration || (owner.current.key === acceptedOwnerKey && owner.current.generation === currentGeneration + 1))) close();
      if (loadAttempted) await latest.current.onReloaded();
    } catch (failure) {
      const parts = [errorMessage(failure)];
      if (ownsOperation(operation) && loadAttempted) {
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
      if (ownsOperation(operation)) setError((loadAttempted ? (profile?.display_name ?? connected?.display_name ?? "Model") + " · " : "") + parts.filter(Boolean).join(" "));
    } finally { finishOperation(operation); }
  }

  function loadedContextSize(deployment?: Deployment): number | null {
    const reported = deployment?.server_props?.n_ctx;
    if (typeof reported === "number") return reported;
    const requested = deployment?.settings?.startup?.requested?.ctx_size;
    return typeof requested === "number" ? requested : null;
  }
  function savedContextSize(profile?: RunProfile): number | null {
    const requested = profile?.bags.startup.requested.ctx_size;
    return typeof requested === "number" ? requested : null;
  }
  function rememberChoice(current: SetupConfiguration, next: SetupConfiguration) {
    const key = latest.current.selectedBundleId ?? latest.current.selectedDeployment?.id;
    if (!key) return next;
    return { ...next, model_overrides: { ...remembered(current), [key]: { model_configuration_id: latest.current.selectedProfile?.id ?? null, startup_overrides: next.startup_overrides, per_request_overrides: next.per_request_overrides } } };
  }
  async function applyThinking(nextThinking: Record<string, unknown>) {
    // A context reload must not drop or delay the next message's Thinking change.
    if (thinkingPending.current || disabled) return;
    const operation = {}; thinkingPending.current = operation; acceptedThinking.current = nextThinking; setThinking(nextThinking); setError("");
    try {
      const current = latest.current.configuration;
      const currentContext = typeof current.startup_overrides?.ctx_size === "number" ? current.startup_overrides.ctx_size : null;
      const next = rememberChoice(current, chatTuningCandidate(current, nextThinking, currentContext));
      if (thinkingPending.current !== operation || owner.current.generation !== currentGeneration) return;
      await latest.current.onApply(next);
    } catch (failure) {
      if (thinkingPending.current === operation && owner.current.generation === currentGeneration) {
        const restored = thinkingSettings(latest.current.configuration);
        acceptedThinking.current = restored; setThinking(restored); setError(errorMessage(failure));
      }
    } finally { if (thinkingPending.current === operation) thinkingPending.current = null; }
  }
  async function commitContext(nextContext: number | null) {
    if (disabled) return;
    if (pending.current) { contextQueued.current = { value: nextContext }; return; }
    const profile = latest.current.selectedProfile;
    const deployment = latest.current.selectedDeployment;
    const accepted = typeof latest.current.configuration.startup_overrides?.ctx_size === "number" ? latest.current.configuration.startup_overrides.ctx_size : null;
    const target = nextContext ?? savedContextSize(profile);
    const loadedSize = loadedContextSize(deployment);
    // Only a healthy running model reloads. A stopped model would cold-start; active work waits.
    const reload = !latest.current.runtimeBusy && Boolean(profile?.bundle_id) && deployment?.status === "running" && Boolean(deployment.health?.healthy) && typeof target === "number" && loadedSize !== null && target !== loadedSize;
    if (nextContext === accepted && !reload) return;
    const operation = {}; pending.current = operation; setBusy(true); setError("");
    let loadedId: string | undefined;
    try {
      if (reload && profile?.bundle_id) {
        const startup = chatTuningCandidate(latest.current.configuration, acceptedThinking.current, nextContext).startup_overrides ?? {};
        const loaded = await api.applyChatStartupOverrides(profile.bundle_id, profile.id, startup);
        if (!loaded.health?.healthy || loaded.status !== "running") throw new Error(loaded.error ?? "Model did not become ready.");
        loadedId = loaded.id;
      }
      if (!ownsOperation(operation) || contextQueued.current) return;
      const current = latest.current.configuration;
      const next = rememberChoice(current, chatTuningCandidate(current, acceptedThinking.current, nextContext));
      if (loadedId) next.deployment_id = loadedId;
      await latest.current.onApply(next);
      if (!ownsOperation(operation)) return;
      if (loadedId) {
        try { await latest.current.onReloaded(); }
        catch (failure) { if (ownsOperation(operation)) setError(errorMessage(failure)); }
      }
    } catch (failure) {
      if (ownsOperation(operation)) setError(errorMessage(failure));
    } finally { finishOperation(operation); }
  }

  function choiceRow(profile: RunProfile | null, connected: Deployment | null, label: string, close: () => void, className = "chat-model-choice", description = "", details = description) {
    const key = profile?.id ?? connected?.id ?? label;
    const state = observed(profile, connected);
    const reason = incompatibleChoices[key];
    const variant = className.includes("chat-model-variant");
    const selected = profile ? selectedProfile?.id === profile.id : connected?.id === selectedDeploymentId;
    const index = visibleKeys.indexOf(variant ? `${key}:variant` : key);
    const status = <span className={"model-state-dot is-" + (reason ? "attention" : state.tone)} aria-label={reason || state.label} />;
    return <button id={`chat-model-option-${index}`} type="button" role="option" aria-selected={selected} data-highlighted={index === highlighted} className={className} key={key} disabled={disabled || busy || fixedModel || Boolean(reason) || (!profile && !connected)} aria-pressed={selected} title={[label, details, reason || state.label].filter(Boolean).join(" · ")} onPointerMove={() => setHighlighted(index)} onClick={() => void applyChoice(profile, connected, close)}>
      {!variant ? status : null}
      <span className="chat-model-choice-name"><strong>{label}</strong></span>
      {description ? <span className="chat-model-quantization">{description}</span> : null}
      {variant && (reason || state.tone === "loading" || state.tone === "attention") ? status : variant && selected ? <Icon name="check" size={14} /> : null}
    </button>;
  }
  const baseContext = facts["startup.ctx_size"]?.inherited_value;
  const contextSupported = Boolean(selectedProfile?.bundle_id) && options?.context_size.supported !== false;
  const contextDefault = defaultSettingDisplay(facts["startup.ctx_size"], "configuration", "ctx_size");
  const thinkingFacts = residency.data?.effective_values ?? facts;
  const selectedContext = typeof baseContext === "number" ? baseContext : selectedProfile?.bags.startup.requested.ctx_size;
  const contextMaximum = options?.context_size.maximum;
  const displayedContext = context === 0 ? contextMaximum ?? null : context ?? (selectedContext === 0 ? contextMaximum ?? null : typeof selectedContext === "number" ? selectedContext : null);
  const contextReason = selectedDeployment?.scope === "connected" && !selectedProfile?.bundle_id ? "Context is managed by this connection." : options?.context_size.supported === false ? "Context control unavailable." : "";
  const contextHelp = contextReason || (runtimeBusy ? "A context change waits for the next message." : "A context change reloads the model.");
  useEffect(() => {
    if (!pickerOpen || !selectedBundleId) return;
    const controller = new AbortController();
    const startup = mergedStartup(selectedProfile?.bags.startup.requested ?? {}, previewConfiguration.startup_overrides ?? {});
    void estimateModel({ bundle_id: selectedBundleId, startup }, false, controller.signal).then(data => {
      if (controller.signal.aborted) return;
      const known = data.gpu_bytes != null || data.ram_bytes != null;
      setMemory(known ? formatBytes((data.gpu_bytes ?? 0) + (data.ram_bytes ?? 0)) : "Unknown");
    }).catch(() => { if (!controller.signal.aborted) setMemory("Unknown"); });
    return () => controller.abort();
  }, [pickerOpen, selectedBundleId, optionStartup]);
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
        <div className="chat-model-settings">
          <ResponseSettingsEditor part="thinking-only" value={thinking} facts={facts} presentationFacts={thinkingFacts} options={options} loading={preview.loading} disabled={disabled} showReadout={false} onChange={next => void applyThinking(next)} />
          <SettingRow label="Context" help={contextHelp} onReset={context !== null && !busy ? () => { stageContext(null); void commitContext(null); } : undefined} resetLabel="Reset" resetTitle={contextDefault.title}>
            <div className="chat-context-line">
              <ContextSlider label="Chat context" value={displayedContext} maximum={contextMaximum ?? null} disabled={Boolean(contextReason) || !contextSupported} title={contextHelp} onChange={next => { stageContext(next); void commitContext(next); }} />
              <span className="chat-context-memory">{memory}</span>
            </div>
          </SettingRow>
        </div>
        {error ? <Notice tone="error">{error}</Notice> : null}
      </>}
    </MenuPopover>
  </>;
}
