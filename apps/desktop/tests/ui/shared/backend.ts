import { spawn, type ChildProcess } from "node:child_process";
import { createServer, request as httpRequest, type Server } from "node:http";
import { mkdir, readFile, rm } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { randomUUID } from "node:crypto";
import { requireDesktopTestScratchPath } from "../../../src/main/desktopTestIsolation.ts";

export const repositoryRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../../../..");
const scratchRoot = path.join(repositoryRoot, ".scratch", "ui-baseline");
const localTokenHeader = "X-Workbench-Local-Token";

export interface BackendSeed {
  project_id: string;
  conversation_id: string;
  deployment_id: string;
  profile_id: string | null;
  fixture_root: string;
  paths?: Record<string, string>;
  [key: string]: unknown;
}

export interface BackendHandle {
  readonly origin: string;
  readonly browserOrigin: string;
  readonly dataRoot: string;
  readonly pid: number;
  /** Native main reads this same isolated secret; never place it in page JS or evidence. */
  readonly token: string;
  seed: BackendSeed;
  control<T = Record<string, unknown>>(route: string, body?: unknown): Promise<T>;
  state<T = Record<string, unknown>>(): Promise<T>;
  restart(): Promise<void>;
  close(): Promise<void>;
  loseNextCommandResponseBeforeAcceptance(): void;
}

const pause = (ms: number) => new Promise(resolve => setTimeout(resolve, ms));

async function waitUntil<T>(operation: () => Promise<T | undefined>, timeout = 30_000): Promise<T> {
  const deadline = Date.now() + timeout;
  while (Date.now() < deadline) {
    const result = await operation();
    if (result !== undefined) return result;
    await pause(100);
  }
  throw new Error("The isolated backend did not become ready before the startup deadline.");
}

async function terminateOwnedProcess(child: ChildProcess | undefined): Promise<void> {
  if (!child?.pid || child.exitCode !== null) return;
  if (process.platform === "win32") {
    const killer = spawn("taskkill.exe", ["/PID", String(child.pid), "/T", "/F"], { windowsHide: true, stdio: "ignore" });
    await new Promise<void>((resolve, reject) => {
      const deadline = setTimeout(() => { killer.kill(); reject(new Error("Owned fixture process-tree cleanup exceeded its deadline.")); }, 10_000);
      killer.once("error", error => { clearTimeout(deadline); reject(error); });
      killer.once("exit", () => { clearTimeout(deadline); resolve(); });
    });
  } else child.kill("SIGTERM");
  await waitUntil(async () => child.exitCode !== null || child.signalCode !== null ? true : undefined, 10_000);
}

/** Actual product requests pass through unchanged. Authentication exists only on the server hop. */
async function startAuthBoundary(target: () => { origin: string; token: string }, faults: { loseCommandResponse: boolean }): Promise<{ server: Server; origin: string }> {
  const server = createServer((incoming, outgoing) => {
    const current = target();
    const route = incoming.url ?? "/";
    if (!current.origin || !/^\/(?:health(?:\?|$)|v1(?:\/|\?|$)|__test__(?:\/|\?|$))/.test(route) || route.includes("\\")) {
      outgoing.writeHead(400).end("Unsupported isolated backend route.");
      return;
    }
    const upstreamUrl = new URL(route, current.origin);
    if (upstreamUrl.origin !== current.origin) {
      outgoing.writeHead(400).end("The isolated boundary accepts only its owned backend.");
      return;
    }
    const headers = { ...incoming.headers };
    const loseResponse = faults.loseCommandResponse && incoming.method === "POST" && route.endsWith("/commands");
    if (loseResponse) faults.loseCommandResponse = false;
    for (const key of Object.keys(headers)) {
      if (["host", "x-workbench-local-token", "authorization", "cookie"].includes(key.toLowerCase())) delete headers[key];
    }
    headers[localTokenHeader] = current.token;
    const upstream = httpRequest(upstreamUrl, { method: incoming.method, headers }, response => {
      if (loseResponse) { response.resume(); return; }
      const responseHeaders = { ...response.headers };
      for (const key of Object.keys(responseHeaders)) {
        if (["x-workbench-local-token", "authorization", "set-cookie"].includes(key.toLowerCase())) delete responseHeaders[key];
      }
      if (responseHeaders.location) {
        const redirect = new URL(responseHeaders.location, current.origin);
        if (redirect.origin !== current.origin) {
          response.resume();
          outgoing.writeHead(502).end("External redirects are unavailable in the isolated boundary.");
          return;
        }
        responseHeaders.location = redirect.pathname + redirect.search + redirect.hash;
      }
      outgoing.writeHead(response.statusCode ?? 502, responseHeaders);
      response.pipe(outgoing);
    });
    upstream.on("error", () => {
      if (loseResponse) return;
      if (!outgoing.headersSent) outgoing.writeHead(503, { "Content-Type": "application/json" });
      outgoing.end(JSON.stringify({ detail: "The isolated backend is restarting." }));
    });
    outgoing.once("close", () => { if (!loseResponse) upstream.destroy(); });
    incoming.pipe(upstream);
    // The original request continues to the actual admission owner. Only the
    // acknowledgement is lost; this boundary never issues an execution retry.
    if (loseResponse) incoming.once("end", () => outgoing.writeHead(503, { "Content-Type": "application/json" }).end(JSON.stringify({ error: "Baseline transport ended while admission was pending" })));
  });
  await new Promise<void>((resolve, reject) => {
    server.once("error", reject);
    server.listen(0, "127.0.0.1", resolve);
  });
  const address = server.address();
  if (!address || typeof address === "string") throw new Error("The isolated boundary has no loopback port.");
  return { server, origin: `http://127.0.0.1:${address.port}` };
}

export async function startBackend(options: { dataRoot?: string; scenario?: string; inference?: "deterministic" | "real" } = {}): Promise<BackendHandle> {
  const dataRoot = path.resolve(options.dataRoot ?? path.join(scratchRoot, `case-${randomUUID()}`));
  const relative = path.relative(path.join(repositoryRoot, ".scratch"), dataRoot);
  if (!relative || relative.startsWith("..") || path.isAbsolute(relative)) throw new Error("UI tests require a distinct data root inside repository .scratch.");
  requireDesktopTestScratchPath(repositoryRoot, dataRoot, "UI backend data root");
  await mkdir(dataRoot, { recursive: true });
  let child: ChildProcess | undefined;
  let origin = "";
  let token = "";
  let pid = 0;
  let closed = false;
  let startupFailure = "";
  const faults = { loseCommandResponse: false };
  const boundary = await startAuthBoundary(() => ({ origin, token }), faults);

  async function launch(): Promise<void> {
    const readyFile = path.join(dataRoot, "test-ready.json");
    requireDesktopTestScratchPath(repositoryRoot, readyFile, "UI backend readiness file");
    await rm(readyFile, { force: true });
    startupFailure = "";
    child = spawn("uv", ["run", "--no-sync", "--project", "apps/backend", "python", "-m", "tests_ui.server", "--data-root", dataRoot, "--port", "0", "--ready-file", readyFile, "--inference", options.inference ?? "deterministic"], {
      cwd: repositoryRoot, windowsHide: true, stdio: ["ignore", "pipe", "pipe"],
      env: { ...process.env, PYTHONPATH: path.join(repositoryRoot, "apps", "backend"), WORKBENCH_DATA_ROOT: dataRoot, PYTHONUTF8: "1" },
    });
    // Do not persist process logs: startup output may contain environment-specific paths.
    child.stdout?.resume();
    child.stderr?.on("data", data => { startupFailure = (startupFailure + String(data)).slice(-4000); });
    child.once("error", error => { startupFailure = error.message; });
    const ready = await waitUntil(async () => {
      if (child?.exitCode !== null && child?.exitCode !== undefined) throw new Error(`The isolated backend exited during startup (${child.exitCode}). ${startupFailure.replaceAll(token || "__no_secret__", "[redacted]")}`);
      try { return JSON.parse(await readFile(readyFile, "utf8")) as { origin?: string; backend_url?: string; pid: number; data_root: string }; }
      catch { return undefined; }
    }, options.inference === "real" ? 180_000 : 30_000);
    await rm(readyFile, { force: true });
    origin = ready.origin ?? ready.backend_url ?? "";
    const parsed = new URL(origin);
    if (parsed.protocol !== "http:" || parsed.hostname !== "127.0.0.1" || !parsed.port || parsed.pathname !== "/" || parsed.username || parsed.password || parsed.search || parsed.hash || !Number.isInteger(ready.pid) || ready.pid <= 0 || path.resolve(ready.data_root) !== dataRoot) throw new Error("The backend readiness identity is not the owned isolated fixture.");
    pid = ready.pid;
    token = (await readFile(path.join(dataRoot, "state", "desktop_backend_shared_secret"), "utf8")).trim();
    if (!token) throw new Error("The isolated backend has no local authentication secret.");
    await waitUntil(async () => {
      try { return (await fetch(origin + "/health", { signal: AbortSignal.timeout(1000) })).ok ? true : undefined; }
      catch { return undefined; }
    });
  }

  async function control<T>(route: string, body?: unknown): Promise<T> {
    if (!route.startsWith("/__test__/")) throw new Error("Fixture control calls must use the isolated control namespace.");
    const timeout = options.inference === "real" && route === "/__test__/seed" ? 180_000 : 15_000;
    const response = await fetch(origin + route, { method: body === undefined ? "GET" : "POST", headers: { [localTokenHeader]: token, "Content-Type": "application/json" }, ...(body === undefined ? {} : { body: JSON.stringify(body) }), signal: AbortSignal.timeout(timeout) });
    if (!response.ok) throw new Error(`Fixture control ${route} failed (${response.status}): ${(await response.text()).replaceAll(token, "[redacted]")}`);
    return await response.json() as T;
  }

  async function stop(): Promise<void> {
    const failures: unknown[] = [];
    if (origin && child && child.exitCode === null && child.signalCode === null) {
      try { await control("/__test__/scenario", { release_model: true, release_model_load: true, release_submit: true }); }
      catch (error) { failures.push(error); }
      try { await control("/__test__/shutdown", {}); }
      catch (error) { failures.push(error); }
      try { await waitUntil(async () => !child || child.exitCode !== null || child.signalCode !== null ? true : undefined, 15_000); }
      catch (error) {
        failures.push(error);
        try { await terminateOwnedProcess(child); } catch (cleanupError) { failures.push(cleanupError); }
      }
    } else {
      try { await terminateOwnedProcess(child); } catch (error) { failures.push(error); }
    }
    if (child && (child.exitCode !== 0 || child.signalCode !== null)) {
      failures.push(new Error(`The owned backend exited uncleanly (code ${child.exitCode}, signal ${child.signalCode ?? "none"}).`));
    }
    if (failures.length) throw new AggregateError(failures, "The isolated backend did not shut down cleanly.");
  }

  const handle: BackendHandle = {
    get origin() { return origin; }, get browserOrigin() { return boundary.origin; }, get dataRoot() { return dataRoot; }, get pid() { return pid; }, get token() { return token; },
    seed: {} as BackendSeed, control,
    loseNextCommandResponseBeforeAcceptance: () => { faults.loseCommandResponse = true; },
    state: <T = Record<string, unknown>>() => control<T>("/__test__/state"),
    restart: async () => { await stop(); origin = ""; await launch(); handle.seed = await control<BackendSeed>("/__test__/seed", { scenario: options.scenario ?? "baseline" }); },
    close: async () => {
      if (closed) return;
      closed = true;
      try { await stop(); }
      finally { boundary.server.closeAllConnections(); await new Promise<void>(resolve => boundary.server.close(() => resolve())); }
    },
  };
  try {
    await launch();
    handle.seed = await control<BackendSeed>("/__test__/seed", { scenario: options.scenario ?? "baseline" });
    return handle;
  } catch (error) {
    try { await handle.close(); }
    catch (cleanupError) { throw new AggregateError([error, cleanupError], "Isolated backend startup and cleanup failed."); }
    throw error;
  }
}
