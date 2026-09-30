import assert from "node:assert/strict";
import path from "node:path";
import { fileURLToPath } from "node:url";
import React from "react";
import { act, create } from "react-test-renderer";
import { createServer as createViteServer } from "vite";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const vite = await createViteServer({ root, appType: "custom", server: { middlewareMode: true, hmr: false }, logLevel: "error" });
const saved = Object.fromEntries(["window", "document", "fetch", "setTimeout", "clearTimeout", "setInterval", "clearInterval"].map(key => [key, globalThis[key]]));
const savedNow = Date.now;
let view;
try {
  const { emptyResourceReadings, observeResourceReadings, staleResourceReadings, resourceUsageColour } = await vite.ssrLoadModule("/src/renderer/systemResources.ts");
  const { SystemResourceMonitor } = await vite.ssrLoadModule("/src/renderer/SystemResourceMonitor.tsx");
  await act(async () => { view = create(React.createElement(SystemResourceMonitor)); });
  assert.equal(view.root.findAllByProps({ "data-state": "unavailable" }).length, 2, "headless mounts retain honest unknown values without browser polling");
  await act(async () => view.unmount()); view = null;
  let now = Date.parse("2026-09-30T12:00:00Z");
  const snapshot = (extra = {}) => ({
    observed_at: new Date(now).toISOString(), source: "nvidia-smi + psutil", stale: false, reasons: [],
    gpu_observed_at: new Date(now).toISOString(), gpu_stale: false,
    ram_observed_at: new Date(now).toISOString(), ram_stale: false,
    gpu_devices: [{ id: "GPU-1", name: "Small GPU", total_bytes: 100, used_bytes: 75, available_bytes: 10 },
      { id: "GPU-2", name: "Large GPU", total_bytes: 1000, used_bytes: 500, available_bytes: 400 }],
    ram_total_bytes: 100, ram_available_bytes: 50, ...extra,
  });
  const empty = emptyResourceReadings();
  let readings = observeResourceReadings(empty, snapshot(), now);
  assert.equal(readings.gpu.percent, 75, "select the highest percentage, not the largest used memory or total-minus-free");
  assert.match(readings.gpu.name, /Small GPU/);
  assert.equal(readings.ram.percent, 50);
  const partial = observeResourceReadings(readings, snapshot({ gpu_stale: true, ram_available_bytes: 75 }), now);
  assert.equal(partial.gpu.percent, 75); assert.equal(partial.gpu.stale, true);
  assert.equal(partial.ram.percent, 25); assert.equal(partial.ram.stale, false);
  for (const used of [null, -1, 101, NaN, Infinity, "75"]) {
    const bad = observeResourceReadings(empty, snapshot({ gpu_devices: [{ id: "bad", name: "Bad GPU", total_bytes: 100, used_bytes: used }] }), now);
    assert.equal(bad.gpu.percent, null, "malformed or unavailable GPU usage never becomes zero");
    assert.equal(bad.ram.percent, 50);
  }
  assert.equal(observeResourceReadings(empty, snapshot({ gpu_devices: [] }), now).gpu.percent, null);
  assert.equal(observeResourceReadings(empty, snapshot({ ram_available_bytes: 101 }), now).ram.percent, null);
  assert.equal(observeResourceReadings(empty, snapshot({ ram_total_bytes: 0 }), now).ram.percent, null);
  assert.equal(observeResourceReadings(readings, snapshot({ gpu_observed_at: "invalid" }), now).gpu.stale, true);
  assert.equal(observeResourceReadings(empty, snapshot({ gpu_observed_at: new Date(now - 10_000).toISOString() }), now).gpu.stale, true);
  assert.strictEqual(staleResourceReadings(readings, now + 9_999), readings);
  assert.equal(staleResourceReadings(readings, now + 10_000).ram.stale, true);
  assert.equal(observeResourceReadings(partial, snapshot(), now).gpu.stale, false, "a successful observation recovers independently");
  assert.equal(resourceUsageColour(0), "var(--ok)"); assert.equal(resourceUsageColour(50), "var(--ok)");
  assert.match(resourceUsageColour(65), /var\(--warn\) 50\.00%/);
  assert.match(resourceUsageColour(80), /var\(--danger\).*0\.00%/);
  assert.match(resourceUsageColour(87.5), /var\(--danger\).*50\.00%/);
  assert.equal(resourceUsageColour(95), resourceUsageColour(100));
  assert.match(resourceUsageColour(100), /var\(--muted\)/, "high usage uses muted theme red");

  const timers = new Map(); let timerId = 0;
  const schedule = (callback, delay, interval = false) => {
    const id = ++timerId; timers.set(id, { callback, at: now + delay, interval: interval ? delay : 0 }); return id;
  };
  globalThis.setTimeout = (callback, delay) => schedule(callback, delay);
  globalThis.setInterval = (callback, delay) => schedule(callback, delay, true);
  globalThis.clearTimeout = globalThis.clearInterval = id => timers.delete(id);
  Date.now = () => now;
  const listeners = new Set();
  globalThis.document = { visibilityState: "visible", addEventListener: (event, callback) => { assert.equal(event, "visibilitychange"); listeners.add(callback); }, removeEventListener: (_, callback) => listeners.delete(callback) };
  globalThis.window = { workbench: { backendUrl: "http://127.0.0.1:8123" } };
  const requests = []; let ignoreAbort = false;
  globalThis.fetch = (url, init) => new Promise((resolve, reject) => {
    assert.equal(url, "http://127.0.0.1:8123/v1/system/resources"); assert.equal(init.cache, "no-store");
    const item = { init, resolve: body => resolve({ ok: true, json: async () => body }), reject };
    requests.push(item);
    init.signal.addEventListener("abort", () => { if (!ignoreAbort) reject(new DOMException("Cancelled", "AbortError")); }, { once: true });
  });
  const flush = async callback => act(async () => { callback?.(); await Promise.resolve(); });
  const advance = async milliseconds => {
    const end = now + milliseconds;
    while (true) {
      const next = [...timers.entries()].filter(([, timer]) => timer.at <= end).sort((a, b) => a[1].at - b[1].at)[0];
      if (!next) break;
      const [id, timer] = next; now = timer.at;
      if (timer.interval) timer.at += timer.interval; else timers.delete(id);
      await flush(timer.callback);
    }
    now = end;
  };
  const visibility = async value => flush(() => { document.visibilityState = value; for (const callback of listeners) callback(); });
  let parentRenders = 0;
  function Parent() { parentRenders++; return React.createElement(SystemResourceMonitor); }
  await flush(() => { view = create(React.createElement(Parent)); });
  const metric = name => view.root.findByProps({ "data-resource": name }).props;
  assert.equal(requests.length, 1); assert.equal(metric("gpu")["data-state"], "unavailable");
  assert.equal(metric("gpu").role, "img");
  await flush(() => requests[0].resolve(snapshot()));
  assert.equal(metric("gpu")["aria-valuenow"], 75); assert.equal(metric("ram")["aria-valuenow"], 50);
  assert.match(metric("gpu")["aria-label"], /Small GPU/);
  for (const node of view.root.findAll(() => true)) {
    for (const prop of ["onClick", "onMouseEnter", "title", "aria-live", "tabIndex"]) assert.equal(node.props[prop], undefined, "rings stay quiet and non-interactive");
  }
  await advance(1_999); assert.equal(requests.length, 1);
  await advance(1); assert.equal(requests.length, 2);
  await advance(3_999); assert.equal(requests.length, 2, "a slow read never overlaps another read");
  assert.equal(metric("gpu")["data-state"], "current");
  await advance(1);
  assert.equal(requests[1].init.signal.aborted, true, "requests time out after four seconds");
  assert.equal(metric("gpu")["data-state"], "stale"); assert.equal(metric("gpu")["aria-valuenow"], 75);
  assert.equal(metric("gpu").style.color, "var(--muted)");
  await advance(2_000); assert.equal(requests.length, 3);
  await flush(() => requests[2].resolve(snapshot({ gpu_stale: true, ram_available_bytes: 75 })));
  assert.equal(metric("gpu")["data-state"], "stale"); assert.equal(metric("ram")["data-state"], "current");
  assert.equal(metric("ram")["aria-valuenow"], 25);
  await advance(2_000);
  await flush(() => requests[3].resolve(snapshot({ gpu_devices: [{ id: "zero", name: "Zero GPU", total_bytes: 100, used_bytes: 0 }], ram_available_bytes: 0 })));
  assert.equal(metric("gpu")["aria-valuenow"], 0); assert.equal(metric("gpu")["data-state"], "current");
  assert.equal(metric("ram")["aria-valuenow"], 100); assert.notEqual(metric("ram").style.color, "var(--muted)");
  await advance(2_000);
  await flush(() => requests[4].reject(new Error("Network failed")));
  assert.equal(metric("ram")["data-state"], "stale", "reported failures grey immediately");
  await advance(2_000);
  await flush(() => requests[5].resolve(snapshot()));
  assert.equal(metric("gpu")["data-state"], "current"); assert.equal(metric("ram")["data-state"], "current");
  assert.equal(parentRenders, 1, "polling does not rerender the containing navigation or Chat");
  await visibility("hidden"); assert.equal(timers.size, 0);
  const hiddenCount = requests.length;
  await advance(11_000); assert.equal(requests.length, hiddenCount, "hidden windows stop polling and expiry timers");
  await visibility("visible");
  assert.equal(metric("gpu")["data-state"], "stale", "expired readings turn grey immediately on return");
  assert.equal(requests.length, hiddenCount + 1);
  ignoreAbort = true;
  const old = requests.at(-1);
  await visibility("hidden"); assert.equal(old.init.signal.aborted, true);
  await visibility("visible");
  const current = requests.at(-1);
  await flush(() => current.resolve(snapshot()));
  await flush(() => old.resolve(snapshot({ ram_available_bytes: 0 })));
  assert.equal(metric("ram")["aria-valuenow"], 50, "a late cancelled response cannot overwrite the resumed observer");
  await advance(2_000);
  const pending = requests.at(-1);
  await flush(() => view.unmount()); view = null;
  assert.equal(pending.init.signal.aborted, true); assert.equal(timers.size, 0); assert.equal(listeners.size, 0);
  await flush(() => pending.resolve(snapshot()));
  await advance(20_000); assert.equal(requests.at(-1), pending, "unmounted monitors cannot schedule more work");
  console.log("System resource values, freshness, colour and mounted polling checks passed.");
} finally {
  if (view) await act(async () => view.unmount());
  Object.assign(globalThis, saved); Date.now = savedNow;
  await vite.close();
}
