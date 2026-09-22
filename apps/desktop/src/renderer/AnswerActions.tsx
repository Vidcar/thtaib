import { useEffect, useState } from "react";
import { chatHistoryActionsApi } from "./chatHistoryActionsApi";
import { CopyIconButton } from "./CopyIconButton";
import { Icon } from "./Icon";
import type { ChatConversation } from "./types";

export function AnswerActions({
  conversation,
  runId,
  answerText,
  disabled = false,
  onConversationCreated,
  onError,
}: {
  conversation: ChatConversation;
  runId: string;
  answerText: string;
  disabled?: boolean;
  onConversationCreated: (next: ChatConversation) => void;
  onError: (message: string) => void;
}) {
  const [branchAvailable, setBranchAvailable] = useState(false);
  const [regenerateAvailable, setRegenerateAvailable] = useState(false);
  const [branchReason, setBranchReason] = useState<string | null>(null);
  const [regenerateReason, setRegenerateReason] = useState<string | null>(null);
  const [busy, setBusy] = useState<"branch" | "regenerate" | null>(null);
  const projectState = Boolean(conversation.project_path || conversation.area_project_path || conversation.workspace_id || conversation.area_workspace_id);

  useEffect(() => {
    let cancelled = false;
    setBranchAvailable(false);
    setRegenerateAvailable(false);
    setBranchReason(null);
    setRegenerateReason(null);
    void chatHistoryActionsApi.replyActions(conversation.id, runId).then(next => {
      if (cancelled) return;
      setBranchAvailable(next.branch_available);
      setRegenerateAvailable(next.regenerate_available);
      setBranchReason(next.branch_reason);
      setRegenerateReason(next.regenerate_reason);
    }).catch((error: unknown) => {
      if (!cancelled) onError(error instanceof Error ? error.message : String(error));
    });
    return () => { cancelled = true; };
  }, [conversation.id, conversation.current_run_id, conversation.current_run?.status, runId, onError]);

  async function run(mode: "continue" | "regenerate") {
    setBusy(mode === "regenerate" ? "regenerate" : "branch");
    try {
      onConversationCreated(await chatHistoryActionsApi.createBranch(conversation.id, runId, mode, false));
    } catch (error) {
      onError(error instanceof Error ? error.message : String(error));
    } finally {
      setBusy(null);
    }
  }

  const blocked = disabled || busy !== null;
  const branchLabel = projectState ? "Branch workspace" : "Branch chat";
  return (
    <div className="answer-actions" role="group" aria-label="Answer actions">
      <CopyIconButton text={answerText} label="Copy answer" />
      <button type="button" className="icon-button" aria-label="Regenerate answer" title={regenerateReason ?? "Regenerate answer"} disabled={blocked || !regenerateAvailable} onClick={() => void run("regenerate")}>
        <Icon name="refresh" size={14} />
      </button>
      <button type="button" className="icon-button" aria-label={branchLabel} title={branchReason ?? branchLabel} disabled={blocked || !branchAvailable} onClick={() => void run("continue")}>
        <Icon name="branch" size={14} />
      </button>
    </div>
  );
}
