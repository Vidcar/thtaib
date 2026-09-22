import { useEffect, useState } from "react";

import { Icon } from "./Icon";
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
        <div>
          <p className="eyebrow">Attention</p>
          <h2>Items that need you</h2>
        </div>
        <button type="button" disabled={busy} onClick={() => void refresh()}>
          Refresh
        </button>
      </div>

      {message ? <p role="status" className="notice">{message}</p> : null}
      {items.length === 0 ? <p className="hint">No approvals, questions or failures are waiting.</p> : null}

      <ul className="packet03-list">
        {items.map((item) => (
          <li key={item.identity} className="packet03-item">
            <div className="packet03-row">
              <div>
                <strong>{item.title || "Untitled conversation"}</strong>
                <div className="packet03-meta">
                  <span>{attentionKindLabel(item.kind)}</span>
                </div>
                <details className="packet03-details">
                  <summary>Details</summary>
                  <p className="hint">Run: {item.run_id}</p>
                  <p className="hint">Record: {item.identity}</p>
                </details>
              </div>
              <button type="button" disabled={!onOpenConversation} onClick={() => onOpenConversation?.(item.conversation_id)}>
                Open in Chat
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
}

export function AttentionButton({ onOpen }: AttentionButtonProps) {
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
    <button type="button" className="packet03-attention-button" onClick={onOpen} aria-label={`${count} attention item${count === 1 ? "" : "s"}`}>
      <Icon name="attention" size={18} />
      <span>Attention</span>
      {count ? <strong>{count}</strong> : null}
    </button>
  );
}
