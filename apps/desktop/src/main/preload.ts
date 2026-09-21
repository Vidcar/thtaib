import { contextBridge, ipcRenderer } from "electron";

contextBridge.exposeInMainWorld("workbench", {
  productName: "Local AI Workbench",
  surface: "managed-inference",
  backendUrl: "http://127.0.0.1:8000",
  selectPath: (kind: "file" | "folder") => ipcRenderer.invoke("workbench:select-path", kind),
  activateRestore: (destination: string) => ipcRenderer.invoke("workbench:activate-restore", destination),
  saveAsset: (input: { assetId: string; sessionId?: string; projectPath?: string }) => ipcRenderer.invoke("workbench:save-asset", input),
  onAttention: (callback: (conversationId: string | null) => void) => {
    const listener = (_event: unknown, id: string | null) => callback(id);
    ipcRenderer.on("workbench:attention", listener);
    return () => ipcRenderer.removeListener("workbench:attention", listener);
  },
});
