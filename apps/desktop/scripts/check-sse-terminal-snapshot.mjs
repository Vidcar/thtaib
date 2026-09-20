import assert from "node:assert/strict";
import { mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { fileURLToPath, pathToFileURL } from "node:url";
import path from "node:path";
import ts from "typescript";

const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../..");
const desktopRoot = path.join(repoRoot, "apps/desktop");
const scratchRoot = path.join(repoRoot, ".scratch/desktop-sse-check");
const compiledPath = path.join(scratchRoot, "sse.mjs");

function compileSseModule() {
  rmSync(scratchRoot, { recursive: true, force: true });
  mkdirSync(scratchRoot, { recursive: true });
  const source = readFileSync(path.join(desktopRoot, "src/renderer/sse.ts"), "utf8");
  const output = ts.transpileModule(source, {
    compilerOptions: {
      module: ts.ModuleKind.ES2022,
      target: ts.ScriptTarget.ES2022,
      verbatimModuleSyntax: false,
    },
  });
  const js = output.outputText
    .replaceAll('from "./sharedContracts";', 'from "./sharedContracts.mjs";')
    .replaceAll('from "./types";', 'from "./types.mjs";');
  writeFileSync(compiledPath, js);
  writeFileSync(path.join(scratchRoot, "sharedContracts.mjs"), "export {};\n");
  writeFileSync(path.join(scratchRoot, "types.mjs"), "export {};\n");
}

function sseBlock(event, envelope, id) {
  const idLine = id == null ? "" : `id: ${id}\n`;
  return `${idLine}event: ${event}\ndata: ${JSON.stringify(envelope)}\n\n`;
}

function streamFromBlocks(blocks) {
  const encoder = new TextEncoder();
  return new ReadableStream({
    start(controller) {
      for (const block of blocks) {
        controller.enqueue(encoder.encode(block));
      }
      controller.close();
    },
  });
}

function streamResponse(body) {
  return {
    ok: true,
    body,
    async json() {
      return {};
    },
  };
}

function conversation({ id, roles }) {
  return {
    id,
    current_run: { id: "agent_done", status: "completed", events: [] },
    transcript: roles.map((role, index) => ({
      role,
      content: `${role}-${index}`,
      at: "2026-09-20T12:00:00Z",
      run_id: role === "assistant" ? "agent_done" : null,
    })),
  };
}

async function testTerminalSnapshotHydratesFinalTranscript(api) {
  const observed = [];
  const finalConversation = conversation({ id: "chat_done", roles: ["user", "assistant"] });
  const liveSnapshot = conversation({ id: "chat_done", roles: ["user"] });
  liveSnapshot.current_run = { id: "agent_done", status: "running", events: [] };

  globalThis.window = {
    workbench: { backendUrl: "http://127.0.0.1:8000" },
    setTimeout,
    clearTimeout,
  };
  globalThis.fetch = async (url) => {
    const text = String(url);
    if (text.includes("/v1/events")) {
      return streamResponse(
        streamFromBlocks([
          sseBlock("snapshot", { type: "snapshot", snapshot: liveSnapshot, status: "running" }),
          sseBlock(
            "run_event",
            {
              type: "run_event",
              seq: 1,
              status: "completed",
              event: { at: "2026-09-20T12:00:01Z", kind: "completed", detail: {} },
            },
            1,
          ),
          sseBlock("stream_end", { type: "stream_end", status: "completed" }),
        ]),
      );
    }
    assert.equal(text, "http://127.0.0.1:8000/v1/chat/conversations/chat_done");
    return {
      ok: true,
      async json() {
        return finalConversation;
      },
    };
  };

  await api.subscribeWorkbenchEvents({
    conversationId: "chat_done",
    signal: new AbortController().signal,
    apply: api.applyConversationEvent,
    onRecord: (record) => observed.push(record),
    terminalSnapshot: (signal) => api.fetchConversationSnapshot("chat_done", signal),
  });

  assert.deepEqual(
    observed.at(-1).transcript.map((item) => item.role),
    ["user", "assistant"],
    "normal stream_end must deliver the final persisted transcript",
  );
}

async function testAbortDoesNotDeliverStaleTerminalSnapshot(api) {
  const observed = [];
  const controller = new AbortController();

  globalThis.window = {
    workbench: { backendUrl: "http://127.0.0.1:8000" },
    setTimeout,
    clearTimeout,
  };
  globalThis.fetch = async (url) => {
    const text = String(url);
    if (text.includes("/v1/events")) {
      return streamResponse(
        streamFromBlocks([
          sseBlock("snapshot", {
            type: "snapshot",
            snapshot: conversation({ id: "chat_old", roles: ["user"] }),
            status: "running",
          }),
          sseBlock("stream_end", { type: "stream_end", status: "completed" }),
        ]),
      );
    }
    assert.fail(`terminal snapshot fetch should not run after abort, got ${text}`);
  };

  await api.subscribeWorkbenchEvents({
    conversationId: "chat_old",
    signal: controller.signal,
    apply: api.applyConversationEvent,
    onRecord: (record) => {
      observed.push(record);
      controller.abort();
    },
    terminalSnapshot: (signal) => api.fetchConversationSnapshot("chat_old", signal),
  });

  assert.equal(observed.length, 1, "aborting after switch must not deliver a stale final snapshot");
  assert.deepEqual(observed[0].transcript.map((item) => item.role), ["user"]);
}

async function testAbortDuringTerminalSnapshotDoesNotDeliver(api) {
  const observed = [];
  const controller = new AbortController();
  let resolveTerminal;
  const terminalStarted = new Promise((resolve) => {
    resolveTerminal = resolve;
  });

  globalThis.window = {
    workbench: { backendUrl: "http://127.0.0.1:8000" },
    setTimeout,
    clearTimeout,
  };
  globalThis.fetch = async (url) => {
    const text = String(url);
    if (text.includes("/v1/events")) {
      return streamResponse(
        streamFromBlocks([
          sseBlock("snapshot", {
            type: "snapshot",
            snapshot: conversation({ id: "chat_slow", roles: ["user"] }),
            status: "running",
          }),
          sseBlock("stream_end", { type: "stream_end", status: "completed" }),
        ]),
      );
    }
    assert.equal(text, "http://127.0.0.1:8000/v1/chat/conversations/chat_slow");
    resolveTerminal();
    await new Promise((resolve) => setTimeout(resolve, 0));
    return {
      ok: true,
      async json() {
        return conversation({ id: "chat_slow", roles: ["user", "assistant"] });
      },
    };
  };

  const subscribed = api.subscribeWorkbenchEvents({
    conversationId: "chat_slow",
    signal: controller.signal,
    apply: api.applyConversationEvent,
    onRecord: (record) => observed.push(record),
    terminalSnapshot: (signal) => api.fetchConversationSnapshot("chat_slow", signal),
  });
  await terminalStarted;
  controller.abort();
  await subscribed;

  assert.equal(observed.length, 1, "abort during terminal snapshot must not deliver final state");
  assert.deepEqual(observed[0].transcript.map((item) => item.role), ["user"]);
}

compileSseModule();
const api = await import(pathToFileURL(compiledPath).href);
await testTerminalSnapshotHydratesFinalTranscript(api);
await testAbortDoesNotDeliverStaleTerminalSnapshot(api);
await testAbortDuringTerminalSnapshotDoesNotDeliver(api);
// Exercise the actual request serializer: null clears; omission preserves.
const requestSource = readFileSync(path.join(desktopRoot, "src/renderer/api.ts"), "utf8");
const requestJs = ts.transpileModule(requestSource, {
  compilerOptions: { module: ts.ModuleKind.ES2022, target: ts.ScriptTarget.ES2022 },
}).outputText.replaceAll('from "./sse";', 'from "./sse.mjs";');
const requestPath = path.join(scratchRoot, "api.mjs");
writeFileSync(requestPath, requestJs);
const { api: requests } = await import(pathToFileURL(requestPath).href);
const posted = [];
globalThis.fetch = async (_url, init) => {
  posted.push(JSON.parse(init.body));
  return { ok: true, json: async () => ({}) };
};
await requests.startChat("chat_clear", {
  task: "clear", profile_id: null, project_path: null, embedding_deployment_id: null,
});
await requests.startChat("chat_keep", { task: "keep" });
assert.deepEqual(posted, [
  { task: "clear", profile_id: null, project_path: null, embedding_deployment_id: null },
  { task: "keep" },
]);
console.log("SSE terminal snapshot behavior check passed.");
