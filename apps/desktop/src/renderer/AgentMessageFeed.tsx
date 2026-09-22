import type { BaseMessage } from "@langchain/core/messages";
import type { AssembledToolCall } from "@langchain/react";
import type React from "react";
import { useLayoutEffect, useMemo, useRef, useState } from "react";
import ReactMarkdown, { defaultUrlTransform } from "react-markdown";
import remarkGfm from "remark-gfm";
import { CopyIconButton } from "./CopyIconButton";
import { Icon } from "./Icon";
import { ImagePreview, safeImageDataUrl } from "./ImagePreview";
import { ReadSources, SourceLink, SourceScope, sourceReference } from "./SourceReference";

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
  return { id: fields.tool_call_id, name: message.name ?? "Tool", status: fields.status, result: message.contentBlocks ?? message.content };
}

function mergeTool(block: ToolBlock, retained: ToolBlock | undefined, live: AssembledToolCall | undefined): ToolBlock {
  return {
    ...block,
    name: live?.name || (block.name !== "Tool" ? block.name : retained?.name) || "Tool",
    args: live?.input ?? live?.args ?? block.args,
    status: retained ? retained.status ?? (toolError(retained) ? "error" : "success") : live?.status ?? block.status,
    result: retained ? retained.result : live?.status === "finished" ? live.output : block.result,
    error: retained?.status === "success" ? undefined : live?.error ?? block.error,
  };
}

const LIVE_TOOL_TAIL = 4000;
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
    if (next === "n") out += "\n";
    else if (next === "t") out += "\t";
    else if (next === "r") out += "\r";
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

function writtenAmount(count: number): string {
  if (count < 1024) return `${count.toLocaleString()} characters written`;
  const kilobytes = count / 1024;
  return `${kilobytes < 10 ? kilobytes.toFixed(1) : Math.round(kilobytes).toLocaleString()} KB written`;
}

function toolIsStreaming(tool: ToolBlock): boolean {
  if (toolError(tool)) return false;
  const status = tool.status ?? "";
  if (["finished", "success", "completed", "error", "failed"].includes(status)) return false;
  return tool.result === undefined;
}

function toolTarget(args: unknown): string {
  const path = toolFilePath(args);
  if (path) return path.replace(/\s+/g, " ").slice(0, 100);
  if (typeof args === "string") return args.replace(/\s+/g, " ").slice(0, 100);
  if (!args || typeof args !== "object") return "";
  const fields = args as Record<string, unknown>;
  for (const key of ["file_path", "path", "command", "query", "q", "pattern", "url", "prompt", "description", "text"]) {
    if (typeof fields[key] === "string" && fields[key]) return fields[key].replace(/\s+/g, " ").slice(0, 100);
  }
  return "";
}

function toolStatus(tool: ToolBlock): string {
  if (toolError(tool)) return "Failed";
  if (["finished", "success", "completed"].includes(tool.status ?? "") || tool.result !== undefined) return "Done";
  if (tool.status === "running") return "Running";
  if (tool.status === "preparing") return "Preparing";
  return "Requested";
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

export function LiveToolCode({ text, copyText }: { text: string; copyText: string }) {
  const ref = useRef<HTMLPreElement>(null);
  useLayoutEffect(() => {
    const elementCtor = typeof HTMLElement === "undefined" ? null : HTMLElement;
    const pre = ref.current;
    if (!elementCtor || !(pre instanceof elementCtor)) return undefined;
    const pin = () => {
      pre.scrollTop = pre.scrollHeight;
      const box = pre.closest(".tool-call-details");
      if (box instanceof elementCtor) box.scrollTop = box.scrollHeight;
    };
    pin();
    if (typeof window === "undefined" || typeof window.requestAnimationFrame !== "function") return undefined;
    const frame = window.requestAnimationFrame(pin);
    return () => window.cancelAnimationFrame(frame);
  }, [text]);
  return (
    <div className="code-block-wrap">
      <CopyIconButton text={copyText} label="Copy tool input" />
      <pre ref={ref} className="code-block live-tool-code"><code>{text}</code></pre>
    </div>
  );
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

function MarkdownMessage({ text }: { text: string }) {
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
        code({ children, className, ...rest }) {
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
      <div className="reasoning-content">{reasoning.map((item, index) => (
        <MarkdownMessage key={index} text={item} />
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

function ToolBlockList({
  defaultOpen,
  messageKey,
  onToggle,
  openStates,
  toolBlocks,
}: {
  defaultOpen: boolean;
  messageKey: string;
  onToggle: (id: string, open: boolean) => void;
  openStates: ReadonlyMap<string, boolean>;
  toolBlocks: ToolBlock[];
}) {
  if (toolBlocks.length === 0) {
    return null;
  }
  return <div className="tool-call-list">{toolBlocks.map((tool, index) => {
    const id = tool.id ? `tool:${tool.id}` : `${messageKey}:tool:${index}`;
    const error = toolError(tool);
    const streaming = toolIsStreaming(tool);
    const writing = streaming ? readableToolText(tool.args) : "";
    const tail = streaming ? writing.slice(Math.max(0, writing.length - LIVE_TOOL_TAIL)) : "";
    const target = toolTarget(tool.args);
    const open = openStates.get(id) ?? defaultOpen;
    const output = parseContent(tool.result && typeof tool.result === "object" && !Array.isArray(tool.result) && "content" in tool.result ? (tool.result as { content: unknown }).content : tool.result);
    return <div className={`tool-call-row${error ? " tool-call-failed" : ""}`} key={id}>
      <DetailSection
        className="message-tools"
        defaultOpen={defaultOpen}
        id={id}
        onToggle={onToggle}
        openStates={openStates}
        summary={<>
          <Icon name={tool.name === "execute" ? "terminal" : /file|glob|grep|^ls$/.test(tool.name) ? "files" : "activity"} size={14} />
          <span className="tool-call-name" title={`Inspect ${tool.name} input and output`}>{tool.name}</span>
          {target ? <span className="tool-call-target" title={target}>{target}</span> : null}
          {streaming && writing ? <span className="tool-call-progress">{writtenAmount(writing.length)}</span> : null}
          <span className="tool-call-state" data-state={error ? "error" : tool.status ?? "requested"}>{toolStatus(tool)}</span>
        </>}
      >
        {streaming && !open ? null : <div className="tool-call-details">
          {streaming ? <section aria-label="Tool input"><span className="tool-detail-label">Writing</span>{writing.length > LIVE_TOOL_TAIL ? <p className="hint">Showing the latest 4,000 characters.</p> : null}<LiveToolCode text={tail} copyText={writing} /></section> : null}
          {!streaming && tool.args !== undefined ? <section aria-label="Tool input"><span className="tool-detail-label">Input</span><CodeBlock text={stringifyValue(tool.args)} label="Copy tool input"><code>{stringifyValue(tool.args)}</code></CodeBlock></section> : null}
          {!streaming && tool.result !== undefined ? <section aria-label="Tool output"><span className="tool-detail-label">Output</span>{output.answer ? <CodeBlock><code>{output.answer}</code></CodeBlock> : <span className="hint">{output.attachments.length ? "Image output below" : "No text output"}</span>}</section> : null}
          {tool.error ? <section aria-label="Tool error"><span className="tool-detail-label">Error</span><pre className="code-block"><code>{tool.error}</code></pre></section> : null}
        </div>}
      </DetailSection>
      <AttachmentList attachments={output.attachments} />
      {tool.name === "read_attachment" && !error ? <ReadSources text={output.answer} /> : null}
      {error ? <p className="tool-call-error" role="status">{error.split("\n")[0].slice(0, 240)}</p> : null}
    </div>;
  })}</div>;
}

function useFollowTranscript(messages: BaseMessage[], incompleteMessageIds: ReadonlySet<string>, toolCalls: AssembledToolCall[]) {
  const rootRef = useRef<HTMLDivElement | null>(null);
  const shouldFollow = useRef(true);
  const hasContent = messages.length > 0 || toolCalls.length > 0;
  const signature = useMemo(
    () =>
      messages
        .map((message) => {
          const content = typeof message.content === "string" ? message.content : JSON.stringify(message.content);
          return `${message.id ?? ""}:${content.length}:${incompleteMessageIds.has(message.id ?? "") ? "partial" : "done"}`;
        })
        .join("|") + toolCalls.map(call => `${call.callId}:${call.status}:${stringifyValue(call.output).length}:${call.error ?? ""}`).join("|"),
    [incompleteMessageIds, messages, toolCalls],
  );

  useLayoutEffect(() => {
    const transcript = rootRef.current?.closest(".transcript");
    const elementCtor = typeof HTMLElement === "undefined" ? null : HTMLElement;
    if (!elementCtor || !(transcript instanceof elementCtor)) {
      return undefined;
    }
    const nearBottom = () => transcript.scrollHeight - transcript.scrollTop - transcript.clientHeight < 96;
    const onScroll = () => {
      shouldFollow.current = nearBottom();
    };
    transcript.addEventListener("scroll", onScroll, { passive: true });
    shouldFollow.current = nearBottom();
    return () => transcript.removeEventListener("scroll", onScroll);
  }, [hasContent]);

  useLayoutEffect(() => {
    const transcript = rootRef.current?.closest(".transcript");
    const elementCtor = typeof HTMLElement === "undefined" ? null : HTMLElement;
    if (!elementCtor || !(transcript instanceof elementCtor) || !shouldFollow.current) {
      return;
    }
    const selection = typeof document === "undefined" ? null : document.getSelection?.();
    if (selection && !selection.isCollapsed && transcript.contains(selection.anchorNode)) {
      return;
    }
    const reduceMotion = typeof window === "undefined" ? false : window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;
    if (typeof transcript.scrollTo === "function") {
      transcript.scrollTo({ top: transcript.scrollHeight, behavior: reduceMotion ? "auto" : "smooth" });
    } else {
      transcript.scrollTop = transcript.scrollHeight;
    }
  }, [signature]);

  return rootRef;
}

export function AgentMessageFeed(props: {
  messages: BaseMessage[];
  toolCalls?: AssembledToolCall[];
  incompleteMessageIds?: ReadonlySet<string>;
  fallback?: React.ReactNode;
  detailedStreams?: boolean;
  renderMessageFooter?: (message: BaseMessage) => React.ReactNode;
  renderAnswerActions?: (message: BaseMessage, incomplete: boolean, answerText: string) => React.ReactNode;
  userMessageText?: (message: BaseMessage) => string | undefined;
  sourceScope?: { sessionId?: string; projectPath?: string };
}) {
  const { messages, toolCalls = [], incompleteMessageIds = new Set(), fallback, detailedStreams = false } = props;
  const rootRef = useFollowTranscript(messages, incompleteMessageIds, toolCalls);
  const [openStates, setOpenStates] = useState<Map<string, boolean>>(() => new Map());
  const handleDetailToggle = (id: string, open: boolean) => {
    setOpenStates((current) => {
      if (current.get(id) === open) {
        return current;
      }
      const next = new Map(current);
      next.set(id, open);
      return next;
    });
  };
  if (messages.length === 0 && toolCalls.length === 0) {
    return fallback;
  }
  const prepared = messages.map((message, index) => {
    const type = messageType(message);
    const submittedText = type === "human" ? props.userMessageText?.(message) : undefined;
    return { message, type, key: message.id ?? `${type}-${index}`, parts: parseContent(submittedText ?? message.contentBlocks ?? message.content) };
  });
  const resultById = new Map<string, ToolBlock>();
  const callIds = new Set<string>();
  for (const item of prepared) {
    const result = toolResultMessage(item.message);
    if (result?.id) resultById.set(result.id, result);
    if (item.type !== "tool") for (const call of item.parts.toolBlocks) if (call.id) callIds.add(call.id);
  }
  const liveById = new Map(toolCalls.map(call => [call.callId || call.id, call]));
  const remainingLive = toolCalls.filter(call => !callIds.has(call.callId || call.id) && !resultById.has(call.callId || call.id));
  const renderTools = (tools: ToolBlock[], key: string) => <ToolBlockList defaultOpen={detailedStreams} messageKey={key} onToggle={handleDetailToggle} openStates={openStates} toolBlocks={tools} />;
  return (
    <SourceScope.Provider value={props.sourceScope ?? {}}><div className="message-feed" ref={rootRef}>
      {prepared.map(({ message, type, key: messageKey, parts }) => {
        const incomplete = Boolean(message.id && incompleteMessageIds.has(message.id));
        const result = toolResultMessage(message);
        if (result) {
          // A completed ToolMessage and the SDK's live handle describe the same
          // call. Keep its result beside the original call in transcript order.
          if (result.id && callIds.has(result.id)) return null;
          return <div className="tool-message" key={messageKey}>{renderTools([mergeTool(result, result, result.id ? liveById.get(result.id) : undefined)], messageKey)}</div>;
        }
        const messageTools = parts.toolBlocks.map(block => mergeTool(block, block.id ? resultById.get(block.id) : undefined, block.id ? liveById.get(block.id) : undefined));
        if (type === "ai" && !parts.answer && !parts.reasoning.length && !parts.attachments.length && !messageTools.length && !incomplete) return null;
        return (
          <article key={messageKey} className={`bubble bubble-${type === "human" ? "user" : type === "ai" ? "assistant" : "system"}`}>
            <header>
              <strong>{roleLabel(type)}</strong>
              {incomplete ? <span className="message-state" aria-label="Incomplete response">Partial</span> : null}
            </header>
            <div className="message-body">
              <ReasoningDetails
                defaultOpen={detailedStreams}
                messageKey={messageKey}
                onToggle={handleDetailToggle}
                openStates={openStates}
                reasoning={parts.reasoning}
              />
              <MarkdownMessage text={parts.answer} />
              <AttachmentList attachments={parts.attachments} />
              {renderTools(messageTools, messageKey)}
            </div>
            {type === "ai" ? props.renderAnswerActions?.(message, incomplete, parts.answer) : null}
            {props.renderMessageFooter?.(message)}
          </article>
        );
      })}
      {renderTools(remainingLive.map(call => mergeTool({ id: call.callId || call.id, name: call.name }, undefined, call)), "live-tools")}
    </div></SourceScope.Provider>
  );
}
