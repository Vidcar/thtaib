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
  interrupt_id: "sdk-int",
  namespace: ["n"],
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
  const { visibleApprovalInterrupt: realVisibleApprovalInterrupt } = await vite.ssrLoadModule("/src/renderer/InteractionStream.tsx");
  // This deliberately broken control recreates the former first-SDK-card join.
  // It must fail the same target/body assertions as the shipped projection.
  const visibleApprovalInterrupt = process.env.WORKBENCH_APPROVAL_CONTROL === "wrong-card"
    ? (stream, run) => {
      const correct = realVisibleApprovalInterrupt(stream, run);
      return correct ? { ...correct, id: stream.interrupts[0]?.id, namespace: stream.interrupts[0]?.namespace ?? [] } : null;
    }
    : realVisibleApprovalInterrupt;
  const { InterruptApproval } = await vite.ssrLoadModule("/src/renderer/InterruptApproval.tsx");
  const { helperApprovalOwner } = await vite.ssrLoadModule("/src/renderer/RunActivitySummary.tsx");

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
  const cancelling = { id: "run-cancelling", status: "cancel_requested", pending_interrupt: pending };
  assert.equal(visibleApprovalInterrupt(stream(cancelling), cancelling), null,
    "requested cancellation must hide actionable cards even while the SDK retains its old requests");
  assert.equal(
    visibleApprovalInterrupt(stream({ id: "run-current", status: "running", pending_interrupt: pending }, "run-other"), { id: "run-current", status: "running", pending_interrupt: pending }),
    null,
    "interrupts for a different workbench run must be hidden",
  );

  const initial = visibleApprovalInterrupt(stream(null, "run-later"), null);
  assert.equal(initial, null, "raw interrupts wait for an authoritative selected run before offering decisions");

  const visible = visibleApprovalInterrupt(
    stream({ id: "run-current", status: "running", pending_interrupt: pending }, "run-current"),
    { id: "run-current", status: "running", pending_interrupt: pending },
  );
  assert.equal(visible?.id, "sdk-int", "authoritative pending interrupt should preserve actual SDK interrupt id");
  assert.deepEqual(visible?.namespace, ["n"], "authoritative pending interrupt should preserve actual SDK namespace");
  assert.equal(visible?.pending, pending, "presentation should use authoritative app pending_interrupt");
  assert.equal(visible?.waitingCount, 1);

  const alpha = { ...pending, interrupt_id: "alpha-native", namespace: ["tools:alpha", "task:write"], identity: "alpha-native", action_requests: [{ name: "write_file", args: { path: "alpha.txt", content: "Alpha only", tool_call_id: "same-call" }, allowed_decisions: ["approve", "reject"] }] };
  const beta = { ...alpha, interrupt_id: "beta-native", namespace: ["tools:beta", "task:write"], identity: "beta-native", action_requests: [{ ...alpha.action_requests[0], args: { path: "beta.txt", content: "Beta only", tool_call_id: "same-call" } }] };
  const alphaSDK = { id: alpha.interrupt_id, namespace: alpha.namespace, value: alpha };
  const betaSDK = { id: beta.interrupt_id, namespace: beta.namespace, value: beta };
  const parallelRun = { id: "parallel-run", status: "running", pending_interrupt: alpha, child_runs: [
    { name: "Alpha", namespace: ["tools:alpha"] }, { name: "Beta", namespace: ["tools:beta"] },
  ] };
  for (const selectedPending of [alpha, beta]) for (const order of [[betaSDK, alphaSDK], [alphaSDK, betaSDK]]) {
    const selectedRun = { ...parallelRun, pending_interrupt: selectedPending };
    const selected = visibleApprovalInterrupt(stream(selectedRun, selectedRun.id, order), selectedRun);
    assert.equal(selected?.id, selectedPending.interrupt_id, "wrong-card control: SDK order must never choose a different helper target");
    assert.deepEqual(selected?.namespace, selectedPending.namespace);
    assert.equal(selected?.pending.action_requests[0].args.path, selectedPending.action_requests[0].args.path, "body belongs to the exact selected native target");
    assert.equal(selected?.waitingCount, 2, "all actionable pending helpers count, independent of SDK order");
    assert.equal(helperApprovalOwner(selectedRun, selected.namespace), selectedPending === alpha ? "Alpha" : "Beta", "selected card names its exact helper");
  }
  assert.equal(visibleApprovalInterrupt(stream(parallelRun, parallelRun.id, [{ ...alphaSDK, namespace: undefined, ns: alpha.namespace }, betaSDK]), parallelRun)?.id, alpha.interrupt_id, "legacy native ns tuple is matched exactly too");
  for (const [label, sdk] of [
    ["wrong namespace", { ...alphaSDK, namespace: beta.namespace }],
    ["namespace prefix", { ...alphaSDK, namespace: ["tools:alpha"] }],
    ["namespace suffix", { ...alphaSDK, namespace: [...alpha.namespace, "deeper"] }],
    ["stale identity", { ...alphaSDK, id: "stale-alpha" }],
  ]) assert.equal(visibleApprovalInterrupt(stream(parallelRun, parallelRun.id, [sdk, betaSDK]), parallelRun), null, `${label} cannot display or target another request`);
  assert.equal(visibleApprovalInterrupt(stream(parallelRun, parallelRun.id, [alphaSDK, alphaSDK]), parallelRun), null, "ambiguous duplicate native identities cannot display an actionable card");
  assert.equal(visibleApprovalInterrupt(stream(parallelRun, parallelRun.id, [alphaSDK]), { ...parallelRun, pending_interrupt: { ...alpha, interrupt_id: undefined } }), null, "an unidentified selected record cannot borrow an SDK target");
  assert.equal(visibleApprovalInterrupt(stream({ ...parallelRun, id: "earlier-run" }, parallelRun.id, [alphaSDK]), parallelRun), null, "projected run ownership must agree with selected run ownership");
  const browserPending = { ...pending, kind: "browser_control" };
  assert.equal(visibleApprovalInterrupt(stream(parallelRun, parallelRun.id, [{ id: "browser", namespace: [], value: browserPending }, alphaSDK, betaSDK]), parallelRun)?.waitingCount, 2, "browser takeover remains with its existing owner and does not inflate action counts");

  const helperResponses = [];
  let helperRenderer;
  const renderHelperCard = (selectedRun, sdkInterrupts, busy = false) => {
    const selected = visibleApprovalInterrupt(stream(selectedRun, selectedRun.id, sdkInterrupts), selectedRun);
    return selected ? React.createElement(InterruptApproval, {
      key: JSON.stringify([selectedRun.id, selected.id, selected.namespace]), pending: selected.pending,
      ownerLabel: helperApprovalOwner(selectedRun, selected.namespace), waitingCount: selected.waitingCount, busy,
      onRespond: payload => helperResponses.push({ interrupt_id: selected.id, namespace: selected.namespace, response: payload }),
    }) : null;
  };
  await act(async () => { helperRenderer = create(renderHelperCard(parallelRun, [betaSDK, alphaSDK])); });
  assert.match(textOf(helperRenderer.root), /Review requested actions · Alpha/);
  assert.match(textOf(helperRenderer.root), /2 requests waiting/);
  assert.match(textOf(helperRenderer.root), /alpha.txt/);
  assert.doesNotMatch(textOf(helperRenderer.root), /beta.txt/);
  await act(async () => button(helperRenderer, "Send decisions").props.onClick());
  assert.deepEqual(helperResponses.at(-1), { interrupt_id: alpha.interrupt_id, namespace: alpha.namespace, response: { decisions: [{ type: "approve", scope: "once" }] } });
  // A pending command keeps the other helper's decision unavailable. Only a
  // confirmed run selection advances to the remaining card, including after remount.
  await act(async () => helperRenderer.update(renderHelperCard(parallelRun, [alphaSDK, betaSDK], true)));
  assert.equal(button(helperRenderer, "Send decisions").props.disabled, true);
  assert.match(textOf(helperRenderer.root), /Review requested actions · Alpha/);
  const betaRun = { ...parallelRun, pending_interrupt: beta };
  await act(async () => helperRenderer.update(renderHelperCard(betaRun, [betaSDK])));
  assert.match(textOf(helperRenderer.root), /Review requested actions · Beta/);
  assert.match(textOf(helperRenderer.root), /1 request waiting/);
  assert.doesNotMatch(textOf(helperRenderer.root), /alpha.txt/);
  await act(async () => helperRenderer.unmount());
  await act(async () => { helperRenderer = create(renderHelperCard(betaRun, [betaSDK])); });
  assert.equal(helperResponses.length, 1, "reconnect remount observes the selected card without submitting");
  const rejectBeta = helperRenderer.root.findAll(node => node.type === "input").find(node => textOf(node.parent).includes("Reject"));
  await act(async () => rejectBeta.props.onChange());
  await act(async () => button(helperRenderer, "Send decisions").props.onClick());
  assert.deepEqual(helperResponses.at(-1), { interrupt_id: beta.interrupt_id, namespace: beta.namespace, response: { decisions: [{ type: "reject", scope: "once" }] } });
  await act(async () => helperRenderer.update(renderHelperCard({ ...betaRun, status: "completed", pending_interrupt: null }, [alphaSDK, betaSDK])));
  assert.equal(helperRenderer.toJSON(), null, "completed runs never reopen replayed pending cards");
  await act(async () => helperRenderer.unmount());

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
  const betaChoice = renderer.root.findAll((node) => node.type === "input").find((node) => textOf(node.parent).includes("beta"));
  await act(async () => {
    betaChoice.props.onChange();
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

  const setup = { version: 1, capability: "browser", id: "browser-install", tool_names: ["browser_navigate"], code: "browser_worker_missing", message: "Install the Browser worker in Settings.", action: "Set up Browser", target: "settings", target_id: null, requires_new_input: false };
  const setupPending = { ...pending, kind: "capability_setup", environment: "capability_setup", identity: "saved-setup-checkpoint", interrupt_id: "native-setup-id", namespace: ["helper", "tools"], action_requests: [{ name: "capability_setup", args: {}, allowed_decisions: ["respond", "reject"], setup }] };
  const setupRun = { id: "setup-run", status: "running", pending_interrupt: setupPending };
  const setupVisible = visibleApprovalInterrupt(stream(setupRun, setupRun.id, [{ id: "native-setup-id", namespace: ["helper", "tools"], value: setupPending }]), setupRun);
  assert.equal(setupVisible.id, "native-setup-id");
  assert.deepEqual(setupVisible.namespace, ["helper", "tools"], "setup cards preserve their native saved invocation target");
  assert.equal(visibleApprovalInterrupt(stream({ ...setupRun, status: "cancelled", pending_interrupt: null }, setupRun.id, [{ id: "native-setup-id", value: setupPending }]), { ...setupRun, status: "cancelled", pending_interrupt: null }), null, "a cancelled setup cannot render a stale Continue action");
  const configured = [];
  await act(async () => renderer.update(React.createElement(InterruptApproval, { pending: setupPending, onRespond: payload => responses.push(payload), onConfigureSetup: request => configured.push(request) })));
  assert.equal(textOf(renderer.root).includes("Always allow"), false, "capability setup does not duplicate permissions");
  const beforeSetup = responses.length;
  await act(async () => button(renderer, "Configure").props.onClick());
  assert.deepEqual(configured, [setup]); assert.equal(responses.length, beforeSetup, "Configure navigates without resuming saved work");
  await act(async () => button(renderer, "Continue saved work").props.onClick());
  assert.deepEqual(responses.at(-1), { decisions: [{ type: "respond", message: "continue", scope: "once" }] });
  const changedSetup = { ...setupPending, identity: "changed-capability", action_requests: [{ ...setupPending.action_requests[0], setup: { ...setup, requires_new_input: true } }] };
  await act(async () => renderer.update(React.createElement(InterruptApproval, { pending: changedSetup, onRespond: payload => responses.push(payload), onConfigureSetup: request => configured.push(request) })));
  assert.equal(button(renderer, "Continue saved work").props.disabled, true, "changed frozen choices require a newly accepted message");
  await act(async () => button(renderer, "Skip this step").props.onClick());
  assert.equal(responses.at(-1).decisions[0].type, "reject");
  await act(async () => renderer.unmount());
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
