import assert from "node:assert/strict";
import path from "node:path";
import { fileURLToPath } from "node:url";
import React from "react";
import { act, create } from "react-test-renderer";
import { createServer } from "vite";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;
globalThis.window = {
  setTimeout, clearTimeout, setInterval, clearInterval,
  addEventListener() {}, removeEventListener() {},
  requestAnimationFrame(callback) { return setTimeout(callback, 0); },
  workbench: { backendUrl: "http://127.0.0.1:8765" },
};
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const vite = await createServer({ root, appType: "custom", server: { middlewareMode: true, hmr: false }, logLevel: "error" });
const tick = () => new Promise(resolve => setTimeout(resolve, 0));
const text = node => typeof node === "string" ? node : (node?.children ?? []).map(text).join("");
const json = body => ({ ok: true, status: 200, json: async () => body });
const tool = (id, name) => ({ id, name, description: `${name} tool`, input_schema: {} });
const stamp = { created_at: "2026-10-01T00:00:00Z", updated_at: "2026-10-01T00:00:00Z", credential_present: false, enabled: true, version: 1, args: [] };
const testedAt = "2026-10-01T00:01:00Z";

let sidebar;
let connections;
try {
  const { workbenchTabs, tabLabel } = await vite.ssrLoadModule("/src/renderer/workspaceNavigation.ts");
  const { WorkbenchSidebar } = await vite.ssrLoadModule("/src/renderer/WorkbenchSidebar.tsx");
  const primary = workbenchTabs.filter(item => item !== "attention" && item !== "settings");
  assert.equal(tabLabel("lab"), "Lab");
  assert.equal(tabLabel("agent-run"), "Workflows");
  assert.ok(primary.includes("lab") && primary.includes("agent-run"), "Lab and Workflows stay on the primary sidebar");
  assert.doesNotMatch(`${tabLabel("lab")} ${tabLabel("agent-run")}`, /Measurements|suite/i);

  globalThis.fetch = async (url) => {
    const pathname = new URL(String(url)).pathname;
    if (pathname === "/v1/chat/conversations" || pathname === "/v1/projects" || pathname === "/v1/desktop/attention") return json([]);
    throw new Error(`unexpected sidebar read ${pathname}`);
  };
  await act(async () => {
    sidebar = create(React.createElement(WorkbenchSidebar, {
      tab: "lab", collapsed: true, width: 232, backendOk: true, backendStatus: "Local",
      activeConversationId: null, historyRevision: 0, projectRevision: 0,
      onCollapsedChange() {}, onWidthChange() {}, onNavigate() {}, onOpenConversation() {},
      onNewChat() {}, onAddProject() {}, onHistoryNotice() {},
    }));
    await tick();
  });
  const labels = sidebar.root.findByProps({ "aria-label": "Destinations" }).findAllByType("button").map(button => button.props["aria-label"]);
  assert.deepEqual(labels, primary.map(tabLabel), "primary sidebar shows Lab and Workflows");
  assert.ok(labels.includes("Lab") && labels.includes("Workflows"));
  assert.equal(labels.some(label => /Measurements|suite/i.test(label)), false, "Lab is not named Measurements or a future suite");
  await act(async () => sidebar.unmount());
  sidebar = null;

  let records = [
    { ...stamp, id: "files", name: "Files", kind: "mcp", transport: "http", url: "https://files.test/mcp", protocol_capabilities: ["resources"], tools: [], last_tested_at: testedAt, last_error: null },
    { ...stamp, id: "tools", name: "Tools", kind: "mcp", transport: "http", url: "https://tools.test/mcp", protocol_capabilities: ["tools"], tools: [tool("echo", "Echo"), tool("search", "Search")], last_tested_at: testedAt, last_error: null },
    { ...stamp, id: "broken", name: "Broken", kind: "mcp", transport: "http", url: "https://broken.test/mcp", protocol_capabilities: [], tools: [], last_tested_at: testedAt, last_error: "Could not connect" },
  ];
  const tested = id => {
    if (id === "files") return { tools: [], protocol_capabilities: ["resources"], last_error: null, last_tested_at: testedAt };
    if (id === "tools") return { tools: [tool("echo", "Echo"), tool("search", "Search")], protocol_capabilities: ["tools"], last_error: null, last_tested_at: testedAt };
    return { tools: [], last_error: "Could not connect", last_tested_at: testedAt };
  };
  globalThis.fetch = async (url, init = {}) => {
    const pathname = new URL(String(url)).pathname;
    if (pathname === "/v1/connections" && (init.method ?? "GET") === "GET") return json(records);
    const match = pathname.match(/^\/v1\/connections\/([^/]+)\/test$/);
    if (match && init.method === "POST") {
      records = records.map(item => item.id === match[1] ? { ...item, ...tested(match[1]) } : item);
      return json(records.find(item => item.id === match[1]));
    }
    throw new Error(`unexpected connection ${init.method ?? "GET"} ${pathname}`);
  };
  const { ConnectionsPanel } = await vite.ssrLoadModule("/src/renderer/ConnectionsPanel.tsx");
  await act(async () => { connections = create(React.createElement(ConnectionsPanel)); await tick(); });
  const row = name => {
    const found = connections.root.findAll(node => node.type === "li" && node.props.className === "connection-row").find(node => text(node).includes(name));
    assert.ok(found, `connection row ${name}`);
    return found;
  };
  const status = name => text(row(name).findAllByType("button").find(node => node.props.className === "connection-title"));
  const pressTest = async name => { await act(async () => { row(name).findAllByType("button").find(node => text(node).trim() === "Test").props.onClick(); await tick(); }); };
  assert.match(status("Files"), /Ready · no tools/);
  assert.doesNotMatch(status("Files"), /0 tools ready/);
  assert.match(status("Tools"), /2 tools ready/);
  assert.match(status("Broken"), /Needs attention/);
  assert.doesNotMatch(status("Broken"), /tools ready/);
  await pressTest("Files");
  assert.match(status("Files"), /Ready · no tools/);
  assert.doesNotMatch(text(connections.root), /0 tools ready/);
  await pressTest("Tools");
  assert.match(status("Tools"), /2 tools ready/);
  assert.doesNotMatch(text(connections.root), /0 tools ready/);
  console.log("Sidebar and connection wording checks passed.");
} finally {
  if (sidebar) await act(async () => sidebar.unmount());
  if (connections) await act(async () => connections.unmount());
  await vite.close();
}
