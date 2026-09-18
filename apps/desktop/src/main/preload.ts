import { contextBridge } from "electron";

contextBridge.exposeInMainWorld("workbench", {
  productName: "Local AI Workbench",
  surface: "scaffold",
});
