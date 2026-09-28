import React, { useEffect, useLayoutEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import { ChatDock, chatDockGeometry, useConversationDockView, type ChatRailPage } from "../../src/renderer/ChatDock";
import { PanelResize, usePanelWidth } from "../../src/renderer/PanelResize";
import { BrowserRail } from "../../src/renderer/BrowserRail";
import { HelperRequest } from "../../src/renderer/HelperRail";
import * as monacoApi from "monaco-editor/editor/editor.api";
import "../../src/renderer/appearanceDefaults.css";
import "../../src/renderer/styles.css";
import "../../src/renderer/ChatPanel.css";

const fixture = { streams: 0, aborted: 0, preferred: 0, view: {} as any, selectChat: (_id: string) => {}, editor: () => monacoApi.editor.getEditors().find(editor => editor.getDomNode()?.closest(".chat-dock-editor")) };
Object.assign(window, { fixture, workbench: { backendUrl: "http://dock-fixture.test" } });
if (!localStorage.getItem("workbench.chat.dock.width")) localStorage.setItem("workbench.inspector.width", "420");
const assets = Array.from({ length: 30 }, (_, index) => ({ id: `asset_${index}`, filename: `chat-file-${index}.txt`, content_kind: "text", content_type: "text/plain", scope: "session", session_id: "one", origin: "upload", size_bytes: 100, observed_at: "2026-09-28T08:00:00Z", source_run_id: null, source_tool_name: null, mutable_reference: null, deleted_at: null }));
window.fetch = async (url, init = {}) => {
  const target = new URL(String(url)), pathname = target.pathname;
  if (pathname === "/v1/assets") return Response.json(assets);
  if (/\/v1\/assets\/[^/]+\/preview/.test(pathname)) return Response.json({ id: pathname.split("/")[3], filename: "chat-file-0.txt", preview: "This is a retained upload.", source_status: "retained_only", size_bytes: 100, content_type: "text/plain", truncated: false });
  if (pathname.includes("/projects/project/files")) return Response.json({ entries: target.searchParams.get("path") === "src" ? [{ path: "src/file.txt", name: "file.txt", kind: "file", size_bytes: 100 }] : [{ path: "src", name: "src", kind: "directory" }, { path: "README.md", name: "README.md", kind: "file", size_bytes: 100 }, ...Array.from({ length: 60 }, (_, index) => ({ path: `file-${index}.txt`, name: `file-${index}.txt`, kind: "file", size_bytes: 100 }))] });
  if (pathname.includes("/projects/project/file")) return Response.json({ path: target.searchParams.get("path"), text: Array.from({ length: 400 }, (_, index) => `Line ${index + 1}: ${"Project file preview. ".repeat(10)}`).join("\n"), image_data_url: null });
  const match = pathname.match(/^\/v1\/browser\/sessions\/([^/]+)(\/.*)?$/);
  if (match) {
    const [, thread, endpoint = ""] = match;
    const status = { thread_id: thread, state: "active", session_id: `${thread}_session`, revision: 1, tabs: [{ page_id: "page", title: "Dock fixture", url: "https://fixture.test" }], active_page_id: "page", viewport: { width: 1440, height: 900 }, control: "agent", worker: { installed: true, chrome_available: true } };
    if (endpoint === "/events") return new Response(new ReadableStream({ start(controller) {
      fixture.streams += 1;
      controller.enqueue(new TextEncoder().encode(`event: state\ndata: ${JSON.stringify(status)}\n\n`));
      init.signal?.addEventListener("abort", () => { fixture.streams -= 1; fixture.aborted += 1; controller.close(); }, { once: true });
    } }), { headers: { "Content-Type": "text/event-stream" } });
    return Response.json(status);
  }
  throw Error(`Unexpected fixture route ${pathname}`);
};

function Fixture() {
  const [chat, setChat] = useState("one");
  const [view, update] = useConversationDockView(chat);
  const [preferred, resize] = usePanelWidth("workbench.chat.dock.width", 320, 280, 1100, "workbench.inspector.width");
  const [available, setAvailable] = useState(innerWidth);
  const geometry = chatDockGeometry(preferred, available);
  const visible = view.open && geometry.canOpen;
  const body = useRef<HTMLDivElement>(null);
  const restoring = useRef(false);
  fixture.preferred = preferred; fixture.view = view; fixture.selectChat = setChat;
  useEffect(() => { const changed = () => setAvailable(innerWidth); addEventListener("resize", changed); return () => removeEventListener("resize", changed); }, []);
  useLayoutEffect(() => {
    if (!body.current || !visible || view.page === "browser") return;
    const element = body.current, target = view.page === "files" ? view.filesScroll : view.helpersScroll;
    restoring.current = true;
    const restore = () => { if (restoring.current) element.scrollTop = target; };
    restore(); const observer = new ResizeObserver(restore); if (element.firstElementChild) observer.observe(element.firstElementChild);
    return () => { restoring.current = false; observer.disconnect(); };
  }, [chat, view.page, visible]);
  const page = (next: ChatRailPage) => update({ page: next, open: true });
  return <section className="chat-layout" style={{ height: "100vh", width: "100vw", "--inspector-width": `${geometry.width}px` } as React.CSSProperties}>
    <div className="chat-main"><header className="chat-header"><h2>Chat {chat}</h2><button aria-label="Toggle dock" onClick={() => update({ open: !view.open })}>Toggle dock</button><button onClick={() => setChat(chat === "one" ? "two" : "one")}>Switch chat</button></header>
      <div className={`chat-workspace${visible ? " files-open" : ""}${visible && view.page === "browser" ? " browser-open" : ""}`}>
        <div className="chat-conversation"><div className="transcript">The conversation remains readable.</div></div><form className="compose"><textarea aria-label="Fixture composer" /></form>
        <aside className="chat-files-panel chat-rail" hidden={!visible}><PanelResize label="Resize conversation rail" width={geometry.width} min={280} max={geometry.max} reset={320} reverse onResize={value => resize(Math.max(280, Math.min(geometry.max, value)))} />
          <div className="chat-rail-tabs" role="tablist">{(["files", "browser", "helpers"] as const).map(name => <button key={name} role="tab" aria-selected={view.page === name} onClick={() => page(name)}>{name[0].toUpperCase() + name.slice(1)}</button>)}</div>
          <div className="chat-rail-body" ref={body} onWheel={() => { restoring.current = false; }} onPointerDown={() => { restoring.current = false; }} onScroll={event => { if (!restoring.current && view.page !== "browser") update(view.page === "files" ? { filesScroll: event.currentTarget.scrollTop } : { helpersScroll: event.currentTarget.scrollTop }); }}>
            {view.page === "files" ? <ChatDock page="files" onPage={page} projectId="project" conversationId={chat} runIds={["response"]} selectedPath={view.path} onSelectPath={path => update({ path, projectId: "project" })} view={view} onViewChange={update} onReuseAssets={() => {}} /> : null}
            {view.page === "browser" ? <BrowserRail threadId={chat} visible={visible} enabled projectBound attachments={[]} onConfigure={() => {}} onOpenFiles={() => page("files")} /> : null}
            {view.page === "helpers" ? <div className="helper-rail">{view.helper ? <><button onClick={() => update({ helper: "" })}>All helpers</button><h3>Selected helper</h3><HelperRequest request={"Delegated request\n".repeat(100)} /><div style={{ height: 1000 }}>Helper output</div></> : <button onClick={() => update({ helper: "selected", helpersScroll: 0 })}>Research helper</button>}</div> : null}
          </div>
        </aside>
      </div>
    </div>
  </section>;
}
createRoot(document.getElementById("root")!).render(<Fixture />);
