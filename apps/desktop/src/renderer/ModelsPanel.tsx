import { useEffect, useRef, useState, type KeyboardEvent } from "react";

import { api } from "./api";
import { DeploymentsPanel } from "./DeploymentsPanel";
import { formatBytes } from "./display";
import { EmptyState } from "./EmptyState";
import { errorMessage } from "./errors";
import { Notice } from "./Notice";
import { ImportJobsPanel, useImportJobs } from "./ImportJobsPanel";
import { ModelDeletion } from "./ModelDeletion";
import { ModelStoragePanel } from "./ModelStoragePanel";
import { Help } from "./ModelControls";
import { CompactSwitch } from "./CompactControls";
import { PathBrowseButton } from "./PathField";
import { ModelPicker } from "./ModelPicker";
import { ModelResponseRecipes } from "./ModelResponseRecipes";
import type { InspectReport, ModelBundle, RunProfile } from "./types";
import { HuggingFaceImport } from "./HuggingFaceImport";
import "./ModelsPanel.css";

export function ModelsPanel() {
  const [view, setView] = useState<"library" | "add" | "downloads">("library");
  const [localBusy, setLocalBusy] = useState(false);
  const [bundles, setBundles] = useState<ModelBundle[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [inspect, setInspect] = useState<InspectReport | null>(null);
  const [localPath, setLocalPath] = useState("");
  const [localName, setLocalName] = useState("");
  const [copyLocal, setCopyLocal] = useState(true);
  const [profiles, setProfiles] = useState<RunProfile[]>([]);
  const [message, setMessage] = useState("");
  const [loadError, setLoadError] = useState("");
  const [loading, setLoading] = useState(true);
  const [importRevision, setImportRevision] = useState(0);
  const [verifyBusy, setVerifyBusy] = useState(false);
  const [draftModelIds, setDraftModelIds] = useState<ReadonlySet<string>>(new Set());
  const refreshGeneration = useRef(0);

  async function refresh(): Promise<void> {
    const generation = ++refreshGeneration.current;
    setLoading(true);
    let bundlesLoaded = false;
    try {
      const nextBundles = await api.bundles();
      if (generation !== refreshGeneration.current) return;
      setBundles(nextBundles);
      setSelectedId(current => nextBundles.some(bundle => bundle.id === current) ? current : nextBundles[0]?.id ?? "");
      bundlesLoaded = true;
      setLoading(false);
      const nextProfiles = await api.profiles();
      if (generation !== refreshGeneration.current) return;
      setProfiles(nextProfiles);
      const latestBundles = await api.bundles();
      if (generation !== refreshGeneration.current) return;
      setBundles(latestBundles);
      setLoadError("");
    } catch (error) {
      if (generation === refreshGeneration.current) throw error;
    } finally {
      if (generation === refreshGeneration.current && !bundlesLoaded) setLoading(false);
    }
  }

  useEffect(() => {
    void refresh().catch((error: unknown) => {
      setLoadError(errorMessage(error));
    });
  }, []);

  const imports = useImportJobs(importRevision, refresh);
  const tabs = ["library", "add", "downloads"] as const;
  function onTabKeyDown(event: KeyboardEvent<HTMLButtonElement>, current: typeof view) {
    const index = tabs.indexOf(current);
    const next = event.key === "ArrowRight" ? tabs[(index + 1) % tabs.length]
      : event.key === "ArrowLeft" ? tabs[(index + tabs.length - 1) % tabs.length]
      : event.key === "Home" ? tabs[0] : event.key === "End" ? tabs[tabs.length - 1] : null;
    if (!next) return;
    event.preventDefault(); setView(next);
    document.getElementById(`models-tab-${next}`)?.focus();
  }

  const selected = bundles.find((bundle) => bundle.id === selectedId) ?? null;
  const selectedBundleVersion = selected ? JSON.stringify([
    selected.id,
    selected.default_configuration_id,
    selected.primary_path,
    selected.disk_matches,
    selected.source.resolved_revision,
    selected.huggingface_configuration?.metadata_refreshed_at,
    selected.huggingface_configuration?.template_origin,
    selected.huggingface_configuration?.template_file,
    selected.huggingface_configuration?.generation_defaults,
    selected.files.map(file => [file.name, file.sha256]),
    selected.companions.map(file => [file.name, file.sha256]),
  ]) : selectedId;
  const publisherTemplateFound = Boolean(selected?.huggingface_configuration?.source_verified && selected.files.some(file =>
    file.name === ".workbench-publisher/chat_template.jinja" || file.name === ".workbench-publisher/chat_template.from-tokenizer.jinja"));
  function fail(error: unknown): void {
    setMessage(errorMessage(error));
  }
  if (loadError) {
    return (
      <section className="surface">
        <h2>Models</h2>
        <Notice tone="error">{loadError}</Notice>
        <button type="button" onClick={() => void refresh().catch((error: unknown) => setLoadError(errorMessage(error)))}>
          Retry
        </button>
      </section>
    );
  }

  return (
    <section className="surface models-surface">
      <header className="models-heading">
        <h2>Models</h2>
      </header>
      <nav className="model-tabs" role="tablist" aria-label="Model sections">
        <button id="models-tab-library" type="button" role="tab" aria-controls="models-panel-library" aria-selected={view === "library"} aria-current={view === "library" ? "page" : undefined} tabIndex={view === "library" ? 0 : -1} onKeyDown={event => onTabKeyDown(event, "library")} onClick={() => setView("library")}>My models <span>{bundles.length}</span></button>
        <button id="models-tab-add" type="button" role="tab" aria-controls="models-panel-add" aria-selected={view === "add"} aria-current={view === "add" ? "page" : undefined} tabIndex={view === "add" ? 0 : -1} onKeyDown={event => onTabKeyDown(event, "add")} onClick={() => setView("add")}>Add models</button>
        <button id="models-tab-downloads" type="button" role="tab" aria-controls="models-panel-downloads" aria-selected={view === "downloads"} aria-current={view === "downloads" ? "page" : undefined} tabIndex={view === "downloads" ? 0 : -1} onKeyDown={event => onTabKeyDown(event, "downloads")} onClick={() => setView("downloads")}>Downloads {imports.attentionCount ? <span aria-label={`${imports.attentionCount} downloads active or needing attention`}>{imports.attentionCount}</span> : null}</button>
      </nav>
      {message ? <Notice tone={/fail|error|mismatch/i.test(message) ? "error" : "info"}>{message}</Notice> : null}
      <div id="models-panel-add" role="tabpanel" aria-labelledby="models-tab-add" className="models-tab-panel models-add-panel" hidden={view !== "add"}>
      <HuggingFaceImport onStarted={async job => {
        setImportRevision(value => value + 1);
        if (job.bundle_id) { setSelectedId(job.bundle_id); setMessage("Model added to your library."); }
        setView("downloads");
        await refresh();
      }} />
      <section className="card local-model-import"><h3>From your computer</h3>
        <form
          className="local-model-form"
          onSubmit={(event) => {
            event.preventDefault();
            setLocalBusy(true);
            void api
              .importLocal(localPath, localName || undefined, copyLocal)
              .then((job) => {
                if (job.bundle_id) setSelectedId(job.bundle_id);
                setMessage(
                  job.error
                    ? `Local import ${job.status}: ${job.error}`
                    : job.status === "complete" ? "Model added to your library." : "Import started. Track progress in Downloads.",
                );
                setImportRevision(value => value + 1);
                setView("downloads");
                return refresh();
              })
              .catch(fail).finally(() => setLocalBusy(false));
          }}
        >
          <div className="setting-title"><span>Add a GGUF file or folder</span><Help label="Local model">A folder can include a complete set of split files and a compatible vision companion.</Help></div>
          <label>
            Model file or folder
            <input
              value={localPath}
              onChange={(event) => setLocalPath(event.target.value)}
              placeholder="C:\Users\…\Qwen3.8-27B-UD-IQ4_XS.gguf"
            />
          </label>
          <div className="actions"><PathBrowseButton kind="file" label="Browse file" icon="files" disabled={localBusy} onPicked={setLocalPath} onError={fail} /><PathBrowseButton kind="folder" label="Browse folder" icon="folder" disabled={localBusy} onPicked={setLocalPath} onError={fail} /></div>
          <label>
            Display name (optional)
            <input value={localName} onChange={(event) => setLocalName(event.target.value)} />
          </label>
          <CompactSwitch label="Copy into model storage" description="Turn off to use the original files without another copy. External originals are preserved when this library entry is removed." checked={copyLocal} onChange={setCopyLocal} />
          <button type="submit" className="primary-button" disabled={!localPath.trim() || localBusy}>
            {localBusy ? "Adding model…" : "Add model"}
          </button>
        </form>

      </section>
      </div>
      <div id="models-panel-library" role="tabpanel" aria-labelledby="models-tab-library" className="models-workspace" hidden={view !== "library"}>
      {loading ? <EmptyState title="Loading your models">Loading saved model details.</EmptyState> : bundles.length === 0 ? <EmptyState title="Your first model starts here">Add a model from your computer or download one from Hugging Face. <button type="button" onClick={() => setView("add")}>Add models</button></EmptyState> : null}
      {bundles.length ? <ModelPicker bundles={bundles} selectedId={selectedId} dirtyIds={draftModelIds} onSelect={id => { setSelectedId(id); setInspect(null); }} /> : null}
      <div className="model-detail">
      <DeploymentsPanel selectedBundleId={selectedId} bundlesVersion={selectedBundleVersion} initialBundles={bundles} initialProfiles={profiles} onBundlesChanged={refresh} onSelectBundle={id => { setSelectedId(id); setInspect(null); }} onDirtyModelsChange={setDraftModelIds} />
      {selected?.source.kind === "huggingface" ? <ModelResponseRecipes key={selected.id} bundle={selected} profiles={profiles} onChanged={refresh} /> : null}
      {selected ? <details className="card technical-details model-facts-details"><summary>Files, source &amp; metadata</summary>
      <div className="model-file-actions"><span className="hint">{formatBytes(selected.files.reduce((total, file) => total + file.size_bytes, 0))} on disk · {selected.files.length} {selected.files.length === 1 ? "file" : "files"}</span><ModelDeletion key={selected.id} kind="bundle" id={selected.id} name={selected.display_name} onDeleted={refresh} /></div>
      {selected.huggingface_configuration ? <section className="source-provenance" aria-label="Hugging Face model settings">
        <h4>Publisher guidance &amp; template <span className="hint">{selected.huggingface_configuration.source_verified ? "Verified publisher source" : "GGUF repository only"}</span></h4>
        {selected.huggingface_configuration.source_repo_id ? <p className="hint">{selected.huggingface_configuration.source_repo_id} @ {selected.huggingface_configuration.source_revision?.slice(0, 8) ?? "unverified"}</p> : null}
        <p>Chat template for next load: <strong>{selected.huggingface_configuration.template_origin === "gguf" ? "GGUF embedded" : selected.huggingface_configuration.template_origin === "none" ? "Unavailable" : selected.huggingface_configuration.template_origin === "publisher" ? "Publisher file" : "GGUF repository file"}</strong>{selected.huggingface_configuration.template_differs ? " · publisher file differs" : ""}</p>
        {publisherTemplateFound ? <div className="actions">
          {selected.huggingface_configuration.template_compatible ? <span className="hint">Publisher template passed the runtime check.</span> : <button type="button" disabled={verifyBusy} onClick={() => { setVerifyBusy(true); setMessage("Testing publisher template with this model…"); void api.selectModelChatTemplate(selected.id, "publisher").then(() => { setMessage("Publisher template passed the runtime check and is selected for the next load."); return refresh(); }).catch(fail).finally(() => setVerifyBusy(false)); }}>{selected.huggingface_configuration.template_origin === "publisher" ? "Test publisher template" : "Test and use publisher template"}</button>}
          {selected.huggingface_configuration.template_differs && selected.huggingface_configuration.template_origin !== "gguf" ? <button type="button" disabled={verifyBusy} onClick={() => { setVerifyBusy(true); void api.selectModelChatTemplate(selected.id, "gguf").then(() => { setMessage("GGUF embedded template selected for the next load."); return refresh(); }).catch(fail).finally(() => setVerifyBusy(false)); }}>Use GGUF template</button> : null}
        </div> : null}
        {Object.keys(selected.huggingface_configuration.generation_defaults).length ? <dl className="meta compact">{Object.entries(selected.huggingface_configuration.generation_defaults).map(([key, value]) => <div key={key}><dt>{key.replaceAll("_", " ")}</dt><dd>{key === "logit_bias" ? "Source token suppression" : String(value)}</dd></div>)}</dl> : <p className="hint">No verified publisher generation settings were found.</p>}
        {Object.keys(selected.huggingface_configuration.unsupported).length ? <details className="technical-details"><summary>Settings not applied ({Object.keys(selected.huggingface_configuration.unsupported).length})</summary><dl className="meta compact">{Object.entries(selected.huggingface_configuration.unsupported).map(([key, reason]) => <div key={key}><dt>{key}</dt><dd>{reason}</dd></div>)}</dl></details> : null}
      </section> : null}
          <section className="files-metadata"><h4>Files &amp; metadata</h4>
            <p className="hint">Model ID: <code>{selected.id}</code></p>
            <p>
              {selected.files.length} files
              {selected.companions.length ? ` · ${selected.companions.length} companions` : ""}
              {selected.primary_path ? (
                <>
                  {" "}
                  · <code>{selected.primary_path}</code>
                </>
              ) : null}
            </p>
            {selected.source.kind === "huggingface" ? (
              <p className="hint">
                {selected.source.repo_id} @ {selected.source.resolved_revision ?? selected.source.requested_revision}
              </p>
            ) : (
              <p className="hint">{selected.source.original_path}</p>
            )}
            {!selected.disk_matches ? (
              <Notice tone="warn">Recorded files do not match what is on disk.</Notice>
            ) : null}
            <div className="actions"><button type="button" disabled={verifyBusy} onClick={() => {
              setVerifyBusy(true); void api.verifyModel(selected.id).then(result => { setMessage(result.disk_matches ? "All recorded model files match their hashes." : "Files are missing or changed. Repair the recorded installation or restore your original local files."); return refresh(); }).catch(fail).finally(() => setVerifyBusy(false));
            }}>{verifyBusy ? "Checking files…" : "Verify installed files"}</button>
              {selected.source.kind === "huggingface" ? <button type="button" disabled={verifyBusy} onClick={() => { setVerifyBusy(true); void api.repairModel(selected.id).then(() => { setImportRevision(value => value + 1); setMessage("Repair started using the recorded revision and exact file selection."); }).catch(fail).finally(() => setVerifyBusy(false)); }}>Repair recorded installation</button> : null}
            </div>
            <ul className="plain-list">
              {selected.files.map((file) => (
                <li key={file.path}>
                  {file.role} · {file.name} · {formatBytes(file.size_bytes)}
                </li>
              ))}
            </ul>
            <button
              type="button"
              onClick={() => {
                void api.inspect(selected.id).then(setInspect).catch(fail);
              }}
            >
              Inspect metadata
            </button>
            {inspect && inspect.bundle_id === selected.id ? (
              <dl className="meta compact">
                <div>
                  <dt>Architecture</dt>
                  <dd>{inspect.architecture ?? "unknown"}</dd>
                </div>
                <div>
                  <dt>Name</dt>
                  <dd>{inspect.name ?? "unnamed"}</dd>
                </div>
                <div>
                  <dt>Tensors</dt>
                  <dd>{inspect.tensors.length}</dd>
                </div>
                <div>
                  <dt>Reader</dt>
                  <dd>
                    {inspect.reader_mode} · metadata edited {String(inspect.metadata_edited)}
                  </dd>
                </div>
              </dl>
            ) : null}
          </section>
        </details> : null}
      </div></div>
      <div id="models-panel-downloads" role="tabpanel" aria-labelledby="models-tab-downloads" className="models-tab-panel models-downloads-panel" hidden={view !== "downloads"}>
        <ImportJobsPanel state={imports} onOpenModel={id => { setSelectedId(id); setInspect(null); setView("library"); void refresh().catch(fail); }} />
        <ModelStoragePanel />
      </div>
    </section>
  );
}
