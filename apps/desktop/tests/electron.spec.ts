import { _electron, expect, test, type ElectronApplication } from "@playwright/test";
import { createHash, randomUUID } from "node:crypto";
import { cp, mkdir, readFile, readdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import { execFile } from "node:child_process";
import { promisify } from "node:util";
import { repositoryRoot, startBackend, type BackendHandle } from "./ui/shared/backend";
import { requireDesktopTestScratchPath } from "../src/main/desktopTestIsolation";

interface NativeBridge {
  backendUrl: string;
  productName: string;
  selectPath(kind: "file" | "folder"): Promise<string | null>;
  readAppearance(): Promise<unknown>;
  writeAppearance(value: unknown): Promise<unknown>;
}

const artifactHash = async (file: string) => createHash("sha256").update(await readFile(file)).digest("hex");
const productionConnectSource = "connect-src 'self' http://127.0.0.1:8000 http://localhost:8000;";
interface WindowsProcessIdentity { pid: number; parentPid: number; executable: string; commandLine: string; createdUtc: string }
async function windowsLaunchIdentities(mainPid: number, launcherPid: number): Promise<WindowsProcessIdentity[]> {
  if (![mainPid, launcherPid].every(pid => Number.isSafeInteger(pid) && pid > 0)) throw new Error("Native identity requires actual positive process IDs.");
  const command = `$ids = @(${mainPid}, ${launcherPid}); $items = @($ids | ForEach-Object { $item = Get-CimInstance Win32_Process -Filter ('ProcessId=' + $_); if (!$item) { throw 'An identified native process has exited' }; [pscustomobject]@{ pid = [int]$item.ProcessId; parentPid = [int]$item.ParentProcessId; executable = $item.ExecutablePath; commandLine = $item.CommandLine; createdUtc = $item.CreationDate.ToUniversalTime().ToString('o') } }); ConvertTo-Json -InputObject $items -Compress`;
  const powershell = path.join(process.env.SystemRoot ?? "C:\\Windows", "System32", "WindowsPowerShell", "v1.0", "powershell.exe");
  const { stdout } = await promisify(execFile)(powershell, ["-NoProfile", "-NonInteractive", "-Command", command], { windowsHide: true, timeout: 10_000, encoding: "utf8" });
  return JSON.parse(stdout) as WindowsProcessIdentity[];
}
async function rendererHashes(root: string, relative = ""): Promise<Record<string, string>> {
  const hashes: Record<string, string> = {};
  for (const entry of await readdir(path.join(root, relative), { withFileTypes: true })) {
    expect(entry.isSymbolicLink()).toBe(false);
    const name = path.join(relative, entry.name);
    if (entry.isDirectory()) Object.assign(hashes, await rendererHashes(root, name));
    else hashes[name] = await artifactHash(path.join(root, name));
  }
  return hashes;
}

test("actual Windows desktop uses isolated authenticated backend and native bridge", async ({}, testInfo) => {
  expect(process.platform).toBe("win32");
  const desktopRoot = path.join(repositoryRoot, "apps", "desktop");
  const electronExecutable = createRequire(import.meta.url)("electron") as string;
  // Node fixture writes must satisfy the same canonical guard before Electron is launched.
  const scratchTarget = (target: string, label: string) => requireDesktopTestScratchPath(repositoryRoot, target, label);
  const runtimeRoot = scratchTarget(path.join(repositoryRoot, ".scratch", "ui-baseline", `electron-${randomUUID()}`), "Native smoke runtime");
  const profileRoot = scratchTarget(path.join(runtimeRoot, "profile"), "Native smoke profile");
  const temporary = scratchTarget(path.join(runtimeRoot, "temp"), "Native smoke temporary directory");
  const appData = scratchTarget(path.join(runtimeRoot, "appdata"), "Native smoke APPDATA");
  const localAppData = scratchTarget(path.join(runtimeRoot, "localappdata"), "Native smoke LOCALAPPDATA");
  const dataRoot = scratchTarget(path.join(runtimeRoot, "data"), "Native smoke backend data");
  const rendererCopy = scratchTarget(path.join(runtimeRoot, "renderer"), "Native smoke renderer copy");
  const copiedDocument = scratchTarget(path.join(rendererCopy, "index.html"), "Native smoke copied document");
  await Promise.all([profileRoot, temporary, appData, localAppData].map(directory => mkdir(directory, { recursive: true })));
  const mainFile = path.join(desktopRoot, "dist-electron", "main.js");
  const preloadFile = path.join(desktopRoot, "dist-electron", "preload.js");
  const documentFile = path.join(desktopRoot, "dist", "index.html");
  const hashes = { main: await artifactHash(mainFile), preload: await artifactHash(preloadFile), document: await artifactHash(documentFile) };
  const builtRendererHashes = await rendererHashes(path.dirname(documentFile));
  let backend: BackendHandle | undefined;
  let desktop: ElectronApplication | undefined;
  try {
    backend = await startBackend({ dataRoot, scenario: "baseline" });
    await cp(path.dirname(documentFile), rendererCopy, { recursive: true, errorOnExist: true, force: false });
    const originalDocument = await readFile(documentFile, "utf8");
    expect(originalDocument.split(productionConnectSource)).toHaveLength(2);
    await writeFile(copiedDocument, originalDocument.replace(productionConnectSource, `connect-src 'self' ${backend.origin};`));
    const copiedRendererHashes = await rendererHashes(rendererCopy);
    expect(Object.keys(copiedRendererHashes).sort()).toEqual(Object.keys(builtRendererHashes).sort());
    for (const [file, hash] of Object.entries(builtRendererHashes)) {
      if (file !== "index.html") expect(copiedRendererHashes[file]).toBe(hash);
    }
    expect((await readFile(copiedDocument, "utf8")).replace(`connect-src 'self' ${backend.origin};`, productionConnectSource)).toBe(originalDocument);
    expect(backend.origin).not.toBe("http://127.0.0.1:8000");
    const unauthenticated = await fetch(`${backend.origin}/v1/projects`);
    expect(unauthenticated.status).toBe(401);
    const invalidAuthentication = await fetch(`${backend.origin}/v1/projects`, { headers: { "X-Workbench-Local-Token": "invalid-fixture-token" } });
    expect(invalidAuthentication.status).toBe(403);
    const environment = Object.fromEntries(Object.entries({
      ...process.env,
      ELECTRON_RUN_AS_NODE: undefined,
      VITE_DEV_SERVER_URL: undefined,
      WORKBENCH_DESKTOP_TEST_MODE: "isolated",
      WORKBENCH_TEST_BACKEND_ORIGIN: backend.origin,
      WORKBENCH_TEST_PROFILE_ROOT: profileRoot,
      WORKBENCH_TEST_RENDERER_DOCUMENT: copiedDocument,
      WORKBENCH_DATA_ROOT: backend.dataRoot,
      APPDATA: appData,
      LOCALAPPDATA: localAppData,
      TEMP: temporary,
      TMP: temporary,
    }).filter((entry): entry is [string, string] => entry[1] !== undefined));
    const launchedAt = Date.now();
    desktop = await _electron.launch({ executablePath: electronExecutable, args: [desktopRoot], cwd: desktopRoot, env: environment, timeout: 30_000 });
    const productionRequestsAfterObserver: string[] = [];
    desktop.context().on("request", request => { if (new URL(request.url()).origin === "http://127.0.0.1:8000") productionRequestsAfterObserver.push(request.url()); });
    const page = await desktop.firstWindow();
    await page.waitForLoadState("domcontentloaded");
    await expect.poll(() => page.evaluate(() => Reflect.get(window, "workbench")?.productName)).toBe("Local AI Workbench");
    expect(new URL(page.url()).protocol).toBe("file:");
    expect(fileURLToPath(page.url())).toBe(copiedDocument);
    const browserFacts = await page.evaluate(async () => {
      const bridge = Reflect.get(window, "workbench") as NativeBridge;
      const response = await fetch(`${bridge.backendUrl}/v1/projects`);
      return { backendUrl: bridge.backendUrl, status: response.status, projects: await response.json(), hasNode: typeof Reflect.get(window, "require") !== "undefined", bridgeNames: Object.keys(bridge) };
    });
    expect(browserFacts.backendUrl).toBe(backend.origin);
    expect(browserFacts.status).toBe(200);
    expect(browserFacts.projects).toEqual(expect.arrayContaining([expect.objectContaining({ id: backend.seed.project_id })]));
    await page.getByRole("button", { name: "Baseline conversation", exact: true }).click();
    await expect(page.getByText("Saved baseline answer", { exact: true })).toBeVisible();
    expect(browserFacts.hasNode).toBe(false);
    expect(browserFacts.bridgeNames.some(name => /secret|token|credential/i.test(name))).toBe(false);
    const identity = await desktop.evaluate(({ app, BrowserWindow }) => {
      const window = BrowserWindow.getAllWindows().find(candidate => candidate.getTitle() === "Local AI Workbench");
      if (!window) throw new Error("The actual application window was not created.");
      const readPreferences = Reflect.get(window.webContents, "getLastWebPreferences") as (() => Electron.WebPreferences) | undefined;
      if (typeof readPreferences !== "function") throw new Error("Electron did not provide the actual window preferences for identity verification.");
      const preferences = readPreferences.call(window.webContents);
      // Electron 44 omits preload from getLastWebPreferences; its native getter retains the actual path.
      const readPreload = Reflect.get(window.webContents, "_getPreloadScript") as (() => Electron.PreloadScript | null) | undefined;
      if (typeof readPreload !== "function") throw new Error("Electron did not provide its actual window preload identity.");
      const preloadScript = readPreload.call(window.webContents);
      const rendererPid = window.webContents.getOSProcessId();
      const renderer = app.getAppMetrics().find(metric => metric.pid === rendererPid);
      return { pid: process.pid, executable: process.execPath, electronVersion: process.versions.electron, appPath: app.getAppPath(), profile: app.getPath("userData"), sessionData: app.getPath("sessionData"), rendererPid, rendererSandboxed: renderer?.sandboxed, rendererMetrics: renderer, preferences, registeredPreloadScripts: window.webContents.session.getPreloadScripts(), preloadScript, preload: preloadScript?.filePath, sandbox: preferences.sandbox, contextIsolation: preferences.contextIsolation, nodeIntegration: preferences.nodeIntegration, document: window.webContents.getURL() };
    });
    await testInfo.attach("native-window-preferences", { contentType: "application/json", body: Buffer.from(JSON.stringify(identity, null, 2)) });
    const launcherPid = desktop.process().pid;
    if (!launcherPid) throw new Error("Playwright did not report its Windows launcher process.");
    // Playwright 1.62.1 launches Electron through shell=true on Windows; process() owns that shell.
    const launchIdentities = await windowsLaunchIdentities(identity.pid, launcherPid);
    await testInfo.attach("native-process-chain", { contentType: "application/json", body: Buffer.from(JSON.stringify({ launchedAt, launchIdentities }, null, 2)) });
    const mainIdentity = launchIdentities.find(item => item.pid === identity.pid);
    const launcherIdentity = launchIdentities.find(item => item.pid === launcherPid);
    expect(mainIdentity).toBeDefined();
    expect(launcherIdentity).toBeDefined();
    expect(mainIdentity!.parentPid).toBe(launcherPid);
    expect(path.resolve(mainIdentity!.executable)).toBe(path.resolve(electronExecutable));
    expect(path.resolve(launcherIdentity!.executable).toLowerCase()).toBe(path.resolve(process.env.ComSpec ?? path.join(process.env.SystemRoot ?? "C:\\Windows", "System32", "cmd.exe")).toLowerCase());
    expect(mainIdentity!.commandLine.toLowerCase()).toContain(desktopRoot.toLowerCase());
    expect(launcherIdentity!.commandLine.toLowerCase()).toContain(electronExecutable.toLowerCase());
    expect(launcherIdentity!.commandLine.toLowerCase()).toContain(desktopRoot.toLowerCase());
    expect(Date.parse(mainIdentity!.createdUtc)).toBeGreaterThanOrEqual(Date.parse(launcherIdentity!.createdUtc));
    expect(Date.parse(launcherIdentity!.createdUtc)).toBeGreaterThanOrEqual(launchedAt - 1000);
    expect(path.resolve(identity.executable)).toBe(path.resolve(electronExecutable));
    expect(path.resolve(identity.appPath)).toBe(desktopRoot);
    expect(path.resolve(identity.profile)).toBe(profileRoot);
    expect(path.resolve(identity.sessionData)).toBe(path.join(profileRoot, "sessions"));
    expect(identity.preloadScript?.type).toBe("frame");
    expect(path.resolve(identity.preload!)).toBe(preloadFile);
    expect(identity.sandbox).toBe(true);
    expect(identity.rendererSandboxed).toBe(true);
    expect(identity.contextIsolation).toBe(true);
    expect(identity.nodeIntegration).toBe(false);
    const processRecord = JSON.parse(await readFile(path.join(backend.dataRoot, "state", "desktop-process.json"), "utf8"));
    expect(processRecord.pid).toBe(identity.pid);
    const appearance = { version: 1, values: { "font-ui": "15px" }, light: {} };
    const appearanceResult = await page.evaluate(async value => {
      const bridge = Reflect.get(window, "workbench") as NativeBridge;
      await bridge.writeAppearance(value);
      return await bridge.readAppearance();
    }, appearance);
    expect(appearanceResult).toEqual(appearance);
    expect(JSON.parse(await readFile(path.join(backend.dataRoot, "appearance.json"), "utf8"))).toEqual(appearance);
    // Exercise the shipped IPC operation; replace only its OS dialog in this smoke.
    await desktop.evaluate(({ dialog }, selectedPath) => {
      dialog.showOpenDialog = async () => ({ canceled: false, filePaths: [selectedPath] });
    }, runtimeRoot);
    expect(await page.evaluate(() => (Reflect.get(window, "workbench") as NativeBridge).selectPath("folder"))).toBe(runtimeRoot);
    expect(productionRequestsAfterObserver).toEqual([]);
    expect(await artifactHash(mainFile)).toBe(hashes.main);
    expect(await artifactHash(preloadFile)).toBe(hashes.preload);
    expect(await artifactHash(documentFile)).toBe(hashes.document);
    expect(await rendererHashes(rendererCopy)).toEqual(copiedRendererHashes);
    expect(await rendererHashes(path.dirname(documentFile))).toEqual(builtRendererHashes);
    const screenshot = testInfo.outputPath("actual-desktop.png");
    await page.screenshot({ path: screenshot });
    await testInfo.attach("actual-desktop", { contentType: "image/png", path: screenshot });
    await testInfo.attach("native-identity", { contentType: "application/json", body: Buffer.from(JSON.stringify({ identity, launchIdentities, artifacts: { mainFile, preloadFile, documentFile, hashes, copiedDocument, builtRendererHashes, copiedRendererHashes, documentChange: "Only connect-src uses the owned isolated backend origin" }, backend: { origin: backend.origin, pid: backend.pid, dataRoot: backend.dataRoot }, authenticatedStatus: browserFacts.status, nativeBridge: ["appearance-write", "appearance-read", "select-path"], requestObservation: "Context requests after observer installation; startup absence established only by isolation source guards", productionRequestsAfterObserver }, null, 2)) });
  } finally {
    try { await desktop?.close(); }
    finally { await backend?.close(); }
  }
});
