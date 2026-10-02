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
const css = readFileSync(path.join(desktopRoot, "src/renderer/ChatPanel.css"), "utf8");
const dockSource = readFileSync(path.join(desktopRoot, "src/renderer/ChatDock.tsx"), "utf8");
const monacoSource = readFileSync(path.join(desktopRoot, "src/renderer/monacoSetup.ts"), "utf8");

assert.match(css, /grid-template-columns:\s*minmax\(0, 1fr\) minmax\(0, min\(var\(--inspector-width, 380px\), 48%, calc\(100% - 400px\)\)\)/, "the dock preserves a readable conversation while observed resize geometry catches up");
assert.doesNotMatch(css, /files-expanded[\s\S]*display:\s*none/, "widening the dock does not hide the conversation");
assert.match(css, /grid-area: 1 \/ 2 \/ 3 \/ 3/, "the rail stays a full-height column beside the transcript and composer");
assert.doesNotMatch(css, /max-width: 1120px/, "a narrower window does not move the rail above the composer");
assert.match(readFileSync(path.join(desktopRoot, "src/renderer/ChatPanel.tsx"), "utf8"), /MenuPopover label="Chat actions"[\s\S]*<ChatHistoryActions conversation=/, "conversation export and deletion live in the Chat header");
assert.match(dockSource, /Project files/, "the dock retains the project file browser");
assert.doesNotMatch(dockSource, /file-changes|reverse|DiffEditor/, "the retired file-change and undo path is absent");
assert.match(monacoSource, /loader\.config\(\{ monaco \}\)/, "Monaco is loaded from the desktop package");
assert.doesNotMatch(`${dockSource}\n${monacoSource}`, /cdn\.|jsdelivr|unpkg/, "the editor does not request a CDN");

const vite = await createViteServer({ root: desktopRoot, appType: "custom", server: { middlewareMode: true, hmr: false }, logLevel: "error" });
try {
  const { acceptedProjectFilePath, refusedProjectPathNotice, isRefusedProjectPathNotice, useConversationDockView, chatDockGeometry } = await vite.ssrLoadModule("/src/renderer/ChatDock.tsx");
  assert.equal(acceptedProjectFilePath("/skills/browser-validation/SKILL.md"), "", "a skill route is not a project file");
  assert.equal(acceptedProjectFilePath("src/app.ts"), "src/app.ts", "a relative project file stays selectable");
  assert.equal(acceptedProjectFilePath("C:/outside.txt"), "", "a drive path is not a project file");
  assert.equal(acceptedProjectFilePath(".."), "", "a parent segment is not a project file");
  const knowledgeNotice = "That path is managed knowledge or history, not a project file.";
  const outsideNotice = "That path is outside the project.";
  for (const route of ["memories", "skills", "retrieved", "conversation_history", "large_tool_results"]) {
    assert.equal(acceptedProjectFilePath(`${route}/note.md`), "", `${route} stays refused`);
    assert.equal(refusedProjectPathNotice(`/${route}/note.md`), knowledgeNotice, `${route} uses the knowledge notice`);
  }
  assert.equal(refusedProjectPathNotice("C:/outside.txt"), outsideNotice, "a drive path is outside the project");
  assert.equal(refusedProjectPathNotice("D:\\outside.txt"), outsideNotice, "a Windows drive path is outside the project");
  assert.equal(refusedProjectPathNotice(".."), outsideNotice, "a parent segment is outside the project");
  assert.equal(refusedProjectPathNotice("src/../secret.txt"), outsideNotice, "a nested parent segment is outside the project");
  assert.equal(refusedProjectPathNotice("src/app.ts"), "", "an accepted file has no refusal notice");
  assert.equal(isRefusedProjectPathNotice(knowledgeNotice), true);
  assert.equal(isRefusedProjectPathNotice(outsideNotice), true);
  assert.equal(isRefusedProjectPathNotice("Connection interrupted. Checking whether the message was accepted."), false, "another conversation notice is not a path refusal");
  assert.deepEqual(chatDockGeometry(320, 706), { width: 306, max: 306, canOpen: true }, "the half-width Chat pane retains a 400px readable conversation");
  assert.deepEqual(chatDockGeometry(620, 680), { width: 280, max: 280, canOpen: true }, "the minimum dock and readable conversation fit at 680px");
  assert.equal(chatDockGeometry(620, 679).canOpen, false, "below 680px the dock waits for a wider pane");
  assert.equal(chatDockGeometry(620, 1400).width, 620, "widening restores the preferred dock width");
  const { usePanelWidth } = await vite.ssrLoadModule("/src/renderer/PanelResize.tsx");
  const oldWindow = globalThis.window;
  const storage = new Map([["workbench.inspector.width", "560"], ["workbench.browser.rail.width", "900"]]);
  globalThis.window = { localStorage: { getItem: key => storage.get(key) ?? null, setItem: (key, value) => storage.set(key, value) } };
  function DockView({ conversationId }) {
    const [view, update] = useConversationDockView(conversationId);
    const [width, resize] = usePanelWidth("workbench.chat.dock.width", 320, 280, 1100, "workbench.inspector.width");
    return React.createElement("output", { view, update, width, resize });
  }
  let dock;
  try {
    await act(async () => { dock = create(React.createElement(DockView, { conversationId: "a" })); });
    const read = () => dock.root.findByType("output").props;
    assert.equal(read().width, 560, "the one dock preference is seeded from Files rather than Browser");
    const remembered = { open: true, page: "browser", helper: "parent:helper", projectId: "project", path: "src/file.txt", filter: "file", folders: ["src"], previewId: "upload", filesScroll: 420, helpersScroll: 80, treeScroll: 560, treeScrollLeft: 20, treeSelection: "src/file.txt", fileViews: { "project:src/file.txt": { state: null, scrollTop: 1200, scrollLeft: 50 } } };
    await act(async () => { read().update(remembered); read().resize(620); });
    await act(async () => dock.update(React.createElement(DockView, { conversationId: "b" })));
    assert.equal(read().view.open, false); assert.equal(read().view.filter, "", "another conversation does not inherit file filters"); assert.equal(read().width, 620, "tabs and chats use the same preferred width");
    await act(async () => read().update({ open: true, page: "helpers", helper: "other" }));
    await act(async () => dock.update(React.createElement(DockView, { conversationId: "a" })));
    for (const [key, value] of Object.entries(remembered)) assert.deepEqual(read().view[key], value, `A to B to A restores ${key}`);
    await act(async () => dock.unmount()); dock = null;
    await act(async () => { dock = create(React.createElement(DockView, { conversationId: "a" })); });
    assert.equal(read().width, 620); assert.equal(read().view.previewId, "upload"); assert.equal(read().view.filesScroll, 420, "restart restores only local presentation state");
    storage.set("workbench.chat.dock.view:skill", JSON.stringify({ open: true, page: "browser", path: "/skills/browser-validation/SKILL.md", projectId: "project_52" }));
    await act(async () => dock.update(React.createElement(DockView, { conversationId: "skill" })));
    assert.equal(read().view.path, "", "a saved skill path is not opened as a project file");
    assert.equal(JSON.parse(storage.get("workbench.chat.dock.view:skill")).path, "", "the refused path is removed from the saved view");
  } finally { if (dock) await act(async () => dock.unmount()); globalThis.window = oldWindow; }
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
  assert.match(html, /Edited thistest\.md/);
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
  const matchedGrant = { id: "grant_exact_read", scope: "session", thread_id: "chat-thread-7", project_path: "D:/Project/Scope", action: "read_file", arguments: { file_path: "SKILL.md", offset: 0, limit: 20 }, created_at: "2026-09-24T01:15:00Z", source_run_id: "original-grant-run", display_name: "Read SKILL.md · This session" };
  const namedGrant = renderToStaticMarkup(React.createElement(AgentMessageFeed, { messages: [
    new AIMessage({ id: "matched-grant", content: "", tool_calls: [readCall] }),
    new ToolMessage({ tool_call_id: "read-1", name: "read_file", content: "skill", status: "success", additional_kwargs: { authorization_source: "saved_permission", authorization_grant: matchedGrant } }),
  ] }));
  assert.match(namedGrant, /Allowed by saved permission: Read SKILL\.md · This session/, "the activity names the actual matched grant");
  assert.match(namedGrant, /grant_exact_read/); assert.match(namedGrant, /chat-thread-7/); assert.match(namedGrant, /D:\/Project\/Scope/); assert.match(namedGrant, /original-grant-run/); assert.match(namedGrant, /2026-09-24T01:15:00Z/); assert.match(namedGrant, /&quot;limit&quot;: 20/);
  assert.ok(namedGrant.indexOf('class="tool-raw-arguments"') < namedGrant.indexOf('aria-label="Matched saved permission"'), "full grant stays in the existing further disclosure");
  const restoredGrant = renderToStaticMarkup(React.createElement(AgentMessageFeed, { toolAuthorizations: { "read-1": "saved_permission" }, toolAuthorizationGrants: { "read-1": matchedGrant, "unrelated-call": { ...matchedGrant, id: "wrong-grant", display_name: "Wrong permission" } }, messages: [new AIMessage({ id: "restored-grant", content: "", tool_calls: [readCall] }), new ToolMessage({ tool_call_id: "read-1", name: "read_file", content: "skill", status: "success" })] }));
  assert.match(restoredGrant, /Read SKILL\.md · This session/); assert.match(restoredGrant, /grant_exact_read/); assert.match(restoredGrant, /&quot;limit&quot;: 20/); assert.doesNotMatch(restoredGrant, /Wrong permission|wrong-grant/, "grant identity belongs to the exact call");
  const unprovenGrant = renderToStaticMarkup(React.createElement(AgentMessageFeed, { toolAuthorizationGrants: { "read-1": matchedGrant }, messages: [new AIMessage({ id: "unproven", content: "", tool_calls: [readCall] }), new ToolMessage({ tool_call_id: "read-1", name: "read_file", content: "success", status: "success", additional_kwargs: { authorization_grant: matchedGrant } })] }));
  assert.doesNotMatch(unprovenGrant, /Allowed by saved permission|grant_exact_read/, "grant-shaped metadata without actual authorization attribution cannot imply grant use");
  for (const scope of ["session", "always"]) {
    const noProjectGrant = renderToStaticMarkup(React.createElement(AgentMessageFeed, { messages: [new AIMessage({ id: `no-project-${scope}`, content: "", tool_calls: [readCall] }), new ToolMessage({ tool_call_id: "read-1", name: "read_file", content: "skill", status: "success", additional_kwargs: { authorization_source: "saved_permission", authorization_grant: { ...matchedGrant, scope, project_path: null, thread_id: null } } })] }));
    assert.match(noProjectGrant, /<dt>Project<\/dt><dd>No project<\/dd>/, "a projectless grant does not authorize other projects");
    assert.match(noProjectGrant, scope === "always" ? /<dt>Session<\/dt><dd>Any session<\/dd>/ : /<dt>Session<\/dt><dd>Not recorded<\/dd>/, "only an always grant can apply across sessions");
    assert.doesNotMatch(noProjectGrant, /Not restricted/, "unknown scope is never presented as unrestricted");
  }
  const incompleteGrant = renderToStaticMarkup(React.createElement(AgentMessageFeed, { messages: [new AIMessage({ id: "incomplete-grant", content: "", tool_calls: [readCall] }), new ToolMessage({ tool_call_id: "read-1", name: "read_file", content: "skill", status: "success", additional_kwargs: { authorization_source: "saved_permission", authorization_grant: { id: "incomplete", display_name: "Unverified name" } } })] }));
  assert.match(incompleteGrant, /Allowed by saved permission/); assert.doesNotMatch(incompleteGrant, /Unverified name|Matched saved permission/, "incomplete identity retains only the proven generic attribution");
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

  let renderer;
  await act(async () => {
    renderer = create(React.createElement(ChatDockContext.Provider, {
      value: {
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
  assert.deepEqual(opened, ["thistest.md"], "activity opens the current project file");
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
