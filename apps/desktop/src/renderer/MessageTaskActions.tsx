import { useEffect, useState } from "react";
import { chatHistoryActionsApi } from "./chatHistoryActionsApi";
import { Icon } from "./Icon";
import { MenuPopover } from "./MenuPopover";
import { errorMessage } from "./errors";
import type { ChatConversation } from "./types";

export function MessageTaskActions({ conversation, runId, task, disabled, onCreated, onError }: { conversation: ChatConversation; runId: string; task: string; disabled: boolean; onCreated: (conversation: ChatConversation) => void; onError: (error: string) => void }) {
  const [availability, setAvailability] = useState<{ available: boolean; reason: string | null }>({ available: false, reason: "Checking" });
  const [edited, setEdited] = useState(task);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    let stale = false;
    void chatHistoryActionsApi.replyActions(conversation.id, runId).then(result => { if (!stale) setAvailability({ available: result.retry_available, reason: result.retry_reason }); }).catch(error => { if (!stale) setAvailability({ available: false, reason: errorMessage(error) }); });
    return () => { stale = true; };
  }, [conversation.id, runId, conversation.current_run?.status]);
  async function branch(mode: "retry" | "edit") {
    if (!window.confirm("This attempt may repeat file changes, commands or other external effects. Continue?")) return;
    setBusy(true);
    try { onCreated(await chatHistoryActionsApi.createBranch(conversation.id, runId, mode, true, mode === "edit" ? edited.trim() : undefined)); }
    catch (error) { onError(errorMessage(error)); }
    finally { setBusy(false); }
  }
  return <div className="message-task-actions" role="group" aria-label="Message actions">
    <button type="button" className="icon-button" aria-label="Retry task" title={availability.reason ?? "Retry task"} disabled={disabled || busy || !availability.available} onClick={() => void branch("retry")}><Icon name="refresh" size={14} /></button>
    <MenuPopover label="Edit task" trigger={<Icon name="edit" size={14} />} disabled={disabled || busy || !availability.available}><label>Edit task<textarea aria-label="Edit task text" value={edited} onChange={event => setEdited(event.target.value)} /></label><button type="button" disabled={busy || !edited.trim()} onClick={() => void branch("edit")}>Create edit branch</button></MenuPopover>
  </div>;
}
