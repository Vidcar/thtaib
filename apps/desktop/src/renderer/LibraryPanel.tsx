import { useEffect, useMemo, useRef, useState } from "react";

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

interface LibraryPanelProps {
  sessionId?: string | null;
  projectPath?: string | null;
  onReuseSelectedAssets?: (assets: RetainedAsset[]) => void;
  onReuseAssets?: (result: RetainedAssetReuseResult, assets: RetainedAsset[]) => void;
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
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

function sourceStatusLabel(status: RetainedAssetPreview["source_status"]): string {
  switch (status) {
    case "retained_only":
      return "Retained copy";
    case "unchanged":
      return "Source unchanged";
    case "changed":
      return "Source changed; showing retained copy";
    case "missing":
      return "Source missing; showing retained copy";
    case "unavailable":
      return "Source status unavailable";
    default: {
      const unexpected: never = status;
      return unexpected;
    }
  }
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
  const loadGeneration = useRef(0);
  const detailGeneration = useRef(0);

  const selectedAssets = useMemo(
    () => assets.filter((asset) => selectedIds.includes(asset.id)),
    [assets, selectedIds],
  );

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
    void loadAssets();
  }, [origin, scope, includeDeleted, sessionId, projectPath]);

  async function showPreview(asset: RetainedAsset): Promise<void> {
    const requestGeneration = detailGeneration.current + 1;
    detailGeneration.current = requestGeneration;
    setBusy(true);
    setMessage("");
    setFullContent(null);
    try {
      const next = await packet03Api.previewAsset(asset.id, assetAccessScope(asset, { sessionId, projectPath }));
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
      const next = await packet03Api.contentAsset(asset.id, assetAccessScope(asset, { sessionId, projectPath }));
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
    setBusy(true);
    setMessage("");
    try {
      const result = await packet03Api.reuseAssets({
        asset_ids: selectedIds,
        session_id: sessionId,
        project_path: projectPath,
        allow_cross_session_reuse: scope === "all",
      });
      onReuseAssets(result, selectedAssets);
      setMessage("Ready to reuse in a draft.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : String(error));
    } finally {
      setBusy(false);
    }
  }

  async function previewDeletion(): Promise<void> {
    if (selectedIds.length === 0) return;
    setBusy(true);
    setMessage("");
    try {
      setDeletionPreview(await packet03Api.deleteAssetPreview(selectedIds));
    } catch (error) {
      setMessage(error instanceof Error ? error.message : String(error));
    } finally {
      setBusy(false);
    }
  }

  async function confirmDelete(): Promise<void> {
    if (!deletionPreview?.affected_asset_ids.length) return;
    setBusy(true);
    setMessage("");
    try {
      const result = await packet03Api.deleteAssets(deletionPreview.affected_asset_ids);
      setDeletionPreview(result);
      setSelectedIds([]);
      setMessage(deleteOutcomeText(result));
      await loadAssets({ clearMessage: false });
    } catch (error) {
      setMessage(error instanceof Error ? error.message : String(error));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="packet03-panel" aria-label="Library">
      <div className="packet03-row">
        <div>
          <p className="eyebrow">Library</p>
          <h2>Retained files</h2>
        </div>
        <button type="button" disabled={busy} onClick={() => void loadAssets()}>
          Refresh
        </button>
      </div>

      <div className="packet03-toolbar" aria-label="Library filters">
        <label>
          Scope
          <select value={scope} onChange={(event) => setScope(event.target.value as typeof scope)}>
            <option value="available">Available here</option>
            <option value="session">This conversation</option>
            <option value="project">This project</option>
            <option value="all">All retained</option>
          </select>
        </label>
        <label>
          Type
          <select value={origin} onChange={(event) => setOrigin(event.target.value as RetainedAssetOrigin | "all")}>
            <option value="all">Uploads and outputs</option>
            <option value="upload">Uploads</option>
            <option value="verified_output">Verified outputs</option>
          </select>
        </label>
        <label className="check-row">
          <input type="checkbox" checked={includeDeleted} onChange={(event) => setIncludeDeleted(event.target.checked)} />
          Show deleted
        </label>
      </div>

      {message ? <p role="status" className="notice">{message}</p> : null}

      <div className="packet03-grid">
        <ul className="packet03-list">
          {assets.map((asset) => (
            <li key={asset.id} className="packet03-item" aria-disabled={asset.deleted_at ? "true" : "false"}>
              <label className="check-row">
                <input
                  type="checkbox"
                  disabled={Boolean(asset.deleted_at)}
                  checked={selectedIds.includes(asset.id)}
                  onChange={(event) => {
                    setDeletionPreview(null);
                    setSelectedIds((current) => event.target.checked ? [...current, asset.id] : current.filter((id) => id !== asset.id));
                  }}
                />
                <strong>{asset.filename}</strong>
              </label>
              <div className="packet03-meta">
                <span>{assetOriginLabel(asset.origin)}</span>
                <span>{asset.scope === "project" ? "Project scoped" : "Conversation scoped"}</span>
                <span>{formatBytes(asset.size_bytes)}</span>
                <span>{asset.mutable_reference ? "Retained copy; source may have changed" : "Immutable retained copy"}</span>
                {asset.deleted_at ? <span>Deleted</span> : null}
              </div>
              {asset.observation ? <p className="hint">{asset.observation}</p> : null}
              <div className="packet03-actions">
                <button type="button" disabled={busy || Boolean(asset.deleted_at)} onClick={() => void showPreview(asset)}>
                  Preview
                </button>
                <button type="button" disabled={busy || Boolean(asset.deleted_at)} onClick={() => void showFullContent(asset)}>
                  Open full text
                </button>
                {window.workbench?.saveAsset ? (
                  <button
                    type="button"
                    disabled={busy || Boolean(asset.deleted_at)}
                    onClick={() => void window.workbench?.saveAsset?.({
                      assetId: asset.id,
                      ...assetAccessScope(asset, { sessionId, projectPath }),
                    })}
                  >
                    Save copy
                  </button>
                ) : null}
              </div>
            </li>
          ))}
        </ul>

        <aside className="packet03-item" aria-label="Library detail">
          <h3>Preview</h3>
          {preview ? (
            <>
              <div className="packet03-meta">
                <span>{preview.filename}</span>
                <span>{formatBytes(preview.size_bytes)}</span>
                <span>{preview.truncated ? "Preview truncated" : "Complete preview"}</span>
                <span>{sourceStatusLabel(preview.source_status)}</span>
                {fullContent?.id === preview.id ? <span>Full retained text</span> : null}
              </div>
              <pre className="packet03-preview">{preview.preview}</pre>
            </>
          ) : (
            <p className="hint">Choose Preview to inspect text safely before reuse.</p>
          )}

          <div className="packet03-actions">
            <button
              type="button"
              disabled={busy || selectedIds.length === 0 || (!onReuseSelectedAssets && (!sessionId || !onReuseAssets))}
              onClick={() => void reuseSelected()}
            >
              Reuse selected
            </button>
            <button type="button" disabled={busy || selectedIds.length === 0} onClick={() => void previewDeletion()}>
              Preview delete
            </button>
          </div>

          {deletionPreview ? (
            <div className="notice notice-warn">
              <p>{deletionPreview.note}</p>
              <p>
                {deletionPreview.affected_asset_ids.length} item{deletionPreview.affected_asset_ids.length === 1 ? "" : "s"} affected,
                {" "}{deletionPreview.preserved_asset_ids.length} preserved by other references.
              </p>
              <button type="button" disabled={busy || deletionPreview.affected_asset_ids.length === 0} onClick={() => void confirmDelete()}>
                Delete affected retained copies
              </button>
            </div>
          ) : null}
        </aside>
      </div>
    </section>
  );
}
