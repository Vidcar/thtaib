import assert from "node:assert/strict";
import path from "node:path";
import { fileURLToPath } from "node:url";
import React from "react";
import { act, create } from "react-test-renderer";
import { createServer } from "vite";
import { checkAgentSavedActions, checkKnowledgeSavedActions } from "./fixtures/knowledge-action-journeys.mjs";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;
globalThis.window = { setTimeout, clearTimeout, setInterval, clearInterval, workbench: { backendUrl: "http://127.0.0.1:8000" } };
const desktopRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const vite = await createServer({ root: desktopRoot, appType: "custom", server: { middlewareMode: true, hmr: false }, logLevel: "error" });
try {
  const { KnowledgePanel } = await vite.ssrLoadModule("/src/renderer/KnowledgePanel.tsx");
  await checkSelectedEntryOwnsVersionHistory(KnowledgePanel);
  await checkKnowledgeOwnershipAndReview(KnowledgePanel);
  await checkSkillResourceNavigation((await vite.ssrLoadModule("/src/renderer/SkillPackageControls.tsx")).SkillResources);
  await checkAgentDraftConflict((await vite.ssrLoadModule("/src/renderer/AgentSetupsPanel.tsx")).AgentSetupsPanel);
  await checkAgentSavedActions((await vite.ssrLoadModule("/src/renderer/AgentSetupsPanel.tsx")).AgentSetupsPanel);
  await checkKnowledgeSavedActions(KnowledgePanel);
  await checkConnectionCredentialsAndTest((await vite.ssrLoadModule("/src/renderer/ConnectionsPanel.tsx")).ConnectionsPanel);
  await checkFileReversalConflict((await vite.ssrLoadModule("/src/renderer/FileChangesPanel.tsx")).FileChangesPanel);
  await checkRunProposalConflict((await vite.ssrLoadModule("/src/renderer/RunMemoryProposals.tsx")).RunMemoryProposals);
  await checkLifecyclePreview((await vite.ssrLoadModule("/src/renderer/LifecycleAction.tsx")).LifecycleAction);
} finally { await vite.close(); }
console.log("Knowledge workspace checks passed.");

async function checkSkillResourceNavigation(Component) {
  const pending = [];
  globalThis.fetch = url => { const result = deferred(); pending.push({ url: new URL(String(url)), ...result }); return result.promise; };
  const resource = path => ({ path, size_bytes: 40 });
  let renderer;
  try {
    await act(async () => { renderer = create(React.createElement(Component, { versionId: "version-a", resources: [resource("guide.md")] })); });
    await act(async () => renderer.root.findByType("button").props.onClick());
    assert.match(text(renderer.root), /Loading file/);
    await act(async () => renderer.update(React.createElement(Component, { versionId: "version-b", resources: [resource("new.md"), resource("other.md")] })));
    assert.equal(pending.length, 1, "changing version cannot request the previous version's selected path");
    assert.doesNotMatch(text(renderer.root), /Loading file/, "an unselected version has no pending preview");
    await act(async () => { pending[0].resolve(json({ path: "guide.md", content: "OLD VERSION CONTENT", binary: false })); await tick(); });
    assert.doesNotMatch(text(renderer.root), /OLD VERSION CONTENT|Loading file/);
    await act(async () => renderer.root.findAllByType("button")[0].props.onClick());
    await act(async () => renderer.root.findAllByType("button")[1].props.onClick());
    assert.equal(pending[1].url.pathname, "/v1/knowledge/versions/version-b/resource");
    assert.equal(pending[1].url.searchParams.get("path"), "new.md");
    await act(async () => { pending[2].resolve(json({ path: "other.md", content: "CURRENT RESOURCE", binary: false })); await tick(); });
    await act(async () => { pending[1].resolve({ ok: false, status: 500, json: async () => ({ error: "STALE RESOURCE ERROR" }) }); await tick(); });
    assert.match(text(renderer.root), /CURRENT RESOURCE/);
    assert.doesNotMatch(text(renderer.root), /STALE RESOURCE ERROR|Loading file/);
    await act(async () => renderer.update(React.createElement(Component, { versionId: "version-c", resources: [] })));
    assert.doesNotMatch(text(renderer.root), /CURRENT RESOURCE|Loading file/);
  } finally { for (const item of pending) item.resolve(json({})); if (renderer) await act(async () => renderer.unmount()); }
}

async function checkSelectedEntryOwnsVersionHistory(KnowledgePanel) {
  const first = deferred();
  const entries = [entry("one", "First memory"), entry("two", "Second memory")];
  globalThis.fetch = async url => {
    const pathname = new URL(String(url)).pathname;
    if (pathname === "/v1/knowledge/entries") return json(entries);
    if (pathname === "/v1/knowledge/config") return json({ context_captures: { redaction_mode: "redact_secrets", retention_seconds: null }, scope_policies: {} });
    if (pathname === "/v1/knowledge/entries/one/versions") return first.promise;
    if (pathname === "/v1/knowledge/entries/two/versions") return json([{ ...entries[1], id: "two-version", entry_id: "two", content: "SECOND VERSION CONTENT" }]);
    if (["/v1/projects", "/v1/agent-setups", "/v1/knowledge/proposals", "/v1/knowledge/scopes"].includes(pathname)) return json([]);
    throw new Error(`unexpected fetch ${pathname}`);
  };
  let renderer;
  try {
    await act(async () => { renderer = create(React.createElement(KnowledgePanel)); await tick(); });
    const selectSecond = renderer.root.findAllByType("button").find(button => text(button).includes("Second memory"));
    await act(async () => { selectSecond.props.onClick(); await tick(); });
    assert.ok(text(renderer.root).includes("SECOND VERSION CONTENT"));
    await act(async () => { first.resolve(json([{ ...entries[0], id: "one-version", entry_id: "one", content: "STALE FIRST VERSION" }])); await tick(); });
    assert.ok(!text(renderer.root).includes("STALE FIRST VERSION"), "a late version response for the previous selection must not replace the current entry's history");
  } finally { if (renderer) await act(async () => renderer.unmount()); }
}

async function checkKnowledgeOwnershipAndReview(Component) {
  let entries = [entry("one", "First memory")];
  const calls = [];
  const scopes = [{ scope: "user", scope_id: null, label: "Personal", active: true }, { scope: "project", scope_id: "project_real", label: "Actual project", active: true }];
  const proposals = [{ id: "proposal", status: "pending", scope: "project", scope_id: "project_real", content: "Suggested content", display_name: "Useful fact", provenance: { actor: "agent", run_id: "run_origin" }, created_at: "2026-09-22T00:00:00Z" }];
  globalThis.fetch = async (url, init = {}) => {
    const path = new URL(String(url)).pathname; const body = init.body ? JSON.parse(init.body) : undefined;
    if (init.method) calls.push({ path, method: init.method, body });
    if (path === "/v1/knowledge/scopes") return json(scopes);
    if (path === "/v1/knowledge/proposals") return json(proposals);
    if (path === "/v1/knowledge/proposals/proposal/review") { proposals[0].status = body.decision === "accept" ? "accepted" : "rejected"; return json(proposals[0]); }
    if (path === "/v1/knowledge/config") return json({ context_captures: { redaction_mode: "redact_secrets" }, automatic_save_policies: [] });
    if (path === "/v1/knowledge/automatic-save-policy") return json({ context_captures: { redaction_mode: "redact_secrets" }, automatic_save_policies: [body] });
    if (path === "/v1/knowledge/entries" && init.method === "POST") { const next = { ...entry("created", body.display_name), ...body }; entries = [...entries, next]; return json(next); }
    if (path === "/v1/knowledge/entries") return json(entries);
    if (path.endsWith("/versions")) return json([]);
    if (path.endsWith("/delete-preview")) return json({ target_kind: "knowledge", target_id: "created", blockers: [], consumers: [], retained: ["Saved versions"] });
    if (path.endsWith("/edit")) return { ok: false, status: 409, json: async () => ({ error: "Version conflict: reload before saving." }) };
    if (path === "/v1/knowledge/entries/created" && init.method === "PATCH") { entries = entries.map(item => item.id === "created" ? { ...item, ...body } : item); return json(entries.at(-1)); }
    throw new Error(`unexpected ${path}`);
  };
  let renderer;
  try {
    await act(async () => { renderer = create(React.createElement(Component)); await tick(); });
    await act(async () => button(renderer, "New memory").props.onClick());
    await act(async () => field(renderer, "Use in", "select").props.onChange({ target: { value: "project" } }));
    assert.ok(text(field(renderer, "Project", "select")).includes("Actual project"));
    await act(async () => { field(renderer, "Project", "select").props.onChange({ target: { value: "project_real" } }); field(renderer, "Name (optional)", "input").props.onChange({ target: { value: "Scoped fact" } }); field(renderer, "Content", "textarea").props.onChange({ target: { value: "Remember this" } }); });
    await act(async () => { renderer.root.findByType("form").props.onSubmit({ preventDefault() {} }); await tick(); });
    const created = calls.find(call => call.path === "/v1/knowledge/entries" && call.method === "POST").body;
    assert.equal(created.scope_id, "project_real"); assert.equal(created.scope, "project"); assert.ok(!Object.hasOwn(created, "provenance"), "the desktop cannot forge actor or run provenance");
    await act(async () => { button(renderer, "Disable").props.onClick(); await tick(); });
    assert.equal(calls.some(call => call.method === "PATCH"), false, "disabling knowledge waits for the reviewed dependency preview");
    await act(async () => { button(renderer, "Disable entry").props.onClick(); await tick(); });
    assert.equal(calls.find(call => call.method === "PATCH").body.enabled, false);
    await act(async () => field(renderer, "Content", "textarea").props.onChange({ target: { value: "Unsaved human change" } }));
    await act(async () => { button(renderer, "Save").props.onClick(); await tick(); });
    assert.equal(calls.find(call => call.path.endsWith("/edit")).body.base_version, "created-version");
    assert.equal(field(renderer, "Content", "textarea").props.value, "Unsaved human change", "conflict must preserve the human draft");
    await act(async () => { button(renderer, "Accept").props.onClick(); await tick(); });
    assert.deepEqual(calls.find(call => call.path.endsWith("/review")).body, { decision: "accept" });
    await act(async () => field(renderer, "Destination", "select").props.onChange({ target: { value: "project:project_real" } }));
    await act(async () => { field(renderer, "Allow agents", "input").props.onChange({ target: { checked: true } }); await tick(); });
    assert.deepEqual(calls.find(call => call.path.endsWith("automatic-save-policy")).body, { scope: "project", scope_id: "project_real", automatic_agent_writes: true });
  } finally { if (renderer) await act(async () => renderer.unmount()); }
}

async function checkLifecyclePreview(Component) {
  const read = deferred(), mutation = deferred();
  const calls = [];
  let renderer, completed = 0, fail = false;
  globalThis.fetch = async (url, init = {}) => {
    calls.push({ path: new URL(String(url)).pathname, method: init.method ?? "GET" });
    if (init.method === "DELETE") return mutation.promise;
    if (fail) return { ok: false, status: 503, json: async () => ({ error: "Dependency report unavailable" }) };
    return read.promise;
  };
  const props = { path: "/v1/projects/real", name: "Real project", label: "Remove link", confirmLabel: "Confirm removal", onComplete: () => completed++ };
  try {
    await act(async () => { renderer = create(React.createElement(Component, props)); });
    await act(async () => { button(renderer, "Remove link").props.onClick(); await tick(); });
    assert.equal(button(renderer, "Confirm removal").props.disabled, true, "no mutation can run before the preview arrives");
    await act(async () => { read.resolve(json({ target_kind: "project", target_id: "real", summary: "Source files stay in place.", consumers: [{ kind: "chat", id: "chat", label: "Research conversation", retained: true, future_use: true, live: true, effect: "Future turns need an active project." }], retained: ["Source folder", "Saved conversation history"], blockers: [] })); await tick(); });
    assert.ok(text(renderer.root).includes("Research conversation"));
    assert.ok(text(renderer.root).includes("Future turns need an active project."));
    assert.ok(text(renderer.root).includes("Source folder"));
    assert.equal(calls.some(call => call.method === "DELETE"), false);
    await act(async () => { button(renderer, "Confirm removal").props.onClick(); button(renderer, "Confirm removal").props.onClick(); await tick(); });
    assert.equal(calls.filter(call => call.method === "DELETE").length, 1, "repeated confirmation sends one mutation");
    await act(async () => { mutation.resolve({ ok: false, status: 409, json: async () => ({ error: "A dependency changed. Refresh the preview." }) }); await tick(); });
    assert.equal(completed, 0, "a rejected deletion cannot be reported as complete");
    assert.ok(text(renderer.root).includes("A dependency changed"));
    fail = true;
    await act(async () => { button(renderer, "Refresh preview").props.onClick(); await tick(); });
    assert.equal(button(renderer, "Confirm removal").props.disabled, true, "failed refresh cannot leave a stale preview authorized");
    assert.ok(text(renderer.root).includes("Dependency report unavailable"));
  } finally { if (renderer) await act(async () => renderer.unmount()); }
}

async function checkAgentDraftConflict(Component) {
  const records = ["one", "two"].map(id => ({ id, name: `Agent ${id}`, current_version_id: `${id}-v1`, configuration: { instructions: `Original ${id}` }, active: true, missing_dependencies: [] }));
  let update;
  globalThis.fetch = async (url, init = {}) => {
    const path = new URL(String(url)).pathname;
    if (path === "/v1/agent-setups") return json(records);
    if (path === "/v1/agent-setups/one" && init.method === "PATCH") { update = JSON.parse(init.body); return { ok: false, status: 409, json: async () => ({ error: "Newer version exists." }) }; }
    if (path.endsWith("/versions")) return json([]);
    if (path === "/v1/agent-tools") return json({ enabled: [] });
    if (["/v1/deployments", "/v1/bundles", "/v1/profiles", "/v1/knowledge/entries", "/v1/connections"].includes(path)) return json([]);
    throw new Error(`unexpected ${path}`);
  };
  let renderer;
  try {
    await act(async () => { renderer = create(React.createElement(Component)); await tick(); });
    await act(async () => field(renderer, "Instructions", "textarea").props.onChange({ target: { value: "My draft" } }));
    await act(async () => { button(renderer, "Agent twoReusable setup").props.onClick(); await tick(); });
    await act(async () => { button(renderer, "Agent oneReusable setup · Unsaved changes").props.onClick(); await tick(); });
    assert.equal(field(renderer, "Instructions", "textarea").props.value, "My draft");
    await act(async () => { renderer.root.findByType("form").props.onSubmit({ preventDefault() {} }); await tick(); });
    assert.equal(update.base_version, "one-v1"); assert.equal(update.configuration.instructions, "My draft");
    assert.equal(field(renderer, "Instructions", "textarea").props.value, "My draft");
  } finally { if (renderer) await act(async () => renderer.unmount()); }
}

async function checkConnectionCredentialsAndTest(Component) {
  let record = { id: "connection_1", name: "Research", kind: "mcp", transport: "http", url: "https://example.test/mcp", enabled: true, version: 1, credential_present: false, tools: [] };
  const calls = [];
  globalThis.fetch = async (url, init = {}) => {
    const path = new URL(String(url)).pathname;
    if (path === "/v1/connections") return json([record]);
    calls.push({ path, method: init.method, body: init.body ? JSON.parse(init.body) : undefined });
    if (path.endsWith("/test")) record = { ...record, last_tested_at: "now", last_error: "Authentication required" };
    if (path.endsWith("/credential")) record = { ...record, credential_present: init.method === "PUT", version: 2 };
    return json(record);
  };
  let renderer;
  try {
    await act(async () => { renderer = create(React.createElement(Component)); await tick(); });
    await act(async () => { button(renderer, "Test").props.onClick(); await tick(); });
    assert.ok(text(renderer.root).includes("Authentication required"), "a 200 response with last_error is not a successful test");
    await act(async () => renderer.root.findAllByType("button").find(item => item.props.className === "connection-title").props.onClick());
    await act(async () => field(renderer, "Access token", "input").props.onChange({ target: { value: "fixture-secret-value" } }));
    await act(async () => { renderer.root.findByType("form").props.onSubmit({ preventDefault() {} }); await tick(); });
    assert.equal(calls.at(-1).body.secret, "fixture-secret-value");
    assert.equal(field(renderer, "Replace access token", "input").props.value, "", "the token input must clear after saving");
    assert.ok(!text(renderer.root).includes("fixture-secret-value"));
    await act(async () => button(renderer, "Edit").props.onClick());
    assert.equal(field(renderer, "Server URL", "input").props.disabled, true, "credentials cannot be silently redirected to another host");
  } finally { if (renderer) await act(async () => renderer.unmount()); }
}

async function checkFileReversalConflict(Component) {
  const held = deferred(); const calls = [];
  const change = { change: { id: "edit", run_id: "second", operation: "modified", path: "notes.txt", status: "changed", before: { exists: true, text: "before" }, after: { exists: true, text: "after" } }, diff: "-before\n+after", reversal_available: true, current_matches: true, note: "Only this file change is reversed." };
  globalThis.fetch = async (url, init = {}) => {
    const path = new URL(String(url)).pathname; calls.push(path);
    if (path.endsWith("/reverse")) return { ok: false, status: 409, json: async () => ({ error: "File changed since this run. Refresh before reversing." }) };
    if (path.includes("/first/")) return held.promise;
    return json([change]);
  };
  let renderer;
  try {
    await act(async () => { renderer = create(React.createElement(Component, { runIds: ["first"], currentRunId: "first" })); await tick(); });
    await act(async () => { renderer.update(React.createElement(Component, { runIds: ["first", "second"], currentRunId: "second" })); await tick(); });
    assert.ok(text(renderer.root).includes("notes.txt"));
    await act(async () => { held.resolve(json([{ ...change, change: { ...change.change, id: "stale", path: "stale.txt" } }])); await tick(); });
    assert.ok(!text(renderer.root).includes("stale.txt"), "old run file changes must not leak into the selected run");
    await act(async () => button(renderer, "Reverse this file change").props.onClick());
    assert.ok(!calls.some(path => path.endsWith("/reverse")), "show the concrete file reversal before submitting it");
    await act(async () => { button(renderer, "Reverse change").props.onClick(); await tick(); });
    assert.ok(text(renderer.root).includes("File changed since this run"));
    assert.ok(text(renderer.root).includes("+after"), "a conflict must not pretend the file was reversed");
  } finally { held.resolve(json([])); if (renderer) await act(async () => renderer.unmount()); }
}
function button(renderer, label) { const result = renderer.root.findAllByType("button").find(item => text(item).trim() === label); assert.ok(result, `expected button ${label}`); return result; }
async function checkRunProposalConflict(Component) {
  let requestedRun;
  globalThis.fetch = async (url, init = {}) => {
    const address = new URL(String(url));
    if (address.pathname.endsWith("/scopes")) return json([{ scope: "user", label: "Personal", active: true }]);
    if (address.pathname.endsWith("/review")) return { ok: false, status: 409, json: async () => ({ error: "A newer memory version exists." }) };
    requestedRun = address.searchParams.get("run_id");
    return json([{ id: "proposal", status: "pending", scope: "user", content: "Suggested change", entry_id: "entry", provenance: { actor: "agent" } }]);
  };
  let renderer;
  try {
    await act(async () => { renderer = create(React.createElement(Component, { runId: "run_selected", status: "completed", onOpenKnowledge() {} })); await tick(); });
    assert.equal(requestedRun, "run_selected", "the right panel must only review suggestions from its selected run");
    await act(async () => { button(renderer, "Accept memory").props.onClick(); await tick(); });
    assert.ok(text(renderer.root).includes("A newer memory version exists"));
    assert.ok(button(renderer, "Accept memory"), "a conflicted proposal must not be displayed as committed");
  } finally { if (renderer) await act(async () => renderer.unmount()); }
}
function field(renderer, label, type) { const result = renderer.root.findAllByType("label").find(item => text(item).startsWith(label)); assert.ok(result, `expected label ${label}`); return result.findByType(type); }
function entry(id, name) { return { id, display_name: name, scope: "user", scope_id: null, kind: "memory", content: `content ${id}`, current_version_id: `${id}-version`, provenance: { actor: "human" }, created_at: "2026-09-22T00:00:00Z", updated_at: "2026-09-22T00:00:00Z" }; }
function json(body) { return { ok: true, status: 200, json: async () => body }; }
function text(node) { return typeof node === "string" ? node : (node?.children ?? []).map(text).join(""); }
function deferred() { let resolve; const promise = new Promise(r => { resolve = r; }); return { promise, resolve }; }
async function tick() { await new Promise(resolve => setTimeout(resolve, 0)); }
