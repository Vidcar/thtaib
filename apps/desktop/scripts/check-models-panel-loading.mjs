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
  const { ModelsPanel } = await vite.ssrLoadModule("/src/renderer/ModelsPanel.tsx");
  const { DeploymentsPanel } = await vite.ssrLoadModule("/src/renderer/DeploymentsPanel.tsx");
  const { ModelPresetPanel } = await vite.ssrLoadModule("/src/renderer/ModelPresetPanel.tsx");
  await checkModelPicker((await vite.ssrLoadModule("/src/renderer/ModelPicker.tsx")).ModelPicker);
  await checkVariantPresentation(await vite.ssrLoadModule("/src/renderer/modelVariantPresentation.ts"));
  await checkFileLinkAndRecipes((await vite.ssrLoadModule("/src/renderer/HuggingFaceImport.tsx")).HuggingFaceImport);
  await checkInstalledConfigurationWarning((await vite.ssrLoadModule("/src/renderer/ImportJobsPanel.tsx")).ImportJobsPanel);
  const { settingValue } = await vite.ssrLoadModule("/src/renderer/effectiveSettings.ts");
  assert.equal(settingValue(0.949999988079071), "0.95", "server float noise should not leak into the settings readout");
  await checkModelsRenderBeforeDeferredRuntimeAndConfiguration(ModelsPanel);
  await checkRefreshFailureKeepsModelDraft(ModelsPanel);
  await checkSavedLoadingRetainsRunningModel(DeploymentsPanel);
  await checkDraftRevisionConflicts(DeploymentsPanel);
  await checkExistingBundleRecipes((await vite.ssrLoadModule("/src/renderer/ModelResponseRecipes.tsx")).ModelResponseRecipes);
  await checkPinnedCardViewer((await vite.ssrLoadModule("/src/renderer/ModelResponseRecipes.tsx")).ModelResponseRecipes);
  await checkModelPresetDraftAndVisibility(ModelPresetPanel);
  await checkPresetLateModelOwnership(ModelPresetPanel);
  await checkSelectedModelOwnsDetails(ModelsPanel, DeploymentsPanel);
  await checkCardViewerAndLateRefreshRetainNewSelection(ModelsPanel);
  await checkRepositorySelectionLoadsFiles(ModelsPanel);
  await checkRepositoryChoicesAndLateResults((await vite.ssrLoadModule("/src/renderer/HuggingFaceImport.tsx")).HuggingFaceImport);
  await checkReviewOffersBuiltinMtp((await vite.ssrLoadModule("/src/renderer/HuggingFaceImport.tsx")).HuggingFaceImport);
  await checkPermanentDeletionPreview((await vite.ssrLoadModule("/src/renderer/ModelDeletion.tsx")).ModelDeletion);
  await checkSavedCapabilities((await vite.ssrLoadModule("/src/renderer/ModelCapabilities.tsx")).ModelCapabilities);
  await checkExplicitVisionSelection((await vite.ssrLoadModule("/src/renderer/ModelProjectorControls.tsx")).ModelProjectorControls);
} finally {
  await vite.close();
}

console.log("Models loading, contextual details, preset drafts/visibility and late-result ownership checks passed.");

function contextInput(renderer, label = "Context") { const input = renderer.root.findAll(node => node.type === "input" && node.props.type === "range" && node.props["aria-label"] === label)[0]; assert.ok(input, "expected " + label); return input; }
function ownerControl(node, name) { while (node && node.type?.name !== name) node = node.parent; assert.ok(node, "expected " + name); return node; }
function changeContext(renderer, value, label = "Context") { ownerControl(contextInput(renderer, label), "ContextSlider").props.onChange(value); }
function resetSetting(renderer, label) { const row = renderer.root.findAll(node => node.type?.name === "SettingRow" && node.props.label === label)[0]; assert.equal(typeof row?.props.onReset, "function"); row.props.onReset(); }

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

async function checkSelectedModelOwnsDetails(ModelsPanel, DeploymentsPanel) {
  const originalFetch = globalThis.fetch;
  let renderer;
  const deployment = { id: "gemma-live", bundle_id: "gemma", profile_id: "gemma-default", display_name: "managed:Gemma", scope: "managed", status: "running", health: { healthy: true }, applied_startup: {}, endpoint: "http://localhost:8080/v1" };
  const gemmaProfile = { id: "gemma-default", bundle_id: "gemma", display_name: "Default", revision: 1, bags: { startup: { requested: {} }, per_request: { requested: {} }, agent: { requested: {} } } };
  const models = [bundle("qwen", "Selected Qwen"), { ...bundle("gemma", "Loaded Gemma"), default_configuration_id: "gemma-default" }];
  globalThis.fetch = async (url, init = {}) => {
    const address = String(url), body = init.body ? JSON.parse(init.body) : null;
    if (address.endsWith("/v1/bundles")) return jsonResponse(models);
    if (address.endsWith("/v1/deployments")) return jsonResponse([deployment]);
    if (address.endsWith("/v1/profiles")) return jsonResponse([gemmaProfile]);
    if (address.endsWith("/v1/setup-resolution")) return jsonResponse({ configuration: { ...body.overrides, deployment_id: body.overrides.model_configuration_id === "gemma-default" ? "gemma-live" : null }, effective_values: {}, instruction_layers: [] });
    if (address.endsWith("/v1/imports")) return jsonResponse([]);
    if (address.endsWith("/v1/paths")) return jsonResponse({ models: "D:\\Models" });
    if (address.endsWith("/v1/runtime/models")) return jsonResponse({ max_loaded_models: 1, loaded_deployment_ids: [], loading_deployment_ids: [], router_status: "stopped" });
    if (address.endsWith("/v1/runtime")) return jsonResponse(runtimeReady());
    if (address.includes("/configuration-options")) return jsonResponse(configurationOptions());
    if (address.endsWith("/projectors")) return jsonResponse({ selected_path: null, candidates: [] });
    if (address.endsWith("/probes")) return jsonResponse({ evidence: [], current_support: {}, current_fingerprint: "now", image_setup: {} });
    if (address.endsWith("/v1/models/storage")) return jsonResponse({ future_install_root: "D:\\Models", locations: [] });
    throw new Error(`unexpected fetch ${address}`);
  };
  try {
    await act(async () => { renderer = create(React.createElement(ModelsPanel)); await tick(); });
    assert.equal(renderer.root.findAll(node => node.type?.name === "ModelCapabilities").length, 0, "another loaded model must not occupy the selected model's detailed controls");
    assert.equal(textOf(renderer.root.findByProps({ "aria-label": "Selected model" })).includes("Selected Qwen"), true);
    assert.equal(renderer.root.findAllByProps({ "aria-label": "Other active models" }).length, 0, "runtime details have one contextual owner instead of another main-page strip");
    await act(async () => renderer.root.findAllByType("button").find(node => textOf(node) === "Model card").props.onClick());
    assert.equal(renderer.root.find(node => node.type?.name === "ModelInspector").props.view, "presets", "the header opens the selected model's presets");
    await act(async () => renderer.root.findAllByType("button").find(node => textOf(node) === "Files & model information").props.onClick());
    assert.ok(renderer.root.findByProps({ "aria-label": "Model files, source and metadata" }), "Files opens the information panel");
    await act(async () => renderer.root.findByProps({ "aria-label": "Loaded model details" }).props.onClick());
    assert.equal(renderer.root.find(node => node.type?.name === "ModelInspector").props.view, "runtime", "the loaded-state action opens runtime diagnostics in the shared inspector");
    await act(async () => renderer.root.findAllByProps({ className: "catalogue-row" }).find(node => textOf(node).includes("Loaded Gemma")).props.onClick());
    assert.equal(textOf(renderer.root.findByProps({ "aria-label": "Selected model" })).includes("Loaded Gemma"), true, "the catalogue chooses the detailed model");
    assert.equal(renderer.root.find(node => node.type?.name === "ModelInspector").props.view, null, "a model switch dismisses the previous model's inspector");
    assert.equal(renderer.root.findAll(node => node.type?.name === "ModelCapabilities").length, 0, "runtime capabilities stay out of the central editor");

    await act(async () => renderer.unmount());
    await act(async () => { renderer = create(React.createElement(DeploymentsPanel, { selectedBundleId: "gemma", initialBundles: models, initialProfiles: [gemmaProfile] })); await tick(); });
    await act(async () => renderer.root.findByProps({ "aria-label": "Loaded model details" }).props.onClick());
    assert.deepEqual(renderer.root.findAll(node => node.type?.name === "ModelCapabilities").map(node => node.props.deployment.id), ["gemma-live"], "opening the selected model's runtime details restores its own persisted probes");
    assert.ok(textOf(renderer.root).includes("Selected model loads"));
  } finally { if (renderer) await act(async () => renderer.unmount()); globalThis.fetch = originalFetch; }
}

async function checkSavedLoadingRetainsRunningModel(Panel) {
  const originalFetch = globalThis.fetch;
  const bag = requested => ({ requested, applied: requested, unsupported: [], retired: [], overridden: [], unverified: [] });
  const model = { ...bundle("stock-qwen", "Stock Qwen"), default_configuration_id: "stock-default", huggingface_configuration: {
    source_repo_id: "publisher/qwen", source_revision: "revision-test", response_recipes: [{ id: "publisher-sampling", name: "Publisher sampling", reasoning: "preserve", per_request: { temperature: 1, top_p: 0.95 }, source_repo_id: "publisher/qwen", source_revision: "revision-test", card_sha256: "hash", section: "Sampling" }],
  } };
  let profiles = [{ id: "stock-default", bundle_id: model.id, display_name: "Stock", revision: 1, bags: { startup: bag({ ctx_size: 32768 }), per_request: bag({ temperature: 1 }), agent: bag({}) } }];
  const deployment = (id, context, updated, status = "running", profile = "stock-default") => ({ id, bundle_id: model.id, profile_id: profile, display_name: id, scope: "managed", status, pid: context, updated_at: `2026-09-29T${updated}:00:00Z`, health: { healthy: status === "running" }, applied_startup: { ctx_size: context }, server_props: { n_ctx: context, total_slots: 1 }, endpoint: `http://localhost:${context}/v1` });
  const originalRunning = deployment("loaded-32768", 32768, "10");
  let deployments = [
    deployment("earlier-healthy", 24576, "09"),
    deployment("wrong-configuration", 131072, "16", "running", "other-default"),
    deployment("loaded-46080", 46080, "15", "stopped"),
    deployment("later-failed", 65536, "14", "failed"),
    deployment("later-unhealthy", 65536, "13", "unhealthy"),
    originalRunning,
  ];
  const calls = [];
  let renderer, rejectSave = false;
  const panel = () => React.createElement(Panel, { selectedBundleId: model.id, initialBundles: [model], initialProfiles: profiles, onBundlesChanged: async () => renderer.update(panel()) });
  globalThis.fetch = async (url, init = {}) => {
    const address = String(url), body = init.body ? JSON.parse(init.body) : null;
    calls.push({ address, body });
    if (address.endsWith("/v1/runtime")) return jsonResponse(runtimeReady());
    if (address.endsWith("/v1/deployments")) return jsonResponse(deployments);
    if (address.endsWith("/v1/setup-resolution")) {
      const context = body.overrides.startup_overrides?.ctx_size ?? profiles[0].bags.startup.requested.ctx_size;
      return jsonResponse({ configuration: { ...body.overrides, deployment_id: `loaded-${context}` }, effective_values: { "startup.ctx_size": { value: context, known: true, source: "Configuration: Stock", default_value: 32768, default_source: "pinned_runtime_default" } }, instruction_layers: [] });
    }
    if (address.includes("/configuration-options")) return jsonResponse({ ...configurationOptions(), bundle_id: model.id });
    if (address.endsWith("/v1/settings/preview")) return jsonResponse({ startup: bag(body.startup), per_request: bag(body.per_request), agent: bag(body.agent ?? {}) });
    if (address.endsWith("/configurations")) {
      if (rejectSave) throw new Error("Save temporarily unavailable");
      profiles = [{ ...profiles[0], revision: profiles[0].revision + 1, bags: { startup: bag(body.startup), per_request: bag(body.per_request), agent: bag(body.agent ?? {}) }, recipe_origin: body.recipe_origin ?? null }];
      return jsonResponse(profiles[0]);
    }
    if (address.endsWith("/v1/deployments/managed")) {
      assert.equal(body.profile_id, profiles[0].id);
      const context = profiles[0].bags.startup.requested.ctx_size;
      const loaded = deployment(`loaded-${context}`, context, "11");
      deployments = [deployment("newer-healthy-snapshot", 98304, "17"), ...deployments.filter(item => item.id !== loaded.id).map(item => item.id === originalRunning.id ? { ...item, status: "stopped" } : item), loaded];
      return jsonResponse(loaded);
    }
    if (address.endsWith("/v1/hardware/estimate")) return jsonResponse({ completeness: "unavailable", reasons: [], unknown_costs: [], gpu: {}, ram: {}, components: [], devices: [] });
    throw new Error(`Unexpected saved-loading request ${address}`);
  };
  const button = label => renderer.root.findAllByType("button").find(node => textOf(node) === label);
  const readiness = () => textOf(renderer.root.findByProps({ "aria-label": "Loaded model details" }));
  const toolbar = () => textOf(renderer.root.findByProps({ className: "model-toolbar-status" }));
  const temperature = () => renderer.root.findAllByType("input").find(node => node.props.id === "model-response-temperature");
  const contextRow = () => renderer.root.findAll(node => node.type?.name === "SettingRow" && node.props.label === "Context")[0];
  const save = async () => act(async () => { renderer.root.findByProps({ id: "model-settings-form" }).props.onSubmit({ preventDefault() {} }); await tick(); });
  try {
    await act(async () => { renderer = create(panel(), { createNodeMock: element => element.type === "form" ? { reportValidity: () => true } : null }); await tick(); });
    const range = contextInput(renderer);
    const cpuThreads = renderer.root.findAllByType("select").find(node => node.props.id === "model-threads");
    for (const key of ["threads", "threads_batch", "spec_draft_threads", "spec_draft_threads_batch", "parallel"]) {
      const control = renderer.root.findAllByType("select").find(node => node.props.id === `model-${key}`);
      assert.ok(control, `${key} keeps its named native mode after descriptor loading`);
      assert.equal(control.props.value, "-1");
      assert.equal(textOf(control.findAllByType("option").find(node => node.props.value === "-1")), "Auto");
      assert.equal(Object.hasOwn(profiles[0].bags.startup.requested, key), false, "viewing Auto does not materialize inherited loading settings");
    }
    for (const label of ["Prompt batch size", "Draft tokens"]) {
      const row = renderer.root.findAll(node => node.type?.name === "SettingRow" && node.props.label === label)[0];
      assert.equal(row.findAllByType("input").find(node => node.props.type === "number").props.min, 0, "descriptor minimum zero wins for ordinary numeric counts");
    }
    assert.equal(readiness(), "Ready"); assert.ok(button("Load")); assert.ok(button("Reload"));
    await act(async () => { changeContext(renderer, 46080); await tick(); });
    assert.equal(contextInput(renderer), range, "Context editing retains the mounted range");
    assert.equal(readiness(), "Ready"); assert.ok(button("Load saved"));
    assert.match(contextRow().props.hint.props.children.join(""), /Loaded per request: 32k tokens/);
    await save();
    assert.equal(profiles[0].bags.startup.requested.ctx_size, 46080);
    assert.equal(contextInput(renderer), range, "Save retains the editor and focus target");
    assert.equal(renderer.root.findAllByType("select").find(node => node.props.id === "model-threads"), cpuThreads, "descriptor refresh preserves the mounted Auto selector");
    assert.equal(range.props["data-token-value"], 46080);
    assert.equal(readiness(), "Ready", "saving future loading settings keeps the current model's healthy state");
    assert.ok(button("Load"), "saved loading changes retain an explicit Load action");
    assert.ok(button("Reload"), "a running record keeps a separate Reload");
    assert.match(contextRow().props.hint.props.children.join(""), /Loaded per request: 32k tokens/, "loaded Context remains distinct from saved Context until reload");
    assert.equal(originalRunning.pid, 32768);
    assert.equal(calls.filter(call => call.address.endsWith("/v1/deployments/managed")).length, 0, "Save never starts or replaces a child process");
    assert.equal(calls.filter(call => call.address.includes("/configuration-options")).at(-1).body.deployment_id, originalRunning.id, "metadata stays attributed to the actual running child");
    assert.equal(toolbar(), "Saved.");

    await act(async () => temperature().props.onChange({ target: { value: "0.7" } }));
    assert.equal(renderer.root.findByProps({ className: "model-edit-state" }).props["data-dirty"], true);
    assert.ok(!toolbar().includes("Saved"), "response edits clear the previous save confirmation");
    await save();
    assert.equal(toolbar(), "Saved.");
    await act(async () => renderer.root.findByProps({ id: "model-authored-instructions" }).props.onChange({ target: { value: "Use this instruction" } }));
    assert.ok(!toolbar().includes("Saved"), "instruction edits clear the previous save confirmation");
    await save();
    await act(async () => button("Model card").props.onClick());
    await act(async () => button("Apply to draft").props.onClick());
    assert.equal(renderer.root.findByProps({ className: "model-edit-state" }).props["data-dirty"], true);
    assert.ok(!toolbar().includes("Saved"), "applying a preset clears the previous save confirmation");
    rejectSave = true;
    await save();
    assert.match(toolbar(), /Save temporarily unavailable/);
    await act(async () => temperature().props.onChange({ target: { value: "0.8" } }));
    assert.match(toolbar(), /Save temporarily unavailable/, "editing keeps actionable errors visible");
    await act(async () => button("Revert edits").props.onClick());
    await act(async () => { button("Load").props.onClick(); await tick(); });
    assert.equal(calls.filter(call => call.address.endsWith("/v1/deployments/managed")).length, 1, "only explicit Load starts the saved setup");
    assert.equal(calls.filter(call => call.address.includes("/configuration-options")).at(-1).body.deployment_id, "loaded-46080", "exact desired residency wins over a newer historical configuration instance");
    assert.equal(readiness(), "Ready"); assert.equal(contextRow().props.hint, undefined, "loaded and saved Context agree after explicit reload");
  } finally { if (renderer) await act(async () => renderer.unmount()); globalThis.fetch = originalFetch; }
}

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
      renderer.root.findByProps({ id: "model-configuration-name" }).props.onChange({ target: { value: "My draft" } });
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
    assert.equal(renderer.root.findByProps({ id: "model-configuration-name" }).props.value, "My draft");
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
    assert.equal(savedRequests[0].display_name, "My draft");
    assert.equal(savedRequests[0].agent.system_prompt, "Full edited model instructions\nKeep the user's wording.", "saved text reaches only its model agent bag");
    assert.equal(button("Retry"), undefined, "save refresh clears the earlier catalogue error");
    assert.equal(renderer.root.findByProps({ className: "model-edit-state" }).props["data-dirty"], false);
    assert.ok(textOf(renderer.root).includes("Saved"));

    await act(async () => resetSetting(renderer, "Model instructions"));
    assert.equal(renderer.root.findByProps({ id: "model-authored-instructions" }).props.value, "");
    await act(async () => { renderer.root.findByProps({ id: "model-settings-form" }).props.onSubmit({ preventDefault() {} }); await tick(); });
    assert.equal(savedRequests.length, 2);
    assert.deepEqual(savedRequests[1].agent, {}, "Reset removes only optional model guidance");
    assert.equal(savedRequests[1].startup.ctx_size, 16384); assert.equal(savedRequests[1].per_request.temperature, 0.7, "reset retains other saved settings");

    await act(async () => renderer.unmount());
    failure = "bundles";
    await act(async () => { renderer = create(React.createElement(ModelsPanel)); await tick(); });
    assert.ok(textOf(renderer.root).includes("Model refresh connection failed"), "initial failure still exposes its retry notice");
    assert.ok(!textOf(renderer.root).includes("Your first model starts here"), "failed loading does not imply the user's model catalogue is empty");
    failure = "";
    await act(async () => { button("Retry").props.onClick(); await tick(); });
    assert.equal(context().props["data-token-value"], 16384, "initial-error recovery loads the saved configuration");
  } finally {
    if (renderer) await act(async () => renderer.unmount());
    globalThis.fetch = originalFetch;
  }
}

async function checkRepositoryChoicesAndLateResults(HuggingFaceImport) {
  const first = createDeferred(), second = createDeferred(), downloads = [];
  let inspections = 0, completions = 0, renderer;
  globalThis.fetch = async (url, init = {}) => {
    const address = String(url);
    if (address.includes("/huggingface/search?")) return jsonResponse([{ repo_id: "org/first", downloads: 1 }, { repo_id: "org/second", downloads: 2 }]);
    if (address.endsWith("/huggingface/inspect")) { inspections++; return inspections === 1 ? first.promise : second.promise; }
    if (address.endsWith("/imports/huggingface")) { downloads.push(JSON.parse(init.body)); return jsonResponse({ id: "import", status: "running", bundle_id: null }); }
    throw new Error(`unexpected fetch ${address}`);
  };
  try {
    await act(async () => { renderer = create(React.createElement(HuggingFaceImport, { onStarted: async () => completions++ })); });
    await act(async () => renderer.root.findByType("input").props.onChange({ target: { value: "model" } }));
    await act(async () => { renderer.root.findByType("form").props.onSubmit({ preventDefault() {} }); await tick(); });
    const choices = renderer.root.findAllByType("button").filter(node => textOf(node) === "Select repository");
    await act(async () => { choices[0].props.onClick(); await tick(); });
    await act(async () => { choices[1].props.onClick(); await tick(); });
    const repository = { repo_id: "org/second", resolved_revision: "pinned-revision", variants: [{ name: "Q4", complete: true, files: ["weights[4].gguf"], size_bytes: 100 }], projectors: [{ name: "vision", files: ["mmproj.gguf"], complete: true, size_bytes: 30 }], guidance_files: ["README.md"], warnings: [] };
    await act(async () => { second.resolve(jsonResponse(repository)); await tick(); });
    await act(async () => { first.resolve(jsonResponse({ ...repository, repo_id: "org/first", variants: [] })); await tick(); });
    assert.ok(textOf(renderer.root.findByProps({ "aria-label": "Repository files" })).includes("org/second"), "late first selection cannot replace the latest repository files");
    let review = renderer.root.findAllByType("button").find(node => textOf(node) === "Review download");
    assert.equal(review.props.disabled, true, "a repository offering vision requires an explicit vision or text-only choice");
    await act(async () => renderer.root.findAllByType("input").find(node => node.props.name === "image-input" && node.props.value === "vision").props.onChange());
    review = renderer.root.findAllByType("button").find(node => textOf(node) === "Review download");
    await act(async () => review.props.onClick());
    let download = renderer.root.findAllByType("button").find(node => textOf(node) === "Download model");
    await act(async () => { download.props.onClick(); download.props.onClick(); await tick(); });
    assert.deepEqual(downloads, [{ repo_id: "org/second", revision: "pinned-revision", allow_patterns: ["weights[[]4].gguf", "mmproj.gguf", "README.md"], recipe_ids: [], default_recipe_id: null, initial_startup: {} }], "an untouched review downloads the selected files without inventing context or GPU flags");
    assert.equal(completions, 1);
  } finally { if (renderer) await act(async () => renderer.unmount()); }
}

async function checkCardViewerAndLateRefreshRetainNewSelection(ModelsPanel) {
  const originalFetch = globalThis.fetch;
  const pendingView = createDeferred();
  const card = (model, markdown) => ({ bundle_id: model.id, repo_id: model.source.repo_id, revision: model.source.resolved_revision, sha256: "b".repeat(64), markdown, origin: "saved" });
  const hfBundle = (id, name) => ({ ...bundle(id, name), source: { kind: "huggingface", repo_id: `org/${id}`, resolved_revision: "a".repeat(40) },
    huggingface_configuration: { source_verified: false, template_origin: "gguf", generation_defaults: {}, unsupported: {}, response_recipes: [] } });
  const first = hfBundle("first", "First model"), second = hfBundle("second", "Second model");
  const active = { id: "second-live", bundle_id: second.id, display_name: "managed:Second", scope: "managed", status: "running", health: { healthy: true }, applied_startup: {}, endpoint: "http://localhost:8080/v1" };
  globalThis.fetch = async url => {
    const address = String(url);
    if (address.endsWith("/v1/bundles")) return jsonResponse([first, second]);
    if (address.endsWith("/v1/deployments")) return jsonResponse([active]);
    if (address.endsWith("/v1/profiles") || address.endsWith("/v1/imports")) return jsonResponse([]);
    if (address.endsWith("/v1/paths")) return jsonResponse({ models: "D:\\Models" });
    if (address.endsWith("/v1/runtime/models")) return jsonResponse({ max_loaded_models: 1, loaded_deployment_ids: [], loading_deployment_ids: [], router_status: "stopped" });
    if (address.endsWith("/v1/runtime")) return jsonResponse(runtimeReady());
    if (address.includes("/configuration-options")) return jsonResponse(configurationOptions());
    if (address.endsWith("/projectors")) return jsonResponse({ selected_path: null, candidates: [] });
    if (address.endsWith("/probes")) return jsonResponse({ evidence: [], current_support: {}, current_fingerprint: "now", image_setup: {} });
    if (address.endsWith("/v1/models/storage")) return jsonResponse({ future_install_root: "D:\\Models", locations: [] });
    if (address.endsWith("/v1/bundles/first/model-card")) return pendingView.promise;
    if (address.endsWith("/v1/bundles/second/model-card")) return jsonResponse(card(second, "Second card content"));
    throw new Error(`unexpected fetch ${address}`);
  };
  let renderer;
  try {
    await act(async () => { renderer = create(React.createElement(ModelsPanel)); await tick(); });
    assert.equal(renderer.root.findAll(node => node.type?.name === "ModelResponseRecipes").length, 0, "card content is not mounted until requested from the header");
    const button = label => renderer.root.findAllByType("button").find(node => textOf(node) === label);
    await act(async () => { button("Model card").props.onClick(); await tick(); });
    assert.equal(renderer.root.find(node => node.type?.name === "ModelInspector").props.view, "presets", "the main Model card action opens preset comparison");
    assert.equal(renderer.root.findAll(node => node.type?.name === "ModelResponseRecipes").length, 0, "opening presets does not fetch or mount the occasional README viewer");
    await act(async () => { renderer.root.find(node => node.type?.name === "DeploymentsPanel").props.inspector.open("card"); await tick(); });
    assert.equal(renderer.root.find(node => node.type?.name === "ModelResponseRecipes").props.bundle.id, "first");
    assert.ok(textOf(renderer.root).includes("Loading this model's pinned card"));
    assert.equal(button("Show model card"), undefined, "the opened card panel has no second show-card control");
    const lateRefresh = renderer.root.find(node => node.type?.name === "DeploymentsPanel").props.onBundlesChanged;
    await act(async () => { renderer.root.findAllByProps({ className: "catalogue-row" }).find(node => textOf(node).includes("Second model")).props.onClick(); await tick(); });
    assert.equal(renderer.root.find(node => node.type?.name === "ModelInspector").props.view, null);
    await act(async () => { button("Model card").props.onClick(); await tick(); });
    await act(async () => { renderer.root.find(node => node.type?.name === "DeploymentsPanel").props.inspector.open("card"); await tick(); });
    assert.ok(textOf(renderer.root).includes("Second card content"), "the newly selected model loads its own pinned card");
    await act(async () => { pendingView.resolve(jsonResponse(card(first, "First card content"))); await tick(); });
    assert.ok(!textOf(renderer.root).includes("First card content"), "a late card response cannot appear after switching models");
    await act(async () => { await lateRefresh(); await tick(); });
    assert.ok(textOf(renderer.root.findByProps({ "aria-label": "Selected model" })).includes("Second model"), "late card refresh retains the newly selected model");
    assert.equal(renderer.root.find(node => node.type?.name === "ModelResponseRecipes").props.bundle.id, "second");
  } finally { if (renderer) await act(async () => renderer.unmount()); globalThis.fetch = originalFetch; }
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
    throw new Error(`unexpected fetch ${String(url)}`);
  };
  let renderer, refreshed = 0;
  try {
    await act(async () => { renderer = create(React.createElement(ModelResponseRecipes, { bundle: model, onChanged: async () => { refreshed++; } })); });
    assert.ok(textOf(renderer.root).includes("Coding guidance"), "each recommendation retains its source section");
    assert.ok(textOf(renderer.root).includes("Thinking unchanged"), "mode-neutral recommendations retain their meaning");
    assert.equal(renderer.root.findAllByType("input").length, 0, "Model card has no duplicate configuration editor");
    assert.equal(renderer.root.findAllByType("button").some(node => textOf(node).includes("Create")), false);
    await act(async () => { renderer.root.findAllByType("button").find(node => textOf(node) === "Refresh model card").props.onClick(); await tick(); });
    assert.ok(textOf(renderer.root).includes("Card refresh failed: pinned card temporarily unavailable"));
    assert.equal(refreshed, 0, "failed refresh leaves saved metadata untouched");
    await act(async () => { renderer.root.findAllByType("button").find(node => textOf(node) === "Refresh model card").props.onClick(); await tick(); });
    assert.equal(calls.length, 2);
    assert.ok(calls.every(call => call.address.endsWith("/response-recipes/refresh")), "refresh never downloads weights or creates a configuration");
    assert.equal(refreshed, 1);
  } finally { if (renderer) await act(async () => renderer.unmount()); globalThis.fetch = originalFetch; }
}

function presetBundle(id = "preset-model") {
  const source = { source_repo_id: `org/${id}`, source_revision: "a".repeat(40), card_sha256: "b".repeat(64) };
  return { ...bundle(id, "Preset model"), source: { kind: "huggingface", repo_id: source.source_repo_id, resolved_revision: source.source_revision }, huggingface_configuration: { hidden_response_recipe_ids: [], response_recipes: [
    { ...source, id: "coding", name: "Thinking", section: "Coding guidance", per_request: { temperature: 0.6, min_p: 0 }, reasoning: "on" },
    { ...source, id: "instruct", name: "Non-thinking", section: "Non-thinking guidance", per_request: { temperature: 0.7, presence_penalty: 1.5 }, reasoning: "off" },
    { ...source, id: "neutral", name: "Recommended response", section: "Recommended settings", per_request: { temperature: 0.7, top_p: 0.9 }, reasoning: "preserve" },
  ] } };
}

async function checkModelPresetDraftAndVisibility(ModelPresetPanel) {
  const originalFetch = globalThis.fetch;
  let model = presetBundle(), current = { temperature: 0.2, top_p: 0.95, top_k: 30, max_tokens: 6000, reasoning: "off" }, origin = null;
  let renderer, changed = 0, restoreFailures = 1, externalDisabled = false;
  let options = { per_request_defaults: { reasoning: { supported: true } } };
  const edits = [], calls = [];
  const props = () => ({ bundle: model, value: current, origin, options, disabled: externalDisabled, onApply: (value, nextOrigin) => { current = value; origin = nextOrigin; edits.push({ value, origin }); renderer.update(React.createElement(ModelPresetPanel, props())); }, onChanged: async () => { changed++; renderer.update(React.createElement(ModelPresetPanel, props())); } });
  const button = label => renderer.root.findAllByType("button").find(node => textOf(node) === label);
  const choose = async id => act(async () => renderer.root.findAllByType("input").find(node => node.props.type === "radio" && node.props.value === id).props.onChange());
  globalThis.fetch = async (url, init = {}) => {
    const address = String(url), body = init.body ? JSON.parse(init.body) : null;
    calls.push({ address, method: init.method ?? "GET", body });
    if (address.endsWith("/neutral/visibility")) {
      assert.equal(init.method, "PUT"); assert.deepEqual(body, { visible: false });
      model = { ...model, huggingface_configuration: { ...model.huggingface_configuration, hidden_response_recipe_ids: ["neutral"] } };
      return jsonResponse(model);
    }
    if (address.endsWith("/response-recipes/refresh")) {
      assert.equal(init.method, "POST");
      if (body.restore_hidden && restoreFailures-- > 0) throw new Error("Pinned card temporarily unavailable");
      if (body.restore_hidden) model = { ...model, huggingface_configuration: { ...model.huggingface_configuration, hidden_response_recipe_ids: [] } };
      return jsonResponse(model);
    }
    throw new Error(`Unexpected preset request ${address}`);
  };
  try {
    await act(async () => { renderer = create(React.createElement(ModelPresetPanel, props())); });
    assert.equal(renderer.root.findAllByType("select").length, 0, "presets are applied from a panel rather than a competing setup selector");
    await choose("coding");
    assert.equal(edits.length, 0, "previewing a preset leaves the draft untouched");
    assert.ok(textOf(renderer.root).includes("Coding guidance"));
    assert.ok(textOf(renderer.root).includes("org/preset-model"), "the apply preview identifies recorded publisher provenance");
    assert.ok(textOf(renderer.root.findByType("table")).includes("Thinking"), "the preview includes the preset's explicit Thinking mode");
    await act(async () => button("Apply to draft").props.onClick());
    assert.deepEqual(current, { temperature: 0.6, top_p: 0.95, top_k: 30, max_tokens: 6000, reasoning: "on", min_p: 0 }, "apply merges only supplied response values and Thinking");
    assert.deepEqual(origin, { recipe_id: "coding", name: "Thinking", source_repo_id: "org/preset-model", source_revision: "a".repeat(40), card_sha256: "b".repeat(64), section: "Coding guidance" });
    assert.equal(calls.length, 0, "applying does not save, load, refresh or create a setup");
    await act(async () => { current = { ...current, temperature: 0.8 }; renderer.update(React.createElement(ModelPresetPanel, props())); });
    const temperature = renderer.root.findAllByType("tr").find(node => textOf(node.findAllByType("th")[0]) === "Temperature");
    assert.deepEqual(temperature.findAllByType("td").map(textOf), ["0.8", "0.6"], "preview compares the edited draft with the supplied value");
    await act(async () => button("Apply to draft").props.onClick());
    assert.equal(current.temperature, 0.6, "reapplying restores the supplied value in the draft");
    await choose("instruct");
    await act(async () => button("Apply to draft").props.onClick());
    assert.equal(current.reasoning, "off"); assert.equal(current.presence_penalty, 1.5); assert.equal(current.max_tokens, 6000);
    await choose("neutral");
    assert.ok(!renderer.root.findAllByType("tr").some(node => textOf(node.findAllByType("th")[0]) === "Thinking"), "mode-neutral presets do not advertise a Thinking change");
    await act(async () => button("Apply to draft").props.onClick());
    assert.equal(current.reasoning, "off", "mode-neutral apply preserves the draft's Thinking choice");
    assert.equal(current.top_p, 0.9); assert.equal(current.top_k, 30);
    const responseBeforeHide = { ...current }, originBeforeHide = { ...origin };
    await act(async () => { button("Remove from list").props.onClick(); await tick(); });
    assert.deepEqual(model.huggingface_configuration.hidden_response_recipe_ids, ["neutral"]);
    assert.equal(model.huggingface_configuration.response_recipes.length, 3, "removal keeps underlying records for saved ancestry");
    assert.equal(renderer.root.findAllByType("input").some(node => node.props.value === "neutral"), false);
    assert.deepEqual(current, responseBeforeHide); assert.deepEqual(origin, originBeforeHide, "hiding does not detach the saved source");
    await act(async () => renderer.unmount());
    await act(async () => { renderer = create(React.createElement(ModelPresetPanel, props())); });
    assert.equal(renderer.root.findAllByType("input").some(node => node.props.value === "neutral"), false, "reopening respects persisted visibility");
    await act(async () => { button("Restore presets").props.onClick(); await tick(); });
    assert.ok(textOf(renderer.root).includes("Pinned card temporarily unavailable"));
    assert.deepEqual(model.huggingface_configuration.hidden_response_recipe_ids, ["neutral"], "failed restore leaves the previous exclusions intact");
    assert.equal(changed, 1, "failed restore does not publish a new catalogue");
    await act(async () => { button("Restore presets").props.onClick(); await tick(); });
    assert.ok(renderer.root.findAllByType("input").some(node => node.props.value === "neutral"));
    assert.ok(calls.slice(1, 3).every(call => call.body.restore_hidden === true), "restore explicitly requests pinned restoration");
    assert.deepEqual(current, responseBeforeHide); assert.deepEqual(origin, originBeforeHide);
    await act(async () => { button("Refresh presets").props.onClick(); await tick(); });
    assert.equal(calls.at(-1).body.restore_hidden, false, "ordinary refresh does not silently restore removed choices");
    assert.ok(calls.every(call => call.address.includes("/response-recipes/")), "preset management cannot change saved setups or model weights");
    await choose("coding");
    await act(async () => { externalDisabled = true; renderer.update(React.createElement(ModelPresetPanel, props())); });
    assert.equal(button("Apply to draft").props.disabled, true, "parent Save/Load activity blocks preset draft edits");
    assert.equal(button("Remove from list").props.disabled, true);
    assert.equal(button("Refresh presets").props.disabled, true);
    assert.ok(renderer.root.findAllByType("input").every(node => node.props.disabled));
    const requestsBeforeBlockedRefresh = calls.length;
    await act(async () => { button("Refresh presets").props.onClick(); await tick(); });
    assert.equal(calls.length, requestsBeforeBlockedRefresh, "a parent mutation cannot race a preset refresh");
    await act(async () => { externalDisabled = false; renderer.update(React.createElement(ModelPresetPanel, props())); });
    await act(async () => { options = { per_request_defaults: { reasoning: { supported: false } } }; renderer.update(React.createElement(ModelPresetPanel, props())); });
    assert.equal(button("Apply to draft").props.disabled, true, "unsupported explicit Thinking cannot be applied");
    assert.ok(textOf(renderer.root).includes("unavailable for the selected template"));
    await act(async () => { model = { ...model, huggingface_configuration: { ...model.huggingface_configuration, hidden_response_recipe_ids: ["coding", "instruct", "neutral"] } }; renderer.update(React.createElement(ModelPresetPanel, props())); });
    assert.equal(renderer.root.findAllByType("input").length, 0);
    assert.ok(textOf(renderer.root).includes("All presets were removed from this list"), "an empty hidden list points to restoration");
    assert.equal(button("Restore presets").props.disabled, false);
  } finally { if (renderer) await act(async () => renderer.unmount()); globalThis.fetch = originalFetch; }
}

async function checkPresetLateModelOwnership(ModelPresetPanel) {
  const originalFetch = globalThis.fetch;
  const pendingRefresh = createDeferred(), pendingRestore = createDeferred();
  const first = presetBundle("first-preset"), second = presetBundle("second-preset");
  first.huggingface_configuration.hidden_response_recipe_ids = ["neutral"];
  second.huggingface_configuration.response_recipes = [{ ...second.huggingface_configuration.response_recipes[0], id: "second-only", name: "Second model preset" }];
  let currentModel = first, renderer, refreshed = 0;
  const draft = { temperature: 0.4, reasoning: "off", max_tokens: 4096 }, edits = [];
  const props = () => ({ bundle: currentModel, value: draft, origin: null, options: { per_request_defaults: { reasoning: { supported: true } } }, onApply: value => edits.push(value), onChanged: async () => { refreshed++; renderer.update(React.createElement(ModelPresetPanel, props())); } });
  const button = label => renderer.root.findAllByType("button").find(node => textOf(node) === label);
  globalThis.fetch = async (url, init = {}) => {
    const address = String(url), body = JSON.parse(init.body);
    if (address.includes("/first-preset/response-recipes/refresh")) return body.restore_hidden ? pendingRestore.promise : pendingRefresh.promise;
    if (address.includes("/second-preset/response-recipes/refresh")) return jsonResponse(second);
    throw new Error(`Unexpected late preset request ${address}`);
  };
  try {
    await act(async () => { renderer = create(React.createElement(ModelPresetPanel, props())); });
    await act(async () => { button("Refresh presets").props.onClick(); await tick(); });
    await act(async () => { currentModel = second; renderer.update(React.createElement(ModelPresetPanel, props())); await tick(); });
    assert.equal(button("Refresh presets").props.disabled, false, "a new model does not inherit another model's pending presentation");
    await act(async () => { pendingRefresh.reject(new Error("First model refresh failed late")); await tick(); });
    assert.ok(!textOf(renderer.root).includes("First model refresh failed late"), "late failure cannot become the selected model's error");
    assert.ok(textOf(renderer.root).includes("Second model preset"));
    await act(async () => { button("Refresh presets").props.onClick(); await tick(); });
    assert.equal(refreshed, 1);
    await act(async () => { currentModel = first; renderer.update(React.createElement(ModelPresetPanel, props())); await tick(); });
    await act(async () => { button("Restore presets").props.onClick(); await tick(); });
    await act(async () => { currentModel = second; renderer.update(React.createElement(ModelPresetPanel, props())); await tick(); });
    await act(async () => { pendingRestore.resolve(jsonResponse({ ...first, huggingface_configuration: { ...first.huggingface_configuration, hidden_response_recipe_ids: [] } })); await tick(); });
    assert.equal(refreshed, 2, "successful background changes refresh the global catalogue even after selection changes");
    assert.ok(textOf(renderer.root).includes("Second model preset"));
    assert.equal(renderer.root.findAllByType("input").some(node => node.props.value === "neutral"), false, "late restored recipes cannot appear for another selected model");
    assert.equal(button("Refresh presets").props.disabled, false);
    assert.equal(edits.length, 0); assert.deepEqual(draft, { temperature: 0.4, reasoning: "off", max_tokens: 4096 }, "background management leaves the selected response draft intact");
  } finally { if (renderer) await act(async () => renderer.unmount()); globalThis.fetch = originalFetch; }
}

async function checkFileLinkAndRecipes(HuggingFaceImport) {
  const originalFetch = globalThis.fetch;
  const files = ["model-IQ4_XS.gguf", "model-LOW-MTP-IQ4_XS.gguf", "model-MTP-IQ4_XS.gguf"];
  const repo_id = "org/model-GGUF";
  const linked = `https://huggingface.co/${repo_id}?show_file_info=${encodeURIComponent(files[1])}`;
  let inspected = { repo_id, resolved_revision: "a".repeat(40), file_hint: files[1], variants: files.map((name, index) => ({ name, files: [name], size_bytes: 100 + index, complete: true })), projectors: [], guidance_files: ["README.md"], warnings: [], response_recipes: [
    { id: "general", name: "General thinking", section: "Suggested settings", per_request: { temperature: 1, min_p: 0 }, reasoning: "on", source_repo_id: repo_id, source_revision: "a".repeat(40), card_sha256: "b".repeat(64) },
    { id: "coding", name: "Precise coding", section: "Suggested settings", per_request: { temperature: 0.6, min_p: 0 }, reasoning: "on", source_repo_id: repo_id, source_revision: "a".repeat(40), card_sha256: "b".repeat(64) },
    { id: "instruct", name: "Non-thinking", section: "Suggested settings", per_request: { temperature: 0.7, presence_penalty: 1.5 }, reasoning: "off", source_repo_id: repo_id, source_revision: "a".repeat(40), card_sha256: "b".repeat(64) },
    { id: "recommended", name: "Recommended response", section: "Recommended settings", per_request: { temperature: 0.7, top_p: 0.9 }, reasoning: "preserve", notes: ["Not copied: Launch flags are guidance only"], source_repo_id: repo_id, source_revision: "a".repeat(40), card_sha256: "b".repeat(64) },
    { id: "invalid", name: "Invalid", section: "Suggested settings", per_request: { temperature: "high" }, reasoning: "on", source_repo_id: repo_id, source_revision: "a".repeat(40), card_sha256: "b".repeat(64) },
  ] };
  const calls = [], downloads = [];
  globalThis.fetch = async (url, init = {}) => {
    const address = String(url);
    if (address.endsWith("/huggingface/inspect")) { calls.push(JSON.parse(init.body)); return jsonResponse(inspected); }
    if (address.endsWith("/imports/huggingface")) { downloads.push(JSON.parse(init.body)); return jsonResponse({ id: "import", status: "running", bundle_id: null }); }
    throw new Error(`unexpected fetch ${address}`);
  };
  let renderer;
  try {
    await act(async () => { renderer = create(React.createElement(HuggingFaceImport, { onStarted: async () => {} })); });
    const query = renderer.root.findByProps({ id: "model-search-query" });
    assert.ok(query.props.maxLength >= linked.length, "a pasted file-specific Hugging Face URL must fit in the search field");
    await act(async () => query.props.onChange({ target: { value: linked } }));
    await act(async () => { renderer.root.findByType("form").props.onSubmit({ preventDefault() {} }); await tick(); });
    assert.equal(calls[0].repo_id, linked, "the full file-specific URL reaches inspection");
    const choices = renderer.root.findAllByType("input").filter(node => node.props.name === "model-variant");
    assert.equal(choices.length, 3);
    assert.equal(choices.find(node => node.props.value === files[1]).props.checked, true, "the linked LOW-MTP variant is selected exactly");
    assert.ok(choices.find(node => node.props.value === files[1]).props["aria-label"].includes("LOW-MTP"), "the variant kind is accessible");
    const recipes = renderer.root.findAllByType("input").filter(node => node.props.type === "checkbox");
    assert.equal(recipes.length, 4, "mode-neutral recipes are offered and malformed card settings remain hidden");
    assert.ok(textOf(renderer.root).includes("Thinking unchanged"), "Add models shows that the recipe preserves thinking mode");
    assert.ok(textOf(renderer.root).includes("Not copied: Launch flags are guidance only"), "Add models labels omitted card guidance");
    await act(async () => { for (const recipe of recipes) recipe.props.onChange({ target: { checked: true } }); });
    await act(async () => renderer.root.findByProps({ id: "import-initial-recipe" }).props.onChange({ target: { value: "general" } }));
    assert.equal(downloads.length, 0, "Choose never transfers weights");
    await act(async () => renderer.root.findAllByType("button").find(node => textOf(node) === "Back").props.onClick());
    await act(async () => { renderer.root.findByType("form").props.onSubmit({ preventDefault() {} }); await tick(); });
    assert.equal(calls.length, 1, "returning to an unchanged exact source must not re-inspect or reset choices");
    assert.equal(renderer.root.findAllByType("input").find(node => node.props.name === "model-variant" && node.props.value === files[1]).props.checked, true);
    assert.equal(renderer.root.findByProps({ id: "import-initial-recipe" }).props.value, "general");
    await act(async () => renderer.root.findAllByType("button").find(node => textOf(node) === "Review download").props.onClick());
    assert.ok(textOf(renderer.root.findByProps({ className: "selected-download-files" })).includes("LOW-MTP"), "review shows the selected kind and exact file before download");
    assert.equal(renderer.root.findByProps({ "aria-label": "Import GPU layers" }).props.value, "", "untouched GPU placement does not look chosen");
    assert.equal(renderer.root.findByProps({ "aria-label": "Import key cache precision" }).props.value, "", "untouched K cache does not display a precision");
    assert.equal(renderer.root.findByProps({ "aria-label": "Import cache location" }).props.value, "", "untouched cache location does not display GPU");
    await act(async () => {
      changeContext(renderer, 16384, "Import context");
      renderer.root.findByProps({ "aria-label":"Import cache location" }).props.onChange({ target:{value:"cpu"} });
    });
    await act(async () => renderer.root.findAllByType("button").find(node => textOf(node) === "Back").props.onClick());
    assert.equal(renderer.root.findByProps({ id: "import-initial-recipe" }).props.value, "general", "Back preserves the generation recipe");
    await act(async () => renderer.root.findAllByType("button").find(node => textOf(node) === "Review download").props.onClick());
    assert.equal(contextInput(renderer, "Import context").props["data-token-value"], 16384, "Back preserves context");
    assert.equal(renderer.root.findByProps({ "aria-label":"Import cache location" }).props.value, "cpu", "Back preserves KV placement");
    await act(async () => { renderer.root.findAllByType("button").find(node => textOf(node) === "Download model").props.onClick(); await tick(); });
    assert.deepEqual(downloads, [{ repo_id, revision: "a".repeat(40), allow_patterns: [files[1], "README.md"], recipe_ids: ["general", "coding", "instruct", "recommended"], default_recipe_id: null, initial_startup:{kv_offload:false, ctx_size:16384}, initial_recipe_id: "general", initial_per_request: { temperature: 1, min_p: 0, reasoning: "on" } }], "download retains the exact file, recipe and only the loading settings the person set");
    inspected = { ...inspected, file_hint: "missing-IQ4_XS.gguf", variants: [inspected.variants[0]] };
    await act(async () => renderer.root.findAllByType("button").find(node => textOf(node) === "Back").props.onClick());
    await act(async () => renderer.root.findAllByType("button").find(node => textOf(node) === "Back").props.onClick());
    await act(async () => renderer.root.findByProps({id:"model-search-query"}).props.onChange({ target: { value: `https://huggingface.co/${repo_id}?show_file_info=missing-IQ4_XS.gguf` } }));
    await act(async () => { renderer.root.findByType("form").props.onSubmit({ preventDefault() {} }); await tick(); });
    assert.ok(textOf(renderer.root).includes("Linked GGUF file unavailable"), "an unavailable file hint is visible");
    assert.equal(renderer.root.findAllByType("input").find(node => node.props.name === "model-variant").props.checked, false, "an unavailable hint cannot fall back to a different file even when only one variant is listed");
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

function capabilityMark(renderer, label) {
  const button = renderer.root.findAllByType("button").find(node => node.props["aria-label"] === label);
  assert.ok(button, `expected a ${label} capability icon`);
  const mark = button.findAll(node => node.props?.["data-state"])[0];
  assert.ok(mark, `expected a ${label} status mark`);
  return mark;
}

async function checkSavedCapabilities(ModelCapabilities) {
  let renderer, requests = 0, posts = 0, fail = false, failPost = false;
  const evidence = { id: "saved", capability: "tools", status: "passed", fingerprint: "setup-one", tested_at: "2026-09-22T10:00:00Z", observations: {}, note: "A real tool call completed." };
  let report = { current_fingerprint: "setup-one", current_support: { tools: "passed" }, evidence: [evidence], image_setup: { selected_projector: null, projector_present: null, runtime_support: false } };
  globalThis.fetch = async (_url, init = {}) => {
    requests++;
    if (fail) throw new Error("Service unavailable");
    if (init.method === "POST") {
      if (failPost) throw new Error("Capability check failed");
      posts++;
      report = { ...report, current_support: { ...report.current_support, tools: "passed" }, evidence: [...report.evidence, { ...evidence, fingerprint: report.current_fingerprint }] };
      return jsonResponse(report.evidence.at(-1));
    }
    return jsonResponse(report);
  };
  const deployment = { id: "deployment", status: "running", health: { healthy: true }, scope: "managed", server_props: { modalities: { vision: false }, chat_template_caps: {} } };
  const action = async (_key, operation) => operation();
  try {
    await act(async () => { renderer = create(React.createElement(ModelCapabilities, { deployment, busy: "", action })); await tick(); });
    assert.equal(capabilityMark(renderer, "Tools").props["data-state"], "passed", "saved probe evidence hydrates without rerunning it");
    assert.equal(requests, 1);
    assert.equal(posts, 0, "a partial status report does not start checks for missing keys");
    assert.equal(capabilityMark(renderer, "Image").props["data-state"], "absent", "a text model without a vision file shows no image check");
    report = { ...report, current_fingerprint: "setup-two", current_support: { tools: "untested" } };
    await act(async () => {
      renderer.update(React.createElement(ModelCapabilities, { deployment: { ...deployment }, busy: "", action }));
      for (let attempt = 0; attempt < 6; attempt++) await tick();
    });
    assert.equal(posts, 1, "a healthy model runs an untested check once");
    assert.equal(capabilityMark(renderer, "Tools").props["data-state"], "passed", "the completed check replaces the unchecked icon");
    failPost = true;
    report = { ...report, current_fingerprint: "setup-three", current_support: { tools: "untested" } };
    await act(async () => {
      renderer.update(React.createElement(ModelCapabilities, { deployment: { ...deployment }, busy: "", action }));
      for (let attempt = 0; attempt < 6; attempt++) await tick();
    });
    assert.match(textOf(renderer.root), /Capability check failed/, "a thrown capability check stays visible");
    assert.equal(capabilityMark(renderer, "Tools").props["data-state"], "untested", "a thrown check does not invent a pass");
    assert.equal(textOf(renderer.root).includes("Saved results unavailable"), false, "a probe failure is separate from a missing saved report");
    failPost = false;
    fail = true;
    await act(async () => { renderer.update(React.createElement(ModelCapabilities, { deployment: { ...deployment }, busy: "", action })); await tick(); });
    assert.ok(textOf(renderer.root).includes("Saved results unavailable"), "fetch failures are visible instead of silently showing a pass");
    assert.notEqual(capabilityMark(renderer, "Tools").props["data-state"], "passed");
  } finally { if (renderer) await act(async () => renderer.unmount()); }
}

async function checkReviewOffersBuiltinMtp(HuggingFaceImport) {
  const downloads = [], estimates = [];
  const estimate = {
    hardware: { gpu_devices: [{ id: "gpu", name: "GPU", total_bytes: 1000, available_bytes: 800 }], observed_at: "2026-09-29T00:00:00Z", source: "test", stale: false, ram_total_bytes: 2000, ram_available_bytes: 1500 },
    source: "metadata", completeness: "partial", estimated_at: "2026-09-29T00:00:00Z", devices: [], assumptions: [], unknown_reasons: [],
    builtin_mtp: true, mtp_draft_files: ["MTP/head.gguf"], advertised_modalities: ["image"], context_maximum: 8192,
    weights_bytes: 100, kv_bytes: 10, gpu_bytes: 80, ram_bytes: 40, speculation_bytes: 0,
  };
  globalThis.fetch = async (url, init = {}) => {
    const address = String(url);
    if (address.endsWith("/huggingface/inspect")) return jsonResponse({ repo_id: "org/mtp", resolved_revision: "b".repeat(40), variants: [{ name: "Q4", complete: true, files: ["model.gguf"], size_bytes: 100 }], projectors: [], guidance_files: [], warnings: [], auxiliary_ggufs: [{ name: "MTP/head.gguf", files: ["MTP/head.gguf"], complete: true, size_bytes: 20 }] });
    if (address.endsWith("/models/estimate")) { estimates.push(JSON.parse(init.body)); return jsonResponse(estimate); }
    if (address.endsWith("/imports/huggingface")) { downloads.push(JSON.parse(init.body)); return jsonResponse({ id: "import", status: "running", bundle_id: null }); }
    throw new Error(`unexpected fetch ${address}`);
  };
  let renderer;
  try {
    await act(async () => { renderer = create(React.createElement(HuggingFaceImport, { onStarted: async () => {} })); });
    await act(async () => renderer.root.findByProps({ id: "model-search-query" }).props.onChange({ target: { value: "org/mtp" } }));
    await act(async () => { renderer.root.findByType("form").props.onSubmit({ preventDefault() {} }); await tick(); });
    await act(async () => renderer.root.findAllByType("button").find(node => textOf(node) === "Review download").props.onClick());
    assert.equal(capabilityMark(renderer, "Text").props["data-state"], "untested");
    assert.equal(capabilityMark(renderer, "Image").props["data-state"], "absent", "image stays unavailable until the header or a vision file says otherwise");
    await act(async () => { await new Promise(resolve => setTimeout(resolve, 350)); });
    assert.equal(capabilityMark(renderer, "Image").props["data-state"], "untested", "a header that identifies image input offers that check");
    const mtp = renderer.root.findByProps({ "aria-label": "Import MTP" });
    assert.equal(mtp.props.value, "");
    assert.ok(mtp.findAllByType("option").some(node => node.props.value === "builtin"));
    assert.ok(mtp.findAllByType("option").some(node => node.props.value === "MTP/head.gguf"));
    await act(async () => { renderer.root.findAllByType("button").find(node => textOf(node) === "Download model").props.onClick(); await tick(); });
    assert.deepEqual(downloads[0].initial_startup, {}, "leaving MTP off sends no speculation flag");
    await act(async () => {
      renderer.root.findByProps({ "aria-label": "Import MTP" }).props.onChange({ target: { value: "MTP/head.gguf" } });
      changeContext(renderer, 8192, "Import context");
    });
    await act(async () => { await new Promise(resolve => setTimeout(resolve, 350)); });
    assert.equal(estimates.at(-1).startup.spec_type, "draft-mtp");
    assert.equal(estimates.at(-1).startup.spec_draft_model, "MTP/head.gguf");
    assert.equal("n_gpu_layers" in estimates.at(-1).startup, false);
    await act(async () => { renderer.root.findAllByType("button").find(node => textOf(node) === "Download model").props.onClick(); await tick(); });
    assert.deepEqual(downloads[1].initial_startup, { ctx_size: 8192, spec_type: "draft-mtp", spec_draft_model: "MTP/head.gguf" });
    assert.deepEqual(downloads[1].allow_patterns, ["model.gguf", "MTP/head.gguf"]);
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

async function checkRepositorySelectionLoadsFiles(ModelsPanel) {
  const originalFetch = globalThis.fetch;
  const calls = [];
  const inspection = createDeferred();
  globalThis.fetch = async (url, init = {}) => {
    const address = String(url);
    calls.push({ address, body: init.body ? JSON.parse(init.body) : null });
    if (address.includes("/huggingface/search?")) return jsonResponse([{ repo_id: "publisher/model-GGUF", downloads: 100 }]);
    if (address.endsWith("/huggingface/inspect")) return inspection.promise;
    if (address.endsWith("/v1/models/storage")) return jsonResponse({ future_install_root: "D:\\Models", locations: [], managed_bytes: 0, staging_bytes: 0, cache_bytes: 0, metadata_bytes: 0, available_bytes: 1000, reclaimable_bytes: 0 });
    if (address.endsWith("/v1/runtime/models")) return jsonResponse({ max_loaded_models: 1, loaded_deployment_ids: [], loading_deployment_ids: [], router_status: "stopped" });
    if (address.endsWith("/v1/runtime")) return jsonResponse(runtimeReady());
    if (address.endsWith("/v1/paths")) return jsonResponse({ models: "D:\\Models" });
    if (["/v1/bundles", "/v1/profiles", "/v1/deployments", "/v1/imports"].some(suffix => address.endsWith(suffix))) return jsonResponse([]);
    throw new Error(`unexpected fetch ${address}`);
  };
  let renderer;
  try {
    await act(async () => { renderer = create(React.createElement(ModelsPanel)); await tick(); });
    await act(async () => renderer.root.findByProps({ id: "models-tab-add" }).props.onClick());
    const query = renderer.root.findByProps({ id: "model-search-query" });
    await act(async () => query.props.onChange({ target: { value: "model" } }));
    const searchForm = renderer.root.findAllByType("form").find(node => node.findAllByType("input").some(input => input.props.id === "model-search-query"));
    await act(async () => { searchForm.props.onSubmit({ preventDefault() {} }); await tick(); });
    await act(async () => { renderer.root.findAllByType("button").find(node => textOf(node).includes("Select repository")).props.onClick(); await tick(); });
    assert.equal(calls.filter(call => call.address.endsWith("/huggingface/inspect")).length, 1, "selecting a search result must inspect that repository immediately");
    assert.ok(textOf(renderer.root).includes("Loading model files"), "selected repository must expose pending file inspection");
    await act(async () => {
      inspection.resolve(jsonResponse({ repo_id: "publisher/model-GGUF", resolved_revision: "revision-123", variants: [{ name: "Q4_K_M", files: ["model-Q4_K_M.gguf"], size_bytes: 4096, complete: true }], projectors: [], guidance_files: ["README.md"], warnings: [] }));
      await tick();
    });
    assert.ok(textOf(renderer.root).includes("Q4_K_M"), "selected repository reveals the actual model variant");
    assert.ok(renderer.root.findAllByType("button").some(node => textOf(node) === "Review download" && node.props.disabled === false), "one complete text variant is ready to review after inspection");
    await act(async () => renderer.root.findByProps({ id: "models-tab-downloads" }).props.onClick());
    await act(async () => renderer.root.findByProps({ id: "models-tab-add" }).props.onClick());
    assert.ok(textOf(renderer.root.findByProps({ "aria-label": "Repository files" })).includes("Q4_K_M"), "inspected selection survives tab changes");
    await act(async () => renderer.root.findAllByType("button").find(node => textOf(node) === "Back").props.onClick());
    assert.equal(renderer.root.findByProps({ id: "model-search-query" }).props.value, "model", "search text survives tab changes and Back");
  } finally {
    if (renderer) await act(async () => renderer.unmount());
    globalThis.fetch = originalFetch;
  }
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

function createDeferred() {
  let resolve;
  let reject;
  const promise = new Promise((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
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

async function checkDraftRevisionConflicts(Panel) {
  const originalFetch = globalThis.fetch;
  const bag = requested => ({ requested, applied: requested, unsupported: [], retired: [], overridden: [], unverified: [] });
  const model = { ...bundle("revision-model", "Revision model"), default_configuration_id: "original" };
  const makeProfile = (id, name) => ({ id, bundle_id: model.id, display_name: name, revision: 1, bags: { startup: bag({ ctx_size: 8192, cache_type_k: "q8_0" }), per_request: bag({ temperature: 1 }), agent: bag({}) } });
  let profiles = [makeProfile("original", "Original"), makeProfile("other", "Other")];
  let renderer, refreshFails = false;
  const writes = [], validations = [], resolutions = [], descriptors = [];
  const panel = () => React.createElement(Panel, { selectedBundleId: model.id, initialBundles: [model], initialProfiles: profiles, onBundlesChanged: async () => { if (refreshFails) throw new Error("Catalogue refresh unavailable"); renderer.update(panel()); } });
  globalThis.fetch = async (url, init = {}) => {
    const address = String(url), body = init.body ? JSON.parse(init.body) : null;
    if (address.endsWith("/v1/runtime")) return jsonResponse(runtimeReady());
    if (address.endsWith("/v1/deployments")) return jsonResponse([]);
    if (address.endsWith("/v1/setup-resolution")) {
      const selected = profiles.find(item => item.id === body.overrides.model_configuration_id) ?? profiles[0];
      resolutions.push(body.overrides);
      const facts = {};
      for (const [name, defaults] of [["startup", { ctx_size: 4096, cache_type_k: "f16", cache_type_v: "f16" }], ["per_request", { temperature: 1, top_p: 0.95 }]]) {
        const overrides = body.overrides[`${name}_overrides`] ?? {}, requested = { ...selected.bags[name].requested, ...overrides };
        for (const key of new Set([...Object.keys(defaults), ...Object.keys(requested)])) {
          const value = requested[key] ?? defaults[key];
          facts[`${name}.${key}`] = { value, known: value != null, source: Object.hasOwn(overrides, key) && overrides[key] !== null ? "Turn overrides" : requested[key] == null ? "Model default" : "Configuration: " + selected.display_name, default_value: defaults[key], default_source: "Model default" };
        }
      }
      return jsonResponse({ configuration: body.overrides, effective_values: facts, instruction_layers: [] });
    }
    if (address.includes("/configuration-options")) { descriptors.push(body); return jsonResponse({ ...configurationOptions(), bundle_id: model.id }); }
    if (address.endsWith("/v1/settings/preview")) { validations.push(body); return jsonResponse({ startup: bag(body.startup), per_request: bag(body.per_request), agent: bag(body.agent ?? {}) }); }
    if (address.endsWith("/configurations")) {
      writes.push(body);
      const existing = profiles.find(item => item.id === body.configuration_id);
      if (existing && body.expected_revision !== existing.revision) return { ok: false, status: 409, json: async () => ({ error: "This configuration changed elsewhere. Refresh before saving.", code: "configuration_revision_conflict" }) };
      const saved = { ...(existing ?? makeProfile(profiles.some(item => item.id === "copy") ? "copy-2" : "copy", body.display_name)), display_name: body.display_name, revision: existing ? existing.revision + 1 : 1, bags: { startup: bag(body.startup), per_request: bag(body.per_request), agent: bag(body.agent ?? {}) }, recipe_origin: body.recipe_origin ?? null };
      profiles = [...profiles.filter(item => item.id !== saved.id), saved];
      return jsonResponse(saved);
    }
    if (address.endsWith("/v1/hardware/estimate")) return jsonResponse({ completeness: "unavailable", reasons: [], unknown_costs: [], gpu: {}, ram: {}, components: [], devices: [] });
    throw new Error(`Unexpected revision request ${address}`);
  };
  const getOriginal = () => profiles.find(item => item.id === "original");
  const button = label => { const found = renderer.root.findAllByType("button").find(node => textOf(node) === label); assert.ok(found, label); return found; };
  const temperature = () => renderer.root.findAllByType("input").find(node => node.props.id === "model-response-temperature");
  const status = () => textOf(renderer.root.findByProps({ className: "model-toolbar-status" }));
  const startupReadout = label => renderToStaticMarkup(renderer.root.findAll(node => node.type?.name === "SettingRow" && node.props.label === label)[0].props.provenance);
  const estimateStartup = () => renderer.root.findAll(node => node.type?.name === "ModelHardwareEstimate")[0].props.selection.startup;
  const validate = async () => act(async () => { button("Validate draft").props.onClick(); await tick(); });
  const editTemperature = async value => act(async () => { temperature().props.onChange({ target: { value: String(value) } }); await tick(); });
  const choose = async id => act(async () => { renderer.root.findByProps({ id: "model-configuration" }).props.onChange({ target: { value: id } }); await tick(); });
  const save = async () => act(async () => { renderer.root.findByProps({ id: "model-settings-form" }).props.onSubmit({ preventDefault() {} }); await tick(); });
  const externalSave = async value => {
    profiles = profiles.map(item => item.id === "original" ? { ...item, revision: item.revision + 1, bags: { ...item.bags, per_request: bag({ temperature: value }) } } : item);
    await act(async () => { renderer.update(panel()); await tick(); });
  };
  try {
    await act(async () => { renderer = create(panel(), { createNodeMock: element => element.type === "form" ? { reportValidity: () => true } : null }); await tick(); });
    await externalSave(0.2);
    assert.equal(temperature().props.value, 0.2, "a clean editor follows a refreshed saved revision");
    assert.equal(renderer.root.findByProps({ className: "model-edit-state" }).props["data-dirty"], false);
    await act(async () => { changeContext(renderer, 16384); await tick(); });
    await externalSave(0.8);
    await save();
    assert.equal(writes.at(-1).expected_revision, 2, "active edits retain the actual authoring revision");
    assert.match(status(), /changed elsewhere.*Revert edits.*Save a copy/, "conflict recovery names the available draft-preserving choices");
    assert.equal(getOriginal().bags.per_request.requested.temperature, 0.8, "a conflicting save cannot overwrite the other saved response");
    assert.equal(contextInput(renderer).props["data-token-value"], 16384, "conflict retains the local startup edit");
    await choose("other"); await choose("original");
    await save();
    assert.equal(writes.at(-1).expected_revision, 2, "stashing and restoring cannot advance a dirty draft's revision");
    assert.match(status(), /changed elsewhere/);
    await act(async () => button("Revert edits").props.onClick()); await tick();
    assert.equal(temperature().props.value, 0.8, "explicit revert adopts the latest saved response");
    await act(async () => { changeContext(renderer, 24576); await tick(); });
    refreshFails = true;
    await save();
    assert.equal(writes.at(-1).expected_revision, 3);
    assert.match(status(), /Saved\. The screen could not refresh/);
    assert.equal(getOriginal().bags.startup.requested.ctx_size, 24576);
    assert.equal(estimateStartup().ctx_size, 24576, "failed observation keeps estimates on the confirmed saved draft");
    await validate();
    assert.equal(validations.at(-1).startup.ctx_size, 24576, "validation keeps the confirmed save even while parent records are stale");
    refreshFails = false;
    await save();
    assert.equal(writes.at(-1).expected_revision, 4, "successful save adopts its returned revision even if observation fails");
    assert.equal(writes.at(-1).startup.ctx_size, 24576, "retry after failed observation cannot restore stale startup values");
    assert.equal(writes.at(-1).per_request.temperature, 0.8);
    assert.equal(status(), "Saved.");
    await act(async () => { changeContext(renderer, 32768); await tick(); });
    await act(async () => button("Save a copy").props.onClick());
    await act(async () => { button("Save copy").props.onClick(); await tick(); });
    assert.equal(Object.hasOwn(writes.at(-1), "expected_revision"), false, "a new copy has no existing revision to compare");
    assert.equal(profiles.find(item => item.id === "copy").bags.startup.requested.ctx_size, 32768);
    assert.equal(getOriginal().bags.startup.requested.ctx_size, 24576, "copy creation preserves its source setup");

    await editTemperature(0.4);
    await validate();
    const retained = { ctx_size: 32768, cache_type_k: "q8_0" };
    assert.deepEqual(validations.at(-1).startup, retained);
    profiles = profiles.map(item => item.id === "copy" ? { ...item, revision: item.revision + 1, bags: { ...item.bags, startup: bag({ ctx_size: 65536, cache_type_v: "q4_0" }), per_request: bag({ temperature: 0.1, top_p: 0.3 }) } } : item);
    await act(async () => { renderer.update(panel()); await tick(); });
    assert.equal(contextInput(renderer).props["data-token-value"], 32768, "a response-only draft retains its authored startup values after an external save");
    assert.match(startupReadout("Context"), /32,768 tokens/, "resolved context describes the retained draft, not the latest saved record");
    assert.match(startupReadout("K cache precision"), /q8_0/, "an externally removed setting remains in the draft preview");
    assert.match(startupReadout("V cache precision"), /f16/, "an externally added setting does not enter the draft preview");
    assert.deepEqual(estimateStartup(), retained, "memory estimates use exactly the retained draft startup");
    const editorResolution = resolutions.findLast(item => Object.hasOwn(item, "startup_overrides"));
    assert.deepEqual(editorResolution.startup_overrides, { ctx_size: 32768, cache_type_v: null, cache_type_k: "q8_0" });
    assert.deepEqual(editorResolution.per_request_overrides, { temperature: 0.4, top_p: null }, "response preview also removes newly saved settings outside the retained draft");
    assert.deepEqual(descriptors.at(-1).startup, editorResolution.startup_overrides, "control descriptors resolve the same draft additions and removals");
    assert.equal(textOf(renderer.root).includes("Out of date"), false, "an external save cannot invalidate an unchanged checked draft");
    await validate();
    assert.deepEqual(validations.at(-1).startup, retained, "Validate draft checks the values retained for Save a copy");
    await choose("other"); await choose("copy");
    assert.deepEqual(estimateStartup(), retained, "stashed drafts restore their original estimate inputs");
    await validate();
    assert.deepEqual(validations.at(-1).startup, retained, "stashed drafts restore the same validation inputs");
    await act(async () => { changeContext(renderer, 40960); await tick(); });
    assert.equal(textOf(renderer.root).includes("Out of date"), true, "a local startup edit invalidates the previous check");
    await act(async () => { changeContext(renderer, 32768); await tick(); });
    assert.equal(textOf(renderer.root).includes("Out of date"), false, "returning to the checked draft restores matching check identity");
    await act(async () => button("Save a copy").props.onClick());
    await act(async () => { button("Save copy").props.onClick(); await tick(); });
    assert.deepEqual(writes.at(-1).startup, retained, "copy submission agrees with the displayed, checked and estimated startup");
    assert.equal(writes.at(-1).per_request.temperature, 0.4);
    assert.equal(profiles.find(item => item.id === "copy").bags.startup.requested.ctx_size, 65536, "a new copy preserves the externally saved source");
    await choose("copy-2");
    await editTemperature(0.6);
    profiles = profiles.map(item => item.id === "copy-2" ? { ...item, revision: item.revision + 1, bags: { ...item.bags, startup: bag({ ctx_size: 65536, cache_type_v: "q4_0" }) } } : item);
    await act(async () => { renderer.update(panel()); await tick(); });
    await act(async () => { button("Revert edits").props.onClick(); await tick(); });
    assert.equal(contextInput(renderer).props["data-token-value"], 65536, "explicit revert adopts the latest startup values");
    assert.deepEqual(estimateStartup(), { ctx_size: 65536, cache_type_v: "q4_0" }, "explicit revert adopts latest estimate inputs including removals");
    assert.match(startupReadout("K cache precision"), /f16/);
    await validate();
    assert.deepEqual(validations.at(-1).startup, estimateStartup(), "reverted validation and estimates remain aligned");
  } finally {
    if (renderer) await act(async () => renderer.unmount());
    globalThis.fetch = originalFetch;
  }
}
