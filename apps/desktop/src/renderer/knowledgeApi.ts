import { request } from "./api";
import type { SchemaKnowledgeScopeOption, SchemaKnowledgeProposal, SchemaKnowledgeAutomaticPolicy } from "../generated/shared-contracts/openapi";
import type { KnowledgeConfig, KnowledgeEntry, KnowledgeScope } from "./types";
export type KnowledgeScopeOption = SchemaKnowledgeScopeOption;
export type KnowledgeProposal = SchemaKnowledgeProposal;
export interface SkillResourceChange { path: string; content_base64?: string; remove?: boolean }
export interface SkillGuidedFields { name: string; description: string; instructions: string }
export interface SkillPreview { content: string; name: string | null; description: string | null; instructions: string | null; guided_available: boolean; valid: boolean; issues: string[] }
export const knowledgeApi = {
  previewSkill: (payload: { content: string; fields?: SkillGuidedFields; scope?: KnowledgeScope; scope_id?: string | null; entry_id?: string }) => request<SkillPreview>("/v1/knowledge/skills/preview", { method: "POST", body: JSON.stringify(payload) }),
  createEntry: (payload: { content: string; kind: "memory" | "skill" | "protected_instruction"; scope: KnowledgeScope; scope_id?: string; display_name?: string; resource_changes?: SkillResourceChange[] }) => request<KnowledgeEntry>("/v1/knowledge/entries", { method: "POST", body: JSON.stringify(payload) }),
  editEntry: (id: string, content: string, base_version: string, resource_changes: SkillResourceChange[] = []) => request<KnowledgeEntry>(`/v1/knowledge/entries/${id}/edit`, { method: "POST", body: JSON.stringify({ content, base_version, resource_changes }) }),
  scopes: () => request<KnowledgeScopeOption[]>("/v1/knowledge/scopes"),
  proposals: (runId?: string) => request<KnowledgeProposal[]>(`/v1/knowledge/proposals${runId ? `?run_id=${encodeURIComponent(runId)}` : ""}`),
  review: (id: string, decision: "accept" | "reject") => request<KnowledgeProposal>(`/v1/knowledge/proposals/${id}/review`, { method: "POST", body: JSON.stringify({ decision }) }),
  updateEntry: (id: string, payload: { display_name?: string; enabled?: boolean }) => request<KnowledgeEntry>(`/v1/knowledge/entries/${id}`, { method: "PATCH", body: JSON.stringify(payload) }),
  removeEntry: (id: string) => request<KnowledgeEntry>(`/v1/knowledge/entries/${id}`, { method: "DELETE" }),
  automaticPolicy: (payload: SchemaKnowledgeAutomaticPolicy) => request<KnowledgeConfig>("/v1/knowledge/automatic-save-policy", { method: "PUT", body: JSON.stringify(payload) }),
};
