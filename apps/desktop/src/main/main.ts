import { existsSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { app, BrowserWindow } from "electron";
import { installBackground, retainWindowInBackground } from "./background";

import {
  ensureSharedSecret,
  resolveProductDataRoot,
} from "./localTrust";
import {
  installLocalTrustHeader,
  installTrustedAppWindow,
  packagedAppDocumentUrl,
} from "./trustBoundary";

const currentDir = path.dirname(fileURLToPath(import.meta.url));
const ownsSingleInstance = app.requestSingleInstanceLock();

if (!ownsSingleInstance) {
  app.quit();
}

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
    width: 1280,
    height: 860,
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
  retainWindowInBackground(window);

  const devServerUrl = process.env.VITE_DEV_SERVER_URL;
  if (devServerUrl) {
    installTrustedAppWindow(window, { appUrl: devServerUrl });
    // Vite's URL is a development bundler helper, not a product HTTP surface.
    void window.loadURL(devServerUrl);
    return;
  }

  const indexHtmlPath = path.join(currentDir, "../dist/index.html");
  installTrustedAppWindow(window, { appUrl: packagedAppDocumentUrl(indexHtmlPath) });
  void window.loadFile(indexHtmlPath);
}

function focusExistingWindow(): void {
  const [window] = BrowserWindow.getAllWindows();
  if (!window) {
    return;
  }
  if (window.isMinimized()) {
    window.restore();
  }
  window.show();
  window.focus();
}

function installApplicationTrust(): void {
  const token = ensureSharedSecret(resolveProductDataRoot());
  installLocalTrustHeader(token);
}

if (ownsSingleInstance) {
  app.on("second-instance", focusExistingWindow);

  app.whenReady().then(async () => {
    installApplicationTrust();
    await installBackground(focusExistingWindow);
    createWindow();

    app.on("activate", () => {
      if (BrowserWindow.getAllWindows().length === 0) {
        createWindow();
      }
    });
  });
}

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") {
    app.quit();
  }
});
