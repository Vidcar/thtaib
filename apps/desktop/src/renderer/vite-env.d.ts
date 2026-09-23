/// <reference types="vite/client" />

type WorkbenchSurface = "managed-inference";

interface WorkbenchBridge {
  productName: string;
  surface: WorkbenchSurface;
  backendUrl: string;
  selectPath?: (kind: "file" | "folder") => Promise<string | null>;
  readAppearance?: () => Promise<unknown>;
  writeAppearance?: (value: unknown) => Promise<unknown>;
  openAppearancePreview?: () => Promise<void>;
  currentAppearancePreview?: () => Promise<unknown>;
  publishAppearancePreview?: (value: unknown) => Promise<unknown>;
  onAppearancePreview?: (callback: (value: unknown) => void) => () => void;
  activateRestore?: (destination: string) => Promise<void>;
  saveAsset?: (input: { assetId: string; sessionId?: string; projectPath?: string }) => Promise<string | null>;
  onAttention?: (callback: (conversationId: string | null, runId: string) => void) => () => void;
}

declare global {
  interface Window {
    workbench?: WorkbenchBridge;
  }
}

export {};
