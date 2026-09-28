import React, { useState } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRail } from "../../src/renderer/BrowserRail";
import type { BrowserSessionStatus } from "../../src/renderer/types";
import "../../src/renderer/appearanceDefaults.css";
import "../../src/renderer/styles.css";
import "../../src/renderer/ChatPanel.css";

const fixture = { calls: [] as Array<{ thread: string; endpoint: string; method: string; body: any }>, streams: 0, aborted: 0, visible: true, toggle: (_visible: boolean) => {}, switchChat: (_thread: string) => {} };
Object.assign(window, { fixture, workbench: { backendUrl: "http://browser-fixture.test" } });
const states = new Map<string, BrowserSessionStatus>();
const controllers = new Map<string, ReadableStreamDefaultController<Uint8Array>>();
let timestamp = 0;
function state(thread: string): BrowserSessionStatus {
  return { thread_id: thread, state: "active", session_id: `${thread}_session`, revision: 1, tabs: [{ page_id: `${thread}_page`, title: "Fixture page", url: "https://fixture.test/" }], active_page_id: `${thread}_page`, viewport: { width: 1440, height: 900 }, control: "agent", worker: { supported: true, installed: true, chrome_available: true, chrome_version: "fixture", node_version: "fixture", playwright_mcp_version: "fixture", reason: null } };
}
function publish(thread: string) {
  const current = states.get(thread)!;
  const controller = controllers.get(thread);
  if (!controller) return;
  const canvas = document.createElement("canvas");
  canvas.width = current.viewport.width; canvas.height = current.viewport.height;
  const context = canvas.getContext("2d")!;
  context.fillStyle = "#eef2f7"; context.fillRect(0, 0, canvas.width, canvas.height);
  context.fillStyle = "#286dd5"; context.fillRect(20, 20, canvas.width - 40, 80);
  context.fillStyle = "white"; context.font = "30px sans-serif"; context.fillText(`Page ${canvas.width} × ${canvas.height}`, 40, 72);
  context.strokeStyle = "#555"; context.beginPath(); context.moveTo(canvas.width / 2, 100); context.lineTo(canvas.width / 2, canvas.height); context.moveTo(0, canvas.height / 2); context.lineTo(canvas.width, canvas.height / 2); context.stroke();
  const frame = { session_id: current.session_id, page_id: current.active_page_id, revision: current.revision, viewport: current.viewport, timestamp: ++timestamp, data: canvas.toDataURL("image/jpeg", .75).split(",")[1] };
  controller.enqueue(new TextEncoder().encode(`event: state\ndata: ${JSON.stringify(current)}\n\nevent: frame\ndata: ${JSON.stringify(frame)}\n\n`));
}
window.fetch = async (url, init = {}) => {
  const pathname = new URL(String(url)).pathname;
  const [, thread, endpoint = ""] = pathname.match(/^\/v1\/browser\/sessions\/([^/]+)(\/.*)?$/)!;
  const body = init.body ? JSON.parse(String(init.body)) : null;
  fixture.calls.push({ thread, endpoint, method: init.method ?? "GET", body });
  if (!states.has(thread)) states.set(thread, state(thread));
  if (endpoint === "/events") {
    return new Response(new ReadableStream({ start(controller) {
      controllers.set(thread, controller); fixture.streams += 1;
      init.signal?.addEventListener("abort", () => { controllers.delete(thread); fixture.streams -= 1; fixture.aborted += 1; controller.close(); }, { once: true });
      publish(thread);
    } }), { headers: { "Content-Type": "text/event-stream" } });
  }
  let current = states.get(thread)!;
  if (endpoint === "/control") current = { ...current, control: body.action === "take" ? "user" : "agent" };
  if (endpoint === "/actions" && body.action.type === "resize") current = { ...current, revision: current.revision + 1, viewport: { width: body.action.width, height: body.action.height } };
  states.set(thread, current);
  if (init.method === "POST") publish(thread);
  return Response.json(current);
};
function Fixture() {
  const [visible, setVisible] = useState(true);
  const [thread, setThread] = useState("one");
  fixture.toggle = next => { fixture.visible = next; setVisible(next); };
  fixture.switchChat = setThread;
  // This fixture exercises Browser rendering and scaled input at a narrow rail
  // width. Mounted Chat tests own the minimum width needed to open its dock.
  return <section className="chat-layout" style={{ height: "100vh", width: "100vw" }}><aside className="chat-rail" hidden={!visible} style={{ width: "min(640px, 100%)", minWidth: 0, minHeight: 0, display: "flex", flexDirection: "column", overflow: "hidden" }}><div className="chat-rail-tabs"><span>Browser</span></div><div className="chat-rail-body" style={{ flex: 1, overflow: "hidden" }}><BrowserRail key={thread} threadId={thread} visible={visible} enabled projectBound attachments={[]} onConfigure={() => {}} onOpenFiles={() => {}} /></div></aside></section>;
}
createRoot(document.getElementById("root")!).render(<Fixture />);
