import assert from "node:assert/strict";
import path from "node:path";
import { fileURLToPath } from "node:url";
import React from "react";
import { AIMessage, HumanMessage, ToolMessage } from "@langchain/core/messages";
import { renderToStaticMarkup } from "react-dom/server";
import { act, create } from "react-test-renderer";
import { createServer as createViteServer } from "vite";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;
const desktopRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const vite = await createViteServer({ root: desktopRoot, appType: "custom", server: { middlewareMode: true, hmr: false }, logLevel: "error" });
try {
  const { AgentMessageFeed } = await vite.ssrLoadModule("/src/renderer/AgentMessageFeed.tsx");
  const { RunActivitySummary } = await vite.ssrLoadModule("/src/renderer/RunActivitySummary.tsx");
  const { ProjectPreview } = await vite.ssrLoadModule("/src/renderer/ProjectPreview.tsx");
  const calls = Array.from({ length: 6 }, (_, index) => ({ id: `write-${index}`, name: "write_file", args: { file_path: `file-${index}.txt`, content: `body ${index}` } }));
  const states = ["succeeded", "succeeded", "failed", "uncertain", "not_dispatched", "incomplete_arguments"];
  const failedRun = {
    id: "old-run", input_message_id: "old-input", status: "failed", error: "Original worker connection failed",
    failure: { message: "Original worker connection failed", recovery_action: "inspect_effects" },
    tool_outcomes: Object.fromEntries(calls.map((call, index) => [call.id, { call_id: call.id, name: call.name, outcome: states[index],
      detail: states[index] === "failed" ? "Permission denied on the third file" : null,
      result: index < 2 ? `Saved file-${index}.txt` : null,
    }])),
  };
  const newRun = { id: "new-run", input_message_id: "new-input", status: "completed", tool_outcomes: {} };
  const failedMessages = [new HumanMessage({ id: "old-input", content: "Write six files" }), new AIMessage({ id: "old-ai", content: "Creating the files", tool_calls: calls }), new AIMessage({ id: "empty-tail", content: "" })];
  const recovered = renderToStaticMarkup(React.createElement(AgentMessageFeed, {
    messages: [...failedMessages, new HumanMessage({ id: "new-input", content: "Continue" }), new AIMessage({ id: "new-ai", content: "Continued" })],
    currentRunId: newRun.id, helperRuns: [failedRun, newRun], live: false, detailedStreams: true,
  }));
  assert.match(recovered, /Created 2 files/, "successful siblings survive a failed batch without claiming the remaining writes succeeded");
  assert.match(recovered, /Permission denied on the third file/);
  assert.match(recovered, /Check effects for file-3.txt/);
  assert.match(recovered, /Not started: file-4.txt/);
  assert.match(recovered, /Unfinished input for file-5.txt/);
  assert.equal((recovered.match(/Original worker connection failed/g) ?? []).length, 1, "the original historical failure stays visible even after an empty assistant tail and a later successful turn");
  assert.equal((recovered.match(/class="tool-call-row tool-call-failed"/g) ?? []).length, 1, "uncertain and unstarted actions are distinct from a confirmed failed action");

  const durableSuccess = renderToStaticMarkup(React.createElement(AgentMessageFeed, {
    messages: failedMessages.slice(0, 2), currentRunId: failedRun.id, helperRuns: [failedRun], live: false, detailedStreams: true,
    toolCalls: [{ id: "write-0", callId: "write-0", name: "write_file", input: calls[0].args, status: "error", error: "Stale stream cancellation" }],
  }));
  assert.doesNotMatch(durableSuccess, /Stale stream cancellation/, "a durable successful result takes precedence over a cancelled live handle");
  assert.match(durableSuccess, /Saved file-0.txt/);

  const orphan = renderToStaticMarkup(React.createElement(AgentMessageFeed, {
    messages: [new HumanMessage({ id: "old-input", content: "Old turn" }), new ToolMessage({ tool_call_id: "write-0", name: "write_file", content: "Old native result", status: "success" }), new HumanMessage({ id: "new-input", content: "New turn" })],
    currentRunId: newRun.id, helperRuns: [failedRun, { ...newRun, tool_outcomes: { "write-0": { outcome: "failed", detail: "Unrelated new error" } } }], live: false,
  }));
  assert.doesNotMatch(orphan, /Unrelated new error/, "a compacted historical result uses its own run when a later call reuses an ID");
  assert.match(orphan, /Saved file-0.txt/);
  const thinkingMessage = new AIMessage({ id: "thinking", content: [{ type: "reasoning", reasoning: "Considering the next action" }] });
  for (const [phase, label] of [["thinking", "Thinking"], ["using_tools", "Using tools"], ["summarizing", "Summarizing"], ["saving_changes", "Saving"]]) {
    const current = { ...newRun, status: "running", activity_phase: phase === "saving_changes" ? null : phase, finalization_phase: phase === "saving_changes" ? phase : null };
    const html = renderToStaticMarkup(React.createElement(AgentMessageFeed, { messages: [thinkingMessage], currentRunId: current.id, helperRuns: [current], live: true }));
    assert.match(html, new RegExp(`aria-label="Response in progress">${label}</span>`), "the current reasoning bubble names the actual live stage");
    const finished = renderToStaticMarkup(React.createElement(AgentMessageFeed, { messages: [thinkingMessage], currentRunId: current.id, helperRuns: [{ ...current, status: "completed" }], live: false }));
    assert.doesNotMatch(finished, /class="message-state"/, "a completed message has no live stage badge");
  }
  for (const [action, label] of [["inspect_effects", "Inspect effects"], ["change_limit", "Change response limit"], ["correct_setup", "Correct setup"], ["continue", "Continue from results"]]) {
    const html = renderToStaticMarkup(React.createElement(RunActivitySummary, { run: { ...failedRun, failure: { ...failedRun.failure, recovery_action: action } }, onRecover() {} }));
    assert.match(html, new RegExp(label), `recovery routes ${action} to the relevant action`);
    assert.match(html, /Original worker connection failed/);
  }
  const poolFailure = { ...failedRun, failure: { category: "capacity", code: "context_pool_exhausted", message: "The engine could not allocate enough context memory.", recovery_action: "change_limit" } };
  let poolRecoveryRun;
  let poolRenderer;
  try {
    await act(async () => { poolRenderer = create(React.createElement(RunActivitySummary, { run: poolFailure, onRecover(run) { poolRecoveryRun = run; } })); });
    const recoveryButton = poolRenderer.root.findByType("button");
    assert.equal(recoveryButton.props.children, "Review parallel setting", "shared allocation recovery targets parallelism rather than the response allowance");
    await act(async () => recoveryButton.props.onClick());
    assert.equal(poolRecoveryRun, poolFailure, "the exact failed run reaches the existing Models recovery route");
  } finally {
    if (poolRenderer) await act(async () => poolRenderer.unmount());
  }
  const poolHint = renderToStaticMarkup(React.createElement(RunActivitySummary, { run: poolFailure }));
  assert.match(poolHint, /Wait for other work to finish, or reduce Parallel/);
  assert.doesNotMatch(poolHint, /Adjust the response or context limit/);

  const old = { fetch: globalThis.fetch, window: globalThis.window, setInterval: globalThis.setInterval, clearInterval: globalThis.clearInterval };
  const pending = [];
  const timers = new Map();
  let timerId = 0;
  globalThis.window = { workbench: { backendUrl: "http://127.0.0.1:8000" } };
  globalThis.setInterval = callback => { timers.set(++timerId, callback); return timerId; };
  globalThis.clearInterval = id => timers.delete(id);
  globalThis.fetch = (url, init) => new Promise(resolve => pending.push({ url: String(url), method: init?.method ?? "GET", body: init?.body, resolve }));
  const take = (thread, method = "GET", suffix = "") => {
    const index = pending.findIndex(item => item.url.endsWith(`/v1/previews/${thread}${suffix}`) && item.method === method);
    assert.ok(index >= 0, `expected ${method} preview request for ${thread}${suffix}`);
    return pending.splice(index, 1)[0];
  };
  const respond = (item, body, status = 200) => act(async () => { item.resolve({ ok: status < 400, status, json: async () => body }); });
  const poll = () => act(async () => { for (const callback of timers.values()) callback(); });
  let renderer;
  const props = threadId => ({ threadId, selectedPath: "games/driving game.html", enabled: true });
  const button = label => renderer.root.findAllByType("button").find(item => item.props.children === label);
  const view = () => JSON.stringify(renderer.toJSON());
  try {
    await act(async () => { renderer = create(React.createElement(ProjectPreview, props("first"))); });
    await respond(take("first"), { state: "active", url: "http://127.0.0.1:55101/old.html", entry_path: "old.html" });
    assert.equal(renderer.root.findByType("a").props.href, "http://127.0.0.1:55101/old.html");
    await poll();
    const stalePoll = take("first");
    await act(async () => button("Stop").props.onClick());
    await respond(take("first", "DELETE"), { state: "closed" });
    await respond(stalePoll, { state: "active", url: "http://127.0.0.1:55101/old.html" });
    assert.equal(renderer.root.findAllByType("a").length, 0, "a poll begun before Stop cannot resurrect the stopped preview");

    await act(async () => button("Preview page").props.onClick());
    const oldStart = take("first", "POST", "/start");
    assert.deepEqual(JSON.parse(oldStart.body), { entry_path: "games/driving game.html" });
    await act(async () => renderer.update(React.createElement(ProjectPreview, props("second"))));
    assert.equal(renderer.root.findAllByType("a").length, 0, "changing chats hides the former chat URL before the new status arrives");
    await respond(oldStart, { state: "active", url: "http://127.0.0.1:55101/wrong.html" });
    assert.equal(renderer.root.findAllByType("a").length, 0, "a late Start response cannot cross into a different chat");
    await respond(take("second"), { state: "closed" });
    await poll();
    await respond(take("second"), { error: "Temporary status failure" }, 503);
    assert.match(view(), /Temporary status failure/);
    await poll();
    await respond(take("second"), { state: "active", url: "http://127.0.0.1:55102/games/driving%20game.html" });
    assert.doesNotMatch(view(), /Temporary status failure/, "a successful status refresh clears the old network error");
    assert.equal(renderer.root.findByType("a").props.href, "http://127.0.0.1:55102/games/driving%20game.html", "Open preserves the exact server URL including encoded entry path");
    await poll();
    await respond(take("second"), { state: "lost", url: null });
    assert.equal(button("Preview page").props.disabled, true);
    assert.equal(renderer.root.findAllByType("a").length, 0);
    await act(async () => button("Clear lost preview").props.onClick());
    await respond(take("second", "POST", "/reset"), { state: "closed" });
    assert.equal(button("Preview page").props.disabled, false, "lost ownership has an explicit recovery before starting another preview");
    await poll();
    await respond(take("second"), { state: "lost", stop_pending: true, error: "Preview stop unconfirmed" });
    assert.match(view(), /Stop unconfirmed/);
    assert.ok(button("Stop"), "an unconfirmed stop retains a retry through its owned identity");
    assert.equal(button("Clear lost preview"), undefined, "a live owned process cannot be cleared as historical lost state");
    assert.equal(button("Preview page").props.disabled, true, "a new launch is blocked until owned cleanup is confirmed");
    await act(async () => button("Stop").props.onClick());
    await respond(take("second", "DELETE"), { state: "closed", stop_pending: false });
    assert.equal(button("Preview page").props.disabled, false, "successful cleanup restores ordinary preview controls");
    await poll();
    await respond(take("second"), { state: "active", url: "http://remote.invalid/" });
    assert.equal(renderer.root.findAllByType("a").length, 0, "the preview control never opens a non-loopback destination");
    assert.ok(button("Stop"), "owned processes remain stoppable even when no safe URL is available");
  } finally {
    if (renderer) await act(async () => renderer.unmount());
    Object.assign(globalThis, old);
  }
} finally {
  await vite.close();
}
console.log("Durable tool recovery and preview ownership checks passed.");
