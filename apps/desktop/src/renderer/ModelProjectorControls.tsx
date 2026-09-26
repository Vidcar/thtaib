import { useEffect, useRef, useState } from "react";
import { api } from "./api";
import { errorMessage } from "./errors";
import { formatBytes } from "./display";
import { Help } from "./ModelControls";
import { Notice } from "./Notice";
import { pickWorkbenchPath } from "./PathField";
import type { SchemaBundleProjectors } from "../generated/shared-contracts/openapi";

export function ModelProjectorControls({ bundleId, active, disabled, onSaved, action }: { bundleId: string; active: boolean; disabled: boolean; onSaved: () => Promise<void>; action: (key: string, operation: () => Promise<unknown>) => Promise<void> }) {
  const [report, setReport] = useState<SchemaBundleProjectors | null>(null);
  const [selected, setSelected] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [revision, setRevision] = useState(0);
  const generation = useRef(0);
  const saving = useRef(false);
  useEffect(() => {
    let cancelled = false;
    generation.current += 1;
    setReport(null); setError(""); setMessage(""); setBusy(false);
    void api.modelProjectors(bundleId).then(next => { if (!cancelled) { setReport(next); setSelected(next.selected_path ?? ""); } }).catch(failure => { if (!cancelled) setError(errorMessage(failure)); });
    return () => { cancelled = true; generation.current += 1; };
  }, [bundleId, revision]);
  async function chooseFile() {
    const current = generation.current;
    try { const path = await pickWorkbenchPath("file"); if (path && generation.current === current) setSelected(path); }
    catch (failure) { if (generation.current === current) setError(errorMessage(failure)); }
  }
  async function save() {
    if (active || saving.current) return;
    saving.current = true;
    const current = generation.current;
    setBusy(true); setError(""); setMessage("");
    try {
      await api.selectModelProjector(bundleId, selected || null);
      const next = await api.modelProjectors(bundleId);
      if (generation.current !== current) return;
      setReport(next); setSelected(next.selected_path ?? "");
      setMessage(next.selected_path ? "Vision file saved. Start the model, then test Vision and Screenshot reading above." : "Text-only setup saved. Start the model to apply it.");
      await onSaved();
    } catch (failure) { if (generation.current === current) setError(errorMessage(failure)); }
    finally { saving.current = false; if (generation.current === current) setBusy(false); }
  }
  const locked = disabled || busy || active;
  const candidates = report?.candidates ?? [];
  return <details className="card model-projector-settings"><summary>Image input <span>{!report ? error ? "Unavailable" : "Loading…" : report.selected_path ? "Vision file selected" : candidates.length ? `${candidates.length} vision file${candidates.length === 1 ? "" : "s"} available` : "Text only"}</span></summary>
    <div className="setting-title"><label htmlFor={`vision-file-${bundleId}`}>Vision file</label><Help label="Vision companion">Image input needs a compatible GGUF vision projector, often named mmproj. Nearby files are listed for you to choose; compatibility is verified by loading and testing the model.</Help></div>
    <select id={`vision-file-${bundleId}`} value={selected} disabled={locked || !report} onChange={event => { setSelected(event.target.value); setMessage(""); }}><option value="">Text only</option>{candidates.map(item => <option key={item.path} value={item.path}>{item.name} · {formatBytes(item.size_bytes)}</option>)}{selected && !candidates.some(item => item.path === selected) ? <option value={selected}>{selected}</option> : null}</select>
    {active ? <p className="hint">Unload this model before changing its vision file, then start it again.</p> : null}
    {selected ? <p className="hint model-projector-path">{selected}</p> : null}
    <div className="actions"><button type="button" disabled={locked || !window.workbench?.selectPath} onClick={() => void chooseFile()}>Choose file</button><button type="button" disabled={locked || !report || selected === (report.selected_path ?? "")} onClick={() => void action(`projector-${bundleId}`, save)}>{busy ? "Saving…" : "Save image setup"}</button></div>
    {error ? <Notice tone="error" role="alert" action={!report ? <button type="button" disabled={disabled || busy} onClick={() => setRevision(value => value + 1)}>Retry</button> : undefined}>{error}</Notice> : null}{message ? <p role="status">{message}</p> : null}
  </details>;
}
