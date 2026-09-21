import assert from "node:assert/strict";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { createServer as createViteServer } from "vite";

const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../..");
const desktopRoot = path.join(repoRoot, "apps/desktop");

const pending = {
  kind: "deepagents_interrupt_on",
  environment: "windows_host_shell",
  isolation: "none",
  action_requests: [{ name: "execute", args: { command: "echo ok" }, allowed_decisions: ["approve", "reject"] }],
};

function stream(run, interruptRunId = run?.id, interrupts = [{ id: "sdk-int", namespace: ["n"], value: pending }]) {
  return {
    values: {
      workbench: {
        run,
        interrupt_run_id: interruptRunId,
      },
    },
    interrupts,
  };
}

const vite = await createViteServer({ root: desktopRoot, appType: "custom", server: { middlewareMode: true }, logLevel: "error" });
try {
  const { visibleApprovalInterrupt } = await vite.ssrLoadModule("/src/renderer/InteractionStream.tsx");

  assert.equal(
    visibleApprovalInterrupt(stream({ id: "run-cancelled", status: "cancelled", pending_interrupt: null }), { id: "run-cancelled", status: "cancelled", pending_interrupt: null }),
    null,
    "terminal authoritative run must hide stale SDK interrupts",
  );
  assert.equal(
    visibleApprovalInterrupt(stream({ id: "run-live", status: "running", pending_interrupt: null }), { id: "run-live", status: "running", pending_interrupt: null }),
    null,
    "live authoritative run with cleared pending_interrupt must hide stale SDK interrupts",
  );
  assert.equal(
    visibleApprovalInterrupt(stream({ id: "run-current", status: "running", pending_interrupt: pending }, "run-other"), { id: "run-current", status: "running", pending_interrupt: pending }),
    null,
    "interrupts for a different workbench run must be hidden",
  );

  const initial = visibleApprovalInterrupt(stream(null, "run-later"), null);
  assert.equal(initial?.id, "sdk-int", "initial raw interrupt before authoritative run projection should remain visible");
  assert.deepEqual(initial?.namespace, ["n"]);
  assert.equal(initial?.pending.action_requests[0].name, "execute");

  const visible = visibleApprovalInterrupt(
    stream({ id: "run-current", status: "running", pending_interrupt: pending }, "run-current"),
    { id: "run-current", status: "running", pending_interrupt: pending },
  );
  assert.equal(visible?.id, "sdk-int", "authoritative pending interrupt should preserve actual SDK interrupt id");
  assert.deepEqual(visible?.namespace, ["n"], "authoritative pending interrupt should preserve actual SDK namespace");
  assert.equal(visible?.pending, pending, "presentation should use authoritative app pending_interrupt");
} finally {
  await vite.close();
}

console.log("Interrupt visibility checks passed.");
