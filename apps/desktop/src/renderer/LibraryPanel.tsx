import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "./api";
import { conversationTitle, formatBytes } from "./display";
import { HoverHelp } from "./HoverHelp";
import { Icon } from "./Icon";
import { Notice } from "./Notice";
import { loadRetainedContent, loadRetainedPreview, saveRetainedCopy, sourceStatusLabel } from "./retainedFiles";

import {
  packet03Api,
  type RetainedAsset,
  type RetainedAssetContent,
  type RetainedAssetDeletionPreview,
  type RetainedAssetOrigin,
  type RetainedAssetPreview,
} from "./packet03Api";
import "./packet03Panels.css";
import "./fileBrowser.css";
import { RetainedImage } from "./ImagePreview";
import type { ChatConversation } from "./types";
import { workspaceApi, type ProjectRecord } from "./workspaceApi";

type SourceLoadState = "loading" | "ready" | "error";
type LibraryScope = "all" | "project" | "chat";
const normalizedPath = (path: string) => path.replaceAll("\\", "/").replace(/\/+$/, "").toLowerCase();
const folderName = (path: string) => path.replaceAll("\\", "/").split("/").filter(Boolean).at(-1) || path;

function assetOriginLabel(origin: RetainedAssetOrigin): string {
  if ((origin as string) === "browser_download") return "Browser download";
  if ((origin as string) === "capture") return "Screenshot";
  return origin === "verified_output" ? "Verified output" : "Upload";
}

function assetAccessScope(asset: RetainedAsset): { sessionId?: string; projectPath?: string } {
  if (asset.session_id) {
    return { sessionId: asset.session_id };
  }
  if (asset.project_path) {
    return { projectPath: asset.project_path };
  }
  return {};
}

function deleteOutcomeText(result: RetainedAssetDeletionPreview): string {
  const deleted = result.affected_asset_ids.length;
  const preserved = result.preserved_asset_ids.length;
  const deletedText = `${deleted} retained item${deleted === 1 ? "" : "s"} marked deleted`;
  if (preserved === 0) {
    return `${deletedText}.`;
  }
  return `${deletedText}; ${preserved} shared item${preserved === 1 ? "" : "s"} preserved.`;
}

export function LibraryPanel() {
  const [origin, setOrigin] = useState<RetainedAssetOrigin | "all">("all");
  const [scope, setScope] = useState<LibraryScope>("all");
  const [scopeTarget, setScopeTarget] = useState("");
  const [includeDeleted, setIncludeDeleted] = useState(false);
  const [assets, setAssets] = useState<RetainedAsset[]>([]);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [preview, setPreview] = useState<RetainedAssetPreview | null>(null);
  const [fullContent, setFullContent] = useState<RetainedAssetContent | null>(null);
  const [deletionPreview, setDeletionPreview] = useState<RetainedAssetDeletionPreview | null>(null);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState("");
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState("recent");
  const [projects, setProjects] = useState<ProjectRecord[]>([]);
  const [chats, setChats] = useState<ChatConversation[]>([]);
  const [projectState, setProjectState] = useState<SourceLoadState>("loading");
  const [chatState, setChatState] = useState<SourceLoadState>("loading");
  const [sourceAssets, setSourceAssets] = useState<RetainedAsset[]>([]);
  const loadGeneration = useRef(0);
  const detailGeneration = useRef(0);
  const actionGeneration = useRef(0);
  const catalogueGeneration = useRef(0);

  async function loadSourceNames(): Promise<void> {
    const generation = ++catalogueGeneration.current;
    setProjectState("loading");
    setChatState("loading");
    const projectFlight = workspaceApi.projects(true).then(next => {
      if (catalogueGeneration.current !== generation) return;
      setProjects(next); setProjectState("ready");
    }).catch(() => { if (catalogueGeneration.current === generation) setProjectState("error"); });
    const chatFlight = api.chatConversations(true).then(next => {
      if (catalogueGeneration.current !== generation) return;
      setChats(next); setChatState("ready");
    }).catch(() => { if (catalogueGeneration.current === generation) setChatState("error"); });
    await Promise.allSettled([projectFlight, chatFlight]);
  }

  useEffect(() => {
    void loadSourceNames();
    return () => { catalogueGeneration.current += 1; };
  }, []);

  const projectsByPath = useMemo(() => new Map(projects.flatMap(project => [
    [normalizedPath(project.path), project] as const,
    [normalizedPath(project.canonical_path || project.path), project] as const,
  ])), [projects]);
  const chatsById = useMemo(() => new Map(chats.map(chat => [chat.id, chat])), [chats]);
  function projectName(path: string): string {
    const project = projectsByPath.get(normalizedPath(path));
    if (project) return `${project.name}${project.active === false || project.missing ? " · Unavailable" : ""}`;
    return `${folderName(path)}${projectState === "ready" ? " · Project unavailable" : projectState === "error" ? " · Name unavailable" : ""}`;
  }
  function chatName(id: string): string {
    const chat = chatsById.get(id);
    if (chat) return `${conversationTitle(chat)}${chat.archived ? " · Archived" : ""}`;
    return chatState === "ready" ? "Chat unavailable" : chatState === "error" ? "Chat name unavailable" : "Chat";
  }
  function sourceName(asset: RetainedAsset): string {
    return [asset.session_id ? chatName(asset.session_id) : "", asset.project_path ? projectName(asset.project_path) : ""].filter(Boolean).join(" · ") || "Saved file";
  }
  const projectOptions = useMemo(() => {
    const options = new Map(projects.map(project => [project.id, { value: project.path, label: projectName(project.path) }]));
    const retainedPaths = new Set<string>();
    for (const asset of [...sourceAssets, ...assets]) if (asset.project_path) {
      const project = projectsByPath.get(normalizedPath(asset.project_path));
      const key = project?.id ?? normalizedPath(asset.project_path);
      if (retainedPaths.has(key)) continue;
      retainedPaths.add(key);
      options.set(key, { value: asset.project_path, label: projectName(asset.project_path) });
    }
    return [...options.values()].sort((a, b) => a.label.localeCompare(b.label));
  }, [projectsByPath, projects, sourceAssets, assets, projectState]);
  const chatOptions = useMemo(() => {
    const options = new Map(chats.map(chat => [chat.id, { value: chat.id, label: chatName(chat.id) }]));
    for (const asset of [...sourceAssets, ...assets]) if (asset.session_id && !options.has(asset.session_id)) {
      options.set(asset.session_id, { value: asset.session_id, label: `${chatName(asset.session_id)} · ${asset.filename}` });
    }
    return [...options.values()].sort((a, b) => a.label.localeCompare(b.label));
  }, [chatsById, chats, sourceAssets, assets, chatState]);
  const selectedAssets = useMemo(() => assets.filter(asset => selectedIds.includes(asset.id) && !asset.deleted_at), [assets, selectedIds]);
  const visibleAssets = assets.filter(asset => `${asset.filename} ${asset.project_path ?? ""} ${sourceName(asset)}`.toLowerCase().includes(query.trim().toLowerCase())).sort((a, b) =>
    sort === "name" ? a.filename.localeCompare(b.filename) : sort === "size" ? b.size_bytes - a.size_bytes : b.observed_at.localeCompare(a.observed_at));
  const activeAsset = assets.find(asset => asset.id === preview?.id);
  const selectable = visibleAssets.filter(asset => !asset.deleted_at);

  async function loadAssets(options: { clearMessage?: boolean } = {}): Promise<void> {
    const { clearMessage = true } = options;
    const requestGeneration = loadGeneration.current + 1;
    loadGeneration.current = requestGeneration;
    if (clearMessage) setMessage("");
    if (scope !== "all" && !scopeTarget) {
      setAssets([]); setBusy(false); setLoading(false);
      return;
    }
    setBusy(true); setLoading(true);
    try {
      const filters: Parameters<typeof packet03Api.assets>[0] = {
        includeDeleted,
        origin: origin === "all" ? undefined : origin,
      };
      if (scope === "chat") filters.sessionId = scopeTarget;
      if (scope === "project") filters.projectPath = scopeTarget;
      const next = await packet03Api.assets(filters);
      if (loadGeneration.current !== requestGeneration) return;
      setAssets(next);
      if (scope === "all") setSourceAssets(next);
      setSelectedIds(current => current.filter(id => next.some(asset => asset.id === id && !asset.deleted_at)));
    } catch (error) {
      if (loadGeneration.current !== requestGeneration) return;
      setMessage(error instanceof Error ? error.message : String(error));
    } finally {
      if (loadGeneration.current === requestGeneration) { setBusy(false); setLoading(false); }
    }
  }

  useEffect(() => {
    detailGeneration.current += 1;
    setPreview(null);
    setFullContent(null);
    setAssets([]);
    setSelectedIds([]);
    setDeletionPreview(null);
    void loadAssets();
    return () => { loadGeneration.current += 1; detailGeneration.current += 1; actionGeneration.current += 1; };
  }, [origin, scope, scopeTarget, includeDeleted]);

  async function showPreview(asset: RetainedAsset): Promise<void> {
    const requestGeneration = detailGeneration.current + 1;
    detailGeneration.current = requestGeneration;
    setBusy(true);
    setMessage("");
    setFullContent(null);
    try {
      const next = await loadRetainedPreview(asset.id, assetAccessScope(asset));
      if (detailGeneration.current !== requestGeneration) return;
      setPreview(next);
    } catch (error) {
      if (detailGeneration.current !== requestGeneration) return;
      setMessage(error instanceof Error ? error.message : String(error));
    } finally {
      if (detailGeneration.current === requestGeneration) setBusy(false);
    }
  }

  async function showFullContent(asset: RetainedAsset): Promise<void> {
    const requestGeneration = detailGeneration.current + 1;
    detailGeneration.current = requestGeneration;
    setBusy(true);
    setMessage("");
    try {
      const next = await loadRetainedContent(asset.id, assetAccessScope(asset));
      if (detailGeneration.current !== requestGeneration) return;
      setFullContent(next);
      setPreview({
        id: next.id,
        filename: next.filename,
        content_type: next.content_type,
        size_bytes: next.size_bytes,
        sha256: next.sha256,
        preview: next.text,
        truncated: false,
        source_status: next.source_status,
      });
    } catch (error) {
      if (detailGeneration.current !== requestGeneration) return;
      setMessage(error instanceof Error ? error.message : String(error));
    } finally {
      if (detailGeneration.current === requestGeneration) setBusy(false);
    }
  }

  async function saveCopy(asset: RetainedAsset): Promise<void> {
    const requestGeneration = ++actionGeneration.current;
    setBusy(true);
    setMessage("");
    try {
      const saved = await saveRetainedCopy(asset.id, assetAccessScope(asset));
      if (actionGeneration.current !== requestGeneration) return;
      setMessage(saved ? `Saved ${asset.filename}.` : "Save cancelled.");
    } catch (error) {
      if (actionGeneration.current !== requestGeneration) return;
      setMessage(error instanceof Error ? error.message : String(error));
    } finally {
      if (actionGeneration.current === requestGeneration) setBusy(false);
    }
  }

  async function previewDeletion(): Promise<void> {
    if (selectedAssets.length === 0) return;
    const requestGeneration = ++actionGeneration.current;
    setBusy(true);
    setMessage("");
    try {
      const result = await packet03Api.deleteAssetPreview(selectedAssets.map(asset => asset.id));
      if (actionGeneration.current !== requestGeneration) return;
      setDeletionPreview(result);
    } catch (error) {
      if (actionGeneration.current !== requestGeneration) return;
      setMessage(error instanceof Error ? error.message : String(error));
    } finally {
      if (actionGeneration.current === requestGeneration) setBusy(false);
    }
  }

  async function confirmDelete(): Promise<void> {
    if (!deletionPreview?.affected_asset_ids.length) return;
    const requestGeneration = ++actionGeneration.current;
    setBusy(true);
    setMessage("");
    try {
      const result = await packet03Api.deleteAssets(deletionPreview.affected_asset_ids);
      if (actionGeneration.current !== requestGeneration) return;
      detailGeneration.current += 1;
      setPreview(current => current && result.affected_asset_ids.includes(current.id) ? null : current);
      setFullContent(current => current && result.affected_asset_ids.includes(current.id) ? null : current);
      setDeletionPreview(null);
      setSelectedIds([]);
      setMessage(deleteOutcomeText(result));
      await loadAssets({ clearMessage: false });
    } catch (error) {
      if (actionGeneration.current !== requestGeneration) return;
      setMessage(error instanceof Error ? error.message : String(error));
    } finally {
      if (actionGeneration.current === requestGeneration) setBusy(false);
    }
  }

  return (
    <section className="surface file-browser" aria-label="Library">
      <header className="surface-head">
        <div className="entity-head"><h2>Library</h2><span className="file-count">{assets.length} {assets.length === 1 ? "file" : "files"}</span><HoverHelp title="About saved files">Files uploaded to chats and saved outputs. These are retained copies; project originals stay in their folders.</HoverHelp></div>
        <button type="button" className="icon-button" aria-label="Refresh files" title="Refresh files" disabled={busy} onClick={() => { void loadAssets(); void loadSourceNames(); }}><Icon name="refresh" size={16} /></button>
      </header>

      <div className="file-browser-toolbar" aria-label="Library filters">
        <label className="file-search"><Icon name="search" size={16} /><input aria-label="Search files" placeholder="Search files…" value={query} onChange={event => setQuery(event.target.value)} /></label>
        <select aria-label="File location" value={scope} onChange={event => { setScope(event.target.value as LibraryScope); setScopeTarget(""); }}>
          <option value="all">All files</option><option value="project">Project</option><option value="chat">Chat</option>
        </select>
        {scope === "project" ? <select aria-label="Project" value={scopeTarget} onChange={event => setScopeTarget(event.target.value)}><option value="">Choose a project</option>{projectOptions.map(project => <option key={project.value} value={project.value}>{project.label}</option>)}</select> : scope === "chat" ? <select aria-label="Chat" value={scopeTarget} onChange={event => setScopeTarget(event.target.value)}><option value="">Choose a chat</option>{chatOptions.map(chat => <option key={chat.value} value={chat.value}>{chat.label}</option>)}</select> : null}
        <select aria-label="File type" value={origin} onChange={event => setOrigin(event.target.value as RetainedAssetOrigin | "all")}>
          <option value="all">All types</option><option value="upload">Uploads</option><option value="verified_output">Outputs</option><option value="browser_download">Browser downloads</option><option value="capture">Screenshots</option>
        </select>
        <select aria-label="Sort files" value={sort} onChange={event => setSort(event.target.value)}><option value="recent">Newest first</option><option value="name">Name</option><option value="size">Largest first</option></select>
        <button type="button" className="chip file-deleted-toggle" aria-pressed={includeDeleted} onClick={() => setIncludeDeleted(current => !current)}>Deleted</button>
      </div>

      {projectState === "error" || chatState === "error" ? <Notice tone="warn">Some {projectState === "error" && chatState === "error" ? "project and chat" : projectState === "error" ? "project" : "chat"} names could not load. Saved files remain available; refresh to try again.</Notice> : null}
      {selectedAssets.length ? <div className="file-selection-bar" aria-label="File actions">
        <span>{selectedAssets.length} selected</span>
        <button type="button" disabled={busy} onClick={() => { setSelectedIds([]); setDeletionPreview(null); }}>Clear selection</button>
        <button type="button" disabled={busy} onClick={() => void previewDeletion()}><Icon name="trash" size={14} /> Delete</button>
      </div> : null}
      {message ? <Notice role="status">{message}</Notice> : null}
      {deletionPreview ? <div className="notice notice-warn file-delete-review" role="group" aria-label="Review file deletion">
        <strong>Delete {deletionPreview.affected_asset_ids.length} saved {deletionPreview.affected_asset_ids.length === 1 ? "file" : "files"}?</strong>
        <p>Original project files stay in place.{deletionPreview.preserved_asset_ids.length ? ` ${deletionPreview.preserved_asset_ids.length} shared files will be kept.` : ""}</p>
        <div className="actions"><button type="button" disabled={busy || !deletionPreview.affected_asset_ids.length} onClick={() => void confirmDelete()}>Delete saved files</button><button type="button" onClick={() => setDeletionPreview(null)}>Cancel</button><HoverHelp title="Deletion details">{deletionPreview.note}</HoverHelp></div>
      </div> : null}

      <div className={`file-browser-body${preview ? " has-preview" : ""}${activeAsset?.content_kind === "image" ? " has-image-preview" : ""}`}>
        <div className="file-table-wrap">
          <table className="file-table" aria-label="Saved files">
            <thead><tr><th className="file-check"><input type="checkbox" aria-label="Select all visible files" disabled={busy || !selectable.length} checked={selectable.length > 0 && selectable.every(asset => selectedIds.includes(asset.id))} onChange={event => { setDeletionPreview(null); setSelectedIds(event.target.checked ? selectable.map(asset => asset.id) : []); }} /></th><th>Name</th><th className="file-location">Source</th><th>Size</th><th className="file-date">Added</th></tr></thead>
            <tbody>{visibleAssets.map(asset => <tr key={asset.id} className={`${preview?.id === asset.id ? "is-active " : ""}${asset.deleted_at ? "is-deleted" : ""}`}>
              <td className="file-check"><input type="checkbox" aria-label={`Select ${asset.filename}`} disabled={busy || Boolean(asset.deleted_at)} checked={selectedIds.includes(asset.id)} onChange={event => { setDeletionPreview(null); setSelectedIds(current => event.target.checked ? [...new Set([...current, asset.id])] : current.filter(id => id !== asset.id)); }} /></td>
              <td><button type="button" className="file-name" disabled={Boolean(asset.deleted_at)} aria-label={`Preview ${asset.filename}`} onClick={() => void showPreview(asset)}><Icon name={asset.content_kind === "image" ? "image" : "file"} size={17} /><span><strong>{asset.filename}</strong><small>{asset.deleted_at ? "Deleted" : assetOriginLabel(asset.origin)}</small><small className="file-inline-source">{sourceName(asset)}</small></span></button></td>
              <td className="file-location"><span title={sourceName(asset)}>{asset.session_id ? chatName(asset.session_id) : "Saved file"}</span>{asset.project_path ? <small title={asset.project_path}>{projectName(asset.project_path)}</small> : null}</td>
              <td className="file-size">{formatBytes(asset.size_bytes)}</td>
              <td className="file-date">{new Date(asset.observed_at).toLocaleDateString()}</td>
            </tr>)}</tbody>
          </table>
          {!visibleAssets.length ? <div className="file-browser-empty"><Icon name="files" size={28} /><strong>{loading ? "Loading files…" : scope !== "all" && !scopeTarget ? `Choose a ${scope}` : query ? "No matching files" : "No saved files yet"}</strong></div> : null}
        </div>

        {preview ? <aside className="file-preview-pane" aria-label="Library detail">
          <header><div><strong>{preview.filename}</strong><span>{formatBytes(preview.size_bytes)} · {sourceStatusLabel(preview.source_status)}</span>{activeAsset ? <span>{sourceName(activeAsset)}</span> : null}</div><button type="button" className="icon-button" aria-label="Close file preview" title="Close file preview" onClick={() => { detailGeneration.current += 1; setPreview(null); setFullContent(null); setBusy(false); }}><Icon name="close" size={15} /></button></header>
          <div className="file-preview-actions">
            {activeAsset && activeAsset.content_kind !== "image" && (activeAsset.content_kind as string) !== "binary" && fullContent?.id !== preview.id ? <button type="button" disabled={busy} onClick={() => void showFullContent(activeAsset)}><Icon name="expand" size={14} /> Open full text</button> : null}
            {activeAsset && window.workbench?.saveAsset ? <button type="button" disabled={busy} onClick={() => void saveCopy(activeAsset)}><Icon name="download" size={14} /> Save copy</button> : null}
          </div>
          {preview.truncated ? <p className="hint">Preview shortened. Open full text to read the entire saved file.</p> : null}
          {(activeAsset?.content_kind as string) === "binary" ? <p className="hint">Saved browser download. Save a copy to open this file in its application.</p> : activeAsset?.content_kind === "image" ? <RetainedImage key={activeAsset.id} asset={activeAsset} /> : <pre className="file-preview-content">{preview.preview}</pre>}
          {preview.extraction ? <p className="hint">{preview.extraction.status === "no_text" ? "No text found" : "Text extracted locally"} <HoverHelp title="Extraction details">{preview.extraction.note ?? preview.extraction.parser}</HoverHelp></p> : null}
        </aside> : null}
      </div>
    </section>
  );
}
