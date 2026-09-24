import assert from "node:assert/strict";
import React from "react";
import { act, create } from "react-test-renderer";
import { createServer } from "vite";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;
globalThis.window = { setTimeout, clearTimeout, setInterval, clearInterval };
const vite = await createServer({ appType: "custom", server: { middlewareMode: true, hmr: false }, logLevel: "error" });
const response = body => ({ ok: true, status: 200, json: async () => body });
const text = node => typeof node === "string" ? node : (node?.children ?? []).map(text).join("");
const settingRow = node => { let current = node; while (current && !String(current.props?.className ?? "").split(" ").includes("setting-row")) current = current.parent; assert.ok(current, "control sits in a shared setting row"); return current; };
const tick = () => new Promise(resolve => setTimeout(resolve, 0));
const bag = requested => ({ requested, applied: requested, unsupported: [], retired: [], overridden: [], unverified: [] });
const originalFetch = globalThis.fetch;
try {
  const { DeploymentsPanel } = await vite.ssrLoadModule("/src/renderer/DeploymentsPanel.tsx");
  const { SetupConfigurationEditor } = await vite.ssrLoadModule("/src/renderer/SetupConfigurationEditor.tsx");
  const { ChatModelControls } = await vite.ssrLoadModule("/src/renderer/ChatModelControls.tsx");
  await configurations(DeploymentsPanel);
  await retainedModelDrafts(DeploymentsPanel);
  await configurationNavigationOwnership(DeploymentsPanel);
  await configurationNavigationOwnership(DeploymentsPanel, true);
  await chatApplyOwnership(ChatModelControls, false);
  await chatApplyOwnership(ChatModelControls, true);
  await failedReloadFacts(DeploymentsPanel, ChatModelControls);
  await inheritedAccessAndEmptyTools(SetupConfigurationEditor);
} finally { globalThis.fetch = originalFetch; await vite.close(); }
console.log("Unified settings save, revision, inheritance and explicit-none checks passed.");

async function configurations(Panel) {
  const calls = [];
  const bundle = { id: "model", display_name: "Example model", default_configuration_id: "default", disk_matches: true, files: [], companions: [] };
  let profiles = [{ id: "default", bundle_id: "model", display_name: "Example model", revision: 4, bags: { startup: bag({ ctx_size: 8192, parallel: 1 }), per_request: bag({ temperature: 0.5, max_tokens: 512 }), agent: bag({}) } }];
  let renderer;
  const options = { bundle_id: "model", context_size: { maximum: 32768, options: [4096, 8192, 16384, 32768].map(value => ({ value, label: String(value) })) }, gpu_layers: { maximum: 32, options: [] }, startup_defaults: {}, per_request_defaults: {}, metadata: {} };
  globalThis.fetch = async (url, init = {}) => {
    const path = String(url), body = init.body ? JSON.parse(init.body) : null;
    calls.push({ path, method: init.method ?? "GET", body });
    if (path.endsWith("/v1/runtime")) return response({ status: "ready" });
    if (path.endsWith("/v1/deployments")) return response([]);
    if (path.includes("/configuration-options")) return response(options);
    if (path.endsWith("/projectors")) return response({ candidates: [] });
    if (path.endsWith("/v1/setup-resolution")) {
      const changes = body.overrides.per_request_overrides ?? {};
      const facts = Object.fromEntries(['temperature', 'max_tokens'].map(key => {
        const specified = Object.hasOwn(changes, key);
        const requested = specified ? changes[key] : profiles.find(item => item.id === body.overrides.model_configuration_id)?.bags.per_request.requested[key];
        const value = requested ?? (key === 'temperature' ? 0.8 : null);
        return [`per_request.${key}`, { value, known: value != null, source: requested == null ? 'Model default' : specified ? 'Application defaults' : 'Configuration: Example model' }];
      }));
      const startupChanges = body.overrides.startup_overrides ?? {};
      const ctxSize = startupChanges.ctx_size ?? profiles.find(item => item.id === body.overrides.model_configuration_id)?.bags.startup.requested.ctx_size;
      facts['startup.ctx_size'] = { value: ctxSize, known: ctxSize != null, source: Object.hasOwn(startupChanges, 'ctx_size') ? 'Application defaults' : 'Configuration: Example model' };
      return response({ configuration: body.overrides, effective_values: facts, instruction_layers: [] });
    }
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
    const lastPreview = () => calls.findLast(call => call.path.endsWith('/v1/setup-resolution')).body;
    assert.deepEqual(lastPreview().overrides.per_request_overrides, {}, 'unchanged saved response settings retain named configuration provenance');
    assert.deepEqual(lastPreview().overrides.startup_overrides, {}, 'unchanged startup settings remain inherited from the saved configuration');
    assert.equal(lastPreview().editing_layer, 'application', 'Models replacement preview excludes application and Chat overrides');
    assert.ok(text(renderer.root).includes('512'), 'the saved reply limit is displayed as its resolved value');
    assert.match(text(settingRow(renderer.root.findByProps({ id: 'model-ctx-size' }))), /8,192 tokens.*Configuration: Example model.*Set in configuration/, 'startup control displays its resolved value and saved source');
    await act(async () => { renderer.root.findByProps({ id: 'model-ctx-size' }).props.onChange({ target: { value: '16384' } }); await tick(); });
    assert.equal(lastPreview().overrides.startup_overrides.ctx_size, 16384, 'staged launch changes reach the shared setup preview');
    assert.match(text(settingRow(renderer.root.findByProps({ id: 'model-ctx-size' }))), /16,384 tokens.*This editor.*Selected for next load/, 'edited launch value and status replace stale saved readout');
    const numeric = label => {
      const ids = { Temperature: 'model-response-temperature', 'Reply limit': 'model-response-max_tokens' };
      return renderer.root.findAllByType('input').find(node => node.props.id === ids[label]);
    };
    await act(async () => { numeric('Temperature').props.onChange({ target: { value: '' } }); await tick(); });
    assert.equal(lastPreview().overrides.per_request_overrides.temperature, null, 'clearing a saved response setting explicitly resets the authoritative preview');
    assert.equal(numeric('Temperature').props.value, '', 'empty input remains an inherited setting, not a saved default');
    assert.equal(numeric('Temperature').props.placeholder, '0.8', 'the empty field previews the inherited value it will use');
    assert.match(text(settingRow(numeric('Temperature'))), /0\.8.*Model default.*Inherited/, 'resolved model default and its source are the visible readout');
    await act(async () => { numeric('Reply limit').props.onChange({ target: { value: '' } }); await tick(); });
    assert.equal(lastPreview().overrides.per_request_overrides.max_tokens, null);
    assert.match(text(settingRow(numeric('Reply limit'))), /Not reported.*Inherited/, 'unknown default is not invented from the saved value');
    assert.ok(button("Save changes"), "save is available without a running deployment");
    await act(async () => { button("Save changes").props.onClick(); await tick(); });
    assert.equal(profiles[0].bags.per_request.requested.temperature, undefined, 'saving commits the same numeric removal shown in preview');
    assert.equal(profiles[0].bags.per_request.requested.max_tokens, undefined);
    await act(async () => { button("Save changes").props.onClick(); await tick(); });
    assert.equal(profiles.length, 1, "ordinary repeated saving does not create another configuration");
    assert.equal(profiles[0].revision, 6);
    assert.equal(profiles[0].bags.startup.requested.port, undefined, "automatic port is not frozen into a saved configuration");
    assert.equal(calls.some(call => call.path.includes("/deployments/managed")), false, "saving never creates a deployment");
    await act(async () => { button("Save as configuration").props.onClick(); });
    await act(async () => { button("Create configuration").props.onClick(); await tick(); });
    assert.equal(profiles.length, 2, "only explicit Save as configuration creates another configuration");
    assert.equal(profiles[1].display_name, "Example model copy");
  } finally { if (renderer) await act(async () => renderer.unmount()); }
}

async function retainedModelDrafts(Panel) {
  const bundles = ["first", "second"].map(id => ({ id, display_name: id, default_configuration_id: `${id}-default`, disk_matches: true, files: [], companions: [] }));
  const profiles = [
    { id: "first-default", bundle_id: "first", display_name: "First default", revision: 1, bags: { startup: bag({ ctx_size: 8192 }), per_request: bag({}), agent: bag({}) } },
    { id: "first-variant", bundle_id: "first", display_name: "First variant", revision: 1, bags: { startup: bag({ ctx_size: 4096 }), per_request: bag({}), agent: bag({}) } },
    { id: "second-default", bundle_id: "second", display_name: "Second default", revision: 1, bags: { startup: bag({ ctx_size: 4096 }), per_request: bag({}), agent: bag({}) } },
  ];
  let selected = "first", renderer, dirty = new Set();
  globalThis.fetch = async (url, init = {}) => {
    const path = String(url);
    if (path.endsWith("/v1/runtime")) return response({ status: "ready" });
    if (path.endsWith("/v1/deployments")) return response([]);
    if (path.endsWith("/projectors")) return response({ candidates: [] });
    if (path.includes("/configuration-options")) return response({ bundle_id: path.includes("/first/") ? "first" : "second", context_size: { maximum: 32768, options: [] }, gpu_layers: { maximum: 32 }, startup_defaults: {}, per_request_defaults: {}, metadata: {} });
    if (path.endsWith("/v1/setup-resolution")) return response({ configuration: JSON.parse(init.body).overrides, effective_values: {}, instruction_layers: [] });
    throw new Error(`Unexpected draft request ${path}`);
  };
  const props = () => ({ selectedBundleId: selected, initialBundles: bundles, initialProfiles: profiles, onDirtyModelsChange: ids => { dirty = ids; } });
  try {
    await act(async () => { renderer = create(React.createElement(Panel, props())); await tick(); });
    await act(async () => renderer.root.findByProps({ id: "model-ctx-size" }).props.onChange({ target: { value: "16384" } }));
    assert.ok(dirty.has("first"), "an unsaved edit marks its model");
    await act(async () => { selected = "second"; renderer.update(React.createElement(Panel, props())); await tick(); });
    assert.ok(dirty.has("first"), "another model keeps the earlier unsaved marker");
    await act(async () => { selected = "first"; renderer.update(React.createElement(Panel, props())); await tick(); });
    assert.equal(renderer.root.findByProps({ id: "model-ctx-size" }).props.value, "16384", "unsaved startup edit survives model switching");
    const configuration = () => renderer.root.findAllByType("select").find(node => node.findAllByType("option").some(option => option.props.value === "first-variant"));
    await act(async () => configuration().props.onChange({ target: { value: "first-variant" } }));
    await act(async () => renderer.root.findByProps({ id: "model-ctx-size" }).props.onChange({ target: { value: "12288" } }));
    await act(async () => configuration().props.onChange({ target: { value: "first-default" } }));
    assert.equal(renderer.root.findByProps({ id: "model-ctx-size" }).props.value, "16384", "the first configuration keeps its draft");
    await act(async () => configuration().props.onChange({ target: { value: "first-variant" } }));
    assert.equal(renderer.root.findByProps({ id: "model-ctx-size" }).props.value, "12288", "the second configuration keeps its own draft");
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
    await act(async () => renderer.root.findByProps({ id: 'model-ctx-size' }).props.onChange({ target: { value: '16384' } }));
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
    if (navigateBack) assert.equal(Number(renderer.root.findByProps({ id: 'model-ctx-size' }).props.value), 16384, 'the saved revision is visible after returning');
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

async function failedReloadFacts(Panel, ChatControl) {
  const profile = { id: 'config', bundle_id: 'model', display_name: 'Default', revision: 1, bags: { startup: bag({ ctx_size: 8192 }), per_request: bag({}), agent: bag({}) } };
  const bundle = { id: 'model', display_name: 'Example', default_configuration_id: 'config', disk_matches: true, files: [], companions: [] };
  let deployment = { id: 'deploy', bundle_id: 'model', profile_id: 'config', display_name: 'Example', scope: 'managed', status: 'running', health: { healthy: true }, server_props: { n_ctx: 8192 }, applied_startup: { ctx_size: 8192 }, settings: profile.bags, updated_at: 'old', startup_overrides: {} };
  let renderer, reads = 0, reloads = 0;
  const originalError = 'The previous configuration is saved; recovery is needed.';
  globalThis.fetch = async (url, init = {}) => {
    const path = String(url), body = init.body ? JSON.parse(init.body) : null;
    if (path.endsWith('/v1/runtime')) return response({ status: 'ready' });
    if (path.endsWith('/v1/deployments')) { reads++; return response([deployment]); }
    if (path.endsWith('/projectors')) return response({ candidates: [] });
    if (path.includes('/configuration-options')) return response({ bundle_id: 'model', context_size: { maximum: 32768, options: [4096, 8192, 16384].map(value => ({ value, label: String(value) })) }, gpu_layers: { maximum: 32 }, startup_defaults: {}, per_request_defaults: {}, metadata: {} });
    if (path.endsWith('/v1/settings/preview')) return response({ startup: bag(body.startup), per_request: bag(body.per_request), agent: bag({}) });
    if (path.endsWith('/v1/setup-resolution')) return response({ configuration: { ...body.overrides, deployment_id: 'deploy' }, effective_values: { 'startup.ctx_size': { value: body.overrides.startup_overrides?.ctx_size ?? 8192, requires_reload: true } }, instruction_layers: [] });
    if (path.endsWith('/reconfigure')) {
      deployment = { ...deployment, status: 'failed', health: { healthy: false }, server_props: null, error: 'Recovery needed' };
      return { ok: false, status: 409, json: async () => ({ error: originalError, code: 'reconfigure_failed', details: { recovered: false } }) };
    }
    throw new Error(`Unexpected failed reload request ${path}`);
  };
  try {
    await act(async () => { renderer = create(React.createElement(Panel, { selectedBundleId: 'model', initialBundles: [bundle], initialProfiles: [profile] })); await tick(); });
    await act(async () => renderer.root.findByProps({ id: 'model-ctx-size' }).props.onChange({ target: { value: '16384' } }));
    await act(async () => { renderer.root.findByProps({ className: 'model-settings' }).props.onSubmit({ preventDefault() {} }); await tick(); });
    assert.ok(reads > 1, 'failed Apply refreshes the receiver state instead of retaining a stale healthy deployment');
    const badges = renderer.root.findAll(node => node.type === 'span' && String(node.props.className).startsWith('badge '));
    assert.equal(badges.some(node => text(node) === 'Ready'), false, 'a failed receiver is no longer labeled Ready');
    assert.ok(text(renderer.root).includes('Needs attention'));
    assert.ok(text(renderer.root).includes(originalError));
    assert.equal(Number(renderer.root.findByProps({ id: 'model-ctx-size' }).props.value), 16384, 'failed reload refresh preserves staged edits');
    await act(async () => renderer.unmount()); renderer = null;
    deployment = { ...deployment, status: 'running', health: { healthy: true }, server_props: { n_ctx: 8192 } };
    await act(async () => { renderer = create(React.createElement(ChatControl, { profiles: [profile], deployments: [deployment], selectedDeploymentId: 'deploy', configuration: { model_configuration_id: 'config' }, onApply: () => assert.fail('failed reload must not apply'), onReloaded: async () => { reloads++; throw new Error('Secondary refresh failure'); } })); await tick(); });
    await act(async () => { renderer.root.findByProps({ 'aria-label': 'Exact context size' }).props.onChange({ target: { value: '16384' } }); await tick(); });
    await act(async () => { renderer.root.findAllByType('button').find(node => text(node) === 'Apply & reload').props.onClick(); await tick(); });
    assert.equal(reloads, 1, 'Chat also refreshes failed reload facts');
    assert.ok(text(renderer.root).includes(originalError), 'refresh failures retain the actual lifecycle failure');
    assert.equal(text(renderer.root).includes('Secondary refresh failure'), false);
    assert.equal(Number(renderer.root.findByProps({ 'aria-label': 'Exact context size' }).props.value), 16384);
  } finally { if (renderer) await act(async () => renderer.unmount()); }
}
