import assert from "node:assert/strict";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

import ts from "typescript";

const desktopRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const sourcePath = path.join(desktopRoot, "src/main/backendCompatibility.ts");
const scratch = path.resolve(desktopRoot, "../../.scratch/backend-compatibility-check");
mkdirSync(scratch, { recursive: true });
const compiledPath = path.join(scratch, "backendCompatibility.mjs");
writeFileSync(compiledPath, ts.transpileModule(readFileSync(sourcePath, "utf8"), {
  compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ES2022 },
  fileName: sourcePath,
}).outputText, "utf8");

const { probeBackendCompatibility } = await import(pathToFileURL(compiledPath).toString());
const origin = "http://127.0.0.1:8000";
const token = "isolated-test-token";
const health = Response.json({ status: "ok", product: "Local AI Workbench" });
const currentTools = ["echo", "browser_take_screenshot", "desktop_screenshot", "start_preview"];

function serverWith(toolsResponse) {
  return async (url, options) => {
    if (url === `${origin}/health`) return health.clone();
    assert.equal(url, `${origin}/v1/agent-tools`);
    assert.equal(options.headers["X-Workbench-Local-Token"], token);
    return toolsResponse;
  };
}

assert.equal(await probeBackendCompatibility(origin, token,
  serverWith(Response.json({ enabled: currentTools }))), "compatible");
assert.equal(await probeBackendCompatibility(origin, token,
  serverWith(Response.json({ enabled: ["echo", "read_file"] }))), "incompatible");
assert.equal(await probeBackendCompatibility(origin, token,
  serverWith(new Response(null, { status: 404 }))), "incompatible");
assert.equal(await probeBackendCompatibility(origin, token,
  async () => { throw new Error("backend offline"); }), "unavailable");
console.log("Backend compatibility check passed.");
