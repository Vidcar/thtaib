import { useEffect, useRef, useState, type ReactNode } from "react";
import { ModelDeletion } from "./ModelDeletion";
import type { ModelInspectorConnection } from "./ModelInspector";
import { api, ApiError } from "./api";
import { formatBytes } from "./display";
import { errorMessage } from "./errors";
import { ChoiceControl, ContextSlider, numberChoices, tokenLabel } from "./ModelControls";
import { NumberField, SettingRow, SettingSection } from "./CompactControls";
import { mergedStartup, startupPayload } from "./deploymentSettings";
import { EmptyState } from "./EmptyState";
import { Notice } from "./Notice";
import { SettingsNotes } from "./settingsNotes";
import { StatusBadge } from "./StatusBadge";
import { Icon } from "./Icon";
import { ResponseSettingsEditor } from "./ResponseSettingsEditor";
import { defaultSettingDisplay, effectiveSettingDisplay, settingValue } from "./effectiveSettings";
import type { EffectiveSetting } from "./effectiveSettings";
import { useSetupPreview } from "./effectiveSettings";
import { ModelProjectorControls } from "./ModelProjectorControls";
import { ModelChecks } from "./ModelChecks";
import { ModelResponseRecipes } from "./ModelResponseRecipes";
import { ModelHardwareEstimate } from "./ModelHardwareEstimate";
import { TypedStartupSettings } from "./TypedStartupSettings";

import { MenuPopover } from "./MenuPopover";
import { CompactDialog } from "./CompactDialog";
import type { BundleConfigurationOptions, Deployment, DeploymentProfileChanges, ModelBundle, ResponseRecipeOrigin, RunProfile, RuntimeManifest } from "./types";
import "./deploymentReadouts.css";

const cacheTypes = ["f16", "q8_0", "q4_0", "q4_1", "q5_0", "q5_1", "bf16", "f32", "iq4_nl"];
const choices = (values: string[]) => values.map(value => ({ value, label: value }));
const switches = [{ value: "on", label: "On" }, { value: "off", label: "Off" }];
const initialSettings: Record<string, string> = { ctx_size: "", n_gpu_layers: "", flash_attn: "", swa_full: "", fit: "", cache_type_k: "", cache_type_v: "", kv_offload: "", kv_unified: "", op_offload: "", mmproj_use_gpu: "", spec_draft_ngl: "", threads: "", threads_batch: "", load_mode: "", parallel: "", port: "", batch_size: "", ubatch_size: "", reasoning: "", reasoning_effort: "", reasoning_preserve: "", reasoning_format: "", reasoning_budget: "", embedding: "", pooling: "", spec_type: "", spec_draft_n_max: "", spec_draft_n_min: "", spec_draft_p_min: "", spec_draft_p_split: "", spec_draft_threads: "", spec_draft_threads_batch: "", spec_draft_cache_type_k: "", spec_draft_cache_type_v: "" };
const EMPTY_BUNDLES: ModelBundle[] = [];
const EMPTY_PROFILES: RunProfile[] = [];
type ModelDraft = { baseProfile: RunProfile | undefined; settings: Record<string, string>; response: Record<string, unknown>; agent: Record<string, unknown>; origin: ResponseRecipeOrigin | null; name: string; advanced: string; changed: string[]; presetApplied: boolean };
const draftKey = (bundle: string, profile: string) => `${bundle}:${profile || "default"}`;
const settingOverrides = (saved: Record<string, unknown>, candidate: Record<string, unknown>) => Object.fromEntries(
  [...new Set([...Object.keys(saved), ...Object.keys(candidate)])]
    .filter(key => JSON.stringify(saved[key]) !== JSON.stringify(candidate[key]))
    .map(key => [key, candidate[key] ?? null]));

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
  catalogueReady = true,
  onBundlesChanged,
  onDirtyModelsChange,
  active = true,
  openConfigurationId,
  openRequest,
  onBrowseModels,
  modelInformation,
}: {
  selectedBundleId?: string;
  bundlesVersion?: string;
  initialBundles?: ModelBundle[];
  initialProfiles?: RunProfile[];
  catalogueReady?: boolean;
  onBundlesChanged?: () => Promise<void>;
  onSelectBundle?: (id: string) => void;
  onDirtyModelsChange?: (ids: ReadonlySet<string>) => void;
  active?: boolean;
  inspector?: ModelInspectorConnection;
  openConfigurationId?: string;
  openRequest?: number;
  onBrowseModels?: () => void;
  modelInformation?: ReactNode;
} = {}) {
  const formRef = useRef<HTMLFormElement>(null);
  const selection = useRef(selectedBundleId); selection.current = selectedBundleId;
  const selectionOwner = useRef({ id: selectedBundleId, profile: "", generation: 0 });

  const hydrated = useRef({ bundle: "", deployment: "", profile: "", revision: 0 });
  const dirty = useRef(false);
  // Keep the authoring base through refreshes; only revert or confirmed Save replaces it.
  const draftProfile = useRef<RunProfile | undefined>(undefined);
  const drafts = useRef(new Map<string, ModelDraft>());
  const activeDraftKey = useRef("");
  const actionPending = useRef(false);
  const openedRequest = useRef("");
  const changedStartup = useRef(new Set<string>());
  const [runtime, setRuntime] = useState<RuntimeManifest | null>(null);
  const [deployments, setDeployments] = useState<Deployment[]>([]);
  const [profileId, setProfileId] = useState("");
  const catalogueProfiles = useRef(initialProfiles); catalogueProfiles.current = initialProfiles;
  const [acknowledgedProfile, setAcknowledgedProfile] = useState<{ record: RunProfile; catalogue: RunProfile[] } | null>(null);
  if (selectionOwner.current.id !== selectedBundleId || selectionOwner.current.profile !== profileId) selectionOwner.current = { id: selectedBundleId, profile: profileId, generation: selectionOwner.current.generation + 1 };
  const presetApplied = useRef(false);
  const presentation = useRef<{ selection: string; facts: Record<string, EffectiveSetting> }>({ selection: "", facts: {} });
  const [configurationName, setConfigurationName] = useState("");
  const [variantName, setVariantName] = useState("");
  const [creatingVariant, setCreatingVariant] = useState(false);
  const [setupDialog, setSetupDialog] = useState<"create" | "copy" | "rename" | "new" | null>(null);
  const renameCancelled = useRef(false);
  const [renamingModel, setRenamingModel] = useState(false);
  const [modelName, setModelName] = useState("");
  const [cardOpen, setCardOpen] = useState(false);
  const [memoryDetailsOpen, setMemoryDetailsOpen] = useState(false);
  const [deletingSetup, setDeletingSetup] = useState(false);
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
  const contextSpan = maximumContext ?? 262144;
  const [layers, setLayers] = useState<number | null>(null);
  const [threadChoices, setThreadChoices] = useState([{ value: "-1", label: "Auto" }, ...numberChoices([1, 2, 4, 6, 8, 12, 16, 24, 32])]);
  const [modelInfo, setModelInfo] = useState("Reading model limits…");
  const [advancedStartup, setAdvancedStartup] = useState("");
  const [message, setMessage] = useState("");
  const [messageTone, setMessageTone] = useState<"info" | "error" | "ok">("info");
  const [healthPollError, setHealthPollError] = useState("");
  const [loadError, setLoadError] = useState("");
  const [busy, setBusy] = useState("");
  const bundles = initialBundles;
  // A successful save is authoritative while its catalogue refresh is pending.
  // The next published catalogue replaces this temporary acknowledgement,
  // including when it no longer contains the record.
  const profiles = acknowledgedProfile?.catalogue === initialProfiles
    ? [...initialProfiles.filter(item => item.id !== acknowledgedProfile.record.id), acknowledgedProfile.record]
    : initialProfiles;
  useEffect(() => {
    if (acknowledgedProfile && acknowledgedProfile.catalogue !== initialProfiles) setAcknowledgedProfile(null);
  }, [initialProfiles, acknowledgedProfile]);
  const selectedProfile = profiles.find(item => item.id === profileId);
  const editorProfile = draftProfile.current?.id === profileId ? draftProfile.current : selectedProfile;
  const responseChanges = settingOverrides(selectedProfile?.bags.per_request.requested ?? {}, response);
  const selected = bundles.find(b => b.id === selectedBundleId);
  const editorReady = catalogueReady && hydrated.current.bundle === selectedBundleId;
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
  const candidateStartup = draftStartup(stagedStartup ?? {});
  const startupChanges = settingOverrides(selectedProfile?.bags.startup.requested ?? {}, candidateStartup);
  const optionsProfile = selectedProfile ?? profiles.find(item => item.id === selected?.default_configuration_id);
  const optionsSelection = JSON.stringify({ configuration_id: optionsProfile?.id ?? null, startup: settingOverrides(optionsProfile?.bags.startup.requested ?? {}, candidateStartup) });
  const canonical = (values: Record<string, unknown>) => JSON.stringify(Object.fromEntries(Object.keys(values).sort().map(key => [key, values[key]])));
  if (hydrated.current.bundle === selectedBundleId && hydrated.current.profile === profileId && draftProfile.current?.id === profileId) {
    dirty.current = presetApplied.current || Boolean(stagedStartupError) || canonical(mergedStartup(draftProfile.current.bags.startup.requested, stagedStartup ?? {})) !== canonical(draftProfile.current.bags.startup.requested)
      || canonical(response) !== canonical(draftProfile.current.bags.per_request.requested) || canonical(agentSettings) !== canonical(draftProfile.current.bags.agent.requested) || JSON.stringify(recipeOrigin) !== JSON.stringify(draftProfile.current.recipe_origin ?? null) || configurationName.trim() !== draftProfile.current.display_name;
    if (!dirty.current) drafts.current.delete(activeDraftKey.current);
  }
  // Resolve the retained draft against the current saved record. Differences
  // include external changes and removals; the draft still owns its authoring base.
  const setupPreview = useSetupPreview({ bundle_id: selectedBundleId || null, model_configuration_id: profileId || null,
    startup_overrides: startupChanges, per_request_overrides: responseChanges }, null, null, "conversation",
    `${bundlesVersion}:${selectedProfile?.revision ?? 0}:${selectedRunning?.updated_at ?? ""}:${configurationRevision}`, Boolean(active && editorReady && selectedBundleId && stagedStartup));
  const modelFacts = Object.fromEntries(Object.entries(setupPreview.data?.effective_values ?? {})
    .map(([key, fact]) => [key, fact.source === "Turn overrides" && key.startsWith("per_request.") && Object.hasOwn(responseChanges, key.slice(12))
      ? { ...fact, source: "Unsaved changes" }
      : fact.source === "Turn overrides" && key.startsWith("startup.") && Object.hasOwn(startupChanges, key.slice(8))
        ? { ...fact, source: "This editor" } : fact]));
  const responseFacts = modelFacts;
  const presentationSelection = `${selectedBundleId}:${profileId}`;
  if (setupPreview.data) presentation.current = { selection: presentationSelection, facts: modelFacts };
  const presentationFacts = presentation.current.selection === presentationSelection ? presentation.current.facts : {};
  const startupReadout = (key: string) => {
    const fact = modelFacts[`startup.${key}`];
    const display = stagedStartupError ? { value: "Check settings", source: stagedStartupError } : effectiveSettingDisplay(fact, setupPreview.loading);
    if (fact?.known && fact.supported !== false && !stagedStartupError && !setupPreview.loading) display.value = startupValueLabel(key, fact.value);
    const edited = stagedStartup && Object.hasOwn(stagedStartup, key);
    const saved = Object.hasOwn(editorProfile?.bags.startup.requested ?? {}, key);
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
    || (Object.hasOwn(editorProfile?.bags.startup.requested ?? {}, key) && stagedStartup?.[key] !== null);
  const startupReset = (key: string) => { const target = defaultSettingDisplay(modelFacts[`startup.${key}`], "model", key); return { resetLabel: "Reset", resetTitle: target.title }; };

  function publishDraftMarkers() {
    const ids = new Set([...drafts.current.keys()].map(key => key.split(":", 1)[0]));
    if (dirty.current && activeDraftKey.current) ids.add(activeDraftKey.current.split(":", 1)[0]);
    onDirtyModelsChange?.(ids);
  }
  function stashDraft() {
    if (!activeDraftKey.current || !dirty.current) return;
    drafts.current.set(activeDraftKey.current, { baseProfile: draftProfile.current, settings: { ...settings }, response: { ...response }, agent: { ...agentSettings }, origin: recipeOrigin, name: configurationName, advanced: advancedStartup, changed: [...changedStartup.current], presetApplied: presetApplied.current });
    publishDraftMarkers();
  }
  function restoreDraft(key: string): boolean {
    const draft = drafts.current.get(key);
    if (!draft) return false;
    activeDraftKey.current = key;
    draftProfile.current = draft.baseProfile;
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
    // Saved records own the draft. Runtime observations may arrive much later.
    if (!catalogueReady) return;
    const changedModel = hydrated.current.bundle !== selectedBundleId;
    const saved = changedModel ? profiles.find(item => item.id === selected?.default_configuration_id) : selectedProfile;
    if (!changedModel && profileId && !selectedProfile) { setMessageTone("error"); setMessage("The selected setup is no longer available. Choose another saved setup."); }
    const changedProfile = hydrated.current.profile !== (saved?.id ?? "") || hydrated.current.revision !== (saved?.revision ?? 0);
    const shouldHydrate = changedModel || (!dirty.current && changedProfile) || (selectedRunning && !dirty.current && hydrated.current.deployment !== selectedRunning.id);
    if (changedModel) { stashDraft(); dirty.current = false; setMessage(""); setProfileId(""); renameCancelled.current = true; setRenamingModel(false); setSetupDialog(null); setDeletingSetup(false); }
    if (changedModel) { setMemoryDetailsOpen(false); setCardOpen(false); setConfiguration(null); setMaximumContext(null); setLayers(null); setModelInfo("Loading model details…"); }
    if (shouldHydrate) {
    hydrated.current = { bundle: selectedBundleId, deployment: selectedRunning?.id ?? "", profile: saved?.id ?? "", revision: saved?.revision ?? 0 };
    draftProfile.current = saved;
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
    setConfigurationName(saved?.display_name ?? ""); setResponse(saved?.bags.per_request.requested ?? {}); setAgentSettings(saved?.bags.agent.requested ?? {}); setRecipeOrigin(saved?.recipe_origin ?? null);
    const starting = { ...initialSettings };
    const extra: Record<string, unknown> = {};
    const formStartup = saved?.bags.startup.requested ?? {};
    for (const [key, value] of Object.entries(formStartup)) {
      if (key in starting) starting[key] = key === "reasoning_preserve" ? value === true ? "keep" : value === false ? "drop" : "" : String(value);
      else extra[key] = value;
    }
    setSettings(starting); setAdvancedStartup(Object.keys(extra).length ? JSON.stringify(extra, null, 2) : "");
    }
    }
  // Load existing settings once per selection; stopping a model must not erase edits.
  }, [selectedBundleId, catalogueReady, selectedRunning?.id, profiles.length, selectedProfile?.id, selectedProfile?.revision, selected?.default_configuration_id]);
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
        if (!cancelled) {
          setHealthPollError("");
          setDeployments(records => records.map(record => updated.find(item => item.id === record.id) ?? record));
        }
      }).catch((failure: unknown) => {
        if (!cancelled) setHealthPollError(errorMessage(failure));
      }).finally(() => { inFlight = false; });
    }, 3000);
    return () => { cancelled = true; window.clearInterval(timer); };
  }, [deployments, active]);
  function markDraftChanged() { dirty.current = true; if (messageTone === "ok") setMessage(""); }
  function change(key: string, value: string) { markDraftChanged(); changedStartup.current.add(key); setSettings(previous => ({ ...previous, [key]: value })); }
  function changePlacement(mode: string) {
    change("n_gpu_layers", mode === "all" ? "all" : mode === "cpu" ? "0" : mode === "exact" ? String(Math.max(1, Math.floor((layers ?? 32) / 2))) : "auto");
  }
  function selectProfile(id: string, record?: RunProfile) {
    stashDraft();
    setMessage("");
    const key = draftKey(selectedBundleId, id);
    const profile = record ?? profiles.find(item => item.id === id);
    hydrated.current = { ...hydrated.current, profile: id, revision: profile?.revision ?? 0 };
    draftProfile.current = profile;
    activeDraftKey.current = key;
    dirty.current = false;
    presetApplied.current = false;
    changedStartup.current = new Set();
    setProfileId(id);
    if (restoreDraft(key)) return;
    setConfigurationName(profile?.display_name ?? ""); setResponse(profile?.bags.per_request.requested ?? {}); setAgentSettings(profile?.bags.agent.requested ?? {}); setRecipeOrigin(profile?.recipe_origin ?? null); setCreatingVariant(false);
    const next = { ...initialSettings }, extra: Record<string, unknown> = {};
    for (const [key, value] of Object.entries(profile?.bags.startup.requested ?? {})) {
      if (key in next) next[key] = key === "reasoning_preserve" ? value === true ? "keep" : value === false ? "drop" : "" : String(value);
      else extra[key] = value;
    }
    setSettings(next); setAdvancedStartup(Object.keys(extra).length ? JSON.stringify(extra, null, 2) : "");
  }
  useEffect(() => {
    if (!active || !editorReady || !openConfigurationId || !profiles.some(profile => profile.id === openConfigurationId && profile.bundle_id === selectedBundleId)) return;
    const request = `${openRequest ?? 0}:${openConfigurationId}`;
    if (openedRequest.current === request) return;
    openedRequest.current = request;
    selectProfile(openConfigurationId);
  }, [active, editorReady, openConfigurationId, openRequest, selectedBundleId, profiles]);
  async function action(key: string, operation: () => Promise<unknown>) {
    if (actionPending.current) return;
    actionPending.current = true;
    const owner = selectionOwner.current;
    setBusy(key); setMessage("");
    try { await operation(); } catch (error) { if (selectionOwner.current === owner) { setMessage(errorMessage(error)); setMessageTone("error"); } } finally { actionPending.current = false; setBusy(""); }
  }
  function startup(): Record<string, unknown> {
    const saved = editorProfile?.bags.startup.requested ?? {};
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
  function draftStartup(overrides = startup()): Record<string, unknown> {
    return mergedStartup(editorProfile?.bags.startup.requested ?? {}, overrides);
  }
  async function preview(startupValues = draftStartup(), responseValues = response) {
    const report = await api.previewSettings(startupValues, responseValues, agentSettings);
    const result = { ...report, per_request: { ...report.per_request,
      unsupported: [...new Set([...report.per_request.unsupported, ...Object.keys(responseValues).filter(key => configuration?.per_request_defaults[key]?.supported === false)])] } };
    if (result.startup.unsupported.length || result.startup.retired.length || result.per_request.unsupported.length || result.per_request.retired.length) throw new Error("Some settings are unsupported. Review the affected controls.");
    return result;
  }
  function configurationPayload(asVariant = false) {
    const name = (asVariant ? variantName : configurationName).trim();
    if (!name) throw new Error("Enter a configuration name.");
    return {
      display_name: name,
      startup: draftStartup(), per_request: response, agent: agentSettings,
      recipe_origin: recipeOrigin,
      ...(asVariant ? {} : { configuration_id: profileId || undefined, expected_revision: draftProfile.current?.revision }),
    };
  }
  async function persistConfiguration(payload: ReturnType<typeof configurationPayload>, asVariant: boolean, owner: typeof selectionOwner.current) {
    const saved = await api.saveModelConfiguration(owner.id, payload).catch(failure => {
      if (failure instanceof ApiError && failure.code === "configuration_revision_conflict") {
        throw new Error("This setup changed elsewhere. Revert edits to use its latest saved values, or Save a copy to keep your draft.");
      }
      throw failure;
    });
    if (selectionOwner.current === owner) {
      setAcknowledgedProfile({ record: saved, catalogue: catalogueProfiles.current });
      drafts.current.delete(activeDraftKey.current);
      activeDraftKey.current = draftKey(owner.id, saved.id);
      draftProfile.current = saved;
      setProfileId(saved.id); setConfigurationName(saved.display_name); changedStartup.current.clear(); dirty.current = false; presetApplied.current = false;
      publishDraftMarkers();
      setCreatingVariant(false); setVariantName("");
    }
    const savedLabel = asVariant ? "Copy saved." : "Saved.";
    try {
      await onBundlesChanged?.();
      await refresh();
    } catch (error) {
      throw new Error(`${savedLabel} The screen could not refresh. ${errorMessage(error)}`);
    }
    if (selectionOwner.current === owner) { setMessageTone("ok"); setMessage(savedLabel); }
    return saved;
  }
  async function saveConfiguration(asVariant = false) {
    const payload = configurationPayload(asVariant), owner = selectionOwner.current;
    await preview(payload.startup, payload.per_request);
    return persistConfiguration(payload, asVariant, owner);
  }
  async function refreshAfterUserAction(failure: unknown): Promise<void> {
    try {
      await refresh();
    } catch (error) {
      const refreshError = `The model list could not refresh. ${errorMessage(error)}`;
      throw failure ? new Error(`${errorMessage(failure)} ${refreshError}`) : new Error(refreshError);
    }
    if (failure) throw failure;
  }
  async function loadSavedSetup() {
    if (!selectedProfile) throw new Error("Save this setup before loading it.");
    const owner = selectionOwner.current;
    let failure: unknown;
    try {
      const result = await api.loadSavedModelSetup(owner.id, selectedProfile.id);
      if (result.status === "failed" || result.error) throw new Error(result.error ?? "Model could not load.");
      if (selectionOwner.current === owner) { setMessageTone("ok"); setMessage(result.health?.healthy ? "Saved setup loaded." : "Loading saved setup…"); }
    } catch (error) {
      failure = error;
    }
    await refreshAfterUserAction(failure);
  }
  async function reloadRunningModel() {
    if (!selectedActive) throw new Error("No running model to reload.");
    const owner = selectionOwner.current;
    let failure: unknown;
    try {
      const result = await api.reload(selectedActive.id);
      if (result.status === "failed" || result.error) throw new Error(result.error ?? "Model could not reload.");
      if (selectionOwner.current === owner) { setMessageTone("ok"); setMessage(result.health?.healthy ? "Model reloaded." : "Reloading…"); }
    } catch (error) {
      failure = error;
    }
    await refreshAfterUserAction(failure);
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
  const contextResolvedRaw = startupResolved("ctx_size");
  const contextResolved = typeof contextResolvedRaw === "number" ? contextResolvedRaw : null;
  const portResolved = startupResolved("port");
  const contextAuto = settings.ctx_size === "auto" || settings.ctx_size === "" && !changedStartup.current.has("ctx_size") && startupResolved("ctx_size") === "auto";
  const contextShown = contextAuto ? null : settings.ctx_size === "0" || settings.ctx_size === "" && contextResolved === 0 ? maximumContext : settings.ctx_size !== "" && Number.isFinite(Number(settings.ctx_size)) && Number(settings.ctx_size) > 0 ? Number(settings.ctx_size) : contextResolved && contextResolved > 0 ? contextResolved : null;
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
  const toolbarMessage = messageTone === "ok" && creatingVariant ? "" : message;
  const modelProfiles = profiles.filter(item => item.bundle_id === selectedBundleId);
  const speculationModes = descriptorOptions("spec_type");
  const contextMode = settings.ctx_size === "0" ? "full" : contextAuto ? "auto" : "fixed";
  async function saveSetupDialog() {
    if (!variantName.trim() || !selected) return;
    const owner = selectionOwner.current;
    if (setupDialog === "create") {
      const saved = await api.saveModelConfiguration(selected.id, { display_name: variantName.trim(), startup: {}, per_request: {}, agent: {} });
      drafts.current.delete(draftKey(selected.id, saved.id));
      if (selectionOwner.current === owner) { setAcknowledgedProfile({ record: saved, catalogue: catalogueProfiles.current }); selectProfile(saved.id, saved); }
      await onBundlesChanged?.(); await refresh();
    } else if (setupDialog === "rename") {
      if (!selectedProfile) throw new Error("Choose a saved setup first.");
      const saved = await api.saveModelConfiguration(owner.id, { display_name: variantName.trim(), configuration_id: selectedProfile.id, expected_revision: selectedProfile.revision, startup: selectedProfile.bags.startup.requested, per_request: selectedProfile.bags.per_request.requested, agent: selectedProfile.bags.agent.requested, recipe_origin: selectedProfile.recipe_origin });
      if (selectionOwner.current === owner) { setAcknowledgedProfile({ record: saved, catalogue: catalogueProfiles.current }); draftProfile.current = draftProfile.current ? { ...draftProfile.current, revision: draftProfile.current.revision === selectedProfile.revision ? saved.revision : draftProfile.current.revision, display_name: saved.display_name } : saved; setConfigurationName(saved.display_name); }
      await onBundlesChanged?.(); await refresh();
    } else {
      await saveConfiguration(true);
    }
    if (selectionOwner.current.id === owner.id) { setSetupDialog(null); setCreatingVariant(false); setVariantName(""); }
  }
  return <section className="model-configuration">
    {selected && !editorReady ? <p role="status">Loading saved setups…</p> : selected ? <section className="model-setup" aria-label="Selected model">
      <header className="model-refresh-header">
        <div className="model-title-line">
          <button type="button" className="icon-button models-browse-button" aria-label="Browse models" onClick={onBrowseModels}><Icon name="panel" /></button>
          {renamingModel ? <input className="model-rename-input" aria-label="Rename model" autoFocus value={modelName} maxLength={160} onChange={event => setModelName(event.target.value)} onKeyDown={event => { if (event.key === "Escape") { renameCancelled.current = true; setRenamingModel(false); } if (event.key === "Enter") { event.preventDefault(); event.currentTarget.blur(); } }} onBlur={() => { setRenamingModel(false); if (!renameCancelled.current && modelName.trim() && modelName.trim() !== selected.display_name) void action("rename-model", async () => { await api.renameModel(selected.id, modelName.trim()); await onBundlesChanged?.(); }); }} /> : <h3 className="selected-model-name" title={selected.display_name}>{selected.display_name}</h3>}
          <button type="button" className="icon-button" aria-label="Rename model" title="Rename model" disabled={Boolean(busy)} onClick={() => { renameCancelled.current = false; setModelName(selected.display_name); setRenamingModel(true); }}><Icon name="edit" size={16} /></button>
          {selected.source.repo_id ? <button type="button" className="icon-button" aria-label="Model card" title="Model card" onClick={() => setCardOpen(true)}><Icon name="knowledge" /></button> : null}
          <ModelChecks refreshVersion={`${selectedRunning?.id ?? ""}:${selectedRunning?.updated_at ?? ""}`} profile={selectedProfile} active={active} disabled={Boolean(busy) || !profileId || !runtimeReady || !selected.disk_matches} onReloaded={refresh} />
          <span className="model-runtime-pill" data-state={selectedRunning ? "ready" : selectedActive ? "loading" : "idle"}>{!loaded ? loadError ? "Unavailable" : "Checking…" : selectedRunning ? "Ready" : selectedActive ? "Loading…" : "Not loaded"}</span>
        </div>
        <p className="model-refresh-subtitle" title={selected.primary_path ?? ""}>{selected.source.repo_id?.split("/")[0] ?? "Local model"} · {selected.quantization ?? "GGUF"}</p>
        <div className="model-setup-toolbar">
          {modelProfiles.length > 1 ? <><label className="visually-hidden" htmlFor="model-configuration">Saved setup</label><select id="model-configuration" aria-label="Saved setup" value={profileId} disabled={Boolean(busy)} onChange={event => selectProfile(event.target.value)}><option value="">Choose a saved setup</option>{modelProfiles.map(profile => <option key={profile.id} value={profile.id}>{profile.display_name}{selected.default_configuration_id === profile.id ? " · preferred" : ""}</option>)}</select></> : modelProfiles.length === 1 ? <button type="button" className="model-single-setup text-button" disabled={Boolean(busy)} onClick={() => selectProfile(modelProfiles[0].id)}>{selectedProfile ? selectedProfile.display_name : "Choose " + modelProfiles[0].display_name}</button> : <span className="model-new-setup-label">New setup</span>}
          <button type="button" className="text-button" disabled={Boolean(busy)} onClick={() => { setVariantName(""); setSetupDialog("create"); }}>Create</button>
          <button type="button" className="text-button" disabled={Boolean(busy) || !selectedProfile} onClick={() => setDeletingSetup(true)}>Delete</button>
          <MenuPopover label="Setup actions" panelClassName="models-menu model-setup-actions" placement="below" align="end" trigger={<Icon name="more" size={16} />} disabled={Boolean(busy) || !selectedProfile}>
            {close => <><button type="button" onClick={() => { setVariantName(configurationName); setSetupDialog("rename"); close(); }}>Rename setup</button><button type="button" onClick={() => { setVariantName(configurationName + " copy"); setCreatingVariant(true); setSetupDialog("copy"); close(); }}>Save a copy</button>{selectedProfile && selected.default_configuration_id !== selectedProfile.id ? <button type="button" onClick={() => { close(); void action("default", async () => { await api.setDefaultConfiguration(selected.id, selectedProfile.id); await onBundlesChanged?.(); }); }}>Make preferred</button> : null}<button type="button" disabled={!dirty.current} onClick={() => { drafts.current.delete(activeDraftKey.current); dirty.current = false; presetApplied.current = false; selectProfile(profileId); close(); }}>Revert edits</button></>}
          </MenuPopover>
        </div>
      </header>
      <div className="model-toolbar-status" role="status" data-tone={stagedStartupError || setupPreview.error || loadError || healthPollError ? "error" : messageTone}>{stagedStartupError || toolbarMessage || setupPreview.error || loadError || healthPollError || (!loaded ? "Checking local engine…" : !runtimeReady ? "Set up the local engine in Settings" : "\u00a0")}{loadError ? <button type="button" className="text-button" onClick={() => void refresh()}>Retry</button> : null}</div>
      {cardOpen ? <CompactDialog title="Model card" labelledBy="model-card-dialog-title" onClose={() => setCardOpen(false)}><ModelResponseRecipes key={selected.id} bundle={selected} profiles={modelProfiles} onChanged={async () => { await onBundlesChanged?.(); await refresh(); }} panel /></CompactDialog> : null}
      {setupDialog ? <CompactDialog title={setupDialog === "create" ? "Create setup" : setupDialog === "rename" ? "Rename setup" : setupDialog === "new" ? "Save setup" : "Save a setup copy"} labelledBy="setup-copy-title" busy={Boolean(busy)} onClose={() => { setSetupDialog(null); setCreatingVariant(false); }}><label htmlFor="model-variant-name">Setup name</label><input autoFocus id="model-variant-name" value={variantName} maxLength={160} onChange={event => setVariantName(event.target.value)} /><button type="button" className="primary-button" disabled={Boolean(busy) || !variantName.trim()} onClick={() => void action("save", saveSetupDialog)}>{setupDialog === "create" ? "Create" : "Save"}</button></CompactDialog> : null}
      {deletingSetup && selectedProfile ? <CompactDialog title="Delete setup" labelledBy="setup-delete-title" busy={Boolean(busy)} onClose={() => setDeletingSetup(false)}><ModelDeletion kind="profile" id={selectedProfile.id} name={selectedProfile.display_name} initialOpen onDeleted={async () => { drafts.current.delete(activeDraftKey.current); dirty.current = false; setDeletingSetup(false); draftProfile.current = undefined; hydrated.current.profile = ""; setProfileId(""); await onBundlesChanged?.(); }} /></CompactDialog> : null}
      {profileId || !modelProfiles.length ? <form id="model-settings-form" ref={formRef} className="model-settings" onSubmit={event => { event.preventDefault(); if (formRef.current?.reportValidity()) { if (profileId) void action("save", () => saveConfiguration()); else { setVariantName(""); setSetupDialog("new"); } } }}>
      <div className="model-settings-scroll"><div className="model-settings-columns">
        <SettingSection title="Generation">
          <ResponseSettingsEditor layout="models" presentationFacts={presentationFacts} part="thinking" value={response} onChange={next => { markDraftChanged(); setResponse(next); }} facts={responseFacts} options={configuration} disabled={Boolean(busy)} inheritance="model" loading={setupPreview.loading} />
          <ResponseSettingsEditor layout="models" presentationFacts={presentationFacts} part="sampling" value={response} onChange={next => { markDraftChanged(); setResponse(next); }} facts={responseFacts} options={configuration} disabled={Boolean(busy)} inheritance="model" loading={setupPreview.loading} />
          <details className="models-disclosure"><summary>Model instructions <span className="models-show-hide" /></summary><SettingRow layout="models" stacked label="Instructions" htmlFor="model-authored-instructions" help="Optional instructions supplied by this saved setup." onReset={agentSettings.system_prompt && !busy ? () => { const next = { ...agentSettings }; delete next.system_prompt; markDraftChanged(); setAgentSettings(next); } : undefined}><textarea id="model-authored-instructions" rows={3} value={String(agentSettings.system_prompt ?? "")} disabled={Boolean(busy)} onChange={event => { markDraftChanged(); setAgentSettings(event.target.value ? { ...agentSettings, system_prompt: event.target.value } : Object.fromEntries(Object.entries(agentSettings).filter(([key]) => key !== "system_prompt"))); }} /></SettingRow></details>
        </SettingSection>
        <SettingSection title="Loading">
          <SettingRow layout="models" className="model-context-row" label="Context" htmlFor="model-context-number" help={<><span>Total context pool in tokens, shared by parallel requests. {modelInfo}</span><code>--ctx-size</code></>} provenance={startupReadout("ctx_size")} onReset={canResetStartup("ctx_size") && !busy ? () => change("ctx_size", "") : undefined} {...startupReset("ctx_size")}>
            <div className="model-context-inline"><select aria-label="Context mode" value={contextMode} disabled={Boolean(busy)} onChange={event => change("ctx_size", event.target.value === "auto" ? "auto" : event.target.value === "full" ? "0" : String(contextShown ?? 32768))}><option value="auto">Auto</option><option value="full" disabled={!maximumContext}>Full</option><option value="fixed">Fixed</option></select><ContextSlider id="model-ctx-size" value={contextShown} maximum={maximumContext} span={contextSpan} unknownLabel={contextAuto ? "Auto" : "Not reported"} disabled={Boolean(busy) || contextMode !== "fixed"} onChange={value => change("ctx_size", String(value))} /><NumberField id="model-context-number" label="Exact context" value={contextMode === "fixed" ? contextShown : null} placeholder={contextMode === "auto" ? "Auto" : "Full"} min={1} max={maximumContext ?? undefined} step={1} disabled={Boolean(busy) || contextMode !== "fixed"} onChange={value => change("ctx_size", value == null ? "" : String(value))} /></div>
          </SettingRow>
          <SettingRow layout="models" label="GPU layers" help={<><span>Weight placement; other offloads stay independent.</span><code>--n-gpu-layers</code></>} provenance={startupReadout("n_gpu_layers")} onReset={canResetStartup("n_gpu_layers") && !busy ? () => change("n_gpu_layers", "") : undefined} {...startupReset("n_gpu_layers")}><div className="model-placement-control"><select aria-label="GPU layers" value={gpuMode} disabled={Boolean(busy)} onChange={event => changePlacement(event.target.value)}><option value="auto">Auto</option><option value="all">All</option><option value="cpu">CPU</option><option value="exact">Exact</option></select><span className="model-gpu-exact" data-active={gpuMode === "exact"}><NumberField label="Exact GPU layers" min={1} max={layers ?? undefined} step={1} value={gpuMode === "exact" ? gpuValue : null} disabled={Boolean(busy) || gpuMode !== "exact"} onChange={value => change("n_gpu_layers", value == null ? "custom" : String(value))} /></span></div></SettingRow>
          {field("cache_type_k", "K cache precision", "Stores attention keys.", choices(cacheTypes))}
          {field("cache_type_v", "V cache precision", "Stores attention values; some precisions need Flash attention.", choices(cacheTypes))}
          {field("flash_attn", "Flash attention", "Faster attention when supported.", [{ value: "auto", label: "Auto" }, ...switches])}
          {field("spec_type", "Speculation", "Uses supported drafting to propose tokens ahead.", speculationModes.length ? speculationModes.map(item => ({ ...item, label: item.value === "none" ? "Off" : item.value === "draft-mtp" ? "Built-in MTP" : item.label })) : [{ value: "none", label: "Off" }])}
          <details className="models-disclosure"><summary>Cache &amp; processing <span className="models-show-hide" /></summary><div className="setting-rows">
            {field("kv_offload", "Cache placement", "Cache placement is independent of weights.", [{ value: "true", label: "GPU" }, { value: "false", label: "CPU" }])}
            {field("fit", "Memory fitting", "Fits loading values not fixed explicitly.", switches)}
            {field("parallel", "Parallel slots", "Auto shares one context pool across four slots.", [{ value: "-1", label: "Auto" }, ...numberChoices([1, 2, 4, 8])], true, -1)}
            {field("kv_unified", "Shared context", "Shares KV storage between slots.", [{ value: "true", label: "On" }, { value: "false", label: "Off" }])}
            {field("batch_size", "Prompt batch", "Logical prompt batch in tokens.", numberChoices([128, 512, 2048, 8192]), true, 1)}
            {field("ubatch_size", "Physical batch", "Physical compute batch. Zero uses prompt batch.", numberChoices([0, 128, 512, 2048]), true, 0)}
            {field("threads", "CPU threads", "Generation threads. Auto lets the engine choose.", threadChoices, true, -1)}
            {field("threads_batch", "Prompt threads", "Prompt processing threads.", threadChoices, true, -1)}
          </div></details>
          <details className="models-disclosure"><summary>Advanced loading <span className="models-show-hide" /></summary><div className="setting-rows">
            {field("load_mode", "Model loading", "How model weights are read.", descriptorOptions("load_mode").length ? descriptorOptions("load_mode") : choices(["auto", "none", "mmap", "mlock", "mmap+mlock", "dio"]))}
            {configuration?.startup_defaults.swa_full ? field("swa_full", "Full sliding cache", "Allocate full sliding-window cache.", [{ value: "true", label: "On" }, { value: "false", label: "Off" }]) : null}
            {field("op_offload", "Operation offload", "GPU operation offload independently of weights.", [{ value: "true", label: "On" }, { value: "false", label: "Off" }])}
            {field("mmproj_use_gpu", "Vision offload", "Where the vision projector runs.", [{ value: "true", label: "GPU" }, { value: "false", label: "CPU" }])}
            {field("embedding", "Model role", "Chat or document-search embeddings.", [{ value: "off", label: "Chat" }, { value: "on", label: "Embeddings" }])}
            {startupResolved("embedding") === "on" || settings.embedding === "on" ? field("pooling", "Embedding pooling", "Combines tokens into one vector.", choices(["last", "mean", "cls"])) : null}
            <SettingRow layout="models" label="Server port" htmlFor="model-port" help={<><span>Automatic chooses a free local port.</span><code>--port</code></>} provenance={startupReadout("port")} onReset={canResetStartup("port") && !busy ? () => change("port", "") : undefined}><NumberField id="model-port" label="Server port" value={settings.port} placeholder={typeof portResolved === "number" ? String(portResolved) : "Auto"} min={1} max={65535} step={1} disabled={Boolean(busy)} onChange={value => change("port", value == null ? "" : String(value))} /></SettingRow>
            <TypedStartupSettings value={advancedStartup} options={configuration} disabled={Boolean(busy)} onChange={value => { markDraftChanged(); setAdvancedStartup(value); }} onError={setMessage} />
          </div></details>
          {String(settings.spec_type || startupResolved("spec_type") || "none") !== "none" ? <details className="models-disclosure"><summary>Draft settings <span className="models-show-hide" /></summary><div className="setting-rows">
            {field("spec_draft_n_max", "Draft tokens", "Maximum tokens drafted per step.", descriptorOptions("spec_draft_n_max"), true, 1)}
            {field("spec_draft_n_min", "Minimum draft", "Minimum accepted draft tokens.", numberChoices([0, 1, 2, 3]), true, 0)}
            {field("spec_draft_p_min", "Draft probability", "Minimum probability for drafting.", descriptorOptions("spec_draft_p_min"), true, 0, 1)}
            {field("spec_draft_p_split", "Split probability", "Draft branching probability.", descriptorOptions("spec_draft_p_split"), true, 0, 1)}
            {field("spec_draft_threads", "Draft CPU threads", "Generation threads for a separate draft.", threadChoices, true, -1)}
            {field("spec_draft_threads_batch", "Draft prompt threads", "Prompt processing threads for a separate draft.", threadChoices, true, -1)}
            {field("spec_draft_ngl", "Draft GPU layers", "Requested GPU layers for a separate draft.", [{ value: "auto", label: "Auto" }, { value: "all", label: "All" }, ...numberChoices([0, 8, 16, 32])], true, 0)}
            {field("spec_draft_cache_type_k", "Draft K precision", "Draft attention-key cache precision.", choices(cacheTypes))}
            {field("spec_draft_cache_type_v", "Draft V precision", "Draft attention-value cache precision.", choices(cacheTypes))}
          </div></details> : null}
          <details className="models-disclosure" onToggle={event => setMemoryDetailsOpen(event.currentTarget.open)}><summary>Memory details <span className="models-show-hide" /></summary><ModelHardwareEstimate selection={{ bundle_id: selectedBundleId, startup: candidateStartup }} active={active && memoryDetailsOpen && !stagedStartupError} /></details>
          <details className="models-disclosure"><summary>Files &amp; maintenance <span className="models-show-hide" /></summary>{modelInformation}<button type="button" disabled={Boolean(busy)} onClick={() => void action("metadata", async () => { applyConfiguration(await api.modelConfiguration(selectedBundleId, selectedRunning?.id, true, { configuration_id: selectedProfile?.id ?? null, startup: startupChanges })); })}>Refresh model details</button><ModelProjectorControls key={"projector:" + selected.id} bundleId={selected.id} active={bundleActive} disabled={Boolean(busy)} action={action} onSaved={async () => { await onBundlesChanged?.(); await refresh(); }} /></details>
          <details className="models-disclosure"><summary>Loaded model <span className="models-show-hide" /></summary>{selectedActive ? <button type="button" disabled={Boolean(busy)} onClick={() => void action("reload", reloadRunningModel)}>Reload saved setup</button> : null}{selectedCurrent.length ? <ul className="plain-list">{selectedCurrent.map(renderDeployment)}</ul> : <p className="hint">This setup is not loaded.</p>}{otherVariants.length ? <details><summary>Other loaded setups</summary><ul className="plain-list">{otherVariants.map(renderDeployment)}</ul></details> : null}{history.length ? <details><summary>Runtime history</summary><ul className="plain-list">{history.map(renderDeployment)}</ul></details> : null}</details>
        </SettingSection>
      </div></div>
      <footer className="model-refresh-footer"><div className="model-save-state" data-dirty={dirty.current}><Icon name={dirty.current ? "edit" : "check"} /><span><strong>{!profileId ? "Setup not saved" : dirty.current ? "Unsaved edits" : "Setup saved"}</strong><small>{configurationName}</small></span></div><div className="model-footer-actions"><button type="submit" disabled={Boolean(busy) || Boolean(profileId) && !dirty.current}>{busy === "save" ? "Saving…" : "Save"}</button>{selectedActive ? <button type="button" disabled={Boolean(busy)} onClick={() => void action("unload", async () => { await api.stop(selectedActive.id); await refresh(); })}>Unload</button> : null}<button type="button" className="primary-button" title="Load this saved setup. Unsaved edits stay in this editor." disabled={Boolean(busy) || !selectedProfile || !runtimeReady || !selected.disk_matches} onClick={() => void action("load", loadSavedSetup)}>{busy === "load" ? "Loading…" : dirty.current ? "Load saved" : "Load"}</button></div></footer>
      </form> : <div className="model-empty-setup"><EmptyState title={modelProfiles.length ? "Choose a saved setup" : "Create your first setup"}>A named setup keeps the settings you want to load.<button type="button" onClick={() => { setVariantName(""); setSetupDialog("create"); }}>Create setup</button></EmptyState><details className="models-disclosure"><summary>Files &amp; maintenance <span className="models-show-hide" /></summary>{modelInformation}</details></div>}
    </section> : <EmptyState title="Choose a model to get started">Select one from your library, or add a new model.</EmptyState>}
  </section>;
}
