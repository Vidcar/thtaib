import type { Dispatch, SetStateAction } from "react";
import { api } from "./api";
import type { ChatRailPage } from "./ChatDock";
import type { AgentRun, ChatConversation, WorkbenchTab } from "./types";

interface SelectionOwner {
  conversationId: string;
  threadId: string;
  generation: number;
}

interface PendingStopRequest {
  id: string;
  conversation_id: string;
  thread_id: string;
  selection_generation: number;
}

export function stopCurrentWork(deps: {
  conversation: ChatConversation | null;
  interactionThreadId: string | null;
  boundGeneration: number;
  pendingSubmissionActive: boolean;
  pendingSubmit: PendingStopRequest | null;
  setPendingStop: Dispatch<SetStateAction<PendingStopRequest | null>>;
  isCurrentOwner: (owner: SelectionOwner) => boolean;
  cacheConversation: (next: ChatConversation) => void;
  setConversation: Dispatch<SetStateAction<ChatConversation | null>>;
  fail: (error: unknown) => void;
  updateConversationForRun: (conversation: ChatConversation, owner: SelectionOwner, runId: string) => void;
}): void {
  const {
    conversation, interactionThreadId, boundGeneration, pendingSubmissionActive, pendingSubmit, setPendingStop,
    isCurrentOwner, cacheConversation, setConversation, fail, updateConversationForRun,
  } = deps;
  if (!conversation || !interactionThreadId) {
    return;
  }
  const owner = {
    conversationId: conversation.id,
    threadId: interactionThreadId,
    generation: boundGeneration,
  };
  if (pendingSubmissionActive && pendingSubmit) {
    const stopRequest = {
      id: pendingSubmit.id,
      conversation_id: pendingSubmit.conversation_id,
      thread_id: pendingSubmit.thread_id,
      selection_generation: pendingSubmit.selection_generation,
    };
    setPendingStop(stopRequest);
    void api.cancelChat(conversation.id, pendingSubmit.id)
      .then((next) => {
        if (!isCurrentOwner(owner)) {
          cacheConversation(next);
          return;
        }
        cacheConversation(next);
        setConversation(next);
        // This response acknowledges the stop claim. The submission owner
        // still resolves acceptance or failure while model loading unwinds.
      })
      .catch((error: unknown) => {
        if (isCurrentOwner(owner)) {
          setPendingStop((current) => (current?.id === stopRequest.id ? null : current));
          fail(error);
        }
      });
    return;
  }
  if (conversation.current_run?.finalization_phase === "saving_changes") {
    return;
  }
  if (!conversation.current_run) {
    return;
  }
  const cancelledRunId = conversation.current_run.id;
  void api.cancelAgentRun(cancelledRunId)
    .then((next) => {
      updateConversationForRun({ ...conversation, current_run: next, current_run_id: next.id }, owner, cancelledRunId);
    })
    .catch((error: unknown) => {
      if (isCurrentOwner(owner)) {
        fail(error);
      }
    });
}

export function recoverRun(run: AgentRun, deps: {
  setRecoveryRun: (run: AgentRun | null) => void;
  openRail: (page: ChatRailPage) => void;
  navigateAway: (tab: WorkbenchTab, recordId?: string) => void;
  task: string;
  updateTask: (next: string) => void;
}): void {
  const { setRecoveryRun, openRail, navigateAway, task, updateTask } = deps;
  const action = run.failure?.recovery_action;
  if (action === "inspect_effects" || action === "ask") {
    setRecoveryRun(run);
    openRail("files");
  } else if (action === "change_limit") {
    navigateAway("models");
  } else if (action === "correct_setup") {
    navigateAway("agents");
  } else {
    if (!task.trim()) updateTask("Continue from the confirmed results. Inspect existing work before repeating any action.");
    document.querySelector<HTMLTextAreaElement>('textarea[aria-label="Message"]')?.focus();
  }
}
