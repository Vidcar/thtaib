import assert from "node:assert/strict";
import { mkdir, access, symlink, unlink, writeFile } from "node:fs/promises";
import path from "node:path";
import { randomUUID } from "node:crypto";
import { startBackend, repositoryRoot } from "./backend.ts";
import { requireDesktopTestScratchPath } from "../../../src/main/desktopTestIsolation.ts";

const runRoot = requireDesktopTestScratchPath(repositoryRoot, path.join(repositoryRoot, ".scratch", "ui-baseline", `helper-safety-${randomUUID()}`), "Fixture safety evidence");
await mkdir(runRoot, { recursive: true });
const exists = target => access(target).then(() => true, () => false);
const link = path.join(runRoot, "outside-junction");
const refusedName = `fixture-must-not-write-${randomUUID()}`;
const wouldEscape = path.join(repositoryRoot, refusedName);
await symlink(repositoryRoot, link, process.platform === "win32" ? "junction" : "dir");
try {
  assert.equal(await exists(wouldEscape), false);
  await assert.rejects(startBackend({ dataRoot: path.join(link, refusedName) }), /resolves outside/);
  assert.equal(await exists(wouldEscape), false, "canonical refusal must occur before Node creates a directory");
} finally {
  await unlink(link);
}

const backend = await startBackend({ dataRoot: path.join(runRoot, "shutdown-data") });
const before = await backend.state();
await backend.control("/__test__/scenario", { fail_shutdown: true });
let closed = false;
try {
  await assert.rejects(async () => {
    try { await backend.close(); }
    finally { closed = true; }
  }, error => error instanceof AggregateError && error.errors.some(cause => String(cause).includes("Baseline native shutdown failed")), "native cleanup failures must reach the caller after cleanup attempts");
} finally {
  if (!closed) await backend.close();
}
await assert.rejects(fetch(backend.origin + "/health", { signal: AbortSignal.timeout(1000) }), undefined, "the failed shutdown must still stop its actual backend listener");
const evidence = { canonical_junction_refused_before_write: true, failed_native_shutdown_reported: true, owned_listener_stopped: true, before_shutdown: before, data_root: backend.dataRoot };
await writeFile(path.join(runRoot, "report.json"), JSON.stringify(evidence, null, 2));
process.stdout.write(`Fixture safety negative controls passed. Evidence: ${path.join(runRoot, "report.json")}\n`);
