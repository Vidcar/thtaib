import assert from "node:assert/strict";
import path from "node:path";
import { fileURLToPath } from "node:url";
import React from "react";
import { act, create } from "react-test-renderer";
import { createServer as createViteServer } from "vite";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;
const intervalCallbacks = new Map();
let nextIntervalId = 0;
globalThis.window = { workbench: { backendUrl: "http://visual-testing.test" }, setInterval: callback => { const id = ++nextIntervalId; intervalCallbacks.set(id, callback); return id; }, clearInterval: id => intervalCallbacks.delete(id) };
const desktopRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const calls = [];
let scope = { scope: "off", selected_window: null, stale: false };
let sessionState = "active";
let failWindows = false;
const previousFetch = globalThis.fetch;
globalThis.fetch = async (url, init = {}) => {
  const pathValue = new URL(String(url)).pathname;
  calls.push({ path: pathValue, method: init.method ?? "GET", body: init.body ? JSON.parse(init.body) : null });
  let value;
  if (pathValue === "/v1/browser/runtime") value = { supported: true, installed: true };
  else if (pathValue === "/v1/browser/sessions/thread_1") value = { thread_id: "thread_1", state: sessionState };
  else if (pathValue === "/v1/browser/sessions/thread_1/reset") value = { thread_id: "thread_1", state: "closed" };
  else if (pathValue === "/v1/window-testing/runtime") value = { available: true, installed: true };
  else if (pathValue === "/v1/window-testing/windows") { if (failWindows) throw new Error("Window list unavailable"); value = [{ hwnd: 42, title: "Fixture", process_name: "fixture.exe", process_id: 1234 }]; }
  else if (pathValue === "/v1/window-testing/conversations/chat_1/scope") {
    if (init.method === "PUT") { const body = JSON.parse(init.body); scope = { scope: body.scope, selected_window: body.hwnd ? { hwnd: body.hwnd, title: "Fixture", process_name: "fixture.exe", process_id: 1234 } : null, stale: false }; }
    value = scope;
  } else throw new Error(`Unexpected visual testing endpoint: ${pathValue}`);
  return { ok: true, json: async () => value };
};
function text(node) { return typeof node === "string" ? node : node?.children?.map(text).join("") ?? ""; }
function button(renderer, label) { const found = renderer.root.findAll(node => node.type === "button" && text(node).trim() === label)[0]; assert.ok(found, `Expected ${label}`); return found; }

const vite = await createViteServer({ root: desktopRoot, appType: "custom", server: { middlewareMode: true, hmr: false }, logLevel: "error" });
try {
  const { VisualTestingControls } = await vite.ssrLoadModule("/src/renderer/VisualTestingControls.tsx");
  const { browserToolNames, defaultNextTurnTools, desktopToolNames, effectiveNextTurnTools, withBrowserTools, withDesktopTools } = await vite.ssrLoadModule("/src/renderer/chatSetup.ts");
  const { scopedSetupConfiguration } = await vite.ssrLoadModule("/src/renderer/SetupConfigurationEditor.tsx");
  const browser = withBrowserTools(["grep"], true, true, false);
  assert.ok(browserToolNames.every(name => browser.includes(name)));
  assert.equal(browser.includes("read_file"), false, "Browser selection does not insert a file tool");
  assert.equal(withBrowserTools(withBrowserTools([], true, false, false), false, false, false).includes("read_file"), false, "Browser On then Off leaves no projectless file tool");
  const desktop = withDesktopTools(browser, true, true, false);
  assert.ok(desktopToolNames.every(name => desktop.includes(name)));
  assert.equal(desktop.includes("read_file"), false, "Windows selection does not insert a file tool");
  assert.deepEqual(effectiveNextTurnTools(["browser_navigate", "desktop_inspect", "execute", "grep", "task"], "plan"), ["grep", "task"], "Setup's Plan summary contains only tools the next Plan turn can use");
  assert.deepEqual(effectiveNextTurnTools(["browser_navigate", "execute"], "work"), ["browser_navigate", "execute"], "Work summary reflects selected capabilities");
  assert.deepEqual(defaultNextTurnTools(["echo", "read_file", "ls", "execute", "read_attachment", "browser_navigate"], false, false, false), ["echo"], "projectless default summary omits file, shell, attachment, and optional visual tools");
  assert.deepEqual(defaultNextTurnTools(["echo", "read_file", "ls", "execute", "read_attachment"], false, true, true), ["echo", "read_file", "ls", "read_attachment"], "next-turn default includes read routes and attachments only when available");
  assert.ok(browserToolNames.every(name => withDesktopTools(desktop, false, true, false).includes(name)), "revoking Windows keeps browser tools");
  assert.deepEqual(scopedSetupConfiguration({ instructions: "Research", presented_tools: desktop, desktop_access: "selected", approval_mode: "full_access" }, "agent"), { instructions: "Research" }, "saved agent setup cannot retain Chat capability or access grants");
  const windowChoices = [];
  let renderer;
  await act(async () => { renderer = create(React.createElement(VisualTestingControls, { conversationId: "chat_1", threadId: "thread_1", browserEnabled: false, onBrowserEnabled: () => {}, desktopAccess: "selected", onDesktopAccess: value => windowChoices.push(value), focusSection: "windows" })); });
  assert.match(text(renderer.toJSON()), /fresh Windows grant/, "reopened chat shows that its live grant is missing");
  await act(async () => button(renderer, "Choose window").props.onClick());
  await act(async () => button(renderer, "Use window").props.onClick());
  assert.deepEqual(windowChoices, ["selected", "selected"], "intended scope is selected before the live grant, then confirmed after grant");
  assert.ok(calls.some(call => call.method === "PUT" && call.body?.scope === "selected" && call.body?.hwnd === 42));
  await act(async () => renderer.root.findAll(node => node.type === "button" && node.props.className === "visual-testing-disclosure")[0].props.onClick());
  await act(async () => button(renderer, "Reset").props.onClick());
  assert.ok(calls.some(call => call.path === "/v1/browser/sessions/thread_1/reset"), "Browser recovery is available in the same capability menu");
  await act(async () => renderer.unmount());
  scope = { scope: "all", selected_window: null, stale: false };
  windowChoices.length = 0;
  await act(async () => { renderer = create(React.createElement(VisualTestingControls, { conversationId: "chat_1", threadId: "thread_1", browserEnabled: false, onBrowserEnabled: () => {}, desktopAccess: "all", onDesktopAccess: value => windowChoices.push(value), focusSection: "windows" })); });
  await act(async () => renderer.root.findByProps({ "aria-label": "Windows access" }).props.onChange({ target: { value: "selected" } }));
  assert.equal(scope.scope, "off", "All-windows grant is revoked before the selected-window picker opens");
  await act(async () => button(renderer, "Cancel").props.onClick());
  assert.equal(scope.scope, "off", "cancelling the picker never restores All-windows access");
  assert.deepEqual(windowChoices, ["selected"], "intended Selected state remains visible after cancellation");
  await act(async () => renderer.unmount());
  scope = { scope: "all", selected_window: null, stale: false };
  failWindows = true;
  await act(async () => { renderer = create(React.createElement(VisualTestingControls, { conversationId: "chat_1", threadId: "thread_1", browserEnabled: false, onBrowserEnabled: () => {}, desktopAccess: "all", onDesktopAccess: () => {}, focusSection: "windows" })); });
  await act(async () => renderer.root.findByProps({ "aria-label": "Windows access" }).props.onChange({ target: { value: "selected" } }));
  assert.equal(scope.scope, "off", "failed picker keeps the narrower live scope");
  assert.match(text(renderer.toJSON()), /Window list unavailable/, "picker failure is visible");
  await act(async () => renderer.unmount());
  failWindows = false;
  let prepared = 0;
  await act(async () => { renderer = create(React.createElement(VisualTestingControls, { conversationId: null, threadId: null, browserEnabled: false, onBrowserEnabled: () => {}, desktopAccess: "selected", onDesktopAccess: () => {}, onPrepareConversation: async () => { prepared += 1; }, focusSection: "windows" })); });
  assert.equal(renderer.root.findByProps({ "aria-label": "Windows access" }).props.disabled, false, "the intended scope remains editable before chat creation");
  await act(async () => button(renderer, "Create chat").props.onClick());
  assert.equal(prepared, 1);
  await act(async () => renderer.unmount());
  let readinessChanges = 0;
  sessionState = "active";
  await act(async () => { renderer = create(React.createElement(VisualTestingControls, { conversationId: "chat_1", threadId: "thread_1", browserEnabled: true, onBrowserEnabled: () => {}, desktopAccess: "off", onDesktopAccess: () => {}, onReadinessChange: () => { readinessChanges += 1; } })); });
  assert.equal(intervalCallbacks.size, 1, "runtime polling exists only while the tool menu row is mounted");
  const readyBaseline = readinessChanges;
  sessionState = "lost";
  await act(async () => { for (const poll of intervalCallbacks.values()) poll(); await Promise.resolve(); });
  assert.ok(readinessChanges > readyBaseline, "a Browser session lost after readiness refreshes Send preflight");
  const lostBaseline = readinessChanges;
  await act(async () => { for (const poll of intervalCallbacks.values()) poll(); await Promise.resolve(); });
  assert.equal(readinessChanges, lostBaseline, "unchanged runtime polls do not churn readiness");
  await act(async () => renderer.unmount());
  assert.equal(intervalCallbacks.size, 0, "closing the tool menu stops runtime polling");
  console.log("Visual testing grants and scoped setup checks passed.");
} finally { globalThis.fetch = previousFetch; await vite.close(); }
