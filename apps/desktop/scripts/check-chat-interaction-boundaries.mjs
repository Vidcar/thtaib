import assert from "node:assert/strict";
import { createServer } from "node:http";
import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import React, { StrictMode } from "react";
import { act, create } from "react-test-renderer";
import { createServer as createViteServer } from "vite";

const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../..");
const desktopRoot = path.join(repoRoot, "apps/desktop");
const chatPanelSourceOverride = process.env.CHAT_PANEL_SOURCE_OVERRIDE;
const aggregateCases = process.env.CHAT_PANEL_AGGREGATE === "1";
const reproduceProjectionLeak = process.env.CHAT_PANEL_REPRODUCE_PROJECTION_LEAK === "1";
const originalFetch = globalThis.fetch;

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

class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { error: null };
  }

  componentDidCatch(error) {
    this.setState({ error });
  }

  render() {
    if (this.state.error) {
      return React.createElement("pre", { "data-error": true }, this.state.error.stack ?? String(this.state.error));
    }
    return this.props.children;
  }
}

function deferred() {
  let resolve;
  let reject;
  const promise = new Promise((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

function now() {
  return "2026-09-21T12:00:00.000Z";
}

function run(id, status = "running", inputMessageId = null, messageContent = "stream") {
  return {
    id,
    input_message_id: inputMessageId,
    messageContent,
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

function conversation(id, title, currentRun = null, overrides = {}) {
  return {
    id,
    title,
    created_at: now(),
    updated_at: now(),
    deployment_id: "dep_1",
    profile_id: null,
    inherit_deployment_settings: true,
    project_path: null,
    workspace_id: null,
    thread_id: null,
    enabled_tools: ["echo"],
    memory_version_refs: [],
    skill_version_refs: [],
    protected_instruction_version_refs: [],
    knowledge_version_refs: [],
    embedding_deployment_id: null,
    retrieval_project_paths: [],
    filesystem_tools_available: false,
    shell_tools_available: false,
    deploy_health: null,
    transcript: [{ id: `${id}_user`, role: "user", content: title, at: now(), run_id: null, content_blocks: [] }],
    history_replaced: false,
    harness: "deepagents",
    second_agent_loop: false,
    source_surface: "chat",
    events: [],
    current_run: currentRun,
    current_run_id: currentRun?.id ?? null,
    run_ids: currentRun ? [currentRun.id] : [],
    pending_cancel_input_ids: [],
    ...overrides,
  };
}

const baseDeployment = {
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
};

const stoppedManagedDeployment = {
  ...baseDeployment,
  display_name: "managed:test",
  status: "stopped",
  scope: "managed",
};

function json(res, status, body) {
  res.writeHead(status, { "content-type": "application/json" });
  res.end(JSON.stringify(body));
}

function sse(res, frames = []) {
  res.writeHead(200, { "content-type": "text/event-stream" });
  for (const frame of frames) {
    res.write(`data: ${JSON.stringify(frame)}\n\n`);
  }
  res.end();
}

function streamFrame(runValue, content = "stream") {
  return {
    type: "event",
    method: "values",
    params: {
      namespace: [],
      data: {
        messages: [{ id: `${runValue.id}_message`, type: "ai", content: runValue.messageContent ?? content }],
        workbench: { run: runValue },
      },
    },
  };
}

function makeHarness(options = {}) {
  const aRun = Object.hasOwn(options, "aRun") ? options.aRun : run("run_a");
  const bRun = Object.hasOwn(options, "bRun") ? options.bRun : null;
  const threadARun = Object.hasOwn(options, "threadARun") ? options.threadARun : aRun;
  const threadBRun = Object.hasOwn(options, "threadBRun") ? options.threadBRun : bRun ?? run("run_b");
  const threadNewRun = Object.hasOwn(options, "threadNewRun") ? options.threadNewRun : run("run_new");
  const state = {
    conversations: {
      conv_a: conversation("conv_a", "Conversation A", aRun),
      conv_b: conversation("conv_b", "Conversation B", bRun),
    },
    createdConversation: conversation("conv_new", "New conversation", null),
    requests: {
      commands: [],
      registers: [],
      cancels: [],
      streams: [],
      states: [],
      chatGets: [],
      draftUpdates: [],
      searches: [],
      renames: [],
      archives: [],
      queues: [],
      chatCancels: [],
      closedStreams: [],
    },
    barriers: {
      chatConversation: new Map(),
      register: new Map(),
      command: new Map(),
      cancel: new Map(),
      chatCancel: new Map(),
    },
    queuedConversationResponses: new Map(),
    consumedResponses: [],
    outgoingRequests: [],
    openStreams: new Map(),
    allStreams: new Map(),
    completeCommands: options.completeCommands ?? false,
    commandProjectsRun: options.commandProjectsRun ?? false,
    commandRejects: options.commandRejects ?? false,
    commandRejectAcceptsRun: options.commandRejectAcceptsRun ?? false,
    projectedRunIndex: 0,
    threadByConversation: new Map([
      ["conv_a", "thread_a"],
      ["conv_b", "thread_b"],
      ["conv_new", "thread_new"],
    ]),
    streamRuns: new Map([
      ["thread_a", threadARun],
      ["thread_b", threadBRun],
      ["thread_new", threadNewRun],
    ]),
    chatGetCounts: new Map(),
    deploymentRequests: 0,
  };

  const server = createServer((req, res) => {
    let body = "";
    req.on("data", (chunk) => {
      body += String(chunk);
    });
    req.on("end", async () => {
      const url = new URL(req.url ?? "/", "http://127.0.0.1");
      try {
        if (req.method === "GET" && url.pathname === "/v1/deployments") {
          state.deploymentRequests += 1;
          const override = typeof options.deployments === "function"
            ? options.deployments(state.deploymentRequests)
            : options.deployments;
          json(res, 200, override ?? [baseDeployment]);
          return;
        }
        if (req.method === "GET" && url.pathname === "/v1/profiles") {
          json(res, 200, []);
          return;
        }
        if (req.method === "GET" && url.pathname === "/v1/agent-tools") {
          json(res, 200, { enabled: ["echo"] });
          return;
        }
        if (req.method === "GET" && url.pathname === "/v1/knowledge/entries") {
          json(res, 200, []);
          return;
        }
        if (req.method === "GET" && url.pathname === "/v1/chat/conversations") {
          json(res, 200, [state.conversations.conv_a, state.conversations.conv_b]);
          return;
        }
        if (req.method === "GET" && url.pathname === "/v1/chat/conversations/search") {
          const query = (url.searchParams.get("q") ?? "").toLowerCase();
          state.requests.searches.push(query);
          const matches = Object.values(state.conversations)
            .filter((item) => {
              const haystack = [item.title, ...item.transcript.map((message) => message.content)].join(" ").toLowerCase();
              return haystack.includes(query);
            })
            .map((item) => ({ conversation: item, matched_messages: item.transcript }));
          json(res, 200, matches);
          return;
        }
        const conversationMatch = url.pathname.match(/^\/v1\/chat\/conversations\/([^/]+)$/);
        if (req.method === "GET" && conversationMatch) {
          const id = conversationMatch[1];
          const count = (state.chatGetCounts.get(id) ?? 0) + 1;
          state.chatGetCounts.set(id, count);
          state.requests.chatGets.push({ id, count });
          const responseConversation = state.queuedConversationResponses.get(`${id}:${count}`) ?? state.conversations[id];
          const barrier = state.barriers.chatConversation.get(`${id}:${count}`) ?? state.barriers.chatConversation.get(id);
          if (barrier) {
            await barrier.promise;
          }
          json(res, 200, responseConversation);
          return;
        }
        if (req.method === "PATCH" && conversationMatch) {
          const id = conversationMatch[1];
          const payload = body ? JSON.parse(body) : {};
          state.requests.renames.push({ id, title: payload.title });
          state.conversations[id] = { ...state.conversations[id], title: payload.title, updated_at: now() };
          json(res, 200, state.conversations[id]);
          return;
        }
        const archiveMatch = url.pathname.match(/^\/v1\/chat\/conversations\/([^/]+)\/archive$/);
        if (req.method === "POST" && archiveMatch) {
          const id = archiveMatch[1];
          const payload = body ? JSON.parse(body) : {};
          state.requests.archives.push({ id, archived: payload.archived });
          state.conversations[id] = {
            ...state.conversations[id],
            archived: payload.archived === true,
            archived_at: payload.archived === true ? now() : null,
            updated_at: now(),
          };
          json(res, 200, state.conversations[id]);
          return;
        }
        const chatCancelMatch = url.pathname.match(/^\/v1\/chat\/conversations\/([^/]+)\/cancel$/);
        if (req.method === "POST" && chatCancelMatch) {
          const id = chatCancelMatch[1];
          const payload = body ? JSON.parse(body) : {};
          state.requests.chatCancels.push({ id, payload });
          const barrier = state.barriers.chatCancel.get(id);
          if (barrier) {
            await barrier.promise;
          }
          const current = state.conversations[id];
          if (!current) {
            json(res, 404, { error: "Unknown conversation" });
            return;
          }
          json(res, 200, current);
          return;
        }
        const reopenMatch = url.pathname.match(/^\/v1\/chat\/conversations\/([^/]+)\/reopen$/);
        if (req.method === "POST" && reopenMatch) {
          const id = reopenMatch[1];
          state.requests.archives.push({ id, archived: false });
          state.conversations[id] = { ...state.conversations[id], archived: false, archived_at: null, updated_at: now() };
          json(res, 200, state.conversations[id]);
          return;
        }
        const draftMatch = url.pathname.match(/^\/v1\/chat\/conversations\/([^/]+)\/draft$/);
        if (req.method === "PUT" && draftMatch) {
          const id = draftMatch[1];
          const payload = body ? JSON.parse(body) : {};
          state.requests.draftUpdates.push({ id, payload });
          const current = state.conversations[id];
          if (!current) {
            json(res, 404, { error: "Unknown conversation" });
            return;
          }
          const revision = (current.draft?.revision ?? 0) + 1;
          state.conversations[id] = {
            ...current,
            draft: {
              content: payload.content ?? "",
              content_blocks: payload.content_blocks ?? null,
              intended_config: payload.intended_config ?? {},
              revision,
              updated_at: now(),
            },
          };
          json(res, 200, state.conversations[id]);
          return;
        }
        const queueMatch = url.pathname.match(/^\/v1\/chat\/conversations\/([^/]+)\/queue$/);
        if (req.method === "POST" && queueMatch) {
          const id = queueMatch[1];
          const payload = body ? JSON.parse(body) : {};
          state.requests.queues.push({ id, payload });
          const current = state.conversations[id];
          const item = {
            id: `queue_${state.requests.queues.length}`,
            task: payload.task,
            content_blocks: payload.content_blocks ?? null,
            intended_config: payload,
            frozen_config: payload,
            input_message_id: payload.input_message_id ?? null,
            output_schema: null,
            status: "queued",
            pause_reason: null,
            created_at: now(),
            updated_at: now(),
          };
          state.conversations[id] = { ...current, queue: [...(current.queue ?? []), item], updated_at: now() };
          json(res, 200, state.conversations[id]);
          return;
        }
        if (req.method === "POST" && url.pathname === "/v1/chat/conversations") {
          const barrier = state.barriers.chatConversation.get("create");
          if (barrier) {
            await barrier.promise;
          }
          json(res, 200, state.createdConversation);
          return;
        }
        if (req.method === "POST" && url.pathname === "/v1/agent-interaction/threads") {
          const payload = body ? JSON.parse(body) : {};
          state.requests.registers.push(payload);
          const conversationId = payload.conversation_id ?? "agent";
          const barrier = state.barriers.register.get(conversationId);
          if (barrier) {
            await barrier.promise;
          }
          json(res, 200, { thread_id: state.threadByConversation.get(conversationId) ?? "thread_agent" });
          return;
        }
        const stateMatch = url.pathname.match(/^\/v1\/agent-interaction\/threads\/([^/]+)\/state$/);
        if (req.method === "GET" && stateMatch) {
          const threadId = stateMatch[1];
          state.requests.states.push(threadId);
          const runValue = state.streamRuns.get(threadId) ?? null;
          json(res, 200, {
            values: {
              messages: runValue ? [{ id: `${runValue.id}_message`, type: "ai", content: runValue.messageContent ?? "stream" }] : [],
              workbench: { run: runValue },
            },
            next: runValue && ["queued", "running", "cancel_requested"].includes(runValue.status) ? ["agent"] : [],
            tasks: [],
          });
          return;
        }
        const streamMatch = url.pathname.match(/^\/v1\/agent-interaction\/threads\/([^/]+)\/stream\/events$/);
        if (req.method === "POST" && streamMatch) {
          const threadId = streamMatch[1];
          state.requests.streams.push(threadId);
          const runValue = state.streamRuns.get(threadId);
          res.writeHead(200, { "content-type": "text/event-stream" });
          if (runValue) {
            res.write(`data: ${JSON.stringify(streamFrame(runValue))}\n\n`);
          }
          state.openStreams.set(threadId, res);
          state.allStreams.set(res, threadId);
          if (state.completeCommands && runValue?.status === "completed") {
            res.write(`data: ${JSON.stringify({ type: "event", method: "lifecycle", params: { namespace: [], data: { event: "completed", run_id: runValue.id } } })}\n\n`);
          }
          res.on("close", () => {
            state.allStreams.delete(res);
            if (state.openStreams.get(threadId) === res) {
              state.openStreams.delete(threadId);
            }
            state.requests.closedStreams.push(threadId);
          });
          return;
        }
        const commandMatch = url.pathname.match(/^\/v1\/agent-interaction\/threads\/([^/]+)\/commands$/);
        if (req.method === "POST" && commandMatch) {
          const threadId = commandMatch[1];
          const payload = body ? JSON.parse(body) : {};
          state.requests.commands.push({ threadId, payload });
          const message = payload.params?.input?.messages?.[0];
          if (state.commandRejects) {
            const conversationId = [...state.threadByConversation.entries()].find(([, value]) => value === threadId)?.[0];
            let accepted = null;
            if (conversationId && state.conversations[conversationId]) {
              const current = state.conversations[conversationId];
              accepted = state.commandRejectAcceptsRun ? run("run_accepted_after_error", "running", message?.id ?? null, "accepted after error") : null;
              state.conversations[conversationId] = {
                ...current,
                transcript: [
                  ...current.transcript,
                  { id: message?.id ?? "input_failed", role: "user", content: message?.content ?? "", at: now(), run_id: accepted?.id ?? null, content_blocks: [] },
                ],
                current_run: accepted,
                current_run_id: accepted?.id ?? null,
                run_ids: accepted ? [...current.run_ids, accepted.id] : current.run_ids,
                updated_at: now(),
              };
              if (accepted) {
                state.streamRuns.set(threadId, accepted);
              }
            }
            const barrier = state.barriers.command.get(threadId);
            if (barrier) {
              await barrier.promise;
            }
            if (accepted) {
              const stream = state.openStreams.get(threadId);
              stream?.write(`data: ${JSON.stringify(streamFrame(accepted))}\n\n`);
            }
            json(res, 409, {
              type: "error",
              id: payload.id ?? "cmd",
              error: "model_start_failed",
              message: "Model startup failed before a run was accepted.",
            });
            return;
          }
          if (state.commandProjectsRun) {
            state.projectedRunIndex += 1;
            const projected = run(
              `run_projected_${state.projectedRunIndex}`,
              "completed",
              message?.id ?? null,
              `accepted ${state.projectedRunIndex}`,
            );
            state.streamRuns.set(threadId, projected);
            const conversationId = [...state.threadByConversation.entries()].find(([, value]) => value === threadId)?.[0];
            if (conversationId && state.conversations[conversationId]) {
              state.conversations[conversationId] = {
                ...state.conversations[conversationId],
                current_run: projected,
                current_run_id: projected.id,
                run_ids: state.conversations[conversationId].run_ids.includes(projected.id)
                  ? state.conversations[conversationId].run_ids
                  : [...state.conversations[conversationId].run_ids, projected.id],
              };
            }
            const stream = state.openStreams.get(threadId);
            stream?.write(`data: ${JSON.stringify(streamFrame(projected))}\n\n`);
          }
          const barrier = state.barriers.command.get(threadId);
          if (barrier) {
            await barrier.promise;
          }
          json(res, 200, { type: "success", id: payload.id ?? "cmd", result: {} });
          if (state.completeCommands) {
            for (const [response, owner] of state.allStreams) {
              if (owner === threadId) {
                response.write(`data: ${JSON.stringify({ type: "event", method: "lifecycle", params: { namespace: [], data: { event: "completed", run_id: state.streamRuns.get(threadId)?.id } } })}\n\n`);
              }
            }
          }
          return;
        }
        const cancelMatch = url.pathname.match(/^\/v1\/agent-runs\/([^/]+)\/cancel$/);
        if (req.method === "POST" && cancelMatch) {
          const runId = cancelMatch[1];
          state.requests.cancels.push(runId);
          const barrier = state.barriers.cancel.get(runId);
          if (barrier) {
            await barrier.promise;
          }
          json(res, 200, run(runId, "cancel_requested"));
          return;
        }
        json(res, 404, { error: `${req.method} ${url.pathname}` });
      } catch (error) {
        json(res, 500, { error: error instanceof Error ? error.message : String(error) });
      }
    });
  });

  return { server, state };
}

async function renderChat(vite, harness) {
  await new Promise((resolve) => harness.server.listen(0, "127.0.0.1", resolve));
  const address = harness.server.address();
  const port = typeof address === "object" && address ? address.port : 0;
  globalThis.fetch = async (input, init) => {
    const target = new URL(typeof input === "string" || input instanceof URL ? input : input.url);
    const request = { path: target.pathname, method: init?.method ?? "GET" };
    harness.state.outgoingRequests.push(request);
    const response = await originalFetch(input, init);
    const readJson = response.json.bind(response);
    response.json = async () => {
      const result = await readJson();
      harness.state.consumedResponses.push(request);
      return result;
    };
    return response;
  };
  globalThis.window = {
    workbench: { backendUrl: `http://127.0.0.1:${port}` },
    setInterval,
    clearInterval,
  };
  const { ChatPanel } = await vite.ssrLoadModule("/src/renderer/ChatPanel.tsx");
  let renderer;
  await act(async () => {
    renderer = create(React.createElement(StrictMode, null, React.createElement(ErrorBoundary, null, React.createElement(ChatPanel))));
    await Promise.resolve();
  });
  await act(async () => {
    await Promise.resolve();
  });
  return renderer;
}

async function closeHarness(renderer, harness) {
  await act(async () => {
    renderer.unmount();
  });
  for (const stream of harness.state.allStreams.keys()) {
    stream.end();
  }
  harness.state.openStreams.clear();
  harness.state.allStreams.clear();
  harness.server.closeAllConnections?.();
  await new Promise((resolve) => harness.server.close(resolve));
  globalThis.fetch = originalFetch;
}

async function releaseResponse(harness, barrier, path, method = "GET") {
  const count = () => harness.state.consumedResponses.filter(item => item.path === path && item.method === method).length;
  const before = count();
  barrier.resolve();
  await waitFor(() => assert.ok(count() > before), `consumed delayed ${method} ${path}`);
  await flush();
}

function selectedRunId(renderer) {
  const progress = renderer.root.findAll(node => typeof node.type === "function" && node.type.name === "RunProgress");
  return progress[0]?.props.run?.id ?? null;
}

function buttons(renderer, label) {
  return renderer.root.findAll((node) => node.type === "button" && textOf(node).includes(label));
}

function button(renderer, label) {
  const found = buttons(renderer, label);
  assert.ok(found.length > 0, `expected button ${label}`);
  return found[0];
}

function activeConversationTitle(renderer) {
  const found = renderer.root.findAll(
    (node) => node.type === "button" && typeof node.props.className === "string" && node.props.className.includes("active"),
  );
  assert.equal(found.length, 1, `expected one active conversation, saw ${found.length}`);
  return textOf(found[0]);
}

function textarea(renderer) {
  const found = renderer.root.findAll((node) => node.type === "textarea");
  assert.ok(found.length > 0, "expected textarea");
  return found[0];
}

function inputByPlaceholder(renderer, placeholder) {
  const found = renderer.root.findAll((node) => node.type === "input" && node.props.placeholder === placeholder);
  assert.ok(found.length > 0, `expected input ${placeholder}`);
  return found[0];
}

function composeForm(renderer) {
  const found = renderer.root.findAll((node) => node.type === "form" && node.props.className === "compose");
  assert.ok(found.length > 0, "expected compose form");
  return found[0];
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

async function flush() {
  await act(async () => {
    await Promise.resolve();
  });
}

async function waitFor(assertion, label) {
  let lastError;
  const deadline = Date.now() + 3000;
  while (Date.now() < deadline) {
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

async function testHeldRegistrationDoesNotBindOldThread(vite) {
  const heldRegister = deferred();
  const harness = makeHarness();
  harness.state.barriers.register.set("conv_b", heldRegister);
  const renderer = await renderChat(vite, harness);
  try {
    await waitFor(() => button(renderer, "Conversation A"), "initial chat list");
    await act(async () => {
      button(renderer, "Conversation A").props.onClick();
      await Promise.resolve();
    });
    await waitFor(() => assert.equal(harness.state.requests.registers.at(-1)?.conversation_id, "conv_a"), "A registration");
    await waitFor(() => assert.match(allText(renderer), /Run progress/i), "A run projection");
    await waitFor(() => assert.ok(harness.state.openStreams.has("thread_a"), JSON.stringify(harness.state.requests) + allText(renderer)), "A subscription connected");
    const oldAStream = harness.state.openStreams.get("thread_a");
    assert.ok(oldAStream, "A has a real subscription before navigation");

    await act(async () => {
      button(renderer, "Conversation B").props.onClick();
      await Promise.resolve();
    });
    await flush();
    await waitFor(() => assert.equal(harness.state.requests.registers.at(-1)?.conversation_id, "conv_b"), "B held registration started");
    assert.match(activeConversationTitle(renderer), /Conversation B/, "held B registration should mark B as the pending selection");
    assert.match(allText(renderer), /Loading conversation/, "held B registration should show a safe loading state");
    assert.equal(harness.state.openStreams.has("thread_a"), false, "A stream must not remain attached while B registration is held");
    // Keep the originating server response even after the client detaches.
    // The producer attempts a real late write; looking it up after removal
    // would silently skip the event this regression is meant to exercise.
    oldAStream.write(`data: ${JSON.stringify(streamFrame(run("run_a_late"), "late A frame"))}\n\n`);
    await flush();
    assert.doesNotMatch(allText(renderer), /late A frame/i, "late A stream frames must not attach while B registration is held");
    assert.doesNotMatch(allText(renderer), /Run progress/i, "loading selection must not keep A's live transport mounted");

    await releaseResponse(harness, heldRegister, "/v1/agent-interaction/threads", "POST");
    await waitFor(() => assert.match(activeConversationTitle(renderer), /Conversation B/), "B selected after registration");
    assert.doesNotMatch(allText(renderer), /Run progress/i, "B must not render A's run after B registration completes");
    assert.equal(harness.state.requests.registers.at(-1).conversation_id, "conv_b");
  } finally {
    heldRegister.resolve();
    await closeHarness(renderer, harness);
  }
}

async function testTerminalHydrationCannotReselectAfterNew(vite) {
  const terminalRun = run("run_a_done", "completed");
  const heldHydration = deferred();
  const harness = makeHarness({ aRun: terminalRun, threadARun: terminalRun });
  harness.state.barriers.chatConversation.set("conv_a:2", heldHydration);
  const renderer = await renderChat(vite, harness);
  try {
    await waitFor(() => button(renderer, "Conversation A"), "initial chat list");
    await act(async () => {
      button(renderer, "Conversation A").props.onClick();
      await Promise.resolve();
    });
    await flush();
    await waitFor(() => assert.ok((harness.state.chatGetCounts.get("conv_a") ?? 0) >= 2), "terminal hydration request");
    await act(async () => {
      button(renderer, "New").props.onClick();
      await Promise.resolve();
    });
    await flush();
    assert.match(allText(renderer), /Start a conversation/i, "New should clear active selection");
    await releaseResponse(harness, heldHydration, "/v1/chat/conversations/conv_a", "GET");
    assert.match(allText(renderer), /Start a conversation/i, "late terminal hydration must not reselect A");
  } finally {
    heldHydration.resolve();
    await closeHarness(renderer, harness);
  }
}

async function testTerminalHydrationCannotReselectAfterB(vite) {
  const terminalRun = run("run_a_done", "completed");
  const heldHydration = deferred();
  const harness = makeHarness({ aRun: terminalRun, threadARun: terminalRun });
  harness.state.barriers.chatConversation.set("conv_a:2", heldHydration);
  const renderer = await renderChat(vite, harness);
  try {
    await waitFor(() => button(renderer, "Conversation A"), "initial chat list");
    await act(async () => {
      button(renderer, "Conversation A").props.onClick();
      await Promise.resolve();
    });
    await waitFor(() => assert.ok((harness.state.chatGetCounts.get("conv_a") ?? 0) >= 2), "terminal hydration request");
    await act(async () => {
      button(renderer, "Conversation B").props.onClick();
      await Promise.resolve();
    });
    await waitFor(() => assert.match(activeConversationTitle(renderer), /Conversation B/), "B selected before stale hydration release");
    await releaseResponse(harness, heldHydration, "/v1/chat/conversations/conv_a", "GET");
    assert.match(activeConversationTitle(renderer), /Conversation B/, "late terminal hydration must not reselect A after selecting B");
  } finally {
    heldHydration.resolve();
    await closeHarness(renderer, harness);
  }
}

async function testTerminalHydrationAwayBackSameConversationGeneration(vite) {
  const terminalRun = run("run_a_done", "completed");
  const heldHydration = deferred();
  const harness = makeHarness({ aRun: terminalRun, threadARun: terminalRun });
  harness.state.barriers.chatConversation.set("conv_a:2", heldHydration);
  const renderer = await renderChat(vite, harness);
  try {
    await waitFor(() => button(renderer, "Conversation A"), "initial chat list");
    await act(async () => {
      button(renderer, "Conversation A").props.onClick();
      await Promise.resolve();
    });
    await waitFor(() => assert.ok((harness.state.chatGetCounts.get("conv_a") ?? 0) >= 2), "terminal hydration request");
    await act(async () => {
      button(renderer, "New").props.onClick();
      await Promise.resolve();
    });
    const newerRun = run("run_a_newer", "completed");
    harness.state.conversations.conv_a = conversation("conv_a", "Conversation A", newerRun);
    harness.state.streamRuns.set("thread_a", newerRun);
    await act(async () => {
      button(renderer, "Conversation A").props.onClick();
      await Promise.resolve();
    });
    await waitFor(() => assert.match(activeConversationTitle(renderer), /Conversation A/), "A reselected with newer generation");
    await waitFor(() => assert.equal(selectedRunId(renderer), newerRun.id), "newer A run selected");
    await releaseResponse(harness, heldHydration, "/v1/chat/conversations/conv_a", "GET");
    assert.match(activeConversationTitle(renderer), /Conversation A/, "old away/back hydration must not disrupt the newer A selection generation");
    assert.equal(selectedRunId(renderer), newerRun.id, "old generation hydration must not replace the newer A run");
  } finally {
    heldHydration.resolve();
    await closeHarness(renderer, harness);
  }
}

async function testCancelResponseCannotReselectAfterSwitch(vite) {
  const heldCancel = deferred();
  const harness = makeHarness();
  harness.state.barriers.cancel.set("run_a", heldCancel);
  const renderer = await renderChat(vite, harness);
  try {
    await waitFor(() => button(renderer, "Conversation A"), "initial chat list");
    await act(async () => {
      button(renderer, "Conversation A").props.onClick();
      await Promise.resolve();
    });
    await waitFor(() => assert.ok(harness.state.requests.states.includes("thread_a")), "A bound before cancellation");
    await flush();
    await act(async () => {
      button(renderer, "Cancel").props.onClick();
      await Promise.resolve();
    });
    await waitFor(() => assert.deepEqual(harness.state.requests.cancels, ["run_a"]), "cancel request held");
    await act(async () => {
      button(renderer, "Conversation B").props.onClick();
      await Promise.resolve();
    });
    await waitFor(() => assert.ok(harness.state.requests.states.includes("thread_b")), "B bound before old cancellation resolves");
    await flush();
    await releaseResponse(harness, heldCancel, "/v1/agent-runs/run_a/cancel", "POST");
    await waitFor(() => assert.match(activeConversationTitle(renderer), /Conversation B/), "B remains selected after stale cancel");
    assert.doesNotMatch(allText(renderer), /cancel_requested/i, "stale A cancellation must not attach to B or reselect A");
  } finally {
    heldCancel.resolve();
    await closeHarness(renderer, harness);
  }
}

async function testCreateRegisterAfterNewDoesNotSubmitOrSelect(vite) {
  const heldCreate = deferred();
  const harness = makeHarness({ aRun: null, threadARun: null });
  harness.state.barriers.chatConversation.set("create", heldCreate);
  const renderer = await renderChat(vite, harness);
  try {
    await waitFor(() => button(renderer, "Conversation A"), "initial chat list");
    await act(async () => {
      textarea(renderer).props.onChange({ target: { value: "create then leave" } });
      await Promise.resolve();
    });
    await act(async () => {
      composeForm(renderer).props.onSubmit({ preventDefault() {} });
      await Promise.resolve();
    });
    await act(async () => {
      button(renderer, "New").props.onClick();
      await Promise.resolve();
    });
    await releaseResponse(harness, heldCreate, "/v1/chat/conversations", "POST");
    assert.match(allText(renderer), /Start a conversation/i, "New should remain active after delayed create/register");
    assert.equal(harness.state.requests.commands.length, 0, "delayed create/register must not submit after navigation");
    assert.equal(harness.state.outgoingRequests.some(item => item.path === "/v1/agent-interaction/threads" && item.method === "POST"), false, "abandoned creation must not start registration");
  } finally {
    heldCreate.resolve();
    await closeHarness(renderer, harness);
  }
}

async function testNewConversationHeldRegistrationAfterCreateDoesNotSubmitAfterNavigation(vite) {
  const heldRegister = deferred();
  const harness = makeHarness({ aRun: null, threadARun: null });
  harness.state.barriers.register.set("conv_new", heldRegister);
  const renderer = await renderChat(vite, harness);
  try {
    await waitFor(() => button(renderer, "Conversation A"), "initial chat list");
    await act(async () => {
      textarea(renderer).props.onChange({ target: { value: "create then registration waits" } });
      await Promise.resolve();
    });
    await waitFor(() => assert.equal(textarea(renderer).props.value, "create then registration waits"), "new conversation draft");
    await act(async () => {
      composeForm(renderer).props.onSubmit({ preventDefault() {} });
      await Promise.resolve();
    });
    await waitFor(() => assert.equal(harness.state.requests.registers.at(-1)?.conversation_id, "conv_new"), "new conversation registration held");
    await act(async () => {
      button(renderer, "New").props.onClick();
      await Promise.resolve();
    });
    await releaseResponse(harness, heldRegister, "/v1/agent-interaction/threads", "POST");
    assert.match(allText(renderer), /Start a conversation/i, "New should remain active after delayed new-conversation registration");
    assert.equal(harness.state.requests.commands.length, 0, "delayed new-conversation registration must not submit after navigation");
  } finally {
    heldRegister.resolve();
    await closeHarness(renderer, harness);
  }
}

async function testSubmitBlockedDuringHeldSelectionRegistration(vite) {
  const heldRegister = deferred();
  const harness = makeHarness({ aRun: null, threadARun: null });
  harness.state.barriers.register.set("conv_b", heldRegister);
  const renderer = await renderChat(vite, harness);
  try {
    await waitFor(() => button(renderer, "Conversation B"), "initial chat list");
    await act(async () => {
      button(renderer, "Conversation B").props.onClick();
      await Promise.resolve();
    });
    await waitFor(() => assert.match(allText(renderer), /Loading conversation/), "B loading state");
    await act(async () => {
      textarea(renderer).props.onChange({ target: { value: "must not submit while binding" } });
      await Promise.resolve();
    });
    composeForm(renderer).props.onSubmit({ preventDefault() {} });
    await flush();
    assert.equal(harness.state.requests.commands.length, 0, "loading selection must not submit to an old thread");
    assert.equal(harness.state.requests.chatGets.some((item) => item.id === "conv_new"), false, "loading selection must not create a new conversation");
  } finally {
    heldRegister.resolve();
    await closeHarness(renderer, harness);
  }
}

async function testOldTerminalHydrationCannotOverwriteNewerRunOnSameSelection(vite) {
  const oldRun = run("run_old", "completed", null, "old answer");
  const oldConversation = conversation("conv_a", "Conversation A", oldRun);
  const heldHydration = deferred();
  const harness = makeHarness({ aRun: oldRun, threadARun: oldRun, commandProjectsRun: true });
  harness.state.queuedConversationResponses.set("conv_a:2", oldConversation);
  harness.state.barriers.chatConversation.set("conv_a:2", heldHydration);
  const renderer = await renderChat(vite, harness);
  try {
    await waitFor(() => button(renderer, "Conversation A"), "initial chat list");
    await act(async () => {
      button(renderer, "Conversation A").props.onClick();
      await Promise.resolve();
    });
    await waitFor(() => assert.ok((harness.state.chatGetCounts.get("conv_a") ?? 0) >= 2), "old terminal hydration held");
    await act(async () => {
      textarea(renderer).props.onChange({ target: { value: "newer same conversation run" } });
      await Promise.resolve();
    });
    await waitFor(() => assert.equal(textarea(renderer).props.value, "newer same conversation run"), "newer same-selection draft");
    await act(async () => {
      composeForm(renderer).props.onSubmit({ preventDefault() {} });
      await Promise.resolve();
    });
    await waitFor(() => assert.match(allText(renderer), /accepted 1/), "newer run projected");
    await releaseResponse(harness, heldHydration, "/v1/chat/conversations/conv_a", "GET");
    assert.match(allText(renderer), /accepted 1/, "old terminal hydration must not overwrite the newer same-selection run");
    assert.equal(selectedRunId(renderer), "run_projected_1", "older terminal hydration must not regress selected run metadata");
    assert.doesNotMatch(allText(renderer), /old answer/, "old terminal hydration response must not restore the old run output");
  } finally {
    heldHydration.resolve();
    await closeHarness(renderer, harness);
  }
}

async function testSubmitAckDoesNotClearNewerDraft(vite, changeDraft = true) {
  const heldCommand = deferred();
  const harness = makeHarness({ aRun: null, threadARun: null, commandProjectsRun: true, completeCommands: true });
  harness.state.barriers.command.set("thread_a", heldCommand);
  const renderer = await renderChat(vite, harness);
  try {
    await waitFor(() => button(renderer, "Conversation A"), "initial chat list");
    await act(async () => {
      button(renderer, "Conversation A").props.onClick();
      await Promise.resolve();
    });
    await waitFor(() => assert.ok(harness.state.requests.states.includes("thread_a")), "A bound before submitting draft");
    await flush();
    await act(async () => {
      textarea(renderer).props.onChange({ target: { value: "first draft" } });
      await Promise.resolve();
    });
    await act(async () => {
      composeForm(renderer).props.onSubmit({ preventDefault() {} });
      await Promise.resolve();
    });
    await waitFor(() => assert.equal(harness.state.requests.commands.length, 1), "submit command");
    if (changeDraft) {
      await act(async () => {
        textarea(renderer).props.onChange({ target: { value: "newer draft" } });
        await Promise.resolve();
      });
    }
    heldCommand.resolve();
    await waitFor(() => assert.match(allText(renderer), /accepted 1/), "submitted run completed");
    await waitFor(() => assert.ok(harness.state.requests.streams.includes("thread_a")), "completion subscription received");
    await flush();
    if (changeDraft) {
      assert.equal(textarea(renderer).props.value, "newer draft", "late submit acknowledgement must not clear newer draft");
    } else {
      await waitFor(() => assert.equal(textarea(renderer).props.value, ""), "unchanged submitted draft clears after completion");
    }
  } finally {
    heldCommand.resolve();
    await closeHarness(renderer, harness);
  }
}

async function testProjectBranchesGroupByImmutableArea(vite) {
  const originalArea = "D:\\Removed Source\\Original Project";
  const harness = makeHarness({
    aRun: null,
    bRun: null,
  });
  harness.state.conversations.conv_a = conversation("conv_a", "Branch from restored workspace A", null, {
    area_kind: "project",
    area_id: originalArea,
    area_label: "Original Project",
    area_project_path: originalArea,
    project_path: "D:\\LocalAIWorkbench\\workspaces\\branch-a",
    workspace_id: "workspace_a",
  });
  harness.state.conversations.conv_b = conversation("conv_b", "Branch from restored workspace B", null, {
    area_kind: "project",
    area_id: originalArea,
    area_label: "Original Project",
    area_project_path: originalArea,
    project_path: "D:\\LocalAIWorkbench\\workspaces\\branch-b",
    workspace_id: "workspace_b",
  });
  const renderer = await renderChat(vite, harness);
  try {
    await waitFor(() => button(renderer, "Branch from restored workspace A"), "project branch A listed");
    const group = renderer.root.findAll(
      (node) => node.type === "details" && textOf(node).includes("Original Project"),
    );
    assert.equal(group.length, 1, "branches with the same immutable area should share one group");
    const summaries = renderer.root.findAll(
      (node) => node.type === "summary" && textOf(node).includes("Original Project"),
    );
    assert.equal(summaries.length, 1, "header label should use the immutable original area label");
    assert.equal(renderer.root.findAll((node) => node.type === "summary" && textOf(node).includes("branch-a")).length, 0, "group header must not use execution workspace A");
    assert.equal(renderer.root.findAll((node) => node.type === "summary" && textOf(node).includes("branch-b")).length, 0, "group header must not use execution workspace B");
    const groupText = textOf(group[0]);
    assert.match(groupText, /Branch from restored workspace A/);
    assert.match(groupText, /Branch from restored workspace B/);
  } finally {
    await closeHarness(renderer, harness);
  }
}

async function testRejectedSubmitWithOnlyStagedInputKeepsDraftAndError(vite) {
  const harness = makeHarness({ aRun: null, threadARun: null, commandRejects: true });
  const renderer = await renderChat(vite, harness);
  try {
    await waitFor(() => button(renderer, "Conversation A"), "initial chat list");
    await act(async () => {
      button(renderer, "Conversation A").props.onClick();
      await Promise.resolve();
    });
    await waitFor(() => assert.ok(harness.state.requests.states.includes("thread_a")), "A bound before rejected submit");
    await act(async () => {
      textarea(renderer).props.onChange({ target: { value: "failed model startup" } });
      await Promise.resolve();
    });
    await act(async () => {
      composeForm(renderer).props.onSubmit({ preventDefault() {} });
      await Promise.resolve();
    });
    await waitFor(() => assert.equal(harness.state.requests.commands.length, 1), "rejected submit command");
    await waitFor(() => assert.match(allText(renderer), /Model startup failed before a run was accepted/), "rejected submit error");
    assert.equal(textarea(renderer).props.value, "failed model startup", "staged input without accepted run must keep the draft");
    assert.equal(harness.state.conversations.conv_a.run_ids.length, 0, "staged failed input must not invent an accepted run");
    assert.equal(harness.state.conversations.conv_a.transcript.at(-1)?.run_id, null, "failed staged input is not accepted");
  } finally {
    await closeHarness(renderer, harness);
  }
}

async function testPendingSubmitDoesNotReusePreviousCancelledStatus(vite) {
  const previousCancelled = run("run_cancelled_previous", "cancelled", "old-input", "cancelled before follow-up");
  const heldCommand = deferred();
  const harness = makeHarness({ aRun: previousCancelled, threadARun: previousCancelled });
  harness.state.barriers.command.set("thread_a", heldCommand);
  const renderer = await renderChat(vite, harness);
  try {
    await waitFor(() => button(renderer, "Conversation A"), "initial chat list");
    await act(async () => {
      button(renderer, "Conversation A").props.onClick();
      await Promise.resolve();
    });
    await waitFor(() => assert.ok(harness.state.requests.states.includes("thread_a")), "A bound with previous cancelled run");
    await act(async () => {
      textarea(renderer).props.onChange({ target: { value: "follow-up waits for stopped model" } });
      await Promise.resolve();
    });
    await act(async () => {
      composeForm(renderer).props.onSubmit({ preventDefault() {} });
      await Promise.resolve();
    });
    await waitFor(() => assert.equal(harness.state.requests.commands.length, 1), "pending follow-up command held");
    assert.match(allText(renderer), /Working(?:(?!This can continue).)*Loading model/s, "pending submit should show loading status");
    assert.doesNotMatch(allText(renderer), /Working(?:(?!This can continue).)*Cancelled/s, "pending submit must not reuse previous terminal run status");
  } finally {
    heldCommand.resolve();
    await closeHarness(renderer, harness);
  }
}

async function testPendingSubmitStopUsesPendingInputIdentity(vite) {
  const previousCancelled = run("run_cancelled_previous", "cancelled", "old-input", "cancelled before follow-up");
  const heldCommand = deferred();
  const heldStop = deferred();
  const harness = makeHarness({ aRun: previousCancelled, threadARun: previousCancelled, commandProjectsRun: true });
  harness.state.barriers.command.set("thread_a", heldCommand);
  harness.state.barriers.chatCancel.set("conv_a", heldStop);
  const renderer = await renderChat(vite, harness);
  try {
    await waitFor(() => button(renderer, "Conversation A"), "initial chat list");
    await act(async () => {
      button(renderer, "Conversation A").props.onClick();
      await Promise.resolve();
    });
    await waitFor(() => assert.ok(harness.state.requests.states.includes("thread_a")), "A bound with previous cancelled run");
    await act(async () => {
      textarea(renderer).props.onChange({ target: { value: "follow-up waits for stopped model" } });
      await Promise.resolve();
    });
    await act(async () => {
      composeForm(renderer).props.onSubmit({ preventDefault() {} });
      await Promise.resolve();
    });
    await waitFor(() => assert.equal(harness.state.requests.commands.length, 1), "pending follow-up command held");
    const pendingInputId = harness.state.requests.commands[0].payload.params.input.messages[0].id;
    await act(async () => {
      buttons(renderer, "Stop").at(-1).props.onClick();
      await Promise.resolve();
    });
    await waitFor(() => assert.equal(harness.state.requests.chatCancels.length, 1), "pending stop uses chat cancel");
    assert.deepEqual(
      harness.state.requests.chatCancels[0],
      { id: "conv_a", payload: { input_message_id: pendingInputId } },
      "pending stop must carry the pending input identity",
    );
    assert.deepEqual(harness.state.requests.cancels, [], "pending stop must not cancel the previous terminal run");
    assert.match(allText(renderer), /Working(?:(?!This can continue).)*Stopping submission/s, "pending stop should show an in-flight stopping state");
    harness.state.conversations.conv_a.title = "Stop acknowledged";
    heldStop.resolve();
    await waitFor(() => button(renderer, "Stop acknowledged"), "cancel acknowledgment rendered");
    assert.match(allText(renderer), /Working(?:(?!This can continue).)*Stopping submission/s,
      "acknowledgment with only the previous terminal run must not claim pending work stopped");
    heldCommand.resolve();
    await waitFor(() => assert.doesNotMatch(allText(renderer), /Stopping submission/), "accepted submit clears pending stop");
    await waitFor(() => assert.match(allText(renderer), /accepted 1/), "accepted submit renders after pending stop clears");
  } finally {
    heldStop.resolve();
    heldCommand.resolve();
    await closeHarness(renderer, harness);
  }
}

async function testReopenedPendingCancelShowsStoppingUntilAuthoritativeClear(vite) {
  const previousCancelled = run("run_cancelled_previous", "cancelled", "old-input", "cancelled before follow-up");
  const pendingView = conversation("conv_a", "Conversation A", previousCancelled, {
    pending_cancel_input_ids: ["pending-input-after-restart"],
  });
  const clearedView = conversation("conv_a", "Conversation A", run("run_after_pending_cancel", "completed", "pending-input-after-restart", "accepted after restart"), {
    pending_cancel_input_ids: [],
  });
  const harness = makeHarness({ aRun: previousCancelled, threadARun: previousCancelled });
  harness.state.conversations.conv_a = pendingView;
  harness.state.queuedConversationResponses.set("conv_a:2", clearedView);
  const renderer = await renderChat(vite, harness);
  try {
    await waitFor(() => button(renderer, "Conversation A"), "initial chat list");
    await act(async () => {
      button(renderer, "Conversation A").props.onClick();
      await Promise.resolve();
    });
    await waitFor(() => assert.match(allText(renderer), /Working(?:(?!This can continue).)*Stopping submission/s), "reopened pending cancel shows stopping");
    assert.doesNotMatch(allText(renderer), /Working(?:(?!This can continue).)*Cancelled/s, "reopened pending cancel does not show previous terminal run as current work");
    assert.equal(buttons(renderer, "Stop").at(-1).props.disabled, true, "durable pending cancel must not cancel previous terminal run");
    await act(async () => {
      button(renderer, "New").props.onClick();
      await Promise.resolve();
    });
    harness.state.streamRuns.set("thread_a", clearedView.current_run);
    await act(async () => {
      button(renderer, "Conversation A").props.onClick();
      await Promise.resolve();
    });
    await waitFor(() => assert.doesNotMatch(allText(renderer), /Stopping submission/), "authoritative terminal view clears pending cancel");
    await waitFor(() => assert.equal(selectedRunId(renderer), "run_after_pending_cancel"), "authoritative terminal run selected after pending cancel clears");
    assert.deepEqual(harness.state.requests.cancels, [], "reopened pending cancel must not call previous run cancel");
    assert.deepEqual(harness.state.requests.chatCancels, [], "reopened pending cancel must not send a new stop without a local submission");
  } finally {
    await closeHarness(renderer, harness);
  }
}

async function testStoppedManagedDeploymentShowsLoadOnSendNotice(vite) {
  const diagnostic = "Bound deployment is not healthy. Live Chat completion requires a healthy managed/connected llama.cpp. Continuity/thread linkage is not proof of live completion.";
  const stoppedConversation = conversation("conv_a", "Conversation A", null, {
    deploy_health: {
      deployment_id: "dep_1",
      deployment_status: "stopped",
      healthy: false,
      code: "deploy_unhealthy",
      message: diagnostic,
      detail: null,
      note: "diagnostic",
    },
  });
  const harness = makeHarness({ aRun: null, threadARun: null, deployments: [stoppedManagedDeployment] });
  harness.state.conversations.conv_a = stoppedConversation;
  const renderer = await renderChat(vite, harness);
  try {
    await waitFor(() => button(renderer, "Conversation A"), "initial chat list");
    await act(async () => {
      button(renderer, "Conversation A").props.onClick();
      await Promise.resolve();
    });
    await waitFor(() => assert.doesNotMatch(allText(renderer), /Loading conversation/), "stopped managed conversation bound");
    await waitFor(() => assert.match(allText(renderer), /Loads when sent/), "stopped managed selector shows load-on-send state");
    assert.match(allText(renderer), /This saved model setup will load when you send a message\./, "stopped managed health is presented as load-on-send");
    assert.doesNotMatch(allText(renderer), /Continuity\/thread linkage is not proof of live completion/, "stopped managed chat should not show technical unhealthy diagnostic before send");
  } finally {
    await closeHarness(renderer, harness);
  }
}

async function testUnknownProjectionRequiresAuthoritativeCurrentRun(vite) {
  const known = run("run_known_previous", "completed", "old-input", "previous answer");
  const unknown = run("run_unknown_stream", "running", "new-input", "new queued answer");
  const staleView = conversation("conv_a", "Conversation A", known, {
    run_ids: [known.id],
  });
  const harness = makeHarness({ aRun: known, threadARun: unknown });
  harness.state.conversations.conv_a = staleView;
  harness.state.queuedConversationResponses.set("conv_a:2", staleView);
  const renderer = await renderChat(vite, harness);
  try {
    await waitFor(() => button(renderer, "Conversation A"), "initial chat list");
    await act(async () => {
      button(renderer, "Conversation A").props.onClick();
      await Promise.resolve();
    });
    await waitFor(() => assert.ok((harness.state.chatGetCounts.get("conv_a") ?? 0) >= 2), "unknown projection ownership lookup");
    assert.equal(selectedRunId(renderer), known.id, "unknown stream run is ignored until server owns it");
    assert.doesNotMatch(allText(renderer), /new queued answer/, "unknown stream output must not render without authoritative ownership");
  } finally {
    await closeHarness(renderer, harness);
  }
}

async function testUnknownProjectionAdoptsAuthoritativeNewCurrentRun(vite) {
  const known = run("run_known_previous", "completed", "old-input", "previous answer");
  const nextRun = run("run_authoritative_new", "running", "new-input", "new queued answer");
  const initialView = conversation("conv_a", "Conversation A", known, {
    run_ids: [known.id],
  });
  const authoritativeView = conversation("conv_a", "Conversation A", nextRun, {
    run_ids: [known.id, nextRun.id],
  });
  const harness = makeHarness({ aRun: known, threadARun: nextRun });
  harness.state.conversations.conv_a = initialView;
  harness.state.queuedConversationResponses.set("conv_a:2", authoritativeView);
  const renderer = await renderChat(vite, harness);
  try {
    await waitFor(() => button(renderer, "Conversation A"), "initial chat list");
    await act(async () => {
      button(renderer, "Conversation A").props.onClick();
      await Promise.resolve();
    });
    await waitFor(() => assert.ok((harness.state.chatGetCounts.get("conv_a") ?? 0) >= 2), "unknown projection authoritative lookup");
    await waitFor(() => assert.equal(selectedRunId(renderer), nextRun.id), "authoritative new run adopted from ownership lookup");
    assert.match(allText(renderer), /Working(?:(?!This can continue).)*Running/s, "authoritative new run shows active progress");
    assert.match(allText(renderer), /new queued answer/, "authoritative new stream output renders");
  } finally {
    await closeHarness(renderer, harness);
  }
}

async function testOlderUnknownProjectionLookupCannotOverwriteNewerAdoptedRun(vite) {
  const known = run("run_known_previous", "completed", "old-input", "previous answer");
  const r2 = run("run_unknown_r2", "running", "r2-input", "r2 stream");
  const r3 = run("run_unknown_r3", "running", "r3-input", "r3 stream");
  const initialView = conversation("conv_a", "Conversation A", known, {
    run_ids: [known.id],
  });
  const r2View = conversation("conv_a", "Conversation A", r2, {
    run_ids: [known.id, r2.id],
  });
  const r3View = conversation("conv_a", "Conversation A", r3, {
    run_ids: [known.id, r3.id],
  });
  const heldR2Lookup = deferred();
  const harness = makeHarness({ aRun: known, threadARun: r2 });
  harness.state.conversations.conv_a = initialView;
  harness.state.queuedConversationResponses.set("conv_a:2", r2View);
  harness.state.barriers.chatConversation.set("conv_a:2", heldR2Lookup);
  harness.state.queuedConversationResponses.set("conv_a:3", r3View);
  const renderer = await renderChat(vite, harness);
  try {
    await waitFor(() => button(renderer, "Conversation A"), "initial chat list");
    await act(async () => {
      button(renderer, "Conversation A").props.onClick();
      await Promise.resolve();
    });
    await waitFor(() => assert.ok((harness.state.chatGetCounts.get("conv_a") ?? 0) >= 2), "R2 ownership lookup held");
    assert.equal(selectedRunId(renderer), known.id, "held R2 lookup does not adopt before response");
    harness.state.streamRuns.set("thread_a", r3);
    await act(async () => {
      harness.state.openStreams.get("thread_a")?.write(`data: ${JSON.stringify(streamFrame(r3))}\n\n`);
      await Promise.resolve();
    });
    await waitFor(() => assert.equal(selectedRunId(renderer), r3.id), "newer R3 authoritative lookup adopted");
    await releaseResponse(harness, heldR2Lookup, "/v1/chat/conversations/conv_a", "GET");
    await waitFor(() => assert.equal(selectedRunId(renderer), r3.id), "older R2 ownership lookup must not overwrite newer adopted run");
    assert.match(allText(renderer), /r3 stream/, "newer R3 output remains visible");
    assert.doesNotMatch(allText(renderer), /r2 stream/, "older R2 output must not replace newer adopted run");
  } finally {
    heldR2Lookup.resolve();
    await closeHarness(renderer, harness);
  }
}

async function testAcceptedSubmitErrorRefreshSuppressesStaleErrorButKeepsNewerDraft(vite) {
  const heldRefresh = deferred();
  const harness = makeHarness({ aRun: null, threadARun: null, commandRejects: true, commandRejectAcceptsRun: true });
  harness.state.barriers.chatConversation.set("conv_a:2", heldRefresh);
  const renderer = await renderChat(vite, harness);
  try {
    await waitFor(() => button(renderer, "Conversation A"), "initial chat list");
    await act(async () => {
      button(renderer, "Conversation A").props.onClick();
      await Promise.resolve();
    });
    await waitFor(() => assert.ok(harness.state.requests.states.includes("thread_a")), "A bound before accepted error submit");
    await act(async () => {
      textarea(renderer).props.onChange({ target: { value: "accepted but command failed" } });
      await Promise.resolve();
    });
    await act(async () => {
      composeForm(renderer).props.onSubmit({ preventDefault() {} });
      await Promise.resolve();
    });
    await waitFor(() => assert.ok((harness.state.chatGetCounts.get("conv_a") ?? 0) >= 2), "post-error accepted refresh held");
    await act(async () => {
      textarea(renderer).props.onChange({ target: { value: "newer draft survives" } });
      await Promise.resolve();
    });
    await releaseResponse(harness, heldRefresh, "/v1/chat/conversations/conv_a", "GET");
    await waitFor(() => assert.equal(textarea(renderer).props.value, "newer draft survives"), "newer draft retained after accepted error refresh");
    assert.doesNotMatch(allText(renderer), /Model startup failed before a run was accepted/, "accepted run association suppresses stale submit error");
    assert.equal(harness.state.conversations.conv_a.transcript.at(-1)?.run_id, "run_accepted_after_error", "accepted refresh must have a durable run association");
  } finally {
    heldRefresh.resolve();
    await closeHarness(renderer, harness);
  }
}

async function testAcceptedSubmitErrorRefreshAfterNavigationDoesNotRetarget(vite) {
  const heldRefresh = deferred();
  const harness = makeHarness({ aRun: null, threadARun: null, commandRejects: true, commandRejectAcceptsRun: true });
  harness.state.barriers.chatConversation.set("conv_a:2", heldRefresh);
  const renderer = await renderChat(vite, harness);
  try {
    await waitFor(() => button(renderer, "Conversation A"), "initial chat list");
    await act(async () => {
      button(renderer, "Conversation A").props.onClick();
      await Promise.resolve();
    });
    await waitFor(() => assert.ok(harness.state.requests.states.includes("thread_a")), "A bound before navigation error submit");
    await act(async () => {
      textarea(renderer).props.onChange({ target: { value: "accepted then navigate" } });
      await Promise.resolve();
    });
    await act(async () => {
      composeForm(renderer).props.onSubmit({ preventDefault() {} });
      await Promise.resolve();
    });
    await waitFor(() => assert.ok((harness.state.chatGetCounts.get("conv_a") ?? 0) >= 2), "post-error navigation refresh held");
    await act(async () => {
      button(renderer, "Conversation B").props.onClick();
      await Promise.resolve();
    });
    await waitFor(() => assert.match(activeConversationTitle(renderer), /Conversation B/), "B selected before accepted error refresh");
    await releaseResponse(harness, heldRefresh, "/v1/chat/conversations/conv_a", "GET");
    assert.match(activeConversationTitle(renderer), /Conversation B/, "late accepted error refresh must not retarget current selection");
    assert.doesNotMatch(allText(renderer), /accepted after error/, "late accepted A refresh must not project into B");
  } finally {
    heldRefresh.resolve();
    await closeHarness(renderer, harness);
  }
}

async function testAcceptedSubmitTargetsOriginalThreadAfterNavigationAndRevisit(vite) {
  const heldCommand = deferred();
  const harness = makeHarness({ aRun: null, threadARun: null, commandProjectsRun: true });
  harness.state.barriers.command.set("thread_a", heldCommand);
  const renderer = await renderChat(vite, harness);
  try {
    await waitFor(() => button(renderer, "Conversation A"), "initial chat list");
    await act(async () => {
      button(renderer, "Conversation A").props.onClick();
      await Promise.resolve();
    });
    await waitFor(() => assert.ok(harness.state.requests.states.includes("thread_a")), "A bound before accepted navigation submit");
    await act(async () => {
      textarea(renderer).props.onChange({ target: { value: "accepted then leave" } });
      await Promise.resolve();
    });
    await waitFor(() => assert.equal(textarea(renderer).props.value, "accepted then leave"), "accepted navigation draft");
    await act(async () => {
      composeForm(renderer).props.onSubmit({ preventDefault() {} });
      await Promise.resolve();
    });
    await waitFor(() => assert.equal(harness.state.requests.commands.length, 1), "A submit command");
    await act(async () => {
      button(renderer, "Conversation B").props.onClick();
      await Promise.resolve();
    });
    await waitFor(() => assert.match(activeConversationTitle(renderer), /Conversation B/), "B selected before A command ack");
    await releaseResponse(harness, heldCommand, "/v1/agent-interaction/threads/thread_a/commands", "POST");
    assert.equal(harness.state.requests.commands.length, 1, "accepted command must be sent exactly once");
    assert.equal(harness.state.requests.commands[0].threadId, "thread_a", "accepted command must target A's original thread");
    assert.match(activeConversationTitle(renderer), /Conversation B/, "A command acknowledgement must not retarget the current selection");
    await act(async () => {
      button(renderer, "New").props.onClick();
      await Promise.resolve();
    });
    await act(async () => {
      button(renderer, "Conversation A").props.onClick();
      await Promise.resolve();
    });
    await waitFor(() => assert.match(activeConversationTitle(renderer), /Conversation A/), "A revisited");
    await waitFor(() => assert.match(allText(renderer), /accepted 1/), "A revisit shows the accepted run outcome");
  } finally {
    heldCommand.resolve();
    await closeHarness(renderer, harness);
  }
}

async function testEarlyShellActions(vite) {
  const harness = makeHarness({ bRun: run("run_b") });
  const renderer = await renderChat(vite, harness);
  try {
    await waitFor(() => button(renderer, "Conversation A"), "initial chat list");
    assert.equal(inputByPlaceholder(renderer, "Leave empty to chat without a project").props.readOnly, false, "new conversation project field starts editable");
    await act(async () => {
      inputByPlaceholder(renderer, "Search titles and messages").props.onChange({ target: { value: "Conversation B" } });
      await Promise.resolve();
    });
    await waitFor(() => assert.deepEqual(harness.state.requests.searches.at(-1), "conversation b"), "backend search requested");
    await waitFor(() => assert.doesNotMatch(allText(renderer), /Conversation A/, "search narrows the sidebar"), "search narrows sidebar");
    await act(async () => {
      button(renderer, "Conversation B").props.onClick();
      await Promise.resolve();
    });
    await waitFor(() => assert.ok(harness.state.requests.states.includes("thread_b")), "B bound for shell actions");
    await waitFor(() => assert.equal(inputByPlaceholder(renderer, "Leave empty to chat without a project").props.readOnly, true), "saved conversation project field is read-only");
    await act(async () => {
      textarea(renderer).props.onChange({ target: { value: "remember this draft" } });
      await Promise.resolve();
    });
    await waitFor(() => assert.equal(harness.state.requests.draftUpdates.at(-1)?.payload.content, "remember this draft"), "draft saved");
    const originalPrompt = globalThis.window.prompt;
    globalThis.window.prompt = () => "Renamed B";
    await act(async () => {
      button(renderer, "Rename").props.onClick();
      await Promise.resolve();
    });
    globalThis.window.prompt = originalPrompt;
    await waitFor(() => assert.equal(harness.state.conversations.conv_b.title, "Renamed B"), "conversation renamed");
    await act(async () => {
      button(renderer, "Archive").props.onClick();
      await Promise.resolve();
    });
    await waitFor(() => assert.equal(harness.state.conversations.conv_b.archived, true), "conversation archived");
    await act(async () => {
      const archivedToggle = renderer.root.findAll((node) => node.type === "input" && node.props.type === "checkbox")[0];
      archivedToggle.props.onChange({ target: { checked: true } });
      await Promise.resolve();
    });
    await act(async () => {
      inputByPlaceholder(renderer, "Search titles and messages").props.onChange({ target: { value: "" } });
      await Promise.resolve();
    });
    await waitFor(() => button(renderer, "Reopen"), "archived conversation visible");
    await act(async () => {
      button(renderer, "Reopen").props.onClick();
      await Promise.resolve();
    });
    await waitFor(() => assert.equal(harness.state.conversations.conv_b.archived, false), "conversation reopened");
    await act(async () => {
      button(renderer, "Renamed B").props.onClick();
      await Promise.resolve();
    });
    await waitFor(() => assert.match(activeConversationTitle(renderer), /Renamed B/), "renamed conversation selected");
    await waitFor(() => assert.equal(inputByPlaceholder(renderer, "Leave empty to chat without a project").props.readOnly, true), "reopened saved conversation project field remains read-only");
    await act(async () => {
      textarea(renderer).props.onChange({ target: { value: "queue this follow-up" } });
      await Promise.resolve();
    });
    await waitFor(() => assert.equal(textarea(renderer).props.value, "queue this follow-up"), "queue follow-up draft applied");
    await act(async () => {
      composeForm(renderer).props.onSubmit({ preventDefault() {} });
      await Promise.resolve();
    });
    await waitFor(() => assert.equal(harness.state.requests.queues.at(-1)?.payload.task, "queue this follow-up"), "busy conversation queues follow-up");
    assert.match(allText(renderer), /queue this follow-up/, "queued item is visible");
    await act(async () => {
      button(renderer, "New").props.onClick();
      await Promise.resolve();
    });
    await waitFor(() => assert.equal(inputByPlaceholder(renderer, "Leave empty to chat without a project").props.readOnly, false), "new conversation project field is editable");
  } finally {
    await closeHarness(renderer, harness);
  }
}

async function testProjectionOwnershipLeakReproduction(vite) {
  const heldRegister = deferred();
  const harness = makeHarness();
  harness.state.barriers.register.set("conv_b", heldRegister);
  const renderer = await renderChat(vite, harness);
  try {
    await waitFor(() => button(renderer, "Conversation A"), "initial chat list");
    await act(async () => {
      button(renderer, "Conversation A").props.onClick();
      await Promise.resolve();
    });
    await waitFor(() => assert.ok(harness.state.openStreams.has("thread_a")), "A subscription connected");
    await act(async () => {
      button(renderer, "Conversation B").props.onClick();
      await Promise.resolve();
    });
    await waitFor(() => assert.equal(harness.state.requests.registers.at(-1)?.conversation_id, "conv_b"), "B held registration started");
    await releaseResponse(harness, heldRegister, "/v1/agent-interaction/threads", "POST");
    await waitFor(() => assert.match(allText(renderer), /Run progress/i), "broken source exposes an unowned projected run");
  } finally {
    heldRegister.resolve();
    await closeHarness(renderer, harness);
  }
}

const vite = await createViteServer({
  root: desktopRoot,
  appType: "custom",
  server: { middlewareMode: true, hmr: false },
  logLevel: "error",
  plugins: chatPanelSourceOverride || reproduceProjectionLeak ? [{
    name: "chat-panel-source-override",
    enforce: "pre",
    load(id) {
      const normalized = id.replace(/\\/g, "/");
      if (normalized.endsWith("/src/renderer/ChatPanel.tsx")) {
        const source = readFileSync(chatPanelSourceOverride ?? path.join(desktopRoot, "src/renderer/ChatPanel.tsx"), "utf8");
        if (!reproduceProjectionLeak) {
          return source;
        }
        return source.replace(
          /const projectionRunOwned = !run \|\|[\s\S]*?\n  \);/,
          "const projectionRunOwned = true;",
        );
      }
      return null;
    },
  }] : [],
});
try {
  if (reproduceProjectionLeak) {
    await testProjectionOwnershipLeakReproduction(vite);
    console.log("Projection ownership leak reproduction exposed the broken state.");
  } else {
    const cases = [
    ["held registration", testHeldRegistrationDoesNotBindOldThread],
    ["terminal hydration after New", testTerminalHydrationCannotReselectAfterNew],
    ["terminal hydration after B", testTerminalHydrationCannotReselectAfterB],
    ["terminal hydration away/back A", testTerminalHydrationAwayBackSameConversationGeneration],
    ["cancel after switch", testCancelResponseCannotReselectAfterSwitch],
    ["create after New", testCreateRegisterAfterNewDoesNotSubmitOrSelect],
    ["new conversation registration after New", testNewConversationHeldRegistrationAfterCreateDoesNotSubmitAfterNavigation],
    ["submit blocked while loading", testSubmitBlockedDuringHeldSelectionRegistration],
    ["same-selection stale terminal", testOldTerminalHydrationCannotOverwriteNewerRunOnSameSelection],
    ["submit ack draft isolation", testSubmitAckDoesNotClearNewerDraft],
    ["submitted draft clears", (vite) => testSubmitAckDoesNotClearNewerDraft(vite, false)],
    ["pending submit hides previous cancelled status", testPendingSubmitDoesNotReusePreviousCancelledStatus],
    ["pending submit stop uses input identity", testPendingSubmitStopUsesPendingInputIdentity],
    ["reopened pending cancel clears from authoritative view", testReopenedPendingCancelShowsStoppingUntilAuthoritativeClear],
    ["stopped managed deployment shows load-on-send notice", testStoppedManagedDeploymentShowsLoadOnSendNotice],
    ["unknown projection requires authoritative current run", testUnknownProjectionRequiresAuthoritativeCurrentRun],
    ["unknown projection adopts authoritative new current run", testUnknownProjectionAdoptsAuthoritativeNewCurrentRun],
    ["older unknown projection lookup cannot overwrite newer adopted run", testOlderUnknownProjectionLookupCannotOverwriteNewerAdoptedRun],
    ["rejected submit keeps draft", testRejectedSubmitWithOnlyStagedInputKeepsDraftAndError],
    ["accepted submit error preserves newer draft", testAcceptedSubmitErrorRefreshSuppressesStaleErrorButKeepsNewerDraft],
    ["accepted submit error navigation guard", testAcceptedSubmitErrorRefreshAfterNavigationDoesNotRetarget],
    ["accepted ack navigation/revisit", testAcceptedSubmitTargetsOriginalThreadAfterNavigationAndRevisit],
    ["early shell actions", testEarlyShellActions],
    ["project branches group by immutable area", testProjectBranchesGroupByImmutableArea],
  ];
    const failures = [];
    for (const [name, fn] of cases) {
      if (!aggregateCases) {
        await fn(vite);
        continue;
      }
      try {
        await fn(vite);
        console.log(`CASE PASS: ${name}`);
      } catch (error) {
        const message = error instanceof Error ? error.message.split("\n")[0] : String(error);
        console.log(`CASE FAIL: ${name}: ${message}`);
        failures.push(name);
      }
    }
    if (failures.length > 0) {
      throw new Error(`${failures.length} chat boundary case(s) failed: ${failures.join(", ")}`);
    }
  }
} finally {
  await vite.close();
}

if (!reproduceProjectionLeak) {
  console.log("Chat interaction boundary checks passed.");
}
