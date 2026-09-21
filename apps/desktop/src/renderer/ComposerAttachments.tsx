import { useEffect, useRef, useState } from "react";

import { packet03Api, type AssetContentKind, type RetainedAsset } from "./packet03Api";
import "./packet03Panels.css";

const MAX_UPLOAD_BYTES = 1_000_000;

export interface StagedComposerAttachment {
  id: string;
  asset: RetainedAsset;
}

interface LocalUpload {
  id: string;
  filename: string;
  size: number;
  status: "uploading" | "ready" | "error";
  message?: string;
  asset?: RetainedAsset;
}

interface ComposerAttachmentsProps {
  sessionId: string | null | undefined;
  disabled?: boolean;
  onAttachmentsChanged?: (attachments: StagedComposerAttachment[]) => void;
}

export function ComposerAttachments({ sessionId, disabled = false, onAttachmentsChanged }: ComposerAttachmentsProps) {
  const [items, setItems] = useState<LocalUpload[]>([]);
  const [dragActive, setDragActive] = useState(false);
  const generation = useRef(0);
  const onAttachmentsChangedRef = useRef(onAttachmentsChanged);

  useEffect(() => {
    onAttachmentsChangedRef.current = onAttachmentsChanged;
  }, [onAttachmentsChanged]);

  useEffect(() => {
    generation.current += 1;
    setItems([]);
    onAttachmentsChangedRef.current?.([]);
  }, [sessionId]);

  function readyAttachments(nextItems = items): StagedComposerAttachment[] {
    return nextItems
      .filter((item): item is LocalUpload & { asset: RetainedAsset } => item.status === "ready" && Boolean(item.asset))
      .map((item) => ({ id: item.asset.id, asset: item.asset }));
  }

  function commitItems(updater: (current: LocalUpload[]) => LocalUpload[]) {
    setItems((current) => {
      const next = updater(current);
      onAttachmentsChangedRef.current?.(readyAttachments(next));
      return next;
    });
  }

  async function stageFiles(fileList: FileList | File[]): Promise<void> {
    if (!sessionId) {
      commitItems((current) => [
        ...current,
        {
          id: crypto.randomUUID(),
          filename: "Attachment",
          size: 0,
          status: "error",
          message: "Choose a conversation before attaching files.",
        },
      ]);
      return;
    }
    const files = Array.from(fileList);
    const startedGeneration = generation.current;
    for (const file of files) {
      const localId = crypto.randomUUID();
      commitItems((current) => [
        ...current,
        { id: localId, filename: file.name || "untitled.txt", size: file.size, status: "uploading" },
      ]);
      try {
        const prepared = await prepareFile(file);
        const asset = await packet03Api.uploadAsset({
          session_id: sessionId,
          filename: file.name || "untitled.txt",
          content_type: prepared.contentType,
          content_kind: prepared.kind,
          content_base64: prepared.contentBase64,
        });
        if (generation.current !== startedGeneration) {
          continue;
        }
        commitItems((current) => current.map((item) => item.id === localId ? { ...item, status: "ready", asset, message: "Attached" } : item));
      } catch (error) {
        if (generation.current !== startedGeneration) {
          continue;
        }
        commitItems((current) => current.map((item) => item.id === localId ? {
          ...item,
          status: "error",
          message: error instanceof Error ? error.message : String(error),
        } : item));
      }
    }
  }

  function removeItem(id: string) {
    commitItems((current) => current.filter((item) => item.id !== id));
  }

  const cannotAttach = disabled || !sessionId;

  return (
    <section className="packet03-attachments" aria-label="Composer attachments">
      <div
        className={`packet03-dropzone${dragActive ? " is-active" : ""}`}
        onDragEnter={(event) => {
          event.preventDefault();
          setDragActive(true);
        }}
        onDragOver={(event) => event.preventDefault()}
        onDragLeave={() => setDragActive(false)}
        onDrop={(event) => {
          event.preventDefault();
          setDragActive(false);
          if (!cannotAttach) {
            void stageFiles(event.dataTransfer.files);
          }
        }}
      >
        <label>
          Attach text or code files
          <input
            type="file"
            multiple
            disabled={cannotAttach}
            onChange={(event) => {
              if (event.target.files) {
                void stageFiles(event.target.files);
              }
              event.currentTarget.value = "";
            }}
          />
        </label>
        <p className="hint">
          Files are read in the browser, validated as UTF-8 text or code, then stored as immutable retained uploads for this conversation.
        </p>
      </div>

      {items.length ? (
        <ul className="packet03-list">
          {items.map((item) => (
            <li key={item.id} className="packet03-item">
              <div className="packet03-row">
                <strong>{item.filename}</strong>
                <span className="hint">{formatBytes(item.size)}</span>
              </div>
              <p className={item.status === "error" ? "notice notice-warn" : "hint"}>
                {item.message ?? (item.status === "uploading" ? "Uploading..." : "Ready")}
              </p>
              {item.asset ? <p className="hint">Staged retained upload: {item.asset.id}</p> : null}
              <button type="button" disabled={disabled} onClick={() => removeItem(item.id)}>
                Remove from draft
              </button>
            </li>
          ))}
        </ul>
      ) : null}
    </section>
  );
}

async function prepareFile(file: File): Promise<{ contentBase64: string; contentType: string; kind: AssetContentKind }> {
  if (file.size === 0) {
    throw new Error("Empty files cannot be attached.");
  }
  if (file.size > MAX_UPLOAD_BYTES) {
    throw new Error(`File is too large. Attach text/code files up to ${formatBytes(MAX_UPLOAD_BYTES)}.`);
  }
  const bytes = new Uint8Array(await file.arrayBuffer());
  let text: string;
  try {
    text = new TextDecoder("utf-8", { fatal: true }).decode(bytes);
  } catch {
    throw new Error("File is not valid UTF-8 text. Attach a text or code file.");
  }
  if (hasControlBytes(text)) {
    throw new Error("File looks like binary data. Attach a text or code file.");
  }
  const contentType = normalizedContentType(file);
  if (!isSupportedTextType(contentType, file.name)) {
    throw new Error("Unsupported attachment type. Attach plain text, Markdown, JSON, YAML, XML, CSV or source code.");
  }
  return {
    contentBase64: bytesToBase64(bytes),
    contentType,
    kind: codeLike(file.name, contentType) ? "code" : "text",
  };
}

function normalizedContentType(file: File): string {
  return file.type || contentTypeFromName(file.name) || "text/plain";
}

function isSupportedTextType(contentType: string, filename: string): boolean {
  return contentType.startsWith("text/")
    || ["application/json", "application/xml", "application/x-yaml", "application/yaml"].includes(contentType)
    || codeLike(filename, contentType);
}

function codeLike(filename: string, contentType: string): boolean {
  const extension = filename.toLowerCase().split(".").pop() ?? "";
  return [
    "c", "cc", "cpp", "cs", "css", "go", "h", "hpp", "html", "java", "js", "jsx", "json", "kt", "mdx",
    "php", "ps1", "py", "rb", "rs", "sh", "sql", "ts", "tsx", "xml", "yaml", "yml",
  ].includes(extension) || contentType.includes("javascript") || contentType.includes("json") || contentType.includes("xml");
}

function contentTypeFromName(filename: string): string | null {
  const extension = filename.toLowerCase().split(".").pop() ?? "";
  if (extension === "md") return "text/markdown";
  if (extension === "csv") return "text/csv";
  if (extension === "json") return "application/json";
  if (extension === "xml") return "application/xml";
  if (extension === "yaml" || extension === "yml") return "application/yaml";
  if (codeLike(filename, "")) return "text/plain";
  return null;
}

function hasControlBytes(text: string): boolean {
  return /[\u0000-\u0008\u000b\u000c\u000e-\u001f]/.test(text);
}

function bytesToBase64(bytes: Uint8Array): string {
  let binary = "";
  for (const byte of bytes) {
    binary += String.fromCharCode(byte);
  }
  return btoa(binary);
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}
