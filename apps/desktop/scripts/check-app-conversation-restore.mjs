import assert from "node:assert/strict";
import path from "node:path";
import { fileURLToPath } from "node:url";
import React from "react";
import { act, create } from "react-test-renderer";
import { createServer } from "vite";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;
const stored = new Map();
const backend = "http://restore-app.test";
const storageKey = `workbench.chat.selection:${backend}`;
globalThis.window = Object.assign(new EventTarget(), { innerWidth: 1280, setInterval: () => 1, clearInterval() {}, setTimeout, clearTimeout, localStorage: { getItem: key => stored.get(key) ?? null, setItem: (key, value) => stored.set(key, value) }, workbench: { backendUrl: backend } });
globalThis.document = { documentElement: { dataset: {} }, dispatchEvent() {} };
globalThis.appFixture = { chat: null, sidebar: null, launches: [] };
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const children = new Set(["AgentRunPanel", "AttentionPanel", "CreateProjectDialog", "ProjectsPanel", "AgentSetupsPanel", "KnowledgePanel", "LabPanel", "LibraryPanel", "ModelsPanel", "SettingsPanel"]);
const vite = await createServer({ root, appType: "custom", server: { middlewareMode: true, hmr: false }, logLevel: "error", plugins: [{ name: "app-selection-boundaries", enforce: "pre", load(id) {
  const name = path.basename(id).replace(/\.tsx?$/, "");
  if (children.has(name)) return `export function ${name}() { return null; }`;
  if (name === "appearanceStore") return "export async function loadAppearance() {} export function setAppearanceTheme() {}";
  if (name === "PanelResize") return "export function usePanelWidth() { return [232, () => {}]; }";
  if (name === "WorkbenchSidebar") return "export function WorkbenchSidebar(props) { globalThis.appFixture.sidebar = props; return null; }";
  if (name === "ChatPanel") return `import React, {useEffect, useState} from 'react'; export function ChatPanel(props) {
    globalThis.appFixture.chat = props; const [selected, setSelected] = useState(null);
    useEffect(() => { props.onActiveConversationId?.(selected); }, [selected]);
    useEffect(() => { if (!props.chatLaunch) return; globalThis.appFixture.launches.push(props.chatLaunch); setSelected(props.chatLaunch.kind === 'fresh' ? null : props.chatLaunch.conversationId); props.onChatLaunchHandled?.(); }, [props.chatLaunch?.id]);
    return React.createElement('output', {'aria-label':'Selected conversation'}, selected ?? 'New conversation');
  }`;
  return null;
} }] });
const requests = [];
let catalog = [{ id: "chat-a", title: "ScratchArea" }], barrier = null, rejectCatalog = false;
globalThis.fetch = async (url, init = {}) => {
  const address = new URL(String(url)); requests.push({ path: address.pathname, method: init.method ?? "GET" });
  if (address.pathname === "/v1/chat/conversations") { if (barrier) await barrier.promise; if (rejectCatalog) return { ok: false, status: 503, json: async () => ({ error: "Temporarily unavailable" }) }; return json(catalog); }
  if (address.pathname === "/v1/settings/presentation") return json({ theme: "dark", detailed_streams: false, attention_notifications: true, success_notifications: false });
  if (address.pathname === "/health") return json({ status: "ok" });
  throw new Error(`Unexpected restore request ${address.pathname}`);
};
function json(body) { return { ok: true, status: 200, json: async () => body }; }
const tick = () => new Promise(resolve => setTimeout(resolve, 0));
async function settle(work) { await act(async () => { await work?.(); await tick(); }); }
function deferred() { let resolve; return { promise: new Promise(done => { resolve = done; }), resolve }; }
let renderer;
try {
  const { App } = await vite.ssrLoadModule("/src/renderer/App.tsx");
  const mount = async () => { globalThis.appFixture.launches = []; await settle(() => { renderer = create(React.createElement(App)); }); };
  const unmount = async () => { await settle(() => renderer.unmount()); renderer = null; };
  const selected = () => renderer.root.findByProps({ "aria-label": "Selected conversation" }).children.join("");
  await mount();
  await settle(() => globalThis.appFixture.sidebar.onOpenConversation(catalog[0]));
  assert.equal(selected(), "chat-a");
  assert.equal(stored.get(storageKey), "chat-a", "confirmed selection must survive a renderer restart");
  await unmount(); await mount();
  assert.equal(stored.get(storageKey), "chat-a", "initial New state cannot erase the pending restoration");
  assert.equal(globalThis.appFixture.launches.length, 0, "wait for catalogue readiness");
  assert.equal(globalThis.appFixture.chat.restoringSelection, true, "composer remains in restoration state before catalogue hydration");
  await settle(() => globalThis.appFixture.sidebar.onListsReady(true));
  await settle();
  assert.equal(selected(), "chat-a", "restart restores the existing conversation");
  assert.equal(globalThis.appFixture.chat.restoringSelection, false);
  assert.equal(globalThis.appFixture.launches[0].kind, "open");
  assert.equal(requests.some(item => item.method !== "GET"), false, "restoration cannot submit work or create data");
  await unmount();

  barrier = deferred(); await mount();
  await settle(() => globalThis.appFixture.sidebar.onListsReady(true));
  assert.equal(globalThis.appFixture.chat.restoringSelection, true, "a held catalogue cannot expose a sendable New chat");
  await settle(() => globalThis.appFixture.sidebar.onNewChat());
  await settle(() => { barrier.resolve(); }); barrier = null;
  assert.equal(selected(), "New conversation", "explicit New beats a late saved-selection response");
  assert.equal(stored.get(storageKey), "");
  assert.equal(globalThis.appFixture.chat.restoringSelection, false, "explicit New releases the startup loading state");
  await unmount(); await mount();
  const reads = requests.filter(item => item.path === "/v1/chat/conversations").length;
  await settle(() => globalThis.appFixture.sidebar.onListsReady(true));
  assert.equal(selected(), "New conversation", "explicit New state survives another restart");
  assert.equal(requests.filter(item => item.path === "/v1/chat/conversations").length, reads);
  await unmount();

  stored.set(storageKey, "deleted-chat"); await mount();
  await settle(() => globalThis.appFixture.sidebar.onListsReady(true)); await settle();
  assert.equal(selected(), "New conversation"); assert.equal(stored.get(storageKey), "", "confirmed missing selection is cleared");
  await unmount();

  stored.set(storageKey, "chat-a"); rejectCatalog = true; await mount();
  await settle(() => globalThis.appFixture.sidebar.onListsReady(true)); await settle();
  assert.equal(stored.get(storageKey), "chat-a", "a failed catalogue load cannot discard the remembered chat");
  assert.equal(globalThis.appFixture.launches.length, 0);
  rejectCatalog = false;
  const deadline = Date.now() + 2500;
  while (selected() !== "chat-a" && Date.now() < deadline) await act(async () => { await new Promise(resolve => setTimeout(resolve, 25)); });
  assert.equal(selected(), "chat-a", "a successful retry restores after temporary service failure");
  await unmount();

  barrier = deferred(); await mount();
  await settle(() => globalThis.appFixture.sidebar.onListsReady(true));
  await settle(() => globalThis.appFixture.sidebar.onOpenConversation({ id: "chat-b", title: "Other chat" }));
  await settle(() => barrier.resolve()); barrier = null;
  assert.equal(selected(), "chat-b", "manual conversation selection wins over pending startup restoration");
  assert.equal(stored.get(storageKey), "chat-b");
  await unmount();
  window.workbench.backendUrl = "http://separate-backend.test";
  await mount(); await settle(() => globalThis.appFixture.sidebar.onListsReady(true));
  assert.equal(selected(), "New conversation", "a different backend has its own selection preference");
  console.log("App conversation restoration checks passed.");
} finally { barrier?.resolve(); if (renderer) await settle(() => renderer.unmount()); await vite.close(); }
