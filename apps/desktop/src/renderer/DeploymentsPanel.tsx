import { useEffect, useRef, useState, type CSSProperties } from "react";
import { api, DEFAULT_EMBEDDING_STARTUP } from "./api";
import { formatBytes } from "./display";
import { errorMessage } from "./errors";
import { ChoiceControl, numberChoices, tokenLabel } from "./ModelControls";
import { CompactSlider, CompactSwitch, NumberField, SegmentedChoice, SettingRow, SettingSection } from "./CompactControls";
import { mergedStartup, startupPayload } from "./deploymentSettings";
import { EmptyState } from "./EmptyState";
import { Notice } from "./Notice";
import { SettingsNotes } from "./settingsNotes";
import { StatusBadge } from "./StatusBadge";
import { Icon } from "./Icon";
import { ModelCapabilities } from "./ModelCapabilities";
import { ResponseSettingsEditor } from "./ResponseSettingsEditor";
import { effectiveSettingDisplay, settingValue } from "./effectiveSettings";
import { useSetupPreview } from "./effectiveSettings";
import { ModelProjectorControls } from "./ModelProjectorControls";
import type { BundleConfigurationOptions, Deployment, DeploymentProfileChanges, ModelBundle, RunProfile, RuntimeManifest, SettingsBags } from "./types";
import "./deploymentReadouts.css";

const cacheTypes = ["f16", "q8_0", "q4_0", "q4_1", "q5_0", "q5_1", "bf16", "f32", "iq4_nl"];
const choices = (values: string[]) => values.map(value => ({ value, label: value }));
const switches = [{ value: "on", label: "On" }, { value: "off", label: "Off" }];
const initialSettings: Record<string, string> = { ctx_size: "", n_gpu_layers: "", flash_attn: "", fit: "", cache_type_k: "", cache_type_v: "", threads: "", threads_batch: "", load_mode: "", parallel: "", port: "", batch_size: "", ubatch_size: "", reasoning: "", reasoning_effort: "", reasoning_preserve: "", reasoning_format: "", reasoning_budget: "", embedding: "", pooling: "", spec_type: "", spec_draft_n_max: "" };
const EMPTY_BUNDLES: ModelBundle[] = [];
const EMPTY_PROFILES: RunProfile[] = [];
type ModelDraft = { settings: Record<string, string>; response: Record<string, unknown>; name: string; advanced: string; changed: string[] };
const draftKey = (bundle: string, profile: string) => `${bundle}:${profile || "default"}`;

function startupValueLabel(key: string, value: unknown): string {
  if (key === "ctx_size" && typeof value === "number") return `${value.toLocaleString()} tokens`;
  if (key === "n_gpu_layers") return value === -1 || value === "-1" || value === "auto" ? "Automatic fit" : value === "all" ? "All layers requested" : value === 0 ? "CPU only" : typeof value === "number" ? `${value} layers requested` : settingValue(value);
  if (key === "spec_type" && value === "none") return "Off";
  if (key === "reasoning_budget" && value === -1) return "Unrestricted";
  if (key === "reasoning_preserve") return value === true ? "Keep" : value === false ? "Drop" : settingValue(value);
  if (key === "embedding") return value === "on" ? "Document search" : value === "off" ? "Chat" : settingValue(value);
  return settingValue(value);
}

function contextSteps(offered: number[], maximum: number | null): number[] {
  const values = offered.filter(value => Number.isFinite(value) && value > 0 && (!maximum || value <= maximum));
  if (values.length >= 2) return [...new Set(values)].sort((a, b) => a - b);
  const steps: number[] = [];
  for (let value = 2048; value <= (maximum && maximum > 0 ? maximum : 131072); value *= 2) steps.push(value);
  if (maximum && maximum > 0 && steps.at(-1) !== maximum) steps.push(maximum);
  return steps;
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
}: {
  selectedBundleId?: string;
  bundlesVersion?: string;
  initialBundles?: ModelBundle[];
  initialProfiles?: RunProfile[];
  onBundlesChanged?: () => Promise<void>;
  onSelectBundle?: (id: string) => void;
  onDirtyModelsChange?: (ids: ReadonlySet<string>) => void;
} = {}) {
  const formRef = useRef<HTMLFormElement>(null);
  const selection = useRef(selectedBundleId); selection.current = selectedBundleId;
  const selectionOwner = useRef({ id: selectedBundleId, generation: 0 });
  if (selectionOwner.current.id !== selectedBundleId) selectionOwner.current = { id: selectedBundleId, generation: selectionOwner.current.generation + 1 };
  const hydrated = useRef({ bundle: "", deployment: "", profile: "", revision: 0 });
  const dirty = useRef(false);
  const drafts = useRef(new Map<string, ModelDraft>());
  const activeDraftKey = useRef("");
  const actionPending = useRef(false);
  const changedStartup = useRef(new Set<string>());
  const [runtime, setRuntime] = useState<RuntimeManifest | null>(null);
  const [deployments, setDeployments] = useState<Deployment[]>([]);
  const [profileId, setProfileId] = useState("");
  const [configurationName, setConfigurationName] = useState("");
  const [variantName, setVariantName] = useState("");
  const [creatingVariant, setCreatingVariant] = useState(false);
  const [response, setResponse] = useState<Record<string, unknown>>({});
  const [logs, setLogs] = useState<Record<string, string>>({});
  const [generation, setGeneration] = useState<Record<string, string>>({});
  const [profileChanges, setProfileChanges] = useState<Record<string, DeploymentProfileChanges>>({});
  const [loaded, setLoaded] = useState(false);
  const [settings, setSettings] = useState({ ...initialSettings });
  const [configuration, setConfiguration] = useState<BundleConfigurationOptions | null>(null);
  const [configurationRevision, setConfigurationRevision] = useState(0);
  const [maximumContext, setMaximumContext] = useState<number | null>(null);
  const [layers, setLayers] = useState<number | null>(null);
  const [threadChoices, setThreadChoices] = useState(numberChoices([1, 2, 4, 6, 8, 12, 16, 24, 32]));
  const [modelInfo, setModelInfo] = useState("Reading model limits…");
  const [endpoint, setEndpoint] = useState("http://127.0.0.1:8080/v1");
  const [connectionName, setConnectionName] = useState("");
  const [connectedEmbedder, setConnectedEmbedder] = useState(false);
  const [advancedStartup, setAdvancedStartup] = useState("");
  const [settingsPreview, setSettingsPreview] = useState<SettingsBags | null>(null);
  const [message, setMessage] = useState("");
  const [messageTone, setMessageTone] = useState<"info" | "error" | "ok">("info");
  const [loadError, setLoadError] = useState("");
  const [busy, setBusy] = useState("");
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
  const selectedCurrent = visibleCurrent.filter(d => d.bundle_id === selectedBundleId);
  const otherCurrent = visibleCurrent.filter(d => d.bundle_id !== selectedBundleId && bundles.some(bundle => bundle.id === d.bundle_id));
  const externalCurrent = visibleCurrent.filter(d => d.bundle_id !== selectedBundleId && !bundles.some(bundle => bundle.id === d.bundle_id));
  const selectedConnections = extraConnections.filter(d => selectedCurrent.some(model => model.endpoint === d.endpoint));
  const history = deployments.filter(d => d.status === "stopped" && d.bundle_id === selectedBundleId);
  const selectedRunning = current.find(d => d.bundle_id === selectedBundleId && d.health?.healthy);
  const selectedActive = current.find(d => d.bundle_id === selectedBundleId && d.scope === "managed" && d.status !== "failed");
  const connectedAlready = current.some(d => d.endpoint?.replace(/\/$/, "") === endpoint.trim().replace(/\/$/, ""));
  const engineInUse = current.some(d => d.scope === "managed" && d.status !== "failed");
  const runtimeReady = loaded && runtime?.status === "ready";
  const thinkingAvailable = Boolean(configuration?.per_request_defaults?.reasoning?.supported || configuration?.per_request_defaults?.reasoning_effort?.supported);
  const descriptorOptions = (key: string) => (configuration?.startup_defaults[key]?.options ?? []).map(option => ({ value: String(option.value ?? ""), label: option.label }));
  let stagedStartup: Record<string, unknown> | null = null;
  let stagedStartupError = "";
  try { stagedStartup = startup(); } catch (error) { stagedStartupError = errorMessage(error); }
  // The editor previews a replacement model configuration. Only changed keys
  // are overrides; omission continues to mean inheritance at submission.
  const setupPreview = useSetupPreview({ bundle_id: selectedBundleId || null, model_configuration_id: profileId || null,
    startup_overrides: stagedStartup ?? {}, per_request_overrides: responseChanges }, null, null, "application",
    `${bundlesVersion}:${selectedProfile?.revision ?? 0}:${selectedRunning?.updated_at ?? ""}:${configurationRevision}`, Boolean(selectedBundleId && stagedStartup));
  const modelFacts = Object.fromEntries(Object.entries(setupPreview.data?.effective_values ?? {})
    .map(([key, fact]) => [key, fact.source === "Application defaults" && key.startsWith("per_request.") && Object.hasOwn(responseChanges, key.slice(12))
      ? { ...fact, source: "Unsaved changes" }
      : fact.source === "Application defaults" && key.startsWith("startup.") && Object.hasOwn(stagedStartup ?? {}, key.slice(8))
        ? { ...fact, source: "This editor" } : fact]));
  const responseFacts = modelFacts;
  const startupReadout = (key: string) => {
    const fact = modelFacts[`startup.${key}`];
    const display = stagedStartupError ? { value: "Check settings", source: stagedStartupError } : effectiveSettingDisplay(fact, setupPreview.loading);
    if (fact?.known && fact.supported !== false && !stagedStartupError && !setupPreview.loading) display.value = startupValueLabel(key, fact.value);
    const edited = stagedStartup && Object.hasOwn(stagedStartup, key);
    const saved = Object.hasOwn(selectedProfile?.bags.startup.requested ?? {}, key);
    const state = edited && stagedStartup?.[key] !== null ? "Selected for next load" : saved && !edited ? "Set in configuration" : "Inherited";
    return <span className="model-effective-readout" data-state={state === "Inherited" ? "inherited" : "set"}><strong>{display.value}</strong>{[display.source, !setupPreview.loading && !stagedStartupError ? state : ""].filter(Boolean).map(part => ` · ${part}`).join("")}</span>;
  };
  const startupResolved = (key: string) => {
    const fact = modelFacts[`startup.${key}`];
    return fact?.known && fact.supported !== false ? fact.value : null;
  };
  const canResetStartup = (key: string) => (Object.hasOwn(stagedStartup ?? {}, key) && stagedStartup?.[key] !== null)
    || (Object.hasOwn(selectedProfile?.bags.startup.requested ?? {}, key) && stagedStartup?.[key] !== null);

  function publishDraftMarkers() {
    const ids = new Set([...drafts.current.keys()].map(key => key.split(":", 1)[0]));
    if (dirty.current && activeDraftKey.current) ids.add(activeDraftKey.current.split(":", 1)[0]);
    onDirtyModelsChange?.(ids);
  }
  function stashDraft() {
    if (!activeDraftKey.current || !dirty.current) return;
    drafts.current.set(activeDraftKey.current, { settings: { ...settings }, response: { ...response }, name: configurationName, advanced: advancedStartup, changed: [...changedStartup.current] });
    publishDraftMarkers();
  }
  function restoreDraft(key: string): boolean {
    const draft = drafts.current.get(key);
    if (!draft) return false;
    activeDraftKey.current = key;
    dirty.current = true;
    changedStartup.current = new Set(draft.changed);
    setSettings({ ...draft.settings }); setResponse({ ...draft.response }); setConfigurationName(draft.name); setAdvancedStartup(draft.advanced); setSettingsPreview(null);
    publishDraftMarkers();
    return true;
  }
  useEffect(() => { publishDraftMarkers(); }, [settings, response, configurationName, advancedStartup, selectedBundleId, profileId]);

  function applyConfiguration(report: BundleConfigurationOptions) {
    if (report.bundle_id !== selection.current) return;
    setConfiguration(report);
    setConfigurationRevision(value => value + 1);
    const maximum = report.context_size.maximum;
    setMaximumContext(maximum); setLayers(report.gpu_layers.maximum);
    const threads = report.startup_defaults.threads;
    if (threads?.options.length) setThreadChoices(threads.options.filter(option => typeof option.value === "number" && Number(option.value) > 0).map(option => ({ value: String(option.value), label: option.label })));
    setModelInfo(maximum && maximum > 0 ? `${tokenLabel(maximum)} maximum context · ${report.metadata.architecture ?? "GGUF"}` : "Model capacity unavailable");
  }

  async function refresh() {
    const [r, d] = await Promise.all([api.runtime(), api.deployments()]);
    setRuntime(r); setDeployments(d); setLoaded(true); setLoadError("");
  }
  useEffect(() => { void refresh().catch(error => setLoadError(errorMessage(error))); }, [bundlesVersion]);
  useEffect(() => {
    if (!loaded) return;
    const changedModel = hydrated.current.bundle !== selectedBundleId;
    const saved = (!changedModel ? selectedProfile : undefined) ?? profiles.find(item => item.id === (selectedRunning?.profile_id ?? selected?.default_configuration_id)) ?? profiles.find(item => item.bundle_id === selectedBundleId);
    const changedProfile = saved && (hydrated.current.profile !== saved.id || hydrated.current.revision !== saved.revision);
    const shouldHydrate = changedModel || (!dirty.current && changedProfile) || (selectedRunning && !dirty.current && hydrated.current.deployment !== selectedRunning.id);
    if (changedModel) { stashDraft(); dirty.current = false; setMessage(""); setProfileId(""); }
    let cancelled = false;
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
    changedStartup.current = new Set([...Object.keys(selectedRunning?.startup_overrides ?? {}), ...(!saved ? Object.keys(selectedRunning?.requested_startup ?? {}) : [])]);
    setConfigurationName(saved?.display_name ?? selected?.display_name ?? "Default"); setResponse(saved?.bags.per_request.requested ?? {});
    const starting = { ...initialSettings };
    const extra: Record<string, unknown> = {};
    const inherited = saved;
    const formStartup = inherited
      ? mergedStartup(inherited.bags.startup.requested, selectedRunning?.startup_overrides ?? {})
      : selectedRunning?.requested_startup ?? selectedRunning?.startup_overrides ?? {};
    for (const [key, value] of Object.entries(formStartup)) {
      if (key in starting) starting[key] = key === "reasoning_preserve" ? value === true ? "keep" : value === false ? "drop" : "" : String(value);
      else if (key !== "host") extra[key] = value;
    }
    for (const [key, value] of Object.entries(selectedRunning?.startup_overrides ?? {})) {
      if (value === null && key in starting) starting[key] = "";
    }
    setSettings(starting); setAdvancedStartup(Object.keys(extra).length ? JSON.stringify(extra, null, 2) : ""); setSettingsPreview(null);
    }
    }
    if (selectedBundleId) void api.modelConfiguration(selectedBundleId, selectedRunning?.id).then(report => {
      if (cancelled) return;
      applyConfiguration(report);
    }).catch(() => { if (!cancelled) setModelInfo("Model details unavailable · refresh to retry"); });
    return () => { cancelled = true; };
  // Load existing settings once per selection; stopping a model must not erase edits.
  }, [selectedBundleId, loaded, selectedRunning?.id, profiles.length, selectedProfile?.id, selectedProfile?.revision, selected?.default_configuration_id]);
  useEffect(() => {
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
  }, [deployments]);
  function change(key: string, value: string) { dirty.current = true; changedStartup.current.add(key); setSettings(previous => ({ ...previous, [key]: value })); setSettingsPreview(null); setMessage(""); }
  function selectProfile(id: string) {
    stashDraft();
    const key = draftKey(selectedBundleId, id);
    const profile = profiles.find(item => item.id === id);
    hydrated.current = { ...hydrated.current, profile: id, revision: profile?.revision ?? 0 };
    activeDraftKey.current = key;
    dirty.current = false;
    changedStartup.current = new Set();
    setProfileId(id);
    if (restoreDraft(key)) return;
    setConfigurationName(profile?.display_name ?? selected?.display_name ?? "Default"); setResponse(profile?.bags.per_request.requested ?? {});
    const next = { ...initialSettings }, extra: Record<string, unknown> = {};
    for (const [key, value] of Object.entries(profile?.bags.startup.requested ?? {})) {
      if (key in next) next[key] = key === "reasoning_preserve" ? value === true ? "keep" : value === false ? "drop" : "" : String(value);
      else extra[key] = value;
    }
    setSettings(next); setAdvancedStartup(Object.keys(extra).length ? JSON.stringify(extra, null, 2) : ""); setSettingsPreview(null);
  }
  async function action(key: string, operation: () => Promise<unknown>) {
    if (actionPending.current) return;
    actionPending.current = true;
    const owner = selectionOwner.current;
    setBusy(key); setMessage("");
    try { await operation(); } catch (error) { if (selectionOwner.current === owner) { setMessage(errorMessage(error)); setMessageTone("error"); } } finally { actionPending.current = false; setBusy(""); }
  }
  function startup(): Record<string, unknown> {
    const values = startupPayload(settings, advancedStartup, profiles.find(profile => profile.id === profileId)?.bags.startup.requested ?? {}, changedStartup.current);
    if (!thinkingAvailable && !profileId) {
      for (const key of ["reasoning", "reasoning_effort", "reasoning_format", "reasoning_budget", "reasoning_preserve"]) {
        if (!changedStartup.current.has(key) && !selectedRunning?.applied_startup[key]) delete values[key];
      }
    }
    return values;
  }
  async function preview(startupValues = mergedStartup(selectedProfile?.bags.startup.requested ?? {}, startup()), responseValues = response, owner = selectionOwner.current) {
    const result = await api.previewSettings(startupValues, responseValues, {});
    if (selectionOwner.current === owner) setSettingsPreview(result);
    if (result.startup.unsupported.length || result.startup.retired.length || result.per_request.unsupported.length || result.per_request.retired.length) throw new Error("Some settings need attention. See the details below.");
    return result;
  }
  function configurationPayload(asVariant = false) {
    const name = (asVariant ? variantName : configurationName).trim();
    if (!name) throw new Error("Enter a configuration name.");
    return {
      display_name: name,
      startup: mergedStartup(selectedProfile?.bags.startup.requested ?? {}, startup()), per_request: response,
      ...(asVariant ? {} : { configuration_id: profileId || undefined, expected_revision: selectedProfile?.revision }),
    };
  }
  async function persistConfiguration(payload: ReturnType<typeof configurationPayload>, asVariant: boolean, owner: typeof selectionOwner.current) {
    const saved = await api.saveModelConfiguration(owner.id, payload);
    if (selectionOwner.current === owner) {
      drafts.current.delete(activeDraftKey.current);
      activeDraftKey.current = draftKey(owner.id, saved.id);
      setProfileId(saved.id); setConfigurationName(saved.display_name); changedStartup.current.clear(); dirty.current = false;
      publishDraftMarkers();
      setCreatingVariant(false); setVariantName("");
    }
    await onBundlesChanged?.(); await refresh();
    if (selectionOwner.current === owner) { setMessageTone("ok"); setMessage(asVariant ? "Configuration created." : "Configuration saved. Active and queued turns keep their settings."); }
    return saved;
  }
  async function saveConfiguration(asVariant = false) {
    const payload = configurationPayload(asVariant), owner = selectionOwner.current;
    await preview(payload.startup, payload.per_request, owner);
    return persistConfiguration(payload, asVariant, owner);
  }
  const field = (key: string, label: string, help: string, options: Array<{ value: string; label: string }>, custom = false, min = 0, max?: number) => {
    const requested = settings[key];
    const observed = key === "ctx_size" ? selectedRunning?.server_props?.n_ctx : configuration?.startup_defaults[key]?.observed;
    const loadedValue = observed ?? selectedRunning?.applied_startup[key];
    const normalizedLoaded = key === "reasoning_preserve" ? loadedValue === true ? "keep" : loadedValue === false ? "drop" : loadedValue : loadedValue;
    const resolved = modelFacts[`startup.${key}`];
    const showLoaded = selectedRunning && normalizedLoaded != null && (!resolved?.known || String(normalizedLoaded) !== String(resolved.value ?? ""));
    const resolvedValue = startupResolved(key);
    const normalizedResolved = key === "reasoning_preserve" ? resolvedValue === true ? "keep" : resolvedValue === false ? "drop" : resolvedValue : resolvedValue;
    const resolvedLabel = normalizedResolved == null ? "Inherited · not reported" : options.find(option => option.value === String(normalizedResolved))?.label ?? startupValueLabel(key, resolvedValue);
    return <SettingRow key={key} label={label} htmlFor={`model-${key}`} help={<>{help}<code>{`--${key.replaceAll("_", "-")}`}</code></>} provenance={startupReadout(key)}
      onReset={canResetStartup(key) && !busy ? () => change(key, "") : undefined}
      hint={showLoaded ? <span className="model-loaded-difference">Loaded: {key === "ctx_size" ? `${tokenLabel(Number(loadedValue))} tokens` : settingValue(normalizedLoaded)}</span> : undefined}>
      <ChoiceControl id={`model-${key}`} label={label} value={requested} options={options} onChange={value => change(key, value)} custom={custom} min={min} max={max} disabled={Boolean(busy)} resolvedLabel={resolvedLabel} resolvedValue={normalizedResolved} />
    </SettingRow>;
  };
  const gpuMode = settings.n_gpu_layers === "" ? "inherit" : ["auto", "-1"].includes(settings.n_gpu_layers) ? "auto" : settings.n_gpu_layers === "all" ? "all" : settings.n_gpu_layers === "0" ? "cpu" : "exact";
  const contextLoaded = selectedRunning?.server_props?.n_ctx;
  const contextResolvedRaw = startupResolved("ctx_size");
  const contextResolved = typeof contextResolvedRaw === "number" ? contextResolvedRaw : null;
  const portResolved = startupResolved("port");
  const contextChoices = contextSteps(configuration?.context_size.options?.map(option => Number(option.value)) ?? [], maximumContext);
  const contextShown = settings.ctx_size !== "" && Number.isFinite(Number(settings.ctx_size)) && Number(settings.ctx_size) > 0 ? Number(settings.ctx_size) : contextResolved ?? contextChoices[0] ?? 4096;
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
        {Object.keys(sampling).length ? <><h4>Response settings reported by server</h4>{readout(sampling)}</> : null}
        <SettingsNotes unsupported={d.settings?.startup.unsupported} retired={d.settings?.startup.retired} />
        {d.profile_id ? <><button type="button" disabled={Boolean(busy)} onClick={() => void action(`profile-${d.id}`, async () => { const result = await api.deploymentProfileChanges(d.id); setProfileChanges(previous => ({ ...previous, [d.id]: result })); })}>Compare with saved configuration</button>
          {profileChanges[d.id] ? <p className="hint">{profileChanges[d.id].has_pending_startup_changes ? "The saved configuration has different startup settings. This deployment keeps its original configuration; unload and start a new setup to apply the edited settings." : "No pending startup differences."}{profileChanges[d.id].has_pending_per_request_changes || profileChanges[d.id].has_pending_agent_changes ? " Response or agent settings have changed for future work." : ""}</p> : null}</> : null}
        {d.health?.detail ? <p className="hint">Health check: {d.health.detail}</p> : null}
        {d.error && d.status === "stopped" ? <p className="hint">Last event: {d.error}</p> : null}
        {d.scope === "managed" ? <><button type="button" disabled={Boolean(busy)} onClick={() => void action(`logs-${d.id}`, async () => { const result = await api.deploymentLogs(d.id); setLogs(previous => ({ ...previous, [d.id]: result.text })); })}>Read recent engine log</button>{logs[d.id] ? <pre className="engine-log">{logs[d.id]}</pre> : null}</> : null}
      </details>
    </li>;
  }
  return <section className="model-configuration">
    {loadError ? <Notice tone="error">{loadError}<button type="button" onClick={() => void refresh().catch(error => setLoadError(errorMessage(error)))}>Try again</button></Notice> : null}
    {otherCurrent.length ? <aside className="other-active-models" aria-label="Other active models"><span className="hint">Also active</span>{otherCurrent.map(d => <button type="button" key={d.id} disabled={!onSelectBundle} onClick={() => onSelectBundle?.(d.bundle_id!)}><span>{bundles.find(bundle => bundle.id === d.bundle_id)?.display_name}</span><StatusBadge {...stateOf(d)} /></button>)}</aside> : null}
    {selectedCurrent.length ? <div className="model-run-summary" aria-label="Loaded model status"><StatusBadge {...stateOf(selectedCurrent[0])} /><span>{selectedRunning?.server_props?.n_ctx ? `${tokenLabel(selectedRunning.server_props.n_ctx)} context loaded` : selectedCurrent[0].status === "starting" ? "Starting engine" : "Engine state available in details"}</span>{selectedActive ? <button type="button" disabled={Boolean(busy)} onClick={() => void action(selectedActive.id, async () => { await api.stop(selectedActive.id); await refresh(); })}>Unload</button> : null}<details><summary>Diagnostics</summary><ul className="plain-list">{selectedCurrent.map(renderDeployment)}</ul>{selectedConnections.length ? <ul className="plain-list">{selectedConnections.map(renderDeployment)}</ul> : null}</details></div> : null}
    {selected ? <section className="model-setup"><div className="model-setup-head"><div><h3>Model settings</h3><p className="hint model-capacity">{modelInfo}</p></div><span className="badge model-edit-state" data-dirty={dirty.current}>{dirty.current ? "Unsaved" : "Saved configuration"}</span><button type="button" className="icon-button" aria-label="Refresh model details" title="Re-read model metadata and supported controls" disabled={Boolean(busy)} onClick={() => void action("metadata", async () => { applyConfiguration(await api.modelConfiguration(selectedBundleId, selectedRunning?.id, true)); })}><Icon name="refresh" size={16} /></button></div><form ref={formRef} className="model-settings" onSubmit={event => {
      event.preventDefault(); void action("start", async () => {
        const payload = configurationPayload(), overrides = startup(), owner = selectionOwner.current;
        await preview(payload.startup, payload.per_request, owner);
        let result: Deployment;
        try {
          result = selectedActive ? await api.reconfigure(selectedActive.id, { startup: payload.startup, replace_startup: true, model_configuration_id: profileId || undefined, expected_configuration_revision: selectedProfile?.revision, expected_updated_at: selectedActive.updated_at }) : await api.startManaged(selectedBundleId, profileId || undefined, overrides);
          if (result.status === "failed") throw new Error(result.error ?? "Model could not load. Your saved configuration is unchanged.");
        } catch (failure) {
          // Failed rollback can leave a stopped or failed engine. Keep edits,
          // fetch its actual state, and preserve the original lifecycle error.
          await refresh().catch(() => {});
          throw failure;
        }
        await persistConfiguration(payload, false, owner);
        if (selectionOwner.current === owner) {
          dirty.current = false; setMessageTone("info");
          setMessage(result.error ?? (result.health?.healthy ? `${selected.display_name} is ready. Open Chat to get started.` : "Loading your model. Its status will update automatically."));
        }
        await refresh();
      });
    }}>
      <SettingSection title="Configuration" description={<>Saved settings apply to future Chat, Lab and Workflows turns. {selectedActive ? "Apply & reload updates this loaded engine." : "Loading applies startup settings."}</>}
        actions={selectedProfile && selected.default_configuration_id !== selectedProfile.id ? <button type="button" className="quiet-button" disabled={Boolean(busy)} onClick={() => void action("default", async () => { await api.setDefaultConfiguration(selectedBundleId, selectedProfile.id); await onBundlesChanged?.(); })}>Use as model default</button> : undefined}>
        <SettingRow label="Configuration" htmlFor="model-configuration" help="A named set of launch and response settings for this model. Switching keeps unsaved edits for each configuration.">
          <select id="model-configuration" value={profileId} disabled={Boolean(busy)} onChange={event => selectProfile(event.target.value)}>{!profileId ? <option value="">Model default</option> : null}{profiles.filter(profile => profile.bundle_id === selectedBundleId).map(profile => <option key={profile.id} value={profile.id}>{profile.display_name}{profile.id === selected.default_configuration_id && profile.display_name.trim().toLowerCase() !== "default" ? " · default" : ""}</option>)}</select>
        </SettingRow>
        <SettingRow label="Name" htmlFor="model-configuration-name">
          <input id="model-configuration-name" value={configurationName} disabled={Boolean(busy)} onChange={event => { dirty.current = true; setConfigurationName(event.target.value); }} />
        </SettingRow>
      </SettingSection>
      <SettingSection title="Run &amp; memory" description="Launch settings. Changes apply when the model loads or reloads.">
        <SettingRow label="Context size" htmlFor="model-ctx-size" help={<>Conversation capacity in tokens. Clearing the value restores the inherited setting.<code>--ctx-size</code></>} provenance={startupReadout("ctx_size")}
          onReset={canResetStartup("ctx_size") && !busy ? () => change("ctx_size", "") : undefined}
          hint={contextLoaded != null && (!modelFacts["startup.ctx_size"]?.known || Number(modelFacts["startup.ctx_size"].value) !== contextLoaded) ? <span className="model-loaded-difference">Loaded: {tokenLabel(contextLoaded)} tokens</span> : undefined}>
          <div className="slider-field">
            <CompactSlider hideHeading label="Context size" value={contextShown} values={contextChoices} formatValue={value => `${tokenLabel(value)} tokens`} inherited={settings.ctx_size === ""} disabled={Boolean(busy) || contextChoices.length < 2} onChange={value => change("ctx_size", String(value))} />
            <span className="number-field"><input id="model-ctx-size" type="number" min={1} max={maximumContext ?? undefined} value={settings.ctx_size} placeholder={contextResolved == null ? "" : String(contextResolved)} disabled={Boolean(busy)} onChange={event => change("ctx_size", event.target.value)} /><span className="field-unit">tokens</span></span>
          </div>
        </SettingRow>
        <SettingRow label="GPU layers" labelId="model-gpu-label" help="Automatic fits available memory; All requests full offload; CPU keeps layers off the GPU; Custom sets an exact count." provenance={startupReadout("n_gpu_layers")}
          onReset={canResetStartup("n_gpu_layers") && !busy ? () => change("n_gpu_layers", "") : undefined}
          hint={gpuLoaded != null && (!modelFacts["startup.n_gpu_layers"]?.known || startupValueLabel("n_gpu_layers", modelFacts["startup.n_gpu_layers"].value) !== startupValueLabel("n_gpu_layers", gpuLoaded)) ? <span className="model-loaded-difference">Loaded request: {startupValueLabel("n_gpu_layers", gpuLoaded)}</span> : undefined}>
          <SegmentedChoice bare label="GPU layers" value={gpuMode} disabled={Boolean(busy)} options={[{ value: "inherit", label: "Inherited" }, { value: "auto", label: "Auto" }, { value: "all", label: "All" }, { value: "cpu", label: "CPU" }, { value: "exact", label: "Custom…" }]} onChange={mode => change("n_gpu_layers", mode === "inherit" ? "" : mode === "all" ? "all" : mode === "cpu" ? "0" : mode === "exact" ? String(Math.max(1, Math.floor((layers ?? 32) / 2))) : "auto")} />
          {gpuMode === "exact" ? <div className="slider-field">
            <input type="range" aria-label="GPU layers slider" min={1} max={layers ?? 128} step={1} value={Number(settings.n_gpu_layers) || 1} disabled={Boolean(busy)} style={{ "--range-fill": `${((Number(settings.n_gpu_layers) || 1) - 1) / Math.max(1, (layers ?? 128) - 1) * 100}%` } as CSSProperties} onChange={event => change("n_gpu_layers", event.target.value)} />
            <span className="number-field"><input type="number" aria-label="Exact GPU layers" min={1} max={layers ?? undefined} value={settings.n_gpu_layers} disabled={Boolean(busy)} onChange={event => change("n_gpu_layers", event.target.value || "custom")} /><span className="field-unit">{layers ? `of ${layers}` : "layers"}</span></span>
          </div> : null}
        </SettingRow>
        {field("fit", "Memory fitting", "Adjust settings not fixed explicitly to fit GPU memory.", switches)}
        {field("flash_attn", "Flash attention", "Faster, more memory-efficient attention when supported.", [...switches, ...(settings.flash_attn === "auto" ? [{ value: "auto", label: "Engine automatic" }] : [])])}
        {field("cache_type_k", "Key cache precision", "Stores attention keys. Lower precision saves memory with a possible quality trade-off.", choices(cacheTypes))}
        {field("cache_type_v", "Value cache precision", "Stores attention values. Some lower-precision combinations require Flash attention.", choices(cacheTypes))}
        {field("spec_type", "Speculative mode", configuration?.startup_defaults.spec_type?.description ?? "Drafts ahead to accelerate generation where supported.", descriptorOptions("spec_type").length ? descriptorOptions("spec_type") : [{ value: "none", label: "Off" }])}
        {settings.spec_type.startsWith("draft-") ? field("spec_draft_n_max", "Draft tokens", "Maximum tokens drafted per step.", descriptorOptions("spec_draft_n_max"), true, 1) : null}
      </SettingSection>
      <SettingSection title="Thinking &amp; responses" description="Response settings for future turns. Active and queued turns keep theirs.">
        {configuration?.startup_defaults.reasoning_preserve?.supported ? field("reasoning_preserve", "Thinking history", "Keep or drop earlier thinking in later ordinary turns.", [{ value: "keep", label: "Keep" }, { value: "drop", label: "Drop" }]) : null}
        <ResponseSettingsEditor part="thinking" value={response} onChange={next => { dirty.current = true; setResponse(next); }} facts={responseFacts} options={configuration} disabled={Boolean(busy)} inheritance="model" loading={setupPreview.loading} />
        {stagedStartupError || setupPreview.error ? <p role="status" className="hint">{stagedStartupError || setupPreview.error}</p> : null}
      </SettingSection>
      <SettingSection title="Sampling" description="Leave a value empty to inherit it.">
        <ResponseSettingsEditor part="sampling" value={response} onChange={next => { dirty.current = true; setResponse(next); }} facts={responseFacts} options={configuration} disabled={Boolean(busy)} inheritance="model" loading={setupPreview.loading} />
      </SettingSection>
      <details className="settings-group technical-settings"><summary>More details <span>CPU, batch, templates, port and diagnostics</span></summary>
      <SettingSection title="Memory &amp; processing">
        {field("threads", "CPU threads", "CPU threads used to generate responses. For a new model, the suggested count uses your physical CPU cores. Automatic lets the engine decide; it may not report the resolved count.", threadChoices, true, 1)}
        {field("threads_batch", "Prompt processing threads", "CPU threads used to process your prompt. When linked, uses the same count as generation.", threadChoices, true, 1)}
        {field("load_mode", "Model loading", "Automatic chooses how weights are read. Memory mapping reads files as needed; locking keeps pages in RAM and needs sufficient memory.", [{ value: "auto", label: "Automatic" }, { value: "mmap", label: "Memory mapped (mmap)" }, { value: "mmap+mlock", label: "Memory mapped + locked" }, { value: "mlock", label: "Loaded + locked in RAM" }, { value: "none", label: "Standard file loading" }, { value: "dio", label: "Direct disk access" }])}
        {field("parallel", "Concurrent requests", "Requests processed at once. Multiple slots share the configured context and use more memory.", numberChoices([1, 2, 4, 8]), true, 1)}
        {field("batch_size", "Prompt batch size", "Maximum tokens processed together when reading a prompt. Larger batches can improve speed but use more memory.", numberChoices([128, 256, 512, 1024, 2048, 4096, 8192]), true, 1)}
        {field("ubatch_size", "Physical batch size", "Tokens handled in one computation batch. Usually smaller than the prompt batch size; reduce it if prompt processing runs out of memory.", numberChoices([64, 128, 256, 512, 1024, 2048]), true, 1)}
      </SettingSection>
      <SettingSection title="Model behaviour">
        {thinkingAvailable ? field("reasoning_budget", "Thinking budget", "Maximum thinking tokens when the template supports a budget. Unrestricted lets the model decide.", [{ value: "-1", label: "Unrestricted" }, ...numberChoices([0, 512, 1024, 2048, 4096, 8192, 16384])], true, -1) : null}
        {thinkingAvailable ? field("reasoning_format", "Thinking format", "How thinking is separated from the answer. No separation keeps raw output; it does not disable thinking.", [{ value: "auto", label: "Automatic" }, { value: "none", label: "No separation" }, { value: "deepseek", label: "DeepSeek" }, { value: "deepseek-legacy", label: "DeepSeek legacy" }]) : null}
        {field("embedding", "Model purpose", "Chat generates responses. Embeddings turn text into vectors for document search and require an embedding model.", [{ value: "off", label: "Chat" }, { value: "on", label: "Document search (embeddings)" }])}
        {settings.embedding === "on" ? field("pooling", "Embedding pooling", "Combines tokens into one vector. Choose the method recommended by the model publisher.", choices(["last", "mean", "cls"])) : null}
      </SettingSection>
      <SettingSection title="Advanced settings">
        <SettingRow label="Server port" htmlFor="model-port" help={<>Automatic chooses a free port when the model loads. Fixed ports are checked before starting.<code>--port</code></>} provenance={startupReadout("port")} onReset={canResetStartup("port") && !busy ? () => change("port", "") : undefined}>
          <NumberField id="model-port" label="Server port" value={settings.port} placeholder={typeof portResolved === "number" ? String(portResolved) : "Automatic"} min={1} max={65535} step={1} disabled={Boolean(busy)} onChange={value => change("port", value == null ? "" : String(value))} />
        </SettingRow>
        <SettingRow stacked label="Additional settings" htmlFor="additional-startup" help="JSON for supported template and draft-model controls. Use the named controls above for settings already shown.">
          <textarea id="additional-startup" spellCheck={false} value={advancedStartup} onChange={event => { dirty.current = true; setAdvancedStartup(event.target.value); setSettingsPreview(null); setMessage(""); }} placeholder="{}" />
        </SettingRow>
      </SettingSection>{selected ? <ModelProjectorControls key={selected.id} bundleId={selected.id} active={Boolean(selectedActive)} disabled={Boolean(busy)} action={action} onSaved={async () => { await onBundlesChanged?.(); await refresh(); }} /> : null}</details>
      <footer className="model-start-footer"><div className="runtime-indicator"><span className={runtimeReady ? "status-dot ready" : "status-dot"} />{!loaded ? "Checking local engine…" : runtimeReady ? "Local engine ready" : "Engine setup required"}</div><div className="actions">
        <button type="button" className="quiet-button" disabled={Boolean(busy)} onClick={() => { if (formRef.current?.reportValidity()) void action("preview", async () => { const owner = selectionOwner.current; await preview(); if (selectionOwner.current === owner) { setMessageTone("ok"); setMessage("Settings checked. Review the launch values below."); } }); }}>Check settings</button>
        <button type="button" disabled={Boolean(busy)} onClick={() => { setCreatingVariant(true); setVariantName(`${configurationName} copy`); }}>Save as configuration</button>
        <button type="button" disabled={Boolean(busy) || !configurationName.trim()} onClick={() => { if (formRef.current?.reportValidity()) void action("save", () => saveConfiguration()); }}>Save changes</button>
        <button type="submit" className="primary-button" disabled={Boolean(busy) || !runtimeReady || !selected.disk_matches || Boolean(selectedActive && !selectedRunning)} title={!runtimeReady ? "Set up the local engine first" : !selected.disk_matches ? "Repair or verify model files first" : selectedActive && !selectedRunning ? "Wait for the model to finish loading" : undefined}>{busy === "start" ? "Applying…" : selectedActive ? "Apply & reload" : "Load model"}</button>
      </div></footer>
      {creatingVariant ? <div className="model-variant-form"><label htmlFor="model-variant-name">Configuration name</label><input id="model-variant-name" value={variantName} onChange={event => setVariantName(event.target.value)} /><button type="button" className="primary-button" disabled={Boolean(busy) || !variantName.trim()} onClick={() => void action("variant", () => saveConfiguration(true))}>Create configuration</button><button type="button" className="quiet-button" onClick={() => setCreatingVariant(false)}>Cancel</button></div> : null}
      {settingsPreview ? <details className="technical-details" open><summary>Checked launch settings</summary><p className="hint">Applies on the next start. Final context and memory use are reported after loading.</p>{readout(settingsPreview.startup.applied)}<SettingsNotes unsupported={settingsPreview.startup.unsupported} retired={settingsPreview.startup.retired} /></details> : null}
    </form></section> : <EmptyState title="Choose a model to get started">Select one from your library, or add a new model.</EmptyState>}
    {message ? <Notice tone={messageTone}>{message}</Notice> : null}
    {externalCurrent.length ? <details className="card"><summary>Other model servers <span>{externalCurrent.length}</span></summary><ul className="plain-list">{externalCurrent.map(renderDeployment)}</ul></details> : null}
    <details className="card connection-settings"><summary>Connect an existing server</summary><form onSubmit={event => { event.preventDefault(); void action("connect", async () => { const result = await api.attachConnected(endpoint, connectionName || undefined, connectedEmbedder ? { ...DEFAULT_EMBEDDING_STARTUP } : undefined); await refresh(); setMessageTone(result.health?.healthy ? "ok" : "info"); setMessage(result.health?.healthy ? "Server connected and ready." : "Server saved. Check that it is running at this address."); }); }}>
      <p className="hint">Use a model served by another app. Manage its start and stop controls in that app.</p>
      <label>Server address<input type="url" required value={endpoint} onChange={event => setEndpoint(event.target.value)} /></label><label>Name (optional)<input value={connectionName} onChange={event => setConnectionName(event.target.value)} placeholder="My model server" /></label>
      <CompactSwitch label="Use for document search" description={<>The server must already serve embeddings with last-token pooling.<code>--embedding --pooling last</code></>} checked={connectedEmbedder} onChange={setConnectedEmbedder} />
      <button type="submit" disabled={Boolean(busy) || connectedAlready}>{busy === "connect" ? "Connecting…" : connectedAlready ? "Already connected" : "Connect server"}</button>
    </form></details>
    <details className="card engine-settings"><summary>Local engine <span>{!loaded ? "Checking" : runtimeReady ? "Ready" : "Setup required"}</span></summary><p className="hint">Runs models on this computer using your NVIDIA GPU.</p>
      {runtime ? <dl className="model-facts"><div><dt>Engine</dt><dd>llama.cpp {runtime.release_tag}</dd></div><div><dt>Platform</dt><dd>{runtime.platform} · {runtime.flavor}</dd></div><div><dt>Executable</dt><dd><code>{runtime.executable}</code></dd></div></dl> : null}
      {runtime?.error ? <Notice tone="error">{runtime.error}</Notice> : null}
      {engineInUse ? <p className="hint">Stop your local models before changing the engine installation.</p> : null}
      <button type="button" disabled={Boolean(busy) || engineInUse} onClick={() => void action("engine", async () => { const result = await api.pinRuntime(); setRuntime(result); setMessageTone(result.error ? "error" : "ok"); setMessage(result.error ?? "Local engine is ready."); })}>{busy === "engine" ? "Setting up…" : runtime?.status === "ready" ? "Verify engine installation" : "Set up local engine"}</button>
    </details>
    {history.length ? <details className="card"><summary>Runtime history <span>{history.length}</span></summary><ul className="plain-list">{history.map(renderDeployment)}</ul></details> : null}
  </section>;
}
