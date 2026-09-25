import assert from "node:assert/strict";
import { createServer } from "node:http";
import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import React, { StrictMode, useState } from "react";
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

function clearDraftIfRevision(conversation, revision) {
  if (revision == null || !conversation?.draft || conversation.draft.revision !== revision) {
    return conversation;
  }
  return {
    ...conversation,
    draft: {
      content: "",
      content_blocks: null,
      attachment_ids: [],
      intended_config: conversation.draft.intended_config ?? {},
      revision: conversation.draft.revision + 1,
      updated_at: now(),
    },
    updated_at: now(),
  };
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
    windowScope: { scope: "off", selected_window: null, stale: false },
    browserInstalled: options.browserInstalled ?? true,
    browserSessionState: options.browserSessionState ?? "active",
    testIntervals: new Map(),
    requests: {
      commands: [],
      creates: [],
      resolutions: [],
      registers: [],
      readiness: [],
      cancels: [],
      streams: [],
      states: [],
      chatGets: [],
      draftUpdates: [],
      searches: [],
      renames: [],
      archives: [],
      deletes: [],
      queues: [],
      chatCancels: [],
      assetUploads: [],
      assetLists: [],
      closedStreams: [],
    },
    barriers: {
      chatConversation: new Map(),
      register: new Map(),
      profiles: new Map(),
      command: new Map(),
      cancel: new Map(),
      chatCancel: new Map(),
      assetUpload: new Map(),
      draft: new Map(),
    },
    registrationFailures: new Map(),
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
    assets: new Map(options.assets ? options.assets.map((asset) => [asset.id, asset]) : []),
    chatGetCounts: new Map(),
    deploymentRequests: 0,
    conversationListError: options.conversationListError ?? null,
  };

  const server = createServer((req, res) => {
    let body = "";
    req.on("data", (chunk) => {
      body += String(chunk);
    });
    req.on("end", async () => {
      const url = new URL(req.url ?? "/", "http://127.0.0.1");
      try {
        if (req.method === "GET" && url.pathname === "/v1/projects") { json(res, 200, options.projects ?? []); return; }
        if (req.method === "GET" && url.pathname === "/v1/agent-setups") { json(res, 200, options.agentSetups ?? []); return; }
        if (req.method === "GET" && url.pathname === "/v1/bundles") { json(res, 200, options.bundles ?? []); return; }
        if (req.method === "GET" && url.pathname === "/v1/browser/runtime") { json(res, 200, { supported: true, installed: state.browserInstalled }); return; }
        if (req.method === "POST" && url.pathname === "/v1/browser/runtime/install") { state.browserInstalled = true; json(res, 200, { supported: true, installed: true }); return; }
        if (/^\/v1\/browser\/sessions\/[^/]+$/.test(url.pathname)) { if (req.method === "DELETE") state.browserSessionState = "closed"; json(res, 200, { thread_id: url.pathname.split("/").at(-1), state: state.browserSessionState }); return; }
        if (req.method === "POST" && /^\/v1\/browser\/sessions\/[^/]+\/reset$/.test(url.pathname)) { state.browserSessionState = "closed"; json(res, 200, { thread_id: url.pathname.split("/").at(-2), state: "closed" }); return; }
        if (req.method === "GET" && url.pathname === "/v1/window-testing/runtime") { json(res, 200, { available: true, installed: true }); return; }
        if (req.method === "GET" && url.pathname === "/v1/window-testing/windows") { json(res, 200, [{ hwnd: 42, title: "Fixture window", process_name: "fixture.exe", process_id: 1234 }]); return; }
        if (/^\/v1\/window-testing\/conversations\/[^/]+\/scope$/.test(url.pathname)) {
          if (req.method === "PUT") { const scope = JSON.parse(body); state.windowScope = { scope: scope.scope, selected_window: scope.hwnd ? { hwnd: scope.hwnd, title: "Fixture window", process_name: "fixture.exe", process_id: 1234 } : null, stale: false }; }
          json(res, 200, state.windowScope); return;
        }
        if (req.method === "POST" && /^\/v1\/chat\/conversations\/[^/]+\/readiness$/.test(url.pathname)) {
          const id = url.pathname.split("/").at(-2);
          const payload = body ? JSON.parse(body) : {};
          state.requests.readiness.push({ id, payload });
          const result = await options.readiness?.({ id, payload, count: state.requests.readiness.length });
          json(res, 200, result ?? { status: "ready", can_send: true, issues: [], selection: null }); return;
        }
        if (req.method === "POST" && url.pathname === "/v1/setup-resolution") {
          const payload = JSON.parse(body); state.requests.resolutions.push(payload);
          const resolved = await options.resolveSetup?.(payload) ?? { configuration: { ...payload.overrides }, instruction_layers: [] };
          const config = resolved.configuration ?? {};
          json(res, 200, { ...resolved, effective_values: resolved.effective_values ?? {
            "per_request.reasoning": { value: config.per_request_overrides?.reasoning ?? "on", known: true, source: "Model default" },
            "per_request.reasoning_effort": { value: config.per_request_overrides?.reasoning_effort ?? "medium", known: true, source: "Model default" },
          } }); return;
        }
        if (req.method === "GET" && url.pathname === "/v1/deployments") {
          state.deploymentRequests += 1;
          const override = typeof options.deployments === "function"
            ? options.deployments(state.deploymentRequests)
            : options.deployments;
          json(res, 200, override ?? [baseDeployment]);
          return;
        }
        if (req.method === "GET" && url.pathname === "/v1/profiles") {
          const barrier = state.barriers.profiles.get("list");
          if (barrier) await barrier.promise;
          json(res, 200, options.profiles ?? []);
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
        if (req.method === "GET" && url.pathname.match(/^\/v1\/bundles\/[^/]+\/configuration-options$/)) {
          json(res, 200, options.configurationOptions?.(url) ?? {
            startup: {},
            per_request: {},
              agent: {},
              context_size: { options: [], maximum: null },
              per_request_defaults: {
                reasoning_effort: {
                  supported: true,
                options: [
                  { value: "default", label: "Model default" },
                  { value: "low", label: "Low" },
                  { value: "medium", label: "Medium" },
                  { value: "high", label: "High" },
                ],
              },
            },
          });
          return;
        }
        if (req.method === "GET" && url.pathname === "/v1/assets") {
          const sessionId = url.searchParams.get("session_id");
          state.requests.assetLists.push({ sessionId });
          const assets = [...state.assets.values()].filter((asset) => !sessionId || asset.session_id === sessionId);
          json(res, 200, assets);
          return;
        }
        if (req.method === "POST" && url.pathname === "/v1/assets/uploads") {
          const payload = body ? JSON.parse(body) : {};
          state.requests.assetUploads.push(payload);
          const barrier = state.barriers.assetUpload.get(payload.session_id) ?? state.barriers.assetUpload.get("*");
          if (barrier) {
            await barrier.promise;
          }
          const asset = {
            id: `asset_${state.requests.assetUploads.length}`,
            origin: "upload",
            scope: "session",
            session_id: payload.session_id,
            project_path: null,
            access_scope: "session",
            storage: "application.sqlite",
            filename: payload.filename ?? "attachment.txt",
            content_type: payload.content_type ?? "text/plain",
            content_kind: payload.content_kind ?? "text",
            encoding: "utf-8",
            size_bytes: payload.content_base64 ? Buffer.from(payload.content_base64, "base64").length : 0,
            sha256: `sha_${state.requests.assetUploads.length}`,
            observed_at: now(),
            source_run_id: null,
            source_tool_call_id: null,
            source_tool_name: null,
            mutable_reference: null,
            observation: null,
            deleted_at: null,
          };
          state.assets.set(asset.id, asset);
          json(res, 200, asset);
          return;
        }
        if (req.method === "GET" && url.pathname === "/v1/chat/conversations") {
          if (state.conversationListError) { json(res, state.conversationListError.status, { error: state.conversationListError.message }); return; }
          json(res, 200, Object.values(state.conversations)
            .filter(item => url.searchParams.get("include_archived") === "true" || !item.archived));
          return;
        }
        if (req.method === "GET" && url.pathname === "/v1/chat/conversations/search") {
          const query = (url.searchParams.get("q") ?? "").toLowerCase();
          state.requests.searches.push(query);
          const matches = Object.values(state.conversations)
            .filter(item => url.searchParams.get("include_archived") === "true" || !item.archived)
            .filter((item) => {
              const haystack = [item.title, ...item.transcript.map((message) => message.content)].join(" ").toLowerCase();
              return haystack.includes(query);
            })
            .map((item) => ({ conversation: item, matched_messages: item.transcript }));
          json(res, 200, matches);
          return;
        }
        const conversationMatch = url.pathname.match(/^\/v1\/chat\/conversations\/([^/]+)$/);
        const deletePreviewMatch = url.pathname.match(/^\/v1\/chat\/conversations\/([^/]+)\/delete-preview$/);
        if ((req.method === "POST" && deletePreviewMatch) || (req.method === "DELETE" && conversationMatch)) {
          const id = (deletePreviewMatch ?? conversationMatch)[1];
          if (req.method === "DELETE") {
            state.requests.deletes.push({ id, payload: JSON.parse(body) });
            delete state.conversations[id];
          }
          json(res, 200, { conversation_id: id, can_delete: true, blockers: [], affected_sessions: [id],
            retained_sessions: [], affected_runs: [], retained_runs: [], affected_assets: [], retained_assets: [],
            checkpoint_threads_deleted: [], checkpoint_threads_retained: [], scratch_deleted: [],
            diagnostics_deleted: req.method === "DELETE", project_sources_deleted: false, model_files_deleted: false, note: "" });
          return;
        }
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
          json(res, responseConversation ? 200 : 404, responseConversation ?? { error: "Unknown Chat conversation", code: "chat_missing" });
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
              attachment_ids: payload.attachment_ids ?? [],
              intended_config: payload.intended_config ?? {},
              revision,
              updated_at: now(),
            },
          };
          const saved = state.conversations[id];
          const barrier = state.barriers.draft.get(id);
          if (barrier) await barrier.promise;
          json(res, 200, saved);
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
          state.conversations[id] = clearDraftIfRevision(
            { ...current, queue: [...(current.queue ?? []), item], updated_at: now() },
            payload.draft_revision,
          );
          json(res, 200, state.conversations[id]);
          return;
        }
        if (req.method === "POST" && url.pathname === "/v1/chat/conversations") {
          const payload = JSON.parse(body);
          state.requests.creates.push(payload);
          const project = options.projects?.find(item => item.id === payload.project_id);
          if (project) state.createdConversation = { ...state.createdConversation, project_id: project.id, project_path: project.path, area_project_path: project.path, area_id: project.id, area_label: project.name, area_kind: "project" };
          const barrier = state.barriers.chatConversation.get("create");
          if (barrier) {
            await barrier.promise;
          }
          state.conversations[state.createdConversation.id] = state.createdConversation;
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
          const failures = state.registrationFailures.get(conversationId) ?? 0;
          if (failures > 0) {
            state.registrationFailures.set(conversationId, failures - 1);
            json(res, 503, { error: "Thread registration is temporarily unavailable" });
            return;
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
          const workbench = payload.params?.metadata?.workbench ?? {};
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
              state.conversations[conversationId] = clearDraftIfRevision(state.conversations[conversationId], workbench.draft_revision);
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
              options.commandProjectedStatus ?? "completed",
              message?.id ?? null,
              `accepted ${state.projectedRunIndex}`,
            );
            state.streamRuns.set(threadId, projected);
            const conversationId = [...state.threadByConversation.entries()].find(([, value]) => value === threadId)?.[0];
            if (conversationId && state.conversations[conversationId]) {
              state.conversations[conversationId] = {
                ...state.conversations[conversationId],
                ...(options.commandDisplayTitle ? { display_title: options.commandDisplayTitle } : {}),
                transcript: options.commandSuppressesStream
                  ? [...state.conversations[conversationId].transcript, {
                    id: message?.id ?? "input_accepted", role: "user", content: message?.content ?? "",
                    at: now(), run_id: projected.id, content_blocks: [],
                  }]
                  : state.conversations[conversationId].transcript,
                current_run: projected,
                current_run_id: projected.id,
                run_ids: state.conversations[conversationId].run_ids.includes(projected.id)
                  ? state.conversations[conversationId].run_ids
                  : [...state.conversations[conversationId].run_ids, projected.id],
              };
              state.conversations[conversationId] = clearDraftIfRevision(state.conversations[conversationId], workbench.draft_revision);
            }
            const stream = state.openStreams.get(threadId);
            if (!options.commandSuppressesStream) stream?.write(`data: ${JSON.stringify(streamFrame(projected))}\n\n`);
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

function ChatHarness({ ChatPanel, WorkbenchSidebar, panelProps }) {
  const [chatLaunch, setChatLaunch] = useState(null);
  const [historyNotice, setHistoryNotice] = useState(null);
  const [historyRevision, setHistoryRevision] = useState(0);
  const [activeConversationId, setActiveConversationId] = useState(null);
  const ownedPreparation = React.useRef(null);
  const preparation = panelProps.navigationPreparationRef ?? ownedPreparation;
  const conversationListRef = React.useRef(null);
  return React.createElement(React.Fragment, null,
    React.createElement(WorkbenchSidebar, {
      tab: "chat",
      collapsed: false,
      width: 232,
      onCollapsedChange: () => {},
      onWidthChange: () => {},
      onNavigate: (next) => panelProps.onNavigate?.(next),
      backendOk: true,
      backendStatus: "Local",
      activeConversationId,
      historyRevision,
      projectRevision: 0,
      conversationListRef,
      onOpenConversation: (conversation) => setChatLaunch({ id: `open-${conversation.id}-${crypto.randomUUID()}`, kind: "open", conversationId: conversation.id, conversation }),
      onNewChat: () => setChatLaunch({ id: `fresh-${crypto.randomUUID()}`, kind: "fresh" }),
      onAddProject: () => {},
      onHistoryNotice: (notice) => { setHistoryNotice(notice); setHistoryRevision(value => value + 1); },
      onBeforeConversationChange: () => preparation.current?.() ?? Promise.resolve(),
    }),
    React.createElement(ChatPanel, {
      ...panelProps,
      navigationPreparationRef: preparation,
      conversationListRef,
      chatLaunch,
      onChatLaunchHandled: () => setChatLaunch(null),
      historyNotice,
      onHistoryChanged: () => setHistoryRevision(value => value + 1),
      onActiveConversationId: setActiveConversationId,
    }),
  );
}

async function renderChat(vite, harness, props = {}) {
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
  globalThis.window = Object.assign(new EventTarget(), {
    workbench: { backendUrl: `http://127.0.0.1:${port}` },
    setInterval: (callback, delay) => { const id = setInterval(callback, delay); harness.state.testIntervals.set(id, callback); return id; },
    clearInterval: id => { clearInterval(id); harness.state.testIntervals.delete(id); },
  });
  const { ChatPanel } = await vite.ssrLoadModule("/src/renderer/ChatPanel.tsx");
  const { WorkbenchSidebar } = await vite.ssrLoadModule("/src/renderer/WorkbenchSidebar.tsx");
  let renderer;
  await act(async () => {
    renderer = create(React.createElement(StrictMode, null, React.createElement(ErrorBoundary, null, React.createElement(ChatHarness, { ChatPanel, WorkbenchSidebar, panelProps: props }))));
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
  const selected = renderer.root.findAll(node => typeof node.type === "function" && node.type.name === "ChatInteractionStream");
  return selected[0]?.props.conversation.current_run_id ?? null;
}

function buttons(renderer, label) {
  return renderer.root.findAll((node) => node.type === "button" &&
    (textOf(node).includes(label) || String(node.props["aria-label"] ?? "").includes(label)));
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

function assertFreshConversation(renderer, message) {
  assert.equal(renderer.root.findAll(node => node.type === "button" && node.props.className === "nav-item active").length, 0, message);
  assert.equal(renderer.root.findByProps({ "aria-label": "Chat project" }).props.disabled, false, message);
  assert.equal(selectedRunId(renderer), null, message);
}

function textarea(renderer) {
  const found = composeForm(renderer).findAll((node) => node.type === "textarea");
  assert.ok(found.length > 0, "expected textarea");
  return found[0];
}

function inputByPlaceholder(renderer, placeholder) {
  const found = renderer.root.findAll((node) => node.type === "input" && node.props.placeholder === placeholder);
  assert.ok(found.length > 0, `expected input ${placeholder}`);
  return found[0];
}

function inputByType(renderer, type) {
  const found = renderer.root.findAll((node) => node.type === "input" && node.props.type === type);
  assert.ok(found.length > 0, `expected input type ${type}`);
  return found[0];
}

function buttonByAriaLabel(renderer, label) {
  // Attachments now begin at the composer's Add menu; the actual file input
  // still owns native selection and upload, and is exercised below.
  if (label === "Attach files") label = "Add to message";
  const found = renderer.root.findAll((node) => node.type === "button" && node.props["aria-label"] === label);
  assert.ok(found.length > 0, `expected button aria-label ${label}`);
  return found[0];
}

function approvalModeButton(renderer, label) {
  const found = renderer.root.findAll(
    (node) => node.type === "button" && node.props.role === "radio" && node.props["aria-label"] === label,
  );
  assert.ok(found.length > 0, `expected approval mode ${label}`);
  return found[0];
}

function thinkingEffortSlider(renderer) {
  return renderer.root.findAll(node => node.type === "input" && node.props.type === "range" && node.props["aria-label"] === "Thinking level")[0];
}

async function openModelPicker(renderer) {
  const trigger = renderer.root.findAll(node => node.type === "button" && String(node.props["aria-label"] ?? "").startsWith("Chat model:"))[0];
  assert.ok(trigger, "Chat model picker is available");
  await act(async () => trigger.props.onClick());
}

async function applyModelChanges(renderer) {
  await waitFor(() => assert.equal(button(renderer, "Apply").props.disabled, false), "staged model preview ready");
  await act(async () => button(renderer, "Apply").props.onClick());
  await waitFor(() => assert.equal(textarea(renderer).props.disabled, false), "applied model setup ready for submission");
}

function testFile(name, content, type = "text/plain") {
  const bytes = new TextEncoder().encode(content);
  if (typeof File !== "undefined") {
    return new File([bytes], name, { type });
  }
  return {
    name,
    type,
    size: bytes.byteLength,
    arrayBuffer: async () => bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength),
  };
}

async function stageAttachment(renderer, filename = "note.md", content = "# note") {
  await act(async () => {
    buttonByAriaLabel(renderer, "Attach files").props.onClick();
    await Promise.resolve();
  });
  await act(async () => {
    inputByType(renderer, "file").props.onChange({
      target: { files: [testFile(filename, content, "text/markdown")] },
      currentTarget: { value: filename },
    });
    await Promise.resolve();
  });
  await waitFor(() => {
    const text = allText(renderer);
    assert.match(text, new RegExp(filename.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")));
    assert.match(text, /Attached/);
  }, `uploaded ${filename} ready`);
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
  if (Array.isArray(node)) {
    return node.map(textOf).join("");
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

async function testStartupRefreshFailureRemainsUsable(vite) {
  const navigated = [];
  const harness = makeHarness({ conversationListError: { status: 503, message: "History is temporarily unavailable" } });
  const renderer = await renderChat(vite, harness, { onNavigate: next => navigated.push(next) });
  try {
    await waitFor(() => assert.match(allText(renderer), /History is temporarily unavailable/), "initial history error visible");
    assert.ok(buttonByAriaLabel(renderer, "New chat"), "history failure retains New chat");
    assert.ok(buttonByAriaLabel(renderer, "Models"), "history failure retains navigation");
    await selectFixtureModel(renderer);
    assert.equal(buttonByAriaLabel(renderer, "Attach files").props.disabled, false, "independent model data remains usable");
    await act(async () => { buttonByAriaLabel(renderer, "Models").props.onClick(); });
    await waitFor(() => assert.deepEqual(navigated, ["models"]), "navigation works after load failure");
    harness.state.conversationListError = null;
    await act(async () => { button(renderer, "Retry").props.onClick(); });
    await waitFor(() => button(renderer, "Conversation A"), "retry restores history");
    assert.doesNotMatch(allText(renderer), /History is temporarily unavailable/);
  } finally { await closeHarness(renderer, harness); }
}

async function testDeletedHistorySelectionRecoversToNewChat(vite) {
  const harness = makeHarness();
  const renderer = await renderChat(vite, harness);
  try {
    await waitFor(() => button(renderer, "Conversation A"), "history loaded before external deletion");
    delete harness.state.conversations.conv_a;
    await act(async () => { button(renderer, "Conversation A").props.onClick(); });
    await waitFor(() => assert.match(allText(renderer), /no longer available/i), "missing selected chat has clear recovery");
    assertFreshConversation(renderer, "deleted selection returns to New chat");
    assert.equal(buttons(renderer, "Conversation A").length, 0, "deleted history entry removed");
    assert.equal(harness.state.requests.registers.length, 0, "missing chat never registers an interaction thread");
    await selectFixtureModel(renderer);
    assert.equal(buttonByAriaLabel(renderer, "Attach files").props.disabled, false);
  } finally { await closeHarness(renderer, harness); }
}

async function testStartupRestorationBlocksComposer(vite) {
  const harness = makeHarness();
  const renderer = await renderChat(vite, harness, { restoringSelection: true });
  try {
    await waitFor(() => button(renderer, "Conversation A"), "normal catalogue loaded while restore remains pending");
    assert.equal(textarea(renderer).props.disabled, true);
    assert.equal(buttonByAriaLabel(renderer, "Opening conversation…").props.disabled, true);
    await act(async () => textarea(renderer).props.onChange({ target: { value: "Cannot submit into an unresolved selection" } }));
    await act(async () => composeForm(renderer).props.onSubmit({ preventDefault() {}, currentTarget: { querySelectorAll: () => [] } }));
    assert.equal(harness.state.requests.commands.length, 0);
    assert.equal(harness.state.requests.registers.length, 0);
    assert.equal(harness.state.outgoingRequests.some(item => item.path === "/v1/chat/conversations" && item.method === "POST"), false, "restoration cannot create or submit a new chat");
  } finally { await closeHarness(renderer, harness); }
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
    await waitFor(() => assert.equal(selectedRunId(renderer), "run_a"), "A run projection");
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
    assert.ok(renderer.root.findAll(node => node.type === "article" && node.props.className === "bubble bubble-user" && textOf(node).includes("Conversation B")).length,
      "held B registration should show the fetched transcript");
    assert.equal(buttonByAriaLabel(renderer, "Opening conversation…").props.disabled, true, "opening an existing chat cannot claim a message is being sent");
    assert.equal(harness.state.requests.commands.length, 0, "opening a conversation submits no message");
    assert.equal(harness.state.openStreams.has("thread_a"), false, "A stream must not remain attached while B registration is held");
    // Keep the originating server response even after the client detaches.
    // The producer attempts a real late write; looking it up after removal
    // would silently skip the event this regression is meant to exercise.
    oldAStream.write(`data: ${JSON.stringify(streamFrame(run("run_a_late"), "late A frame"))}\n\n`);
    await flush();
    assert.doesNotMatch(allText(renderer), /late A frame/i, "late A stream frames must not attach while B registration is held");
    assert.equal(selectedRunId(renderer), null, "loading selection must not keep A's live transport mounted");

    await releaseResponse(harness, heldRegister, "/v1/agent-interaction/threads", "POST");
    await waitFor(() => assert.match(activeConversationTitle(renderer), /Conversation B/), "B selected after registration");
    assert.equal(selectedRunId(renderer), null, "B must not render A's run after B registration completes");
    assert.equal(harness.state.requests.registers.at(-1).conversation_id, "conv_b");
  } finally {
    heldRegister.resolve();
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
      button(renderer, "Stop").props.onClick();
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
    await selectFixtureModel(renderer);
    await act(async () => {
      textarea(renderer).props.onChange({ target: { value: "create then leave" } });
      await Promise.resolve();
    });
    await act(async () => {
      composeForm(renderer).props.onSubmit({ preventDefault() {}, currentTarget: { querySelectorAll: () => [] } });
      await Promise.resolve();
    });
    await act(async () => {
      button(renderer, "New").props.onClick();
      await Promise.resolve();
    });
    await releaseResponse(harness, heldCreate, "/v1/chat/conversations", "POST");
    assertFreshConversation(renderer, "New should remain active after delayed create/register");
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
    await selectFixtureModel(renderer);
    await act(async () => {
      textarea(renderer).props.onChange({ target: { value: "create then registration waits" } });
      await Promise.resolve();
    });
    await waitFor(() => assert.equal(textarea(renderer).props.value, "create then registration waits"), "new conversation draft");
    await act(async () => {
      composeForm(renderer).props.onSubmit({ preventDefault() {}, currentTarget: { querySelectorAll: () => [] } });
      await Promise.resolve();
    });
    await waitFor(() => assert.equal(harness.state.requests.registers.at(-1)?.conversation_id, "conv_new"), "new conversation registration held");
    await act(async () => {
      button(renderer, "New").props.onClick();
      await Promise.resolve();
    });
    await releaseResponse(harness, heldRegister, "/v1/agent-interaction/threads", "POST");
    assertFreshConversation(renderer, "New should remain active after delayed new-conversation registration");
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
    await waitFor(() => assert.ok(renderer.root.findAll(node => node.type === "article" && node.props.className === "bubble bubble-user" && textOf(node).includes("Conversation B")).length), "fetched B transcript visible during registration");
    assert.equal(textarea(renderer).props.disabled, true, "composer waits for registration while the transcript is visible");
    await act(async () => {
      textarea(renderer).props.onChange({ target: { value: "must not submit while binding" } });
      await Promise.resolve();
    });
    composeForm(renderer).props.onSubmit({ preventDefault() {}, currentTarget: { querySelectorAll: () => [] } });
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
      composeForm(renderer).props.onSubmit({ preventDefault() {}, currentTarget: { querySelectorAll: () => [] } });
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
      composeForm(renderer).props.onSubmit({ preventDefault() {}, currentTarget: { querySelectorAll: () => [] } });
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
      (node) => node.type === "section" && node.props.className === "chat-group" && textOf(node).includes("Original Project"),
    );
    assert.equal(group.length, 1, "branches with the same immutable area should share one group");
    const headers = renderer.root.findAll(
      (node) => node.type === "button" && node.props.className === "chat-group-toggle" && textOf(node).includes("Original Project"),
    );
    assert.equal(headers.length, 1, "header label should use the immutable original area label");
    assert.equal(renderer.root.findAll((node) => node.type === "button" && node.props.className === "chat-group-toggle" && textOf(node).includes("branch-a")).length, 0, "group header must not use execution workspace A");
    assert.equal(renderer.root.findAll((node) => node.type === "button" && node.props.className === "chat-group-toggle" && textOf(node).includes("branch-b")).length, 0, "group header must not use execution workspace B");
    const groupText = textOf(group[0]);
    assert.match(groupText, /Branch from restored workspace A/);
    assert.match(groupText, /Branch from restored workspace B/);
    await act(async () => button(renderer, "Branch from restored workspace A").props.onClick());
    await waitFor(() => assert.ok(harness.state.requests.states.includes("thread_a")), "workspace branch selected");
    await act(async () => textarea(renderer).props.onChange({ target: { value: "Continue inside this branch" } }));
    await act(async () => composeForm(renderer).props.onSubmit({ preventDefault() {}, currentTarget: { querySelectorAll: () => [] } }));
    await waitFor(() => assert.equal(harness.state.requests.commands.length, 1), "workspace branch submission sent");
    const config = harness.state.requests.commands[0].payload.params.metadata.workbench;
    assert.equal(config.workspace_id, "workspace_a", "continuation preserves restored workspace identity");
    assert.equal(config.project_path, "D:\\LocalAIWorkbench\\workspaces\\branch-a");
    assert.equal(harness.state.requests.draftUpdates.at(-1).payload.intended_config.workspace_id, "workspace_a");
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
      composeForm(renderer).props.onSubmit({ preventDefault() {}, currentTarget: { querySelectorAll: () => [] } });
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
      composeForm(renderer).props.onSubmit({ preventDefault() {}, currentTarget: { querySelectorAll: () => [] } });
      await Promise.resolve();
    });
    await waitFor(() => assert.equal(harness.state.requests.commands.length, 1), "pending follow-up command held");
    const waiting = renderer.root.findByProps({ className: "chat-waiting" });
    assert.equal(waiting.props.role, "status", "waiting is announced once in the answer area");
    assert.match(textOf(waiting), /Preparing reply/, "pending submit shows its own preparation status");
    assert.doesNotMatch(textOf(waiting), /Cancelled|Stopped/, "pending submit must not reuse previous terminal run status");
    assert.equal(buttonByAriaLabel(renderer, "Starting…").props.disabled, true,
      "a pending submission without an accepted run cannot queue another message");
    assert.equal(textarea(renderer).props.disabled, false, "the next draft remains editable while admission is pending");
    await act(async () => textarea(renderer).props.onChange({ target: { value: "Second draft while starting" } }));
    await act(async () => composeForm(renderer).props.onSubmit({ preventDefault() {}, currentTarget: { querySelectorAll: () => [] } }));
    assert.equal(harness.state.requests.queues.length, 0, "submitting again before run admission cannot create an idle queue item");
    heldCommand.resolve();
    await waitFor(() => assert.equal(textarea(renderer).props.value, "Second draft while starting"), "later draft survives the first command acknowledgement");
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
      composeForm(renderer).props.onSubmit({ preventDefault() {}, currentTarget: { querySelectorAll: () => [] } });
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
    await waitFor(() => assert.equal((harness.state.chatGetCounts.get("conv_a") ?? 0) >= 3, true), "terminal hydration fetched after cleared pending cancel");
    assert.equal(selectedRunId(renderer), "run_after_pending_cancel", "stale terminal hydration must not restore the previous cancelled run");
    assert.deepEqual(harness.state.requests.cancels, [], "reopened pending cancel must not call previous run cancel");
    assert.deepEqual(harness.state.requests.chatCancels, [], "reopened pending cancel must not send a new stop without a local submission");
  } finally {
    await closeHarness(renderer, harness);
  }
}

async function testProjectAttachmentScope(vite) {
  const project = { id: "project_review", name: "Workspace review", path: "D:\\Projects\\Review", canonical_path: "d:\\projects\\review", defaults: { deployment_id: "dep_1" }, active: true };
  for (const mode of ["picker", "drop"]) {
    const harness = makeHarness({ aRun: null, threadARun: null, threadNewRun: null, projects: [project], commandRejects: true,
      resolveSetup: payload => ({ configuration: payload.project_id ? project.defaults : {}, instruction_layers: [] }) });
    const renderer = await renderChat(vite, harness, { workspaceLaunch: { id: `project-${mode}`, projectId: project.id } });
    try {
      await waitFor(() => { const select = renderer.root.findByProps({ "aria-label": "Chat project" }); assert.equal(select.props.value, project.id); assert.equal(select.props.disabled, false); assert.equal(buttonByAriaLabel(renderer, "Attach files").props.disabled, false); }, "project launch setup ready");
      if (mode === "picker") {
        await act(async () => buttonByAriaLabel(renderer, "Attach files").props.onClick());
        await waitFor(() => assert.equal(inputByType(renderer, "file").props.disabled, false), "new project attachment picker ready");
        await act(async () => inputByType(renderer, "file").props.onChange({ target: { files: [testFile("review.csv", "topic,count\nreview,2\n", "text/csv")] }, currentTarget: { value: "review.csv" } }));
      } else {
        await act(async () => renderer.root.findByProps({ className: "chat-main" }).props.onDrop({ preventDefault() {}, stopPropagation() {}, dataTransfer: { types: ["Files"], files: [testFile("review.csv", "topic,count\nreview,2\n", "text/csv")] } }));
      }
      await waitFor(() => assert.match(allText(renderer), /Attached/), "project upload ready");
      assert.equal(harness.state.requests.creates[0].project_id, project.id, "attachment preparation creates the selected canonical project conversation");
      assert.equal(harness.state.requests.assetUploads[0].session_id, "conv_new");
      await act(async () => textarea(renderer).props.onChange({ target: { value: "Use the attached review table." } }));
      await act(async () => composeForm(renderer).props.onSubmit({ preventDefault() {}, currentTarget: { querySelectorAll: () => [] } }));
      await waitFor(() => assert.equal(harness.state.requests.commands.length, 1), "project attachment submitted");
      const submitted = harness.state.requests.commands[0].payload.params.metadata.workbench;
      assert.equal(submitted.project_id, project.id);
      assert.equal(Object.hasOwn(submitted, "workspace_id"), false, "canonical project submission must not assert a null workspace without its project path");
      assert.deepEqual(submitted.attachment_ids, ["asset_1"]);
      assert.equal(harness.state.requests.draftUpdates.at(-1).payload.intended_config.project_id, project.id);
      await waitFor(() => assert.match(allText(renderer), /Model startup failed before a run was accepted/), "failed project submission remains actionable");
      assert.equal(textarea(renderer).props.value, "Use the attached review table.", "failed submission preserves project draft text");
      assert.match(allText(renderer), /review\.csv/, "failed submission preserves the staged source");
      assert.equal(renderer.root.findByProps({ "aria-label": "Chat project" }).props.value, project.id);
    } finally { await closeHarness(renderer, harness); }
  }
}

async function testWholeChatDropStagesFiles(vite, fresh = false) {
  const harness = makeHarness({ aRun: null, threadARun: null });
  const renderer = await renderChat(vite, harness);
  try {
    await waitFor(() => button(renderer, "Conversation A"), "chat list loaded before drop");
    if (fresh) await selectFixtureModel(renderer);
    if (!fresh) {
      await act(async () => button(renderer, "Conversation A").props.onClick());
      await waitFor(() => assert.ok(harness.state.requests.states.includes("thread_a")), "existing chat bound before drop");
    }
    const surface = () => renderer.root.findByProps({ className: "chat-main" });
    assert.equal(typeof surface().props.onDrop, "function", "the ordinary Chat surface must accept files while the attachment picker is closed");
    let prevented = 0;
    await act(async () => surface().props.onDrop({
      preventDefault() { prevented += 1; }, stopPropagation() {}, dataTransfer: { types: ["text/plain"], files: [] },
    }));
    assert.equal(prevented, 0, "normal text dragging retains its usual behaviour");
    const file = testFile("dropped-note.md", "The verification code is amber-meadow-72.", "text/markdown");
    await act(async () => {
      surface().props.onDrop({
        preventDefault() { prevented += 1; }, stopPropagation() {},
        dataTransfer: { types: ["Files"], files: [file] },
      });
    });
    await waitFor(() => assert.equal(harness.state.requests.assetUploads.length, 1, allText(renderer).slice(-2400)), "dropped file reaches the retained upload owner");
    await waitFor(() => assert.match(allText(renderer), /dropped-note.md/), "drop reveals the staged filename");
    const attachment = renderer.root.findByProps({ "aria-label": "Composer attachments" });
    assert.match(attachment.props.className, /compact-attachments/, "dropped files appear as visible composer chips");
    assert.equal(prevented, 1, "drop prevents Chromium file navigation");
    assert.equal(harness.state.requests.assetUploads[0].session_id, fresh ? "conv_new" : "conv_a");
    await waitFor(() => assert.equal(buttonByAriaLabel(renderer, "Send").props.disabled, false), "attachment-only Send becomes available");
    await act(async () => composeForm(renderer).props.onSubmit({ preventDefault() {}, currentTarget: { querySelectorAll: () => [] } }));
    await waitFor(() => assert.equal(harness.state.requests.commands.length, 1), "attachment-only drop submits once");
    assert.deepEqual(harness.state.requests.commands[0].payload.params.metadata.workbench.attachment_ids, ["asset_1"]);
    assert.equal(harness.state.requests.assetUploads.length, 1, "one drop is not uploaded twice");
  } finally {
    await closeHarness(renderer, harness);
  }
}

async function testAttentionActivationDoesNotPinConversation(vite) {
  const harness = makeHarness();
  const handled = [];
  const renderer = await renderChat(vite, harness, {
    attentionConversationId: "conv_a",
    onAttentionHandled: id => handled.push(id),
  });
  try {
    await waitFor(() => assert.match(activeConversationTitle(renderer), /Conversation A/), "notification conversation selected");
    await waitFor(() => assert.ok(renderer.root.findAll(node => typeof node.type === "function" && node.type.name === "ChatInteractionStream" && node.props.conversation.id === "conv_a").length), "notification conversation fully bound before switching");
    assert.deepEqual(handled, ["conv_a"], "notification selection is consumed once");
    const previousReads = harness.state.chatGetCounts.get("conv_a");
    await act(async () => { button(renderer, "Conversation B").props.onClick(); });
    await waitFor(() => assert.match(activeConversationTitle(renderer), /Conversation B/), "history selection remains available after notification activation");
    await flush();
    assert.equal(harness.state.chatGetCounts.get("conv_a"), previousReads, "notification target cannot trigger another read when selecting a different conversation");
    assert.equal(harness.state.requests.commands.length, 0, "opening attention cannot submit or replay work");
  } finally { await closeHarness(renderer, harness); }
}

async function testExternalAttentionNavigationPreservesDraft(vite) {
  const harness = makeHarness({ aRun: null, threadARun: null });
  const navigationPreparationRef = { current: null };
  const renderer = await renderChat(vite, harness, { navigationPreparationRef });
  try {
    await waitFor(() => button(renderer, "Conversation A"), "initial history loaded");
    await act(async () => { button(renderer, "Conversation A").props.onClick(); });
    await waitFor(() => assert.match(activeConversationTitle(renderer), /Conversation A/), "conversation selected");
    await waitFor(() => assert.ok(renderer.root.findAll(node => typeof node.type === "function" && node.type.name === "ChatInteractionStream" && node.props.conversation.id === "conv_a").length), "conversation ready for draft editing");
    await act(async () => { textarea(renderer).props.onChange({ target: { value: "Draft typed immediately before activating a task notification" } }); });
    assert.equal(typeof navigationPreparationRef.current, "function", "notification navigation uses Chat's draft-save boundary");
    let canNavigate;
    await act(async () => { canNavigate = await navigationPreparationRef.current(); });
    assert.equal(canNavigate, true);
    assert.equal(harness.state.conversations.conv_a.draft.content, "Draft typed immediately before activating a task notification", "draft reaches durable state before leaving Chat");
    assert.equal(harness.state.requests.commands.length, 0);
  } finally { await closeHarness(renderer, harness); }
  assert.equal(navigationPreparationRef.current, null, "unmounted Chat cannot receive later notification navigation");
}

async function testFileDropDuringNewChatRegistrationCannotRetarget(vite) {
  const held = deferred();
  const harness = makeHarness({ aRun: null, threadARun: null });
  harness.state.barriers.register.set("conv_new", held);
  const renderer = await renderChat(vite, harness);
  try {
    await waitFor(() => button(renderer, "Conversation A"), "chat list loaded");
    await selectFixtureModel(renderer);
    await act(async () => renderer.root.findByProps({ className: "chat-main" }).props.onDrop({
      preventDefault() {}, stopPropagation() {},
      dataTransfer: { types: ["Files"], files: [testFile("old-drop.txt", "old drop")] },
    }));
    await waitFor(() => assert.equal(harness.state.requests.registers.at(-1)?.conversation_id, "conv_new"), "new drop waits on session registration");
    await act(async () => button(renderer, "Conversation A").props.onClick());
    await waitFor(() => assert.match(activeConversationTitle(renderer), /Conversation A/), "another conversation selected");
    held.resolve();
    await flush();
    assert.equal(harness.state.requests.assetUploads.length, 0, "obsolete drop is not uploaded into another session");
    assert.doesNotMatch(allText(renderer), /old-drop.txt/);
  } finally {
    held.resolve();
    await closeHarness(renderer, harness);
  }
}

async function testAttachmentOnlySdkSubmitKeepsMetadata(vite) {
  const harness = makeHarness({
    aRun: null,
    threadARun: null,
    deployments: [{ ...baseDeployment, bundle_id: "bundle_1" }],
  });
  const renderer = await renderChat(vite, harness);
  try {
    await waitFor(() => button(renderer, "Conversation A"), "initial chat list");
    await act(async () => {
      button(renderer, "Conversation A").props.onClick();
      await Promise.resolve();
    });
    await waitFor(() => assert.ok(harness.state.requests.states.includes("thread_a")), "A bound before attachment submit");
    await stageAttachment(renderer, "attachment-only.md", "attached context");
    await waitFor(() => assert.equal(harness.state.requests.assetUploads.length, 1), "attachment-only upload captured");
    await act(async () => {
      approvalModeButton(renderer, "Full access").props.onClick();
    });
    await openModelPicker(renderer);
    await waitFor(() => assert.equal(thinkingEffortSlider(renderer)?.props.disabled, false), "thinking preview ready after access change");
    await act(async () => {
      thinkingEffortSlider(renderer).props.onChange({ target: { value: "2" } });
      await Promise.resolve();
    });
    await applyModelChanges(renderer);
    await act(async () => {
      composeForm(renderer).props.onSubmit({ preventDefault() {}, currentTarget: { querySelectorAll: () => [] } });
      await Promise.resolve();
    });
    await waitFor(() => assert.equal(harness.state.requests.commands.length, 1), "attachment-only SDK command captured");
    const command = harness.state.requests.commands[0].payload;
    const message = command.params.input.messages[0];
    const metadata = command.params.metadata.workbench;
    assert.equal(message.content, "", "attachment-only submit sends an empty human message body");
    assert.deepEqual(metadata.attachment_ids, ["asset_1"], "SDK metadata preserves staged attachment ids");
    assert.equal(metadata.approval_mode, "full_access", "approval mode is carried in SDK metadata");
    assert.deepEqual(metadata.per_request_overrides, { reasoning_effort: "high" }, "per-message reasoning override is carried in SDK metadata");
    assert.equal(command.params.multitaskStrategy, "reject", "SDK direct submit preserves reject multitask strategy");
  } finally {
    await closeHarness(renderer, harness);
  }
}

async function testFreshDraftPersistsBeforeImmediateNavigation(vite) {
  const navigations = [];
  const harness = makeHarness({ aRun: null, threadARun: null });
  const renderer = await renderChat(vite, harness, { onNavigate: (tab) => navigations.push(tab) });
  try {
    await waitFor(() => button(renderer, "Conversation A"), "initial chat list");
    await selectFixtureModel(renderer);
    await act(async () => {
      textarea(renderer).props.onChange({ target: { value: "fresh unsent draft" } });
      await Promise.resolve();
    });
    await act(async () => {
      button(renderer, "Models").props.onClick();
      await Promise.resolve();
    });
    await waitFor(() => assert.equal(harness.state.requests.draftUpdates.length, 1), "fresh draft saved before tab navigation");
    assert.equal(harness.state.requests.draftUpdates[0].id, "conv_new");
    assert.equal(harness.state.requests.draftUpdates[0].payload.content, "fresh unsent draft");
    assert.equal(harness.state.conversations.conv_new.draft.content, "fresh unsent draft");
    await waitFor(() => assert.equal(navigations.length, 1), "navigation proceeds once after draft persistence");
    assert.equal(navigations[0], "models", "navigation target is preserved after draft persistence");
  } finally {
    await closeHarness(renderer, harness);
  }
}

async function testFreshSubmitSharesCreatedDraftSessionAndSendsRevision(vite) {
  const harness = makeHarness({ aRun: null, threadARun: null, commandProjectsRun: true });
  const renderer = await renderChat(vite, harness);
  try {
    await waitFor(() => button(renderer, "Conversation A"), "initial chat list");
    await selectFixtureModel(renderer);
    await act(async () => {
      textarea(renderer).props.onChange({ target: { value: "fresh submit after draft save" } });
      await Promise.resolve();
    });
    await act(async () => {
      composeForm(renderer).props.onSubmit({ preventDefault() {}, currentTarget: { querySelectorAll: () => [] } });
      await Promise.resolve();
    });
    await waitFor(() => assert.equal(harness.state.requests.draftUpdates.length, 1), "fresh submit saves draft once");
    await waitFor(() => assert.equal(harness.state.requests.registers.at(-1)?.conversation_id, "conv_new"), "fresh submit registers created draft conversation");
    await waitFor(() => assert.equal(harness.state.requests.commands.length, 1), "fresh submit command sent");
    assert.equal(harness.state.requests.draftUpdates[0].id, "conv_new");
    assert.equal(harness.state.requests.commands[0].threadId, "thread_new");
    assert.equal(
      harness.state.requests.commands[0].payload.params.metadata.workbench.draft_revision,
      1,
      "SDK metadata carries the persisted submitted draft revision",
    );
    assert.equal(Object.keys(harness.state.conversations).filter((id) => id === "conv_new").length, 1, "draft save and submit share one created conversation");
    assert.equal(harness.state.conversations.conv_new.draft.revision, 2, "accepted command clears submitted draft with incremented revision");
    assert.equal(harness.state.conversations.conv_new.draft.content, "");
  } finally {
    await closeHarness(renderer, harness);
  }
}

async function testAcceptedDraftNextSaveUsesIncrementedRevision(vite) {
  const draft = {
    content: "send saved draft",
    content_blocks: null,
    attachment_ids: [],
    intended_config: { work_mode: "work", helper_agent_ids: [], review: { enabled: false, criteria: "", max_revisions: 2 }, deployment_id: "dep_1", model_configuration_id: null, startup_overrides: {}, project_path: null, workspace_id: null, embedding_deployment_id: null, presented_tools: null, per_request_overrides: {}, knowledge_version_refs: [], memory_version_refs: [], skill_version_refs: [], protected_instruction_version_refs: [] },
    revision: 4,
    updated_at: now(),
  };
  const savedConversation = conversation("conv_a", "Conversation A", null, { draft });
  const harness = makeHarness({ aRun: null, threadARun: null, commandProjectsRun: true });
  harness.state.conversations.conv_a = savedConversation;
  const renderer = await renderChat(vite, harness);
  try {
    await waitFor(() => button(renderer, "Conversation A"), "initial chat list");
    await act(async () => {
      button(renderer, "Conversation A").props.onClick();
      await Promise.resolve();
    });
    await waitFor(() => assert.equal(textarea(renderer).props.value, "send saved draft"), "saved draft restored");
    await waitFor(() => assert.equal(textarea(renderer).props.disabled, false), "saved draft chat registered before Send");
    await act(async () => {
      composeForm(renderer).props.onSubmit({ preventDefault() {}, currentTarget: { querySelectorAll: () => [] } });
      await Promise.resolve();
    });
    await waitFor(() => assert.equal(harness.state.requests.commands.length, 1), "saved draft command sent");
    assert.equal(
      harness.state.requests.commands[0].payload.params.metadata.workbench.draft_revision,
      4,
      "submitted saved draft revision is sent in SDK metadata",
    );
    await waitFor(() => assert.equal(textarea(renderer).props.value, ""), "accepted saved draft clears composer");
    await act(async () => {
      textarea(renderer).props.onChange({ target: { value: "next unsent draft" } });
      await Promise.resolve();
    });
    await waitFor(() => {
      const last = harness.state.requests.draftUpdates.at(-1);
      assert.equal(last?.payload.content, "next unsent draft");
      assert.equal(last?.payload.expected_revision, 5);
    }, "next draft save uses incremented accepted revision");
  } finally {
    await closeHarness(renderer, harness);
  }
}

async function testQueuedDraftClearDoesNotEraseLaterDraft(vite) {
  const draft = {
    content: "queue saved draft",
    content_blocks: null,
    attachment_ids: [],
    intended_config: { work_mode: "work", helper_agent_ids: [], review: { enabled: false, criteria: "", max_revisions: 2 }, deployment_id: "dep_1", model_configuration_id: null, startup_overrides: {}, project_path: null, workspace_id: null, embedding_deployment_id: null, presented_tools: null, per_request_overrides: {}, knowledge_version_refs: [], memory_version_refs: [], skill_version_refs: [], protected_instruction_version_refs: [] },
    revision: 3,
    updated_at: now(),
  };
  const busyRun = run("run_busy", "running");
  const busyConversation = conversation("conv_a", "Conversation A", busyRun, { draft });
  const harness = makeHarness({ aRun: busyRun, threadARun: busyRun });
  harness.state.conversations.conv_a = busyConversation;
  const renderer = await renderChat(vite, harness);
  try {
    await waitFor(() => button(renderer, "Conversation A"), "initial chat list");
    await act(async () => {
      button(renderer, "Conversation A").props.onClick();
      await Promise.resolve();
    });
    await waitFor(() => assert.equal(textarea(renderer).props.value, "queue saved draft"), "queued draft restored");
    await waitFor(() => assert.equal(textarea(renderer).props.disabled, false), "queued draft chat registered before Queue");
    await act(async () => {
      composeForm(renderer).props.onSubmit({ preventDefault() {}, currentTarget: { querySelectorAll: () => [] } });
      await Promise.resolve();
    });
    await waitFor(() => assert.equal(harness.state.requests.queues.length, 1), "queued saved draft request sent");
    assert.equal(harness.state.requests.queues[0].payload.draft_revision, 3, "queue payload carries submitted draft revision");
    await waitFor(() => assert.equal(textarea(renderer).props.value, ""), "queued draft clears composer");
    assert.equal(harness.state.conversations.conv_a.draft.revision, 4, "queue response increments cleared draft revision");
    await act(async () => {
      textarea(renderer).props.onChange({ target: { value: "newer draft after queue" } });
      await Promise.resolve();
    });
    await waitFor(() => {
      const last = harness.state.requests.draftUpdates.at(-1);
      assert.equal(last?.payload.content, "newer draft after queue");
      assert.equal(last?.payload.expected_revision, 4);
    }, "newer post-queue draft saves against incremented revision");
    assert.equal(harness.state.conversations.conv_a.draft.content, "newer draft after queue");
  } finally {
    await closeHarness(renderer, harness);
  }
}

async function testQueuedSubmitKeepsAttachmentsToolsAndOverrides(vite) {
  const harness = makeHarness({
    aRun: run("run_busy", "running"),
    threadARun: run("run_busy", "running"),
    deployments: [{ ...baseDeployment, bundle_id: "bundle_1" }],
  });
  harness.state.conversations.conv_a.workspace_id = "workspace_queue";
  harness.state.conversations.conv_a.project_path = "D:\\LocalAIWorkbench\\workspaces\\queued-branch";
  const renderer = await renderChat(vite, harness);
  try {
    await waitFor(() => button(renderer, "Conversation A"), "initial chat list");
    await act(async () => {
      button(renderer, "Conversation A").props.onClick();
      await Promise.resolve();
    });
    await waitFor(() => assert.ok(harness.state.requests.states.includes("thread_a")), "A bound before queued submit");
    await stageAttachment(renderer, "queued-context.md", "queued context");
    await act(async () => {
      textarea(renderer).props.onChange({ target: { value: "queued turn with attachment" } });
      approvalModeButton(renderer, "Full access").props.onClick();
    });
    await openModelPicker(renderer);
    await waitFor(() => assert.equal(thinkingEffortSlider(renderer)?.props.disabled, false), "queued thinking preview ready");
    await act(async () => {
      thinkingEffortSlider(renderer).props.onChange({ target: { value: "1" } });
      await Promise.resolve();
    });
    await applyModelChanges(renderer);
    await act(async () => {
      composeForm(renderer).props.onSubmit({ preventDefault() {}, currentTarget: { querySelectorAll: () => [] } });
      await Promise.resolve();
    });
    await waitFor(() => assert.equal(harness.state.requests.queues.length, 1), "queued submit captured");
    const queued = harness.state.requests.queues[0].payload;
    assert.equal(queued.task, "queued turn with attachment");
    assert.equal(queued.workspace_id, "workspace_queue", "queued branch keeps its owned workspace identity");
    assert.equal(queued.project_path, "D:\\LocalAIWorkbench\\workspaces\\queued-branch");
    assert.deepEqual(queued.attachment_ids, ["asset_1"], "queue request preserves staged attachment ids");
    assert.equal(queued.approval_mode, "full_access", "queue request preserves the approval mode");
    assert.deepEqual(queued.per_request_overrides, { reasoning_effort: "medium" }, "queue request preserves per-message reasoning override");
    assert.deepEqual(harness.state.conversations.conv_a.queue[0].intended_config.attachment_ids, ["asset_1"], "queued item intended config stores attachment ids for reload");
  } finally {
    await closeHarness(renderer, harness);
  }
}

async function testPersistedDraftRestoresAttachmentsAndIntendedConfig(vite) {
  const savedAsset = {
    id: "asset_saved",
    origin: "upload",
    scope: "session",
    session_id: "conv_a",
    project_path: null,
    access_scope: "session",
    storage: "application.sqlite",
    filename: "saved-draft.md",
    content_type: "text/markdown",
    content_kind: "text",
    encoding: "utf-8",
    size_bytes: 12,
    sha256: "sha_saved",
    observed_at: now(),
    source_run_id: null,
    source_tool_call_id: null,
    source_tool_name: null,
    mutable_reference: null,
    observation: null,
    deleted_at: null,
  };
  const draft = {
    content: "restored draft text",
    content_blocks: null,
    attachment_ids: ["asset_saved"],
    intended_config: {
      deployment_id: "dep_1",
      profile_id: null,
      inherit_deployment_settings: true,
      project_path: null,
      embedding_deployment_id: null,
      presented_tools: [],
      approval_mode: "full_access",
      per_request_overrides: { reasoning_effort: "high" },
    },
    revision: 7,
    updated_at: now(),
  };
  const restoredConversation = conversation("conv_a", "Conversation A", null, { draft });
  const harness = makeHarness({
    aRun: null,
    threadARun: null,
    assets: [savedAsset],
    deployments: [{ ...baseDeployment, bundle_id: "bundle_1" }],
  });
  harness.state.conversations.conv_a = restoredConversation;
  const renderer = await renderChat(vite, harness);
  try {
    await waitFor(() => button(renderer, "Conversation A"), "initial chat list");
    await act(async () => {
      button(renderer, "Conversation A").props.onClick();
      await Promise.resolve();
    });
    await waitFor(() => assert.equal(textarea(renderer).props.value, "restored draft text"), "draft content restored");
    await waitFor(() => assert.match(allText(renderer), /saved-draft\.md/), "draft attachment restored from session assets");
    assert.equal(renderer.root.findByProps({ "aria-label": "Composer attachments" }).props.className, "packet03-attachments compact-attachments", "restored draft attachments are visible as chips before sending");
    assert.equal(harness.state.requests.assetLists.at(-1)?.sessionId, "conv_a", "draft restore lists assets for the selected conversation");
    assert.equal(approvalModeButton(renderer, "Full access").props["aria-checked"], true, "draft intended config restores the approval mode");
    await openModelPicker(renderer);
    await waitFor(() => assert.equal(thinkingEffortSlider(renderer)?.props["aria-valuetext"], "High"), "draft intended config restores per-message reasoning choice");
    await act(async () => {
      textarea(renderer).props.onChange({ target: { value: "restored draft text plus edit" } });
      await Promise.resolve();
    });
    await waitFor(() => assert.equal(harness.state.requests.draftUpdates.at(-1)?.payload.attachment_ids?.[0], "asset_saved"), "draft save retains restored attachment id");
    assert.deepEqual(
      harness.state.requests.draftUpdates.at(-1)?.payload.intended_config?.per_request_overrides,
      { reasoning_effort: "high" },
      "draft save retains restored intended per-message config",
    );
  } finally {
    await closeHarness(renderer, harness);
  }
}

async function testLateUploadAfterNavigationDoesNotAttachToNewConversation(vite) {
  const heldUpload = deferred();
  const harness = makeHarness({
    aRun: null,
    bRun: null,
    threadARun: null,
    threadBRun: null,
  });
  const renderer = await renderChat(vite, harness);
  try {
    harness.state.barriers.assetUpload.set("conv_a", heldUpload);
    await waitFor(() => button(renderer, "Conversation A"), "initial chat list");
    await act(async () => {
      button(renderer, "Conversation A").props.onClick();
      await Promise.resolve();
    });
    await waitFor(() => assert.ok(harness.state.requests.states.includes("thread_a")), "A bound before late upload");
    await act(async () => {
      buttonByAriaLabel(renderer, "Attach files").props.onClick();
      await Promise.resolve();
    });
    await act(async () => {
      inputByType(renderer, "file").props.onChange({
        target: { files: [testFile("late-a.md", "late A", "text/markdown")] },
        currentTarget: { value: "late-a.md" },
      });
      await Promise.resolve();
    });
    await waitFor(() => assert.equal(harness.state.requests.assetUploads.length, 1), "late A upload started");
    await act(async () => {
      button(renderer, "Conversation B").props.onClick();
      await Promise.resolve();
    });
    await waitFor(() => assert.equal(harness.state.requests.registers.at(-1)?.conversation_id, "conv_b"), "B selected while A upload held");
    heldUpload.resolve();
    await flush();
    await waitFor(() => assert.equal(activeConversationTitle(renderer).includes("Conversation B"), true), "B remains selected after late A upload resolves");
    assert.doesNotMatch(allText(renderer), /late-a\.md/, "late upload from previous conversation must not attach to newly selected conversation");
    await act(async () => {
      textarea(renderer).props.onChange({ target: { value: "B message" } });
      await Promise.resolve();
    });
    await act(async () => {
      composeForm(renderer).props.onSubmit({ preventDefault() {}, currentTarget: { querySelectorAll: () => [] } });
      await Promise.resolve();
    });
    await waitFor(() => assert.equal(harness.state.requests.commands.length, 1), "B submit captured");
    assert.deepEqual(
      harness.state.requests.commands[0].payload.params.metadata.workbench.attachment_ids,
      [],
      "B submit must not inherit a late upload from A",
    );
  } finally {
    heldUpload.resolve();
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
    assert.doesNotMatch(allText(renderer), /This saved model setup will load when you send a message\./, "startup warming does not add a load-on-send sentence");
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

async function testMeasurementOnlyProjectionRefreshesCurrentConversation(vite) {
  const context = estimatedInput => ({
    schema_version: 1,
    capacity_tokens: 8192,
    capacity_source: "server_props.n_ctx",
    output_reservation_tokens: 1024,
    estimated_input_tokens: estimatedInput,
    margin_tokens: 64,
    fits: true,
    counting_method: "estimate",
    summarization_path: "deepagents-upstream",
    notes: [],
  });
  const initial = { ...run("measurement_run_a"), generation_observation: null, context_observation: context(1000) };
  const other = { ...run("measurement_run_b"), generation_observation: null, context_observation: context(300) };
  const measured = {
    ...initial,
    generation_observation: { input_tokens: 1200, output_tokens: 456, elapsed_seconds: 10, tokens_per_second: 45.6, context_limit: 8192, measured_at: now() },
    context_observation: initial.context_observation,
  };
  const harness = makeHarness({ aRun: initial, bRun: other });
  const renderer = await renderChat(vite, harness);
  const measurements = () => renderer.root.find(node => typeof node.type === "function" && node.type.name === "ChatMeasurements");
  const publish = async (threadId, projected) => {
    const stream = harness.state.openStreams.get(threadId);
    assert.ok(stream, `expected open ${threadId} SDK stream`);
    await act(async () => {
      stream.write(`data: ${JSON.stringify(streamFrame(projected))}\n\n`);
      await Promise.resolve();
    });
  };
  try {
    await waitFor(() => button(renderer, "Conversation A"), "initial chat list");
    await act(async () => button(renderer, "Conversation A").props.onClick());
    await waitFor(() => assert.ok(harness.state.openStreams.has("thread_a")), "A SDK stream connected");
    await waitFor(() => assert.equal(measurements().props.run?.context_observation?.estimated_input_tokens, 1000), "initial A context");
    assert.equal(measured.id, initial.id);
    assert.equal(measured.status, initial.status);
    assert.equal(measured.events.length, initial.events.length, "the update has no new audit event");
    await publish("thread_a", measured);
    await waitFor(() => assert.match(textOf(measurements()), /45\.6 tok\/s/), "same-event-count measurement reaches visible composer");
    assert.equal(measurements().props.run.context_observation.estimated_input_tokens, 1000, "generation-only update preserves its prepared request context");

    const readout = () => renderer.root.findByProps({ className: "chat-measurements" });
    await publish("thread_a", { ...measured, context_observation: context(1700) });
    await waitFor(() => assert.equal(Number(readout().props["data-estimated-input"]), 1700), "context-only update reaches composer without a new generation or audit event");

    const nextRequest = { ...measured, generation_observation: null, context_observation: context(2100) };
    await publish("thread_a", nextRequest);
    await waitFor(() => assert.equal(readout().props["data-tokens-per-second"], ""), "next model request clears previous generation");
    assert.equal(Number(readout().props["data-estimated-input"]), 2100);
    assert.doesNotMatch(textOf(measurements()), /45\.6 tok\/s/, "pending call must not show the preceding call's speed");

    await act(async () => button(renderer, "Conversation B").props.onClick());
    await waitFor(() => assert.equal(measurements().props.run?.id, other.id), "B owns composer measurements");
    await waitFor(() => assert.ok(harness.state.openStreams.has("thread_b")), "B SDK stream connected");
    await flush();
    await publish("thread_b", measured);
    await flush();
    assert.equal(measurements().props.run.id, other.id);
    assert.equal(measurements().props.run.context_observation.estimated_input_tokens, 300);
    assert.equal(measurements().props.run.generation_observation, null);
    assert.doesNotMatch(textOf(measurements()), /45\.6 tok\/s/, "A's late telemetry cannot bleed into B's composer");
  } finally {
    await closeHarness(renderer, harness);
  }
}

async function testSavingProjectStateDisablesStop(vite) {
  const initial = run("run_a");
  const finalizing = { ...initial, finalization_phase: "saving_changes", settled_status: "completed",
    events: [...initial.events, { at: now(), kind: "finalizing", detail: { phase: "saving_changes" } }] };
  const harness = makeHarness({ aRun: initial });
  const renderer = await renderChat(vite, harness);
  try {
    await waitFor(() => button(renderer, "Conversation A"), "initial chat list");
    await act(async () => button(renderer, "Conversation A").props.onClick());
    await waitFor(() => assert.ok(harness.state.openStreams.has("thread_a")), "A SDK stream connected");
    assert.equal(buttonByAriaLabel(renderer, "Stop").props.disabled, false, "Stop is available during execution");
    const stream = harness.state.openStreams.get("thread_a");
    await act(async () => {
      stream.write(`data: ${JSON.stringify(streamFrame(finalizing))}\n\n`);
      await Promise.resolve();
    });
    await waitFor(() => assert.equal(buttonByAriaLabel(renderer, "Saving project state").props.disabled, true), "Stop disabled during finalization");
    assert.match(allText(renderer), /Saving project state/);
    const cancelCount = harness.state.requests.cancels.length;
    await act(async () => buttonByAriaLabel(renderer, "Saving project state").props.onClick());
    assert.equal(harness.state.requests.cancels.length, cancelCount, "saving phase does not send a cancel request");
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
    assert.equal(button(renderer, "Stop").props.disabled, false, "the composer Stop control is the running stop");
    assert.doesNotMatch(allText(renderer), /Working/, "an observed active run has no duplicate generic progress row");
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
      composeForm(renderer).props.onSubmit({ preventDefault() {}, currentTarget: { querySelectorAll: () => [] } });
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
      composeForm(renderer).props.onSubmit({ preventDefault() {}, currentTarget: { querySelectorAll: () => [] } });
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
      composeForm(renderer).props.onSubmit({ preventDefault() {}, currentTarget: { querySelectorAll: () => [] } });
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

async function testArchiveImmediatelyLeavesHistoryAndSearch(vite) {
  for (const searching of [false, true]) {
    const harness = makeHarness({ aRun: null, bRun: null });
    const renderer = await renderChat(vite, harness);
    try {
      await waitFor(() => button(renderer, "Conversation A"), "initial chat list");
      if (searching) {
        await act(async () => {
          inputByPlaceholder(renderer, "Search chats").props.onChange({ target: { value: "Conversation" } });
        });
        await waitFor(() => assert.equal(harness.state.requests.searches.at(-1), "conversation"), "search requested");
      }
      await act(async () => button(renderer, "Archive").props.onClick());
      await waitFor(() => assert.equal(harness.state.requests.archives.length, 1), "archive persisted");
      await flush();
      const archivedId = harness.state.requests.archives[0].id;
      const archivedTitle = harness.state.conversations[archivedId].title;
      assert.equal(buttons(renderer, archivedTitle).length, 0,
        `${searching ? "Search" : "History"} must remove the archived row without navigation`);
      assert.equal(renderer.root.findAll(node => node.props.className === "conversation-row archived").length, 0);
    } finally {
      await closeHarness(renderer, harness);
    }
  }
}

async function testModelChangeClearsOnlyModelSpecificOverrides(vite) {
  const harness = makeHarness({
    aRun: null, threadARun: null, completeCommands: true,
    deployments: [{ ...baseDeployment, scope: "connected", bundle_id: null }, { ...baseDeployment, id: "dep_2", scope: "connected", bundle_id: null, display_name: "connected:Second model" }],
  });
  const renderer = await renderChat(vite, harness);
  const modelControls = () => renderer.root.findAll(node => typeof node.type === "function" && node.type.name === "ChatModelControls")[0];
  try {
    await waitFor(() => button(renderer, "Conversation A"), "initial chat list");
    await act(async () => button(renderer, "Conversation A").props.onClick());
    await waitFor(() => assert.equal(modelControls().props.conversationId, "conv_a"), "conversation A fully restored");
    await waitFor(() => assert.equal(modelControls().props.selectedDeploymentId, "dep_1"), "current model restored");
    await act(async () => approvalModeButton(renderer, "Full access").props.onClick());
    assert.equal(approvalModeButton(renderer, "Full access").props["aria-checked"], true, "Chat shows selected access before model choice");
    assert.equal(modelControls().props.configuration.approval_mode, "full_access", "Chat passes the selected access into model picker");
    const next = renderer.root.findAll(node => node.type === "button" && node.props.className === "chat-model-choice" && textOf(node).includes("Second model"))[0];
    assert.ok(next, "the second connected model is listed once");
    await act(async () => next.props.onClick());
    await waitFor(() => assert.equal(modelControls().props.selectedDeploymentId, "dep_2"), "explicit model choice binds immediately");
    assert.equal(approvalModeButton(renderer, "Full access").props["aria-checked"], true, "model choice preserves visible Chat access");
    await act(async () => textarea(renderer).props.onChange({ target: { value: "Use the second model" } }));
    await act(async () => composeForm(renderer).props.onSubmit({ preventDefault() {}, currentTarget: { querySelectorAll: () => [] } }));
    await waitFor(() => assert.equal(harness.state.requests.commands.length, 1), "selected model is sent");
    const submitted = harness.state.requests.commands[0].payload.params.metadata.workbench;
    assert.equal(submitted.deployment_id, "dep_2");
    assert.equal(submitted.approval_mode, "full_access");
  } finally {
    await closeHarness(renderer, harness);
  }
}

async function selectFixtureModel(renderer) {
  const choice = renderer.root.findAll(node => node.type === "button" && node.props.className === "chat-model-choice" && textOf(node).includes("test"))[0];
  assert.ok(choice, "fixture model is available to select explicitly");
  await act(async () => choice.props.onClick());
  await waitFor(() => {
    const picker = renderer.root.findAll(node => typeof node.type === "function" && node.type.name === "ChatModelControls")[0];
    assert.equal(picker.props.selectedDeploymentId, "dep_1");
  }, "fixture model applied to Chat");
}

async function testFirstTurnWindowsGrantPreservesDraft(vite) {
  const harness = makeHarness({ aRun: null, threadARun: null, completeCommands: true,
    resolveSetup: payload => ({ configuration: { ...payload.overrides, deployment_id: "dep_1", desktop_access: "selected" }, instruction_layers: [] }) });
  const renderer = await renderChat(vite, harness);
  try {
    await waitFor(() => buttonByAriaLabel(renderer, "Add to message"), "tool menu available");
    await waitFor(() => assert.equal(renderer.root.findAll(node => node.props["aria-label"] === "Chat project")[0].props.disabled, false), "fresh chat ready");
    await act(async () => textarea(renderer).props.onChange({ target: { value: "Inspect this window" } }));
    await act(async () => composeForm(renderer).props.onSubmit({ preventDefault() {}, currentTarget: { querySelectorAll: () => [] } }));
    await waitFor(() => assert.equal(harness.state.requests.creates.length, 1), "first send creates a chat for the live grant");
    await waitFor(() => assert.equal(textarea(renderer).props.value, "Inspect this window"), "the draft survives grant setup");
    assert.equal(harness.state.requests.commands.length, 0, "a turn cannot dispatch before the window is granted");
    await waitFor(() => assert.ok(buttons(renderer, "Choose window").length), "window chooser available in the current chat");
    await act(async () => button(renderer, "Choose window").props.onClick());
    await waitFor(() => assert.ok(buttons(renderer, "Use window").length), "live window listed");
    await act(async () => button(renderer, "Use window").props.onClick());
    await waitFor(() => assert.equal(harness.state.windowScope.scope, "selected"), "live selected-window grant saved");
    await act(async () => composeForm(renderer).props.onSubmit({ preventDefault() {}, currentTarget: { querySelectorAll: () => [] } }));
    await waitFor(() => assert.equal(harness.state.requests.commands.length, 1), "first turn sends after the grant");
  } finally { await closeHarness(renderer, harness); }
}

function visualControls(renderer) {
  return renderer.root.findAll(node => typeof node.type === "function" && node.type.name === "VisualTestingControls");
}

async function testSingleToolMenuBeforeModelAndRuntimeCleanup(vite) {
  const harness = makeHarness({ deployments: [], aRun: null, threadARun: null, browserInstalled: false });
  const renderer = await renderChat(vite, harness);
  try {
    const trigger = () => buttonByAriaLabel(renderer, "Add to message");
    await waitFor(() => assert.equal(trigger().props.disabled, false), "tool menu usable before choosing a model");
    assert.equal(visualControls(renderer).length, 0, "runtime controls do not mount while the menu is closed");
    assert.equal(renderer.root.findAll(node => node.type === "button" && node.props["aria-label"] === "Helpers").length, 0, "there is no second top-right helper button");
    await act(async () => trigger().props.onClick());
    await waitFor(() => assert.equal(visualControls(renderer).length, 1), "Browser and Windows have one control location in the + menu");
    await waitFor(() => assert.equal(visualControls(renderer)[0].findAll(node => node.type === "button" && node.props.className === "visual-testing-disclosure").length, 2), "both capability rows present");
    const browserRow = visualControls(renderer)[0].findAll(node => node.type === "button" && node.props.className === "visual-testing-disclosure")[0];
    await act(async () => browserRow.props.onClick());
    await waitFor(() => assert.ok(buttons(renderer, "Install browser worker").length), "Browser worker installation reachable before model choice");
    await act(async () => button(renderer, "Install browser worker").props.onClick());
    await waitFor(() => assert.equal(harness.state.browserInstalled, true), "pre-model worker installation completed");
    const browserRequests = () => harness.state.outgoingRequests.filter(item => item.path === "/v1/browser/runtime").length;
    await act(async () => trigger().props.onClick());
    await waitFor(() => assert.equal(visualControls(renderer).length, 0), "closing + unmounts its runtime controls");
    const closedCount = browserRequests();
    await act(async () => { for (const poll of harness.state.testIntervals.values()) poll(); await Promise.resolve(); });
    assert.equal(browserRequests(), closedCount, "no hidden Browser status polling remains after + closes");
  } finally { await closeHarness(renderer, harness); }
}

async function testToolReadinessActionsOpenRecovery(vite) {
  let issueCode = "browser_worker_missing";
  const harness = makeHarness({ aRun: null, threadARun: null, browserInstalled: false, browserSessionState: "lost", readiness: () => ({ status: "needs_action", can_send: false, issues: [{ code: issueCode, message: issueCode === "browser_worker_missing" ? "Browser worker needs installation" : "Browser session was lost", action: issueCode === "browser_worker_missing" ? "Install browser worker" : "Reset browser" }], selection: null }) });
  const renderer = await renderChat(vite, harness);
  try {
    await waitFor(() => button(renderer, "Conversation A"), "chat list ready");
    await act(async () => button(renderer, "Conversation A").props.onClick());
    await waitFor(() => assert.ok(buttons(renderer, "Install browser worker").length), "worker readiness action visible in chat");
    await act(async () => button(renderer, "Install browser worker").props.onClick());
    await waitFor(() => assert.equal(visualControls(renderer).length, 1), "readiness opens + menu");
    assert.equal(visualControls(renderer)[0].props.focusSection, "browser", "recovery focuses Browser row");
    assert.equal(visualControls(renderer)[0].findAll(node => node.type === "button" && node.props.className === "visual-testing-disclosure")[0].props["aria-expanded"], true, "Browser recovery detail expands");
    issueCode = "browser_session_lost";
    await act(async () => visualControls(renderer)[0].findAll(node => node.type === "button" && textOf(node) === "Install browser worker")[0].props.onClick());
    await waitFor(() => assert.ok(buttons(renderer, "Reset browser").length), "lost-session readiness follows installation");
    await act(async () => button(renderer, "Reset browser").props.onClick());
    assert.equal(visualControls(renderer)[0].props.focusSection, "browser", "lost-session recovery keeps Browser focused");
    await act(async () => visualControls(renderer)[0].findAll(node => node.type === "button" && textOf(node) === "Reset")[0].props.onClick());
    await waitFor(() => assert.equal(harness.state.browserSessionState, "closed"), "Reset recovery reaches the Browser session action");
  } finally { await closeHarness(renderer, harness); }
}

async function testArchivePreservesDraftBeforeLeaving(vite) {
  const harness = makeHarness({ aRun: null, threadARun: null });
  const renderer = await renderChat(vite, harness);
  try {
    await waitFor(() => button(renderer, "Conversation A"), "initial chat list");
    await act(async () => button(renderer, "Conversation A").props.onClick());
    await waitFor(() => assert.equal(renderer.root.findByProps({ "aria-label": "Chat project" }).props.disabled && !textarea(renderer).props.disabled, true), "A selected");
    await act(async () => textarea(renderer).props.onChange({ target: { value: "Keep this newly typed draft" } }));
    await act(async () => button(renderer, "Archive").props.onClick());
    await waitFor(() => assert.equal(harness.state.requests.archives.length, 1), "archive saved");
    await flush();
    assert.equal(harness.state.conversations.conv_a.draft?.content, "Keep this newly typed draft",
      "archiving during the save debounce must persist the current draft before leaving");
    assertFreshConversation(renderer, "archiving selected chat returns to a fresh composer");
  } finally {
    await closeHarness(renderer, harness);
  }
}

async function testDeleteWhileSelectionLoadsCannotRestoreDeletedConversation(vite) {
  const held = deferred();
  const harness = makeHarness({ aRun: null, bRun: null });
  harness.state.barriers.chatConversation.set("conv_a", held);
  const renderer = await renderChat(vite, harness);
  try {
    await waitFor(() => button(renderer, "Conversation A"), "initial chat list");
    await act(async () => button(renderer, "Conversation A").props.onClick());
    await waitFor(() => assert.equal(harness.state.chatGetCounts.get("conv_a"), 1), "selection request held");
    const row = renderer.root.findAll(node => node.props.className === "conversation-row")
      .find(node => textOf(node).includes("Conversation A"));
    await act(async () => row.findAllByType("button").find(node => node.props["aria-label"] === "Delete chat").props.onClick());
    const confirmButton = () => renderer.root.findByType("dialog").findAllByType("button").find(node => textOf(node) === "Delete chat");
    await waitFor(() => assert.equal(confirmButton().props.disabled, false), "delete preview ready");
    await act(async () => confirmButton().props.onClick());
    await waitFor(() => assert.equal(harness.state.requests.deletes.length, 1), "delete persisted");
    await waitFor(() => assert.equal(buttons(renderer, "Conversation A").length, 0), "deleted row leaves history");
    assert.equal(harness.state.requests.deletes[0].payload.include_diagnostics, true);
    await releaseResponse(harness, held, "/v1/chat/conversations/conv_a");
    assert.equal(buttons(renderer, "Conversation A").length, 0);
    assert.equal(harness.state.requests.registers.some(item => item.conversation_id === "conv_a"), false,
      "late selection must not register a deleted conversation");
    assert.equal(renderer.root.findByProps({ "aria-label": "Chat project" }).props.disabled, false,
      "deleting the loading selection returns to a fresh chat");
  } finally {
    held.resolve();
    await closeHarness(renderer, harness);
  }
}

async function testLateDraftSaveCannotRestoreDeletedChat(vite) {
  const held = deferred();
  const harness = makeHarness({ aRun: null, threadARun: null });
  harness.state.barriers.draft.set("conv_a", held);
  const renderer = await renderChat(vite, harness);
  try {
    await waitFor(() => button(renderer, "Conversation A"), "initial chat list");
    await act(async () => button(renderer, "Conversation A").props.onClick());
    await waitFor(() => assert.equal(renderer.root.findByProps({ "aria-label": "Chat project" }).props.disabled && !textarea(renderer).props.disabled, true), "A selected");
    await act(async () => textarea(renderer).props.onChange({ target: { value: "Draft response arrives after delete" } }));
    await act(async () => button(renderer, "New chat").props.onClick());
    await waitFor(() => assert.equal(harness.state.requests.draftUpdates.length, 1), "save accepted and response held");
    const row = renderer.root.findAll(node => node.props.className === "conversation-row").find(node => textOf(node).includes("Conversation A"));
    await act(async () => row.findAllByType("button").find(node => node.props["aria-label"] === "Delete chat").props.onClick());
    const confirm = () => renderer.root.findByType("dialog").findAllByType("button").find(node => textOf(node) === "Delete chat");
    await waitFor(() => assert.equal(confirm().props.disabled, false), "delete preview ready");
    await act(async () => confirm().props.onClick());
    await waitFor(() => assert.equal(harness.state.requests.deletes.length, 1), "delete saved");
    await releaseResponse(harness, held, "/v1/chat/conversations/conv_a/draft", "PUT");
    assert.equal(buttons(renderer, "Conversation A").length, 0, "late save must not put deleted history back in the cache");
    assertFreshConversation(renderer, "late save must not restore deleted chat selection");
  } finally {
    held.resolve();
    await closeHarness(renderer, harness);
  }
}

async function testEarlyShellActions(vite) {
  const harness = makeHarness({ bRun: run("run_b") });
  harness.state.conversations.conv_b.transcript[0].content = "An unrelated retained message";
  const renderer = await renderChat(vite, harness);
  try {
    await waitFor(() => button(renderer, "Conversation A"), "initial chat list");
    assert.equal(renderer.root.findByProps({ "aria-label": "Chat project" }).props.disabled, false, "new conversation project field starts editable");
    await act(async () => {
      inputByPlaceholder(renderer, "Search chats").props.onChange({ target: { value: "Conversation B" } });
      await Promise.resolve();
    });
    await waitFor(() => assert.deepEqual(harness.state.requests.searches.at(-1), "conversation b"), "backend search requested");
    await waitFor(() => assert.doesNotMatch(allText(renderer), /Conversation A/, "search narrows the sidebar"), "search narrows sidebar");
    await act(async () => {
      button(renderer, "Conversation B").props.onClick();
      await Promise.resolve();
    });
    await waitFor(() => assert.ok(harness.state.requests.states.includes("thread_b")), "B bound for shell actions");
    await waitFor(() => assert.equal(renderer.root.findByProps({ "aria-label": "Chat project" }).props.disabled && !textarea(renderer).props.disabled, true), "saved conversation project field is read-only");
    await act(async () => {
      textarea(renderer).props.onChange({ target: { value: "remember this draft" } });
      await Promise.resolve();
    });
    await waitFor(() => assert.equal(harness.state.requests.draftUpdates.at(-1)?.payload.content, "remember this draft"), "draft saved");
    await act(async () => {
      button(renderer, "Rename").props.onClick();
      await Promise.resolve();
    });
    await act(async () => {
      renderer.root.findByProps({ className: "conversation-rename" }).findByType("input").props.onChange({ target: { value: "Renamed B" } });
    });
    await act(async () => {
      renderer.root.findByProps({ className: "conversation-rename" }).props.onSubmit({ preventDefault() {}, currentTarget: { querySelectorAll: () => [] } });
    });
    await waitFor(() => assert.equal(harness.state.conversations.conv_b.title, "Renamed B"), "conversation renamed");
    await waitFor(() => assert.match(allText(renderer), /No matching conversations/, "rename invalidates retained search results"), "renamed conversation no longer matches old query");
    await act(async () => {
      inputByPlaceholder(renderer, "Search chats").props.onChange({ target: { value: "Renamed B" } });
    });
    await waitFor(() => button(renderer, "Archive"), "rename response closes inline editor");
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
      inputByPlaceholder(renderer, "Search chats").props.onChange({ target: { value: "" } });
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
    await waitFor(() => assert.equal(renderer.root.findByProps({ "aria-label": "Chat project" }).props.disabled && !textarea(renderer).props.disabled, true), "reopened saved conversation project field remains read-only");
    await act(async () => {
      textarea(renderer).props.onChange({ target: { value: "queue this follow-up" } });
      await Promise.resolve();
    });
    await waitFor(() => assert.equal(textarea(renderer).props.value, "queue this follow-up"), "queue follow-up draft applied");
    await act(async () => {
      composeForm(renderer).props.onSubmit({ preventDefault() {}, currentTarget: { querySelectorAll: () => [] } });
      await Promise.resolve();
    });
    await waitFor(() => assert.equal(harness.state.requests.queues.at(-1)?.payload.task, "queue this follow-up"), "busy conversation queues follow-up");
    await waitFor(() => assert.match(allText(renderer), /queue this follow-up/), "queued item is visible after its response");
    await act(async () => {
      button(renderer, "New").props.onClick();
      await Promise.resolve();
    });
    await waitFor(() => assert.equal(renderer.root.findByProps({ "aria-label": "Chat project" }).props.disabled, false), "new conversation project field is editable");
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
    await waitFor(() => assert.ok(renderer.root.findAll(node => typeof node.type === "function" &&
      node.type.name === "AgentMessageFeed" && node.props.messages.length > 0).length), "broken source exposes an unowned projected run");
  } finally {
    heldRegister.resolve();
    await closeHarness(renderer, harness);
  }
}

async function testAccessModeBelongsToSelectedConversation(vite) {
  const harness = makeHarness({ aRun: null, threadARun: null });
  harness.state.conversations.conv_a.approval_mode = "ask";
  harness.state.conversations.conv_a.setup_overrides = { approval_mode: "ask" };
  const renderer = await renderChat(vite, harness);
  try {
    await waitFor(() => button(renderer, "Conversation A"), "history loaded");
    await act(async () => approvalModeButton(renderer, "Full access").props.onClick());
    assert.equal(approvalModeButton(renderer, "Full access").props["aria-checked"], true);
    await act(async () => button(renderer, "Conversation A").props.onClick());
    await waitFor(() => assert.equal(textarea(renderer).props.disabled, false), "selected chat ready");
    await waitFor(() => assert.match(activeConversationTitle(renderer), /Conversation A/), "Ask chat selected");
    assert.equal(approvalModeButton(renderer, "Ask").props["aria-checked"], true,
      "opening an Ask chat cannot retain another chat's Full access choice");
  } finally { await closeHarness(renderer, harness); }
}

async function testNewChatResetsAccessToApplicationDefault(vite) {
  const harness = makeHarness({ aRun: null, threadARun: null, completeCommands: true,
    resolveSetup: payload => ({ configuration: { ...payload.overrides, deployment_id: payload.overrides.deployment_id ?? "dep_1", approval_mode: payload.overrides.approval_mode ?? "ask" }, instruction_layers: [] }) });
  harness.state.conversations.conv_a.setup_overrides = { approval_mode: "full_access" };
  const renderer = await renderChat(vite, harness);
  try {
    await waitFor(() => button(renderer, "Conversation A"), "history loaded");
    await act(async () => button(renderer, "Conversation A").props.onClick());
    await waitFor(() => assert.equal(approvalModeButton(renderer, "Full access").props["aria-checked"], true), "saved chat access restored");
    await act(async () => button(renderer, "New").props.onClick());
    await waitFor(() => assert.equal(approvalModeButton(renderer, "Ask").props["aria-checked"], true), "new Chat returns to application access");
    await act(async () => textarea(renderer).props.onChange({ target: { value: "New chat with inherited access" } }));
    await act(async () => composeForm(renderer).props.onSubmit({ preventDefault() {}, currentTarget: { querySelectorAll: () => [] } }));
    await waitFor(() => assert.equal(harness.state.requests.commands.length, 1), "new Chat sends");
    assert.equal(Object.hasOwn(harness.state.requests.commands[0].payload.params.metadata.workbench, "approval_mode"), false, "previous Chat's Full access is not submitted");
  } finally { await closeHarness(renderer, harness); }
}

async function testMainAgentKeepsChatAccessAndTools(vite) {
  const agentSetups = [{ id: "agent_two", name: "Agent two", current_version_id: "two-version", missing_dependencies: [] }];
  const harness = makeHarness({ aRun: null, threadARun: null, completeCommands: true, agentSetups,
    resolveSetup: payload => ({ configuration: { ...payload.overrides, deployment_id: payload.overrides.deployment_id ?? "dep_1", approval_mode: payload.overrides.approval_mode ?? "ask", presented_tools: payload.overrides.presented_tools ?? null }, instruction_layers: [] }) });
  harness.state.conversations.conv_a.setup_overrides = { approval_mode: "full_access", presented_tools: ["execute"] };
  const renderer = await renderChat(vite, harness);
  try {
    await waitFor(() => button(renderer, "Conversation A"), "history loaded");
    await act(async () => button(renderer, "Conversation A").props.onClick());
    await waitFor(() => assert.equal(approvalModeButton(renderer, "Full access").props["aria-checked"], true), "chat access restored");
    await act(async () => button(renderer, "Agent two").props.onClick());
    await waitFor(() => assert.match(textOf(buttonByAriaLabel(renderer, "Main agent")), /Agent two/), "agent changed");
    assert.equal(approvalModeButton(renderer, "Full access").props["aria-checked"], true, "main agent keeps Chat access visible");
    await act(async () => textarea(renderer).props.onChange({ target: { value: "Continue with this access" } }));
    await act(async () => composeForm(renderer).props.onSubmit({ preventDefault() {}, currentTarget: { querySelectorAll: () => [] } }));
    await waitFor(() => assert.equal(harness.state.requests.commands.length, 1), "agent-switched Chat sends");
    const submitted = harness.state.requests.commands[0].payload.params.metadata.workbench;
    assert.equal(submitted.approval_mode, "full_access", "submitted access matches displayed Chat access");
    assert.deepEqual(submitted.presented_tools, ["execute"], "Chat tool choice survives main agent selection");
    assert.equal(submitted.agent_setup_version_id, "two-version");
  } finally { await closeHarness(renderer, harness); }
}

async function testReopenedAccessUsesCurrentInheritanceWithSerializedNullOverrides(vite) {
  for (const currentDefault of ["ask", null]) {
    for (const override of [null, "full_access"]) {
      const harness = makeHarness({ aRun: null, threadARun: null,
        resolveSetup: payload => ({ configuration: {
          deployment_id: "dep_1", approval_mode: payload.overrides?.approval_mode ?? currentDefault,
        }, instruction_layers: [] }),
      });
      Object.assign(harness.state.conversations.conv_a, {
        agent_setup_version_id: "saved-agent-version", approval_mode: "full_access",
        // The real API serializes optional SetupConfiguration fields as null.
        setup_overrides: { deployment_id: null, approval_mode: override, presented_tools: null },
      });
      const renderer = await renderChat(vite, harness);
      try {
        await waitFor(() => button(renderer, "Conversation A"), "history loaded");
        await act(async () => button(renderer, "Conversation A").props.onClick());
        await waitFor(() => assert.equal(textarea(renderer).props.disabled, false), "selected chat ready");
        await waitFor(() => assert.match(activeConversationTitle(renderer), /Conversation A/), "inherited chat selected");
        const expectedLabel = override ? "Full access" : "Ask";
        assert.equal(approvalModeButton(renderer, expectedLabel).props["aria-checked"], true,
          `serialized null must inherit current ${currentDefault ?? "default Ask"}; explicit Full remains selected`);
        await act(async () => textarea(renderer).props.onChange({ target: { value: "Use this access choice" } }));
        await act(async () => composeForm(renderer).props.onSubmit({ preventDefault() {}, currentTarget: { querySelectorAll: () => [] } }));
        await waitFor(() => assert.equal(harness.state.requests.commands.length, 1), "inherited mode submission");
        const submitted = harness.state.requests.commands[0].payload.params.metadata.workbench;
        assert.equal(Object.hasOwn(submitted, "approval_mode"), override !== null,
          "opening the chat must not convert inherited access into an explicit override");
        if (override) assert.equal(submitted.approval_mode, override);
      } finally { await closeHarness(renderer, harness); }
    }
  }
}

async function testDraftAgentChangeDoesNotRestorePreviousAccess(vite) {
  for (const draftOverride of [null, "full_access"]) {
    const harness = makeHarness({ aRun: null, threadARun: null,
      resolveSetup: payload => ({ configuration: {
        deployment_id: "dep_1", approval_mode: payload.overrides?.approval_mode ?? "ask",
      }, instruction_layers: [] }),
    });
    Object.assign(harness.state.conversations.conv_a, {
      agent_setup_version_id: "previous-agent", approval_mode: "full_access",
      setup_overrides: { approval_mode: "full_access" },
      draft: { content: "Continue with the newly selected agent", revision: 1, updated_at: now(),
        attachment_ids: [], intended_config: { agent_setup_version_id: "new-agent",
          ...(draftOverride ? { approval_mode: draftOverride } : {}) } },
    });
    const renderer = await renderChat(vite, harness);
    try {
      await waitFor(() => button(renderer, "Conversation A"), "history loaded");
      await act(async () => button(renderer, "Conversation A").props.onClick());
      await waitFor(() => assert.equal(textarea(renderer).props.disabled, false), "draft agent ready");
      await waitFor(() => assert.match(activeConversationTitle(renderer), /Conversation A/), "draft agent selected");
      assert.equal(approvalModeButton(renderer, draftOverride ? "Full access" : "Ask").props["aria-checked"], true,
        "reopening a changed-agent draft must preserve its chosen access, not the previous agent's override");
      await act(async () => composeForm(renderer).props.onSubmit({ preventDefault() {}, currentTarget: { querySelectorAll: () => [] } }));
      await waitFor(() => assert.equal(harness.state.requests.commands.length, 1), "draft agent submitted");
      const submitted = harness.state.requests.commands[0].payload.params.metadata.workbench;
      assert.equal(submitted.agent_setup_version_id, "new-agent");
      assert.equal(Object.hasOwn(submitted, "approval_mode"), draftOverride !== null);
      if (draftOverride) assert.equal(submitted.approval_mode, draftOverride);
    } finally { await closeHarness(renderer, harness); }
  }
}

async function testAgentSetupInheritanceAndFutureTurn(vite) {
  const setups = ["one", "two"].map(id => ({ id, name: `Agent ${id}`, current_version_id: `${id}-version`, missing_dependencies: [] }));
  const harness = makeHarness({ aRun: null, threadARun: null, completeCommands: false,
    commandProjectsRun: true, commandProjectedStatus: "running", agentSetups: setups,
    resolveSetup: payload => ({ agent_setup_version_id: payload.agent_setup_version_id, configuration: { deployment_id: "dep_1", presented_tools: [], memory_version_refs: ["saved-memory-version"], per_request_overrides: { temperature: 0.4 } }, instruction_layers: [{ name: "Agent instructions", content: "Keep these instructions intact" }] }) });
  const renderer = await renderChat(vite, harness);
  try {
    await waitFor(() => assert.ok(allText(renderer).includes("Agent one")), "saved agent choices");
    await act(async () => button(renderer, "Agent one").props.onClick());
    await waitFor(() => assert.match(textOf(buttonByAriaLabel(renderer, "Main agent")), /Agent one/), "agent applied");
    assert.equal(approvalModeButton(renderer, "Ask").props["aria-checked"], true, "a saved agent without a mode stays on Ask");
    assert.ok(allText(renderer).includes("Keep these instructions intact"));
    await act(async () => textarea(renderer).props.onChange({ target: { value: "First task" } }));
    await act(async () => composeForm(renderer).props.onSubmit({ preventDefault() {}, currentTarget: { querySelectorAll: () => [] } }));
    await waitFor(() => assert.equal(harness.state.requests.commands.length, 1), "setup-backed submission");
    const submitted = harness.state.requests.commands[0].payload.params.metadata.workbench;
    await waitFor(() => assert.equal(buttonByAriaLabel(renderer, "Queue message").props.disabled, true), "first accepted run is live before queuing a later draft");
    assert.equal(submitted.agent_setup_version_id, "one-version");
    assert.equal(harness.state.requests.creates[0].agent_setup_version_id, "one-version");
    assert.equal(submitted.deployment_id, "dep_1", "the visible main model remains bound after changing agent");
    for (const key of ["profile_id", "presented_tools", "memory_version_refs", "skill_version_refs", "protected_instruction_version_refs", "per_request_overrides"]) {
      assert.equal(Object.hasOwn(submitted, key), false, `untouched ${key} must inherit instead of overwriting the saved setup`);
    }
    await act(async () => button(renderer, "Agent two").props.onClick());
    await waitFor(() => assert.match(textOf(buttonByAriaLabel(renderer, "Main agent")), /Agent two/), "next-turn agent selected");
    assert.equal(harness.state.requests.commands[0].payload.params.metadata.workbench.agent_setup_version_id, "one-version", "changing next-turn setup cannot mutate the in-flight request");
    await act(async () => { approvalModeButton(renderer, "Full access").props.onClick(); textarea(renderer).props.onChange({ target: { value: "Queue the next task" } }); });
    await act(async () => composeForm(renderer).props.onSubmit({ preventDefault() {}, currentTarget: { querySelectorAll: () => [] } }));
    await waitFor(() => assert.equal(harness.state.requests.queues.length, 1), "next task queued");
    const queued = harness.state.requests.queues[0].payload;
    assert.equal(queued.agent_setup_version_id, "two-version");
    assert.equal(queued.queue_after_run_id, "run_projected_1", "the later task queues behind the accepted live run");
    assert.equal(queued.approval_mode, "full_access", "an approval-mode choice is sent with the queued turn");
    assert.equal(Object.hasOwn(queued, "presented_tools"), false, "the chat shield does not replace the agent's tool list");
  } finally { await closeHarness(renderer, harness); }
}

async function testGeneratedDisplayTitleUpdatesSidebar(vite) {
  const harness = makeHarness({ aRun: null, threadARun: null, commandProjectsRun: true,
    commandDisplayTitle: "Generated answer title" });
  const renderer = await renderChat(vite, harness);
  try {
    await waitFor(() => button(renderer, "Conversation A"), "original sidebar title available");
    await act(async () => button(renderer, "Conversation A").props.onClick());
    await waitFor(() => assert.equal(textarea(renderer).props.disabled, false), "chat registered");
    await act(async () => textarea(renderer).props.onChange({ target: { value: "Reply with exactly OK." } }));
    await act(async () => composeForm(renderer).props.onSubmit({ preventDefault() {}, currentTarget: { querySelectorAll: () => [] } }));
    await waitFor(() => assert.equal(harness.state.requests.commands.length, 1), "turn submitted");
    await waitFor(() => assert.match(activeConversationTitle(renderer), /Generated answer title/), "chat fetch receives generated title");
    await waitFor(() => button(renderer, "Generated answer title"), "sidebar refreshes when only display title changes");
  } finally { await closeHarness(renderer, harness); }
}

async function testAcceptedSubmissionRecoversWithoutStreamProjection(vite) {
  const heldCommand = deferred();
  const harness = makeHarness({ aRun: null, threadARun: null, commandProjectsRun: true,
    commandProjectedStatus: "running", commandSuppressesStream: true });
  harness.state.barriers.command.set("thread_a", heldCommand);
  const renderer = await renderChat(vite, harness);
  try {
    await waitFor(() => button(renderer, "Conversation A"), "saved chat available");
    await act(async () => button(renderer, "Conversation A").props.onClick());
    await waitFor(() => assert.equal(textarea(renderer).props.disabled, false), "chat bound");
    await act(async () => textarea(renderer).props.onChange({ target: { value: "Accepted without a stream event" } }));
    await act(async () => composeForm(renderer).props.onSubmit({ preventDefault() {}, currentTarget: { querySelectorAll: () => [] } }));
    await waitFor(() => assert.equal(harness.state.requests.commands.length, 1), "command sent");
    assert.equal(buttonByAriaLabel(renderer, "Starting…").props.disabled, true, "second admission waits for confirmed run");
    await waitFor(() => assert.equal(selectedRunId(renderer), "run_projected_1"), "saved chat confirms accepted run without stream projection");
    await act(async () => textarea(renderer).props.onChange({ target: { value: "Queue behind recovered run" } }));
    await waitFor(() => assert.equal(buttonByAriaLabel(renderer, "Queue message").props.disabled, false), "Queue becomes available after durable run confirmation");
    await act(async () => composeForm(renderer).props.onSubmit({ preventDefault() {}, currentTarget: { querySelectorAll: () => [] } }));
    await waitFor(() => assert.equal(harness.state.requests.queues.length, 1), "later turn queued");
    assert.equal(harness.state.requests.queues[0].payload.queue_after_run_id, "run_projected_1");
  } finally {
    heldCommand.resolve();
    await closeHarness(renderer, harness);
  }
}

async function testFailedRegistrationKeepsChatReadOnlyUntilRetry(vite) {
  const harness = makeHarness({ aRun: null, threadARun: null });
  harness.state.registrationFailures.set("conv_a", 1);
  const renderer = await renderChat(vite, harness);
  try {
    await waitFor(() => button(renderer, "Conversation A"), "saved chat available");
    await act(async () => button(renderer, "Conversation A").props.onClick());
    await waitFor(() => assert.ok(buttons(renderer, "Retry opening chat").length), "failed registration offers retry");
    assert.ok(renderer.root.findAll(node => node.type === "article" && node.props.className === "bubble bubble-user" && textOf(node).includes("Conversation A")).length,
      "fetched transcript stays visible after registration fails");
    assert.equal(textarea(renderer).props.disabled, true, "failed registration never enables an unbound composer");
    await act(async () => composeForm(renderer).props.onSubmit({ preventDefault() {}, currentTarget: { querySelectorAll: () => [] } }));
    assert.equal(harness.state.requests.commands.length, 0, "failed registration cannot silently submit");
    assert.equal(harness.state.requests.queues.length, 0, "failed registration cannot queue");
    await act(async () => button(renderer, "Retry opening chat").props.onClick());
    await waitFor(() => assert.equal(harness.state.requests.registers.filter(item => item.conversation_id === "conv_a").length, 2), "retry registers the same chat");
    await waitFor(() => assert.ok(harness.state.requests.states.includes("thread_a")), "retry binds the interaction thread");
    await waitFor(() => assert.equal(textarea(renderer).props.disabled, false), "composer enables only after retry binds");
    assert.equal(buttons(renderer, "Retry opening chat").length, 0, "successful retry clears the error action");
    await act(async () => textarea(renderer).props.onChange({ target: { value: "Continue after retry" } }));
    await act(async () => composeForm(renderer).props.onSubmit({ preventDefault() {}, currentTarget: { querySelectorAll: () => [] } }));
    await waitFor(() => assert.equal(harness.state.requests.commands.length, 1), "retry establishes an owner for the next Send");
  } finally { await closeHarness(renderer, harness); }
}

async function testPendingAdmissionFailureKeepsEditedNextDraft(vite) {
  const heldCommand = deferred();
  const previous = run("run_previous", "completed", "old-input", "previous answer");
  const harness = makeHarness({ aRun: previous, threadARun: previous, commandRejects: true });
  harness.state.barriers.command.set("thread_a", heldCommand);
  const renderer = await renderChat(vite, harness);
  try {
    await waitFor(() => button(renderer, "Conversation A"), "saved chat available");
    await act(async () => button(renderer, "Conversation A").props.onClick());
    await waitFor(() => assert.equal(textarea(renderer).props.disabled, false), "saved chat bound");
    await act(async () => textarea(renderer).props.onChange({ target: { value: "First pending request" } }));
    await act(async () => composeForm(renderer).props.onSubmit({ preventDefault() {}, currentTarget: { querySelectorAll: () => [] } }));
    await waitFor(() => assert.equal(harness.state.requests.commands.length, 1), "first command held before response");
    await act(async () => textarea(renderer).props.onChange({ target: { value: "Next draft survives failure" } }));
    assert.equal(buttonByAriaLabel(renderer, "Starting…").props.disabled, true);
    heldCommand.resolve();
    await waitFor(() => assert.match(allText(renderer), /Model startup failed before a run was accepted/), "failed first request reported");
    assert.equal(textarea(renderer).props.value, "Next draft survives failure", "later draft remains editable after failed admission");
    assert.equal(harness.state.requests.queues.length, 0, "failure does not leave an idle queued turn");
  } finally { heldCommand.resolve(); await closeHarness(renderer, harness); }
}

async function testSelectedModelSurvivesAgentAndNewChat(vite) {
  const agentSetups = [{ id: "agent_one", name: "Agent one", current_version_id: "agent-one-version", missing_dependencies: [] }];
  const project = { id: "project_one", name: "Project one", path: "D:\\Projects\\One", canonical_path: "d:\\projects\\one", defaults: {}, active: true };
  const harness = makeHarness({ aRun: null, threadARun: null, agentSetups, projects: [project],
    resolveSetup: payload => ({ configuration: { ...payload.overrides, deployment_id: payload.overrides.deployment_id ?? "dep_1" }, instruction_layers: [] }) });
  const renderer = await renderChat(vite, harness);
  const picker = () => renderer.root.findAll(node => typeof node.type === "function" && node.type.name === "ChatModelControls")[0];
  try {
    await waitFor(() => button(renderer, "Agent one"), "agent available");
    await selectFixtureModel(renderer);
    await act(async () => button(renderer, "Agent one").props.onClick());
    await waitFor(() => assert.match(textOf(buttonByAriaLabel(renderer, "Main agent")), /Agent one/), "agent applied after model");
    assert.equal(picker().props.selectedDeploymentId, "dep_1", "agent selection retains the visible model");
    assert.equal(picker().props.configuration.deployment_id, "dep_1", "agent selection retains the submitted model");
    await act(async () => renderer.root.findByProps({ "aria-label": "Chat project" }).props.onChange({ target: { value: project.id } }));
    await waitFor(() => assert.equal(renderer.root.findByProps({ "aria-label": "Chat project" }).props.value, project.id), "project applied after model");
    assert.equal(picker().props.configuration.deployment_id, "dep_1", "project selection retains the submitted model");
    await act(async () => button(renderer, "New").props.onClick());
    await waitFor(() => assert.equal(picker().props.selectedDeploymentId, "dep_1"), "new chat retains the selected model");
    await act(async () => textarea(renderer).props.onChange({ target: { value: "Keep the selected model" } }));
    await act(async () => composeForm(renderer).props.onSubmit({ preventDefault() {}, currentTarget: { querySelectorAll: () => [] } }));
    await waitFor(() => assert.equal(harness.state.requests.creates.length, 1), "new chat created");
    assert.equal(harness.state.requests.creates[0].deployment_id, "dep_1", "creation submits the selected model");
    assert.equal(harness.state.requests.creates[0].agent_setup_version_id, "agent-one-version");
    assert.equal(harness.state.requests.creates[0].project_id, project.id);
  } finally { await closeHarness(renderer, harness); }
}

async function testSoleHealthyModelFallbackKeepsConfigurationIdentity(vite) {
  const healthy = { ...baseDeployment, scope: "managed", bundle_id: "bundle_1", profile_id: "config_1", health: { healthy: true } };
  const harness = makeHarness({ aRun: null, threadARun: null, deployments: [healthy] });
  const renderer = await renderChat(vite, harness);
  const picker = () => renderer.root.findAll(node => typeof node.type === "function" && node.type.name === "ChatModelControls")[0];
  try {
    await waitFor(() => assert.equal(picker().props.selectedDeploymentId, "dep_1"), "sole healthy deployment selected");
    assert.equal(picker().props.selectedConfigurationId, "config_1", "deployment configuration remains exact even before its catalogue entry is available");
    await act(async () => textarea(renderer).props.onChange({ target: { value: "Use the running model" } }));
    await act(async () => composeForm(renderer).props.onSubmit({ preventDefault() {}, currentTarget: { querySelectorAll: () => [] } }));
    await waitFor(() => assert.equal(harness.state.requests.creates.length, 1), "fallback chat created");
    assert.equal(harness.state.requests.creates[0].model_configuration_id, "config_1");
  } finally { await closeHarness(renderer, harness); }

  const multiple = makeHarness({ aRun: null, threadARun: null, deployments: [healthy, { ...healthy, id: "dep_2", profile_id: "config_2" }] });
  const multiRenderer = await renderChat(vite, multiple);
  try {
    await waitFor(() => button(multiRenderer, "Conversation A"), "catalogue loaded");
    assert.equal(pickerFor(multiRenderer).props.selectedDeploymentId, "", "multiple running models require an explicit choice");
  } finally { await closeHarness(multiRenderer, multiple); }
}

async function testStoppedNamedConfigurationSurvivesNewChat(vite) {
  const bag = (requested = {}) => ({ requested, applied: {}, overridden: [], unsupported: [], retired: [] });
  const stopped = { ...stoppedManagedDeployment, bundle_id: "bundle_cold", profile_id: "config_cold",
    settings: { startup: bag(), per_request: bag(), agent: bag() } };
  const profile = { id: "config_cold", bundle_id: "bundle_cold", display_name: "Cold configuration",
    bags: { startup: bag(), per_request: bag(), agent: bag() } };
  const harness = makeHarness({ aRun: null, threadARun: null, deployments: [stopped], profiles: [profile] });
  harness.state.conversations.conv_a.profile_id = profile.id;
  harness.state.conversations.conv_a.setup_overrides = { deployment_id: stopped.id, model_configuration_id: profile.id };
  const renderer = await renderChat(vite, harness);
  try {
    await waitFor(() => button(renderer, "Conversation A"), "saved chat available");
    await act(async () => button(renderer, "Conversation A").props.onClick());
    await waitFor(() => assert.equal(pickerFor(renderer).props.selectedConfigurationId, profile.id), "saved named configuration restored");
    await act(async () => button(renderer, "New").props.onClick());
    await waitFor(() => assert.equal(pickerFor(renderer).props.selectedConfigurationId, profile.id), "unloaded named configuration retained for New Chat");
    await act(async () => textarea(renderer).props.onChange({ target: { value: "Load the saved configuration on Send" } }));
    await act(async () => composeForm(renderer).props.onSubmit({ preventDefault() {}, currentTarget: { querySelectorAll: () => [] } }));
    await waitFor(() => assert.equal(harness.state.requests.creates.length, 1), "cold named chat created on Send");
    assert.equal(harness.state.requests.creates[0].model_configuration_id, profile.id);
    assert.equal(harness.state.requests.creates[0].deployment_id, stopped.id);
  } finally { await closeHarness(renderer, harness); }
}

function pickerFor(renderer) {
  return renderer.root.findAll(node => typeof node.type === "function" && node.type.name === "ChatModelControls")[0];
}

async function testFetchedChatVisibleWhileOpeningAndLateResultsIgnored(vite) {
  const registration = deferred();
  const resolution = deferred();
  const harness = makeHarness({ aRun: null, bRun: null, threadARun: null, threadBRun: null,
    resolveSetup: async payload => {
      if (payload.agent_setup_version_id === "agent-b") await resolution.promise;
      return { configuration: { ...payload.overrides, deployment_id: "dep_1" }, instruction_layers: [] };
    } });
  harness.state.conversations.conv_b.agent_setup_version_id = "agent-b";
  harness.state.barriers.register.set("conv_b", registration);
  const renderer = await renderChat(vite, harness);
  try {
    await waitFor(() => button(renderer, "Conversation B"), "B available");
    await act(async () => button(renderer, "Conversation B").props.onClick());
    await waitFor(() => assert.ok(renderer.root.findAll(node => node.type === "article" && node.props.className === "bubble bubble-user" && textOf(node).includes("Conversation B")).length), "fetched transcript visible before binding");
    await waitFor(() => assert.ok(harness.state.requests.registers.some(item => item.conversation_id === "conv_b")), "B registration started");
    assert.ok(harness.state.requests.resolutions.some(item => item.agent_setup_version_id === "agent-b"), "B setup resolution started alongside registration");
    assert.equal(textarea(renderer).props.disabled, true, "composer waits for both binding requests");
    await act(async () => button(renderer, "Conversation A").props.onClick());
    await waitFor(() => assert.match(activeConversationTitle(renderer), /Conversation A/), "A selected before B finishes");
    registration.resolve(); resolution.resolve();
    await waitFor(() => assert.equal(textarea(renderer).props.disabled, false), "A bound after navigation");
    assert.match(activeConversationTitle(renderer), /Conversation A/, "late B work cannot restore B");
  } finally {
    registration.resolve(); resolution.resolve();
    await closeHarness(renderer, harness);
  }
}

async function testColdSendAndLiveTurnQueueSkipBlockingPreview(vite) {
  const modelLoadRequired = { status: "needs_action", can_send: false, selection: null,
    issues: [{ code: "model_load_required", message: "Load this model configuration before using it in Chat." }] };
  const cold = makeHarness({ aRun: null, threadARun: null, deployments: [stoppedManagedDeployment],
    readiness: () => modelLoadRequired });
  const coldRenderer = await renderChat(vite, cold);
  try {
    await waitFor(() => button(coldRenderer, "Conversation A"), "cold chat available");
    await act(async () => button(coldRenderer, "Conversation A").props.onClick());
    await waitFor(() => assert.ok(cold.state.requests.readiness.some(item => item.id === "conv_a")), "cold model preview returned");
    await act(async () => textarea(coldRenderer).props.onChange({ target: { value: "Load on Send" } }));
    await waitFor(() => assert.equal(buttonByAriaLabel(coldRenderer, "Send").props.disabled, false), "cold model can be sent");
    await act(async () => composeForm(coldRenderer).props.onSubmit({ preventDefault() {}, currentTarget: { querySelectorAll: () => [] } }));
    await waitFor(() => assert.equal(cold.state.requests.commands.length, 1), "cold model reaches direct submit");
    assert.equal(cold.state.requests.queues.length, 0);
  } finally { await closeHarness(coldRenderer, cold); }

  const live = run("run_live", "running");
  const queue = makeHarness({ aRun: live, threadARun: live });
  const queueRenderer = await renderChat(vite, queue);
  try {
    await waitFor(() => button(queueRenderer, "Conversation A"), "live chat available");
    await act(async () => button(queueRenderer, "Conversation A").props.onClick());
    await waitFor(() => assert.ok(queue.state.openStreams.has("thread_a")), "live run observed");
    assert.equal(queue.state.requests.readiness.filter(item => item.id === "conv_a").length, 0, "active run does not trigger a blocking readiness preview");
    await act(async () => textarea(queueRenderer).props.onChange({ target: { value: "Queue while running" } }));
    assert.equal(buttonByAriaLabel(queueRenderer, "Queue message").props.disabled, false);
    await act(async () => composeForm(queueRenderer).props.onSubmit({ preventDefault() {}, currentTarget: { querySelectorAll: () => [] } }));
    await waitFor(() => assert.equal(queue.state.requests.queues.length, 1), "live turn reaches queue admission");
    assert.equal(queue.state.requests.queues[0].payload.queue_after_run_id, "run_live", "queue admission identifies the run being followed");
    assert.equal(queue.state.requests.commands.length, 0);
    const terminal = run("run_live", "completed");
    await act(async () => {
      queue.state.openStreams.get("thread_a")?.write(`data: ${JSON.stringify(streamFrame(terminal))}\n\n`);
      await Promise.resolve();
    });
    await waitFor(() => assert.equal(queue.state.requests.readiness.some(item => item.id === "conv_a"), true), "terminal run refreshes setup preview");
    assert.doesNotMatch(allText(queueRenderer), /Wait for this chat's current turn to finish/);
  } finally { await closeHarness(queueRenderer, queue); }

  const backendActive = makeHarness({ aRun: null, threadARun: null,
    readiness: () => ({ status: "needs_action", can_send: false, selection: null,
      issues: [{ code: "chat_turn_active", message: "Wait for this chat's current turn to finish." }] }) });
  const backendActiveRenderer = await renderChat(vite, backendActive);
  try {
    await waitFor(() => button(backendActiveRenderer, "Conversation A"), "saved chat available");
    await act(async () => button(backendActiveRenderer, "Conversation A").props.onClick());
    await waitFor(() => assert.ok(backendActive.state.requests.readiness.some(item => item.id === "conv_a")), "backend activity preview returned");
    await act(async () => textarea(backendActiveRenderer).props.onChange({ target: { value: "Queue against backend activity" } }));
    await waitFor(() => assert.equal(buttonByAriaLabel(backendActiveRenderer, "Queue message").props.disabled, false), "backend activity offers Queue");
    await act(async () => composeForm(backendActiveRenderer).props.onSubmit({ preventDefault() {}, currentTarget: { querySelectorAll: () => [] } }));
    await waitFor(() => assert.equal(backendActive.state.requests.queues.length, 1), "backend activity routes to durable Queue");
    assert.equal(backendActive.state.requests.queues[0].payload.queue_after_run_id, undefined, "an unobserved run is not guessed from stale local state");
    assert.equal(backendActive.state.requests.commands.length, 0);
  } finally { await closeHarness(backendActiveRenderer, backendActive); }
}

async function testLateReadinessCannotBlockAnotherChat(vite) {
  const heldA = deferred();
  const harness = makeHarness({ aRun: null, bRun: null, threadARun: null, threadBRun: null,
    readiness: async ({ id }) => {
      if (id === "conv_a") {
        await heldA.promise;
        return { status: "incompatible", can_send: false, selection: null,
          issues: [{ code: "old_setup", message: "Old chat setup is unavailable." }] };
      }
      return { status: "ready", can_send: true, selection: null, issues: [] };
    } });
  const renderer = await renderChat(vite, harness);
  try {
    await waitFor(() => button(renderer, "Conversation A"), "chats available");
    await act(async () => button(renderer, "Conversation A").props.onClick());
    await waitFor(() => assert.ok(harness.state.requests.readiness.some(item => item.id === "conv_a")), "A preview held");
    await act(async () => button(renderer, "Conversation B").props.onClick());
    await waitFor(() => assert.ok(harness.state.requests.readiness.some(item => item.id === "conv_b")), "B preview started");
    heldA.resolve();
    await act(async () => textarea(renderer).props.onChange({ target: { value: "Send in B" } }));
    await waitFor(() => assert.equal(buttonByAriaLabel(renderer, "Send").props.disabled, false), "late A response cannot block B");
    assert.doesNotMatch(allText(renderer), /Old chat setup is unavailable/);
  } finally { heldA.resolve(); await closeHarness(renderer, harness); }
}

async function testRestoredDraftCanClearSavedConfiguration(vite) {
  const harness = makeHarness({ aRun: null, threadARun: null,
    deployments: [baseDeployment, { ...baseDeployment, id: "dep_2", display_name: "connected:Second model" }] });
  harness.state.conversations.conv_a = conversation("conv_a", "Conversation A", null, {
    profile_id: "old-configuration", setup_overrides: { model_configuration_id: "old-configuration", deployment_id: "dep_1" },
    draft: { content: "Use the connected model", attachment_ids: [], intended_config: {
      model_configuration_id: null, profile_id: null, deployment_id: "dep_2",
    }, revision: 3, updated_at: now() },
  });
  const renderer = await renderChat(vite, harness);
  try {
    await waitFor(() => button(renderer, "Conversation A"), "saved chat available");
    await act(async () => button(renderer, "Conversation A").props.onClick());
    await waitFor(() => assert.equal(pickerFor(renderer).props.selectedDeploymentId, "dep_2"), "draft connected deployment restored");
    assert.equal(pickerFor(renderer).props.selectedConfigurationId, undefined, "explicit null clears the old named configuration");
    assert.equal(pickerFor(renderer).props.configuration.model_configuration_id, null);
  } finally { await closeHarness(renderer, harness); }
}

async function testRestoredDraftFindsRunningNamedConfiguration(vite) {
  const harness = makeHarness({ aRun: null, threadARun: null,
    deployments: [baseDeployment, { ...baseDeployment, id: "dep_2", bundle_id: "bundle_2", profile_id: "config_2", scope: "managed", health: { healthy: true } }],
    resolveSetup: payload => ({ configuration: { ...payload.overrides, model_configuration_id: "config_2", deployment_id: "dep_2" }, instruction_layers: [] }) });
  harness.state.conversations.conv_a = conversation("conv_a", "Conversation A", null, {
    draft: { content: "Use the running configuration", attachment_ids: [], intended_config: {
      model_configuration_id: "config_2",
    }, revision: 4, updated_at: now() },
  });
  const renderer = await renderChat(vite, harness);
  try {
    await waitFor(() => button(renderer, "Conversation A"), "saved chat available");
    await act(async () => button(renderer, "Conversation A").props.onClick());
    await waitFor(() => assert.equal(pickerFor(renderer).props.selectedDeploymentId, "dep_2"), "matching running deployment restored from named configuration");
    assert.equal(pickerFor(renderer).props.selectedConfigurationId, "config_2");
    assert.ok(harness.state.requests.resolutions.some(item => item.overrides?.model_configuration_id === "config_2"), "named configuration resolved on open");
  } finally { await closeHarness(renderer, harness); }
}

async function testExecutionPreferencesSurviveDraftAndFreezeAtSubmission(vite) {
  for (const queued of [false, true]) {
    const busy = queued ? run("run_existing", "running") : null;
    const harness = makeHarness({ aRun: busy, threadARun: busy, agentSetups: [{ id: "helper_one", name: "Research helper", configuration: { deployment_id: "dep_1" }, current_version_id: "helper_v1", missing_dependencies: [] }] });
    const renderer = await renderChat(vite, harness);
    const planButton = () => renderer.root.findAll(node => node.type === "button" && textOf(node).startsWith("Plan mode"))[0];
    const helper = () => renderer.root.findAll(node => node.type === "label" && node.props.className === "helper-choice")[0].findByType("input");
    try {
      await waitFor(() => button(renderer, "Conversation A"), "history ready");
      await act(async () => button(renderer, "Conversation A").props.onClick());
      await waitFor(() => assert.equal(textarea(renderer).props.disabled, false), "conversation ready");
      await act(async () => {
        textarea(renderer).props.onChange({ target: { value: "Investigate this carefully" } });
        planButton().props.onClick();
        helper().props.onChange({ target: { checked: true } });
        buttonByAriaLabel(renderer, "Review before finishing").props.onClick();
        approvalModeButton(renderer, "Full access").props.onClick();
      });
      await act(async () => renderer.root.findByProps({ placeholder: "What should a good result satisfy?" }).props.onChange({ target: { value: "Cite the relevant files" } }));
      assert.equal(textarea(renderer).props.value, "Investigate this carefully", "control changes preserve the typed draft");
      assert.ok(buttonByAriaLabel(renderer, "Turn off Plan mode"), "Full access does not switch Plan into Work");
      await act(async () => button(renderer, "Conversation B").props.onClick());
      await waitFor(() => assert.match(activeConversationTitle(renderer), /Conversation B/), "other chat selected");
      await act(async () => button(renderer, "Conversation A").props.onClick());
      await waitFor(() => assert.equal(textarea(renderer).props.value, "Investigate this carefully"), "draft restored");
      await waitFor(() => assert.equal(textarea(renderer).props.disabled, false), "restored conversation bound");
      assert.ok(buttonByAriaLabel(renderer, "Turn off Plan mode"));
      assert.equal(helper().props.checked, true);
      assert.equal(renderer.root.findByProps({ placeholder: "What should a good result satisfy?" }).props.value, "Cite the relevant files");
      await act(async () => composeForm(renderer).props.onSubmit({ preventDefault() {}, currentTarget: { querySelectorAll: () => [] } }));
      await waitFor(() => assert.equal(queued ? harness.state.requests.queues.length : harness.state.requests.commands.length, 1), "submission reaches its owner");
      const submitted = queued ? harness.state.requests.queues[0].payload : harness.state.requests.commands[0].payload.params.metadata.workbench;
      assert.equal(submitted.work_mode, "plan");
      assert.deepEqual(submitted.helper_agent_ids, ["helper_one"]);
      assert.deepEqual(submitted.review, { enabled: true, criteria: "Cite the relevant files", max_revisions: 2 });
      assert.equal(submitted.approval_mode, "full_access");
      await act(async () => buttonByAriaLabel(renderer, "Turn off Plan mode").props.onClick());
      assert.equal(submitted.work_mode, "plan", "later UI choices do not alter submitted work");
    } finally { await closeHarness(renderer, harness); }
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
    ["startup restoration blocks composer", testStartupRestorationBlocksComposer],
    ["execution preferences durable draft and submission", testExecutionPreferencesSurviveDraftAndFreezeAtSubmission],
    ["reopened draft agent access", testDraftAgentChangeDoesNotRestorePreviousAccess],
    ["reopened access inherits serialized null", testReopenedAccessUsesCurrentInheritanceWithSerializedNullOverrides],
    ["access belongs to selected conversation", testAccessModeBelongsToSelectedConversation],
    ["new Chat resets access", testNewChatResetsAccessToApplicationDefault],
    ["main agent keeps Chat access", testMainAgentKeepsChatAccessAndTools],
    ["startup refresh failure remains usable", testStartupRefreshFailureRemainsUsable],
    ["deleted history selection recovery", testDeletedHistorySelectionRecoversToNewChat],
    ["agent setup inheritance and future turns", testAgentSetupInheritanceAndFutureTurn],
    ["selected model survives agent and New Chat", testSelectedModelSurvivesAgentAndNewChat],
    ["sole healthy model fallback keeps configuration", testSoleHealthyModelFallbackKeepsConfigurationIdentity],
    ["stopped named configuration survives New Chat", testStoppedNamedConfigurationSurvivesNewChat],
    ["fetched chat visible while opening and late results ignored", testFetchedChatVisibleWhileOpeningAndLateResultsIgnored],
    ["cold Send and live turn Queue skip blocking preview", testColdSendAndLiveTurnQueueSkipBlockingPreview],
    ["late readiness cannot block another chat", testLateReadinessCannotBlockAnotherChat],
    ["restored draft clears saved configuration", testRestoredDraftCanClearSavedConfiguration],
    ["restored draft finds running named configuration", testRestoredDraftFindsRunningNamedConfiguration],
    ["attention selection consumed", testAttentionActivationDoesNotPinConversation],
    ["attention navigation saves current draft", testExternalAttentionNavigationPreservesDraft],
    ["whole-chat file drop", testWholeChatDropStagesFiles],
    ["new-chat file drop", vite => testWholeChatDropStagesFiles(vite, true)],
    ["file-drop creation navigation guard", testFileDropDuringNewChatRegistrationCannotRetarget],
    ["held registration", testHeldRegistrationDoesNotBindOldThread],
    ["failed registration stays read-only until retry", testFailedRegistrationKeepsChatReadOnlyUntilRetry],
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
    ["accepted submission recovers without stream projection", testAcceptedSubmissionRecoversWithoutStreamProjection],
    ["pending admission failure keeps edited next draft", testPendingAdmissionFailureKeepsEditedNextDraft],
    ["pending submit stop uses input identity", testPendingSubmitStopUsesPendingInputIdentity],
    ["reopened pending cancel clears from authoritative view", testReopenedPendingCancelShowsStoppingUntilAuthoritativeClear],
    ["fresh draft persists before navigation", testFreshDraftPersistsBeforeImmediateNavigation],
    ["fresh submit shares draft session", testFreshSubmitSharesCreatedDraftSessionAndSendsRevision],
    ["generated display title updates sidebar", testGeneratedDisplayTitleUpdatesSidebar],
    ["first-turn Windows grant preserves draft", testFirstTurnWindowsGrantPreservesDraft],
    ["single pre-model tool menu and runtime cleanup", testSingleToolMenuBeforeModelAndRuntimeCleanup],
    ["tool readiness recovery opens focused menu", testToolReadinessActionsOpenRecovery],
    ["accepted draft next save uses incremented revision", testAcceptedDraftNextSaveUsesIncrementedRevision],
    ["queued draft clear preserves later draft", testQueuedDraftClearDoesNotEraseLaterDraft],
    ["attachment-only SDK submit metadata", testAttachmentOnlySdkSubmitKeepsMetadata],
    ["project attachment immutable scope", testProjectAttachmentScope],
    ["queued submit attachment/config capture", testQueuedSubmitKeepsAttachmentsToolsAndOverrides],
    ["persisted draft attachment/config reload", testPersistedDraftRestoresAttachmentsAndIntendedConfig],
    ["late upload navigation guard", testLateUploadAfterNavigationDoesNotAttachToNewConversation],
    ["stopped managed deployment shows load-on-send notice", testStoppedManagedDeploymentShowsLoadOnSendNotice],
    ["unknown projection requires authoritative current run", testUnknownProjectionRequiresAuthoritativeCurrentRun],
    ["measurement-only projection refresh and isolation", testMeasurementOnlyProjectionRefreshesCurrentConversation],
    ["saving project state disables Stop", testSavingProjectStateDisablesStop],
    ["unknown projection adopts authoritative new current run", testUnknownProjectionAdoptsAuthoritativeNewCurrentRun],
    ["older unknown projection lookup cannot overwrite newer adopted run", testOlderUnknownProjectionLookupCannotOverwriteNewerAdoptedRun],
    ["rejected submit keeps draft", testRejectedSubmitWithOnlyStagedInputKeepsDraftAndError],
    ["accepted submit error preserves newer draft", testAcceptedSubmitErrorRefreshSuppressesStaleErrorButKeepsNewerDraft],
    ["accepted submit error navigation guard", testAcceptedSubmitErrorRefreshAfterNavigationDoesNotRetarget],
    ["accepted ack navigation/revisit", testAcceptedSubmitTargetsOriginalThreadAfterNavigationAndRevisit],
    ["early shell actions", testEarlyShellActions],
    ["archive immediately leaves history and search", testArchiveImmediatelyLeavesHistoryAndSearch],
    ["model switch clears only model-specific overrides", testModelChangeClearsOnlyModelSpecificOverrides],
    ["archive preserves draft before leaving", testArchivePreservesDraftBeforeLeaving],
    ["delete while selection loads", testDeleteWhileSelectionLoadsCannotRestoreDeletedConversation],
    ["late draft save cannot restore deleted chat", testLateDraftSaveCannotRestoreDeletedChat],
    ["project branches group by immutable area", testProjectBranchesGroupByImmutableArea],
  ];
    const failures = [];
    for (const [name, fn] of cases) {
      if (process.env.CHAT_PANEL_CASE && name !== process.env.CHAT_PANEL_CASE) continue;
      if (!aggregateCases) {
        await fn(vite);
        continue;
      }
      try {
        await fn(vite);
        console.log(`CASE PASS: ${name}`);
      } catch (error) {
        const message = error instanceof Error ? error.message : String(error);
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
