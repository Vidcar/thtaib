import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

import ts from "typescript";

if (process.platform !== "win32") {
  console.log("Windows notification identity check skipped on non-Windows host.");
  process.exit(0);
}

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const desktopRoot = path.resolve(scriptDir, "..");
const repoRoot = path.resolve(desktopRoot, "../..");
const electronBin = path.join(desktopRoot, "node_modules/electron/dist/electron.exe");
assert.ok(existsSync(electronBin), `Electron binary not found at ${electronBin}`);

const scratch = path.join(repoRoot, ".scratch/windows-notification-identity");
const shortcutDir = path.join(scratch, "shortcuts");
const testIdentity = {
  appUserModelId: "com.vidcar.local-ai-workbench.test",
  toastActivatorClsid: "{F03484E2-B453-48AF-AC4A-B26A9651001C}",
};
mkdirSync(shortcutDir, { recursive: true });

const compiledIdentity = compileMainModule("windowsNotificationIdentity.ts");
const fixtureMain = path.join(scratch, "fixture-main.mjs");
writeFileSync(fixtureMain, fixtureSource(compiledIdentity, shortcutDir, testIdentity), "utf8");
writeFileSync(path.join(scratch, "package.json"), JSON.stringify({ type: "module", main: "fixture-main.mjs" }), "utf8");

const result = await runFixture();

assert.equal(result.constants.appUserModelId, testIdentity.appUserModelId);
assert.equal(result.constants.toastActivatorClsid, testIdentity.toastActivatorClsid);
assert.equal(result.shortcut.target, electronBin);
assert.equal(result.shortcut.args, `"${scratch}" --workbench-launch-backend`);
assert.equal(result.shortcut.cwd, scratch);
assert.equal(result.shortcut.description, "Local AI Workbench");
assert.equal(result.shortcut.appUserModelId, result.constants.appUserModelId);
assert.equal(result.shortcut.toastActivatorClsid, result.constants.toastActivatorClsid);
assert.equal(result.shortcutPath, path.join(shortcutDir, "Local AI Workbench.lnk"));

console.log("Windows notification identity fixture passed.");

function compileMainModule(relativePath) {
  const sourcePath = path.join(desktopRoot, "src/main", relativePath);
  const source = readFileSync(sourcePath, "utf8");
  const output = ts.transpileModule(source, {
    compilerOptions: {
      target: ts.ScriptTarget.ES2022,
      module: ts.ModuleKind.ES2022,
      moduleResolution: ts.ModuleResolutionKind.NodeNext,
      esModuleInterop: true,
      verbatimModuleSyntax: false,
    },
    fileName: sourcePath,
  }).outputText;
  const outPath = path.join(scratch, relativePath.replace(/\.ts$/, ".mjs"));
  writeFileSync(outPath, output, "utf8");
  return outPath;
}

function fixtureSource(identityPath, testShortcutDir, testIdentity) {
  const identityUrl = pathToFileURL(identityPath).toString();
  return `
import assert from "node:assert/strict";
import { app, shell } from "electron";
import {
  configureWindowsNotificationIdentity,
  ensureWindowsNotificationShortcut,
} from ${JSON.stringify(identityUrl)};

console.log("notification identity fixture boot");
app.commandLine.appendSwitch("disable-gpu");
app.on("window-all-closed", () => {});

const testIdentity = ${JSON.stringify(testIdentity)};
configureWindowsNotificationIdentity(testIdentity);
void app.whenReady().then(async () => {
  console.log("notification identity fixture ready");
  const result = await ensureWindowsNotificationShortcut(${JSON.stringify(testShortcutDir)}, testIdentity);
  assert.ok(result);
  const shortcut = shell.readShortcutLink(result.shortcutPath);
  console.log("WINDOWS_NOTIFICATION_IDENTITY_RESULT " + JSON.stringify({
    shortcutPath: result.shortcutPath,
    shortcut,
    constants: testIdentity,
  }));
  app.exit(0);
}).catch((error) => {
  console.error(error && error.stack ? error.stack : error);
  app.exit(1);
});
`;
}

async function runFixture() {
  const child = spawn(electronBin, [scratch], {
    cwd: scratch,
    env: {
      ...process.env,
      ELECTRON_DISABLE_SECURITY_WARNINGS: "true",
    },
    stdio: ["ignore", "pipe", "pipe"],
  });
  let stdout = "";
  let stderr = "";
  child.stdout.setEncoding("utf8");
  child.stderr.setEncoding("utf8");
  child.stdout.on("data", (chunk) => {
    stdout += chunk;
  });
  child.stderr.on("data", (chunk) => {
    stderr += chunk;
  });
  const timeout = setTimeout(() => {
    child.kill();
  }, 45000);
  const exitCode = await new Promise((resolve) => {
    child.on("exit", (code) => resolve(code));
  });
  clearTimeout(timeout);
  if (exitCode !== 0) {
    throw new Error(`Electron notification identity fixture failed with ${exitCode}\nSTDOUT:\n${stdout}\nSTDERR:\n${stderr}`);
  }
  const resultLine = stdout.trim().split(/\r?\n/).find((line) => line.startsWith("WINDOWS_NOTIFICATION_IDENTITY_RESULT "));
  assert.ok(resultLine, `Fixture did not report a result\nSTDOUT:\n${stdout}\nSTDERR:\n${stderr}`);
  return JSON.parse(resultLine.slice("WINDOWS_NOTIFICATION_IDENTITY_RESULT ".length));
}
