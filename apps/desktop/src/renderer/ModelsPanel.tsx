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
import type { InspectReport, ModelBundle, PathsInfo, RunProfile } from "./types";
import type { SchemaHubRepository } from "../generated/shared-contracts/openapi";

export function ModelsPanel() {
  const [view, setView] = useState<"library" | "add" | "presets">("library");
  const [localBusy, setLocalBusy] = useState(false);
  const [paths, setPaths] = useState<PathsInfo | null>(null);
  const [bundles, setBundles] = useState<ModelBundle[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [inspect, setInspect] = useState<InspectReport | null>(null);
  const [localPath, setLocalPath] = useState("");
  const [localName, setLocalName] = useState("");
  const [copyLocal, setCopyLocal] = useState(true);
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState<Array<{ repo_id: string; downloads: number | null }>>([]);
  const [searchBusy, setSearchBusy] = useState(false);
  const [searchError, setSearchError] = useState("");
  const [repoId, setRepoId] = useState("");
  const [hub, setHub] = useState<SchemaHubRepository | null>(null);
  const [variant, setVariant] = useState("");
  const [projector, setProjector] = useState("");
  const [hubBusy, setHubBusy] = useState(false);
  const [hubMessage, setHubMessage] = useState("");
  const [profiles, setProfiles] = useState<RunProfile[]>([]);
  const [message, setMessage] = useState("");
  const [loadError, setLoadError] = useState("");
  const [loading, setLoading] = useState(true);
  const [importRevision, setImportRevision] = useState(0);
  const [verifyBusy, setVerifyBusy] = useState(false);

  async function refresh(): Promise<void> {
    setLoading(true);
    try {
      const [nextPaths, nextBundles, nextProfiles] = await Promise.all([
        api.paths(),
        api.bundles(),
        api.profiles(),
      ]);
      setPaths(nextPaths);
      setBundles(nextBundles);
      setSelectedId(current => nextBundles.some(bundle => bundle.id === current) ? current : nextBundles[0]?.id ?? "");
      setProfiles(nextProfiles);
      setLoadError("");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void refresh().catch((error: unknown) => {
      setLoadError(errorMessage(error));
    });
  }, []);

  const selected = bundles.find((bundle) => bundle.id === selectedId) ?? null;
  const selectedVariant = hub?.variants.find((item) => item.name === variant);
  const selectedProjector = hub?.projectors.find((item) => item.name === projector);
  const selectedHubFiles = [...(selectedVariant?.files ?? []), ...(selectedProjector?.files ?? []), ...(hub?.guidance_files ?? [])];

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
        <div><p className="eyebrow">YOUR WORKSPACE</p><h2>Models</h2>
        <p className="lede">Find your model. Make it your own.</p></div>
        <button type="button" className="primary-button" onClick={() => setView(view === "add" ? "library" : "add")}>{view === "add" ? "Back to library" : "+ Add model"}</button>
      </header>
      <nav className="model-tabs" aria-label="Model sections">
        <button type="button" aria-current={view === "library" ? "page" : undefined} onClick={() => setView("library")}>My models <span>{bundles.length}</span></button>
        <button type="button" aria-current={view === "presets" ? "page" : undefined} onClick={() => { setView("presets"); void refresh().catch(fail); }}>Saved presets <span>{profiles.length}</span></button>
      </nav>
      {message ? <Notice tone={/fail|error|mismatch/i.test(message) ? "error" : "info"}>{message}</Notice> : null}
      {view === "add" ? <>
      <div className="grid">
        <form
          className="card"
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
          <h3>Add from your computer</h3>
          <p className="hint">Use a GGUF model you’ve already downloaded.</p>
          <label>
            Model file or folder
            <input
              value={localPath}
              onChange={(event) => setLocalPath(event.target.value)}
              placeholder="C:\Users\…\Qwen3.8-27B-UD-IQ4_XS.gguf"
            />
          </label>
          <label>
            Display name (optional)
            <input value={localName} onChange={(event) => setLocalName(event.target.value)} />
          </label>
          <label className="check-row"><input type="checkbox" checked={copyLocal} onChange={event => setCopyLocal(event.target.checked)} />Copy into managed storage</label>
          <p className="hint">Turn this off to use your original files in place without another copy. They remain yours and are not deleted when you remove the library entry.</p>
          <button type="submit" className="primary-button" disabled={!localPath.trim() || localBusy}>
            {localBusy ? "Adding model…" : "Add model"}
          </button>
        </form>

        <form
          className="card"
          onSubmit={(event) => {
            event.preventDefault();
            setHubBusy(true);
            setHubMessage("Reading available model files…");
            setHub(null);
            void api.inspectHf(repoId).then((result) => {
              setHub(result);
              setVariant(result.variants.length === 1 && result.variants[0].complete ? result.variants[0].name : "");
              setProjector(result.projectors.length ? "" : "text-only");
              setHubMessage("");
            }).catch((error: unknown) => setHubMessage(errorMessage(error))).finally(() => setHubBusy(false));
          }}
        >
          <h3>Download from Hugging Face</h3>
          <p className="hint">Choose the version and size that suit your computer.</p>
          <label>
            Hugging Face link or repository
            <input
              value={repoId}
              onChange={(event) => { setRepoId(event.target.value); setHub(null); }}
              disabled={hubBusy}
              placeholder="unsloth/Qwen3.8-27B-GGUF"
            />
          </label>
          <button type="submit" disabled={!repoId.trim() || hubBusy}>
            Find model files
          </button>
          {hub ? <>
            <label>Model variant
              <select value={variant} disabled={hubBusy} onChange={(event) => setVariant(event.target.value)}>
                <option value="">Choose a GGUF variant</option>
                {hub.variants.map((item) => <option key={item.name} value={item.name} disabled={!item.complete}>
                  {item.name} · {item.size_bytes == null ? "size unknown" : formatBytes(item.size_bytes)}{item.complete ? "" : " · missing shards"}
                </option>)}
              </select>
            </label>
            {hub.projectors.length ? <label>Vision companion
              <select value={projector} disabled={hubBusy} onChange={(event) => setProjector(event.target.value)}>
                <option value="">Choose a projector or text-only</option>
                <option value="text-only">Text-only — no projector</option>
                {hub.projectors.map((item) => <option key={item.name} value={item.name}>{item.name} · compatibility unverified</option>)}
              </select>
            </label> : null}
            {hub.warnings.map((warning) => <p className="hint" key={warning}>{warning}</p>)}
            <p className="hint">Downloads use temporary space as well as the installed copy. When both locations share a disk, allow roughly twice the selected file size, plus download metadata. Available space is checked before copying.</p>
            <p className="hint">Read the publisher’s <a href={`https://huggingface.co/${hub.repo_id}/blob/${hub.resolved_revision}/README.md`} target="_blank" rel="noreferrer">model guide</a> for recommended settings and supported features.</p>
            <details><summary>Files and recorded revision</summary>
              <p className="hint">{hub.resolved_revision}</p>
              <ul>{selectedHubFiles.map((file) => <li key={file}>{file}</li>)}</ul>
            </details>
            <button type="button" disabled={hubBusy || !selectedVariant || !projector} onClick={() => {
              setHubBusy(true);
              setHubMessage("Starting your selected download…");
              const exactFiles = selectedHubFiles.map((file) => file.replaceAll("[", "[[]").replaceAll("?", "[?]").replaceAll("*", "[*]"));
              void api.importHf(hub.repo_id, hub.resolved_revision, exactFiles).then((job) => {
                setHubMessage(job.error ? `Import ${job.status}: ${job.error}` : job.status === "complete" ? "Model added to your library." : "Download started. Progress and recovery controls are below.");
                setImportRevision(value => value + 1);
                if (job.bundle_id) { setSelectedId(job.bundle_id); setView("library"); setMessage("Model added to your library."); }
                return refresh();
              }).catch((error: unknown) => setHubMessage(errorMessage(error))).finally(() => setHubBusy(false));
            }}>Download selected variant</button>
          </> : null}
          {hubMessage ? <p role="status">{hubMessage}</p> : null}
        </form>
      </div>
      <form className="card" onSubmit={event => {
        event.preventDefault(); setSearchBusy(true); setSearchError("");
        void api.searchHf(searchQuery).then(results => { setSearchResults(results); if (!results.length) setSearchError("No matching repositories found. Try a different name or enter a repository directly above."); }).catch(error => setSearchError(errorMessage(error))).finally(() => setSearchBusy(false));
      }}>
        <h3>Search model repositories</h3><p className="hint">Shows up to 20 matches. Inspect a repository’s files before choosing a GGUF variant; search results do not establish compatibility.</p>
        <label>Model name or publisher<input value={searchQuery} maxLength={200} onChange={event => setSearchQuery(event.target.value)} placeholder="Model name, GGUF, publisher…" /></label>
        <button disabled={searchBusy || !searchQuery.trim()}>{searchBusy ? "Searching…" : "Search Hugging Face"}</button>
        {searchError ? <p role="status">{searchError}</p> : null}
        <ul className="plain-list">{searchResults.map(result => <li className="entity" key={result.repo_id}><strong>{result.repo_id}</strong>{result.downloads != null ? <p className="hint">{result.downloads.toLocaleString()} reported downloads</p> : null}<button type="button" onClick={() => { setRepoId(result.repo_id); setHub(null); setHubMessage("Repository selected. Use Find model files to inspect its available variants."); }}>Select repository</button></li>)}</ul>
      </form>
      </> : null}
      {view === "library" ? <div className="models-workspace">
      <aside className="model-library" aria-label="Your models">
        <div className="section-heading"><h3>Your library</h3><span className="hint">{bundles.length} models</span></div>
        {loading ? (
          <EmptyState title="Loading your models">
            Checking model files. This may take a moment.
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
      </aside>
      <div className="model-detail">
      <DeploymentsPanel selectedBundleId={selectedId} bundlesVersion={bundles.map((bundle) => bundle.id).join(",")} />
      {selected ? (
          <details className="card technical-details"><summary>Model files &amp; technical details</summary>
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
            <ModelDeletion key={selected.id} kind="bundle" id={selected.id} name={selected.display_name} onDeleted={refresh} />
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
              Read model metadata
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
