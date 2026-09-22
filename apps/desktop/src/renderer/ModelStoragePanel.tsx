import { useEffect, useState } from "react";
import { api } from "./api";
import { formatBytes } from "./display";
import { errorMessage } from "./errors";
import { ConfirmNote } from "./ConfirmNote";
import { Notice } from "./Notice";
import { pickWorkbenchPath } from "./PathField";
import { Help } from "./ModelControls";
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
  return <details className="card model-storage"><summary>Storage {storage ? <span className="hint">· {formatBytes(storage.managed_bytes)} installed</span> : null}</summary>
    {storage ? <div className="storage-summary"><span className="hint"><strong>{storage.available_bytes === null ? "Free space unknown" : `${formatBytes(storage.available_bytes)} free`}</strong> at the install destination</span><span className="hint">{formatBytes(storage.reclaimable_bytes)} available to clean</span></div> : null}
    <form className="storage-destination" onSubmit={event => { event.preventDefault(); void action(async () => { const result = await api.setModelStorage(path.trim()); setStorage(result); setPath(result.future_install_root); setMessage("New install destination saved. Existing models stay where they are."); }); }}>
      <label>Destination for new installs<input required value={path} onChange={event => setPath(event.target.value)} /></label>
      <button type="button" disabled={busy || !window.workbench?.selectPath} onClick={() => void action(async () => { const selected = await pickWorkbenchPath("folder"); if (selected) setPath(selected); })}>Browse</button>
      <button disabled={busy || !path.trim() || path.trim() === storage?.future_install_root}>Save</button>
      <Help label="Install location">Changes affect new installations only. Existing models stay at their current locations.</Help>
    </form>
    {storage ? <><dl className="storage-breakdown"><div><dt>Installed files</dt><dd>{formatBytes(storage.managed_bytes)}</dd></div><div><dt>Downloads</dt><dd>{formatBytes(storage.staging_bytes)}</dd></div><div><dt>Hub cache</dt><dd>{formatBytes(storage.cache_bytes)}</dd></div><div><dt>App records</dt><dd>{formatBytes(storage.metadata_bytes)}</dd></div></dl>
      <details className="technical-details"><summary>Locations and references</summary><ul>{storage.locations.map(item => <li key={`${item.kind}-${item.path}`}><strong>{item.kind}</strong>: <code>{item.path}</code> — {formatBytes(item.bytes)}; {item.reference_count} references</li>)}</ul></details></> : null}
    <div className="actions"><button type="button" disabled={busy} onClick={() => void action(refresh)}>Refresh sizes</button><button type="button" disabled={busy || !storage?.reclaimable_bytes} onClick={() => setConfirm(true)}>Clean unused downloads</button><Help label="Storage measurements">Disk sizes include separate temporary and installed copies, not RAM or GPU requirements. Cleanup manages this app's unreferenced cache only. To delete a model, select it in My models.</Help></div>
    {confirm ? <ConfirmNote disabled={busy} confirmLabel="Confirm cleanup" cancelLabel="Keep files" onConfirm={() => void action(async () => { const result = await api.cleanupModelStorage(); setConfirm(false); await refresh(); setMessage(result.removed.length ? `Cleaned ${result.removed.length} unused locations.` : "No eligible unused temporary files found."); })} onCancel={() => setConfirm(false)}>Remove only application-owned temporary downloads that are no longer referenced? Active work, retained partial downloads and installed models remain protected.</ConfirmNote> : null}
    {error ? <Notice tone="error">{error}</Notice> : null}{message ? <p role="status">{message}</p> : null}
  </details>;
}
