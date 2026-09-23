import assert from "node:assert/strict";
import path from "node:path";
import { fileURLToPath } from "node:url";

import React from "react";
import { act, create } from "react-test-renderer";
import { createServer as createViteServer } from "vite";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../..");
const desktopRoot = path.join(repoRoot, "apps/desktop");
const vite = await createViteServer({ root: desktopRoot, appType: "custom", server: { middlewareMode: true, hmr: false }, logLevel: "error" });

async function checkSaveAndKeyboard(ConversationRename) {
  const saved = [];
  let cancelled = 0;
  let renderer;
  await act(async () => {
    renderer = create(React.createElement(ConversationRename, {
      conversation,
      currentTitle: "Old title",
      onRename: async (title, item) => saved.push({ title, id: item.id }),
      onCancel: () => { cancelled += 1; },
    }));
  });

  const input = renderer.root.findByType("input");
  assert.equal(input.props.value, "Old title");
  await act(async () => {
    input.props.onChange({ target: { value: "  New title  " } });
  });
  await act(async () => {
    renderer.root.findByType("form").props.onSubmit({ preventDefault() {} });
  });
  assert.deepEqual(saved, [{ title: "New title", id: "chat_rename" }], "submit should trim and save the entered title");

  await act(async () => {
    renderer.root.findByType("form").props.onKeyDown({ key: "Escape", preventDefault() {} });
  });
  assert.equal(cancelled, 1, "Escape should cancel the inline editor");
}

async function checkValidationAndErrorState(ConversationRename) {
  const saved = [];
  let failNext = true;
  let renderer;
  await act(async () => {
    renderer = create(React.createElement(ConversationRename, {
      conversation,
      currentTitle: "Stable title",
      onRename: async (title) => {
        saved.push(title);
        if (failNext) {
          failNext = false;
          throw new Error("Name could not be saved.");
        }
      },
      onCancel: () => {},
    }));
  });

  const input = () => renderer.root.findByType("input");
  const save = () => button(renderer, "Save");
  assert.equal(save().props.disabled, false);

  await act(async () => {
    input().props.onChange({ target: { value: "   " } });
  });
  assert.equal(save().props.disabled, true, "blank names should not be submittable");
  await act(async () => {
    renderer.root.findByType("form").props.onSubmit({ preventDefault() {} });
  });
  assert.ok(textOf(renderer.root).includes("Enter a conversation name."), "blank submit should show an accessible validation error");
  assert.deepEqual(saved, [], "blank submit must not call onRename");

  const longTitle = "x".repeat(201);
  await act(async () => {
    input().props.onChange({ target: { value: longTitle } });
  });
  assert.equal(save().props.disabled, true, "overlong names should not be submittable");
  await act(async () => {
    renderer.root.findByType("form").props.onSubmit({ preventDefault() {} });
  });
  assert.ok(textOf(renderer.root).includes("200 characters or fewer"), "overlong submit should explain the limit");

  await act(async () => {
    input().props.onChange({ target: { value: "Keep this after failure" } });
  });
  await act(async () => {
    renderer.root.findByType("form").props.onSubmit({ preventDefault() {} });
    await tick();
  });
  assert.ok(textOf(renderer.root).includes("Name could not be saved."), "rename failure should be shown inline");
  assert.equal(input().props.value, "Keep this after failure", "failed save should preserve the edited text");
  assert.deepEqual(saved, ["Keep this after failure"]);
}

function button(renderer, text) {
  const found = renderer.root.findAll((node) => node.type === "button" && textOf(node).includes(text))[0];
  assert.ok(found, `button ${text} should render`);
  return found;
}

function textOf(node) {
  if (typeof node === "string") return node;
  return (node.children ?? []).map((child) => typeof child === "string" ? child : textOf(child)).join("");
}

function tick() {
  return new Promise((resolve) => setTimeout(resolve, 0));
}

const conversation = {
  id: "chat_rename",
  title: "Old title",
  deployment_id: "dep_1",
  profile_id: null,
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
  queue: [],
  events: [],
  created_at: "2026-09-22T00:00:00Z",
  updated_at: "2026-09-22T00:00:00Z",
};

try {
  const { conversationTitle } = await vite.ssrLoadModule("/src/renderer/display.ts");
  const derived = "this is a stream test, please write out 150 lines wit…";
  const legacySummary = { ...conversation, title: null, display_title: derived, transcript: [] };
  const legacyFull = { ...legacySummary, transcript: [{ role: "user", content: "A competing transcript-derived title" }] };
  assert.equal(conversationTitle(legacySummary), derived, "The sidebar uses the server's title even without its transcript.");
  assert.equal(conversationTitle(legacyFull), derived, "The header uses the same authoritative title as the sidebar.");
  const { ConversationRename } = await vite.ssrLoadModule("/src/renderer/ConversationRename.tsx");
  await checkSaveAndKeyboard(ConversationRename);
  await checkValidationAndErrorState(ConversationRename);
} finally {
  await vite.close();
}

console.log("ConversationRename inline editor checks passed.");
