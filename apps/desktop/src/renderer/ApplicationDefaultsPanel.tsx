import { useEffect, useRef, useState } from "react";
import { request } from "./api";
import { SetupConfigurationEditor, scopedSetupConfiguration, useSetupCatalogue, visualSetupCompatibilityIssue } from "./SetupConfigurationEditor";
import type { SetupConfiguration } from "./workspaceApi";
import { Notice } from "./Notice";
import { errorMessage } from "./errors";
import "./WorkspacePanels.css";

export function ApplicationDefaultsPanel() {
  const [value, setValue] = useState<SetupConfiguration>({});
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);
  const pending = useRef(false);
  const { catalogue, error: catalogueError } = useSetupCatalogue();
  const visualCompatibilityIssue = visualSetupCompatibilityIssue(value, catalogue);
  useEffect(() => { let cancelled = false; void request<SetupConfiguration>("/v1/setup-defaults").then(next => { if (!cancelled) setValue(next); }).catch(failure => { if (!cancelled) setError(errorMessage(failure)); }).finally(() => { if (!cancelled) setLoading(false); }); return () => { cancelled = true; }; }, []);
  const save = () => { if (pending.current) return; if (visualCompatibilityIssue) { setError(visualCompatibilityIssue); return; } pending.current = true; setBusy(true); setSaved(false); setError(""); void request<SetupConfiguration>("/v1/setup-defaults", { method: "PUT", body: JSON.stringify(scopedSetupConfiguration(value, "application")) }).then(next => { setValue(next); setSaved(true); }).catch(failure => setError(errorMessage(failure))).finally(() => { pending.current = false; setBusy(false); }); };
  return <section className="setting-section workspace-records-surface">
    <header className="setting-section-head"><div><h3>Default access for new chats</h3><p>Each chat remembers Ask or Full access after it is created.</p></div></header>
    {error || catalogueError ? <Notice tone="error">{error || catalogueError}</Notice> : null}
    {loading ? <p role="status" className="hint">Loading defaults…</p> : <form className="workspace-editor" onSubmit={event => { event.preventDefault(); save(); }}>
      <SetupConfigurationEditor scope="application" value={value} onChange={next => { setValue(next); setSaved(false); }} catalogue={catalogue} disabled={busy} />
      <div className="setting-actions">{saved ? <p role="status" className="hint">Defaults saved for future work.</p> : null}<button type="submit" className="primary-button" disabled={busy || Boolean(visualCompatibilityIssue)}>{busy ? "Saving…" : "Save defaults"}</button></div>
    </form>}
  </section>;
}
