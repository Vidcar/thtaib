import { useRef, useState } from "react";
import { api } from "./api";
import { formatBytes } from "./display";
import { errorMessage } from "./errors";
import { Notice } from "./Notice";
import { Icon } from "./Icon";
import type { DeletePreview } from "./types";

export function ModelDeletion({ kind, id, name, onDeleted }: { kind: "bundle" | "profile"; id: string; name: string; onDeleted: () => Promise<void> }) {
  const [preview, setPreview] = useState<DeletePreview | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [permanent, setPermanent] = useState(false);
  const pending = useRef(false);
  const noun = kind === "bundle" ? "model installation" : "preset";
  async function inspect(deleteFiles = permanent) {
    if (pending.current) return;
    pending.current = true;
    setPermanent(deleteFiles); setPreview(null);
    setBusy(true); setError("");
    try { setPreview(await api.deletionPreview(kind, id, deleteFiles)); } catch (failure) { setError(errorMessage(failure)); } finally { pending.current = false; setBusy(false); }
  }
  async function remove() {
    if (pending.current || !preview || preview.blockers.length) return;
    pending.current = true;
    setBusy(true); setError("");
    try { await api.deleteModelRecord(kind, id, permanent); setPreview(null); await onDeleted(); }
    catch (failure) { setError(errorMessage(failure)); } finally { pending.current = false; setBusy(false); }
  }
  return <div className="model-deletion">
    {kind === "bundle" ? <div className="actions"><button type="button" title="Remove the installation; preserve external original files" disabled={busy} onClick={() => void inspect(false)}>Remove installation</button><button type="button" disabled={busy} onClick={() => void inspect(true)}><Icon name="trash" size={14} />Delete from disk</button></div> : <button type="button" className="icon-button" title={`Remove ${noun}`} aria-label={`Remove ${name}`} disabled={busy} onClick={() => void inspect(false)}><Icon name="trash" size={16} /></button>}
    {error ? <Notice tone="error">{error}</Notice> : null}
    {preview ? <section className="inline-note" aria-label={`Remove ${name}`}>
      <h4>{permanent ? "Permanently delete" : "Remove"} {name}?</h4>
      <p>{permanent ? "Deletes the files listed below, including original imports, and removes this model’s saved setups and installation records. This cannot be undone." : `Removes this ${noun} from future selection. History keeps its recorded configuration.`}</p>
      {kind === "bundle" ? <p><strong>{formatBytes(preview.removable_bytes)}</strong> will be freed. {permanent ? "Shared files and active work must be resolved first." : "External original files and shared files are kept."}</p> : null}
      {preview.blockers.length ? <Notice tone="warn">Finish or cancel the active work, then refresh this preview before removing it.<ul>{preview.blockers.map((item, index) => <li key={`${item.kind}-${item.id}-${index}`}>{item.label ?? item.kind}</li>)}</ul></Notice> : null}
      {preview.consumers.length || preview.retained.length ? <details><summary>Saved items and retained history</summary><ul>{preview.consumers.map((item, index) => <li key={`${item.kind}-${item.id}-${index}`}>{item.label ?? item.kind} — {item.retained ? "retained" : "removed"}</li>)}{preview.retained.map(item => <li key={item}>{item}</li>)}</ul></details> : null}
      {preview.files.length ? <details open={permanent}><summary>File changes ({preview.files.length})</summary><ul>{preview.files.map(file => <li key={file.path}><code>{file.path}</code> — {file.removable ? "delete" : file.reason ?? "keep"}</li>)}</ul></details> : null}
      <div className="actions"><button type="button" disabled={busy || Boolean(preview.blockers.length)} onClick={() => void remove()}>{permanent ? "Permanently delete files" : "Confirm removal"}</button><button type="button" disabled={busy} onClick={() => void inspect()}>Refresh preview</button><button type="button" disabled={busy} onClick={() => setPreview(null)}>Cancel</button></div>
    </section> : null}
  </div>;
}
