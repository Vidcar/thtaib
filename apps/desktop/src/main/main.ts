import { existsSync } from "node:fs";
import { spawn } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { app, BrowserWindow } from "electron";
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

function shouldLaunchBackendFromShortcut(argv = process.argv): boolean {
  return process.platform === "win32" && !app.isPackaged && argv.includes(WINDOWS_LAUNCH_BACKEND_ARG);
}

async function ensureBackendFromShortcut(argv = process.argv): Promise<boolean> {
  if (!shouldLaunchBackendFromShortcut(argv)) {
    return false;
  }
  if (await backendHealthy()) {
    return false;
  }
  const launcher = localLauncherPath();
  if (!launcher) {
    console.warn("Windows shortcut backend launch skipped: launcher script not found for this app path.");
    return false;
  }
  await runLauncherNoDesktop(launcher);
  return await backendHealthy();
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

async function backendHealthy(): Promise<boolean> {
  try {
    const response = await fetch(`${WORKBENCH_BACKEND_ORIGIN}/health`, { signal: AbortSignal.timeout(1500) });
    if (!response.ok) {
      return false;
    }
    const health = await response.json() as { status?: string; product?: string };
    return health.status === "ok" && health.product === "Local AI Workbench";
  } catch {
    return false;
  }
}

if (ownsSingleInstance) {
  app.on("second-instance", (_event, argv) => {
    if (shouldLaunchBackendFromShortcut(argv)) {
      void ensureBackendFromShortcut(argv).then((recovered) => {
        if (recovered) {
          installApplicationTrust();
          for (const window of BrowserWindow.getAllWindows()) window.reload();
        }
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
