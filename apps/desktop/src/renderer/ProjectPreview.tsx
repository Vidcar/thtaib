import { useEffect, useRef, useState } from "react";
import { request } from "./api";
import { errorMessage } from "./errors";

interface Preview { state: "active" | "closed" | "lost"; url?: string | null; entry_path?: string | null; error?: string | null }
interface PreviewProps { threadId?: string | null; selectedPath: string; enabled: boolean; revision?: string }

export function ProjectPreview(props: PreviewProps) {
  // A saved preview and every pending request belong to exactly one chat.
  return props.threadId ? <ThreadPreview key={props.threadId} {...props} threadId={props.threadId} /> : null;
}

function ThreadPreview({ threadId, selectedPath, enabled, revision }: PreviewProps & { threadId: string }) {
  const [preview, setPreview] = useState<Preview>();
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const requestSequence = useRef(0);
  const mutating = useRef(false);
  const mounted = useRef(false);
  const endpoint = `/v1/previews/${encodeURIComponent(threadId)}`;
  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; requestSequence.current += 1; };
  }, []);
  useEffect(() => {
    let disposed = false;
    const refresh = () => {
      if (mutating.current) return;
      const sequence = ++requestSequence.current;
      void request<Preview>(endpoint).then(value => {
        if (!disposed && sequence === requestSequence.current) { setPreview(value); setError(""); }
      }).catch(caught => {
        if (!disposed && sequence === requestSequence.current) setError(errorMessage(caught));
      });
    };
    refresh();
    const timer = setInterval(refresh, 3000);
    return () => { disposed = true; clearInterval(timer); };
  }, [endpoint, revision]);
  const state = preview?.state;
  const canOpen = state === "active" && preview?.url && /^http:\/\/(127\.0\.0\.1|localhost)(:\d+)?\//.test(preview.url);
  const html = /\.html?$/i.test(selectedPath);
  async function act(action: "start" | "stop" | "reset") {
    if (mutating.current) return;
    mutating.current = true;
    const sequence = ++requestSequence.current;
    setBusy(true); setError("");
    try {
      const value = await request<Preview>(`${endpoint}${action === "stop" ? "" : `/${action}`}`, {
        method: action === "stop" ? "DELETE" : "POST", ...(action === "start" ? {body: JSON.stringify({entry_path: selectedPath})} : {}),
      });
      if (mounted.current && sequence === requestSequence.current) setPreview(value);
    } catch (caught) {
      if (mounted.current && sequence === requestSequence.current) setError(errorMessage(caught));
    } finally {
      mutating.current = false;
      if (mounted.current) setBusy(false);
    }
  }
  return <section className="project-preview" aria-label="Project preview"><div className="project-preview-actions">
    <strong>Preview</strong><span className="hint">{state === "active" ? "Running" : state === "lost" ? "Lost" : state === "closed" ? "Stopped" : "Checking…"}</span>
    {canOpen ? <a href={preview!.url!} target="_blank" rel="noreferrer">Open</a> : null}
    {state === "active" ? <button type="button" disabled={busy} onClick={() => void act("stop")}>Stop</button> : null}
    {state === "lost" ? <button type="button" disabled={busy} title="Clear the lost status without stopping any unverified process" onClick={() => void act("reset")}>Clear lost preview</button> : null}
    {html ? <button type="button" disabled={!enabled || busy || state === "lost"} title={enabled ? "Open this HTML page through a local server" : "Enable project preview in Browser tools first"} onClick={() => void act("start")}>Preview page</button> : null}
    </div>{preview?.entry_path ? <small className="hint">{preview.entry_path}</small> : null}
    {error || preview?.error ? <p className="tool-call-error" role="status">{error || preview?.error}</p> : null}
  </section>;
}
