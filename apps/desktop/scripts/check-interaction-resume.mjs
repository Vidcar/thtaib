import assert from "node:assert/strict";
import { createServer } from "node:http";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { createServer as createViteServer } from "vite";

const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../..");
const desktopRoot = path.join(repoRoot, "apps/desktop");

const streamBodies = [];
let releaseSecond = () => {};
const secondHeld = new Promise((resolve) => {
  releaseSecond = resolve;
});

const server = createServer((req, res) => {
  let body = "";
  req.on("data", (chunk) => {
    body += String(chunk);
  });
  req.on("end", () => {
    const url = new URL(req.url ?? "/", "http://127.0.0.1");
    if (req.method === "GET" && url.pathname === "/v1/agent-interaction/threads/resume_test/state") {
      res.writeHead(200, { "content-type": "application/json" });
      res.end(JSON.stringify({
        values: { messages: [{ id: "m1", type: "ai", content: "Hello" }], workbench: { run: { id: "run_1", status: "running" } } },
        next: ["running"],
        tasks: [],
        interaction_cursor: 4,
      }));
      return;
    }
    if (req.method === "POST" && url.pathname === "/v1/agent-interaction/threads/resume_test/stream/events") {
      streamBodies.push(JSON.parse(body));
      res.writeHead(200, { "content-type": "text/event-stream" });
      if (streamBodies.length === 1) {
        res.end(`id: 6\ndata: ${JSON.stringify({
          type: "event",
          method: "values",
          seq: 6,
          params: { namespace: [], data: { messages: [{ id: "m1", type: "ai", content: "Hello" }] } },
        })}\n\n`);
        return;
      }
      res.write(": keepalive\n\n");
      secondHeld.then(() => res.end());
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

const vite = await createViteServer({
  root: desktopRoot,
  appType: "custom",
  server: { middlewareMode: true, hmr: false },
  logLevel: "error",
});

try {
  const { createResumingInteractionTransport } = await vite.ssrLoadModule("/src/renderer/interactionResume.ts");
  const adapter = createResumingInteractionTransport("resume_test");
  const state = await adapter.getState();
  assert.equal(state.interaction_cursor, 4);

  const stream = adapter.openEventStream({ channels: ["values"], namespaces: [[]] });
  await stream.ready;
  const deadline = Date.now() + 4000;
  while (streamBodies.length < 2 && Date.now() < deadline) {
    await new Promise((resolve) => setTimeout(resolve, 20));
  }
  assert.equal(streamBodies.length >= 2, true, `expected a reconnect, saw ${streamBodies.length} stream requests`);
  assert.equal(streamBodies[0].since, 4, "the first subscribe continues after the snapshot cursor");
  assert.equal(streamBodies[1].since, 6, "a reconnect continues after the last event, not from the start");
  stream.close();
  releaseSecond();
} finally {
  await vite.close();
  await new Promise((resolve) => server.close(resolve));
}

console.log("Interaction stream resume cursor check passed.");
