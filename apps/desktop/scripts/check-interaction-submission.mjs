import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import React, { useEffect, useRef, useState } from "react";
import { act, create } from "react-test-renderer";
import { createServer } from "vite";

const desktopRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const negative = process.env.INTERACTION_SUBMISSION_NEGATIVE;
globalThis.IS_REACT_ACT_ENVIRONMENT = true;
globalThis.window = { workbench: { backendUrl: "http://127.0.0.1:9" } };
const originalConsoleError = console.error;
console.error = (...args) => {
  if (String(args[0]).startsWith("react-test-renderer is deprecated") || String(args[0]).startsWith("An update to ")) return;
  originalConsoleError(...args);
};
const vite = await createServer({ root: desktopRoot, appType: "custom", server: { middlewareMode: true, hmr: false }, logLevel: "error",
  plugins: negative ? [{ name: "submission-negative-control", enforce: "pre", load(id) {
    if (!id.replace(/\\/g, "/").endsWith("/src/renderer/interactionSubmission.tsx")) return null;
    const source = readFileSync(path.join(desktopRoot, "src/renderer/interactionSubmission.tsx"), "utf8");
    if (negative === "draft-loss") return source.replace("// submit resolves for some errors;", "latest.current.onAccepted(item.request.source, null as V);\n    // submit resolves for some errors;");
    if (negative === "stale-owner") return source.replace(/return mounted.current && record.current === item &&[^;]+;/, "return mounted.current;");
    throw new Error("Unknown negative control");
  } }] : [],
});

function deferred() { let resolve; const promise = new Promise(res => { resolve = res; }); return { promise, resolve }; }
function run(id = "input_original", status = "running") { return { id: "run_original", input_message_id: id, status, error: status === "failed" ? "Actual model failure" : null }; }
async function flush() { await act(async () => { await Promise.resolve(); }); }
async function waitFor(assertion, label) {
  const deadline = Date.now() + 3000;
  let last;
  while (Date.now() < deadline) {
    await flush();
    try { return assertion(); } catch (error) { last = error; await new Promise(resolve => setTimeout(resolve, 5)); }
  }
  throw new Error(`${label}: ${last?.message}`);
}

try {
  const { useInteractionSubmission, SubmissionRecoveryNotice } = await vite.ssrLoadModule("/src/renderer/interactionSubmission.tsx");
  const { InteractionCommandError, createResumingInteractionTransport } = await vite.ssrLoadModule("/src/renderer/interactionResume.ts");
  const commandError = (status = 503, code = "unknown_error") => new InteractionCommandError("Acknowledgement interrupted", status, code, "command_1", "input_original", "thread_original");

  async function fixture(spec = {}) {
    const state = { sent: [], reads: 0, accepted: 0, rejected: 0, failures: [], observations: 0, view: null,
      read: async () => state.view, send: (_input, options) => { options.onError?.(commandError()); }, controller: null };
    Object.assign(state, spec);
    const stream = { threadId: "thread_original", submit: async (input, options) => {
      state.sent.push(structuredClone({ input, metadata: options.metadata }));
      state.lastError = options.onError;
      state.send(input, options);
    } };
    function Harness() {
      const [owner, setOwner] = useState("owner_original");
      const [pending, setPending] = useState({ id: "input_original", draftRevision: 0, task: "Original task", config: { model: "original" } });
      const [draft, setDraft] = useState("Original task");
      const revision = useRef(0);
      const controller = useInteractionSubmission({
        pending: pending ? { id: pending.id, threadId: "thread_original", ownerKey: owner, source: pending,
          observationOnly: state.observationOnly,
          input: { messages: [{ type: "human", id: pending.id, content: pending.task }] }, options: { metadata: { workbench: pending.config } } } : null,
        ownerKey: owner, isCurrentOwner: () => true,
        read: async () => { state.reads += 1; return state.read(); },
        hasAccepted: (view, id) => view?.input_message_id === id,
        runInView: view => view,
        projectedView: view => view,
        onAccepted: submitted => { state.accepted += 1; if (revision.current === submitted.draftRevision) setDraft(""); setPending(null); },
        onRejected: () => { state.rejected += 1; setPending(null); },
        onFailure: error => state.failures.push(error.message),
        refreshObservation: () => { state.observations += 1; },
      });
      state.controller = controller;
      state.edit = text => { revision.current += 1; setDraft(text); };
      state.switchOwner = () => { revision.current = 0; setOwner("owner_new"); setDraft("Other task draft"); setPending(null); };
      state.changeCapturedSource = () => setPending(current => ({ ...current, task: "Mutated task", config: { model: "later" } }));
      state.remountObserver = () => controller.submit(stream);
      useEffect(() => { controller.submit(stream); }, [controller, pending]);
      return React.createElement("div", null,
        React.createElement("textarea", { value: draft, readOnly: true }),
        React.createElement(SubmissionRecoveryNotice, { controller }));
    }
    let renderer;
    await act(async () => { renderer = create(React.createElement(Harness)); });
    return { state, renderer, draft: () => renderer.root.findByType("textarea").props.value,
      close: async () => { await act(async () => renderer.unmount()); } };
  }

  async function rejectedDraft() {
    const f = await fixture({ send: (_input, options) => options.onError(commandError(400, "invalid_request")) });
    try {
      await waitFor(() => assert.equal(f.state.rejected, 1), "typed rejection reconciled");
      assert.equal(f.draft(), "Original task", "rejected submission must retain the original draft");
      assert.equal(f.state.accepted, 0, "resolved native submit must not imply acceptance");
      assert.equal(f.state.sent.length, 1);
    } finally { await f.close(); }
  }

  async function unknownRetry() {
    const hold = deferred();
    const f = await fixture();
    try {
      await waitFor(() => assert.ok(f.state.controller.recovery), "unknown admission has recovery actions");
      assert.equal(f.draft(), "Original task");
      await act(async () => { f.state.edit("Newer draft"); f.state.changeCapturedSource(); });
      f.state.read = () => hold.promise;
      await act(async () => { f.state.controller.recovery.retryOriginal(); f.state.controller.recovery.retryOriginal(); });
      assert.equal(f.state.sent.length, 1, "repeated recovery clicks cannot issue parallel attempts");
      f.state.send = (_input, options) => { f.state.view = run(); options.onError(commandError()); };
      await act(async () => hold.resolve(null));
      await waitFor(() => assert.equal(f.state.sent.length, 2), "one explicit original retry sent");
      assert.deepEqual(f.state.sent[1], f.state.sent[0], "retry freezes original input/configuration/identity");
      f.state.read = async () => f.state.view;
      await act(async () => f.state.lastError(commandError()));
      await waitFor(() => assert.equal(f.state.accepted, 1), "retry acceptance reconciled");
      assert.equal(f.draft(), "Newer draft", "acceptance cannot clear a newer draft");
      await act(async () => f.state.remountObserver());
      assert.equal(f.state.sent.length, 2, "observer remount cannot submit again");
    } finally { hold.resolve(null); await f.close(); }
  }

  async function staleOwner() {
    const hold = deferred();
    const f = await fixture({ read: () => hold.promise });
    try {
      await waitFor(() => assert.ok(f.state.reads), "old lookup started");
      await act(async () => f.state.switchOwner());
      await act(async () => hold.resolve(run()));
      await flush();
      assert.equal(f.draft(), "Other task draft", "old admission cannot clear another owner's draft");
      assert.equal(f.state.accepted, 0, "obsolete lookup cannot accept on the new owner");
      await act(async () => f.state.lastError(commandError()));
      assert.deepEqual(f.state.failures, [], "late old command error cannot target another owner");
    } finally { hold.resolve(null); await f.close(); }
  }

  async function failureAndAcknowledgement() {
    for (const failed of [false, true]) {
      const f = await fixture({ view: run("input_original", failed ? "failed" : "running") });
      try {
        await waitFor(() => assert.equal(f.state.accepted, 1), "accepted input reconciled after command error");
        assert.equal(f.draft(), "");
        if (failed) assert.deepEqual(f.state.failures, ["Actual model failure"], "accepted failure stays a real failure");
        else assert.deepEqual(f.state.failures, [], "accepted acknowledgement error is suppressed");
        assert.equal(f.state.sent.length, 1);
      } finally { await f.close(); }
    }
    const f = await fixture({ send: () => {} });
    try {
      await act(async () => f.state.controller.observe(run()));
      f.state.view = run();
      await act(async () => f.state.lastError(commandError()));
      await flush();
      assert.equal(f.state.observations, 0, "late acknowledgement does not replace a working observer");
      assert.deepEqual(f.state.failures, []);
      await act(async () => f.state.controller.onError(new Error("Native execution failed")));
      assert.deepEqual(f.state.failures, ["Native execution failed"], "real later stream failure is visible");
    } finally { await f.close(); }
  }

  async function observationOnly() {
    const f = await fixture({ observationOnly: true });
    try {
      await waitFor(() => assert.ok(f.state.controller.recovery), "restored unresolved request is actionable");
      assert.equal(f.state.sent.length, 0, "restoring an observer never submits");
      await act(async () => f.state.controller.recovery.checkAgain());
      assert.equal(f.state.sent.length, 0, "empty acceptance lookup never submits");
      f.state.view = run();
      await act(async () => f.state.controller.recovery.checkAgain());
      await waitFor(() => assert.equal(f.state.accepted, 1), "existing admission recovered");
      assert.equal(f.state.sent.length, 0, "known accepted work only hydrates");
    } finally { await f.close(); }
  }

  async function commandFacts() {
    const originalFetch = globalThis.fetch;
    try {
      let responseBody = { type: "error", id: "cmd", error: "invalid_request", message: "Exact denial" };
      let status = 400;
      globalThis.fetch = async () => new Response(JSON.stringify(responseBody), { status });
      const transport = createResumingInteractionTransport("thread_original");
      await assert.rejects(transport.send({ id: "cmd", method: "run.start", params: { input: { messages: [{ id: "input_original" }] } } }), error => {
        assert.ok(error instanceof InteractionCommandError);
        assert.equal(error.status, 400); assert.equal(error.code, "invalid_request");
        assert.equal(error.commandId, "cmd"); assert.equal(error.inputId, "input_original");
        return true;
      });
      responseBody = { type: "error", id: "some_other_command", error: "invalid_request", code: "proxy_code" };
      await assert.rejects(transport.send({ id: "cmd", method: "run.start", params: {} }), error => {
        assert.equal(error.code, undefined, "unmatched envelopes cannot certify rejection"); return true;
      });
      responseBody = { values: { messages: [] } };
      status = 200;
      assert.deepEqual(await transport.getState(), { values: { messages: [] } }, "observation delegates unchanged");
      await transport.close();
    } finally { globalThis.fetch = originalFetch; }
  }

  const cases = negative === "draft-loss" ? [["rejected draft", rejectedDraft]] : negative === "stale-owner" ? [["stale owner", staleOwner]] : [
    ["rejected draft", rejectedDraft], ["immutable original retry", unknownRetry], ["stale owner", staleOwner],
    ["real failure and late acknowledgement", failureAndAcknowledgement], ["restored observation only", observationOnly], ["typed command facts", commandFacts],
  ];
  for (const [name, check] of cases) { await check(); console.log(`CASE PASS: ${name}`); }
} finally { await vite.close(); console.error = originalConsoleError; }
console.log("Shared interaction submission checks passed.");
