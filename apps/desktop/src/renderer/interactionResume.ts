import { HttpAgentServerAdapter } from "@langchain/react";

import { backendUrl } from "./api";

// The pinned SDK patch keeps hydration, subscription replay and reconnect
// cursors at their respective owners.
export function createResumingInteractionTransport(threadId: string) {
  return new HttpAgentServerAdapter({
    apiUrl: `${backendUrl()}/v1/agent-interaction`,
    threadId,
  });
}
