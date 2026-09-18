/// <reference types="vite/client" />

type WorkbenchSurface = "scaffold";

interface WorkbenchBridge {
  productName: string;
  surface: WorkbenchSurface;
}

declare global {
  interface Window {
    workbench?: WorkbenchBridge;
  }
}

export {};
