import assert from "node:assert/strict";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

import ts from "typescript";

const desktopRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const sourcePath = path.join(desktopRoot, "src/main/desktopProcess.ts");
const scratch = path.resolve(desktopRoot, "../../.scratch/desktop-process-record-check");
mkdirSync(scratch, { recursive: true });
const compiledPath = path.join(scratch, "desktopProcess.mjs");
writeFileSync(compiledPath, ts.transpileModule(readFileSync(sourcePath, "utf8"), {
  compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ES2022 },
  fileName: sourcePath,
}).outputText, "utf8");

const { publishDesktopProcess, clearDesktopProcess, desktopProcessRecordPath } = await import(pathToFileURL(compiledPath).href);
const dataRoot = path.join(scratch, "data");
const recordPath = desktopProcessRecordPath(dataRoot);

publishDesktopProcess(dataRoot);
assert.deepEqual(JSON.parse(readFileSync(recordPath, "utf8")), { pid: process.pid });

clearDesktopProcess(dataRoot, process.pid + 1);
assert.equal(existsSync(recordPath), true, "a different process must leave the record in place");

clearDesktopProcess(dataRoot);
assert.equal(existsSync(recordPath), false);
clearDesktopProcess(dataRoot);

writeFileSync(recordPath, "{", "utf8");
clearDesktopProcess(dataRoot);
assert.equal(readFileSync(recordPath, "utf8"), "{");

const mainSource = readFileSync(path.join(desktopRoot, "src/main/main.ts"), "utf8");
const backgroundSource = readFileSync(path.join(desktopRoot, "src/main/background.ts"), "utf8");
assert.match(mainSource, /app\.on\("will-quit", \(\) => \{\s*clearDesktopProcess\(resolveProductDataRoot\(\)\);\s*\}\)/);
assert.equal(mainSource.includes("before-quit"), false);
assert.match(backgroundSource, /app\.on\("before-quit", \(event\) => \{ if \(!quitting\) \{ event\.preventDefault\(\); void requestQuit\(\); \} \}\)/);

console.log("Desktop process record check passed.");
