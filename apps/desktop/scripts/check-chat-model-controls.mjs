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
  const { useDismissibleDetails } = await vite.ssrLoadModule("/src/renderer/useDismissibleDetails.ts");
  await checkPopoverDismissal(useDismissibleDetails);
  await checkCompactControls(ChatModelControls);
  await checkFetchedThinkingEffortOptions(ChatModelControls);
  await checkThinkingEffortLoadingAndDeploymentChange(ChatModelControls);
  await checkStoppedManagedCopy(ChatModelControls);
  await checkMissingThinkingEffortOptions(ChatModelControls);
  await checkUnsupportedThinkingEffort(ChatModelControls);
  await checkLoadedSettingsDoNotFollowSelectedProfile(ChatModelControls);
  await checkThinkingModesAndStaleModelFetch(ChatModelControls);
  await checkUnsupportedSavedThinkingReset(ChatModelControls);
  await checkInvalidLoadedThinkingCannotReset(ChatModelControls);
  await checkAcceptedThinkingAliasAndExplicitDefault(ChatModelControls);
  await checkAdaptiveThinkingControls(ChatModelControls);
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
  assert.equal(renderer.root.findByType("details").props.name, "chat-composer-controls", "model and tools use native mutually exclusive menus");
  const presetSelect = renderer.root.findByProps({ "aria-label": "Preset" });
  assert.equal(renderer.root.findByProps({ htmlFor: presetSelect.props.id }).type, "label", "Preset retains an explicit accessible label");
  let helpParent = renderer.root.findByProps({ "aria-label": "About presets" }).parent;
  while (helpParent) {
    assert.notEqual(helpParent.type, "label", "opening preset help must not activate the select through an enclosing label");
    helpParent = helpParent.parent;
  }
  assert.match(text, /Qwen/, "compact button should show selected model");
  assert.match(text, /Context32k tokens/, "context readout should use reported server context");
  assert.match(helpMessage(renderer, "About the loaded model"), /reported by the running model/, "loaded context provenance stays available without repeating it in the control");
  assert.equal(input(renderer, "range").props.value, 2, "thinking effort should come from selected profile per-request settings");
  assert.match(text, /Thinking limit1k tokens/, "thinking budget must show the loaded model, not the selected response preset");
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
        options: effortOptions(["low", "medium", "high"]),
      },
    },
  });
  let renderer;
  try {
    await act(async () => {
      renderer = create(React.createElement(ChatModelControls, {
        deployments: [deployment("dep_running", "managed:Gpt-oss", "running", { n_ctx: 32768 })],
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
    assert.equal(slider.props.max, 2, "fetched thinking slider should use only the selected model's reported levels");
    await act(async () => {
      slider.props.onChange({ target: { value: "2" } });
    });
    assert.deepEqual(changes.at(-1), { reasoning_effort: "high" }, "fetched options should emit the selected model's effort value");
    assert.equal(renderer.root.findByProps({ className: "chat-model-controls-efforts" }).children.length, 3,
      "unreported levels must not be added to the model's choices");
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
        perRequestOverrides: { reasoning_effort: "high" },
        onDeploymentChange: () => {},
        onProfileChange: () => {},
        onInheritDeploymentSettingsChange: () => {},
        onPerRequestOverridesChange: () => { throw new Error("missing thinking options should not emit changes"); },
      }));
    });
    await act(async () => {
      await Promise.resolve();
    });
    assert.match(helpMessage(renderer, "Thinking availability"), /no reported per-message thinking effort options/,
      "missing affirmative options should explain model-controlled thinking in help");
    assert.equal(renderer.root.findAll(node => node.type === "input" && node.props.type === "range").length, 0,
      "unverified thinking effort must not appear as a control");
    assert.equal(renderer.root.findAllByProps({ "aria-label": "Use model default thinking" }).length, 0,
      "missing capability evidence must not claim that a saved effort is unsupported");
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
  assert.match(helpMessage(renderer, "Thinking availability"), /reports that per-message thinking effort is unavailable/,
    "unsupported thinking effort should explain why it is unavailable in help");
  assert.equal(renderer.root.findAll(node => node.type === "input" && node.props.type === "range").length, 0,
    "unsupported thinking effort slider must be absent");
}

async function checkLoadedSettingsDoNotFollowSelectedProfile(ChatModelControls) {
  const loaded = deployment("dep_loaded", "managed:Loaded", "running", null);
  loaded.applied_startup = { ctx_size: 16384, reasoning_budget: 2048 };
  const props = {
    deployments: [loaded], profiles: [profile("new_preset", "Large next reply", { ctx_size: 65536, reasoning_budget: 8192 })],
    selectedDeploymentId: loaded.id, selectedProfileId: "", inheritDeploymentSettings: true,
    thinkingEffortOptions: effortOptions(["default", "low"]),
    onDeploymentChange() {}, onProfileChange() {}, onInheritDeploymentSettingsChange() {}, onPerRequestOverridesChange() {},
  };
  let renderer;
  try {
    await act(async () => { renderer = create(React.createElement(ChatModelControls, props)); });
    const before = renderer.root.findByProps({ className: "chat-model-controls-facts" });
    assert.match(textOf(before), /Context16k tokens/);
    assert.match(textOf(before), /Thinking limit2k tokens/);
    await act(async () => { renderer.update(React.createElement(ChatModelControls, { ...props, selectedProfileId: "new_preset" })); });
    const after = renderer.root.findByProps({ className: "chat-model-controls-facts" });
    assert.match(textOf(after), /Context16k tokens/, "selecting a response preset must not claim the loaded context changed");
    assert.match(textOf(after), /Thinking limit2k tokens/, "selecting a response preset must not claim the loaded budget changed");
    assert.doesNotMatch(textOf(after), /64k|8k/);
  } finally {
    if (renderer) await act(async () => renderer.unmount());
  }
}

async function checkThinkingModesAndStaleModelFetch(ChatModelControls) {
  const first = deferred();
  const changes = [];
  const restore = mockConfigurationOptionsForUrl(async (url) => {
    if (String(url).includes("deployment_id=dep_effort")) {
      await first.promise;
      return configurationOptions(effortOptions(["low", "medium", "high"]));
    }
    return { per_request_defaults: { reasoning: { options: [
      { value: "auto", label: "Model default" }, { value: "on", label: "On" }, { value: "off", label: "Off" },
    ] }, reasoning_effort: { options: [] } } };
  });
  const props = {
    deployments: [deployment("dep_effort", "managed:Effort model", "running", null), deployment("dep_mode", "managed:On-off model", "running", null)],
    profiles: [], selectedDeploymentId: "dep_effort", selectedProfileId: "", inheritDeploymentSettings: true,
    perRequestOverrides: { temperature: 0.7 },
    onDeploymentChange() {}, onProfileChange() {}, onInheritDeploymentSettingsChange() {},
    onPerRequestOverridesChange: value => changes.push(value),
  };
  let renderer;
  try {
    await act(async () => { renderer = create(React.createElement(ChatModelControls, props)); });
    await act(async () => { renderer.update(React.createElement(ChatModelControls, { ...props, selectedDeploymentId: "dep_mode" })); });
    const mode = () => renderer.root.findByProps({ "aria-label": "Thinking mode for this message" });
    assert.deepEqual(mode().findAllByType("option").map(node => node.props.value), ["default", "on", "off"]);
    assert.equal(renderer.root.findAll(node => node.type === "input" && node.props.type === "range").length, 0,
      "an on-off model must not offer effort levels");
    await act(async () => { first.resolve(); await first.promise; });
    assert.equal(renderer.root.findAll(node => node.type === "input" && node.props.type === "range").length, 0,
      "the old model's late response must not add unsupported effort levels to the new selection");
    assert.deepEqual(mode().findAllByType("option").map(node => node.props.value), ["default", "on", "off"]);
    for (const value of ["off", "on", "default"]) {
      await act(async () => mode().props.onChange({ target: { value } }));
      assert.deepEqual(changes.at(-1), { temperature: 0.7, reasoning: value === "default" ? "auto" : value },
        "thinking mode must preserve other overrides and explicitly reset to model default");
    }
  } finally {
    first.resolve();
    if (renderer) await act(async () => renderer.unmount());
    restore();
  }
}

async function checkUnsupportedSavedThinkingReset(ChatModelControls) {
  const changes = [];
  const restore = mockConfigurationOptions({ per_request_defaults: {
    reasoning_effort: { supported: false, source: "unavailable", options: [] },
    reasoning: { supported: false, source: "unavailable", options: [] },
  } });
  const props = {
    deployments: [deployment("dep_basic", "managed:Basic", "running", null)],
    profiles: [profile("old_preset", "Other model preset", {}, { reasoning_effort: "high", reasoning: "on" })],
    selectedDeploymentId: "dep_basic", selectedProfileId: "old_preset", inheritDeploymentSettings: true,
    perRequestOverrides: { temperature: 0.65, top_p: 0.85 },
    onDeploymentChange() {}, onProfileChange() {}, onInheritDeploymentSettingsChange() {},
    onPerRequestOverridesChange: value => changes.push(value),
  };
  let renderer;
  try {
    await act(async () => { renderer = create(React.createElement(ChatModelControls, props)); });
    assert.match(textOf(renderer.toJSON()), /Thinking settings don't match this model/,
      "a hidden unsupported inherited effort must have an actionable explanation");
    assert.equal(renderer.root.findAllByProps({ className: "thinking-chip" }).length, 0,
      "unsupported inherited thinking must not appear as an applied chip");
    assert.equal(renderer.root.findAll(node => node.type === "input" && node.props.type === "range").length, 0);
    const reset = renderer.root.findByProps({ "aria-label": "Use model default thinking" });
    await act(async () => reset.props.onClick());
    assert.deepEqual(changes.at(-1), { temperature: 0.65, top_p: 0.85, reasoning_effort: "default", reasoning: "auto" },
      "reset must explicitly override inherited thinking while preserving sampling");
    await act(async () => { renderer.update(React.createElement(ChatModelControls, { ...props, perRequestOverrides: changes.at(-1) })); });
    assert.doesNotMatch(textOf(renderer.toJSON()), /Thinking settings don't match this model/);
    assert.equal(renderer.root.findAllByProps({ className: "thinking-chip" }).length, 0);
  } finally {
    if (renderer) await act(async () => renderer.unmount());
    restore();
  }
}

async function checkInvalidLoadedThinkingCannotReset(ChatModelControls) {
  const restore = mockConfigurationOptions({ per_request_defaults: {
    reasoning_effort: { supported: false, source: "unavailable", options: [] },
  } });
  const loaded = deployment("dep_loaded_invalid", "managed:Basic", "running", null);
  loaded.applied_startup.reasoning_effort = "high";
  let renderer;
  try {
    await act(async () => { renderer = create(React.createElement(ChatModelControls, {
      deployments: [loaded], profiles: [], selectedDeploymentId: loaded.id, selectedProfileId: "", inheritDeploymentSettings: true,
      onDeploymentChange() {}, onProfileChange() {}, onInheritDeploymentSettingsChange() {},
      onPerRequestOverridesChange() { throw new Error("a message reset cannot repair loaded startup settings"); },
    })); });
    assert.match(textOf(renderer.toJSON()), /Loaded thinking needs attention/);
    assert.match(helpMessage(renderer, "Loaded thinking mismatch"), /Models.*reload/i);
    assert.equal(renderer.root.findAllByProps({ "aria-label": "Use model default thinking" }).length, 0,
      "reset to loaded default cannot repair an invalid loaded effort");
  } finally {
    if (renderer) await act(async () => renderer.unmount());
    restore();
  }
}

async function checkAcceptedThinkingAliasAndExplicitDefault(ChatModelControls) {
  const changes = [];
  const restore = mockConfigurationOptions({ per_request_defaults: {
    reasoning_effort: { supported: true, accepted_values: ["low", "medium", "xhigh", "high"], options: effortOptions(["default", "low", "medium", "xhigh"]) },
  } });
  const props = {
    deployments: [deployment("dep_alias", "managed:Template aliases", "running", null)],
    profiles: [profile("alias_preset", "Saved high", {}, { reasoning_effort: "high" })],
    selectedDeploymentId: "dep_alias", selectedProfileId: "alias_preset", inheritDeploymentSettings: true,
    perRequestOverrides: { temperature: 0.45 },
    onDeploymentChange() {}, onProfileChange() {}, onInheritDeploymentSettingsChange() {},
    onPerRequestOverridesChange: value => changes.push(value),
  };
  let renderer;
  try {
    await act(async () => { renderer = create(React.createElement(ChatModelControls, props)); });
    assert.doesNotMatch(textOf(renderer.toJSON()), /Thinking settings don't match this model/,
      "a template-confirmed alias must not be called unsupported");
    assert.equal(textOf(renderer.root.findByProps({ className: "thinking-chip" })), "High",
      "the applied alias must not be mislabeled as model default");
    assert.equal(input(renderer, "range").props.value, 4, "the slider must represent the applied valid alias");
    await act(async () => input(renderer, "range").props.onChange({ target: { value: "0" } }));
    assert.deepEqual(changes.at(-1), { temperature: 0.45, reasoning_effort: "default" },
      "choosing default must override the inherited effort rather than inherit it again");
    await act(async () => { renderer.update(React.createElement(ChatModelControls, { ...props, perRequestOverrides: { temperature: 0.45, reasoning_effort: "max" } })); });
    assert.match(textOf(renderer.toJSON()), /Thinking settings don't match this model/,
      "a proven closed template must identify unaccepted inherited or explicit levels");
    assert.equal(renderer.root.findAllByProps({ className: "thinking-chip" }).length, 0);
  } finally {
    if (renderer) await act(async () => renderer.unmount());
    restore();
  }
}

async function checkAdaptiveThinkingControls(ChatModelControls) {
  const changes = [];
  const restore = mockConfigurationOptions({ per_request_defaults: {
    reasoning_effort: { supported: true, accepted_values: ["low", "medium", "high"], options: effortOptions(["default", "low", "medium", "high"]) },
    reasoning: { supported: true, options: [{ value: "auto", label: "Model default" }, { value: "on", label: "On" }, { value: "off", label: "Off" }] },
  } });
  const selected = deployment("dep_adaptive", "managed:Adaptive", "running", { n_ctx: 65536 });
  selected.applied_startup = {};
  const props = {
    deployments: [selected], profiles: [], selectedDeploymentId: selected.id, selectedProfileId: "", inheritDeploymentSettings: true,
    perRequestOverrides: { temperature: 0.4, reasoning_effort: "high" },
    onDeploymentChange() {}, onProfileChange() {}, onInheritDeploymentSettingsChange() {},
    onPerRequestOverridesChange: value => changes.push(value),
  };
  let renderer;
  try {
    await act(async () => { renderer = create(React.createElement(ChatModelControls, props)); });
    assert.equal(input(renderer, "range").props["aria-valuetext"], "High", "keyboard and screen reader users get the named effort level");
    assert.doesNotMatch(textOf(renderer.root.findByProps({ className: "chat-model-controls-facts" })), /Default|Endpoint|Thinking limit/,
      "unknown/default load facts do not fill the popover with status cards");
    const mode = () => renderer.root.findByProps({ "aria-label": "Thinking mode for this message" });
    await act(async () => mode().props.onChange({ target: { value: "off" } }));
    assert.deepEqual(changes.at(-1), { temperature: 0.4, reasoning_effort: "high", reasoning: "off" }, "turning thinking off preserves the chosen effort for later reuse");
    await act(async () => { renderer.update(React.createElement(ChatModelControls, { ...props, perRequestOverrides: changes.at(-1) })); });
    assert.equal(renderer.root.findAll(node => node.type === "input" && node.props.type === "range").length, 0, "thinking off hides the irrelevant effort slider");
    assert.equal(textOf(renderer.root.findByProps({ className: "thinking-chip" })), "Thinking off", "the trigger reports the actual mode instead of a dormant effort");
    await act(async () => mode().props.onChange({ target: { value: "on" } }));
    await act(async () => { renderer.update(React.createElement(ChatModelControls, { ...props, perRequestOverrides: changes.at(-1) })); });
    assert.equal(input(renderer, "range").props["aria-valuetext"], "High", "reenabling thinking retains its chosen effort");
    await act(async () => { renderer.update(React.createElement(ChatModelControls, { ...props, perRequestOverrides: {} })); });
    assert.equal(renderer.root.findAllByProps({ className: "thinking-chip" }).length, 0, "model-default thinking does not add a redundant Default badge");
  } finally {
    if (renderer) await act(async () => renderer.unmount());
    restore();
  }
}

function effortOptions(values) {
  return values.map((value) => ({ value, label: value === "default" ? "Default" : value[0].toUpperCase() + value.slice(1) }));
}

async function checkPopoverDismissal(useDismissibleDetails) {
  const originalDocument = globalThis.document;
  const listeners = new Map();
  let focusCount = 0;
  const inside = {};
  const menu = {
    open: true,
    contains: target => target === inside,
    querySelectorAll: () => [{ getAttribute: () => "description own-help" }],
    querySelector: () => ({ focus: () => { focusCount += 1; } }),
  };
  globalThis.document = {
    addEventListener: (name, handler) => listeners.set(name, handler),
    removeEventListener: name => listeners.delete(name),
  };
  function Fixture() { return React.createElement("details", { ref: useDismissibleDetails() }); }
  let renderer;
  try {
    await act(async () => { renderer = create(React.createElement(Fixture), { createNodeMock: () => menu }); });
    listeners.get("pointerdown")({ target: inside });
    assert.equal(menu.open, true, "clicking controls inside the menu keeps it open");
    listeners.get("pointerdown")({ target: { closest: () => ({ id: "own-help" }) } });
    assert.equal(menu.open, true, "the menu owns its portalled help via aria-describedby");
    listeners.get("pointerdown")({ target: { closest: () => ({ id: "another-control-help" }) } });
    assert.equal(menu.open, false, "an unrelated help popover remains an outside click");
    assert.equal(focusCount, 0, "outside clicks keep focus at their new destination");
    menu.open = true;
    listeners.get("pointerdown")({ target: {} });
    assert.equal(menu.open, false, "clicking the conversation dismisses the menu");
    menu.open = true;
    listeners.get("keydown")({ key: "ArrowRight" });
    assert.equal(menu.open, true, "normal keyboard control input is unaffected");
    let prevented = false;
    listeners.get("keydown")({ key: "Escape", preventDefault: () => { prevented = true; } });
    assert.equal(menu.open, false);
    assert.equal(focusCount, 1, "Escape returns focus to the menu summary");
    assert.equal(prevented, true);
    await act(async () => renderer.unmount());
    renderer = null;
    assert.equal(listeners.size, 0, "closing the component removes document listeners");
  } finally {
    if (renderer) await act(async () => renderer.unmount());
    globalThis.document = originalDocument;
  }
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
    const target = new URL(String(url));
    assert.equal(target.pathname, "/v1/bundles/bundle_1/configuration-options");
    assert.match(target.searchParams.get("deployment_id") ?? "", /^dep_/, "component should fetch configuration-options for the selected deployment bundle");
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

function helpMessage(renderer, title) {
  assert.ok(renderer.root.findAll(node => node.type === "button" && node.props["aria-label"] === title).length,
    "the explanation must have a named keyboard-accessible trigger");
  const help = renderer.root.findAll(node => typeof node.type === "function" && node.type.name === "HoverHelp" && node.props.title === title);
  assert.equal(help.length, 1);
  return String(help[0].props.children);
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
