import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import React from "react";
import { act, create } from "react-test-renderer";
import { createServer } from "vite";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;
const desktopRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
// A disposable source fixture lets the same mounted assertions challenge the
// original defect without changing the working tree or weakening the check.
const sidebarFixture = process.env.STARTUP_CATALOGUE_SIDEBAR_FIXTURE;
const vite = await createServer({
  root: desktopRoot, appType: "custom", logLevel: "error",
  server: { middlewareMode: true, hmr: false },
  plugins: [{ name: "catalogue-test-boundaries", enforce: "pre", async load(id) {
    if (path.basename(id) === "AttentionPanel.tsx") return "export function AttentionButton() { return null; }";
    if (sidebarFixture && path.basename(id) === "WorkbenchSidebar.tsx") return readFile(sidebarFixture, "utf8");
    return null;
  } }],
});

async function checkExtendedFailure(Sidebar) {
  const fixture = new CatalogueFixture(Sidebar);
  fixture.responses.chats = () => unavailable("Chat catalogue unavailable");
  fixture.responses.projects = () => unavailable("Project catalogue unavailable");
  try {
    await fixture.mount();
    // Cross the former thirty-attempt boundary entirely in virtual time. Keep
    // this assertion first so the original source fails on false readiness.
    await fixture.clock.advance(300_000);
    assert.equal(fixture.ready.at(-1), false, "failed reads must remain unresolved beyond thirty failures");
    assert.ok(fixture.ready.every(value => value === false), "no failure may transiently mark the catalogue ready");
    for (const list of ["chats", "projects"]) {
      const calls = fixture.callsFor(list);
      assert.ok(calls.length > 30, `${list} keeps retrying beyond thirty failures`);
      assert.deepEqual(calls.slice(1, 6).map((call, index) => call.at - calls[index].at), [1000, 2000, 4000, 8000, 8000], `${list} increases delay to the eight-second cap`);
      assert.ok(calls.slice(4).every((call, index) => call.at - calls[index + 3].at === 8000), `${list} remains capped after sustained failure`);
    }
    assert.doesNotMatch(fixture.text(), /No chats yet|No projects yet/, "failed responses cannot authorize empty-list copy");
    assert.match(fixture.text(), /Chats: Chat catalogue unavailable/);
    assert.match(fixture.text(), /Projects: Project catalogue unavailable/);
    assert.equal(fixture.clock.timers.size, 2, "each unresolved list owns one retry");

    fixture.responses.chats = () => json([]);
    await fixture.clock.advance(8000);
    assert.equal(fixture.ready.at(-1), false, "one success does not mark both lists ready");
    assert.match(fixture.text(), /No chats yet/, "a successful empty chat response permits empty chat copy");
    assert.doesNotMatch(fixture.text(), /Chats:|No projects yet/);
    assert.match(fixture.text(), /Projects: Project catalogue unavailable/);
    assert.equal(fixture.clock.timers.size, 1);
    const chatReads = fixture.callsFor("chats").length;
    fixture.responses.projects = () => json([project("recovered-project")]);
    await fixture.clock.advance(8000);
    assert.equal(fixture.ready.at(-1), true, "late project recovery releases catalogue readiness");
    assert.match(fixture.text(), /recovered-project/);
    assert.doesNotMatch(fixture.text(), /Projects:|No projects yet/);
    assert.equal(fixture.clock.timers.size, 0, "success finishes both retry owners");
    await fixture.clock.advance(60_000);
    assert.equal(fixture.callsFor("chats").length, chatReads, "successful chats are not polled by project retries");
  } finally { await fixture.close(); }
}

async function checkIndependentLists(Sidebar, failedList) {
  const fixture = new CatalogueFixture(Sidebar);
  const successfulList = failedList === "chats" ? "projects" : "chats";
  const label = failedList === "chats" ? "Chats" : "Projects";
  try {
    await fixture.mount();
    assert.equal(fixture.ready.at(-1), false);
    assert.doesNotMatch(fixture.text(), /No chats yet|No projects yet/);
    await fixture.respond(fixture.take(failedList), unavailable("Still unavailable"));
    assert.match(fixture.text(), new RegExp(`${label}: Still unavailable`), "the first failure is already visible");
    // Resolve the successful list after the other list's error is rendered.
    await fixture.respond(fixture.take(successfulList), json([]));
    assert.match(fixture.text(), new RegExp(`${label}: Still unavailable`), "the other list's success cannot erase this failure");
    assert.equal(fixture.ready.at(-1), false);
    assert.doesNotMatch(fixture.text(), new RegExp(`No ${failedList} yet`));
    assert.match(fixture.text(), new RegExp(`No ${successfulList} yet`));
    await fixture.clock.advance(1000);
    await fixture.respond(fixture.take(failedList), json(failedList === "chats" ? [chat("recovered-chat")] : [project("recovered-project")]));
    assert.equal(fixture.ready.at(-1), true);
    assert.match(fixture.text(), /recovered-/);
    assert.doesNotMatch(fixture.text(), /Still unavailable/);
    assert.equal(fixture.callsFor(successfulList).length, 1, "recovery reads only its own catalogue");
    assert.equal(fixture.clock.timers.size, 0);
  } finally { await fixture.close(); }
}

async function checkInterruptedJsonRecovery(Sidebar) {
  const fixture = new CatalogueFixture(Sidebar);
  fixture.responses.chats = () => ({ ok: true, status: 200, json: async () => { throw new DOMException("Response interrupted", "AbortError"); } });
  fixture.responses.projects = () => json([]);
  try {
    await fixture.mount();
    assert.equal(fixture.ready.at(-1), false, "an interrupted successful response cannot establish catalogue readiness");
    assert.match(fixture.text(), /Chats: Response interrupted/, "body interruption remains a failed read");
    assert.doesNotMatch(fixture.text(), /No chats yet/);
    assert.equal(fixture.clock.timers.size, 1, "the failed body retains its retry owner");
    fixture.responses.chats = () => json([chat("body-recovered-chat")]);
    await fixture.clock.advance(1000);
    assert.equal(fixture.ready.at(-1), true);
    assert.match(fixture.text(), /body-recovered-chat/);
    assert.doesNotMatch(fixture.text(), /Response interrupted/);
    assert.equal(fixture.clock.timers.size, 0);
  } finally { await fixture.close(); }
}

async function checkResponseParsing(request, ApiError) {
  const originalFetch = globalThis.fetch;
  const originalWindow = globalThis.window;
  globalThis.window = { workbench: { backendUrl: "http://catalogue.test" } };
  try {
    const interrupted = new DOMException("Response interrupted", "AbortError");
    globalThis.fetch = async () => ({ ok: true, status: 200, json: async () => { throw interrupted; } });
    await assert.rejects(request("/v1/deployments"), failure => failure === interrupted, "a successful status cannot turn body failure into usable data");
    globalThis.fetch = async () => ({ ok: false, status: 409, json: async () => { throw new SyntaxError("No JSON error body"); } });
    await assert.rejects(request("/v1/deployments"), failure => failure instanceof ApiError && failure.status === 409, "an unreadable error body preserves HTTP rejection attribution");
    globalThis.fetch = async () => json({ detail: { code: "model_unavailable", message: "Model unavailable" } }, 409);
    await assert.rejects(request("/v1/deployments"), failure => failure instanceof ApiError && failure.status === 409 && failure.code === "model_unavailable" && failure.message === "Model unavailable");
    globalThis.fetch = async () => json([]);
    assert.deepEqual(await request("/v1/deployments"), [], "a genuine successful empty list remains usable");
  } finally { globalThis.fetch = originalFetch; globalThis.window = originalWindow; }
}

async function checkActionRecovery(Sidebar) {
  const fixture = new CatalogueFixture(Sidebar);
  const conversation = chat("archive-target");
  fixture.responses.chats = () => json([conversation]);
  fixture.responses.projects = () => unavailable("Project catalogue unavailable");
  const catalogueFetch = globalThis.fetch;
  let archiveAttempts = 0;
  globalThis.fetch = (url, init = {}) => {
    if (new URL(String(url)).pathname !== "/v1/chat/conversations/archive-target/archive") return catalogueFetch(url, init);
    assert.equal(init.method, "POST");
    assert.deepEqual(JSON.parse(init.body), { archived: true });
    archiveAttempts += 1;
    return Promise.resolve(archiveAttempts === 1 ? unavailable("Archive temporarily failed") : json({ ...conversation, archived: true }));
  };
  try {
    await fixture.mount();
    assert.equal(archiveAttempts, 0, "passive mount cannot archive a chat");
    await act(async () => { fixture.renderer.root.findByProps({ "aria-label": "Archive chat" }).props.onClick(); });
    assert.match(fixture.text(), /Archive temporarily failed/);
    assert.match(fixture.text(), /Projects: Project catalogue unavailable/);
    await act(async () => { fixture.renderer.root.findByProps({ "aria-label": "Archive chat" }).props.onClick(); });
    assert.equal(archiveAttempts, 2);
    assert.doesNotMatch(fixture.text(), /Archive temporarily failed|archive-target/, "successful retry clears its action error and archives the row");
    assert.match(fixture.text(), /Projects: Project catalogue unavailable/, "action recovery cannot erase the independent catalogue failure");
    assert.equal(fixture.ready.at(-1), false);
    assert.equal(fixture.clock.timers.size, 1, "the unresolved project catalogue keeps its retry");
  } finally { await fixture.close(); }
}

async function checkTimerReplacement(Sidebar, owner) {
  const fixture = new CatalogueFixture(Sidebar);
  const list = owner === "project" ? "projects" : "chats";
  const other = list === "chats" ? "projects" : "chats";
  fixture.responses.chats = () => json([]);
  fixture.responses.projects = () => json([]);
  try {
    await fixture.mount();
    assert.equal(fixture.ready.at(-1), true);
    fixture.responses[list] = () => unavailable("Obsolete failure");
    await fixture.changeOwner(owner);
    assert.equal(fixture.ready.at(-1), false, `${owner} replacement invalidates previous empty success`);
    assert.doesNotMatch(fixture.text(), new RegExp(`No ${list} yet`));
    assert.equal(fixture.clock.timers.size, 1);
    const obsoleteTimers = [...fixture.clock.timers.keys()];
    fixture.responses[list] = null;
    await fixture.changeOwner(owner);
    assert.ok(obsoleteTimers.every(id => !fixture.clock.timers.has(id)), `${owner} change removes the former retry timer`);
    assert.equal(fixture.clock.timers.size, 0);
    assert.doesNotMatch(fixture.text(), /Obsolete failure/, "replacement owns its own failure state");
    const replacement = fixture.take(list);
    await fixture.clock.advance(16_000);
    assert.equal(fixture.pending.length, 0, "obsolete retry cannot issue another read while the replacement is pending");
    assert.equal(fixture.callsFor(other).length, 1, `${owner} does not invalidate the independent list`);
    await fixture.respond(replacement, json([]));
    assert.equal(fixture.ready.at(-1), true);
    assert.match(fixture.text(), new RegExp(`No ${list} yet`), "only the replacement's empty response restores empty copy");
  } finally { await fixture.close(); }
}

async function checkLateResponse(Sidebar, owner, outcome, replacementFirst) {
  const fixture = new CatalogueFixture(Sidebar);
  const list = owner === "project" ? "projects" : "chats";
  const entry = list === "chats" ? chat : project;
  fixture.responses.chats = () => json([chat("saved-chat")]);
  fixture.responses.projects = () => json([project("saved-project")]);
  try {
    await fixture.mount();
    fixture.responses[list] = null;
    await fixture.changeOwner(owner);
    const obsolete = fixture.take(list);
    await fixture.changeOwner(owner);
    const replacement = fixture.take(list);
    assert.equal(fixture.ready.at(-1), false);
    assert.match(fixture.text(), new RegExp(list === "chats" ? "saved-chat" : "saved-project"), "a replacement read retains useful saved rows");
    if (replacementFirst) await fixture.respond(replacement, json([entry("replacement-row")]));
    const readinessBeforeLateResult = [...fixture.ready];
    if (outcome === "success") await fixture.respond(obsolete, json([entry("obsolete-row")]));
    else await fixture.reject(obsolete, new Error("Obsolete network rejection"));
    assert.deepEqual(fixture.ready, readinessBeforeLateResult, `${owner} late ${outcome} cannot change replacement readiness`);
    assert.doesNotMatch(fixture.text(), /obsolete-row|Obsolete network rejection/, `${owner} late ${outcome} cannot overwrite replacement state`);
    assert.equal(fixture.clock.timers.size, 0, "an obsolete rejection cannot schedule another retry");
    if (!replacementFirst) await fixture.respond(replacement, json([entry("replacement-row")]));
    assert.equal(fixture.ready.at(-1), true);
    assert.match(fixture.text(), /replacement-row/);
    await fixture.clock.advance(16_000);
    assert.equal(fixture.pending.length, 0);
    if (owner === "archived") assert.deepEqual(fixture.callsFor("chats").map(call => call.archived), [false, true, false], "archive selection reaches the actual lightweight request boundary");
  } finally { await fixture.close(); }
}

async function checkUnmount(Sidebar) {
  const failed = new CatalogueFixture(Sidebar);
  failed.responses.chats = failed.responses.projects = () => unavailable("Unavailable");
  try {
    await failed.mount();
    assert.equal(failed.clock.timers.size, 2);
    await failed.unmount();
    assert.equal(failed.clock.timers.size, 0, "unmount cancels both pending retries immediately");
    const readCount = failed.calls.length;
    await failed.clock.advance(60_000);
    assert.equal(failed.calls.length, readCount, "disposed owners perform no reads");
  } finally { await failed.close(); }
  for (const rejectedList of ["chats", "projects"]) {
    const held = new CatalogueFixture(Sidebar);
    try {
      await held.mount();
      const chats = held.take("chats"), projects = held.take("projects");
      await held.unmount();
      const priorReadiness = [...held.ready];
      await held.reject(rejectedList === "chats" ? chats : projects, new Error("Late disposal rejection"));
      await held.respond(rejectedList === "chats" ? projects : chats, json([]));
      assert.equal(held.clock.timers.size, 0, "late in-flight failure cannot resurrect a disposed retry owner");
      assert.deepEqual(held.ready, priorReadiness, "late in-flight success cannot publish readiness after unmount");
      await held.clock.advance(60_000);
      assert.equal(held.calls.length, 2);
    } finally { await held.close(); }
  }
}

class FakeClock {
  now = 0;
  nextId = 0;
  timers = new Map();
  setTimeout = (callback, delay = 0, ...args) => {
    const id = ++this.nextId;
    this.timers.set(id, { at: this.now + Number(delay), callback: () => callback(...args) });
    return id;
  };
  clearTimeout = id => { this.timers.delete(id); };
  async advance(milliseconds) {
    const target = this.now + milliseconds;
    let callbacks = 0;
    while (true) {
      const next = [...this.timers].filter(([, timer]) => timer.at <= target).sort((a, b) => a[1].at - b[1].at || a[0] - b[0])[0];
      if (!next) break;
      assert.ok(++callbacks < 1000, "virtual clock must not encounter an unbounded immediate retry loop");
      this.now = next[1].at;
      this.timers.delete(next[0]);
      await act(async () => { next[1].callback(); });
    }
    this.now = target;
  }
}

class CatalogueFixture {
  clock = new FakeClock();
  calls = [];
  pending = [];
  ready = [];
  responses = { chats: null, projects: null };
  props = {
    tab: "chat", collapsed: false, width: 232, backendOk: true, backendStatus: "Reading saved lists",
    activeConversationId: null, historyRevision: 0, projectRevision: 0,
    onCollapsedChange() {}, onWidthChange() {}, onNavigate() {}, onOpenConversation() {},
    onNewChat() {}, onAddProject() {}, onHistoryNotice() {}, onListsReady: value => { this.ready.push(value); },
  };
  constructor(Sidebar) {
    this.Sidebar = Sidebar;
    this.originals = { fetch: globalThis.fetch, window: globalThis.window, setTimeout: globalThis.setTimeout, clearTimeout: globalThis.clearTimeout };
    globalThis.window = Object.assign(new EventTarget(), { workbench: { backendUrl: "http://catalogue.test" }, setTimeout: this.clock.setTimeout, clearTimeout: this.clock.clearTimeout });
    globalThis.setTimeout = this.clock.setTimeout;
    globalThis.clearTimeout = this.clock.clearTimeout;
    globalThis.fetch = (url, init = {}) => {
      const address = new URL(String(url));
      assert.equal(init.method ?? "GET", "GET", "passive catalogue reads cannot submit work or load a model");
      const list = address.pathname === "/v1/chat/conversations" ? "chats" : address.pathname === "/v1/projects" ? "projects" : null;
      assert.ok(list, `unexpected catalogue request: ${address.pathname}`);
      const call = { list, at: this.clock.now, archived: address.searchParams.get("include_archived") === "true" };
      this.calls.push(call);
      if (this.responses[list]) return Promise.resolve(this.responses[list](call));
      return new Promise((resolve, reject) => { this.pending.push({ ...call, resolve, reject }); });
    };
  }
  callsFor(list) { return this.calls.filter(call => call.list === list); }
  text() { return textOf(this.renderer.toJSON()); }
  async mount() { await act(async () => { this.renderer = create(React.createElement(this.Sidebar, this.props)); }); }
  async unmount() { if (this.renderer) { await act(async () => { this.renderer.unmount(); }); this.renderer = null; } }
  async changeOwner(owner) {
    await act(async () => {
      if (owner === "archived") {
        const checkbox = this.renderer.root.findByProps({ "aria-label": "Show archived" });
        checkbox.props.onChange({ target: { checked: !checkbox.props.checked } });
      } else {
        this.props = { ...this.props, [owner === "history" ? "historyRevision" : "projectRevision"]: this.props[owner === "history" ? "historyRevision" : "projectRevision"] + 1 };
        this.renderer.update(React.createElement(this.Sidebar, this.props));
      }
    });
  }
  take(list) {
    const index = this.pending.findIndex(call => call.list === list);
    assert.ok(index >= 0, `expected a pending ${list} read`);
    return this.pending.splice(index, 1)[0];
  }
  async respond(call, response) { await act(async () => { call.resolve(response); }); }
  async reject(call, error) { await act(async () => { call.reject(error); }); }
  async close() { try { await this.unmount(); } finally { Object.assign(globalThis, this.originals); } }
}

function json(body, status = 200) { return { ok: status < 400, status, json: async () => body }; }
function unavailable(message) { return json({ error: message }, 503); }
function chat(title) { return { id: title, title, updated_at: "2026-09-29T12:00:00Z", archived: false }; }
function project(name) { return { id: name, name, path: `D:\\Isolated\\${name}`, missing: false }; }
function textOf(node) {
  if (typeof node === "string") return node;
  if (Array.isArray(node)) return node.map(textOf).join("");
  return (node?.children ?? []).map(textOf).join("");
}

try {
  const { WorkbenchSidebar } = await vite.ssrLoadModule("/src/renderer/WorkbenchSidebar.tsx");
  const { request, ApiError } = await vite.ssrLoadModule("/src/renderer/api.ts");
  // Finish the loader's background optimizer before replacing process timers.
  // Otherwise its delayed logging can be mistaken for a catalogue retry.
  await vite.close();
  await checkResponseParsing(request, ApiError);
  await checkExtendedFailure(WorkbenchSidebar);
  await checkIndependentLists(WorkbenchSidebar, "chats");
  await checkIndependentLists(WorkbenchSidebar, "projects");
  await checkInterruptedJsonRecovery(WorkbenchSidebar);
  await checkActionRecovery(WorkbenchSidebar);
  for (const owner of ["archived", "history", "project"]) {
    await checkTimerReplacement(WorkbenchSidebar, owner);
    for (const outcome of ["success", "rejection"]) {
      await checkLateResponse(WorkbenchSidebar, owner, outcome, false);
      await checkLateResponse(WorkbenchSidebar, owner, outcome, true);
    }
  }
  await checkUnmount(WorkbenchSidebar);
  console.log("Startup catalogue checks passed: response interruption, extended failure, capped backoff, independent recovery, owner replacement and disposal.");
} finally {
  await vite.close();
}
