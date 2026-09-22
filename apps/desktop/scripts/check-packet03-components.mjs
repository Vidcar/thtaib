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
  const { PanelResize, usePanelWidth } = await vite.ssrLoadModule("/src/renderer/PanelResize.tsx");
  const { HoverHelp } = await vite.ssrLoadModule("/src/renderer/HoverHelp.tsx");
  const { AttentionPanel } = await vite.ssrLoadModule("/src/renderer/AttentionPanel.tsx");

  await checkComposerUploadStaleGuard(ComposerAttachments);
  await checkDropWaitsForSavedAttachments(ComposerAttachments);
  await checkLibraryStalePreviewAndScopedCalls(LibraryPanel);
  await checkChatHistoryActions(ChatHistoryActions);
  await checkPanelResize(PanelResize, usePanelWidth);
  await checkHoverHelp(HoverHelp);
  await checkAttentionTargets(AttentionPanel);
} finally {
  await vite.close();
}

console.log("Packet03 component checks passed.");

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
    await act(async () => { for (const target of buttons) target.props.onClick(); });
    assert.deepEqual(opened, items, "Attention preserves the exact conversation or task target rather than dropping non-Chat identity");
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
  globalThis.fetch = async (url, init) => {
    const address = String(url);
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
    let renderer;
    await act(async () => {
      renderer = create(React.createElement(LibraryPanel, { sessionId: "current_session", projectPath: null }));
      await tick();
    });
    await act(async () => {
      await tick();
    });

    assert.ok(button(renderer, "Reuse selected").props.disabled, "reuse must be disabled without a destination callback");

    await act(async () => {
      button(renderer, "Preview").props.onClick();
      await tick();
    });
    assert.ok(previewCalls.at(-1).address.includes("session_id=source_session"), "preview should use selected asset source session scope");

    const previewButtons = renderer.root.findAll((node) => node.type === "button" && textOf(node).includes("Preview"));
    await act(async () => {
      previewButtons[1].props.onClick();
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
    assert.ok(!textOf(renderer.root).includes("first"), "stale preview response should be ignored");

    await act(async () => {
      button(renderer, "Open full text").props.onClick();
      await tick();
    });
    assert.ok(textOf(renderer.root).includes("full retained text"));
    assert.ok(textOf(renderer.root).includes("Source changed; showing retained copy"));

    const checkboxes = renderer.root.findAll((node) => node.type === "input" && node.props.type === "checkbox");
    await act(async () => {
      checkboxes[0].props.onChange({ target: { checked: true } });
      checkboxes[1].props.onChange({ target: { checked: true } });
    });
    await act(async () => {
      button(renderer, "Preview delete").props.onClick();
      await tick();
    });
    await act(async () => {
      button(renderer, "Delete affected retained copies").props.onClick();
      await tick();
    });
    assert.deepEqual(deleteRequestedIds, ["asset_a"], "delete confirmation must request only deletable affected ids");
    assert.ok(textOf(renderer.root).includes("1 shared item preserved"));
    assert.ok(!textOf(renderer.root).includes("full retained text"), "deleting the previewed retained asset must clear its content immediately");
  } finally {
    globalThis.fetch = originalFetch;
  }
}

async function checkChatHistoryActions(ChatHistoryActions) {
  const originalFetch = globalThis.fetch;
  const originalConfirm = globalThis.window.confirm;
  const originalDocument = globalThis.document;
  const originalCreateObjectUrl = globalThis.URL?.createObjectURL;
  const originalRevokeObjectUrl = globalThis.URL?.revokeObjectURL;
  const created = [];
  const deleted = [];
  const errors = [];
  const branchRequests = [];
  const downloads = [];
  let turnCompleted = false;
  let deleteBody = null;
  let confirmCalls = 0;
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
    body: { appendChild: () => {} },
    createElement: () => ({
      href: "",
      download: "",
      click() {
        downloads.at(-1).filename = this.download;
      },
      remove() {},
    }),
  };
  globalThis.fetch = async (url, init = {}) => {
    const address = String(url);
    if (address.includes("/replies/run_done/actions")) {
      return jsonResponse({
        branch_available: turnCompleted,
        retry_available: turnCompleted,
        regenerate_available: false,
        branch_reason: turnCompleted ? null : "Wait for the active turn to stop before branching.",
        retry_reason: turnCompleted ? null : "Wait for the active turn to stop before branching.",
        regenerate_reason: "This turn has no matching retained project snapshot.",
      });
    }
    if (address.includes("/branches")) {
      branchRequests.push(JSON.parse(String(init.body)));
      return jsonResponse({ ...conversationFixture(), id: "chat_branch", source_conversation_id: "chat_source" });
    }
    if (address.includes("/export")) {
      return jsonResponse({
        schema_version: 1,
        exported_at: "2026-09-21T00:02:00Z",
        conversation: conversationFixture(),
        runs: [{ id: "run_done", task: "Do work" }],
        retained_assets: [{ filename: "notes.txt" }],
        note: "Readable export only.",
      });
    }
    if (address.includes("/delete-preview")) {
      return jsonResponse(deletePreviewFixture());
    }
    if (init.method === "DELETE" && address.includes("/v1/chat/conversations/chat_source")) {
      deleteBody = JSON.parse(String(init.body));
      return jsonResponse({ ...deletePreviewFixture(), diagnostics_deleted: Boolean(deleteBody.include_diagnostics) });
    }
    throw new Error(`unexpected fetch ${address}`);
  };

  try {
    let renderer;
    await act(async () => {
      renderer = create(React.createElement(ChatHistoryActions, {
        conversation: { ...conversationFixture(), current_run: { ...conversationFixture().current_run, status: "running" } },
        onConversationCreated: (next) => created.push(next.id),
        onDeleted: (id) => deleted.push(id),
        onError: (message) => errors.push(message),
      }));
      await tick();
    });
    await act(async () => {
      await tick();
    });

    assert.equal(button(renderer, "Retry task").props.disabled, true, "running turn cannot be retried");
    turnCompleted = true;
    await act(async () => {
      renderer.update(React.createElement(ChatHistoryActions, {
        conversation: { ...conversationFixture(), current_run: { ...conversationFixture().current_run, status: "completed" } },
        onConversationCreated: (next) => created.push(next.id),
        onDeleted: (id) => deleted.push(id),
        onError: (message) => errors.push(message),
      }));
      await tick();
    });
    assert.equal(button(renderer, "Retry task").props.disabled, false, "terminal hydration refreshes saved reply availability without reopening Chat");

    assert.ok(textOf(renderer.root).includes("Regenerate answer"));
    assert.ok(textOf(renderer.root).includes("This turn has no matching retained project snapshot."), "unavailable regenerate reason should be visible");

    await act(async () => {
      button(renderer, "Retry task").props.onClick();
      await tick();
    });
    assert.equal(confirmCalls, 1, "retry must disclose repeated effects before creating a branch");
    assert.deepEqual(branchRequests.at(-1), {
      source_run_id: "run_done",
      mode: "retry",
      acknowledge_repeated_effects: true,
    });
    assert.deepEqual(created, ["chat_branch"]);

    const editBox = renderer.root.findByType("textarea");
    await act(async () => {
      editBox.props.onChange({ target: { value: "Do the safer edited task" } });
    });
    await act(async () => {
      button(renderer, "Edit task branch").props.onClick();
      await tick();
    });
    assert.deepEqual(branchRequests.at(-1), {
      source_run_id: "run_done",
      mode: "edit",
      acknowledge_repeated_effects: true,
      edited_task: "Do the safer edited task",
    });

    await act(async () => {
      button(renderer, "Readable export").props.onClick();
      await tick();
    });
    assert.equal(downloads.at(-1).filename, "Source-chat.md");
    assert.match(await downloads.at(-1).blob.text(), /# Source chat[\s\S]*## You[\s\S]*Do work[\s\S]*## Assistant[\s\S]*Done/);

    await act(async () => {
      button(renderer, "Advanced JSON export").props.onClick();
      await tick();
    });
    assert.equal(downloads.at(-1).filename, "Source-chat-structured.json");
    assert.match(await downloads.at(-1).blob.text(), /"schema_version": 1/);

    await act(async () => {
      button(renderer, "Preview delete").props.onClick();
      await tick();
    });
    assert.ok(textOf(renderer.root).includes("1 retained asset"));
    assert.ok(textOf(renderer.root).includes("Project files and model files are retained."));

    assert.equal(renderer.root.findAll((node) => node.type === "input" && node.props.type === "checkbox").length, 0, "chat deletion always removes owned diagnostics without an optional partial-deletion toggle");
    await act(async () => {
      button(renderer, "Delete conversation").props.onClick();
      await tick();
    });
    assert.deepEqual(deleteBody, { execute: true, include_diagnostics: true });
    assert.deepEqual(deleted, ["chat_source"]);
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
