import { packet03Api, type RetainedAsset, type RetainedAssetContent, type RetainedAssetPreview, type RetainedAssetSourceStatus } from "./packet03Api";

export interface RetainedAccess {
  sessionId?: string;
  projectPath?: string;
}

export function sourceStatusLabel(status: RetainedAssetSourceStatus): string {
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
    default: {
      const unexpected: never = status;
      return unexpected;
    }
  }
}

export function loadRetainedPreview(assetId: string, access: RetainedAccess): Promise<RetainedAssetPreview> {
  return packet03Api.previewAsset(assetId, access);
}

export function loadRetainedContent(assetId: string, access: RetainedAccess): Promise<RetainedAssetContent> {
  return packet03Api.contentAsset(assetId, access);
}

/** Reuse an explicitly selected, scoped original with a new Chat owner. */
export async function copyRetainedAsset(asset: RetainedAsset, sessionId: string, access: RetainedAccess): Promise<RetainedAsset> {
  const content = await loadRetainedContent(asset.id, access);
  let original = content.content_base64;
  if (content.encoding === "utf-8") {
    let binary = "";
    for (const byte of new TextEncoder().encode(content.text)) binary += String.fromCharCode(byte);
    original = btoa(binary);
  }
  if (typeof original !== "string") throw new Error("The selected file's original content is unavailable.");
  return packet03Api.uploadAsset({ session_id: sessionId, filename: asset.filename, content_type: asset.content_type, content_kind: asset.content_kind, content_base64: original });
}

export async function saveRetainedCopy(assetId: string, access: RetainedAccess): Promise<boolean> {
  if (!window.workbench?.saveAsset) {
    throw new Error("Saving originals is available in the desktop app.");
  }
  const saved = await window.workbench.saveAsset({ assetId, ...access });
  return Boolean(saved);
}
