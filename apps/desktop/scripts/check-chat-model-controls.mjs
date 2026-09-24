import assert from "node:assert/strict";
import path from "node:path";
import { fileURLToPath } from "node:url";
import React from "react";
import { act, create } from "react-test-renderer";
import { createServer as createViteServer } from "vite";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;
globalThis.window = Object.assign(new EventTarget(), { workbench: { backendUrl: "http://chat-model-controls.test" } });
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const vite = await createViteServer({ root, appType: "custom", server: { middlewareMode: true, hmr: false }, logLevel: "error" });
const { ChatModelControls } = await vite.ssrLoadModule("/src/renderer/ChatModelControls.tsx");
const { preferredChatDeploymentId } = await vite.ssrLoadModule("/src/renderer/ChatPanel.tsx");
const { api } = await vite.ssrLoadModule("/src/renderer/api.ts");
const { workspaceApi } = await vite.ssrLoadModule("/src/renderer/workspaceApi.ts");
const original = { modelConfiguration: api.modelConfiguration, reconfigure: api.reconfigure, start: api.start, startManaged: api.startManaged, saveModelConfiguration: api.saveModelConfiguration, resolveSetup: workspaceApi.resolveSetup };
const bag = (requested = {}) => ({ requested, applied: {}, overridden: [], unsupported: [], retired: [] });
const profile = (id, bundle) => ({ id, bundle_id: bundle, revision: 1, display_name: id === "model_a" ? "Qwen" : "Second model", bags: { startup: bag({ ctx_size: 32768, n_gpu_layers: 50 }), per_request: bag({ temperature: 0.7 }), agent: bag() } });
const deployment = (id, bundle, scope = "managed") => ({ id, profile_id: id === "dep_a" ? "model_a" : "model_b", bundle_id: bundle, display_name: `${scope}:${id}`, scope, status: "running", updated_at: "2026-09-23T12:00:00Z", health: { healthy: true }, server_props: { n_ctx: 32768 }, applied_startup: { ctx_size: 32768, n_gpu_layers: 50 }, settings: { startup: bag(), per_request: bag(), agent: bag() } });
const option = value => ({ value, label: value === "xhigh" ? "Xhigh" : value[0].toUpperCase() + value.slice(1) });
const options = (efforts = ["low", "medium", "xhigh"]) => ({ context_size: { maximum: 131072, options: [8192, 32768, 65536, 131072].map(value => ({ value, label: String(value) })) }, per_request_defaults: { reasoning: { supported: true, options: ["auto", "on", "off"].map(option) }, reasoning_effort: { supported: true, options: efforts.map(option) } } });
const fact = (value, source = "Model default", requires_reload = false) => ({ value, source, known: value != null, inherited: true, requires_reload });
function preview(config = {}) {
  const id = config.model_configuration_id ?? "model_a";
  const dep = config.deployment_id ?? (id === "model_b" ? "dep_b" : "dep_a");
  const context = config.startup_overrides?.ctx_size ?? 32768;
  return { configuration: { ...config, deployment_id: dep, model_configuration_id: config.deployment_id === "connected" ? null : id }, instruction_layers: [], effective_values: {
    model_selection: fact(id === "model_b" ? "Second model" : "Qwen", "Loaded model"),
    model_configuration_target: { ...fact(config.deployment_id === "connected" ? null : id, "Qwen · Default"), unavailable_reason: config.deployment_id === "connected" ? "Connected models are configured by their external server." : null },
    "startup.ctx_size": fact(context, "Conversation", context !== 32768),
    "per_request.reasoning": fact(config.per_request_overrides?.reasoning ?? "on"),
    "per_request.reasoning_effort": fact(config.per_request_overrides?.reasoning_effort ?? "xhigh"),
  } };
}
function deferred() { let resolve; const promise = new Promise(r => { resolve = r; }); return { promise, resolve }; }
function text(node) { return typeof node === "string" ? node : (node?.children ?? []).map(text).join(""); }
function button(renderer, label) { const found = renderer.root.findAll(node => node.type === "button" && text(node) === label)[0]; assert.ok(found, `button ${label}`); return found; }
function range(renderer, label) { return renderer.root.findAll(node => node.type === "input" && node.props.type === "range" && node.props["aria-label"] === label)[0]; }
async function flush() { await act(async () => { for (let i = 0; i < 6; i++) await Promise.resolve(); }); }
async function render(overrides = {}, resolve = preview) {
  const applied = [], saved = [], reloads = [], reconfigured = [], started = [], managed = [];
  workspaceApi.resolveSetup = async (_project, _agent, config) => resolve(config);
  api.modelConfiguration = async () => options();
  api.reconfigure = async (id, payload) => { reconfigured.push({ id, payload }); return deployment(id, "bundle_a"); };
  api.start = async id => { started.push(id); return deployment(id, "bundle_a"); };
  api.startManaged = async (bundle, profileId, startup) => { managed.push({ bundle, profileId, startup }); return deployment("dep_variant", bundle); };
  api.saveModelConfiguration = async (bundle, payload) => { saved.push({ bundle, payload }); return profile(payload.configuration_id, bundle); };
  const props = { deployments: [deployment("dep_a", "bundle_a"), deployment("dep_b", "bundle_b"), deployment("connected", null, "connected")], profiles: [profile("model_a", "bundle_a"), profile("model_b", "bundle_b")], selectedDeploymentId: "dep_a", configuration: { model_configuration_id: "model_a" }, onApply: value => applied.push(value), onReloaded: async () => { reloads.push(true); }, ...overrides };
  let renderer;
  await act(async () => { renderer = create(React.createElement(ChatModelControls, props)); });
  await flush();
  return { renderer, props, applied, saved, reloads, reconfigured, started, managed, async update(value) { Object.assign(props, value); await act(async () => renderer.update(React.createElement(ChatModelControls, props))); await flush(); }, async close() { await act(async () => renderer.unmount()); } };
}

try {
  assert.equal(preferredChatDeploymentId([deployment("dep_a", "bundle_a")], "", "variant_a"), "", "refresh cannot attach an old deployment to a newly selected variant");
  assert.equal(preferredChatDeploymentId([deployment("dep_a", "bundle_a")], ""), "dep_a", "automatic Chat selection still finds an available deployment");
  {
    const state = await render({ configuration: {}, selectedDeploymentId: "", selectedConfigurationId: "model_b", projectId: "project_with_model_choice" }, config => preview({ ...config, model_configuration_id: "model_b" }));
    assert.equal(state.renderer.root.findAll(node => node.type === "button" && node.props["aria-label"] === "Chat model settings: Second model").length, 1, "the trigger names an inherited configuration even before its model is loaded");
    await state.close();
  }
  {
    const state = await render();
    const { renderer, applied, saved } = state;
    assert.equal(renderer.root.findAll(node => node.props["aria-label"] === "Preset").length, 0, "there is one model choice, without a separate preset path");
    assert.match(text(renderer.toJSON()), /Xhigh/, "the known model default is named");
    assert.equal(range(renderer, "Thinking level").props["aria-valuetext"], "Xhigh");
    assert.deepEqual(applied, [], "displaying a known default does not create an override");
    await act(async () => range(renderer, "Thinking level").props.onChange({ target: { value: "1" } }));
    await flush();
    assert.deepEqual(applied, [], "editing remains staged until Apply");
    await state.update({ configuration: { model_configuration_id: "model_a", approval_mode: "full_access", work_mode: "plan" } });
    assert.equal(range(renderer, "Thinking level").props["aria-valuetext"], "Medium", "unrelated access and mode changes preserve staged model settings");
    await act(async () => button(renderer, "Apply").props.onClick());
    assert.equal(applied[0].per_request_overrides.reasoning_effort, "medium");
    assert.equal(applied[0].approval_mode, "full_access", "Apply uses the current independent access selection");
    assert.deepEqual(saved, [], "Apply does not save global model defaults");
    await act(async () => button(renderer, "Save to model").props.onClick());
    assert.equal(saved[0].payload.configuration_id, "model_a");
    assert.equal(saved[0].payload.per_request.temperature, 0.7, "saving one response option preserves other saved values");
    assert.equal(saved[0].payload.per_request.reasoning_effort, "medium");
    assert.equal(applied.length, 1, "Save does not also apply chat settings");
    await state.close();
  }
  {
    const state = await render();
    api.reconfigure = async () => { throw new Error("Another conversation is using this model"); };
    await act(async () => state.renderer.root.findByProps({ "aria-label": "Exact context size" }).props.onChange({ target: { value: "65536" } }));
    await flush();
    assert.equal(state.applied.length, 0);
    await act(async () => button(state.renderer, "Apply & reload").props.onClick());
    assert.match(text(state.renderer.toJSON()), /Another conversation is using this model/);
    assert.deepEqual(state.applied, [], "failed reload cannot publish staged setup as active");
    assert.equal(state.props.configuration.startup_overrides, undefined, "loaded configuration remains intact after failure");
    api.reconfigure = async (id, payload) => { state.reconfigured.push({ id, payload }); return deployment(id, "bundle_a"); };
    await act(async () => button(state.renderer, "Apply & reload").props.onClick());
    assert.equal(state.reconfigured[0].payload.startup.n_gpu_layers, 50, "context reload preserves the startup recipe");
    assert.equal(state.applied[0].startup_overrides.ctx_size, 65536);
    await state.close();
  }
  {
    const state = await render();
    await state.update({ onApply: async () => { throw new Error("Could not resolve selected setup"); } });
    const trigger = state.renderer.root.findByProps({ "aria-label": "Chat model settings: Qwen" });
    await act(async () => trigger.props.onClick());
    await act(async () => range(state.renderer, "Thinking level").props.onChange({ target: { value: "1" } }));
    await act(async () => button(state.renderer, "Apply").props.onClick());
    assert.equal(trigger.props["aria-expanded"], true, "a failed Chat setup bind leaves model settings open");
    assert.equal(range(state.renderer, "Thinking level").props["aria-valuetext"], "Medium", "a failed bind preserves the staged model edit");
    assert.match(text(state.renderer.toJSON()), /Could not resolve selected setup/);
    await state.close();
  }
  {
    const variant = { ...profile("model_a", "bundle_a"), id: "variant_a", display_name: "96k Q8 MTP variant", bags: { ...profile("model_a", "bundle_a").bags, startup: bag({ ctx_size: 98304, spec_type: "draft-mtp", cache_type_k: "q8_0", cache_type_v: "q8_0" }) } };
    const state = await render({ configuration: { model_configuration_id: variant.id, deployment_id: null }, selectedDeploymentId: "dep_b", profiles: [variant] }, config => ({
      ...preview(config),
      configuration: { ...config, model_configuration_id: variant.id, deployment_id: null },
      effective_values: { "startup.ctx_size": fact(98304, "Configuration") },
    }));
    await state.update({ onApply: value => {
      state.applied.push(value);
      state.props.configuration = value;
      state.props.selectedDeploymentId = value.deployment_id;
      state.renderer.update(React.createElement(ChatModelControls, state.props));
    } });
    const trigger = state.renderer.root.findAll(node => node.type === "button" && String(node.props["aria-label"] ?? "").startsWith("Chat model settings:"))[0];
    await act(async () => trigger.props.onClick());
    assert.equal(button(state.renderer, "Apply & load").props.disabled, false, "a selected variant without a deployment can be loaded from Chat");
    await act(async () => button(state.renderer, "Apply & load").props.onClick());
    assert.deepEqual(state.managed, [{ bundle: "bundle_a", profileId: variant.id, startup: variant.bags.startup.requested }], "loading uses the selected variant's full startup recipe");
    assert.equal(state.reconfigured.length, 0, "an older deployment for another bundle cannot override a resolved null deployment");
    assert.equal(state.applied[0].deployment_id, "dep_variant", "the loaded deployment is bound to the applied Chat setup");
    assert.equal(state.applied[0].model_configuration_id, variant.id);
    assert.equal(trigger.props["aria-expanded"], false, "successful Apply closes even after the parent updates its model configuration");
    await state.close();
  }
  {
    const variant = { ...profile("model_a", "bundle_a"), id: "variant_a", display_name: "96k Q8 MTP variant", bags: { ...profile("model_a", "bundle_a").bags, startup: bag({ ctx_size: 98304, spec_type: "draft-mtp", cache_type_k: "q8_0", cache_type_v: "q8_0" }) } };
    const state = await render({ configuration: { model_configuration_id: variant.id, deployment_id: null }, selectedDeploymentId: "dep_a", profiles: [variant] }, config => ({
      ...preview(config), configuration: { ...config, model_configuration_id: variant.id, deployment_id: null },
      effective_values: { "startup.ctx_size": fact(98304, "Configuration") },
    }));
    assert.equal(button(state.renderer, "Apply & reload").props.disabled, false, "a running same-bundle model can switch to a new variant without starting a second copy");
    await act(async () => button(state.renderer, "Apply & reload").props.onClick());
    assert.equal(state.reconfigured.length, 1);
    assert.equal(state.reconfigured[0].id, "dep_a");
    assert.equal(state.reconfigured[0].payload.model_configuration_id, variant.id);
    assert.deepEqual(state.managed, []);
    assert.equal(state.applied[0].deployment_id, "dep_a");
    await state.close();
  }
  {
    const stopped = { ...deployment("dep_a", "bundle_a"), status: "stopped", health: null, server_props: null };
    const state = await render({ deployments: [stopped] }, config => ({
      ...preview(config),
      effective_values: { "startup.ctx_size": fact(65536, "Configuration", true) },
    }));
    assert.equal(button(state.renderer, "Apply & reload").props.disabled, false, "a stopped deployment with changed startup can be reconfigured");
    await act(async () => button(state.renderer, "Apply & reload").props.onClick());
    assert.equal(state.reconfigured.length, 1);
    assert.equal(state.reconfigured[0].id, stopped.id);
    assert.equal(state.reconfigured[0].payload.model_configuration_id, "model_a", "reconfiguration refreshes the selected configuration snapshot even when its id is unchanged");
    assert.equal(state.reconfigured[0].payload.expected_configuration_revision, 1);
    assert.equal(state.applied[0].deployment_id, stopped.id);
    await state.close();
  }
  {
    const stopped = { ...deployment("dep_a", "bundle_a"), status: "stopped", health: null, server_props: null };
    const state = await render({ deployments: [stopped] });
    assert.equal(button(state.renderer, "Apply & load").props.disabled, false, "a matching stopped model offers a load action");
    await act(async () => button(state.renderer, "Apply & load").props.onClick());
    assert.deepEqual(state.started, [stopped.id]);
    assert.equal(state.reconfigured.length, 0);
    assert.equal(state.applied[0].deployment_id, stopped.id);
    await state.close();
  }
  {
    const loaded = { ...deployment("dep_a", "bundle_a"), profile_id: null, requested_startup: { ctx_size: 8192, n_gpu_layers: 30 }, settings: { startup: bag(), per_request: bag({ temperature: 0.4 }), agent: bag() } };
    const state = await render({ configuration: {}, projectId: "project_without_model_choice", deployments: [loaded] }, config => ({
      ...preview(config), configuration: { ...config, deployment_id: "dep_a", model_configuration_id: null, profile_id: null },
    }));
    assert.equal(button(state.renderer, "Save to model").props.disabled, false, "a migrated loaded model has an authoritative save target without a selected profile");
    assert.equal(text(state.renderer.root.findAll(node => node.type === "option" && node.props.value === "")[0]), "Use loaded model", "being inside a project does not falsely claim the project chose this model");
    await act(async () => button(state.renderer, "Save to model").props.onClick());
    assert.equal(state.saved[0].payload.configuration_id, "model_a");
    assert.equal(state.saved[0].payload.startup.ctx_size, 8192, "saving a loaded snapshot preserves its startup recipe");
    assert.equal(state.saved[0].payload.per_request.temperature, 0.4, "saving the loaded model cannot replace its response settings with a later saved recipe");
    assert.deepEqual(state.applied, [], "resolving a save destination does not pin or apply that configuration");
    await state.close();
  }
  {
    const state = await render({ configuration: { deployment_id: "connected" }, selectedDeploymentId: "connected" });
    assert.equal(range(state.renderer, "Context size").props.disabled, true);
    assert.match(text(state.renderer.toJSON()), /managed outside Workbench/);
    assert.equal(button(state.renderer, "Save to model").props.disabled, true);
    assert.match(button(state.renderer, "Save to model").props.title, /external server/);
    await state.close();
  }
  {
    const state = await render({ configuration: { deployment_id: "connected" }, selectedDeploymentId: "connected" }, config => ({
      ...preview(config), effective_values: { "startup.ctx_size": fact(65536, "Configuration", true) },
    }));
    assert.equal(button(state.renderer, "Apply").props.disabled, true, "Workbench cannot apply startup changes to a connected server");
    await state.close();
  }
  {
    const state = await render({ runtimeBusy: true });
    assert.equal(range(state.renderer, "Context size").props.disabled, true);
    assert.match(text(state.renderer.toJSON()), /running and queued work/);
    await state.close();
  }
  {
    const state = await render();
    workspaceApi.resolveSetup = async (_p, _a, config) => ({ ...preview(config), effective_values: { "per_request.reasoning": fact("on"), "per_request.reasoning_effort": fact(null) } });
    await state.update({ configuration: { model_configuration_id: "model_a", per_request_overrides: { temperature: 0.9 } } });
    assert.equal(range(state.renderer, "Thinking level"), undefined, "unknown model default cannot falsely select the lowest notch");
    assert.match(text(state.renderer.toJSON()), /unknown/);
    assert.deepEqual(state.applied, []);
    await state.close();
  }
  {
    const state = await render();
    const old = deferred(), next = deferred();
    workspaceApi.resolveSetup = async (_p, _a, config) => config.per_request_overrides?.reasoning_effort === "low" ? old.promise : next.promise;
    await act(async () => range(state.renderer, "Thinking level").props.onChange({ target: { value: "0" } }));
    await state.update({ configuration: { model_configuration_id: "model_b" }, selectedDeploymentId: "dep_b" });
    await act(async () => next.resolve(preview({ model_configuration_id: "model_b", per_request_overrides: { reasoning_effort: "medium" } })));
    await act(async () => old.resolve(preview({ model_configuration_id: "model_a", per_request_overrides: { reasoning_effort: "low" } })));
    assert.equal(range(state.renderer, "Thinking level").props["aria-valuetext"], "Medium", "late resolution from an old selection cannot replace current facts");
    await state.close();
  }
  {
    const state = await render();
    const first = deferred(), second = deferred();
    api.modelConfiguration = async bundle => bundle === "bundle_a" ? first.promise : second.promise;
    await state.update({ deployments: [deployment("dep_changed", "bundle_a"), deployment("dep_b", "bundle_b")], selectedDeploymentId: "dep_changed", configuration: { model_configuration_id: "model_a", deployment_id: "dep_changed" } });
    await state.update({ configuration: { model_configuration_id: "model_b", deployment_id: "dep_b" }, selectedDeploymentId: "dep_b" });
    await act(async () => second.resolve(options(["medium", "xhigh"])));
    await act(async () => first.resolve(options(["low"])));
    assert.equal(range(state.renderer, "Thinking level").props.max, 1, "late model option fetch cannot replace the current model's supported levels");
    assert.equal(range(state.renderer, "Thinking level").props["aria-valuetext"], "Xhigh");
    await state.close();
  }
  console.log("Chat model staged configuration, default provenance, reload failure and stale response checks passed.");
} finally {
  Object.assign(api, { modelConfiguration: original.modelConfiguration, reconfigure: original.reconfigure, start: original.start, startManaged: original.startManaged, saveModelConfiguration: original.saveModelConfiguration });
  workspaceApi.resolveSetup = original.resolveSetup;
  await vite.close();
}
