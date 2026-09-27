import assert from "node:assert/strict";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { spawnSync } from "node:child_process";
import React from "react";
import { act, create } from "react-test-renderer";
import { createServer as createViteServer } from "vite";
import { makeHarness, run, deferred, json, renderChat, closeHarness, button, textarea, composeForm, textOf, waitFor } from "./check-chat-interaction-boundaries.mjs";

const desktop = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const vite = await createViteServer({ root: desktop, appType: "custom", server: { middlewareMode: true, hmr: false }, logLevel: "error" });
const picked = renderer => renderer.root.findAll(node => typeof node.type === "function" && node.type.name === "ComposerPicker")[0];
const control = (renderer, label) => renderer.root.findAll(node => node.type === "button" && node.props["aria-label"] === label)[0];
const option = (renderer, name) => renderer.root.findAll(node => node.type === "button" && node.props.role === "option" && textOf(node).startsWith(name))[0];
const submit = renderer => composeForm(renderer).props.onSubmit({ preventDefault() {}, currentTarget: { querySelectorAll: () => [] } });
const entries = [
  { id: "memory_record", current_version_id: "memory_v1", kind: "memory", display_name: "Memory notes", enabled: true, active: true },
  { id: "skill_record", current_version_id: "skill_v1", kind: "skill", display_name: "Research files", enabled: true, active: true },
  { id: "disabled_record", current_version_id: "skill_disabled_v1", kind: "skill", display_name: "Disabled skill", enabled: false, active: true },
];
const shortcuts = [{ id: "explain", version: "v1", name: "Explain", description: "Explain the selected subject", prompt: "Frozen backend instructions never enter the user task." }];
const contractPayloads = { starts: [], creates: [], queueUpdates: [] };
let renderer;
try {
  for (const queued of [false, true]) {
    const live = queued ? run("existing_run", "running") : null;
    const routes = [];
    const harness = makeHarness({ aRun: live, threadARun: live, knowledgeEntries: entries, commandProjectsRun: true, commandProjectedStatus: "running", requestOverride: ({ req, res, url }) => {
      if (req.method === "GET" && url.pathname === "/v1/chat/shortcuts") { json(res, 200, shortcuts); return true; }
    } });
    harness.state.conversations.conv_a.draft = { revision: 1, content: "", attachment_ids: [], intended_config: { protected_instruction_entry_ids: ["missing_instruction"], model_overrides: { remote: { startup_overrides: { ctx_size: 8192 } } }, inherited_model_configuration: { deployment_id: "dep_1" } } };
    renderer = await renderChat(vite, harness, { onNavigate: target => routes.push(target) });
    try {
      assert.equal(renderer.root.findByProps({ className: "chat-search" }).props.hidden, true, "Search is hidden until the rail entry point is chosen");
      await act(async () => control(renderer, "Search chats").props.onClick());
      assert.equal(renderer.root.findByProps({ className: "chat-search" }).props.hidden, false);
      await act(async () => control(renderer, "Close search").props.onClick());
      await waitFor(() => button(renderer, "Conversation A"), "history ready");
      await act(async () => button(renderer, "Conversation A").props.onClick());
      await waitFor(() => assert.equal(textarea(renderer).props.disabled, false), "Chat bound");
      let submissions = 0;
      const key = (key, patch = {}) => ({ key, shiftKey: false, nativeEvent: { isComposing: false }, preventDefault() {}, currentTarget: { form: { requestSubmit: () => submissions++ } }, ...patch });
      await act(async () => textarea(renderer).props.onChange({ target: { value: "@mem" } }));
      assert.equal(picked(renderer).props.autocomplete, true);
      assert.equal(textarea(renderer).props["aria-activedescendant"], "composer-option-0");
      await act(async () => textarea(renderer).props.onKeyDown(key("Enter")));
      assert.equal(submissions, 0, "Enter accepts a highlighted reference before it can send");
      assert.equal(textarea(renderer).props.value, "");
      assert.ok(control(renderer, "Remove Memory notes"));
      assert.equal(harness.state.requests.commands.length, 0);
      await act(async () => textarea(renderer).props.onChange({ target: { value: "/exp" } }));
      await waitFor(() => assert.ok(option(renderer, "Explain")), "backend shortcut catalogue available");
      await act(async () => textarea(renderer).props.onKeyDown(key("Enter")));
      assert.ok(control(renderer, "Remove Explain"));
      await act(async () => control(renderer, "Add to message").props.onClick());
      await act(async () => button(renderer, "Skills & actions").props.onClick());
      assert.equal(picked(renderer).props.autocomplete, false, "mouse and slash use the shared picker");
      await act(async () => option(renderer, "Research files").props.onClick());
      assert.ok(control(renderer, "Remove Research files"));
      await act(async () => textarea(renderer).props.onChange({ target: { value: "@not-a-match" } }));
      await act(async () => textarea(renderer).props.onKeyDown(key("Escape")));
      assert.equal(Boolean(picked(renderer)), false, "Escape closes suggestions and leaves text intact");
      assert.equal(textarea(renderer).props.value, "@not-a-match");
      await act(async () => textarea(renderer).props.onKeyDown(key("Enter", { shiftKey: true })));
      await act(async () => textarea(renderer).props.onKeyDown(key("Enter", { nativeEvent: { isComposing: true } })));
      assert.equal(submissions, 0, "Shift Enter and IME remain composer input");
      await act(async () => textarea(renderer).props.onChange({ target: { value: "Explain this task" } }));
      await act(async () => button(renderer, "Conversation B").props.onClick());
      await waitFor(() => assert.equal(harness.state.conversations.conv_a.draft.content, "Explain this task"), "navigation persists text and selectors");
      const draft = harness.state.conversations.conv_a.draft.intended_config;
      assert.deepEqual(draft.memory_entry_ids, ["memory_record"]);
      assert.deepEqual(draft.skill_entry_ids, ["skill_record"]);
      assert.deepEqual(draft.shortcut_ids, ["explain"]);
      assert.equal(draft.model_overrides.remote.startup_overrides.ctx_size, 8192);
      await act(async () => button(renderer, "Conversation A").props.onClick());
      await waitFor(() => assert.equal(textarea(renderer).props.value, "Explain this task"), "intent restored");
      await waitFor(() => assert.equal(textarea(renderer).props.disabled, false), "restored Chat bound");
      assert.ok(control(renderer, "Remove Memory notes"));
      assert.ok(control(renderer, "Remove Explain"));
      assert.ok(control(renderer, "Remove Research files"));
      assert.equal(harness.state.outgoingRequests.some(item => /knowledge\/versions/.test(item.path)), false, "selection does not inject fetched source into the task");
      await act(async () => submit(renderer));
      await waitFor(() => assert.equal(queued ? harness.state.requests.queues.length : harness.state.requests.commands.length, 1), "selected intent admitted once");
      const request = queued ? harness.state.requests.queues[0].payload : { ...harness.state.requests.commands[0].payload.params.metadata.workbench, task: harness.state.requests.commands[0].payload.params.input.messages[0].content };
      contractPayloads.starts.push(request);
      assert.equal(request.task, "Explain this task", "shortcut instructions remain outside the authored user message");
      assert.deepEqual(request.memory_entry_ids, ["memory_record"]);
      assert.deepEqual(request.protected_instruction_entry_ids, ["missing_instruction"], "missing records retain their authored identity for backend correction");
      assert.deepEqual(request.skill_entry_ids, ["skill_record"]);
      assert.deepEqual(request.shortcut_ids, ["explain"]);
      assert.equal(Object.hasOwn(request, "model_overrides"), false);
      assert.equal(Object.hasOwn(request, "inherited_model_configuration"), false);
      await waitFor(() => assert.equal(Boolean(control(renderer, "Remove Explain")), false), "accepted message clears its one-message action");
      assert.equal(Boolean(control(renderer, "Remove Research files")), false, "accepted message clears its one-message skill");
      assert.ok(control(renderer, "Remove Memory notes"), "context remains selected for following messages");
      await act(async () => textarea(renderer).props.onChange({ target: { value: "/Disabled" } }));
      assert.equal(option(renderer, "Disabled skill").props["aria-disabled"], true);
      await act(async () => textarea(renderer).props.onKeyDown(key("Enter")));
      await waitFor(() => assert.equal(routes.at(-1), "knowledge"), "unavailable authored selection routes to its owner");
      assert.equal(harness.state.requests.commands.length, queued ? 0 : 1);
    } finally { await closeHarness(renderer, harness); renderer = null; }
  }

  const queueUpdates = [];
  let rejectSetupOnce = true;
  const queuedHarness = makeHarness({ aRun: run("running_snapshot", "running"), threadARun: run("running_snapshot", "running"), knowledgeEntries: entries,
    requestOverride: ({ req, res, url, body, state }) => {
      if (req.method !== "PATCH" || url.pathname !== "/v1/chat/conversations/conv_a/queue/paused_item") return;
      const payload = JSON.parse(body);
      queueUpdates.push(payload);
      contractPayloads.queueUpdates.push(payload);
      if (payload.intended_config && rejectSetupOnce) {
        rejectSetupOnce = false;
        json(res, 409, { detail: "This queued message changed. Refresh and try again." }); return true;
      }
      const current = state.conversations.conv_a;
      const item = current.queue.find(item => item.id === "paused_item");
      assert.equal(payload.expected_revision, item.revision);
      state.conversations.conv_a = { ...current, queue: current.queue.map(item => item.id !== "paused_item" ? item : { ...item, task: payload.task, attachment_ids: payload.attachment_ids, revision: item.revision + 1,
        ...(payload.intended_config ? { intended_config: payload.intended_config, frozen_config: { ...payload.intended_config, agent_setup_version_id: "frozen_by_backend" }, pause_error: null } : {}) }) };
      json(res, 200, state.conversations.conv_a); return true;
    } });
  const originalFrozen = { deployment_id: "dep_1", startup_overrides: { ctx_size: 2048 }, presented_tools: ["read_file"], agent_setup_version_id: "old_agent_version", memory_version_refs: ["old_memory_version"] };
  const untouchedItem = { id: "later_item", task: "Keep this captured setup", revision: 2, status: "queued", attachment_ids: [], intended_config: { work_mode: "plan" }, frozen_config: { ...originalFrozen } };
  queuedHarness.state.conversations.conv_a.queue = [
    { id: "paused_item", task: "Repair this task", revision: 5, status: "paused", pause_reason: "validation_failed", pause_error: "The selected context size cannot run. Choose a smaller context.", attachment_ids: [], intended_config: { deployment_id: "dep_1" }, frozen_config: originalFrozen },
    untouchedItem,
  ];
  queuedHarness.state.conversations.conv_a.draft = { revision: 1, content: "", attachment_ids: [], intended_config: { memory_entry_ids: ["memory_record"] } };
  const runningSnapshot = structuredClone(queuedHarness.state.conversations.conv_a.current_run);
  renderer = await renderChat(vite, queuedHarness);
  try {
    await waitFor(() => button(renderer, "Conversation A"), "queue recovery history ready");
    await act(async () => button(renderer, "Conversation A").props.onClick());
    const queuePanel = () => renderer.root.findAll(node => typeof node.type === "function" && node.type.name === "ChatQueuePanel")[0];
    await waitFor(() => assert.ok(queuePanel()), "paused queue visible");
    assert.match(textOf(queuePanel()), /selected context size cannot run/, "pause error is visible before opening Edit");
    assert.equal(renderer.root.findAll(node => node.type === "textarea" && node.props["aria-label"] === "Queued message").length, 0);
    const editButtons = () => renderer.root.findAll(node => node.type === "button" && node.props["aria-label"] === "Edit queued turn");
    await act(async () => editButtons()[0].props.onClick());
    const queueText = () => renderer.root.findAll(node => node.type === "textarea" && node.props["aria-label"] === "Queued message")[0];
    await act(async () => queueText().props.onChange({ target: { value: "My repaired task" } }));
    await act(async () => control(renderer, "Save queued turn").props.onClick());
    await waitFor(() => assert.equal(queueUpdates.length, 1), "text-only queue save captured");
    await waitFor(() => assert.equal(control(renderer, "Save queued turn").props.disabled, true), "text-only save settled");
    assert.equal(queueUpdates[0].expected_revision, 5);
    assert.equal(Object.hasOwn(queueUpdates[0], "replace_setup"), false, "ordinary text save retains the existing snapshot");
    assert.equal(Object.hasOwn(queueUpdates[0], "intended_config"), false, "text-only save never promotes frozen defaults");
    assert.deepEqual(queuedHarness.state.conversations.conv_a.queue[0].frozen_config, originalFrozen);
    const model = renderer.root.findAll(node => typeof node.type === "function" && node.type.name === "ChatModelControls")[0];
    await act(async () => model.props.onApply({ deployment_id: "dep_1", startup_overrides: { ctx_size: 8192 }, per_request_overrides: { reasoning_effort: "medium" }, model_overrides: { dep_1: { startup_overrides: { ctx_size: 8192 } } }, inherited_model_configuration: { deployment_id: "dep_1" } }));
    await act(async () => queueText().props.onChange({ target: { value: "Keep my latest unsaved edit" } }));
    const useSetup = () => button(renderer, "Use current setup");
    await act(async () => useSetup().props.onClick());
    await waitFor(() => assert.match(textOf(queuePanel()), /queued message changed/), "revision conflict is visible inside the owning queue item");
    assert.equal(queueText().props.value, "Keep my latest unsaved edit", "conflict preserves editable text");
    assert.equal(queueUpdates[1].expected_revision, 6);
    assert.equal(queueUpdates[1].replace_setup, true, "deliberate correction replaces the saved override layer");
    assert.equal(queueUpdates[1].intended_config.startup_overrides.ctx_size, 8192);
    assert.deepEqual(queueUpdates[1].intended_config.memory_entry_ids, ["memory_record"], "explicit repair takes staged context choices");
    for (const key of ["model_overrides", "inherited_model_configuration", "presented_tools", "memory_version_refs"]) assert.equal(Object.hasOwn(queueUpdates[1].intended_config, key), false, `${key} never leaks from a draft map or previous frozen setup`);
    assert.equal(queueUpdates[1].intended_config.agent_setup_version_id, undefined, "old frozen agent version never becomes a composer override");
    assert.deepEqual(queuedHarness.state.conversations.conv_a.queue[1], untouchedItem);
    assert.deepEqual(queuedHarness.state.conversations.conv_a.current_run, runningSnapshot);
    // An authoritative refresh advances the revision while the dirty local
    // edit survives. The deliberate retry must use that new revision.
    queuedHarness.state.conversations.conv_a.queue[0] = { ...queuedHarness.state.conversations.conv_a.queue[0], revision: 7 };
    await act(async () => queuePanel().props.onUpdated(structuredClone(queuedHarness.state.conversations.conv_a)));
    assert.equal(queueText().props.value, "Keep my latest unsaved edit");
    await act(async () => useSetup().props.onClick());
    await waitFor(() => assert.equal(queueUpdates.length, 3), "corrected setup retry captured");
    await waitFor(() => assert.equal(control(renderer, "Save queued turn").props.disabled, true), "successful setup save settled");
    assert.equal(queueUpdates[2].expected_revision, 7);
    assert.equal(queueUpdates[2].replace_setup, true);
    assert.equal(queuedHarness.state.conversations.conv_a.queue[0].frozen_config.agent_setup_version_id, "frozen_by_backend", "backend owns the new exact snapshot");
    assert.deepEqual(queuedHarness.state.conversations.conv_a.queue[1], untouchedItem, "later queued snapshot is unchanged");
    assert.deepEqual(queuedHarness.state.conversations.conv_a.current_run, runningSnapshot, "running snapshot is unchanged");
    assert.equal(queuedHarness.state.outgoingRequests.some(item => item.path.endsWith("/queue/resume")), false, "repair cannot silently resume the queue");
    contractPayloads.starts.push({ ...queueUpdates[2].intended_config, task: queueUpdates[2].task });
  } finally { await closeHarness(renderer, queuedHarness); renderer = null; }

  const choice = deferred();
  let checking = false;
  const guarded = makeHarness({ aRun: null, bRun: null, threadARun: null, threadBRun: null,
    agentSetups: [{ id: "agent_target", current_version_id: "target_v1", name: "Target agent", configuration: {}, missing_dependencies: [] }],
    readiness: async ({ payload }) => {
      if (payload.agent_setup_id === "agent_target") { checking = true; await choice.promise; }
      return { status: "ready", can_send: true, issues: [], selection: null };
    } });
  renderer = await renderChat(vite, guarded);
  try {
    await waitFor(() => button(renderer, "Conversation A"), "guarded history ready");
    await act(async () => button(renderer, "Conversation A").props.onClick());
    await waitFor(() => assert.equal(textarea(renderer).props.disabled, false), "original owner bound");
    await act(async () => button(renderer, "Target agent").props.onClick());
    await waitFor(() => assert.equal(checking, true), "agent compatibility held for original owner");
    await act(async () => button(renderer, "Conversation B").props.onClick());
    await waitFor(() => assert.equal(textarea(renderer).props.disabled, false), "destination owner bound");
    await act(async () => { choice.resolve(); await Promise.resolve(); });
    await waitFor(() => assert.equal(guarded.state.consumedResponses.some(item => item.path === "/v1/chat/conversations/conv_a/readiness" && item.method === "POST"), true), "old compatibility consumed");
    assert.doesNotMatch(textOf(control(renderer, "Main agent")), /Target agent/, "late agent selection cannot retarget the destination Chat");
    assert.equal(guarded.state.requests.resolutions.some(item => item.agent_setup_id === "agent_target"), false, "late choice cannot load or resolve against a changed owner");
  } finally { choice.resolve(); await closeHarness(renderer, guarded); renderer = null; }

  const fresh = makeHarness({ aRun: null, threadARun: null, commandProjectsRun: true, commandProjectedStatus: "running" });
  renderer = await renderChat(vite, fresh);
  try {
    await waitFor(() => button(renderer, "Conversation A"), "fresh shell ready");
    const model = renderer.root.findAll(node => typeof node.type === "function" && node.type.name === "ChatModelControls")[0];
    await act(async () => model.props.onApply({ deployment_id: "dep_1", model_overrides: { remote: { startup_overrides: { ctx_size: 8192 } } }, inherited_model_configuration: { deployment_id: "dep_1" } }));
    await act(async () => textarea(renderer).props.onChange({ target: { value: "Start a new Chat" } }));
      await act(async () => submit(renderer));
    await waitFor(() => assert.equal(fresh.state.requests.commands.length, 1), "fresh admission complete");
    contractPayloads.creates.push(fresh.state.requests.creates[0]);
    assert.ok(fresh.state.requests.draftUpdates[0].payload.intended_config.model_overrides, "draft persistence keeps the model map despite strict wire separation");
    contractPayloads.starts.push({ ...fresh.state.requests.commands[0].payload.params.metadata.workbench, task: "Start a new Chat" });
  } finally { await closeHarness(renderer, fresh); renderer = null; }

  // Use the actual backend models, including extra=forbid, against captured UI
  // payloads. A permissive renderer fixture cannot hide invalid admission keys.
  const validation = spawnSync("uv", ["run", "python", "-c", "import tests, json, sys; from workbench_backend.chat.schemas import ChatStartRequest, ChatConversationCreateRequest, ChatQueueItemUpdateRequest; values=json.load(sys.stdin); [ChatStartRequest.model_validate(value) for value in values['starts']]; [ChatConversationCreateRequest.model_validate(value, extra='forbid') for value in values['creates']]; [ChatQueueItemUpdateRequest.model_validate(value, extra='forbid') for value in values['queueUpdates']]; print('Strict backend admission contracts passed.')"], { cwd: path.join(desktop, "../backend"), input: JSON.stringify(contractPayloads), encoding: "utf8", windowsHide: true });
  assert.equal(validation.status, 0, validation.stderr || validation.stdout || validation.error?.message);

  const { WorkerSettings } = await vite.ssrLoadModule("/src/renderer/WorkerSettings.tsx");
  const { api } = await vite.ssrLoadModule("/src/renderer/api.ts");
  const original = { browserRuntime: api.browserRuntime, windowRuntime: api.windowRuntime, installBrowserRuntime: api.installBrowserRuntime, installWindowRuntime: api.installWindowRuntime };
  const calls = [];
  try {
    api.browserRuntime = async () => ({ supported: true, installed: false });
    api.windowRuntime = async () => ({ installed: false, available: false });
    api.installBrowserRuntime = async () => { calls.push("browser"); return { supported: true, installed: true, chrome_available: true }; };
    api.installWindowRuntime = async () => { calls.push("windows"); return { installed: true, available: true }; };
    await act(async () => { renderer = create(React.createElement(WorkerSettings)); await Promise.resolve(); });
    assert.equal(calls.length, 0, "opening Settings observes workers without installing");
    await act(async () => button(renderer, "Install browser worker").props.onClick());
    await act(async () => button(renderer, "Install Windows worker").props.onClick());
    assert.deepEqual(calls, ["browser", "windows"], "installation works before any model or Chat exists");
  } finally { Object.assign(api, original); if (renderer) await act(async () => renderer.unmount()); renderer = null; }
  console.log("Shared composer pickers, durable record selectors, strict backend admission and Settings worker ownership checks passed.");
} finally {
  if (renderer) await act(async () => renderer.unmount());
  await vite.close();
}
