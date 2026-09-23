import { contextBridge, ipcRenderer } from "electron";

contextBridge.exposeInMainWorld("workbench", {
  productName: "Local AI Workbench",
  surface: "managed-inference",
  backendUrl: "http://127.0.0.1:8000",
  selectPath: (kind: "file" | "folder") => ipcRenderer.invoke("workbench:select-path", kind),
  readAppearance: () => ipcRenderer.invoke("workbench:appearance-read"),
  writeAppearance: (value: unknown) => ipcRenderer.invoke("workbench:appearance-write", value),
  activateRestore: (destination: string) => ipcRenderer.invoke("workbench:activate-restore", destination),
  saveAsset: (input: { assetId: string; sessionId?: string; projectPath?: string }) => ipcRenderer.invoke("workbench:save-asset", input),
  onAttention: (callback: (conversationId: string | null, runId: string) => void) => {
    const listener = (_event: unknown, id: string | null, runId: string) => callback(id, runId);
    ipcRenderer.on("workbench:attention", listener);
    return () => ipcRenderer.removeListener("workbench:attention", listener);
  },
});
