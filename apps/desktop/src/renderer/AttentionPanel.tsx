import { useEffect, useState } from "react";

import { Icon } from "./Icon";
import { EmptyState } from "./EmptyState";
import { HoverHelp } from "./HoverHelp";
import { Notice } from "./Notice";
import { packet03Api, type AttentionItem } from "./packet03Api";
import "./packet03Panels.css";

interface AttentionPanelProps {
  onOpenItem?: (item: AttentionItem) => void;
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

export function notifyAttentionChanged(): void {
  if (typeof window !== "undefined" && typeof window.dispatchEvent === "function") {
    window.dispatchEvent(new Event("workbench-attention"));
  }
}

export function AttentionPanel({ onOpenItem }: AttentionPanelProps) {
  const [items, setItems] = useState<AttentionItem[]>([]);
  const [busy, setBusy] = useState(true);
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

  async function dismiss(item: AttentionItem): Promise<void> {
    setBusy(true);
    setMessage("");
    try {
      await packet03Api.dismissAttention(item.identity);
      notifyAttentionChanged();
      setItems(await packet03Api.attention());
    } catch (error) {
      setMessage(error instanceof Error ? error.message : String(error));
    } finally {
      setBusy(false);
    }
  }

  async function openItem(item: AttentionItem): Promise<void> {
    setBusy(true);
    setMessage("");
    try {
      await packet03Api.dismissAttention(item.identity);
      notifyAttentionChanged();
      onOpenItem?.(item);
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
        <div className="entity-head"><h2>Attention</h2><HoverHelp title="About Attention">Approvals, questions and run outcomes that need a look. Open an item to return to its conversation or task.</HoverHelp></div>
        <button type="button" disabled={busy} onClick={() => void refresh()}>
          <Icon name="refresh" size={14} /> Refresh
        </button>
      </div>

      {message ? <Notice role="status">{message}</Notice> : null}
      {items.length === 0 && !message ? busy ? <p className="hint">Loading…</p> : <EmptyState title="You're all caught up." /> : null}

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
              <div className="actions">
                <button type="button" disabled={busy || !onOpenItem} onClick={() => openItem(item)}>
                  <Icon name="chat" size={14} /> Open
                </button>
                <button type="button" className="icon-button" aria-label={`Dismiss ${item.title || "notice"}`} title="Dismiss" disabled={busy} onClick={() => void dismiss(item)}>
                  <Icon name="close" size={14} />
                </button>
              </div>
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
    const onChanged = () => { void refresh(); };
    const listen = typeof window.addEventListener === "function";
    if (listen) window.addEventListener("workbench-attention", onChanged);
    const timer = window.setInterval(() => void refresh(), 30000);
    return () => {
      cancelled = true;
      if (listen) window.removeEventListener("workbench-attention", onChanged);
      window.clearInterval(timer);
    };
  }, []);

  return (
    <button type="button" className={`tab packet03-attention-button${active ? " active" : ""}${collapsed ? " is-collapsed" : ""} ${className}`} onClick={onOpen} aria-current={active ? "page" : undefined} aria-label={`Attention, ${count} item${count === 1 ? "" : "s"}`} title={`Attention · ${count} item${count === 1 ? "" : "s"}`}>
      <Icon name="attention" size={18} />
      {!collapsed ? <span className="nav-label">Attention</span> : null}
      {count ? <strong className="attention-count">{count}</strong> : null}
    </button>
  );
}
