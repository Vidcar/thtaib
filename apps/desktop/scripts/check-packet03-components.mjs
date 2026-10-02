import assert from "node:assert/strict";
import path from "node:path";
import { fileURLToPath } from "node:url";

import React from "react";
import { act, create } from "react-test-renderer";
import { createServer as createViteServer } from "vite";

const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../..");
const desktopRoot = path.join(repoRoot, "apps/desktop");

globalThis.IS_REACT_ACT_ENVIRONMENT = true;

globalThis.window = {
  workbench: {
    saveAsset: async () => "C:\\Temp\\saved.txt",
  },
};

const vite = await createViteServer({ root: desktopRoot, appType: "custom", server: { middlewareMode: true, hmr: false }, logLevel: "error" });
try {
  const { ComposerAttachments } = await vite.ssrLoadModule("/src/renderer/ComposerAttachments.tsx");
  const { LibraryPanel } = await vite.ssrLoadModule("/src/renderer/LibraryPanel.tsx");
  const { ChatHistoryActions } = await vite.ssrLoadModule("/src/renderer/ChatHistoryActions.tsx");
  const { AnswerActions } = await vite.ssrLoadModule("/src/renderer/AnswerActions.tsx");
  const { PanelResize, usePanelWidth } = await vite.ssrLoadModule("/src/renderer/PanelResize.tsx");
  const { HoverHelp } = await vite.ssrLoadModule("/src/renderer/HoverHelp.tsx");
  const { MessageTaskActions } = await vite.ssrLoadModule("/src/renderer/MessageTaskActions.tsx");
  const { ChatMeasurements } = await vite.ssrLoadModule("/src/renderer/ChatMeasurements.tsx");
  const { AttentionPanel } = await vite.ssrLoadModule("/src/renderer/AttentionPanel.tsx");

  await checkComposerUploadStaleGuard(ComposerAttachments);
  await checkDropWaitsForSavedAttachments(ComposerAttachments);
  await checkLibraryStalePreviewAndScopedCalls(LibraryPanel);
  await checkLibraryScopeNamesAndStaleActions(LibraryPanel);
  await checkLibrarySourceNamesDoNotBlockFiles(LibraryPanel);
  await checkChatHistoryActions(ChatHistoryActions, AnswerActions);
  await checkPanelResize(PanelResize, usePanelWidth);
  await checkHoverHelp(HoverHelp);
  await checkMessageTaskActions(MessageTaskActions);
  await checkChatMeasurements(ChatMeasurements);
  await checkAttentionTargets(AttentionPanel);
  await checkAttentionEmpty(AttentionPanel);
  await checkBlockedAttentionNavigationPreservesItem(AttentionPanel);
} finally {
  await vite.close();
}

console.log("Packet03 component checks passed.");

async function checkLibraryScopeNamesAndStaleActions(LibraryPanel) {
  const originalFetch = globalThis.fetch;
  const heldDeletion = createDeferred();
  const heldSave = createDeferred();
  const originalSave = globalThis.window.workbench.saveAsset;
  const requests = [], saves = [];
  const files = [
    asset("asset_a", "a.txt", "chat_a", { project_path: "D:\\ProjectA" }),
    asset("asset_b", "b.txt", "chat_b", { project_path: "D:\\ProjectB" }),
    asset("asset_orphan", "orphan.txt", "gone_chat", { project_path: "D:\\Gone" }),
  ];
  let renderer;
  globalThis.window.workbench.saveAsset = async value => { saves.push(value); return heldSave.promise; };
  globalThis.fetch = async (url, init = {}) => {
    const address = new URL(String(url));
    if (address.pathname === "/v1/projects") return jsonResponse([
      { id: "project_a", name: "Writing project", path: "D:\\Writing", canonical_path: "D:\\ProjectA", active: true, missing: false },
      { id: "project_b", name: "Research project", path: "D:\\ProjectB", active: true, missing: true },
    ]);
    if (address.pathname === "/v1/chat/conversations") return jsonResponse([
      { id: "chat_a", title: "Writing chat", archived: false },
      { id: "chat_b", display_title: "Research chat", archived: true },
    ]);
    if (address.pathname === "/v1/assets/delete-preview") return heldDeletion.promise;
    if (address.pathname.endsWith("/preview")) {
      const current = files.find(file => address.pathname.includes(file.id));
      return jsonResponse({ ...current, preview: "Saved source text", truncated: false, source_status: "retained_only" });
    }
    if (address.pathname === "/v1/assets") {
      requests.push(address);
      const project = address.searchParams.get("project_path"), chat = address.searchParams.get("session_id");
      assert.ok(!(project && chat), "Library never asks for two OR-combined scope targets");
      return jsonResponse(files.filter(file => (!project || file.project_path === project) && (!chat || file.session_id === chat)));
    }
    throw new Error("Unexpected Library request " + address.pathname + " " + init.method);
  };
  try {
    await act(async () => { renderer = create(React.createElement(LibraryPanel)); await tick(); });
    assert.equal(requests[0].searchParams.has("session_id"), false, "All files has no hidden conversation filter");
    assert.equal(requests[0].searchParams.has("project_path"), false, "All files has no hidden project filter");
    assert.match(textOf(renderer.root), /Writing chat/);
    assert.match(textOf(renderer.root), /Writing project/);
    assert.match(textOf(renderer.root), /Research chat · Archived/);
    assert.match(textOf(renderer.root), /Research project · Unavailable/);
    assert.match(textOf(renderer.root), /Chat unavailable/);
    assert.match(textOf(renderer.root), /Gone · Project unavailable/);
    assert.equal(renderer.root.findAllByProps({ "aria-label": "File actions" }).length, 0, "bulk actions stay hidden until files are selected");
    assert.equal(renderer.root.findAllByType("button").filter(node => textOf(node).includes("Use in Chat")).length, 0, "Library has no Chat handoff");

    await act(async () => renderer.root.findByProps({ "aria-label": "File location" }).props.onChange({ target: { value: "project" } }));
    const beforeTarget = requests.length;
    assert.equal(textOf(renderer.root.findByProps({ className: "file-browser-empty" }).findByType("strong")), "Choose a project");
    assert.doesNotMatch(textOf(renderer.root), /Select a project to see its saved files/);
    assert.equal(renderer.root.findByProps({ "aria-label": "Project" }).findAllByType("option").filter(node => textOf(node) === "Writing project").length, 1, "canonical project paths share one readable option");
    await act(async () => renderer.root.findByProps({ "aria-label": "Project" }).props.onChange({ target: { value: "D:\\ProjectA" } }));
    assert.equal(requests.length, beforeTarget + 1);
    assert.equal(requests.at(-1).searchParams.get("project_path"), "D:\\ProjectA");
    assert.equal(requests.at(-1).searchParams.has("session_id"), false);
    assert.equal(renderer.root.findAllByProps({ "aria-label": "Preview b.txt" }).length, 0, "project scope actually filters its files");
    await act(async () => renderer.root.findByProps({ "aria-label": "Select a.txt" }).props.onChange({ target: { checked: true } }));
    assert.equal(renderer.root.findAllByProps({ "aria-label": "File actions" }).length, 1);
    await act(async () => { exactButton(renderer, "Delete").props.onClick(); await tick(); });
    await act(async () => renderer.root.findByProps({ "aria-label": "File location" }).props.onChange({ target: { value: "chat" } }));
    await act(async () => renderer.root.findByProps({ "aria-label": "Chat" }).props.onChange({ target: { value: "chat_b" } }));
    assert.equal(requests.at(-1).searchParams.get("session_id"), "chat_b");
    assert.equal(requests.at(-1).searchParams.has("project_path"), false);
    await act(async () => { heldDeletion.resolve(jsonResponse({ affected_asset_ids: ["asset_a"], preserved_asset_ids: [], note: "Old scope" })); await tick(); });
    assert.equal(renderer.root.findAllByProps({ "aria-label": "Review file deletion" }).length, 0, "old deletion review cannot appear after a scope change");
    assert.equal(renderer.root.findAllByProps({ "aria-label": "File actions" }).length, 0, "scope changes clear old selection");
    await act(async () => { renderer.root.findByProps({ "aria-label": "Preview b.txt" }).props.onClick(); await tick(); });
    await act(async () => { button(renderer, "Save copy").props.onClick(); await tick(); });
    assert.equal(saves[0].sessionId, "chat_b", "saving uses the retained item's source scope");
    await act(async () => renderer.root.findByProps({ "aria-label": "File location" }).props.onChange({ target: { value: "all" } }));
    await act(async () => { heldSave.resolve("D:\\saved-b.txt"); await tick(); });
    assert.doesNotMatch(textOf(renderer.root), /Saved b.txt/, "late save status cannot appear in another scope");
    await act(async () => renderer.root.findByProps({ "aria-label": "Select orphan.txt" }).props.onChange({ target: { checked: true } }));
    assert.equal(exactButton(renderer, "Delete").props.disabled, false, "stale actions cannot leave the new scope busy");
    await act(async () => button(renderer, "Clear selection").props.onClick());
    assert.equal(renderer.root.findAllByProps({ "aria-label": "File actions" }).length, 0);
  } finally {
    heldDeletion.resolve(jsonResponse({ affected_asset_ids: [], preserved_asset_ids: [] })); heldSave.resolve(null);
    if (renderer) await act(async () => renderer.unmount());
    globalThis.fetch = originalFetch; globalThis.window.workbench.saveAsset = originalSave;
  }
}

async function checkLibrarySourceNamesDoNotBlockFiles(LibraryPanel) {
  const originalFetch = globalThis.fetch;
  const heldChats = createDeferred();
  let renderer;
  globalThis.fetch = async url => {
    const address = new URL(String(url));
    if (address.pathname === "/v1/projects") throw new Error("Projects offline");
    if (address.pathname === "/v1/chat/conversations") return heldChats.promise;
    if (address.pathname === "/v1/assets") return jsonResponse([asset("asset_a", "a.txt", "chat_a", { project_path: "D:\\Writing" })]);
    throw new Error("Unexpected request " + address.pathname);
  };
  try {
    await act(async () => { renderer = create(React.createElement(LibraryPanel)); await tick(); });
    assert.equal(renderer.root.findAllByProps({ "aria-label": "Preview a.txt" }).length, 1, "retained files load while chat names are pending");
    assert.match(textOf(renderer.root), /Saved files remain available/);
    assert.match(textOf(renderer.root), /Writing · Name unavailable/);
    await act(async () => { heldChats.resolve(jsonResponse([{ id: "chat_a", title: "Writing chat" }])); await tick(); });
    assert.match(textOf(renderer.root), /Writing chat/, "successful source names appear independently of another catalogue's failure");
    await act(async () => renderer.root.findByProps({ "aria-label": "Search files" }).props.onChange({ target: { value: "Writing chat" } }));
    assert.equal(renderer.root.findAllByProps({ "aria-label": "Preview a.txt" }).length, 1, "file search includes human source names");
  } finally {
    heldChats.resolve(jsonResponse([])); if (renderer) await act(async () => renderer.unmount()); globalThis.fetch = originalFetch;
  }
}

async function checkBlockedAttentionNavigationPreservesItem(AttentionPanel) {
  const originalFetch = globalThis.fetch;
  const dismissed = [];
  const navigation = createDeferred();
  let renderer;
  const item = { identity: "approval-pending", kind: "approval", title: "Needs approval", conversation_id: "chat_a", run_id: "run_a" };
  globalThis.fetch = async (url, init = {}) => { if (init.method === "POST") { dismissed.push(String(url)); return jsonResponse({ dismissed: true }); } return jsonResponse([item]); };
  try {
    await act(async () => { renderer = create(React.createElement(AttentionPanel, { onOpenItem: () => navigation.promise })); await tick(); });
    let opening;
    await act(async () => { opening = button(renderer, "Open").props.onClick(); await tick(); });
    assert.deepEqual(dismissed, [], "attention stays visible while draft navigation is being checked");
    await act(async () => { navigation.resolve(false); await opening; });
    assert.deepEqual(dismissed, [], "a blocked navigation cannot acknowledge or hide unfinished attention");
    assert.ok(textOf(renderer.root).includes("Needs approval"));
    await act(async () => renderer.update(React.createElement(AttentionPanel, { onOpenItem: async () => true })));
    await act(async () => { await button(renderer, "Open").props.onClick(); });
    assert.equal(dismissed.length, 1, "accepted navigation acknowledges the exact item once");
    assert.ok(dismissed[0].includes("approval-pending/dismiss"));
  } finally { navigation.resolve(false); if (renderer) await act(async () => renderer.unmount()); globalThis.fetch = originalFetch; }
}

async function checkChatMeasurements(ChatMeasurements) {
  const originals = { window: globalThis.window, document: globalThis.document };
  const listeners = new Map();
  const events = { addEventListener: (key, handler) => listeners.set(key, handler), removeEventListener: key => listeners.delete(key) };
  const anchor = { getBoundingClientRect: () => ({ left: 710, top: 520, bottom: 548 }), contains: () => false };
  const tip = { getBoundingClientRect: () => ({ width: 272, height: 180 }), contains: () => false };
  globalThis.window = { ...originals.window, innerWidth: 800, innerHeight: 600, ...events };
  globalThis.document = { body: { nodeType: 1, children: [], createNodeMock: () => tip }, ...events };
  const context = { input_tokens: 2516, counting_basis: "estimated", capacity_tokens: 65536 };
  let run = { id: "usage", status: "running", context_observation: context };
  let renderer;
  const tipText = () => textOf(renderer.root.findByProps({ className: "hover-help-bubble chat-usage-bubble" }));
  const update = async observation => {
    run = { ...run, generation_observation: observation };
    await act(async () => renderer.update(React.createElement(ChatMeasurements, { run })));
  };
  try {
    await act(async () => { renderer = create(React.createElement(ChatMeasurements, { run }), { createNodeMock: node => node.type === "button" ? anchor : tip }); });
    const trigger = renderer.root.findByProps({ "aria-label": "Context and speed" });
    assert.equal(trigger.props.title, undefined, "usage uses a real hover/focus popover, not a native title");
    await act(async () => renderer.root.findByProps({ className: "hover-help" }).props.onMouseEnter());
    assert.match(tipText(), /Estimated/);
    assert.match(tipText(), /2,516/);
    assert.equal(renderer.root.findByProps({ role: "tooltip" }).props.style.left, 520, "usage is kept inside a narrow window");
    await update({ request_id: "call-a", phase: "generating", input_tokens: 1946, output_tokens: 59, context_used_tokens: 2005, context_limit: 65536, tokens_per_second: 43.29, basis: "llama_cpp_timings", interval: "current_model_call_generation" });
    assert.match(tipText(), /Generating/);
    assert.match(tipText(), /2,005/);
    assert.doesNotMatch(tipText(), /Estimated|2,516/);
    assert.match(tipText(), /43.3 tok\/s/);
    assert.equal(renderer.root.findByProps({ role: "status" }).children.join(""), "Generating", "the screen-reader stage matches the visible model stage");
    assert.match(textOf(trigger), /Generating.*43.3 tok\/s/, "generation is visible without opening the measurements popover");
    for (const [phase, label] of [["using_tools", "Using tools"], ["summarizing", "Summarizing"], ["checking_images", "Checking image support"]]) {
      run = { ...run, activity_phase: phase };
      await act(async () => renderer.update(React.createElement(ChatMeasurements, { run })));
      assert.equal(renderer.root.findByProps({ role: "status" }).children.join(""), label);
      assert.match(textOf(trigger), new RegExp(label));
      assert.equal(renderer.root.findAllByProps({ className: "usage-live-dot" }).length, 0, "a prior work sample cannot imply generation during another stage");
    }
    run = { ...run, status: "completed", activity_phase: "thinking" };
    await act(async () => renderer.update(React.createElement(ChatMeasurements, { run })));
    assert.equal(renderer.root.findAllByProps({ role: "status" }).length, 0, "a terminal run ignores a retained generating sample");
    assert.doesNotMatch(tipText(), /Thinking|Generating/);
    run = { ...run, status: "running", activity_phase: null };
    run = { ...run, finalization_phase: "saving_changes" };
    await act(async () => renderer.update(React.createElement(ChatMeasurements, { run })));
    assert.match(tipText(), /Saving/);
    assert.doesNotMatch(tipText(), /Live|Generating/, "settled generation is not presented as live while saving");
    assert.equal(renderer.root.findByProps({ role: "status" }).children.join(""), "Saving project state");
    run = { ...run, finalization_phase: null };
    await update({ ...run.generation_observation, phase: "completed", interval: "last_model_call_generation" });
    assert.match(tipText(), /Last request generation average/);
    assert.equal(renderer.root.findByProps({ role: "status" }).children.join(""), "Working", "unknown active work does not infer a thinking phase");
    assert.doesNotMatch(tipText(), /Live/);
    await update(null);
    assert.match(tipText(), /Estimated/);
    assert.doesNotMatch(tipText(), /43.3|2,005/, "a new request cannot keep the prior call's live counters");
    await update({ phase: "prompt_processing", input_tokens: 0, output_tokens: null, context_used_tokens: 0, context_limit: 65536, tokens_per_second: null, basis: "llama_cpp_timings" });
    assert.match(tipText(), /Preparing/);
    assert.doesNotMatch(tipText(), /Estimated|0.0 tok\/s/, "zero reported context is real; missing speed is not zero");
    await update({ phase: "completed", input_tokens: 1946, output_tokens: 59, tokens_per_second: 38.7, basis: "reported_tokens_model_call_wall_time" });
    assert.match(tipText(), /including prompt processing/);
    assert.match(tipText(), /2,005/, "reported legacy usage is actual even without native timing fields");
    await update({ phase: "completed", input_tokens: 26587, cached_input_tokens: 26506, processed_input_tokens: 81, output_tokens: 914, context_used_tokens: 27501, context_limit: 65536, tokens_per_second: 51.3, prefill_seconds: 42.21, time_to_first_token_seconds: 42.48, basis: "llama_cpp_timings" });
    const rows = renderer.root.findByProps({ className: "usage-token-counts" }).children;
    assert.deepEqual(rows.map(textOf), ["Input total26,587", "Cached input26,506", "Newly processed81", "Output914"]);
    assert.match(tipText(), /parts of input total/);
    assert.match(tipText(), /27,501.*65,536.*42%/);
    assert.match(tipText(), /Prompt processing42.21 s.*First output delay42.48 s/);
    run = { ...run, generation_history: [
      { request_id: "call-old", purpose: "work", phase: "completed", cached_input_tokens: 6065, processed_input_tokens: 29, prefill_seconds: .41, time_to_first_token_seconds: .46 },
      { request_id: "call-summary", purpose: "summary", phase: "interrupted", cached_input_tokens: null, processed_input_tokens: null, prefill_seconds: null, time_to_first_token_seconds: null },
    ] };
    await update(null);
    assert.match(tipText(), /Recent model calls \(2\)/, "a reset preserves earlier call evidence");
    assert.equal(renderer.root.findByProps({ "aria-label": "Context and speed", role: "dialog" }).props.role, "dialog", "interactive call history uses a labelled nonmodal dialog");
    const calls = renderer.root.findByProps({ "aria-label": "Completed model call measurements" });
    assert.equal(calls.props.tabIndex, 0, "call history is keyboard scrollable");
    assert.match(textOf(calls), /Summary.*Stopped.*Cached inputNot reported.*Newly processedNot reported.*Work.*Complete.*Cached input6,065.*Newly processed29.*0.41 s/);
    await update({ phase: "completed", prefill_seconds: -1, time_to_first_token_seconds: Infinity });
    assert.deepEqual(renderer.root.findByProps({ className: "usage-token-counts usage-timings" }).children.map(textOf), ["Prompt processingNot reported", "First output delayNot reported"]);
    for (const [patch, label] of [[{pending_interrupt:{}}, "Waiting"], [{pending_interrupt:null,status:"cancel_requested"}, "Stopping"], [{status:"queued"}, "Starting"]]) {
      run = {...run,...patch};
      await act(async () => renderer.update(React.createElement(ChatMeasurements, {run})));
      assert.equal(renderer.root.findByProps({role:"status"}).children.join(""), label);
    }
    await act(async () => listeners.get("keydown")({ key: "Escape", stopPropagation() {} }));
    assert.equal(renderer.root.findAllByProps({ className: "hover-help-bubble chat-usage-bubble" }).length, 0);
    await act(async () => trigger.props.onFocus());
    assert.equal(renderer.root.findAllByProps({ className: "hover-help-bubble chat-usage-bubble" }).length, 1, "keyboard focus opens the same context details");
    await act(async () => renderer.update(React.createElement(ChatMeasurements, { run, onInspect() {} })));
    const usageTrigger = renderer.root.findByProps({ className: "chat-usage-trigger" });
    await act(async () => usageTrigger.props.onFocus());
    const bubble = renderer.root.findByProps({ className: "hover-help-bubble chat-usage-bubble" });
    const inputs = bubble.findAll((node) => node.type === "button" && textOf(node).trim() === "Inputs");
    assert.equal(inputs.length, 1, "the open context bubble has one Inputs control");
    assert.equal(inputs[0].props.title, "Instructions, memories, skills, and files for the next message.");
    assert.doesNotMatch(textOf(renderer.root), /What the agent sees/);
  } finally {
    if (renderer) await act(async () => renderer.unmount());
    Object.assign(globalThis, originals);
  }
}

async function checkAttentionTargets(AttentionPanel) {
  const originalFetch = globalThis.fetch;
  const items = [
    { identity: "approval_chat", kind: "approval", title: "Chat needs approval", conversation_id: "chat_waiting", run_id: "run_chat" },
    { identity: "question_agent", kind: "question", title: "Task needs an answer", conversation_id: null, run_id: "run_agent" },
  ];
  const opened = [];
  let renderer;
  globalThis.fetch = async () => jsonResponse(items);
  try {
    await act(async () => {
      renderer = create(React.createElement(AttentionPanel, { onOpenItem: item => opened.push(item) }));
      await tick();
    });
    const buttons = renderer.root.findAll(node => node.type === "button" && textOf(node).includes("Open"));
    await act(async () => { await Promise.all(buttons.map((target) => Promise.resolve(target.props.onClick()))); });
    assert.deepEqual(opened, items, "Attention preserves the exact conversation or task target rather than dropping non-Chat identity");
  } finally {
    if (renderer) await act(async () => renderer.unmount());
    globalThis.fetch = originalFetch;
  }
}

async function checkAttentionEmpty(AttentionPanel) {
  const originalFetch = globalThis.fetch;
  let renderer;
  globalThis.fetch = async () => jsonResponse([]);
  try {
    await act(async () => {
      renderer = create(React.createElement(AttentionPanel));
      await tick();
    });
    const empty = renderer.root.findAll((node) => node.props?.className === "empty-state");
    assert.equal(empty.length, 1, "a successful empty attention read has one empty state");
    assert.equal(textOf(empty[0].findByType("h3")), "Nothing waiting");
    assert.doesNotMatch(textOf(renderer.root), /You're all caught up\./);
    assert.equal(renderer.root.findAll((node) => node.type === "p" && textOf(node) === "Loading…").length, 0, "the loading line is not the empty title");
  } finally {
    if (renderer) await act(async () => renderer.unmount());
    globalThis.fetch = originalFetch;
  }
}

async function checkHoverHelp(HoverHelp) {
  const originals = { window: globalThis.window, document: globalThis.document, setTimeout: globalThis.setTimeout, clearTimeout: globalThis.clearTimeout };
  const listeners = new Map();
  const timers = new Map();
  let timerId = 0;
  let anchor = { left: 900, top: 750, bottom: 772 };
  const buttonNode = { getBoundingClientRect: () => anchor, contains: target => target === buttonNode };
  const tooltipNode = { getBoundingClientRect: () => ({ width: 282, height: 210 }), contains: target => target === tooltipNode };
  const events = { addEventListener: (name, handler) => listeners.set(name, handler), removeEventListener: name => listeners.delete(name) };
  globalThis.window = { ...originals.window, innerWidth: 1024, innerHeight: 800, ...events };
  globalThis.document = { body: { nodeType: 1, children: [], createNodeMock: () => tooltipNode }, ...events };
  globalThis.setTimeout = handler => { timers.set(++timerId, handler); return timerId; };
  globalThis.clearTimeout = id => timers.delete(id);
  let renderer;
  const tooltips = () => renderer.root.findAllByProps({ role: "tooltip" });
  const help = () => renderer.root.findByProps({ className: "hover-help" });
  const button = () => renderer.root.findByType("button");
  const flushTimers = () => act(async () => { for (const [id, handler] of [...timers]) { timers.delete(id); handler(); } });
  try {
    await act(async () => { renderer = create(React.createElement(HoverHelp, { title: "About context" }, "A long help explanation"), {
      createNodeMock: element => element.type === "button" ? buttonNode : tooltipNode,
    }); });
    await act(async () => button().props.onFocus());
    assert.equal(tooltips()[0].props.style.left, 734, "tooltip is constrained by its measured width");
    assert.equal(tooltips()[0].props.style.top, 532, "long tooltip flips above its trigger without leaving the viewport");
    assert.equal(button().props["aria-describedby"], tooltips()[0].props.id);
    await act(async () => help().props.onMouseLeave());
    await flushTimers();
    assert.equal(tooltips().length, 1, "mouse leaving does not dismiss keyboard-focused help");
    await act(async () => button().props.onBlur());
    await act(async () => tooltips()[0].props.onMouseEnter());
    await flushTimers();
    assert.equal(tooltips().length, 1, "moving into the bubble keeps it available to read and select");
    await act(async () => tooltips()[0].props.onMouseLeave());
    await flushTimers();
    assert.equal(tooltips().length, 0);

    await act(async () => help().props.onMouseEnter());
    anchor = { left: 24, top: 120, bottom: 142 };
    await act(async () => listeners.get("scroll")());
    assert.equal(tooltips()[0].props.style.top, 150, "scrolling follows the trigger");
    await act(async () => listeners.get("keydown")({ key: "Escape", stopPropagation() {} }));
    assert.equal(tooltips().length, 0, "Escape dismisses hovered help");
    assert.equal(listeners.size, 0, "closed help removes document listeners");
    await act(async () => button().props.onClick());
    await act(async () => listeners.get("pointerdown")({ target: {} }));
    assert.equal(tooltips().length, 0, "touch-opened help closes on an outside tap");
    await act(async () => help().props.onMouseEnter());
    await act(async () => help().props.onMouseLeave());
    assert.equal(timers.size, 1);
    await act(async () => renderer.unmount());
    renderer = null;
    assert.equal(timers.size, 0, "unmount cancels delayed state changes");
    assert.equal(listeners.size, 0);
  } finally {
    if (renderer) await act(async () => renderer.unmount());
    Object.assign(globalThis, originals);
  }
}

async function checkMessageTaskActions(MessageTaskActions) {
  const saved = { window: globalThis.window, document: globalThis.document };
  const events = { addEventListener() {}, removeEventListener() {} };
  const buttonNode = { getBoundingClientRect: () => ({ left: 40, top: 200, bottom: 228, width: 28, height: 28 }), contains: () => false, matches: () => false };
  const tooltipNode = { getBoundingClientRect: () => ({ width: 180, height: 28 }), contains: () => false };
  globalThis.window = { ...saved.window, innerWidth: 800, innerHeight: 600, ...events };
  globalThis.document = { body: { nodeType: 1, children: [], createNodeMock: () => tooltipNode }, querySelector: () => null, ...events };
  const calls = { retry: 0, edit: 0 };
  const held = "Wait until this turn finishes";
  const render = (reason) => React.createElement(MessageTaskActions, {
    runId: "run_1",
    held: reason,
    onRetry: () => { calls.retry += 1; },
    onEdit: () => { calls.edit += 1; },
  });
  let renderer;
  try {
    await act(async () => {
      renderer = create(render(held), { createNodeMock: (element) => element.type === "button" ? buttonNode : tooltipNode });
    });
    const buttons = () => renderer.root.findAllByType("button");
    assert.equal(buttons().length, 2);
    for (const node of buttons()) {
      assert.equal(node.props["aria-disabled"], true);
      assert.equal(node.props.disabled, undefined);
      assert.equal(node.props.title, held);
      assert.equal(node.props["aria-label"] === "Retry" || node.props["aria-label"] === "Edit", true);
    }
    assert.equal(buttons().find((node) => node.props["aria-label"] === "Edit").props["data-edit-run"], "run_1");
    await act(async () => { buttons()[0].props.onClick(); buttons()[1].props.onClick(); });
    await act(async () => {
      buttons()[0].props.onKeyDown({ key: "Enter", preventDefault() {}, stopPropagation() {} });
      buttons()[1].props.onKeyDown({ key: " ", preventDefault() {}, stopPropagation() {} });
    });
    assert.equal(calls.retry, 0);
    assert.equal(calls.edit, 0);
    await act(async () => renderer.root.findAllByProps({ className: "hover-help" })[0].props.onMouseEnter());
    const tips = renderer.root.findAllByProps({ role: "tooltip" });
    assert.equal(tips.length > 0, true);
    assert.equal(tips[0].props.children, held);
    await act(async () => { renderer.update(render(null)); });
    const active = renderer.root.findAllByType("button");
    for (const node of active) assert.equal(node.props["aria-disabled"], undefined);
    await act(async () => { active[0].props.onClick(); active[1].props.onClick(); });
    assert.equal(calls.retry, 1);
    assert.equal(calls.edit, 1);
  } finally {
    if (renderer) await act(async () => renderer.unmount());
    globalThis.window = saved.window;
    globalThis.document = saved.document;
  }
}

async function checkPanelResize(PanelResize, usePanelWidth) {
  const savedWindow = globalThis.window;
  const stored = new Map([["review.panel.width", "250"]]);
  globalThis.window = { ...savedWindow, localStorage: { getItem: key => stored.get(key) ?? null, setItem: (key, value) => stored.set(key, value) } };
  function ResizablePanel({ reverse = false }) {
    const [width, setWidth] = usePanelWidth("review.panel.width", 232, 190, 380);
    return React.createElement(PanelResize, { label: "Resize review panel", width, onResize: setWidth, min: 190, max: 380, reset: 232, reverse });
  }
  let renderer;
  const captures = new Set();
  const target = {
    setPointerCapture: id => captures.add(id),
    hasPointerCapture: id => captures.has(id),
    releasePointerCapture: id => captures.delete(id),
  };
  const pointer = (clientX, button = 0) => ({ clientX, button, pointerId: 4, currentTarget: target, preventDefault() {} });
  const separator = () => renderer.root.findByProps({ role: "separator" });
  const width = () => separator().props["aria-valuenow"];
  const keyboard = key => act(async () => separator().props.onKeyDown({ key, preventDefault() {} }));
  try {
    await act(async () => { renderer = create(React.createElement(ResizablePanel)); });
    assert.equal(width(), 250, "panel restores its saved width");
    await keyboard("ArrowRight");
    assert.equal(width(), 266);
    await keyboard("End");
    await keyboard("ArrowRight");
    assert.equal(width(), 380, "keyboard resizing stays within its maximum");
    await keyboard("Home");
    await keyboard("ArrowLeft");
    assert.equal(width(), 190, "keyboard resizing stays within its minimum");
    await act(async () => separator().props.onDoubleClick());
    assert.equal(width(), 232);

    await act(async () => separator().props.onPointerDown(pointer(100)));
    assert.ok(captures.has(4), "resize owns pointer while dragging outside its narrow handle");
    await act(async () => separator().props.onPointerMove(pointer(158)));
    assert.equal(width(), 290);
    await act(async () => separator().props.onPointerUp(pointer(158)));
    assert.ok(!captures.has(4));
    await act(async () => separator().props.onPointerMove(pointer(200)));
    assert.equal(width(), 290, "movement after release does not resize");
    assert.equal(stored.get("review.panel.width"), "290");

    await act(async () => { renderer.unmount(); renderer = create(React.createElement(ResizablePanel, { reverse: true })); });
    assert.equal(width(), 290, "width survives unmount and reopening");
    await keyboard("ArrowLeft");
    assert.equal(width(), 306, "left edge of a right-hand panel expands toward the left");
    await act(async () => separator().props.onPointerDown(pointer(200)));
    await act(async () => separator().props.onPointerMove(pointer(180)));
    assert.equal(width(), 326);
    await act(async () => separator().props.onLostPointerCapture());
    await act(async () => separator().props.onPointerMove(pointer(140)));
    assert.equal(width(), 326, "losing capture cancels the drag");
    await act(async () => separator().props.onPointerDown(pointer(200, 2)));
    await act(async () => separator().props.onPointerMove(pointer(160)));
    assert.equal(width(), 326, "secondary pointer buttons do not begin resizing");
  } finally {
    if (renderer) await act(async () => renderer.unmount());
    globalThis.window = savedWindow;
  }
}

async function checkComposerUploadStaleGuard(ComposerAttachments) {
  const originalFetch = globalThis.fetch;
  const uploads = new Map();
  const uploadRequests = [];
  globalThis.fetch = async (url, init) => {
    assert.match(String(url), /\/v1\/assets\/uploads$/);
    const body = JSON.parse(String(init.body));
    uploadRequests.push(body);
    const deferred = createDeferred();
    uploads.set(body.session_id, { body, deferred });
    return deferred.promise;
  };

  try {
    const attachments = [];
    let renderer;
    await act(async () => {
      renderer = create(React.createElement(ComposerAttachments, {
        sessionId: "chat_old",
        onAttachmentsChanged: (next) => attachments.push(next.map((item) => item.id)),
      }));
    });

    await act(async () => {
      input(renderer, "file").props.onChange({ target: { files: [
        new File(["old"], "old.txt", { type: "text/plain" }),
        new File(["old second"], "old-second.txt", { type: "text/plain" }),
      ] }, currentTarget: { value: "" } });
      await tick();
    });
    assert.equal(uploads.get("chat_old").body.content_base64, "b2xk");

    await act(async () => {
      renderer.update(React.createElement(ComposerAttachments, {
        sessionId: "chat_new",
        onAttachmentsChanged: (next) => attachments.push(next.map((item) => item.id)),
      }));
    });
    await act(async () => {
      input(renderer, "file").props.onChange({ target: { files: [new File(["new"], "new.ts", { type: "text/plain" })] }, currentTarget: { value: "" } });
      await tick();
    });

    uploads.get("chat_old").deferred.resolve(jsonResponse(asset("asset_old", "old.txt", "chat_old")));
    await act(async () => {
      await tick();
    });
    assert.ok(!textOf(renderer.root).includes("old.txt"), "stale upload response from previous session must not stage an attachment");
    assert.ok(!textOf(renderer.root).includes("old-second.txt"), "remaining files from an obsolete selection must not appear in the current conversation");
    assert.equal(uploadRequests.filter(item => item.session_id === "chat_old").length, 1, "navigation cancels undispatched files from the old selection");

    uploads.get("chat_new").deferred.resolve(jsonResponse(asset("asset_new", "new.ts", "chat_new")));
    await act(async () => {
      await tick();
    });
    assert.ok(textOf(renderer.root).includes("new.ts"), "current upload should show its filename");
    assert.deepEqual(attachments.at(-1), ["asset_new"]);

    await act(async () => {
      button(renderer, "Remove from draft").props.onClick();
    });
    assert.deepEqual(attachments.at(-1), [], "removing staged attachment should only update parent draft attachments");
  } finally {
    globalThis.fetch = originalFetch;
  }
}

async function checkDropWaitsForSavedAttachments(ComposerAttachments) {
  const originalFetch = globalThis.fetch;
  const restored = createDeferred();
  const savedAsset = asset("asset_saved", "saved.txt", "chat_restore");
  const addedAsset = asset("asset_added", "added.txt", "chat_restore");
  const incomingDrop = { id: "drop_restore", sessionId: "chat_restore", files: [new File(["added"], "added.txt", { type: "text/plain" })] };
  const uploads = [];
  const changes = [];
  let renderer;
  function ComposerHost() {
    const [ids, setIds] = React.useState([savedAsset.id]);
    return React.createElement(ComposerAttachments, {
      sessionId: "chat_restore", attachmentIds: ids, incomingDrop,
      onAttachmentsChanged: next => { const nextIds = next.map(item => item.id); changes.push(nextIds); setIds(nextIds); },
    });
  }
  globalThis.fetch = async (url, init) => {
    if (String(url).includes("/uploads")) {
      uploads.push(JSON.parse(String(init.body)));
      return jsonResponse(addedAsset);
    }
    return restored.promise.then(() => jsonResponse([savedAsset]));
  };
  try {
    await act(async () => { renderer = create(React.createElement(React.StrictMode, null, React.createElement(ComposerHost))); await tick(); });
    assert.equal(uploads.length, 0, "a drop on the first render waits until existing draft attachments are restored");
    assert.equal(changes.length, 0, "pending restoration must not erase the saved draft attachment IDs");
    await act(async () => { restored.resolve(jsonResponse([savedAsset])); await tick(); });
    assert.equal(uploads.length, 1, "StrictMode and restoration deliver a drop only once");
    assert.deepEqual(changes.at(-1), [savedAsset.id, addedAsset.id], "the saved and newly dropped originals remain staged together");
    assert.match(textOf(renderer.root), /saved.txt/);
    assert.match(textOf(renderer.root), /added.txt/);
  } finally {
    restored.resolve(jsonResponse([savedAsset]));
    if (renderer) await act(async () => renderer.unmount());
    globalThis.fetch = originalFetch;
  }
}

async function checkLibraryStalePreviewAndScopedCalls(LibraryPanel) {
  const originalFetch = globalThis.fetch;
  const previewCalls = [];
  const previewDefers = new Map();
  let deleteRequestedIds = null;
  let renderer;
  globalThis.fetch = async (url, init) => {
    const address = String(url);
    if (address.includes("/v1/projects") || address.includes("/v1/chat/conversations")) return jsonResponse([]);
    if (address.includes("/v1/assets/delete-preview")) {
      return jsonResponse({
        requested_asset_ids: ["asset_a", "asset_b"],
        affected_asset_ids: ["asset_a"],
        preserved_asset_ids: ["asset_b"],
        affected_sessions: [],
        retained_sessions: [],
        affected_runs: [],
        retained_runs: [],
        affected_projects: [],
        retained_projects: [],
        affected_branches: [],
        retained_branches: [],
        affected_cases: [],
        retained_cases: ["case_1"],
        note: "Preview only.",
      });
    }
    if (address.includes("/v1/assets/delete")) {
      deleteRequestedIds = JSON.parse(String(init.body)).asset_ids;
      return jsonResponse({
        requested_asset_ids: deleteRequestedIds,
        affected_asset_ids: ["asset_a"],
        preserved_asset_ids: ["asset_b"],
        affected_sessions: [],
        retained_sessions: [],
        affected_runs: [],
        retained_runs: [],
        affected_projects: [],
        retained_projects: [],
        affected_branches: [],
        retained_branches: [],
        affected_cases: [],
        retained_cases: ["case_1"],
        note: "Deleted what was safe.",
      });
    }
    if (address.includes("/v1/assets/asset_a/content")) {
      return jsonResponse({
        id: "asset_a",
        filename: "a.txt",
        content_type: "text/plain",
        encoding: "utf-8",
        text: "full retained text",
        sha256: "sha",
        size_bytes: 18,
        source_status: "changed",
      });
    }
    if (address.includes("/preview")) {
      const id = address.includes("asset_a") ? "asset_a" : "asset_b";
      const deferred = createDeferred();
      previewCalls.push({ id, address });
      previewDefers.set(id, deferred);
      return deferred.promise;
    }
    if (address.includes("/v1/assets")) {
      return jsonResponse([
        asset("asset_a", "a.txt", "source_session", { source_status: "changed" }),
        asset("asset_b", "b.txt", "other_session", { project_path: "D:\\Project", source_status: "unchanged" }),
      ]);
    }
    throw new Error(`unexpected fetch ${address}`);
  };

  try {
    await act(async () => {
      renderer = create(React.createElement(LibraryPanel));
      await tick();
    });
    await act(async () => {
      await tick();
    });

    assert.equal(renderer.root.findAllByType("button").filter(node => textOf(node).includes("Use in Chat")).length, 0, "Library has no Chat handoff");

    await act(async () => {
      renderer.root.findByProps({ "aria-label": "Preview a.txt" }).props.onClick();
      await tick();
    });
    assert.ok(previewCalls.at(-1).address.includes("session_id=source_session"), "preview should use selected asset source session scope");

    await act(async () => {
      renderer.root.findByProps({ "aria-label": "Preview b.txt" }).props.onClick();
      await tick();
    });
    assert.ok(previewCalls.at(-1).address.includes("session_id=other_session"), "all-retained preview should not omit access scope");

    previewDefers.get("asset_b").resolve(jsonResponse({
      id: "asset_b",
      filename: "b.txt",
      content_type: "text/plain",
      size_bytes: 6,
      sha256: "sha",
      preview: "second",
      truncated: false,
      source_status: "unchanged",
    }));
    await act(async () => {
      await tick();
    });
    previewDefers.get("asset_a").resolve(jsonResponse({
      id: "asset_a",
      filename: "a.txt",
      content_type: "text/plain",
      size_bytes: 5,
      sha256: "sha",
      preview: "first",
      truncated: false,
      source_status: "changed",
    }));
    await act(async () => {
      await tick();
    });
    assert.ok(textOf(renderer.root).includes("second"), "latest preview should stay visible");
    assert.equal(textOf(renderer.root.findByProps({ className: "file-preview-content" })), "second", "stale preview response should be ignored");

    await act(async () => { renderer.root.findByProps({ "aria-label": "Preview a.txt" }).props.onClick(); await tick(); });
    previewDefers.get("asset_a").resolve(jsonResponse({ id: "asset_a", filename: "a.txt", content_type: "text/plain", size_bytes: 5, sha256: "sha", preview: "first", truncated: false, source_status: "changed" }));
    await act(async () => { await tick(); });

    await act(async () => {
      button(renderer, "Open full text").props.onClick();
      await tick();
    });
    assert.ok(textOf(renderer.root).includes("full retained text"));
    assert.ok(textOf(renderer.root).includes("Source changed; retained copy preserved"));

    await act(async () => {
      renderer.root.findByProps({ "aria-label": "Select a.txt" }).props.onChange({ target: { checked: true } });
      renderer.root.findByProps({ "aria-label": "Select b.txt" }).props.onChange({ target: { checked: true } });
    });
    await act(async () => {
      exactButton(renderer, "Delete").props.onClick();
      await tick();
    });
    await act(async () => {
      button(renderer, "Delete saved files").props.onClick();
      await tick();
    });
    assert.deepEqual(deleteRequestedIds, ["asset_a"], "delete confirmation must request only deletable affected ids");
    assert.equal(renderer.root.findAllByProps({ "aria-label": "Review file deletion" }).length, 0, "the deletion review closes after the saved files are deleted");
    assert.ok(textOf(renderer.root).includes("1 shared item preserved"));
    assert.ok(!textOf(renderer.root).includes("full retained text"), "deleting the previewed retained asset must clear its content immediately");
  } finally {
    if (renderer) await act(async () => renderer.unmount());
    globalThis.fetch = originalFetch;
  }
}

function transcriptElement(tag, props = {}, children = []) {
  const childNodes = children.map((child) => typeof child === "string" ? transcriptText(child) : child);
  const elements = childNodes.filter((child) => child.nodeType === 1);
  const node = {
    nodeType: 1,
    tag,
    attrs: props,
    children: elements,
    childNodes,
    get textContent() {
      return childNodes.map((child) => child.textContent).join("");
    },
    getAttribute(name) { return Object.hasOwn(props, name) ? props[name] : null; },
    classList: { contains: (name) => String(props.class ?? "").split(/\s+/).includes(name) },
    matches(selector) { return selector.split(",").some((part) => transcriptMatches(node, part.trim())); },
    querySelector(selector) { return transcriptQuery(node, selector)[0] ?? null; },
    querySelectorAll(selector) { return transcriptQuery(node, selector); },
  };
  return node;
}

function transcriptText(value) {
  return { nodeType: 3, textContent: value, children: [], childNodes: [] };
}

function transcriptMatches(node, selector) {
  if (selector.startsWith(".")) return node.classList.contains(selector.slice(1));
  const tag = selector.split("[")[0];
  if (tag && node.tag !== tag) return false;
  const attr = selector.match(/\[([^=]+)="([^"]+)"\]/);
  return attr ? node.getAttribute(attr[1]) === attr[2] : true;
}

function transcriptQuery(node, selector) {
  let current = [node];
  for (const part of selector.split(/\s+/)) {
    const next = [];
    for (const parent of current) transcriptCollect(parent, part, next);
    current = next;
  }
  return current;
}

function transcriptCollect(node, part, into) {
  for (const child of node.children ?? []) {
    if (typeof child === "string" || child.nodeType !== 1) continue;
    if (transcriptMatches(child, part)) into.push(child);
    transcriptCollect(child, part, into);
  }
}

function paintedTranscript() {
  return transcriptElement("div", { class: "transcript" }, [
    transcriptElement("article", { class: "bubble bubble-user" }, [
      transcriptElement("p", { class: "user-message-text" }, ["Do work"]),
    ]),
    transcriptElement("article", { class: "bubble bubble-assistant", "data-markdown-source": "**Done**" }, [
      transcriptElement("p", {}, ["Done"]),
      transcriptElement("details", { class: "activity-group" }, [
        transcriptElement("summary", {}, [transcriptElement("span", {}, ["Read 3 files"])]),
        transcriptElement("span", { class: "activity-line" }, ["Read notes.txt"]),
        transcriptElement("span", { class: "activity-line" }, ["Read plan.md failed"]),
      ]),
      transcriptElement("button", { class: "helper-delegation" }, [
        transcriptElement("span", { class: "helper-delegation-head" }, [
          transcriptElement("strong", {}, ["Researcher"]),
          transcriptElement("span", {}, ["Done"]),
        ]),
        transcriptElement("span", { class: "helper-delegation-request" }, ["Find the note"]),
      ]),
      transcriptElement("ol", { "aria-label": "Todo list" }, [
        transcriptElement("li", {}, [
          transcriptElement("span", { class: "todo-status" }, ["✓"]),
          transcriptText(" Check the file"),
        ]),
      ]),
      transcriptElement("div", { class: "tool-call-row" }, [
        transcriptElement("details", { class: "message-tools" }, [
          transcriptElement("summary", {}, [
            transcriptElement("span", { class: "activity-line" }, ["Checked the vault"]),
          ]),
          transcriptElement("div", { class: "tool-call-details" }, [
            transcriptElement("section", { "aria-label": "Tool output" }, [
              transcriptText("UNIQUE-TOOL-OUTPUT-should-not-export"),
            ]),
            transcriptElement("details", { class: "tool-raw-arguments" }, [
              transcriptElement("section", { "aria-label": "Raw tool arguments" }, [
                transcriptText("UNIQUE-RAW-ARGS-should-not-export"),
              ]),
            ]),
          ]),
        ]),
      ]),
      transcriptElement("div", { class: "message-reasoning" }, [transcriptElement("p", {}, ["secret thought"])]),
    ]),
    transcriptElement("div", { class: "tool-message" }, [
      transcriptElement("span", { class: "activity-line" }, ["Waiting: echo"]),
    ]),
    transcriptElement("section", { class: "chat-retained-files" }, [
      transcriptElement("button", { class: "retained-file-name" }, [
        transcriptElement("span", {}, ["notes.txt"]),
        transcriptElement("small", {}, ["12 B"]),
      ]),
    ]),
  ]);
}

async function checkChatHistoryActions(ChatHistoryActions, AnswerActions) {
  const originalFetch = globalThis.fetch;
  const originalConfirm = globalThis.window.confirm;
  const originalDocument = globalThis.document;
  const originalCreateObjectUrl = globalThis.URL?.createObjectURL;
  const originalRevokeObjectUrl = globalThis.URL?.revokeObjectURL;
  const deleted = [];
  const errors = [];
  const downloads = [];
  let deleteBody = null;
  let confirmCalls = 0;
  const transcript = paintedTranscript();
  globalThis.window.confirm = () => {
    confirmCalls += 1;
    return true;
  };
  globalThis.URL.createObjectURL = (blob) => {
    downloads.push({ blob, filename: null });
    return `blob:download-${downloads.length}`;
  };
  globalThis.URL.revokeObjectURL = () => {};
  globalThis.document = {
    body: { appendChild() {} },
    querySelector: (selector) => transcriptMatches(transcript, selector) ? transcript : transcript.querySelector(selector),
    createElement: () => ({
      href: "",
      download: "",
      click() { downloads.at(-1).filename = this.download; },
      remove() {},
    }),
  };
  globalThis.fetch = async (url, init = {}) => {
    const address = String(url);
    if (address.includes("/delete-preview")) return jsonResponse(deletePreviewFixture());
    if (init.method === "DELETE" && address.includes("/v1/chat/conversations/chat_source")) {
      deleteBody = JSON.parse(String(init.body));
      return jsonResponse({ ...deletePreviewFixture(), diagnostics_deleted: Boolean(deleteBody.include_diagnostics) });
    }
    throw new Error(`unexpected fetch ${address}`);
  };

  try {
    let renderer;
    const mount = (conversation) => React.createElement(ChatHistoryActions, {
      conversation,
      onDeleted: (id) => deleted.push(id),
      onError: (message) => errors.push(message),
    });
    await act(async () => {
      renderer = create(mount({ ...conversationFixture(), current_run: { id: "run_done", status: "running" } }));
      await tick();
    });
    assert.equal(button(renderer, "Download transcript").props.disabled, undefined, "a running turn still downloads a transcript");
    assert.equal(textOf(renderer.root).includes("Regenerate"), false);
    assert.equal(textOf(renderer.root).includes("Branch"), false);
    assert.equal(textOf(renderer.root).includes("JSON"), false);
    let answers;
    await act(async () => {
      answers = create(React.createElement(AnswerActions, { answerText: "Done" }));
      await tick();
    });
    assert.ok(answers.root.findByProps({ "aria-label": "Copy answer" }));
    assert.equal(answers.root.findAll((node) => node.type === "button" && /Regenerate|Branch/.test(textOf(node))).length, 0);
    await act(async () => { answers.unmount(); });

    await act(async () => {
      button(renderer, "Download transcript").props.onClick();
      await tick();
    });
    assert.equal(downloads.at(-1).filename, "Source-chat.md");
    const transcriptTextBody = await downloads.at(-1).blob.text();
    assert.match(transcriptTextBody, /# Source chat\n\nExported: .+\nArea: Project\n\nThis file is a transcript\. It is not a restore\.\n\n## You\n\nDo work\n\n## Assistant\n\n\*\*Done\*\*\n\nRead notes\.txt\nRead plan\.md failed\nResearcher Done Find the note\n✓ Check the file\nChecked the vault\nWaiting: echo\n\n## Retained files\n\n- notes\.txt\n/);
    assert.equal(transcriptTextBody.includes("Read 3 files"), false);
    assert.equal(transcriptTextBody.includes("secret thought"), false);
    assert.equal(transcriptTextBody.includes("UNIQUE-TOOL-OUTPUT-should-not-export"), false);
    assert.equal(transcriptTextBody.includes("UNIQUE-RAW-ARGS-should-not-export"), false);
    assert.equal(transcriptTextBody.includes("Checked the vault"), true);
    assert.equal(transcriptTextBody.includes("12 B"), false);

    await act(async () => {
      renderer.update(mount({ ...conversationFixture(), title: "Café notes", display_title: null }));
      await tick();
    });
    await act(async () => {
      button(renderer, "Download transcript").props.onClick();
      await tick();
    });
    assert.equal(downloads.at(-1).filename, "Caf-notes.md");
    await act(async () => {
      renderer.update(mount({ ...conversationFixture(), title: "", display_title: null }));
      await tick();
    });
    await act(async () => {
      button(renderer, "Download transcript").props.onClick();
      await tick();
    });
    assert.equal(downloads.at(-1).filename, "New-conversation.md");

    await act(async () => {
      renderer.update(mount(conversationFixture()));
      button(renderer, "Delete").props.onClick();
      await tick();
    });
    const dialog = textOf(renderer.root);
    assert.ok(dialog.includes("This permanently removes this chat and its history. Project files and model files stay."));
    assert.ok(dialog.includes("History shared with another chat is kept for that chat."));
    assert.equal(dialog.includes("backup"), false);
    assert.equal(dialog.includes(deletePreviewFixture().note), false);
    assert.equal(button(renderer, "Delete chat").props.disabled, false);
    await act(async () => {
      button(renderer, "Delete chat").props.onClick();
      await tick();
    });
    assert.deepEqual(deleteBody, { execute: true, include_diagnostics: true });
    assert.deepEqual(deleted, ["chat_source"]);
    assert.equal(confirmCalls, 0);
    assert.deepEqual(errors, []);
  } finally {
    globalThis.fetch = originalFetch;
    globalThis.window.confirm = originalConfirm;
    globalThis.document = originalDocument;
    globalThis.URL.createObjectURL = originalCreateObjectUrl;
    globalThis.URL.revokeObjectURL = originalRevokeObjectUrl;
  }
}

function conversationFixture() {
  return {
    id: "chat_source",
    title: "Source chat",
    archived: false,
    archived_at: null,
    area_kind: "project",
    area_id: "D:/Project",
    area_label: "Project",
    area_project_path: "D:/Project",
    area_workspace_id: null,
    deployment_id: "deploy_1",
    profile_id: null,
    inherit_deployment_settings: true,
    project_path: "D:/Project",
    workspace_id: null,
    thread_id: "thread_1",
    transcript: [
      { id: "msg_user", role: "user", content: "Do work", at: "2026-09-21T00:00:00Z", run_id: "run_done" },
      { id: "msg_assistant", role: "assistant", content: "Done", at: "2026-09-21T00:01:00Z", run_id: "run_done" },
    ],
    current_run_id: null,
    run_ids: ["run_done"],
    history_replaced: false,
    harness: "deepagents",
    second_agent_loop: false,
    source_surface: "chat",
    current_run: null,
    pending_cancel_input_ids: [],
    draft: null,
    queue: [],
    events: [],
    continuity: null,
    deploy_health: null,
    filesystem_tools_available: true,
    shell_tools_available: true,
    enabled_tools: [],
    created_at: "2026-09-21T00:00:00Z",
    updated_at: "2026-09-21T00:01:00Z",
  };
}

function deletePreviewFixture() {
  return {
    conversation_id: "chat_source",
    can_delete: true,
    blockers: [],
    affected_sessions: ["chat_source"],
    retained_sessions: ["chat_other"],
    affected_runs: ["run_done"],
    retained_runs: [],
    affected_assets: ["asset_a"],
    retained_assets: ["asset_b"],
    checkpoint_threads_deleted: ["thread_1"],
    checkpoint_threads_retained: [],
    scratch_deleted: [],
    diagnostics_deleted: false,
    project_sources_deleted: false,
    model_files_deleted: false,
    note: "Conversation deletion removes only application-owned records. Project files and model files are retained.",
  };
}

function asset(id, filename, sessionId, overrides = {}) {
  return {
    id,
    origin: "upload",
    scope: "session",
    session_id: sessionId,
    project_path: null,
    access_scope: `session:${sessionId}`,
    storage: "application.sqlite",
    filename,
    content_type: "text/plain",
    content_kind: "text",
    encoding: "utf-8",
    size_bytes: filename.length,
    sha256: "sha",
    observed_at: "2026-09-21T00:00:00Z",
    source_run_id: null,
    source_tool_call_id: null,
    source_tool_name: null,
    mutable_reference: null,
    observation: null,
    deleted_at: null,
    ...overrides,
  };
}

function jsonResponse(body, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function createDeferred() {
  let resolve;
  let reject;
  const promise = new Promise((innerResolve, innerReject) => {
    resolve = innerResolve;
    reject = innerReject;
  });
  return { promise, resolve, reject };
}

async function tick() {
  await Promise.resolve();
  await Promise.resolve();
}

function input(renderer, type) {
  const found = renderer.root.findAll((node) => node.type === "input" && node.props.type === type);
  assert.ok(found.length > 0, `expected input ${type}`);
  return found[0];
}

function button(renderer, label) {
  const found = renderer.root.findAll((node) => node.type === "button" && textOf(node).includes(label));
  assert.ok(found.length > 0, `expected button ${label}`);
  return found[0];
}

function exactButton(renderer, label) {
  const found = renderer.root.findAll((node) => node.type === "button" && textOf(node).trim() === label);
  assert.equal(found.length, 1, `expected one button labelled ${label}`);
  return found[0];
}

function textOf(value) {
  if (value == null || typeof value === "boolean") {
    return "";
  }
  if (typeof value === "string" || typeof value === "number") {
    return String(value);
  }
  if (Array.isArray(value)) {
    return value.map(textOf).join("");
  }
  if (value.children) {
    return textOf(value.children);
  }
  return "";
}
