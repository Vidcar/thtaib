import { api } from "./api";
import type { ChatConversation } from "./types";

type DraftWrite = Parameters<typeof api.updateChatDraft>[1];

/** Serialize this window's draft writes while SQLite remains the authority. */
export class ChatDraftWriter {
  private tail: Promise<unknown> = Promise.resolve();
  private revisions = new Map<string, number>();

  observe(conversation: ChatConversation): void {
    this.revisions.set(conversation.id, Math.max(this.revisions.get(conversation.id) ?? 0, conversation.draft?.revision ?? 0));
  }

  accepted(conversationId: string, submittedRevision: number | null | undefined): void {
    if (submittedRevision == null) return;
    this.revisions.set(conversationId, Math.max(this.revisions.get(conversationId) ?? 0, submittedRevision + 1));
  }

  save(conversation: ChatConversation, payload: DraftWrite): Promise<ChatConversation> {
    this.observe(conversation);
    const snapshot = structuredClone(payload);
    const next = this.tail.catch(() => undefined).then(async () => {
      const result = await api.updateChatDraft(conversation.id, {
        ...snapshot,
        expected_revision: this.revisions.get(conversation.id) ?? 0,
      });
      this.observe(result);
      return result;
    });
    this.tail = next;
    return next;
  }
}

export function sameDraftValue(left: unknown, right: unknown): boolean {
  const canonical = (value: unknown): unknown => Array.isArray(value) ? value.map(canonical)
    : value !== null && typeof value === "object" ? Object.fromEntries(Object.entries(value).sort(([a], [b]) => a.localeCompare(b)).map(([key, item]) => [key, canonical(item)]))
    : value;
  return JSON.stringify(canonical(left)) === JSON.stringify(canonical(right));
}
