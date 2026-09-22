import { createContext, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { packet03Request } from "./packet03Api";
import { Icon } from "./Icon";
import "./SourceReference.css";

export const SourceScope = createContext<{ sessionId?: string; projectPath?: string }>({});
interface Reference { assetId: string; sha256: string; source: string | null; line: number; start: number; end: number | null }
interface Passage { filename: string; sha256: string; source: string; extracted_line: number; start_char: number; end_char: number; text: string; truncated: boolean; parser?: string }
export function sourceReference(href?: string): Reference | null {
  try {
    const url = new URL(href ?? "");
    if (url.protocol !== "workbench-source:" || !/^asset_[a-z0-9]+$/i.test(url.hostname) || !/^\/[a-f0-9]{64}$/.test(url.pathname) || url.username || url.password || url.port) return null;
    const line = Number(url.searchParams.get("line") ?? 1), start = Number(url.searchParams.get("start") ?? 0), endValue = url.searchParams.get("end"), end = endValue === null ? null : Number(endValue);
    if (!Number.isSafeInteger(line) || line < 1 || !Number.isSafeInteger(start) || start < 0 || (end !== null && (!Number.isSafeInteger(end) || end < start))) return null;
    return { assetId: url.hostname, sha256: url.pathname.slice(1), source: url.searchParams.get("source"), line, start, end };
  } catch { return null; }
}

export function SourceLink({ href, children }: { href: string; children: ReactNode }) {
  const scope = useContext(SourceScope), reference = sourceReference(href);
  const [open, setOpen] = useState(false), [passage, setPassage] = useState<Passage>(), [error, setError] = useState(""), [saving, setSaving] = useState(false);
  const dialog = useRef<HTMLDialogElement>(null), trigger = useRef<HTMLButtonElement>(null), generation = useRef(0);
  useEffect(() => { generation.current++; setOpen(false); setPassage(undefined); }, [href, scope.sessionId, scope.projectPath]);
  useEffect(() => { if (open) dialog.current?.showModal(); else dialog.current?.close(); }, [open]);
  useEffect(() => () => { generation.current++; }, []);
  if (!reference || (!scope.sessionId && !scope.projectPath)) return <span>{children}</span>;
  function close() {
    generation.current++;
    dialog.current?.close();
    setOpen(false);
    trigger.current?.focus();
  }
  async function inspect() {
    if (!reference) return;
    const version = ++generation.current;
    setOpen(true); setPassage(undefined); setError("");
    try {
      const value = await packet03Request<Passage>(`/v1/assets/${encodeURIComponent(reference.assetId)}/source`, { method: "POST", body: JSON.stringify({ sha256: reference.sha256, source: reference.source, extracted_line: reference.line, start_char: reference.start, end_char: reference.end, session_id: scope.sessionId, project_path: scope.projectPath }) });
      if (generation.current === version) setPassage(value);
    } catch (caught) { if (generation.current === version) setError(caught instanceof Error ? caught.message : String(caught)); }
  }
  async function save() {
    if (!reference) return;
    setSaving(true); setError("");
    try {
      if (!window.workbench?.saveAsset) throw new Error("Saving originals is available in the desktop app.");
      await window.workbench.saveAsset({ assetId: reference.assetId, ...scope });
    } catch (caught) { setError(caught instanceof Error ? caught.message : String(caught)); }
    finally { setSaving(false); }
  }
  return <><button ref={trigger} className="source-reference-link" type="button" onClick={() => void inspect()}><Icon name="files" size={12} />{children}</button>
    {open && createPortal(<dialog ref={dialog} className="source-viewer" aria-label="Retained source" onCancel={event => { event.preventDefault(); close(); }} onClose={close}>
      <header><div><strong>{passage?.filename ?? "Retained source"}</strong><span>{passage?.source ?? (error ? "Source unavailable" : "Loading source…")}{reference.source ? ` · line ${reference.line}` : ""}</span></div><button type="button" className="icon-button" aria-label="Close source" onClick={close}><Icon name="close" /></button></header>
      {error ? <p role="alert">{error}</p> : null}
      {passage ? <><pre>{passage.text || "This range is empty."}</pre>{passage.truncated ? <p className="hint">Showing the first 12,000 characters of this range. Save the original to inspect the complete document.</p> : null}<footer><span title={passage.sha256}>Retained version {passage.sha256.slice(0, 10)}{passage.parser ? ` · ${passage.parser}` : ""}</span><button type="button" disabled={saving} onClick={() => void save()}><Icon name="download" size={14} />Save original</button></footer></> : !error ? <p role="status">Loading…</p> : null}
    </dialog>, document.body)}
  </>;
}

export function ReadSources({ text }: { text: string }) {
  try {
    const result = JSON.parse(text) as { excerpts?: Array<{ source?: string; extracted_line?: number; source_url?: string }> };
    const refs = result.excerpts?.filter(item => sourceReference(item.source_url)) ?? [];
    if (!refs.length) return null;
    return <details className="read-sources"><summary>Sources read · {refs.length} {refs.length === 1 ? "passage" : "passages"}</summary><ul>{refs.map((ref, i) => <li key={i}><SourceLink href={ref.source_url!}>{ref.source} · line {ref.extracted_line}</SourceLink></li>)}</ul></details>;
  } catch { return null; }
}
