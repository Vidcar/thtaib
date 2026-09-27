import { useEffect, useRef, useState } from "react";
import { Tree, type NodeRendererProps, type TreeApi } from "react-arborist";
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
}) {
  return <div className="chat-dock">
    {props.showPages === false ? null : <div className="chat-dock-pages" role="tablist" aria-label="Dock pages">
      <button type="button" role="tab" aria-selected aria-pressed onClick={() => props.onPage("files")}>Files</button>
    </div>}
    <div className="chat-dock-body">
      {props.page === "files" ? <FilesPage key={props.projectId ?? "no-project"} {...props} /> : null}
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
}) {
  const [nodes, setNodes] = useState<FileNode[]>([]);
  const [filter, setFilter] = useState("");
  const [treeError, setTreeError] = useState("");
  const [fileError, setFileError] = useState("");
  const [file, setFile] = useState<SchemaProjectFileContent | null>(null);
  const [refreshVersion, setRefreshVersion] = useState(0);
  const treeRef = useRef<HTMLDivElement>(null);
  const treeApi = useRef<TreeApi<FileNode> | null>(null);
  const nodesRef = useRef<FileNode[]>([]);
  const expandedPaths = useRef(new Set<string>());
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
    })().catch(failure => { if (revision === treeRevision.current) setTreeError(errorMessage(failure)); });
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
    setFile(null);
    setFileError("");
    if (!props.projectId || !props.selectedPath) return;
    let cancelled = false;
    void request<SchemaProjectFileContent>(`/v1/projects/${encodeURIComponent(props.projectId)}/file?path=${encodeURIComponent(props.selectedPath)}`).then(next => {
      if (!cancelled) setFile(next);
    }).catch(failure => { if (!cancelled) setFileError(errorMessage(failure)); });
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
      <label>Filter<input aria-label="Filter project files" value={filter} onChange={event => setFilter(event.target.value)} /></label>
      {treeError || fileError ? <Notice tone="error">{[treeError, fileError].filter(Boolean).join(" · ")}</Notice> : null}
      <div className="project-file-tree" ref={treeRef}>
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
          searchTerm={filter}
          searchMatch={(node, term) => node.data.name.toLowerCase().includes(term.toLowerCase())}
          childrenAccessor={node => node.kind === "directory" ? node.children ?? [] : null}
          idAccessor="path"
          onToggle={id => {
            if (!treeApi.current?.isOpen(id)) { expandedPaths.current.delete(id); return; }
            expandedPaths.current.add(id);
            const node = findNode(nodesRef.current, id);
            if (node?.kind === "directory") void openDirectory(id);
          }}
          onActivate={node => { if (node.data.kind === "file") props.onSelectPath(node.data.path); }}
        >
          {FileRow}
        </Tree>
      </div>
    </>}
    {file?.text != null ? <div className="chat-dock-editor" aria-label="Project file"><MonacoFile text={file.text} /></div> : file?.text_unavailable_reason ? <p className="hint">{file.text_unavailable_reason}</p> : null}
    {image && file ? <ImagePreview src={image} name={file.path} /> : null}
    {props.conversationId ? <section aria-label="Chat files and retained copies"><h3>Chat files</h3><ChatRetainedFiles compact conversationId={props.conversationId} runIds={props.runIds} currentRunId={props.currentRunId} currentRunStatus={props.currentRunStatus} onReuse={ids => props.onReuseAssets?.(ids.map(id => ({ id })))} /></section> : null}
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
