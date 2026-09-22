import { packet03Api, type RetainedAssetContent, type RetainedAssetPreview, type RetainedAssetSourceStatus } from "./packet03Api";

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

export async function saveRetainedCopy(assetId: string, access: RetainedAccess): Promise<boolean> {
  if (!window.workbench?.saveAsset) {
    throw new Error("Saving originals is available in the desktop app.");
  }
  const saved = await window.workbench.saveAsset({ assetId, ...access });
  return Boolean(saved);
}
