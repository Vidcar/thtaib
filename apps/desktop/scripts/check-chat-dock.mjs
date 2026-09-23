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

assert.match(css, /grid-template-columns:\s*minmax\(0, 1fr\) minmax\(0, min\(var\(--inspector-width, 380px\), 48%\)\)/, "the dock stays within half the available width so fixed column minimums cannot overflow a narrow conversation");
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
  assert.match(html, /aria-label="Completed"/, "completed todos expose an accessible status mark");
  assert.doesNotMatch(html, /Allowed by saved permission/, "successful tools do not imply a saved grant");

  const authorised = renderToStaticMarkup(React.createElement(AgentMessageFeed, { messages: [
    new AIMessage({ id: "authorised", content: "", tool_calls: [readCall] }),
    new ToolMessage({ tool_call_id: "read-1", name: "read_file", content: "skill", status: "success", additional_kwargs: { authorization_source: "saved_permission" } }),
  ] }));
  assert.match(authorised, /Allowed by saved permission/, "the backend grant fact is visible on the exact tool");
  const durableAuthorisation = renderToStaticMarkup(React.createElement(AgentMessageFeed, { toolAuthorizations: { "read-1": "saved_permission" }, messages: [new AIMessage({ id: "restored", content: "", tool_calls: [readCall] })] }));
  assert.match(durableAuthorisation, /Allowed by saved permission/, "retained run authorization can restore the exact call fact");
  const { RunActivitySummary, helperApprovalOwner } = await vite.ssrLoadModule("/src/renderer/RunActivitySummary.tsx");
  const reviewedRun = { child_runs: [{ run_id: "child-1", name: "Research helper", namespace: ["tools:parent", "helper:one"], status: "waiting for approval or answer" }], review_observation: { enabled: true, status: "max_iterations_reached", max_revisions: 2, evidence_scope: "Model review; no executable checks.", evaluations: [{ explanation: "One issue remains", criteria: [{ name: "Citations", passed: false, gap: "Missing source for the last claim" }] }] } };
  assert.equal(helperApprovalOwner(reviewedRun, ["tools:parent", "helper:one", "tools:child"]), "Research helper");
  assert.equal(helperApprovalOwner(reviewedRun, ["tools:other"]), undefined, "an unrelated approval cannot be attributed to a helper");
  const reviewHtml = renderToStaticMarkup(React.createElement(RunActivitySummary, { run: reviewedRun }));
  assert.match(reviewHtml, /Research helper/);
  assert.match(reviewHtml, /Review limit reached/);
  assert.match(reviewHtml, /Missing source for the last claim/);
  assert.doesNotMatch(reviewHtml, /Review passed/, "exhausted revisions never imply a passing review");

  const { groupActivity } = await vite.ssrLoadModule("/src/renderer/activityLine.ts");
  const activity = [
    { id: 1, label: "Read one", finished: true, failed: false },
    { id: 2, label: "Read two", finished: true, failed: false },
    { id: 3, label: "Read failed", finished: true, failed: true },
    { id: 4, label: "Read four", finished: true, failed: false },
    { id: 5, label: "Reading five", finished: false, failed: false },
  ];
  const groups = groupActivity(activity, item => item);
  assert.deepEqual(groups.map(group => group.items.map(item => item.id)), [[1, 2], [3], [4], [5]], "failed and running calls remain visible chronological boundaries");
  assert.equal(groups[0].label, "Read 2 files");
  assert.deepEqual(groups.flatMap(group => group.items), activity, "grouping retains every original tool record");

  const { groupConsecutiveChanges, MonacoDiff } = await vite.ssrLoadModule("/src/renderer/ChatDock.tsx");
  const changes = [
    { change: { id: "first", path: "one.md" }, before: "A", after: "B" },
    { change: { id: "second", path: "one.md" }, before: "B", after: "C" },
    { change: { id: "third", path: "two.md" }, before: "X", after: "Y" },
    { change: { id: "fourth", path: "one.md" }, before: "C", after: "D" },
  ];
  const changeGroups = groupConsecutiveChanges(changes);
  assert.deepEqual(changeGroups.map(group => group.items.map(item => item.change.id)), [["first", "second"], ["third"], ["fourth"]]);
  assert.equal(changeGroups[0].items[1], changes[1], "a grouped edit keeps its own before/after evidence and reversal identity");
  let loadAttempts = 0;
  const rejectEditor = async () => { loadAttempts += 1; throw new Error("Editor resource unavailable"); };
  let unavailable;
  await act(async () => { unavailable = create(React.createElement(MonacoDiff, { original: "A", modified: "B", sideBySide: true, load: rejectEditor })); });
  assert.match(JSON.stringify(unavailable.toJSON()), /The difference is unavailable/);
  assert.doesNotMatch(JSON.stringify(unavailable.toJSON()), /Opening the difference/, "failed loading cannot leave an indefinite progress label");
  await act(async () => unavailable.root.findByType("button").props.onClick());
  assert.equal(loadAttempts, 2, "retry reattempts the failed editor resource");
  await act(async () => unavailable.unmount());

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
