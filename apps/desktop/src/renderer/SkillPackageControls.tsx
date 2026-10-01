import { useEffect, useRef, useState } from "react";
import { request } from "./api";
import { errorMessage } from "./errors";
import { Notice } from "./Notice";
import { PathBrowseButton } from "./PathField";
import { knowledgeApi, type KnowledgeScopeOption, type SkillResourceChange } from "./knowledgeApi";
import type { KnowledgeEntry } from "./types";
import type { SchemaSkillResource, SchemaSkillResourceView } from "../generated/shared-contracts/openapi";

type SkillResource = SchemaSkillResource;
type ResourceView = SchemaSkillResourceView & { execution_supported?: boolean };

interface BundledSkill {
  id: string; name: string; description: string; content: string; sha256: string;
  resources: Array<{ path: string; sha256: string; size_bytes: number }>;
  required_tools: string[]; required_connections: string[]; requires_project: boolean;
}

export function BundledRuntimeSkills({ onImported }: { onImported: (entry: KnowledgeEntry) => Promise<void> }) {
  const [skills, setSkills] = useState<BundledSkill[]>([]);
  const [skillId, setSkillId] = useState("");
  const [scopes, setScopes] = useState<KnowledgeScopeOption[]>([]);
  const [destination, setDestination] = useState("user:");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const pending = useRef(false);
  useEffect(() => { let cancelled = false; void Promise.all([request<BundledSkill[]>("/v1/knowledge/skills/bundled"), knowledgeApi.scopes()]).then(([next, options]) => { if (!cancelled) { setSkills(next); setScopes(options); } }).catch(failure => { if (!cancelled) setError(errorMessage(failure)); }); return () => { cancelled = true; }; }, []);
  const skill = skills.find(item => item.id === skillId);
  function install() {
    const scope = scopes.find(item => `${item.scope}:${item.scope_id ?? ""}` === destination);
    if (pending.current || !skill || !scope) return;
    pending.current = true; setBusy(true); setError("");
    void request<KnowledgeEntry>(`/v1/knowledge/skills/bundled/${encodeURIComponent(skill.id)}/install`, { method: "POST", body: JSON.stringify({ scope: scope.scope, scope_id: scope.scope_id }) })
      .then(onImported).catch(failure => setError(errorMessage(failure))).finally(() => { pending.current = false; setBusy(false); });
  }
  return <details className="card"><summary>Bundled runtime skills · {skills.length || "Loading"}</summary><div className="workspace-editor">
    <p className="hint">Add a conditional workflow to Knowledge, then select it in an agent or chat. Installation grants no tools, access or automatic memory saving.</p>
    <label>Workflow<select value={skillId} disabled={busy} onChange={event => setSkillId(event.target.value)}><option value="">Choose a skill</option>{skills.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
    {skill ? <><p>{skill.description}</p><p className="hint">{[skill.requires_project ? "Project required" : "", skill.required_tools.length ? `Required selected tools: ${skill.required_tools.join(", ")}` : "Use applicable selected sources"].filter(Boolean).join(" · ")}</p><details><summary>Review instructions and supporting files</summary><pre className="wrapped-text">{skill.content}</pre><ul>{skill.resources.map(resource => <li key={resource.path}>{resource.path} · {resource.size_bytes} bytes</li>)}</ul><p className="hint">Inert references under virtual /skills/ paths. These paths cannot be passed directly to a host command.</p></details></> : null}
    <label>Use in<select disabled={busy} value={destination} onChange={event => setDestination(event.target.value)}>{scopes.filter(item => item.active).map(item => <option key={`${item.scope}:${item.scope_id ?? ""}`} value={`${item.scope}:${item.scope_id ?? ""}`}>{item.label}</option>)}</select></label>
    <button type="button" onClick={install} disabled={busy || !skill}>{busy ? "Adding…" : "Add to Knowledge"}</button>{error ? <Notice tone="error">{error}</Notice> : null}
  </div></details>;
}

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
  return <details><summary>Supporting files · {resources.length}</summary>{resources.length ? <div className="setup-selection-options">{resources.map(item => <button key={item.path} type="button" onClick={() => setSelection({ versionId, path: item.path })} aria-pressed={path === item.path}>{item.path} <span className="hint">{Math.ceil(item.size_bytes / 1024)} KB</span></button>)}</div> : <p className="hint">This version has no supporting files.</p>}{current?.loading ? <p role="status">Loading file…</p> : null}{current?.error ? <Notice tone="error">{current.error}</Notice> : null}{current?.resource ? <section><h4>{current.resource.path}</h4>{current.resource.binary ? <p className="hint">Binary file retained with the skill; text preview is unavailable.</p> : <pre className="wrapped-text">{current.resource.content}</pre>}<p className="hint">{current.resource.execution_supported ? "Python skill scripts can run in a project Work chat with Run skill scripts and Run commands selected, subject to approval. Knowledge only previews this frozen resource; it never executes it." : "Read-only supporting content. Importing and reading a package never executes it."}</p></section> : null}</details>;
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
