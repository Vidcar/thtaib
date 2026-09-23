import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import React from "react";
import { AIMessage, ToolMessage } from "@langchain/core/messages";
import { renderToStaticMarkup } from "react-dom/server";
import { act, create } from "react-test-renderer";
import { createServer as createViteServer } from "vite";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const desktopRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const css = readFileSync(path.join(desktopRoot, "src/renderer/surfacePolish.css"), "utf8");
const dockSource = readFileSync(path.join(desktopRoot, "src/renderer/ChatDock.tsx"), "utf8");
const monacoSource = readFileSync(path.join(desktopRoot, "src/renderer/monacoSetup.ts"), "utf8");

assert.match(css, /grid-template-columns:\s*minmax\(var\(--chat-workspace-files-open-grid-template-columns\), 1fr\) minmax\(var\(--chat-workspace-files-open-grid-template-columns-2\), var\(--inspector-width/, "opening the dock keeps a readable conversation column");
assert.doesNotMatch(css, /files-expanded[\s\S]*display:\s*none/, "widening the dock does not hide the conversation");
assert.match(css, /grid-area: 1 \/ 2 \/ 3 \/ 3/, "the rail stays a full-height column beside the transcript and composer");
assert.doesNotMatch(css, /max-width: 1120px/, "a narrower window does not move the rail above the composer");
assert.match(css, /\.chat-rail \.chat-history-actions \{[^}]*position: static/, "conversation actions sit in the rail instead of covering the answer");
assert.match(dockSource, /DiffEditor/, "file differences use Monaco's diff editor");
assert.match(monacoSource, /loader\.config\(\{ monaco \}\)/, "Monaco is loaded from the desktop package");
assert.doesNotMatch(`${dockSource}\n${monacoSource}`, /cdn\.|jsdelivr|unpkg/, "the editor does not request a CDN");

const vite = await createViteServer({ root: desktopRoot, appType: "custom", server: { middlewareMode: true, hmr: false }, logLevel: "error" });
try {
  const { AgentMessageFeed } = await vite.ssrLoadModule("/src/renderer/AgentMessageFeed.tsx");
  const { ChatDockContext } = await vite.ssrLoadModule("/src/renderer/chatDockContext.tsx");
  const opened = [];
  const sends = [];
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async (url, init) => {
    sends.push({ url: String(url), method: init?.method ?? "GET" });
    throw new Error("activity lines must not send a chat message");
  };
  const readCall = { id: "read-1", name: "read_file", args: { file_path: "SKILL.md" } };
  const editCall = { id: "edit-1", name: "edit_file", args: { file_path: "thistest.md" } };
  const firstTodos = { id: "todo-1", name: "write_todos", args: { todos: [{ content: "Start", status: "pending" }] } };
  const secondTodos = { id: "todo-2", name: "write_todos", args: { todos: [{ content: "Replace", status: "completed" }] } };
  const failedTodos = { id: "todo-3", name: "write_todos", args: { todos: [{ content: "Should not replace", status: "pending" }] } };
  const html = renderToStaticMarkup(React.createElement(ChatDockContext.Provider, {
    value: {
      fileChanges: [{ id: "change-1", toolCallId: "edit-1", path: "thistest.md", addedLines: 5, removedLines: 4 }],
      openChange: (id) => opened.push(id),
      openFile: (file) => opened.push(file),
    },
  }, React.createElement(AgentMessageFeed, {
    messages: [
      new AIMessage({ id: "turn", content: "", tool_calls: [readCall, editCall, firstTodos, secondTodos] }),
      new ToolMessage({ tool_call_id: "read-1", name: "read_file", content: "skill", status: "success" }),
      new ToolMessage({ tool_call_id: "edit-1", name: "edit_file", content: "edited", status: "success" }),
      new ToolMessage({ tool_call_id: "todo-1", name: "write_todos", content: "ok", status: "success" }),
      new ToolMessage({ tool_call_id: "todo-2", name: "write_todos", content: "ok", status: "success" }),
    ],
  })));
  assert.match(html, /Read SKILL\.md(?! \+)/, "a read has no added or removed count");
  assert.match(html, /Edited thistest\.md \+5 -4/);
  assert.match(html, /Replace/);
  assert.doesNotMatch(html, />Start</, "a later successful list replaces the previous one");
  assert.match(html, /List arguments/, "raw todo arguments stay behind expand");

  let renderer;
  await act(async () => {
    renderer = create(React.createElement(ChatDockContext.Provider, {
      value: {
        fileChanges: [{ id: "change-1", toolCallId: "edit-1", path: "thistest.md", addedLines: 5, removedLines: 4 }],
        openChange: (id) => opened.push(id),
        openFile: (file) => opened.push(file),
      },
    }, React.createElement(AgentMessageFeed, {
      messages: [
        new AIMessage({ id: "turn", content: "", tool_calls: [editCall] }),
        new ToolMessage({ tool_call_id: "edit-1", name: "edit_file", content: "edited", status: "success" }),
      ],
    })));
  });
  const line = renderer.root.findByProps({ className: "activity-line" });
  await act(async () => { line.props.onClick({ preventDefault() {}, stopPropagation() {} }); });
  assert.deepEqual(opened, ["change-1"]);
  assert.deepEqual(sends, []);

  const failed = renderToStaticMarkup(React.createElement(AgentMessageFeed, {
    messages: [
      new AIMessage({ id: "todos", content: "", tool_calls: [secondTodos, failedTodos] }),
      new ToolMessage({ tool_call_id: "todo-2", name: "write_todos", content: "ok", status: "success" }),
      new ToolMessage({ tool_call_id: "todo-3", name: "write_todos", status: "error", content: "Error: list rejected" }),
    ],
  }));
  assert.match(failed, /Replace/, "a failed update keeps the previous list");
  assert.match(failed, /list rejected/);
  assert.doesNotMatch(failed, /Should not replace/);
  globalThis.fetch = originalFetch;
} finally {
  await vite.close();
}

console.log("Chat dock and activity line checks passed.");
