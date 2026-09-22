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
} finally {
  await vite.close();
}

console.log("Models panel deferred loading checks passed.");

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
    assert.deepEqual(renderer.root.findByProps({ id: "model-reasoning_effort" }).findAllByType("option").map(option => option.props.value), ["", "low", "medium", "xhigh"], "Only model-specific thinking levels are offered");
  } finally {
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
