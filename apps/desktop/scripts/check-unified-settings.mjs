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
  const { ChatModelControls } = await vite.ssrLoadModule("/src/renderer/ChatModelControls.tsx");
  await configurations(DeploymentsPanel);
  await configurationNavigationOwnership(DeploymentsPanel);
  await configurationNavigationOwnership(DeploymentsPanel, true);
  await chatApplyOwnership(ChatModelControls, false);
  await chatApplyOwnership(ChatModelControls, true);
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

async function configurationNavigationOwnership(Panel, navigateBack = false) {
  const bundles = ['first', 'second'].map(id => ({ id, display_name: id, default_configuration_id: `${id}-default`, disk_matches: true, files: [], companions: [] }));
  const profiles = bundles.map(bundle => ({ id: bundle.default_configuration_id, bundle_id: bundle.id, display_name: `${bundle.id} configuration`, revision: 1, bags: { startup: bag({ ctx_size: 8192 }), per_request: bag({}), agent: bag({}) } }));
  const saves = [];
  let selected = 'first', renderer, releasePreview;
  globalThis.fetch = async (url, init = {}) => {
    const path = String(url), body = init.body ? JSON.parse(init.body) : null;
    if (path.endsWith('/v1/runtime')) return response({ status: 'ready' });
    if (path.endsWith('/v1/deployments')) return response([]);
    if (path.endsWith('/projectors')) return response({ candidates: [] });
    if (path.includes('/configuration-options')) return response({ bundle_id: path.includes('/first/') ? 'first' : 'second', context_size: { maximum: 32768, options: [4096, 8192, 16384].map(value => ({ value, label: String(value) })) }, gpu_layers: { maximum: 32 }, startup_defaults: {}, per_request_defaults: {}, metadata: {} });
    if (path.endsWith('/v1/setup-resolution')) return response({ configuration: body.overrides, effective_values: {}, instruction_layers: [] });
    if (path.endsWith('/v1/settings/preview')) return await new Promise(resolve => { releasePreview = () => resolve(response({ startup: bag(body.startup), per_request: bag(body.per_request), agent: bag({}) })); });
    if (path.endsWith('/configurations')) {
      saves.push({ path, body });
      profiles[0] = { ...profiles[0], revision: 2, bags: { startup: bag(body.startup), per_request: bag(body.per_request), agent: bag({}) } };
      return response(profiles[0]);
    }
    throw new Error(`Unexpected navigation request ${path}`);
  };
  const props = () => ({ selectedBundleId: selected, initialBundles: bundles, initialProfiles: [...profiles], onBundlesChanged: async () => { renderer.update(React.createElement(Panel, props())); } });
  try {
    await act(async () => { renderer = create(React.createElement(Panel, props()), { createNodeMock: element => element.type === 'form' ? { reportValidity: () => true } : null }); await tick(); });
    const button = label => renderer.root.findAllByType('button').find(node => text(node) === label);
    await act(async () => renderer.root.findByProps({ 'aria-label': 'Exact context size' }).props.onChange({ target: { value: '16384' } }));
    await act(async () => { button('Save changes').props.onClick(); await tick(); });
    assert.ok(releasePreview, 'save waits at the actual preview receiver');
    await act(async () => { selected = 'second'; renderer.update(React.createElement(Panel, props())); await tick(); });
    if (navigateBack) await act(async () => { selected = 'first'; renderer.update(React.createElement(Panel, props())); await tick(); });
    await act(async () => { releasePreview(); await tick(); });
    assert.equal(saves.length, 1);
    assert.ok(saves[0].path.includes('/first/'), 'a pending save remains owned by its original model');
    assert.equal(saves[0].body.startup.ctx_size, 16384, 'navigation cannot remove staged edits from an already requested save');
    const chooser = renderer.root.findAllByType('select').find(node => node.findAllByType('option').some(option => option.props.value === `${selected}-default`));
    assert.equal(chooser.props.value, `${selected}-default`, 'old completion cannot replace the newly selected configuration');
    if (navigateBack) assert.equal(Number(renderer.root.findByProps({ 'aria-label': 'Exact context size' }).props.value), 16384, 'a clean editor refreshes to the newly saved revision after returning');
    assert.equal(text(renderer.root).includes('Configuration saved.'), false, 'old status is not shown as completion for the new model');
    assert.equal(text(renderer.root).includes('Checked launch settings'), false, 'old checked settings are not presented for the new model');
  } finally { if (renderer) await act(async () => renderer.unmount()); }
}

async function chatApplyOwnership(Control, navigateAwayAndBack) {
  const profile = { id: 'config', bundle_id: 'model', display_name: 'Default', revision: 1, bags: { startup: bag({ ctx_size: 8192 }), per_request: bag({}), agent: bag({}) } };
  const deployment = { id: 'deploy', bundle_id: 'model', profile_id: 'config', display_name: 'Model', scope: 'managed', health: { healthy: true }, server_props: { n_ctx: 8192 }, updated_at: 'old', settings: profile.bags };
  const applied = [];
  let renderer, releaseReload, conversationId = 'first-chat', configuration = { model_configuration_id: 'config', approval_mode: 'full_access' };
  globalThis.fetch = async (url, init = {}) => {
    const path = String(url), body = init.body ? JSON.parse(init.body) : null;
    if (path.endsWith('/v1/setup-resolution')) return response({ configuration: { ...body.overrides, deployment_id: 'deploy' }, effective_values: { 'startup.ctx_size': { value: body.overrides.startup_overrides?.ctx_size ?? 8192, requires_reload: body.overrides.startup_overrides?.ctx_size === 16384 } }, instruction_layers: [] });
    if (path.includes('/configuration-options')) return response({ bundle_id: 'model', context_size: { maximum: 32768, options: [8192, 16384].map(value => ({ value, label: String(value) })) }, per_request_defaults: {}, startup_defaults: {} });
    if (path.endsWith('/reconfigure')) return response({ ...deployment, server_props: { n_ctx: 16384 } });
    throw new Error(`Unexpected chat settings request ${path}`);
  };
  const props = () => ({ profiles: [profile], deployments: [deployment], selectedDeploymentId: 'deploy', conversationId, configuration,
    onApply: value => applied.push(value), onReloaded: async () => await new Promise(resolve => { releaseReload = resolve; }) });
  try {
    await act(async () => { renderer = create(React.createElement(Control, props())); await tick(); });
    await act(async () => { renderer.root.findByProps({ 'aria-label': 'Exact context size' }).props.onChange({ target: { value: '16384' } }); await tick(); });
    const apply = renderer.root.findAllByType('button').find(node => text(node) === 'Apply & reload');
    await act(async () => { apply.props.onClick(); await tick(); });
    assert.ok(releaseReload, 'Apply reached the model reload completion boundary');
    if (navigateAwayAndBack) {
      await act(async () => { conversationId = 'second-chat'; renderer.update(React.createElement(Control, props())); await tick(); });
      await act(async () => { conversationId = 'first-chat'; renderer.update(React.createElement(Control, props())); await tick(); });
    } else {
      await act(async () => { configuration = { ...configuration, approval_mode: 'ask', helper_agent_ids: ['new-helper'] }; renderer.update(React.createElement(Control, props())); await tick(); });
    }
    await act(async () => { releaseReload(); await tick(); });
    if (navigateAwayAndBack) assert.equal(applied.length, 0, 'navigation generation invalidates old Apply even after returning to the same conversation');
    else {
      assert.equal(applied.length, 1);
      assert.equal(applied[0].approval_mode, 'ask', 'model Apply must preserve a newer Access choice');
      assert.deepEqual(applied[0].helper_agent_ids, ['new-helper'], 'model Apply must preserve newer helper selection');
      assert.equal(applied[0].startup_overrides.ctx_size, 16384);
    }
  } finally { if (renderer) await act(async () => renderer.unmount()); }
}
