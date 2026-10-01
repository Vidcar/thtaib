import assert from "node:assert/strict";
import path from "node:path";
import { fileURLToPath } from "node:url";
import React from "react";
import { act, create } from "react-test-renderer";
import { createServer as createViteServer } from "vite";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;
const originalWindow = globalThis.window;
const memoryStorage = () => { const values = new Map(); return { getItem: key => values.has(key) ? values.get(key) : null, setItem: (key, value) => { values.set(String(key), String(value)); }, removeItem: key => { values.delete(key); }, clear() { values.clear(); } }; };
const storage = memoryStorage();
globalThis.sessionStorage = storage;
globalThis.localStorage = storage;
globalThis.window = Object.assign(new EventTarget(), { setTimeout, clearTimeout, sessionStorage: storage, localStorage: storage, matchMedia: () => ({ matches: false, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {} }), workbench: { backendUrl: "http://chat-model-controls.test" } });
const jsonResponse = body => ({ ok: true, status: 200, json: async () => body });
globalThis.fetch = async (url) => {
  const path = String(url);
  if (path.endsWith("/v1/models/estimate")) return jsonResponse({ gpu_bytes: 5368709120, ram_bytes: 0, kv_bytes: 0 });
  if (path.endsWith("/v1/deployments")) return jsonResponse([]);
  if (path.endsWith("/v1/profiles")) return jsonResponse([]);
  if (path.endsWith("/v1/agent-tools")) return jsonResponse({ enabled: [], tools: [], groups: [] });
  if (path.endsWith("/v1/settings/presentation")) return jsonResponse({ theme: "system", detailed_streams: false, attention_notifications: true, success_notifications: false });
  if (path.endsWith("/v1/settings/grants")) return jsonResponse([]);
  if (path.endsWith("/v1/projects")) return jsonResponse([{ id: "project-1", name: "Notes", path: "D:/Notes", missing: false }]);
  throw new Error("Unexpected fetch " + path);
};
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const vite = await createViteServer({ root, appType: "custom", server: { middlewareMode: true, hmr: false }, logLevel: "error" });
const { ChatModelControls } = await vite.ssrLoadModule("/src/renderer/ChatModelControls.tsx");
const { api } = await vite.ssrLoadModule("/src/renderer/api.ts");
const { workspaceApi } = await vite.ssrLoadModule("/src/renderer/workspaceApi.ts");
const original = { deploymentConfiguration: api.deploymentConfiguration, modelConfiguration: api.modelConfiguration, applyChatStartupOverrides: api.applyChatStartupOverrides, resolveSetup: workspaceApi.resolveSetup, chatReadiness: workspaceApi.chatReadiness };
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
function thinkingChoice(renderer, value) { const found = renderer.root.findAll(node => node.type === "input" && node.props.type === "radio" && node.props.value === value)[0]; assert.ok(found, "expected thinking choice " + value); return found; }
function choices(renderer) { return renderer.root.findAll(node => node.type === "button" && node.props.className === "chat-model-choice"); }
function ownerControl(node, name) { while (node && node.type?.name !== name) node = node.parent; assert.ok(node, "expected " + name); return node; }
function changeContext(renderer, value) { ownerControl(aria(renderer, "Chat context", "input"), "ContextSlider").props.onChange(value); }
function resetSetting(renderer, label) { const row = renderer.root.findAll(node => node.type?.name === "SettingRow" && node.props.label === label)[0]; assert.equal(typeof row?.props.onReset, "function"); row.props.onReset(); }
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
  const optionSelections = [];
  api.modelConfiguration = async (_bundle, _deployment, _refresh, selection) => { optionCalls++; optionSelections.push(selection); return options; };
  api.deploymentConfiguration = async () => options;
  api.applyChatStartupOverrides = async (bundle, config, startup) => {
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
  assert.equal(optionCalls, 1, "the open menu asks only for the selected model's thinking levels");
  assert.equal(optionSelections[0].configuration_id, "config_a");
  assert.equal(previewCalls, 2, "opening the menu resolves that model's effective settings");
  assert.equal(renderer.root.findAll(node => node.props.name === "tune" || node.props["aria-label"] === "Tune model").length, 0, "the model menu has no tune icon");
  assert.equal(renderer.root.findAll(node => node.type === "button" && /Apply|Stage/.test(text(node))).length, 0, "the model menu has no Apply or Stage");
  assert.doesNotMatch(text(renderer.root), /This chat|This task|Apply this chat/);
  const variants = () => renderer.root.findAll(node => node.type === "button" && node.props.className === "chat-model-choice chat-model-variant");
  assert.equal(loaded.length, 0, "showing configuration choices never loads a model");
  assert.equal(variants().length, 2, "configuration choices are visible only when a model has multiple configurations");
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
  await open(renderer, "Chat model: Qwen");
  assert.ok(optionCalls > 0 && previewCalls > 0, "the menu fetches support and effective facts for the selected model");
  assert.equal(renderer.root.findAll(node => node.props["aria-label"] === "Response limit" || node.props["aria-label"] === "Thinking limit").length, 0, "Models owns token-limit editing");
  await act(async () => thinkingChoice(renderer, "medium").props.onChange());
  assert.equal(applied.at(-1).per_request_overrides.reasoning_effort, "medium", "Thinking applies immediately to the next message without a reload action");
  assert.equal(applied.at(-1).per_request_overrides.temperature, 0.2, "Thinking preserves explicit sampling");
  assert.equal(applied.at(-1).per_request_overrides.max_tokens, 6000);
  assert.equal(loaded.length, beforeStaging + 1, "Thinking does not reload the model");
  const beforeContext = loaded.length;
  await act(async () => changeContext(renderer, options.context_size.maximum)); await flush();
  assert.equal(loaded.length, beforeContext, "active work does not reload for a context choice");
  assert.equal(applied.at(-1).startup_overrides.ctx_size, options.context_size.maximum, "the context choice is remembered for the next message");
  assert.equal(resolutionCalls.at(-1).startup_overrides.ctx_size, options.context_size.maximum, "the single slider reaches the known model maximum");
  assert.equal(optionSelections.at(-1).configuration_id, "config_a");
  assert.equal(optionSelections.at(-1).startup.ctx_size, options.context_size.maximum, "template controls follow the chosen context");
  assert.equal(aria(renderer, "Chat context", "input").props["data-token-value"], options.context_size.maximum, "the readout shows the supported maximum");
  assert.match(aria(renderer, "Chat context", "input").props.title, /waits for the next message/);
  assert.match(text(renderer.root), /5\.00 GB/, "the context choice shows a short memory figure");
  await act(async () => changeContext(renderer, 8192)); await flush();
  assert.equal(loaded.length, beforeContext, "active tuning changes never reload");
  const tuned = applied.at(-1);
  assert.equal(tuned.startup_overrides.ctx_size, 8192);
  assert.equal(tuned.per_request_overrides.reasoning_effort, "medium");
  assert.equal(tuned.per_request_overrides.max_tokens, 6000, "Chat preserves permanent output limit without editing it");
  assert.equal(tuned.per_request_overrides.reasoning_budget_tokens, 1024);
  assert.equal(tuned.per_request_overrides.temperature, 0.2);
  assert.equal(tuned.model_overrides.bundle_a.startup_overrides.ctx_size, 8192);
  await update({ configuration: tuned });
  await open(renderer, "Chat model: Qwen");
  await act(async () => { resetSetting(renderer, "Thinking"); resetSetting(renderer, "Context"); }); await flush();
  const resetApplied = applied.at(-1);
  assert.equal(Object.hasOwn(resetApplied.startup_overrides ?? {}, "ctx_size"), false, "cleared context is absent");
  assert.equal(Object.hasOwn(resetApplied.per_request_overrides, "reasoning_effort"), false, "cleared thinking is absent");
  await update({ configuration: resetApplied });
  assert.equal(thinkingChoice(renderer, "high").props.checked, true, "reset selects the actual parent value rather than a Default position");
  await update({ configuration: tuned, runtimeBusy: false });
  const queuedLoad = Promise.withResolvers();
  const loadBeforeQueue = api.applyChatStartupOverrides;
  let queuedLoads = 0;
  api.applyChatStartupOverrides = async (...args) => {
    queuedLoads += 1;
    if (queuedLoads === 1) await queuedLoad.promise;
    return loadBeforeQueue(...args);
  };
  await act(async () => changeContext(renderer, 9216));
  assert.equal(aria(renderer, "Chat context", "input").props.disabled, false, "a context reload does not disable the slider");
  await act(async () => changeContext(renderer, 10240));
  await act(async () => queuedLoad.resolve()); await flush();
  assert.equal(applied.at(-1).startup_overrides.ctx_size, 10240, "a newer context choice replaces an in-flight reload");
  api.applyChatStartupOverrides = loadBeforeQueue;
  await update({ configuration: { ...tuned, startup_overrides: { ctx_size: 8192, threads: 4 } } });
  await update({ configuration: tuned });
  await act(async () => choices(renderer)[1].props.onClick()); await flush();
  await update({ configuration: applied.at(-1), selectedConfigurationId: "config_b", selectedDeploymentId: "" });
  await act(async () => choices(renderer)[0].props.onClick()); await flush();
  assert.equal(applied.at(-1).startup_overrides.ctx_size, 8192, "A to B to A restores chat-local context");
  assert.equal(applied.at(-1).per_request_overrides.reasoning_effort, "medium");
  await update({ runtimeBusy: false, conversationId: "chat_reload", selectionGeneration: 1, selectedConfigurationId: "config_a", selectedDeploymentId: "dep_a", configuration: { model_configuration_id: "config_a", deployment_id: "dep_a", startup_overrides: { ctx_size: 8192 }, per_request_overrides: { temperature: 0.2, reasoning_effort: "medium" } } });
  await open(renderer, "Chat model: Qwen");
  const idleContext = aria(renderer, "Chat context", "input");
  const idleHelp = renderer.root.findAll(node => node.type?.name === "SettingRow" && node.props.label === "Context")[0];
  assert.match(idleContext.props.title, /A context change reloads the model/);
  assert.match(String(idleHelp.props.help), /A context change reloads the model/);
  assert.doesNotMatch(text(renderer.root), /A context change reloads the model/, "the reload explanation stays on hover or focus");
  const heldContext = Promise.withResolvers();
  const loadBeforeThinking = api.applyChatStartupOverrides;
  api.applyChatStartupOverrides = async (...args) => { await heldContext.promise; return loadBeforeThinking(...args); };
  await act(async () => changeContext(renderer, 12288));
  await act(async () => thinkingChoice(renderer, "off").props.onChange()); await flush();
  assert.equal(applied.at(-1).startup_overrides.ctx_size, 8192, "Thinking uses the accepted context, not the slider draft");
  assert.equal(applied.at(-1).per_request_overrides.temperature, 0.2);
  assert.equal(applied.at(-1).per_request_overrides.reasoning, "off");
  assert.equal(aria(renderer, "Chat context", "input").props["data-token-value"], 12288, "Thinking updates retain the pending context input");
  await act(async () => heldContext.resolve()); await flush();
  assert.equal(applied.at(-1).startup_overrides.ctx_size, 12288, "the finished context reload keeps the newer Thinking choice");
  assert.equal(applied.at(-1).per_request_overrides.reasoning, "off");
  api.applyChatStartupOverrides = loadBeforeThinking;
  failure = "GPU memory exhausted while reloading";
  const beforeFailedReload = applied.length;
  await act(async () => changeContext(renderer, 16384)); await flush();
  assert.equal(applied.length, beforeFailedReload, "a failed reload does not replace the prior chat binding");
  assert.equal(props.configuration.deployment_id, "dep_a");
  assert.equal(aria(renderer, "Chat context", "input").props["data-token-value"], 16384, "the failed candidate stays available for correction or retry");
  assert.match(text(renderer.root), /GPU memory exhausted while reloading/);
  const reloadConfiguration = props.configuration;
  await update({ conversationId: "chat_other", selectionGeneration: 2, configuration: { model_configuration_id: "config_a", deployment_id: "dep_a" } });
  await update({ conversationId: "chat_reload", selectionGeneration: 3, configuration: reloadConfiguration });
  assert.equal(aria(renderer, "Chat context", "input").props["data-token-value"], 16384, "returning to a chat restores its pending capacity draft");
  failure = "";
  let refreshCalls = 0;
  await update({ onReloaded: async () => { refreshCalls++; throw new Error("Status service unavailable"); } });
  const beforeRefreshApply = applied.length, beforeRefreshLoad = loaded.length;
  await act(async () => changeContext(renderer, 12288)); await flush();
  assert.equal(applied.length, beforeRefreshApply + 1, "a successful loaded candidate is applied despite status-refresh failure");
  assert.equal(applied.at(-1).deployment_id, "dep_config_a", "the applied chat binding identifies the actual loaded result");
  assert.equal(applied.at(-1).startup_overrides.ctx_size, 12288, "the accepted context matches the candidate that loaded");
  assert.equal(loaded.length, beforeRefreshLoad + 1);
  assert.equal(refreshCalls, 1, "a failed observation is not automatically repeated");
  assert.match(text(renderer.root), /Status service unavailable/);
  assert.doesNotMatch(text(renderer.root), /Settings applied/);
  assert.equal(renderer.root.findAll(node => node.type === "button" && text(node) === "Refresh status").length, 0, "status refresh has no retry button");
  const acceptedTuning = applied.at(-1);
  await update({ configuration: acceptedTuning, selectedDeploymentId: acceptedTuning.deployment_id, deployments: [deployment("dep_config_a", "bundle_a", "config_a", { ctx_size: 12288 })] });
  assert.equal(aria(renderer, "Chat context", "input").props["data-token-value"], 12288, "accepted context stays visible after the caller publishes it");

  await update({ onReloaded: async () => {}, conversationId: "chat_apply_failure", configuration: { model_configuration_id: "config_a", deployment_id: "dep_config_a", startup_overrides: { ctx_size: 12288 } }, onApply: async () => { throw new Error("Chat selection unavailable"); } });
  await act(async () => changeContext(renderer, 16384)); await flush();
  assert.match(text(renderer.root), /Chat selection unavailable/, "a failed application remains an operation failure even if loading succeeded");
  assert.doesNotMatch(text(renderer.root), /Settings applied/);
  assert.equal(props.configuration.startup_overrides.ctx_size, 12288, "failed application leaves the accepted chat configuration unchanged");
  assert.equal(aria(renderer, "Chat context", "input").props["data-token-value"], 16384, "failed application retains the candidate for correction");

  const normalLoad = api.applyChatStartupOverrides;
  const lateLoad = Promise.withResolvers();
  api.applyChatStartupOverrides = async () => lateLoad.promise;
  await update({ conversationId: "chat_late_load", onApply: next => applied.push(next), configuration: { model_configuration_id: "config_a", deployment_id: "dep_config_a", startup_overrides: { ctx_size: 12288 } } });
  const beforeLateLoad = applied.length;
  await act(async () => changeContext(renderer, 20480)); await flush();
  await update({ conversationId: "chat_after_load", configuration: { model_configuration_id: "config_a", deployment_id: "dep_config_a", startup_overrides: { ctx_size: 8192 } } });
  await act(async () => lateLoad.resolve(deployment("late", "bundle_a", "config_a", { ctx_size: 20480 }))); await flush();
  assert.equal(applied.length, beforeLateLoad, "a late load cannot apply its candidate to the newly selected chat");
  assert.equal(aria(renderer, "Chat context", "input").props["data-token-value"], 8192);
  assert.equal(aria(renderer, "Chat context", "input").props.disabled, false, "a stale completion releases controls for the current chat");
  api.applyChatStartupOverrides = normalLoad;

  const lateRefresh = Promise.withResolvers();
  await update({ conversationId: "chat_late_refresh", onReloaded: async () => lateRefresh.promise });
  await act(async () => changeContext(renderer, 24576)); await flush();
  await update({ conversationId: "chat_after_refresh", configuration: { model_configuration_id: "config_a", deployment_id: "dep_config_a", startup_overrides: { ctx_size: 8192 } } });
  await act(async () => lateRefresh.reject(new Error("Previous chat status unavailable"))); await flush();
  assert.doesNotMatch(text(renderer.root), /Previous chat status unavailable/, "a late refresh failure cannot become another chat's warning");
  await update({ onReloaded: async () => {} });
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
  assert.notEqual(thinkingChoice(renderer, "off").props.disabled, true, "an assigned model still exposes its Thinking levels");
  assert.notEqual(aria(renderer, "Chat context", "input").props.disabled, true, "an assigned model still exposes Context");
  await act(async () => button(renderer, "Change in Agents").props.onClick());
  assert.equal(managedAgent, 1);
  const fullResolve = workspaceApi.resolveSetup;
  const effortSupport = options.per_request_defaults.reasoning_effort.supported;
  options.per_request_defaults.reasoning_effort.supported = false;
  workspaceApi.resolveSetup = async (...args) => {
    const result = await fullResolve(...args);
    const selected = args[2].per_request_overrides?.reasoning;
    result.effective_values['per_request.reasoning'] = { value: selected ?? null, known: selected != null, source: selected == null ? 'Template default not reported' : 'This chat', inherited_value: null, default_value: null };
    return result;
  };
  const coldProfile = { ...profiles[0], bags: { ...profiles[0].bags, per_request: bag({ temperature: 0.3, max_tokens: 6000 }) } };
  await update({ fixedModel: false, profiles: [coldProfile], deployments: [], selectedDeploymentId: '', selectedConfigurationId: coldProfile.id, conversationId: 'cold_auto', configuration: { model_configuration_id: coldProfile.id } });
  await open(renderer, "Chat model: Qwen");
  assert.notEqual(thinkingChoice(renderer, 'off').props.disabled, true, 'supported cold binary Thinking allows Off even when the native default is unknown');
  const coldLoads = loaded.length;
  await act(async () => thinkingChoice(renderer, 'off').props.onChange()); await flush();
  assert.equal(applied.at(-1).per_request_overrides.reasoning, 'off', 'cold Off applies to the next accepted message');
  assert.equal(loaded.length, coldLoads, 'choosing cold Thinking never loads weights');
  await update({ configuration: applied.at(-1) });
  await act(async () => resetSetting(renderer, 'Thinking')); await flush();
  assert.equal(Object.hasOwn(applied.at(-1).per_request_overrides, 'reasoning'), false, 'reset restores unknown native default by omission');
  workspaceApi.resolveSetup = fullResolve;
  options.per_request_defaults.reasoning_effort.supported = effortSupport;
  const connected = { ...deployment("connected_1", null, null), scope: "connected", display_name: "connected:Remote" };
  await update({ fixedModel: false, bundles: [], profiles: [], deployments: [connected], selectedDeploymentId: connected.id, selectedConfigurationId: undefined, configuration: { deployment_id: connected.id } });
  await open(renderer, "Chat model: Remote");
  const connectedContext = aria(renderer, "Chat context", "input");
  const connectedHelp = renderer.root.findAll(node => node.type?.name === "SettingRow" && node.props.label === "Context")[0];
  assert.equal(connectedContext.props.disabled, true, "external connection has no owned reload authority");
  assert.match(connectedContext.props.title, /Context is managed by this connection/);
  assert.match(String(connectedHelp.props.help), /Context is managed by this connection/);
  assert.doesNotMatch(text(renderer.root), /Context is managed by this connection/, "the connection reason stays on hover or focus");
  previewFailure = true;
  await update({ conversationId: "chat_4" }); await flush();
  const duplicates = ["publisher_a", "publisher_b"].map((publisher, index) => ({ ...bundles[0], id: "duplicate_" + index, display_name: publisher + "/qwen-8b", source: { repo_id: publisher + "/qwen-8b" }, default_configuration_id: "duplicate_config_" + index }));
  await update({ bundles: duplicates, deployments: [], profiles: duplicates.map((bundle, index) => profile("duplicate_config_" + index, bundle.id, "Default")) });
  assert.equal(new Set(choices(renderer).map(text)).size, 2, "short model names retain distinct publisher identities");
  assert.ok(choices(renderer).every(node => !text(node).includes(".gguf")), "model groups keep full filenames in their tooltip");
  const dotted = { id: "bundle_dot", display_name: "Qwen3.5-0.8B.Q4_K_M.gguf", quantization: "Q4_K_M", primary_path: "C:/models/Qwen3.5-0.8B.Q4_K_M.gguf", status: "ready", disk_matches: true, default_configuration_id: "config_dot" };
  const unknownBundle = { id: "bundle_unknown", display_name: "custom-weights.gguf", quantization: null, primary_path: "C:/models/custom-weights.gguf", status: "ready", disk_matches: true, default_configuration_id: "config_unknown" };
  await update({ bundles: [dotted, unknownBundle], profiles: [profile("config_dot", "bundle_dot", "Default"), profile("config_unknown", "bundle_unknown", "Default")], deployments: [], selectedDeploymentId: "", selectedConfigurationId: "config_dot", configuration: { model_configuration_id: "config_dot" }, fixedModel: false });
  const dottedRow = choices(renderer).find(node => text(node).includes("Q4_K_M"));
  assert.ok(dottedRow, "a known quantization token stays visible after a dot");
  assert.match(dottedRow.props.title, /Qwen3\.5-0\.8B\.Q4_K_M\.gguf/);
  const unknownRow = choices(renderer).find(node => text(node).includes("Custom Weights"));
  assert.ok(unknownRow, "an unknown weight name stays selectable");
  assert.doesNotMatch(text(unknownRow), /Q\d|IQ\d|F16|F32|BF16/, "an unknown name does not invent a quantization");
  await assertEverydayLabels();
  await act(async () => renderer.unmount()); renderer = undefined;
  await checkSavedRevisionAndChoiceCompletion();
  console.log("Chat model picker, exact residency, safe staging and per-model tuning checks passed.");
} finally {
  if (renderer) await act(async () => renderer.unmount());
  Object.assign(api, { deploymentConfiguration: original.deploymentConfiguration, modelConfiguration: original.modelConfiguration, applyChatStartupOverrides: original.applyChatStartupOverrides });
  Object.assign(workspaceApi, { resolveSetup: original.resolveSetup, chatReadiness: original.chatReadiness });
  globalThis.window = originalWindow;
  await vite.close();
}

async function assertEverydayLabels() {
  const { RecoverySettingsPanel } = await vite.ssrLoadModule("/src/renderer/RecoverySettingsPanel.tsx");
  const { ProjectFileGrantControls } = await vite.ssrLoadModule("/src/renderer/ProjectFileGrantControls.tsx");
  const { AgentRunPanel } = await vite.ssrLoadModule("/src/renderer/AgentRunPanel.tsx");
  let settings, projectEdit, task;
  try {
    await act(async () => { settings = create(React.createElement(RecoverySettingsPanel, {})); }); await flush();
    assert.match(text(settings.root), /Theme/, "Settings keeps a short Theme label");
    assert.match(text(settings.root), /System/);
    assert.match(text(settings.root), /Dark/);
    assert.match(text(settings.root), /Light/);
    await act(async () => { projectEdit = create(React.createElement(ProjectFileGrantControls, { onSaved: async () => {} })); }); await flush();
    assert.match(text(projectEdit.root), /Project/);
    assert.match(text(projectEdit.root), /Create files/);
    assert.match(text(projectEdit.root), /Edit files/);
    await act(async () => { task = create(React.createElement(AgentRunPanel, {})); }); await flush();
    assert.match(text(task.root), /Run a task/);
    const menu = task.root.findAll(node => String(node.props.className ?? "").includes("chat-model-controls"))[0];
    assert.ok(menu, "the one-task page uses the chat model menu");
    assert.equal(menu.findAll(node => node.props.name === "tune" || node.props["aria-label"] === "Tune model").length, 0, "the one-task menu has no tune icon");
    assert.equal(menu.findAll(node => node.type === "button" && /Apply|Stage/.test(text(node))).length, 0, "the one-task menu has no Apply or Stage");
    assert.doesNotMatch(text(menu), /This chat|This task|Apply this chat/);
  } finally {
    for (const mounted of [settings, projectEdit, task]) if (mounted) await act(async () => mounted.unmount());
  }
}

async function checkSavedRevisionAndChoiceCompletion() {
  let mounted;
  const localProfiles = profiles.map(item => ({ ...item, revision: 1 }));
  const loads = [], applications = [], busyReports = [];
  let optionReads = 0, pendingRefresh = null, pendingAcceptance = null;
  let props = { bundles, profiles: localProfiles, deployments: [deployment("resident", "bundle_a", "config_a")], selectedDeploymentId: "resident", selectedConfigurationId: "config_a", configuration: { model_configuration_id: "config_a", deployment_id: "resident" }, conversationId: "revision-chat" };
  const publish = patch => { props = { ...props, ...patch }; mounted.update(React.createElement(ChatModelControls, props)); };
  const update = async patch => { await act(async () => publish(patch)); await flush(); };
  workspaceApi.resolveSetup = async (_project, _agent, configuration) => {
    const selected = props.profiles.find(item => item.id === configuration.model_configuration_id);
    const startup = { ...selected?.bags.startup.requested, ...configuration.startup_overrides };
    const exact = props.deployments.find(item => item.bundle_id === selected?.bundle_id && item.settings.startup.requested.ctx_size === startup.ctx_size);
    const inherited = (key, bag) => ({ value: configuration[bag + "_overrides"]?.[key] ?? selected?.bags[bag].requested[key], known: true, source: "Configuration: Default", inherited: true, inherited_value: selected?.bags[bag].requested[key], inherited_source: "Configuration: Default" });
    return { configuration: { ...configuration, deployment_id: exact?.id ?? null }, instruction_layers: [], effective_values: { "startup.ctx_size": inherited("ctx_size", "startup"), "per_request.reasoning": inherited("reasoning", "per_request"), "per_request.reasoning_effort": inherited("reasoning_effort", "per_request") } };
  };
  workspaceApi.chatReadiness = async () => ({ status: "ready", can_send: true, issues: [] });
  api.modelConfiguration = async () => { optionReads++; return options; };
  api.applyChatStartupOverrides = async (bundle, configuration, startup) => {
    const selected = props.profiles.find(item => item.id === configuration);
    const loaded = deployment("loaded-" + loads.length, bundle, configuration, { ...selected.bags.startup.requested, ...startup });
    loads.push(loaded); return loaded;
  };
  props.onApply = async configuration => {
    applications.push(configuration);
    publish({ configuration, selectedConfigurationId: configuration.model_configuration_id, selectedDeploymentId: configuration.deployment_id });
    if (pendingAcceptance) await pendingAcceptance.promise;
  };
  props.onReloaded = async () => {
    if (pendingRefresh) await pendingRefresh.promise;
    publish({ deployments: [loads.at(-1)] });
  };
  props.onBusyChange = busy => busyReports.push(busy);
  try {
    await act(async () => { mounted = create(React.createElement(ChatModelControls, props)); }); await flush();
    await open(mounted, "Chat model: Qwen");
    assert.equal(aria(mounted, "Chat context", "input").props["data-token-value"], 32768);
    assert.equal(thinkingChoice(mounted, "high").props.checked, true);
    const oldOptionReads = optionReads;
    localProfiles[0] = { ...localProfiles[0], revision: 2, bags: { ...localProfiles[0].bags, startup: bag({ ctx_size: 16384 }), per_request: bag({ reasoning: "on", reasoning_effort: "medium" }) } };
    await update({ profiles: [...localProfiles] });
    assert.equal(aria(mounted, "Chat context", "input").props["data-token-value"], 16384, "an open tuning panel follows revised inherited Context");
    assert.equal(thinkingChoice(mounted, "medium").props.checked, true, "Thinking follows the revised saved default");
    assert.ok(optionReads > oldOptionReads, "descriptor options also follow the selected saved revision");
    assert.equal(loads.length, 0, "refreshing a saved setup remains passive");
    await open(mounted, "Chat model: Qwen");
    assert.match(choices(mounted)[0].props.title, /Settings not loaded/, "old native settings cannot remain Ready after a saved startup edit");
    await act(async () => choices(mounted)[0].props.onClick()); await flush();
    assert.equal(loads.length, 1, "explicit selection loads the revised saved setup");
    assert.equal(loads[0].settings.startup.requested.ctx_size, 16384);
    localProfiles[0] = { ...localProfiles[0], revision: 3, bags: { ...localProfiles[0].bags, per_request: bag({ reasoning: "on", reasoning_effort: "low" }) } };
    await update({ profiles: [...localProfiles] });
    await open(mounted, "Chat model: Qwen");
    assert.equal(thinkingChoice(mounted, "low").props.checked, true, "a response-only revision updates the visible default");
    await open(mounted, "Chat model: Qwen");
    await act(async () => choices(mounted)[0].props.onClick()); await flush();
    assert.equal(loads.length, 1, "a response-only save reuses the exact loaded startup");

    pendingRefresh = Promise.withResolvers(); pendingAcceptance = Promise.withResolvers();
    await open(mounted, "Chat model: Qwen");
    await act(async () => choices(mounted)[1].props.onClick()); await flush();
    assert.equal(props.configuration.model_configuration_id, "config_b");
    assert.equal(aria(mounted, "Chat model: Gemma").props["aria-expanded"], true, "selection is still awaiting acceptance completion");
    await act(async () => pendingAcceptance.resolve()); await flush();
    assert.equal(aria(mounted, "Chat model: Gemma").props["aria-expanded"], false, "its own accepted model transition closes the picker before delayed status refresh");
    await act(async () => pendingRefresh.resolve()); await flush();
    pendingRefresh = null;

    pendingAcceptance = Promise.withResolvers();
    await open(mounted, "Chat model: Gemma");
    await act(async () => choices(mounted)[0].props.onClick()); await flush();
    await update({ conversationId: "another-chat" });
    await open(mounted, "Chat model: Qwen");
    await act(async () => pendingAcceptance.resolve()); await flush();
    assert.equal(aria(mounted, "Chat model: Qwen").props["aria-expanded"], true, "late acceptance cannot close a newly selected chat's picker");
    assert.equal(applications.length, 3, "late completion cannot reapply a selection");

    await update({ conversationId: null, selectionGeneration: 10, selectedConfigurationId: "config_a", selectedDeploymentId: "", configuration: { model_configuration_id: "config_a", startup_overrides: { ctx_size: 8192 } } });
    await open(mounted, "Chat model: Qwen");
    await act(async () => changeContext(mounted, 12288)); await flush();
    await update({ selectionGeneration: 11 });
    assert.equal(aria(mounted, "Chat context", "input").props["data-token-value"], 12288, "fresh New preserves pending settings while changing transient operation ownership");

    const resolving = Promise.withResolvers(), resolveBeforeDisposal = workspaceApi.resolveSetup;
    workspaceApi.resolveSetup = async (...args) => { if (args[2].model_configuration_id === "config_b") await resolving.promise; return resolveBeforeDisposal(...args); };
    const beforeDisposal = { loads: loads.length, applications: applications.length };
    await open(mounted, "Chat model: Qwen");
    await act(async () => choices(mounted)[1].props.onClick()); await flush();
    assert.equal(busyReports.at(-1), true, "model preflight publishes its pending state");
    await act(async () => mounted.unmount()); mounted = undefined;
    assert.equal(busyReports.at(-1), false, "disposal clears the reported selection gate");
    await act(async () => resolving.resolve()); await flush();
    assert.equal(loads.length, beforeDisposal.loads, "disposed model preparation cannot start a model later");
    assert.equal(applications.length, beforeDisposal.applications, "disposed model preparation cannot apply to a replacement owner");
    workspaceApi.resolveSetup = resolveBeforeDisposal;
  } finally {
    pendingAcceptance?.resolve(); pendingRefresh?.resolve();
    if (mounted) await act(async () => mounted.unmount());
  }
}
