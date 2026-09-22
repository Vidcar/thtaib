import { useEffect, useMemo, useRef, useState } from "react";

import {
  packet03Api,
  type RetainedAsset,
  type RetainedAssetContent,
  type RetainedAssetPreview,
} from "./packet03Api";
import "./ChatRetainedFiles.css";
import { Icon } from "./Icon";

export interface ChatRetainedFilesProps {
  conversationId: string;
  runIds?: string[];
  currentRunId?: string | null;
  currentRunStatus?: string | null;
  records?: RetainedAsset[];
  compact?: boolean;
  onReuse: (assetIds: string[]) => void;
  onOpenFiles?: (assetIds: string[]) => void;
}

const TERMINAL_RUN_STATUSES = new Set(["completed", "failed", "cancelled", "interrupted"]);

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function originLabel(asset: RetainedAsset): string {
  if (asset.origin === "verified_output") {
    return asset.source_tool_name ? `Verified ${asset.source_tool_name} output` : "Verified output";
  }
  return "Uploaded file";
}

function sourceLabel(status: RetainedAssetPreview["source_status"] | null, asset: RetainedAsset): string {
  if (asset.deleted_at) {
    return "Deleted retained copy";
  }
  switch (status) {
    case "unchanged":
      return "Source unchanged";
    case "changed":
      return "Source changed; retained copy preserved";
    case "missing":
      return "Source missing; retained copy preserved";
    case "retained_only":
      return "Retained copy";
    case "unavailable":
      return "Source status unavailable";
    default:
      return asset.mutable_reference ? "Retained copy; source can change" : "Immutable retained copy";
  }
}

function groupLabel(group: string, currentRunId?: string | null, currentRunStatus?: string | null): string {
  if (group === "__uploads__") {
    return "Uploaded files";
  }
  if (group === currentRunId) {
    return currentRunStatus && !TERMINAL_RUN_STATUSES.has(currentRunStatus) ? "Files from current response" : "Files from this response";
  }
  return "Files from an earlier response";
}

function accessScope(asset: RetainedAsset, conversationId: string): { sessionId?: string; projectPath?: string } {
  if (asset.project_path) {
    return { projectPath: asset.project_path };
  }
  return { sessionId: conversationId };
}

export function useChatRetainedAssets(conversationId: string, providedRecords?: RetainedAsset[]): {
  records: RetainedAsset[];
  loading: boolean;
  error: string;
  refresh: () => void;
} {
  const [records, setRecords] = useState<RetainedAsset[]>(providedRecords ?? []);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const generation = useRef(0);

  function refresh(): void {
    if (providedRecords || !conversationId) {
      return;
    }
    const request = ++generation.current;
    setLoading(true);
    setError("");
    void packet03Api.assets({ sessionId: conversationId })
      .then((next) => {
        if (generation.current === request) {
          setRecords(next);
        }
      })
      .catch((caught: unknown) => {
        if (generation.current === request) {
          setError(caught instanceof Error ? caught.message : String(caught));
        }
      })
      .finally(() => {
        if (generation.current === request) {
          setLoading(false);
        }
      });
  }

  useEffect(() => {
    generation.current += 1;
    setRecords(providedRecords ?? []);
    setLoading(false);
    setError("");
    refresh();
    return () => {
      generation.current += 1;
    };
  }, [conversationId, providedRecords]);

  return { records, loading, error, refresh };
}

export function ChatRetainedFiles({
  conversationId,
  runIds,
  currentRunId = null,
  currentRunStatus = null,
  records: providedRecords,
  compact = false,
  onReuse,
  onOpenFiles,
}: ChatRetainedFilesProps) {
  const { records, loading, error, refresh } = useChatRetainedAssets(conversationId, providedRecords);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [preview, setPreview] = useState<RetainedAssetPreview | null>(null);
  const [content, setContent] = useState<RetainedAssetContent | null>(null);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState("");
  const detailGeneration = useRef(0);
  const terminalRefreshKey = useRef("");
  const runFilter = useMemo(() => new Set(runIds ?? []), [runIds]);
  const visible = useMemo(() => {
    const filtered = records.filter((asset) => !asset.deleted_at && (runFilter.size === 0 || (asset.source_run_id && runFilter.has(asset.source_run_id))));
    return filtered.sort((left, right) => Date.parse(left.observed_at) - Date.parse(right.observed_at));
  }, [records, runFilter]);
  const grouped = useMemo(() => {
    const groups = new Map<string, RetainedAsset[]>();
    for (const asset of visible) {
      const key = asset.source_run_id ?? "__uploads__";
      groups.set(key, [...(groups.get(key) ?? []), asset]);
    }
    return [...groups.entries()];
  }, [visible]);

  useEffect(() => {
    setSelectedIds((current) => current.filter((id) => visible.some((asset) => asset.id === id)));
  }, [visible]);

  useEffect(() => {
    if (!currentRunId || !currentRunStatus || !TERMINAL_RUN_STATUSES.has(currentRunStatus) || providedRecords) {
      return;
    }
    const key = `${conversationId}:${currentRunId}:${currentRunStatus}`;
    if (terminalRefreshKey.current === key) {
      return;
    }
    terminalRefreshKey.current = key;
    refresh();
  }, [conversationId, currentRunId, currentRunStatus, providedRecords]);

  if (!loading && !error && visible.length === 0) {
    return null;
  }

  async function showPreview(asset: RetainedAsset, full = false): Promise<void> {
    const request = ++detailGeneration.current;
    setBusy(asset.id);
    setMessage("");
    try {
      const scope = accessScope(asset, conversationId);
      if (full) {
        const next = await packet03Api.contentAsset(asset.id, scope);
        if (detailGeneration.current !== request) {
          return;
        }
        setContent(next);
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
        onOpenFiles?.([asset.id]);
      } else {
        const next = await packet03Api.previewAsset(asset.id, scope);
        if (detailGeneration.current !== request) {
          return;
        }
        setContent(null);
        setPreview(next);
      }
    } catch (caught) {
      if (detailGeneration.current === request) {
        setMessage(caught instanceof Error ? caught.message : String(caught));
      }
    } finally {
      if (detailGeneration.current === request) {
        setBusy("");
      }
    }
  }

  async function saveCopy(asset: RetainedAsset): Promise<void> {
    setBusy(asset.id);
    setMessage("");
    try {
      const saved = await window.workbench?.saveAsset?.({
        assetId: asset.id,
        ...accessScope(asset, conversationId),
      });
      setMessage(saved ? `Saved ${asset.filename}.` : "Save cancelled.");
    } catch (caught) {
      setMessage(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setBusy("");
    }
  }

  function toggle(id: string, checked: boolean): void {
    setSelectedIds((current) => checked ? [...new Set([...current, id])] : current.filter((item) => item !== id));
  }

  return (
    <section className={`chat-retained-files${compact ? " compact" : ""}`} aria-label="Retained files">
      {!compact ? <div className="chat-retained-files-head">
        <div>
          <p className="eyebrow">Retained files</p>
          <h3>{visible.length} file{visible.length === 1 ? "" : "s"} available</h3>
        </div>
        <div className="chat-retained-files-actions">
          <button type="button" disabled={loading || Boolean(providedRecords)} onClick={refresh}>Refresh</button>
          <button type="button" disabled={selectedIds.length === 0} onClick={() => onReuse(selectedIds)}>Reuse selected</button>
        </div>
      </div> : null}
      {loading ? <p className="hint">Loading retained files...</p> : null}
      {error ? <p role="status" className="notice notice-error">{error}</p> : null}
      {message ? <p role="status" className="notice">{message}</p> : null}
      <div className="chat-retained-file-groups">
        {grouped.map(([group, assets]) => (
          <div key={group} className="chat-retained-file-group">
            {!compact ? <h4>{groupLabel(group, currentRunId, currentRunStatus)}</h4> : null}
            <ul>
              {assets.map((asset) => (
                <li key={asset.id} className="chat-retained-file-card">
                  {compact ? <button className="retained-file-name" type="button" disabled={busy === asset.id} onClick={() => void showPreview(asset)} title={`Preview ${asset.filename}`}><Icon name="files" /><span>{asset.filename}</span><small>{formatBytes(asset.size_bytes)}</small></button> : <label className="check-row">
                    <input type="checkbox" checked={selectedIds.includes(asset.id)} onChange={(event) => toggle(asset.id, event.target.checked)} />
                    <strong>{asset.filename}</strong>
                  </label>}
                  {!compact ? <div className="chat-retained-file-meta">
                    <span>{originLabel(asset)}</span>
                    <span>{asset.scope === "project" ? "Project scoped" : "Conversation scoped"}</span>
                    <span>{formatBytes(asset.size_bytes)}</span>
                    <span>{sourceLabel(preview?.id === asset.id ? preview.source_status : null, asset)}</span>
                  </div> : null}
                  {asset.observation ? <p className="hint">{asset.observation}</p> : null}
                  <div className="chat-retained-files-actions">
                    {compact ? <button type="button" onClick={() => onReuse([asset.id])}>Use again</button> : <button type="button" disabled={busy === asset.id} onClick={() => void showPreview(asset)}>Preview</button>}
                    <button type="button" disabled={busy === asset.id} onClick={() => void showPreview(asset, true)}>Open text</button>
                    {window.workbench?.saveAsset ? (
                      <button type="button" disabled={busy === asset.id} onClick={() => void saveCopy(asset)}>Save copy</button>
                    ) : null}
                  </div>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>
      {preview ? (
        <details className="chat-retained-preview" open>
          <summary>{content?.id === preview.id ? "Full retained text" : "Preview"}: {preview.filename}</summary>
          <div className="chat-retained-file-meta">
            <span>{formatBytes(preview.size_bytes)}</span>
            <span>{sourceLabel(preview.source_status, visible.find((asset) => asset.id === preview.id) ?? retainedPreviewAsset(preview, conversationId))}</span>
            {preview.truncated ? <span>Preview truncated</span> : null}
          </div>
          <pre>{preview.preview}</pre>
        </details>
      ) : null}
    </section>
  );
}

function retainedPreviewAsset(preview: RetainedAssetPreview, conversationId: string): RetainedAsset {
  return {
    id: preview.id,
    origin: "upload",
    scope: "session",
    session_id: conversationId,
    project_path: null,
    access_scope: `session:${conversationId}`,
    storage: "application.sqlite",
    filename: preview.filename,
    content_type: preview.content_type,
    content_kind: "text",
    encoding: "utf-8",
    size_bytes: preview.size_bytes,
    sha256: preview.sha256,
    observed_at: new Date(0).toISOString(),
    source_run_id: null,
    source_tool_call_id: null,
    source_tool_name: null,
    mutable_reference: null,
    observation: null,
    deleted_at: null,
  };
}
