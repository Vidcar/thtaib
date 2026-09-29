import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import React, { StrictMode } from "react";
import { act } from "react-test-renderer";
import { createServer } from "vite";
import { makeHarness, renderChat, closeHarness, ChatHarness, ErrorBoundary, textOf, json, deferred } from "./check-chat-interaction-boundaries.mjs";

const desktopRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const sourceFixture = process.env.CHAT_PANEL_SOURCE_OVERRIDE;
const vite = await createServer({
  root: desktopRoot, appType: "custom", logLevel: "error", server: { middlewareMode: true, hmr: false },
  plugins: sourceFixture ? [{ name: "chat-startup-source-fixture", enforce: "pre", load(id) {
    if (id.replaceAll("\\", "/").endsWith("/src/renderer/ChatPanel.tsx")) return readFileSync(sourceFixture, "utf8");
  } }] : [],
});
const modules = new Map();
for (const name of ["ChatPanel", "WorkbenchSidebar"]) modules.set(`/src/renderer/${name}.tsx`, await vite.ssrLoadModule(`/src/renderer/${name}.tsx`));
// Vite's own optimizer timers must not become application clock observations.
await vite.close();
const loader = { ssrLoadModule: name => modules.get(name) };
const { ChatPanel } = modules.get("/src/renderer/ChatPanel.tsx");

class FakeClock {
  now = 0;
  nextId = 0;
  timers = new Map();
  setTimeout = (callback, delay = 0, ...args) => this.schedule(callback, delay, args, false);
  setInterval = (callback, delay = 0, ...args) => this.schedule(callback, delay, args, true);
  clearTimeout = id => { this.timers.delete(id); };
  clearInterval = this.clearTimeout;
  schedule(callback, delay, args, interval) {
    const id = { id: ++this.nextId, unref() { return this; }, ref() { return this; } };
    this.timers.set(id, { at: this.now + Number(delay), callback: () => callback(...args), interval: interval ? Math.max(1, Number(delay)) : 0 });
    return id;
  }
  tick(milliseconds) {
    const target = this.now + milliseconds;
    let count = 0;
    while (true) {
      const next = [...this.timers].filter(([, timer]) => timer.at <= target).sort((a, b) => a[1].at - b[1].at || a[0].id - b[0].id)[0];
      if (!next) break;
      assert.ok(++count < 10000, "bounded virtual timer callbacks");
      this.now = next[1].at;
      if (next[1].interval) next[1].at += next[1].interval;
      else this.timers.delete(next[0]);
      next[1].callback();
    }
    this.now = target;
  }
}
let clock;

async function settle() {
  await act(async () => {
    clock.tick(0);
    for (let i = 0; i < 12; i++) await new Promise(resolve => setImmediate(resolve));
  });
}
async function until(assertion, label) {
  let failure;
  for (let i = 0; i < 160; i++) {
    await settle();
    try { return assertion(); } catch (error) { failure = error; }
  }
  throw new Error(`${label}: ${failure?.message ?? "condition not reached"}`);
}
async function advance(milliseconds) { await act(async () => { clock.tick(milliseconds); }); await settle(); }
function panelText(renderer) { return textOf(renderer.root.findByType(ChatPanel)); }
async function updatePanel(renderer, props) {
  const harness = renderer.root.findByType(ChatHarness);
  await act(async () => renderer.update(React.createElement(StrictMode, null, React.createElement(ErrorBoundary, null,
    React.createElement(ChatHarness, { ...harness.props, panelProps: { ...harness.props.panelProps, ...props } })))));
  await settle();
}
async function withFixture(options, check) {
  clock = new FakeClock();
  const originals = Object.fromEntries(["setTimeout", "clearTimeout", "setInterval", "clearInterval"].map(key => [key, globalThis[key]]));
  for (const key of Object.keys(originals)) globalThis[key] = clock[key];
  const harness = makeHarness(options);
  let renderer;
  try { renderer = await renderChat(loader, harness, { activeTab: "chat" }); await check(renderer, harness); }
  finally {
    try {
      if (renderer) await closeHarness(renderer, harness);
      const disposedReads = harness.state.outgoingRequests.length;
      await advance(60000);
      assert.equal(harness.state.outgoingRequests.length, disposedReads, "unmount cancels reads and late failures cannot restart them");
    } finally { Object.assign(globalThis, originals); }
  }
}

await withFixture({ requestOverride({ req, res, url }) {
  if (req.method === "GET" && url.pathname === "/v1/deployments") { json(res, 503, { error: "Model status unavailable" }); return true; }
} }, async renderer => {
  await until(() => assert.match(panelText(renderer), /Model status unavailable/), "initial failed model read");
  assert.doesNotMatch(panelText(renderer), /Your workspace for local AI/, "failed model reads cannot establish an empty workspace");
});

{
  let failModels = true, failFiles = true, modelReads = 0, fileReads = 0;
  await withFixture({ conversationListError: { status: 503, message: "History unavailable" }, requestOverride({ req, res, url }) {
    if (req.method !== "GET") return;
    if (url.pathname === "/v1/deployments") { modelReads++; json(res, failModels ? 503 : 200, failModels ? { error: "Model status unavailable" } : []); return true; }
    if (url.pathname === "/v1/bundles") { fileReads++; json(res, failFiles ? 503 : 200, failFiles ? { error: "Model files unavailable" } : []); return true; }
  } }, async (renderer, harness) => {
    await until(() => assert.match(panelText(renderer), /Model files unavailable/), "independent startup errors");
    for (const delay of [1000, 2000, 4000, ...Array(34).fill(8000)]) {
      const prior = harness.state.consumedResponses.filter(item => item.path === "/v1/bundles").length;
      await advance(delay);
      await until(() => assert.ok(harness.state.consumedResponses.filter(item => item.path === "/v1/bundles").length > prior), "retry response consumed before advancing the clock");
    }
    assert.ok(modelReads > 30 && fileReads > 30, `failed initial reads keep retrying beyond thirty failures (models=${modelReads}, files=${fileReads})`);
    assert.match(panelText(renderer), /Models: Model status unavailable/);
    assert.match(panelText(renderer), /Model files: Model files unavailable/);
    assert.doesNotMatch(panelText(renderer), /Your workspace for local AI/);
    failModels = false;
    harness.state.conversationListError = null;
    await advance(8000);
    await until(() => assert.doesNotMatch(panelText(renderer), /Models:|History unavailable/), "model and history reads recover automatically");
    assert.match(panelText(renderer), /Model files: Model files unavailable/, "one resource cannot clear another failure");
    assert.doesNotMatch(panelText(renderer), /Your workspace for local AI/);
    failFiles = false;
    await advance(8000);
    await until(() => assert.match(panelText(renderer), /Your workspace for local AI/), "only successful empty catalogues permit empty copy");
    assert.doesNotMatch(panelText(renderer), /Model files unavailable|History unavailable|Model status unavailable/);
    const verifiedFileReads = fileReads;
    await advance(60000);
    assert.equal(fileReads, verifiedFileReads, "successful static catalogues do not keep polling");
    const starts = harness.state.outgoingRequests.filter(item => item.method === "POST" && /\/start$|\/commands$/.test(item.path));
    assert.deepEqual(starts, [], "passive failure recovery never starts a model or run");
  });
}

{
  let fail = true, reads = 0;
  await withFixture({ requestOverride({ req, res, url }) {
    if (req.method === "GET" && url.pathname === "/v1/bundles") { reads++; json(res, fail ? 503 : 200, fail ? { error: "Files temporarily unavailable" } : []); return true; }
  } }, async renderer => {
    await until(() => assert.match(panelText(renderer), /Files temporarily unavailable/), "failed read owns retry");
    await updatePanel(renderer, { activeTab: "models" });
    const inactiveReads = reads;
    await advance(60000);
    assert.equal(reads, inactiveReads, "inactive Chat cancels obsolete read retries");
    fail = false;
    await updatePanel(renderer, { activeTab: "chat" });
    await until(() => assert.doesNotMatch(panelText(renderer), /Files temporarily unavailable/), "reactivation acquires a fresh read owner");
    assert.ok(reads > inactiveReads);
  });
}

for (const oldFailure of [false, true]) {
  const barrier = deferred();
  let firstGeneration = true, held = 0, reads = 0;
  await withFixture({ requestOverride: async ({ req, res, url }) => {
    if (req.method !== "GET" || url.pathname !== "/v1/bundles") return;
    reads++;
    if (firstGeneration) {
      held++;
      await barrier.promise;
      json(res, oldFailure ? 503 : 200, oldFailure ? { error: "Obsolete file error" } : [{ id: "obsolete", display_name: "Obsolete model", status: "ready", primary_path: "old.gguf", disk_matches: true }]);
    } else json(res, 200, []);
    return true;
  }, deployments: [] }, async renderer => {
    await until(() => assert.ok(held > 0), "initial model files request held");
    firstGeneration = false;
    await updatePanel(renderer, { activeTab: "models" });
    await updatePanel(renderer, { activeTab: "chat" });
    await until(() => assert.match(panelText(renderer), /Your workspace for local AI/), "replacement empty response verified");
    await act(async () => barrier.resolve());
    await settle();
    assert.match(panelText(renderer), /Your workspace for local AI/, "obsolete success cannot overwrite replacement model files");
    assert.doesNotMatch(panelText(renderer), /Obsolete file error/);
    const settledReads = reads;
    await advance(60000);
    assert.equal(reads, settledReads, "obsolete failure cannot schedule retries for a replacement owner");
  });
}

{
  let failProjects = true, failAgents = true;
  await withFixture({ requestOverride({ req, res, url }) {
    if (req.method !== "GET") return;
    if (url.pathname === "/v1/projects" && failProjects) { json(res, 503, { error: "Projects unavailable" }); return true; }
    if (url.pathname === "/v1/agent-setups" && failAgents) { json(res, 503, { error: "Agents unavailable" }); return true; }
  } }, async renderer => {
    await until(() => {
      assert.match(panelText(renderer), /Projects: Projects unavailable/);
      assert.match(panelText(renderer), /Agents: Agents unavailable/);
    }, "project and agent reads own independent failures");
    failProjects = false;
    await advance(1000);
    await until(() => assert.doesNotMatch(panelText(renderer), /Projects: Projects unavailable/), "project recovery");
    assert.match(panelText(renderer), /Agents: Agents unavailable/);
    failAgents = false;
    await advance(2000);
    await until(() => assert.doesNotMatch(panelText(renderer), /Agents: Agents unavailable/), "agent recovery");
  });
}

{
  let failDefaults = true;
  await withFixture({ requestOverride({ req, res, url, body }) {
    if (req.method !== "POST" || url.pathname !== "/v1/setup-resolution") return;
    const input = JSON.parse(body);
    if (input.project_id || input.agent_setup_version_id || Object.keys(input.overrides ?? {}).length) return;
    json(res, failDefaults ? 503 : 200, failDefaults ? { error: "Defaults unavailable" } : {
      configuration: { approval_mode: "full_access" }, instruction_layers: [],
    });
    return true;
  } }, async (renderer, harness) => {
    await until(() => assert.match(panelText(renderer), /Defaults: Defaults unavailable/), "defaults failure remains explicit");
    const open = renderer.root.findAll(node => node.type === "button" && textOf(node) === "Conversation A")[0];
    assert.ok(open);
    await act(async () => open.props.onClick());
    await until(() => assert.ok(harness.state.requests.registers.length), "saved conversation has a different selection owner");
    const asksForAccess = () => renderer.root.findAll(node => node.type === "button" && node.props.role === "radio" && node.props["aria-label"] === "Ask").some(node => node.props["aria-checked"] === true);
    await until(() => assert.equal(asksForAccess(), true), "restored chat access observed");
    failDefaults = false;
    await advance(1000);
    await until(() => assert.doesNotMatch(panelText(renderer), /Defaults: Defaults unavailable/), "defaults recover without manual retry");
    assert.equal(asksForAccess(), true, "late initial defaults cannot overwrite the selected chat");
  });
}

for (const explicitAsk of [false, true]) {
  let failDefaults = true;
  await withFixture({ deployments: [{ id: "dep_1", scope: "connected", status: "running", display_name: "Connected test", health: { healthy: true }, settings: { startup: { requested: {} }, per_request: { requested: {} }, agent: { requested: {} } } }], requestOverride({ req, res, url, body }) {
    if (req.method !== "POST" || url.pathname !== "/v1/setup-resolution") return;
    const input = JSON.parse(body);
    if (input.project_id || input.agent_setup_version_id || Object.keys(input.overrides ?? {}).length) return;
    json(res, failDefaults ? 503 : 200, failDefaults ? { error: "Defaults unavailable" } : {
      configuration: { approval_mode: "full_access" }, instruction_layers: [],
    });
    return true;
  } }, async (renderer, harness) => {
    await until(() => assert.match(panelText(renderer), /Defaults: Defaults unavailable/), "initial defaults remain unresolved");
    const askControl = () => renderer.root.findAll(node => node.type === "button" && node.props.role === "radio" && node.props["aria-label"] === "Ask")[0];
    if (explicitAsk) await act(async () => askControl().props.onClick());
    failDefaults = false;
    await advance(1000);
    await until(() => assert.doesNotMatch(panelText(renderer), /Defaults: Defaults unavailable/), "untouched defaults recover with a sole healthy model");
    assert.equal(askControl().props["aria-checked"], explicitAsk, explicitAsk
      ? "recovered defaults preserve an explicit Access choice"
      : "passive model fallback cannot discard recovered application defaults");
    assert.deepEqual(harness.state.outgoingRequests.filter(item => item.method === "POST" && /\/start$|\/commands$/.test(item.path)), [], "defaults recovery remains passive");
  });
}

console.log("Mounted Chat startup reads: truthful empty state, independent sustained recovery, passive reads and obsolete-owner cancellation passed.");
