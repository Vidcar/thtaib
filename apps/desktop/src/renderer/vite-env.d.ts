/// <reference types="vite/client" />

type WorkbenchSurface = "managed-inference";

interface WorkbenchBridge {
  productName: string;
  surface: WorkbenchSurface;
  backendUrl: string;
  selectPath?: (kind: "file" | "folder") => Promise<string | null>;
  activateRestore?: (destination: string) => Promise<void>;
  saveAsset?: (input: { assetId: string; sessionId?: string; projectPath?: string }) => Promise<string | null>;
  onAttention?: (callback: (conversationId: string | null) => void) => () => void;
}

declare global {
  interface Window {
    workbench?: WorkbenchBridge;
  }
}

export {};
