import { app, BrowserWindow, dialog, ipcMain, Menu, Notification, Tray } from "electron";
import { writeFile } from "node:fs/promises";
import path from "node:path";
import { createHash } from "node:crypto";
import { ensureSharedSecret, resolveProductDataRoot, WORKBENCH_BACKEND_ORIGIN, WORKBENCH_LOCAL_TOKEN_HEADER } from "./localTrust";
import { requireTrustedIpc, installLocalTrustHeader } from "./trustBoundary";

let tray: Tray | undefined;
let quitting = false;
let checkingQuit = false;
let timer: ReturnType<typeof setInterval> | undefined;
let polling = false;
const notified = new Set<string>();

async function backend<T>(route: string, method = "GET", body?: object): Promise<T> {
  const response = await fetch(`${WORKBENCH_BACKEND_ORIGIN}/v1/${route}`, {
    method, headers: { [WORKBENCH_LOCAL_TOKEN_HEADER]: ensureSharedSecret(resolveProductDataRoot()), "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : undefined,
    signal: AbortSignal.timeout(20000),
  });
  if (!response.ok) throw new Error(await response.text());
  return await response.json() as T;
}

async function requestQuit(): Promise<void> {
  if (quitting || checkingQuit) return;
  checkingQuit = true;
  try {
    const work = await backend<{ active_run_ids: string[]; active_import_ids: string[] }>("desktop/work");
    if (work.active_run_ids.length || work.active_import_ids.length) {
      const choice = await dialog.showMessageBox({ type: "question", title: "Work is still running",
        message: "Keep work running, or stop owned work and quit?", detail: "Partial answers and completed changes remain saved. Connected engines are not stopped.",
        buttons: ["Keep running", "Stop work and quit"], defaultId: 0, cancelId: 0 });
      if (choice.response !== 1) return;
    }
    await backend("desktop/stop-owned-work", "POST");
    quitting = true;
    if (timer) clearInterval(timer);
    tray?.destroy();
    app.quit();
  } catch {
    await dialog.showMessageBox({ type: "warning", message: "Work could not be confirmed stopped.",
      detail: "The app is staying open. Reopen it from the tray to inspect the local service and try again." });
  } finally { checkingQuit = false; }
}

export function retainWindowInBackground(window: BrowserWindow): void {
  window.on("close", (event) => {
    if (!quitting && tray) { event.preventDefault(); window.hide(); }
  });
}

export async function installBackground(openWindow: () => void): Promise<void> {
  tray = new Tray(await app.getFileIcon(process.execPath, { size: "small" }));
  tray.setToolTip("Local AI Workbench");
  tray.setContextMenu(Menu.buildFromTemplate([
    { label: "Open Local AI Workbench", click: openWindow },
    { type: "separator" }, { label: "Quit", click: () => { void requestQuit(); } },
  ]));
  tray.on("double-click", openWindow);
  app.on("before-quit", (event) => { if (!quitting) { event.preventDefault(); void requestQuit(); } });
  ipcMain.handle("workbench:select-path", async (event, kind: unknown) => {
    requireTrustedIpc(event);
    if (kind !== "file" && kind !== "folder") throw new Error("Unsupported selection");
    const result = await dialog.showOpenDialog({ properties: [kind === "folder" ? "openDirectory" : "openFile"] });
    requireTrustedIpc(event);
    return result.canceled ? null : result.filePaths[0] ?? null;
  });
  ipcMain.handle("workbench:save-asset", async (event, input: unknown) => {
    requireTrustedIpc(event);
    if (!input || typeof input !== "object" || Array.isArray(input)) throw new Error("Invalid file selection");
    const value = input as Record<string, unknown>;
    if (Object.keys(value).some(key => !["assetId", "sessionId", "projectPath"].includes(key))
      || typeof value.assetId !== "string" || !/^asset_[a-zA-Z0-9]+$/.test(value.assetId)
      || (value.sessionId !== undefined && (typeof value.sessionId !== "string" || value.sessionId.length > 200))
      || (value.projectPath !== undefined && (typeof value.projectPath !== "string" || value.projectPath.length > 4096))) {
      throw new Error("Invalid file scope");
    }
    const query = new URLSearchParams();
    if (typeof value.sessionId === "string") query.set("session_id", value.sessionId);
    if (typeof value.projectPath === "string") query.set("project_path", value.projectPath);
    const asset = await backend<{ text: string; filename: string; sha256: string; size_bytes: number }>(
      `assets/${encodeURIComponent(value.assetId)}/content?${query}`);
    requireTrustedIpc(event);
    const bytes = Buffer.from(asset.text, "utf8");
    if (bytes.length !== asset.size_bytes || createHash("sha256").update(bytes).digest("hex") !== asset.sha256) {
      throw new Error("Retained file verification failed");
    }
    const result = await dialog.showSaveDialog({ title: "Save retained file", defaultPath: path.basename(asset.filename),
      properties: ["showOverwriteConfirmation"] });
    requireTrustedIpc(event);
    if (result.canceled || !result.filePath) return null;
    await writeFile(result.filePath, bytes);
    return result.filePath;
  });
  ipcMain.handle("workbench:activate-restore", async (event, destination: unknown) => {
    requireTrustedIpc(event);
    if (typeof destination !== "string" || !destination || destination.length > 4096) throw new Error("Invalid restored location");
    await backend("backups/activate", "POST", { destination_root: destination });
    requireTrustedIpc(event);
    const deadline = Date.now() + 45000;
    while (Date.now() < deadline) {
      try {
        await backend("desktop/work");
        requireTrustedIpc(event);
        installLocalTrustHeader(ensureSharedSecret(resolveProductDataRoot()));
        for (const window of BrowserWindow.getAllWindows()) window.reload();
        return;
      } catch { await new Promise(resolve => setTimeout(resolve, 250)); }
    }
    throw new Error("The restore was selected, but the local service has not restarted. Reopen Local AI Workbench to retry startup.");
  });
  timer = setInterval(() => { void pollAttention(openWindow); }, 3000);
}

async function pollAttention(openWindow: () => void): Promise<void> {
  if (polling || quitting) return;
  polling = true;
  try {
    const [items, preferences] = await Promise.all([
      backend<Array<{ identity: string; conversation_id: string | null; title: string; kind: string; notified: boolean }>>("desktop/attention"),
      backend<{ attention_notifications: boolean }>("settings/presentation"),
    ]);
    const attentionCount = items.filter(item => item.kind !== "success").length;
    tray?.setToolTip(attentionCount ? `Local AI Workbench — ${attentionCount} need attention` : "Local AI Workbench");
    const foreground = BrowserWindow.getAllWindows().some((window) => window.isFocused() && window.isVisible());
    for (const item of items) {
      if (item.notified || notified.has(item.identity)) continue;
      if (foreground || !preferences.attention_notifications || !Notification.isSupported()) continue;
      const claim = await backend<{ claimed: boolean }>(`desktop/attention/${encodeURIComponent(item.identity)}/claim`, "POST");
      if (!claim.claimed) continue;
      notified.add(item.identity);
      const notification = new Notification({ title: item.title,
        body: item.kind === "approval" ? "An action needs your approval." : item.kind === "question" ? "An answer is needed." : item.kind === "success" ? "Your task is complete." : "Work needs attention after a failure." });
      notification.on("click", () => {
        openWindow();
        for (const window of BrowserWindow.getAllWindows()) window.webContents.send("workbench:attention", item.conversation_id);
      });
      notification.show();
    }
    const active = new Set(items.map((item) => item.identity));
    for (const id of notified) if (!active.has(id)) notified.delete(id);
  } catch { /* In-app attention remains authoritative when notifications cannot be delivered. */ }
  finally { polling = false; }
}
