import { useEffect, useState } from "react";

import { api } from "./api";
import { DeploymentsPanel } from "./DeploymentsPanel";
import { formatBytes } from "./display";
import { EmptyState } from "./EmptyState";
import { errorMessage } from "./errors";
import { Notice } from "./Notice";
import { ProfilesPanel } from "./ProfilesPanel";
import { ImportJobsPanel } from "./ImportJobsPanel";
import { ModelDeletion } from "./ModelDeletion";
import { ModelStoragePanel } from "./ModelStoragePanel";
import { Help } from "./ModelControls";
import { PathBrowseButton } from "./PathField";
import { Icon } from "./Icon";
import { PanelResize, usePanelWidth } from "./PanelResize";
import type { InspectReport, ModelBundle, PathsInfo, RunProfile } from "./types";
import { HuggingFaceImport } from "./HuggingFaceImport";
import "./ModelsPanel.css";

export function ModelsPanel() {
  const [libraryWidth, setLibraryWidth] = usePanelWidth("models-library", 220, 180, 400);
  const [view, setView] = useState<"library" | "add" | "presets">("library");
  const [localBusy, setLocalBusy] = useState(false);
  const [paths, setPaths] = useState<PathsInfo | null>(null);
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

  async function refresh(): Promise<void> {
    setLoading(true);
    let bundlesLoaded = false;
    try {
      const nextBundles = await api.bundles();
      setBundles(nextBundles);
      setSelectedId(current => nextBundles.some(bundle => bundle.id === current) ? current : nextBundles[0]?.id ?? "");
      bundlesLoaded = true;
      setLoading(false);
      const [nextPaths, nextProfiles] = await Promise.all([
        api.paths(),
        api.profiles(),
      ]);
      setPaths(nextPaths);
      setProfiles(nextProfiles);
      setLoadError("");
    } finally {
      if (!bundlesLoaded) setLoading(false);
    }
  }

  useEffect(() => {
    void refresh().catch((error: unknown) => {
      setLoadError(errorMessage(error));
    });
  }, []);

  const selected = bundles.find((bundle) => bundle.id === selectedId) ?? null;
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
        <button type="button" className="primary-button" onClick={() => setView(view === "add" ? "library" : "add")}><Icon name={view === "add" ? "close" : "plus"} size={16} />{view === "add" ? "Close" : "Add model"}</button>
      </header>
      <nav className="model-tabs" aria-label="Model sections">
        <button type="button" aria-current={view === "library" ? "page" : undefined} onClick={() => setView("library")}>My models <span>{bundles.length}</span></button>
        <button type="button" aria-current={view === "presets" ? "page" : undefined} onClick={() => { setView("presets"); void refresh().catch(fail); }}>Saved presets <span>{profiles.length}</span></button>
      </nav>
      {message ? <Notice tone={/fail|error|mismatch/i.test(message) ? "error" : "info"}>{message}</Notice> : null}
      {view === "add" ? <>
      <HuggingFaceImport onStarted={async job => {
        setImportRevision(value => value + 1);
        if (job.bundle_id) { setSelectedId(job.bundle_id); setView("library"); setMessage("Model added to your library."); }
        await refresh();
      }} />
      <details className="card local-model-import"><summary>From your computer</summary>
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
                    : job.status === "complete" ? "Model added to your library." : "Import started. Progress and recovery controls are below.",
                );
                setImportRevision(value => value + 1);
                if (job.bundle_id) setView("library");
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
          <div className="setting-title"><label className="check-row"><input type="checkbox" checked={copyLocal} onChange={event => setCopyLocal(event.target.checked)} />Copy into model storage</label><Help label="Copy model">Turn off to use the original files without another copy. External originals are preserved when this library entry is removed.</Help></div>
          <button type="submit" className="primary-button" disabled={!localPath.trim() || localBusy}>
            {localBusy ? "Adding model…" : "Add model"}
          </button>
        </form>

      </details>
      </> : null}
      {view === "library" ? <div className="models-workspace" style={{ gridTemplateColumns: `${libraryWidth}px minmax(0, 1fr)` }}>
      <aside className="model-library" aria-label="Your models" style={{ position: "relative" }}>
        <div className="section-heading"><h3>Installed</h3><span className="hint">{bundles.length}</span></div>
        {loading ? (
          <EmptyState title="Loading your models">
            Loading saved model details.
          </EmptyState>
        ) : bundles.length === 0 ? (
          <EmptyState title="Your first model starts here">
            Add a model from your computer or download one from Hugging Face.
          </EmptyState>
        ) : (
          <ul className="model-list">
            {bundles.map((bundle) => (
              <li key={bundle.id}>
                <button
                  type="button"
                  className={bundle.id === selectedId ? "model-tile selected" : "model-tile"}
                  aria-pressed={bundle.id === selectedId}
                  onClick={() => {
                    setSelectedId(bundle.id);
                    setInspect(null);
                  }}
                >
                  <span className="nav-item-title">{bundle.display_name}</span>
                  <span className="nav-item-meta">
                    {bundle.quantization ?? "GGUF"} · {formatBytes(bundle.files.reduce((total, file) => total + file.size_bytes, 0))}
                    {!bundle.disk_matches ? " · Check files" : ""}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        )}
        {paths ? <details className="library-storage"><summary>Storage location</summary><code>{paths.models}</code></details> : null}
        <PanelResize label="Resize model library" width={libraryWidth} onResize={setLibraryWidth} min={180} max={400} reset={220} />
      </aside>
      <div className="model-detail">
      {selected ? <header className="model-selected-heading" aria-label="Selected model"><h3>{selected.display_name}</h3><div className="model-file-actions"><span className="hint">{formatBytes(selected.files.reduce((total, file) => total + file.size_bytes, 0))} on disk · {selected.files.length} {selected.files.length === 1 ? "file" : "files"}</span><ModelDeletion key={selected.id} kind="bundle" id={selected.id} name={selected.display_name} onDeleted={refresh} /></div></header> : null}
      <DeploymentsPanel selectedBundleId={selectedId} bundlesVersion={bundles.map((bundle) => `${bundle.id}:${bundle.companions.map(file => file.sha256).join("-")}`).join(",")} initialBundles={bundles} initialProfiles={profiles} onBundlesChanged={refresh} onSelectBundle={id => { setSelectedId(id); setInspect(null); }} />
      {selected ? (
          <details className="card technical-details"><summary>Files &amp; metadata</summary>
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
          </details>
        ) : null}
      </div></div> : null}
      {view === "presets" ? <ProfilesPanel profiles={profiles} bundles={bundles} refresh={refresh} /> : null}
      <ImportJobsPanel revision={importRevision} onCompleted={refresh} />
      <ModelStoragePanel />
    </section>
  );
}
