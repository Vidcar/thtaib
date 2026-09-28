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
  await configurations(DeploymentsPanel);
  await sameBundleVariantsLoadSeparately(DeploymentsPanel);
  await retainedModelDrafts(DeploymentsPanel);
  await configurationNavigationOwnership(DeploymentsPanel);
  await configurationNavigationOwnership(DeploymentsPanel, true);
  await failedReloadFacts(DeploymentsPanel);
  await projectKnowledgeOwnership(SetupConfigurationEditor);
  await agentOwnedSettings(SetupConfigurationEditor);
  await toolGroupSelection(SetupConfigurationEditor);
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
    if (path.endsWith("/v1/runtime/models")) return response({ max_loaded_models: 1, loaded_deployment_ids: [], loading_deployment_ids: [], router_status: "stopped" });
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
        return [`per_request.${key}`, { value, known: value != null, source: requested == null ? 'Model default' : specified ? 'Turn overrides' : 'Configuration: Example model', default_value: key === 'temperature' ? 0.8 : null, default_source: 'Model default' }];
      }));
      const startupChanges = body.overrides.startup_overrides ?? {};
      const ctxSize = startupChanges.ctx_size ?? profiles.find(item => item.id === body.overrides.model_configuration_id)?.bags.startup.requested.ctx_size;
      facts['startup.ctx_size'] = { value: ctxSize, known: ctxSize != null, source: Object.hasOwn(startupChanges, 'ctx_size') ? 'Turn overrides' : 'Configuration: Example model' };
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
    assert.equal(lastPreview().editing_layer, 'conversation', 'Models preview uses the existing model-capable resolver boundary');
    assert.equal(lastPreview().project_id, null, 'Models preview excludes project selection');
    assert.equal(lastPreview().agent_setup_version_id, null, 'Models preview excludes agent selection');
    assert.ok(text(renderer.root).includes('512'), 'the saved reply limit is displayed as its resolved value');
    assert.match(text(settingRow(renderer.root.findByProps({ id: 'model-ctx-size' }))), /8,192 tokens.*Configuration default/, 'startup control displays its resolved value and saved source');
    await act(async () => { renderer.root.findByProps({ id: 'model-ctx-size' }).props.onChange({ target: { value: '16384' } }); await tick(); });
    assert.equal(lastPreview().overrides.startup_overrides.ctx_size, 16384, 'staged launch changes reach the shared setup preview');
    assert.match(text(settingRow(renderer.root.findByProps({ id: 'model-ctx-size' }))), /16,384 tokens.*This editor.*Unsaved change/, 'edited launch value and status replace stale saved readout');
    await act(async () => { renderer.root.findByProps({ id: 'model-ctx-size' }).props.onChange({ target: { value: '8192' } }); await tick(); });
    assert.deepEqual(lastPreview().overrides.startup_overrides, {}, 'returning to the saved startup value removes the preview override');
    assert.match(text(settingRow(renderer.root.findByProps({ id: 'model-ctx-size' }))), /8,192 tokens.*Configuration default/, 'a reverted field follows the saved configuration again');
    assert.ok(!text(settingRow(renderer.root.findByProps({ id: 'model-ctx-size' }))).includes('Unsaved change'), 'reverted field clears its dirty provenance');
    assert.equal(renderer.root.findByProps({ className: 'badge model-edit-state' }).props['data-dirty'], false, 'reverted editor clears its dirty indicator');
    await act(async () => { renderer.root.findByProps({ id: 'model-ctx-size' }).props.onChange({ target: { value: '16384' } }); await tick(); });
    const numeric = label => {
      const ids = { Temperature: 'model-response-temperature', 'Reply limit': 'model-response-max_tokens' };
      return renderer.root.findAllByType('input').find(node => node.props.id === ids[label]);
    };
    await act(async () => { numeric('Temperature').props.onChange({ target: { value: '' } }); await tick(); });
    assert.equal(lastPreview().overrides.per_request_overrides.temperature, null, 'clearing a saved response setting explicitly resets the authoritative preview');
    assert.equal(numeric('Temperature').props.value, '', 'empty input remains an inherited setting, not a saved default');
    assert.equal(numeric('Temperature').props.placeholder, '0.8', 'the empty field previews the inherited value it will use');
    assert.equal(numeric('Temperature').props.max, undefined, 'exact entry is not capped by the slider range');
    assert.equal(numeric('Temperature').props.step, 'any', 'exact entry accepts any precision');
    assert.match(text(settingRow(numeric('Temperature'))), /0\.8.*Model default/, 'resolved model default and its source are the visible readout');
    assert.ok(!text(settingRow(numeric('Temperature'))).includes('Inherited'), 'default following is described by its actual value and source');
    await act(async () => { numeric('Reply limit').props.onChange({ target: { value: '' } }); await tick(); });
    assert.equal(lastPreview().overrides.per_request_overrides.max_tokens, null);
    assert.match(text(settingRow(numeric('Reply limit'))), /Not reported/, 'unknown default is not invented from the saved value');
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
    if (path.endsWith("/v1/runtime/models")) return response({ max_loaded_models: 1, loaded_deployment_ids: [], loading_deployment_ids: [], router_status: "stopped" });
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

async function projectKnowledgeOwnership(Editor) {
  let renderer;
  const edits = [];
  const catalogue = { bundles: [], profiles: [], deployments: [], knowledge: [], connections: [], tools: [] };
  globalThis.fetch = async (url, init) => {
    assert.ok(String(url).endsWith("/v1/setup-resolution"));
    const request = JSON.parse(init.body);
    assert.equal(request.editing_layer, "project");
    return response({ configuration: { approval_mode: "full_access" }, effective_values: { approval_mode: { value: "full_access", source: "Application default", known: true, inherited: true }, presented_tools: { value: ["read_file"], source: "Application default", known: true, inherited: true } }, instruction_layers: [] });
  };
  try {
    await act(async () => { renderer = create(React.createElement(Editor, { value: { approval_mode: "full_access", presented_tools: ["read_file"], model_configuration_id: "stale" }, scope: "project", projectId: "project", catalogue, onChange: value => edits.push(value) })); await tick(); });
    assert.match(text(renderer.root), /Project knowledge/, "project editor owns knowledge");
    assert.doesNotMatch(text(renderer.root), /Access|Tools|Helper model|Protected instructions/, "project editor cannot save Chat access, model selection, or agent instructions");
    const memoryChoice = renderer.root.findAll(node => node.props.role === "radiogroup")[0];
    await act(async () => memoryChoice.findAll(node => node.type === "input" && node.props.type === "radio" && node.props.value === "choose")[0].props.onChange());
    assert.deepEqual(edits.at(-1), { memory_entry_ids: [] }, "project knowledge keeps record identities and drops execution fields");
  } finally { if (renderer) await act(async () => renderer.unmount()); }
}

async function configurationNavigationOwnership(Panel, navigateBack = false) {
  const bundles = ['first', 'second'].map(id => ({ id, display_name: id, default_configuration_id: `${id}-default`, disk_matches: true, files: [], companions: [] }));
  const profiles = bundles.map(bundle => ({ id: bundle.default_configuration_id, bundle_id: bundle.id, display_name: `${bundle.id} configuration`, revision: 1, bags: { startup: bag({ ctx_size: 8192 }), per_request: bag({}), agent: bag({}) } }));
  const saves = [];
  let selected = 'first', renderer, releasePreview;
  globalThis.fetch = async (url, init = {}) => {
    const path = String(url), body = init.body ? JSON.parse(init.body) : null;
    if (path.endsWith('/v1/runtime/models')) return response({ max_loaded_models: 1, loaded_deployment_ids: [], loading_deployment_ids: [], router_status: 'stopped' });
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

async function failedReloadFacts(Panel) {
  const profile = { id: 'config', bundle_id: 'model', display_name: 'Default', revision: 1, bags: { startup: bag({ ctx_size: 8192 }), per_request: bag({}), agent: bag({}) } };
  const bundle = { id: 'model', display_name: 'Example', default_configuration_id: 'config', disk_matches: true, files: [], companions: [] };
  let deployment = { id: 'deploy', bundle_id: 'model', profile_id: 'config', display_name: 'Example', scope: 'managed', status: 'running', health: { healthy: true }, server_props: { n_ctx: 8192 }, applied_startup: { ctx_size: 8192 }, settings: profile.bags, updated_at: 'old', startup_overrides: {} };
  let renderer, reads = 0;
  const originalError = 'The previous configuration is saved; recovery is needed.';
  globalThis.fetch = async (url, init = {}) => {
    const path = String(url), body = init.body ? JSON.parse(init.body) : null;
    if (path.endsWith('/v1/runtime/models')) return response({ max_loaded_models: 1, loaded_deployment_ids: [], loading_deployment_ids: [], router_status: 'stopped' });
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
  } finally { if (renderer) await act(async () => renderer.unmount()); }
}

async function sameBundleVariantsLoadSeparately(Panel) {
  const bundle = { id: "model", display_name: "Example", default_configuration_id: "variant-a", disk_matches: true, files: [], companions: [] };
  const profiles = ["a", "b"].map(name => ({ id: `variant-${name}`, bundle_id: "model", display_name: `Variant ${name.toUpperCase()}`, revision: 1, bags: { startup: bag({ ctx_size: name === "a" ? 8192 : 16384 }), per_request: bag({}), agent: bag({}) } }));
  const deployment = (name, ctx) => ({ id: `deploy-${name}`, bundle_id: "model", profile_id: `variant-${name}`, display_name: `managed:Variant ${name.toUpperCase()}`, scope: "managed", status: "running", health: { healthy: true }, server_props: { n_ctx: ctx }, applied_startup: { ctx_size: ctx }, settings: profiles.find(profile => profile.id === `variant-${name}`).bags, updated_at: "current", startup_overrides: {} });
  let deployments = [deployment("a", 8192)];
  const calls = [];
  globalThis.fetch = async (url, init = {}) => {
    const path = String(url), body = init.body ? JSON.parse(init.body) : null;
    calls.push({ path, method: init.method ?? "GET", body });
    if (path.endsWith("/v1/runtime/models")) return response({ max_loaded_models: 2, loaded_deployment_ids: deployments.map(item => item.id), loading_deployment_ids: [], router_status: "running" });
    if (path.endsWith("/v1/runtime")) return response({ status: "ready" });
    if (path.endsWith("/v1/deployments")) return response(deployments);
    if (path.includes("/configuration-options")) return response({ bundle_id: "model", context_size: { maximum: 32768, options: [] }, gpu_layers: { maximum: 32 }, startup_defaults: {}, per_request_defaults: {}, metadata: {} });
    if (path.endsWith("/projectors")) return response({ candidates: [] });
    if (path.endsWith("/v1/setup-resolution")) return response({ configuration: body.overrides, effective_values: {}, instruction_layers: [] });
    if (path.endsWith("/v1/settings/preview")) return response({ startup: bag(body.startup), per_request: bag(body.per_request), agent: bag({}) });
    if (path.endsWith("/v1/deployments/managed")) { deployments = [...deployments, deployment("b", 16384)]; return response(deployments.at(-1)); }
    if (path.endsWith("/configurations")) return response({ ...profiles[1], revision: 2, display_name: body.display_name });
    throw new Error(`Unexpected variant request ${path}`);
  };
  let renderer;
  try {
    await act(async () => { renderer = create(React.createElement(Panel, { selectedBundleId: "model", initialBundles: [bundle], initialProfiles: profiles })); await tick(); });
    await act(async () => renderer.root.findByProps({ id: "model-configuration" }).props.onChange({ target: { value: "variant-b" } }));
    const submit = () => renderer.root.findByProps({ className: "model-settings" });
    assert.ok(renderer.root.findAllByType("button").some(item => text(item) === "Load"), "variant B is offered a separate load while A is running");
    await act(async () => { submit().props.onSubmit({ preventDefault() {} }); await tick(); });
    assert.ok(calls.some(call => call.path.endsWith("/v1/deployments/managed") && call.body.profile_id === "variant-b"), "Models loads exact variant B");
    assert.equal(calls.some(call => call.path.endsWith("/reconfigure")), false, "Models does not reconfigure variant A when selecting B");
    assert.equal(deployments[0].profile_id, "variant-a", "variant A remains bound to its original setup");
  } finally { if (renderer) await act(async () => renderer.unmount()); }
}

async function agentOwnedSettings(Editor) {
  const edits = [];
  const catalogue = { bundles: [{ id: "model", display_name: "Local model" }], profiles: [{ id: "fixed-config", bundle_id: "model", display_name: "Precise" }], deployments: [], connections: [], tools: [{ id: "execute", name: "Run shell" }, { id: "browser_navigate", name: "Navigate" }], knowledge: [{ kind: "protected_instruction", id: "instruction", current_version_id: "instruction_v1", display_name: "Editorial rules", enabled: true }] };
  globalThis.fetch = async (url, init) => {
    assert.ok(String(url).endsWith("/v1/setup-resolution"));
    assert.equal(JSON.parse(init.body).editing_layer, "agent");
    return response({ configuration: {}, effective_values: {}, instruction_layers: [] });
  };
  let renderer;
  try {
    const helper = { id: "helper", name: "Research helper", configuration: {}, missing_dependencies: [{ kind: "main", id: "main", reason: "Main role unavailable" }], helper_missing_dependencies: [] };
    await act(async () => { renderer = create(React.createElement(Editor, { value: { approval_mode: "full_access", presented_tools: ["execute"] }, scope: "agent", catalogue, agentOptions: [helper], onChange: value => edits.push(value) })); await tick(); });
    assert.doesNotMatch(text(renderer.root), /Default access for new chats/, "agent editor cannot assign main Chat access");
    await act(async () => renderer.root.findByProps({ "aria-label": "Add helper" }).props.onChange({ target: { value: "helper" } }));
    const addHelper = renderer.root.findAllByType("button").find(node => text(node).trim() === "Add helper");
    assert.equal(addHelper.props.disabled, false, "helper eligibility uses helper dependencies, not main role dependencies");
    await act(async () => addHelper.props.onClick());
    assert.deepEqual(edits.at(-1).helper_agent_ids, ["helper"], "agent can select named helpers");
    assert.equal(edits.at(-1).approval_mode, undefined, "agent edit drops stale access");
    assert.deepEqual(edits.at(-1).presented_tools, ["execute"], "agent edit retains agent-owned tools");
    await act(async () => renderer.root.findByProps({ role: "switch", "aria-label": "Review before finishing" }).props.onClick());
    assert.deepEqual(edits.at(-1).review, { enabled: true, criteria: "", max_revisions: 2 }, "agent review has a bounded revision count");
    const protectedChoice = renderer.root.findAll(node => node.props.role === "radiogroup")[2];
    await act(async () => protectedChoice.findAll(node => node.type === "input" && node.props.type === "radio" && node.props.value === "choose")[0].props.onChange());
    assert.deepEqual(edits.at(-1).protected_instruction_entry_ids, [], "agent owns protected-instruction record selection");
    await act(async () => renderer.root.findByProps({ role: "switch", "aria-label": "Browser" }).props.onClick());
    assert.deepEqual(edits.at(-1).presented_tools, ["execute", "browser_navigate"], "group selection updates canonical individual tools");
    assert.equal(edits.at(-1).desktop_access, undefined);
    await act(async () => renderer.root.findAllByType("select").find(node => text(node).includes("Use Chat model")).props.onChange({ target: { value: "configuration:fixed-config" } }));
    assert.equal(edits.at(-1).model_configuration_id, "fixed-config", "assigned model is agent-owned");
  } finally { if (renderer) await act(async () => renderer.unmount()); }
}

async function toolGroupSelection(Editor) {
  const edits = [];
  const catalogue = {
    bundles: [], profiles: [], deployments: [], connections: [], knowledge: [], toolCatalogueStatus: "ready",
    tools: [
      { id: "ls", name: "List files", description: "List authorized project files." },
      { id: "read_file", name: "Read files", description: "Read authorized project files." },
      { id: "execute", name: "Run shell" },
      { id: "browser_navigate", name: "Navigate" },
      { id: "echo", name: "Echo", available: false, unavailable_reason: "Restore its connection in Settings." },
    ],
  };
  globalThis.fetch = async (url, init) => {
    assert.ok(String(url).endsWith("/v1/setup-resolution"));
    return response({ configuration: JSON.parse(init.body).overrides, effective_values: {}, instruction_layers: [] });
  };
  let current, renderer;
  function Host(props) {
    const [value, setValue] = React.useState({ instructions: "Keep this draft", presented_tools: ["read_file", "execute", "missing_tool"] });
    current = value;
    return React.createElement(Editor, { ...props, value, sections: ["tools"], onChange: next => { edits.push(next); setValue(next); } });
  }
  const disclosure = name => renderer.root.findAllByType("button").find(node => node.props.className === "setup-tool-group-expand" && text(node).startsWith(name));
  const choice = name => renderer.root.findByProps({ role: "switch", "aria-label": name });
  const panel = name => renderer.root.findByProps({ id: disclosure(name).props["aria-controls"] });
  const action = label => renderer.root.findAllByType("button").find(node => text(node) === label);
  const click = async node => { await act(async () => { node.props.onClick(); await tick(); }); };
  const domParent = node => { let parent = node.parent; while (parent && typeof parent.type !== "string") parent = parent.parent; return parent; };
  try {
    await act(async () => { renderer = create(React.createElement(Host, { catalogue })); await tick(); });
    assert.equal(disclosure("Project files").props["aria-expanded"], false, "groups start collapsed");
    assert.equal(panel("Project files").props.hidden, true, "collapsed choices are hidden from keyboard and accessibility navigation");
    assert.match(text(disclosure("Project files")), /1 of 2 selected/, "a single selected/total count explains a partial group");
    assert.equal(choice("Project files").props["aria-checked"], false, "partial groups are on only when complete");
    assert.equal(disclosure("Project files").props.type, "button", "disclosure never submits the agent form");
    assert.ok(domParent(disclosure("Project files")) === domParent(choice("Project files")), "disclosure and group toggle are sibling controls");
    assert.equal(disclosure("Project files").parent.props.onClick, undefined, "the group does not intercept toggle clicks");
    assert.doesNotMatch(text(renderer.root), /Individual .* tools/, "there is no duplicate individual-tools heading");
    assert.equal(renderer.root.findAllByProps({ className: "setup-tool-group-count" }).length, 4, "each populated group has exactly one count");

    await click(disclosure("Project files"));
    await click(disclosure("Browser"));
    assert.equal(edits.length, 0, "expanding groups does not write configuration");
    assert.equal(panel("Project files").props.hidden, false);
    assert.equal(panel("Browser").props.hidden, false, "groups can stay open independently");
    await click(choice("Project files"));
    assert.deepEqual(new Set(current.presented_tools), new Set(["ls", "read_file", "execute", "missing_tool"]), "the partial switch completes its group and retains other choices");
    assert.equal(choice("Project files").props["aria-checked"], true);
    assert.equal(disclosure("Project files").props["aria-expanded"], true, "selection does not collapse a group");
    await click(choice("Read files"));
    assert.equal(choice("Project files").props["aria-checked"], false, "individual selection updates the group's state");
    assert.match(text(disclosure("Project files")), /1 of 2 selected/);
    assert.equal(panel("Project files").props.hidden, false);
    await click(choice("Project files"));
    await click(choice("Project files"));
    assert.deepEqual(current.presented_tools, ["execute", "missing_tool"], "a complete group switches off without clearing other groups or missing tools");
    await click(disclosure("Project files"));
    await click(choice("Project files"));
    assert.equal(panel("Project files").props.hidden, true, "a collapsed group toggle does not expand it");
    assert.equal(panel("Browser").props.hidden, false);
    assert.ok(text(renderer.root).includes("Restore its connection in Settings."), "unavailable individual tools retain corrective information");
    await click(choice("missing_tool"));
    assert.ok(!current.presented_tools.includes("missing_tool"), "missing saved choices remain removable");

    await click(action("Turn all off"));
    assert.deepEqual(current.presented_tools, [], "the bulk off action stays an explicit empty selection");
    assert.equal(panel("Browser").props.hidden, false);
    await click(action("Standard tools"));
    assert.equal(current.presented_tools, null, "the standard action retains canonical default-following semantics");
    assert.equal(choice("Project files").props["aria-checked"], true);
    assert.equal(choice("Host shell").props["aria-checked"], false);
    assert.equal(current.instructions, "Keep this draft", "tool editing retains unrelated draft fields");
    assert.equal(current.approval_mode, undefined, "selecting tools does not assign access");
    assert.equal(current.desktop_access, undefined);

    await act(async () => renderer.update(React.createElement(Host, { catalogue, disabled: true })));
    assert.equal(choice("Project files").props.disabled, true);
    assert.equal(choice("Read files").props.disabled, true);
    assert.equal(action("Standard tools").props.disabled, true);
    const beforeDisabled = edits.length;
    await click(disclosure("Project files"));
    assert.equal(panel("Project files").props.hidden, false, "disabled editing still permits inspecting choices");
    assert.equal(edits.length, beforeDisabled);

    await act(async () => renderer.update(React.createElement(Host, { catalogue: { ...catalogue, tools: [], toolCatalogueStatus: "loading" } })));
    assert.match(text(renderer.root), /Loading tool choices/, "loading is distinct from an empty catalogue");
    assert.equal(renderer.root.findAllByProps({ className: "setup-tool-group-expand" }).length, 0, "empty groups have no toggle");
    await act(async () => renderer.update(React.createElement(Host, { catalogue: { ...catalogue, tools: [], toolCatalogueStatus: "error" } })));
    assert.match(text(renderer.root), /Tool choices unavailable/, "catalogue failures retain the corrective state");
    assert.equal(current.instructions, "Keep this draft", "loading/error transitions retain the draft");
  } finally { if (renderer) await act(async () => renderer.unmount()); }
}
