import { useEffect, useState } from "react";

import { Icon } from "./Icon";
import { HoverHelp } from "./HoverHelp";
import { packet03Api, type AttentionItem } from "./packet03Api";
import "./packet03Panels.css";

interface AttentionPanelProps {
  onOpenConversation?: (conversationId: string | null) => void;
}

function attentionKindLabel(kind: AttentionItem["kind"]): string {
  switch (kind) {
    case "approval":
      return "Approval needed";
    case "question":
      return "Answer needed";
    case "failure":
      return "Needs review";
    case "success":
      return "Completed";
    default:
      return kind || "Attention";
  }
}

export function AttentionPanel({ onOpenConversation }: AttentionPanelProps) {
  const [items, setItems] = useState<AttentionItem[]>([]);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");

  async function refresh(): Promise<void> {
    setBusy(true);
    setMessage("");
    try {
      setItems(await packet03Api.attention());
    } catch (error) {
      setMessage(error instanceof Error ? error.message : String(error));
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    void refresh();
  }, []);

  return (
    <section className="packet03-panel" aria-label="Attention">
      <div className="packet03-row">
        <div className="entity-head"><h2>Attention</h2><HoverHelp title="About Attention">Approvals, questions and run outcomes that need a look. Open an item to continue in Chat.</HoverHelp></div>
        <button type="button" disabled={busy} onClick={() => void refresh()}>
          <Icon name="refresh" size={14} /> Refresh
        </button>
      </div>

      {message ? <p role="status" className="notice">{message}</p> : null}
      {items.length === 0 ? <p className="hint">{busy ? "Loading…" : "You're all caught up."}</p> : null}

      <ul className="packet03-list">
        {items.map((item) => (
          <li key={item.identity} className="packet03-item">
            <div className="packet03-row">
              <div>
                <strong>{item.title || "Untitled conversation"}</strong>
                <div className="packet03-meta">
                  <span>{attentionKindLabel(item.kind)}</span>
                </div>
                <HoverHelp title="Item details">Run: {item.run_id}<br />Record: {item.identity}</HoverHelp>
              </div>
              <button type="button" disabled={!onOpenConversation} onClick={() => onOpenConversation?.(item.conversation_id)}>
                <Icon name="chat" size={14} /> Open
              </button>
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}

interface AttentionButtonProps {
  onOpen?: () => void;
  active?: boolean;
  collapsed?: boolean;
  className?: string;
}

export function AttentionButton({ onOpen, active = false, collapsed = false, className = "" }: AttentionButtonProps) {
  const [count, setCount] = useState(0);

  useEffect(() => {
    let cancelled = false;
    async function refresh(): Promise<void> {
      try {
        const items = await packet03Api.attention();
        if (!cancelled) {
          setCount(items.length);
        }
      } catch {
        if (!cancelled) {
          setCount(0);
        }
      }
    }
    void refresh();
    const timer = window.setInterval(() => void refresh(), 30000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, []);

  return (
    <button type="button" className={`tab packet03-attention-button${active ? " active" : ""}${collapsed ? " is-collapsed" : ""} ${className}`} onClick={onOpen} aria-current={active ? "page" : undefined} aria-label={`Attention, ${count} item${count === 1 ? "" : "s"}`} title={`Attention · ${count} item${count === 1 ? "" : "s"}`}>
      <Icon name="attention" size={18} />
      {!collapsed ? <span className="nav-label">Attention</span> : null}
      {count ? <strong>{count}</strong> : null}
    </button>
  );
}
