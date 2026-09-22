import { existsSync } from "node:fs";
import { mkdir } from "node:fs/promises";
import path from "node:path";
import { app, shell } from "electron";

export const WINDOWS_APP_USER_MODEL_ID = "com.vidcar.local-ai-workbench";
export const WINDOWS_TOAST_ACTIVATOR_CLSID = "{7A8F8374-B3D4-46A1-95C7-4C4B0E3254A2}";
export const WINDOWS_LAUNCH_BACKEND_ARG = "--workbench-launch-backend";
export const WINDOWS_SHORTCUT_NAME = "Local AI Workbench.lnk";

export interface WindowsNotificationIdentityOptions {
  appUserModelId?: string;
  toastActivatorClsid?: string;
}

export interface WindowsNotificationShortcutResult {
  shortcutPath: string;
  target: string;
  args: string;
  cwd: string;
}

export function configureWindowsNotificationIdentity(options: WindowsNotificationIdentityOptions = {}): void {
  if (process.platform !== "win32") {
    return;
  }
  app.setAppUserModelId(options.appUserModelId ?? WINDOWS_APP_USER_MODEL_ID);
  app.setToastActivatorCLSID(options.toastActivatorClsid ?? WINDOWS_TOAST_ACTIVATOR_CLSID);
}

export async function ensureWindowsNotificationShortcut(
  shortcutDirectory = defaultStartMenuProgramsPath(),
  options: WindowsNotificationIdentityOptions = {},
): Promise<WindowsNotificationShortcutResult | null> {
  if (process.platform !== "win32") {
    return null;
  }
  const details = notificationShortcutDetails(options);
  const shortcutPath = path.join(shortcutDirectory, WINDOWS_SHORTCUT_NAME);
  await mkdir(shortcutDirectory, { recursive: true });
  const operation = existsSync(shortcutPath) ? "update" : "create";
  const written = shell.writeShortcutLink(shortcutPath, operation, details);
  if (!written) {
    throw new Error(`Could not create Windows notification shortcut at ${shortcutPath}`);
  }
  return {
    shortcutPath,
    target: details.target,
    args: details.args ?? "",
    cwd: details.cwd ?? "",
  };
}

function notificationShortcutDetails(options: WindowsNotificationIdentityOptions): Electron.ShortcutDetails {
  const target = process.execPath;
  const appPath = app.getAppPath();
  const unpackaged = !app.isPackaged;
  const cwd = unpackaged ? appPath : path.dirname(target);
  return {
    target,
    args: unpackaged ? `${quoteShortcutArgument(appPath)} ${WINDOWS_LAUNCH_BACKEND_ARG}` : "",
    cwd,
    description: "Local AI Workbench",
    icon: target,
    iconIndex: 0,
    appUserModelId: options.appUserModelId ?? WINDOWS_APP_USER_MODEL_ID,
    toastActivatorClsid: options.toastActivatorClsid ?? WINDOWS_TOAST_ACTIVATOR_CLSID,
  };
}

function defaultStartMenuProgramsPath(): string {
  const appData = process.env.APPDATA;
  if (appData) {
    return path.join(appData, "Microsoft", "Windows", "Start Menu", "Programs");
  }
  return path.join(app.getPath("appData"), "Microsoft", "Windows", "Start Menu", "Programs");
}

function quoteShortcutArgument(value: string): string {
  return `"${value.replaceAll("\"", "\\\"")}"`;
}
