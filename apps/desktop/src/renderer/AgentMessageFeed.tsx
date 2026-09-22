import type { BaseMessage } from "@langchain/core/messages";
import type { AssembledToolCall } from "@langchain/react";
import type React from "react";
import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

// Markdown presentation follows the safe ReactMarkdown + remark-gfm pattern from
// langchain-ai/agent-chat-ui at revision 41926d89c9798cebe45a26886d6e437acc5201c1.
// We do not enable raw HTML rehype plugins, so embedded HTML is rendered as text.

interface MessageParts {
  answer: string;
  reasoning: string[];
  attachments: string[];
  toolBlocks: ToolBlock[];
}

interface ToolBlock {
  name: string;
  args?: unknown;
  status?: string;
  result?: unknown;
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

function isErrorLike(value: unknown): boolean {
  const text = stringifyValue(value).toLowerCase();
  return /\b(error|failed|exception|traceback)\b/.test(text);
}

function imageMarker(part: Record<string, unknown>, index: number): string {
  const source =
    part.source ||
    part.url ||
    part.image_url ||
    (part.image_url && typeof part.image_url === "object" && "url" in part.image_url ? (part.image_url as { url?: string }).url : undefined);
  const label = typeof source === "string" && source && !source.startsWith("data:") ? source : `image ${index + 1}`;
  return `Image attachment: ${label}`;
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
  const attachments: string[] = [];
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
    if (blockType === "tool_call" || blockType === "tool_result" || blockType === "tool") {
      toolBlocks.push({
        name: String(block.name ?? block.tool_name ?? block.id ?? "tool"),
        args: block.args ?? block.input,
        status: typeof block.status === "string" ? block.status : undefined,
        result: block.result ?? block.output ?? block.content,
      });
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

function CodeBlock({ children }: { children: React.ReactNode }) {
  const code = textFromNode(children);
  // Adapted from Agent Chat UI's useCopyToClipboard/CodeHeader at the revision
  // above; local styling, error handling and timer cleanup stay in this UI.
  const [copyState, setCopyState] = useState<"ready" | "copied" | "failed">("ready");
  const resetTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => () => { if (resetTimer.current) clearTimeout(resetTimer.current); }, []);
  return (
    <div className="code-block-wrap">
      <button
        type="button"
        className="copy-code"
        aria-label={copyState === "copied" ? "Code copied" : "Copy code block"}
        disabled={copyState === "copied"}
        onClick={() => {
          if (!code || !navigator.clipboard) { setCopyState("failed"); return; }
          void navigator.clipboard.writeText(code).then(() => {
            setCopyState("copied");
            if (resetTimer.current) clearTimeout(resetTimer.current);
            resetTimer.current = setTimeout(() => setCopyState("ready"), 3000);
          }).catch(() => setCopyState("failed"));
        }}
      >
        {copyState === "copied" ? "Copied" : copyState === "failed" ? "Retry copy" : "Copy"}
      </button>
      <pre className="code-block">{children}</pre>
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
      components={{
        a({ children, href }) {
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
      summary="Reasoning"
    >
      {reasoning.map((item, index) => (
        <MarkdownMessage key={index} text={item} />
      ))}
    </DetailSection>
  );
}

function AttachmentList({ attachments }: { attachments: string[] }) {
  if (attachments.length === 0) {
    return null;
  }
  return (
    <ul className="message-attachments" aria-label={`${attachments.length} image attachment${attachments.length === 1 ? "" : "s"}`}>
      {attachments.map((item, index) => (
        <li key={`${item}-${index}`}>{item}</li>
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
  return (
    <DetailSection
      className="message-tools"
      defaultOpen={defaultOpen}
      id={`${messageKey}:tools`}
      onToggle={onToggle}
      openStates={openStates}
      summary={`Tool activity (${toolBlocks.length})`}
    >
      <ul className="plain-list">
        {toolBlocks.map((tool, index) => (
          <li key={`${tool.name}-${index}`}>
            <strong>{tool.name}</strong>
            {tool.status ? <span className="message-state">{tool.status}</span> : null}
            {!defaultOpen && isErrorLike(tool.result) ? <p className="notice notice-error">{stringifyValue(tool.result)}</p> : null}
            {tool.args !== undefined ? (
              <pre className="code-block">
                <code>{JSON.stringify(tool.args, null, 2)}</code>
              </pre>
            ) : null}
            {tool.result !== undefined ? <MarkdownMessage text={stringifyValue(tool.result)} /> : null}
          </li>
        ))}
      </ul>
    </DetailSection>
  );
}

function useFollowTranscript(messages: BaseMessage[], incompleteMessageIds: ReadonlySet<string>) {
  const rootRef = useRef<HTMLDivElement | null>(null);
  const shouldFollow = useRef(true);
  const signature = useMemo(
    () =>
      messages
        .map((message) => {
          const content = typeof message.content === "string" ? message.content : JSON.stringify(message.content);
          return `${message.id ?? ""}:${content.length}:${incompleteMessageIds.has(message.id ?? "") ? "partial" : "done"}`;
        })
        .join("|"),
    [incompleteMessageIds, messages],
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
  }, []);

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
  userMessageText?: (message: BaseMessage) => string | undefined;
}) {
  const { messages, toolCalls = [], incompleteMessageIds = new Set(), fallback, detailedStreams = false } = props;
  const rootRef = useFollowTranscript(messages, incompleteMessageIds);
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
  if (messages.length === 0) {
    return fallback;
  }
  return (
    <div className="message-feed" ref={rootRef}>
      {messages.map((message, index) => {
        const type = messageType(message);
        const incomplete = Boolean(message.id && incompleteMessageIds.has(message.id));
        const submittedText = type === "human" ? props.userMessageText?.(message) : undefined;
        const parts = parseContent(submittedText ?? message.contentBlocks ?? message.content);
        const messageKey = message.id ?? `${type}-${index}`;
        const compactToolMessage = type === "tool" && !detailedStreams;
        const toolMessageText = compactToolMessage ? stringifyValue(message.content) : "";
        return (
          <article key={messageKey} className={`bubble bubble-${type === "human" ? "user" : type === "ai" ? "assistant" : "system"}`}>
            <header>
              <strong>{type === "tool" && message.name ? `Tool: ${message.name}` : roleLabel(type)}</strong>
              {incomplete ? <span className="message-state" aria-label="Incomplete response">Partial</span> : null}
            </header>
            <div className="message-body">
              {compactToolMessage ? (
                <>
                  {isErrorLike(toolMessageText) ? <p className="notice notice-error">{toolMessageText}</p> : null}
                  <ToolBlockList
                    defaultOpen={detailedStreams}
                    messageKey={`${messageKey}:tool-message`}
                    onToggle={handleDetailToggle}
                    openStates={openStates}
                    toolBlocks={[{ name: message.name ?? "tool", result: toolMessageText }]}
                  />
                </>
              ) : (
                <MarkdownMessage text={parts.answer} />
              )}
              <AttachmentList attachments={parts.attachments} />
              <ReasoningDetails
                defaultOpen={detailedStreams}
                messageKey={messageKey}
                onToggle={handleDetailToggle}
                openStates={openStates}
                reasoning={parts.reasoning}
              />
              <ToolBlockList
                defaultOpen={detailedStreams}
                messageKey={messageKey}
                onToggle={handleDetailToggle}
                openStates={openStates}
                toolBlocks={parts.toolBlocks}
              />
            </div>
            {props.renderMessageFooter?.(message)}
          </article>
        );
      })}
      {toolCalls.length > 0 ? (
        <DetailSection
          className="card"
          defaultOpen={detailedStreams}
          id="live-tool-calls"
          onToggle={handleDetailToggle}
          openStates={openStates}
          summary={`Tool activity (${toolCalls.length})`}
        >
          <ul className="plain-list">
            {toolCalls.map((call, index) => (
              <li key={`${call.id ?? call.name}-${index}`}>
                <strong>{call.name}</strong>
                {"status" in call && typeof call.status === "string" ? <span className="message-state">{call.status}</span> : null}
                {"result" in call && isErrorLike(call.result) ? <p className="notice notice-error">{stringifyValue(call.result)}</p> : null}
                <pre className="code-block">
                  <code>{JSON.stringify({ args: call.args ?? {}, result: "result" in call ? call.result : undefined }, null, 2)}</code>
                </pre>
              </li>
            ))}
          </ul>
        </DetailSection>
      ) : null}
    </div>
  );
}
