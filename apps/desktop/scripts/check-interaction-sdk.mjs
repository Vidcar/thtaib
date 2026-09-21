import assert from "node:assert/strict";
import { createServer } from "node:http";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { HttpAgentServerAdapter } from "@langchain/react";

const require = createRequire(import.meta.url);
const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../..");

const reactPackage = require("@langchain/react/package.json");
const sdkPackage = require("@langchain/langgraph-sdk/package.json");
const corePackage = require("@langchain/core/package.json");
const reactMarkdownPackage = JSON.parse(readFileSync(path.join(repoRoot, "apps/desktop/node_modules/react-markdown/package.json"), "utf8"));
const remarkGfmPackage = JSON.parse(readFileSync(path.join(repoRoot, "apps/desktop/node_modules/remark-gfm/package.json"), "utf8"));

assert.equal(reactPackage.version, "1.1.1");
assert.equal(sdkPackage.version, "1.11.1");
assert.equal(corePackage.version, "1.2.9");
assert.equal(reactMarkdownPackage.version, "10.1.0");
assert.equal(remarkGfmPackage.version, "4.0.1");
assert.equal(sdkPackage.dependencies["@langchain/protocol"], "^0.0.19");

const streamSource = readFileSync(path.join(repoRoot, "apps/desktop/src/renderer/InteractionStream.tsx"), "utf8");
assert.ok(!streamSource.includes("stream.disconnect()"), "InteractionStream must not disconnect on stream object updates");
assert.ok(streamSource.includes("new HttpAgentServerAdapter"), "desktop must use the stock adapter");
assert.ok(streamSource.includes("threadId }),"), "adapter construction must include the registered interaction thread id");
assert.ok(streamSource.includes("optimistic: true"), "SDK optimistic input must stay enabled for stable caller ids");
assert.ok(streamSource.includes("incomplete_message_ids"), "Workbench projection must expose backend incomplete message ids");

const chatSource = readFileSync(path.join(repoRoot, "apps/desktop/src/renderer/ChatPanel.tsx"), "utf8");
assert.ok(chatSource.includes("interactionThreadId"), "Chat must keep adapter thread separate from graph thread_id");
assert.ok(!chatSource.includes("const bound = { ...created, thread_id"), "Chat must not overwrite conversation.thread_id with interaction id");
assert.ok(chatSource.includes("task: inputTask"), "task must be pulled into the message input");
assert.ok(chatSource.includes("id: messageId"), "caller id must be pulled into the message input");
assert.ok(chatSource.includes("draft_revision: _draftRevision"), "UI-only draft ownership must stay out of metadata.workbench");
assert.ok(chatSource.includes("selection_generation: _selectionGeneration"), "UI-only selection ownership must stay out of metadata.workbench");
assert.ok(chatSource.includes("submittedIds.current.has(pendingSubmit.id)"), "Chat submit effect must guard StrictMode duplicate submits");
assert.ok(chatSource.includes("terminalRefreshKey.current === key"), "Chat terminal refresh must be keyed to avoid repeat fetch loops");
assert.ok(chatSource.includes("selectionRequest.current !== requestId"), "Chat selection load must ignore late async frames");
const loadRegisterBlock = chatSource.slice(chatSource.indexOf(".chatConversation(item.id)"), chatSource.indexOf("setDeploymentId(next.deployment_id)"));
assert.ok(loadRegisterBlock.includes("registerAgentInteractionThread"), "saved chat load must register an SDK interaction thread");
assert.ok(!loadRegisterBlock.includes("isAgentRunLive"), "saved chat load registration must not be limited to live runs");

const feedSource = readFileSync(path.join(repoRoot, "apps/desktop/src/renderer/AgentMessageFeed.tsx"), "utf8");
assert.ok(feedSource.includes("ReactMarkdown"), "AgentMessageFeed must use ReactMarkdown for Markdown presentation");
assert.ok(feedSource.includes("remarkGfm"), "AgentMessageFeed must enable GFM Markdown support");
assert.ok(feedSource.includes("safeHref"), "AgentMessageFeed must keep link sanitization explicit");
assert.ok(feedSource.includes("incompleteMessageIds"), "AgentMessageFeed must mark backend-reported partial messages");
assert.ok(feedSource.includes("aria-label=\"Incomplete response\""), "partial message label must be accessible and status-neutral");
assert.ok(feedSource.includes("blockType === \"reasoning\""), "reasoning blocks must render separately from answer text");
assert.ok(feedSource.includes("useFollowTranscript"), "feed must preserve near-bottom transcript follow-scroll while streaming");
assert.ok(!feedSource.includes("dangerouslySetInnerHTML"), "AgentMessageFeed must not render raw HTML");
assert.ok(!feedSource.includes("rehypeRaw"), "AgentMessageFeed must not enable raw HTML rehype plugins");

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

console.log("Interaction SDK dependency, adapter, stream, submit, and response checks passed.");
