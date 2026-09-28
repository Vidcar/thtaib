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
