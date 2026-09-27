import assert from "node:assert/strict";
import path from "node:path";
import { fileURLToPath } from "node:url";
import React from "react";
import { act, create } from "react-test-renderer";
import { createServer as createViteServer } from "vite";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;
const desktop = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const calls = [];
const streams = new Map();
const intervals = new Map();
const frames = new Map();
const timeouts = new Map();
let nextId = 0;
globalThis.window = {
  workbench: { backendUrl: "http://browser-rail.test" },
  setInterval: callback => { const id = ++nextId; intervals.set(id, callback); return id; },
  clearInterval: id => intervals.delete(id),
  requestAnimationFrame: callback => { const id = ++nextId; frames.set(id, callback); return id; },
  cancelAnimationFrame: id => frames.delete(id),
  setTimeout: callback => { const id = ++nextId; timeouts.set(id, callback); return id; },
  clearTimeout: id => timeouts.delete(id),
};
const runtime = { supported: true, installed: true, chrome_available: true, chrome_version: "fixture", node_version: "fixture", playwright_mcp_version: "fixture", reason: null };
function state(thread_id, patch = {}) {
  return { thread_id, state: "active", worker: runtime, session_id: `${thread_id}_session`, revision: 1, active_page_id: "page_a", tabs: [{ page_id: "page_a", title: "First", url: "https://same.test/" }, { page_id: "page_b", title: "Second", url: "https://same.test/" }], viewport: { width: 1440, height: 900 }, control: "agent", ...patch };
}
const states = new Map([["one", state("one", { state: "closed", session_id: null, tabs: [], active_page_id: null })], ["two", state("two", { control: "user" })]]);
const previousFetch = globalThis.fetch;
let aborted = 0;
globalThis.fetch = async (url, init = {}) => {
  const pathname = new URL(String(url)).pathname;
  const match = pathname.match(/^\/v1\/browser\/sessions\/([^/]+)(\/.*)?$/);
  assert.ok(match, `Unexpected browser endpoint ${pathname}`);
  const [, thread, endpoint = ""] = match;
  const body = init.body ? JSON.parse(init.body) : null;
  calls.push({ thread, endpoint, method: init.method ?? "GET", body });
  if (endpoint === "/events") {
    assert.equal(init.headers.Accept, "text/event-stream");
    assert.equal(Object.keys(init.headers).some(name => /token|authorization/i.test(name)), false, "renderer never supplies worker or backend credentials");
    const bodyStream = new ReadableStream({ start(controller) {
      streams.set(thread, controller);
      init.signal.addEventListener("abort", () => { aborted += 1; streams.delete(thread); controller.close(); }, { once: true });
    } });
    return { ok: true, body: bodyStream };
  }
  let next = states.get(thread);
  if (endpoint === "/start") next = state(thread);
  if (endpoint === "/control") next = { ...next, control: body.action === "take" ? "user" : "agent" };
  if (endpoint === "/reset" || init.method === "DELETE") next = { ...next, state: "closed", session_id: null, tabs: [], active_page_id: null };
  if (endpoint === "/actions") {
    assert.equal(body.session_id, next.session_id);
    assert.equal(body.revision, next.revision);
    const action = body.action;
    if (action.type === "resize") next = { ...next, revision: next.revision + 1, viewport: { width: action.width, height: action.height } };
    if (action.type === "select_tab") next = { ...next, revision: next.revision + 1, active_page_id: action.page_id };
    if (action.type === "dialog") next = { ...next, dialog: null };
    if (action.type === "upload") next = { ...next, file_chooser: null };
  }
  states.set(thread, next);
  return { ok: true, json: async () => next };
};
function text(node) { return typeof node === "string" ? node : node?.children?.map(text).join("") ?? ""; }
function button(renderer, label) { return renderer.root.find(node => node.type === "button" && text(node).trim() === label); }
const tick = async () => { for (let i = 0; i < 12; i += 1) await Promise.resolve(); };
async function emit(thread, type, data, fragmented = false) {
  const bytes = new TextEncoder().encode(`event: ${type}\r\ndata: ${JSON.stringify(data)}\r\n\r\n`);
  await act(async () => {
    const controller = streams.get(thread);
    assert.ok(controller, `Live stream is connected for ${thread}`);
    if (fragmented) { controller.enqueue(bytes.slice(0, 13)); controller.enqueue(bytes.slice(13, 14)); controller.enqueue(bytes.slice(14)); }
    else controller.enqueue(bytes);
    await tick();
  });
}
async function flushFrames() { await act(async () => { for (const [id, callback] of frames) { frames.delete(id); callback(); } await tick(); }); }
function fixtureFrame(thread, patch = {}) {
  const current = states.get(thread);
  return { session_id: current.session_id, page_id: current.active_page_id, revision: current.revision, viewport: current.viewport, data: "Zmlyc3Q=", timestamp: 1, ...patch };
}
const viewportNode = { getBoundingClientRect: () => ({ left: 10, top: 20, width: 640, height: 500 }), focus() {}, setPointerCapture() {}, hasPointerCapture: () => true, releasePointerCapture() {} };
function pointer(renderer, name, patch = {}) { return renderer.root.findByProps({ "aria-label": "Live browser page" }).props[name]({ currentTarget: viewportNode, clientX: 330, clientY: 270, pointerId: 1, button: 0, preventDefault() {}, ...patch }); }
const props = { threadId: "one", visible: true, enabled: true, projectBound: true, attachments: [{ id: "asset_file", filename: "selected.txt" }], onConfigure() {}, onOpenLibrary() {} };
const vite = await createViteServer({ root: desktop, appType: "custom", server: { middlewareMode: true, hmr: false }, logLevel: "error" });
let renderer;
try {
  const { BrowserRail, browserPoint, browserFrameMatches, useBrowserRailActivity } = await vite.ssrLoadModule("/src/renderer/BrowserRail.tsx");
  const { visiblePendingInterrupt } = await vite.ssrLoadModule("/src/renderer/types.ts");
  const { visibleApprovalInterrupt } = await vite.ssrLoadModule("/src/renderer/InteractionStream.tsx");
  assert.deepEqual(browserPoint({ left: 10, top: 20, width: 640, height: 500 }, { width: 1440, height: 900 }, 330, 270), { x: 720, y: 450 });
  assert.equal(browserPoint({ left: 10, top: 20, width: 640, height: 500 }, { width: 1440, height: 900 }, 330, 25), null, "letterbox clicks do not touch the page");
  assert.equal(browserFrameMatches(null, state("one")), false);
  assert.equal(browserFrameMatches(fixtureFrame("two"), state("two", { active_page_id: "page_b" })), false, "duplicate URLs cannot confer page identity");
  const pending = { kind: "browser_control", environment: "browser_control", action_requests: [], note: "Return in Browser." };
  assert.equal(visiblePendingInterrupt({ pending_interrupt: pending, events: [] }), null, "takeover has no generic approval buttons");
  assert.equal(visibleApprovalInterrupt({ interrupts: [{ id: "native", value: pending }], values: {} }, { status: "running", pending_interrupt: pending }), null, "native handoff cannot be resumed as a tool approval");
  await act(async () => { renderer = create(React.createElement(BrowserRail, props), { createNodeMock: element => element.props["aria-label"] === "Live browser page" ? viewportNode : null }); await tick(); });
  await act(async () => { button(renderer, "Start browser").props.onClick(); await tick(); });
  assert.equal(states.get("one").state, "active");
  assert.equal(renderer.root.findByProps({ "aria-label": "Browser back" }).props.disabled, true, "agent ownership disables manual actions");
  await emit("one", "state", states.get("one"), true);
  await emit("one", "frame", fixtureFrame("one"));
  await emit("one", "frame", fixtureFrame("one", { data: "c2Vjb25k", timestamp: 2 }));
  assert.equal(frames.size, 1, "frame arrivals have one pending render");
  await flushFrames();
  assert.equal(renderer.root.findByType("img").props.src, "data:image/jpeg;base64,c2Vjb25k", "superseded frames are dropped");
  await act(async () => { renderer.root.findByType("img").props.onLoad(); button(renderer, "Take control").props.onClick(); await tick(); });
  await act(async () => { pointer(renderer, "onPointerDown"); pointer(renderer, "onPointerMove", { clientX: 490 }); pointer(renderer, "onPointerUp", { clientX: 490 }); await tick(); });
  const pointerCalls = calls.filter(call => call.endpoint === "/actions" && call.body.action.type === "pointer");
  assert.deepEqual(pointerCalls.map(call => call.body.action.event), ["down", "move", "up"], "manual dragging keeps the gesture order");
  assert.equal(pointerCalls[0].body.action.x, 720); assert.equal(pointerCalls[0].body.action.y, 450);
  assert.equal(pointerCalls[1].body.action.x, 1080, "scaled movement uses actual page pixels");
  await act(async () => { pointer(renderer, "onWheel", { deltaX: 0, deltaY: 3, deltaMode: 1 }); await tick(); });
  assert.equal(calls.at(-1).body.action.delta_y, 48, "line scrolling is normalized to viewport pixels");
  await act(async () => {
    const live = renderer.root.findByProps({ "aria-label": "Live browser page" });
    live.props.onKeyDown({ key: "é", nativeEvent: {}, preventDefault() {} });
    live.props.onPaste({ clipboardData: { getData: () => "private paste" }, preventDefault() {} });
    await tick();
  });
  assert.deepEqual(calls.filter(call => call.body?.action?.type === "text").map(call => call.body.action.text), ["é", "private paste"]);
  await act(async () => { renderer.root.findByProps({ "aria-label": "Browser resolution" }).props.onChange({ target: { value: "phone" } }); await tick(); });
  assert.deepEqual(states.get("one").viewport, { width: 390, height: 844 });
  assert.equal(renderer.root.findAllByType("img").length, 0, "resize clears the old frame before further pointer input");
  await emit("one", "frame", fixtureFrame("one", { revision: 1, viewport: { width: 1440, height: 900 } })); await flushFrames();
  assert.equal(renderer.root.findAllByType("img").length, 0, "a late pre-resize frame cannot restore stale input");
  await emit("one", "frame", fixtureFrame("one")); await flushFrames();
  await act(async () => renderer.root.findByType("img").props.onLoad());
  await act(async () => { pointer(renderer, "onPointerDown"); pointer(renderer, "onPointerUp"); await tick(); });
  assert.ok(Math.abs(calls.at(-1).body.action.x - 195) < 0.001); assert.ok(Math.abs(calls.at(-1).body.action.y - 422) < 0.001, "portrait input accounts for horizontal letterboxing");
  await act(async () => { renderer.root.findAll(node => node.type === "button" && node.props.role === "tab")[1].props.onClick(); await tick(); });
  assert.equal(calls.at(-1).body.action.page_id, "page_b", "tab switching uses stable identity even with identical URLs");
  states.set("one", { ...states.get("one"), file_chooser: { multiple: true }, dialog: { type: "prompt", message: "Enter fixture", default_value: "initial" } });
  await emit("one", "state", states.get("one"));
  await act(async () => { renderer.root.findByProps({ "aria-label": "Page dialog response" }).props.onChange({ target: { value: "typed" } }); await tick(); });
  await act(async () => { button(renderer, "Accept").props.onClick(); await tick(); });
  assert.deepEqual(calls.at(-1).body.action, { type: "dialog", accept: true, prompt_text: "typed" });
  await act(async () => { renderer.root.find(node => node.type === "input" && node.props.type === "checkbox").props.onChange({ target: { checked: true } }); renderer.root.findByProps({ "aria-label": "Browser upload project paths" }).props.onChange({ target: { value: "files/fixture.txt" } }); });
  await act(async () => { button(renderer, "Upload selected files").props.onClick(); await tick(); });
  assert.deepEqual(calls.at(-1).body.action, { type: "upload", asset_ids: ["asset_file"], project_paths: ["files/fixture.txt"] }, "uploads express selected identities and scoped paths");
  await act(async () => button(renderer, "Reset").props.onClick());
  assert.equal(calls.filter(call => call.endpoint === "/reset").length, 0, "reset is reviewable before sign-ins are cleared");
  await act(async () => { button(renderer, "Clear sign-ins and reset").props.onClick(); await tick(); });
  assert.equal(calls.filter(call => call.endpoint === "/reset").length, 1);
  assert.equal(button(renderer, "Return to agent").props.disabled, false, "resetting Chrome cannot strand the paused task");
  await act(async () => { button(renderer, "Return to agent").props.onClick(); await tick(); });
  assert.equal(states.get("one").control, "agent", "a closed browser still supports the handoff return");
  states.set("one", { ...states.get("one"), state: "lost" });
  await emit("one", "state", states.get("one"));
  assert.equal(button(renderer, "Start browser").props.disabled, true, "worker loss cannot silently repeat a browser action");
  const resetsBeforeRecovery = calls.filter(call => call.endpoint === "/reset").length;
  await act(async () => { button(renderer, "Close").props.onClick(); await tick(); });
  assert.equal(states.get("one").state, "closed", "explicit Close acknowledges loss before a fresh session");
  assert.equal(calls.filter(call => call.endpoint === "/reset").length, resetsBeforeRecovery, "loss recovery does not erase sign-ins");
  const beforeHidden = calls.length;
  await act(async () => renderer.update(React.createElement(BrowserRail, { ...props, visible: false })));
  assert.equal(streams.size, 0, "hiding the rail disconnects streaming");
  assert.equal(calls.slice(beforeHidden).some(call => call.method === "DELETE"), false, "hiding never closes Chrome");
  states.set("one", state("one", { control: "user" }));
  await act(async () => { renderer.update(React.createElement(BrowserRail, props)); await tick(); });
  assert.equal(streams.size, 1, "reopening connects the same chat session");
  await emit("one", "state", states.get("one"));
  await act(async () => { renderer.update(React.createElement(BrowserRail, { ...props, threadId: "two" })); await tick(); });
  assert.equal(streams.has("one"), false); assert.equal(streams.has("two"), true);
  await emit("two", "state", states.get("two"));
  await emit("two", "frame", fixtureFrame("one")); await flushFrames();
  assert.equal(renderer.root.findAllByType("img").length, 0, "chat switching rejects former session frames");
  await act(async () => renderer.unmount());
  assert.ok(aborted >= 3); assert.equal(streams.size, 0); assert.equal(frames.size, 0);

  const activities = [];
  function Activity({ thread }) { useBrowserRailActivity(thread, true, active => activities.push(active)); return null; }
  await act(async () => { renderer = create(React.createElement(Activity, { thread: "one" })); await tick(); });
  assert.deepEqual(activities, [false, true], "background activity is observable without opening the dock");
  await act(async () => { for (const poll of intervals.values()) poll(); await tick(); });
  assert.deepEqual(activities, [false, true], "unchanged activity does not repeat notifications");
  states.set("one", state("one", { session_id: "replacement_session" }));
  await act(async () => { for (const poll of intervals.values()) poll(); await tick(); });
  assert.deepEqual(activities, [false, true], "new browsing leaves the dock preference unchanged");
  states.set("one", state("one", { state: "closed" }));
  await act(async () => { for (const poll of intervals.values()) poll(); await tick(); });
  assert.deepEqual(activities, [false, true, false], "closed sessions clear the activity indicator");
  await act(async () => renderer.unmount());
  assert.equal(intervals.size, 0);
  console.log("Browser rail identity, scaled input, handoff, files and visible-stream checks passed.");
} finally {
  if (renderer) await act(async () => renderer.unmount());
  globalThis.fetch = previousFetch;
  await vite.close();
}
