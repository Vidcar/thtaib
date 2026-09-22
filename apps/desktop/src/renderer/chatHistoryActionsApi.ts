import { request } from "./api";
import type { ChatConversation } from "./types";

export interface ChatReplyActions {
  branch_available: boolean;
  retry_available: boolean;
  regenerate_available: boolean;
  branch_reason: string | null;
  retry_reason: string | null;
  regenerate_reason: string | null;
}

export type ChatBranchMode = "continue" | "retry" | "edit" | "regenerate";

export interface ConversationExportPayload {
  schema_version: 1;
  exported_at: string;
  conversation: Record<string, unknown>;
  runs: Array<Record<string, unknown>>;
  retained_assets: Array<Record<string, unknown>>;
  note: string;
}

export interface ConversationDeletePreview {
  conversation_id: string;
  can_delete: boolean;
  blockers: Array<Record<string, string>>;
  affected_sessions: string[];
  retained_sessions: string[];
  affected_runs: string[];
  retained_runs: string[];
  affected_assets: string[];
  retained_assets: string[];
  checkpoint_threads_deleted: string[];
  checkpoint_threads_retained: string[];
  scratch_deleted: string[];
  diagnostics_deleted: boolean;
  project_sources_deleted: false;
  model_files_deleted: false;
  note: string;
}

export const chatHistoryActionsApi = {
  replyActions: (conversationId: string, runId: string) =>
    request<ChatReplyActions>(`/v1/chat/conversations/${encodeURIComponent(conversationId)}/replies/${encodeURIComponent(runId)}/actions`),
  createBranch: (conversationId: string, sourceRunId: string, mode: ChatBranchMode, acknowledgeRepeatedEffects = false, editedTask?: string) =>
    request<ChatConversation>(`/v1/chat/conversations/${encodeURIComponent(conversationId)}/branches`, {
      method: "POST",
      body: JSON.stringify({
        source_run_id: sourceRunId,
        mode,
        acknowledge_repeated_effects: acknowledgeRepeatedEffects,
        edited_task: editedTask,
      }),
    }),
  exportConversation: (conversationId: string) =>
    request<ConversationExportPayload>(`/v1/chat/conversations/${encodeURIComponent(conversationId)}/export`),
  deletePreview: (conversationId: string) =>
    request<ConversationDeletePreview>(`/v1/chat/conversations/${encodeURIComponent(conversationId)}/delete-preview`, { method: "POST", body: "{}" }),
  deleteConversation: (conversationId: string, includeDiagnostics = true) =>
    request<ConversationDeletePreview>(`/v1/chat/conversations/${encodeURIComponent(conversationId)}`, {
      method: "DELETE",
      body: JSON.stringify({ execute: true, include_diagnostics: includeDiagnostics }),
    }),
};
