import { useState } from "react";
import { api } from "./api";
import { formatBytes } from "./display";
import { errorMessage } from "./errors";
import { Notice } from "./Notice";
import type { DeletePreview } from "./types";

export function ModelDeletion({ kind, id, name, onDeleted }: { kind: "bundle" | "profile"; id: string; name: string; onDeleted: () => Promise<void> }) {
  const [preview, setPreview] = useState<DeletePreview | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const noun = kind === "bundle" ? "model installation" : "preset";
  async function inspect() {
    setBusy(true); setError("");
    try { setPreview(await api.deletionPreview(kind, id)); } catch (failure) { setError(errorMessage(failure)); } finally { setBusy(false); }
  }
  async function remove() {
    setBusy(true); setError("");
    try { await api.deleteModelRecord(kind, id); setPreview(null); await onDeleted(); }
    catch (failure) { setError(errorMessage(failure)); } finally { setBusy(false); }
  }
  return <div className="model-deletion">
    <button type="button" disabled={busy} onClick={() => void inspect()}>Remove {noun}…</button>
    {error ? <Notice tone="error">{error}</Notice> : null}
    {preview ? <section className="inline-note" aria-label={`Remove ${name}`}>
      <h4>Remove {name}?</h4>
      <p>This removes the {noun} from future selection. Retained history keeps its recorded configuration and may show an unavailable dependency.</p>
      {kind === "bundle" ? <p>Eligible owned files: {formatBytes(preview.removable_bytes)}. Original imports and shared files are excluded.</p> : null}
      {preview.blockers.length ? <Notice tone="warn">Finish or cancel the active work, then refresh this preview before removing it.<ul>{preview.blockers.map((item, index) => <li key={`${item.kind}-${item.id}-${index}`}>{item.label ?? item.kind}</li>)}</ul></Notice> : null}
      {preview.consumers.length ? <><p>Affected saved items:</p><ul>{preview.consumers.map((item, index) => <li key={`${item.kind}-${item.id}-${index}`}>{item.label ?? item.kind} — {item.retained ? "retained" : "removed"}</li>)}</ul></> : null}
      {preview.retained.length ? <ul>{preview.retained.map(item => <li key={item}>{item}</li>)}</ul> : null}
      {preview.files.length ? <details><summary>File changes</summary><ul>{preview.files.map(file => <li key={file.path}><code>{file.path}</code> — {file.removable ? "remove" : file.reason ?? "retain"}</li>)}</ul></details> : null}
      <div className="actions"><button type="button" disabled={busy || Boolean(preview.blockers.length)} onClick={() => void remove()}>Confirm removal</button><button type="button" disabled={busy} onClick={() => void inspect()}>Refresh preview</button><button type="button" disabled={busy} onClick={() => setPreview(null)}>Keep {noun}</button></div>
    </section> : null}
  </div>;
}
