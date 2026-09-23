import type { BrowserWindow, BrowserWindowConstructorOptions, Rectangle } from "electron";
import { ipcMain, screen } from "electron";

import { installTrustedAppWindow, requireTrustedIpc } from "./trustBoundary";

export interface AppearancePreviewState {
  theme: "" | "light" | "dark";
  activeId: string;
  activeName: string;
  activeDetail: string;
  overrides: Record<string, string>;
}

interface PreviewHost {
  preloadPath: string;
  appUrl: string;
  load: (window: BrowserWindow) => void;
  mainWindow: () => BrowserWindow | undefined;
  createWindow: (options: BrowserWindowConstructorOptions) => BrowserWindow;
}

let latest: AppearancePreviewState | null = null;
let preview: BrowserWindow | undefined;
let lastBounds: Rectangle | undefined;

export function installAppearancePreview(host: PreviewHost): void {
  ipcMain.handle("workbench:appearance-preview-open", (event) => {
    requireTrustedIpc(event);
    openAppearancePreview(host);
  });
  ipcMain.handle("workbench:appearance-preview-current", (event) => {
    requireTrustedIpc(event);
    return latest;
  });
  ipcMain.handle("workbench:appearance-preview-state", (event, payload: unknown) => {
    requireTrustedIpc(event);
    const next = sanitizePreviewState(payload);
    if (!next) return;
    latest = next;
    deliverPreviewState();
  });
}

export function openAppearancePreview(host: PreviewHost): void {
  if (preview && !preview.isDestroyed()) {
    if (preview.isMinimized()) preview.restore();
    preview.show();
    preview.focus();
    deliverPreviewState();
    return;
  }
  const placed = lastBounds ?? beside(host.mainWindow());
  const window = host.createWindow({
    title: "Appearance preview",
    x: placed.x,
    y: placed.y,
    width: placed.width,
    height: placed.height,
    minWidth: 360,
    minHeight: 480,
    autoHideMenuBar: true,
    show: false,
    webPreferences: {
      preload: host.preloadPath,
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });
  preview = window;
  installTrustedAppWindow(window, { appUrl: host.appUrl });
  window.once("ready-to-show", () => window.show());
  window.on("move", () => remember(window));
  window.on("resize", () => remember(window));
  window.on("closed", () => {
    if (preview === window) preview = undefined;
  });
  window.webContents.on("did-finish-load", () => deliverPreviewState());
  host.load(window);
}

function remember(window: BrowserWindow): void {
  if (!window.isDestroyed()) lastBounds = window.getBounds();
}

function deliverPreviewState(): void {
  if (!latest || !preview || preview.isDestroyed()) return;
  preview.webContents.send("workbench:appearance-preview-state", latest);
}

function beside(main: BrowserWindow | undefined): Rectangle {
  const width = 560;
  const height = 820;
  if (!main || main.isDestroyed()) return { x: 80, y: 80, width, height };
  const bounds = main.getBounds();
  const area = screen.getDisplayMatching(bounds).workArea;
  const margin = 16;
  const fittedHeight = Math.min(height, area.height - margin * 2);
  let x = bounds.x + bounds.width + margin;
  if (x + width > area.x + area.width) x = bounds.x - width - margin;
  if (x < area.x) x = area.x + margin;
  const y = Math.min(Math.max(bounds.y, area.y + margin), area.y + area.height - fittedHeight);
  return { x, y, width, height: fittedHeight };
}

function sanitizePreviewState(payload: unknown): AppearancePreviewState | null {
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) return null;
  const record = payload as Record<string, unknown>;
  const theme = record.theme === "light" || record.theme === "dark" ? record.theme : "";
  const activeId = plainText(record.activeId, 40);
  const activeName = plainText(record.activeName, 80);
  const activeDetail = plainText(record.activeDetail, 240);
  if (activeId === null || activeName === null || activeDetail === null) return null;
  if (activeId && !/^[a-z0-9-]+$/.test(activeId)) return null;
  const overrides: Record<string, string> = {};
  const source = record.overrides;
  if (!source || typeof source !== "object" || Array.isArray(source)) return null;
  for (const [name, value] of Object.entries(source)) {
    if (!/^--[a-z0-9-]{1,40}$/.test(name) || typeof value !== "string" || value.length > 300 || /[;{}<>]/.test(value)) continue;
    overrides[name] = value;
    if (Object.keys(overrides).length > 80) break;
  }
  return { theme, activeId, activeName, activeDetail, overrides };
}

function plainText(value: unknown, max: number): string | null {
  if (typeof value !== "string" || value.length > max) return null;
  return value;
}
