import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { Tree, type NodeRendererProps, type TreeApi } from "react-arborist";
import type { editor as MonacoEditor, IDisposable } from "monaco-editor";
import type { SchemaProjectFileContent, SchemaProjectFile } from "../generated/shared-contracts/openapi";
import { request } from "./api";
import { errorMessage } from "./errors";
import { Notice } from "./Notice";
import { ImagePreview, safeImageDataUrl } from "./ImagePreview";
import { ChatRetainedFiles } from "./ChatRetainedFiles";
import { RunMemoryProposals } from "./RunMemoryProposals";
import { ProjectPreview } from "./ProjectPreview";
import { editorFontSize, editorTheme, ensureMonaco } from "./monacoSetup";
import "./ChatDock.css";

export type DockPage = "files";
export type ChatRailPage = DockPage | "browser" | "helpers";
export interface ChatFileView {
  state: MonacoEditor.ICodeEditorViewState | null;
  scrollTop: number;
  scrollLeft: number;
}
export interface ChatDockView {
  open: boolean;
  page: ChatRailPage;
  helper: string;
  projectId: string | null;
  path: string;
  filter: string;
  folders: string[];
  previewId: string;
  previewOpen: boolean;
  filesScroll: number;
  helpersScroll: number;
  treeScroll: number;
  treeScrollLeft: number;
  treeSelection: string;
  fileViews: Record<string, ChatFileView>;
}
const emptyDockView: ChatDockView = { open: false, page: "files", helper: "", projectId: null, path: "", filter: "", folders: [], previewId: "", previewOpen: true, filesScroll: 0, helpersScroll: 0, treeScroll: 0, treeScrollLeft: 0, treeSelection: "", fileViews: {} };
const RESERVED_PROJECT_ROUTES = new Set(["memories", "skills", "retrieved", "conversation_history", "large_tool_results"]);
/** A dock selection is one relative project file. Framework routes and unsafe paths are refused locally. */
export function acceptedProjectFilePath(value: string): string {
  const normalized = value.replaceAll("\\", "/").trim();
  if (!normalized || normalized.startsWith("//") || /[\u0000-\u001f]/.test(normalized)) return "";
  const parts = normalized.replace(/^\/+/, "").split("/");
  if (!parts.length || parts.some(part => !part || part === "." || part === ".." || part.includes(":"))) return "";
  if (RESERVED_PROJECT_ROUTES.has(parts[0].toLowerCase())) return "";
  return parts.join("/");
}
const PROJECT_FILE_KNOWLEDGE_NOTICE = "That path is managed knowledge or history, not a project file.";
const PROJECT_FILE_OUTSIDE_NOTICE = "That path is outside the project.";
/** Copy for a path acceptedProjectFilePath refused. Knowledge wording is only the reserved framework routes. */
export function refusedProjectPathNotice(value: string): string {
  if (!value.trim() || acceptedProjectFilePath(value)) return "";
  const normalized = value.replaceAll("\\", "/").trim();
  if (normalized.startsWith("//") || /[\u0000-\u001f]/.test(normalized)) return PROJECT_FILE_OUTSIDE_NOTICE;
  const parts = normalized.replace(/^\/+/, "").split("/");
  if (!parts.length || parts.some(part => !part || part === "." || part === ".." || part.includes(":"))) return PROJECT_FILE_OUTSIDE_NOTICE;
  if (RESERVED_PROJECT_ROUTES.has((parts[0] ?? "").toLowerCase())) return PROJECT_FILE_KNOWLEDGE_NOTICE;
  return PROJECT_FILE_OUTSIDE_NOTICE;
}
export function isRefusedProjectPathNotice(message: string): boolean {
  return message === PROJECT_FILE_KNOWLEDGE_NOTICE || message === PROJECT_FILE_OUTSIDE_NOTICE;
}
export function chatDockGeometry(preferredWidth: number, availableWidth: number) {
  const max = Math.max(0, Math.min(1100, Math.floor(availableWidth * 0.48), Math.floor(availableWidth - 400)));
  return { width: Math.min(preferredWidth, max), max, canOpen: availableWidth >= 680 };
}
/** Local presentation state only; file, helper and browser authority stays on the backend. */
export function useConversationDockView(conversationId: string) {
  const views = useRef(new Map<string, ChatDockView>());
  const [, render] = useState(0);
  const key = conversationId || "new";
  if (!views.current.has(key)) {
    let saved: Partial<ChatDockView> = {};
    try { saved = JSON.parse(window.localStorage?.getItem(`workbench.chat.dock.view:${key}`) || "{}"); } catch { /* Use the closed default. */ }
    const path = typeof saved.path === "string" ? acceptedProjectFilePath(saved.path) : "";
    const next = { ...emptyDockView, ...saved, path, open: saved.open === true, page: ["files", "browser", "helpers"].includes(saved.page ?? "") ? saved.page! : "files", folders: Array.isArray(saved.folders) ? saved.folders.filter(item => typeof item === "string") : [] };
    views.current.set(key, next);
    if (typeof saved.path === "string" && saved.path !== path) {
      try { window.localStorage?.setItem(`workbench.chat.dock.view:${key}`, JSON.stringify(next)); } catch { /* The open view still omits the refused path. */ }
    }
  }
  const update = useCallback((patch: Partial<ChatDockView>) => {
    const next = { ...views.current.get(key)!, ...patch };
    views.current.set(key, next);
    try { window.localStorage?.setItem(`workbench.chat.dock.view:${key}`, JSON.stringify(next)); } catch { /* The open app still remembers this view. */ }
    render(value => value + 1);
  }, [key]);
  return [views.current.get(key)!, update] as const;
}

interface FileNode {
  id: string;
  name: string;
  path: string;
  kind: "file" | "directory";
  children?: FileNode[] | null;
}

export function ChatDock(props: {
  page: DockPage;
  onPage: (page: DockPage) => void;
  projectId?: string | null;
  runIds: string[];
  currentRunId?: string | null;
  currentRunStatus?: string;
  selectedPath: string;
  onSelectPath: (path: string) => void;
  conversationId?: string;
  projectPath?: string | null;
  onOpenKnowledge?: () => void;
  onUseMemoryVersion?: (versionId: string) => Promise<void> | void;
  onReuseAssets?: (assets: { id: string }[]) => void;
  showPages?: boolean;
  threadId?: string | null;
  previewEnabled?: boolean;
  fileRevision?: string;
  view?: ChatDockView;
  onViewChange?: (patch: Partial<ChatDockView>) => void;
}) {
  return <div className="chat-dock">
    {props.showPages === false ? null : <div className="chat-dock-pages" role="tablist" aria-label="Dock pages">
      <button type="button" role="tab" aria-selected aria-pressed onClick={() => props.onPage("files")}>Files</button>
    </div>}
    <div className="chat-dock-body">
      {props.page === "files" ? <FilesPage key={`${props.conversationId ?? "new"}:${props.projectId ?? "no-project"}`} {...props} /> : null}
    </div>
  </div>;
}

function FilesPage(props: {
  threadId?: string | null;
  previewEnabled?: boolean;
  fileRevision?: string;
  projectId?: string | null;
  selectedPath: string;
  onSelectPath: (path: string) => void;
  conversationId?: string;
  runIds: string[];
  currentRunId?: string | null;
  currentRunStatus?: string;
  onOpenKnowledge?: () => void;
  onUseMemoryVersion?: (versionId: string) => Promise<void> | void;
  onReuseAssets?: (assets: { id: string }[]) => void;
  view?: ChatDockView;
  onViewChange?: (patch: Partial<ChatDockView>) => void;
}) {
  const [nodes, setNodes] = useState<FileNode[]>([]);
  const [filter, setFilter] = useState(props.view?.filter ?? "");
  const [treeError, setTreeError] = useState("");
  const [fileError, setFileError] = useState("");
  const [file, setFile] = useState<SchemaProjectFileContent | null>(null);
  const [treeLoading, setTreeLoading] = useState(Boolean(props.projectId));
  const [fileLoading, setFileLoading] = useState(false);
  const [refreshVersion, setRefreshVersion] = useState(0);
  const treeRef = useRef<HTMLDivElement>(null);
  const treeApi = useRef<TreeApi<FileNode> | null>(null);
  const treeRestored = useRef(false);
  const fileViews = useRef(props.view?.fileViews ?? {});
  const nodesRef = useRef<FileNode[]>([]);
  const expandedPaths = useRef(new Set(props.view?.folders ?? []));
  const treeRevision = useRef(0);
  const directoryRequests = useRef(new Map<string, number>());
  const [treeHeight, setTreeHeight] = useState(240);
  function updateNodes(update: (current: FileNode[]) => FileNode[]) {
    nodesRef.current = update(nodesRef.current);
    setNodes(nodesRef.current);
  }
  useEffect(() => {
    const revision = ++treeRevision.current;
    setTreeError("");
    setTreeLoading(Boolean(props.projectId));
    if (!props.projectId) { updateNodes(() => []); return; }
    void (async () => {
      const listing = await request<{ entries: SchemaProjectFile[] }>(`/v1/projects/${encodeURIComponent(props.projectId!)}/files`);
      if (revision !== treeRevision.current) return;
      updateNodes(current => mergeEntries(listing.entries, current));
      // Refresh parents before children: a removed directory is never restored
      // by a late nested response, and open descendants retain their contents.
      const expanded = [...expandedPaths.current].sort((left, right) => left.split("/").length - right.split("/").length);
      for (const path of expanded) {
        if (revision !== treeRevision.current) return;
        if (findNode(nodesRef.current, path)?.kind === "directory") await openDirectory(path, revision);
      }
    })().catch(failure => { if (revision === treeRevision.current) setTreeError(errorMessage(failure)); }).finally(() => { if (revision === treeRevision.current) setTreeLoading(false); });
    return () => { treeRevision.current += 1; };
  }, [props.projectId, props.currentRunId, props.currentRunStatus, props.fileRevision, refreshVersion]);
  useEffect(() => {
    const element = treeRef.current;
    if (!element || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(entries => setTreeHeight(Math.max(160, Math.floor(entries[0]?.contentRect.height || 240))));
    observer.observe(element);
    return () => observer.disconnect();
  }, []);
  useEffect(() => {
    const tree = treeApi.current;
    if (treeLoading || !tree || treeRestored.current) return;
    const selected = props.view?.treeSelection || props.selectedPath;
    if (selected && tree.get(selected)) tree.setSelection({ ids: [selected], anchor: selected, mostRecent: selected });
    tree.scrollToOffset(props.view?.treeScroll ?? 0);
    if (tree.listEl.current) tree.listEl.current.scrollLeft = props.view?.treeScrollLeft ?? 0;
    treeRestored.current = true;
  }, [treeLoading, nodes, treeHeight]);
  useEffect(() => {
    setFile(null);
    setFileError("");
    const readablePath = acceptedProjectFilePath(props.selectedPath);
    setFileLoading(Boolean(props.projectId && readablePath));
    if (props.projectId && props.selectedPath && !readablePath) {
      const refusal = refusedProjectPathNotice(props.selectedPath);
      if (refusal) setFileError(refusal);
    }
    if (!props.projectId || !readablePath) return;
    let cancelled = false;
    void request<SchemaProjectFileContent>(`/v1/projects/${encodeURIComponent(props.projectId)}/file?path=${encodeURIComponent(readablePath)}`).then(next => {
      if (!cancelled) setFile(next);
    }).catch(failure => { if (!cancelled) setFileError(errorMessage(failure)); }).finally(() => { if (!cancelled) setFileLoading(false); });
    return () => { cancelled = true; };
  }, [props.projectId, props.selectedPath, props.currentRunId, props.currentRunStatus, props.fileRevision, refreshVersion]);
  async function openDirectory(id: string, revision = treeRevision.current) {
    if (!props.projectId) return;
    const sequence = (directoryRequests.current.get(id) ?? 0) + 1;
    directoryRequests.current.set(id, sequence);
    try {
      const listing = await request<{ entries: SchemaProjectFile[] }>(`/v1/projects/${encodeURIComponent(props.projectId)}/files?path=${encodeURIComponent(id)}`);
      if (revision !== treeRevision.current || sequence !== directoryRequests.current.get(id)) return;
      updateNodes(current => replaceChildren(current, id, listing.entries));
    } catch (failure) {
      if (revision === treeRevision.current && sequence === directoryRequests.current.get(id)) setTreeError(errorMessage(failure));
    }
  }
  const image = safeImageDataUrl(file?.image_data_url);
  return <>
    <div className="project-preview-actions"><span className="hint">Project files</span>{props.projectId ? <button type="button" onClick={() => setRefreshVersion(value => value + 1)}>Refresh</button> : null}</div>
    <ProjectPreview threadId={props.threadId} selectedPath={props.selectedPath} enabled={Boolean(props.previewEnabled)} revision={`${props.currentRunId}:${props.currentRunStatus}`} />
    {!props.projectId ? <p className="hint">This conversation has no project folder.</p> : <>
      <label>Filter<input aria-label="Filter project files" value={filter} onChange={event => { setFilter(event.target.value); props.onViewChange?.({ filter: event.target.value }); }} /></label>
      {treeLoading ? <p className="hint" role="status">Loading project files…</p> : !nodes.length && !treeError ? <p className="hint">This project has no files.</p> : null}
      {treeError || fileError ? <Notice tone="error">{[treeError, fileError].filter(Boolean).join(" · ")}</Notice> : null}
      <div className="project-file-tree" ref={treeRef} onScrollCapture={event => {
        const list = treeApi.current?.listEl.current;
        if (treeRestored.current && event.target === list) props.onViewChange?.({ treeScrollLeft: list.scrollLeft });
      }}>
        <Tree<FileNode>
          ref={treeApi}
          data={nodes}
          width="100%"
          height={treeHeight}
          indent={16}
          rowHeight={28}
          disableDrag
          disableDrop
          disableEdit
          openByDefault={false}
          initialOpenState={Object.fromEntries((props.view?.folders ?? []).map(path => [path, true]))}
          searchTerm={filter}
          searchMatch={(node, term) => node.data.name.toLowerCase().includes(term.toLowerCase())}
          childrenAccessor={node => node.kind === "directory" ? node.children ?? [] : null}
          idAccessor="path"
          aria-label="Project file tree"
          onScroll={({ scrollOffset, scrollUpdateWasRequested }) => {
            if (treeRestored.current && !scrollUpdateWasRequested) props.onViewChange?.({ treeScroll: scrollOffset });
          }}
          onSelect={selection => {
            if (treeRestored.current) props.onViewChange?.({ treeSelection: selection[0]?.data.path ?? "" });
          }}
          onToggle={id => {
            if (!treeApi.current?.isOpen(id)) { expandedPaths.current.delete(id); props.onViewChange?.({ folders: [...expandedPaths.current] }); return; }
            expandedPaths.current.add(id);
            props.onViewChange?.({ folders: [...expandedPaths.current] });
            const node = findNode(nodesRef.current, id);
            if (node?.kind === "directory") void openDirectory(id);
          }}
          onActivate={node => { if (node.data.kind === "file") props.onSelectPath(node.data.path); }}
        >
          {FileRow}
        </Tree>
      </div>
    </>}
    {fileLoading ? <p className="hint" role="status">Loading {props.selectedPath}…</p> : null}
    {file?.text != null ? <div className="chat-dock-editor" aria-label="Project file" data-path={file.path}><MonacoFile key={`${props.projectId}:${file.path}`} text={file.text} view={props.view?.fileViews?.[`${props.projectId}:${file.path}`]} onViewChange={view => {
      const next = { ...fileViews.current, [`${props.projectId}:${file.path}`]: view };
      fileViews.current = next;
      props.onViewChange?.({ fileViews: next });
    }} /></div> : file?.text_unavailable_reason ? <p className="hint">{file.text_unavailable_reason}</p> : null}
    {image && file ? <ImagePreview src={image} name={file.path} /> : null}
    {props.conversationId ? <section aria-label="Chat files and retained copies"><h3>Chat files</h3><ChatRetainedFiles compact showEmpty conversationId={props.conversationId} currentRunId={props.currentRunId} currentRunStatus={props.currentRunStatus} previewId={props.view?.previewId} previewOpen={props.view?.previewOpen} onPreviewOpen={previewOpen => props.onViewChange?.({ previewOpen })} onPreviewId={previewId => props.onViewChange?.({ previewId })} onReuse={ids => props.onReuseAssets?.(ids.map(id => ({ id })))} /></section> : null}
    {props.currentRunId && props.currentRunStatus && props.onOpenKnowledge ? <RunMemoryProposals runId={props.currentRunId} status={props.currentRunStatus} onOpenKnowledge={props.onOpenKnowledge} onUseMemoryVersion={props.onUseMemoryVersion} /> : null}
  </>;
}

function FileRow({ node, style }: NodeRendererProps<FileNode>) {
  return <div style={style} className="project-file-row">
    <button type="button" aria-expanded={node.isInternal ? node.isOpen : undefined} onClick={event => {
      event.stopPropagation();
      node.select();
      if (node.isInternal) node.toggle();
      else node.activate();
    }}>{node.isInternal ? (node.isOpen ? "▾" : "▸") : ""} {node.data.name}</button>
  </div>;
}

function toNode(entry: SchemaProjectFile): FileNode {
  return { id: entry.path, name: entry.name, path: entry.path, kind: entry.kind };
}

function mergeEntries(entries: SchemaProjectFile[], previous: FileNode[]): FileNode[] {
  const retained = new Map(previous.map(node => [node.path, node]));
  return entries.map(entry => ({ ...toNode(entry), children: entry.kind === "directory" ? retained.get(entry.path)?.children : undefined }));
}

function findNode(nodes: FileNode[], path: string): FileNode | undefined {
  for (const node of nodes) {
    if (node.path === path) return node;
    const child = node.children ? findNode(node.children, path) : undefined;
    if (child) return child;
  }
  return undefined;
}

function replaceChildren(nodes: FileNode[], path: string, entries: SchemaProjectFile[]): FileNode[] {
  return nodes.map(node => node.path === path ? { ...node, children: mergeEntries(entries, node.children ?? []) } : node.children ? { ...node, children: replaceChildren(node.children, path, entries) } : node);
}

function MonacoFile({ text, view, onViewChange }: { text: string; view?: ChatFileView; onViewChange: (view: ChatFileView) => void }) {
  const Editor = useMonacoFile();
  const plain = useRef<HTMLPreElement>(null);
  const restoringPlain = useRef(true);
  const saveView = useRef(onViewChange);
  saveView.current = onViewChange;
  const subscriptions = useRef<IDisposable[]>([]);
  const lastView = useRef(view ?? null);
  useLayoutEffect(() => {
    if (!plain.current) return;
    plain.current.scrollTop = view?.scrollTop ?? 0;
    plain.current.scrollLeft = view?.scrollLeft ?? 0;
  }, [Editor]);
  useLayoutEffect(() => () => {
    for (const subscription of subscriptions.current) subscription.dispose();
    if (lastView.current) saveView.current(lastView.current);
  }, []);
  if (!Editor) return <pre ref={plain} className="plain-file-content" tabIndex={0} onWheel={() => { restoringPlain.current = false; }} onPointerDown={() => { restoringPlain.current = false; }} onKeyDown={() => { restoringPlain.current = false; }} onScroll={event => {
    if (restoringPlain.current) return;
    lastView.current = { state: null, scrollTop: event.currentTarget.scrollTop, scrollLeft: event.currentTarget.scrollLeft };
    saveView.current(lastView.current);
  }}>{text}</pre>;
  return <Editor value={text} language="plaintext" theme={editorTheme()} height="100%" saveViewState={false} onMount={editor => {
    if (view?.state) editor.restoreViewState(view.state);
    else { editor.setScrollTop(view?.scrollTop ?? 0); editor.setScrollLeft(view?.scrollLeft ?? 0); }
    const capture = () => {
      lastView.current = { state: editor.saveViewState(), scrollTop: editor.getScrollTop(), scrollLeft: editor.getScrollLeft() };
      saveView.current(lastView.current);
    };
    subscriptions.current = [editor.onDidScrollChange(capture), editor.onDidChangeCursorSelection(capture)];
    lastView.current = { state: editor.saveViewState(), scrollTop: editor.getScrollTop(), scrollLeft: editor.getScrollLeft() };
  }} options={{ readOnly: true, domReadOnly: true, scrollBeyondLastLine: false, fontSize: editorFontSize() }} />;
}

function useMonacoFile() {
  const [Editor, setEditor] = useState<typeof import("@monaco-editor/react").Editor | null>(null);
  useEffect(() => {
    let cancelled = false;
    void ensureMonaco().then(() => import("@monaco-editor/react")).then(mod => { if (!cancelled) setEditor(() => mod.Editor); }).catch(() => { /* The retained plain-text view remains available. */ });
    return () => { cancelled = true; };
  }, []);
  return Editor;
}
