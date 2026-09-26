import assert from "node:assert/strict";
import path from "node:path";
import { fileURLToPath } from "node:url";

import React from "react";
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
  await checkModelPicker((await vite.ssrLoadModule("/src/renderer/ModelPicker.tsx")).ModelPicker);
  await checkVariantPresentation(await vite.ssrLoadModule("/src/renderer/modelVariantPresentation.ts"));
  await checkFileLinkAndRecipes((await vite.ssrLoadModule("/src/renderer/HuggingFaceImport.tsx")).HuggingFaceImport);
  await checkInstalledConfigurationWarning((await vite.ssrLoadModule("/src/renderer/ImportJobsPanel.tsx")).ImportJobsPanel);
  const { settingValue } = await vite.ssrLoadModule("/src/renderer/effectiveSettings.ts");
  assert.equal(settingValue(0.949999988079071), "0.95", "server float noise should not leak into the settings readout");
  await checkModelsRenderBeforeDeferredRuntimeAndConfiguration(ModelsPanel);
  await checkExistingBundleRecipes((await vite.ssrLoadModule("/src/renderer/ModelResponseRecipes.tsx")).ModelResponseRecipes);
  await checkPinnedCardViewer((await vite.ssrLoadModule("/src/renderer/ModelResponseRecipes.tsx")).ModelResponseRecipes);
  await checkSelectedModelOwnsDetails(ModelsPanel);
  await checkCardRefreshRetainsNewSelection(ModelsPanel);
  await checkRepositorySelectionLoadsFiles(ModelsPanel);
  await checkRepositoryChoicesAndLateResults((await vite.ssrLoadModule("/src/renderer/HuggingFaceImport.tsx")).HuggingFaceImport);
  await checkPermanentDeletionPreview((await vite.ssrLoadModule("/src/renderer/ModelDeletion.tsx")).ModelDeletion);
  await checkSavedCapabilities((await vite.ssrLoadModule("/src/renderer/ModelCapabilities.tsx")).ModelCapabilities);
  await checkExplicitVisionSelection((await vite.ssrLoadModule("/src/renderer/ModelProjectorControls.tsx")).ModelProjectorControls);
} finally {
  await vite.close();
}

console.log("Models panel deferred loading checks passed.");

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

async function checkSelectedModelOwnsDetails(ModelsPanel) {
  const originalFetch = globalThis.fetch;
  let renderer;
  const deployment = { id: "gemma-live", bundle_id: "gemma", profile_id: "gemma-default", display_name: "managed:Gemma", scope: "managed", status: "running", health: { healthy: true }, applied_startup: {}, endpoint: "http://localhost:8080/v1" };
  const gemmaProfile = { id: "gemma-default", bundle_id: "gemma", display_name: "Default", revision: 1, bags: { startup: { requested: {} }, per_request: { requested: {} }, agent: { requested: {} } } };
  globalThis.fetch = async url => {
    const address = String(url);
    if (address.endsWith("/v1/bundles")) return jsonResponse([bundle("qwen", "Selected Qwen"), { ...bundle("gemma", "Loaded Gemma"), default_configuration_id: "gemma-default" }]);
    if (address.endsWith("/v1/deployments")) return jsonResponse([deployment]);
    if (address.endsWith("/v1/profiles")) return jsonResponse([gemmaProfile]);
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
    const loaded = renderer.root.findByProps({ "aria-label": "Other active models" });
    await act(async () => { loaded.findByType("button").props.onClick(); await tick(); });
    assert.equal(textOf(renderer.root.findByProps({ "aria-label": "Selected model" })).includes("Loaded Gemma"), true, "the compact active-model strip selects that model");
    assert.deepEqual(renderer.root.findAll(node => node.type?.name === "ModelCapabilities").map(node => node.props.deployment.id), ["gemma-live"], "selecting the loaded model restores its own controls and persisted probes");
  } finally { if (renderer) await act(async () => renderer.unmount()); globalThis.fetch = originalFetch; }
}

async function checkModelsRenderBeforeDeferredRuntimeAndConfiguration(ModelsPanel) {
  const originalFetch = globalThis.fetch;
  const runtime = createDeferred();
  const configuration = createDeferred();
  const calls = [];
  globalThis.fetch = async (url) => {
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
    assert.ok(textOf(renderer.root).includes("Checking local engine"), "runtime state should be pending while /v1/runtime is delayed");
    assert.ok(!textOf(renderer.root).includes("Engine setup required"), "pending runtime must not be shown as missing engine setup");
    assert.ok(!calls.some((call) => call.includes("/configuration-options")), "configuration metadata should wait until deployment runtime data has loaded");

    runtime.resolve(jsonResponse(runtimeReady()));
    await act(async () => {
      await tick();
    });
    assert.ok(calls.some((call) => call.includes("/configuration-options")), "configuration metadata should load after runtime/deployment refresh");
    assert.ok(textOf(renderer.root).includes("Local engine ready"), "ready runtime should replace pending engine copy");

    configuration.resolve(jsonResponse(configurationOptions()));
    await act(async () => {
      await tick();
    });
    assert.ok(textOf(renderer.root).includes("256k maximum context"), "deferred configuration result should hydrate model capacity");
    const speculation = renderer.root.find(node => node.type === "div" && node.props.id === "model-spec_type" && node.props.role === "radiogroup");
    const speculationChoices = speculation.findAll(node => node.type === "input" && node.props.type === "radio");
    assert.deepEqual(speculationChoices.map(option => option.props.value), ["", "none", "draft-mtp"], "startup controls offer a distinct inherited choice");
    assert.equal(speculationChoices.find(option => option.props.checked)?.props.value, "", "an unset startup control shows its inherited choice");
    await act(async () => { speculationChoices.find(option => option.props.value === "draft-mtp").props.onChange(); });
    assert.equal(renderer.root.findByProps({ id: "model-spec_draft_n_max" }).props.value, "", "MTP draft count stays inherited until explicitly selected");
    const thinkingEditor = renderer.root.findAll(node => node.type?.name === "ResponseSettingsEditor")[0];
    assert.deepEqual(thinkingEditor.props.options.per_request_defaults.reasoning_effort.options.map(option => option.value), ["default", "low", "medium", "xhigh"], "The response editor receives only model-specific thinking levels");
    assert.equal(renderer.root.findAll(node => node.type === "label" && textOf(node).startsWith("Saved preset")).length, 0, "Models has one configuration editor instead of a second preset selection");
    await act(async () => renderer.unmount());
  } finally {
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
    let download = renderer.root.findAllByType("button").find(node => textOf(node) === "Download model");
    assert.equal(download.props.disabled, true, "a repository offering vision requires an explicit vision or text-only choice");
    await act(async () => renderer.root.findAllByType("input").find(node => node.props.name === "image-input" && node.props.value === "vision").props.onChange());
    download = renderer.root.findAllByType("button").find(node => textOf(node) === "Download model");
    await act(async () => { download.props.onClick(); download.props.onClick(); await tick(); });
    assert.deepEqual(downloads, [{ repo_id: "org/second", revision: "pinned-revision", allow_patterns: ["weights[[]4].gguf", "mmproj.gguf", "README.md"], recipe_ids: [], default_recipe_id: null }], "download pins the inspected revision and exact files, escaping glob syntax and deduplicating clicks");
    assert.equal(completions, 1);
  } finally { if (renderer) await act(async () => renderer.unmount()); }
}

async function checkCardRefreshRetainsNewSelection(ModelsPanel) {
  const originalFetch = globalThis.fetch;
  const pendingCard = createDeferred();
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
    if (address.endsWith("/v1/bundles/first/response-recipes/refresh")) return pendingCard.promise;
    if (address.endsWith("/v1/bundles/first/model-card")) return pendingView.promise;
    if (address.endsWith("/v1/bundles/second/model-card")) return jsonResponse(card(second, "Second card content"));
    throw new Error(`unexpected fetch ${address}`);
  };
  let renderer;
  try {
    await act(async () => { renderer = create(React.createElement(ModelsPanel)); await tick(); });
    assert.equal(renderer.root.find(node => node.type?.name === "ModelResponseRecipes").props.bundle.id, "first");
    await act(async () => { renderer.root.findAllByType("button").find(node => textOf(node) === "Show model card").props.onClick(); await tick(); });
    await act(async () => { renderer.root.findAllByType("button").find(node => textOf(node) === "Refresh model card").props.onClick(); await tick(); });
    await act(async () => { renderer.root.findByProps({ "aria-label": "Other active models" }).findByType("button").props.onClick(); await tick(); });
    await act(async () => { renderer.root.findAllByType("button").find(node => textOf(node) === "Show model card").props.onClick(); await tick(); });
    assert.ok(textOf(renderer.root).includes("Second card content"), "the newly selected model loads its own pinned card");
    await act(async () => { pendingView.resolve(jsonResponse(card(first, "First card content"))); await tick(); });
    assert.ok(!textOf(renderer.root).includes("First card content"), "a late card response cannot appear after switching models");
    await act(async () => { pendingCard.resolve(jsonResponse(first)); await tick(); });
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
  const saved = [{ id: "profile-general", bundle_id: model.id, display_name: "General thinking edited", recipe_origin: { recipe_id: "general", source_repo_id: "org/model", source_revision: "a".repeat(40), card_sha256: "b".repeat(64) } }];
  globalThis.fetch = async (url, init = {}) => {
    calls.push({ address: String(url), body: init.body ? JSON.parse(init.body) : null });
    if (String(url).endsWith("/response-recipes/refresh")) {
      if (refreshFailures-- > 0) throw new Error("pinned card temporarily unavailable");
      return jsonResponse(model);
    }
    if (String(url).endsWith("/response-recipes/configurations")) return jsonResponse({ bundle: model, configurations: saved });
    throw new Error(`unexpected fetch ${String(url)}`);
  };
  let renderer, refreshed = 0;
  try {
    await act(async () => { renderer = create(React.createElement(ModelResponseRecipes, { bundle: model, profiles: saved, onChanged: async () => { refreshed++; } })); });
    assert.ok(textOf(renderer.root).includes("Created from model card as “General thinking edited”"), "edited configurations keep origin without claiming their current values match the card");
    assert.ok(textOf(renderer.root).includes("Coding guidance"), "each recipe displays its own source section");
    assert.ok(textOf(renderer.root).includes("Thinking unchanged"), "mode-neutral recipes do not claim a thinking override");
    assert.ok(textOf(renderer.root).includes("Not copied: Prompt format is guidance only"), "omitted guidance is labelled in My models");
    const checks = renderer.root.findAllByType("input").filter(node => node.props.type === "checkbox");
    for (const checkbox of checks) await act(async () => checkbox.props.onChange({ target: { checked: true } }));
    const defaultChoice = renderer.root.findByProps({ id: "model-recipe-default-bundle-card" });
    assert.equal(defaultChoice.props.value, "", "creating configurations must not silently choose a model default");
    await act(async () => defaultChoice.props.onChange({ target: { value: "general" } }));
    const createButton = renderer.root.findAllByType("button").find(node => textOf(node) === "Create selected configurations");
    assert.equal(createButton.props.disabled, false, "a missing guidance file does not block metadata-only configuration creation");
    await act(async () => { createButton.props.onClick(); await tick(); });
    assert.deepEqual(calls[0].body, { recipe_ids: ["general", "coding", "recommended"], default_recipe_id: "general" });
    assert.equal(refreshed, 1, "recipe creation refreshes the saved model and configurations");
    await act(async () => { renderer.root.findAllByType("button").find(node => textOf(node) === "Refresh model card").props.onClick(); await tick(); });
    assert.ok(textOf(renderer.root).includes("Card refresh failed: pinned card temporarily unavailable"), "refresh errors are visible without losing saved recipe choices");
    assert.equal(refreshed, 1, "a failed refresh leaves existing library metadata untouched");
    await act(async () => { renderer.root.findAllByType("button").find(node => textOf(node) === "Refresh model card").props.onClick(); await tick(); });
    assert.ok(calls[2].address.endsWith("/response-recipes/refresh"), "retry reads only the pinned metadata endpoint rather than importing weights");
    assert.equal(refreshed, 2);
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
    assert.ok(textOf(renderer.root.findByProps({ className: "selected-download-files" })).includes("LOW-MTP"), "the selected kind and exact file are shown before download");
    const recipes = renderer.root.findAllByType("input").filter(node => node.props.type === "checkbox");
    assert.equal(recipes.length, 4, "mode-neutral recipes are offered and malformed card settings remain hidden");
    assert.ok(textOf(renderer.root).includes("Thinking unchanged"), "Add models shows that the recipe preserves thinking mode");
    assert.ok(textOf(renderer.root).includes("Not copied: Launch flags are guidance only"), "Add models labels omitted card guidance");
    await act(async () => { for (const recipe of recipes) recipe.props.onChange({ target: { checked: true } }); });
    await act(async () => renderer.root.findAllByType("input").find(node => node.props.name === "recipe-default" && node.props.value === "general").props.onChange());
    await act(async () => { renderer.root.findAllByType("button").find(node => textOf(node) === "Download model").props.onClick(); await tick(); });
    assert.deepEqual(downloads, [{ repo_id, revision: "a".repeat(40), allow_patterns: [files[1], "README.md"], recipe_ids: ["general", "coding", "instruct", "recommended"], default_recipe_id: "general" }], "download retains exact LOW-MTP file and explicit recipe/default choices");
    inspected = { ...inspected, file_hint: "missing-IQ4_XS.gguf", variants: [inspected.variants[0]] };
    await act(async () => query.props.onChange({ target: { value: `https://huggingface.co/${repo_id}?show_file_info=missing-IQ4_XS.gguf` } }));
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

async function checkSavedCapabilities(ModelCapabilities) {
  let renderer, requests = 0, fail = false;
  const evidence = { id: "saved", capability: "tools", status: "passed", fingerprint: "setup-one", tested_at: "2026-09-22T10:00:00Z", observations: {}, note: "A real tool call completed." };
  let report = { current_fingerprint: "setup-one", current_support: { tools: "passed" }, evidence: [evidence], image_setup: { selected_projector: null, projector_present: null, runtime_support: false } };
  globalThis.fetch = async (_url, init = {}) => {
    requests++;
    if (fail) throw new Error("Service unavailable");
    if (init.method === "POST") { report = { ...report, current_support: { tools: "passed" }, evidence: [...report.evidence, { ...evidence, fingerprint: report.current_fingerprint }] }; return jsonResponse(report.evidence.at(-1)); }
    return jsonResponse(report);
  };
  const deployment = { id: "deployment", status: "running", health: { healthy: true }, scope: "managed", server_props: { modalities: { vision: false } } };
  const action = async (_key, operation) => operation();
  const row = label => renderer.root.findAllByType("li").find(node => node.findAllByType("strong").some(strong => textOf(strong) === label));
  try {
    await act(async () => { renderer = create(React.createElement(ModelCapabilities, { deployment, busy: "", action })); await tick(); });
    assert.ok(textOf(row("Tools")).includes("Verified"), "saved probe evidence hydrates without rerunning it");
    assert.equal(requests, 1);
    assert.ok(textOf(row("Vision")).includes("No vision file is loaded"));
    assert.equal(row("Vision").findAllByType("button").find(node => node.props["aria-label"] === "Test vision").props.disabled, true);
    assert.equal(row("Screenshot reading").findAllByType("button").find(node => node.props["aria-label"] === "Test screenshot reading").props.disabled, true);
    report = { ...report, current_fingerprint: "setup-two", current_support: { tools: "untested" } };
    await act(async () => { renderer.update(React.createElement(ModelCapabilities, { deployment: { ...deployment }, busy: "", action })); await tick(); });
    assert.ok(textOf(row("Tools")).includes("Needs retest"), "changed setup preserves old evidence but never calls it verified");
    await act(async () => { row("Tools").findByProps({ "aria-label": "Retest tools" }).props.onClick(); await tick(); });
    assert.ok(textOf(row("Tools")).includes("Verified"), "retest refreshes durable evidence from the service");
    fail = true;
    await act(async () => { renderer.update(React.createElement(ModelCapabilities, { deployment: { ...deployment }, busy: "", action })); await tick(); });
    assert.ok(textOf(renderer.root).includes("Saved results unavailable"), "fetch failures are visible instead of silently showing untested");
    assert.ok(!textOf(row("Tools")).includes("Verified"));
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
    assert.ok(renderer.root.findAllByType("button").some(node => textOf(node).startsWith("Download") && node.props.disabled === false), "one complete text variant is ready to download after inspection");
    await act(async () => renderer.root.findByProps({ id: "models-tab-downloads" }).props.onClick());
    await act(async () => renderer.root.findByProps({ id: "models-tab-add" }).props.onClick());
    assert.equal(renderer.root.findByProps({ id: "model-search-query" }).props.value, "model", "search text survives tab changes");
    assert.ok(textOf(renderer.root.findByProps({ "aria-label": "Repository files" })).includes("Q4_K_M"), "inspected selection survives tab changes");
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
      threads: { recommended: 8, options: [{ value: 8, label: "8 threads" }] },
      spec_type: { options: [{ value: "none", label: "Off" }, { value: "draft-mtp", label: "MTP" }] },
      spec_draft_n_max: { options: [{ value: 3, label: "3" }, { value: 6, label: "6" }] },
    },
    metadata: { architecture: "qwen", inspection_cached: true },
    per_request_defaults: { reasoning_effort: { supported: true, options: ["default", "low", "medium", "xhigh"].map(value => ({ value, label: value })) } },
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
