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
  const decoder = new TextDecoder();
  let pending = "";
  let eventId: number | null = null;
  let hasData = false;
  // Only a complete SSE frame can advance the resume cursor. A connection
  // may end after its id line but before its token data has reached the SDK.
  // pipeThrough also propagates cancellation to the original response body.
  const stream = response.body!.pipeThrough(new TransformStream<Uint8Array, Uint8Array>({
    transform(value, controller) {
      pending += decoder.decode(value, { stream: true });
      let end: number;
      while ((end = pending.search(/[\r\n]/)) >= 0) {
        if (pending[end] === "\r" && end === pending.length - 1) break;
        const line = pending.slice(0, end);
        pending = pending.slice(end + (pending.slice(end, end + 2) === "\r\n" ? 2 : 1));
        if (line === "") {
          if (hasData && eventId !== null) onSeq(eventId);
          eventId = null;
          hasData = false;
        } else if (line.startsWith("id:")) {
          const raw = line.slice(3).trim();
          const seq = Number(raw);
          eventId = raw && Number.isSafeInteger(seq) && seq >= 0 ? seq : null;
        } else if (line.startsWith("data:")) {
          hasData = true;
        }
      }
      controller.enqueue(value);
    },
  }));
  return new Response(stream, {
    status: response.status,
    statusText: response.statusText,
    headers: response.headers,
  });
}
