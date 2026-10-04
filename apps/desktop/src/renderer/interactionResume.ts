import { HttpAgentServerAdapter } from "@langchain/react";

import { backendUrl } from "./api";

/** Keep command facts that the SDK's generic HTTP error otherwise discards. */
export class InteractionCommandError extends Error {
  constructor(message: string, readonly status: number, readonly code: string | undefined,
    readonly commandId: string | number | undefined, readonly inputId: string | undefined,
    readonly threadId: string) {
    super(message);
    this.name = "InteractionCommandError";
  }
}

function commandFetch(threadId: string): typeof fetch {
  const requestFetch = fetch;
  return async (input, init) => {
    const response = await requestFetch(input, init);
    const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
    if (response.ok || init?.method !== "POST" || !url.endsWith(`/threads/${encodeURIComponent(threadId)}/commands`)) return response;
    let command: { id?: string | number; params?: { input?: { messages?: Array<{ id?: string }> } } } = {};
    let failure: { type?: string; id?: string | number; error?: string; code?: string; message?: string } = {};
    try { command = JSON.parse(typeof init.body === "string" ? init.body : "{}"); } catch { /* Preserve the response error. */ }
    try { failure = await response.clone().json(); } catch { /* A proxy failure has no protocol envelope. */ }
    const protocol = failure.type === "error" && (typeof command.id === "string" || typeof command.id === "number") && failure.id === command.id;
    throw new InteractionCommandError(
      failure.message ?? (protocol ? failure.error : undefined) ?? `Command request failed (${response.status}).`,
      response.status, protocol ? failure.error : undefined, command.id,
      command.params?.input?.messages?.[0]?.id, threadId,
    );
  };
}

// The pinned SDK patch keeps hydration, subscription replay and reconnect
// cursors at their respective owners.
export function createResumingInteractionTransport(threadId: string) {
  return new HttpAgentServerAdapter({
    apiUrl: `${backendUrl()}/v1/agent-interaction`,
    threadId,
    fetch: commandFetch(threadId),
  });
}
