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

let streamRequests = 0;
let commandRequests = 0;
const server = createServer((req, res) => {
  let body = "";
  req.on("data", (chunk) => {
    body += String(chunk);
  });
  req.on("end", () => {
    const url = new URL(req.url ?? "/", "http://127.0.0.1");
    if (req.method === "GET" && url.pathname === "/v1/agent-interaction/threads/react_owner/state") {
      res.writeHead(200, { "content-type": "application/json" });
      res.end(JSON.stringify({ values: { messages: [], workbench: { run: { id: "run_1", status: "running" } } }, next: ["running"], tasks: [], interaction_cursor: 0 }));
      return;
    }
    if (req.method === "POST" && url.pathname === "/v1/agent-interaction/threads/react_owner/history") {
      res.writeHead(200, { "content-type": "application/json" });
      res.end("[]");
      return;
    }
    if (req.method === "POST" && url.pathname === "/v1/agent-interaction/threads/react_owner/stream/events") {
      if (process.env.WORKBENCH_TEST_DISABLE_STREAM === "1") {
        res.writeHead(503, { "content-type": "application/json" });
        res.end(JSON.stringify({ error: "deliberately broken observation fixture" }));
        return;
      }
      streamRequests += 1;
      res.writeHead(200, { "content-type": "text/event-stream" });
      res.write(`data: ${JSON.stringify({
        type: "event",
        method: "values",
        params: { namespace: [], data: { messages: [{ id: "m1", type: "ai", content: "first" }], workbench: { run: { id: "run_1", status: "running" } } } },
      })}\n\n`);
      setTimeout(() => {
        res.write(`data: ${JSON.stringify({
          type: "event",
          method: "values",
          params: { namespace: [], data: { messages: [{ id: "m1", type: "ai", content: "first" }, { id: "m2", type: "ai", content: "second" }], workbench: { run: { id: "run_1", status: "running" } } } },
        })}\n\n`);
      }, 5);
      setTimeout(() => res.end(), 25);
      return;
    }
    if (req.method === "POST" && url.pathname === "/v1/agent-interaction/threads/react_owner/commands") {
      commandRequests += 1;
      res.writeHead(200, { "content-type": "application/json" });
      res.end(JSON.stringify({ type: "success", id: body ? JSON.parse(body).id : "cmd", result: {} }));
      return;
    }
    res.writeHead(404, { "content-type": "application/json" });
    res.end(JSON.stringify({ error: "missing" }));
  });
});

await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
const address = server.address();
const port = typeof address === "object" && address ? address.port : 0;
globalThis.window = { workbench: { backendUrl: `http://127.0.0.1:${port}` } };

const vite = await createViteServer({ configFile: false, root: desktopRoot, appType: "custom", server: { middlewareMode: true, hmr: false }, logLevel: "error" });
let renderer;
try {
  const { InteractionStream, useWorkbenchProjection } = await vite.ssrLoadModule("/src/renderer/InteractionStream.tsx");
  let renderCount = 0;
  const observedMessages = new Map();
  function Observation({ stream }) {
    const { messages } = useWorkbenchProjection(stream);
    for (const message of messages) observedMessages.set(message.id, message.content);
    return React.createElement("span", null, messages.map(message => message.content).join(" "));
  }
  function Probe() {
    return React.createElement(InteractionStream, { threadId: "react_owner" }, (stream) => {
      renderCount += 1;
      return React.createElement(Observation, { stream });
    });
  }
  await act(async () => {
    renderer = create(React.createElement(StrictMode, null, React.createElement(Probe)));
  });
  const deadline = Date.now() + 4000;
  while (!observedMessages.has("m2") && Date.now() < deadline) {
    await act(async () => { await new Promise(resolve => setTimeout(resolve, 20)); });
  }
  await act(async () => {
    renderer.update(React.createElement(StrictMode, null, React.createElement(Probe)));
    await new Promise((resolve) => setTimeout(resolve, 40));
  });
  assert.ok(renderCount > 0, "InteractionStream should render through React");
  assert.equal(commandRequests, 0, "mounting/render updates must not send SDK commands");
  assert.ok(streamRequests > 0, "observation must actually open a stream");
  assert.ok(streamRequests <= 2, `StrictMode ownership should avoid per-token duplicate stream effects; saw ${streamRequests}`);
  assert.equal(observedMessages.get("m1"), "first", "the native selector must receive the first streamed message");
  assert.equal(observedMessages.get("m2"), "second", "the native selector must receive the later streamed message");
} finally {
  if (renderer) await act(async () => renderer.unmount());
  await vite.close();
  server.closeAllConnections();
  await new Promise((resolve) => server.close(resolve));
}

console.log("InteractionStream React StrictMode ownership check passed.");
