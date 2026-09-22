import assert from "node:assert/strict";
import path from "node:path";
import { fileURLToPath } from "node:url";

import React from "react";
import { act, create } from "react-test-renderer";
import { createServer as createViteServer } from "vite";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;
globalThis.window = { workbench: { backendUrl: "http://127.0.0.1:8000" } };

const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../..");
const desktopRoot = path.join(repoRoot, "apps/desktop");

const vite = await createViteServer({ root: desktopRoot, appType: "custom", server: { middlewareMode: true, hmr: false }, logLevel: "error" });

async function checkInlineEditAndResume(ChatQueuePanel) {
  const requests = [];
  const updated = [];
  const errors = [];
  const assets = [asset("asset_old", "old.txt")];
  globalThis.fetch = async (url, init = {}) => {
    const parsed = new URL(String(url));
    requests.push({ method: init.method ?? "GET", path: parsed.pathname, search: parsed.search, body: init.body ? JSON.parse(String(init.body)) : null });
    if (parsed.pathname === "/v1/assets") {
      return jsonResponse(assets);
    }
    if (parsed.pathname === "/v1/bundles/bundle-a/configuration-options") {
      return jsonResponse({
        per_request_defaults: {
          reasoning_effort: {
            options: [
              { value: "default", label: "Default" },
              { value: "low", label: "Low" },
              { value: "high", label: "High" },
            ],
          },
        },
      });
    }
    if (parsed.pathname.endsWith("/queue/q1") && init.method === "PATCH") {
      const body = requests.at(-1).body;
      return jsonResponse({ ...conversation, queue: [{ ...conversation.queue[0], task: body.task, attachment_ids: body.attachment_ids, intended_config: body.intended_config }] });
    }
    if (parsed.pathname.endsWith("/queue/q1") && init.method === "DELETE") {
      return jsonResponse({ ...conversation, queue: conversation.queue.slice(1) });
    }
    if (parsed.pathname.endsWith("/queue/resume") && init.method === "POST") {
      return jsonResponse({ ...conversation, queue: conversation.queue.map((item) => ({ ...item, status: "queued", pause_reason: null, pause_error: null })) });
    }
    throw new Error(`unexpected request ${init.method ?? "GET"} ${parsed.pathname}`);
  };

  let renderer;
  await act(async () => {
    renderer = create(React.createElement(ChatQueuePanel, {
      conversation: liveConversation,
      deployments,
      profiles,
      onUpdated: (next) => updated.push(next),
      onError: (message) => errors.push(message),
    }));
    await tick();
  });
  await act(async () => {
    await tick();
  });

  const textareas = renderer.root.findAllByType("textarea");
  assert.ok(textareas.length >= 2, "queued items should render inline task editors");
  assert.equal(textareas[0].props.value, "first queued task");
  assert.equal(textareas[1].props.disabled, false, "paused frozen uncertain item should remain editable before deliberate resume");
  assert.equal(textareas[2].props.disabled, true, "dispatching queued item should be locked");

  await act(async () => {
    textareas[0].props.onChange({ target: { value: "" } });
  });

  const selects = renderer.root.findAllByType("select");
  assert.ok(selects.length >= 2, "queued item should expose model and preset controls");
  await act(async () => {
    selects[0].props.onChange({ target: { value: "dep_b" } });
    selects[1].props.onChange({ target: { value: "!none" } });
  });
  const thinkingRange = renderer.root.findAll((node) => node.type === "input" && node.props.type === "range")[0];
  assert.ok(thinkingRange, "queued item should expose supported thinking control");
  await act(async () => {
    thinkingRange.props.onChange({ target: { value: "2" } });
  });

  await act(async () => {
    button(renderer, "Save queued turn").props.onClick();
    await tick();
  });
  const patch = requests.find((request) => request.method === "PATCH" && request.path.endsWith("/queue/q1"));
  assert.deepEqual(patch.body, {
    task: "",
    attachment_ids: ["asset_old"],
    intended_config: {
      deployment_id: "dep_b",
      profile_id: null,
      inherit_deployment_settings: false,
      per_request_overrides: { reasoning_effort: "high" },
    },
  });

  await act(async () => {
    button(renderer, "Remove queued turn").props.onClick();
    await tick();
  });
  assert.ok(requests.some((request) => request.method === "DELETE" && request.path.endsWith("/queue/q1")), "remove should call queue item delete endpoint");

  const continueBeforeAck = button(renderer, "Continue queue");
  assert.equal(continueBeforeAck.props.disabled, true, "uncertain dispatch resume should require explicit acknowledgement");
  const ack = renderer.root.findAll((node) => node.type === "input" && node.props.type === "checkbox")[0];
  await act(async () => {
    ack.props.onChange({ target: { checked: true } });
  });
  assert.equal(button(renderer, "Continue queue").props.disabled, true, "live run should block queue resume even after uncertainty acknowledgement");
  await act(async () => {
    renderer.update(React.createElement(ChatQueuePanel, {
      conversation,
      deployments,
      profiles,
      onUpdated: (next) => updated.push(next),
      onError: (message) => errors.push(message),
    }));
    await tick();
  });
  await act(async () => {
    button(renderer, "Continue queue").props.onClick();
    await tick();
  });
  const resume = requests.find((request) => request.method === "POST" && request.path.endsWith("/queue/resume"));
  assert.deepEqual(resume.body, { resume_paused: true, acknowledge_uncertain_effects: true });

  assert.equal(errors.length, 0);
  assert.ok(updated.length >= 3, "patch/delete/resume should publish updated conversations");
}

function button(renderer, text) {
  const found = renderer.root.findAll((node) => node.type === "button" && textOf(node).includes(text))[0];
  assert.ok(found, `button ${text} should render`);
  return found;
}

function textOf(node) {
  if (typeof node === "string") return node;
  const children = node.children ?? [];
  return children.map((child) => typeof child === "string" ? child : textOf(child)).join("");
}

function tick() {
  return new Promise((resolve) => setTimeout(resolve, 0));
}

function jsonResponse(body, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  };
}

function asset(id, filename) {
  return {
    id,
    origin: "upload",
    scope: "session",
    session_id: "chat_1",
    project_path: null,
    access_scope: "session:chat_1",
    storage: "application.sqlite",
    filename,
    content_type: "text/plain",
    content_kind: "text",
    encoding: "utf-8",
    size_bytes: 3,
    sha256: "abc",
    observed_at: "2026-09-21T00:00:00Z",
    source_run_id: null,
    source_tool_call_id: null,
    source_tool_name: null,
    mutable_reference: null,
    observation: null,
    deleted_at: null,
  };
}

const deployments = [
  {
    id: "dep_a",
    display_name: "managed:Alpha",
    scope: "managed",
    status: "running",
    bundle_id: "bundle-a",
    endpoint: null,
    applied_startup: {},
    settings: settingsBags(),
    health: null,
    resource_usage: null,
    server_props: { n_ctx: 4096 },
    error: null,
  },
  {
    id: "dep_b",
    display_name: "connected:Beta",
    scope: "connected",
    status: "running",
    bundle_id: "bundle-a",
    endpoint: "http://localhost",
    applied_startup: {},
    settings: settingsBags(),
    health: null,
    resource_usage: null,
    server_props: null,
    error: null,
  },
];

const profiles = [
  { id: "profile_a", display_name: "Profile A", bags: settingsBags() },
];

function settingsBags() {
  return {
    startup: { applied: {}, requested: {}, unsupported: [], overridden: [], retired: [] },
    per_request: { applied: {}, requested: {}, unsupported: [], overridden: [], retired: [] },
    agent: { applied: {}, requested: {}, unsupported: [], overridden: [], retired: [] },
  };
}

const conversation = {
  id: "chat_1",
  deployment_id: "dep_a",
  profile_id: "profile_a",
  inherit_deployment_settings: true,
  project_path: null,
  workspace_id: null,
  thread_id: "thread_1",
  transcript: [],
  current_run_id: null,
  run_ids: [],
  history_replaced: false,
  harness: "deepagents",
  second_agent_loop: false,
  source_surface: "chat",
  current_run: null,
  queue: [
    {
      id: "q1",
      task: "first queued task",
      run_id: null,
      input_message_id: null,
      content_blocks: null,
      attachment_ids: ["asset_old"],
      output_schema: null,
      intended_config: { deployment_id: "dep_a", profile_id: "profile_a", inherit_deployment_settings: true, per_request_overrides: { reasoning_effort: "low" } },
      frozen_config: null,
      status: "queued",
      pause_reason: null,
      pause_error: null,
      pause_error_code: null,
      created_at: "2026-09-21T00:00:00Z",
      updated_at: "2026-09-21T00:00:00Z",
    },
    {
      id: "q2",
      task: "paused task",
      run_id: null,
      input_message_id: null,
      content_blocks: null,
      attachment_ids: [],
      output_schema: null,
      intended_config: { deployment_id: "dep_a" },
      frozen_config: { deployment_id: "dep_a", profile_id: "profile_a" },
      status: "paused",
      pause_reason: "dispatch_uncertain",
      pause_error: "The previous dispatch may have started.",
      pause_error_code: "dispatch_uncertain",
      created_at: "2026-09-21T00:00:00Z",
      updated_at: "2026-09-21T00:00:00Z",
    },
    {
      id: "q3",
      task: "dispatching task",
      run_id: "run_3",
      input_message_id: "input_3",
      content_blocks: null,
      attachment_ids: [],
      output_schema: null,
      intended_config: { deployment_id: "dep_b" },
      frozen_config: { deployment_id: "dep_b", profile_id: null },
      status: "dispatching",
      pause_reason: null,
      pause_error: null,
      pause_error_code: null,
      created_at: "2026-09-21T00:00:00Z",
      updated_at: "2026-09-21T00:00:00Z",
    },
  ],
  events: [],
  created_at: "2026-09-21T00:00:00Z",
  updated_at: "2026-09-21T00:00:00Z",
};

const liveConversation = {
  ...conversation,
  current_run_id: "run_live",
  current_run: { id: "run_live", status: "running" },
};

try {
  const { ChatQueuePanel } = await vite.ssrLoadModule("/src/renderer/ChatQueuePanel.tsx");
  await checkInlineEditAndResume(ChatQueuePanel);
} finally {
  await vite.close();
}

console.log("ChatQueuePanel inline queue editing checks passed.");
