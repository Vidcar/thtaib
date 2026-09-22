import assert from "node:assert/strict";
import { createServer } from "node:http";

import { HttpAgentServerAdapter } from "@langchain/react";

const requests = [];
let streamClosed = false;
const server = createServer((req, res) => {
  let body = "";
  req.on("data", (chunk) => {
    body += String(chunk);
  });
  req.on("end", () => {
    const url = new URL(req.url ?? "/", "http://127.0.0.1");
    requests.push({ method: req.method, path: url.pathname, body: body ? JSON.parse(body) : null });

    if (req.method === "GET" && url.pathname === "/v1/agent-interaction/threads/interaction_test/state") {
      res.writeHead(200, { "content-type": "application/json" });
      res.end(JSON.stringify({
        values: {
          messages: [{ id: "m1", type: "human", content: "hello" }],
          workbench: { run: { id: "run_1", status: "running" }, conversation_id: "chat_1" },
        },
        next: ["running"],
        tasks: [],
      }));
      return;
    }

    if (req.method === "POST" && url.pathname === "/v1/agent-interaction/threads/interaction_test/commands") {
      const command = JSON.parse(body);
      res.writeHead(200, { "content-type": "application/json" });
      res.end(JSON.stringify({ type: "success", id: command.id, result: { run_id: "run_1", applied_through_seq: 3 } }));
      return;
    }

    if (req.method === "POST" && url.pathname === "/v1/agent-interaction/threads/interaction_test/stream/events") {
      res.writeHead(200, { "content-type": "text/event-stream" });
      res.write(`data: ${JSON.stringify({
        type: "event",
        method: "values",
        params: {
          namespace: [],
          data: {
            messages: [{ id: "m1", type: "human", content: "hello" }, { id: "m2", type: "ai", content: "world" }],
            workbench: { run: { id: "run_1", status: "completed" }, conversation_id: "chat_1" },
          },
        },
      })}\n\n`);
      res.end();
      req.on("close", () => {
        streamClosed = true;
      });
      return;
    }

    res.writeHead(404, { "content-type": "application/json" });
    res.end(JSON.stringify({ error: "missing" }));
  });
});

await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
const address = server.address();
const port = typeof address === "object" && address ? address.port : 0;
const apiUrl = `http://127.0.0.1:${port}/v1/agent-interaction`;

try {
  const adapter = new HttpAgentServerAdapter({ apiUrl, threadId: "interaction_test" });
  assert.equal(adapter.threadId, "interaction_test");

  const state = await adapter.getState?.();
  assert.equal(state?.values.workbench.conversation_id, "chat_1");

  const stream = adapter.openEventStream({ channels: ["values"], namespaces: [[]] });
  await stream.ready;
  const iterator = stream.events[Symbol.asyncIterator]();
  const first = await iterator.next();
  assert.equal(first.value.method, "values");
  assert.equal(first.value.params.data.messages.at(-1).content, "world");
  await iterator.return?.();
  assert.equal(streamClosed, true, "event stream should close only when explicitly closed");

  const submit = await adapter.send({
    id: "cmd_submit",
    method: "run.start",
    params: {
      input: { messages: [{ type: "human", id: "stable-message-id", content: "hello" }] },
      metadata: { workbench: { deployment_id: "deploy_1", project_path: null } },
    },
  });
  assert.equal(submit?.result.run_id, "run_1");

  const respond = await adapter.send({
    id: "cmd_respond",
    method: "input.respond",
    params: { interrupt_id: "interrupt_1", namespace: [], response: { decisions: [{ type: "approve" }] } },
  });
  assert.equal(respond?.result.run_id, "run_1");

  const commandBodies = requests.filter((item) => item.path.endsWith("/commands")).map((item) => item.body);
  assert.equal(commandBodies[0].params.input.messages[0].id, "stable-message-id");
  assert.deepEqual(commandBodies[0].params.metadata.workbench, { deployment_id: "deploy_1", project_path: null });
  assert.equal("task" in commandBodies[0].params.metadata.workbench, false);
  assert.deepEqual(commandBodies[1].params.response, { decisions: [{ type: "approve" }] });
} finally {
  await new Promise((resolve) => server.close(resolve));
}

console.log("Interaction SDK adapter, stream, submit, and response checks passed.");
