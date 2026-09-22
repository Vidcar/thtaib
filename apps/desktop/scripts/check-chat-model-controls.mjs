import assert from "node:assert/strict";
import path from "node:path";
import { fileURLToPath } from "node:url";

import React from "react";
import { act, create } from "react-test-renderer";
import { createServer as createViteServer } from "vite";

const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../..");
const desktopRoot = path.join(repoRoot, "apps/desktop");

globalThis.IS_REACT_ACT_ENVIRONMENT = true;
globalThis.window = { workbench: { backendUrl: "http://chat-model-controls.test" } };

const vite = await createViteServer({ root: desktopRoot, appType: "custom", server: { middlewareMode: true, hmr: false }, logLevel: "error" });
try {
  const { ChatModelControls } = await vite.ssrLoadModule("/src/renderer/ChatModelControls.tsx");
  await checkCompactControls(ChatModelControls);
  await checkFetchedThinkingEffortOptions(ChatModelControls);
  await checkThinkingEffortLoadingAndDeploymentChange(ChatModelControls);
  await checkStoppedManagedCopy(ChatModelControls);
  await checkMissingThinkingEffortOptions(ChatModelControls);
  await checkUnsupportedThinkingEffort(ChatModelControls);
} finally {
  await vite.close();
}

console.log("Chat model controls checks passed.");

async function checkCompactControls(ChatModelControls) {
  const changes = [];
  let renderer;
  await act(async () => {
    renderer = create(React.createElement(ChatModelControls, {
      deployments: [deployment("dep_running", "managed:Qwen", "running", { n_ctx: 32768 })],
      profiles: [profile("profile_deep", "Deep thinking", { reasoning_budget: 4096 }, { reasoning: "on", reasoning_effort: "high" })],
      selectedDeploymentId: "dep_running",
      selectedProfileId: "profile_deep",
      inheritDeploymentSettings: true,
      perRequestOverrides: {},
      thinkingEffortOptions: effortOptions(["default", "low", "high"]),
      onDeploymentChange: (value) => changes.push(["deployment", value]),
      onProfileChange: (value) => changes.push(["profile", value]),
      onInheritDeploymentSettingsChange: (value) => changes.push(["inherit", value]),
      onPerRequestOverridesChange: (value) => changes.push(["overrides", value]),
    }));
  });

  const text = textOf(renderer.toJSON());
  assert.match(text, /Qwen/, "compact button should show selected model");
  assert.match(text, /32k tokens reported by server/, "context readout should use reported server context");
  assert.match(text, /Thinking effortHigh/, "thinking effort readout should come from selected profile per-request settings");
  assert.match(text, /4k tokens/, "thinking budget readout should reflect selected profile startup settings");
  const slider = input(renderer, "range");
  assert.equal(slider.props.disabled, false, "supported thinking effort slider should be functional");
  await act(async () => {
    slider.props.onChange({ target: { value: "2" } });
  });
  assert.deepEqual(changes.at(-1), ["overrides", { reasoning_effort: "high" }], "thinking effort slider should emit per-request overrides");

  await act(async () => {
    selects(renderer)[1].props.onChange({ target: { value: "!none" } });
  });
  assert.deepEqual(changes.slice(-2), [["profile", "!none"], ["inherit", false]], "No preset option should clear preset inheritance");
}

async function checkFetchedThinkingEffortOptions(ChatModelControls) {
  const changes = [];
  const restore = mockConfigurationOptions({
    per_request_defaults: {
      reasoning_effort: {
        options: effortOptions(["default", "minimal", "low", "medium", "high", "xhigh", "max"]),
      },
    },
  });
  let renderer;
  try {
    await act(async () => {
      renderer = create(React.createElement(ChatModelControls, {
        deployments: [deployment("dep_running", "managed:Qwen", "running", { n_ctx: 32768 })],
        profiles: [],
        selectedDeploymentId: "dep_running",
        selectedProfileId: "",
        inheritDeploymentSettings: true,
        perRequestOverrides: {},
        onDeploymentChange: () => {},
        onProfileChange: () => {},
        onInheritDeploymentSettingsChange: () => {},
        onPerRequestOverridesChange: (value) => changes.push(value),
      }));
    });
    await act(async () => {
      await Promise.resolve();
    });
    const slider = input(renderer, "range");
    assert.equal(slider.props.disabled, false, "configuration-options effort values should enable the thinking slider");
    assert.equal(slider.props.max, 6, "fetched thinking slider should use the runtime-reported effort count");
    await act(async () => {
      slider.props.onChange({ target: { value: "5" } });
    });
    assert.deepEqual(changes.at(-1), { reasoning_effort: "xhigh" }, "fetched options should emit the selected runtime effort value");
  } finally {
    restore();
  }
}

async function checkThinkingEffortLoadingAndDeploymentChange(ChatModelControls) {
  const first = deferred();
  const second = deferred();
  const restore = mockConfigurationOptionsForUrl(async (url) => {
    if (String(url).includes("deployment_id=dep_first")) {
      await first.promise;
      return configurationOptions(effortOptions(["default", "low"]));
    }
    if (String(url).includes("deployment_id=dep_second")) {
      await second.promise;
      return configurationOptions(effortOptions(["default", "high"]));
    }
    throw new Error(`unexpected url ${url}`);
  });
  let renderer;
  const props = (selectedDeploymentId) => ({
    deployments: [
      deployment("dep_first", "managed:First", "running", { n_ctx: 8192 }),
      deployment("dep_second", "managed:Second", "running", { n_ctx: 8192 }),
    ],
    profiles: [],
    selectedDeploymentId,
    selectedProfileId: "",
    inheritDeploymentSettings: true,
    perRequestOverrides: {},
    onDeploymentChange: () => {},
    onProfileChange: () => {},
    onInheritDeploymentSettingsChange: () => {},
    onPerRequestOverridesChange: () => {},
  });
  try {
    await act(async () => {
      renderer = create(React.createElement(ChatModelControls, props("dep_first")));
    });
    assert.match(textOf(renderer.toJSON()), /Loading options/, "slow configuration-options should show loading rather than unavailable");
    assert.equal(input(renderer, "range").props.disabled, true, "loading effort options should keep slider disabled");
    await act(async () => {
      first.resolve();
      await first.promise;
    });
    assert.equal(input(renderer, "range").props.disabled, false, "resolved effort options should enable slider");
    await act(async () => {
      renderer.update(React.createElement(ChatModelControls, props("dep_second")));
    });
    assert.match(textOf(renderer.toJSON()), /Loading options/, "deployment change should clear old effort options while loading the new setup");
    assert.equal(input(renderer, "range").props.disabled, true, "old fetched options must not stay enabled after deployment changes");
    await act(async () => {
      second.resolve();
      await second.promise;
    });
    assert.equal(input(renderer, "range").props.disabled, false, "new deployment effort options should enable after fetch");
    assert.match(textOf(renderer.toJSON()), /High/, "new deployment options should replace previous effort labels");
  } finally {
    restore();
  }
}

async function checkStoppedManagedCopy(ChatModelControls) {
  let renderer;
  await act(async () => {
    renderer = create(React.createElement(ChatModelControls, {
      deployments: [deployment("dep_stopped", "managed:Saved setup", "stopped", null)],
      profiles: [],
      selectedDeploymentId: "dep_stopped",
      selectedProfileId: "",
      inheritDeploymentSettings: true,
      perRequestOverrides: {},
      thinkingEffortOptions: effortOptions(["default", "low"]),
      locked: true,
      onDeploymentChange: () => {},
      onProfileChange: () => {},
      onInheritDeploymentSettingsChange: () => {},
      onPerRequestOverridesChange: () => {},
    }));
  });
  const text = textOf(renderer.toJSON());
  assert.match(text, /Loads when sent/, "stopped managed deployment should be presented as load-on-send");
  assert.equal(selects(renderer)[0].props.disabled, true, "locked saved conversation disables model changes");
  assert.equal(input(renderer, "range").props.disabled, false, "locked saved conversation still allows supported per-request thinking changes");
}

async function checkMissingThinkingEffortOptions(ChatModelControls) {
  const restore = mockConfigurationOptions({ per_request_defaults: {} });
  let renderer;
  try {
    await act(async () => {
      renderer = create(React.createElement(ChatModelControls, {
        deployments: [deployment("dep_basic", "managed:Basic", "running", { n_ctx: 8192 })],
        profiles: [],
        selectedDeploymentId: "dep_basic",
        selectedProfileId: "",
        inheritDeploymentSettings: true,
        perRequestOverrides: {},
        onDeploymentChange: () => {},
        onProfileChange: () => {},
        onInheritDeploymentSettingsChange: () => {},
        onPerRequestOverridesChange: () => { throw new Error("missing thinking options should not emit changes"); },
      }));
    });
    await act(async () => {
      await Promise.resolve();
    });
    assert.match(textOf(renderer.toJSON()), /no reported per-message thinking effort options/, "missing affirmative options should disable thinking effort");
    assert.equal(input(renderer, "range").props.disabled, true, "missing thinking effort options disables slider");
  } finally {
    restore();
  }
}

async function checkUnsupportedThinkingEffort(ChatModelControls) {
  let renderer;
  await act(async () => {
    renderer = create(React.createElement(ChatModelControls, {
      deployments: [deployment("dep_basic", "managed:Basic", "running", { n_ctx: 8192 }, { unsupported: ["reasoning_effort"] })],
      profiles: [],
      selectedDeploymentId: "dep_basic",
      selectedProfileId: "",
      inheritDeploymentSettings: true,
      perRequestOverrides: {},
      thinkingEffortOptions: effortOptions(["default", "low"]),
      onDeploymentChange: () => {},
      onProfileChange: () => {},
      onInheritDeploymentSettingsChange: () => {},
      onPerRequestOverridesChange: () => { throw new Error("unsupported thinking effort should not emit changes"); },
    }));
  });
  assert.match(textOf(renderer.toJSON()), /reports that per-message thinking effort is unavailable/, "unsupported thinking effort should explain why slider is unavailable");
  assert.equal(input(renderer, "range").props.disabled, true, "unsupported thinking effort slider is disabled");
}

function effortOptions(values) {
  return values.map((value) => ({ value, label: value === "default" ? "Default" : value[0].toUpperCase() + value.slice(1) }));
}

function mockConfigurationOptions(body) {
  return mockConfigurationOptionsForUrl(async () => ({
    bundle_id: "bundle_1",
    deployment_id: "dep_running",
    ...body,
  }));
}

function mockConfigurationOptionsForUrl(handler) {
  const previous = globalThis.fetch;
  globalThis.fetch = async (url) => {
    assert.match(String(url), /\/v1\/bundles\/bundle_1\/configuration-options\?deployment_id=dep_/, "component should fetch configuration-options for the selected deployment bundle");
    return {
      ok: true,
      json: async () => handler(url),
    };
  };
  return () => {
    globalThis.fetch = previous;
  };
}

function configurationOptions(options) {
  return {
    bundle_id: "bundle_1",
    deployment_id: "dep_running",
    per_request_defaults: {
      reasoning_effort: { options },
    },
  };
}

function deferred() {
  let resolve;
  const promise = new Promise((done) => {
    resolve = done;
  });
  return { promise, resolve };
}

function deployment(id, displayName, status, serverProps, perRequestOptions = {}) {
  return {
    id,
    display_name: displayName,
    scope: "managed",
    status,
    bundle_id: "bundle_1",
    profile_id: null,
    endpoint: null,
    applied_startup: { reasoning_budget: 1024 },
    startup_overrides: {},
    settings: {
      startup: bag({ reasoning_budget: 1024 }),
      per_request: bag({}, perRequestOptions),
      agent: bag({}),
    },
    health: null,
    resource_usage: null,
    server_props: serverProps ? {
      fetched: "2026-09-21T00:00:00Z",
      source_url: "http://127.0.0.1:8080",
      build_info: "test",
      model_alias: displayName,
      model_path: "D:\\Models\\model.gguf",
      n_ctx: serverProps.n_ctx,
      total_slots: 1,
      modalities: {},
      chat_template_caps: {},
      chat_template: null,
      bos_token: null,
      eos_token: null,
    } : null,
    error: null,
  };
}

function profile(id, displayName, startup, perRequest = {}) {
  return {
    id,
    display_name: displayName,
    bundle_id: null,
    bags: {
      startup: bag(startup),
      per_request: bag(perRequest),
      agent: bag({}),
    },
  };
}

function bag(settings, options = {}) {
  return {
    requested: settings,
    applied: settings,
    unsupported: options.unsupported ?? [],
    overridden: [],
    unverified: [],
    retired: options.retired ?? [],
  };
}

function selects(renderer) {
  return renderer.root.findAll((node) => node.type === "select");
}

function input(renderer, type) {
  const found = renderer.root.findAll((node) => node.type === "input" && node.props.type === type);
  assert.ok(found.length > 0, `expected input ${type}`);
  return found[0];
}

function textOf(node) {
  if (typeof node === "string") {
    return node;
  }
  if (!node?.children) {
    return "";
  }
  return node.children.map(textOf).join("");
}
