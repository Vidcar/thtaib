import assert from "node:assert/strict";
import React from "react";
import { act, create } from "react-test-renderer";
import { createServer } from "vite";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;
const originalWindow = globalThis.window;
globalThis.window = Object.assign(new EventTarget(), { setTimeout, clearTimeout, setInterval, clearInterval, workbench: { backendUrl: "http://screen-endpoints.test" } });
const vite = await createServer({ appType: "custom", server: { middlewareMode: true, hmr: false }, logLevel: "error" });
const tick = () => new Promise(resolve => setTimeout(resolve, 0));
const text = node => typeof node === "string" ? node : (node?.children ?? []).map(text).join("");
const button = (renderer, label) => renderer.root.findAllByType("button").find(node => text(node) === label);
const ownerControl = (node, name) => { let current = node; while (current && current.type?.name !== name) current = current.parent; assert.ok(current, `expected ${name}`); return current; };
const bag = requested => ({ requested, applied: requested, unsupported: [], retired: [], overridden: [], unverified: [] });
const jsonResponse = body => ({ ok: true, status: 200, json: async () => body });
const options = { bundle_id: "model", context_size: { supported: true, maximum: 32768, flag: "--ctx-size", options: [] }, gpu_layers: { maximum: 32, options: [] }, startup_defaults: {}, per_request_defaults: { reasoning: { supported: true, options: [{ value: "on", label: "On" }, { value: "off", label: "Off" }] } }, metadata: { architecture: "qwen" } };

const calls = [];
let deployments = [];
let failManaged = false;
const profile = { id: "config", bundle_id: "model", display_name: "Default", revision: 1, bags: { startup: bag({ ctx_size: 8192 }), per_request: bag({}), agent: bag({}) } };
const bundle = { id: "model", display_name: "Example", source: { kind: "local" }, default_configuration_id: "config", disk_matches: true, files: [], companions: [], status: "ready" };
const running = { id: "running-1", bundle_id: "model", profile_id: "config", display_name: "Example", scope: "managed", status: "running", health: { healthy: true }, server_props: { n_ctx: 8192 }, applied_startup: { ctx_size: 8192 }, settings: profile.bags, updated_at: "current", endpoint: "http://127.0.0.1:8080" };
const stopped = { ...running, id: "stopped-1", status: "stopped", health: null, server_props: null, updated_at: "earlier" };
deployments = [running, stopped];

globalThis.fetch = async (url, init = {}) => {
  const path = String(url);
  const body = init.body ? JSON.parse(init.body) : null;
  const method = init.method ?? "GET";
  calls.push({ path, method, body });
  if (path.endsWith("/v1/runtime")) return jsonResponse({ status: "ready" });
  if (path.endsWith("/v1/deployments")) return jsonResponse(deployments);
  if (path.includes("/configuration-options")) return jsonResponse(options);
  if (path.endsWith("/v1/setup-resolution")) return jsonResponse({ configuration: { ...body.overrides, deployment_id: "running-1" }, effective_values: { "startup.ctx_size": { value: body.overrides?.startup_overrides?.ctx_size ?? 8192, known: true, source: "This chat", inherited_value: 8192, default_value: 8192 } }, instruction_layers: [] });
  if (path.endsWith("/v1/settings/preview")) return jsonResponse({ startup: bag(body.startup), per_request: bag(body.per_request), agent: bag(body.agent ?? {}) });
  if (path.endsWith("/v1/models/estimate")) return { ok: false, status: 503, json: async () => ({ error: "estimate unavailable" }) };
  if (path.endsWith("/configurations")) return jsonResponse(profile);
  if (path.endsWith("/v1/deployments/managed")) {
    assert.equal(method, "POST");
    if (failManaged) {
      deployments = deployments.map(item => item.id === "running-1" ? { ...item, status: "failed", health: { healthy: false }, error: "GPU memory exhausted" } : item);
      return { ok: false, status: 409, json: async () => ({ error: "GPU memory exhausted", code: "start_failed" }) };
    }
    return jsonResponse({ ...running, id: "running-1" });
  }
  if (path.endsWith("/v1/deployments/running-1/reload")) {
    assert.equal(method, "POST");
    return jsonResponse({ ...running, health: { healthy: true } });
  }
  if (path.endsWith("/v1/deployments/stopped-1/start")) {
    assert.equal(method, "POST");
    return jsonResponse({ ...stopped, status: "running", health: { healthy: true } });
  }
  throw new Error(`Unexpected screen endpoint ${method} ${path}`);
};

const managedCalls = () => calls.filter(call => call.path.endsWith("/v1/deployments/managed"));
let models;
let chat;
let failedRefresh;
let attention;
try {
  const { DeploymentsPanel } = await vite.ssrLoadModule("/src/renderer/DeploymentsPanel.tsx");
  const { ChatModelControls } = await vite.ssrLoadModule("/src/renderer/ChatModelControls.tsx");
  await act(async () => {
    models = create(React.createElement(DeploymentsPanel, { selectedBundleId: "model", initialBundles: [bundle], initialProfiles: [profile] }), { createNodeMock: element => element.type === "form" ? { reportValidity: () => true } : null });
    await tick();
  });
  assert.ok(button(models, "Load"), "a clean saved setup offers Load");
  assert.ok(button(models, "Reload saved setup"), "a managed record offers Reload in loaded-model details");
  assert.equal(button(models, "Load").props.title.includes("saved setup"), true);
  const beforeSave = managedCalls().length;
  await act(async () => { models.root.findByProps({ id: "model-settings-form" }).props.onSubmit({ preventDefault() {} }); await tick(); });
  assert.equal(managedCalls().length, beforeSave, "Save does not start a model");
  assert.ok(calls.some(call => call.method === "POST" && call.path.endsWith("/v1/bundles/model/configurations")), "Save posts the bundle configuration");

  await act(async () => { button(models, "Load").props.onClick(); await tick(); });
  const loaded = managedCalls().at(-1);
  assert.equal(loaded.method, "POST");
  assert.equal(loaded.body.profile_id, "config");
  assert.deepEqual(loaded.body.startup, {});
  assert.equal(loaded.body.auto_start, true);
  assert.equal(calls.some(call => call.path.endsWith("/reload")), false, "Load does not reload the running record");

  await act(async () => ownerControl(models.root.findAllByType("input").find(node => node.props.id === "model-ctx-size"), "ContextSlider").props.onChange(16384));
  assert.ok(button(models, "Load saved"));
  await act(async () => { button(models, "Load saved").props.onClick(); await tick(); });
  const savedLoad = managedCalls().at(-1);
  assert.deepEqual(savedLoad.body.startup, {}, "Load saved ignores unsaved edits");
  assert.equal(savedLoad.body.profile_id, "config");
  assert.match(text(models.root), /Saved setup loaded\./, "a Load saved success stays visible while unsaved edits remain");

  await act(async () => { button(models, "Reload saved setup").props.onClick(); await tick(); });
  const reload = calls.find(call => call.path.endsWith("/v1/deployments/running-1/reload"));
  assert.equal(reload?.method, "POST", "Reload posts the same deployment record");
  assert.equal(calls.filter(call => call.path.endsWith("/reload")).length, 1);

  assert.ok(models.root.findAllByType("summary").some(node => text(node).startsWith("Loaded model")), "runtime actions remain in the loaded-model disclosure");
  await act(async () => { button(models, "Load snapshot").props.onClick(); await tick(); });
  const snapshot = calls.find(call => call.path.endsWith("/v1/deployments/stopped-1/start"));
  assert.equal(snapshot?.method, "POST", "Load snapshot starts the stopped record");

  failManaged = true;
  await act(async () => ownerControl(models.root.findAllByType("input").find(node => node.props.id === "model-ctx-size"), "ContextSlider").props.onChange(12288));
  await act(async () => { button(models, "Load saved").props.onClick(); await tick(); });
  assert.match(text(models.root), /GPU memory exhausted/);
  const badges = models.root.findAll(node => node.type === "span" && String(node.props.className).startsWith("badge "));
  assert.equal(badges.some(node => text(node) === "Ready"), false, "a failed load is not labelled Ready");

  const chatProfile = { ...profile, bags: { startup: bag({ ctx_size: 8192 }), per_request: bag({ reasoning: "on" }), agent: bag({}) } };
  const chatDeployment = { ...running, settings: chatProfile.bags };
  await act(async () => {
    chat = create(React.createElement(ChatModelControls, {
      bundles: [bundle], deployments: [chatDeployment], profiles: [chatProfile], selectedDeploymentId: "running-1", selectedConfigurationId: "config",
      configuration: { model_configuration_id: "config", deployment_id: "running-1", startup_overrides: { ctx_size: 8192 } },
      conversationId: "chat-1", onApply: async () => {}, onReloaded: async () => {}, onManageAgent: () => {},
    }));
    await tick();
  });
  const tune = chat.root.findAll(node => node.type === "button" && node.props["aria-label"] === "Tune model")[0];
  await act(async () => { if (!tune.props["aria-expanded"]) tune.props.onClick(); await tick(); });
  await act(async () => ownerControl(chat.root.findAllByType("input").find(node => node.props["aria-label"] === "Chat context"), "ContextSlider").props.onChange(12288));
  for (let attempt = 0; attempt < 8 && button(chat, "Apply this chat's settings")?.props.disabled; attempt += 1) await act(async () => { await tick(); });
  assert.equal(button(chat, "Reload"), undefined, "chat tuning does not say Reload");
  const helpText = node => node == null ? "" : Array.isArray(node) ? node.map(helpText).join("") : typeof node === "object" ? helpText(node.props?.children) : String(node);
  const contextHelp = chat.root.findAll(node => node.type?.name === "SettingRow" && node.props.label === "Context")[0];
  assert.match(helpText(contextHelp.props.help), /Apply this chat's settings changes loading settings/);
  const beforeChat = managedCalls().length;
  await act(async () => { button(chat, "Apply this chat's settings").props.onClick(); await tick(); });
  const applied = managedCalls().at(-1);
  assert.equal(managedCalls().length, beforeChat + 1);
  assert.equal(applied.method, "POST");
  assert.equal(applied.body.profile_id, "config");
  assert.equal(applied.body.auto_start, true);
  assert.equal(applied.body.startup.ctx_size, 12288, "chat apply posts that chat's startup overrides");
  assert.equal(calls.filter(call => call.path.includes("/reload")).length, 1, "chat apply does not call reload");

  failManaged = false;
  await act(async () => {
    failedRefresh = create(React.createElement(ChatModelControls, {
      bundles: [bundle], deployments: [chatDeployment], profiles: [chatProfile], selectedDeploymentId: "running-1", selectedConfigurationId: "config",
      configuration: { model_configuration_id: "config", deployment_id: "running-1", startup_overrides: { ctx_size: 8192 } },
      conversationId: "chat-2", onApply: async () => {}, onReloaded: async () => { throw new Error("Model status could not refresh"); }, onManageAgent: () => {},
    }));
    await tick();
  });
  const failedTune = failedRefresh.root.findAll(node => node.type === "button" && node.props["aria-label"] === "Tune model")[0];
  await act(async () => { if (!failedTune.props["aria-expanded"]) failedTune.props.onClick(); await tick(); });
  await act(async () => ownerControl(failedRefresh.root.findAllByType("input").find(node => node.props["aria-label"] === "Chat context"), "ContextSlider").props.onChange(16384));
  for (let attempt = 0; attempt < 8 && button(failedRefresh, "Apply this chat's settings")?.props.disabled; attempt += 1) await act(async () => { await tick(); });
  await act(async () => { button(failedRefresh, "Apply this chat's settings").props.onClick(); await tick(); });
  assert.match(text(failedRefresh.root), /Model status could not refresh/, "a failed model refresh stays visible after chat settings are applied");
  let attentionFailed = false;
  globalThis.fetch = async (url) => {
    if (String(url).endsWith("/v1/desktop/attention")) {
      if (attentionFailed) throw new Error("Attention list unavailable");
      return jsonResponse([]);
    }
    throw new Error(`Unexpected attention endpoint ${url}`);
  };
  const { AttentionButton } = await vite.ssrLoadModule("/src/renderer/AttentionPanel.tsx");
  await act(async () => { attention = create(React.createElement(AttentionButton, {})); await tick(); });
  assert.equal(attention.root.findByType("button").props["aria-label"], "Attention, 0 items");
  attentionFailed = true;
  await act(async () => { attention.root.findByType("button").props.onClick?.(); globalThis.window.dispatchEvent(new Event("workbench-attention")); await tick(); });
  const attentionButton = attention.root.findByType("button");
  assert.match(attentionButton.props["aria-label"], /Attention could not load/);
  assert.match(attentionButton.props["aria-label"], /Attention list unavailable/);
  assert.equal(text(attentionButton).includes("!"), true, "a failed attention load is not shown as zero items");
  const heldAttention = [];
  globalThis.fetch = async url => {
    assert.ok(String(url).endsWith("/v1/desktop/attention"));
    return new Promise((resolve, reject) => heldAttention.push({ resolve: value => resolve(jsonResponse(value)), reject }));
  };
  await act(async () => { globalThis.window.dispatchEvent(new Event("workbench-attention")); globalThis.window.dispatchEvent(new Event("workbench-attention")); await tick(); });
  assert.equal(heldAttention.length, 2, "two independent attention refreshes have reached the API");
  await act(async () => { heldAttention[1].resolve([{ identity: "latest-approval" }]); await tick(); });
  assert.equal(attention.root.findByType("button").props["aria-label"], "Attention, 1 item");
  await act(async () => { heldAttention[0].resolve([]); await tick(); });
  assert.equal(attention.root.findByType("button").props["aria-label"], "Attention, 1 item", "an old empty response cannot hide current attention");
  await act(async () => { globalThis.window.dispatchEvent(new Event("workbench-attention")); globalThis.window.dispatchEvent(new Event("workbench-attention")); await tick(); });
  await act(async () => { heldAttention[3].resolve([]); await tick(); });
  await act(async () => { heldAttention[2].reject(new Error("Obsolete attention failure")); await tick(); });
  assert.equal(attention.root.findByType("button").props["aria-label"], "Attention, 0 items", "an old failure cannot replace a newer successful refresh");
  console.log("Screen controls call the endpoints their labels name.");
} finally {
  if (models) await act(async () => models.unmount());
  if (chat) await act(async () => chat.unmount());
  if (failedRefresh) await act(async () => failedRefresh.unmount());
  if (attention) await act(async () => attention.unmount());
  globalThis.window = originalWindow;
  await vite.close();
}
