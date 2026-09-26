import React from "react";
import { AIMessage, HumanMessage } from "@langchain/core/messages";
import { AgentMessageFeed } from "../../src/renderer/AgentMessageFeed";
import { HelperRequest } from "../../src/renderer/HelperRail";
import { createRoot } from "react-dom/client";
import { SourceLink, SourceScope } from "../../src/renderer/SourceReference";
import { ImagePreview } from "../../src/renderer/ImagePreview";
import { LibraryPanel } from "../../src/renderer/LibraryPanel";
import { MenuPopover } from "../../src/renderer/MenuPopover";
import { VisualTestingControls } from "../../src/renderer/VisualTestingControls";
import { WorkbenchSidebar } from "../../src/renderer/WorkbenchSidebar";
import { ChatDock } from "../../src/renderer/ChatDock";
import "../../src/renderer/appearanceDefaults.css";
import "../../src/renderer/styles.css";
import "../../src/renderer/ChatPanel.css";

const sha = "a".repeat(64);
const sidebarChat = { id: "sidebar-chat", title: "Build a simple top-down 2D driving game", display_title: "Build a simple top-down 2D driving game", transcript: [], project_id: "project-game", project_path: "D:/Games", archived: false, updated_at: "2026-09-26T12:00:00Z" };
const imageData = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jB9kAAAAASUVORK5CYII=";
Object.assign(window, { workbench: { backendUrl: "http://fixture.invalid", saveAsset: async () => { window.fixture.saved++; } }, fixture: { saved: 0, calls: [] } });
window.fetch = async (url, init) => {
  const address = new URL(String(url));
  if (/^\/v1\/projects\/tree-[ab]\/(files|file)$/.test(address.pathname)) {
    const project = address.pathname.split("/")[3];
    const entryPath = address.searchParams.get("path") ?? "";
    const listing = address.pathname.endsWith("/files");
    window.fixture.fileRequests ??= [];
    window.fixture.fileRequests.push({ project, entryPath, listing });
    const entry = (path: string, kind = "file") => ({ path, name: path.split("/").at(-1), kind });
    if (project === "tree-a" && listing && entryPath === "src" && window.fixture.holdDirectory) {
      window.fixture.holdDirectory = false;
      return { ok: true, json: () => new Promise(resolve => { window.fixture.resolveDirectory = () => resolve({ entries: [entry("src/late-wrong-project.txt")] }); }) } as Response;
    }
    if (project === "tree-a" && !listing && window.fixture.holdFile) {
      window.fixture.holdFile = false;
      return { ok: true, json: () => new Promise(resolve => { window.fixture.resolveFile = () => resolve({ path: entryPath, text_unavailable_reason: "OLD PROJECT CONTENT" }); }) } as Response;
    }
    const entries = project === "tree-b" ? [entry("second-only.txt")] : entryPath === "src/nested" ? [entry("src/nested/old.txt"), ...(window.fixture.filesAdded ? [entry("src/nested/new.txt")] : [])]
      : entryPath === "src" ? [entry("src/first.txt"), entry("src/nested", "directory"), ...(window.fixture.filesAdded ? [entry("src/second.txt")] : [])]
      : [entry("src", "directory"), entry("blocked.txt")];
    return { ok: true, json: async () => listing ? { entries } : { path: entryPath, text_unavailable_reason: `Viewing ${entryPath}` } } as Response;
  }
  if (address.pathname === "/v1/chat/conversations") return { ok: true, json: async () => [sidebarChat] } as Response;
  if (address.pathname === "/v1/chat/conversations/search") return { ok: true, json: async () => address.searchParams.get("q") === "absent" ? [] : [{ conversation: sidebarChat }] } as Response;
  if (address.pathname === "/v1/projects") return { ok: true, json: async () => [{ id: "other-project", name: "Unrelated project", path: "D:/Other" }, { id: "project-game", name: "Game project", path: "D:/Games" }] } as Response;
  if (address.pathname === "/v1/desktop/attention") return { ok: true, json: async () => [] } as Response;
  if (address.pathname === "/v1/assets") return { ok: true, json: async () => [{ id: "asset_image", filename: "Library image.png", session_id: "chat_fixture", content_kind: "image", content_type: "image/png", size_bytes: 90, origin: "upload", observed_at: "2026-09-22T12:00:00Z" }] } as Response;
  if (address.pathname === "/v1/assets/asset_image/preview") return { ok: true, json: async () => ({ id: "asset_image", filename: "Library image.png", size_bytes: 90, source_status: "retained_only", image_data_url: imageData }) } as Response;
  if (address.pathname === "/v1/assets/asset_image/content") return { ok: true, json: () => new Promise(resolve => { window.fixture.resolveOriginal = () => resolve({ content_type: "image/png", content_base64: imageData.split(",")[1] }); }) } as Response;
  if (address.pathname === "/v1/browser/runtime") return { ok: true, json: async () => ({ supported: true, installed: true, reason: null }) } as Response;
  if (address.pathname === "/v1/window-testing/runtime") return { ok: true, json: async () => ({ available: true, installed: true, reason: null }) } as Response;
  const input = JSON.parse(init?.body as string);
  window.fixture.calls.push(input);
  if (String(url).includes("asset_error")) return { ok: false, status: 404, json: async () => ({ error: "This source is unavailable in the selected conversation." }) } as Response;
  return { ok: true, json: async () => ({ filename: "Long retained research notes — exact original version.docx", sha256: sha, source: "Paragraph 24 · Selected introduction", extracted_line: input.extracted_line, start_char: input.start_char, end_char: input.end_char, text: "This is the actual selected source passage.\n" + Array.from({ length: 80 }, (_, index) => `${index + 1}. Long source text with a very long address https://example.test/${"long-path/".repeat(30)}.`).join("\n"), truncated: true, parser: "python-docx" }) } as Response;
};
const root = createRoot(document.getElementById("root")!);
function HelperDensityFixture() {
  const [open, setOpen] = React.useState(false);
  const request = "Review the actual project files and verify each requirement with evidence.\n".repeat(90);
  return <main style={{ padding: 12, width: 360 }}><AgentMessageFeed messages={[new AIMessage({ id: "delegate-message", content: "", tool_calls: [{ id: "delegate", name: "task", args: { subagent_type: "Research", description: request } }] })]}
    currentRunId="parent" live={false} onHelperOpen={() => { window.fixture.openedHelper = true; setOpen(true); }} />
    {open ? <section className="helper-rail"><HelperRequest request={request} /><p data-helper-activity>Read index.html</p></section> : null}</main>;
}
window.fixture.originalUserText = "Open C:\\Users\\Dave_\\.codex\\worktrees\\reliable-chat\\thtaib\\.scratch\\notes.txt\nKeep `literal backticks` and **stars**.\n\n  Preserve indentation and <script>plain text</script>.";
window.fixture.showUserText = () => root.render(<main style={{ width: 340, padding: 12 }}><AgentMessageFeed
  messages={[new HumanMessage({ id: "literal-user", content: window.fixture.originalUserText + "\nINTERNAL MODEL NOTE" }),
    new AIMessage({ id: "formatted-answer", content: "Assistant **bold** and `code`." })]}
  userMessageContent={() => window.fixture.originalUserText} /></main>);
window.fixture.showHelperDensity = () => root.render(<HelperDensityFixture />);
window.fixture.showLibrary = () => root.render(<main style={{ padding: 20 }}><LibraryPanel /></main>);
function ToolMenuFixture() {
  const [open, setOpen] = React.useState(false);
  const [browserEnabled, setBrowserEnabled] = React.useState(true);
  const [desktopAccess, setDesktopAccess] = React.useState<"off" | "selected" | "all">("selected");
  return <main style={{ padding: 12, display: "flex", justifyContent: "flex-end", height: "100vh" }}><MenuPopover label="Add to message" trigger="+" placement="below" panelClassName="chat-tools-popover-panel" onOpenChange={setOpen}><div className="menu-section chat-capability-group"><div className="chat-capability-summary">Project files <small>Choose a project</small></div><button type="button" className="menu-action">Shell <small>Off</small></button>{open ? <VisualTestingControls conversationId={null} threadId={null} browserEnabled={browserEnabled} onBrowserEnabled={setBrowserEnabled} desktopAccess={desktopAccess} onDesktopAccess={setDesktopAccess} /> : null}</div></MenuPopover></main>;
}
window.fixture.showToolMenu = () => root.render(<ToolMenuFixture />);
window.fixture.showSidebar = (width = 232) => root.render(<div className="app" style={{ "--navigation-width": `${width}px`, height: "100vh" } as React.CSSProperties}><WorkbenchSidebar
  tab="chat" collapsed={false} width={width} onCollapsedChange={() => {}} onWidthChange={() => {}} onNavigate={() => {}}
  backendOk={true} backendStatus="Ready" activeConversationId={null} historyRevision={0} projectRevision={0}
  onOpenConversation={item => { window.fixture.openedChat = item.id; window.fixture.chatClicks = (window.fixture.chatClicks ?? 0) + 1; }}
  onNewChat={() => {}} onAddProject={() => {}} onHistoryNotice={() => {}}
/><main /></div>);
function FileTreeFixture() {
  const [projectId, setProjectId] = React.useState("tree-a");
  const [selectedPath, setSelectedPath] = React.useState("");
  const [revision, setRevision] = React.useState(0);
  window.fixture.switchFileProject = () => { setSelectedPath(""); setProjectId("tree-b"); };
  window.fixture.refreshFiles = () => setRevision(value => value + 1);
  return <main style={{ width: 380, height: 700 }}><ChatDock page="files" onPage={() => {}} projectId={projectId} runIds={[]}
    selectedPath={selectedPath} onSelectPath={value => { (window.fixture.selectedPaths ??= []).push(value); setSelectedPath(value); }} fileRevision={String(revision)} /></main>;
}
window.fixture.showFileTree = () => root.render(<FileTreeFixture />);
root.render(<main style={{ padding: 20 }}><SourceScope.Provider value={{ sessionId: "chat_fixture" }}><p><SourceLink href={`workbench-source://asset_ready/${sha}?source=Paragraph%2024&line=24&start=12&end=120`}>Read selected passage</SourceLink></p><p><SourceLink href={`workbench-source://asset_error/${sha}?source=Page%203&line=3&start=0&end=100`}>Read missing passage</SourceLink></p></SourceScope.Provider><button type="button">Next focus target</button><ImagePreview name="Retained image" src={imageData} /><MenuPopover label="Test actions" trigger="Actions"><button type="button">First action</button></MenuPopover></main>);
