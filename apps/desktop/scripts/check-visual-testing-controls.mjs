import assert from "node:assert/strict";
import path from "node:path";
import { fileURLToPath } from "node:url";

import React from "react";
import { act, create } from "react-test-renderer";
import { createServer as createViteServer } from "vite";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;
globalThis.window = { workbench: { backendUrl: "http://visual-testing.test" }, setInterval, clearInterval };

const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../..");
const desktopRoot = path.join(repoRoot, "apps/desktop");
const calls = [];
let scope = { scope: "off", selected_window: null, stale: false };
const previousFetch = globalThis.fetch;
globalThis.fetch = async (url, init = {}) => {
  const pathValue = new URL(String(url)).pathname;
  calls.push({ path: pathValue, method: init.method ?? "GET", body: init.body ? JSON.parse(init.body) : null });
  let value;
  if (pathValue === "/v1/browser/runtime") value = { supported: true, installed: true, node_version: "24.19.0", playwright_mcp_version: "0.0.82", reason: null };
  else if (pathValue === "/v1/browser/sessions/thread_1") value = { thread_id: "thread_1", state: init.method === "DELETE" ? "closed" : "active", worker: { installed: true } };
  else if (pathValue === "/v1/browser/sessions/thread_1/reset") value = { thread_id: "thread_1", state: "closed", worker: { installed: true } };
  else if (pathValue === "/v1/window-testing/runtime") value = { available: true, installed: true };
  else if (pathValue === "/v1/window-testing/windows") value = [{ hwnd: 42, title: "Fixture", process_name: "fixture.exe", process_id: 1234 }];
  else if (pathValue === "/v1/window-testing/conversations/chat_1/scope") {
    if (init.method === "PUT") {
      const body = JSON.parse(init.body);
      scope = { scope: body.scope, selected_window: body.hwnd ? { hwnd: body.hwnd, title: "Fixture", process_name: "fixture.exe", process_id: 1234 } : null, stale: false };
    }
    value = scope;
  } else throw new Error(`Unexpected visual testing endpoint: ${pathValue}`);
  return { ok: true, json: async () => value };
};

const vite = await createViteServer({ root: desktopRoot, appType: "custom", server: { middlewareMode: true, hmr: false }, logLevel: "error" });
try {
  const { VisualTestingControls } = await vite.ssrLoadModule("/src/renderer/VisualTestingControls.tsx");
  const { browserToolNames, desktopToolNames, withBrowserTools, withDesktopTools } = await vite.ssrLoadModule("/src/renderer/chatSetup.ts");
  const browserTools = withBrowserTools(["read_file", "grep"], true, true, false);
  assert.ok(browserToolNames.every(name => browserTools.includes(name)), "browser selection must present every browser tool");
  assert.ok(browserTools.includes("start_preview") && browserTools.includes("grep"), "browser selection must retain existing tools and project preview");
  const desktopTools = withDesktopTools(browserTools, true, true, false);
  assert.ok(desktopToolNames.every(name => desktopTools.includes(name)), "Windows access must present every desktop tool");
  assert.ok(browserToolNames.every(name => desktopTools.includes(name)), "Windows access must preserve browser tools");
  const revokedDesktopTools = withDesktopTools(desktopTools, false, true, false);
  assert.ok(desktopToolNames.every(name => !revokedDesktopTools.includes(name)), "revoking Windows access must remove desktop tools");
  assert.ok(browserToolNames.every(name => revokedDesktopTools.includes(name)), "revoking Windows access must preserve browser tools");
  const captureOnly = withBrowserTools(withDesktopTools(["grep"], true, false, false), false, false, false);
  const retainedCaptureTools = withDesktopTools(captureOnly, false, false, false);
  assert.ok(retainedCaptureTools.includes("read_file"), "turning both workers off must retain read_file for prior captures");
  const browserChoices = [], windowChoices = [];
  let renderer;
  await act(async () => {
    renderer = create(React.createElement(VisualTestingControls, {
      conversationId: "chat_1", threadId: "thread_1", browserEnabled: false,
      onBrowserEnabled: value => browserChoices.push(value), desktopAccess: "off",
      onDesktopAccess: value => windowChoices.push(value),
    }));
  });
  assert.match(textOf(renderer.toJSON()), /Visual testing/);
  await act(async () => {
    renderer.root.findByProps({ type: "checkbox" }).props.onChange({ target: { checked: true } });
  });
  assert.deepEqual(browserChoices, [true], "browser toggle must request tool selection");
  await act(async () => {
    renderer.root.findByProps({ "aria-label": "Windows access" }).props.onChange({ target: { value: "all" } });
  });
  assert.deepEqual(windowChoices, ["all"], "all-window access must be an explicit scope write");
  assert.ok(calls.some(call => call.method === "PUT" && call.body?.scope === "all"));
  await act(async () => {
    renderer.root.findByProps({ "aria-label": "Windows access" }).props.onChange({ target: { value: "selected" } });
  });
  assert.match(textOf(renderer.toJSON()), /Fixture/);
  await act(async () => { button(renderer, "Use window").props.onClick(); });
  assert.deepEqual(windowChoices, ["all", "selected"]);
  assert.ok(calls.some(call => call.method === "PUT" && call.body?.scope === "selected" && call.body?.hwnd === 42));
  await act(async () => { button(renderer, "Reset").props.onClick(); });
  assert.ok(calls.some(call => call.path.endsWith("/reset") && call.method === "POST"));
  await act(async () => { renderer.unmount(); });
  let prepared = 0;
  await act(async () => {
    renderer = create(React.createElement(VisualTestingControls, {
      conversationId: null, threadId: null, browserEnabled: false,
      onBrowserEnabled: () => {}, desktopAccess: "off", onDesktopAccess: () => {},
      onPrepareConversation: async () => { prepared += 1; },
    }));
  });
  assert.equal(renderer.root.findByProps({ "aria-label": "Windows access" }).props.disabled, true, "a new chat cannot grant Windows access before it exists");
  await act(async () => { button(renderer, "Create chat").props.onClick(); });
  assert.equal(prepared, 1, "the first-turn flow must offer to create a chat for its grant");
  await act(async () => { renderer.unmount(); });
  const { AgentSetupsPanel } = await vite.ssrLoadModule("/src/renderer/AgentSetupsPanel.tsx");
  const { visualSetupCompatibilityIssue } = await vite.ssrLoadModule("/src/renderer/SetupConfigurationEditor.tsx");
  await savedAgentWithOldBackend(AgentSetupsPanel, visualSetupCompatibilityIssue, browserToolNames, desktopToolNames);
} finally {
  globalThis.fetch = previousFetch;
  await vite.close();
}
console.log("Visual testing controls checks passed.");

function button(renderer, label) {
  const result = renderer.root.findAll(node => node.type === "button" && textOf(node).trim() === label);
  assert.ok(result.length, `Expected ${label} button`);
  return result[0];
}

function textOf(node) {
  if (typeof node === "string") return node;
  return node?.children?.map(textOf).join("") ?? "";
}

async function savedAgentWithOldBackend(Panel, compatibilityIssue, browserNames, desktopNames) {
  const core = ["echo", "time_now", "ls", "read_file", "write_file", "edit_file", "glob", "grep", "execute", "write_todos", "ask_user", "propose_memory", "read_attachment"];
  const selected = [...core, ...browserNames, ...desktopNames];
  assert.equal(selected.length, 38, "the saved selection matches the reported 38-tool case");
  const configuration = { presented_tools: selected, desktop_access: "selected" };
  const record = { id: "agent_old", name: "Visual tester", role: null, current_version_id: "version_1", configuration, missing_dependencies: [] };
  const catalogue = names => ({ deployments: [], bundles: [], profiles: [], knowledge: [], connections: [], tools: names.map(id => ({ id, name: id })) });
  assert.ok(compatibilityIssue(configuration, catalogue(core)), "an old backend blocks saving the still-selected visual tools");
  assert.equal(compatibilityIssue(configuration, catalogue(selected)), null, "the matching backend accepts the saved choices");
  let advertised = core;
  const writes = [];
  globalThis.fetch = async (url, init = {}) => {
    const path = new URL(String(url)).pathname;
    const method = init.method ?? "GET";
    if (path === "/v1/agent-setups") return { ok: true, json: async () => [record] };
    if (path === "/v1/agent-setups/agent_old" && method === "PATCH") {
      writes.push(JSON.parse(init.body));
      return { ok: true, json: async () => record };
    }
    if (path === "/v1/agent-setups/agent_old/versions") return { ok: true, json: async () => [] };
    if (["/v1/deployments", "/v1/bundles", "/v1/profiles", "/v1/knowledge/entries", "/v1/connections"].includes(path)) return { ok: true, json: async () => [] };
    if (path === "/v1/agent-tools") return { ok: true, json: async () => ({ enabled: advertised, tools: advertised.map(id => ({ id, name: id, description: "" })) }) };
    if (path === "/v1/setup-resolution") return { ok: true, json: async () => ({ configuration, effective_values: {}, instruction_layers: [] }) };
    throw new Error(`Unexpected setup endpoint: ${method} ${path}`);
  };
  let renderer;
  try {
    await act(async () => { renderer = create(React.createElement(Panel)); await new Promise(resolve => setTimeout(resolve, 0)); });
    const save = button(renderer, "Save agent");
    assert.equal(save.props.disabled, true, "a stale backend cannot receive the unsupported setup payload");
    assert.match(textOf(renderer.toJSON()), /Restart Workbench to load the updated backend/);
    const unavailable = renderer.root.findAll(node => node.type === "summary" && textOf(node) === "25 unavailable selections");
    assert.equal(unavailable.length, 1, "the 25 newer tools are grouped instead of repeated generic rows");
    assert.equal(renderer.root.findAll(node => node.type === "button" && node.props["aria-label"] === "Unavailable selection").length, 0);
    assert.ok(renderer.root.findAll(node => node.type === "button" && node.props["aria-label"] === "browser navigate").length);
    await act(async () => { renderer.root.findByType("form").props.onSubmit({ preventDefault() {} }); });
    assert.equal(writes.length, 0, "form submit also refuses the unsupported payload");
    await act(async () => { renderer.unmount(); });
    renderer = null;
    advertised = selected;
    await act(async () => { renderer = create(React.createElement(Panel)); await new Promise(resolve => setTimeout(resolve, 0)); });
    assert.equal(button(renderer, "Save agent").props.disabled, false, "the updated catalogue restores saving without changing the draft");
    await act(async () => { renderer.root.findByType("form").props.onSubmit({ preventDefault() {} }); await new Promise(resolve => setTimeout(resolve, 0)); });
    assert.equal(writes.length, 1);
    assert.deepEqual(writes[0].configuration, configuration, "the compatible save keeps all selected tools and desktop scope");
  } finally { if (renderer) await act(async () => renderer.unmount()); }
}
