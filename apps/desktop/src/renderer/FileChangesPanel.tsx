import { useEffect, useRef, useState } from "react";
import type { SchemaProjectFileChangeView } from "../generated/shared-contracts/openapi";
import { request } from "./api";
import { errorMessage } from "./errors";
import { CodeBlock } from "./AgentMessageFeed";
import { ConfirmNote } from "./ConfirmNote";
import { Notice } from "./Notice";
import { StatusBadge } from "./StatusBadge";
import "./FileChangesPanel.css";

type FileChange = SchemaProjectFileChangeView;
export function FileChangesPanel({ runIds, currentRunId, currentRunStatus }: { runIds: string[]; currentRunId?: string | null; currentRunStatus?: string }) {
  const [runId, setRunId] = useState(currentRunId ?? runIds.at(-1) ?? "");
  const [changes, setChanges] = useState<FileChange[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [confirm, setConfirm] = useState(false);
  const [revision, setRevision] = useState(0);
  const pending = useRef(false);
  const generation = useRef(0);
  const selected = changes.find(item => item.change.id === selectedId);
  const ids = [...new Set([...runIds, ...(currentRunId ? [currentRunId] : [])])].reverse();
  useEffect(() => { setRunId(currentRunId ?? runIds.at(-1) ?? ""); }, [currentRunId, runIds.join("|")]);
  useEffect(() => {
    const owner = ++generation.current;
    setChanges([]); setConfirm(false); setError("");
    if (!runId) return;
    setLoading(true);
    void request<FileChange[]>(`/v1/agent-runs/${runId}/file-changes`).then(next => { if (generation.current === owner) { setChanges(next); setSelectedId(current => next.some(item => item.change.id === current) ? current : next[0]?.change.id ?? ""); } }).catch(failure => { if (generation.current === owner) setError(errorMessage(failure)); }).finally(() => { if (generation.current === owner) setLoading(false); });
    return () => { generation.current += 1; };
  }, [runId, currentRunStatus, revision]);
  async function reverse() {
    if (!selected || pending.current || !selected.reversal_available) return;
    const owner = generation.current;
    pending.current = true; setBusy(true); setError("");
    try {
      const next = await request<FileChange>(`/v1/agent-runs/${runId}/file-changes/${selected.change.id}/reverse`, { method: "POST" });
      if (generation.current === owner) { setChanges(current => current.map(item => item.change.id === next.change.id ? next : item)); setConfirm(false); }
    } catch (failure) { if (generation.current === owner) setError(errorMessage(failure)); }
    finally { pending.current = false; setBusy(false); }
  }
  return <section className="file-changes-panel"><div className="file-changes-heading"><h4>Changed project files</h4><button type="button" disabled={busy || loading || !runId} onClick={() => setRevision(value => value + 1)}>Refresh</button></div>{ids.length ? <label>Turn<select aria-label="File changes turn" value={runId} disabled={busy} onChange={event => setRunId(event.target.value)}>{ids.map((id, index) => <option key={id} value={id}>{id === currentRunId ? "Latest turn" : `Earlier turn ${ids.length - index}`}</option>)}</select></label> : null}
    {loading ? <p role="status" className="hint">Reading file changes…</p> : !changes.length && !error ? <p className="hint">No recorded project file changes for this turn.</p> : null}{error ? <Notice tone="error">{error}</Notice> : null}
    <ul className="plain-list file-change-list">{changes.map(item => <li key={item.change.id}><button type="button" disabled={busy} aria-pressed={item.change.id === selectedId} onClick={() => { setSelectedId(item.change.id); setConfirm(false); }}><span>{item.change.destination ? `${item.change.path} → ${item.change.destination}` : item.change.path}</span><small>{item.change.operation}{item.change.reversed_at ? " · reversed" : ""}</small></button></li>)}</ul>
    {selected ? <div className="file-change-detail"><div className="file-changes-heading"><strong>{selected.change.path}</strong><StatusBadge label={selected.change.status} /></div>{selected.change.error ? <Notice tone="error">{selected.change.error}</Notice> : null}{selected.diff != null ? <CodeBlock text={selected.diff || "No text difference."} label="Copy file difference" preClassName="file-change-diff" ariaLabel="File difference" /> : <p className="hint">{selected.diff_unavailable_reason || "A text difference is unavailable."}</p>}<details><summary>Before and after</summary>{(["before", "after"] as const).map(side => <section key={side}><h5>{side === "before" ? "Before" : "After"}</h5>{selected.change[side]?.text != null ? <CodeBlock text={selected.change[side]?.text ?? ""} label={`Copy ${side === "before" ? "before" : "after"}`} preClassName="file-change-diff" /> : <p className="hint">{selected.change[side]?.exists ? "Text preview unavailable." : "File does not exist."}</p>}</section>)}</details>
      <p className="hint">{selected.note}</p>{selected.reversal_available ? confirm ? <ConfirmNote className="notice" disabled={busy} confirmLabel="Reverse change" cancelLabel="Keep change" onConfirm={() => void reverse()} onCancel={() => setConfirm(false)}>Reverse this file change? The current file must still match the recorded result.</ConfirmNote> : <button disabled={busy} type="button" onClick={() => setConfirm(true)}>Reverse this file change</button> : <p className="hint">{selected.change.reversed_at ? "This change has been reversed." : selected.reversal_unavailable_reason || "This change cannot be reversed."}</p>}
    </div> : null}
  </section>;
}
