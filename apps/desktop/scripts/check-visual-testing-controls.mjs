import assert from "node:assert/strict";
import path from "node:path";
import { fileURLToPath } from "node:url";
import React from "react";
import { act, create } from "react-test-renderer";
import { createServer as createViteServer } from "vite";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;
globalThis.window = { workbench: { backendUrl: "http://visual-testing.test" }, setInterval, clearInterval };
const desktopRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const calls = [];
let scope = { scope: "off", selected_window: null, stale: false };
const previousFetch = globalThis.fetch;
globalThis.fetch = async (url, init = {}) => {
  const pathValue = new URL(String(url)).pathname;
  calls.push({ path: pathValue, method: init.method ?? "GET", body: init.body ? JSON.parse(init.body) : null });
  let value;
  if (pathValue === "/v1/browser/runtime") value = { supported: true, installed: true };
  else if (pathValue === "/v1/browser/sessions/thread_1") value = { thread_id: "thread_1", state: "active" };
  else if (pathValue === "/v1/browser/sessions/thread_1/reset") value = { thread_id: "thread_1", state: "closed" };
  else if (pathValue === "/v1/window-testing/runtime") value = { available: true, installed: true };
  else if (pathValue === "/v1/window-testing/windows") value = [{ hwnd: 42, title: "Fixture", process_name: "fixture.exe", process_id: 1234 }];
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
  const { browserToolNames, desktopToolNames, withBrowserTools, withDesktopTools } = await vite.ssrLoadModule("/src/renderer/chatSetup.ts");
  const { scopedSetupConfiguration } = await vite.ssrLoadModule("/src/renderer/SetupConfigurationEditor.tsx");
  const browser = withBrowserTools(["read_file", "grep"], true, true, false);
  assert.ok(browserToolNames.every(name => browser.includes(name)));
  const desktop = withDesktopTools(browser, true, true, false);
  assert.ok(desktopToolNames.every(name => desktop.includes(name)));
  assert.ok(browserToolNames.every(name => withDesktopTools(desktop, false, true, false).includes(name)), "revoking Windows keeps browser tools");
  assert.deepEqual(scopedSetupConfiguration({ instructions: "Research", presented_tools: desktop, desktop_access: "selected", approval_mode: "full_access" }, "agent"), { instructions: "Research" }, "saved agent setup cannot retain Chat capability or access grants");
  const windowChoices = [];
  let renderer;
  await act(async () => { renderer = create(React.createElement(VisualTestingControls, { conversationId: "chat_1", threadId: "thread_1", browserEnabled: false, onBrowserEnabled: () => {}, desktopAccess: "selected", onDesktopAccess: value => windowChoices.push(value) })); });
  assert.match(text(renderer.toJSON()), /fresh Windows grant/, "reopened chat shows that its live grant is missing");
  await act(async () => button(renderer, "Choose window").props.onClick());
  await act(async () => button(renderer, "Use window").props.onClick());
  assert.deepEqual(windowChoices, ["selected"]);
  assert.ok(calls.some(call => call.method === "PUT" && call.body?.scope === "selected" && call.body?.hwnd === 42));
  await act(async () => renderer.unmount());
  let prepared = 0;
  await act(async () => { renderer = create(React.createElement(VisualTestingControls, { conversationId: null, threadId: null, browserEnabled: false, onBrowserEnabled: () => {}, desktopAccess: "off", onDesktopAccess: () => {}, onPrepareConversation: async () => { prepared += 1; } })); });
  assert.equal(renderer.root.findByProps({ "aria-label": "Windows access" }).props.disabled, true);
  await act(async () => button(renderer, "Create chat").props.onClick());
  assert.equal(prepared, 1);
  await act(async () => renderer.unmount());
  console.log("Visual testing grants and scoped setup checks passed.");
} finally { globalThis.fetch = previousFetch; await vite.close(); }
