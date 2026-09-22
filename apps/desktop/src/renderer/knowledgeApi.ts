import { request } from "./api";
import type { SchemaKnowledgeScopeOption, SchemaKnowledgeProposal, SchemaKnowledgeAutomaticPolicy } from "../generated/shared-contracts/openapi";
import type { KnowledgeConfig, KnowledgeEntry } from "./types";
export type KnowledgeScopeOption = SchemaKnowledgeScopeOption;
export type KnowledgeProposal = SchemaKnowledgeProposal;
export const knowledgeApi = {
  scopes: () => request<KnowledgeScopeOption[]>("/v1/knowledge/scopes"),
  proposals: (runId?: string) => request<KnowledgeProposal[]>(`/v1/knowledge/proposals${runId ? `?run_id=${encodeURIComponent(runId)}` : ""}`),
  review: (id: string, decision: "accept" | "reject") => request<KnowledgeProposal>(`/v1/knowledge/proposals/${id}/review`, { method: "POST", body: JSON.stringify({ decision }) }),
  updateEntry: (id: string, payload: { display_name?: string; enabled?: boolean }) => request<KnowledgeEntry>(`/v1/knowledge/entries/${id}`, { method: "PATCH", body: JSON.stringify(payload) }),
  removeEntry: (id: string) => request<KnowledgeEntry>(`/v1/knowledge/entries/${id}`, { method: "DELETE" }),
  automaticPolicy: (payload: SchemaKnowledgeAutomaticPolicy) => request<KnowledgeConfig>("/v1/knowledge/automatic-save-policy", { method: "PUT", body: JSON.stringify(payload) }),
};
