import { useEffect, useRef, useState } from "react";
import { chatHistoryActionsApi, type ConversationDeletePreview } from "./chatHistoryActionsApi";
import { conversationTitle } from "./display";
import { Icon } from "./Icon";
import type { ChatConversation } from "./types";

export function DeleteChatDialog({ conversation, onClose, onDeleted }: { conversation: ChatConversation; onClose: () => void; onDeleted: (id: string) => void }) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [preview, setPreview] = useState<ConversationDeletePreview | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    dialog.current?.showModal();
    let cancelled = false;
    void chatHistoryActionsApi.deletePreview(conversation.id).then(value => { if (!cancelled) setPreview(value); }).catch(reason => { if (!cancelled) setError(String(reason.message ?? reason)); });
    return () => { cancelled = true; };
  }, [conversation.id]);
  async function remove() {
    setBusy(true); setError("");
    try { await chatHistoryActionsApi.deleteConversation(conversation.id, true); onDeleted(conversation.id); onClose(); }
    catch (reason) { setError(reason instanceof Error ? reason.message : String(reason)); setBusy(false); }
  }
  return <dialog ref={dialog} className="compact-dialog" aria-labelledby="delete-chat-title" onCancel={event => { if (busy) event.preventDefault(); else onClose(); }}>
    <header><h3 id="delete-chat-title">Delete chat?</h3><button type="button" className="icon-button" aria-label="Close" disabled={busy} onClick={onClose}><Icon name="close" /></button></header>
    <p className="delete-chat-name">{conversationTitle(conversation)}</p>
    <p>This permanently removes this chat and its history. Files created in your project stay.</p>
    {preview && !preview.can_delete ? <p className="notice notice-warn">Stop active work before deleting this chat.</p> : null}
    {preview && (preview.retained_sessions.length + preview.retained_runs.length + preview.checkpoint_threads_retained.length) > 0 ? <p className="hint">History shared with another chat is kept for that chat.</p> : null}
    {error ? <p role="alert" className="notice notice-error">{error}</p> : null}
    <footer><button type="button" disabled={busy} onClick={onClose}>Cancel</button><button type="button" className="danger" disabled={!preview?.can_delete || busy} onClick={() => void remove()}>{busy ? "Deleting…" : "Delete chat"}</button></footer>
  </dialog>;
}
