import { useEffect, useRef, useState } from "react";
import { Tree, type NodeRendererProps } from "react-arborist";
import type { SchemaProjectFileContent, SchemaProjectFile } from "../generated/shared-contracts/openapi";
import { request } from "./api";
import { errorMessage } from "./errors";
import { Notice } from "./Notice";
import { ImagePreview, safeImageDataUrl } from "./ImagePreview";
import { ChatRetainedFiles } from "./ChatRetainedFiles";
import { LibraryPanel } from "./LibraryPanel";
import { RunMemoryProposals } from "./RunMemoryProposals";
import { editorFontSize, editorTheme, ensureMonaco } from "./monacoSetup";
import "./ChatDock.css";

export type DockPage = "files" | "library";

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
  onReuseAssets?: (assets: { id: string }[]) => void;
  showPages?: boolean;
}) {
  return <div className="chat-dock">
    {props.showPages === false ? null : <div className="chat-dock-pages" role="tablist" aria-label="Dock pages">
      {(["files", "library"] as const).map(page => <button key={page} type="button" role="tab" aria-selected={props.page === page} aria-pressed={props.page === page} onClick={() => props.onPage(page)}>{page === "files" ? "Files" : "Library"}</button>)}
    </div>}
    <div className="chat-dock-body">
      {props.page === "files" ? <FilesPage {...props} /> : null}
      {props.page === "library" ? <LibraryPanel sessionId={props.conversationId} projectPath={props.projectPath} onReuseAssets={(_result, assets) => props.onReuseAssets?.(assets)} /> : null}
    </div>
  </div>;
}

function FilesPage(props: {
  projectId?: string | null;
  selectedPath: string;
  onSelectPath: (path: string) => void;
  conversationId?: string;
  runIds: string[];
  currentRunId?: string | null;
  currentRunStatus?: string;
  onOpenKnowledge?: () => void;
}) {
  const [nodes, setNodes] = useState<FileNode[]>([]);
  const [filter, setFilter] = useState("");
  const [error, setError] = useState("");
  const [file, setFile] = useState<SchemaProjectFileContent | null>(null);
  const treeRef = useRef<HTMLDivElement>(null);
  const [treeHeight, setTreeHeight] = useState(240);
  useEffect(() => {
    if (!props.projectId) { setNodes([]); return; }
    let cancelled = false;
    void request<{ entries: SchemaProjectFile[] }>(`/v1/projects/${props.projectId}/files`).then(listing => {
      if (!cancelled) setNodes(listing.entries.map(entry => toNode(entry)));
    }).catch(failure => { if (!cancelled) setError(errorMessage(failure)); });
    return () => { cancelled = true; };
  }, [props.projectId]);
  useEffect(() => {
    const element = treeRef.current;
    if (!element || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(entries => setTreeHeight(Math.max(160, Math.floor(entries[0]?.contentRect.height || 240))));
    observer.observe(element);
    return () => observer.disconnect();
  }, []);
  useEffect(() => {
    if (!props.projectId || !props.selectedPath) { setFile(null); return; }
    let cancelled = false;
    void request<SchemaProjectFileContent>(`/v1/projects/${props.projectId}/file?path=${encodeURIComponent(props.selectedPath)}`).then(next => {
      if (!cancelled) setFile(next);
    }).catch(failure => { if (!cancelled) setError(errorMessage(failure)); });
    return () => { cancelled = true; };
  }, [props.projectId, props.selectedPath]);
  async function openDirectory(id: string) {
    if (!props.projectId) return;
    const listing = await request<{ entries: SchemaProjectFile[] }>(`/v1/projects/${props.projectId}/files?path=${encodeURIComponent(id)}`);
    setNodes(current => replaceChildren(current, id, listing.entries.map(entry => toNode(entry))));
  }
  const image = safeImageDataUrl(file?.image_data_url);
  return <>
    <p className="hint">Project files</p>
    {!props.projectId ? <p className="hint">This conversation has no project folder.</p> : <>
      <label>Filter<input aria-label="Filter project files" value={filter} onChange={event => setFilter(event.target.value)} /></label>
      {error ? <Notice tone="error">{error}</Notice> : null}
      <div className="project-file-tree" ref={treeRef}>
        <Tree<FileNode>
          data={nodes}
          width="100%"
          height={treeHeight}
          indent={16}
          rowHeight={28}
          disableDrag
          disableDrop
          disableEdit
          openByDefault={false}
          searchTerm={filter}
          searchMatch={(node, term) => node.data.name.toLowerCase().includes(term.toLowerCase())}
          childrenAccessor={node => node.kind === "directory" ? node.children ?? null : []}
          idAccessor="path"
          onToggle={id => {
            const node = findNode(nodes, id);
            if (node?.kind === "directory" && node.children == null) void openDirectory(id).catch(failure => setError(errorMessage(failure)));
          }}
          onActivate={node => { if (node.data.kind === "file") props.onSelectPath(node.data.path); }}
        >
          {FileRow}
        </Tree>
      </div>
    </>}
    {file?.text != null ? <div className="chat-dock-editor" aria-label="Project file"><MonacoFile text={file.text} /></div> : file?.text_unavailable_reason ? <p className="hint">{file.text_unavailable_reason}</p> : null}
    {image && file ? <ImagePreview src={image} name={file.path} /> : null}
    {props.conversationId ? <section aria-label="Retained copies"><h3>Retained copies</h3><ChatRetainedFiles compact conversationId={props.conversationId} runIds={props.runIds} currentRunId={props.currentRunId} currentRunStatus={props.currentRunStatus} onReuse={() => undefined} /></section> : null}
    {props.currentRunId && props.currentRunStatus && props.onOpenKnowledge ? <RunMemoryProposals runId={props.currentRunId} status={props.currentRunStatus} onOpenKnowledge={props.onOpenKnowledge} /> : null}
  </>;
}

function FileRow({ node, style }: NodeRendererProps<FileNode>) {
  return <div style={style} className="project-file-row">
    <button type="button" onClick={() => node.isInternal && node.toggle()}>{node.isInternal ? (node.isOpen ? "▾" : "▸") : ""} {node.data.name}{node.data.kind === "file" ? "" : ""}</button>
  </div>;
}

function toNode(entry: SchemaProjectFile): FileNode {
  return { id: entry.path, name: entry.name, path: entry.path, kind: entry.kind, children: entry.kind === "directory" ? null : [] };
}

function findNode(nodes: FileNode[], path: string): FileNode | undefined {
  for (const node of nodes) {
    if (node.path === path) return node;
    const child = node.children ? findNode(node.children, path) : undefined;
    if (child) return child;
  }
  return undefined;
}

function replaceChildren(nodes: FileNode[], path: string, children: FileNode[]): FileNode[] {
  return nodes.map(node => node.path === path ? { ...node, children } : node.children ? { ...node, children: replaceChildren(node.children, path, children) } : node);
}

function MonacoFile({ text }: { text: string }) {
  const Editor = useMonacoFile();
  if (!Editor) return <pre className="plain-file-content">{text}</pre>;
  return <Editor value={text} language="plaintext" theme={editorTheme()} height="100%" options={{ readOnly: true, domReadOnly: true, scrollBeyondLastLine: false, fontSize: editorFontSize() }} />;
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
