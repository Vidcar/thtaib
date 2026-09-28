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
  await checkGuidedSkillDraft((await vite.ssrLoadModule("/src/renderer/SkillEditor.tsx")).SkillEditor);
  await checkAgentDraftConflict((await vite.ssrLoadModule("/src/renderer/AgentSetupsPanel.tsx")).AgentSetupsPanel);
  await checkAgentSavedActions((await vite.ssrLoadModule("/src/renderer/AgentSetupsPanel.tsx")).AgentSetupsPanel);
  await checkKnowledgeSavedActions(KnowledgePanel);
  await checkCurrentKnowledgeRecordSelection((await vite.ssrLoadModule("/src/renderer/SetupConfigurationEditor.tsx")).SetupConfigurationEditor);
  await checkHelperRepair((await vite.ssrLoadModule("/src/renderer/SetupConfigurationEditor.tsx")).SetupConfigurationEditor);
  await checkKnowledgeIndependentLoads(KnowledgePanel);
  await checkAgentCatalogueNavigation((await vite.ssrLoadModule("/src/renderer/AgentSetupsPanel.tsx")).AgentSetupsPanel);
  await checkConnectionCredentialsAndTest((await vite.ssrLoadModule("/src/renderer/ConnectionsPanel.tsx")).ConnectionsPanel);
  await checkRunProposalConflict((await vite.ssrLoadModule("/src/renderer/RunMemoryProposals.tsx")).RunMemoryProposals);
  await checkSavedMemoryNeedsSelection((await vite.ssrLoadModule("/src/renderer/RunMemoryProposals.tsx")).RunMemoryProposals);
  await checkLifecyclePreview((await vite.ssrLoadModule("/src/renderer/LifecycleAction.tsx")).LifecycleAction);
} finally { await vite.close(); }
console.log("Knowledge workspace checks passed.");

async function checkGuidedSkillDraft(Editor) {
  const original = '---\nname: original\ndescription: Read references.\nlicense: MIT\n---\nInstructions.';
  const pending = [];
  const preview = (source, fields) => ({ content: fields ? source.replace('name: original', `name: ${fields.name}`).replace('description: Read references.', `description: ${fields.description}`) : source, name: fields?.name ?? 'original', description: fields?.description ?? 'Read references.', instructions: fields?.instructions ?? 'Instructions.', required_tools: fields?.required_tools ?? ['read_file'], required_connections: fields?.required_connections ?? ['saved_connection'], requires_project: fields?.requires_project ?? true, guided_available: true, valid: true, issues: [] });
  globalThis.fetch = async (url, init) => {
    assert.equal(new URL(String(url)).pathname, '/v1/knowledge/skills/preview');
    const body = JSON.parse(init.body);
    if (body.fields) { const response = deferred(); pending.push({ ...response, body }); return response.promise; }
    return json(preview(body.content));
  };
  let value = original, changes = [], valid = false, renderer;
  function Host() {
    const [source, setSource] = React.useState(original);
    const [resources, setResources] = React.useState([]);
    return React.createElement(Editor, { content: source, scope: 'user', resources: [{ path: 'guide.md', size_bytes: 8 }], resourceChanges: resources,
      onChange: next => { value = next; setSource(next); }, onResourceChanges: next => { changes = next; setResources(next); }, onStateChange: next => { valid = next; } });
  }
  try {
    await act(async () => { renderer = create(React.createElement(Host)); await tick(); });
    assert.equal(valid, true);
    await act(async () => field(renderer, 'Skill name', 'input').props.onChange({ target: { value: 'older-name' } }));
    assert.deepEqual(pending[0].body.fields.required_tools, ['read_file'], 'ordinary Guided edits preserve declared tool requirements');
    assert.deepEqual(pending[0].body.fields.required_connections, ['saved_connection']);
    assert.equal(pending[0].body.fields.requires_project, true);
    assert.equal(valid, false, 'an unconfirmed source transformation cannot save');
    await act(async () => field(renderer, 'Skill name', 'input').props.onChange({ target: { value: 'latest-name' } }));
    assert.equal(button(renderer, 'Source').props.disabled, true, 'Source cannot discard an outstanding guided edit');
    await act(async () => { pending[1].resolve(json(preview(pending[1].body.content, pending[1].body.fields))); await tick(); });
    assert.match(value, /name: latest-name/); assert.match(value, /license: MIT/);
    await act(async () => { pending[0].resolve(json(preview(pending[0].body.content, pending[0].body.fields))); await tick(); });
    assert.match(value, /name: latest-name/, 'a stale preview cannot overwrite the latest human edit');
    await act(async () => button(renderer, 'Source').props.onClick());
    assert.equal(field(renderer, 'SKILL.md', 'textarea').props.value, value, 'both views share one native source draft');
    await act(async () => button(renderer, 'Remove').props.onClick());
    assert.deepEqual(changes, [{ path: 'guide.md', remove: true }], 'resource removal remains in the unsaved skill draft');
    const bytes = new TextEncoder().encode('Replacement file');
    await act(async () => { field(renderer, 'File path', 'input').props.onChange({ target: { value: 'guide.md' } }); });
    await act(async () => { field(renderer, 'Add or replace file', 'input').props.onChange({ target: { value: 'file', files: [{ name: 'replacement.md', size: bytes.length, arrayBuffer: async () => bytes.buffer }] } }); await tick(); });
    assert.equal(changes.length, 1); assert.equal(changes[0].path, 'guide.md');
    assert.equal(atob(changes[0].content_base64), 'Replacement file');
    assert.equal(pending.length, 2, 'adding a supporting file does not dispatch it or write a saved version');
  } finally { for (const item of pending) item.resolve(json(preview(item.body.content, item.body.fields))); if (renderer) await act(async () => renderer.unmount()); }
}

async function checkCurrentKnowledgeRecordSelection(Component) {
  const requests = [];
  globalThis.fetch = async (url, init) => {
    requests.push({ path: new URL(String(url)).pathname, body: JSON.parse(init.body) });
    assert.equal(requests.at(-1).path, "/v1/setup-resolution");
    return json({ configuration: requests.at(-1).body.overrides, effective: {}, instruction_layers: [], missing_dependencies: [] });
  };
  const catalogue = { deployments: [], bundles: [], profiles: [], tools: [], connections: [], knowledge: [
    { ...entry("memory", "Saved memory"), current_version_id: "memory-v2" },
    { ...entry("skill", "Saved skill"), kind: "skill", current_version_id: "skill-v1" },
  ] };
  const edits = [];
  const props = { catalogue, value: { memory_entry_ids: ["memory"], skill_entry_ids: ["skill"] },
    sections: ["knowledge"], onChange: value => edits.push(value) };
  const choice = name => renderer.root.findAllByType("button").find(node => node.props.role === "switch" && node.props["aria-label"] === name);
  let renderer;
  try {
    await act(async () => { renderer = create(React.createElement(Component, props)); await tick(); });
    assert.equal(choice("Saved memory").props["aria-checked"], true);
    assert.equal(choice("Saved skill").props["aria-checked"], true);
    const updatedCatalogue = { ...catalogue, knowledge: catalogue.knowledge.map(item => ({ ...item, current_version_id: `${item.id}-new-version` })) };
    await act(async () => { renderer.update(React.createElement(Component, { ...props, catalogue: updatedCatalogue })); await tick(); });
    assert.equal(choice("Saved memory").props["aria-checked"], true, "a saved version update cannot deselect its chosen record");
    assert.equal(choice("Saved skill").props["aria-checked"], true);
    await act(async () => choice("Saved memory").props.onClick());
    assert.deepEqual(edits.at(-1).memory_entry_ids, [], "explicit deselection is saved as an empty record selection");
    assert.deepEqual(edits.at(-1).skill_entry_ids, ["skill"]);
    assert.equal(Object.hasOwn(edits.at(-1), "memory_version_refs"), false, "the editor leaves exact version resolution to admission");
    assert.equal(requests.some(request => request.path.includes("/knowledge/versions/")), false, "record choices do not fetch or pin earlier native bodies");
  } finally { if (renderer) await act(async () => renderer.unmount()); }
}

async function checkHelperRepair(Editor) {
  const catalogue = { deployments: [], bundles: [{ id: "bundle", display_name: "Local model" }], profiles: [{ id: "configuration", bundle_id: "bundle", display_name: "Careful" }], tools: [], connections: [], knowledge: [] };
  const agents = [
    { id: "self", name: "Main agent", active: true, configuration: {} },
    { id: "broken", name: "Research helper", active: true, configuration: { requires_project: true }, helper_missing_dependencies: [{ kind: "tool", reason: "Search connection unavailable" }] },
    { id: "removed", name: "Former helper", active: false, configuration: {} },
    { id: "eligible", name: "Writer", active: true, configuration: { model_configuration_id: "configuration", requires_host_shell: true }, missing_dependencies: [{ kind: "helper", reason: "Only its main role needs another helper" }], helper_missing_dependencies: [] },
    { id: "unready", name: "Unready helper", active: true, configuration: {}, helper_missing_dependencies: [{ kind: "model", reason: "Assigned model unavailable" }] },
  ];
  globalThis.fetch = async (_url, init) => json({ configuration: JSON.parse(init.body).overrides, effective: {}, instruction_layers: [], missing_dependencies: [] });
  let value, renderer;
  function Host() { const [current, setCurrent] = React.useState({ instructions: "Keep these instructions", helper_agent_ids: ["broken", "removed", "missing"] }); value = current; return React.createElement(Editor, { value: current, onChange: setCurrent, catalogue, agentOptions: agents, currentAgentId: "self", sections: ["helpers"] }); }
  try {
    await act(async () => { renderer = create(React.createElement(Host)); await tick(); });
    assert.match(text(renderer.root), /Research helper.*Search connection unavailable/);
    assert.match(text(renderer.root), /Former helper.*removed or is unavailable/);
    assert.match(text(renderer.root), /Unavailable helper/);
    for (const name of ["Research helper", "Former helper", "Unavailable helper"]) {
      const remove = renderer.root.findByProps({ "aria-label": `Remove ${name}` });
      assert.equal(remove.props.disabled, false, "an unavailable selected helper stays repairable");
      await act(async () => remove.props.onClick());
    }
    assert.deepEqual(value.helper_agent_ids, []);
    assert.equal(value.instructions, "Keep these instructions");
    const addSelect = () => renderer.root.findByProps({ "aria-label": "Add helper" });
    await act(async () => addSelect().props.onChange({ target: { value: "unready" } }));
    assert.equal(button(renderer, "Add helper").props.disabled, true);
    assert.match(text(renderer.root), /Assigned model unavailable.*Repair this agent/);
    await act(async () => addSelect().props.onChange({ target: { value: "eligible" } }));
    assert.equal(button(renderer, "Add helper").props.disabled, false, "main-role dependencies cannot block a valid helper role");
    assert.match(text(addSelect()), /Writer · Local model · Careful/);
    await act(async () => button(renderer, "Add helper").props.onClick());
    assert.deepEqual(value.helper_agent_ids, ["eligible"]);
    assert.match(text(renderer.root), /Writer.*Local model · Careful.*Shell required/);
    await act(async () => renderer.root.findByProps({ "aria-label": "Search helpers" }).props.onChange({ target: { value: "no match" } }));
    assert.match(text(addSelect()), /No matching helpers/);
    assert.equal(addSelect().props.disabled, true);
  } finally { if (renderer) await act(async () => renderer.unmount()); }
}

async function checkKnowledgeIndependentLoads(Panel) {
  const settings = deferred();
  const record = entry("independent", "Useful memory");
  const config = { context_captures: { redaction_mode: "redact_secrets", retention_seconds: 3600 }, scope_policies: {} };
  globalThis.fetch = async url => {
    const route = new URL(String(url)).pathname;
    if (route === "/v1/knowledge/entries") return json([record]);
    if (route === "/v1/knowledge/config") return settings.promise;
    if (route.endsWith("/versions")) return json([]);
    if (["/v1/knowledge/scopes", "/v1/knowledge/proposals"].includes(route)) return { ok: false, status: 503, json: async () => ({ error: route.endsWith("scopes") ? "Destinations offline" : "Suggestions offline" }) };
    throw new Error(`unexpected ${route}`);
  };
  let renderer;
  try {
    await act(async () => { renderer = create(React.createElement(Panel)); await tick(); });
    assert.equal(field(renderer, "Content", "textarea").props.value, record.content, "entries render while settings are pending");
    assert.match(text(renderer.root), /Destinations offline/);
    assert.match(text(renderer.root), /Suggestions offline/);
    await act(async () => field(renderer, "Content", "textarea").props.onChange({ target: { value: "Keep my draft" } }));
    await act(async () => button(renderer, "Rename").props.onClick());
    await act(async () => field(renderer, "Display name", "input").props.onChange({ target: { value: "Draft display name" } }));
    await act(async () => { settings.resolve(json(config)); await tick(); });
    await act(async () => segmented(renderer.root, "Redaction", "discard").props.onChange());
    await act(async () => { renderer.update(React.createElement(Panel, { active: false })); await tick(); });
    await act(async () => { renderer.update(React.createElement(Panel, { active: true })); await tick(); });
    assert.equal(field(renderer, "Content", "textarea").props.value, "Keep my draft");
    assert.equal(field(renderer, "Display name", "input").props.value, "Draft display name");
    assert.equal(segmented(renderer.root, "Redaction", "discard").props.checked, true, "an unsaved capture choice survives navigation");
    await act(async () => field(renderer, "Content", "textarea").props.onChange({ target: { value: record.content } }));
    assert.doesNotMatch(text(catalogueRow(renderer.root, "Useful memory")), /Unsaved changes/, "restoring the saved body clears its dirty marker");
    await act(async () => button(renderer, "New memory").props.onClick());
    const editor = renderer.root.findByProps({ className: "catalogue-editor" });
    assert.equal(editor.findByProps({ id: "knowledge-create-content" }).props.value, "", "new entries use the same detail pane");
    await act(async () => field(renderer, "Content", "textarea").props.onChange({ target: { value: "New personal entry" } }));
    assert.equal(button(renderer, "Save").props.disabled, false, "personal creation does not require destination or proposal availability");
  } finally { settings.resolve(json(config)); if (renderer) await act(async () => renderer.unmount()); }
}

async function checkAgentCatalogueNavigation(Panel) {
  const records = ["one", "two"].map(id => ({ id, name: `Agent ${id}`, role: id === "one" ? "Research" : "Writing", active: true, current_version_id: `${id}-version`, configuration: { instructions: `Instructions ${id}`, model_configuration_id: id === "two" ? "configuration" : null }, missing_dependencies: [], helper_missing_dependencies: [] }));
  const history = deferred();
  const recordLoad = deferred();
  globalThis.fetch = async url => {
    const route = new URL(String(url)).pathname;
    if (route === "/v1/agent-setups") return recordLoad.promise;
    if (route === "/v1/bundles") return json([{ id: "bundle", display_name: "Local model" }]);
    if (route === "/v1/profiles") return json([{ id: "configuration", bundle_id: "bundle", display_name: "Careful" }]);
    if (route === "/v1/agent-tools") return json({ tools: [] });
    if (route === "/v1/setup-resolution") return json({ configuration: {}, effective: {}, instruction_layers: [], missing_dependencies: [] });
    if (route === "/v1/agent-setups/two/versions") return history.promise;
    if (route.endsWith("/versions") || ["/v1/deployments", "/v1/connections", "/v1/knowledge/entries"].includes(route)) return json([]);
    throw new Error(`unexpected ${route}`);
  };
  let renderer;
  try {
    await act(async () => { renderer = create(React.createElement(Panel)); await tick(); });
    await act(async () => button(renderer, "New agent").props.onClick());
    await act(async () => { field(renderer, "Name", "input").props.onChange({ target: { value: "Draft before loading" } }); field(renderer, "Instructions", "textarea").props.onChange({ target: { value: "Keep this new draft" } }); });
    await act(async () => { recordLoad.resolve(json(records)); await tick(); });
    assert.equal(field(renderer, "Name", "input").props.value, "Draft before loading", "the initial list response cannot leave a newly opened creation draft");
    assert.equal(field(renderer, "Instructions", "textarea").props.value, "Keep this new draft");
    assert.ok(renderer.root.findByProps({ "aria-label": "Agent creation steps" }));
    await act(async () => button(renderer, "Cancel").props.onClick());
    await act(async () => { renderer.update(React.createElement(Panel, { openAgentId: "two", openRequest: 1 })); await tick(); });
    assert.equal(field(renderer, "Name", "input").props.value, "Agent two", "an explicit navigation request opens that agent");
    assert.match(text(renderer.root.findByProps({ className: "workspace-versions" })), /Version history\s*Loading…/, "pending history cannot be presented as zero saved versions");
    assert.match(text(catalogueRow(renderer.root, "Agent two")), /Writing.*Local model · Careful/);
    await act(async () => field(renderer, "Instructions", "textarea").props.onChange({ target: { value: "Draft for two" } }));
    await act(async () => { renderer.update(React.createElement(Panel, { openAgentId: "one", openRequest: 2 })); await tick(); });
    assert.equal(field(renderer, "Name", "input").props.value, "Agent one");
    await act(async () => { renderer.update(React.createElement(Panel, { openAgentId: "two", openRequest: 3 })); await tick(); });
    assert.equal(field(renderer, "Instructions", "textarea").props.value, "Draft for two");
    await act(async () => renderer.root.findByProps({ "aria-label": "Search agents" }).props.onChange({ target: { value: "Local model" } }));
    assert.equal(renderer.root.findAllByProps({ className: "catalogue-row" }).length, 1, "model labels participate in agent search");
    await act(async () => { renderer.update(React.createElement(Panel, { openAgentId: "two", openRequest: 3, active: false })); await tick(); });
    await act(async () => { renderer.update(React.createElement(Panel, { openAgentId: "two", openRequest: 3, active: true })); await tick(); });
    assert.equal(field(renderer, "Instructions", "textarea").props.value, "Draft for two");
    await act(async () => field(renderer, "Instructions", "textarea").props.onChange({ target: { value: "Instructions two" } }));
    assert.doesNotMatch(text(catalogueRow(renderer.root, "Agent two")), /Unsaved changes/);
    assert.equal(renderer.root.findAllByType("button").some(node => text(node) === "Discard edits"), false, "restoring saved values clears the draft state");
    await act(async () => { history.resolve(json([{ ...records[1], id: "two-version", created_at: "2026-09-28T00:00:00Z" }])); await tick(); });
    assert.match(text(renderer.root.findByProps({ className: "workspace-versions" })), /1 saved/);
  } finally { recordLoad.resolve(json([])); history.resolve(json([])); if (renderer) await act(async () => renderer.unmount()); }
}

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
    assert.match(text(renderer.root), /Version history\s*Loading…/);
    assert.doesNotMatch(text(renderer.root), /No saved versions/, "pending history is distinct from a known empty history");
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
    await act(async () => field(renderer, "When to use (optional)", "textarea").props.onChange({ target: { value: "Cancelled description" } }));
    await act(async () => button(renderer, "Cancel").props.onClick());
    await act(async () => button(renderer, "New memory").props.onClick());
    assert.equal(field(renderer, "When to use (optional)", "textarea").props.value, "", "a new memory does not inherit a cancelled description");
    await act(async () => segmented(renderer.root, "Use in", "project").props.onChange());
    assert.ok(text(field(renderer, "Project", "select")).includes("Actual project"));
    await act(async () => { field(renderer, "Project", "select").props.onChange({ target: { value: "project_real" } }); field(renderer, "Display name (optional)", "input").props.onChange({ target: { value: "Scoped fact" } }); field(renderer, "Content", "textarea").props.onChange({ target: { value: "Remember this" } }); field(renderer, "When to use (optional)", "textarea").props.onChange({ target: { value: "Use this when preparing a project comparison." } }); });
    await act(async () => { renderer.root.findByType("form").props.onSubmit({ preventDefault() {} }); await tick(); });
    const created = calls.find(call => call.path === "/v1/knowledge/entries" && call.method === "POST").body;
    assert.equal(created.scope_id, "project_real"); assert.equal(created.scope, "project"); assert.ok(!Object.hasOwn(created, "provenance"), "the desktop cannot forge actor or run provenance");
    await act(async () => { button(renderer, "Disable").props.onClick(); await tick(); });
    assert.equal(calls.some(call => call.method === "PATCH"), false, "disabling knowledge waits for the reviewed dependency preview");
    await act(async () => { button(renderer, "Disable entry").props.onClick(); await tick(); });
    assert.equal(calls.find(call => call.method === "PATCH").body.enabled, false);
    await act(async () => field(renderer, "Content", "textarea").props.onChange({ target: { value: "Unsaved human change" } }));
    await act(async () => field(renderer, "When to use (optional)", "textarea").props.onChange({ target: { value: "Updated memory description." } }));
    await act(async () => { button(renderer, "Save").props.onClick(); await tick(); });
    assert.equal(calls.find(call => call.path.endsWith("/edit")).body.base_version, "created-version");
    assert.equal(field(renderer, "Content", "textarea").props.value, "Unsaved human change", "conflict must preserve the human draft");
    assert.equal(field(renderer, "When to use (optional)", "textarea").props.value, "Updated memory description.", "version conflicts preserve the short description draft too");
    assert.equal(calls.find(call => call.path.endsWith("/edit")).body.description, "Updated memory description.");
    assert.equal(calls.find(call => call.path === "/v1/knowledge/entries" && call.method === "POST").body.description, "Use this when preparing a project comparison.");
    await act(async () => { button(renderer, "Discard edits and reload").props.onClick(); await tick(); });
    assert.equal(field(renderer, "Content", "textarea").props.value, "Remember this", "discard restores the saved memory body");
    assert.equal(field(renderer, "When to use (optional)", "textarea").props.value, "Use this when preparing a project comparison.", "discard restores the saved short description");
    await act(async () => { button(renderer, "Accept").props.onClick(); await tick(); });
    assert.deepEqual(calls.find(call => call.path.endsWith("/review")).body, { decision: "accept" });
    await act(async () => field(renderer, "Destination", "select").props.onChange({ target: { value: "project:project_real" } }));
    const automatic = renderer.root.findByProps({ role: "switch", "aria-label": "Save automatically" });
    assert.equal(automatic.props["aria-checked"], false);
    await act(async () => { automatic.props.onClick(); await tick(); });
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
    await act(async () => { catalogueRow(renderer.root, "Agent two").props.onClick(); await tick(); });
    await act(async () => { catalogueRow(renderer.root, "Agent one").props.onClick(); await tick(); });
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
    assert.match(text(renderer.root), /A newer saved version will block acceptance/, "pending updates explain the version conflict safeguard");
    await act(async () => { button(renderer, "Accept memory").props.onClick(); await tick(); });
    assert.ok(text(renderer.root).includes("A newer memory version exists"));
    assert.ok(button(renderer, "Accept memory"), "a conflicted proposal must not be displayed as committed");
  } finally { if (renderer) await act(async () => renderer.unmount()); }
}
async function checkSavedMemoryNeedsSelection(Component) {
  const proposal = { id: "proposal", status: "pending", scope: "user", content: "Suggested fact", provenance: { actor: "agent" } };
  const selections = [];
  globalThis.fetch = async (url) => {
    const address = new URL(String(url));
    if (address.pathname.endsWith("/scopes")) return json([{ scope: "user", label: "Personal", active: true }]);
    if (address.pathname.endsWith("/review")) return json({ ...proposal, status: "accepted", entry_id: "entry-new", committed_version_id: "memory-new" });
    return json([proposal]);
  };
  let renderer;
  try {
    await act(async () => { renderer = create(React.createElement(Component, { runId: "run_saved", status: "completed", onOpenKnowledge() {}, onUseMemoryVersion: id => selections.push(id) })); await tick(); });
    await act(async () => { button(renderer, "Accept memory").props.onClick(); await tick(); });
    assert.deepEqual(selections, [], "saving a suggestion does not alter active context or next-turn selection");
    assert.doesNotMatch(text(renderer.root), /A newer saved version will block acceptance/, "an accepted memory no longer has a pending acceptance warning");
    await act(async () => { button(renderer, "Use next turn").props.onClick(); await tick(); });
    assert.deepEqual(selections, ["memory-new"], "explicit selection uses the committed immutable version");
  } finally { if (renderer) await act(async () => renderer.unmount()); }
}
function field(renderer, label, type) { const labels = renderer.root.findAllByType("label").filter(item => text(item).startsWith(label)); for (const item of labels) { const fields = item.props.htmlFor ? renderer.root.findAll(node => node.type === type && node.props.id === item.props.htmlFor) : item.findAllByType(type); if (fields.length) return fields[0]; } assert.fail(`expected ${type} field ${label}`); }
function catalogueRow(root, name) { const row = root.findAllByType("button").find(node => node.props.className === "catalogue-row" && text(node).startsWith(name)); assert.ok(row, `catalogue row ${name}`); return row; }
function segmented(root, label, value) { const group = root.findAll(node => node.props.role === "radiogroup").find(node => root.findAll(item => item.props.id === node.props["aria-labelledby"]).some(item => text(item) === label)); assert.ok(group, `segmented choice ${label}`); return group.findAllByType("input").find(node => node.props.value === value); }
function entry(id, name) { return { id, display_name: name, scope: "user", scope_id: null, kind: "memory", content: `content ${id}`, current_version_id: `${id}-version`, provenance: { actor: "human" }, created_at: "2026-09-22T00:00:00Z", updated_at: "2026-09-22T00:00:00Z" }; }
function json(body) { return { ok: true, status: 200, json: async () => body }; }
function text(node) { return typeof node === "string" ? node : (node?.children ?? []).map(text).join(""); }
function deferred() { let resolve; const promise = new Promise(r => { resolve = r; }); return { promise, resolve }; }
async function tick() { await new Promise(resolve => setTimeout(resolve, 0)); }
