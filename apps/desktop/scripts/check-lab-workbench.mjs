import assert from "node:assert/strict";
import path from "node:path";
import { fileURLToPath } from "node:url";
import React from "react";
import { act, create } from "react-test-renderer";
import { createServer } from "vite";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;
const intervals = new Map(); let timerId = 0;
globalThis.window = { addEventListener() {}, removeEventListener() {}, setInterval(fn) { intervals.set(++timerId, fn); return timerId; }, clearInterval(id) { intervals.delete(id); } };
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const vite = await createServer({ root, appType: "custom", server: { middlewareMode: true, hmr: false }, logLevel: "error" });
const originals = [];
let renderer;
try {
  const { LabWorkbench } = await vite.ssrLoadModule("/src/renderer/LabWorkbench.tsx");
  const { LabCharts } = await vite.ssrLoadModule("/src/renderer/LabCharts.tsx");
  const { api } = await vite.ssrLoadModule("/src/renderer/api.ts");
  const { labApi } = await vite.ssrLoadModule("/src/renderer/labApi.ts");
  const { labChartSeries, labPromptLengths, labLeaveOwners } = await vite.ssrLoadModule("/src/renderer/labPresentation.ts");
  const { workbenchTabs } = await vite.ssrLoadModule("/src/renderer/workspaceNavigation.ts");
  assert.ok(workbenchTabs.includes("lab"), "Lab is a sidebar destination");
  const patch = (object, key, value) => { originals.push([object, key, object[key]]); object[key] = value; };
  const bag = requested => ({ requested, applied: requested });
  const profiles = [1, 2].map(value => ({ id: `setup${value}`, bundle_id: `model${value}`, display_name: `Setup ${value}`, bags: { startup: bag({ ctx_size: 8192, n_gpu_layers: 0 }), per_request: bag({}), agent: bag({}) } }));
  const options = { bundle_id: "model1", context_size: { key: "ctx_size", maximum: 262144, minimum: 1024, options: [32768, 65536, 131072, 262144].map(value => ({ value, label: String(value) })) }, gpu_layers: { key: "n_gpu_layers", maximum: 32, options: ["auto", "all", 0, 8, 16, 32].map(value => ({ value, label: String(value) })) }, startup_defaults: { parallel: { options: [{ value: -1, label: "Auto" }] }, fit: { supported: true, options: [{ value: "on", label: "On" }, { value: "off", label: "Off" }], default_value: "on" }, spec_type: { supported: true, options: [{ value: "none", label: "Off" }], default_value: "none" } }, per_request_defaults: {}, metadata: {} };
  assert.deepEqual(labPromptLengths(options, 8192), [1024, 2048, 4096, 8192], "Models slider legal sizes stay available below the coarse descriptor suggestions");
  assert.deepEqual(labPromptLengths({ ...options, context_size: { ...options.context_size, maximum: 4096 } }, 8192), [1024, 2048, 4096], "model maximum bounds the prompt switches");
  patch(api, "bundles", async () => [1, 2].map(value => ({ id: `model${value}`, display_name: `Model ${value}`, primary_path: "installed.gguf", disk_matches: true, default_configuration_id: `setup${value}` })));
  patch(api, "profiles", async () => profiles);
  patch(api, "modelConfiguration", async () => structuredClone(options));
  let records = []; let active; let rejectRead = false; let holdStart;
  let challenges = [{ id: "echo", name: "Echo a code", task: "Call echo with CODE", required_text: "CODE", required_tool: "echo", created_at: "2026-09-30T10:00:00Z", updated_at: "2026-09-30T10:00:00Z" }];
  const calls = [];
  const run = (request, id = "run1") => ({ id, kind: request.kind, request, status: "running", created_at: "2026-09-30T10:00:00Z", updated_at: "2026-09-30T10:00:00Z", current: { prompt_length: 1024 }, series: request.configurations.map((item, index) => ({ id: `series${index}`, name: item.configuration_id, configuration_id: item.configuration_id, deployment_id: "loaded", startup: item.startup, context_adjusted: false, concurrent_requests: item.concurrent_requests, benchmark_owned: false })), measurements: [] });
  const point = { id: "point1", series_id: "series0", requested_prompt_length: 1024, prompt_tokens: 1007, context_tokens: 1519, generated_tokens: 512, prefill_tps: 123.4, generation_tps: 27.8, expected: [], missing: [], samples: [], tool_calls: [], created_at: "2026-09-30T10:00:01Z" };
  patch(labApi, "runs", async () => structuredClone(records));
  patch(labApi, "challenges", async () => structuredClone(challenges));
  patch(labApi, "start", async request => { calls.push(["start", structuredClone(request)]); if (holdStart) return holdStart; active = run(request, `run${calls.filter(call => call[0] === "start").length}`); records = [active]; return structuredClone(active); });
  patch(labApi, "run", async id => { calls.push(["read", id]); if (rejectRead) throw new Error("Temporary read failure"); return structuredClone(active); });
  patch(labApi, "stop", async id => { calls.push(["stop", id]); if (active?.id === id) { active = { ...active, status: "stopped", updated_at: "2026-09-30T10:00:09Z", current: null }; records = [active]; return structuredClone(active); } return run(calls.find(call => call[0] === "start")[1], id); });
  patch(labApi, "leave", async ids => { calls.push(["leave", [...ids]]); });
  patch(labApi, "deleteRun", async id => { calls.push(["delete", id]); records = records.filter(item => item.id !== id); });
  patch(labApi, "saveChallenge", async (body, id) => { calls.push(["saveChallenge", body, id]); const saved = { ...body, id: id ?? `new-challenge-${calls.filter(call => call[0] === "saveChallenge" && !call[2]).length}`, created_at: "2026-09-30T11:00:00Z", updated_at: "2026-09-30T11:00:00Z" }; challenges = id ? challenges.map(item => item.id === id ? saved : item) : [...challenges, saved]; return saved; });
  patch(labApi, "deleteChallenge", async id => { challenges = challenges.filter(item => item.id !== id); });
  await mount();
  assert.equal(renderer.root.findByProps({ id: "lab-tab-performance" }).props["aria-selected"], true, "Performance is the first view");
  assert.equal(button("Run benchmark").props.disabled, true);
  assert.match(text(renderer.root), /Choose a model and at least one prompt length/);
  await choose("Lab model", "model1");
  const switches = renderer.root.findAll(node => node.type === "button" && String(node.props["aria-label"] ?? "").startsWith("Prompt length"));
  assert.deepEqual(switches.map(item => item.props["aria-checked"]), [false, false, false, false], "no prompt lengths begin selected");
  assert.equal(renderer.root.findAll(node => node.type === "input" && node.props.type === "radio" && node.props.value === "512")[0].props.checked, true);
  await press("Prompt length 4096 tokens");
  await act(async () => { renderer.root.findAll(node => node.type === "input" && node.props["aria-label"] === "Context")[0].props.onChange({ target: { value: "1" } }); });
  assert.equal(renderer.root.findAll(node => node.type === "button" && node.props["aria-label"] === "Prompt length 4096 tokens").length, 0, "smaller context removes illegal switch");
  assert.equal(button("Run benchmark").props.disabled, true, "removed lengths cannot start a run");
  await act(async () => { renderer.root.findAll(node => node.type === "input" && node.props["aria-label"] === "Context")[0].props.onChange({ target: { value: "7" } }); });
  await press("Prompt length 1024 tokens"); await press("Prompt length 2048 tokens");
  await act(async () => { button("Run benchmark").props.onClick(); button("Run benchmark").props.onClick(); });
  assert.equal(calls.filter(call => call[0] === "start").length, 1, "synchronous double-click submits once");
  assert.equal(calls[0][1].configurations[0].startup.ctx_size, 8192, "unsaved context sent only with run request");
  assert.equal(profiles[0].bags.startup.requested.ctx_size, 8192, "saved profile object was never edited");
  active = { ...active, current: { prompt_length: 2048 }, measurements: [point], updated_at: "2026-09-30T10:00:02Z" };
  await tick();
  const shown = renderer.root.findByType(LabCharts).props.runs;
  assert.deepEqual(labChartSeries(shown, "prefill")[0].points, [{ x: 1007, speed: 123.4 }], "finished first point reaches chart before second finishes and uses reported prompt");
  assert.deepEqual(labChartSeries(shown, "generation")[0].points, [{ x: 1519, speed: 27.8 }], "generation uses actual occupied context rather than configured context");
  rejectRead = true; await tick();
  assert.match(text(renderer.root), /Temporary read failure/);
  assert.equal(button("Run benchmark").props.disabled, true, "failed read retains accepted run ownership");
  assert.equal(calls.filter(call => call[0] === "start").length, 1);
  rejectRead = false; await click("Retry status");
  assert.doesNotMatch(text(renderer.root), /Temporary read failure/);
  await click("Stop");
  assert.equal(renderer.root.findByType(LabCharts).props.runs[0].measurements.length, 1, "Stop keeps only completed points");
  assert.deepEqual(calls.filter(call => call[0] === "stop"), [["stop", "run1"]]);
  const badPointRun = { ...active, measurements: [point, { ...point, id: "failed", error: "Out of memory", requested_prompt_length: 2048, prefill_tps: 0 }] };
  assert.equal(labChartSeries([badPointRun], "prefill")[0].points.length, 1, "failed measurement never becomes a zero chart point");
  await click("Delete");
  assert.equal(calls.filter(call => call[0] === "delete").length, 0, "deletion waits for explicit confirmation");
  await click("Delete result");
  assert.deepEqual(calls.filter(call => call[0] === "delete"), [["delete", "run1"]]);
  await click("Memory");
  assert.equal(renderer.root.findAll(node => node.type === "button" && node.props.role === "switch" && node.props["aria-checked"]).length, 5, "all five depths start on");
  await press("Depth Quarter"); await choose("Memory test", "multi_value");
  await click("Run test");
  assert.deepEqual(calls.filter(call => call[0] === "start").at(-1)[1].depths, [0, 50, 75, 100]);
  await click("Stop");
  await click("Challenges"); await click("Add challenge");
  assert.equal(button("Save challenge").props.disabled, true, "empty text and tool check cannot save");
  await choose("Challenge name", "Clock task"); await choose("Challenge task", "Read the clock"); await choose("Required tool", "time_now");
  await act(async () => renderer.root.findByType("form").props.onSubmit({ preventDefault() {} }));
  assert.match(text(renderer.root), /Echo a code/); assert.match(text(renderer.root), /Clock task/);
  await press("Run challenge Clock task");
  assert.equal(calls.filter(call => call[0] === "start").at(-1)[1].challenge_id, "new-challenge-1");
  await click("Stop");
  await click("Performance");
  await act(async () => renderer.root.findAll(node => node.type === "input" && node.props.type === "radio" && node.props.value === "concurrent")[0].props.onChange());
  await choose("Concurrent requests", "4");
  await click("Add configuration"); await choose("Lab model 2", "model2");
  await click("Run benchmark");
  const concurrent = calls.filter(call => call[0] === "start").at(-1)[1];
  assert.equal(concurrent.mode, "concurrent"); assert.equal(concurrent.configurations.length, 2); assert.equal(concurrent.configurations[0].concurrent_requests, 4);
  await unmount();
  assert.ok(calls.some(call => call[0] === "leave" && call[1].includes(active.id)), "destination exit cleans identified run owners");

  // A late response from the old visit must never cancel the new visit's run.
  records = []; active = null;
  let releaseOld; holdStart = new Promise(resolve => { releaseOld = resolve; });
  await mount(); await choose("Lab model", "model1"); await press("Prompt length 1024 tokens"); await click("Run benchmark");
  const oldRequest = calls.filter(call => call[0] === "start").at(-1)[1];
  await unmount(); holdStart = null; records = [];
  await mount(); await choose("Lab model", "model1"); await press("Prompt length 1024 tokens"); await click("Run benchmark");
  active = { ...active, id: "new-visit" };
  const marker = calls.length;
  await act(async () => releaseOld(run(oldRequest, "old-visit")));
  assert.ok(calls.slice(marker).some(call => call[0] === "stop" && call[1] === "old-visit"));
  assert.ok(calls.slice(marker).filter(call => call[0] === "leave").every(call => call[1].length === 1 && call[1][0] === "old-visit"), "stale response only releases its returned run");
  assert.ok(!calls.slice(marker).some(call => call[0] === "stop" && call[1] === "new-visit"));
  await unmount();

  // An independent failed catalogue read can make Retry slow. Its already-read
  // run snapshot must not erase a subsequent mutation when the catalogue lands.
  records = []; active = null;
  const immediateBundles = api.bundles;
  let catalogueHold = null;
  patch(api, "bundles", () => catalogueHold ?? immediateBundles());
  patch(labApi, "challenges", async () => { throw new Error("Challenge catalogue temporarily unavailable"); });
  await mount(); await choose("Lab model", "model1"); await press("Prompt length 1024 tokens");
  let releaseCatalogue;
  catalogueHold = new Promise(resolve => { releaseCatalogue = resolve; });
  await click("Retry status"); // runs=[] is returned, bundles are still pending
  await click("Run benchmark");
  const acceptedId = active.id;
  await act(async () => releaseCatalogue(await immediateBundles())); catalogueHold = null;
  assert.ok(button("Stop"), "old list response cannot erase a newly accepted run");
  assert.equal(renderer.root.findByType(LabCharts).props.runs[0].id, acceptedId);
  await click("Stop");
  catalogueHold = new Promise(resolve => { releaseCatalogue = resolve; });
  await click("Retry status"); // list captured the old terminal result
  await click("Delete"); await click("Delete result");
  await act(async () => releaseCatalogue(await immediateBundles())); catalogueHold = null;
  assert.equal(renderer.root.findByType(LabCharts).props.runs.length, 0, "old list response cannot resurrect a deleted result");
  // The inverse ordering matters too: reads issued after POST dispatch can
  // still describe the state before that POST was admitted.
  let releasePendingStart;
  holdStart = new Promise(resolve => { releasePendingStart = resolve; });
  await click("Run benchmark");
  const pendingRequest = calls.filter(call => call[0] === "start").at(-1)[1];
  catalogueHold = new Promise(resolve => { releaseCatalogue = resolve; });
  await click("Retry status");
  active = run(pendingRequest, "after-dispatch"); records = [active];
  await act(async () => releasePendingStart(structuredClone(active))); holdStart = null;
  await act(async () => releaseCatalogue(await immediateBundles())); catalogueHold = null;
  assert.ok(button("Stop"), "list issued during pending start cannot erase its later accepted result");
  let releasePendingStop; let releasePendingRead;
  const runningSnapshot = structuredClone(active);
  patch(labApi, "stop", async () => new Promise(resolve => { releasePendingStop = resolve; }));
  patch(labApi, "run", async () => new Promise(resolve => { releasePendingRead = resolve; }));
  await click("Stop"); await tick();
  await act(async () => releasePendingStop({ ...runningSnapshot, status: "stopped" }));
  await act(async () => releasePendingRead(runningSnapshot));
  assert.equal(renderer.root.findByType(LabCharts).props.runs[0].status, "stopped", "same-second poll issued during Stop cannot regress a confirmed terminal result");
  assert.deepEqual(labLeaveOwners([...Array.from({ length: 1001 }, (_, index) => ({ ...run(oldRequest, `history${index}`), status: "completed" })), run(oldRequest, "live-owner")]), ["live-owner"], "large saved history does not overflow the leave request bound");
  await unmount(); records = []; active = null;
  patch(api, "profiles", async () => { throw new Error("Configuration catalogue temporarily unavailable"); });
  patch(labApi, "challenges", async () => structuredClone(challenges));
  await mount(); await click("Challenges");
  // The independent configuration failure keeps a retriable read visible while
  // challenge editing remains usable. Every refresh captures old cards first.
  catalogueHold = new Promise(resolve => { releaseCatalogue = resolve; });
  await click("Retry status"); await click("Add challenge");
  await choose("Challenge name", "New during refresh"); await choose("Challenge task", "Say FRESH"); await choose("Required answer text", "FRESH");
  await act(async () => renderer.root.findByType("form").props.onSubmit({ preventDefault() {} }));
  await act(async () => releaseCatalogue(await immediateBundles())); catalogueHold = null;
  assert.match(text(renderer.root), /New during refresh/, "stale challenge list cannot erase newly saved card");
  catalogueHold = new Promise(resolve => { releaseCatalogue = resolve; });
  await click("Retry status"); await press("Edit challenge Echo a code"); await choose("Required answer text", "EDITED-CHECK");
  await act(async () => renderer.root.findByType("form").props.onSubmit({ preventDefault() {} }));
  await act(async () => releaseCatalogue(await immediateBundles())); catalogueHold = null;
  assert.match(text(renderer.root), /EDITED-CHECK/, "stale challenge list cannot revert the edited check");
  catalogueHold = new Promise(resolve => { releaseCatalogue = resolve; });
  await click("Retry status"); await press("Delete challenge Echo a code"); await click("Delete challenge");
  await act(async () => releaseCatalogue(await immediateBundles())); catalogueHold = null;
  assert.doesNotMatch(text(renderer.root), /Echo a code/, "stale challenge list cannot resurrect a deleted card");
  console.log("Lab destination, legal choices, progressive results, stop/recovery, concurrency, Memory, Challenges and visit ownership checks passed.");

  async function mount() { await act(async () => { renderer = create(React.createElement(LabWorkbench)); }); }
  async function unmount() { if (renderer) { await act(async () => renderer.unmount()); renderer = null; } }
  async function tick() { await act(async () => { for (const callback of [...intervals.values()]) await callback(); }); }
  async function choose(label, value) { await act(async () => renderer.root.findAll(node => ["select", "input", "textarea"].includes(node.type) && node.props["aria-label"] === label)[0].props.onChange({ target: { value } })); }
  async function press(label) { await act(async () => renderer.root.findAll(node => node.type === "button" && node.props["aria-label"] === label)[0].props.onClick()); }
  async function click(label) { const target = button(label); assert.ok(target, `button ${label} exists`); assert.ok(!target.props.disabled, `button ${label} enabled`); await act(async () => { target.props.onClick(); }); }
  function button(label) { return renderer.root.findAll(node => node.type === "button" && text(node) === label)[0]; }
} finally {
  if (renderer) await act(async () => renderer.unmount());
  for (const [object, key, value] of originals.reverse()) object[key] = value;
  await vite.close();
}
function text(node) { if (typeof node === "string") return node; return (node?.children ?? []).map(text).join(""); }
