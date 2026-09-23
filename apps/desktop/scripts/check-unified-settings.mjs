import assert from "node:assert/strict";
import React from "react";
import { act, create } from "react-test-renderer";
import { createServer } from "vite";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;
globalThis.window = { setTimeout, clearTimeout, setInterval, clearInterval };
const vite = await createServer({ appType: "custom", server: { middlewareMode: true, hmr: false }, logLevel: "error" });
const response = body => ({ ok: true, status: 200, json: async () => body });
const text = node => typeof node === "string" ? node : (node?.children ?? []).map(text).join("");
const tick = () => new Promise(resolve => setTimeout(resolve, 0));
const bag = requested => ({ requested, applied: requested, unsupported: [], retired: [], overridden: [], unverified: [] });
const originalFetch = globalThis.fetch;
try {
  const { DeploymentsPanel } = await vite.ssrLoadModule("/src/renderer/DeploymentsPanel.tsx");
  const { SetupConfigurationEditor } = await vite.ssrLoadModule("/src/renderer/SetupConfigurationEditor.tsx");
  await configurations(DeploymentsPanel);
  await inheritedAccessAndEmptyTools(SetupConfigurationEditor);
} finally { globalThis.fetch = originalFetch; await vite.close(); }
console.log("Unified settings save, revision, inheritance and explicit-none checks passed.");

async function configurations(Panel) {
  const calls = [];
  const bundle = { id: "model", display_name: "Example model", default_configuration_id: "default", disk_matches: true, files: [], companions: [] };
  let profiles = [{ id: "default", bundle_id: "model", display_name: "Example model", revision: 4, bags: { startup: bag({ ctx_size: 8192, parallel: 1 }), per_request: bag({ temperature: 0.5 }), agent: bag({}) } }];
  let renderer;
  const options = { bundle_id: "model", context_size: { maximum: 32768, options: [4096, 8192, 16384, 32768].map(value => ({ value, label: String(value) })) }, gpu_layers: { maximum: 32, options: [] }, startup_defaults: {}, per_request_defaults: {}, metadata: {} };
  globalThis.fetch = async (url, init = {}) => {
    const path = String(url), body = init.body ? JSON.parse(init.body) : null;
    calls.push({ path, method: init.method ?? "GET", body });
    if (path.endsWith("/v1/runtime")) return response({ status: "ready" });
    if (path.endsWith("/v1/deployments")) return response([]);
    if (path.includes("/configuration-options")) return response(options);
    if (path.endsWith("/projectors")) return response({ candidates: [] });
    if (path.endsWith("/v1/setup-resolution")) return response({ configuration: body.overrides, effective_values: {}, instruction_layers: [] });
    if (path.endsWith("/v1/settings/preview")) return response({ startup: bag(body.startup), per_request: bag(body.per_request), agent: bag({}) });
    if (path.endsWith("/configurations")) {
      const old = profiles.find(item => item.id === body.configuration_id);
      if (old) assert.equal(body.expected_revision, old.revision, "ordinary saves use optimistic revision checking");
      const saved = { id: old?.id ?? "variant", bundle_id: "model", display_name: body.display_name, revision: (old?.revision ?? 0) + 1, bags: { startup: bag(body.startup), per_request: bag(body.per_request), agent: bag({}) } };
      profiles = old ? profiles.map(item => item.id === old.id ? saved : item) : [...profiles, saved];
      return response(saved);
    }
    throw new Error(`Unexpected settings request: ${path}`);
  };
  const props = () => ({ selectedBundleId: "model", initialBundles: [bundle], initialProfiles: profiles, onBundlesChanged: async () => { renderer.update(React.createElement(Panel, props())); } });
  try {
    await act(async () => { renderer = create(React.createElement(Panel, props()), { createNodeMock: element => element.type === "form" ? { reportValidity: () => true } : null }); await tick(); });
    const button = label => renderer.root.findAllByType("button").find(node => text(node) === label);
    assert.ok(button("Save changes"), "save is available without a running deployment");
    await act(async () => { button("Save changes").props.onClick(); await tick(); });
    await act(async () => { button("Save changes").props.onClick(); await tick(); });
    assert.equal(profiles.length, 1, "ordinary repeated saving does not create another configuration");
    assert.equal(profiles[0].revision, 6);
    assert.equal(profiles[0].bags.startup.requested.port, undefined, "automatic port is not frozen into a saved configuration");
    assert.equal(calls.some(call => call.path.includes("/deployments/managed")), false, "saving never creates a deployment");
    await act(async () => { button("Save as variant").props.onClick(); });
    await act(async () => { button("Save variant").props.onClick(); await tick(); });
    assert.equal(profiles.length, 2, "only explicit Save as variant creates another configuration");
    assert.equal(profiles[1].display_name, "Example model variant");
  } finally { if (renderer) await act(async () => renderer.unmount()); }
}

async function inheritedAccessAndEmptyTools(Editor) {
  let renderer;
  const edits = [];
  const catalogue = { bundles: [], profiles: [], deployments: [], knowledge: [], connections: [], tools: [{ id: "read_file", name: "Read file", description: "Reads a project file without changing it." }] };
  globalThis.fetch = async (url, init) => {
    assert.ok(String(url).endsWith("/v1/setup-resolution"));
    const request = JSON.parse(init.body);
    assert.equal(request.editing_layer, "project");
    return response({ configuration: { approval_mode: "full_access" }, effective_values: { approval_mode: { value: "full_access", source: "Application default", known: true, inherited: true }, presented_tools: { value: ["read_file"], source: "Application default", known: true, inherited: true } }, instruction_layers: [] });
  };
  try {
    await act(async () => { renderer = create(React.createElement(Editor, { value: {}, scope: "project", projectId: "project", catalogue, onChange: value => edits.push(value) })); await tick(); });
    const access = renderer.root.findAllByType("select").find(node => node.findAllByType("option").some(option => option.props.value === "full_access"));
    assert.equal(access.props.value, "", "inherited access stays inherited instead of being coerced to Ask");
    assert.match(text(access.findAllByType("option")[0]), /Full access.*Application default/, "known inherited permission and its owner are displayed");
    const tools = renderer.root.findAllByType("select").find(node => node.props.value === "inherit" && text(node).includes("1 selected"));
    await act(async () => tools.props.onChange({ target: { value: "choose" } }));
    assert.deepEqual(edits.at(-1).presented_tools, [], "explicit None clears inherited tools");
    assert.equal(text(renderer.root).includes("Inherit preset"), false);
  } finally { if (renderer) await act(async () => renderer.unmount()); }
}
