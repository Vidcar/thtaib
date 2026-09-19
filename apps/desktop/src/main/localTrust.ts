import { randomBytes } from "node:crypto";
import { chmodSync, closeSync, existsSync, mkdirSync, openSync, readFileSync, writeSync } from "node:fs";
import { homedir } from "node:os";
import path from "node:path";

/** Locked names shared with Issue #41 (ADR-0002 generator, when merged). */
export const WORKBENCH_LOCAL_TOKEN_HEADER = "X-Workbench-Local-Token";
export const WORKBENCH_LOCAL_BIND = "127.0.0.1";
export const WORKBENCH_BACKEND_ORIGIN = `http://${WORKBENCH_LOCAL_BIND}:8000`;
export const SHARED_SECRET_FILENAME = "desktop_backend_shared_secret";
export const PRODUCT_DATA_DIR = "LocalAIWorkbench";
export const DATA_ROOT_ENV = "WORKBENCH_DATA_ROOT";

export function resolveProductDataRoot(
  environ: NodeJS.ProcessEnv = process.env,
  platform: NodeJS.Platform = process.platform,
): string {
  const override = environ[DATA_ROOT_ENV];
  if (override) {
    return path.resolve(override);
  }
  if (platform === "win32") {
    const localAppData = environ.LOCALAPPDATA;
    if (localAppData) {
      return path.join(localAppData, PRODUCT_DATA_DIR);
    }
    return path.join(homedir(), "AppData", "Local", PRODUCT_DATA_DIR);
  }
  const xdg = environ.XDG_DATA_HOME;
  if (xdg) {
    return path.join(xdg, PRODUCT_DATA_DIR);
  }
  return path.join(homedir(), ".local", "share", PRODUCT_DATA_DIR);
}

export function sharedSecretPath(dataRoot: string): string {
  return path.join(dataRoot, "state", SHARED_SECRET_FILENAME);
}

export function ensureSharedSecret(dataRoot: string): string {
  const filePath = sharedSecretPath(dataRoot);
  mkdirSync(path.dirname(filePath), { recursive: true });
  const existing = readExistingSecret(filePath);
  if (existing) {
    return existing;
  }
  const token = randomBytes(32).toString("base64url");
  try {
    const fd = openSync(filePath, "wx", 0o600);
    try {
      writeSync(fd, token);
    } finally {
      closeSync(fd);
    }
  } catch (error) {
    const code = (error as NodeJS.ErrnoException).code;
    if (code === "EEXIST") {
      const reused = readExistingSecret(filePath);
      if (!reused) {
        throw new Error("Shared secret file exists but is empty");
      }
      return reused;
    }
    throw error;
  }
  chmodSync(filePath, 0o600);
  return token;
}

function readExistingSecret(filePath: string): string {
  if (!existsSync(filePath)) {
    return "";
  }
  return readFileSync(filePath, "utf8").trim();
}
