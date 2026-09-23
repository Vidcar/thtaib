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
  await checkModelsRenderBeforeDeferredRuntimeAndConfiguration(ModelsPanel);
  await checkSelectedModelOwnsDetails(ModelsPanel);
  await checkRepositorySelectionLoadsFiles(ModelsPanel);
  await checkRepositoryChoicesAndLateResults((await vite.ssrLoadModule("/src/renderer/HuggingFaceImport.tsx")).HuggingFaceImport);
  await checkPermanentDeletionPreview((await vite.ssrLoadModule("/src/renderer/ModelDeletion.tsx")).ModelDeletion);
  await checkSavedCapabilities((await vite.ssrLoadModule("/src/renderer/ModelCapabilities.tsx")).ModelCapabilities);
  await checkExplicitVisionSelection((await vite.ssrLoadModule("/src/renderer/ModelProjectorControls.tsx")).ModelProjectorControls);
} finally {
  await vite.close();
}

console.log("Models panel deferred loading checks passed.");

async function checkSelectedModelOwnsDetails(ModelsPanel) {
  const originalFetch = globalThis.fetch;
  let renderer;
  const deployment = { id: "gemma-live", bundle_id: "gemma", display_name: "managed:Gemma", scope: "managed", status: "running", health: { healthy: true }, applied_startup: {}, endpoint: "http://localhost:8080/v1" };
  globalThis.fetch = async url => {
    const address = String(url);
    if (address.endsWith("/v1/bundles")) return jsonResponse([bundle("qwen", "Selected Qwen"), bundle("gemma", "Loaded Gemma")]);
    if (address.endsWith("/v1/deployments")) return jsonResponse([deployment]);
    if (address.endsWith("/v1/profiles") || address.endsWith("/v1/imports")) return jsonResponse([]);
    if (address.endsWith("/v1/paths")) return jsonResponse({ models: "D:\\Models" });
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
    assert.ok(textOf(renderer.root).includes("256k context"), "deferred configuration result should hydrate model capacity");
    const speculation = renderer.root.findAllByType("select").find(select => select.props.id === "model-spec_type");
    assert.deepEqual(speculation.findAllByType("option").map(option => option.props.value), ["none", "draft-mtp"]);
    await act(async () => { speculation.props.onChange({ target: { value: "draft-mtp" } }); });
    assert.equal(renderer.root.findByProps({ id: "model-spec_draft_n_max" }).props.value, "3", "MTP exposes the runtime default draft count");
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
    await act(async () => renderer.root.findAllByType("select")[1].props.onChange({ target: { value: "vision" } }));
    download = renderer.root.findAllByType("button").find(node => textOf(node) === "Download model");
    await act(async () => { download.props.onClick(); download.props.onClick(); await tick(); });
    assert.deepEqual(downloads, [{ repo_id: "org/second", revision: "pinned-revision", allow_patterns: ["weights[[]4].gguf", "mmproj.gguf", "README.md"] }], "download pins the inspected revision and exact files, escaping glob syntax and deduplicating clicks");
    assert.equal(completions, 1);
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
    if (address.endsWith("/v1/runtime")) return jsonResponse(runtimeReady());
    if (address.endsWith("/v1/paths")) return jsonResponse({ models: "D:\\Models" });
    if (["/v1/bundles", "/v1/profiles", "/v1/deployments", "/v1/imports"].some(suffix => address.endsWith(suffix))) return jsonResponse([]);
    throw new Error(`unexpected fetch ${address}`);
  };
  let renderer;
  try {
    await act(async () => { renderer = create(React.createElement(ModelsPanel)); await tick(); });
    await act(async () => renderer.root.findAllByType("button").find(node => textOf(node) === "Add model").props.onClick());
    const query = renderer.root.findAllByType("input").find(node => node.props.maxLength === 200);
    await act(async () => query.props.onChange({ target: { value: "model" } }));
    const searchForm = renderer.root.findAllByType("form").find(node => node.findAllByType("input").some(input => input.props.maxLength === 200));
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
  } finally {
    if (renderer) await act(async () => renderer.unmount());
    globalThis.fetch = originalFetch;
  }
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
