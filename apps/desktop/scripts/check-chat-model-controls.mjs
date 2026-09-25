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
const { api } = await vite.ssrLoadModule("/src/renderer/api.ts");
const { workspaceApi } = await vite.ssrLoadModule("/src/renderer/workspaceApi.ts");
const original = { modelConfiguration: api.modelConfiguration, startManaged: api.startManaged, resolveSetup: workspaceApi.resolveSetup, chatReadiness: workspaceApi.chatReadiness };
const bag = (requested = {}) => ({ requested, applied: {}, overridden: [], unsupported: [], retired: [] });
const profile = (id, bundle, name) => ({ id, bundle_id: bundle, display_name: name, bags: { startup: bag({ ctx_size: 32768 }), per_request: bag({ temperature: 0.7 }), agent: bag() } });
const bundles = [
  { id: "bundle_a", display_name: "Qwen", status: "ready", disk_matches: true, default_configuration_id: "config_a" },
  { id: "bundle_b", display_name: "Gemma", status: "ready", disk_matches: true, default_configuration_id: "config_b" },
];
const profiles = [profile("config_a", "bundle_a", "Default"), profile("config_a_fast", "bundle_a", "Fast"), profile("config_b", "bundle_b", "Default")];
const deployment = (id, bundle, config) => ({ id, profile_id: config, bundle_id: bundle, display_name: `managed:${id}`, scope: "managed", status: "running", health: { healthy: true }, settings: { startup: bag(), per_request: bag(), agent: bag() } });
const option = value => ({ value, label: value[0].toUpperCase() + value.slice(1) });
const options = { per_request_defaults: { reasoning: { supported: true, options: ["auto", "on", "off"].map(option) }, reasoning_effort: { supported: true, options: ["low", "medium", "high"].map(option) } } };
const fact = value => ({ value, source: "Model default", known: value != null });
function text(node) { return typeof node === "string" ? node : (node?.children ?? []).map(text).join(""); }
function button(renderer, label) { const found = renderer.root.findAll(node => node.type === "button" && text(node).includes(label))[0]; assert.ok(found, `button ${label}`); return found; }
async function flush() { await act(async () => { for (let i = 0; i < 6; i++) await Promise.resolve(); }); }
async function openPicker(renderer) {
  const trigger = renderer.root.findAll(node => node.type === "button" && node.props.className === "menu-popover-trigger")[0];
  assert.ok(trigger, "model picker trigger exists");
  if (!trigger.props["aria-expanded"]) await act(async () => trigger.props.onClick());
}

try {
  const applied = [], loaded = [], readinessCalls = [];
  let optionCalls = 0, previewCalls = 0;
  workspaceApi.resolveSetup = async (_project, _agent, config) => { previewCalls++; return { configuration: config, instruction_layers: [], effective_values: { "per_request.reasoning": fact(config.per_request_overrides?.reasoning ?? "on"), "per_request.reasoning_effort": fact(config.per_request_overrides?.reasoning_effort ?? "high") } }; };
  workspaceApi.chatReadiness = async (conversation, candidate) => { readinessCalls.push({ conversation, candidate }); return { status: "needs_action", can_send: false, issues: [{ code: "model_load_required", message: "Load model" }], selection: null }; };
  api.modelConfiguration = async () => { optionCalls++; return options; };
  api.startManaged = async (bundle, config, startup) => { loaded.push({ bundle, config, startup }); return deployment(`dep_${config}`, bundle, config); };
  const props = { bundles, profiles, deployments: [deployment("dep_a", "bundle_a", "config_a")], selectedDeploymentId: "dep_a", configuration: { model_configuration_id: "config_a", deployment_id: "dep_a" }, conversationId: "chat_1", onApply: next => applied.push(next), onReloaded: async () => {} };
  let renderer;
  await act(async () => { renderer = create(React.createElement(ChatModelControls, props)); });
  await flush();
  assert.deepEqual(loaded, [], "rendering the model picker never loads a model");
  assert.equal(readinessCalls.length, 0, "closed picker does not preflight every saved model");
  assert.equal(optionCalls, 0, "closed picker defers model options");
  assert.equal(previewCalls, 0, "closed picker defers setup preview");
  await openPicker(renderer);
  await flush();
  assert.equal(readinessCalls.length, 0, "opening the picker does not preflight every saved model");
  assert.ok(optionCalls > 0 && previewCalls > 0, "picker settings load on opening");
  const rows = renderer.root.findAll(node => node.type === "button" && node.props.className === "chat-model-choice");
  assert.equal(rows.length, 2, "one row is shown per installed model, not per configuration");
  await act(async () => rows[0].props.onClick());
  await flush();
  assert.equal(readinessCalls.length, 0, "clicking the current healthy model skips readiness");
  assert.deepEqual(loaded, [], "clicking the current healthy model skips reload");
  assert.equal(applied.length, 0, "clicking the current healthy model does not reapply setup");
  await openPicker(renderer);
  assert.equal(renderer.root.findAll(node => node.props["aria-label"] === "Exact context size").length, 0, "startup controls are absent from Chat");
  assert.equal(renderer.root.findAll(node => node.props["aria-label"] === "Temperature").length, 0, "sampling controls are absent from Chat");
  const variant = renderer.root.findAll(node => node.type === "select" && node.props["aria-label"] === "Model configuration")[0];
  assert.ok(variant, "configuration choice is secondary to the model rows");
  await act(async () => variant.props.onChange({ target: { value: "config_a_fast" } }));
  await flush();
  assert.deepEqual(loaded, [{ bundle: "bundle_a", config: "config_a_fast", startup: {} }], "explicit variant selection loads its exact saved configuration without launch overrides");
  assert.equal(applied[0].model_configuration_id, "config_a_fast");
  assert.equal(applied[0].deployment_id, "dep_config_a_fast");
  await openPicker(renderer);
  await act(async () => rows[1].props.onClick());
  await flush();
  assert.deepEqual(loaded[1], { bundle: "bundle_b", config: "config_b", startup: {} }, "switching models explicitly loads the new choice");

  const named = { ...props, configuration: { model_configuration_id: "config_a_fast", deployment_id: "dep_config_a_fast" }, selectedDeploymentId: "dep_config_a_fast", deployments: [...props.deployments, deployment("dep_config_a_fast", "bundle_a", "config_a_fast")] };
  await act(async () => renderer.update(React.createElement(ChatModelControls, named)));
  await openPicker(renderer);
  const loadsBeforeNamedClick = loaded.length, readinessBeforeNamedClick = readinessCalls.length, appliesBeforeNamedClick = applied.length;
  await act(async () => rows[0].props.onClick());
  await flush();
  assert.equal(loaded.length, loadsBeforeNamedClick, "model row prefers the current named configuration over the bundle default");
  assert.equal(readinessCalls.length, readinessBeforeNamedClick, "current named configuration skips readiness");
  assert.equal(applied.length, appliesBeforeNamedClick, "current named configuration remains selected");

  const updated = { ...props, configuration: { model_configuration_id: "config_b", deployment_id: "dep_config_b" }, selectedDeploymentId: "dep_config_b", deployments: [...props.deployments, deployment("dep_config_b", "bundle_b", "config_b")] };
  await act(async () => renderer.update(React.createElement(ChatModelControls, updated)));
  await flush();
  await openPicker(renderer);
  const thinking = renderer.root.findAll(node => node.type === "input" && node.props["aria-label"] === "Thinking level")[0];
  assert.ok(thinking, "supported thinking remains in Chat");
  await act(async () => thinking.props.onChange({ target: { value: "1" } }));
  await flush();
  assert.equal(applied.length, 2, "thinking edit remains staged until applied");
  await act(async () => button(renderer, "Apply thinking").props.onClick());
  assert.equal(applied.at(-1).per_request_overrides.reasoning_effort, "medium");

  api.startManaged = async () => { throw new Error("Cannot load this model"); };
  await openPicker(renderer);
  await act(async () => rows[0].props.onClick());
  await flush();
  assert.match(text(renderer.toJSON()), /Cannot load this model/, "failed load is shown and does not bind the selection");
  assert.equal(applied.at(-1).model_configuration_id, "config_b");
  let releaseLoad;
  api.startManaged = (bundle, config) => new Promise(resolve => { releaseLoad = () => resolve(deployment(`dep_${config}`, bundle, config)); });
  const currentRows = () => renderer.root.findAll(node => node.type === "button" && node.props.className === "chat-model-choice");
  const appliedBeforeNavigation = applied.length;
  await openPicker(renderer);
  await act(async () => currentRows()[0].props.onClick());
  await flush();
  assert.ok(releaseLoad, "the selected model begins loading");
  await act(async () => renderer.update(React.createElement(ChatModelControls, { ...updated, conversationId: "chat_2", agentSetupVersionId: "agent_2" })));
  await act(async () => { releaseLoad(); await flush(); });
  assert.equal(applied.length, appliedBeforeNavigation, "an old model load cannot bind after Chat or agent selection changes");

  releaseLoad = undefined;
  const currentConfiguration = { ...updated.configuration, approval_mode: "ask", helper_agent_ids: [] };
  const currentProps = { ...updated, conversationId: "chat_2", agentSetupVersionId: "agent_2", configuration: currentConfiguration };
  await act(async () => renderer.update(React.createElement(ChatModelControls, currentProps)));
  await openPicker(renderer);
  await act(async () => currentRows()[0].props.onClick());
  await flush();
  assert.ok(releaseLoad, "a new model load remains available after navigation");
  await act(async () => renderer.update(React.createElement(ChatModelControls, { ...currentProps, configuration: { ...currentConfiguration, approval_mode: "full_access", helper_agent_ids: ["helper_1"] } })));
  await act(async () => { releaseLoad(); await flush(); });
  assert.equal(applied.at(-1).approval_mode, "full_access", "a pending model load keeps the newest Chat access");
  assert.deepEqual(applied.at(-1).helper_agent_ids, ["helper_1"], "a pending model load keeps the newest helper choice");

  await act(async () => renderer.update(React.createElement(ChatModelControls, { ...currentProps, conversationId: "chat_3" })));
  await flush();
  assert.equal(currentRows()[0].props.disabled, false, "alternatives remain selectable until their compatibility is checked");
  const loadsBeforeIncompatible = loaded.length;
  workspaceApi.chatReadiness = async () => { throw new Error("Preview unavailable"); };
  await act(async () => currentRows()[0].props.onClick());
  await flush();
  assert.equal(loaded.length, loadsBeforeIncompatible, "a failed preview is not treated as compatible");
  assert.match(text(renderer.toJSON()), /Compatibility unknown.*Preview unavailable/, "failed preview reports uncertainty and allows retry");
  assert.equal(currentRows()[0].props.disabled, false, "a failed preview does not permanently disable the choice");
  workspaceApi.chatReadiness = async (_chat, candidate) => candidate.model_configuration_id === "config_a" ? { status: "incompatible", can_send: false, issues: [{ code: "context_unsupported", message: "This chat needs image support" }], selection: null } : { status: "ready", can_send: true, issues: [], selection: null };
  await act(async () => currentRows()[0].props.onClick());
  await flush();
  assert.equal(loaded.length, loadsBeforeIncompatible, "known incompatible model is not loaded");
  assert.equal(currentRows()[0].props.disabled, true, "checked incompatible model is disabled");
  assert.match(currentRows()[0].props.title, /image support/, "incompatibility reason remains on the disabled row");
  const variantProps = { ...currentProps, conversationId: "chat_3", configuration: { model_configuration_id: "config_a_fast", deployment_id: "dep_config_a_fast" }, selectedDeploymentId: "dep_config_a_fast", deployments: [props.deployments[0], deployment("dep_config_a_fast", "bundle_a", "config_a_fast")] };
  await act(async () => renderer.update(React.createElement(ChatModelControls, variantProps)));
  const variantChoice = renderer.root.findAll(node => node.type === "select" && node.props["aria-label"] === "Model configuration")[0];
  await act(async () => variantChoice.props.onChange({ target: { value: "config_a" } }));
  await flush();
  const blockedVariant = renderer.root.findAll(node => node.type === "option" && node.props.value === "config_a")[0];
  assert.equal(blockedVariant.props.disabled, true, "checked incompatible named configuration is disabled");
  assert.match(blockedVariant.props.title, /image support/, "named configuration retains its incompatibility reason");
  await act(async () => renderer.update(React.createElement(ChatModelControls, { ...currentProps, conversationId: "chat_3", configuration: { ...currentConfiguration, approval_mode: "full_access" } })));
  assert.equal(currentRows()[0].props.disabled, false, "changing the setup clears an old incompatibility result");
  workspaceApi.chatReadiness = async () => ({ status: "needs_action", can_send: false, issues: [{ code: "chat_turn_active", message: "Wait for the current turn" }], selection: null });
  api.startManaged = async (bundle, config, startup) => { loaded.push({ bundle, config, startup }); return deployment(`dep_${config}`, bundle, config); };
  await act(async () => currentRows()[0].props.onClick());
  await flush();
  assert.equal(loaded.length, loadsBeforeIncompatible + 1, "a different model enters the guarded load path during a live turn");
  assert.equal(applied.at(-1).model_configuration_id, "config_a", "a selected model is retained for the next turn");
  const failedSelection = { ...updated, conversationId: null, selectedDeploymentId: "dep_failed", configuration: { model_configuration_id: "config_a", deployment_id: "dep_failed" }, deployments: [{ ...deployment("dep_failed", "bundle_a", "config_a"), status: "failed", health: { healthy: false } }] };
  await act(async () => renderer.update(React.createElement(ChatModelControls, failedSelection)));
  assert.match(text(renderer.root.findByProps({ className: "chat-model-status" })), /Needs attention/, "failed selection is not labelled load-on-send");
  await act(async () => renderer.update(React.createElement(ChatModelControls, { ...failedSelection, deployments: [{ ...failedSelection.deployments[0], status: "unhealthy" }] })));
  assert.match(text(renderer.root.findByProps({ className: "chat-model-status" })), /Unhealthy/, "unhealthy selection remains visible");
  api.startManaged = async (bundle, config, startup) => { loaded.push({ bundle, config, startup }); return deployment(`dep_${config}`, bundle, config); };
  await openPicker(renderer);
  const loadsBeforeRecovery = loaded.length;
  await act(async () => currentRows()[0].props.onClick());
  await flush();
  assert.equal(loaded.length, loadsBeforeRecovery + 1, "clicking the same unhealthy configuration follows the load path");
  const namedUnloaded = { ...props, deployments: [], selectedDeploymentId: "", configuration: { model_configuration_id: "config_a_fast", deployment_id: null }, conversationId: null };
  await act(async () => renderer.update(React.createElement(ChatModelControls, namedUnloaded)));
  await openPicker(renderer);
  await act(async () => currentRows()[0].props.onClick());
  await flush();
  assert.equal(loaded.at(-1).config, "config_a_fast", "an unloaded named selection keeps its exact configuration when loaded");
  await act(async () => renderer.unmount());
  console.log("Chat model selection, deferred checks, explicit loads, compatibility, thinking, and recovery passed.");
} finally {
  Object.assign(api, { modelConfiguration: original.modelConfiguration, startManaged: original.startManaged });
  workspaceApi.resolveSetup = original.resolveSetup;
  workspaceApi.chatReadiness = original.chatReadiness;
  await vite.close();
}
