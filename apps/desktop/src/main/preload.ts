import { contextBridge } from "electron";

contextBridge.exposeInMainWorld("workbench", {
  productName: "Local AI Workbench",
  surface: "managed-inference",
  backendUrl: "http://127.0.0.1:8000",
});
