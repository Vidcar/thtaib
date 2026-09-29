import { useEffect, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { ModelPresetPanel } from "./ModelPresetPanel";
import { ModelDeletion } from "./ModelDeletion";
import type { ModelInspectorConnection, ModelInspectorView } from "./ModelInspector";
import { api } from "./api";
import { formatBytes } from "./display";
import { errorMessage } from "./errors";
import { ChoiceControl, ContextSlider, numberChoices, tokenLabel } from "./ModelControls";
import { NumberField, SettingRow, SettingSection } from "./CompactControls";
import { modelFileLabel } from "./ModelPicker";
import { mergedStartup, startupPayload } from "./deploymentSettings";
import { EmptyState } from "./EmptyState";
import { Notice } from "./Notice";
import { SettingsNotes } from "./settingsNotes";
import { StatusBadge } from "./StatusBadge";
import { Icon } from "./Icon";
import { ModelCapabilities } from "./ModelCapabilities";
import { ResponseSettingsEditor } from "./ResponseSettingsEditor";
import { defaultSettingDisplay, effectiveSettingDisplay, settingValue } from "./effectiveSettings";
import type { EffectiveSetting } from "./effectiveSettings";
import { useSetupPreview } from "./effectiveSettings";
import { ModelProjectorControls } from "./ModelProjectorControls";
import { ModelHardwareEstimate } from "./ModelHardwareEstimate";

import { MenuPopover } from "./MenuPopover";
import { CompactDialog } from "./CompactDialog";
import type { BundleConfigurationOptions, Deployment, DeploymentProfileChanges, ModelBundle, ResponseRecipeOrigin, RunProfile, RuntimeManifest, SettingsBags } from "./types";
import "./deploymentReadouts.css";

const cacheTypes = ["f16", "q8_0", "q4_0", "q4_1", "q5_0", "q5_1", "bf16", "f32", "iq4_nl"];
const choices = (values: string[]) => values.map(value => ({ value, label: value }));
const switches = [{ value: "on", label: "On" }, { value: "off", label: "Off" }];
const initialSettings: Record<string, string> = { ctx_size: "", n_gpu_layers: "", flash_attn: "", fit: "", cache_type_k: "", cache_type_v: "", kv_offload: "", kv_unified: "", op_offload: "", mmproj_use_gpu: "", spec_draft_ngl: "", threads: "", threads_batch: "", load_mode: "", parallel: "", port: "", batch_size: "", ubatch_size: "", reasoning: "", reasoning_effort: "", reasoning_preserve: "", reasoning_format: "", reasoning_budget: "", embedding: "", pooling: "", spec_type: "", spec_draft_n_max: "", spec_draft_n_min: "", spec_draft_p_min: "", spec_draft_p_split: "", spec_draft_threads: "", spec_draft_threads_batch: "", spec_draft_cache_type_k: "", spec_draft_cache_type_v: "" };
const EMPTY_BUNDLES: ModelBundle[] = [];
const EMPTY_PROFILES: RunProfile[] = [];
type ModelDraft = { settings: Record<string, string>; response: Record<string, unknown>; agent: Record<string, unknown>; origin: ResponseRecipeOrigin | null; name: string; advanced: string; changed: string[]; presetApplied: boolean };
const draftKey = (bundle: string, profile: string) => `${bundle}:${profile || "default"}`;

function startupValueLabel(key: string, value: unknown): string {
  if (key === "ctx_size" && typeof value === "number") return value === 0 ? "Full model capacity" : `${value.toLocaleString()} tokens`;
  if (key === "n_gpu_layers") return value === -1 || value === "-1" || value === "auto" ? "Automatic fit" : value === "all" ? "All layers requested" : value === 0 ? "CPU only" : typeof value === "number" ? `${value} layers requested` : settingValue(value);
  if (key === "spec_type" && value === "none") return "Off";
  if (key === "reasoning_budget" && value === -1) return "Unrestricted";
  if (key === "reasoning_preserve") return value === true ? "Keep" : value === false ? "Drop" : settingValue(value);
  if (key === "embedding") return value === "on" ? "Document search" : value === "off" ? "Chat" : settingValue(value);
  return settingValue(value, key);
}

function stateOf(d: Deployment): { label: string; tone: "ok" | "warn" | "neutral" | "danger" } {
  if (d.status === "stopped") return { label: "Stopped", tone: "neutral" };
  if (d.status === "failed") return { label: "Needs attention", tone: "danger" };
  if (d.health?.healthy) return { label: "Ready", tone: "ok" };
  return { label: d.status === "starting" ? "Loading" : "Not ready", tone: "warn" };
}

export function DeploymentsPanel({
  selectedBundleId = "",
  bundlesVersion = "",
  initialBundles = EMPTY_BUNDLES,
  initialProfiles = EMPTY_PROFILES,
  onBundlesChanged,
  onSelectBundle,
  onDirtyModelsChange,
  active = true,
  inspector,
  openConfigurationId,
  openRequest,
}: {
  selectedBundleId?: string;
  bundlesVersion?: string;
  initialBundles?: ModelBundle[];
  initialProfiles?: RunProfile[];
  onBundlesChanged?: () => Promise<void>;
  onSelectBundle?: (id: string) => void;
  onDirtyModelsChange?: (ids: ReadonlySet<string>) => void;
  active?: boolean;
  inspector?: ModelInspectorConnection;
  openConfigurationId?: string;
  openRequest?: number;
} = {}) {
  const formRef = useRef<HTMLFormElement>(null);
  const selection = useRef(selectedBundleId); selection.current = selectedBundleId;
  const selectionOwner = useRef({ id: selectedBundleId, profile: "", generation: 0 });

  const hydrated = useRef({ bundle: "", deployment: "", profile: "", revision: 0 });
  const dirty = useRef(false);
  const drafts = useRef(new Map<string, ModelDraft>());
  const activeDraftKey = useRef("");
  const actionPending = useRef(false);
  const openedRequest = useRef("");
  const changedStartup = useRef(new Set<string>());
  const [runtime, setRuntime] = useState<RuntimeManifest | null>(null);
  const [deployments, setDeployments] = useState<Deployment[]>([]);
  const [profileId, setProfileId] = useState("");
  if (selectionOwner.current.id !== selectedBundleId || selectionOwner.current.profile !== profileId) selectionOwner.current = { id: selectedBundleId, profile: profileId, generation: selectionOwner.current.generation + 1 };
  const [localInspector, setLocalInspector] = useState<ModelInspectorView | null>(null);
  const panelView = inspector?.view ?? localInspector;
  const openPanel = (view: ModelInspectorView) => inspector ? inspector.open(view) : setLocalInspector(view);
  const [replacementDefault, setReplacementDefault] = useState("");
  const [settingsPreviewKey, setSettingsPreviewKey] = useState("");
  const [checkedSelection, setCheckedSelection] = useState("");
  const [checkedName, setCheckedName] = useState("");
  const presetApplied = useRef(false);
  const presentation = useRef<{ selection: string; facts: Record<string, EffectiveSetting> }>({ selection: "", facts: {} });
  const [configurationName, setConfigurationName] = useState("");
  const [variantName, setVariantName] = useState("");
  const [creatingVariant, setCreatingVariant] = useState(false);
  const [response, setResponse] = useState<Record<string, unknown>>({});
  const [agentSettings, setAgentSettings] = useState<Record<string, unknown>>({});
  const [recipeOrigin, setRecipeOrigin] = useState<ResponseRecipeOrigin | null>(null);
  const [logs, setLogs] = useState<Record<string, string>>({});
  const [generation, setGeneration] = useState<Record<string, string>>({});
  const [profileChanges, setProfileChanges] = useState<Record<string, DeploymentProfileChanges>>({});
  const [loaded, setLoaded] = useState(false);
  const [settings, setSettings] = useState({ ...initialSettings });
  const [configuration, setConfiguration] = useState<BundleConfigurationOptions | null>(null);
  const [configurationRevision, setConfigurationRevision] = useState(0);
  const [maximumContext, setMaximumContext] = useState<number | null>(null);
  const [contextSpan, setContextSpan] = useState(262144);
  const [layers, setLayers] = useState<number | null>(null);
  const [threadChoices, setThreadChoices] = useState([{ value: "-1", label: "Auto" }, ...numberChoices([1, 2, 4, 6, 8, 12, 16, 24, 32])]);
  const [modelInfo, setModelInfo] = useState("Reading model limits…");
  const [advancedStartup, setAdvancedStartup] = useState("");
  const [settingsPreview, setSettingsPreview] = useState<SettingsBags | null>(null);
  const [message, setMessage] = useState("");
  const [messageTone, setMessageTone] = useState<"info" | "error" | "ok">("info");
  const [loadError, setLoadError] = useState("");
  const [busy, setBusy] = useState("");
  const [busySelection, setBusySelection] = useState("");
  const bundles = initialBundles;
  const profiles = initialProfiles;
  const selectedProfile = profiles.find(item => item.id === profileId);
  const savedResponses = selectedProfile?.bags.per_request.requested ?? {};
  const responseChanges = Object.fromEntries([...new Set([...Object.keys(savedResponses), ...Object.keys(response)])]
    .filter(key => JSON.stringify(savedResponses[key]) !== JSON.stringify(response[key]))
    .map(key => [key, response[key] ?? null]));
  const selected = bundles.find(b => b.id === selectedBundleId);
  const current = deployments.filter(d => d.status !== "stopped");
  const extraConnections = current.filter(d => d.scope === "connected" && current.some(other => other.scope === "managed" && other.endpoint === d.endpoint && other.health?.healthy));
  const visibleCurrent = current.filter(d => !extraConnections.includes(d));
  const savedResidency = useSetupPreview({ model_configuration_id: profileId || null }, null, null, "conversation", `${selectedProfile?.revision ?? 0}:${JSON.stringify(deployments.map(item => [item.id, item.status, item.updated_at]))}`, Boolean(active && profileId));
  const residentId = savedResidency.data?.configuration.deployment_id;
  // Saving loading settings changes the future launch identity, not the child
  // already running for this configuration. Keep its observed state until reload.
  const selectedResident = visibleCurrent.find(d => d.bundle_id === selectedBundleId && d.id === residentId)
    ?? visibleCurrent.filter(d => d.bundle_id === selectedBundleId && d.scope === "managed" && profileId && d.profile_id === profileId && ["starting", "running", "unhealthy"].includes(d.status))
      .sort((a, b) => Number(b.status === "running" && b.health?.healthy) - Number(a.status === "running" && a.health?.healthy)
        || (Date.parse(b.updated_at ?? "") || 0) - (Date.parse(a.updated_at ?? "") || 0) || a.id.localeCompare(b.id))[0];
  const selectedCurrent = selectedResident ? [selectedResident] : [];
  const otherVariants = visibleCurrent.filter(d => d.bundle_id === selectedBundleId && d.id !== selectedResident?.id);
  const otherCurrent = visibleCurrent.filter(d => d.bundle_id !== selectedBundleId && bundles.some(bundle => bundle.id === d.bundle_id));
  const externalCurrent = visibleCurrent.filter(d => d.bundle_id !== selectedBundleId && !bundles.some(bundle => bundle.id === d.bundle_id));
  const selectedConnections = extraConnections.filter(d => selectedCurrent.some(model => model.endpoint === d.endpoint));
  const history = deployments.filter(d => d.status === "stopped" && d.bundle_id === selectedBundleId);
  const selectedRunning = selectedCurrent.find(d => d.status === "running" && d.health?.healthy);
  const selectedActive = selectedCurrent.find(d => d.scope === "managed" && d.status !== "failed");
  const bundleActive = deployments.some(d => d.bundle_id === selectedBundleId && d.scope === "managed"
    && (["starting", "running", "unhealthy"].includes(d.status) || d.pid != null || d.process_identity != null));
  const runtimeReady = loaded && runtime?.status === "ready";
  const thinkingAvailable = Boolean(configuration?.per_request_defaults?.reasoning?.supported || configuration?.per_request_defaults?.reasoning_effort?.supported);
  const descriptorOptions = (key: string) => (configuration?.startup_defaults[key]?.options ?? []).map(option => ({ value: String(option.value ?? ""), label: option.label }));
  let stagedStartup: Record<string, unknown> | null = null;
  let stagedStartupError = "";
  try { stagedStartup = startup(); } catch (error) { stagedStartupError = errorMessage(error); }
  const optionsProfile = selectedProfile ?? profiles.find(item => item.id === selected?.default_configuration_id) ?? profiles.find(item => item.bundle_id === selectedBundleId);
  const optionsSelection = JSON.stringify({ configuration_id: optionsProfile?.id ?? null, startup: stagedStartup ?? {} });
  const canonical = (values: Record<string, unknown>) => JSON.stringify(Object.fromEntries(Object.keys(values).sort().map(key => [key, values[key]])));
  if (hydrated.current.bundle === selectedBundleId && hydrated.current.profile === profileId && selectedProfile) {
    dirty.current = presetApplied.current || Boolean(stagedStartupError) || canonical(mergedStartup(selectedProfile.bags.startup.requested, stagedStartup ?? {})) !== canonical(selectedProfile.bags.startup.requested)
      || canonical(response) !== canonical(savedResponses) || canonical(agentSettings) !== canonical(selectedProfile.bags.agent.requested) || JSON.stringify(recipeOrigin) !== JSON.stringify(selectedProfile.recipe_origin ?? null) || configurationName.trim() !== selectedProfile.display_name;
    if (!dirty.current) drafts.current.delete(activeDraftKey.current);
  }
  // The editor previews a replacement model configuration. Only changed keys
  // are overrides; omission continues to mean inheritance at submission.
  const setupPreview = useSetupPreview({ bundle_id: selectedBundleId || null, model_configuration_id: profileId || null,
    startup_overrides: stagedStartup ?? {}, per_request_overrides: responseChanges }, null, null, "conversation",
    `${bundlesVersion}:${selectedProfile?.revision ?? 0}:${selectedRunning?.updated_at ?? ""}:${configurationRevision}`, Boolean(active && selectedBundleId && stagedStartup));
  const modelFacts = Object.fromEntries(Object.entries(setupPreview.data?.effective_values ?? {})
    .map(([key, fact]) => [key, fact.source === "Turn overrides" && key.startsWith("per_request.") && Object.hasOwn(responseChanges, key.slice(12))
      ? { ...fact, source: "Unsaved changes" }
      : fact.source === "Turn overrides" && key.startsWith("startup.") && Object.hasOwn(stagedStartup ?? {}, key.slice(8))
        ? { ...fact, source: "This editor" } : fact]));
  const responseFacts = modelFacts;
  const presentationSelection = `${selectedBundleId}:${profileId}`;
  if (setupPreview.data) presentation.current = { selection: presentationSelection, facts: modelFacts };
  const presentationFacts = presentation.current.selection === presentationSelection ? presentation.current.facts : {};
  const candidateKey = JSON.stringify([selectedBundleId, profileId, canonical(mergedStartup(selectedProfile?.bags.startup.requested ?? {}, stagedStartup ?? {})), canonical(response), configurationName.trim(), recipeOrigin, canonical(agentSettings)]);
  const checkedHere = checkedSelection === presentationSelection;
  const startupReadout = (key: string) => {
    const fact = modelFacts[`startup.${key}`];
    const display = stagedStartupError ? { value: "Check settings", source: stagedStartupError } : effectiveSettingDisplay(fact, setupPreview.loading);
    if (fact?.known && fact.supported !== false && !stagedStartupError && !setupPreview.loading) display.value = startupValueLabel(key, fact.value);
    const edited = stagedStartup && Object.hasOwn(stagedStartup, key);
    const saved = Object.hasOwn(selectedProfile?.bags.startup.requested ?? {}, key);
    const state = edited && stagedStartup?.[key] !== null ? "Unsaved change" : "";
    return <span className="model-effective-readout" data-state={saved || edited ? "set" : "following"}><strong>{display.value}</strong>{[display.source, !setupPreview.loading && !stagedStartupError ? state : ""].filter(Boolean).map(part => ` · ${part}`).join("")}</span>;
  };
  const startupResolved = (key: string) => {
    const fact = modelFacts[`startup.${key}`] ?? presentationFacts[`startup.${key}`];
    if (fact?.known) return fact.supported !== false ? fact.value : null;
    const descriptor = key === "ctx_size" ? configuration?.context_size : key === "n_gpu_layers" ? configuration?.gpu_layers : configuration?.startup_defaults[key];
    return descriptor?.applied ?? descriptor?.default_value ?? null;
  };
  const canResetStartup = (key: string) => (Object.hasOwn(stagedStartup ?? {}, key) && stagedStartup?.[key] !== null)
    || (Object.hasOwn(selectedProfile?.bags.startup.requested ?? {}, key) && stagedStartup?.[key] !== null);
  const startupReset = (key: string) => { const target = defaultSettingDisplay(modelFacts[`startup.${key}`], "model", key); return { resetLabel: "Reset", resetTitle: target.title }; };

  function publishDraftMarkers() {
    const ids = new Set([...drafts.current.keys()].map(key => key.split(":", 1)[0]));
    if (dirty.current && activeDraftKey.current) ids.add(activeDraftKey.current.split(":", 1)[0]);
    onDirtyModelsChange?.(ids);
  }
  function stashDraft() {
    if (!activeDraftKey.current || !dirty.current) return;
    drafts.current.set(activeDraftKey.current, { settings: { ...settings }, response: { ...response }, agent: { ...agentSettings }, origin: recipeOrigin, name: configurationName, advanced: advancedStartup, changed: [...changedStartup.current], presetApplied: presetApplied.current });
    publishDraftMarkers();
  }
  function restoreDraft(key: string): boolean {
    const draft = drafts.current.get(key);
    if (!draft) return false;
    activeDraftKey.current = key;
    dirty.current = true;
    presetApplied.current = draft.presetApplied;
    changedStartup.current = new Set(draft.changed);
    setSettings({ ...draft.settings }); setResponse({ ...draft.response }); setAgentSettings({ ...draft.agent }); setRecipeOrigin(draft.origin); setConfigurationName(draft.name); setAdvancedStartup(draft.advanced);
    publishDraftMarkers();
    return true;
  }
  useEffect(() => { publishDraftMarkers(); }, [settings, response, agentSettings, recipeOrigin, configurationName, advancedStartup, selectedBundleId, profileId]);

  function applyConfiguration(report: BundleConfigurationOptions) {
    if (report.bundle_id !== selection.current) return;
    setConfiguration(report);
    setConfigurationRevision(value => value + 1);
    const maximum = report.context_size.maximum;
    setMaximumContext(maximum); setLayers(report.gpu_layers.maximum);
    const threads = report.startup_defaults.threads;
    if (threads?.options.length) setThreadChoices(threads.options.filter(option => typeof option.value === "number").map(option => ({ value: String(option.value), label: option.label })));
    setModelInfo(maximum && maximum > 0 ? `${tokenLabel(maximum)} maximum context · ${report.metadata.architecture ?? "GGUF"}` : "Model capacity unavailable");
  }

  async function refresh() {
    const [r, d] = await Promise.all([api.runtime(), api.deployments()]);
    setRuntime(r); setDeployments(d); setLoaded(true); setLoadError("");
  }
  useEffect(() => { if (active) void refresh().catch(error => setLoadError(errorMessage(error))); }, [bundlesVersion, active]);
  useEffect(() => {
    if (!loaded) return;
    const changedModel = hydrated.current.bundle !== selectedBundleId;
    const saved = (!changedModel ? selectedProfile : undefined) ?? profiles.find(item => item.id === (selectedRunning?.profile_id ?? selected?.default_configuration_id)) ?? profiles.find(item => item.bundle_id === selectedBundleId);
    const changedProfile = saved && (hydrated.current.profile !== saved.id || hydrated.current.revision !== saved.revision);
    const shouldHydrate = changedModel || (!dirty.current && changedProfile) || (selectedRunning && !dirty.current && hydrated.current.deployment !== selectedRunning.id);
    if (changedModel) { stashDraft(); dirty.current = false; setMessage(""); setProfileId(""); }
    if (changedModel) { setConfiguration(null); setMaximumContext(null); setLayers(null); setModelInfo("Loading model details…"); }
    if (shouldHydrate) {
    hydrated.current = { bundle: selectedBundleId, deployment: selectedRunning?.id ?? "", profile: saved?.id ?? "", revision: saved?.revision ?? 0 };
    const nextProfileId = saved?.id ?? "";
    const nextKey = draftKey(selectedBundleId, nextProfileId);
    setProfileId(nextProfileId);
    if (changedModel && restoreDraft(nextKey)) {
      // Keep the draft; metadata still refreshes for the newly selected model.
    } else {
    activeDraftKey.current = nextKey;
    dirty.current = false;
    presetApplied.current = false;
    changedStartup.current = new Set();
    setConfigurationName(saved?.display_name ?? "Default"); setResponse(saved?.bags.per_request.requested ?? {}); setAgentSettings(saved?.bags.agent.requested ?? {}); setRecipeOrigin(saved?.recipe_origin ?? null);
    const starting = { ...initialSettings };
    const extra: Record<string, unknown> = {};
    const formStartup = saved?.bags.startup.requested ?? {};
    for (const [key, value] of Object.entries(formStartup)) {
      if (key in starting) starting[key] = key === "reasoning_preserve" ? value === true ? "keep" : value === false ? "drop" : "" : String(value);
      else if (key !== "host") extra[key] = value;
    }
    setSettings(starting); setAdvancedStartup(Object.keys(extra).length ? JSON.stringify(extra, null, 2) : "");
    }
    }
  // Load existing settings once per selection; stopping a model must not erase edits.
  }, [selectedBundleId, loaded, selectedRunning?.id, profiles.length, selectedProfile?.id, selectedProfile?.revision, selected?.default_configuration_id]);
  useEffect(() => {
    if (!active || !loaded || !selectedBundleId || stagedStartupError) return;
    let cancelled = false;
    // Keep descriptor-owned controls mounted while the same model is checked.
    setModelInfo("Checking model details…");
    void api.modelConfiguration(selectedBundleId, selectedRunning?.id, false, JSON.parse(optionsSelection) as { configuration_id: string | null; startup: Record<string, unknown> }).then(report => {
      if (!cancelled) applyConfiguration(report);
    }).catch(() => { if (!cancelled) setModelInfo("Model details unavailable · refresh to retry"); });
    return () => { cancelled = true; };
  }, [active, loaded, selectedBundleId, selectedRunning?.id, optionsSelection, optionsProfile?.revision, stagedStartupError]);
  useEffect(() => {
    if (!active) return;
    const loading = deployments.filter(d => d.scope === "managed" && ["starting", "unhealthy"].includes(d.status));
    if (!loading.length) return;
    let cancelled = false, inFlight = false;
    const timer = window.setInterval(() => {
      if (inFlight) return;
      inFlight = true;
      void Promise.all(loading.map(d => api.healthOf(d.id))).then(updated => {
        if (!cancelled) setDeployments(records => records.map(record => updated.find(item => item.id === record.id) ?? record));
      }).catch(() => {}).finally(() => { inFlight = false; });
    }, 3000);
    return () => { cancelled = true; window.clearInterval(timer); };
  }, [deployments, active]);
  function markDraftChanged() { dirty.current = true; if (messageTone === "ok") setMessage(""); }
  function change(key: string, value: string) { markDraftChanged(); changedStartup.current.add(key); setSettings(previous => ({ ...previous, [key]: value })); }
  function changePlacement(mode: string) {
    change("n_gpu_layers", mode === "all" ? "all" : mode === "cpu" ? "0" : mode === "exact" ? String(Math.max(1, Math.floor((layers ?? 32) / 2))) : "auto");
  }
  function selectProfile(id: string) {
    stashDraft();
    setMessage(""); setReplacementDefault("");
    const key = draftKey(selectedBundleId, id);
    const profile = profiles.find(item => item.id === id);
    hydrated.current = { ...hydrated.current, profile: id, revision: profile?.revision ?? 0 };
    activeDraftKey.current = key;
    dirty.current = false;
    presetApplied.current = false;
    changedStartup.current = new Set();
    setProfileId(id);
    if (restoreDraft(key)) return;
    setConfigurationName(profile?.display_name ?? "Default"); setResponse(profile?.bags.per_request.requested ?? {}); setAgentSettings(profile?.bags.agent.requested ?? {}); setRecipeOrigin(profile?.recipe_origin ?? null); setCreatingVariant(false);
    const next = { ...initialSettings }, extra: Record<string, unknown> = {};
    for (const [key, value] of Object.entries(profile?.bags.startup.requested ?? {})) {
      if (key in next) next[key] = key === "reasoning_preserve" ? value === true ? "keep" : value === false ? "drop" : "" : String(value);
      else extra[key] = value;
    }
    setSettings(next); setAdvancedStartup(Object.keys(extra).length ? JSON.stringify(extra, null, 2) : "");
  }
  useEffect(() => {
    if (!active || !loaded || !openConfigurationId || !profiles.some(profile => profile.id === openConfigurationId && profile.bundle_id === selectedBundleId)) return;
    const request = `${openRequest ?? 0}:${openConfigurationId}`;
    if (openedRequest.current === request) return;
    openedRequest.current = request;
    selectProfile(openConfigurationId);
  }, [active, loaded, openConfigurationId, openRequest, selectedBundleId, profiles]);
  async function action(key: string, operation: () => Promise<unknown>) {
    if (actionPending.current) return;
    actionPending.current = true;
    const owner = selectionOwner.current;
    setBusy(key); setBusySelection(`${owner.id}:${owner.profile}`); setMessage("");
    try { await operation(); } catch (error) { if (selectionOwner.current === owner) { setMessage(errorMessage(error)); setMessageTone("error"); } } finally { actionPending.current = false; setBusy(""); }
  }
  function startup(): Record<string, unknown> {
    const saved = profiles.find(profile => profile.id === profileId)?.bags.startup.requested ?? {};
    const values = startupPayload(settings, advancedStartup, saved, changedStartup.current);
    for (const [key, value] of Object.entries(values)) {
      if (value === null ? !Object.hasOwn(saved, key) : JSON.stringify(value) === JSON.stringify(saved[key])) delete values[key];
    }
    if (!thinkingAvailable && !profileId) {
      for (const key of ["reasoning", "reasoning_effort", "reasoning_format", "reasoning_budget", "reasoning_preserve"]) {
        if (!changedStartup.current.has(key) && !selectedRunning?.applied_startup[key]) delete values[key];
      }
    }
    return values;
  }
  async function preview(startupValues = mergedStartup(selectedProfile?.bags.startup.requested ?? {}, startup()), responseValues = response, owner = selectionOwner.current) {
    const checkedKey = JSON.stringify([owner.id, owner.profile, canonical(startupValues), canonical(responseValues), configurationName.trim(), recipeOrigin, canonical(agentSettings)]);
    const report = await api.previewSettings(startupValues, responseValues, agentSettings);
    const result = { ...report, per_request: { ...report.per_request,
      unsupported: [...new Set([...report.per_request.unsupported, ...Object.keys(responseValues).filter(key => configuration?.per_request_defaults[key]?.supported === false)])] } };
    if (selectionOwner.current === owner) { setSettingsPreview(result); setSettingsPreviewKey(checkedKey); setCheckedSelection(`${owner.id}:${owner.profile}`); setCheckedName(configurationName); }
    if (result.startup.unsupported.length || result.startup.retired.length || result.per_request.unsupported.length || result.per_request.retired.length) { if (selectionOwner.current === owner) openPanel("checks"); throw new Error("Some settings need attention. See Checked setup."); }
    return result;
  }
  function configurationPayload(asVariant = false) {
    const name = (asVariant ? variantName : configurationName).trim();
    if (!name) throw new Error("Enter a configuration name.");
    return {
      display_name: name,
      startup: mergedStartup(selectedProfile?.bags.startup.requested ?? {}, startup()), per_request: response, agent: agentSettings,
      recipe_origin: recipeOrigin,
      ...(asVariant ? {} : { configuration_id: profileId || undefined, expected_revision: selectedProfile?.revision }),
    };
  }
  async function persistConfiguration(payload: ReturnType<typeof configurationPayload>, asVariant: boolean, owner: typeof selectionOwner.current) {
    const saved = await api.saveModelConfiguration(owner.id, payload);
    if (selectionOwner.current === owner) {
      drafts.current.delete(activeDraftKey.current);
      activeDraftKey.current = draftKey(owner.id, saved.id);
      setProfileId(saved.id); setConfigurationName(saved.display_name); changedStartup.current.clear(); dirty.current = false; presetApplied.current = false;
      publishDraftMarkers();
      setCreatingVariant(false); setVariantName("");
    }
    await onBundlesChanged?.(); await refresh();
    if (selectionOwner.current === owner) { setMessageTone("ok"); setMessage(asVariant ? "Copy saved." : "Saved."); }
    return saved;
  }
  async function saveConfiguration(asVariant = false) {
    const payload = configurationPayload(asVariant), owner = selectionOwner.current;
    await preview(payload.startup, payload.per_request, owner);
    return persistConfiguration(payload, asVariant, owner);
  }
  async function loadSavedSetup() {
    if (!selectedProfile) throw new Error("Save this setup before loading it.");
    const owner = selectionOwner.current;
    try {
      const result = await api.startManaged(owner.id, selectedProfile.id, {});
      if (result.status === "failed" || result.error) throw new Error(result.error ?? "Model could not load.");
      if (selectionOwner.current === owner) { setMessageTone("ok"); setMessage(result.health?.healthy ? "Saved setup loaded." : "Loading saved setup…"); }
    } finally { await refresh(); }
  }
  const field = (key: string, label: string, help: string, options: Array<{ value: string; label: string }>, custom = false, min = 0, max?: number, inactive = false) => {
    const requested = settings[key];
    const observed = key === "ctx_size" ? selectedRunning?.server_props?.n_ctx : configuration?.startup_defaults[key]?.observed;
    const loadedValue = observed ?? selectedRunning?.applied_startup[key];
    const normalizedLoaded = key === "reasoning_preserve" ? loadedValue === true ? "keep" : loadedValue === false ? "drop" : loadedValue : loadedValue;
    const resolved = modelFacts[`startup.${key}`];
    const showLoaded = selectedRunning && normalizedLoaded != null && (!resolved?.known || String(normalizedLoaded) !== String(resolved.value ?? ""));
    const resolvedValue = startupResolved(key);
    const normalizedResolved = key === "reasoning_preserve" ? resolvedValue === true ? "keep" : resolvedValue === false ? "drop" : resolvedValue : resolvedValue;
    const defaultValue = modelFacts[`startup.${key}`]?.default_value;
    const normalizedDefault = key === "reasoning_preserve" ? defaultValue === true ? "keep" : defaultValue === false ? "drop" : defaultValue : defaultValue;
    const resolvedLabel = normalizedDefault == null ? "Not reported" : options.find(option => option.value === String(normalizedDefault))?.label ?? startupValueLabel(key, defaultValue);
    const descriptor = configuration?.startup_defaults[key];
    const blocked = Boolean(busy) || descriptor?.supported === false || inactive;
    return <SettingRow layout="models" key={key} label={label} htmlFor={`model-${key}`} help={<>{help}{descriptor?.flag ? <code>{descriptor.flag}</code> : null}{descriptor?.request_path ? <code>{descriptor.request_path}</code> : null}<span>Applies when loaded.</span></>} provenance={startupReadout(key)}
      onReset={canResetStartup(key) && !busy ? () => change(key, "") : undefined} {...startupReset(key)}
      hint={descriptor?.supported === false ? descriptor.description : showLoaded ? <span className="model-loaded-difference">Loaded: {key === "ctx_size" ? `${tokenLabel(Number(loadedValue))} tokens` : settingValue(normalizedLoaded, key)}</span> : undefined}>
      <ChoiceControl stable id={`model-${key}`} label={label} value={requested} options={options} onChange={value => change(key, value)} custom={custom} numericControl={["spec_draft_p_min", "spec_draft_p_split"].includes(key)} min={descriptor?.minimum ?? min} max={descriptor?.maximum ?? max} step={descriptor?.domain === "number" ? "any" : descriptor?.step ?? 1} disabled={blocked} resolvedLabel={resolvedLabel} resolvedValue={normalizedResolved} />
    </SettingRow>;
  };
  const gpuValue = settings.n_gpu_layers || String(startupResolved("n_gpu_layers") ?? "auto");
  const gpuMode = ["auto", "-1"].includes(gpuValue) ? "auto" : gpuValue === "all" ? "all" : gpuValue === "0" ? "cpu" : "exact";
  const contextLoaded = selectedRunning?.server_props?.n_ctx;
  const contextResolvedRaw = startupResolved("ctx_size");
  const contextResolved = typeof contextResolvedRaw === "number" ? contextResolvedRaw : null;
  const portResolved = startupResolved("port");
  const contextAuto = settings.ctx_size === "auto" || settings.ctx_size === "" && !changedStartup.current.has("ctx_size") && startupResolved("ctx_size") === "auto";
  const contextShown = contextAuto ? null : settings.ctx_size === "0" || settings.ctx_size === "" && contextResolved === 0 ? maximumContext : settings.ctx_size !== "" && Number.isFinite(Number(settings.ctx_size)) && Number(settings.ctx_size) > 0 ? Number(settings.ctx_size) : contextResolved && contextResolved > 0 ? contextResolved : null;
  const gpuLoaded = selectedRunning?.applied_startup.n_gpu_layers;
  const readout = (values: Record<string, unknown>) => <dl className="settings-readout">{Object.entries(values).map(([key, value]) => <div key={key}><dt>{key.replaceAll("_", " ")}</dt><dd>{String(value)}</dd></div>)}</dl>;

  function renderDeployment(d: Deployment) {
    const state = stateOf(d), ctx = d.server_props?.n_ctx;
    const sampling = Object.fromEntries(Object.entries(d.server_props?.default_generation_settings?.params ?? {}).filter(([key]) => ["temperature", "top_p", "top_k", "min_p", "repeat_penalty", "n_predict"].includes(key)));
    const name = bundles.find(b => b.id === d.bundle_id)?.display_name ?? d.display_name.replace(/^(managed|connected):/, "");
    const gpuLayers = d.applied_startup.n_gpu_layers;
    const speculation = d.applied_startup.spec_type;
    const thinking = d.applied_startup.reasoning_effort ?? d.applied_startup.reasoning;
    const hasSpeculation = speculation != null && !["", "none", "off"].includes(String(speculation));
    const hasThinkingOverride = thinking != null && !["", "auto", "default"].includes(String(thinking));
    return <li key={d.id} className="running-model">
      <div className="section-heading"><div><strong>{name}</strong><p className="hint">{d.scope === "managed" ? "On this computer" : "External server"}{ctx ? ` · ${tokenLabel(ctx)} context` : ""}{d.resource_usage?.available ? ` · ${formatBytes(d.resource_usage.rss_bytes)} RAM` : ""}</p></div><StatusBadge label={state.label} tone={state.tone} /></div>
      {d.error && d.status !== "stopped" ? <Notice tone="error">{d.error}</Notice> : null}
      {gpuLayers != null || hasSpeculation || hasThinkingOverride || d.loaded_chat_template_origin ? <dl className="model-applied-facts" aria-label="Applied model settings">
        {d.loaded_chat_template_origin ? <div title="The running server reported the selected Hugging Face chat template"><dt>Chat template</dt><dd>{d.loaded_chat_template_origin === "publisher" ? "Publisher" : "GGUF repository"} · confirmed</dd></div> : null}
        {gpuLayers != null ? <div title="GPU layers requested at launch; actual placement is not reported here"><dt>GPU layers</dt><dd>{startupValueLabel("n_gpu_layers", gpuLayers)}</dd></div> : null}
        {hasSpeculation ? <div title="Speculative decoding launch setting"><dt>Speculation</dt><dd>{String(speculation)}{String(speculation).startsWith("draft-") ? ` · ${d.applied_startup.spec_draft_n_max ?? 3} tokens` : ""}</dd></div> : null}
        {hasThinkingOverride ? <div title="Thinking launch setting. Per-message controls can override it."><dt>Thinking</dt><dd>{String(thinking)}</dd></div> : null}
      </dl> : null}
      <div className="actions">
        {d.scope === "managed" && d.status !== "stopped" ? <button type="button" disabled={Boolean(busy)} onClick={() => void action(d.id, async () => { await api.stop(d.id); await refresh(); })}>{busy === d.id ? "Unloading…" : "Unload model"}</button> : null}
        {d.scope === "managed" && d.status === "stopped" ? <button type="button" disabled={Boolean(busy)} onClick={() => void action(d.id, async () => { await api.start(d.id); await refresh(); })}>Load snapshot</button> : null}
        {d.scope === "connected" ? <button type="button" disabled={Boolean(busy)} onClick={() => void action(d.id, async () => { await api.detach(d.id); await refresh(); })}>Disconnect</button> : null}
        {d.status !== "stopped" ? <button type="button" className="quiet-button" disabled={Boolean(busy)} onClick={() => void action(`health-${d.id}`, async () => { await api.healthOf(d.id); await refresh(); })}>Check status</button> : null}
        {d.health?.healthy ? <button type="button" disabled={Boolean(busy)} onClick={() => void action(`test-${d.id}`, async () => { const result = await api.smoke(d.id); setGeneration(previous => ({ ...previous, [d.id]: result.ok ? result.detail ?? "Text generation succeeded for this check." : `Generation check failed: ${result.detail ?? "No completed response"}` })); })}>Test text generation</button> : null}
      </div>
      {generation[d.id] ? <p role="status">{generation[d.id]}</p> : null}
      <ModelCapabilities deployment={d} busy={busy} action={action} />
      <details className="technical-details"><summary>Details &amp; applied settings</summary>
        <dl className="model-facts"><div><dt>Connection</dt><dd>{d.endpoint}</dd></div><div><dt>Deployment ID</dt><dd><code>{d.id}</code></dd></div><div><dt>Context reported by server</dt><dd>{ctx ? `${ctx.toLocaleString()} tokens` : "Not reported"}</dd></div><div><dt>Concurrent requests reported by server</dt><dd>{d.server_props?.total_slots ?? "Not reported"}</dd></div><div><dt>Engine version</dt><dd>{d.server_props?.build_info ?? "Not reported"}</dd></div><div><dt>Settings last reported</dt><dd>{d.server_props?.fetched ? new Date(d.server_props.fetched).toLocaleString() : "Not reported"}</dd></div></dl>
        <h4>Launch settings</h4><p className="hint">Values sent when this model was started. Automatic choices may be adjusted by the engine.</p>{readout(d.applied_startup)}
        {Object.keys(sampling).length ? <><h4>Engine-reported response defaults</h4>{readout(sampling)}</> : null}
        <SettingsNotes unsupported={d.settings?.startup.unsupported} retired={d.settings?.startup.retired} />
        {d.profile_id ? <><button type="button" disabled={Boolean(busy)} onClick={() => void action(`profile-${d.id}`, async () => { const result = await api.deploymentProfileChanges(d.id); setProfileChanges(previous => ({ ...previous, [d.id]: result })); })}>Compare with saved configuration</button>
          {profileChanges[d.id] ? <p className="hint">{profileChanges[d.id].has_pending_startup_changes ? "The saved configuration has different startup settings. This deployment keeps its original configuration; unload and start a new setup to apply the edited settings." : "No pending startup differences."}{profileChanges[d.id].has_pending_per_request_changes ? " Response settings have changed for future work." : ""}</p> : null}</> : null}
        {d.health?.detail ? <p className="hint">Health check: {d.health.detail}</p> : null}
        {d.error && d.status === "stopped" ? <p className="hint">Last event: {d.error}</p> : null}
        {d.scope === "managed" ? <><button type="button" disabled={Boolean(busy)} onClick={() => void action(`logs-${d.id}`, async () => { const result = await api.deploymentLogs(d.id); setLogs(previous => ({ ...previous, [d.id]: result.text })); })}>Read recent engine log</button>{logs[d.id] ? <pre className="engine-log">{logs[d.id]}</pre> : null}</> : null}
      </details>
    </li>;
  }
  let panelContent: ReactNode = null;
  if (panelView === "presets" && selected) panelContent = <ModelPresetPanel key={selected.id} bundle={selected} value={response} facts={responseFacts} origin={recipeOrigin} options={configuration} disabled={Boolean(busy)} onChanged={onBundlesChanged} onReadCard={() => openPanel("card")}
    onApply={(next, origin) => { presetApplied.current = true; markDraftChanged(); setResponse(next); setRecipeOrigin(origin); }} />;
  else if (panelView === "checks") panelContent = <section className="model-check-results">
    <p className="hint">{checkedHere && settingsPreview ? checkedName : configurationName} · checked setup</p>
    {checkedHere && settingsPreview && settingsPreviewKey !== candidateKey ? <Notice tone="warn">Out of date — check the current draft again.</Notice> : null}
    {busySelection === presentationSelection && (busy === "preview" || busy === "save") ? <p role="status">Checking this setup…</p> : null}
    {checkedHere && settingsPreview ? (["startup", "per_request"] as const).map(section => <section key={section}>
      <h4>{section === "startup" ? "Loading settings" : "Response settings"}</h4>{readout(settingsPreview[section].applied)}
      <SettingsNotes category={section === "per_request" ? "response" : "startup"} unsupported={settingsPreview[section].unsupported} retired={settingsPreview[section].retired} />
    </section>) : <p className="hint">{messageTone === "error" && message ? message : "Validate the current draft to inspect its native settings."}</p>}
    <button type="button" disabled={Boolean(busy)} onClick={() => void action("preview", () => preview())}>Validate draft</button>
  </section>;
  else if (panelView === "runtime") panelContent = <>
    <h4>Selected model loads</h4>
    {selectedCurrent.length ? <ul className="plain-list">{selectedCurrent.map(renderDeployment)}</ul> : <p className="hint">This saved setup is not loaded.</p>}
    {otherVariants.length ? <details open><summary>Other saved setups loaded for this model</summary><ul className="plain-list">{otherVariants.map(renderDeployment)}</ul></details> : null}
    {otherCurrent.length ? <details><summary>Other loaded models</summary>{otherCurrent.map(item => <button type="button" key={item.id} onClick={() => onSelectBundle?.(item.bundle_id ?? "")}>{bundles.find(bundle => bundle.id === item.bundle_id)?.display_name ?? item.display_name}</button>)}<ul className="plain-list">{otherCurrent.map(renderDeployment)}</ul></details> : null}
    {selectedConnections.length ? <ul className="plain-list">{selectedConnections.map(renderDeployment)}</ul> : null}
    {externalCurrent.length ? <details><summary>Other model servers</summary><ul className="plain-list">{externalCurrent.map(renderDeployment)}</ul></details> : null}
    {history.length ? <details><summary>Runtime history</summary><ul className="plain-list">{history.map(renderDeployment)}</ul></details> : null}
  </>;
  else if (panelView === "setup" && selectedProfile) panelContent = <section>
    <h4>{selectedProfile.display_name}</h4>
    {profiles.filter(item => item.bundle_id === selectedBundleId).length <= 1 ? <p className="hint">Keep one saved setup for this model. Revert edits or reset its controls instead.</p>
      : selected?.default_configuration_id === profileId ? <>
        <p>Choose another model default before deleting this setup.</p>
        <select aria-label="Replacement model default" value={replacementDefault} onChange={event => setReplacementDefault(event.target.value)}><option value="">Choose saved setup</option>{profiles.filter(item => item.bundle_id === selectedBundleId && item.id !== profileId).map(item => <option key={item.id} value={item.id}>{item.display_name}</option>)}</select>
        <button type="button" disabled={Boolean(busy) || !replacementDefault} onClick={() => void action("default", async () => { await api.setDefaultConfiguration(selectedBundleId, replacementDefault); await onBundlesChanged?.(); })}>Make model default</button>
      </> : <ModelDeletion key={profileId} kind="profile" id={profileId} name={selectedProfile.display_name} initialOpen onDeleted={async () => {
        drafts.current.delete(draftKey(selectedBundleId, profileId)); dirty.current = false; presetApplied.current = false;
        hydrated.current = { ...hydrated.current, profile: "", revision: 0 }; setProfileId(""); inspector?.close(); setLocalInspector(null); await onBundlesChanged?.();
      }} />}
  </section>;
  else if (panelView === "files" && selected) panelContent = <><button type="button" disabled={Boolean(busy)} onClick={() => void action("metadata", async () => { applyConfiguration(await api.modelConfiguration(selectedBundleId, selectedRunning?.id, true, { configuration_id: selectedProfile?.id ?? null, startup: startup() })); })}>Refresh model details</button><ModelProjectorControls key={selected.id} bundleId={selected.id} active={bundleActive} disabled={Boolean(busy)} action={action} onSaved={async () => { await onBundlesChanged?.(); await refresh(); }} /></>;
  const toolbarMessage = messageTone === "ok" && (dirty.current || creatingVariant) ? "" : message;
  return <section className="model-configuration">
    {loadError ? <Notice tone="error">{loadError}<button type="button" onClick={() => void refresh().catch(error => setLoadError(errorMessage(error)))}>Try again</button></Notice> : null}

    {selected ? <section className="model-setup"><form id="model-settings-form" ref={formRef} className="model-settings" onSubmit={event => { event.preventDefault(); if (formRef.current?.reportValidity()) void action("save", () => saveConfiguration(creatingVariant)); }}>
      <header className="model-setup-head">
        <div className="model-setup-identity"><h3 className="selected-model-name">{selected.display_name}</h3><span className="model-weight-variant" title={selected.primary_path ?? modelFileLabel(selected)}>{modelFileLabel(selected)}</span>{!selected.disk_matches ? <span className="model-file-attention">Files need attention</span> : null}</div>
        <button type="button" disabled={Boolean(busy)} onClick={() => openPanel("presets")}>Model card</button>
        {profiles.filter(profile => profile.bundle_id === selectedBundleId).length > 1 ? <div className="model-setup-selector"><label className="visually-hidden" htmlFor="model-configuration">Setup</label><select id="model-configuration" value={profileId} disabled={Boolean(busy)} onChange={event => selectProfile(event.target.value)}>{!profileId ? <option value="">New setup</option> : null}{profiles.filter(profile => profile.bundle_id === selectedBundleId).map(profile => <option key={profile.id} value={profile.id}>{profile.display_name}</option>)}</select></div> : null}
        <button type="submit" className="primary-button" disabled={Boolean(busy) || !(creatingVariant ? variantName : configurationName).trim()}>{busy === "save" ? "Saving…" : "Save"}</button>
        <span className="model-edit-state" data-dirty={dirty.current || creatingVariant}>{creatingVariant ? "New copy" : dirty.current ? "Unsaved" : ""}</span>
        <MenuPopover label="Setup actions" className="model-setup-menu" placement="below" align="end" trigger={<Icon name="more" size={16} />} disabled={Boolean(busy)}>
          {close => <div className="model-setup-actions"><button type="button" onClick={() => { close(); openPanel("files"); }}>Files &amp; model information</button><button type="button" onClick={() => { close(); openPanel("runtime"); }}>Loaded model details</button><button type="button" disabled={Boolean(busy)} onClick={() => { close(); openPanel("checks"); void action("preview", () => preview()); }}>Validate draft</button><label htmlFor="model-configuration-name">Rename setup<input id="model-configuration-name" value={configurationName} disabled={Boolean(busy)} onChange={event => { dirty.current = true; setConfigurationName(event.target.value); }} /></label><button type="button" disabled={Boolean(busy)} onClick={() => { setCreatingVariant(true); setVariantName(`${configurationName} copy`); close(); }}><Icon name="copy" size={14} />Save a copy</button>{selectedProfile && selected.default_configuration_id !== selectedProfile.id ? <button type="button" disabled={Boolean(busy)} onClick={() => { close(); void action("default", async () => { await api.setDefaultConfiguration(selectedBundleId, selectedProfile.id); await onBundlesChanged?.(); }); }}>Make model default</button> : null}<button type="button" disabled={Boolean(busy)} onClick={() => { drafts.current.delete(activeDraftKey.current); dirty.current = false; presetApplied.current = false; selectProfile(profileId); close(); }}>Revert edits</button><button type="button" disabled={Boolean(busy)} onClick={() => { close(); openPanel("setup"); }}>Manage setups</button>{selectedActive ? <button type="button" disabled={Boolean(busy)} onClick={() => { close(); void action("unload", async () => { await api.stop(selectedActive.id); await refresh(); }); }}>{busy === "unload" ? "Unloading…" : "Unload"}</button> : null}</div>}
        </MenuPopover>
        <div className="model-lifecycle-actions"><button type="button" disabled={Boolean(busy) || !profileId || !runtimeReady || !selected.disk_matches || Boolean(selectedActive && !selectedRunning)} title={dirty.current ? "Load the saved setup. Save edits first to use pending values." : "Load the saved setup using its loading settings."} onClick={() => void action("load", loadSavedSetup)}>{busy === "load" ? "Loading…" : dirty.current ? "Load saved" : selectedActive ? "Reload" : "Load"}</button></div>
        <button type="button" className="text-button model-setup-readiness" aria-label="Loaded model details" onClick={() => openPanel("runtime")}><StatusBadge {...(selectedCurrent.length ? stateOf(selectedCurrent[0]) : { label: "Not loaded", tone: "neutral" as const })} /></button>
      <div className="model-toolbar-status" role="status" data-tone={messageTone}>{stagedStartupError || setupPreview.error || toolbarMessage || (!loaded ? "Checking local engine…" : !runtimeReady ? "Set up the local engine in Settings" : "\u00a0")}</div>
      </header>
      {creatingVariant ? <CompactDialog title="Save a setup copy" labelledBy="setup-copy-title" busy={Boolean(busy)} onClose={() => setCreatingVariant(false)}><label htmlFor="model-variant-name">New setup name</label><input autoFocus id="model-variant-name" value={variantName} onChange={event => setVariantName(event.target.value)} /><button type="button" className="primary-button" disabled={Boolean(busy) || !variantName.trim()} onClick={() => void action("save", () => saveConfiguration(true))}>Save copy</button></CompactDialog> : null}
      <div className="model-settings-columns"><SettingSection title="Generation">
        <ResponseSettingsEditor layout="models" presentationFacts={presentationFacts} part="thinking" value={response} onChange={next => { markDraftChanged(); setResponse(next); }} facts={responseFacts} options={configuration} disabled={Boolean(busy)} inheritance="model" loading={setupPreview.loading} />
        <ResponseSettingsEditor layout="models" presentationFacts={presentationFacts} part="sampling" value={response} onChange={next => { markDraftChanged(); setResponse(next); }} facts={responseFacts} options={configuration} disabled={Boolean(busy)} inheritance="model" loading={setupPreview.loading} />
        <details className="technical-details"><summary>Optional model instructions</summary><SettingRow layout="models" stacked label="Model instructions" htmlFor="model-authored-instructions" help="Optional text supplied with this saved model setup for future messages. Agent instructions are managed in Agents; native model formatting is automatic." onReset={typeof agentSettings.system_prompt === "string" && agentSettings.system_prompt.length && !busy ? () => { const next = { ...agentSettings }; delete next.system_prompt; markDraftChanged(); setAgentSettings(next); } : undefined} resetLabel="Reset" resetTitle="Supply no optional model instructions"><textarea id="model-authored-instructions" rows={4} value={typeof agentSettings.system_prompt === "string" ? agentSettings.system_prompt : ""} disabled={Boolean(busy)} onChange={event => { const next = { ...agentSettings }; if (event.target.value) next.system_prompt = event.target.value; else delete next.system_prompt; markDraftChanged(); setAgentSettings(next); }} placeholder="No additional instructions" /></SettingRow></details>
      </SettingSection>
      <SettingSection title="Loading">

        <SettingRow layout="models" label="Context" htmlFor="model-ctx-size" help={<>Total shared context capacity in tokens. Simultaneous requests share this pool. {modelInfo}<code>{configuration?.context_size.flag ?? "--ctx-size"}</code><span>Applies when loaded.</span></>} provenance={startupReadout("ctx_size")}
          onReset={canResetStartup("ctx_size") && !busy ? () => change("ctx_size", "") : undefined} {...startupReset("ctx_size")}
          hint={contextLoaded != null && (!modelFacts["startup.ctx_size"]?.known || Number(modelFacts["startup.ctx_size"].value) !== contextLoaded) ? <span className="model-loaded-difference">Loaded per request: {tokenLabel(contextLoaded)} tokens</span> : undefined}>
          <ContextSlider id="model-ctx-size" value={contextShown} maximum={maximumContext} span={contextSpan} unknownLabel={contextAuto ? "Auto" : "Not reported"} disabled={Boolean(busy)} onChange={value => change("ctx_size", String(value))} />
        </SettingRow>
        <SettingRow layout="models" label="GPU layers" labelId="model-gpu-label" help={<>Auto lets the engine choose weight placement. All requests full weight offload. CPU keeps model weights in RAM; other offload settings stay independent.<code>{configuration?.gpu_layers.flag ?? "--n-gpu-layers"}</code><span>Applies when loaded.</span></>} provenance={startupReadout("n_gpu_layers")}
          onReset={canResetStartup("n_gpu_layers") && !busy ? () => change("n_gpu_layers", "") : undefined} {...startupReset("n_gpu_layers")}
          hint={gpuLoaded != null && (!modelFacts["startup.n_gpu_layers"]?.known || startupValueLabel("n_gpu_layers", modelFacts["startup.n_gpu_layers"].value) !== startupValueLabel("n_gpu_layers", gpuLoaded)) ? <span className="model-loaded-difference">Loaded request: {startupValueLabel("n_gpu_layers", gpuLoaded)}</span> : undefined}>
          <div className="model-placement-control"><select aria-label="GPU layers" value={gpuMode} disabled={Boolean(busy)} onChange={event => changePlacement(event.target.value)}><option value="auto">Auto</option><option value="all">All</option><option value="cpu">CPU</option><option value="exact">Layers</option></select><span className="model-gpu-exact" data-active={gpuMode === "exact"}><NumberField label="Exact GPU layers" min={1} max={layers ?? undefined} step={1} value={gpuMode === "exact" ? gpuValue : null} disabled={Boolean(busy) || gpuMode !== "exact"} onChange={value => change("n_gpu_layers", value == null ? "custom" : String(value))} /></span></div>
        </SettingRow>
        {field("cache_type_k", "K cache precision", "Stores attention keys. Lower precision saves memory with a possible quality trade-off.", choices(cacheTypes))}
        {field("cache_type_v", "V cache precision", "Stores attention values. Some lower-precision combinations require Flash attention.", choices(cacheTypes))}
        {field("flash_attn", "Flash attention", "Faster, more memory-efficient attention when supported.", [{ value: "auto", label: "Auto" }, ...switches])}
        {field("spec_type", "MTP", configuration?.startup_defaults.spec_type?.description ?? "Uses the model's verified next-token prediction tensors to draft ahead.", [{ value: "none", label: "Off" }, ...(descriptorOptions("spec_type").some(option => option.value === "draft-mtp") ? [{ value: "draft-mtp", label: "On" }] : [])])}
        <details className="technical-details memory-advanced"><summary>Cache &amp; processing</summary><div className="setting-rows">
          {field("kv_offload", "Keep cache on GPU", "CPU keeps cache in RAM independently of weight-layer offloading.", [{ value: "true", label: "GPU" }, { value: "false", label: "CPU" }])}
          {field("fit", "Memory fitting", "Adjust settings not fixed explicitly to fit GPU memory.", switches)}
          {field("parallel", "Parallel requests", "Auto uses four native slots with a shared context pool. Choose an explicit count to use a divided pool.", [{ value: "-1", label: "Auto" }, ...numberChoices([1, 2, 4, 8])], true, -1)}
          {field("kv_unified", "Shared context pool", "Unified KV shares cache storage across slots. Off divides the pool when Parallel requests has an explicit count; native Auto always shares it.", [{ value: "true", label: "On" }, { value: "false", label: "Off" }])}
        </div></details>
        <ModelHardwareEstimate compact onDetails={() => openPanel("memory")} detailsTarget={panelView === "memory" ? inspector?.target : null} active={active} selection={{ bundle_id: selectedBundleId, startup: mergedStartup(selectedProfile?.bags.startup.requested ?? {}, stagedStartup ?? {}) }} />
      <details className="settings-group technical-settings"><summary>Advanced loading settings</summary>
      <SettingSection title="Memory &amp; processing">
        <SettingRow layout="models" label="Context mode" help={<>A fixed Context uses the slider value. Auto allows native fitting; Full requests the model metadata maximum.<code>{configuration?.context_size.flag ?? "--ctx-size"}</code></>} provenance={startupReadout("ctx_size")} onReset={canResetStartup("ctx_size") && !busy ? () => change("ctx_size", "") : undefined} {...startupReset("ctx_size")}><select aria-label="Advanced context mode" value={settings.ctx_size === "0" ? "full" : contextAuto ? "auto" : "fixed"} disabled={Boolean(busy)} onChange={event => change("ctx_size", event.target.value === "auto" ? "auto" : event.target.value === "full" ? "0" : String(contextShown ?? 32768))}><option value="fixed">Fixed</option><option value="auto">Auto</option><option value="full" disabled={!maximumContext}>Full</option></select></SettingRow>
        {!maximumContext ? <SettingRow layout="models" label="Context slider range" htmlFor="model-context-span" help="Display range only. Increasing it does not change Context or impose a runtime limit."><NumberField id="model-context-span" label="Context slider range" value={contextSpan} min={1024} step={1024} unit="tokens" disabled={Boolean(busy)} onChange={value => { if (value != null && value >= 1024) setContextSpan(value); }} /></SettingRow> : null}
        {field("threads", "CPU threads", "CPU threads used to generate responses. For a new model, the suggested count uses your physical CPU cores. Automatic lets the engine decide; it may not report the resolved count.", threadChoices, true, 1)}
        {field("threads_batch", "Prompt processing threads", "CPU threads used to process your prompt. When linked, uses the same count as generation.", threadChoices, true, 1)}
        {field("load_mode", "Model loading", "Automatic chooses how weights are read. Memory mapping reads files as needed; locking keeps pages in RAM and needs sufficient memory.", [{ value: "auto", label: "Automatic" }, { value: "mmap", label: "Memory mapped (mmap)" }, { value: "mmap+mlock", label: "Memory mapped + locked" }, { value: "mlock", label: "Loaded + locked in RAM" }, { value: "none", label: "Standard file loading" }, { value: "dio", label: "Direct disk access" }])}
        {field("batch_size", "Prompt batch size", "Maximum tokens processed together when reading a prompt. Larger batches can improve speed but use more memory.", numberChoices([128, 256, 512, 1024, 2048, 4096, 8192]), true, 1)}
        {field("ubatch_size", "Physical batch size", "Tokens handled in one computation batch. 0 uses the prompt batch size; the engine clamps larger values to it. Smaller values can reduce prompt-processing memory.", numberChoices([64, 128, 256, 512, 1024, 2048]), true, 0)}
      </SettingSection>
      <SettingSection title="Model behaviour">
        {field("spec_draft_n_max", "Draft tokens", "Maximum tokens drafted per step. Native MTP starts with three tokens.", descriptorOptions("spec_draft_n_max"), true, 1)}
        <details className="technical-details"><summary>Speculative decoding</summary><div className="setting-rows">
          {field("spec_draft_n_min", "Minimum draft tokens", "Minimum drafted tokens accepted before continuing generation.", numberChoices([0, 1, 2, 3]), true, 0)}
          {field("spec_draft_p_min", "Draft probability", "Minimum probability used by the native speculative decoder.", descriptorOptions("spec_draft_p_min"), true, 0, 1)}
          {field("spec_draft_p_split", "Draft split probability", "Probability threshold for branching speculative drafts.", descriptorOptions("spec_draft_p_split"), true, 0, 1)}
          {field("spec_draft_threads", "Draft CPU threads", "Generation threads for a separate draft model. -1 lets the engine choose.", threadChoices, true, -1)}
          {field("spec_draft_threads_batch", "Draft prompt threads", "Prompt processing threads for a separate draft model. -1 lets the engine choose.", threadChoices, true, -1)}
          {field("spec_draft_cache_type_k", "Draft K cache precision", "Attention-key precision for a separate draft model.", choices(cacheTypes))}
          {field("spec_draft_cache_type_v", "Draft V cache precision", "Attention-value precision for a separate draft model.", choices(cacheTypes))}
        </div></details>
        {field("op_offload", "Operation offload", "Offload supported operations to the GPU independently of model weight placement.", [{ value: "true", label: "On" }, { value: "false", label: "Off" }])}
        {field("mmproj_use_gpu", "Vision offload", "Run the selected vision projector on the GPU independently of model weight placement.", [{ value: "true", label: "GPU" }, { value: "false", label: "CPU" }])}
        {field("spec_draft_ngl", "Draft GPU layers", "GPU layers requested for a separate draft model.", [{ value: "auto", label: "Auto" }, ...numberChoices([0, 8, 16, 32])], true, 0)}
        {startupResolved("embedding") === "on" || settings.embedding === "on" ? field("pooling", "Embedding pooling", "Combines tokens into one vector for document search. Choose the method recommended by the model publisher.", choices(["last", "mean", "cls"])) : null}
      </SettingSection>
      <SettingSection title="Advanced settings">
        <SettingRow layout="models" label="Server port" htmlFor="model-port" help={<>Automatic chooses a free port when the model loads. Fixed ports are checked before starting.<code>--port</code></>} provenance={startupReadout("port")} onReset={canResetStartup("port") && !busy ? () => change("port", "") : undefined} {...startupReset("port")}>
          <NumberField id="model-port" label="Server port" value={settings.port} placeholder={typeof portResolved === "number" ? String(portResolved) : "Automatic"} min={1} max={65535} step={1} disabled={Boolean(busy)} onChange={value => change("port", value == null ? "" : String(value))} />
        </SettingRow>
        <SettingRow layout="models" stacked label="Additional settings" htmlFor="additional-startup" help="JSON for supported template and draft-model controls. Use the named controls above for settings already shown.">
          <textarea id="additional-startup" spellCheck={false} value={advancedStartup} onChange={event => { markDraftChanged(); setAdvancedStartup(event.target.value); }} placeholder="{}" />
        </SettingRow>
      </SettingSection></details></SettingSection></div>

    </form></section> : <EmptyState title="Choose a model to get started">Select one from your library, or add a new model.</EmptyState>}
    {inspector ? inspector.target && panelContent ? createPortal(panelContent, inspector.target) : null : panelContent ? <section className="model-inspector-inline">{panelContent}</section> : null}
  </section>;
}
