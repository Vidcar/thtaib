import { useEffect, useRef, useState } from "react";
import { workspaceApi, type ProjectFiles, type ProjectRecord, type SetupConfiguration } from "./workspaceApi";
import { SetupConfigurationEditor, useSetupCatalogue } from "./SetupConfigurationEditor";
import { errorMessage } from "./errors";
import { formatBytes } from "./display";
import { HoverHelp } from "./HoverHelp";
import { Icon } from "./Icon";
import { Notice } from "./Notice";
import { LifecycleAction } from "./LifecycleAction";
import "./WorkspacePanels.css";

export function ProjectsPanel({ onOpenChat, onAddProject, projectRevision = 0, focusProjectId = null, onFocusHandled }: { onOpenChat?: (project: ProjectRecord) => void; onAddProject?: () => void; projectRevision?: number; focusProjectId?: string | null; onFocusHandled?: () => void }) {
  const [projects, setProjects] = useState<ProjectRecord[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [drafts, setDrafts] = useState<Record<string, { name: string; defaults: SetupConfiguration }>>({});
  const [files, setFiles] = useState<ProjectFiles | null>(null);
  const [folder, setFolder] = useState("");
  const [fileError, setFileError] = useState("");
  const [filesLoading, setFilesLoading] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const actionPending = useRef(false);
  const { catalogue, error: catalogueError } = useSetupCatalogue();
  const selected = projects.find(project => project.id === selectedId);
  const draft = selected ? drafts[selected.id] ?? { name: selected.name, defaults: selected.defaults } : { name: "", defaults: {} };
  async function refresh(preferredId?: string) {
    const next = await workspaceApi.projects(); setProjects(next);
    setSelectedId(current => next.some(project => project.id === (preferredId ?? current)) ? preferredId ?? current : next[0]?.id ?? "");
  }
  useEffect(() => { let cancelled = false; void workspaceApi.projects().then(next => { if (!cancelled) { setProjects(next); setSelectedId(current => { const preferred = focusProjectId && next.some(project => project.id === focusProjectId) ? focusProjectId : current; return next.some(project => project.id === preferred) ? preferred : next[0]?.id ?? ""; }); if (focusProjectId) onFocusHandled?.(); } }).catch(failure => { if (!cancelled) setError(errorMessage(failure)); }).finally(() => { if (!cancelled) setLoading(false); }); return () => { cancelled = true; }; }, [projectRevision, focusProjectId, onFocusHandled]);
  useEffect(() => { setFolder(""); }, [selectedId]);
  useEffect(() => {
    setFiles(null); setFileError("");
    if (!selectedId) return;
    let cancelled = false; setFilesLoading(true);
    void workspaceApi.projectFiles(selectedId, folder).then(next => { if (!cancelled) setFiles(next); }).catch(failure => { if (!cancelled) setFileError(errorMessage(failure)); }).finally(() => { if (!cancelled) setFilesLoading(false); });
    return () => { cancelled = true; };
  }, [selectedId, folder]);
  async function action(work: () => Promise<void>) { if (actionPending.current) return; actionPending.current = true; setBusy(true); setError(""); setMessage(""); try { await work(); } catch (failure) { setError(errorMessage(failure)); } finally { actionPending.current = false; setBusy(false); } }
  function updateDraft(patch: Partial<typeof draft>) { if (selected) setDrafts(current => ({ ...current, [selected.id]: { ...(current[selected.id] ?? { name: selected.name, defaults: selected.defaults }), ...patch } })); }
  return <section className="surface workspace-records-surface">
    <header className="surface-head"><div className="entity-head"><h2>Projects</h2><HoverHelp title="About projects">A project links an existing folder with its own defaults and Knowledge. Conversations stay in their original project. Removing the link never deletes source files.</HoverHelp></div><button disabled={busy} onClick={() => onAddProject?.()}><Icon name="plus" size={15} /> Add project</button></header>
    {error ? <Notice tone="error">{error}{!projects.length ? <button onClick={() => void action(refresh)}>Retry</button> : null}</Notice> : null}{catalogueError ? <Notice tone="warn">Some defaults could not load: {catalogueError}</Notice> : null}{message ? <p role="status" className="hint">{message}</p> : null}
    <div className="workspace-records-layout"><aside className="workspace-record-list" aria-label="Your projects">{loading ? <p className="hint">Loading projects…</p> : !projects.length ? <p className="hint">Add a folder to keep its chats, defaults and Knowledge together.</p> : <ul className="nav-list">{projects.map(project => <li key={project.id}><button type="button" disabled={busy} className={project.id === selectedId ? "nav-item active" : "nav-item"} onClick={() => setSelectedId(project.id)}><span className="nav-item-title">{project.name}</span><span className="nav-item-meta">{project.missing ? "Folder unavailable" : project.path}{drafts[project.id] ? " · Unsaved changes" : ""}</span></button></li>)}</ul>}</aside>
    <div className="workspace-record-detail">{selected ? <>
      <section className="card"><div className="section-heading"><h3>{selected.name}</h3>{onOpenChat ? <button disabled={busy || selected.missing} onClick={() => onOpenChat(selected)}><Icon name="chat" size={15} /> Open project chat</button> : null}</div><p className="workspace-path">{selected.path}</p>{selected.missing ? <Notice tone="warn">This folder is unavailable. Reconnect its drive or restore the folder before using file tools.</Notice> : null}</section>
      <details className="card"><summary>Project defaults</summary><form className="workspace-editor" onSubmit={event => { event.preventDefault(); if (draft.name.trim()) void action(async () => { await workspaceApi.updateProject(selected.id, { name: draft.name.trim(), defaults: draft.defaults }); await refresh(selected.id); setDrafts(current => { const next = { ...current }; delete next[selected.id]; return next; }); setMessage("Project defaults saved for future work."); }); }}><label>Name<input required maxLength={200} value={draft.name} disabled={busy} onChange={event => updateDraft({ name: event.target.value })} /></label><SetupConfigurationEditor value={draft.defaults} onChange={defaults => updateDraft({ defaults })} disabled={busy} catalogue={catalogue} /><div className="actions"><button className="primary-button" disabled={busy || !draft.name.trim()}>Save defaults</button>{drafts[selected.id] ? <button type="button" disabled={busy} onClick={() => setDrafts(current => { const next = { ...current }; delete next[selected.id]; return next; })}>Discard edits</button> : null}</div></form></details>
      <section className="card project-files"><div className="section-heading"><h3>Files</h3>{folder ? <button type="button" disabled={filesLoading} onClick={() => setFolder(folder.replaceAll("\\", "/").split("/").slice(0, -1).join("/"))}>Up one folder</button> : null}</div>{folder ? <p className="hint workspace-path">{folder}</p> : null}{filesLoading ? <p className="hint" role="status">Reading folder…</p> : fileError ? <Notice tone="error">{fileError}<button type="button" onClick={() => setFolder("")}>Return to project folder</button></Notice> : files ? <ul className="plain-list">{files.entries.map(file => <li key={file.path}>{file.kind === "directory" ? <button type="button" onClick={() => setFolder(file.path)}><Icon name="folder" size={14} /><span>{file.name}</span></button> : <span><Icon name="files" size={14} /><span>{file.name}</span></span>}<small className="hint">{file.kind === "directory" ? "Folder" : formatBytes(file.size_bytes)}</small></li>)}{!files.entries.length ? <li className="hint">This folder is empty.</li> : null}</ul> : null}</section>
      <LifecycleAction key={selected.id} path={`/v1/projects/${selected.id}`} name={selected.name} label="Remove project link" confirmLabel="Remove link" disabled={busy} onBusyChange={setBusy} onComplete={async () => { await refresh(); setMessage("Project link removed. Source files are unchanged."); }} />
    </> : <div className="card"><h3>Choose a project</h3><p className="hint">Select an existing project or add a folder.</p></div>}</div></div>
  </section>;
}
