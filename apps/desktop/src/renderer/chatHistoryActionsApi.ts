import { request } from "./api";

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
  deletePreview: (conversationId: string) =>
    request<ConversationDeletePreview>(`/v1/chat/conversations/${encodeURIComponent(conversationId)}/delete-preview`, { method: "POST", body: "{}" }),
  deleteConversation: (conversationId: string, includeDiagnostics = true) =>
    request<ConversationDeletePreview>(`/v1/chat/conversations/${encodeURIComponent(conversationId)}`, {
      method: "DELETE",
      body: JSON.stringify({ execute: true, include_diagnostics: includeDiagnostics }),
    }),
};
