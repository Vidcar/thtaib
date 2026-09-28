import assert from "node:assert/strict";
import path from "node:path";
import { fileURLToPath } from "node:url";
import React from "react";
import { act, create } from "react-test-renderer";
import { createServer as createViteServer } from "vite";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;
const originalWindow = globalThis.window;
globalThis.window = Object.assign(new EventTarget(), { workbench: { backendUrl: "http://chat-model-controls.test" } });
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const vite = await createViteServer({ root, appType: "custom", server: { middlewareMode: true, hmr: false }, logLevel: "error" });
const { ChatModelControls } = await vite.ssrLoadModule("/src/renderer/ChatModelControls.tsx");
const { api } = await vite.ssrLoadModule("/src/renderer/api.ts");
const { workspaceApi } = await vite.ssrLoadModule("/src/renderer/workspaceApi.ts");
const original = { deploymentConfiguration: api.deploymentConfiguration, modelConfiguration: api.modelConfiguration, startManaged: api.startManaged, resolveSetup: workspaceApi.resolveSetup, chatReadiness: workspaceApi.chatReadiness };
const bag = (requested = {}) => ({ requested, applied: requested, overridden: [], unsupported: [], retired: [] });
const profile = (id, bundle, name) => ({ id, bundle_id: bundle, display_name: name, bags: { startup: bag({ ctx_size: 32768 }), per_request: bag({ reasoning: "on", reasoning_effort: "high", max_tokens: 5000 }), agent: bag() } });
const bundles = [
  { id: "bundle_a", display_name: "Qwen", quantization: "IQ4_XS", primary_path: "C:/models/Qwen-8B-IQ4_XS.gguf", status: "ready", disk_matches: true, default_configuration_id: "config_a" },
  { id: "bundle_b", display_name: "Gemma", status: "ready", disk_matches: true, default_configuration_id: "config_b" },
];
const profiles = [profile("config_a", "bundle_a", "Default"), profile("config_a_fast", "bundle_a", "Fast"), profile("config_b", "bundle_b", "Default")];
const deployment = (id, bundle, config, startup = { ctx_size: 32768 }) => ({ id, profile_id: config, bundle_id: bundle, display_name: "managed:" + id, scope: "managed", status: "running", health: { healthy: true }, settings: { startup: bag(startup), per_request: bag(), agent: bag() } });
const options = { context_size: { supported: true, maximum: 65536, options: [] }, per_request_defaults: {
  reasoning: { supported: true, options: ["auto", "on", "off"].map(value => ({ value, label: value })) },
  reasoning_effort: { supported: true, options: ["low", "medium", "high"].map(value => ({ value, label: value })) },
} };
function text(node) { return typeof node === "string" ? node : (node?.children ?? []).map(text).join(""); }
function aria(renderer, label, type = "button") { const found = renderer.root.findAll(node => node.type === type && node.props["aria-label"] === label)[0]; assert.ok(found, "expected " + label); return found; }
function button(renderer, label) { const found = renderer.root.findAll(node => node.type === "button" && text(node) === label)[0]; assert.ok(found, "expected button " + label); return found; }
function choices(renderer) { return renderer.root.findAll(node => node.type === "button" && node.props.className === "chat-model-choice"); }
async function flush() { await act(async () => { for (let i = 0; i < 8; i++) await Promise.resolve(); }); }
async function open(renderer, label) { await act(async () => { const trigger = aria(renderer, label); if (!trigger.props["aria-expanded"]) trigger.props.onClick(); }); await flush(); }
let renderer;
try {
  const applied = [], loaded = [], readinessCalls = [], resolutionCalls = [];
  let optionCalls = 0, previewCalls = 0, failure = "", compatibility = "ready", previewFailure = false, managedAgent = 0;
  workspaceApi.resolveSetup = async (_project, _agent, config) => {
    previewCalls++; resolutionCalls.push(config); if (previewFailure) throw new Error("Preview unavailable");
    const selected = profiles.find(item => item.id === config.model_configuration_id);
    const startup = { ...(selected?.bags.startup.requested ?? {}) };
    for (const [key, value] of Object.entries(config.startup_overrides ?? {})) { if (value === null) delete startup[key]; else startup[key] = value; }
    const identity = value => JSON.stringify(Object.entries(value).sort(([left], [right]) => left.localeCompare(right)));
    const exact = selected ? props.deployments.find(item => item.profile_id === selected.id && identity(item.settings.startup.requested) === identity(startup) && item.status === "running" && item.health?.healthy) : props.deployments.find(item => item.id === config.deployment_id);
    const fact = (value, inherited) => ({ value, known: true, source: "This chat", inherited_value: inherited, inherited_source: "Configuration: Default", default_value: inherited, default_source: "gguf_template" });
    return { configuration: { ...config, deployment_id: exact?.id ?? null }, instruction_layers: [], effective_values: { "startup.ctx_size": fact(config.startup_overrides?.ctx_size ?? 32768, 32768), "per_request.reasoning": fact(config.per_request_overrides?.reasoning ?? "on", "on"), "per_request.reasoning_effort": fact(config.per_request_overrides?.reasoning_effort ?? "high", "high") } };
  };
  workspaceApi.chatReadiness = async (conversation, candidate) => {
    readinessCalls.push({ conversation, candidate });
    if (compatibility === "unknown") throw new Error("Readiness unavailable");
    return { status: compatibility, can_send: compatibility === "ready", issues: compatibility === "incompatible" ? [{ code: "image_support", message: "Image support unavailable" }] : [], selection: null };
  };
  api.modelConfiguration = async () => { optionCalls++; return options; };
  api.deploymentConfiguration = async () => options;
  api.startManaged = async (bundle, config, startup) => {
    loaded.push({ bundle, config, startup }); if (failure) throw new Error(failure);
    return deployment("dep_" + config, bundle, config, { ctx_size: 32768, ...startup });
  };
  let props = { bundles, profiles, deployments: [deployment("dep_a", "bundle_a", "config_a")], selectedDeploymentId: "dep_a", selectedConfigurationId: "config_a", configuration: { model_configuration_id: "config_a", deployment_id: "dep_a" }, conversationId: "chat_1", onApply: next => applied.push(next), onReloaded: async () => {}, onManageAgent: () => { managedAgent++; } };
  async function update(patch) { props = { ...props, ...patch }; await act(async () => renderer.update(React.createElement(ChatModelControls, props))); await flush(); }
  await act(async () => { renderer = create(React.createElement(ChatModelControls, props)); }); await flush();
  assert.deepEqual(loaded, [], "passive restoration remains cold");
  assert.equal(readinessCalls.length, 0);
  assert.equal(optionCalls, 0); assert.equal(previewCalls, 1, "passive resolution observes exact selection without loading");
  await open(renderer, "Chat model: Qwen");
  assert.equal(choices(renderer).length, 2, "one bounded model row per bundle");
  assert.equal(optionCalls, 0, "model picker does not load tuning or every compatibility preview");
  const variants = () => renderer.root.findAll(node => node.type === "button" && node.props.className === "chat-model-choice chat-model-variant");
  assert.equal(loaded.length, 0, "showing configuration choices never loads a model");
  assert.equal(variants().length, 3, "named settings are immediately visible beneath their models");
  assert.equal(renderer.root.findAll(node => node.type === "button" && String(node.props["aria-label"]).startsWith("Configurations for ")).length, 0, "no small expand controls remain");
  assert.ok(text(choices(renderer)[0]).includes("IQ4_XS"), "quantization remains visible on the model row");
  assert.ok(variants().every(node => !text(node).includes(".gguf")), "settings do not repeat weight filenames");
  assert.match(variants()[0].props.title, /Qwen-8B-IQ4_XS\.gguf/, "full file identity remains available on hover");
  await act(async () => aria(renderer, "Search models", "input").props.onChange({ target: { value: "Qwen-8B-IQ4_XS.gguf" } }));
  assert.equal(choices(renderer).length, 1, "original filenames remain searchable");
  await act(async () => aria(renderer, "Search models", "input").props.onChange({ target: { value: "" } }));
  await act(async () => aria(renderer, "Search models", "input").props.onKeyDown({ key: "ArrowDown", preventDefault() {} }));
  assert.equal(variants()[0].props["data-highlighted"], true, "keyboard navigation reaches secondary choices directly");
  await act(async () => choices(renderer)[0].props.onClick()); await flush();
  assert.equal(readinessCalls.length, 0, "exact healthy selection does not preflight");
  assert.equal(loaded.length, 0); assert.equal(applied.length, 0);
  await open(renderer, "Chat model: Qwen");
  const variant = renderer.root.findAll(node => node.props.className === "chat-model-choice chat-model-variant" && text(node).includes("Fast"))[0];
  await act(async () => variant.props.onClick()); await flush();
  assert.deepEqual(loaded[0], { bundle: "bundle_a", config: "config_a_fast", startup: {} });
  assert.equal(applied.at(-1).model_configuration_id, "config_a_fast");
  await update({ deployments: [{ ...deployment("stopped_a", "bundle_a", "config_a"), status: "stopped", health: { healthy: false } }, deployment("dep_a", "bundle_a", "config_a")] });
  const residentBefore = loaded.length;
  await open(renderer, "Chat model: Qwen"); await act(async () => choices(renderer)[0].props.onClick()); await flush();
  assert.equal(loaded.length, residentBefore, "historical stopped deployment cannot mask canonical live selection");
  await update({ runtimeBusy: true });
  const beforeStaging = loaded.length;
  await act(async () => choices(renderer)[1].props.onClick()); await flush();
  assert.equal(loaded.length, beforeStaging, "active model selection never starts runtime loading");
  assert.equal(applied.at(-1).model_configuration_id, "config_b", "exact choice becomes draft intent");
  assert.equal(applied.at(-1).deployment_id, null, "staged choice has no invented loaded binding");
  await update({ runtimeBusy: false, configuration: { model_configuration_id: "config_a", deployment_id: "dep_a", startup_overrides: { ctx_size: 8192 } } });
  const selectedDot = renderer.root.findAll(node => node.type === "span" && node.props.className === "model-state-dot is-idle");
  assert.ok(selectedDot.length, "saved profile match cannot claim different startup settings are loaded");
  await act(async () => choices(renderer)[0].props.onClick()); await flush();
  assert.equal(loaded.length, beforeStaging + 1, "changed startup identity does not skip load");
  await update({ configuration: { model_configuration_id: "config_a", deployment_id: "dep_a", per_request_overrides: { temperature: 0.2, max_tokens: 6000, reasoning_budget_tokens: 1024 } }, runtimeBusy: true });
  await open(renderer, "Tune model");
  assert.ok(optionCalls > 0 && previewCalls > 0, "tuning fetches support and effective facts on demand");
  assert.equal(renderer.root.findAll(node => node.props["aria-label"] === "Response limit" || node.props["aria-label"] === "Thinking limit").length, 0, "Models owns token-limit editing");
  await act(async () => aria(renderer, "Thinking level", "select").props.onChange({ target: { value: "medium" } }));
  await act(async () => aria(renderer, "Chat context", "input").props.onChange({ target: { value: "8192" } }));
  const beforeTuning = loaded.length;
  await act(async () => button(renderer, "Apply").props.onClick()); await flush();
  assert.equal(loaded.length, beforeTuning, "active tuning changes never reload");
  const tuned = applied.at(-1);
  assert.equal(tuned.startup_overrides.ctx_size, 8192);
  assert.equal(tuned.per_request_overrides.reasoning_effort, "medium");
  assert.equal(tuned.per_request_overrides.max_tokens, 6000, "Chat preserves permanent output limit without editing it");
  assert.equal(tuned.per_request_overrides.reasoning_budget_tokens, 1024);
  assert.equal(tuned.per_request_overrides.temperature, 0.2);
  assert.equal(tuned.model_overrides.bundle_a.startup_overrides.ctx_size, 8192);
  await update({ configuration: tuned });
  await open(renderer, "Tune model");
  await act(async () => { aria(renderer, "Thinking level", "select").props.onChange({ target: { value: "" } }); aria(renderer, "Chat context", "input").props.onChange({ target: { value: "" } }); }); await flush();
  const resetPreview = resolutionCalls.at(-1);
  assert.equal(Object.hasOwn(resetPreview.startup_overrides, "ctx_size"), false, "cleared context is absent in preview");
  assert.equal(Object.hasOwn(resetPreview.per_request_overrides, "reasoning_effort"), false, "cleared thinking is absent in preview");
  assert.match(text(aria(renderer, "Thinking level", "select")), /High.*Configuration default/, "default option uses parent value rather than edited Medium");
  await act(async () => button(renderer, "Apply").props.onClick()); await flush();
  assert.deepEqual(applied.at(-1).startup_overrides, resetPreview.startup_overrides, "Apply uses the previewed reset candidate");
  assert.deepEqual(applied.at(-1).per_request_overrides, resetPreview.per_request_overrides);
  await update({ configuration: tuned });
  await open(renderer, "Tune model");
  const normalResolve = workspaceApi.resolveSetup, pendingChecks = [];
  workspaceApi.resolveSetup = (...args) => new Promise(resolve => pendingChecks.push(() => normalResolve(...args).then(resolve)));
  await act(async () => aria(renderer, "Chat context", "input").props.onChange({ target: { value: "9000" } }));
  assert.equal(aria(renderer, "Chat context", "input").props.disabled, false, "checking does not disable typing");
  await act(async () => aria(renderer, "Chat context", "input").props.onChange({ target: { value: "10000" } }));
  assert.equal(button(renderer, "Apply").props.disabled, true);
  await act(async () => { pendingChecks.shift()(); }); await flush();
  assert.equal(button(renderer, "Apply").props.disabled, true, "earlier preview cannot validate a newer draft");
  await act(async () => { pendingChecks.shift()(); }); await flush();
  assert.equal(button(renderer, "Apply").props.disabled, false);
  workspaceApi.resolveSetup = normalResolve;
  await update({ configuration: { ...tuned, startup_overrides: { ctx_size: 8192, threads: 4 } } });
  await update({ configuration: tuned });
  await act(async () => choices(renderer)[1].props.onClick()); await flush();
  await update({ configuration: applied.at(-1), selectedConfigurationId: "config_b", selectedDeploymentId: "" });
  await act(async () => choices(renderer)[0].props.onClick()); await flush();
  assert.equal(applied.at(-1).startup_overrides.ctx_size, 8192, "A to B to A restores chat-local context");
  assert.equal(applied.at(-1).per_request_overrides.reasoning_effort, "medium");
  await update({ conversationId: "chat_2", configuration: { model_configuration_id: "config_a", deployment_id: "dep_a" }, selectedConfigurationId: "config_a", selectedDeploymentId: "dep_a", runtimeBusy: false });
  compatibility = "unknown";
  const beforeUnknown = loaded.length;
  await act(async () => choices(renderer)[1].props.onClick()); await flush();
  assert.equal(loaded.length, beforeUnknown, "unknown compatibility does not load");
  assert.match(text(renderer.root), /Compatibility unknown/);
  compatibility = "incompatible";
  await act(async () => choices(renderer)[1].props.onClick()); await flush();
  assert.equal(loaded.length, beforeUnknown);
  assert.equal(choices(renderer)[1].props.disabled, true, "verified incompatible selection carries a truthful reason");
  compatibility = "ready"; failure = "GPU memory exhausted";
  await update({ conversationId: "chat_3" });
  await act(async () => choices(renderer)[1].props.onClick()); await flush();
  assert.equal(applied.at(-1).model_configuration_id, "config_b", "failed loading retains the attempted draft selection");
  assert.equal(applied.at(-1).deployment_id, null);
  assert.match(text(renderer.root), /GPU memory exhausted/);
  failure = "";
  await update({ fixedModel: true });
  assert.equal(choices(renderer)[1].props.disabled, true, "fixed-model agent assignment cannot be silently overridden");
  await act(async () => button(renderer, "Change in Agents").props.onClick());
  assert.equal(managedAgent, 1);
  const connected = { ...deployment("connected_1", null, null), scope: "connected", display_name: "connected:Remote" };
  await update({ fixedModel: false, bundles: [], profiles: [], deployments: [connected], selectedDeploymentId: connected.id, selectedConfigurationId: undefined, configuration: { deployment_id: connected.id } });
  await open(renderer, "Tune model");
  assert.equal(aria(renderer, "Chat context", "input").props.disabled, true, "external connection has no owned reload authority");
  assert.match(text(renderer.root), /Context is managed by this connection/);
  previewFailure = true;
  await update({ conversationId: "chat_4" }); await flush();
  const duplicates = ["publisher_a", "publisher_b"].map((publisher, index) => ({ ...bundles[0], id: "duplicate_" + index, display_name: publisher + "/qwen-8b", source: { repo_id: publisher + "/qwen-8b" }, default_configuration_id: "duplicate_config_" + index }));
  await update({ bundles: duplicates, deployments: [], profiles: duplicates.map((bundle, index) => profile("duplicate_config_" + index, bundle.id, "Default")) });
  assert.equal(new Set(choices(renderer).map(text)).size, 2, "short model names retain distinct publisher identities");
  assert.ok(choices(renderer).every(node => !text(node).includes(".gguf")), "model groups keep full filenames in their tooltip");
  console.log("Chat model picker, exact residency, safe staging and per-model tuning checks passed.");
} finally {
  if (renderer) await act(async () => renderer.unmount());
  Object.assign(api, { deploymentConfiguration: original.deploymentConfiguration, modelConfiguration: original.modelConfiguration, startManaged: original.startManaged });
  Object.assign(workspaceApi, { resolveSetup: original.resolveSetup, chatReadiness: original.chatReadiness });
  globalThis.window = originalWindow;
  await vite.close();
}
