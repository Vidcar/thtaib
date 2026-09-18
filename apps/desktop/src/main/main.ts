import { existsSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { app, BrowserWindow } from "electron";

const currentDir = path.dirname(fileURLToPath(import.meta.url));

function preloadScriptPath(): string {
  const candidates = ["preload.js", "preload.mjs", "preload.cjs"];
  for (const name of candidates) {
    const candidate = path.join(currentDir, name);
    if (existsSync(candidate)) {
      return candidate;
    }
  }
  return path.join(currentDir, "preload.js");
}

function createWindow(): void {
  const window = new BrowserWindow({
    title: "Local AI Workbench",
    width: 1100,
    height: 780,
    show: false,
    webPreferences: {
      preload: preloadScriptPath(),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });

  window.once("ready-to-show", () => {
    window.show();
  });

  const devServerUrl = process.env.VITE_DEV_SERVER_URL;
  if (devServerUrl) {
    // Vite's URL is a development bundler helper, not a product HTTP surface.
    void window.loadURL(devServerUrl);
    return;
  }

  void window.loadFile(path.join(currentDir, "../dist/index.html"));
}

app.whenReady().then(() => {
  createWindow();

  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
    }
  });
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") {
    app.quit();
  }
});
