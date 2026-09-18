/// <reference types="vite/client" />

type WorkbenchSurface = "managed-inference";

interface WorkbenchBridge {
  productName: string;
  surface: WorkbenchSurface;
  backendUrl: string;
}

declare global {
  interface Window {
    workbench?: WorkbenchBridge;
  }
}

export {};
