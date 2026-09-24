import assert from "node:assert/strict";
import path from "node:path";
import { fileURLToPath } from "node:url";

import React from "react";
import { act, create } from "react-test-renderer";
import { createServer as createViteServer } from "vite";

const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../..");
const desktopRoot = path.join(repoRoot, "apps/desktop");

globalThis.IS_REACT_ACT_ENVIRONMENT = true;

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

const vite = await createViteServer({ root: desktopRoot, appType: "custom", server: { middlewareMode: true, hmr: false }, logLevel: "error" });
try {
  const { visibleApprovalInterrupt } = await vite.ssrLoadModule("/src/renderer/InteractionStream.tsx");
  const { InterruptApproval } = await vite.ssrLoadModule("/src/renderer/InterruptApproval.tsx");

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

  const mixedPending = {
    ...pending,
    identity: "interrupt-a",
    action_requests: [
      { name: "execute", args: { command: "echo one" }, allowed_decisions: ["approve", "reject"] },
      { name: "write_file", args: { path: "report.md" }, allowed_decisions: ["approve", "reject"] },
    ],
  };
  const responses = [];
  let renderer;
  await act(async () => {
    renderer = create(React.createElement(InterruptApproval, { pending: mixedPending, onRespond: (payload) => responses.push(payload) }));
  });
  const inputs = renderer.root.findAll((node) => node.type === "input");
  const alwaysFirst = inputs.find((node) => node.props.name === "decision-0" && textOf(node.parent).includes("Always allow"));
  const rejectSecond = inputs.find((node) => node.props.name === "decision-1" && textOf(node.parent).includes("Reject"));
  await act(async () => {
    alwaysFirst.props.onChange();
    rejectSecond.props.onChange();
  });
  await act(async () => {
    button(renderer, "Send decisions").props.onClick();
  });
  assert.deepEqual(responses.at(-1), {
    decisions: [
      { type: "approve", scope: "always" },
      { type: "reject", scope: "once" },
    ],
  }, "approval response must preserve ordered per-action scopes");

  const nextPending = {
    ...pending,
    identity: "interrupt-b",
    action_requests: [{ name: "execute", args: { command: "echo next" }, allowed_decisions: ["approve", "reject"] }],
  };
  await act(async () => {
    renderer.update(React.createElement(InterruptApproval, { pending: nextPending, onRespond: (payload) => responses.push(payload) }));
  });
  await act(async () => {
    button(renderer, "Send decisions").props.onClick();
  });
  assert.deepEqual(responses.at(-1), { decisions: [{ type: "approve", scope: "once" }] }, "new interrupt must not keep stale decisions");

  const choicePending = {
    kind: "deepagents_interrupt_on",
    environment: "windows_host_shell",
    isolation: "none",
    note: "A user answer is required.",
    identity: "mixed-question",
    action_requests: [
      { name: "execute", args: { command: "echo before" }, allowed_decisions: ["approve", "reject"] },
      { name: "ask_user", args: {}, allowed_decisions: ["respond", "reject"], question: { prompt: "Pick one", answer_type: "choice", choices: ["alpha", "beta"] } },
      { name: "write_file", args: { path: "later.md" }, allowed_decisions: ["approve", "reject"] },
    ],
  };
  await act(async () => {
    renderer.update(React.createElement(InterruptApproval, { pending: choicePending, onRespond: (payload) => responses.push(payload) }));
  });
  assert.equal(button(renderer, "Send decisions").props.disabled, true, "a question needs a typed answer before the mixed batch can resume");
  const beta = renderer.root.findAll((node) => node.type === "input").find((node) => textOf(node.parent).includes("beta"));
  await act(async () => {
    beta.props.onChange();
  });
  await act(async () => {
    button(renderer, "Send decisions").props.onClick();
  });
  assert.deepEqual(responses.at(-1), { decisions: [
    { type: "approve", scope: "once" },
    { type: "respond", message: "beta" },
    { type: "approve", scope: "once" },
  ] }, "mixed question and approval decisions must preserve native action order");

  globalThis.window = { workbench: { selectPath: async () => "C:\\Temp\\chosen.txt" } };
  const filePending = {
    ...choicePending,
    identity: "file-question",
    action_requests: [{ name: "ask_user", args: {}, allowed_decisions: ["respond", "reject"], question: { prompt: "Choose file", answer_type: "file", choices: [] } }],
  };
  await act(async () => {
    renderer.update(React.createElement(InterruptApproval, { pending: filePending, onRespond: (payload) => responses.push(payload) }));
  });
  await act(async () => {
    await button(renderer, "Browse").props.onClick();
  });
  await act(async () => {
    button(renderer, "Send decisions").props.onClick();
  });
  assert.deepEqual(responses.at(-1), { decisions: [{ type: "respond", message: "C:\\Temp\\chosen.txt" }] }, "native file selection should become a typed respond decision");
  await act(async () => {
    renderer.root.findAll((node) => node.type === "input").find((node) => textOf(node.parent).includes("Cancel this question")).props.onChange({ target: { checked: true } });
  });
  await act(async () => {
    button(renderer, "Send decisions").props.onClick();
  });
  assert.deepEqual(responses.at(-1), { decisions: [{ type: "reject", scope: "once", message: "The user cancelled this question. Do not repeat it unless asked." }] }, "cancel question should reject its action explicitly");
} finally {
  await vite.close();
}

console.log("Interrupt visibility checks passed.");

function textOf(value) {
  if (value == null || typeof value === "boolean") {
    return "";
  }
  if (typeof value === "string" || typeof value === "number") {
    return String(value);
  }
  if (Array.isArray(value)) {
    return value.map(textOf).join("");
  }
  if (value.children) {
    return textOf(value.children);
  }
  return "";
}

function button(renderer, label) {
  const found = renderer.root.findAll((node) => node.type === "button" && textOf(node).includes(label));
  assert.ok(found.length > 0, `expected button ${label}`);
  return found[0];
}
