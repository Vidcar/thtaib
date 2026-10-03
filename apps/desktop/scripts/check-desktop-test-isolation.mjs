import assert from "node:assert/strict";
import { cpSync, mkdirSync, mkdtempSync, readFileSync, symlinkSync, unlinkSync, writeFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import ts from "typescript";

const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../..");
const scratch = path.join(repoRoot, ".scratch");
mkdirSync(scratch, { recursive: true });
const runRoot = mkdtempSync(path.join(scratch, "desktop-test-isolation-"));
const sourcePath = path.join(repoRoot, "apps/desktop/src/main/desktopTestIsolation.ts");
const compiledPath = path.join(runRoot, "desktopTestIsolation.mjs");
writeFileSync(compiledPath, ts.transpileModule(readFileSync(sourcePath, "utf8"), {
  compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ES2022 },
}).outputText);
const { resolveDesktopTestIsolation, requireDesktopTestScratchPath, PRODUCTION_CONNECT_SOURCE } = await import(pathToFileURL(compiledPath).href);
const fixtureScratch = runRoot;
const originalRenderer = path.join(runRoot, "original-renderer");
const copiedRenderer = path.join(runRoot, "renderer");
mkdirSync(path.join(originalRenderer, "assets"), { recursive: true });
mkdirSync(fixtureScratch, { recursive: true });
const originalDocument = `<html><meta http-equiv="Content-Security-Policy" content="${PRODUCTION_CONNECT_SOURCE}"><script src="./assets/application.js"></script></html>`;
writeFileSync(path.join(originalRenderer, "index.html"), originalDocument);
writeFileSync(path.join(originalRenderer, "assets", "application.js"), "console.log('current compiled application');");
cpSync(originalRenderer, copiedRenderer, { recursive: true });
const copiedDocument = path.join(copiedRenderer, "index.html");
const resolveFixtureIsolation = (environ, packaged = false) => resolveDesktopTestIsolation(repoRoot, environ, packaged, originalRenderer);
writeFileSync(copiedDocument, originalDocument.replace(PRODUCTION_CONNECT_SOURCE, "connect-src 'self' http://127.0.0.1:49152;"));
const isolated = {
  WORKBENCH_DESKTOP_TEST_MODE: "isolated",
  WORKBENCH_TEST_BACKEND_ORIGIN: "http://127.0.0.1:49152",
  WORKBENCH_TEST_PROFILE_ROOT: path.join(fixtureScratch, "profile"),
  WORKBENCH_TEST_RENDERER_DOCUMENT: copiedDocument,
  WORKBENCH_DATA_ROOT: path.join(fixtureScratch, "data"),
  APPDATA: path.join(fixtureScratch, "appdata"),
  LOCALAPPDATA: path.join(fixtureScratch, "localappdata"),
  TEMP: path.join(fixtureScratch, "temp"),
  TMP: path.join(fixtureScratch, "temp"),
};
assert.equal(resolveFixtureIsolation({}), null, "ordinary launches preserve production defaults");
assert.deepEqual(resolveFixtureIsolation(isolated), {
  backendOrigin: isolated.WORKBENCH_TEST_BACKEND_ORIGIN,
  profileRoot: isolated.WORKBENCH_TEST_PROFILE_ROOT,
  rendererDocument: copiedDocument,
});
for (const origin of ["https://example.com", "http://localhost:49152", "http://127.0.0.1:8000", "http://127.0.0.1:0", "http://127.0.0.1:65536", "http://127.0.0.1:49152/", "http://127.0.0.1:49152?token=secret"]) {
  assert.throws(() => resolveFixtureIsolation({ ...isolated, WORKBENCH_TEST_BACKEND_ORIGIN: origin }), /loopback port/);
}
assert.throws(() => resolveFixtureIsolation(isolated, true), /unpackaged/);
assert.throws(() => resolveFixtureIsolation({ WORKBENCH_TEST_BACKEND_ORIGIN: isolated.WORKBENCH_TEST_BACKEND_ORIGIN }), /isolated launch/);
assert.throws(() => resolveFixtureIsolation({ WORKBENCH_TEST_RENDERER_DOCUMENT: copiedDocument }), /isolated launch/);
assert.throws(() => resolveFixtureIsolation({ ...isolated, WORKBENCH_DESKTOP_TEST_MODE: "yes" }), /isolated launch/);
for (const name of ["WORKBENCH_DATA_ROOT", "WORKBENCH_TEST_PROFILE_ROOT", "WORKBENCH_TEST_RENDERER_DOCUMENT", "APPDATA", "LOCALAPPDATA", "TEMP", "TMP"]) {
  assert.throws(() => resolveFixtureIsolation({ ...isolated, [name]: undefined }), /absolute checkout scratch path/);
  assert.throws(() => resolveFixtureIsolation({ ...isolated, [name]: repoRoot }), /root scratch/);
  assert.throws(() => resolveFixtureIsolation({ ...isolated, [name]: ".scratch/relative" }), /absolute checkout scratch path/);
}
writeFileSync(copiedDocument, originalDocument);
assert.throws(() => resolveFixtureIsolation(isolated), /only its owned backend CSP/);
writeFileSync(copiedDocument, originalDocument.replace(PRODUCTION_CONNECT_SOURCE, "connect-src 'self' http://127.0.0.1:49152;"));
writeFileSync(path.join(copiedRenderer, "assets", "application.js"), "console.log('changed application');");
assert.throws(() => resolveFixtureIsolation(isolated), /assets must match/);
cpSync(path.join(originalRenderer, "assets", "application.js"), path.join(copiedRenderer, "assets", "application.js"));
writeFileSync(path.join(copiedRenderer, "extra.js"), "extra code");
assert.throws(() => resolveFixtureIsolation(isolated), /exactly the current built assets/);
unlinkSync(path.join(copiedRenderer, "extra.js"));
assert.throws(() => requireDesktopTestScratchPath(repoRoot, scratch, "test"), /root scratch/);
const escaped = path.join(fixtureScratch, "outside-junction");
symlinkSync(repoRoot, escaped, process.platform === "win32" ? "junction" : "dir");
try {
  assert.throws(() => requireDesktopTestScratchPath(repoRoot, path.join(escaped, "README.md"), "test"), /resolves outside/);
} finally { unlinkSync(escaped); }
console.log("Desktop test isolation rejects unsafe origins/paths and accepts only copied build bytes with an isolated CSP.");
