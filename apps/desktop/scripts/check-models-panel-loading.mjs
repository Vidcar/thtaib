import assert from "node:assert/strict";
import path from "node:path";
import { fileURLToPath } from "node:url";

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { act, create } from "react-test-renderer";
import { createServer as createViteServer } from "vite";

const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../..");
const desktopRoot = path.join(repoRoot, "apps/desktop");

globalThis.IS_REACT_ACT_ENVIRONMENT = true;
globalThis.window = {
  setTimeout: globalThis.setTimeout.bind(globalThis),
  clearTimeout: globalThis.clearTimeout.bind(globalThis),
  setInterval: globalThis.setInterval.bind(globalThis),
  clearInterval: globalThis.clearInterval.bind(globalThis),
};

const vite = await createViteServer({ root: desktopRoot, appType: "custom", server: { middlewareMode: true, hmr: false }, logLevel: "error" });
try {
  await checkModelPicker((await vite.ssrLoadModule("/src/renderer/ModelPicker.tsx")).ModelPicker);
  await checkVariantPresentation(await vite.ssrLoadModule("/src/renderer/modelVariantPresentation.ts"));
  await checkInstalledConfigurationWarning((await vite.ssrLoadModule("/src/renderer/ImportJobsPanel.tsx")).ImportJobsPanel);
  const { settingValue } = await vite.ssrLoadModule("/src/renderer/effectiveSettings.ts");
  assert.equal(settingValue(0.949999988079071), "0.95", "server float noise should not leak into the settings readout");
  await checkExistingBundleRecipes((await vite.ssrLoadModule("/src/renderer/ModelResponseRecipes.tsx")).ModelResponseRecipes);
  await checkPinnedCardViewer((await vite.ssrLoadModule("/src/renderer/ModelResponseRecipes.tsx")).ModelResponseRecipes);
  await checkPermanentDeletionPreview((await vite.ssrLoadModule("/src/renderer/ModelDeletion.tsx")).ModelDeletion);
  await checkExplicitVisionSelection((await vite.ssrLoadModule("/src/renderer/ModelProjectorControls.tsx")).ModelProjectorControls);
  const { ModelsPanel } = await vite.ssrLoadModule("/src/renderer/ModelsPanel.tsx");
  await checkModelsRenderBeforeDeferredRuntimeAndConfiguration(ModelsPanel);
  for (const pending of ["runtime", "deployments", "profiles", "profiles-failure", "runtime-failure"]) await checkInitialModelDraftOwnership(ModelsPanel, pending);
  await checkRefreshFailureKeepsModelDraft(ModelsPanel);
  await checkSuccessfulEmptyModels(ModelsPanel);
  // Mounted workspace, new lifecycle and import acceptance now live in
  // check-models-workspace.mjs, run by the unified-settings delivery gate.

} finally {
  await vite.close();
}

console.log("Model picker provenance, pinned card, deletion and projector checks passed.");

async function checkModelPicker(ModelPicker) {
  const previousDocument = globalThis.document;
  globalThis.document = { addEventListener() {}, removeEventListener() {} };
  const longName = "Publisher/Qwen3.8-27B-Very-Long-Installed-Model-Name-UD-IQ4_XS";
  const bundles = [bundle("long", longName), bundle("short", "Gemma 4")];
  const chosen = [];
  let renderer;
  try {
    await act(async () => { renderer = create(React.createElement(ModelPicker, { bundles, selectedId: "long", dirtyIds: new Set(["long"]), onSelect: id => chosen.push(id) })); });
    const trigger = renderer.root.findByProps({ className: "model-picker-trigger" });
    assert.equal(textOf(trigger).includes(longName), true, "the full model name remains available to accessibility and title text");
    assert.equal(textOf(trigger).includes("Unsaved"), true);
    await act(async () => trigger.props.onKeyDown({ key: "ArrowDown", preventDefault() {} }));
    const search = renderer.root.findByProps({ "aria-label": "Search installed models" });
    await act(async () => search.props.onChange({ target: { value: "gemma" } }));
    assert.equal(renderer.root.findAllByProps({ role: "option" }).length, 1);
    await act(async () => renderer.root.findByProps({ "aria-label": "Search installed models" }).props.onKeyDown({ key: "Enter", preventDefault() {} }));
    assert.deepEqual(chosen, ["short"], "Enter selects the filtered model");
    assert.equal(renderer.root.findAllByProps({ role: "dialog" }).length, 0, "selection closes the picker");
    await act(async () => renderer.unmount());
    const standard = { ...bundle("standard", "Same GGUF repository"), primary_path: "D:\\Models\\model-IQ4_XS.gguf" };
    const low = { ...bundle("low", "Same GGUF repository"), primary_path: "D:\\Models\\model-LOW-MTP-IQ4_XS.gguf" };
    await act(async () => { renderer = create(React.createElement(ModelPicker, { bundles: [standard, low], selectedId: "standard", dirtyIds: new Set(), onSelect: id => chosen.push(id) })); });
    assert.ok(renderer.root.findByProps({ className: "model-picker-trigger" }).props["aria-label"].includes("Standard · model-IQ4_XS.gguf"), "trigger accessible name identifies the standard file");
    assert.ok(textOf(renderer.root.findByProps({ className: "model-picker-trigger" })).includes("Standard"), "trigger visibly distinguishes the selected file");
    await act(async () => renderer.root.findByProps({ className: "model-picker-trigger" }).props.onClick());
    assert.ok(textOf(renderer.root.findAllByProps({ role: "option" })[1]).includes("LOW-MTP · model-LOW-MTP-IQ4_XS.gguf"), "options identify the low MTP file even when repository names match");
    await act(async () => renderer.root.findByProps({ "aria-label": "Search installed models" }).props.onChange({ target: { value: "low-mtp" } }));
    assert.equal(renderer.root.findAllByProps({ role: "option" }).length, 1, "filename and variant kind are searchable");
    await act(async () => renderer.root.findByProps({ "aria-label": "Search installed models" }).props.onKeyDown({ key: "Enter", preventDefault() {} }));
    assert.deepEqual(chosen, ["short", "low"]);
  } finally { if (renderer) await act(async () => renderer.unmount()); globalThis.document = previousDocument; }
}

async function checkPinnedCardViewer(ModelResponseRecipes) {
  const originalFetch = globalThis.fetch;
  const model = { ...bundle("card-only", "Card without recipes"), source: { kind: "huggingface", repo_id: "org/selected", resolved_revision: "c".repeat(40) },
    huggingface_configuration: { response_recipes: [] } };
  let attempts = 0;
  const calls = [];
  globalThis.fetch = async (url, init = {}) => {
    const address = String(url); calls.push({ address, method: init.method ?? "GET" });
    if (address.endsWith("/model-card")) {
      if (attempts++ === 0) throw new Error("Pinned README unavailable");
      return jsonResponse({ bundle_id: model.id, repo_id: model.source.repo_id, revision: model.source.resolved_revision, sha256: "d".repeat(64), origin: "fetched",
        markdown: "# Selected card\n\n[relative](./guide.md) [outside](../../other/README.md) [unsafe](javascript:alert(1))\n\n![remote image](https://example.com/remote.png)\n\n<script>alert('unsafe')</script>" });
    }
    throw new Error(`unexpected fetch ${address}`);
  };
  let renderer;
  try {
    await act(async () => { renderer = create(React.createElement(ModelResponseRecipes, { bundle: model, profiles: [], onChanged: async () => {} })); });
    assert.equal(calls.length, 0, "model cards load only after opening the viewer");
    assert.ok(renderer.root.findAllByType("a").some(node => node.props.href.endsWith(`/org/selected/blob/${"c".repeat(40)}/README.md`)), "the pinned source link remains available without recipes");
    await act(async () => { renderer.root.findAllByType("button").find(node => textOf(node) === "Show model card").props.onClick(); await tick(); });
    assert.ok(textOf(renderer.root).includes("Model card unavailable: Pinned README unavailable"), "card loading errors are visible");
    await act(async () => { renderer.root.findAllByType("button").find(node => textOf(node) === "Retry card").props.onClick(); await tick(); });
    assert.ok(textOf(renderer.root).includes("Selected card"));
    assert.ok(textOf(renderer.root).includes("Fetched from pinned Hugging Face revision"));
    assert.equal(renderer.root.findAllByType("img").length, 0, "remote Markdown images cannot load");
    assert.equal(renderer.root.findAllByType("script").length, 0, "raw HTML cannot become active content");
    const links = renderer.root.findAllByType("a");
    assert.ok(links.some(node => textOf(node) === "relative" && node.props.href === `https://huggingface.co/org/selected/blob/${"c".repeat(40)}/guide.md`), "relative card links stay on the installed revision");
    assert.ok(!links.some(node => textOf(node) === "outside" || textOf(node) === "unsafe"), "escaped and unsafe links stay inert");
    assert.equal(calls.filter(call => call.method !== "GET").length, 0, "card viewing cannot save configurations or refresh metadata");
  } finally { if (renderer) await act(async () => renderer.unmount()); globalThis.fetch = originalFetch; }
}

async function checkExistingBundleRecipes(ModelResponseRecipes) {
  const originalFetch = globalThis.fetch;
  const calls = [];
  let refreshFailures = 1;
  const model = { ...bundle("bundle-card", "LOW-MTP"), disk_matches: false, source: { kind: "huggingface", repo_id: "org/model", resolved_revision: "a".repeat(40) },
    huggingface_configuration: { response_recipes: [
      { id: "general", name: "General thinking", section: "Suggested settings", per_request: { temperature: 1, min_p: 0 }, reasoning: "on", source_repo_id: "org/model", source_revision: "a".repeat(40), card_sha256: "b".repeat(64) },
      { id: "coding", name: "Precise coding", section: "Coding guidance", per_request: { temperature: 0.6, min_p: 0 }, reasoning: "on", source_repo_id: "org/model", source_revision: "a".repeat(40), card_sha256: "b".repeat(64) },
      { id: "recommended", name: "Recommended response", section: "Recommended settings", per_request: { temperature: 0.7, top_p: 0.9 }, reasoning: "preserve", notes: ["Not copied: Prompt format is guidance only"], source_repo_id: "org/model", source_revision: "a".repeat(40), card_sha256: "b".repeat(64) },
    ] } };
  globalThis.fetch = async (url, init = {}) => {
    calls.push({ address: String(url), body: init.body ? JSON.parse(init.body) : null });
    if (String(url).endsWith("/response-recipes/refresh")) {
      if (refreshFailures-- > 0) throw new Error("pinned card temporarily unavailable");
      return jsonResponse(model);
    }
    if (String(url).endsWith("/response-recipes/configurations")) return jsonResponse({ bundle: model, configurations: [] });
    throw new Error(`unexpected fetch ${String(url)}`);
  };
  let renderer, refreshed = 0;
  try {
    await act(async () => { renderer = create(React.createElement(ModelResponseRecipes, { bundle: model, onChanged: async () => { refreshed++; } })); });
    assert.ok(textOf(renderer.root).includes("Coding guidance"), "each recommendation retains its source section");
    assert.ok(textOf(renderer.root).includes("Thinking unchanged"), "mode-neutral recommendations retain their meaning");
    assert.equal(renderer.root.findAllByType("input").filter(node => node.props.type !== "checkbox").length, 0, "Model card has checked setup choices rather than a duplicate settings editor");
    assert.equal(renderer.root.findAllByType("button").some(node => textOf(node).includes("Create")), false);
    await act(async () => { renderer.root.findAllByType("button").find(node => textOf(node) === "Refresh model card").props.onClick(); await tick(); });
    assert.ok(textOf(renderer.root).includes("Card refresh failed: pinned card temporarily unavailable"));
    assert.equal(refreshed, 0, "failed refresh leaves saved metadata untouched");
    await act(async () => { renderer.root.findAllByType("button").find(node => textOf(node) === "Refresh model card").props.onClick(); await tick(); });
    assert.equal(calls.length, 2);
    assert.ok(calls.every(call => call.address.endsWith("/response-recipes/refresh")), "refresh never downloads weights or creates a configuration");
    assert.equal(refreshed, 1);
    const added = { ...model.huggingface_configuration.response_recipes[0], id: "new-recipe", name: "New recommendation" };
    const updated = { ...model, huggingface_configuration: { response_recipes: [model.huggingface_configuration.response_recipes[1], added] } };
    await act(async () => renderer.update(React.createElement(ModelResponseRecipes, { bundle: updated, onChanged: async () => { refreshed++; } })));
    const choices = renderer.root.findAllByType("input");
    assert.deepEqual(choices.map(node => node.props.checked), [true, false], "removed recipes leave selection and newly discovered recipes stay unchecked");
    await act(async () => { renderer.root.findAllByType("button").find(node => textOf(node) === "Add selected setups").props.onClick(); await tick(); });
    assert.deepEqual(calls.at(-1).body.recipe_ids, ["coding"], "only still-offered checked recipes can be added after metadata refresh");
  } finally { if (renderer) await act(async () => renderer.unmount()); globalThis.fetch = originalFetch; }
}

async function checkInstalledConfigurationWarning(ImportJobsPanel) {
  const opened = [];
  const job = { id: "import", status: "complete", kind: "huggingface", bundle_id: "bundle", error: null, configuration_error: "Could not create the selected recipe", display_name: "LOW-MTP model" };
  let renderer;
  try {
    await act(async () => { renderer = create(React.createElement(ImportJobsPanel, { state: { jobs: [job], error: "", busy: "", action: async () => {}, attentionCount: 1 }, onOpenModel: id => opened.push(id) })); });
    assert.ok(textOf(renderer.root).includes("Installed"), "completed weights remain installed when recipe setup fails");
    assert.ok(textOf(renderer.root).includes("Could not create the selected recipe"), "configuration failure is visible in Downloads");
    assert.ok(!renderer.root.findAllByType("button").some(node => textOf(node) === "Retry"), "configuration failure must not suggest downloading weights again");
    await act(async () => renderer.root.findAllByType("button").find(node => textOf(node) === "Open model recipes").props.onClick());
    assert.deepEqual(opened, ["bundle"]);
  } finally { if (renderer) await act(async () => renderer.unmount()); }
}

async function checkPermanentDeletionPreview(ModelDeletion) {
  const calls = [], deletion = createDeferred();
  let renderer, removed = 0;
  globalThis.fetch = async (url, init = {}) => {
    const address = String(url); calls.push({ address, method: init.method ?? "GET" });
    if (init.method === "DELETE") return deletion.promise;
    return jsonResponse({ id: "bundle", blockers: [], consumers: [], retained: [], removable_bytes: 1024, files: [{ path: "D:\\Original\\model.gguf", removable: true }] });
  };
  try {
    await act(async () => { renderer = create(React.createElement(ModelDeletion, { kind: "bundle", id: "bundle", name: "Saved model", onDeleted: async () => removed++ })); });
    await act(async () => { renderer.root.findAllByType("button").find(node => textOf(node) === "Delete from disk").props.onClick(); await tick(); });
    assert.ok(calls[0].address.endsWith("/bundle/delete-preview?permanent=true"));
    assert.ok(textOf(renderer.root).includes("D:\\Original\\model.gguf"), "permanent preview names original files before committing");
    assert.equal(calls.some(call => call.method === "DELETE"), false, "opening a preview cannot delete files");
    const confirm = renderer.root.findAllByType("button").find(node => textOf(node) === "Permanently delete files");
    await act(async () => { confirm.props.onClick(); confirm.props.onClick(); await tick(); });
    assert.equal(calls.filter(call => call.method === "DELETE").length, 1);
    assert.ok(calls.find(call => call.method === "DELETE").address.endsWith("/bundle?permanent=true"), "confirmation keeps the reviewed permanent-deletion mode");
    await act(async () => { deletion.resolve(jsonResponse({})); await tick(); });
    assert.equal(removed, 1);
  } finally { if (renderer) await act(async () => renderer.unmount()); }
}

async function checkExplicitVisionSelection(ModelProjectorControls) {
  let renderer, selected = null, saved = 0;
  const calls = [];
  globalThis.fetch = async (_url, init = {}) => {
    if (init.method === "PUT") { calls.push(JSON.parse(init.body)); selected = calls.at(-1).path; return jsonResponse({}); }
    return jsonResponse({ bundle_id: "bundle", selected_path: selected, candidates: [{ path: "D:\\Models\\mmproj.gguf", name: "mmproj.gguf", size_bytes: 100, selected: Boolean(selected) }] });
  };
  const props = { bundleId: "bundle", active: false, disabled: false, onSaved: async () => saved++, action: async (_key, operation) => operation() };
  try {
    await act(async () => { renderer = create(React.createElement(ModelProjectorControls, props)); await tick(); });
    assert.equal(renderer.root.findByType("select").props.value, "", "a nearby projector is offered without silently enabling vision");
    await act(async () => renderer.root.findByType("select").props.onChange({ target: { value: "D:\\Models\\mmproj.gguf" } }));
    await act(async () => { renderer.root.findAllByType("button").find(node => textOf(node) === "Save image setup").props.onClick(); await tick(); });
    assert.deepEqual(calls, [{ path: "D:\\Models\\mmproj.gguf" }]);
    assert.equal(saved, 1);
    await act(async () => renderer.update(React.createElement(ModelProjectorControls, { ...props, active: true })));
    assert.equal(renderer.root.findByType("select").props.disabled, true, "active model cannot switch its projector beneath a running deployment");
  } finally { if (renderer) await act(async () => renderer.unmount()); }
}

async function checkVariantPresentation({ presentVariant, variantFamilies }) {
  const variants = [
    { name: "Qwen3.8-27B-UD-IQ2_S.gguf", files: ["a"], size_bytes: 6, complete: true },
    { name: "Qwen3.8-27B-Q4_K_M.gguf", files: ["b", "c"], size_bytes: 15, complete: true },
    { name: "Qwen3.8-27B-BF16.gguf", files: ["d"], size_bytes: 50, complete: true },
    { name: "qwen2.5-0.5b-instruct-fp16.gguf", files: ["f"], size_bytes: 40, complete: true },
    { name: "Qwen3.8-27B-custom.gguf", files: ["e"], size_bytes: null, complete: false },
  ];
  assert.deepEqual(variants.map(presentVariant).map(item => [item.quant, item.family]), [["UD-IQ2_S", "2-bit"], ["Q4_K_M", "4-bit"], ["BF16", "16-bit"], ["FP16", "16-bit"], ["Unknown", "Unknown"]]);
  assert.deepEqual(variantFamilies(variants, "all", "asc").map(group => group.family), ["2-bit", "4-bit", "16-bit", "Unknown"]);
  assert.deepEqual(variantFamilies(variants, 4, "desc").flatMap(group => group.items.map(item => item.quant)), ["Q4_K_M"]);
  assert.deepEqual(["model-IQ4_XS.gguf", "model-LOW-MTP-IQ4_XS.gguf", "model-MTP-IQ4_XS.gguf"].map(name => presentVariant({ name, files: [name], size_bytes: 1, complete: true }).flavour), ["Standard", "LOW-MTP", "MTP"]);
}

function bundle(id, displayName) {
  return {
    id,
    display_name: displayName,
    source: { kind: "local", original_path: "D:\\Models\\qwen.gguf", copied: false },
    files: [{ path: "D:\\Models\\qwen.gguf", name: "qwen.gguf", role: "primary", size_bytes: 1024, sha256: "sha" }],
    companions: [],
    primary_path: "D:\\Models\\qwen.gguf",
    quantization: "GGUF",
    family: "qwen",
    parameter_count: null,
    context_length: 262144,
    created_at: "2026-09-21T00:00:00Z",
    updated_at: "2026-09-21T00:00:00Z",
    managed_root: null,
    disk_matches: true,
  };
}

function runtimeReady() {
  return {
    status: "ready",
    release_tag: "test",
    platform: "windows",
    flavor: "cuda",
    executable: "D:\\Runtime\\llama-server.exe",
    error: null,
  };
}

function configurationOptions() {
  return {
    bundle_id: "bundle_fast",
    context_size: {
      maximum: 262144,
      options: [{ value: 262144, label: "262K" }],
    },
    gpu_layers: {
      maximum: 64,
      options: [{ value: -1, label: "All" }],
    },
    startup_defaults: {
      threads: { applied: -1, default_value: -1, recommended: 8, options: [{ value: -1, label: "Auto" }, ...[8, 16, 32].map(value => ({ value, label: `${value} threads` }))] },
      ...Object.fromEntries(["threads_batch", "spec_draft_threads", "spec_draft_threads_batch", "parallel"].map(key => [key, { applied: -1, default_value: -1, options: [{ value: -1, label: "Auto" }] }])),
      batch_size: { applied: 2048, minimum: 0, options: [] },
      spec_type: { applied: "none", default_value: "none", options: [{ value: "none", label: "Off" }, { value: "draft-mtp", label: "MTP" }] },
      spec_draft_n_max: { applied: 3, default_value: 3, minimum: 0, options: [{ value: 3, label: "3" }, { value: 6, label: "6" }] },
    },
    metadata: { architecture: "qwen", inspection_cached: true },
    per_request_defaults: { reasoning_effort: { applied: "xhigh", default_value: "xhigh", supported: true, options: ["low", "medium", "xhigh"].map(value => ({ value, label: value })) } },
    notes: [],
  };
}

function jsonResponse(body) {
  return {
    ok: true,
    status: 200,
    json: async () => body,
  };
}

async function tick() {
  await new Promise((resolve) => setTimeout(resolve, 0));
}

function textOf(node) {
  if (typeof node === "string") return node;
  if (!node) return "";
  const children = node.children ?? [];
  return children.map(textOf).join("");
}


function createDeferred() { let resolve, reject; const promise = new Promise((yes, no) => { resolve = yes; reject = no; }); return { promise, resolve, reject }; }

function contextInput(renderer, label = "Context") { const input = renderer.root.findAll(node => node.type === "input" && node.props.type === "range" && node.props["aria-label"] === label)[0]; assert.ok(input, "expected " + label); return input; }
function ownerControl(node, name) { while (node && node.type?.name !== name) node = node.parent; assert.ok(node, "expected " + name); return node; }
function changeContext(renderer, value, label = "Context") { ownerControl(contextInput(renderer, label), "ContextSlider").props.onChange(value); }
function resetSetting(renderer, label) { const row = renderer.root.findAll(node => node.type?.name === "SettingRow" && node.props.label === label)[0]; assert.equal(typeof row?.props.onReset, "function"); row.props.onReset(); }

async function checkModelsRenderBeforeDeferredRuntimeAndConfiguration(ModelsPanel) {
  const originalFetch = globalThis.fetch;
  const runtime = createDeferred();
  const configuration = createDeferred();
  const calls = [];
  globalThis.fetch = async (url, init = {}) => {
    const address = String(url);
    calls.push(address);
    if (address.endsWith("/v1/bundles")) {
      return jsonResponse([bundle("bundle_fast", "Qwen existing")]);
    }
    if (address.endsWith("/v1/paths")) {
      return jsonResponse({
        root: "D:\\Data",
        models: "D:\\Data\\models",
        runtimes: "D:\\Data\\runtimes",
        state: "D:\\Data\\state",
        cases: "D:\\Data\\cases",
        snapshots: "D:\\Data\\snapshots",
        workspaces: "D:\\Data\\workspaces",
        knowledge: "D:\\Data\\knowledge",
        logs: "D:\\Data\\logs",
        application_db: "D:\\Data\\application.sqlite",
        checkpoints_db: "D:\\Data\\checkpoints.sqlite",
        windows_layout: "%LOCALAPPDATA%\\LocalAIWorkbench",
      });
    }
    if (address.endsWith("/v1/profiles")) return jsonResponse([]);
    if (address.endsWith("/v1/deployments")) return jsonResponse([]);
    if (address.endsWith("/v1/imports")) return jsonResponse([]);
    if (address.endsWith("/v1/setup-resolution")) return jsonResponse({ configuration: JSON.parse(init.body).overrides, effective_values: {}, instruction_layers: [] });
    if (address.endsWith("/v1/models/storage")) return jsonResponse({ future_install_root: "D:\\Models", locations: [] });
    if (address.endsWith("/projectors")) return jsonResponse({ bundle_id: "bundle_fast", selected_path: null, candidates: [] });
    if (address.endsWith("/v1/runtime/models")) return jsonResponse({ max_loaded_models: 1, loaded_deployment_ids: [], loading_deployment_ids: [], router_status: "stopped" });
    if (address.endsWith("/v1/runtime")) return runtime.promise;
    if (address.includes("/configuration-options")) return configuration.promise;
    throw new Error(`unexpected fetch ${address}`);
  };

  try {
    let renderer;
    await act(async () => {
      renderer = create(React.createElement(ModelsPanel));
      await tick();
    });
    await act(async () => {
      await tick();
    });

    assert.ok(textOf(renderer.root).includes("Qwen existing"), "model library should render as soon as bundles load");
    assert.ok(!textOf(renderer.root).includes("Loading your models"), "library loading copy should not wait for runtime or configuration metadata");
    assert.ok(textOf(renderer.root).includes("Checking local engine"), `runtime state should be pending while /v1/runtime is delayed: ${textOf(renderer.root)}`);
    assert.ok(!textOf(renderer.root).includes("Engine setup required"), "pending runtime must not be shown as missing engine setup");
    assert.ok(!calls.some((call) => call.includes("/configuration-options")), "configuration metadata should wait until deployment runtime data has loaded");

    runtime.resolve(jsonResponse(runtimeReady()));
    await act(async () => {
      await tick();
    });
    assert.ok(calls.some((call) => call.includes("/configuration-options")), "configuration metadata should load after runtime/deployment refresh");
    assert.ok(!textOf(renderer.root).includes("Checking local engine"), "ready runtime clears pending engine copy");

    configuration.resolve(jsonResponse(configurationOptions()));
    await act(async () => {
      await tick();
    });
    assert.equal(ownerControl(contextInput(renderer), "ContextSlider").props.maximum, 262144, "deferred configuration result hydrates the slider's model bound");
    const speculation = renderer.root.findByProps({ id: "model-spec_type", role: "radiogroup" });
    const speculationModes = speculation.findAllByType("input").filter(node => node.props.type === "radio");
    assert.deepEqual(speculationModes.map(option => option.props.value), ["none", "draft-mtp"], "MTP shows actual Off/On values without a duplicate Default");
    assert.deepEqual(speculationModes.filter(option => option.props.checked).map(option => option.props.value), ["none"], "an unset startup control selects the known native Off value");
    await act(async () => { speculationModes.find(option => option.props.value === "draft-mtp").props.onChange(); });
    assert.equal(renderer.root.findAll(node => node.type === "select" && node.props.id === "model-spec_draft_n_max")[0].props.value, "3", "MTP displays its native three-token draft count");
    const thinkingEditor = renderer.root.findAll(node => node.type?.name === "ResponseSettingsEditor")[0];
    assert.deepEqual(thinkingEditor.props.options.per_request_defaults.reasoning_effort.options.map(option => option.value), ["low", "medium", "xhigh"], "the response editor receives actual model-specific Thinking levels");
    assert.equal(renderer.root.findAll(node => node.type === "label" && textOf(node).startsWith("Saved preset")).length, 0, "Models has one configuration editor instead of a second preset selection");
    await act(async () => renderer.unmount());
  } finally {
    globalThis.fetch = originalFetch;
  }
}

async function checkInitialModelDraftOwnership(ModelsPanel, pending) {
  const originalFetch = globalThis.fetch;
  const initial = createDeferred(), metadata = createDeferred(), background = createDeferred(), backgroundRuntime = createDeferred();
  const bag = requested => ({ requested, applied: requested, unsupported: [], retired: [], overridden: [], unverified: [] });
  const models = ["first", "second"].map(id => ({ ...bundle(id, `Model ${id}`), default_configuration_id: `${id}-saved` }));
  let profiles = models.map((model, index) => ({ id: model.default_configuration_id, bundle_id: model.id, display_name: `Saved ${model.id}`, revision: 1,
    bags: { startup: bag({ ctx_size: 8192 + index * 8192 }), per_request: bag({ temperature: index ? 0.6 : 0 }), agent: bag({}) } }));
  let renderer, initialComplete = false, holdBackground = false, failProfiles = pending === "profiles-failure", failRuntime = pending === "runtime-failure";
  const savedRequests = [];
  globalThis.fetch = async (url, init = {}) => {
    const address = String(url), body = init.body ? JSON.parse(init.body) : null;
    if (address.endsWith("/v1/bundles")) return jsonResponse(models);
    if (address.endsWith("/v1/profiles")) {
      if (failProfiles) throw new Error("Initial saved setups unavailable");
      if (!initialComplete && pending === "profiles") return initial.promise;
      if (holdBackground) return background.promise;
      return jsonResponse(profiles);
    }
    if (address.endsWith("/v1/runtime")) {
      if (failRuntime) throw new Error("Initial engine observation unavailable");
      if (holdBackground) return backgroundRuntime.promise;
      return !initialComplete && pending === "runtime" ? initial.promise : jsonResponse(runtimeReady());
    }
    if (address.endsWith("/v1/deployments")) return !initialComplete && pending === "deployments" ? initial.promise : jsonResponse([]);
    if (address.endsWith("/v1/runtime/models")) return jsonResponse({ max_loaded_models: 1, loaded_deployment_ids: [], loading_deployment_ids: [], router_status: "stopped" });
    if (address.endsWith("/v1/imports")) return jsonResponse([]);
    if (address.endsWith("/v1/paths")) return jsonResponse({ models: "D:\\Models" });
    if (address.endsWith("/v1/models/storage")) return jsonResponse({ future_install_root: "D:\\Models", locations: [] });
    if (address.endsWith("/projectors")) return jsonResponse({ selected_path: null, candidates: [] });
    if (address.includes("/configuration-options")) return metadata.promise;
    if (address.endsWith("/v1/setup-resolution")) return jsonResponse({ configuration: body.overrides, effective_values: {}, instruction_layers: [] });
    if (address.endsWith("/v1/settings/preview")) return jsonResponse({ startup: bag(body.startup), per_request: bag(body.per_request), agent: bag(body.agent ?? {}) });
    if (address.endsWith("/configurations")) {
      savedRequests.push(body);
      return { ok: false, status: 409, json: async () => ({ error: "changed elsewhere", code: "configuration_revision_conflict" }) };
    }
    throw new Error(`Unexpected initial ownership request: ${address}`);
  };
  const temperature = () => renderer.root.findAllByType("input").find(node => node.props.id === "model-response-temperature");
  const button = label => renderer.root.findAllByType("button").find(node => textOf(node) === label);
  const chooseModel = async id => act(async () => { renderer.root.findAllByProps({ className: "models-library-row" }).find(node => textOf(node).includes(`Model ${id}`)).props.onClick(); await tick(); });
  const assertDraft = () => {
    assert.equal(temperature().props.value, 0.25, `${pending}: deferred replies retain the edited response`);
    assert.equal(contextInput(renderer).props["data-token-value"], 12288, `${pending}: deferred replies retain the edited context`);
    assert.equal(renderer.root.findByProps({ className: "model-save-state" }).props["data-dirty"], true);
  };
  try {
    await act(async () => { renderer = create(React.createElement(ModelsPanel), { createNodeMock: element => element.type === "form" ? { reportValidity: () => true } : null }); await tick(); });
    assert.ok(textOf(renderer.root).includes("Model first"), "the library is usable before the authoring base arrives");
    if (pending.startsWith("profiles")) {
      assert.equal(Boolean(temperature()), false, "an unknown initial saved setup is not presented as an editable empty draft");
      assert.ok(textOf(renderer.root).includes("Loading saved setup"));
      await chooseModel("second");
      initialComplete = true;
      await act(async () => {
        if (failProfiles) { failProfiles = false; button("Retry").props.onClick(); }
        else initial.resolve(jsonResponse(profiles));
        await tick();
      });
      assert.equal(temperature().props.value, 0.6, "late initial profiles hydrate the currently selected model");
      assert.equal(contextInput(renderer).props["data-token-value"], 16384);
      await chooseModel("first");
    }
    assert.ok(temperature(), "the saved authoring base is available independently from runtime checks");
    assert.equal(temperature().props.disabled, false, "saved setups can be edited while runtime or metadata checks are pending");
    assert.equal(temperature().props.value, 0, "editing starts from the saved authoring base");
    assert.equal(contextInput(renderer).props["data-token-value"], 8192);
    if (["runtime", "deployments"].includes(pending)) assert.equal(textOf(renderer.root.findByProps({ className: "model-runtime-pill" })), "Checking…", "unverified runtime observation cannot assert the model is not loaded");
    await act(async () => { temperature().props.onChange({ target: { value: "0.25" } }); changeContext(renderer, 12288); });
    assertDraft();
    if (failRuntime) {
      assert.equal(textOf(renderer.root.findByProps({ className: "model-runtime-pill" })), "Unavailable", "a failed initial observation must not claim Not loaded");
      await act(async () => { failRuntime = false; button("Retry").props.onClick(); await tick(); });
      assertDraft();
    }
    await chooseModel("second");
    assert.equal(temperature().props.value, 0.6);
    initialComplete = true;
    await act(async () => { initial.resolve(jsonResponse(pending === "runtime" ? runtimeReady() : [])); await tick(); });
    assert.equal(temperature().props.value, 0.6, "late runtime/deployment data cannot restore the previous model's editor");
    await chooseModel("first");
    assertDraft();
    assert.equal(textOf(renderer.root.findByProps({ className: "model-runtime-pill" })), "Not loaded", "a verified empty deployment list can report not loaded");
    const mountedInput = temperature();
    // A background catalogue and descriptor refresh must keep the mounted editor usable.
    holdBackground = true;
    await act(async () => { renderer.update(React.createElement(ModelsPanel, { active: false })); await tick(); });
    await act(async () => { renderer.update(React.createElement(ModelsPanel, { active: true })); await tick(); });
    assert.equal(temperature(), mountedInput, "background checks preserve the field and focus target");
    assert.equal(temperature().props.disabled, false);
    profiles = [{ ...profiles[0], revision: 2, bags: { ...profiles[0].bags, per_request: bag({ temperature: 0.4 }) } }, profiles[1]];
    await act(async () => { background.resolve(jsonResponse(profiles)); backgroundRuntime.reject(new Error("Background engine observation unavailable")); metadata.resolve(jsonResponse({ ...configurationOptions(), bundle_id: "first" })); await tick(); });
    assert.ok(textOf(renderer.root).includes("Background engine observation unavailable"));
    assert.equal(textOf(renderer.root.findByProps({ className: "model-runtime-pill" })), "Not loaded", "failed background checks retain the last verified observation with an error");
    assertDraft();
    await act(async () => { renderer.root.findByProps({ id: "model-settings-form" }).props.onSubmit({ preventDefault() {} }); await tick(); });
    assert.equal(savedRequests.length, 1);
    assert.equal(savedRequests[0].configuration_id, "first-saved");
    assert.equal(savedRequests[0].expected_revision, 1, "the initial authoring revision survives all later observations");
    assert.equal(savedRequests[0].per_request.temperature, 0.25);
    assert.equal(savedRequests[0].startup.ctx_size, 12288);
    assert.ok(textOf(renderer.root).includes("changed elsewhere"));
    assertDraft();
    await act(async () => setupAction(renderer, "Revert edits"));
    assert.equal(temperature().props.value, 0.4, "explicit revert adopts the latest saved setup");
  } finally {
    initial.resolve(jsonResponse([])); background.resolve(jsonResponse(profiles)); backgroundRuntime.resolve(jsonResponse(runtimeReady())); metadata.resolve(jsonResponse(configurationOptions()));
    if (renderer) await act(async () => renderer.unmount());
    globalThis.fetch = originalFetch;
  }
}

async function checkSuccessfulEmptyModels(ModelsPanel) {
  const originalFetch = globalThis.fetch;
  let renderer;
  globalThis.fetch = async (url) => {
    const address = String(url);
    if (address.endsWith("/v1/bundles") || address.endsWith("/v1/profiles")) return jsonResponse([]);
    throw new Error(`Unexpected empty catalogue request: ${address}`);
  };
  try {
    await act(async () => { renderer = create(React.createElement(ModelsPanel)); await tick(); });
    const hint = renderer.root.findByProps({ className: "models-library-list" }).findAll((node) => node.type === "p" && node.props.className === "hint");
    assert.equal(hint.length, 1, "a successful empty catalogue has one hint");
    assert.equal(textOf(hint[0]), "No models");
    const empty = renderer.root.findByProps({ id: "models-panel-library" }).findAll((node) => node.props?.className === "empty-state");
    assert.equal(empty.length, 1, "a successful empty library has one editor empty state");
    assert.equal(textOf(empty[0].findByType("h3")), "No models");
    const visible = textOf(renderer.root);
    assert.equal(visible.includes("Add a model to get started"), false);
    assert.equal(visible.includes("Your first model starts here"), false);
    assert.equal(visible.includes("No matching models"), false);
    assert.equal(visible.includes("Loading your models"), false);
  } finally {
    if (renderer) await act(async () => renderer.unmount());
    globalThis.fetch = originalFetch;
  }
}

async function checkRefreshFailureKeepsModelDraft(ModelsPanel) {
  const originalFetch = globalThis.fetch;
  const bag = requested => ({ requested, applied: requested, unsupported: [], retired: [], overridden: [], unverified: [] });
  const model = { ...bundle("draft-model", "Draft model"), default_configuration_id: "draft-default" };
  let profiles = [{ id: "draft-default", bundle_id: model.id, display_name: "Default", revision: 1, bags: { startup: bag({ ctx_size: 8192 }), per_request: bag({ temperature: 0.5 }), agent: bag({ system_prompt: "Saved model instructions" }) } }];
  let failure = "", catalogue = [model], renderer;
  const savedRequests = [];
  globalThis.fetch = async (url, init = {}) => {
    const address = String(url), body = init.body ? JSON.parse(init.body) : null;
    if (address.endsWith("/v1/bundles")) {
      if (failure === "bundles") throw new Error("Model refresh connection failed");
      return jsonResponse(catalogue);
    }
    if (address.endsWith("/v1/profiles")) {
      if (failure === "profiles") throw new Error("Model configurations temporarily unavailable");
      return jsonResponse(profiles);
    }
    if (address.endsWith("/v1/runtime")) return jsonResponse(runtimeReady());
    if (address.endsWith("/v1/runtime/models")) return jsonResponse({ max_loaded_models: 1, loaded_deployment_ids: [], loading_deployment_ids: [], router_status: "stopped" });
    if (["/v1/deployments", "/v1/imports"].some(suffix => address.endsWith(suffix))) return jsonResponse([]);
    if (address.endsWith("/v1/paths")) return jsonResponse({ models: "D:\\Models" });
    if (address.endsWith("/v1/models/storage")) return jsonResponse({ future_install_root: "D:\\Models", locations: [] });
    if (address.includes("/configuration-options")) return jsonResponse(configurationOptions());
    if (address.endsWith("/projectors")) return jsonResponse({ selected_path: null, candidates: [] });
    if (address.endsWith("/v1/setup-resolution")) return jsonResponse({ configuration: body.overrides, effective_values: {}, instruction_layers: [] });
    if (address.endsWith("/v1/settings/preview")) return jsonResponse({ startup: bag(body.startup), per_request: bag(body.per_request), agent: bag(body.agent ?? {}) });
    if (address.endsWith("/configurations")) {
      savedRequests.push(body);
      assert.equal(body.configuration_id, "draft-default");
      assert.equal(body.expected_revision, profiles[0].revision, "recovered save retains the current configuration revision");
      profiles = [{ ...profiles[0], display_name: body.display_name, revision: profiles[0].revision + 1, bags: { startup: bag(body.startup), per_request: bag(body.per_request), agent: bag(body.agent ?? {}) } }];
      return jsonResponse(profiles[0]);
    }
    throw new Error(`Unexpected model draft request: ${address}`);
  };
  const context = () => contextInput(renderer);
  const temperature = () => renderer.root.findAllByType("input").find(node => node.props.id === "model-response-temperature");
  const button = label => renderer.root.findAllByType("button").find(node => textOf(node) === label);
  try {
    await act(async () => { renderer = create(React.createElement(ModelsPanel), { createNodeMock: element => element.type === "form" ? { reportValidity: () => true } : null }); await tick(); });
    assert.equal(context().props["data-token-value"], 8192);
    assert.equal(renderer.root.findByProps({ id: "model-authored-instructions" }).props.value, "Saved model instructions");
    await act(async () => {
      changeContext(renderer, 16384);
      temperature().props.onChange({ target: { value: "0.7" } });
      renderer.root.findByProps({ id: "model-authored-instructions" }).props.onChange({ target: { value: "Full edited model instructions\nKeep the user's wording." } });
      await tick();
    });
    await act(async () => { renderer.update(React.createElement(ModelsPanel, { active: false })); await tick(); });
    failure = "bundles";
    await act(async () => { renderer.update(React.createElement(ModelsPanel, { active: true })); await tick(); });
    assert.ok(textOf(renderer.root).includes("Model refresh connection failed"));
    assert.ok(button("Retry"), "a refresh failure offers an explicit retry beside the retained editor");
    assert.equal(context().props["data-token-value"], 16384, "failed refresh never unmounts the visited editor or discards its startup draft");
    assert.equal(temperature().props.value, 0.7, "response draft also survives failed re-entry");
    assert.equal(renderer.root.findByProps({ id: "model-authored-instructions" }).props.value, "Full edited model instructions\nKeep the user's wording.", "optional model instruction edits survive failed editor re-entry");
    failure = "";
    await act(async () => { button("Retry").props.onClick(); await tick(); });
    assert.equal(button("Retry"), undefined, "successful retry clears the connection notice");
    assert.equal(context().props["data-token-value"], 16384, "successful retry keeps the unsaved edit rather than restoring saved values");

    await act(async () => { renderer.update(React.createElement(ModelsPanel, { active: false })); await tick(); });
    failure = "profiles";
    catalogue = [bundle("partial-replacement", "Incomplete refresh")];
    await act(async () => { renderer.update(React.createElement(ModelsPanel, { active: true })); await tick(); });
    assert.ok(textOf(renderer.root).includes("Model configurations temporarily unavailable"));
    assert.ok(textOf(renderer.root.findByProps({ "aria-label": "Selected model" })).includes("Draft model"), "partial refresh failure retains the last complete catalogue and selection");
    assert.equal(context().props["data-token-value"], 16384);
    failure = "";
    catalogue = [model];
    assert.equal(button("Save").props.type, "submit", "sticky Save submits the single settings form");
    await act(async () => { renderer.root.findByProps({ id: "model-settings-form" }).props.onSubmit({ preventDefault() {} }); await tick(); });
    assert.equal(savedRequests.length, 1, "a retained editor can save as soon as the connection recovers");
    assert.equal(savedRequests[0].startup.ctx_size, 16384);
    assert.equal(savedRequests[0].per_request.temperature, 0.7);
    assert.equal(savedRequests[0].display_name, "Default");
    assert.equal(savedRequests[0].agent.system_prompt, "Full edited model instructions\nKeep the user's wording.", "saved text reaches only its model agent bag");
    assert.equal(button("Retry"), undefined, "save refresh clears the earlier catalogue error");
    assert.equal(renderer.root.findByProps({ className: "model-save-state" }).props["data-dirty"], false);
    assert.ok(textOf(renderer.root).includes("Saved"));

    await act(async () => resetSetting(renderer, "Instructions"));
    assert.equal(renderer.root.findByProps({ id: "model-authored-instructions" }).props.value, "");
    await act(async () => { renderer.root.findByProps({ id: "model-settings-form" }).props.onSubmit({ preventDefault() {} }); await tick(); });
    assert.equal(savedRequests.length, 2);
    assert.deepEqual(savedRequests[1].agent, {}, "Reset removes only optional model guidance");
    assert.equal(savedRequests[1].startup.ctx_size, 16384); assert.equal(savedRequests[1].per_request.temperature, 0.7, "reset retains other saved settings");

    await act(async () => renderer.unmount());
    failure = "bundles";
    await act(async () => { renderer = create(React.createElement(ModelsPanel)); await tick(); });
    assert.ok(textOf(renderer.root).includes("Model refresh connection failed"), "initial failure still exposes its retry notice");
    assert.ok(!textOf(renderer.root).includes("No models"), "failed loading does not imply the user's model catalogue is empty");
    assert.ok(!textOf(renderer.root).includes("No matching models"), "failed loading does not imply a search miss");
    assert.ok(textOf(renderer.root).includes("Model library unavailable."), "failed loading names the library as unavailable");
    failure = "";
    await act(async () => { button("Retry").props.onClick(); await tick(); });
    assert.equal(context().props["data-token-value"], 16384, "initial-error recovery loads the saved configuration");
  } finally {
    if (renderer) await act(async () => renderer.unmount());
    globalThis.fetch = originalFetch;
  }
}


function setupAction(renderer, label) { const menu = renderer.root.findAll(node => node.type?.name === "MenuPopover" && node.props.label === "Setup actions")[0]; const action = menu.props.children(() => {}).props.children.find(node => node?.props?.children === label); assert.ok(action, label); action.props.onClick(); }
