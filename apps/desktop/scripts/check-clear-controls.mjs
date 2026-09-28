import assert from "node:assert/strict";
import React from "react";
import { act, create } from "react-test-renderer";
import { createServer } from "vite";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;
globalThis.window = { setTimeout, clearTimeout };
const vite = await createServer({ appType: "custom", server: { middlewareMode: true, hmr: false }, logLevel: "error" });
const tick = () => new Promise(resolve => setTimeout(resolve, 0));
const text = node => typeof node === "string" ? node : (node?.children ?? []).map(text).join("");
try {
  const { defaultSettingDisplay, settingValue } = await vite.ssrLoadModule("/src/renderer/effectiveSettings.ts");
  const { ResponseSettingsEditor } = await vite.ssrLoadModule("/src/renderer/ResponseSettingsEditor.tsx");
  const { SettingRow } = await vite.ssrLoadModule("/src/renderer/CompactControls.tsx");
  const { ChoiceControl } = await vite.ssrLoadModule("/src/renderer/ModelControls.tsx");
  const { ModelHardwareEstimate } = await vite.ssrLoadModule("/src/renderer/ModelHardwareEstimate.tsx");
  const fact = { value: "off", known: true, source: "Turn overrides", inherited_value: "on", inherited_source: "Configuration: Balanced", default_value: "off", default_source: "gguf_template" };
  assert.deepEqual(defaultSettingDisplay(fact, "configuration"), { value: "On", source: "Configuration default", label: "Use configuration default", title: "On · Configuration: Balanced" });
  assert.equal(defaultSettingDisplay(fact, "model").value, "Off");
  assert.equal(defaultSettingDisplay({ ...fact, inherited_value: "off", inherited_source: "gguf_template" }, "configuration").label, "Use configuration default", "following a configuration remains distinct even if its current default equals the template");
  assert.equal(settingValue("all", "n_gpu_layers"), "All layers");
  assert.equal(settingValue(-1, "n_gpu_layers"), "Automatic");
  assert.equal(settingValue("off", "fit"), "Off");
  assert.equal(settingValue("q4_0", "cache_type_k"), "q4_0");
  assert.equal(settingValue(null, "ctx_size"), "Not reported");

  let renderer, requested = {}, writes = 0;
  let resolved = 0.6;
  const props = () => ({ part: "sampling", inheritance: "model", value: requested, facts: { "per_request.temperature": { value: Object.hasOwn(requested, "temperature") ? requested.temperature : resolved, known: true, source: "gguf_template", default_value: resolved, default_source: "gguf_template" } }, options: null, onChange: value => { writes++; requested = value; renderer.update(React.createElement(ResponseSettingsEditor, props())); } });
  try {
    await act(async () => { renderer = create(React.createElement(ResponseSettingsEditor, props())); });
    const input = () => renderer.root.findAllByType("input").find(node => node.props.id === "model-response-temperature");
    assert.equal(input().props.placeholder, "0.6");
    assert.equal(writes, 0, "displaying defaults never creates an override");
    resolved = 0.8;
    await act(async () => renderer.update(React.createElement(ResponseSettingsEditor, props())));
    assert.equal(input().props.placeholder, "0.8", "following controls update with changed defaults");
    await act(async () => input().props.onChange({ target: { value: "0.67" } }));
    resolved = 0.9;
    await act(async () => renderer.update(React.createElement(ResponseSettingsEditor, { ...props(), loading: true })));
    assert.equal(input().props.value, 0.67, "explicit selection survives future defaults");
    assert.equal(input().props.disabled, false, "checking does not interrupt editing");
    await act(async () => input().props.onChange({ target: { value: "" } }));
    assert.deepEqual(requested, {}, "clearing restores omission");
    assert.equal(input().props.placeholder, "0.9");
    assert.ok(!text(renderer.root).includes("Inherited"));
  } finally { if (renderer) await act(async () => renderer.unmount()); }

  await stableModelsControls(SettingRow, ChoiceControl, ResponseSettingsEditor);

  const originalFetch = globalThis.fetch;
  const originalTimer = window.setTimeout;
  const originalClear = window.clearTimeout;
  const requests = [];
  const pendingTimers = new Map(); let timerId = 0;
  window.setTimeout = callback => { const id = ++timerId; pendingTimers.set(id, callback); return id; };
  window.clearTimeout = id => pendingTimers.delete(id);
  const flush = async () => { const timers = [...pendingTimers.values()]; pendingTimers.clear(); await act(async () => { timers.forEach(callback => callback()); await tick(); }); };
  globalThis.fetch = async (_url, init) => { requests.push(JSON.parse(init.body)); return { ok: true, status: 200, json: async () => ({ hardware: { gpu_devices: [], ram_available_bytes: null, ram_total_bytes: null }, unknown_reasons: [], assumptions: [], estimated_at: new Date().toISOString() }) }; };
  try {
    await act(async () => { renderer = create(React.createElement(ModelHardwareEstimate, { selection: { bundle_id: "one", startup: {} } })); });
    await flush();
    await act(async () => renderer.root.findByProps({ "aria-label": "Refresh hardware estimate" }).props.onClick());
    await flush();
    await act(async () => renderer.update(React.createElement(ModelHardwareEstimate, { selection: { bundle_id: "one", startup: { ctx_size: 32768 } } })));
    await flush();
    assert.deepEqual(requests.map(request => request.refresh), [false, true, false], "manual Refresh bypasses the cache for one request only");
    assert.ok(text(renderer.root).includes("Not reported"), "unknown GPU availability is explicit");
  } finally { if (renderer) await act(async () => renderer.unmount()); globalThis.fetch = originalFetch; window.setTimeout = originalTimer; window.clearTimeout = originalClear; }
} finally { await vite.close(); }
console.log("Clear controls, live default following and one-request estimate refresh checks passed.");

async function stableModelsControls(SettingRow, ChoiceControl, ResponseSettingsEditor) {
  let renderer;
  const mount = async element => { await act(async () => { renderer = create(element); }); };
  const update = async element => { await act(async () => renderer.update(element)); };
  const unmount = async () => { if (renderer) await act(async () => renderer.unmount()); renderer = null; };
  const input = id => renderer.root.findAllByType("input").find(node => node.props.id === id);
  const options = [{ value: "on", label: "On" }, { value: "off", label: "Off" }];
  const choice = props => React.createElement(ChoiceControl, { id: "models-choice", label: "Placement", value: "", options, onChange: () => {}, custom: false, stable: true, ...props });
  try {
    await mount(choice({ resolvedLabel: "An exceptionally long model default description" }));
    const group = renderer.root.findByProps({ role: "radiogroup" });
    await update(choice({ resolvedLabel: "On" }));
    assert.equal(renderer.root.findByProps({ role: "radiogroup" }), group, "a resolved label's length cannot replace the mounted control kind");
    assert.equal(text(group).includes("Model default"), false, "the value/source column owns dynamic defaults");
    await unmount();

    await mount(choice({ custom: true, value: "on" }));
    const custom = renderer.root.findByProps({ "aria-label": "Custom placement" });
    assert.equal(custom.props.disabled, true);
    await update(choice({ custom: true, value: "custom" }));
    assert.equal(renderer.root.findByProps({ "aria-label": "Custom placement" }), custom, "Custom enables an existing exact-entry slot");
    assert.equal(custom.props.disabled, false);
    await unmount();

    const row = props => React.createElement(SettingRow, { layout: "models", label: "Stable row", help: "Setting help", ...props }, React.createElement("input", { value: "" }));
    await mount(row({ hint: "A long explanation belongs in accessible help.", provenance: "Before" }));
    const reset = renderer.root.findAllByType("button").find(node => text(node) === "Reset");
    assert.equal(reset.props.disabled, true);
    assert.equal(renderer.root.findAllByProps({ className: "setting-row-hint" }).length, 0, "variable prose leaves the row's flow");
    const status = renderer.root.findByProps({ className: "setting-row-status" });
    await update(row({ provenance: "After", onReset: () => {}, status: "Checking…" }));
    assert.equal(renderer.root.findAllByType("button").find(node => text(node) === "Reset"), reset, "Reset availability retains its mounted slot");
    assert.equal(reset.props.disabled, false);
    assert.equal(renderer.root.findByProps({ className: "setting-row-status" }), status, "pending status uses a reserved slot");
    await unmount();

    const fact = value => ({ value, known: true, source: "gguf_template", default_value: value, default_source: "gguf_template" });
    const facts = {
      "per_request.reasoning": fact("on"), "per_request.reasoning_preserve": fact(true),
      "per_request.reasoning_budget_tokens": fact(-1), "per_request.max_tokens": fact(4096),
    };
    const descriptors = { reasoning: { supported: true }, reasoning_preserve: { supported: true }, reasoning_budget_tokens: { supported: true }, max_tokens: { supported: true }, reasoning_format: { supported: true, options: [{ value: "auto", label: "Automatic" }, { value: "none", label: "No separation" }] } };
    let value = { reasoning_budget_tokens: -1 };
    let pending = false;
    const editor = extra => React.createElement(ResponseSettingsEditor, {
      layout: "models", inheritance: "model", value, options: { per_request_defaults: descriptors },
      facts: pending ? {} : facts, presentationFacts: facts, loading: pending,
      onChange: next => { value = next; renderer.update(editor()); }, ...extra,
    });
    await mount(editor());
    const thinking = renderer.root.findAllByProps({ role: "radiogroup" })[0];
    const history = renderer.root.findAllByProps({ role: "radiogroup" })[1];
    const limit = input("response-thinking-budget-model");
    const format = renderer.root.findByProps({ id: "model-response-reasoning-format" });
    assert.equal(limit.props.value, "", "unlimited thinking has a named mode instead of a visible numeric sentinel");
    assert.equal(limit.props.placeholder, "No limit");
    assert.equal(renderer.root.findByProps({ "aria-label": "Thinking limit mode" }).props.value, "unlimited");
    assert.equal(renderer.root.findAllByType("button").some(node => String(node.props.title).startsWith("-1")), false, "reset help also names the unlimited default");
    pending = true;
    await update(editor());
    assert.equal(renderer.root.findAllByProps({ role: "radiogroup" })[0], thinking, "Thinking remains mounted when authoritative facts are pending");
    assert.equal(renderer.root.findAllByProps({ role: "radiogroup" })[1], history, "history does not flip from a switch to a selector during checks");
    assert.equal(input("response-thinking-budget-model"), limit);
    assert.equal(renderer.root.findByProps({ id: "model-response-reasoning-format" }), format);
    assert.ok(text(renderer.root).includes("Checking…"));
    assert.ok(text(renderer.root).includes("Last checked"), "a retained presentation value does not claim current authority");

    await act(async () => renderer.root.findByProps({ "aria-label": "Thinking limit mode" }).props.onChange({ target: { value: "custom" } }));
    assert.equal(value.reasoning_budget_tokens, 1024);
    await act(async () => limit.props.onChange({ target: { value: "" } }));
    assert.equal(Object.hasOwn(value, "reasoning_budget_tokens"), false, "clearing restores canonical omission");
    assert.equal(limit.props.disabled, false, "clearing to Default leaves the mounted number entry focused and usable");
    await act(async () => limit.props.onChange({ target: { value: "3456" } }));
    assert.equal(value.reasoning_budget_tokens, 3456);
    await act(async () => format.props.onChange({ target: { value: "none" } }));
    assert.equal(value.reasoning_format, "none", "format uses the canonical response owner");
    await act(async () => history.findAllByType("input").find(node => node.props.value === "drop").props.onChange());
    assert.equal(value.reasoning_preserve, false, "Drop persists explicit false rather than omitting history");
    const budget = input("model-response-max_tokens");
    await act(async () => budget.props.onChange({ target: { value: "6789" } }));
    assert.equal(input("model-response-max_tokens").props.value, 6789, "authoring remains immediate while the resolver is delayed");
    assert.ok(text(renderer.root).includes("6789"));
    assert.equal(Object.hasOwn(value, "reasoning_budget"), false, "editing never reintroduces the startup alias");

    await update(editor({ options: { per_request_defaults: { ...descriptors, reasoning_budget_tokens: { supported: false, description: "Unsupported by the current template." } } } }));
    assert.equal(input("response-thinking-budget-model"), limit, "current unavailability disables rather than removes the input");
    assert.equal(limit.props.disabled, true, "presentation snapshots cannot override the current descriptor's support");
  } finally { await unmount(); }
}
