import { useEffect, useRef, useState } from "react";
import { request } from "./api";
import { errorMessage } from "./errors";
import { Notice } from "./Notice";
import { knowledgeApi, type KnowledgeScopeOption } from "./knowledgeApi";
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
  async function browse(kind: "file" | "folder") { try { const next = await window.workbench?.selectPath?.(kind); if (next) setSource(next); } catch (failure) { setError(errorMessage(failure)); } }
  return <form className="workspace-editor" onSubmit={event => { event.preventDefault(); if (pending.current || !source.trim()) return; const scope = scopes.find(option => `${option.scope}:${option.scope_id ?? ""}` === destination); if (!entry && !scope) return; pending.current = true; setBusy(true); setError(""); void request<KnowledgeEntry>("/v1/knowledge/skills/import", { method: "POST", body: JSON.stringify({ source_path: source.trim(), scope: entry?.scope ?? scope?.scope, scope_id: entry?.scope_id ?? scope?.scope_id, ...(entry ? { entry_id: entry.id, base_version: entry.current_version_id } : {}) }) }).then(onImported).then(() => setSource("")).catch(failure => setError(errorMessage(failure))).finally(() => { pending.current = false; setBusy(false); }); }}>
    <p className="hint">Import a skill folder, SKILL.md or ZIP. Supporting files stay with this version; importing does not execute them.</p>
    <label>Package path<input value={source} disabled={busy} onChange={event => setSource(event.target.value)} placeholder="Folder, Markdown file or ZIP" /></label><div className="actions"><button type="button" disabled={busy || !window.workbench?.selectPath} onClick={() => void browse("folder")}>Choose folder</button><button type="button" disabled={busy || !window.workbench?.selectPath} onClick={() => void browse("file")}>Choose file</button></div>
    {!entry ? <label>Use in<select disabled={busy} value={destination} onChange={event => setDestination(event.target.value)}>{scopes.filter(option => option.active).map(option => <option key={`${option.scope}:${option.scope_id ?? ""}`} value={`${option.scope}:${option.scope_id ?? ""}`}>{option.label}</option>)}</select></label> : null}
    <button type="submit" disabled={busy || !source.trim()}>{busy ? "Importing…" : entry ? "Import as new version" : "Import skill"}</button>{error ? <Notice tone="error">{error}</Notice> : null}
  </form>;
}

export function SkillResources({ versionId, resources = [] }: { versionId: string; resources?: SkillResource[] }) {
  const [path, setPath] = useState("");
  const [resource, setResource] = useState<ResourceView | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  useEffect(() => { setPath(""); setResource(null); setError(""); }, [versionId]);
  useEffect(() => { let cancelled = false; setResource(null); setError(""); if (!path) return; setLoading(true); void request<ResourceView>(`/v1/knowledge/versions/${versionId}/resource?path=${encodeURIComponent(path)}`).then(next => { if (!cancelled) setResource(next); }).catch(failure => { if (!cancelled) setError(errorMessage(failure)); }).finally(() => { if (!cancelled) setLoading(false); }); return () => { cancelled = true; }; }, [versionId, path]);
  return <details><summary>Supporting files · {resources.length}</summary>{resources.length ? <div className="setup-selection-options">{resources.map(item => <button key={item.path} type="button" onClick={() => setPath(item.path)} aria-pressed={path === item.path}>{item.path} <span className="hint">{Math.ceil(item.size_bytes / 1024)} KB</span></button>)}</div> : <p className="hint">This version has no supporting files.</p>}{loading ? <p role="status">Loading file…</p> : null}{error ? <Notice tone="error">{error}</Notice> : null}{resource ? <section><h4>{resource.path}</h4>{resource.binary ? <p className="hint">Binary file retained with the skill; text preview is unavailable.</p> : <pre className="wrapped-text">{resource.content}</pre>}<p className="hint">Read-only supporting content. Execution is unavailable.</p></section> : null}</details>;
}
