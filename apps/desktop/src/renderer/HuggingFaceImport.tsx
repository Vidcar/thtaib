import { useEffect, useRef, useState } from "react";
import { api } from "./api";
import { formatBytes } from "./display";
import { errorMessage } from "./errors";
import { Help } from "./ModelControls";
import { Icon } from "./Icon";
import { Notice } from "./Notice";
import type { ImportJob } from "./types";
import type { SchemaHubRepository } from "../generated/shared-contracts/openapi";

export function HuggingFaceImport({ onStarted }: { onStarted: (job: ImportJob) => Promise<void> }) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<Array<{ repo_id: string; downloads: number | null }>>([]);
  const [selectedRepo, setSelectedRepo] = useState("");
  const [hub, setHub] = useState<SchemaHubRepository | null>(null);
  const [variant, setVariant] = useState("");
  const [projector, setProjector] = useState("");
  const [busy, setBusy] = useState<"search" | "inspect" | "download" | "">("");
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const generation = useRef(0);
  const downloadPending = useRef(false);
  useEffect(() => () => { generation.current += 1; }, []);

  async function inspectRepository(repo: string) {
    if (downloadPending.current) return;
    const current = ++generation.current;
    setSelectedRepo(repo); setHub(null); setVariant(""); setProjector("");
    setError(""); setMessage(""); setBusy("inspect");
    try {
      const next = await api.inspectHf(repo);
      if (current !== generation.current) return;
      setHub(next); setSelectedRepo(next.repo_id);
      setVariant(next.variants.length === 1 && next.variants[0].complete ? next.variants[0].name : "");
      setProjector(next.projectors.length ? "" : "text-only");
    } catch (failure) { if (current === generation.current) setError(errorMessage(failure)); }
    finally { if (current === generation.current) setBusy(""); }
  }

  async function search() {
    const value = query.trim();
    if (!value || downloadPending.current) return;
    if (/^https?:\/\//i.test(value) || /^[\w.-]+\/[\w.-]+$/.test(value)) {
      setResults([]);
      await inspectRepository(value);
      return;
    }
    const current = ++generation.current;
    setBusy("search"); setError(""); setMessage(""); setHub(null); setSelectedRepo(""); setResults([]);
    try {
      const next = await api.searchHf(value);
      if (current !== generation.current) return;
      setResults(next);
      if (!next.length) setMessage("No matching repositories. Try a model name, publisher, or Hugging Face link.");
    } catch (failure) { if (current === generation.current) setError(errorMessage(failure)); }
    finally { if (current === generation.current) setBusy(""); }
  }

  const selectedVariant = hub?.variants.find(item => item.name === variant);
  const selectedProjector = hub?.projectors.find(item => item.name === projector);
  const files = [...new Set([...(selectedVariant?.files ?? []), ...(selectedProjector?.files ?? []), ...(hub?.guidance_files ?? [])])];
  const size = selectedVariant?.size_bytes == null || (selectedProjector && selectedProjector.size_bytes == null)
    ? null : selectedVariant.size_bytes + (selectedProjector?.size_bytes ?? 0);
  async function download() {
    if (!hub || !selectedVariant?.complete || !projector || downloadPending.current) return;
    downloadPending.current = true;
    const current = ++generation.current;
    setBusy("download"); setError(""); setMessage("");
    try {
      const exactFiles = files.map(file => file.replaceAll("[", "[[]").replaceAll("?", "[?]").replaceAll("*", "[*]"));
      const job = await api.importHf(hub.repo_id, hub.resolved_revision, exactFiles);
      if (current !== generation.current) return;
      setMessage(job.error ? `Download ${job.status}: ${job.error}` : job.status === "complete" ? "Model added to your library." : "Download started. Track progress in Downloads below.");
      await onStarted(job);
    } catch (failure) { if (current === generation.current) setError(errorMessage(failure)); }
    finally { downloadPending.current = false; if (current === generation.current) setBusy(""); }
  }

  return <section className="card model-finder" aria-label="Find a model">
    <div className="setting-title"><h3>Hugging Face</h3><Help label="Find a model">Search by model or publisher, or paste a repository link. Choose one complete GGUF variant; image input also needs a compatible vision file.</Help></div>
    <form className="model-search" onSubmit={event => { event.preventDefault(); void search(); }}>
      <label htmlFor="model-search-query" className="visually-hidden">Model name or Hugging Face repository</label>
      <input id="model-search-query" maxLength={200} value={query} disabled={busy === "download"} onChange={event => setQuery(event.target.value)} placeholder="Search models or paste a Hugging Face link" />
      <button type="submit" disabled={!query.trim() || Boolean(busy)}><Icon name="search" size={15} />{busy === "search" ? "Searching…" : "Find model"}</button>
    </form>
    {results.length ? <ul className="model-search-results" aria-label="Matching repositories">{results.map(result => <li key={result.repo_id} className={selectedRepo === result.repo_id ? "is-selected" : ""}>
      <div><strong>{result.repo_id}</strong>{result.downloads != null ? <span className="hint">{result.downloads.toLocaleString()} downloads</span> : null}</div>
      <button type="button" disabled={busy === "download"} aria-pressed={selectedRepo === result.repo_id} onClick={() => void inspectRepository(result.repo_id)}>{selectedRepo === result.repo_id ? "Selected" : "Select repository"}</button>
    </li>)}</ul> : null}
    {busy === "inspect" ? <p role="status">Loading model files for <strong>{selectedRepo}</strong>…</p> : null}
    {error ? <Notice tone="error">{error}{selectedRepo && !hub ? <button type="button" disabled={Boolean(busy)} onClick={() => void inspectRepository(selectedRepo)}>Retry loading files</button> : null}</Notice> : null}
    {hub ? <section className="model-download-selection" aria-label="Repository files">
      <div className="section-heading"><strong>{hub.repo_id}</strong><a href={`https://huggingface.co/${hub.repo_id}/blob/${hub.resolved_revision}/README.md`} target="_blank" rel="noreferrer">Model guide ↗</a></div>
      {hub.variants.length ? <div className="model-download-options">
        <label>Model variant<select value={variant} disabled={Boolean(busy)} onChange={event => setVariant(event.target.value)}>
          <option value="">Choose a GGUF variant</option>
          {hub.variants.map(item => <option key={item.name} value={item.name} disabled={!item.complete}>{item.name} · {item.size_bytes == null ? "size unknown" : formatBytes(item.size_bytes)}{item.complete ? "" : " · missing files"}</option>)}
        </select></label>
        {hub.projectors.length ? <label>Image input<select value={projector} disabled={Boolean(busy)} onChange={event => setProjector(event.target.value)}>
          <option value="">Choose vision file or text only</option><option value="text-only">Text only</option>
          {hub.projectors.map(item => <option key={item.name} value={item.name} disabled={!item.complete}>{item.name}{item.size_bytes == null ? "" : ` · ${formatBytes(item.size_bytes)}`}{item.complete ? "" : " · missing files"}</option>)}
        </select></label> : null}
      </div> : <Notice tone="warn">No complete GGUF model variants were found. Search for a GGUF version of this model.</Notice>}
      {hub.warnings.length ? <details className="technical-details"><summary>Repository notes ({hub.warnings.length})</summary>{hub.warnings.map(warning => <p key={warning}>{warning}</p>)}</details> : null}
      {selectedVariant ? <><div className="model-download-footer"><span className="hint">{size == null ? "Size unknown" : formatBytes(size)} · {selectedVariant.files.length} model file{selectedVariant.files.length === 1 ? "" : "s"}{selectedProjector ? " + vision file" : ""}</span><Help label="Download and vision files">Allow room for temporary and installed copies, roughly twice the selected size. Vision compatibility is checked after loading the model; a file being listed does not prove it is compatible.</Help><button type="button" className="primary-button" disabled={Boolean(busy) || !selectedVariant.complete || !projector} onClick={() => void download()}><Icon name="download" size={15} />{busy === "download" ? "Starting…" : "Download model"}</button></div>
        <details className="technical-details"><summary>Selected files · revision {hub.resolved_revision.slice(0, 8)}</summary><ul>{files.map(file => <li key={file}>{file}</li>)}</ul></details></> : null}
    </section> : null}
    {message ? <p role="status">{message}</p> : null}
  </section>;
}
