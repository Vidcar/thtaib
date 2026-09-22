import { HttpAgentServerAdapter } from "@langchain/react";

import { backendUrl } from "./api";

// The stock stream client omits its resume cursor after the first attempt.
// Opening a chat would otherwise walk every stored token from the beginning.
export function createResumingInteractionTransport(threadId: string) {
  let cursor = 0;
  const baseFetch = globalThis.fetch.bind(globalThis);
  const fetchWithResume: typeof fetch = async (input, init) => {
    const url = requestUrl(input);
    let nextInit = init;
    if (init?.method === "POST" && url.includes("/stream/events") && typeof init.body === "string") {
      const body = JSON.parse(init.body) as { since?: number };
      body.since = cursor;
      nextInit = { ...init, body: JSON.stringify(body) };
    }
    const response = await baseFetch(input, nextInit);
    if (response.ok && url.includes("/state")) {
      try {
        const snapshot = await response.clone().json() as { interaction_cursor?: unknown };
        if (typeof snapshot.interaction_cursor === "number" && snapshot.interaction_cursor > cursor) {
          cursor = snapshot.interaction_cursor;
        }
      } catch {
        // A non-JSON state response leaves the cursor where it is.
      }
    }
    if (response.ok && response.body && init?.method === "POST" && url.includes("/stream/events")) {
      return tapEventIds(response, (seq) => {
        if (seq > cursor) {
          cursor = seq;
        }
      });
    }
    return response;
  };
  return new HttpAgentServerAdapter({
    apiUrl: `${backendUrl()}/v1/agent-interaction`,
    threadId,
    fetch: fetchWithResume,
  });
}

function requestUrl(input: RequestInfo | URL): string {
  if (typeof input === "string") {
    return input;
  }
  if (input instanceof URL) {
    return input.href;
  }
  return input.url;
}

function tapEventIds(response: Response, onSeq: (seq: number) => void): Response {
  const reader = response.body!.getReader();
  const decoder = new TextDecoder();
  let pending = "";
  const stream = new ReadableStream<Uint8Array>({
    async pull(controller) {
      const { done, value } = await reader.read();
      if (done) {
        controller.close();
        return;
      }
      controller.enqueue(value);
      pending += decoder.decode(value, { stream: true });
      const lines = pending.split("\n");
      pending = lines.pop() ?? "";
      for (const line of lines) {
        const trimmed = line.replace(/\r$/, "");
        if (!trimmed.startsWith("id:")) {
          continue;
        }
        const seq = Number(trimmed.slice(3).trim());
        if (Number.isInteger(seq) && seq >= 0) {
          onSeq(seq);
        }
      }
    },
  });
  return new Response(stream, {
    status: response.status,
    statusText: response.statusText,
    headers: response.headers,
  });
}
