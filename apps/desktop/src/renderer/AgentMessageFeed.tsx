import type { BaseMessage } from "@langchain/core/messages";
import type { AssembledToolCall } from "@langchain/react";
import type React from "react";
import { memo, useCallback, useContext, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { activityLine, groupActivity, parseTodoList, type TodoItem } from "./activityLine";
import { useChatDock } from "./chatDockContext";
import ReactMarkdown, { defaultUrlTransform } from "react-markdown";
import remarkGfm from "remark-gfm";
import { CopyIconButton } from "./CopyIconButton";
import { Icon } from "./Icon";
import { ImagePreview, safeImageDataUrl } from "./ImagePreview";
import { packet03Api } from "./packet03Api";
import { loadRetainedPreview } from "./retainedFiles";
import { ReadSources, SourceLink, SourceScope, sourceReference } from "./SourceReference";
import { closeUnfinishedMarks, splitStreamingMarkdown } from "./streamingMarkdown";
import type { MatchedPermissionGrant } from "./packet03Api";
import type { AgentRun } from "./types";

export let markdownParseCount = 0;
export let finishedBubbleRenders = 0;

export function resetPaintCounters(): void {
  markdownParseCount = 0;
  finishedBubbleRenders = 0;
}

// Markdown presentation follows the safe ReactMarkdown + remark-gfm pattern from
// langchain-ai/agent-chat-ui at revision 41926d89c9798cebe45a26886d6e437acc5201c1.
// We do not enable raw HTML rehype plugins, so embedded HTML is rendered as text.

interface MessageParts {
  answer: string;
  reasoning: string[];
  attachments: Array<{ label: string; src?: string }>;
  toolBlocks: ToolBlock[];
}

interface ToolBlock {
  id?: string;
  name: string;
  args?: unknown;
  status?: string;
  result?: unknown;
  error?: string;
  authorizationSource?: string;
  authorizationGrant?: MatchedPermissionGrant;
}

export function helperKey(runId: string, toolCallId: string): string {
  return `${runId}:${toolCallId}`;
}

interface DetailSectionProps {
  children: React.ReactNode;
  defaultOpen: boolean;
  id: string;
  onToggle: (id: string, open: boolean) => void;
  openStates: ReadonlyMap<string, boolean>;
  summary: React.ReactNode;
  className: string;
}

function roleLabel(type: string): string {
  switch (type) {
    case "human":
      return "You";
    case "ai":
      return "Assistant";
    case "tool":
      return "Tool";
    case "system":
      return "System";
    default:
      return type || "Message";
  }
}

function messageType(message: BaseMessage): string {
  return message.getType?.() ?? String((message as unknown as { type?: string }).type ?? "message");
}

function stringifyValue(value: unknown): string {
  if (typeof value === "string") {
    return value;
  }
  return value == null ? "" : JSON.stringify(value, null, 2);
}

function toolError(tool: ToolBlock): string | undefined {
  if (tool.error) return tool.error;
  const resultText = Array.isArray(tool.result) ? parseContent(tool.result).answer : stringifyValue(tool.result);
  if (tool.status === "error" || tool.status === "failed") return resultText || "The tool could not complete.";
  // Successful output can discuss errors, for example a log search.
  if (tool.status) return undefined;
  const text = resultText;
  return /^\s*(error|failed|exception|traceback)\b/i.test(text) ? text : undefined;
}

function captureAssetId(text: string): string | null {
  return /\/captures\/(asset_[0-9a-f]{32})\.(?:png|jpg|webp)\b/i.exec(text)?.[1] ?? null;
}

function CapturePreview({ assetId }: { assetId: string }) {
  const scope = useContext(SourceScope);
  const [thumbnail, setThumbnail] = useState("");
  const [name, setName] = useState("Screenshot");
  const [error, setError] = useState("");
  useEffect(() => {
    if (!scope.sessionId) return;
    let stale = false;
    void loadRetainedPreview(assetId, { sessionId: scope.sessionId }).then(preview => {
      if (!stale) { setThumbnail(preview.image_data_url ?? ""); setName(preview.filename); setError(""); }
    }).catch(caught => { if (!stale) setError(caught instanceof Error ? caught.message : String(caught)); });
    return () => { stale = true; };
  }, [assetId, scope.sessionId]);
  if (!scope.sessionId) return null;
  return <div className="tool-capture-preview"><span className="tool-detail-label">Retained screenshot</span>{thumbnail ? <ImagePreview src={thumbnail} name={name} small loadOriginal={async () => {
    const content = await packet03Api.contentAsset(assetId, { sessionId: scope.sessionId });
    return `data:${content.content_type};base64,${content.content_base64 ?? ""}`;
  }} /> : <span className="hint" role={error ? "status" : undefined}>{error || "Loading image…"}</span>}</div>;
}

function imageMarker(part: Record<string, unknown>, index: number): { label: string; src?: string } {
  const sourceObject = part.source && typeof part.source === "object" ? part.source as Record<string, unknown> : undefined;
  const source = part.url || (typeof part.image_url === "string" ? part.image_url : part.image_url && typeof part.image_url === "object" ? (part.image_url as { url?: string }).url : undefined)
    || (typeof part.source === "string" ? part.source : sourceObject?.url)
    || (typeof (part.base64 ?? part.data ?? sourceObject?.data) === "string" ? `data:${part.mime_type ?? part.mimeType ?? sourceObject?.media_type};base64,${part.base64 ?? part.data ?? sourceObject?.data}` : undefined);
  const label = typeof source === "string" && source && !source.startsWith("data:") ? source : `image ${index + 1}`;
  return { label: `Image attachment: ${label}`, src: safeImageDataUrl(source) };
}

function parseContent(content: unknown): MessageParts {
  if (typeof content === "string") {
    return { answer: content, reasoning: [], attachments: [], toolBlocks: [] };
  }
  if (!Array.isArray(content)) {
    return { answer: stringifyValue(content), reasoning: [], attachments: [], toolBlocks: [] };
  }

  const answer: string[] = [];
  const reasoning: string[] = [];
  const attachments: MessageParts["attachments"] = [];
  const toolBlocks: ToolBlock[] = [];

  content.forEach((part) => {
    if (typeof part === "string") {
      answer.push(part);
      return;
    }
    if (!part || typeof part !== "object") {
      return;
    }

    const block = part as Record<string, unknown>;
    const blockType = typeof block.type === "string" ? block.type : "";
    if (blockType === "reasoning") {
      const text = stringifyValue(block.reasoning ?? block.text ?? block.content);
      if (text.trim()) {
        reasoning.push(text);
      }
      return;
    }
    if (blockType === "image" || blockType === "image_url" || blockType === "input_image") {
      attachments.push(imageMarker(block, attachments.length));
      return;
    }
    if (["tool_call", "tool_call_chunk", "invalid_tool_call", "tool_result", "tool", "server_tool_call", "server_tool_call_result"].includes(blockType)) {
      const id = block.tool_call_id ?? block.toolCallId ?? block.callId ?? block.id;
      const tool: ToolBlock = {
        id: typeof id === "string" ? id : undefined,
        name: String(block.name ?? block.tool_name ?? "Tool"),
        args: block.args ?? block.input,
        status: typeof block.status === "string" ? block.status : blockType === "tool_call_chunk" ? "preparing" : undefined,
        result: block.result ?? block.output ?? block.content,
        error: typeof block.error === "string" ? block.error : undefined,
      };
      const previous = tool.id ? toolBlocks.find(item => item.id === tool.id) : undefined;
      if (previous) {
        if (tool.name !== "Tool") previous.name = tool.name;
        if (tool.args !== undefined) previous.args = tool.args;
        if (tool.result !== undefined) previous.result = tool.result;
        if (tool.status) previous.status = tool.status;
        if (tool.error) previous.error = tool.error;
      } else {
        toolBlocks.push(tool);
      }
      return;
    }
    if (typeof block.text === "string") {
      answer.push(block.text);
      return;
    }
    if (typeof block.content === "string") {
      answer.push(block.content);
    }
  });

  return {
    answer: answer.filter(Boolean).join("\n\n"),
    reasoning,
    attachments,
    toolBlocks,
  };
}

function toolResultMessage(message: BaseMessage): ToolBlock | undefined {
  if (messageType(message) !== "tool") return undefined;
  const fields = message as BaseMessage & { tool_call_id?: string; status?: string };
  return { id: fields.tool_call_id, name: message.name ?? "Tool", status: fields.status, result: message.contentBlocks ?? message.content, authorizationSource: typeof message.additional_kwargs.authorization_source === "string" ? message.additional_kwargs.authorization_source : undefined, authorizationGrant: matchedPermissionGrant(message.additional_kwargs.authorization_grant) };
}

function matchedPermissionGrant(value: unknown): MatchedPermissionGrant | undefined {
  if (!value || typeof value !== "object") return undefined;
  const grant = value as Record<string, unknown>;
  if (typeof grant.id !== "string" || !grant.id || typeof grant.display_name !== "string" || !grant.display_name.trim()
    || (grant.scope !== "session" && grant.scope !== "always") || typeof grant.action !== "string"
    || !grant.arguments || typeof grant.arguments !== "object" || Array.isArray(grant.arguments)
    || typeof grant.created_at !== "string" || typeof grant.source_run_id !== "string"
    || (grant.thread_id !== null && typeof grant.thread_id !== "string")
    || (grant.project_path !== null && typeof grant.project_path !== "string")) return undefined;
  return {
    id: grant.id,
    display_name: grant.display_name,
    scope: grant.scope,
    action: grant.action,
    arguments: grant.arguments as Record<string, unknown>,
    created_at: grant.created_at,
    source_run_id: grant.source_run_id,
    thread_id: grant.thread_id,
    project_path: grant.project_path,
  };
}

function SavedPermissionDetails({ grant }: { grant: MatchedPermissionGrant }) {
  return <section aria-label="Matched saved permission">
    <strong>{grant.display_name}</strong>
    <dl className="meta compact">
      <div><dt>Permission</dt><dd>{grant.id}</dd></div>
      <div><dt>Scope</dt><dd>{grant.scope === "always" ? "Always allow" : "This session"}</dd></div>
      <div><dt>Action</dt><dd>{grant.action}</dd></div>
      <div><dt>Project</dt><dd>{grant.project_path ?? "No project"}</dd></div>
      <div><dt>Session</dt><dd>{grant.thread_id ?? (grant.scope === "always" ? "Any session" : "Not recorded")}</dd></div>
      <div><dt>Saved</dt><dd>{grant.created_at}</dd></div>
      <div><dt>Originating run</dt><dd>{grant.source_run_id}</dd></div>
    </dl>
    <span className="tool-detail-label">Matching arguments</span>
    <CodeBlock text={stringifyValue(grant.arguments)} label="Copy permission arguments"><code>{stringifyValue(grant.arguments)}</code></CodeBlock>
    <p className="hint">Recorded when this call was allowed. Review or revoke current grants in Settings → Permissions.</p>
  </section>;
}

function mergeTool(block: ToolBlock, retained: ToolBlock | undefined, live: AssembledToolCall | undefined): ToolBlock {
  return {
    ...block,
    name: live?.name || (block.name !== "Tool" ? block.name : retained?.name) || "Tool",
    args: live?.input ?? live?.args ?? block.args,
    status: retained ? retained.status ?? (toolError(retained) ? "error" : "success") : live?.status ?? block.status,
    result: retained ? retained.result : live?.status === "finished" ? live.output : block.result,
    error: retained?.status === "success" ? undefined : live?.error ?? block.error,
    authorizationSource: retained?.authorizationSource ?? block.authorizationSource,
    authorizationGrant: retained?.authorizationGrant ?? block.authorizationGrant,
  };
}

const TOOL_PATH_KEYS = ["file_path", "path"];
const TOOL_BODY_KEYS = ["content", "text", "file_text", "new_string", "command"];

function decodeJsonString(source: string): string {
  let out = "";
  for (let index = 0; index < source.length; index += 1) {
    const character = source[index];
    if (character === '"') return out;
    if (character !== "\\") {
      out += character;
      continue;
    }
    const next = source[index + 1];
    if (next === undefined) break;
    if (next === "u") {
      const digits = source.slice(index + 2, index + 6);
      if (!/^[0-9a-f]{4}$/i.test(digits)) break;
      out += String.fromCharCode(Number.parseInt(digits, 16));
      index += 5;
      continue;
    }
    if (next === "n") out += "\n";
    else if (next === "t") out += "\t";
    else if (next === "r") out += "\r";
    else if (next === "b") out += "\b";
    else if (next === "f") out += "\f";
    else out += next;
    index += 1;
  }
  return out;
}

function jsonStringField(source: string, key: string): string | null {
  const marker = `"${key}"`;
  const at = source.indexOf(marker);
  if (at < 0) return null;
  const colon = source.indexOf(":", at + marker.length);
  if (colon < 0) return null;
  let index = colon + 1;
  while (index < source.length && /\s/.test(source[index])) index += 1;
  if (source[index] !== '"') return null;
  return decodeJsonString(source.slice(index + 1));
}

function toolFilePath(args: unknown): string {
  if (args && typeof args === "object" && !Array.isArray(args)) {
    const fields = args as Record<string, unknown>;
    for (const key of TOOL_PATH_KEYS) {
      if (typeof fields[key] === "string" && fields[key]) return fields[key];
    }
    return "";
  }
  if (typeof args !== "string") return "";
  for (const key of TOOL_PATH_KEYS) {
    const value = jsonStringField(args, key);
    if (value) return value;
  }
  return "";
}

function readableToolText(args: unknown): string {
  if (typeof args === "string") {
    for (const key of TOOL_BODY_KEYS) {
      const value = jsonStringField(args, key);
      if (value != null) return value;
    }
    return args;
  }
  if (args && typeof args === "object" && !Array.isArray(args)) {
    const fields = args as Record<string, unknown>;
    for (const key of TOOL_BODY_KEYS) {
      if (typeof fields[key] === "string" && fields[key]) return fields[key];
    }
  }
  return stringifyValue(args);
}

function writtenFileContent(args: unknown): string | null {
  if (typeof args === "string") return jsonStringField(args, "content");
  if (args && typeof args === "object" && !Array.isArray(args)) {
    const content = (args as Record<string, unknown>).content;
    return typeof content === "string" ? content : null;
  }
  return null;
}

function proposedAmount(count: number): string {
  if (count < 1024) return `${count.toLocaleString()} characters proposed`;
  const kilobytes = count / 1024;
  return `${kilobytes < 10 ? kilobytes.toFixed(1) : Math.round(kilobytes).toLocaleString()} KB proposed`;
}

function toolIsStreaming(tool: ToolBlock): boolean {
  if (toolError(tool)) return false;
  const status = tool.status ?? "";
  if (["finished", "success", "completed", "error", "failed"].includes(status)) return false;
  return tool.result === undefined;
}

function safeHref(href: string | undefined): string | undefined {
  if (!href) {
    return undefined;
  }
  try {
    const parsed = new URL(href);
    if (parsed.protocol === "http:" || parsed.protocol === "https:") {
      return href;
    }
  } catch {
    return undefined;
  }
  return undefined;
}

function textFromNode(node: React.ReactNode): string {
  if (typeof node === "string" || typeof node === "number") {
    return String(node);
  }
  if (Array.isArray(node)) {
    return node.map(textFromNode).join("");
  }
  if (node && typeof node === "object" && "props" in node) {
    return textFromNode((node as { props?: { children?: React.ReactNode } }).props?.children);
  }
  return "";
}

export function CodeBlock({ children, text, label = "Copy code block", preClassName = "code-block", ariaLabel }: {
  children?: React.ReactNode;
  text?: string;
  label?: string;
  preClassName?: string;
  ariaLabel?: string;
}) {
  const code = text ?? textFromNode(children);
  return (
    <div className="code-block-wrap">
      <CopyIconButton text={code} label={label} />
      <pre className={preClassName} aria-label={ariaLabel}>{children ?? text}</pre>
    </div>
  );
}

const MarkdownMessage = memo(function MarkdownMessage({ text }: { text: string }) {
  markdownParseCount += 1;
  if (!text.trim()) {
    return null;
  }
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      urlTransform={url => sourceReference(url) ? url : defaultUrlTransform(url)}
      components={{
        a({ children, href }) {
          if (href && sourceReference(href)) return <SourceLink href={href}>{children}</SourceLink>;
          const allowedHref = safeHref(href);
          if (!allowedHref) {
            return <span>{children}</span>;
          }
          const external = /^https?:/i.test(allowedHref);
          return (
            <a href={allowedHref} rel={external ? "noreferrer" : undefined} target={external ? "_blank" : undefined}>
              {children}
            </a>
          );
        },
        code({ children, className, node: _node, ...rest }) {
          const match = /language-([\w-]+)/.exec(className ?? "");
          return (
            <code className={match ? `language-${match[1]}` : className} {...rest}>
              {children}
            </code>
          );
        },
        pre({ children }) {
          return <CodeBlock>{children}</CodeBlock>;
        },
        table({ children }) {
          return <table className="markdown-table">{children}</table>;
        },
      }}
    >
      {text}
    </ReactMarkdown>
  );
});

function StreamingMarkdown({ text }: { text: string }) {
  const parts = useMemo(() => splitStreamingMarkdown(text), [text]);
  const tail = parts.tail ? closeUnfinishedMarks(parts.tail) : "";
  return (
    <>
      {parts.blocks.map((block, index) => (
        <MarkdownMessage key={`${index}:${block.length}:${block.slice(0, 24)}`} text={block} />
      ))}
      {tail ? <MarkdownMessage text={tail} /> : null}
    </>
  );
}

function useStickToBottom(signature: string, hasContent: boolean, open: boolean) {
  const ref = useRef<HTMLDivElement>(null);
  const stick = useRef(true);
  useLayoutEffect(() => {
    const element = ref.current;
    if (!element) {
      return undefined;
    }
    const onScroll = () => {
      stick.current = element.scrollHeight - element.scrollTop - element.clientHeight < 96;
    };
    element.addEventListener("scroll", onScroll, { passive: true });
    return () => element.removeEventListener("scroll", onScroll);
  }, [hasContent]);
  useLayoutEffect(() => {
    const element = ref.current;
    if (!element || !stick.current || selectionInside(element)) {
      return;
    }
    element.scrollTop = element.scrollHeight;
  }, [signature, open]);
  return ref;
}

function selectionInside(element: HTMLElement): boolean {
  const selection = typeof document === "undefined" ? null : document.getSelection?.();
  return Boolean(selection && !selection.isCollapsed && element.contains(selection.anchorNode));
}

function ToolInputText({ text }: { text: string }) {
  const ref = useStickToBottom(text, true, true);
  return (
    <div ref={ref} className="tool-input-text">
      <pre className="code-block live-tool-code"><code>{text}</code></pre>
    </div>
  );
}

function DetailSection({ children, className, defaultOpen, id, onToggle, openStates, summary }: DetailSectionProps) {
  const open = openStates.get(id) ?? defaultOpen;
  return (
    <details
      className={className}
      open={open}
    >
      <summary
        aria-expanded={open}
        onClick={(event) => {
          event.preventDefault();
          onToggle(id, !open);
        }}
      >
        {summary}
        <span className="activity-toggle" aria-hidden="true">{open ? "−" : "+"}</span>
      </summary>
      {children}
    </details>
  );
}

function ReasoningDetails({
  defaultOpen,
  messageKey,
  onToggle,
  openStates,
  reasoning,
}: {
  defaultOpen: boolean;
  messageKey: string;
  onToggle: (id: string, open: boolean) => void;
  openStates: ReadonlyMap<string, boolean>;
  reasoning: string[];
}) {
  const open = openStates.get(`${messageKey}:reasoning`) ?? defaultOpen;
  const followRef = useStickToBottom(reasoning.join("\n"), reasoning.length > 0, open);
  if (reasoning.length === 0) {
    return null;
  }
  return (
    <DetailSection
      className="message-reasoning"
      defaultOpen={defaultOpen}
      id={`${messageKey}:reasoning`}
      onToggle={onToggle}
      openStates={openStates}
      summary={<><Icon name="activity" size={14} /><span className="activity-name">Reasoning</span></>}
    >
      <div className="reasoning-content" ref={followRef}>{reasoning.map((item, index) => (
        <StreamingMarkdown key={index} text={item} />
      ))}</div>
    </DetailSection>
  );
}

function AttachmentList({ attachments }: { attachments: MessageParts["attachments"] }) {
  if (attachments.length === 0) {
    return null;
  }
  return (
    <ul className="message-attachments" aria-label={`${attachments.length} image attachment${attachments.length === 1 ? "" : "s"}`}>
      {attachments.map((item, index) => (
        <li key={index}>{item.src ? <ImagePreview src={item.src} name={item.label} /> : item.label}</li>
      ))}
    </ul>
  );
}

const FILE_ACTIVITY = new Set(["read_file", "write_file", "edit_file", "ls", "glob", "grep"]);

function todoLabel(status: TodoItem["status"]): string {
  if (status === "in_progress") return "In progress";
  if (status === "completed") return "Completed";
  return "Pending";
}

function TodoChecklist({ defaultOpen, failure, id, items, onToggle, openStates, raw }: {
  defaultOpen: boolean;
  failure: string;
  id: string;
  items: TodoItem[];
  onToggle: (id: string, open: boolean) => void;
  openStates: ReadonlyMap<string, boolean>;
  raw: unknown;
}) {
  return <div className="todo-checklist">
    {items.length ? <ol aria-label="Todo list">{items.map((item, index) => <li key={`${item.status}-${index}`} data-status={item.status}><span className="todo-status" aria-label={todoLabel(item.status)} title={todoLabel(item.status)}>{item.status === "completed" ? "✓" : item.status === "in_progress" ? "◉" : "○"}</span> {item.content}</li>)}</ol> : failure ? null : <p className="activity-line">Updating the list</p>}
    {failure ? <p className="tool-call-error" role="status">{failure}</p> : null}
    <DetailSection className="todo-arguments" defaultOpen={defaultOpen} id={id} onToggle={onToggle} openStates={openStates} summary={<span>List arguments</span>}>
      <CodeBlock text={stringifyValue(raw)} label="Copy tool input"><code>{stringifyValue(raw)}</code></CodeBlock>
    </DetailSection>
  </div>;
}

function todoState(toolBlocks: ToolBlock[]): { items: TodoItem[]; failure: string; raw: unknown } | null {
  let items: TodoItem[] | null = null;
  let failure = "";
  let raw: unknown;
  let saw = false;
  for (const tool of toolBlocks) {
    if (tool.name !== "write_todos") continue;
    saw = true;
    const parsed = parseTodoList(tool.args);
    const error = toolError(tool);
    if (error) {
      failure = error.split("\n")[0].slice(0, 240);
      continue;
    }
    if (parsed) {
      items = parsed;
      failure = "";
      raw = tool.args;
    } else {
      raw = tool.args ?? raw;
    }
  }
  if (!saw) return null;
  return { items: items ?? [], failure, raw };
}

function ToolBlockList({
  defaultOpen,
  live,
  waiting,
  messageKey,
  onToggle,
  openStates,
  toolBlocks,
  onHelperOpen,
  helperName,
  helperStatus,
  helperRunId,
}: {
  defaultOpen: boolean;
  live?: boolean;
  waiting?: boolean;
  messageKey: string;
  onToggle: (id: string, open: boolean) => void;
  openStates: ReadonlyMap<string, boolean>;
  toolBlocks: ToolBlock[];
  onHelperOpen?: (runId: string, toolCallId: string) => void;
  helperName?: (tool: ToolBlock, runId?: string) => string;
  helperStatus?: (tool: ToolBlock, runId?: string) => string;
  helperRunId?: string;
}) {
  const dock = useChatDock();
  if (toolBlocks.length === 0) {
    return null;
  }
  const todos = todoState(toolBlocks);
  const rows = toolBlocks.filter(tool => tool.name !== "write_todos");
  const groups = groupActivity(rows, tool => { const error = toolError(tool); const finished = !toolIsStreaming(tool); return { label: activityLine({ name: tool.name, args: tool.args, finished, failed: Boolean(error) }), finished, failed: Boolean(error) }; });
  function renderTool(tool: ToolBlock, index: number) {
    const id = tool.id ? `${helperRunId ?? "default"}:tool:${tool.id}` : `${messageKey}:tool:${index}`;
    const error = toolError(tool);
    const incomplete = toolIsStreaming(tool);
    const stopped = incomplete && (live === false || tool.status === "unfinished");
    const streaming = incomplete && !stopped;
    const writing = incomplete ? readableToolText(tool.args) : "";
    const fileContent = tool.name === "write_file" ? writtenFileContent(tool.args) : null;
    const readableInput = incomplete ? writing : fileContent;
    const finished = !incomplete && !error;
    const path = toolFilePath(tool.args);
    const label = waiting && incomplete
      ? path ? `Proposed change to ${path}` : `Waiting: ${tool.name}`
      : stopped
      ? path ? `Unfinished input for ${path}` : `Unfinished ${tool.name} input`
      : activityLine({ name: tool.name, args: tool.args, finished, failed: Boolean(error) });
    const openable = FILE_ACTIVITY.has(tool.name) && Boolean(path) && !stopped;
    const open = openStates.get(id) ?? defaultOpen;
    const output = parseContent(tool.result && typeof tool.result === "object" && !Array.isArray(tool.result) && "content" in tool.result ? (tool.result as { content: unknown }).content : tool.result);
    const grant = tool.authorizationSource === "saved_permission" ? tool.authorizationGrant : undefined;
    if (tool.name === "task" && onHelperOpen) {
      const args = typeof tool.args === "string" ? (() => { try { return JSON.parse(tool.args) as Record<string, unknown>; } catch { return {}; } })() : tool.args && typeof tool.args === "object" ? tool.args as Record<string, unknown> : {};
      const request = typeof args.description === "string" ? args.description : "Preparing request…";
      return <button type="button" className="helper-delegation" key={id} onClick={() => tool.id && helperRunId && onHelperOpen(helperRunId, tool.id)} disabled={!tool.id || !helperRunId} aria-label={`Open helper ${helperName?.(tool, helperRunId) ?? String(args.subagent_type ?? "helper")}`}>
        <span className="helper-delegation-head"><Icon name="sparkles" size={14} /><strong>{helperName?.(tool, helperRunId) ?? String(args.subagent_type ?? "Helper")}</strong><span>{helperStatus?.(tool, helperRunId) ?? (incomplete ? "Working" : error ? "Failed" : "Done")}</span></span>
        <span className="helper-delegation-request">{request}</span>
      </button>;
    }
    return <div className={`tool-call-row${error ? " tool-call-failed" : ""}`} key={id}>
      <DetailSection
        className="message-tools"
        defaultOpen={defaultOpen}
        id={id}
        onToggle={onToggle}
        openStates={openStates}
        summary={<>
          <Icon name={tool.name === "execute" ? "terminal" : FILE_ACTIVITY.has(tool.name) ? "files" : "activity"} size={14} />
          {openable ? <button type="button" className="activity-line" onClick={(event) => {
            event.preventDefault();
            event.stopPropagation();
            if (path) dock?.openFile(path);
          }}>{label}{error ? " failed" : ""}</button> : <span className="activity-line">{label}{error ? " failed" : ""}</span>}
          {streaming && writing ? <span className="tool-call-progress">{proposedAmount(writing.length)}</span> : null}
          {tool.authorizationSource === "saved_permission" ? <span className="tool-call-permission">Allowed by saved permission{grant ? `: ${grant.display_name}` : ""}</span> : null}
        </>}
      >
        {incomplete && !open ? null : <div className="tool-call-details">
          {path ? <p className="hint tool-identity">{path}</p> : tool.name === "execute" ? <p className="hint tool-identity">{readableToolText(tool.args)}</p> : null}
          {readableInput !== null ? <section aria-label="Tool input">
            <span className="tool-detail-label">{incomplete ? stopped ? "Partial input" : "Proposed content" : "File content"}</span>
            <div className="code-block-wrap"><CopyIconButton text={readableInput} label="Copy tool input" /><ToolInputText text={readableInput} /></div>
          </section> : null}
          {!incomplete && tool.result !== undefined ? <section aria-label="Tool output"><span className="tool-detail-label">Output</span>{output.answer ? <CodeBlock><code>{output.answer}</code></CodeBlock> : <span className="hint">{output.attachments.length ? "Image output below" : "No text output"}</span>}</section> : null}
          {tool.error ? <section aria-label="Tool error"><span className="tool-detail-label">Error</span><pre className="code-block"><code>{tool.error}</code></pre></section> : null}
          {!incomplete || grant ? <details className="tool-raw-arguments"><summary>Tool details</summary><p className="hint">Tool <span className="tool-call-name">{tool.name}</span></p>{grant ? <SavedPermissionDetails grant={grant} /> : null}{tool.args !== undefined ? <section aria-label="Raw tool arguments"><span className="tool-detail-label">Raw arguments</span><CodeBlock text={stringifyValue(tool.args)} label="Copy raw tool arguments"><code>{stringifyValue(tool.args)}</code></CodeBlock></section> : null}</details> : null}
        </div>}
      </DetailSection>
      <AttachmentList attachments={output.attachments} />
      {!error && !incomplete && ["browser_take_screenshot", "desktop_screenshot"].includes(tool.name) && captureAssetId(output.answer) ? <CapturePreview assetId={captureAssetId(output.answer)!} /> : null}
      {tool.name === "read_attachment" && !error ? <ReadSources text={output.answer} /> : null}
      {error ? <p className="tool-call-error" role="status">{error.split("\n")[0].slice(0, 240)}</p> : null}
    </div>;
  }
  return <div className="tool-call-list">
    {todos ? <TodoChecklist defaultOpen={false} failure={todos.failure} id={`${messageKey}:todos`} items={todos.items} onToggle={onToggle} openStates={openStates} raw={todos.raw} /> : null}
    {groups.map((group, index) => group.label ? <DetailSection key={group.items[0]?.id ?? index} className="activity-group" defaultOpen={defaultOpen} id={`${messageKey}:group:${group.items[0]?.id ?? index}`} onToggle={onToggle} openStates={openStates} summary={<><Icon name="files" size={14} /><span>{group.label}</span></>}>{group.items.map(tool => renderTool(tool, rows.indexOf(tool)))}</DetailSection> : group.items.map(tool => renderTool(tool, rows.indexOf(tool))))}
  </div>;
}

function useFollowTranscript(messages: BaseMessage[], incompleteMessageIds: ReadonlySet<string>, toolCalls: AssembledToolCall[]) {
  const rootRef = useRef<HTMLDivElement | null>(null);
  const shouldFollow = useRef(true);
  const [showJump, setShowJump] = useState(false);
  const lastPosition = useRef({ top: 0, height: 0 });
  const hasContent = messages.length > 0 || toolCalls.length > 0;
  const lastHumanId = [...messages].reverse().find(message => messageType(message) === "human")?.id;
  const previousHumanId = useRef(lastHumanId);
  const signature = useMemo(
    () =>
      messages
        .map((message) => {
          const content = typeof message.content === "string" ? message.content : JSON.stringify(message.content);
          return `${message.id ?? ""}:${content.length}:${incompleteMessageIds.has(message.id ?? "") ? "partial" : "done"}`;
        })
        .join("|") + toolCalls.map(call => `${call.callId}:${call.status}:${stringifyValue(call.input ?? call.args).length}:${stringifyValue(call.output).length}:${call.error ?? ""}`).join("|"),
    [incompleteMessageIds, messages, toolCalls],
  );

  const transcriptElement = useCallback(() => {
    const transcript = rootRef.current?.closest(".transcript");
    const elementCtor = typeof HTMLElement === "undefined" ? null : HTMLElement;
    return elementCtor && transcript instanceof elementCtor ? transcript : null;
  }, []);

  const follow = useCallback((explicit = false) => {
    const transcript = transcriptElement();
    if (!transcript || !shouldFollow.current || (!explicit && selectionInside(transcript))) return;
    if (typeof transcript.scrollTo === "function") {
      transcript.scrollTo({ top: transcript.scrollHeight, behavior: "auto" });
    } else {
      transcript.scrollTop = transcript.scrollHeight;
    }
    lastPosition.current = { top: transcript.scrollTop, height: transcript.scrollHeight };
  }, [transcriptElement]);

  const jumpToLatest = useCallback(() => {
    shouldFollow.current = true;
    setShowJump(false);
    follow(true);
  }, [follow]);

  useLayoutEffect(() => {
    const transcript = transcriptElement();
    if (!transcript) return;
    const nearBottom = () => transcript.scrollHeight - transcript.scrollTop - transcript.clientHeight < 96;
    const onScroll = () => {
      if (nearBottom()) {
        shouldFollow.current = true;
      } else if (transcript.scrollTop < lastPosition.current.top && transcript.scrollHeight >= lastPosition.current.height) {
        // Content growth or browser scroll anchoring does not express intent
        // to stop following. An upward move through unchanged content does.
        shouldFollow.current = false;
      }
      lastPosition.current = { top: transcript.scrollTop, height: transcript.scrollHeight };
      setShowJump(!shouldFollow.current);
    };
    transcript.addEventListener("scroll", onScroll, { passive: true });
    // Images, disclosures, wrapping and content-visibility can change layout
    // without delivering another token. Observe those changes in the same
    // scroll owner rather than adding a second competing smooth scroll.
    const observer = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(() => follow());
    const observed = new Set<Element>();
    const observeContent = () => {
      // Approval cards and run summaries are siblings of the message feed.
      // The feed uses display:contents, so its own box never reports growth.
      // Observe its real message boxes, including late saved-answer actions.
      const targets = new Set<Element>([transcript, ...Array.from(transcript.children ?? []), ...Array.from(rootRef.current?.children ?? [])]);
      for (const element of observed) if (!targets.has(element)) { observer?.unobserve?.(element); observed.delete(element); }
      for (const element of targets) if (!observed.has(element)) { observer?.observe(element); observed.add(element); }
      follow();
    };
    const contentObserver = typeof MutationObserver === "undefined" ? null : new MutationObserver(observeContent);
    contentObserver?.observe(transcript, { childList: true, subtree: true });
    observeContent();
    return () => {
      transcript.removeEventListener("scroll", onScroll);
      observer?.disconnect();
      contentObserver?.disconnect();
    };
  }, [follow, hasContent, transcriptElement]);

  useLayoutEffect(() => {
    if (lastHumanId && lastHumanId !== previousHumanId.current) {
      shouldFollow.current = true;
      setShowJump(false);
    }
    previousHumanId.current = lastHumanId;
    follow();
  }, [follow, lastHumanId, signature]);

  return { rootRef, showJump, jumpToLatest };
}

const EMPTY_INCOMPLETE: ReadonlySet<string> = new Set();

function useFrameSample<T>(value: T, enabled: boolean): T {
  const [shown, setShown] = useState(value);
  const latest = useRef(value);
  latest.current = value;
  const pendingFrame = useRef<number | null>(null);
  const pendingTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const frame = typeof window !== "undefined" && typeof window.requestAnimationFrame === "function";
  const cancel = useCallback(() => {
    if (pendingFrame.current !== null) window.cancelAnimationFrame(pendingFrame.current);
    if (pendingTimer.current !== null) clearTimeout(pendingTimer.current);
    pendingFrame.current = null;
    pendingTimer.current = null;
  }, []);
  useEffect(() => {
    if (!enabled || !frame) {
      cancel();
      setShown(latest.current);
      return;
    }
    if (pendingFrame.current !== null) return;
    const publish = () => {
      cancel();
      setShown(latest.current);
    };
    pendingFrame.current = window.requestAnimationFrame(publish);
    // Hidden windows pause animation frames. Keep the retained view current
    // there too, without resetting the deadline on each incoming token.
    pendingTimer.current = setTimeout(publish, 100);
  }, [cancel, enabled, frame, value]);
  useEffect(() => cancel, [cancel]);
  if (!enabled || !frame) {
    return value;
  }
  return shown;
}

const MessageBubble = memo(function MessageBubble(props: {
  answer: string;
  attachments: MessageParts["attachments"];
  continuation: boolean;
  detailedStreams: boolean;
  incomplete: boolean;
  message: BaseMessage;
  messageKey: string;
  messageTools: ToolBlock[];
  onToggle: (id: string, open: boolean) => void;
  openStates: ReadonlyMap<string, boolean>;
  reasoning: string[];
  renderAnswerActions?: (message: BaseMessage, incomplete: boolean, answerText: string) => React.ReactNode;
  renderMessageFooter?: (message: BaseMessage) => React.ReactNode;
  toolsKey: string;
  toolsLive?: boolean;
  type: string;
  writing: boolean;
  waiting: boolean;
  onHelperOpen?: (runId: string, toolCallId: string) => void;
  helperName?: (tool: ToolBlock, runId?: string) => string;
  helperStatus?: (tool: ToolBlock, runId?: string) => string;
  helperRunId?: string;
}) {
  if (!props.incomplete) {
    finishedBubbleRenders += 1;
  }
  const settled = !props.incomplete;
  return (
    <article className={`bubble bubble-${props.type === "human" ? "user" : props.type === "ai" ? "assistant" : "system"}${settled ? " bubble-settled" : ""}${props.continuation ? " bubble-continuation" : ""}`}>
      <header>
        <strong>{roleLabel(props.type)}</strong>
        {props.incomplete ? <span className="message-state" aria-label={props.waiting ? "Waiting for your response" : props.writing ? "Response in progress" : "Incomplete response"}>{props.waiting ? "Waiting" : props.writing ? "Writing" : "Partial"}</span> : null}
      </header>
      <div className="message-body">
        <ReasoningDetails
          defaultOpen={props.detailedStreams}
          messageKey={props.messageKey}
          onToggle={props.onToggle}
          openStates={props.openStates}
          reasoning={props.reasoning}
        />
        {props.incomplete ? <StreamingMarkdown text={props.answer} /> : <MarkdownMessage text={props.answer} />}
        <AttachmentList attachments={props.attachments} />
        <ToolBlockList defaultOpen={props.detailedStreams} live={props.toolsLive} waiting={props.waiting} messageKey={props.messageKey} onToggle={props.onToggle} openStates={props.openStates} toolBlocks={props.messageTools} onHelperOpen={props.onHelperOpen} helperName={props.helperName} helperStatus={props.helperStatus} helperRunId={props.helperRunId} />
      </div>
      {props.type === "ai" ? props.renderAnswerActions?.(props.message, props.incomplete, props.answer) : null}
      {props.renderMessageFooter?.(props.message)}
    </article>
  );
}, (previous, next) => {
  if (previous.incomplete || next.incomplete) {
    return false;
  }
  return previous.message === next.message
    && previous.continuation === next.continuation
    && previous.toolsKey === next.toolsKey
    && previous.toolsLive === next.toolsLive
    && previous.waiting === next.waiting
    && previous.detailedStreams === next.detailedStreams
    && previous.openStates === next.openStates
    && previous.onToggle === next.onToggle
    && previous.renderAnswerActions === next.renderAnswerActions
    && previous.renderMessageFooter === next.renderMessageFooter
    && previous.onHelperOpen === next.onHelperOpen
    && previous.helperName === next.helperName
    && previous.helperStatus === next.helperStatus
    && previous.helperRunId === next.helperRunId
    && previous.answer === next.answer;
});

export function AgentMessageFeed(props: {
  messages: BaseMessage[];
  toolAuthorizations?: Record<string, string>;
  toolAuthorizationGrants?: Record<string, MatchedPermissionGrant>;
  toolCalls?: AssembledToolCall[];
  incompleteMessageIds?: ReadonlySet<string>;
  live?: boolean;
  waiting?: boolean;
  fallback?: React.ReactNode;
  detailedStreams?: boolean;
  renderMessageFooter?: (message: BaseMessage) => React.ReactNode;
  renderAnswerActions?: (message: BaseMessage, incomplete: boolean, answerText: string) => React.ReactNode;
  userMessageText?: (message: BaseMessage) => string | undefined;
  sourceScope?: { sessionId?: string; projectPath?: string };
  hiddenToolCallIds?: ReadonlySet<string>;
  hiddenHelperResultIds?: ReadonlySet<string>;
  helperRuns?: AgentRun[];
  currentRunId?: string;
  onHelperOpen?: (runId: string, toolCallId: string) => void;
  helperName?: (tool: ToolBlock, runId?: string) => string;
  helperStatus?: (tool: ToolBlock, runId?: string) => string;
}) {
  const { toolCalls = [], fallback, detailedStreams = false } = props;
  const incompleteMessageIds = props.incompleteMessageIds ?? EMPTY_INCOMPLETE;
  const endedToolIds = useRef(new Set<string>());
  if (props.live === false) {
    for (const call of toolCalls) {
      if (toolIsStreaming(mergeTool({ name: call.name }, undefined, call))) {
        endedToolIds.current.add(call.callId || call.id);
      }
    }
  }
  const retainStoppedTool = (tool: ToolBlock): ToolBlock => ({ ...tool,
    status: tool.id && endedToolIds.current.has(tool.id) && toolIsStreaming(tool) ? "unfinished" : tool.status,
    authorizationSource: tool.authorizationSource ?? (tool.id ? props.toolAuthorizations?.[tool.id] : undefined),
    authorizationGrant: tool.authorizationGrant ?? (tool.id ? matchedPermissionGrant(props.toolAuthorizationGrants?.[tool.id]) : undefined),
  });
  const streaming = props.live !== false && (Boolean(props.live) || incompleteMessageIds.size > 0 || toolCalls.some((call) => {
    const status = call.status as string;
    return status === "preparing" || status === "running";
  }));
  const messages = useFrameSample(props.messages, streaming);
  const { rootRef, showJump, jumpToLatest } = useFollowTranscript(messages, incompleteMessageIds, toolCalls);
  const [openStates, setOpenStates] = useState<Map<string, boolean>>(() => new Map());
  const handleDetailToggle = useCallback((id: string, open: boolean) => {
    setOpenStates((current) => {
      if (current.get(id) === open) {
        return current;
      }
      const next = new Map(current);
      next.set(id, open);
      return next;
    });
  }, []);
  if (messages.length === 0 && toolCalls.length === 0) {
    return fallback;
  }
  let lastAiId: string | undefined;
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    const type = messageType(messages[index]);
    if (type === "human") break;
    if (type === "ai") { lastAiId = messages[index].id; break; }
  }
  let previousType = "";
  const latestHumanIndex = messages.map(messageType).lastIndexOf("human");
  const hiddenIds = new Set(props.hiddenToolCallIds ?? []);
  const helperIds = new Set(props.hiddenHelperResultIds ?? []);
  const runByInputId = new Map((props.helperRuns ?? []).flatMap(run => run.input_message_id ? [[run.input_message_id, run.id] as const] : []));
  let turnIndex = -1;
  let turnRunId = latestHumanIndex < 0 ? props.currentRunId : undefined;
  const prepared = messages.map((message, index) => {
    const type = messageType(message);
    if (type === "human") {
      turnIndex += 1;
      turnRunId = (message.id ? runByInputId.get(message.id) : undefined) ?? (index === latestHumanIndex ? props.currentRunId : undefined);
    }
    const runId = turnRunId;
    const scopeKey = runId ? `run:${runId}` : `turn:${turnIndex}`;
    const continuation = type === "ai" && previousType === "ai";
    if (type !== "tool") previousType = type;
    const submittedText = type === "human" ? props.userMessageText?.(message) : undefined;
    const parts = parseContent(submittedText ?? message.contentBlocks ?? message.content);
    parts.toolBlocks = parts.toolBlocks.filter(block => !block.id || !hiddenIds.has(block.id));
    return { message, type, runId, scopeKey, continuation, live: props.live === undefined ? undefined : props.live && index > latestHumanIndex, key: `${scopeKey}:${message.id ?? `${type}-${index}`}`, parts };
  });
  const resultById = new Map<string, ToolBlock>();
  const callIds = new Set<string>();
  const taskIds = new Set<string>();
  for (const item of prepared) {
    const result = toolResultMessage(item.message);
    if (result?.id && !hiddenIds.has(result.id)) resultById.set(`${item.scopeKey}:${result.id}`, result);
    if (item.type !== "tool") for (const call of item.parts.toolBlocks) if (call.id) {
      callIds.add(`${item.scopeKey}:${call.id}`);
      if (call.name === "task" && props.onHelperOpen) taskIds.add(`${item.scopeKey}:${call.id}`);
    }
  }
  const liveById = new Map(toolCalls.map(call => [call.callId || call.id, call]));
  const liveScope = props.currentRunId ? `run:${props.currentRunId}` : prepared.at(-1)?.scopeKey ?? "turn:-1";
  const remainingLive = toolCalls.filter(call => {
    const id = call.callId || call.id;
    const scoped = `${liveScope}:${id}`;
    return !hiddenIds.has(id) && !callIds.has(scoped) && !resultById.has(scoped);
  });
  return (
    <SourceScope.Provider value={props.sourceScope ?? {}}><div className="message-feed" ref={rootRef}>
      {prepared.map(({ message, type, runId, scopeKey, continuation, live, key: messageKey, parts }) => {
        const incomplete = Boolean((message.id && incompleteMessageIds.has(message.id)) || (props.live && message.id && message.id === lastAiId));
        const result = toolResultMessage(message);
        if (result) {
          if (result.id && (hiddenIds.has(result.id) || taskIds.has(`${scopeKey}:${result.id}`) || (runId && helperIds.has(helperKey(runId, result.id))))) return null;
          // A completed ToolMessage and the SDK's live handle describe the same
          // call. Keep its result beside the original call in transcript order.
          if (result.id && callIds.has(`${scopeKey}:${result.id}`)) return null;
          return <div className="tool-message" key={messageKey}><ToolBlockList defaultOpen={detailedStreams} live={live} waiting={props.waiting} messageKey={messageKey} onToggle={handleDetailToggle} openStates={openStates} toolBlocks={[retainStoppedTool(mergeTool(result, result, result.id && (!props.currentRunId || runId === props.currentRunId) ? liveById.get(result.id) : undefined))]} /></div>;
        }
        const messageTools = parts.toolBlocks.map(block => retainStoppedTool(mergeTool(block, block.id ? resultById.get(`${scopeKey}:${block.id}`) : undefined, block.id && (!props.currentRunId || runId === props.currentRunId) ? liveById.get(block.id) : undefined)));
        if (type === "ai" && !parts.answer && !parts.reasoning.length && !parts.attachments.length && !messageTools.length && !incomplete) return null;
        const toolsKey = JSON.stringify(messageTools);
        return (
          <MessageBubble
            key={messageKey}
            answer={parts.answer}
            attachments={parts.attachments}
            continuation={continuation}
            detailedStreams={detailedStreams}
            incomplete={incomplete}
            message={message}
            messageKey={messageKey}
            messageTools={messageTools}
            onHelperOpen={props.onHelperOpen}
            helperName={props.helperName}
            helperStatus={props.helperStatus}
            helperRunId={runId}
            onToggle={handleDetailToggle}
            openStates={openStates}
            reasoning={parts.reasoning}
            renderAnswerActions={props.renderAnswerActions}
            renderMessageFooter={props.renderMessageFooter}
            toolsKey={toolsKey}
            toolsLive={live}
            type={type}
            writing={Boolean(props.live && message.id === lastAiId)}
            waiting={Boolean(props.waiting && message.id === lastAiId)}
          />
        );
      })}
       <ToolBlockList defaultOpen={detailedStreams} live={props.live} waiting={props.waiting} messageKey="live-tools" onToggle={handleDetailToggle} openStates={openStates} toolBlocks={remainingLive.map(call => retainStoppedTool(mergeTool({ id: call.callId || call.id, name: call.name }, undefined, call)))} onHelperOpen={props.onHelperOpen} helperName={props.helperName} helperStatus={props.helperStatus} helperRunId={props.currentRunId} />
      {showJump ? <button type="button" className="chat-jump-latest" aria-label="Jump to latest message" onClick={jumpToLatest}>↓ Latest</button> : null}
    </div></SourceScope.Provider>
  );
}
