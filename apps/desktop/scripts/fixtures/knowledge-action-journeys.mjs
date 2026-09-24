import assert from "node:assert/strict";
import React from "react";
import { act, create } from "react-test-renderer";

const text = node => typeof node === "string" ? node : (node?.children ?? []).map(text).join("");
const json = value => ({ ok: true, status: 200, json: async () => structuredClone(value) });
const failure = message => ({ ok: false, status: 409, json: async () => ({ error: message }) });
const tick = () => new Promise(resolve => setTimeout(resolve, 0));
const settle = async work => { await act(async () => { await work?.(); await tick(); }); };
function button(root, label) { const node = root.findAllByType("button").find(item => text(item).trim() === label); assert.ok(node, `button ${label}`); return node; }
function field(root, label, type) { const row = root.findAllByType("label").find(item => text(item).startsWith(label)); assert.ok(row, `field ${label}`); return row.props.htmlFor ? root.find(node => node.type === type && node.props.id === row.props.htmlFor) : row.findByType(type); }
const change = (root, label, type, value) => settle(() => field(root, label, type).props.onChange({ target: { value } }));
const click = (root, label) => settle(() => button(root, label).props.onClick());
const submit = root => settle(() => root.findByType("form").props.onSubmit({ preventDefault() {} }));
const preview = id => ({ target_id: id, consumers: [], retained: ["Historical versions"], blockers: [] });
const when = "2026-09-23T12:00:00Z";

export async function checkAgentSavedActions(Component) {
  let records = [], serial = 0, rejectCreate = true;
  const history = new Map(), calls = [], used = [];
  function save(id, body) {
    const current = { id, name: body.name, role: body.role, configuration: body.configuration, current_version_id: `agent-version-${++serial}`, active: true, missing_dependencies: [] };
    history.set(id, [...history.get(id) ?? [], { ...current, id: current.current_version_id, agent_setup_id: id, created_at: when }]);
    records = [...records.filter(item => item.id !== id), current]; return current;
  }
  globalThis.fetch = async (url, init = {}) => {
    const path = new URL(String(url)).pathname, method = init.method ?? "GET", body = init.body ? JSON.parse(init.body) : undefined;
    if (method !== "GET") calls.push({ path, method, body });
    if (path === "/v1/setup-resolution") return json({ configuration: body.overrides, effective_values: {}, instruction_layers: [] });
    if (path === "/v1/agent-setups" && method === "GET") return json(records.filter(item => item.active));
    if (path === "/v1/agent-setups" && method === "POST") { if (rejectCreate) return failure("Agent save failed; retry safely."); return json(save("agent-original", body)); }
    const match = path.match(/^\/v1\/agent-setups\/([^/]+)(?:\/(.+))?$/);
    if (match) {
      const [, id, action] = match;
      if (action === "versions") return json(history.get(id) ?? []);
      if (action === "delete-preview") return json(preview(id));
      if (action === "duplicate") return json(save("agent-copy", { ...records.find(item => item.id === id), name: "Reader copy" }));
      if (method === "PATCH") { assert.equal(body.base_version, records.find(item => item.id === id).current_version_id); return json(save(id, body)); }
      if (method === "DELETE") { records = records.map(item => item.id === id ? { ...item, active: false } : item); return json(records.find(item => item.id === id)); }
    }
    if (path === "/v1/agent-tools") return json({ enabled: [] });
    if (["/v1/deployments", "/v1/bundles", "/v1/profiles", "/v1/knowledge/entries", "/v1/connections"].includes(path)) return json([]);
    throw new Error(`Unexpected agent request ${method} ${path}`);
  };
  let renderer;
  try {
    await settle(() => { renderer = create(React.createElement(Component, { onUse: item => used.push(item) })); });
    await change(renderer.root, "Name", "input", "Reader");
    await change(renderer.root, "Purpose", "input", "Compare source material");
    await change(renderer.root, "Instructions", "textarea", "Read precisely.");
    await submit(renderer.root);
    assert.match(text(renderer.root), /Agent save failed/);
    assert.equal(field(renderer.root, "Name", "input").props.value, "Reader", "failed creation preserves the complete draft");
    rejectCreate = false;
    await submit(renderer.root);
    assert.equal(records.length, 1); assert.equal(records[0].configuration.instructions, "Read precisely.");
    await change(renderer.root, "Instructions", "textarea", "Read and cite evidence.");
    await submit(renderer.root);
    const savedVersion = records[0].current_version_id;
    await click(renderer.root, "Use in Chat");
    assert.equal(used[0].current_version_id, savedVersion); assert.equal(used[0].configuration.instructions, "Read and cite evidence.");
    await settle(() => renderer.unmount());
    await settle(() => { renderer = create(React.createElement(Component, { onUse: item => used.push(item) })); });
    assert.equal(field(renderer.root, "Instructions", "textarea").props.value, "Read and cite evidence.", "reopening reads saved content");
    await click(renderer.root, "Load into editor");
    assert.equal(field(renderer.root, "Instructions", "textarea").props.value, "Read precisely.");
    assert.equal(records[0].current_version_id, savedVersion, "loading history alone is not a saved mutation");
    await submit(renderer.root);
    assert.equal(history.get("agent-original").length, 3);
    assert.equal(calls.filter(call => call.method === "PATCH").at(-1).body.base_version, savedVersion);
    await click(renderer.root, "Duplicate");
    assert.equal(records.length, 2); assert.equal(field(renderer.root, "Name", "input").props.value, "Reader copy");
    await click(renderer.root, "Remove agent");
    assert.equal(calls.filter(call => call.method === "DELETE").length, 0);
    await click(renderer.root, "Remove agent");
    assert.equal(records.find(item => item.id === "agent-copy").active, false);
    assert.equal(records.find(item => item.id === "agent-original").active, true);
    assert.equal(field(renderer.root, "Name", "input").props.value, "Reader", "removing duplicate reopens the remaining original");
  } finally { if (renderer) await settle(() => renderer.unmount()); }
}

export async function checkKnowledgeSavedActions(Component) {
  let serial = 1, records = [{ id: "memory", display_name: "Useful fact", scope: "user", scope_id: null, kind: "memory", content: "Original fact", current_version_id: "memory-v1", enabled: false, provenance: { actor: "human" }, created_at: when, updated_at: when }];
  const history = new Map([["memory", [{ ...records[0], id: "memory-v1", entry_id: "memory" }]]]);
  let config = { context_captures: { redaction_mode: "redact_secrets", retention_seconds: null }, automatic_save_policies: [] };
  const proposals = [{ id: "suggestion", status: "pending", scope: "user", content: "Unwanted suggestion", display_name: "Suggestion", provenance: { actor: "agent" }, created_at: when }];
  const calls = []; let rejectImport = true;
  function replace(id, patch) { records = records.map(item => item.id === id ? { ...item, ...patch } : item); return records.find(item => item.id === id); }
  function version(id, content, extra = {}) { const next = replace(id, { content, current_version_id: `${id}-v${++serial}`, ...extra }); history.set(id, [...history.get(id) ?? [], { ...next, id: next.current_version_id, entry_id: id }]); return next; }
  globalThis.fetch = async (url, init = {}) => {
    const path = new URL(String(url)).pathname, method = init.method ?? "GET", body = init.body ? JSON.parse(init.body) : undefined;
    if (method !== "GET") calls.push({ path, method, body });
    if (path === "/v1/knowledge/entries") return json(records);
    if (path === "/v1/knowledge/scopes") return json([{ scope: "user", scope_id: null, label: "Personal", active: true }, { scope: "project", scope_id: "project-real", label: "Research", active: true }]);
    if (path === "/v1/knowledge/proposals") return json(proposals);
    if (path === "/v1/knowledge/proposals/suggestion/review") { proposals[0].status = body.decision === "reject" ? "rejected" : "accepted"; return json(proposals[0]); }
    if (path === "/v1/knowledge/config") { if (method === "PUT") config = { ...config, context_captures: { ...config.context_captures, ...body.context_captures } }; return json(config); }
    if (path === "/v1/knowledge/captures") return json({ id: "capture-real", redacted: config.context_captures.redaction_mode === "redact_secrets", discarded: config.context_captures.redaction_mode === "discard", expired: false });
    if (path === "/v1/knowledge/skills/import") {
      if (rejectImport) return failure("Package unavailable; choose its current location.");
      if (body.entry_id) { assert.equal(body.base_version, records.find(item => item.id === body.entry_id).current_version_id); return json(version(body.entry_id, "Updated skill body", { resources: [{ path: "second.md", size_bytes: 8 }] })); }
      const item = { ...records[0], id: "skill", kind: "skill", display_name: "Packaged skill", scope: body.scope, scope_id: body.scope_id, content: "Imported skill body", current_version_id: "skill-v1", resources: [{ path: "guide.md", size_bytes: 8 }] };
      records.push(item); history.set(item.id, [{ ...item, id: item.current_version_id, entry_id: item.id }]); return json(item);
    }
    const match = path.match(/^\/v1\/knowledge\/entries\/([^/]+)(?:\/(.+))?$/);
    if (match) {
      const [, id, action] = match;
      if (action === "versions") return json(history.get(id) ?? []);
      if (action === "delete-preview") return json(preview(id));
      if (action === "edit") { assert.equal(body.base_version, records.find(item => item.id === id).current_version_id); return json(version(id, body.content)); }
      if (action === "revert") { assert.equal(body.base_version, records.find(item => item.id === id).current_version_id); return json(version(id, history.get(id).find(item => item.id === body.target_version_id).content, { reverted_from_version_id: body.target_version_id })); }
      if (method === "PATCH") return json(replace(id, body));
      if (method === "DELETE") { const removed = records.find(item => item.id === id); records = records.filter(item => item.id !== id); return json(removed); }
    }
    throw new Error(`Unexpected Knowledge request ${method} ${path}`);
  };
  let renderer;
  try {
    await settle(() => { renderer = create(React.createElement(Component)); });
    await click(renderer.root, "Enable"); assert.equal(records[0].enabled, true);
    await click(renderer.root, "Rename"); await change(renderer.root, "Name", "input", "Named fact"); await submit(renderer.root);
    assert.equal(records[0].display_name, "Named fact");
    await change(renderer.root, "Content", "textarea", "Updated fact"); await click(renderer.root, "Save");
    assert.equal(records[0].content, "Updated fact"); assert.equal(history.get("memory").length, 2);
    await click(renderer.root, "Restore version");
    assert.equal(records[0].content, "Original fact"); assert.equal(history.get("memory").length, 3);
    assert.deepEqual(calls.find(call => call.path.endsWith("/revert")).body, { target_version_id: "memory-v1", base_version: "memory-v2" });
    await change(renderer.root, "Content", "textarea", "Unsaved fact"); await click(renderer.root, "Discard edits and reload");
    assert.equal(field(renderer.root, "Content", "textarea").props.value, "Original fact");
    await click(renderer.root, "Reject"); assert.equal(proposals[0].status, "rejected");
    await change(renderer.root, "Redaction", "select", "discard"); await click(renderer.root, "Save setting");
    await change(renderer.root, "Text to capture", "textarea", "Fixture request text"); await click(renderer.root, "Capture");
    assert.deepEqual(calls.find(call => call.path.endsWith("/captures")).body, { content: "Fixture request text", source: "desktop" });
    assert.match(text(renderer.root), /Capture discarded by the current setting/);
    await settle(() => renderer.root.findAllByType("button").find(item => text(item).startsWith("Skills ")).props.onClick());
    let importForm = renderer.root.findByType("form");
    await change(importForm, "Package path", "input", "D:/isolated-skill/SKILL.md");
    await change(importForm, "Use in", "select", "project:project-real"); await submit(importForm);
    assert.match(text(renderer.root), /Package unavailable/); assert.equal(field(importForm, "Package path", "input").props.value, "D:/isolated-skill/SKILL.md");
    rejectImport = false; await submit(importForm);
    const imported = records.find(item => item.id === "skill"); assert.equal(imported.scope_id, "project-real");
    assert.equal(field(renderer.root, "SKILL.md content", "textarea").props.value, "Imported skill body");
    const updateForm = renderer.root.findAllByType("form").find(form => text(form).includes("Import as new version"));
    await change(updateForm, "Package path", "input", "D:/isolated-skill/updated.zip"); await submit(updateForm);
    const request = calls.filter(call => call.path.endsWith("/skills/import")).at(-1).body;
    assert.deepEqual(request, { source_path: "D:/isolated-skill/updated.zip", scope: "project", scope_id: "project-real", entry_id: "skill", base_version: "skill-v1" });
    assert.equal(field(renderer.root, "SKILL.md content", "textarea").props.value, "Updated skill body");
    await click(renderer.root, "Remove"); assert.equal(calls.some(call => call.method === "DELETE"), false); await click(renderer.root, "Remove entry");
    assert.equal(records.some(item => item.id === "skill"), false); assert.equal(records[0].content, "Original fact");
    await click(renderer.root, "New skill");
    assert.match(field(renderer.root, "SKILL.md content", "textarea").props.value, /^---\nname: my-skill\ndescription: /, "new skills start as native SKILL.md documents");
    await change(renderer.root, "SKILL.md content", "textarea", "Plain text is not a skill document");
    assert.match(text(renderer.root), /A skill needs SKILL.md frontmatter/, "the editor explains the required native format");
  } finally { if (renderer) await settle(() => renderer.unmount()); }
}
