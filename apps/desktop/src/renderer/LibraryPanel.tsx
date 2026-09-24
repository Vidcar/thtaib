import { useEffect, useMemo, useRef, useState } from "react";
import { formatBytes } from "./display";
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
  type RetainedAssetReuseResult,
} from "./packet03Api";
import "./packet03Panels.css";
import "./fileBrowser.css";
import { RetainedImage } from "./ImagePreview";
import { workspaceApi } from "./workspaceApi";

interface LibraryPanelProps {
  sessionId?: string | null;
  projectPath?: string | null;
  onReuseSelectedAssets?: (assets: RetainedAsset[]) => void;
  onReuseAssets?: (result: RetainedAssetReuseResult, assets: RetainedAsset[]) => void;
}

function assetOriginLabel(origin: RetainedAssetOrigin): string {
  return origin === "verified_output" ? "Verified output" : "Upload";
}

function assetAccessScope(
  asset: RetainedAsset,
  current: { sessionId?: string | null; projectPath?: string | null },
): { sessionId?: string; projectPath?: string } {
  if (asset.session_id) {
    return { sessionId: asset.session_id };
  }
  if (asset.project_path) {
    return { projectPath: asset.project_path };
  }
  return {
    sessionId: current.sessionId ?? undefined,
    projectPath: current.projectPath ?? undefined,
  };
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

export function LibraryPanel({ sessionId = null, projectPath = null, onReuseSelectedAssets, onReuseAssets }: LibraryPanelProps) {
  const [origin, setOrigin] = useState<RetainedAssetOrigin | "all">("all");
  const [scope, setScope] = useState<"available" | "session" | "project" | "all">("available");
  const [includeDeleted, setIncludeDeleted] = useState(false);
  const [assets, setAssets] = useState<RetainedAsset[]>([]);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [preview, setPreview] = useState<RetainedAssetPreview | null>(null);
  const [fullContent, setFullContent] = useState<RetainedAssetContent | null>(null);
  const [deletionPreview, setDeletionPreview] = useState<RetainedAssetDeletionPreview | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState("recent");
  const [projectLabels, setProjectLabels] = useState<Record<string, string>>({});
  const loadGeneration = useRef(0);
  const detailGeneration = useRef(0);
  const actionGeneration = useRef(0);
  useEffect(() => {
    let cancelled = false;
    void workspaceApi.projects(true).then(projects => {
      if (!cancelled) setProjectLabels(Object.fromEntries(projects.map(project => [project.path.replaceAll("\\", "/").toLowerCase(), project.name])));
    }).catch(() => { /* Folder names remain available when project labels cannot load. */ });
    return () => { cancelled = true; };
  }, []);

  const selectedAssets = useMemo(
    () => assets.filter((asset) => selectedIds.includes(asset.id)),
    [assets, selectedIds],
  );
  const visibleAssets = useMemo(() => assets.filter(asset => `${asset.filename} ${asset.project_path ?? ""}`.toLowerCase().includes(query.trim().toLowerCase())).sort((a, b) =>
    sort === "name" ? a.filename.localeCompare(b.filename) : sort === "size" ? b.size_bytes - a.size_bytes : b.observed_at.localeCompare(a.observed_at)), [assets, query, sort]);
  const activeAsset = assets.find(asset => asset.id === preview?.id);
  const selectable = visibleAssets.filter(asset => !asset.deleted_at);

  async function loadAssets(options: { clearMessage?: boolean } = {}): Promise<void> {
    const { clearMessage = true } = options;
    const requestGeneration = loadGeneration.current + 1;
    loadGeneration.current = requestGeneration;
    setBusy(true);
    if (clearMessage) setMessage("");
    try {
      const filters: Parameters<typeof packet03Api.assets>[0] = {
        includeDeleted,
        origin: origin === "all" ? undefined : origin,
      };
      if (scope === "session" && sessionId) filters.sessionId = sessionId;
      if (scope === "project" && projectPath) filters.projectPath = projectPath;
      if (scope === "available") {
        if (sessionId) filters.sessionId = sessionId;
        if (projectPath) filters.projectPath = projectPath;
      }
      const next = await packet03Api.assets(filters);
      if (loadGeneration.current !== requestGeneration) return;
      setAssets(next);
      setSelectedIds((current) => current.filter((id) => next.some((asset) => asset.id === id)));
    } catch (error) {
      if (loadGeneration.current !== requestGeneration) return;
      setMessage(error instanceof Error ? error.message : String(error));
    } finally {
      if (loadGeneration.current === requestGeneration) setBusy(false);
    }
  }

  useEffect(() => {
    detailGeneration.current += 1;
    setPreview(null);
    setFullContent(null);
    setSelectedIds([]);
    setDeletionPreview(null);
    void loadAssets();
    return () => { loadGeneration.current += 1; detailGeneration.current += 1; actionGeneration.current += 1; };
  }, [origin, scope, includeDeleted, sessionId, projectPath]);

  async function showPreview(asset: RetainedAsset): Promise<void> {
    const requestGeneration = detailGeneration.current + 1;
    detailGeneration.current = requestGeneration;
    setBusy(true);
    setMessage("");
    setFullContent(null);
    try {
      const next = await loadRetainedPreview(asset.id, assetAccessScope(asset, { sessionId, projectPath }));
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
      const next = await loadRetainedContent(asset.id, assetAccessScope(asset, { sessionId, projectPath }));
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

  async function reuseSelected(): Promise<void> {
    if (selectedIds.length === 0) return;
    if (onReuseSelectedAssets && (!sessionId || !onReuseAssets)) {
      if (selectedAssets.length === 0) return;
      onReuseSelectedAssets(selectedAssets);
      setMessage(`Opening Chat to reuse ${selectedAssets.length} retained file${selectedAssets.length === 1 ? "" : "s"}.`);
      return;
    }
    if (!sessionId || !onReuseAssets) return;
    const requestGeneration = ++actionGeneration.current;
    setBusy(true);
    setMessage("");
    try {
      const result = await packet03Api.reuseAssets({
        asset_ids: selectedIds,
        session_id: sessionId,
        project_path: projectPath,
        allow_cross_session_reuse: scope === "all",
      });
      if (actionGeneration.current !== requestGeneration) return;
      onReuseAssets(result, selectedAssets);
      setMessage("Ready to reuse in a draft.");
    } catch (error) {
      if (actionGeneration.current !== requestGeneration) return;
      setMessage(error instanceof Error ? error.message : String(error));
    } finally {
      if (actionGeneration.current === requestGeneration) setBusy(false);
    }
  }

  async function previewDeletion(): Promise<void> {
    if (selectedIds.length === 0) return;
    const requestGeneration = ++actionGeneration.current;
    setBusy(true);
    setMessage("");
    try {
      const result = await packet03Api.deleteAssetPreview(selectedIds);
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
      setDeletionPreview(result);
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
        <div className="entity-head"><h2>Library</h2><span className="file-count">{assets.length} files</span><HoverHelp title="About saved files">Files uploaded to chats and saved outputs. These are retained copies; project originals stay in their folders.</HoverHelp></div>
        <button type="button" className="icon-button" aria-label="Refresh files" disabled={busy} onClick={() => void loadAssets()}><Icon name="refresh" size={16} /></button>
      </header>

      <div className="file-browser-toolbar" aria-label="Library filters">
        <label className="file-search"><Icon name="search" size={16} /><input aria-label="Search files" placeholder="Search files…" value={query} onChange={event => setQuery(event.target.value)} /></label>
        <select aria-label="File location" value={scope} onChange={event => setScope(event.target.value as typeof scope)}>
          <option value="available">{sessionId || projectPath ? "Available here" : "All files"}</option>
          {sessionId ? <option value="session">This conversation</option> : null}
          {projectPath ? <option value="project">This project</option> : null}
          {sessionId || projectPath ? <option value="all">All files</option> : null}
        </select>
        <select aria-label="File type" value={origin} onChange={event => setOrigin(event.target.value as RetainedAssetOrigin | "all")}>
          <option value="all">All types</option><option value="upload">Uploads</option><option value="verified_output">Outputs</option>
        </select>
        <select aria-label="Sort files" value={sort} onChange={event => setSort(event.target.value)}><option value="recent">Newest first</option><option value="name">Name</option><option value="size">Largest first</option></select>
        <button type="button" className="chip file-deleted-toggle" aria-pressed={includeDeleted} onClick={() => setIncludeDeleted(current => !current)}>Deleted</button>
      </div>

      <div className="file-selection-bar" aria-label="File actions">
        <span>{selectedIds.length ? `${selectedIds.length} selected` : "Select files to use in Chat or delete"}</span>
        <button type="button" disabled={busy || !selectedIds.length || (!onReuseSelectedAssets && (!sessionId || !onReuseAssets))} onClick={() => void reuseSelected()}><Icon name="plus" size={14} /> Use in Chat</button>
        <button type="button" disabled={busy || !selectedIds.length} onClick={() => void previewDeletion()}><Icon name="trash" size={14} /> Delete</button>
      </div>
      {message ? <Notice role="status">{message}</Notice> : null}
      {deletionPreview ? <div className="notice notice-warn file-delete-review" role="group" aria-label="Review file deletion">
        <strong>Delete {deletionPreview.affected_asset_ids.length} saved {deletionPreview.affected_asset_ids.length === 1 ? "file" : "files"}?</strong>
        <p>Original project files stay in place.{deletionPreview.preserved_asset_ids.length ? ` ${deletionPreview.preserved_asset_ids.length} shared files will be kept.` : ""}</p>
        <div className="actions"><button type="button" disabled={busy || !deletionPreview.affected_asset_ids.length} onClick={() => void confirmDelete()}>Delete saved files</button><button type="button" onClick={() => setDeletionPreview(null)}>Cancel</button><HoverHelp title="Deletion details">{deletionPreview.note}</HoverHelp></div>
      </div> : null}

      <div className={`file-browser-body${preview ? " has-preview" : ""}`}>
        <div className="file-table-wrap">
          <table className="file-table" aria-label="Saved files">
            <thead><tr><th className="file-check"><input type="checkbox" aria-label="Select all visible files" disabled={!selectable.length} checked={selectable.length > 0 && selectable.every(asset => selectedIds.includes(asset.id))} onChange={event => { setDeletionPreview(null); setSelectedIds(event.target.checked ? selectable.map(asset => asset.id) : []); }} /></th><th>Name</th><th className="file-location">Location</th><th>Size</th><th className="file-date">Added</th></tr></thead>
            <tbody>{visibleAssets.map(asset => <tr key={asset.id} className={`${preview?.id === asset.id ? "is-active " : ""}${asset.deleted_at ? "is-deleted" : ""}`}>
              <td className="file-check"><input type="checkbox" aria-label={`Select ${asset.filename}`} disabled={Boolean(asset.deleted_at)} checked={selectedIds.includes(asset.id)} onChange={event => { setDeletionPreview(null); setSelectedIds(current => event.target.checked ? [...current, asset.id] : current.filter(id => id !== asset.id)); }} /></td>
              <td><button type="button" className="file-name" disabled={Boolean(asset.deleted_at)} aria-label={`Preview ${asset.filename}`} onClick={() => void showPreview(asset)}><Icon name="files" size={17} /><span><strong>{asset.filename}</strong><small>{asset.deleted_at ? "Deleted" : assetOriginLabel(asset.origin)}</small></span></button></td>
              <td className="file-location"><span title={asset.project_path ?? undefined}>{asset.project_path ? projectLabels[asset.project_path.replaceAll("\\", "/").toLowerCase()] ?? asset.project_path.replaceAll("\\", "/").split("/").filter(Boolean).at(-1) : "Conversation"}</span></td>
              <td className="file-size">{formatBytes(asset.size_bytes)}</td>
              <td className="file-date">{new Date(asset.observed_at).toLocaleDateString()}</td>
            </tr>)}</tbody>
          </table>
          {!visibleAssets.length ? <div className="file-browser-empty"><Icon name="files" size={28} /><strong>{busy ? "Loading files…" : query ? "No matching files" : "No saved files yet"}</strong><span>{query ? "Try another name or location." : "Files you attach and outputs you save in Chat appear here."}</span></div> : null}
        </div>

        {preview ? <aside className="file-preview-pane" aria-label="Library detail">
          <header><div><strong>{preview.filename}</strong><span>{formatBytes(preview.size_bytes)} · {sourceStatusLabel(preview.source_status)}</span></div><button type="button" className="icon-button" aria-label="Close file preview" onClick={() => { detailGeneration.current += 1; setPreview(null); setFullContent(null); }}><Icon name="close" size={15} /></button></header>
          <div className="file-preview-actions">
            {activeAsset && activeAsset.content_kind !== "image" && fullContent?.id !== preview.id ? <button type="button" disabled={busy} onClick={() => void showFullContent(activeAsset)}><Icon name="expand" size={14} /> Open full text</button> : null}
            {activeAsset && window.workbench?.saveAsset ? <button type="button" disabled={busy} onClick={() => void saveRetainedCopy(activeAsset.id, assetAccessScope(activeAsset, { sessionId, projectPath })).then(saved => setMessage(saved ? `Saved ${activeAsset.filename}.` : "Save cancelled.")).catch(error => setMessage(error instanceof Error ? error.message : String(error)))}><Icon name="download" size={14} /> Save copy</button> : null}
          </div>
          {preview.truncated ? <p className="hint">Preview shortened. Open full text to read the entire saved file.</p> : null}
          {activeAsset?.content_kind === "image" ? <RetainedImage asset={activeAsset} sessionId={sessionId ?? undefined} /> : <pre className="file-preview-content">{preview.preview}</pre>}
          {preview.extraction ? <p className="hint">{preview.extraction.status === "no_text" ? "No text found" : "Text extracted locally"} <HoverHelp title="Extraction details">{preview.extraction.note ?? preview.extraction.parser}</HoverHelp></p> : null}
        </aside> : null}
      </div>
    </section>
  );
}
