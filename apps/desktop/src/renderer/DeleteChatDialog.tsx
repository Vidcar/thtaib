import { useEffect, useState } from "react";
import { chatHistoryActionsApi, type ConversationDeletePreview } from "./chatHistoryActionsApi";
import { CompactDialog } from "./CompactDialog";
import { conversationTitle } from "./display";
import { Notice } from "./Notice";
import type { ChatConversation } from "./types";

export function DeleteChatDialog({ conversation, onClose, onDeleted }: { conversation: ChatConversation; onClose: () => void; onDeleted: (id: string) => void }) {
  const [preview, setPreview] = useState<ConversationDeletePreview | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    let cancelled = false;
    void chatHistoryActionsApi.deletePreview(conversation.id).then(value => { if (!cancelled) setPreview(value); }).catch(reason => { if (!cancelled) setError(reason instanceof Error ? reason.message : String(reason)); });
    return () => { cancelled = true; };
  }, [conversation.id]);
  async function remove() {
    setBusy(true); setError("");
    try { await chatHistoryActionsApi.deleteConversation(conversation.id, true); onDeleted(conversation.id); onClose(); }
    catch (reason) { setError(reason instanceof Error ? reason.message : String(reason)); setBusy(false); }
  }
  return (
    <CompactDialog title="Delete chat?" labelledBy="delete-chat-title" busy={busy} onClose={onClose}>
      <p className="delete-chat-name">{conversationTitle(conversation)}</p>
      <p>This permanently removes this chat and its history. Files created in your project stay.</p>
      {preview && !preview.can_delete ? <Notice tone="warn">Stop active work before deleting this chat.</Notice> : null}
      {preview && (preview.retained_sessions.length + preview.retained_runs.length + preview.checkpoint_threads_retained.length) > 0 ? <p className="hint">History shared with another chat is kept for that chat.</p> : null}
      {error ? <Notice tone="error" role="alert">{error}</Notice> : null}
      <footer><button type="button" disabled={busy} onClick={onClose}>Cancel</button><button type="button" className="danger" disabled={!preview?.can_delete || busy} onClick={() => void remove()}>{busy ? "Deleting…" : "Delete chat"}</button></footer>
    </CompactDialog>
  );
}
