import { useEffect, useRef, useState } from "react";
import { api, DEFAULT_EMBEDDING_STARTUP } from "./api";
import { formatBytes } from "./display";
import { errorMessage } from "./errors";
import { Choice, Help, numberChoices, tokenLabel } from "./ModelControls";
import { mergedStartup, startupPayload } from "./deploymentSettings";
import { Notice } from "./Notice";
import { SettingsNotes } from "./settingsNotes";
import { StatusBadge } from "./StatusBadge";
import { Icon } from "./Icon";
import type { BundleConfigurationOptions, Deployment, DeploymentProfileChanges, ModelBundle, RunProfile, RuntimeManifest, SettingsBags } from "./types";

const cacheTypes = ["f16", "q8_0", "q4_0", "q4_1", "q5_0", "q5_1", "bf16", "f32", "iq4_nl"];
const choices = (values: string[]) => values.map(value => ({ value, label: value }));
const switches = [{ value: "on", label: "On" }, { value: "off", label: "Off" }];
const initialSettings: Record<string, string> = { ctx_size: "", n_gpu_layers: "-1", flash_attn: "on", fit: "on", cache_type_k: "f16", cache_type_v: "f16", threads: "", threads_batch: "", load_mode: "auto", parallel: "1", port: "8080", batch_size: "2048", ubatch_size: "512", reasoning: "auto", reasoning_effort: "", reasoning_format: "auto", reasoning_budget: "-1", embedding: "off", pooling: "last", spec_type: "none", spec_draft_n_max: "3" };
const EMPTY_BUNDLES: ModelBundle[] = [];
const EMPTY_PROFILES: RunProfile[] = [];

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
}: {
  selectedBundleId?: string;
  bundlesVersion?: string;
  initialBundles?: ModelBundle[];
  initialProfiles?: RunProfile[];
} = {}) {
  const formRef = useRef<HTMLFormElement>(null);
  const selection = useRef(selectedBundleId); selection.current = selectedBundleId;
  const hydrated = useRef({ bundle: "", deployment: "" });
  const dirty = useRef(false);
  const changedStartup = useRef(new Set<string>());
  const [runtime, setRuntime] = useState<RuntimeManifest | null>(null);
  const [deployments, setDeployments] = useState<Deployment[]>([]);
  const [profileId, setProfileId] = useState("");
  const [logs, setLogs] = useState<Record<string, string>>({});
  const [generation, setGeneration] = useState<Record<string, string>>({});
  const [profileChanges, setProfileChanges] = useState<Record<string, DeploymentProfileChanges>>({});
  const [loaded, setLoaded] = useState(false);
  const [settings, setSettings] = useState({ ...initialSettings });
  const [configuration, setConfiguration] = useState<BundleConfigurationOptions | null>(null);
  const [probeResults, setProbeResults] = useState<Record<string, Record<string, string>>>({});
  const [maximumContext, setMaximumContext] = useState<number | null>(null);
  const [layers, setLayers] = useState<number | null>(null);
  const [contextChoices, setContextChoices] = useState<Array<{ value: string; label: string }>>([]);
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
  const selected = bundles.find(b => b.id === selectedBundleId);
  const current = deployments.filter(d => d.status !== "stopped");
  const extraConnections = current.filter(d => d.scope === "connected" && current.some(other => other.scope === "managed" && other.endpoint === d.endpoint && other.health?.healthy));
  const visibleCurrent = current.filter(d => !extraConnections.includes(d));
  const history = deployments.filter(d => d.status === "stopped");
  const selectedRunning = current.find(d => d.bundle_id === selectedBundleId && d.health?.healthy);
  const selectedActive = current.find(d => d.bundle_id === selectedBundleId && d.scope === "managed" && d.status !== "failed");
  const connectedAlready = current.some(d => d.endpoint?.replace(/\/$/, "") === endpoint.trim().replace(/\/$/, ""));
  const engineInUse = current.some(d => d.scope === "managed" && d.status !== "failed");
  const runtimeReady = loaded && runtime?.status === "ready";
  const thinkingAvailable = Boolean(configuration?.per_request_defaults?.reasoning?.supported || configuration?.per_request_defaults?.reasoning_effort?.supported);
  const descriptorOptions = (key: string) => (configuration?.startup_defaults[key]?.options ?? []).map(option => ({ value: String(option.value ?? ""), label: option.label }));

  function applyConfiguration(report: BundleConfigurationOptions) {
    if (report.bundle_id !== selection.current) return;
    setConfiguration(report);
    const maximum = report.context_size.maximum;
    setMaximumContext(maximum); setLayers(report.gpu_layers.maximum);
    setContextChoices(report.context_size.options.filter(option => typeof option.value === "number").map(option => ({ value: String(option.value), label: `${option.label}${option.value === maximum ? " · maximum" : ""}` })));
    const threads = report.startup_defaults.threads;
    if (threads?.options.length) setThreadChoices(threads.options.filter(option => typeof option.value === "number" && Number(option.value) > 0).map(option => ({ value: String(option.value), label: option.label })));
    setModelInfo(maximum && maximum > 0 ? `${tokenLabel(maximum)} context · ${report.metadata.architecture ?? "GGUF"}${report.metadata.inspection_cached ? " · saved details" : ""}` : "Model capacity unavailable");
  }

  async function refresh() {
    const [r, d] = await Promise.all([api.runtime(), api.deployments()]);
    setRuntime(r); setDeployments(d); setLoaded(true); setLoadError("");
    await Promise.all(d.filter(item => item.health?.healthy).map(async item => {
      const result = await api.capabilityStatus(item.id);
      setProbeResults(previous => ({ ...previous, [item.id]: result.current_support }));
    }));
  }
  useEffect(() => { void refresh().catch(error => setLoadError(errorMessage(error))); }, [bundlesVersion]);
  useEffect(() => {
    if (!loaded) return;
    const changedModel = hydrated.current.bundle !== selectedBundleId;
    const shouldHydrate = changedModel || (selectedRunning && !dirty.current && hydrated.current.deployment !== selectedRunning.id);
    if (changedModel) { dirty.current = false; setMessage(""); setProfileId(""); }
    let cancelled = false;
    setConfiguration(null); setMaximumContext(null); setLayers(null); setContextChoices([]); setModelInfo("Loading model details…");
    if (shouldHydrate) {
    changedStartup.current = new Set(Object.keys(selectedRunning?.startup_overrides ?? {}));
    hydrated.current = { bundle: selectedBundleId, deployment: selectedRunning?.id ?? "" };
    setProfileId(selectedRunning?.profile_id ?? "");
    const starting = { ...initialSettings };
    const extra: Record<string, unknown> = {};
    const inherited = profiles.find(profile => profile.id === selectedRunning?.profile_id);
    const formStartup = inherited
      ? mergedStartup(inherited.bags.startup.requested, selectedRunning?.startup_overrides ?? {})
      : selectedRunning?.applied_startup ?? {};
    for (const [key, value] of Object.entries(formStartup)) {
      if (key in starting) starting[key] = String(value);
      else if (key !== "host") extra[key] = value;
    }
    for (const [key, value] of Object.entries(selectedRunning?.startup_overrides ?? {})) {
      if (value === null && key in starting) starting[key] = "";
    }
    if (!inherited && selectedRunning?.server_props?.total_slots && !("parallel" in selectedRunning.applied_startup)) starting.parallel = String(selectedRunning.server_props.total_slots);
    if (!inherited && selectedRunning?.server_props?.n_ctx && Number(starting.parallel) === 1) starting.ctx_size = String(selectedRunning.server_props.n_ctx);
    setSettings(starting); setAdvancedStartup(Object.keys(extra).length ? JSON.stringify(extra, null, 2) : ""); setSettingsPreview(null);
    }
    if (selectedBundleId) void api.modelConfiguration(selectedBundleId, selectedRunning?.id).then(report => {
      if (cancelled) return;
      applyConfiguration(report);
      const threads = report.startup_defaults.threads;
      if (!selectedRunning && threads?.recommended && !dirty.current) setSettings(previous => ({ ...previous, threads: String(threads.recommended) }));
    }).catch(() => { if (!cancelled) setModelInfo("Model details unavailable · refresh to retry"); });
    return () => { cancelled = true; };
  // Load existing settings once per selection; stopping a model must not erase edits.
  }, [selectedBundleId, loaded, selectedRunning?.id]);
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
    changedStartup.current = new Set();
    setProfileId(id); dirty.current = true;
    const profile = profiles.find(item => item.id === id);
    const next = { ...initialSettings }, extra: Record<string, unknown> = {};
    for (const [key, value] of Object.entries(profile?.bags.startup.requested ?? {})) {
      if (key in next) next[key] = String(value);
      else extra[key] = value;
    }
    setSettings(next); setAdvancedStartup(Object.keys(extra).length ? JSON.stringify(extra, null, 2) : ""); setSettingsPreview(null);
  }
  async function action(key: string, operation: () => Promise<unknown>) {
    setBusy(key); setMessage("");
    try { await operation(); } catch (error) { setMessage(errorMessage(error)); setMessageTone("error"); } finally { setBusy(""); }
  }
  function startup(): Record<string, unknown> {
    const values = startupPayload(settings, advancedStartup, profiles.find(profile => profile.id === profileId)?.bags.startup.requested, changedStartup.current);
    if (!thinkingAvailable && !profileId) {
      for (const key of ["reasoning", "reasoning_effort", "reasoning_format", "reasoning_budget"]) {
        if (!changedStartup.current.has(key) && !selectedRunning?.applied_startup[key]) delete values[key];
      }
    }
    return values;
  }
  async function preview() {
    const result = await api.previewSettings(mergedStartup(profiles.find(profile => profile.id === profileId)?.bags.startup.requested ?? {}, startup()), {}, {}); setSettingsPreview(result);
    if (result.startup.unsupported.length || result.startup.retired.length) throw new Error("Some settings need attention. See the details below.");
    return result;
  }
  const field = (key: string, label: string, help: string, options: Array<{ value: string; label: string }>, custom = false, min = 0, max?: number) =>
    <Choice key={key} id={`model-${key}`} label={label} help={help} flag={`--${key.replaceAll("_", "-")}`} value={settings[key]} options={options} onChange={value => change(key, value)} custom={custom} min={min} max={max} disabled={Boolean(busy)} />;
  const readout = (values: Record<string, unknown>) => <dl className="settings-readout">{Object.entries(values).map(([key, value]) => <div key={key}><dt>{key.replaceAll("_", " ")}</dt><dd>{String(value)}</dd></div>)}</dl>;

  function renderDeployment(d: Deployment) {
    const state = stateOf(d), ctx = d.server_props?.n_ctx;
    const sampling = Object.fromEntries(Object.entries(d.server_props?.default_generation_settings?.params ?? {}).filter(([key]) => ["temperature", "top_p", "top_k", "min_p", "repeat_penalty", "n_predict"].includes(key)));
    const name = bundles.find(b => b.id === d.bundle_id)?.display_name ?? d.display_name.replace(/^(managed|connected):/, "");
    return <li key={d.id} className="running-model">
      <div className="section-heading"><div><strong>{name}</strong><p className="hint">{d.scope === "managed" ? "On this computer" : "External server"}{ctx ? ` · ${tokenLabel(ctx)} context` : ""}{d.resource_usage?.available ? ` · ${formatBytes(d.resource_usage.rss_bytes)} RAM` : ""}</p></div><StatusBadge label={state.label} tone={state.tone} /></div>
      {d.error && d.status !== "stopped" ? <Notice tone="error">{d.error}</Notice> : null}
      <dl className="settings-readout applied-summary" aria-label="Applied model settings">
        <div title="Context observed from the running server"><dt>Context</dt><dd>{ctx ? tokenLabel(ctx) : "Not reported"}</dd></div>
        <div title="GPU layers requested when this model was launched"><dt>GPU layers</dt><dd>{d.applied_startup.n_gpu_layers === -1 ? "All requested" : String(d.applied_startup.n_gpu_layers ?? "Auto")}</dd></div>
        <div title="Speculative decoding launch setting"><dt>Speculation</dt><dd>{String(d.applied_startup.spec_type ?? "Off")}{d.applied_startup.spec_type?.toString().startsWith("draft-") ? ` · ${d.applied_startup.spec_draft_n_max ?? 3} tokens` : ""}</dd></div>
        <div title="Thinking launch setting. Per-message controls can override it."><dt>Thinking</dt><dd>{String(d.applied_startup.reasoning_effort ?? d.applied_startup.reasoning ?? "Model default")}</dd></div>
      </dl>
      <div className="actions">
        {d.scope === "managed" && d.status !== "stopped" ? <button type="button" disabled={Boolean(busy)} onClick={() => void action(d.id, async () => { await api.stop(d.id); await refresh(); })}>{busy === d.id ? "Unloading…" : "Unload model"}</button> : null}
        {d.scope === "managed" && d.status === "stopped" ? <button type="button" disabled={Boolean(busy)} onClick={() => void action(d.id, async () => { await api.start(d.id); await refresh(); })}>Load saved setup</button> : null}
        {d.scope === "managed" && d.status === "running" ? <button type="button" disabled={Boolean(busy)} onClick={() => void action(d.id, async () => { await api.reload(d.id); await refresh(); })}>Reload saved setup</button> : null}
        {d.scope === "connected" ? <button type="button" disabled={Boolean(busy)} onClick={() => void action(d.id, async () => { await api.detach(d.id); await refresh(); })}>Disconnect</button> : null}
        {d.status !== "stopped" ? <button type="button" className="quiet-button" disabled={Boolean(busy)} onClick={() => void action(`health-${d.id}`, async () => { await api.healthOf(d.id); await refresh(); })}>Check status</button> : null}
        {d.health?.healthy ? <button type="button" disabled={Boolean(busy)} onClick={() => void action(`test-${d.id}`, async () => { const result = await api.smoke(d.id); setGeneration(previous => ({ ...previous, [d.id]: result.ok ? result.detail ?? "Text generation succeeded for this check." : `Generation check failed: ${result.detail ?? "No completed response"}` })); })}>Test text generation</button> : null}
      </div>
      {generation[d.id] ? <p role="status">{generation[d.id]}</p> : null}
      {d.health?.healthy ? <div className="model-probes"><div className="setting-title"><span>Capability probes</span><Help label="Capability probes">Runs a small real request. Results apply to this exact setup; changing the model or settings makes previous results untested.</Help></div><div className="actions">
        {[["tools", "Tools"], ["text_stream", "Streaming"], ["reasoning", "Thinking"], ["structured_native", "Structured output"], ["image", "Vision"]].map(([capability, label]) => {
          const unavailable = capability === "image" && d.server_props?.modalities?.vision === false;
          const status = unavailable ? "unavailable" : probeResults[d.id]?.[capability] ?? "untested";
          return <button type="button" key={capability} className={`probe-button probe-${status}`} title={`${label}: ${status}.${unavailable ? " This server reports no vision input." : " Run probe."}`} disabled={Boolean(busy) || unavailable} onClick={() => void action(`probe-${d.id}-${capability}`, async () => {
            const result = await api.capabilityProbe(d.id, capability);
            setProbeResults(previous => ({ ...previous, [d.id]: { ...previous[d.id], [capability]: result.status } }));
            setMessageTone(result.status === "passed" ? "ok" : "info"); setMessage(`${label}: ${result.status}${typeof result.observations.error === "string" ? ` · ${result.observations.error}` : ""}`);
          })}><Icon name={status === "passed" ? "check" : "lab"} size={14} />{label}<span className="hint">{busy === `probe-${d.id}-${capability}` ? "Testing…" : status}</span></button>;
        })}
      </div></div> : null}
      <details className="technical-details"><summary>Details &amp; applied settings</summary>
        <dl className="model-facts"><div><dt>Connection</dt><dd>{d.endpoint}</dd></div><div><dt>Deployment ID</dt><dd><code>{d.id}</code></dd></div><div><dt>Context reported by server</dt><dd>{ctx ? `${ctx.toLocaleString()} tokens` : "Not reported"}</dd></div><div><dt>Concurrent requests reported by server</dt><dd>{d.server_props?.total_slots ?? "Not reported"}</dd></div><div><dt>Engine version</dt><dd>{d.server_props?.build_info ?? "Not reported"}</dd></div><div><dt>Settings last reported</dt><dd>{d.server_props?.fetched ? new Date(d.server_props.fetched).toLocaleString() : "Not reported"}</dd></div></dl>
        <h4>Launch settings</h4><p className="hint">Values sent when this model was started. Automatic choices may be adjusted by the engine.</p>{readout(d.applied_startup)}
        {Object.keys(sampling).length ? <><h4>Response settings reported by server</h4>{readout(sampling)}</> : null}
        <SettingsNotes unsupported={d.settings?.startup.unsupported} retired={d.settings?.startup.retired} />
        {d.profile_id ? <><button type="button" disabled={Boolean(busy)} onClick={() => void action(`profile-${d.id}`, async () => { const result = await api.deploymentProfileChanges(d.id); setProfileChanges(previous => ({ ...previous, [d.id]: result })); })}>Compare with saved preset</button>
          {profileChanges[d.id] ? <p className="hint">{profileChanges[d.id].has_pending_startup_changes ? "The saved preset has different startup settings. This deployment keeps its original configuration; unload and start a new setup to apply the edited preset." : "No pending startup differences."}{profileChanges[d.id].has_pending_per_request_changes || profileChanges[d.id].has_pending_agent_changes ? " Response or agent settings have changed for future work." : ""}</p> : null}</> : null}
        {d.health?.detail ? <p className="hint">Health check: {d.health.detail}</p> : null}
        {d.error && d.status === "stopped" ? <p className="hint">Last event: {d.error}</p> : null}
        {d.scope === "managed" ? <><button type="button" disabled={Boolean(busy)} onClick={() => void action(`logs-${d.id}`, async () => { const result = await api.deploymentLogs(d.id); setLogs(previous => ({ ...previous, [d.id]: result.text })); })}>Read recent engine log</button>{logs[d.id] ? <pre className="engine-log">{logs[d.id]}</pre> : null}</> : null}
      </details>
    </li>;
  }
  return <section className="model-configuration">
    {loadError ? <Notice tone="error">{loadError}<button type="button" onClick={() => void refresh().catch(error => setLoadError(errorMessage(error)))}>Try again</button></Notice> : null}
    {current.length ? <section className="card running-section"><div className="section-heading"><h3>In use</h3><span className="hint">Available across your workspace</span></div><ul className="plain-list">{visibleCurrent.map(renderDeployment)}</ul>{extraConnections.length ? <details className="technical-details"><summary>Additional connections to these models <span>{extraConnections.length}</span></summary><ul className="plain-list">{extraConnections.map(renderDeployment)}</ul></details> : null}</section> : null}
    {selected ? <form ref={formRef} className="card model-settings" onSubmit={event => {
      event.preventDefault(); void action("start", async () => {
        await preview(); const result = await api.startManaged(selectedBundleId, profileId || undefined, startup());
        if (result.status !== "failed") dirty.current = false;
        setMessageTone(result.status === "failed" ? "error" : "info");
        setMessage(result.error ?? (result.health?.healthy ? `${selected.display_name} is ready. Open Chat to get started.` : "Loading your model. Its status will update automatically.")); await refresh();
      });
    }}>
      <div className="section-heading"><h3>{selected.display_name}</h3><span className="model-format">{selected.quantization ?? "GGUF"}</span></div>
      <div className="section-heading"><span className="hint model-capacity">{modelInfo}</span><button type="button" className="icon-button" aria-label="Refresh model details" title="Re-read model metadata and supported controls" disabled={Boolean(busy)} onClick={() => void action("metadata", async () => { applyConfiguration(await api.modelConfiguration(selectedBundleId, selectedRunning?.id, true)); })}><Icon name="refresh" size={16} /></button></div>
      <label>Saved preset<select value={profileId} disabled={Boolean(busy)} onChange={event => selectProfile(event.target.value)}><option value="">Custom setup</option>{profiles.filter(profile => !profile.bundle_id || profile.bundle_id === selectedBundleId).map(profile => <option key={profile.id} value={profile.id}>{profile.display_name}</option>)}</select></label>
      {selectedActive ? <div className="inline-note">{selectedRunning ? `Running with ${selectedRunning.server_props?.n_ctx ? `${tokenLabel(selectedRunning.server_props.n_ctx)} context` : "the settings shown in Details"}.` : "This model is loading or waiting for a connection."} Stop it before applying a new setup.</div> : null}
      <div className="model-settings-grid">
        {field("ctx_size", "Context size", "Space for the conversation, instructions and replies, measured in tokens. Larger contexts use more memory. Automatic fitting chooses a size at startup; the running value is shown above.", [{ value: "", label: maximumContext ? `Automatic · up to ${tokenLabel(maximumContext)}` : "Automatic · fit available memory" }, ...contextChoices], true, 1, maximumContext ?? undefined)}
        {field("n_gpu_layers", "GPU layers", "Move model layers to your graphics card for faster responses. All layers requests full offload; memory fitting can adjust this. Zero uses the CPU. The output layer is included in the available count.", [{ value: "-1", label: `All layers (−1)${layers ? ` · ${layers} available` : ""}` }, { value: "auto", label: "Automatic · fit GPU memory" }, { value: "0", label: "0 · CPU only" }, ...numberChoices([...new Set([...(layers ? Array.from({ length: 7 }, (_, i) => Math.max(1, Math.round(layers * (i + 1) / 8))) : [8, 16, 24, 32, 48, 64, 80]), layers ?? 99])])], true, -1, layers ?? undefined)}
        {field("fit", "Memory fitting", "Adjust settings that have not been fixed explicitly to fit GPU memory. Large explicit settings can still exceed available memory.", switches)}
        {field("flash_attn", "Flash attention", "Faster, more memory-efficient attention when supported by your GPU and model. Auto lets the engine choose.", [...switches, { value: "auto", label: "Automatic" }])}
      </div>
      <section className="settings-group"><div className="setting-title"><h4>Performance</h4><Help label="Speculative decoding">MTP is available when the file contains a compatible draft head. Other compatible draft models can be configured in additional settings. Runtime support does not guarantee a speed increase.</Help></div><div className="model-settings-grid">
        {field("spec_type", "Speculative decoding", configuration?.startup_defaults.spec_type?.description ?? "Loading supported modes…", descriptorOptions("spec_type").length ? descriptorOptions("spec_type") : [{ value: "none", label: "Off" }])}
        {settings.spec_type.startsWith("draft-") ? field("spec_draft_n_max", "Draft tokens", "Maximum tokens to draft per step. The runtime default is 3.", descriptorOptions("spec_draft_n_max"), true, 1) : null}
      </div></section>
      <details className="settings-group"><summary>Memory &amp; processing</summary><div className="model-settings-grid">
        {field("cache_type_k", "Key cache precision", "Stores attention keys. f16 uses half precision; q8_0 and q4_0 reduce memory use with a possible quality trade-off.", choices(cacheTypes))}
        {field("cache_type_v", "Value cache precision", "Stores attention values. Lower precision saves memory; some combinations require Flash attention.", choices(cacheTypes))}
        {field("threads", "CPU threads", "CPU threads used to generate responses. For a new model, the suggested count uses your physical CPU cores. Automatic lets the engine decide; it may not report the resolved count.", [{ value: "", label: "Automatic · count not reported" }, ...threadChoices], true, 1)}
        {field("threads_batch", "Prompt processing threads", "CPU threads used to process your prompt. When linked, uses the same count as generation.", [{ value: "", label: settings.threads && settings.threads !== "custom" ? `${settings.threads} · same as CPU threads` : "Same as CPU threads" }, ...threadChoices], true, 1)}
        {field("load_mode", "Model loading", "Automatic chooses how weights are read. Memory mapping reads files as needed; locking keeps pages in RAM and needs sufficient memory.", [{ value: "auto", label: "Automatic" }, { value: "mmap", label: "Memory mapped (mmap)" }, { value: "mmap+mlock", label: "Memory mapped + locked" }, { value: "mlock", label: "Loaded + locked in RAM" }, { value: "none", label: "Standard file loading" }, { value: "dio", label: "Direct disk access" }])}
        {field("parallel", "Concurrent requests", "Requests processed at once. Multiple slots share the configured context and use more memory.", numberChoices([1, 2, 4, 8]), true, 1)}
        {field("batch_size", "Prompt batch size", "Maximum tokens processed together when reading a prompt. Larger batches can improve speed but use more memory.", numberChoices([128, 256, 512, 1024, 2048, 4096, 8192]), true, 1)}
        {field("ubatch_size", "Physical batch size", "Tokens handled in one computation batch. Usually smaller than the prompt batch size; reduce it if prompt processing runs out of memory.", numberChoices([64, 128, 256, 512, 1024, 2048]), true, 1)}
      </div></details>
      <details className="settings-group"><summary>Model behaviour</summary><div className="model-settings-grid">
        {configuration?.per_request_defaults?.reasoning?.supported ? field("reasoning", "Thinking", "Enable or disable thinking using this model's template.", [{ value: "auto", label: "Model default" }, ...switches]) : null}
        {configuration?.per_request_defaults?.reasoning_effort?.supported ? field("reasoning_effort", "Thinking level", "Levels supported by this model's template. This is the launch default; Chat can choose a level per message.", configuration.per_request_defaults.reasoning_effort.options.map(option => ({ value: option.value === "default" ? "" : String(option.value), label: option.label }))) : null}
        {thinkingAvailable ? field("reasoning_budget", "Thinking budget", "Maximum thinking tokens when the template supports a budget. Unrestricted lets the model decide.", [{ value: "-1", label: "Unrestricted" }, ...numberChoices([0, 512, 1024, 2048, 4096, 8192, 16384])], true, -1) : null}
        {thinkingAvailable ? field("reasoning_format", "Thinking format", "How thinking is separated from the answer. No separation keeps raw output; it does not disable thinking.", [{ value: "auto", label: "Automatic" }, { value: "none", label: "No separation" }, { value: "deepseek", label: "DeepSeek" }, { value: "deepseek-legacy", label: "DeepSeek legacy" }]) : null}
        {field("embedding", "Model purpose", "Chat generates responses. Embeddings turn text into vectors for document search and require an embedding model.", [{ value: "off", label: "Chat" }, { value: "on", label: "Document search (embeddings)" }])}
        {settings.embedding === "on" ? field("pooling", "Embedding pooling", "Combines tokens into one vector. Choose the method recommended by the model publisher.", choices(["last", "mean", "cls"])) : null}
      </div></details>
      <details className="settings-group"><summary>Advanced settings <span>Server port and additional flags</span></summary>
        <div className="model-settings-grid">{field("port", "Server port", "Local port for this model. Choose a different port when running more than one model.", numberChoices([8080, 8081, 8082, 8090]), true, 1, 65535)}</div>
        <div className="setting-title"><label htmlFor="additional-startup">Additional settings</label><Help label="Additional settings">JSON for supported template and draft-model controls. Use the named controls above for settings already shown.</Help></div>
        <textarea id="additional-startup" spellCheck={false} value={advancedStartup} onChange={event => { dirty.current = true; setAdvancedStartup(event.target.value); setSettingsPreview(null); setMessage(""); }} placeholder="{}" />
      </details>
      <footer className="model-start-footer"><div className="runtime-indicator"><span className={runtimeReady ? "status-dot ready" : "status-dot"} />{!loaded ? "Checking local engine…" : runtimeReady ? "Local engine ready" : "Engine setup required"}</div><div className="actions">
        <button type="button" disabled={Boolean(busy)} onClick={() => { if (formRef.current?.reportValidity()) void action("preview", async () => { await preview(); setMessageTone("ok"); setMessage("Settings checked. Review the launch values below."); }); }}>Check settings</button>
        <button type="button" disabled={Boolean(busy) || !selected.disk_matches || Boolean(selectedActive)} onClick={() => { if (formRef.current?.reportValidity()) void action("prepare", async () => { await preview(); await api.prepareManaged(selectedBundleId, profileId || undefined, startup()); dirty.current = false; await refresh(); setMessageTone("info"); setMessage("Setup saved. Select it in Chat; the model will load when you send a message."); }); }}>Save setup for Chat</button>
        <button type="submit" className="primary-button" disabled={Boolean(busy) || !runtimeReady || !selected.disk_matches || Boolean(selectedActive)}>{busy === "start" ? "Loading model…" : selectedActive ? "Model is active" : "Start model"}</button>
      </div></footer>
      {settingsPreview ? <details className="technical-details" open><summary>Checked launch settings</summary><p className="hint">Applies on the next start. Final context and memory use are reported after loading.</p>{readout(settingsPreview.startup.applied)}<SettingsNotes unsupported={settingsPreview.startup.unsupported} retired={settingsPreview.startup.retired} /></details> : null}
    </form> : <div className="card"><h3>Choose a model to get started</h3><p className="hint">Select one from your library, or add a new model.</p></div>}
    {message ? <Notice tone={messageTone}>{message}</Notice> : null}
    <details className="card connection-settings"><summary>Connect an existing server</summary><form onSubmit={event => { event.preventDefault(); void action("connect", async () => { const result = await api.attachConnected(endpoint, connectionName || undefined, connectedEmbedder ? { ...DEFAULT_EMBEDDING_STARTUP } : undefined); await refresh(); setMessageTone(result.health?.healthy ? "ok" : "info"); setMessage(result.health?.healthy ? "Server connected and ready." : "Server saved. Check that it is running at this address."); }); }}>
      <p className="hint">Use a model served by another app. Manage its start and stop controls in that app.</p>
      <label>Server address<input type="url" required value={endpoint} onChange={event => setEndpoint(event.target.value)} /></label><label>Name (optional)<input value={connectionName} onChange={event => setConnectionName(event.target.value)} placeholder="My model server" /></label>
      <div className="setting-title"><label className="check-row"><input type="checkbox" checked={connectedEmbedder} onChange={event => setConnectedEmbedder(event.target.checked)} />Use for document search</label><Help label="Document search server" flag="--embedding --pooling last">The server must already serve embeddings with last-token pooling.</Help></div>
      <button type="submit" disabled={Boolean(busy) || connectedAlready}>{busy === "connect" ? "Connecting…" : connectedAlready ? "Already connected" : "Connect server"}</button>
    </form></details>
    <details className="card engine-settings"><summary>Local engine <span>{!loaded ? "Checking" : runtimeReady ? "Ready" : "Setup required"}</span></summary><p className="hint">Runs models on this computer using your NVIDIA GPU.</p>
      {runtime ? <dl className="model-facts"><div><dt>Engine</dt><dd>llama.cpp {runtime.release_tag}</dd></div><div><dt>Platform</dt><dd>{runtime.platform} · {runtime.flavor}</dd></div><div><dt>Executable</dt><dd><code>{runtime.executable}</code></dd></div></dl> : null}
      {runtime?.error ? <Notice tone="error">{runtime.error}</Notice> : null}
      {engineInUse ? <p className="hint">Stop your local models before changing the engine installation.</p> : null}
      <button type="button" disabled={Boolean(busy) || engineInUse} onClick={() => void action("engine", async () => { const result = await api.pinRuntime(); setRuntime(result); setMessageTone(result.error ? "error" : "ok"); setMessage(result.error ?? "Local engine is ready."); })}>{busy === "engine" ? "Setting up…" : runtime?.status === "ready" ? "Verify engine installation" : "Set up local engine"}</button>
    </details>
    {history.length ? <details className="card"><summary>Stopped models <span>{history.length}</span></summary><ul className="plain-list">{history.map(renderDeployment)}</ul></details> : null}
  </section>;
}
