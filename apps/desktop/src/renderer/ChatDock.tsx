import { useEffect, useRef, useState } from "react";
import { Tree, type NodeRendererProps } from "react-arborist";
import type { SchemaProjectFileChangeView, SchemaProjectFileContent, SchemaProjectFile } from "../generated/shared-contracts/openapi";
import { request } from "./api";
import { errorMessage } from "./errors";
import { ConfirmNote } from "./ConfirmNote";
import { Notice } from "./Notice";
import { ImagePreview, safeImageDataUrl } from "./ImagePreview";
import { ChatRetainedFiles } from "./ChatRetainedFiles";
import { LibraryPanel } from "./LibraryPanel";
import { RunMemoryProposals } from "./RunMemoryProposals";
import { editorTheme, ensureMonaco } from "./monacoSetup";
import "./ChatDock.css";

export type DockPage = "changes" | "files" | "library";
type FileChange = SchemaProjectFileChangeView;

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
  selectedChangeId: string;
  selectedPath: string;
  onSelectChange: (id: string) => void;
  onSelectPath: (path: string) => void;
  conversationId?: string;
  projectPath?: string | null;
  width: number;
  onOpenKnowledge?: () => void;
  onReuseAssets?: (assets: { id: string }[]) => void;
  showPages?: boolean;
}) {
  return <div className="chat-dock">
    {props.showPages === false ? null : <div className="chat-dock-pages" role="tablist" aria-label="Dock pages">
      {(["changes", "files", "library"] as const).map(page => <button key={page} type="button" role="tab" aria-selected={props.page === page} aria-pressed={props.page === page} onClick={() => props.onPage(page)}>{page === "changes" ? "Changes" : page === "files" ? "Files" : "Library"}</button>)}
    </div>}
    <div className="chat-dock-body">
      {props.page === "changes" ? <ChangesPage {...props} /> : null}
      {props.page === "files" ? <FilesPage {...props} /> : null}
      {props.page === "library" ? <LibraryPanel sessionId={props.conversationId} projectPath={props.projectPath} onReuseAssets={(_result, assets) => props.onReuseAssets?.(assets)} /> : null}
    </div>
  </div>;
}

function ChangesPage(props: {
  runIds: string[];
  currentRunId?: string | null;
  currentRunStatus?: string;
  selectedChangeId: string;
  onSelectChange: (id: string) => void;
  width: number;
  onOpenKnowledge?: () => void;
}) {
  const [runId, setRunId] = useState(props.currentRunId ?? props.runIds.at(-1) ?? "");
  const [changes, setChanges] = useState<FileChange[]>([]);
  const [error, setError] = useState("");
  const [confirm, setConfirm] = useState(false);
  const [busy, setBusy] = useState(false);
  const generation = useRef(0);
  const selectedId = useRef(props.selectedChangeId);
  selectedId.current = props.selectedChangeId;
  const ids = [...new Set([...props.runIds, ...(props.currentRunId ? [props.currentRunId] : [])])].reverse();
  const selected = changes.find(item => item.change.id === props.selectedChangeId) ?? changes[0];
  useEffect(() => { setRunId(props.currentRunId ?? props.runIds.at(-1) ?? ""); }, [props.currentRunId, props.runIds.join("|")]);
  useEffect(() => {
    const owner = ++generation.current;
    if (!runId) { setChanges([]); return; }
    void request<FileChange[]>(`/v1/agent-runs/${runId}/file-changes`).then(next => {
      if (generation.current !== owner) return;
      setChanges(next);
      if (!next.some(item => item.change.id === selectedId.current)) props.onSelectChange(next[0]?.change.id ?? "");
    }).catch(failure => { if (generation.current === owner) setError(errorMessage(failure)); });
    return () => { generation.current += 1; };
  }, [runId, props.currentRunStatus, props.onSelectChange]);
  async function reverse() {
    if (!selected || busy || !selected.reversal_available) return;
    const owner = generation.current;
    setBusy(true);
    try {
      const next = await request<FileChange>(`/v1/agent-runs/${runId}/file-changes/${selected.change.id}/reverse`, { method: "POST" });
      if (generation.current === owner) setChanges(current => current.map(item => item.change.id === next.change.id ? next : item));
      setConfirm(false);
    } catch (failure) {
      if (generation.current === owner) setError(errorMessage(failure));
    } finally {
      setBusy(false);
    }
  }
  const textReady = selected?.diff != null;
  const before = selected?.change.before.text ?? "";
  const after = selected?.change.after?.text ?? "";
  return <>
    {ids.length ? <label>Turn<select aria-label="File changes turn" value={runId} onChange={event => setRunId(event.target.value)}>{ids.map(id => <option key={id} value={id}>{id === props.currentRunId ? "Latest turn" : id}</option>)}</select></label> : null}
    {error ? <Notice tone="error">{error}</Notice> : null}
    {!changes.length ? <p className="hint">No recorded project file changes for this turn.</p> : <ul className="plain-list file-change-list">{changes.map(item => <li key={item.change.id}><button type="button" aria-pressed={item.change.id === selected?.change.id} onClick={() => { props.onSelectChange(item.change.id); setConfirm(false); }}>{item.change.destination ? `${item.change.path} → ${item.change.destination}` : item.change.path}</button></li>)}</ul>}
    {selected && textReady ? <div className="chat-dock-editor" aria-label="File difference"><MonacoDiff original={before} modified={after} sideBySide={props.width >= 640} /></div> : selected ? <p className="hint">{selected.diff_unavailable_reason || "The difference is unavailable."}</p> : null}
    {selected?.reversal_available ? confirm ? <ConfirmNote className="notice" disabled={busy} confirmLabel="Reverse change" cancelLabel="Keep change" onConfirm={() => void reverse()} onCancel={() => setConfirm(false)}>Reverse this file change? The current file must still match the recorded result.</ConfirmNote> : <button type="button" disabled={busy} onClick={() => setConfirm(true)}>Reverse this file change</button> : selected ? <p className="hint">{selected.reversal_unavailable_reason || selected.note}</p> : null}
    {props.currentRunId && props.currentRunStatus && props.onOpenKnowledge ? <RunMemoryProposals runId={props.currentRunId} status={props.currentRunStatus} onOpenKnowledge={props.onOpenKnowledge} /> : null}
  </>;
}

function FilesPage(props: {
  projectId?: string | null;
  selectedPath: string;
  onSelectPath: (path: string) => void;
  conversationId?: string;
  runIds: string[];
  currentRunId?: string | null;
  currentRunStatus?: string;
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

function MonacoDiff({ original, modified, sideBySide }: { original: string; modified: string; sideBySide: boolean }) {
  const Diff = useMonacoDiff();
  if (!Diff) return <p className="hint">Opening the difference…</p>;
  return <Diff original={original} modified={modified} language="plaintext" theme={editorTheme()} height="100%" options={{ readOnly: true, domReadOnly: true, renderSideBySide: sideBySide, originalEditable: false, scrollBeyondLastLine: false }} />;
}

function MonacoFile({ text }: { text: string }) {
  const Editor = useMonacoFile();
  if (!Editor) return <pre className="file-change-diff">{text}</pre>;
  return <Editor value={text} language="plaintext" theme={editorTheme()} height="100%" options={{ readOnly: true, domReadOnly: true, scrollBeyondLastLine: false }} />;
}

function useMonacoDiff() {
  const [Diff, setDiff] = useState<typeof import("@monaco-editor/react").DiffEditor | null>(null);
  useEffect(() => {
    let cancelled = false;
    void ensureMonaco().then(() => import("@monaco-editor/react")).then(mod => { if (!cancelled) setDiff(() => mod.DiffEditor); });
    return () => { cancelled = true; };
  }, []);
  return Diff;
}

function useMonacoFile() {
  const [Editor, setEditor] = useState<typeof import("@monaco-editor/react").Editor | null>(null);
  useEffect(() => {
    let cancelled = false;
    void ensureMonaco().then(() => import("@monaco-editor/react")).then(mod => { if (!cancelled) setEditor(() => mod.Editor); });
    return () => { cancelled = true; };
  }, []);
  return Editor;
}
