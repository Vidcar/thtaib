import { useEffect, useRef, useState } from "react";
import { request } from "./api";
import { errorMessage } from "./errors";
import { Notice } from "./Notice";
import { PathBrowseButton } from "./PathField";
import { knowledgeApi, type KnowledgeScopeOption, type SkillResourceChange } from "./knowledgeApi";
import type { KnowledgeEntry } from "./types";
import type { SchemaSkillResource, SchemaSkillResourceView } from "../generated/shared-contracts/openapi";

type SkillResource = SchemaSkillResource;
type ResourceView = SchemaSkillResourceView;

export function SkillPackageImport({ entry, onImported }: { entry?: KnowledgeEntry; onImported: (entry: KnowledgeEntry) => Promise<void> }) {
  const [source, setSource] = useState("");
  const [destination, setDestination] = useState("user:");
  const [scopes, setScopes] = useState<KnowledgeScopeOption[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const pending = useRef(false);
  useEffect(() => { let cancelled = false; void knowledgeApi.scopes().then(next => { if (!cancelled) setScopes(next); }).catch(failure => { if (!cancelled) setError(errorMessage(failure)); }); return () => { cancelled = true; }; }, []);
  return <form className="workspace-editor" onSubmit={event => { event.preventDefault(); if (pending.current || !source.trim()) return; const scope = scopes.find(option => `${option.scope}:${option.scope_id ?? ""}` === destination); if (!entry && !scope) return; pending.current = true; setBusy(true); setError(""); void request<KnowledgeEntry>("/v1/knowledge/skills/import", { method: "POST", body: JSON.stringify({ source_path: source.trim(), scope: entry?.scope ?? scope?.scope, scope_id: entry?.scope_id ?? scope?.scope_id, ...(entry ? { entry_id: entry.id, base_version: entry.current_version_id } : {}) }) }).then(onImported).then(() => setSource("")).catch(failure => setError(errorMessage(failure))).finally(() => { pending.current = false; setBusy(false); }); }}>
    <p className="hint">Import a skill folder, SKILL.md or ZIP. Supporting files stay with this version; importing does not execute them.</p>
    <label>Package path<input value={source} disabled={busy} onChange={event => setSource(event.target.value)} placeholder="Folder, Markdown file or ZIP" /></label><div className="actions"><PathBrowseButton kind="folder" label="Choose folder" disabled={busy} onPicked={setSource} onError={failure => setError(errorMessage(failure))} /><PathBrowseButton kind="file" label="Choose file" disabled={busy} onPicked={setSource} onError={failure => setError(errorMessage(failure))} /></div>
    {!entry ? <label>Use in<select disabled={busy} value={destination} onChange={event => setDestination(event.target.value)}>{scopes.filter(option => option.active).map(option => <option key={`${option.scope}:${option.scope_id ?? ""}`} value={`${option.scope}:${option.scope_id ?? ""}`}>{option.label}</option>)}</select></label> : null}
    <button type="submit" disabled={busy || !source.trim()}>{busy ? "Importing…" : entry ? "Import as new version" : "Import skill"}</button>{error ? <Notice tone="error">{error}</Notice> : null}
  </form>;
}

export function SkillResources({ versionId, resources = [] }: { versionId: string; resources?: SkillResource[] }) {
  const [selection, setSelection] = useState<{ versionId: string; path: string } | null>(null);
  const [preview, setPreview] = useState<{ versionId: string; path: string; resource: ResourceView | null; error: string; loading: boolean } | null>(null);
  const path = selection?.versionId === versionId && resources.some(item => item.path === selection.path) ? selection.path : "";
  const current = preview?.versionId === versionId && preview.path === path ? preview : null;
  useEffect(() => {
    if (!path) { setPreview(null); return; }
    let cancelled = false;
    const owner = { versionId, path };
    setPreview({ ...owner, resource: null, error: "", loading: true });
    void request<ResourceView>(`/v1/knowledge/versions/${versionId}/resource?path=${encodeURIComponent(path)}`)
      .then(resource => { if (!cancelled) setPreview({ ...owner, resource, error: "", loading: false }); })
      .catch(failure => { if (!cancelled) setPreview({ ...owner, resource: null, error: errorMessage(failure), loading: false }); });
    return () => { cancelled = true; };
  }, [versionId, path]);
  return <details><summary>Supporting files · {resources.length}</summary>{resources.length ? <div className="setup-selection-options">{resources.map(item => <button key={item.path} type="button" onClick={() => setSelection({ versionId, path: item.path })} aria-pressed={path === item.path}>{item.path} <span className="hint">{Math.ceil(item.size_bytes / 1024)} KB</span></button>)}</div> : <p className="hint">This version has no supporting files.</p>}{current?.loading ? <p role="status">Loading file…</p> : null}{current?.error ? <Notice tone="error">{current.error}</Notice> : null}{current?.resource ? <section><h4>{current.resource.path}</h4>{current.resource.binary ? <p className="hint">Binary file retained with the skill; text preview is unavailable.</p> : <pre className="wrapped-text">{current.resource.content}</pre>}<p className="hint">Read-only supporting content. Execution is unavailable.</p></section> : null}</details>;
}

export function SkillResourceEditor({ versionId, resources = [], changes, onChange, disabled = false, onPendingChange }: { versionId?: string; resources?: SkillResource[]; changes: SkillResourceChange[]; onChange: (changes: SkillResourceChange[]) => void; disabled?: boolean; onPendingChange?: (pending: boolean) => void }) {
  const [path, setPath] = useState("");
  const [error, setError] = useState("");
  const [reading, setReading] = useState(false);
  const currentChanges = useRef(changes); currentChanges.current = changes;
  const paths = [...new Set([...resources.map(resource => resource.path), ...changes.map(change => change.path)])].sort();
  async function upload(file: File) {
    if (reading) return;
    if (file.size > 16 * 1024 * 1024) { setError("Choose a file up to 16 MB."); return; }
    setReading(true); onPendingChange?.(true); setError("");
    try {
      const target = path.trim() || file.name;
      const bytes = new Uint8Array(await file.arrayBuffer());
      let binary = "";
      for (let index = 0; index < bytes.length; index += 8192) binary += String.fromCharCode(...bytes.subarray(index, index + 8192));
      onChange([...currentChanges.current.filter(change => change.path !== target), { path: target, content_base64: btoa(binary) }]);
      setPath("");
    } catch (failure) { setError(errorMessage(failure)); }
    finally { setReading(false); onPendingChange?.(false); }
  }
  return <details className="setup-options"><summary>Supporting files · {paths.filter(path => !changes.find(change => change.path === path)?.remove).length}</summary>
    <label>File path<input value={path} disabled={disabled || reading} onChange={event => setPath(event.target.value)} placeholder="references/guide.md" /></label>
    <label>Add or replace file<input type="file" disabled={disabled || reading} onChange={event => { const file = event.target.files?.[0]; event.target.value = ""; if (file) void upload(file); }} /></label>
    {reading ? <p className="hint" role="status">Reading file…</p> : null}{error ? <Notice tone="error">{error}</Notice> : null}
    <ul className="plain-list">{paths.map(resourcePath => { const change = changes.find(change => change.path === resourcePath); const saved = resources.some(resource => resource.path === resourcePath); return <li key={resourcePath} className="actions"><span>{resourcePath}{change ? change.remove ? " · removed" : saved ? " · replaced" : " · added" : ""}</span>{change ? <button type="button" disabled={disabled || reading} onClick={() => onChange(changes.filter(item => item.path !== resourcePath))}>{saved ? "Undo" : "Remove"}</button> : <button type="button" disabled={disabled || reading} onClick={() => onChange([...changes, { path: resourcePath, remove: true }])}>Remove</button>}</li>; })}</ul>
    {versionId && resources.length ? <SkillResources versionId={versionId} resources={resources} /> : null}
  </details>;
}
