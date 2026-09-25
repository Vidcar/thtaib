import { existsSync } from "node:fs";
import { spawn } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { app, BrowserWindow, dialog } from "electron";
import { installAppearancePreview } from "./appearancePreviewWindow";
import { probeBackendCompatibility } from "./backendCompatibility";
import { installBackground, retainWindowInBackground } from "./background";
import { configureWindowsNotificationIdentity, ensureWindowsNotificationShortcut, WINDOWS_LAUNCH_BACKEND_ARG } from "./windowsNotificationIdentity";

import {
  ensureSharedSecret,
  resolveProductDataRoot,
  WORKBENCH_BACKEND_ORIGIN,
} from "./localTrust";
import {
  installLocalTrustHeader,
  installTrustedAppWindow,
  packagedAppDocumentUrl,
} from "./trustBoundary";

const currentDir = path.dirname(fileURLToPath(import.meta.url));
const ownsSingleInstance = app.requestSingleInstanceLock();
let mainWindow: BrowserWindow | undefined;
const STALE_BACKEND_NOTIFIED_ARG = "--workbench-stale-backend-notified";

configureWindowsNotificationIdentity();

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
    autoHideMenuBar: true,
    show: false,
    webPreferences: {
      preload: preloadScriptPath(),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });

  mainWindow = window;
  window.on("closed", () => {
    if (mainWindow === window) mainWindow = undefined;
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
  const window = mainWindow && !mainWindow.isDestroyed() ? mainWindow : undefined;
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

function shouldLaunchBackendFromShortcut(argv = process.argv): boolean {
  return process.platform === "win32" && !app.isPackaged && argv.includes(WINDOWS_LAUNCH_BACKEND_ARG);
}

async function ensureBackendFromShortcut(argv = process.argv): Promise<boolean> {
  if (!shouldLaunchBackendFromShortcut(argv)) {
    return false;
  }
  const current = await backendCompatibility();
  if (current === "compatible" || current === "incompatible") {
    return false;
  }
  const launcher = localLauncherPath();
  if (!launcher) {
    console.warn("Windows shortcut backend launch skipped: launcher script not found for this app path.");
    return false;
  }
  await runLauncherNoDesktop(launcher);
  return await backendCompatibility() === "compatible";
}

function localLauncherPath(): string | null {
  const appPath = path.resolve(app.getAppPath());
  const expectedDesktopDir = path.join("apps", "desktop");
  if (!appPath.endsWith(expectedDesktopDir)) {
    return null;
  }
  const repoRoot = path.resolve(appPath, "..", "..");
  const launcher = path.join(repoRoot, "scripts", "Launch-Workbench.ps1");
  const relative = path.relative(repoRoot, launcher);
  if (relative !== path.join("scripts", "Launch-Workbench.ps1") || !existsSync(launcher)) {
    return null;
  }
  return launcher;
}

async function runLauncherNoDesktop(launcher: string): Promise<void> {
  await new Promise<void>((resolve, reject) => {
    const child = spawn("powershell.exe", ["-NoProfile", "-ExecutionPolicy", "Bypass", "-File", launcher, "-NoDesktop", "-ShowConsole"], {
      cwd: path.dirname(path.dirname(launcher)),
      detached: false,
      stdio: "ignore",
      windowsHide: true,
      timeout: 90000,
    });
    child.on("error", reject);
    child.on("exit", (code) => {
      if (code === 0) {
        resolve();
      } else {
        reject(new Error(`Launcher exited with ${code ?? "no code"}`));
      }
    });
  }).catch((error: unknown) => {
    console.warn("Windows shortcut backend launch failed", error);
  });
}

async function backendCompatibility() {
  return probeBackendCompatibility(
    WORKBENCH_BACKEND_ORIGIN,
    ensureSharedSecret(resolveProductDataRoot()),
  );
}

async function showIncompatibleBackend(): Promise<void> {
  await dialog.showMessageBox({
    type: "warning",
    title: "Local AI Workbench",
    message: "The local Workbench service needs a restart",
    detail: "It does not provide the visual testing tools in this desktop build. The service and any running model were left untouched. Copy any unfinished edits, then use Quit from the Workbench tray and reopen it. Quit unloads managed models and stops active work after confirmation.",
    buttons: ["OK"],
  });
}

if (ownsSingleInstance) {
  app.on("second-instance", (_event, argv) => {
    if (shouldLaunchBackendFromShortcut(argv)) {
      void ensureBackendFromShortcut(argv).then((recovered) => {
        if (recovered) {
          installApplicationTrust();
          for (const window of BrowserWindow.getAllWindows()) window.reload();
        }
        void backendCompatibility().then((status) => {
          if (status === "incompatible" && !argv.includes(STALE_BACKEND_NOTIFIED_ARG)) void showIncompatibleBackend();
        });
        focusExistingWindow();
      });
    }
    focusExistingWindow();
  });

  app.whenReady().then(async () => {
    installApplicationTrust();
    await ensureWindowsNotificationShortcut().catch((error: unknown) => {
      console.warn("Windows notification shortcut setup failed", error);
    });
    await ensureBackendFromShortcut();
    const compatibility = await backendCompatibility();
    await installBackground(focusExistingWindow);
    installAppearancePreview({
      preloadPath: preloadScriptPath(),
      appUrl: process.env.VITE_DEV_SERVER_URL || packagedAppDocumentUrl(path.join(currentDir, "../dist/index.html")),
      mainWindow: () => mainWindow,
      createWindow: options => new BrowserWindow(options),
      load: window => {
        const devServerUrl = process.env.VITE_DEV_SERVER_URL;
        if (devServerUrl) {
          const url = new URL(devServerUrl);
          url.hash = "appearance-preview";
          void window.loadURL(url.toString());
          return;
        }
        void window.loadFile(path.join(currentDir, "../dist/index.html"), { hash: "appearance-preview" });
      },
    });
    createWindow();
    if (compatibility === "incompatible" && !process.argv.includes(STALE_BACKEND_NOTIFIED_ARG)) {
      await showIncompatibleBackend();
    }

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
