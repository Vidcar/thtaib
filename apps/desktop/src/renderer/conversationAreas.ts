import type { ChatConversation } from "./types";

export function areaKind(conversation: ChatConversation): "general" | "project" {
  return conversation.area_kind ?? (conversation.project_path ? "project" : "general");
}

export function areaLabel(conversation: ChatConversation | null): string {
  if (!conversation || areaKind(conversation) !== "project") {
    return "General";
  }
  if (conversation.area_label?.trim()) {
    return conversation.area_label;
  }
  const path = conversation.area_project_path ?? conversation.project_path;
  if (!path) {
    return "Project";
  }
  const normalized = path.replace(/\\/g, "/");
  return normalized.split("/").filter(Boolean).at(-1) ?? path;
}

export function areaKey(conversation: ChatConversation): string {
  if (areaKind(conversation) !== "project") {
    return "general";
  }
  return conversation.project_id ?? conversation.area_id ?? conversation.area_project_path ?? conversation.project_path ?? conversation.id;
}

export function newestConversationFirst(items: ChatConversation[]): ChatConversation[] {
  return [...items].sort((left, right) => Date.parse(right.updated_at) - Date.parse(left.updated_at));
}
