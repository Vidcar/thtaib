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

const vite = await createViteServer({ root: desktopRoot, appType: "custom", server: { middlewareMode: true, hmr: false }, logLevel: "error" });
try {
  const { RecoverySettingsPanel } = await vite.ssrLoadModule("/src/renderer/RecoverySettingsPanel.tsx");
  await checkPreferencesWaitForHydrationAndSave(RecoverySettingsPanel);
  await checkLateInitialRefreshCannotReplaceSavedPreferences(RecoverySettingsPanel);
  await checkBackupDestinationIsArchiveInsideTypedFolder(RecoverySettingsPanel);
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
    if (parsed.pathname === "/v1/permissions/grants") {
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
    if (parsed.pathname === "/v1/permissions/grants") {
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

async function checkBackupDestinationIsArchiveInsideTypedFolder(RecoverySettingsPanel) {
  const requests = [];
  globalThis.fetch = async (url, init = {}) => {
    const parsed = new URL(String(url));
    const request = { method: init.method ?? "GET", path: parsed.pathname, body: init.body ? JSON.parse(String(init.body)) : null };
    requests.push(request);

    if (parsed.pathname === "/v1/settings/presentation") {
      return jsonResponse({
        theme: "system",
        detailed_streams: false,
        attention_notifications: true,
        success_notifications: false,
      });
    }
    if (parsed.pathname === "/v1/permissions/grants") {
      return jsonResponse([]);
    }
    if (parsed.pathname === "/v1/work/active") {
      return jsonResponse({ active_run_ids: [] });
    }
    if (parsed.pathname === "/v1/backups" && request.method === "POST") {
      return jsonResponse({
        archive_path: request.body.destination,
        manifest: {
          format: "local-ai-workbench-backup",
          schema_version: 1,
          created_at: "2026-09-22T12:00:00Z",
          backup_id: "backup_test",
          source: {},
          counts: {},
          external_references: [],
        },
      });
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

  await submitBackup(renderer, "D:\\CodeProjects\\thtaib\\.scratch\\packet03-native-backups");
  const typedFolderRequest = backupRequests(requests).at(-1);
  assertNestedBackupArchive(
    typedFolderRequest.body.destination,
    "D:\\CodeProjects\\thtaib\\.scratch\\packet03-native-backups",
  );

  await submitBackup(renderer, "D:\\CodeProjects\\thtaib\\.scratch\\packet03-native-backups\\");
  const trailingSeparatorRequest = backupRequests(requests).at(-1);
  assertNestedBackupArchive(
    trailingSeparatorRequest.body.destination,
    "D:\\CodeProjects\\thtaib\\.scratch\\packet03-native-backups",
  );
  await act(async () => renderer.unmount());
}

async function submitBackup(renderer, destinationFolder) {
  const destination = inputByPlaceholder(renderer, "Choose a folder for the backup archive");
  await act(async () => {
    destination.props.onChange({ target: { value: destinationFolder } });
  });
  await act(async () => {
    button(renderer, "Create backup").props.onClick();
    await tick();
  });
}

function assertNestedBackupArchive(destination, folder) {
  assert.notEqual(destination, folder, "backup request must not send the folder path as the archive path");
  assert.ok(destination.startsWith(`${folder}\\`), `backup archive should be nested under typed folder, got ${destination}`);
  assert.match(destination, /local-ai-workbench-\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2}Z\.workbench-backup\.zip$/);
}

function backupRequests(requests) {
  return requests.filter((request) => request.method === "POST" && request.path === "/v1/backups");
}

function inputByPlaceholder(renderer, placeholder) {
  return renderer.root.find((node) => node.type === "input" && node.props.placeholder === placeholder);
}

function themeSelect(renderer) {
  return renderer.root.findByType("select");
}

function preferenceCheckboxes(renderer) {
  return renderer.root.findAll((node) => node.type === "input" && node.props.type === "checkbox" && node.props["data-appearance-guide"] == null);
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
