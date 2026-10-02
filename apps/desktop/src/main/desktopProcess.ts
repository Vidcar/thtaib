import { mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import path from "node:path";

export function desktopProcessRecordPath(dataRoot: string): string {
  return path.join(dataRoot, "state", "desktop-process.json");
}

export function publishDesktopProcess(dataRoot: string, pid: number = process.pid): void {
  try {
    const record = desktopProcessRecordPath(dataRoot);
    mkdirSync(path.dirname(record), { recursive: true });
    writeFileSync(record, JSON.stringify({ pid }), { encoding: "utf8", mode: 0o600 });
  } catch (error: unknown) {
    console.warn("Desktop process record was not written", error);
  }
}

export function clearDesktopProcess(dataRoot: string, pid: number = process.pid): void {
  const record = desktopProcessRecordPath(dataRoot);
  let stored: unknown;
  try {
    stored = JSON.parse(readFileSync(record, "utf8"));
  } catch (error: unknown) {
    if ((error as NodeJS.ErrnoException).code === "ENOENT" || error instanceof SyntaxError) return;
    console.warn("Desktop process record was not cleared", error);
    return;
  }
  const recorded = typeof stored === "object" && stored !== null ? (stored as { pid?: unknown }).pid : undefined;
  if (recorded !== pid) return;
  try {
    rmSync(record, { force: true });
  } catch (error: unknown) {
    console.warn("Desktop process record was not cleared", error);
  }
}
