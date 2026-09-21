import { useEffect, useState } from "react";
import { api } from "./api";
import { formatBytes } from "./display";
import { errorMessage } from "./errors";
import { Notice } from "./Notice";
import type { ModelStorageSummary } from "./types";

export function ModelStoragePanel() {
  const [storage, setStorage] = useState<ModelStorageSummary | null>(null);
  const [path, setPath] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [confirm, setConfirm] = useState(false);
  async function refresh() { const result = await api.modelStorage(); setStorage(result); setPath(result.future_install_root); }
  useEffect(() => { void refresh().catch(failure => setError(errorMessage(failure))); }, []);
  async function action(work: () => Promise<void>) { setBusy(true); setError(""); setMessage(""); try { await work(); } catch (failure) { setError(errorMessage(failure)); } finally { setBusy(false); } }
  return <details className="card"><summary>Model storage</summary>
    <p className="hint">Changing the destination affects new installations. Existing models remain where they are.</p>
    <form onSubmit={event => { event.preventDefault(); void action(async () => { const result = await api.setModelStorage(path.trim()); setStorage(result); setPath(result.future_install_root); setMessage("Destination saved for future installations. Existing files have not moved."); }); }}>
      <label>Destination for new installs<input required value={path} onChange={event => setPath(event.target.value)} /></label>
      <button disabled={busy || !path.trim()}>Save destination</button>
    </form>
    {storage ? <><dl className="model-facts"><div><dt>Installed managed files</dt><dd>{formatBytes(storage.managed_bytes)}</dd></div><div><dt>Download staging</dt><dd>{formatBytes(storage.staging_bytes)}</dd></div><div><dt>Hub cache</dt><dd>{formatBytes(storage.cache_bytes)}</dd></div><div><dt>Local metadata</dt><dd>{formatBytes(storage.metadata_bytes)}</dd></div></dl>
      <p className="hint">Measured file sizes are not RAM or GPU requirements. Temporary and installed copies can both occupy disk; shared disk blocks are not assumed.</p>
      <p>{storage.available_bytes === null ? "Available disk space is unknown." : `${formatBytes(storage.available_bytes)} available at the new-install destination.`} {formatBytes(storage.reclaimable_bytes)} eligible for cleanup.</p>
      <p className="hint">Cache totals cover this application's download cache. Shared caches used by other applications are not managed here.</p>
      <details className="technical-details"><summary>Locations and references</summary><ul>{storage.locations.map(item => <li key={`${item.kind}-${item.path}`}><strong>{item.kind}</strong>: <code>{item.path}</code> — {formatBytes(item.bytes)}; {item.reference_count} references</li>)}</ul></details></> : null}
    <div className="actions"><button type="button" disabled={busy} onClick={() => void action(refresh)}>Measure again</button><button type="button" disabled={busy} onClick={() => setConfirm(true)}>Clean unused temporary downloads…</button></div>
    {confirm ? <div className="inline-note"><p>Remove only application-owned temporary downloads that are no longer referenced? Active work, retained partial downloads and installed models remain protected.</p><button disabled={busy} onClick={() => void action(async () => { const result = await api.cleanupModelStorage(); setConfirm(false); await refresh(); setMessage(result.removed.length ? `Cleaned ${result.removed.length} unused locations.` : "No eligible unused temporary files found."); })}>Confirm cleanup</button><button disabled={busy} onClick={() => setConfirm(false)}>Keep files</button></div> : null}
    {error ? <Notice tone="error">{error}</Notice> : null}{message ? <p role="status">{message}</p> : null}
  </details>;
}
