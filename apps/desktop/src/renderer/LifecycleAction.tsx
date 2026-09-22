import { useEffect, useRef, useState } from "react";
import { request } from "./api";
import { errorMessage } from "./errors";
import { Notice } from "./Notice";
import type { SchemaDeletePreview } from "../generated/shared-contracts/openapi";
import "./LifecycleAction.css";

/** Shared, read-before-confirm boundary for removing a workspace dependency. */
export function LifecycleAction({ path, name, label, confirmLabel = label, disabled = false, method = "DELETE", body, onComplete, onBusyChange }: {
  path: string; name: string; label: string; confirmLabel?: string; disabled?: boolean;
  method?: "DELETE" | "PATCH"; body?: unknown; onComplete: (record: unknown) => Promise<void> | void;
  onBusyChange?: (busy: boolean) => void;
}) {
  const [preview, setPreview] = useState<SchemaDeletePreview | null>(null);
  const [opened, setOpened] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const generation = useRef(0);
  const pending = useRef(false);
  useEffect(() => () => { generation.current++; onBusyChange?.(false); }, [path, onBusyChange]);
  async function inspect() {
    if (pending.current || disabled) return;
    const current = ++generation.current;
    pending.current = true; setOpened(true); setBusy(true); onBusyChange?.(true); setPreview(null); setError("");
    try { const next = await request<SchemaDeletePreview>(`${path}/delete-preview`); if (generation.current === current) setPreview(next); }
    catch (failure) { if (generation.current === current) setError(errorMessage(failure)); }
    finally { if (generation.current === current) { pending.current = false; setBusy(false); onBusyChange?.(false); } }
  }
  async function confirm() {
    if (pending.current || disabled || !preview || preview.blockers?.length) return;
    const current = generation.current;
    pending.current = true; setBusy(true); onBusyChange?.(true); setError("");
    try {
      const record = await request<unknown>(path, { method, ...(body === undefined ? {} : { body: JSON.stringify(body) }) });
      await onComplete(record);
      if (generation.current === current) { setOpened(false); setPreview(null); }
    } catch (failure) { if (generation.current === current) setError(errorMessage(failure)); }
    finally { onBusyChange?.(false); if (generation.current === current) { pending.current = false; setBusy(false); } }
  }
  return <div className="lifecycle-action">
    {!opened ? <button type="button" disabled={disabled || busy} onClick={() => void inspect()}>{label}</button> : <section className="lifecycle-preview" aria-label={`${label}: ${name}`}>
      <strong>{label}: {name}?</strong>
      {busy && !preview ? <p role="status">Checking affected items…</p> : null}
      {error ? <Notice tone="error">{error}</Notice> : null}
      {preview ? <>
        <p>{method === "PATCH" ? "Stops using this entry in future work. Its saved versions and history remain available." : preview.summary}</p>
        {preview.blockers?.length ? <Notice tone="warn"><ul>{preview.blockers.map(item => <li key={`${item.kind}:${item.id}`}>{item.label ?? item.kind}: {item.effect ?? "Resolve this item before continuing."}</li>)}</ul></Notice> : null}
        {preview.consumers?.length ? <ul className="lifecycle-consumers">{preview.consumers.map((item, index) => <li key={`${item.kind}:${item.id}:${index}`}><strong>{item.label ?? item.kind}</strong><span>{item.effect ?? (item.retained ? "History retained" : "Affected by this change")}{item.live ? " · Active work" : ""}</span></li>)}</ul> : <p className="hint">No dependent items found.</p>}
        {preview.retained?.length ? <p className="hint">Kept: {preview.retained.join("; ")}</p> : null}
      </> : null}
      <div className="actions"><button type="button" disabled={disabled || busy || !preview || Boolean(preview.blockers?.length)} onClick={() => void confirm()}>{busy && preview ? "Applying…" : confirmLabel}</button><button type="button" disabled={busy} onClick={() => void inspect()}>Refresh preview</button><button type="button" disabled={busy} onClick={() => { setOpened(false); setPreview(null); setError(""); }}>Cancel</button></div>
    </section>}
  </div>;
}
