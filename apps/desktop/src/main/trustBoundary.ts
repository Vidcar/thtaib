import { pathToFileURL } from "node:url";

import type { BrowserWindow, Event as ElectronEvent, IpcMainInvokeEvent, OnBeforeSendHeadersListenerDetails } from "electron";
import { shell, session } from "electron";

import { WORKBENCH_BACKEND_ORIGIN, WORKBENCH_LOCAL_TOKEN_HEADER } from "./localTrust";

export interface TrustedApplicationDocument {
  appUrl: string;
  backendOrigin?: string;
}

type WillFrameNavigateEvent = ElectronEvent<{ url: string }>;

interface TrustedWindowRecord {
  window: BrowserWindow;
  appUrl: string;
  backendOrigin: string;
}

const trustedWindows = new Map<number, TrustedWindowRecord>();

export function requireTrustedIpc(event: IpcMainInvokeEvent): void {
  const record = trustedWindows.get(event.sender.id);
  const frame = event.senderFrame;
  if (!record || record.window.isDestroyed() || event.sender.isDestroyed() ||
      event.sender !== record.window.webContents || !frame || frame.isDestroyed() || frame.detached ||
      frame !== event.sender.mainFrame || frame.parent !== null ||
      !isTrustedApplicationUrl(event.sender.getURL(), record.appUrl) || !isTrustedApplicationUrl(frame.url, record.appUrl)) {
    throw new Error("This document cannot use desktop actions.");
  }
}

export function packagedAppDocumentUrl(indexHtmlPath: string): string {
  return pathToFileURL(indexHtmlPath).toString();
}

export function isHttpExternalUrl(rawUrl: string): boolean {
  try {
    const parsed = new URL(rawUrl);
    return parsed.protocol === "http:" || parsed.protocol === "https:";
  } catch {
    return false;
  }
}

export function installTrustedAppWindow(window: BrowserWindow, document: TrustedApplicationDocument): void {
  const appUrl = normalizeUrl(document.appUrl);
  const backendOrigin = normalizeOrigin(document.backendOrigin ?? WORKBENCH_BACKEND_ORIGIN);
  const webContentsId = window.webContents.id;
  trustedWindows.set(webContentsId, { window, appUrl, backendOrigin });
  window.on("closed", () => {
    trustedWindows.delete(webContentsId);
  });
  installNavigationPolicy(window, appUrl);
}

export function installLocalTrustHeader(token: string, backendOrigin = WORKBENCH_BACKEND_ORIGIN): void {
  // Electron replaces the previous listener. Reinstall after restore activation
  // so the renderer uses the new root's token with the same document checks.
  const normalizedBackendOrigin = normalizeOrigin(backendOrigin);
  session.defaultSession.webRequest.onBeforeSendHeaders(
    { urls: ["http://*/*", "https://*/*"] },
    (details, callback) => {
      const requestHeaders = withoutLocalToken(details.requestHeaders);
      if (!isTrustedBackendRequest(details, normalizedBackendOrigin)) {
        callback({ requestHeaders });
        return;
      }
      callback({
        requestHeaders: {
          ...requestHeaders,
          [WORKBENCH_LOCAL_TOKEN_HEADER]: token,
        },
      });
    },
  );
}

export function isTrustedBackendRequest(details: OnBeforeSendHeadersListenerDetails, backendOrigin = WORKBENCH_BACKEND_ORIGIN): boolean {
  const target = parseUrl(details.url);
  if (!target) {
    return false;
  }
  const record = details.webContentsId === undefined ? undefined : trustedWindows.get(details.webContentsId);
  if (!record || target.origin !== record.backendOrigin || target.origin !== normalizeOrigin(backendOrigin)) {
    return false;
  }
  try {
    if (record.window.isDestroyed()) {
      return false;
    }
    const contents = details.webContents;
    if (!contents || contents.isDestroyed() || contents !== record.window.webContents) {
      return false;
    }
    const frame = details.frame;
    if (!frame || frame.isDestroyed() || frame.detached || frame !== contents.mainFrame || frame.parent !== null) {
      return false;
    }
    if (!isTrustedApplicationUrl(contents.getURL(), record.appUrl)) {
      return false;
    }
    return isTrustedApplicationUrl(frame.url, record.appUrl);
  } catch {
    return false;
  }
}

function installNavigationPolicy(window: BrowserWindow, appUrl: string): void {
  const contents = window.webContents;
  contents.setWindowOpenHandler(({ url }) => {
    if (isTrustedApplicationUrl(contents.getURL(), appUrl)) {
      openValidatedExternal(url, appUrl);
    }
    return { action: "deny" };
  });
  contents.on("will-navigate", (event, url) => {
    if (!isTrustedApplicationUrl(url, appUrl)) {
      event.preventDefault();
    }
  });
  contents.on("will-frame-navigate", (event: WillFrameNavigateEvent) => {
    if (!isTrustedApplicationUrl(event.url, appUrl)) {
      event.preventDefault();
    }
  });
  contents.on("will-redirect", (event, url) => {
    if (!isTrustedApplicationUrl(url, appUrl)) {
      event.preventDefault();
    }
  });
}

function openValidatedExternal(rawUrl: string, appUrl: string): void {
  const parsed = parseUrl(rawUrl);
  if (!parsed || parsed.username || parsed.password || !isHttpExternalUrl(rawUrl) || isTrustedApplicationUrl(rawUrl, appUrl)) {
    return;
  }
  setImmediate(() => {
    void shell.openExternal(parsed.toString()).catch(() => undefined);
  });
}

function isTrustedApplicationUrl(rawUrl: string, appUrl: string): boolean {
  const parsed = parseUrl(rawUrl);
  if (!parsed) {
    return false;
  }
  if (parsed.protocol === "file:" || parsed.protocol === "http:" || parsed.protocol === "https:") {
    parsed.hash = "";
    return parsed.toString() === appUrl;
  }
  return false;
}

function withoutLocalToken(headers: Record<string, string | string[]>): Record<string, string | string[]> {
  return Object.fromEntries(
    Object.entries(headers).filter(([name]) => name.toLowerCase() !== WORKBENCH_LOCAL_TOKEN_HEADER.toLowerCase()),
  );
}

function normalizeUrl(rawUrl: string): string {
  const parsed = new URL(rawUrl);
  parsed.hash = "";
  return parsed.toString();
}

function normalizeOrigin(rawOrigin: string): string {
  return new URL(rawOrigin).origin;
}

function parseUrl(rawUrl: string): URL | null {
  try {
    return new URL(rawUrl);
  } catch {
    return null;
  }
}
