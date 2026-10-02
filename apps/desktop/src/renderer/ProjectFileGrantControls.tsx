import { useEffect, useRef, useState } from "react";
import { workspaceApi, type ProjectRecord } from "./workspaceApi";
import { packet03Api } from "./packet03Api";
import { errorMessage } from "./errors";
import { Notice } from "./Notice";
import { HoverHelp } from "./HoverHelp";

export function ProjectFileGrantControls({ onSaved }: { onSaved: () => Promise<void> }) {
  const [projects, setProjects] = useState<ProjectRecord[]>([]);
  const [projectId, setProjectId] = useState("");
  const [operations, setOperations] = useState<Array<"write_file" | "edit_file">>(["write_file", "edit_file"]);
  const [exclusions, setExclusions] = useState(".env\n.env.*\n**/.env\n**/.env.*");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const pending = useRef(false);
  useEffect(() => { let cancelled = false; void workspaceApi.projects().then(next => { if (!cancelled) setProjects(next.filter(project => !project.missing)); }).catch(failure => { if (!cancelled) setError(errorMessage(failure)); }); return () => { cancelled = true; }; }, []);
  const project = projects.find(item => item.id === projectId);
  return <details className="setup-options"><summary>Grant project file changes</summary>
    <form className="workspace-editor" onSubmit={event => {
      event.preventDefault(); if (pending.current || !project || !operations.length) return;
      pending.current = true; setBusy(true); setError("");
      void packet03Api.allowProjectFiles({ project_id: project.id, operations, excluded_paths: exclusions.split(/\r?\n/).map(value => value.trim()).filter(Boolean) })
        .then(onSaved).then(() => setProjectId(""))
        .catch(failure => setError(errorMessage(failure))).finally(() => { pending.current = false; setBusy(false); });
    }}>
      <label>Project<select value={projectId} disabled={busy} onChange={event => setProjectId(event.target.value)}><option value="">Choose a project</option>{projects.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
      {project ? <p className="hint">{project.path}</p> : null}
      <fieldset disabled={busy}><legend>Native file operations</legend>{([['write_file', 'Create files'], ['edit_file', 'Edit files']] as const).map(([value, label]) => <label key={value}><input type="checkbox" checked={operations.includes(value)} onChange={event => setOperations(current => event.target.checked ? [...current, value] : current.filter(item => item !== value))} />{label}</label>)}</fieldset>
      <label>Excluded paths or glob patterns, one per line<textarea value={exclusions} disabled={busy} onChange={event => setExclusions(event.target.value)} placeholder="private/**" rows={4} /></label>
      <div className="actions"><button type="submit" disabled={busy || !project || !operations.length}>{busy ? "Saving…" : "Grant these file changes"}</button><HoverHelp title="About project file grants">In Ask mode, selected Create/Edit tools may change files in this project across sessions. Excluded paths still require approval. The .git tree and links outside the project are always excluded. Commands, deletion, browser and account actions keep their own approvals. Reading stays controlled by selected tools.</HoverHelp></div>
      {error ? <Notice tone="error">{error}</Notice> : null}
    </form>
  </details>;
}
