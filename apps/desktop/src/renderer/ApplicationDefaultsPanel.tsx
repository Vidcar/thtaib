import { useEffect, useRef, useState } from "react";
import { request } from "./api";
import { SetupConfigurationEditor, useSetupCatalogue } from "./SetupConfigurationEditor";
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
  useEffect(() => { let cancelled = false; void request<SetupConfiguration>("/v1/setup-defaults").then(next => { if (!cancelled) setValue(next); }).catch(failure => { if (!cancelled) setError(errorMessage(failure)); }).finally(() => { if (!cancelled) setLoading(false); }); return () => { cancelled = true; }; }, []);
  return <details className="card workspace-records-surface"><summary>Default agent setup</summary><p className="hint">The starting point for new work. Project and saved agent choices build on these defaults. Existing runs keep their settings.</p>{error || catalogueError ? <Notice tone="error">{error || catalogueError}</Notice> : null}{loading ? <p role="status">Loading defaults…</p> : <form className="workspace-editor" onSubmit={event => { event.preventDefault(); if (pending.current) return; pending.current = true; setBusy(true); setSaved(false); setError(""); void request<SetupConfiguration>("/v1/setup-defaults", { method: "PUT", body: JSON.stringify(value) }).then(next => { setValue(next); setSaved(true); }).catch(failure => setError(errorMessage(failure))).finally(() => { pending.current = false; setBusy(false); }); }}><SetupConfigurationEditor value={value} onChange={next => { setValue(next); setSaved(false); }} catalogue={catalogue} disabled={busy} /><button type="submit" disabled={busy}>Save defaults</button>{saved ? <p role="status" className="hint">Defaults saved for future work.</p> : null}</form>}</details>;
}
