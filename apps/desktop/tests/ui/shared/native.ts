import { _electron, expect, type ElectronApplication, type Page, type TestInfo } from "@playwright/test";
import { createHash, randomUUID } from "node:crypto";
import { cp, mkdir, readFile, readdir, writeFile } from "node:fs/promises";
import { execFile } from "node:child_process";
import { promisify } from "node:util";
import { createRequire } from "node:module";
import path from "node:path";
import { repositoryRoot, startBackend, type BackendHandle } from "./backend";
import { requireDesktopTestScratchPath } from "../../../src/main/desktopTestIsolation";

const hash = async (file: string) => createHash("sha256").update(await readFile(file)).digest("hex");
async function treeHashes(root: string, relative = ""): Promise<Record<string, string>> {
  const result: Record<string, string> = {};
  for (const entry of await readdir(path.join(root, relative), { withFileTypes: true })) {
    expect(entry.isSymbolicLink()).toBe(false);
    const name = path.join(relative, entry.name);
    if (entry.isDirectory()) Object.assign(result, await treeHashes(root, name));
    else result[name] = await hash(path.join(root, name));
  }
  return result;
}

/** Actual built main/preload/renderer; the copied document changes only loopback CSP. */
export async function withNativeWorkbench(testInfo: TestInfo, inference: "deterministic" | "real", operation: (page: Page, backend: BackendHandle) => Promise<void>): Promise<void> {
  expect(process.platform).toBe("win32");
  const desktopRoot = path.join(repositoryRoot, "apps", "desktop");
  const electronExecutable = createRequire(import.meta.url)("electron") as string;
  const root = requireDesktopTestScratchPath(repositoryRoot, path.join(repositoryRoot, ".scratch", "ui-baseline", `sending-${randomUUID()}`), "Sending native fixture");
  const safePath = (name: string) => requireDesktopTestScratchPath(repositoryRoot, path.join(root, name), `Sending fixture ${name}`);
  const profile = safePath("profile"), temp = safePath("temporary"), appData = safePath("appdata"), localAppData = safePath("localappdata");
  await Promise.all([profile, temp, appData, localAppData].map(folder => mkdir(folder, { recursive: true })));
  const main = path.join(desktopRoot, "dist-electron", "main.js"), preload = path.join(desktopRoot, "dist-electron", "preload.js");
  const source = path.join(desktopRoot, "dist"), renderer = safePath("renderer"), document = path.join(renderer, "index.html");
  const before = { main: await hash(main), preload: await hash(preload), renderer: await treeHashes(source) };
  let backend: BackendHandle | undefined, desktop: ElectronApplication | undefined;
  try {
    backend = await startBackend({ dataRoot: safePath("data"), inference });
    await cp(source, renderer, { recursive: true, errorOnExist: true, force: false });
    const productionCsp = "connect-src 'self' http://127.0.0.1:8000 http://localhost:8000;";
    const original = await readFile(document, "utf8");
    expect(original.split(productionCsp)).toHaveLength(2);
    await writeFile(document, original.replace(productionCsp, `connect-src 'self' ${backend.origin};`));
    const copied = await treeHashes(renderer);
    for (const [file, digest] of Object.entries(before.renderer)) if (file !== "index.html") expect(copied[file]).toBe(digest);
    expect((await readFile(document, "utf8")).replace(`connect-src 'self' ${backend.origin};`, productionCsp)).toBe(original);
    const environment = Object.fromEntries(Object.entries({ ...process.env, ELECTRON_RUN_AS_NODE: undefined, VITE_DEV_SERVER_URL: undefined,
      WORKBENCH_DESKTOP_TEST_MODE: "isolated", WORKBENCH_TEST_BACKEND_ORIGIN: backend.origin, WORKBENCH_TEST_PROFILE_ROOT: profile,
      WORKBENCH_TEST_RENDERER_DOCUMENT: document, WORKBENCH_DATA_ROOT: backend.dataRoot, APPDATA: appData, LOCALAPPDATA: localAppData, TEMP: temp, TMP: temp,
    }).filter((entry): entry is [string, string] => entry[1] !== undefined));
    desktop = await _electron.launch({ executablePath: electronExecutable, args: [desktopRoot], cwd: desktopRoot, env: environment, timeout: 30_000 });
    const page = await desktop.firstWindow();
    await page.waitForLoadState("domcontentloaded");
    await expect(page.getByRole("button", { name: inference === "real" ? "Real model conversation" : "Baseline conversation", exact: true })).toBeVisible();
    const identity = await desktop.evaluate(({ app, BrowserWindow }) => {
      const window = BrowserWindow.getAllWindows()[0];
      const readPreferences = Reflect.get(window.webContents, "getLastWebPreferences") as () => Electron.WebPreferences;
      const preferences = readPreferences.call(window.webContents);
      const getPreload = Reflect.get(window.webContents, "_getPreloadScript") as () => { filePath: string };
      return { pid: process.pid, executable: process.execPath, appPath: app.getAppPath(), profile: app.getPath("userData"), preload: getPreload.call(window.webContents)?.filePath,
        sandbox: preferences.sandbox, contextIsolation: preferences.contextIsolation, nodeIntegration: preferences.nodeIntegration, document: window.webContents.getURL(), electronVersion: process.versions.electron };
    });
    expect(path.resolve(identity.executable)).toBe(path.resolve(electronExecutable));
    expect(path.resolve(identity.appPath)).toBe(desktopRoot);
    expect(path.resolve(identity.preload)).toBe(preload);
    expect(path.resolve(identity.profile)).toBe(profile);
    expect(identity.sandbox).toBe(true); expect(identity.contextIsolation).toBe(true); expect(identity.nodeIntegration).toBe(false);
    const bridge = await page.evaluate(async () => {
      const workbench = Reflect.get(window, "workbench");
      return { origin: workbench.backendUrl, authenticatedStatus: (await fetch(`${workbench.backendUrl}/v1/projects`)).status, secretVisible: Object.keys(workbench).some(name => /secret|token|credential/i.test(name)) };
    });
    expect(bridge.origin).toBe(backend.origin); expect(bridge.authenticatedStatus).toBe(200); expect(bridge.secretVisible).toBe(false);
    const launcherPid = desktop.process().pid;
    expect(launcherPid).toBeGreaterThan(0);
    const powershell = path.join(process.env.SystemRoot ?? "C:\\Windows", "System32", "WindowsPowerShell", "v1.0", "powershell.exe");
    const command = `$ids=@(${identity.pid},${launcherPid}); @($ids | ForEach-Object { $p=Get-CimInstance Win32_Process -Filter ('ProcessId='+$_); if (!$p) { throw 'Owned process exited' }; [pscustomobject]@{pid=[int]$p.ProcessId; parentPid=[int]$p.ParentProcessId; executable=$p.ExecutablePath; createdUtc=$p.CreationDate.ToUniversalTime().ToString('o')} }) | ConvertTo-Json -Compress`;
    const processChain = JSON.parse((await promisify(execFile)(powershell, ["-NoProfile", "-NonInteractive", "-Command", command], { windowsHide: true, timeout: 10_000, encoding: "utf8" })).stdout) as Array<{ pid: number; parentPid: number; executable: string }>;
    expect(processChain.find(item => item.pid === identity.pid)?.parentPid).toBe(launcherPid);
    await operation(page, backend);
    expect(await hash(main)).toBe(before.main); expect(await hash(preload)).toBe(before.preload); expect(await treeHashes(source)).toEqual(before.renderer);
    expect(await treeHashes(renderer)).toEqual(copied);
    const state = await backend.state();
    const safe = JSON.stringify({ identity, processChain, artifacts: before, copiedRenderer: copied, authenticatedStatus: bridge.authenticatedStatus, inference,
      backend: { pid: backend.pid, dataRoot: backend.dataRoot }, state, limit: "Unpackaged Windows application; copied document differs only in isolated backend connect-src" }, null, 2).replaceAll(backend.token, "[redacted]");
    await testInfo.attach("sending-native-identity-and-outcomes", { body: safe, contentType: "application/json" });
    await page.screenshot({ path: testInfo.outputPath("sending-native.png"), timeout: 5000 });
  } finally {
    try { await desktop?.close(); }
    finally { await backend?.close(); }
  }
}
