import assert from "node:assert/strict";
import { createServer } from "node:http";
import path from "node:path";
import { fileURLToPath } from "node:url";
import React from "react";
import { act, create } from "react-test-renderer";
import { createServer as createViteServer } from "vite";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;
const namespace = ["tools:d0a6a3c8-820a-d669-ef45-b9842dd22f92"];
const betaNamespace = ["tools:beta-native-helper"];
const request = "Review each requirement against the actual project files.\n".repeat(45);
const betaRequest = "Review Beta's separate file and report its findings.";
const run = { id: "parent", status: "running", child_runs: [
  { run_id: "child", tool_call_id: "delegation-call", agent_id: "research", version_id: "v1", name: "Research", namespace, status: "working" },
  { run_id: "child-beta", tool_call_id: "delegation-beta", agent_id: "beta", version_id: "v1", name: "Beta", namespace: betaNamespace, status: "working" },
], helper_snapshots: [], events: [
  { kind: "tool_call", detail: { id: "delegation-call", name: "task", args: { description: request } } },
  { kind: "tool_call", detail: { id: "delegation-beta", name: "task", args: { description: betaRequest } } },
], tool_outcomes: {
  "child:read": { call_id: "read", name: "read_file", outcome: "succeeded" },
  "child-beta:read": { call_id: "read", name: "read_file", outcome: "succeeded" },
} };
const earlierRun = { id: "earlier-parent", status: "completed", child_runs: [{ run_id: "earlier-child", tool_call_id: "earlier-delegation", name: "Earlier reviewer", namespace: ["tools:earlier-child"], status: "completed" }] };
const human = { id: "delegated-input", type: "human", content: request };
const tool = { id: "read", name: "read_file", args: { file_path: "/index.html" } };
let seq = 0;
const event = (method, ns, data) => ({ type: "event", method, seq: ++seq, event_id: String(seq), params: { namespace: ns, timestamp: 1, data } });
// Actual v3 message/tool envelopes observed in the live helper, with identifiers sanitized.
const events = [
  // These completed calls are replayed now, so SDK startedAt cannot establish
  // their parent. The current run owns only delegation-call below.
  event("tools", [], { event: "tool-started", tool_call_id: "earlier-delegation", tool_name: "task", input: { subagent_type: "earlier-reviewer", description: "Earlier delegated work" } }),
  event("tools", [], { event: "tool-finished", tool_call_id: "earlier-delegation", output: "Earlier result" }),
  event("tools", [], { event: "tool-started", tool_call_id: "delegation-call", tool_name: "task", input: { subagent_type: "research", description: request } }),
  event("tools", [], { event: "tool-started", tool_call_id: "delegation-beta", tool_name: "task", input: { subagent_type: "beta", description: betaRequest } }),
  event("values", ["tools:unrelated"], { messages: [{ id: "other", type: "ai", content: "UNRELATED HELPER OUTPUT" }] }),
  event("values", namespace, { messages: [human] }),
  event("tools", namespace, { event: "tool-started", tool_call_id: "read", tool_name: "read_file", input: tool.args }),
  event("tools", namespace, { event: "tool-finished", tool_call_id: "read", output: { type: "tool", name: "read_file", tool_call_id: "read", content: "Project file content", status: "success" } }),
  event("values", namespace, { messages: [human, { id: "read-message", type: "ai", content: "", tool_calls: [tool] }, { id: "read-result", type: "tool", tool_call_id: "read", name: "read_file", content: "Project file content", status: "success" }] }),
  // Parallel helpers intentionally reuse local message and tool IDs. Their
  // namespace remains the sole owner of replayed transcript/tool contents.
  event("tools", betaNamespace, { event: "tool-started", tool_call_id: "read", tool_name: "read_file", input: { file_path: "/beta-only.txt" } }),
  event("tools", betaNamespace, { event: "tool-finished", tool_call_id: "read", output: { type: "tool", name: "read_file", tool_call_id: "read", content: "BETA PRIVATE RESULT", status: "success" } }),
  event("values", betaNamespace, { messages: [
    { id: "delegated-input", type: "human", content: betaRequest },
    { id: "read-message", type: "ai", content: "", tool_calls: [{ ...tool, args: { file_path: "/beta-only.txt" } }] },
    { id: "read-result", type: "tool", tool_call_id: "read", name: "read_file", content: "BETA PRIVATE RESULT", status: "success" },
  ] }),
  event("messages", namespace, { event: "message-start", role: "ai", id: "helper-thinking" }),
  event("messages", namespace, { event: "content-block-start", index: 0, content: { type: "reasoning", reasoning: "" } }),
  event("messages", namespace, { event: "content-block-delta", index: 0, delta: { type: "reasoning-delta", reasoning: "Checking the actual track geometry" } }),
];
const matches = (item, filter) => filter.channels.includes(item.method) && (filter.namespaces ?? [[]]).some(prefix =>
  prefix.every((part, index) => item.params.namespace[index] === part) && (filter.depth == null || item.params.namespace.length - prefix.length <= filter.depth));
const streams = new Set(), requests = [];
let replayReady = false, commands = 0;
const send = (res, item) => res.write(`id: ${item.seq}\ndata: ${JSON.stringify(item)}\n\n`);
const server = createServer((req, res) => {
  let raw = "";
  req.on("data", chunk => raw += chunk);
  req.on("end", () => {
    if (req.url.endsWith("/state")) return res.writeHead(200, { "content-type": "application/json" }).end(JSON.stringify({ values: { messages: [], workbench: { run } }, next: ["running"], tasks: [], interaction_cursor: 0 }));
    if (req.url.endsWith("/history")) return res.writeHead(200, { "content-type": "application/json" }).end("[]");
    if (req.url.endsWith("/commands")) commands++;
    if (!req.url.endsWith("/stream/events")) return res.writeHead(404).end();
    const filter = JSON.parse(raw);
    requests.push(filter);
    res.writeHead(200, { "content-type": "text/event-stream" }); res.flushHeaders();
    const live = { res, filter }; streams.add(live); res.on("close", () => streams.delete(live));
    if (replayReady) for (const item of events) if (item.seq > (filter.since ?? 0) && matches(item, filter)) send(res, item);
  });
});
await new Promise(resolve => server.listen(0, "127.0.0.1", resolve));
const oldWindow = globalThis.window;
globalThis.window = { workbench: { backendUrl: `http://127.0.0.1:${server.address().port}` } };
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const vite = await createViteServer({ root, appType: "custom", server: { middlewareMode: true, hmr: false }, logLevel: "error" });
let renderer;
const view = () => JSON.stringify(renderer.toJSON());
async function until(predicate, label) {
  const end = Date.now() + 4000;
  while (!predicate()) { assert.ok(Date.now() < end, `Timed out: ${label}`); await act(async () => { await new Promise(resolve => setTimeout(resolve, 20)); }); }
}
try {
  const { HelperRail } = await vite.ssrLoadModule("/src/renderer/HelperRail.tsx");
  const { InteractionStream, useWorkbenchProjection } = await vite.ssrLoadModule("/src/renderer/InteractionStream.tsx");
  function RootProjection({ stream }) {
    const projected = useWorkbenchProjection(stream);
    return React.createElement("output", { "data-root-tools": true }, JSON.stringify({ calls: projected.toolCalls.map(call => call.callId), rawCalls: stream.toolCalls.map(call => call.callId), discoveries: [...stream.subagents.keys()], messages: projected.messages.map(message => message.id) }));
  }
  const props = { runs: [earlierRun, run], currentRunId: run.id, threadId: "helper-chat", conversationId: "chat", selectedHelperKey: "parent:delegation-call" };
  const render = () => React.createElement(React.Fragment, null,
    React.createElement(InteractionStream, { threadId: "helper-chat" }, stream => React.createElement(RootProjection, { stream })),
    React.createElement(HelperRail, props));
  await act(async () => { renderer = create(render()); });
  await until(() => requests.some(filter => filter.since === 0 && filter.namespaces?.some(ns => ns[0] === namespace[0])), "late scoped replay subscription");
  assert.match(view(), /Loading helper activity/);
  assert.match(view(), /1 tool result recorded/);
  assert.doesNotMatch(view(), /no recoverable public transcript/);
  const disclosure = renderer.root.findByProps({ className: "helper-request-disclosure" });
  assert.equal(disclosure.props.open, undefined, "long exact request is collapsed by default");
  assert.equal(renderer.root.findByProps({ className: "helper-rail-request" }).children.join(""), request);
  await act(async () => {
    replayReady = true;
    for (const live of streams) for (const item of events) if (item.seq > (live.filter.since ?? 0) && matches(item, live.filter)) send(live.res, item);
  });
  await until(() => view().includes("Checking the actual track geometry") && view().includes("index.html"), "replayed native tools and live reasoning");
  assert.doesNotMatch(view(), /UNRELATED HELPER OUTPUT|BETA PRIVATE RESULT|beta-only.txt|Loading helper activity/);
  assert.equal(renderer.root.findAll(node => node.props?.className?.includes?.("bubble user")).length, 0, "the large delegation is not duplicated in a human bubble");
  const liveReasoning = event("messages", namespace, { event: "content-block-delta", index: 0, delta: { type: "reasoning-delta", reasoning: " and finish geometry" } });
  await act(async () => { for (const live of streams) if (matches(liveReasoning, live.filter)) send(live.res, liveReasoning); });
  await until(() => view().includes("and finish geometry"), "new scoped reasoning after replay");
  const rootProjection = JSON.parse(renderer.root.findByProps({ "data-root-tools": true }).children.join(""));
  assert.ok(rootProjection.rawCalls.includes("read"), "fixture reproduces the SDK depth-one child tool entry");
  assert.ok(rootProjection.discoveries.includes("earlier-delegation"), "fixture replays older SDK helper discovery");
  assert.ok(rootProjection.calls.includes("delegation-call"), "the parent task remains visible");
  assert.ok(!rootProjection.calls.includes("read"), "depth-one helper tools stay out of the main feed");
  assert.ok(!rootProjection.messages.includes("read-message"), "the helper AI message stays scoped too");
  await act(async () => renderer.root.findByProps({ className: "quiet-button helper-rail-back" }).props.onClick());
  const activeGroup = renderer.root.findByProps({ "aria-label": "Active helpers" });
  const doneGroup = renderer.root.findByProps({ "aria-label": "Done helpers" });
  assert.equal(activeGroup.findAllByType("button").length, 2, "only the current owned parallel helpers are active");
  assert.equal(doneGroup.findAllByType("button").length, 1, "replaying older task discovery does not duplicate the durable earlier helper");
  assert.equal(commands, 0, "opening helper output never starts a second run");
  const betaButton = activeGroup.findAllByType("button").find(node => node.findAllByType("strong")[0]?.children.join("") === "Beta");
  assert.ok(betaButton, "named Beta helper is selectable");
  await act(async () => betaButton.props.onClick());
  await until(() => view().includes("BETA PRIVATE RESULT") && view().includes("beta-only.txt"), "late second-helper replay with reused local IDs");
  assert.doesNotMatch(view(), /Checking the actual track geometry|Project file content|index.html/);
  assert.equal(renderer.root.findByProps({ className: "helper-rail-request" }).children.join(""), betaRequest);
  assert.equal(commands, 0, "switching scoped helpers observes without submitting work");
  await act(async () => renderer.unmount()); renderer = undefined;
  // Completed helpers use the durable request and replayed scoped transcript too.
  run.status = "completed"; for (const child of run.child_runs) child.status = "completed";
  await act(async () => { renderer = create(render()); });
  await until(() => view().includes("index.html"), "completed helper reopen");
  assert.equal(renderer.root.findByProps({ className: "helper-rail-request" }).children.join(""), request);
  assert.doesNotMatch(view(), /no recoverable public transcript/);
  console.log("Helper rail native replay ownership, parent/child tool isolation, live reasoning and exact request passed.");
} finally {
  if (renderer) await act(async () => renderer.unmount());
  await vite.close();
  server.closeAllConnections(); await new Promise(resolve => server.close(resolve));
  globalThis.window = oldWindow;
}
