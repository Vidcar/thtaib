import assert from "node:assert/strict";
import React from "react";
import { act } from "react-test-renderer";
import { createServer as createViteServer } from "vite";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { readFileSync } from "node:fs";
import { makeHarness, run, deferred, json, renderChat, closeHarness, button, textOf, waitFor, flush } from "./check-chat-interaction-boundaries.mjs";

const desktop = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
export function orderingHarness(options = {}) {
  const runs = new Map();
  const metadata = new Map();
  let messages = [{ id: "conv_a_user", type: "human", content: "TURN ONE" }];
  let origins = [];
  let seq = 0;
  let current = run("order_run_1", "running", "conv_a_user");
  runs.set(current.id, current);
  let harness;
  const requestOverride = async ({ req, res, url, state, body }) => {
    const detail = url.pathname.match(/^\/v1\/agent-runs\/([^/]+)$/);
    if (req.method === "GET" && detail) {
      metadata.get(detail[1])?.requested.resolve();
      await metadata.get(detail[1])?.gate.promise;
      json(res, 200, runs.get(detail[1])); return true;
    }
    if (req.method === "GET" && /^\/v1\/chat\/conversations\/conv_a\/replies\/[^/]+\/actions$/.test(url.pathname)) {
      json(res, 200, { branch_available: true, retry_available: true, regenerate_available: true,
        branch_reason: null, retry_reason: null, regenerate_reason: null }); return true;
    }
    if (req.method === "GET" && url.pathname === "/v1/agent-interaction/threads/thread_a/state") {
      json(res, 200, { values: values(), next: current.status === "running" ? ["agent"] : [], tasks: [], interaction_cursor: seq }); return true;
    }
    if (await options.requestOverride?.({ req, res, url, state, body, scenario })) return true;
    return false;
  };
  harness = makeHarness({ aRun: current, threadARun: current, browser: options.browser, requestOverride });
  harness.state.conversations.conv_a.transcript[0].content = "TURN ONE";
  harness.state.conversations.conv_a.current_run = current;
  current.messages = messages;
  const values = () => ({ messages, workbench: { run: current, tool_origins: origins, incomplete_message_ids: [] } });
  const publish = () => {
    current.messages = messages;
    runs.set(current.id, structuredClone(current));
    harness.state.streamRuns.set("thread_a", current);
    const conversation = harness.state.conversations.conv_a;
    harness.state.conversations.conv_a = { ...conversation, current_run: current, current_run_id: current.id,
      run_ids: [...new Set([...conversation.run_ids, current.id])],
      transcript: messages.filter(m => m.type === "human" || (m.type === "ai" && String(m.content).startsWith("FINAL")))
        .map(m => ({ id: m.id, role: m.type === "human" ? "user" : "assistant", content: m.content, at: "2026-09-26T12:00:00Z",
          run_id: m.type === "human" ? [...runs.values()].find(run => run.input_message_id === m.id)?.id ?? current.id : `order_run_${m.id.split("_")[1]}`, content_blocks: [] })) };
  };
  const emit = (method, data) => {
    const wire = { type: "event", method, seq: ++seq, event_id: `order-${seq}`, params: { namespace: [], data } };
    for (const response of harness.state.allStreams.keys()) response.write(`id: ${seq}\ndata: ${JSON.stringify(wire)}\n\n`);
  };
  const sendValues = () => { publish(); emit("values", values()); };
  const scenario = {
    harness, runs, metadata, values, emit,
    holdMetadata(id) { const held = { gate: deferred(), requested: deferred() }; metadata.set(id, held); return held; },
    begin(number, { inputId = `human_${number}` } = {}) {
      current = run(`order_run_${number}`, "running", inputId);
      messages = [...messages, { id: inputId, type: "human", content: ["", "TURN ONE", "TURN TWO", "TURN THREE", "TURN FOUR"][number] }];
      // The backend already admitted the new run. ChatPanel learns ownership
      // through its delayed conversation lookup after the native frame arrives.
      sendValues();
    },
    adopt() { publish(); },
    text(number, content = `CHECK ${number}`) {
      const id = `check_${number}`;
      emit("messages", { event: "message-start", id, role: "ai" });
      emit("messages", { event: "content-block-start", index: 0, content: { type: "text", text: content } });
      emit("messages", { event: "message-finish" });
      messages = [...messages, { id, type: "ai", content }]; sendValues();
    },
    tool(number, { callId = `read_${number}`, outcome = "success" } = {}) {
      const input = { file_path: `turn-${number}.txt` };
      origins = [...origins, { run_id: current.id, input_message_id: current.input_message_id, namespace: [], call_id: callId }];
      sendValues();
      emit("tools", { event: "tool-started", tool_call_id: callId, tool_name: "read_file", input });
      messages = [...messages, { id: `call_${number}`, type: "ai", content: "", tool_calls: [{ id: callId, name: "read_file", args: input }] }]; sendValues();
      if (outcome === "stopped") return;
      if (outcome === "failed") emit("tools", { event: "tool-error", tool_call_id: callId, tool_name: "read_file", error: `FAILED ${number}` });
      else emit("tools", { event: "tool-finished", tool_call_id: callId, tool_name: "read_file", output: `RESULT ${number}` });
      messages = [...messages, { id: `result_${number}`, type: "tool", tool_call_id: callId, name: "read_file", content: outcome === "failed" ? `FAILED ${number}` : `RESULT ${number}`, status: outcome === "failed" ? "error" : "success" }]; sendValues();
    },
    originBeforeReusedStart(number, callId, previousNumber) {
      origins = [...origins, { run_id: current.id, input_message_id: current.input_message_id, namespace: [], call_id: callId }];
      const index = messages.findIndex(message => message.id === `call_${previousNumber}`);
      messages = [...messages.slice(0, index + 1), { id: `late_result_${previousNumber}`, type: "tool", tool_call_id: callId, name: "read_file", content: `LATE OLD RESULT ${previousNumber}`, status: "success" }, ...messages.slice(index + 1)];
      sendValues();
    },
    startUnprojectedTool(number, callId) {
      emit("tools", { event: "tool-started", tool_call_id: callId, tool_name: "read_file", input: { file_path: `turn-${number}.txt` } });
    },
    final(number, status = "completed", long = false) {
      messages = [...messages, { id: `final_${number}`, type: "ai", content: `FINAL ${number}${long ? "\n\n" + Array.from({length:35}, (_, i) => `Paragraph ${i + 1}. A long response keeps the native transcript larger than the viewport.`).join("\n\n") : ""}` }];
      current.status = status; sendValues();
      emit("lifecycle", { event: status === "cancelled" ? "cancelled" : "completed", run_id: current.id });
    },
    startFinal(number) {
      messages = [...messages, { id: `final_${number}`, type: "ai", content: `FINAL ${number}` }];
      publish();
      emit("messages", { event: "message-start", id: `final_${number}`, role: "ai" });
      emit("messages", { event: "content-block-start", index: 0, content: { type: "text", text: `FINAL ${number}` } });
    },
    appendFinal(number, line) {
      const text = `\n\nParagraph ${line}. A long response keeps the native transcript larger than the viewport.`;
      messages = messages.map(message => message.id === `final_${number}` ? { ...message, content: message.content + text } : message);
      publish(); emit("messages", { event: "content-block-delta", index: 0, delta: { type: "text-delta", text } });
    },
    settle(number, status = "completed") {
      emit("messages", { event: "content-block-finish", index: 0, content: { type: "text", text: messages.find(m => m.id === `final_${number}`).content } });
      emit("messages", { event: "message-finish" }); current.status = status; sendValues();
      emit("lifecycle", { event: status === "cancelled" ? "cancelled" : "completed", run_id: current.id });
    },
    releaseAll() { for (const held of metadata.values()) held.gate.resolve(); for (const held of harness.state.barriers.chatConversation.values()) held.resolve(); },
  };
  return scenario;
}

const feed = renderer => renderer.root.findAll(n => n.type === "div" && n.props.className === "message-feed")[0];
const bubbles = renderer => feed(renderer)?.findAll(n => n.type === "article") ?? [];
const tools = renderer => feed(renderer)?.findAll(n => n.type === "details" && n.props.className === "message-tools") ?? [];
const labels = renderer => bubbles(renderer).map(node => textOf(node).match(/TURN (?:ONE|TWO|THREE|FOUR)|CHECK \d|FINAL \d|turn-\d\.txt/)?.[0] ?? "UNKNOWN");

export async function checkMountedOrdering(vite, { collectBaseline = false } = {}) {
  const scenario = orderingHarness();
  const renderer = await renderChat(vite, scenario.harness);
  const failures = [];
  const verify = (label, fn) => { try { fn(); } catch (error) { if (!collectBaseline) throw error; failures.push(`${label}: ${error.message}`); } };
  try {
    await waitFor(() => button(renderer, "Conversation A"), "ordering conversation listed");
    await act(async () => button(renderer, "Conversation A").props.onClick());
    await waitFor(() => assert.ok(scenario.harness.state.allStreams.size), "actual SDK stream attached");
    await act(async () => { scenario.text(1); scenario.tool(1); scenario.final(1); });
    await waitFor(() => assert.deepEqual(labels(renderer), ["TURN ONE", "CHECK 1", "turn-1.txt", "FINAL 1"]), "first native turn rendered in order");
    const originalFeed = feed(renderer);
    const oldBubble = bubbles(renderer)[2];
    const oldDetails = tools(renderer)[0];
    await act(async () => oldDetails.findAllByType("summary")[0].props.onClick({ preventDefault() {} }));
    assert.equal(oldDetails.findAllByType("summary")[0].props["aria-expanded"], true);
    const heldMetadata = scenario.holdMetadata("order_run_1");
    const heldAdmission = deferred();
    scenario.harness.state.barriers.chatConversation.set("conv_a", heldAdmission);
    const lookupsBeforeAdmission = scenario.harness.state.requests.chatGets.length;
    await act(async () => scenario.begin(2));
    await waitFor(() => assert.ok(scenario.harness.state.requests.chatGets.length > lookupsBeforeAdmission), "unknown queued run begins admission lookup");
    await flush();
    verify("queued admission keeps feed mounted", () => assert.ok(feed(renderer) === originalFeed, "the same feed must stay mounted"));
    verify("queued admission retains old output", () => assert.deepEqual(labels(renderer), ["TURN ONE", "CHECK 1", "turn-1.txt", "FINAL 1"]));
    scenario.adopt();
    scenario.harness.state.barriers.chatConversation.delete("conv_a"); heldAdmission.resolve();
    // The server's response was captured before adoption; deliver another newer
    // native values frame so ownership is checked against the accepted run.
    await act(async () => scenario.emit("values", scenario.values()));
    await waitFor(() => assert.ok(labels(renderer).includes("TURN TWO")), "queued run adopted");
    verify("historical tool has one row while metadata waits", () => assert.equal(tools(renderer).length, 1));
    verify("historical bubble identity survives metadata wait", () => assert.ok(bubbles(renderer)[2] === oldBubble, "the old assistant bubble must retain identity"));
    verify("historical disclosure identity survives metadata wait", () => assert.ok(tools(renderer)[0] === oldDetails, "the old tool disclosure must retain identity"));
    verify("explicit disclosure stays open", () => assert.equal(tools(renderer)[0].findAllByType("summary")[0].props["aria-expanded"], true));
    heldMetadata.gate.resolve();
    await act(async () => { scenario.text(2); scenario.tool(2, { callId: "read_1", outcome: "failed" }); scenario.final(2, "failed"); });
    await waitFor(() => assert.ok(labels(renderer).includes("FINAL 2")), "second final arrives");
    verify("two-turn exact article order", () => assert.deepEqual(labels(renderer), ["TURN ONE", "CHECK 1", "turn-1.txt", "FINAL 1", "TURN TWO", "CHECK 2", "turn-2.txt", "FINAL 2"]));
    verify("reused handle has exactly two owned tool sections", () => assert.equal(tools(renderer).length, 2));
    verify("previous success cannot take current failure", () => { assert.match(textOf(tools(renderer)[0]), /RESULT 1/); assert.doesNotMatch(textOf(tools(renderer)[0]), /FAILED 2/); assert.match(textOf(tools(renderer)[1]), /FAILED 2/); });
    await act(async () => { scenario.begin(3); scenario.text(3); scenario.tool(3, { outcome: "stopped" }); scenario.final(3, "cancelled"); });
    await waitFor(() => assert.ok(labels(renderer).includes("FINAL 3")), "third final arrives without remount");
    verify("three-turn exact article order", () => assert.deepEqual(labels(renderer), ["TURN ONE", "CHECK 1", "turn-1.txt", "FINAL 1", "TURN TWO", "CHECK 2", "turn-2.txt", "FINAL 2", "TURN THREE", "CHECK 3", "turn-3.txt", "FINAL 3"]));
    verify("all calls appear once under their original turn", () => assert.equal(tools(renderer).length, 3));
    verify("third stopped tool cannot claim success", () => assert.doesNotMatch(textOf(tools(renderer)[2]), /RESULT 3|Reading turn-3/));
    verify("first row stays the same mounted row", () => assert.ok(bubbles(renderer)[2] === oldBubble, "the old assistant bubble must retain identity"));
    // The SDK can change an old unfinished handle from graph-state backfill
    // while a new same-ID origin is already public but its tool-start has not
    // arrived. An object change is therefore not proof of a new invocation.
    await act(async () => { scenario.begin(4); scenario.originBeforeReusedStart(4, "read_3", 3); });
    await waitFor(() => assert.ok(labels(renderer).includes("TURN FOUR")), "fourth admission before reused native start");
    verify("origin without matching native start cannot create a new tool", () => assert.equal(tools(renderer).length, 3));
    verify("old backfilled handle cannot appear under new input", () => { const fourth = textOf(feed(renderer)).split("TURN FOUR")[1]; assert.doesNotMatch(fourth, /turn-3\.txt|LATE OLD RESULT 3|RESULT 3/); });
    await act(async () => scenario.startUnprojectedTool(4, "read_3"));
    await waitFor(() => assert.match(textOf(feed(renderer)), /turn-4\.txt/), "confirmed reused native start appears before assistant call projects");
    verify("confirmed new invocation appears once", () => assert.equal(tools(renderer).length, 4));
    verify("confirmed reused native handle has current input only", () => { const fourth = textOf(feed(renderer)).split("TURN FOUR")[1]; assert.match(fourth, /turn-4\.txt/); assert.doesNotMatch(fourth, /turn-3\.txt|LATE OLD RESULT 3/); });
    if (collectBaseline) { assert.ok(failures.length, "baseline must expose an actual failure"); console.log(JSON.stringify({ baselineFailures: failures }, null, 2)); }
  } finally { scenario.releaseAll(); await closeHarness(renderer, scenario.harness); }
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const override = process.env.CHAT_PANEL_SOURCE_OVERRIDE;
  const vite = await createViteServer({ root: desktop, appType: "custom", server: { middlewareMode: true, hmr: false }, logLevel: "error",
    plugins: override ? [{ name: "ordering-baseline", enforce: "pre", load(id) { if (id.replace(/\\/g, "/").endsWith("/src/renderer/ChatPanel.tsx")) return readFileSync(override, "utf8"); } }] : [] });
  try { await checkMountedOrdering(vite, { collectBaseline: process.env.LIVE_CHAT_ORDERING_BASELINE === "1" }); }
  finally { await vite.close(); }
  console.log(process.env.LIVE_CHAT_ORDERING_BASELINE === "1"
    ? "Mounted actual-SDK baseline failure evidence captured."
    : "Mounted actual-SDK live Chat ordering checks passed.");
}
