import { useCallback, useEffect, useRef, useState, type KeyboardEvent } from "react";
import { api } from "./api";
import { DeploymentsPanel } from "./DeploymentsPanel";
import { formatBytes } from "./display";
import { EmptyState } from "./EmptyState";
import { errorMessage } from "./errors";
import { Notice } from "./Notice";
import { ModelDeletion } from "./ModelDeletion";
import { modelFileLabel } from "./ModelPicker";
import { HuggingFaceImport } from "./HuggingFaceImport";
import { Icon } from "./Icon";
import type { ImportJob, InspectReport, ModelBundle, RunProfile } from "./types";
import "./ModelsPanel.css";

export function ModelsPanel({ active = true, openRecordId, openRequest }: { active?: boolean; openRecordId?: string; openRequest?: number } = {}) {
  const [view, setView] = useState<"library" | "add">("library");
  const [bundles, setBundles] = useState<ModelBundle[]>([]);
  const [profiles, setProfiles] = useState<RunProfile[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [search, setSearch] = useState("");
  const [draftModelIds, setDraftModelIds] = useState<ReadonlySet<string>>(new Set());
  const [catalogueOpen, setCatalogueOpen] = useState(false);
  const catalogue = useRef<HTMLElement>(null), catalogueTrigger = useRef<HTMLElement | null>(null);
  const showCatalogue = () => { catalogueTrigger.current = document.activeElement instanceof HTMLElement ? document.activeElement : null; setCatalogueOpen(true); };
  useEffect(() => {
    if (!catalogueOpen) return;
    const trigger = catalogueTrigger.current;
    const controls = () => Array.from(catalogue.current?.querySelectorAll<HTMLElement>("button:not(:disabled), input:not(:disabled), [tabindex=\"0\"]") ?? []).filter(item => item.getClientRects().length);
    controls()[0]?.focus();
    const keydown = (event: globalThis.KeyboardEvent) => {
      if (event.key === "Escape") { event.preventDefault(); setCatalogueOpen(false); }
      if (event.key === "Tab") { const choices = controls(); const first = choices[0], last = choices.at(-1); if (event.shiftKey && (document.activeElement === first || !catalogue.current?.contains(document.activeElement))) { event.preventDefault(); last?.focus(); } else if (!event.shiftKey && (document.activeElement === last || !catalogue.current?.contains(document.activeElement))) { event.preventDefault(); first?.focus(); } }
    };
    document.addEventListener("keydown", keydown);
    return () => { document.removeEventListener("keydown", keydown); trigger?.focus(); };
  }, [catalogueOpen]);
  const generation = useRef(0), cached = useRef(false), opened = useRef("");
  const refresh = useCallback(async () => {
    const owner = ++generation.current;
    setLoading(!cached.current);
    try {
      const nextBundles = await api.bundles();
      if (owner !== generation.current) return;
      if (!cached.current) { setBundles(nextBundles); setSelectedId(id => nextBundles.some(item => item.id === id) ? id : nextBundles[0]?.id ?? ""); setLoading(false); }
      const nextProfiles = await api.profiles();
      const finalBundles = await api.bundles();
      if (owner !== generation.current) return;
      setBundles(finalBundles); setProfiles(nextProfiles); cached.current = true; setLoadError("");
      setSelectedId(id => finalBundles.some(item => item.id === id) ? id : finalBundles[0]?.id ?? "");
    } catch (failure) { if (owner === generation.current) setLoadError(errorMessage(failure)); }
    finally { if (owner === generation.current) setLoading(false); }
  }, []);
  useEffect(() => { if (active) void refresh(); return () => { generation.current += 1; }; }, [active, refresh]);
  useEffect(() => {
    if (!active || !openRecordId || !cached.current) return;
    const key = `${openRequest ?? 0}:${openRecordId}`;
    if (opened.current === key) return;
    opened.current = key;
    const id = profiles.find(item => item.id === openRecordId)?.bundle_id ?? openRecordId;
    if (bundles.some(item => item.id === id)) { setSelectedId(id); setView("library"); setSearch(""); }
  }, [active, openRecordId, openRequest, bundles, profiles]);
  const selected = bundles.find(item => item.id === selectedId);
  const bundleVersion = selected ? JSON.stringify(selected) : selectedId;
  const visible = bundles.filter(item => `${item.display_name} ${item.source.repo_id ?? ""} ${modelFileLabel(item)}`.toLowerCase().includes(search.toLowerCase().trim()));
  function tabKey(event: KeyboardEvent<HTMLButtonElement>) {
    if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
    event.preventDefault();
    const next = event.key === "Home" ? "library" : event.key === "End" ? "add" : view === "library" ? "add" : "library";
    setView(next); document.getElementById(`models-tab-${next}`)?.focus();
  }
  async function imported(job: ImportJob) { if (job.bundle_id) setSelectedId(job.bundle_id); await refresh(); }
  return <section className="models-surface models-refresh" data-catalogue-open={catalogueOpen} aria-label="Models">
    {catalogueOpen ? <button type="button" className="models-catalogue-backdrop" aria-label="Close model catalogue" onClick={() => setCatalogueOpen(false)} /> : null}
    <aside ref={catalogue} className="models-catalogue" role={catalogueOpen ? "dialog" : undefined} aria-modal={catalogueOpen || undefined} aria-label="Model catalogue">
      <header className="models-heading"><h2>Models</h2><button type="button" className="icon-button models-catalogue-close" aria-label="Close model catalogue" onClick={() => setCatalogueOpen(false)}><Icon name="close" /></button></header>
      <nav className="model-tabs" role="tablist" aria-label="Model sections">
        <button id="models-tab-library" type="button" role="tab" aria-controls="models-panel-library" aria-selected={view === "library"} tabIndex={view === "library" ? 0 : -1} onKeyDown={tabKey} onClick={() => setView("library")}>My models <span>{bundles.length}</span></button>
        <button id="models-tab-add" type="button" role="tab" aria-controls="models-panel-add" aria-selected={view === "add"} tabIndex={view === "add" ? 0 : -1} onKeyDown={tabKey} onClick={() => setView("add")}>Add models</button>
      </nav>
      <div className="models-catalogue-body">{view === "library" ? <>
        <label className="models-library-search"><Icon name="search" size={16} /><input type="search" aria-label="Search models" placeholder="Search models…" value={search} onChange={event => setSearch(event.target.value)} /></label>
        <div className="models-library-list">{loading && !bundles.length ? <p className="hint" role="status">Loading…</p> : visible.length ? visible.map(item => <button type="button" key={item.id} className="models-library-row" aria-current={item.id === selectedId ? "true" : undefined} onClick={() => { setSelectedId(item.id); setCatalogueOpen(false); }} title={item.source.repo_id ?? item.primary_path ?? item.display_name}>
          <Icon name="models" /><span><strong>{item.display_name}{draftModelIds.has(item.id) ? <i className="model-draft-dot" aria-label="Unsaved edits" /> : null}</strong><small>{item.source.repo_id?.split("/")[0] ?? "Local model"}</small><small>{item.quantization ?? "GGUF"} · {formatBytes(item.files.reduce((sum, file) => sum + file.size_bytes, 0))}</small>{!item.disk_matches ? <small className="model-file-attention">Files need attention</small> : null}</span>
        </button>) : <p className="hint">{search ? "No matching models" : "Add a model to get started"}</p>}</div>
      </> : <div className="models-add-context"><Icon name="browser" /><h3>Add models</h3><p>Find a repository or choose a local file, then select what to add.</p></div>}</div>
    </aside>
    <div className="models-editor-area" inert={catalogueOpen}>
      {loadError ? <Notice tone="error" action={<button type="button" onClick={() => void refresh()}>Retry</button>}>{loadError}</Notice> : null}
      <div id="models-panel-library" role="tabpanel" aria-labelledby="models-tab-library" className="models-library-panel" hidden={view !== "library"}>
        {selected ? <DeploymentsPanel selectedBundleId={selectedId} bundlesVersion={bundleVersion} initialBundles={bundles} initialProfiles={profiles} catalogueReady={cached.current} active={active && view === "library"} onBundlesChanged={refresh} onSelectBundle={setSelectedId} onDirtyModelsChange={setDraftModelIds} openConfigurationId={profiles.some(item => item.id === openRecordId) ? openRecordId : undefined} openRequest={openRequest} onBrowseModels={showCatalogue} modelInformation={<ModelMaintenance key={selected.id} bundle={selected} onChanged={refresh} onJob={imported} />} /> : loadError ? <p className="hint">Model library unavailable.</p> : <EmptyState title={loading ? "Loading your models" : "Your first model starts here"}>Add a model from your computer or Hugging Face. <button type="button" onClick={() => setView("add")}>Add models</button></EmptyState>}
      </div>
      <div id="models-panel-add" role="tabpanel" aria-labelledby="models-tab-add" className="models-add-panel" hidden={view !== "add"}><HuggingFaceImport active={active && view === "add"} onStarted={imported} onOpenModel={id => { setSelectedId(id); setView("library"); }} onBrowseModels={showCatalogue} /></div>
    </div>
  </section>;
}

function ModelMaintenance({ bundle, onChanged, onJob }: { bundle: ModelBundle; onChanged: () => Promise<void>; onJob: (job: ImportJob) => Promise<void> }) {
  const [busy, setBusy] = useState(false), [message, setMessage] = useState("");
  const [inspect, setInspect] = useState<InspectReport | null>(null);
  async function run(operation: () => Promise<void>) { setBusy(true); setMessage(""); try { await operation(); } catch (failure) { setMessage(errorMessage(failure)); } finally { setBusy(false); } }
  const source = bundle.huggingface_configuration;
  const publisherTemplate = bundle.files.some(file => file.name === ".workbench-publisher/chat_template.jinja" || file.name === ".workbench-publisher/chat_template.from-tokenizer.jinja");
  return <div className="model-maintenance">
    {message ? <p className="hint" role="status">{message}</p> : null}
    <p className="hint">{bundle.source.repo_id ?? bundle.source.original_path}<br />{bundle.source.resolved_revision ?? "Local files"}</p>
    <ul className="plain-list">{[...new Map([...bundle.files, ...bundle.companions].map(file => [file.path, file])).values()].map(file => <li key={file.path}>{file.name} · {formatBytes(file.size_bytes)}</li>)}</ul>
    <div className="actions"><button type="button" disabled={busy} onClick={() => void run(async () => { const result = await api.verifyModel(bundle.id); setMessage(result.disk_matches ? "Recorded files match." : "Files are missing or changed."); await onChanged(); })}>Verify installed files</button>{bundle.source.kind === "huggingface" ? <button type="button" disabled={busy} onClick={() => void run(async () => { await onJob(await api.repairModel(bundle.id)); setMessage("Repair started."); })}>Repair installation</button> : null}<button type="button" disabled={busy} onClick={() => void run(async () => setInspect(await api.inspect(bundle.id)))}>Inspect metadata</button></div>
    {inspect ? <p className="hint">{inspect.architecture ?? "Unknown architecture"} · {inspect.tensors.length} tensors</p> : null}
    {source ? <details className="models-disclosure"><summary>Publisher template</summary><p className="hint">Next load: {source.template_origin} {source.template_compatible ? "· runtime checked" : ""}</p><div className="actions">{publisherTemplate ? <button type="button" disabled={busy} onClick={() => void run(async () => { await api.selectModelChatTemplate(bundle.id, "publisher"); await onChanged(); setMessage("Publisher template checked and selected."); })}>Test and use publisher template</button> : null}{source.template_origin !== "gguf" ? <button type="button" disabled={busy} onClick={() => void run(async () => { await api.selectModelChatTemplate(bundle.id, "gguf"); await onChanged(); })}>Use GGUF template</button> : null}</div></details> : null}
    <ModelDeletion kind="bundle" id={bundle.id} name={bundle.display_name} onDeleted={onChanged} />
  </div>;
}
