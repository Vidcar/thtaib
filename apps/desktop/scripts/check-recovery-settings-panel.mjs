import assert from "node:assert/strict";
import path from "node:path";
import { fileURLToPath } from "node:url";

import React from "react";
import { act, create } from "react-test-renderer";
import { createServer as createViteServer } from "vite";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;
globalThis.window = { workbench: { backendUrl: "http://127.0.0.1:8000" } };

const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../..");
const desktopRoot = path.join(repoRoot, "apps/desktop");

let appearanceTokens = [];
const vite = await createViteServer({ root: desktopRoot, appType: "custom", server: { middlewareMode: true, hmr: false }, logLevel: "error" });
try {
  const { RecoverySettingsPanel } = await vite.ssrLoadModule("/src/renderer/RecoverySettingsPanel.tsx");
  ({ appearanceTokens } = await vite.ssrLoadModule("/src/renderer/appearanceCatalog.ts"));
  await checkPreferencesWaitForHydrationAndSave(RecoverySettingsPanel);
  await checkLateInitialRefreshCannotReplaceSavedPreferences(RecoverySettingsPanel);
  await checkSettingsCategoriesHaveNoBackup(RecoverySettingsPanel);
} finally {
  await vite.close();
}

console.log("Recovery settings panel checks passed.");

async function checkPreferencesWaitForHydrationAndSave(RecoverySettingsPanel) {
  const requests = [];
  const presentationDeferred = createDeferred();
  const manualRefreshDeferred = createDeferred();
  const saveDeferred = createDeferred();
  let presentationGets = 0;
  globalThis.fetch = async (url, init = {}) => {
    const parsed = new URL(String(url));
    const request = { method: init.method ?? "GET", path: parsed.pathname, body: init.body ? JSON.parse(String(init.body)) : null };
    requests.push(request);

    if (parsed.pathname === "/v1/settings/presentation" && request.method === "GET") {
      presentationGets += 1;
      return presentationGets === 1 ? presentationDeferred.promise : manualRefreshDeferred.promise;
    }
    if (parsed.pathname === "/v1/settings/presentation" && request.method === "PATCH") {
      return saveDeferred.promise;
    }
    if (parsed.pathname === "/v1/settings/grants") {
      return jsonResponse([]);
    }
    if (parsed.pathname === "/v1/work/active") {
      return jsonResponse({ active_run_ids: [] });
    }
    throw new Error(`unexpected request ${request.method} ${parsed.pathname}`);
  };

  let renderer;
  await act(async () => {
    renderer = create(React.createElement(RecoverySettingsPanel));
    await tick();
  });

  assert.equal(themeSelect(renderer).props.value, "system", "fallback value can render before preferences load");
  assert.equal(themeSelect(renderer).props.disabled, true, "theme select must be disabled until preferences hydrate");
  for (const checkbox of preferenceCheckboxes(renderer)) {
    assert.equal(checkbox.props.disabled, true, "preference toggles must be disabled until preferences hydrate");
  }

  await act(async () => {
    presentationDeferred.resolve(jsonResponse({
      theme: "light",
      detailed_streams: true,
      attention_notifications: false,
      success_notifications: true,
    }));
    await flush();
  });

  assert.equal(themeSelect(renderer).props.value, "light", "hydrated preferences should replace fallback");
  assert.equal(themeSelect(renderer).props.disabled, false, "theme select should enable after successful hydration");
  const advancedRows = () => renderer.root.findAll(node => node.type === "div" && node.props.className === "appearance-row");
  assert.equal(advancedRows().length, 0, "advanced token editors stay closed during ordinary Settings use");
  assert.ok(renderer.root.findByProps({ "aria-label": "Density" }), "basic density choice remains directly available");
  await act(async () => button(renderer, "Customize appearance").props.onClick());
  assert.equal(advancedRows().length, appearanceTokens.length, "explicit customization retains the complete appearance catalogue");
  await act(async () => button(renderer, "Hide advanced controls").props.onClick());
  assert.equal(advancedRows().length, 0);

  const refreshCountBefore = requests.filter((request) => request.method === "GET" && request.path === "/v1/settings/presentation").length;
  await act(async () => {
    const refresh = button(renderer, "Refresh");
    refresh.props.onClick();
    refresh.props.onClick();
    await flush();
  });
  const refreshCountAfter = requests.filter((request) => request.method === "GET" && request.path === "/v1/settings/presentation").length;
  assert.equal(refreshCountAfter, refreshCountBefore + 1, "same-tick refresh attempts should share one in-flight owner");
  await act(async () => {
    manualRefreshDeferred.resolve(jsonResponse({
      theme: "light",
      detailed_streams: true,
      attention_notifications: false,
      success_notifications: true,
    }));
    await flush();
  });
  await waitFor(() => themeSelect(renderer).props.disabled === false);

  await act(async () => {
    themeSelect(renderer).props.onChange({ target: { value: "dark" } });
    await flush();
  });
  const saveRequest = requests.find((request) => request.method === "PATCH" && request.path === "/v1/settings/presentation");
  assert.deepEqual(saveRequest.body, {
    theme: "dark",
  }, "save should send only the changed preference field");
  assert.equal(themeSelect(renderer).props.disabled, true, "preference controls should lock while save is pending");

  await act(async () => {
    saveDeferred.resolve(jsonResponse({
      theme: "dark",
      detailed_streams: true,
      attention_notifications: false,
      success_notifications: true,
    }));
    await flush();
  });
  assert.equal(themeSelect(renderer).props.value, "dark");
  assert.equal(themeSelect(renderer).props.disabled, false, "preference controls should re-enable after save completes");
  globalThis.fetch = async () => jsonResponse({ error: "Preference storage unavailable" }, 503);
  await act(async () => {
    themeSelect(renderer).props.onChange({ target: { value: "system" } });
    await flush();
  });
  assert.equal(themeSelect(renderer).props.value, "dark", "failed save restores the durable preference");
  assert.equal(themeSelect(renderer).props.disabled, false);
  assert.ok(renderer.root.findAll((node) => node.props.role === "status")
    .some((node) => textOf(node).includes("Preference storage unavailable")), "failed save remains visible");
  await act(async () => renderer.unmount());
}

async function checkLateInitialRefreshCannotReplaceSavedPreferences(RecoverySettingsPanel) {
  const firstPresentation = createDeferred();
  let presentationGets = 0;
  const requests = [];
  globalThis.fetch = async (url, init = {}) => {
    const parsed = new URL(String(url));
    const request = { method: init.method ?? "GET", path: parsed.pathname, body: init.body ? JSON.parse(String(init.body)) : null };
    requests.push(request);

    if (parsed.pathname === "/v1/settings/presentation" && request.method === "GET") {
      presentationGets += 1;
      return firstPresentation.promise;
    }
    if (parsed.pathname === "/v1/settings/presentation" && request.method === "PATCH") {
      assert.deepEqual(request.body, { theme: "dark" });
      return jsonResponse({
        theme: "dark",
        detailed_streams: true,
        attention_notifications: false,
        success_notifications: true,
      });
    }
    if (parsed.pathname === "/v1/settings/grants") {
      return jsonResponse([]);
    }
    if (parsed.pathname === "/v1/work/active") {
      return jsonResponse({ active_run_ids: [] });
    }
    throw new Error(`unexpected request ${request.method} ${parsed.pathname}`);
  };

  let renderer;
  await act(async () => {
    renderer = create(React.createElement(RecoverySettingsPanel));
    await tick();
  });

  await act(async () => {
    button(renderer, "Refresh").props.onClick();
    button(renderer, "Refresh").props.onClick();
    await tick();
  });
  assert.equal(presentationGets, 1, "same-tick initial refresh attempts should not create stale duplicate loads");

  await act(async () => {
    firstPresentation.resolve(jsonResponse({
      theme: "light",
      detailed_streams: true,
      attention_notifications: false,
      success_notifications: true,
    }));
    await flush();
  });
  assert.equal(themeSelect(renderer).props.value, "light");

  await act(async () => {
    themeSelect(renderer).props.onChange({ target: { value: "dark" } });
    await flush();
  });
  const saveRequest = requests.find((request) => request.method === "PATCH" && request.path === "/v1/settings/presentation");
  assert.deepEqual(saveRequest.body, { theme: "dark" });
  assert.equal(themeSelect(renderer).props.value, "dark", "saved preference should be visible immediately after save response");
  await act(async () => renderer.unmount());
}

async function checkSettingsCategoriesHaveNoBackup(RecoverySettingsPanel) {
  globalThis.fetch = async (url, init = {}) => {
    const parsed = new URL(String(url));
    const request = { method: init.method ?? "GET", path: parsed.pathname, body: init.body ? JSON.parse(String(init.body)) : null };
    if (parsed.pathname === "/v1/settings/presentation") {
      return jsonResponse({
        theme: "system",
        detailed_streams: false,
        attention_notifications: true,
        success_notifications: false,
      });
    }
    if (parsed.pathname === "/v1/settings/grants") {
      return jsonResponse([]);
    }
    throw new Error(`unexpected request ${request.method} ${parsed.pathname}`);
  };

  let renderer;
  await act(async () => {
    renderer = create(React.createElement(RecoverySettingsPanel));
    await tick();
  });
  await act(async () => {
    await tick();
  });

  const nav = renderer.root.find((node) => node.type === "nav" && node.props["aria-label"] === "Settings categories");
  const labels = nav.findAll((node) => node.type === "button").map((node) => textOf(node));
  assert.deepEqual(labels, ["Appearance", "Notifications", "Defaults", "Connections", "Permissions"]);
  const visible = textOf(renderer.root);
  assert.equal(visible.includes("Backup"), false, "Settings must not show a Backup section");
  assert.equal(visible.toLowerCase().includes("browser sign-in"), false, "Settings must not offer browser sign-in backup");
  assert.equal(renderer.root.findAll((node) => node.type === "button" && textOf(node).includes("Create backup")).length, 0);
  assert.equal(renderer.root.findAll((node) => node.type === "button" && textOf(node).includes("Restore")).length, 0);
  const howTo = "In Ask mode, choose Allow for this session or Always allow on an action's approval card to save it here. Approve once and Full access do not save permissions.";
  const permissionEmpty = renderer.root.findAll((node) => node.props?.className === "empty-state" && textOf(node.findByType("h3")) === "No saved permissions");
  assert.equal(permissionEmpty.length, 1, "an empty grants list shows No saved permissions");
  assert.equal(renderedText(renderer.root).includes(howTo), false, "the permissions how-to is not visible text");
  const helps = renderer.root.findAll((node) => node.type?.name === "HoverHelp" && textOf(node).includes(howTo));
  assert.equal(helps.length, 1, "the permissions how-to stays in one hover");
  assert.equal(helps[0].props.title, "Saved permissions");
  await act(async () => renderer.unmount());
}

function renderedText(node) {
  if (node == null || typeof node === "boolean") return "";
  if (typeof node === "string" || typeof node === "number") return String(node);
  if (Array.isArray(node)) return node.map((item) => renderedText(item)).join("");
  if (node.children) return renderedText(node.children);
  return "";
}

function themeSelect(renderer) {
  const group = renderer.root.find((node) => node.type === "div" && node.props.role === "radiogroup" && textOf(node).includes("System") && textOf(node).includes("Light"));
  const radios = group.findAll((node) => node.type === "input" && node.props.type === "radio");
  assert.deepEqual(radios.map((radio) => radio.props.value), ["system", "dark", "light"], "theme is a three-way segmented choice");
  const disabled = Boolean(group.props["aria-disabled"]);
  assert.ok(radios.every((radio) => Boolean(radio.props.disabled) === disabled), "every theme option shares the group's disabled state");
  return { props: {
    value: radios.find((radio) => radio.props.checked)?.props.value,
    disabled,
    onChange: (event) => radios.find((radio) => radio.props.value === event.target.value).props.onChange(event),
  } };
}

function preferenceCheckboxes(renderer) {
  const controls = renderer.root.findAll((node) => node.type === "button" && node.props.role === "switch");
  assert.equal(controls.length, 3, "all three boolean preferences use independent switches");
  return controls;
}

function button(renderer, text) {
  const matches = renderer.root.findAll((node) => node.type === "button" && textOf(node).includes(text));
  assert.equal(matches.length, 1, `expected one button containing ${text}, found ${matches.length}`);
  return matches[0];
}

function textOf(node) {
  if (typeof node === "string") return node;
  if (!node?.props?.children) return "";
  return React.Children.toArray(node.props.children).map((child) => typeof child === "string" ? child : textOf(child)).join("");
}

function jsonResponse(body, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
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

function tick() {
  return new Promise((resolve) => setTimeout(resolve, 0));
}

async function flush() {
  await tick();
  await tick();
  await tick();
  await tick();
}

async function waitFor(predicate) {
  for (let attempt = 0; attempt < 10; attempt += 1) {
    if (predicate()) return;
    await act(async () => {
      await flush();
    });
  }
  assert.ok(predicate(), "condition did not become true");
}
