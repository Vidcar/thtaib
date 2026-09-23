import assert from "node:assert/strict";
import { createServer } from "node:http";
import path from "node:path";
import { fileURLToPath } from "node:url";

import React, { StrictMode } from "react";
import { act, create } from "react-test-renderer";
import { createServer as createViteServer } from "vite";

const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../..");
const desktopRoot = path.join(repoRoot, "apps/desktop");

globalThis.IS_REACT_ACT_ENVIRONMENT = true;
globalThis.HTMLElement ??= class HTMLElement {};

const originalConsoleError = console.error;
console.error = (...args) => {
  const first = String(args[0] ?? "");
  if (
    first.startsWith("react-test-renderer is deprecated") ||
    first.startsWith("An update to ") ||
    first.startsWith("When testing, code that causes React state updates should be wrapped into act")
  ) {
    return;
  }
  originalConsoleError(...args);
};

function deferred() {
  let resolve;
  const promise = new Promise((res) => {
    resolve = res;
  });
  return { promise, resolve };
}

function now() {
  return "2026-09-21T12:00:00.000Z";
}

function run(id, status, task, inputMessageId = null) {
  return {
    id,
    input_message_id: inputMessageId,
    task,
    status,
    events: [{ at: now(), kind: "started", detail: {} }],
    error: null,
    stop_reason: null,
    host_shell: { available: false, cwd: null },
    effective_setup: null,
    retrieved_material: [],
    related_files: [],
    structured_output: null,
    context_observation: null,
    pending_interrupt: null,
  };
}

function json(res, status, body) {
  res.writeHead(status, { "content-type": "application/json" });
  res.end(JSON.stringify(body));
}

function frame(runValue) {
  return {
    type: "event",
    method: "values",
    params: {
      namespace: [],
      data: {
        messages: [{ id: `${runValue.id}_message`, type: "ai", content: runValue.task }],
        workbench: { run: runValue },
      },
    },
  };
}

function makeHarness() {
  const heldCancel = deferred();
  const state = {
    nextThread: 1,
    registeredThreads: [],
    registrationPayloads: [],
    registrationBarriers: new Map(),
    savedRuns: new Map([
      ["saved_a", run("saved_a", "completed", "Previously saved task A")],
      ["saved_b", run("saved_b", "completed", "Previously saved task B")],
    ]),
    commands: [],
    cancels: [],
    cancelBarrier: heldCancel,
    streamRuns: new Map(),
  };
  const server = createServer((req, res) => {
    let body = "";
    req.on("data", (chunk) => {
      body += String(chunk);
    });
    req.on("end", async () => {
      const url = new URL(req.url ?? "/", "http://127.0.0.1");
      if (req.method === "GET" && url.pathname === "/v1/profiles") { json(res, 200, []); return; }
      if (req.method === "POST" && url.pathname === "/v1/setup-resolution") { json(res, 200, { configuration: { deployment_id: "dep_1", ...JSON.parse(body).overrides }, instruction_layers: [], effective_values: {} }); return; }
      if (req.method === "GET" && url.pathname === "/v1/deployments") {
        json(res, 200, [{
          id: "dep_1",
          bundle_id: null,
          display_name: "connected:test",
          endpoint: "http://127.0.0.1:9",
          status: "running",
          scope: "connected",
          health: null,
          settings: null,
          created_at: now(),
          updated_at: now(),
        }]);
        return;
      }
      if (req.method === "GET" && url.pathname === "/v1/agent-tools") {
        json(res, 200, { enabled: ["echo"] });
        return;
      }
      if (req.method === "POST" && url.pathname === "/v1/agent-interaction/threads") {
        const payload = body ? JSON.parse(body) : {};
        state.registrationPayloads.push(payload);
        const threadId = payload.run_id ? `thread_${payload.run_id}` : `thread_${state.nextThread++}`;
        if (payload.run_id) {
          await state.registrationBarriers.get(payload.run_id)?.promise;
          state.streamRuns.set(threadId, state.savedRuns.get(payload.run_id));
        }
        state.registeredThreads.push(threadId);
        json(res, 200, { thread_id: threadId });
        return;
      }
      const savedRunMatch = url.pathname.match(/^\/v1\/agent-runs\/([^/]+)$/);
      if (req.method === "GET" && savedRunMatch) {
        const savedRun = state.savedRuns.get(savedRunMatch[1]);
        json(res, savedRun ? 200 : 404, savedRun ?? { error: "This task was deleted." });
        return;
      }
      const stateMatch = url.pathname.match(/^\/v1\/agent-interaction\/threads\/([^/]+)\/state$/);
      if (req.method === "GET" && stateMatch) {
        const runValue = state.streamRuns.get(stateMatch[1]) ?? null;
        json(res, 200, { values: { messages: [], workbench: { run: runValue } }, next: [], tasks: [] });
        return;
      }
      const streamMatch = url.pathname.match(/^\/v1\/agent-interaction\/threads\/([^/]+)\/stream\/events$/);
      if (req.method === "POST" && streamMatch) {
        let runValue = state.streamRuns.get(streamMatch[1]);
        for (let index = 0; !runValue && index < 50; index += 1) {
          await new Promise((resolve) => setTimeout(resolve, 5));
          runValue = state.streamRuns.get(streamMatch[1]);
        }
        res.writeHead(200, { "content-type": "text/event-stream" });
        if (runValue) {
          res.write(`data: ${JSON.stringify(frame(runValue))}\n\n`);
        }
        res.end();
        return;
      }
      const commandMatch = url.pathname.match(/^\/v1\/agent-interaction\/threads\/([^/]+)\/commands$/);
      if (req.method === "POST" && commandMatch) {
        const payload = body ? JSON.parse(body) : {};
        const threadId = commandMatch[1];
        state.commands.push({ threadId, payload });
        const runId = threadId === "thread_1" ? "run_1" : "run_2";
        const message = payload.params?.input?.messages?.[0];
        const task = typeof message?.content === "string" ? message.content : threadId;
        state.streamRuns.set(threadId, run(runId, "completed", task, message?.id ?? null));
        json(res, 200, { type: "success", id: payload.id ?? "cmd", result: {} });
        return;
      }
      const cancelMatch = url.pathname.match(/^\/v1\/agent-runs\/([^/]+)\/cancel$/);
      if (req.method === "POST" && cancelMatch) {
        const runId = cancelMatch[1];
        state.cancels.push(runId);
        await state.cancelBarrier.promise;
        json(res, 200, run(runId, "cancel_requested", "first task"));
        return;
      }
      json(res, 404, { error: `${req.method} ${url.pathname}` });
    });
  });
  return { server, state };
}

async function flush() {
  await act(async () => {
    await Promise.resolve();
  });
}

async function waitFor(assertion, label) {
  let lastError;
  for (let index = 0; index < 40; index += 1) {
    await flush();
    try {
      return assertion();
    } catch (error) {
      lastError = error;
      await new Promise((resolve) => setTimeout(resolve, 5));
    }
  }
  throw new Error(`${label}: ${lastError instanceof Error ? lastError.message : String(lastError)}`);
}

function textOf(node) {
  if (typeof node === "string") {
    return node;
  }
  if (!node?.children) {
    return "";
  }
  return node.children.map(textOf).join("");
}

function allText(renderer) {
  return textOf(renderer.toJSON());
}

function textarea(renderer) {
  const found = renderer.root.findAll((node) => node.type === "textarea");
  assert.ok(found.length > 0, "expected textarea");
  return found[0];
}

function startForm(renderer) {
  const found = renderer.root.findAll((node) => node.type === "form" && node.props.className === "card");
  assert.ok(found.length > 0, "expected Agent run form");
  return found[0];
}

function cancelButton(renderer) {
  const found = renderer.root.findAll((node) => node.type === "button" && textOf(node).includes("Cancel"));
  assert.ok(found.length > 0, "expected cancel button");
  return found[0];
}

const harness = makeHarness();
await new Promise((resolve) => harness.server.listen(0, "127.0.0.1", resolve));
const address = harness.server.address();
const port = typeof address === "object" && address ? address.port : 0;
globalThis.window = { workbench: { backendUrl: `http://127.0.0.1:${port}` } };

const vite = await createViteServer({ root: desktopRoot, appType: "custom", server: { middlewareMode: true, hmr: false }, logLevel: "error" });
try {
  const { AgentRunPanel } = await vite.ssrLoadModule("/src/renderer/AgentRunPanel.tsx");
  let renderer;
  await act(async () => {
    renderer = create(React.createElement(StrictMode, null, React.createElement(AgentRunPanel)));
    await Promise.resolve();
  });
  await waitFor(() => assert.match(allText(renderer), /Workflows/), "initial task surface render");
  const folder = () => renderer.root.findAllByType("input").find(node => node.props.placeholder === "Optional project path");
  await act(async () => folder().props.onChange({ target: { value: "D:/isolated-workflow" } }));
  assert.match(allText(renderer), /Shell tools follow approval rules and saved permissions/);
  await act(async () => renderer.root.findByProps({ role: "radio", "aria-label": "Full access" }).props.onClick());
  assert.match(allText(renderer), /Enabled shell tools run without approval pauses/);
  assert.doesNotMatch(allText(renderer), /Shell commands can access this computer and require approval/);
  await act(async () => {
    textarea(renderer).props.onChange({ target: { value: "first task" } });
    await Promise.resolve();
  });
  await waitFor(() => assert.equal(textarea(renderer).props.value, "first task"), "first draft applied");
  await act(async () => {
    startForm(renderer).props.onSubmit({ preventDefault() {} });
    await Promise.resolve();
  });
  await waitFor(() => assert.match(allText(renderer), /first task/), "first run projection");
  assert.equal(harness.state.commands[0].payload.params.metadata.workbench.approval_mode, "full_access", "the displayed access reaches the workflow submission");
  await act(async () => {
    cancelButton(renderer).props.onClick();
    await Promise.resolve();
  });
  await waitFor(() => assert.deepEqual(harness.state.cancels, ["run_1"]), "first cancel request");
  await act(async () => {
    textarea(renderer).props.onChange({ target: { value: "second task" } });
    await Promise.resolve();
  });
  await waitFor(() => assert.equal(textarea(renderer).props.value, "second task"), "second draft applied");
  await act(async () => {
    startForm(renderer).props.onSubmit({ preventDefault() {} });
    await Promise.resolve();
  });
  await waitFor(() => assert.match(allText(renderer), /second task/), "second run projection");
  harness.state.cancelBarrier.resolve();
  await flush();
  assert.match(allText(renderer), /second task/, "stale first cancel must not replace the second run");
  assert.doesNotMatch(allText(renderer), /Stopping|cancel_requested/, "stale first cancel status must not appear on the second run");
  await act(async () => renderer.unmount());

  const commandsBeforeReopen = harness.state.commands.length;
  const handled = [];
  const onAttentionHandled = id => handled.push(id);
  await act(async () => {
    renderer = create(React.createElement(AgentRunPanel, { attentionRunId: "saved_a", onAttentionHandled }));
  });
  await waitFor(() => assert.match(allText(renderer), /Previously saved task A/), "notification opens its existing non-Chat task");
  assert.deepEqual(harness.state.registrationPayloads.at(-1), { source_surface: "agent", run_id: "saved_a" });
  await waitFor(() => assert.deepEqual(handled, ["saved_a"]), "notification target acknowledged after hydration");
  assert.equal(harness.state.commands.length, commandsBeforeReopen, "notification activation cannot replay a saved task");
  await act(async () => renderer.unmount());

  const staleRegistration = deferred();
  harness.state.registrationBarriers.set("saved_a", staleRegistration);
  const priorRegistrations = harness.state.registrationPayloads.length;
  await act(async () => {
    renderer = create(React.createElement(AgentRunPanel, { attentionRunId: "saved_a", onAttentionHandled }));
  });
  await waitFor(() => assert.equal(harness.state.registrationPayloads.length, priorRegistrations + 1), "first notification registration held");
  await act(async () => {
    renderer.update(React.createElement(AgentRunPanel, { attentionRunId: "saved_b", onAttentionHandled }));
  });
  await waitFor(() => assert.match(allText(renderer), /Previously saved task B/), "newer notification wins before old registration returns");
  staleRegistration.resolve();
  await waitFor(() => assert.ok(harness.state.registeredThreads.filter(id => id === "thread_saved_a").length >= 2), "old registration response delivered");
  await flush();
  assert.match(allText(renderer), /Previously saved task B/, "late registration cannot replace the activated task");
  assert.deepEqual(handled, ["saved_a", "saved_b"], "obsolete notification is never acknowledged as the newer selection");
  assert.equal(harness.state.commands.length, commandsBeforeReopen, "reopening and switching saved tasks issues no work commands");
  await act(async () => renderer.unmount());
} finally {
  for (const barrier of harness.state.registrationBarriers.values()) barrier.resolve();
  await vite.close();
  await new Promise((resolve) => harness.server.close(resolve));
}

console.log("Agent run interaction boundary checks passed.");
