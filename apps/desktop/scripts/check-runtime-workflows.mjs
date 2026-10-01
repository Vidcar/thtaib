import assert from "node:assert/strict";
import path from "node:path";
import { fileURLToPath } from "node:url";
import React from "react";
import { act, create } from "react-test-renderer";
import { createServer } from "vite";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;
globalThis.window = { setTimeout, clearTimeout, setInterval, clearInterval, workbench: { backendUrl: "http://127.0.0.1:8000" } };
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const vite = await createServer({ root, appType: "custom", server: { middlewareMode: true, hmr: false }, logLevel: "error" });
const json = value => ({ ok: true, status: 200, json: async () => value });
const text = node => typeof node === "string" ? node : (node.children ?? []).map(text).join("");
const tick = () => new Promise(resolve => setTimeout(resolve, 0));
const button = (renderer, label) => renderer.root.findAllByType("button").find(node => text(node) === label);
const field = (renderer, label, type) => renderer.root.findAllByType("label").find(node => text(node).startsWith(label)).findByType(type);
try {
  await checkExplicitProjectGrant((await vite.ssrLoadModule("/src/renderer/ProjectFileGrantControls.tsx")).ProjectFileGrantControls);
  await checkOptInSkill((await vite.ssrLoadModule("/src/renderer/SkillPackageControls.tsx")).BundledRuntimeSkills);
  await checkTemplateDraft((await vite.ssrLoadModule("/src/renderer/AgentSetupsPanel.tsx")).AgentSetupsPanel);
} finally { await vite.close(); }
console.log("Runtime skill, project scope and setup template UI checks passed.");

async function checkExplicitProjectGrant(Component) {
  const calls = []; let resolveSave, saved = 0, renderer;
  globalThis.fetch = async (url, init = {}) => {
    const route = new URL(String(url)).pathname;
    if (route === "/v1/projects") return json([{ id: "real-project", name: "Project", path: "D:/Project with spaces", missing: false }]);
    if (route === "/v1/settings/grants/project-files") {
      calls.push(JSON.parse(init.body)); return new Promise(resolve => { resolveSave = resolve; });
    }
    throw new Error(`Unexpected grant route ${route}`);
  };
  try {
    await act(async () => { renderer = create(React.createElement(Component, { onSaved: async () => saved++ })); await tick(); });
    assert.equal(calls.length, 0, "opening controls never creates a grant");
    assert.equal(button(renderer, "Grant these file changes").props.disabled, true);
    await act(async () => field(renderer, "Project", "select").props.onChange({ target: { value: "real-project" } }));
    await act(async () => field(renderer, "Excluded paths", "textarea").props.onChange({ target: { value: "private/**\nsecrets.json" } }));
    await act(async () => { const form = renderer.root.findByType("form"); form.props.onSubmit({ preventDefault() {} }); form.props.onSubmit({ preventDefault() {} }); });
    assert.equal(calls.length, 1, "same-tick duplicate approval is blocked");
    assert.deepEqual(calls[0], { project_id: "real-project", operations: ["write_file", "edit_file"], excluded_paths: ["private/**", "secrets.json"] });
    assert.equal(button(renderer, "Saving…").props.disabled, true);
    await act(async () => { resolveSave(json({ id: "grant" })); await tick(); });
    assert.equal(saved, 1); assert.equal(field(renderer, "Project", "select").props.value, "");
    assert.match(text(renderer.root), /Commands, deletion, browser and account actions keep their own approvals/);
  } finally { if (renderer) await act(async () => renderer.unmount()); }
}

async function checkOptInSkill(Component) {
  const calls = []; let imported, renderer;
  const skill = { id: "failure-diagnosis", name: "failure-diagnosis", description: "Diagnose a failure; skip unrelated work.",
    content: "---\nname: failure-diagnosis\ndescription: Diagnose a failure.\n---\nEvidence before edits.",
    resources: [{ path: "references/outcomes.md", size_bytes: 22, sha256: "hash" }], required_tools: [], requires_project: false };
  globalThis.fetch = async (url, init = {}) => {
    const route = new URL(String(url)).pathname;
    if (route === "/v1/knowledge/skills/bundled") return json([skill]);
    if (route === "/v1/knowledge/scopes") return json([{ scope: "user", label: "Personal knowledge", active: true }, { scope: "project", scope_id: "project-real", label: "Project", active: true }]);
    if (route.endsWith("/failure-diagnosis/install")) { calls.push(JSON.parse(init.body)); return json({ id: "native-entry", current_version_id: "native-version", kind: "skill" }); }
    throw new Error(`Unexpected skill route ${route}`);
  };
  try {
    await act(async () => { renderer = create(React.createElement(Component, { onImported: async entry => { imported = entry; } })); await tick(); });
    assert.equal(calls.length, 0, "viewing the pack never installs it");
    await act(async () => field(renderer, "Workflow", "select").props.onChange({ target: { value: skill.id } }));
    assert.match(text(renderer.root), /Evidence before edits/);
    await act(async () => field(renderer, "Use in", "select").props.onChange({ target: { value: "project:project-real" } }));
    await act(async () => { button(renderer, "Add to Knowledge").props.onClick(); await tick(); });
    assert.deepEqual(calls, [{ scope: "project", scope_id: "project-real" }]);
    assert.equal(imported.current_version_id, "native-version");
    assert.match(text(renderer.root), /Installation grants no tools, access or automatic memory saving/);
  } finally { if (renderer) await act(async () => renderer.unmount()); }
}

async function checkTemplateDraft(Component) {
  const calls = []; let renderer;
  const template = { id: "guarded-project-builder", name: "Guarded project builder", role: "Build local work", recommended_skills: ["project-change"],
    configuration: { instructions: "Preserve unrelated work.", presented_tools: ["read_file", "edit_file"], connection_ids: [], helper_agent_ids: [], skill_entry_ids: ["real-installed-entry"], input_policy: { tool_loading: "when_needed", pinned_tools: ["edit_file"] } },
    note: "Use Ask in Chat. Commands require their own approval.", suggested_chat_mode: "work", suggested_chat_access: "ask", suggested_desktop_access: "off" };
  globalThis.fetch = async (url, init = {}) => {
    const route = new URL(String(url)).pathname; calls.push({ route, method: init.method ?? "GET" });
    if (route === "/v1/agent-setup-templates") return json([template]);
    if (route === "/v1/agent-tools") return json({ tools: [], enabled: [] });
    if (route === "/v1/setup-resolution") return json({ configuration: JSON.parse(init.body).overrides, effective_values: {}, input_sources: [] });
    return json([]);
  };
  try {
    await act(async () => { renderer = create(React.createElement(Component)); await tick(); await tick(); });
    await act(async () => field(renderer, "Starting template", "select").props.onChange({ target: { value: template.id } }));
    await act(async () => button(renderer, "Use template").props.onClick());
    assert.equal(renderer.root.findByProps({ id: "agent-draft-name" }).props.value, template.name);
    assert.match(text(renderer.root), /1 already installed personal skills selected/);
    assert.match(text(renderer.root), /Chat access remains your current choice/);
    assert.equal(calls.filter(call => call.method !== "GET" && call.route !== "/v1/setup-resolution").length, 0, "a template is a reviewable draft, not a saved setup or access change");
    await act(async () => renderer.root.findByType("form").props.onSubmit({ preventDefault() {} }));
    const editor = () => renderer.root.find(node => typeof node.type === "function" && node.type.name === "SetupConfigurationEditor");
    const chosenModel = { deployment_id: "real-deployment", bundle_id: "real-bundle", model_configuration_id: "real-model-setup",
      startup_overrides: { gpu_layers: 13 }, profile_id: "real-profile", inherit_deployment_settings: false, per_request_overrides: { temperature: 0.2 } };
    await act(async () => editor().props.onChange({ ...editor().props.value, ...chosenModel, presented_tools: ["echo"] }));
    await act(async () => button(renderer, "Back").props.onClick());
    await act(async () => button(renderer, "Use template").props.onClick());
    await act(async () => renderer.root.findByType("form").props.onSubmit({ preventDefault() {} }));
    for (const [key, value] of Object.entries(chosenModel)) assert.deepEqual(editor().props.value[key], value, `template preserves chosen model field ${key}`);
    assert.deepEqual(editor().props.value.presented_tools, template.configuration.presented_tools, "template replaces its owned capability selection");
    assert.equal(calls.filter(call => call.method !== "GET" && call.route !== "/v1/setup-resolution").length, 0);
  } finally { if (renderer) await act(async () => renderer.unmount()); }
}
