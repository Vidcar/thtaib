import assert from "node:assert/strict";
import { createServer } from "node:http";

import { Client, HttpAgentServerAdapter, ThreadStream } from "@langchain/langgraph-sdk/client";
import { StreamController, messagesProjection } from "@langchain/langgraph-sdk/stream";

const replayEvents = [
  event(1, "messages", [], { event: "message-start", id: "reply", role: "ai" }),
  event(2, "messages", [], { event: "message-delta", id: "reply", content: "H" }),
  event(3, "tools", ["task:one", "tool:two"], { event: "tool-started", id: "tool-one", name: "read_file" }),
  event(4, "messages", [], { event: "message-delta", id: "reply", content: "ello" }),
  event(5, "messages", [], { event: "message-delta", id: "reply", content: " world" }),
];
const replayRequests = [];
const replayStreams = new Set();
let releaseHeldReplay;
let notifyHeldReplay;
const heldReplayRequested = new Promise((resolve) => { notifyHeldReplay = resolve; });
const hydratedRequests = [];
const hydratedStreams = new Set();
let notifyHydratedRoot;
const hydratedRootRequested = new Promise((resolve) => { notifyHydratedRoot = resolve; });
const reconnectRequests = [];
let reconnectCount = 0;

function event(seq, method, namespace, data) {
  return { type: "event", method, seq, event_id: `evt-${seq}`, params: { namespace, data } };
}

function messageText(message) {
  const content = message?.content;
  if (typeof content === "string") return content;
  return Array.isArray(content) ? content.map((block) => block?.text ?? "").join("") : "";
}

function send(res, item) {
  res.write(`id: ${item.seq}\ndata: ${JSON.stringify(item)}\n\n`);
}

function matches(item, filter) {
  if (!filter.channels.includes(item.method)) return false;
  if (!Array.isArray(filter.namespaces)) return true;
  return filter.namespaces.some((prefix) =>
    prefix.every((segment, i) => item.params.namespace[i] === segment) &&
    (filter.depth == null || item.params.namespace.length - prefix.length <= filter.depth));
}

function within(promise, label) {
  let timeout;
  return Promise.race([
    promise,
    new Promise((_, reject) => {
      timeout = setTimeout(() => reject(new Error(`Timed out waiting for ${label}`)), 4000);
    }),
  ]).finally(() => clearTimeout(timeout));
}

function nextWithin(iterator, label) {
  return within(iterator.next(), label);
}

function waitForStore(store, ready, label) {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => {
      unsubscribe();
      reject(new Error(`Timed out waiting for ${label}`));
    }, 4000);
    const check = () => {
      if (!ready(store.getSnapshot())) return;
      clearTimeout(timer);
      unsubscribe();
      resolve();
    };
    const unsubscribe = store.subscribe(check);
    check();
  });
}

const server = createServer((req, res) => {
  let raw = "";
  req.on("data", (chunk) => { raw += String(chunk); });
  req.on("end", () => {
    const path = new URL(req.url ?? "/", "http://127.0.0.1").pathname;
    if (path.includes("/hydrated_test/") && req.method === "GET" && path.endsWith("/state")) {
      res.writeHead(200, { "content-type": "application/json" });
      res.end(JSON.stringify({
        values: { messages: [{ id: "reply", type: "ai", content: "Hello" }], workbench: { run: { id: "run", status: "running" } } },
        next: ["running"], tasks: [], interaction_cursor: 4,
      }));
      return;
    }
    if (path.includes("/hydrated_test/") && path.includes("/history")) {
      res.writeHead(200, { "content-type": "application/json" }).end("[]");
      return;
    }
    if (req.method !== "POST" || !path.endsWith("/stream/events")) {
      res.writeHead(404).end();
      return;
    }
    const filter = JSON.parse(raw);
    res.writeHead(200, { "content-type": "text/event-stream" });
    if (path.includes("/replay_test/")) {
      replayRequests.push(filter);
      const openReplay = () => {
        res.flushHeaders();
        const live = { res, filter };
        replayStreams.add(live);
        res.on("close", () => replayStreams.delete(live));
        for (const item of replayEvents) {
          if (item.seq > (filter.since ?? 0) && matches(item, filter)) send(res, item);
        }
      };
      if (filter.since === 0 && releaseHeldReplay == null) {
        releaseHeldReplay = openReplay;
        notifyHeldReplay();
        return;
      }
      openReplay();
      return;
    }
    res.flushHeaders();
    if (path.includes("/hydrated_test/")) {
      hydratedRequests.push(filter);
      const live = { res, filter };
      hydratedStreams.add(live);
      res.on("close", () => hydratedStreams.delete(live));
      if (filter.since === 4 && filter.channels.includes("messages") && filter.channels.includes("tools")) {
        notifyHydratedRoot();
      }
      const prior = [
        event(1, "messages", [], { event: "message-start", id: "reply", role: "ai" }),
        event(2, "messages", [], { event: "message-delta", id: "reply", content: "H" }),
        event(3, "messages", ["task:one"], { event: "message-start", id: "nested", role: "ai" }),
        event(4, "messages", [], { event: "message-delta", id: "reply", content: "ello" }),
      ];
      for (const item of prior) if (item.seq > (filter.since ?? 0) && matches(item, filter)) send(res, item);
      return;
    }
    if (path.includes("/reconnect_test/")) {
      reconnectRequests.push(filter);
      reconnectCount += 1;
      if (reconnectCount === 1) {
        send(res, event(6, "values", [], { messages: [] }));
        res.end("id: 7\ndata: {\"type\":\"event\",");
      } else {
        send(res, event(7, "values", [], { messages: [] }));
      }
      return;
    }
    res.end();
  });
});

await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
const address = server.address();
const apiUrl = `http://127.0.0.1:${address.port}/v1/agent-interaction`;
const thread = new ThreadStream(new HttpAgentServerAdapter({ apiUrl, threadId: "replay_test" }), { assistantId: "assistant" });
thread.setHydrationCursor(4);
let controller;

try {
  const root = await thread.subscribe({ channels: ["messages"], namespaces: [[]], depth: 1, since: 4 });
  const rootEvents = root[Symbol.asyncIterator]();
  assert.equal((await nextWithin(rootEvents, "first live token")).value.seq, 5);
  assert.equal(replayRequests[0].since, 4, "hydrated root starts after the saved state");

  thread.startLifecycleWatcher();
  const samePromise = thread.subscribe({ channels: ["messages"], namespaces: [[]], depth: 1 });
  await within(heldReplayRequested, "replay rotation");
  // The new subscription is registered while the old stream still runs.
  // A live event must wait for its replay stream so history remains ordered.
  const liveToken = event(6, "messages", [], { event: "message-delta", id: "reply", content: "!" });
  replayEvents.push(liveToken);
  for (const live of replayStreams) if (matches(liveToken, live.filter)) send(live.res, liveToken);
  assert.equal((await nextWithin(rootEvents, "root live token during rotation")).value.seq, 6);
  releaseHeldReplay();
  const same = await samePromise;
  const sameEvents = same[Symbol.asyncIterator]();
  assert.equal(replayRequests.at(-1).since, 0, "late same-filter subscription replays its history");
  for (const seq of [1, 2, 4, 5, 6]) {
    assert.equal((await nextWithin(sameEvents, `same-filter event ${seq}`)).value.seq, seq);
  }

  const wider = await thread.subscribe({ channels: ["tools", "lifecycle"] });
  const widerEvents = wider[Symbol.asyncIterator]();
  assert.equal(replayRequests.at(-1).since, 0, "late wider subscription replays its history");
  const nestedTool = (await nextWithin(widerEvents, "nested tool")).value;
  assert.equal(nestedTool.seq, 3);
  assert.deepEqual(nestedTool.params.namespace, ["task:one", "tool:two"]);

  const nestedLifecycle = event(7, "lifecycle", ["task:one", "tool:two"], { event: "running" });
  for (const live of replayStreams) if (matches(nestedLifecycle, live.filter)) send(live.res, nestedLifecycle);
  assert.equal((await nextWithin(widerEvents, "nested lifecycle")).value.seq, 7);

  // Exercise the actual root projection. A replayed old message-start
  // would replace the hydrated, unfinished "Hello" with an empty answer.
  controller = new StreamController({
    assistantId: "assistant",
    client: new Client({ apiUrl }),
    transport: new HttpAgentServerAdapter({ apiUrl, threadId: "hydrated_test" }),
  });
  await controller.hydrate("hydrated_test");
  await waitForStore(controller.rootStore, (snapshot) => snapshot.messages.at(-1)?.content === "Hello", "hydrated partial");
  assert.equal(controller.rootStore.getSnapshot().messages.at(-1)?.content, "Hello");
  await within(hydratedRootRequested, "hydrated root stream");
  // The backend restores an open tool at the state cursor, then emits
  // message-start/block seeds at that same cursor before the next delta.
  // Those are real resume events even though their seq equals `since`.
  const resumed = [
    { ...event(4, "tools", ["tools:call-open"], {
      event: "tool-started", tool_call_id: "call-open", tool_name: "read_file", input: { path: "example.txt" },
    }), event_id: "resume:tool:hydrated_test:evt-open-tool" },
    { ...event(4, "messages", [], { event: "message-start", id: "reply", role: "ai" }), event_id: "resume:message-start" },
    { ...event(4, "messages", [], {
      event: "content-block-start", index: 0, content: { type: "text", text: "Hello" },
    }), event_id: "resume:content-block-start" },
    event(5, "messages", [], { event: "content-block-delta", index: 0, delta: { type: "text-delta", text: "!" } }),
  ];
  for (const item of resumed) {
    for (const live of hydratedStreams) if (matches(item, live.filter)) send(live.res, item);
  }
  await waitForStore(controller.rootStore,
    (snapshot) => snapshot.toolCalls.some((tool) => tool.callId === "call-open" && tool.status === "running"),
    "restored open tool");
  await waitForStore(controller.rootStore, (snapshot) => messageText(snapshot.messages.at(-1)) === "Hello!", "resumed partial");
  const scoped = controller.registry.acquire(messagesProjection(["task:one"]));
  await waitForStore(scoped.store, (messages) => messages?.length > 0, "scoped replay");
  assert.equal(messageText(controller.rootStore.getSnapshot().messages.at(-1)), "Hello!");
  assert.ok(hydratedRequests.some((request) => request.since === 4 && request.channels.includes("messages")));
  assert.ok(hydratedRequests.some((request) => request.since === 4 && request.channels.includes("lifecycle")));
  assert.ok(hydratedRequests.some((request) => request.since === 0 && request.channels.includes("messages")));
  scoped.release();
  await controller.dispose();
  controller = undefined;

  const reconnect = new HttpAgentServerAdapter({ apiUrl, threadId: "reconnect_test" });
  const handle = reconnect.openEventStream({ channels: ["values"], namespaces: [[]], since: 4 });
  await handle.ready;
  const reconnectEvents = handle.events[Symbol.asyncIterator]();
  assert.equal((await nextWithin(reconnectEvents, "complete frame before disconnect")).value.seq, 6);
  assert.equal((await nextWithin(reconnectEvents, "replayed incomplete frame")).value.seq, 7);
  assert.deepEqual(reconnectRequests.slice(0, 2).map((request) => request.since), [4, 6]);
  handle.close();
  root.close();
  same.close();
  wider.close();

  // A failed first root stream must not consume the hydration cutoff.
  const retryFilters = [];
  const retryAdapter = {
    open: async () => {},
    close: async () => {},
    openEventStream(filter) {
      retryFilters.push(filter);
      return {
        ready: retryFilters.length === 1 ? Promise.reject(new Error("first stream failed")) : Promise.resolve(),
        events: { [Symbol.asyncIterator]: () => ({ next: () => new Promise(() => {}) }) },
        close: () => {},
      };
    },
  };
  const retryThread = new ThreadStream(retryAdapter, { assistantId: "assistant" });
  try {
    retryThread.setHydrationCursor(4);
    const rootFilter = { channels: ["values", "messages", "tools"], namespaces: [[]], depth: 1 };
    await assert.rejects(retryThread.subscribe(rootFilter), /first stream failed/);
    const retryRoot = await retryThread.subscribe(rootFilter);
    assert.deepEqual(retryFilters.map((filter) => filter.since), [4, 4]);
    retryRoot.close();
  } finally {
    await retryThread.close();
  }
} finally {
  await controller?.dispose();
  await thread.close();
  for (const live of replayStreams) live.res.end();
  for (const live of hydratedStreams) live.res.end();
  server.closeAllConnections();
  await new Promise((resolve) => server.close(resolve));
}

console.log("Pinned SDK hydrated subscription and per-handle reconnect checks passed.");
