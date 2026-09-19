import type { RunStreamEnvelope, RunStreamEventType, SharedAgentEvent } from "./sharedContracts";
import type { AgentRun, AgentRunStatus, ChatConversation } from "./types";

export type { RunStreamEnvelope, RunStreamEventType, SharedAgentEvent };

function backendUrl(): string {
  return window.workbench?.backendUrl ?? "http://127.0.0.1:8000";
}

function parseSseBlock(block: string): { event?: string; id?: string; data?: string } {
  const parsed: { event?: string; id?: string; data?: string } = {};
  for (const raw of block.split(/\r?\n/)) {
    if (!raw || raw.startsWith(":")) {
      continue;
    }
    const idx = raw.indexOf(":");
    const name = idx === -1 ? raw : raw.slice(0, idx);
    const value = idx === -1 ? "" : raw.slice(idx + 1).replace(/^ /, "");
    if (name === "event") {
      parsed.event = value;
    } else if (name === "id") {
      parsed.id = value;
    } else if (name === "data") {
      parsed.data = parsed.data ? `${parsed.data}\n${value}` : value;
    }
  }
  return parsed;
}

function applyStreamEvent<T>(current: T | null, envelope: RunStreamEnvelope): T | null {
  switch (envelope.type) {
    case "snapshot":
      return (envelope.snapshot as T | null | undefined) ?? current;
    case "run_event": {
      if (current === null || envelope.event === null) {
        return current;
      }
      return mergeRunEvent(current, envelope);
    }
    case "stream_end":
      return current;
    default: {
      const exhaustive: never = envelope.type;
      return exhaustive;
    }
  }
}

function recordedEventCount(record: {
  events?: SharedAgentEvent[];
  current_run?: { events: SharedAgentEvent[] } | null;
}): number {
  if (record.current_run != null) {
    return record.current_run.events.length;
  }
  return record.events?.length ?? 0;
}

function mergeRunEvent<T>(current: T, envelope: RunStreamEnvelope): T {
  const event = envelope.event;
  if (event == null) {
    return current;
  }
  const record = current as {
    events?: SharedAgentEvent[];
    current_run?: AgentRun | null;
    status?: AgentRunStatus;
  };
  const seq = envelope.seq;
  const known = recordedEventCount(record);
  if (seq == null || seq <= known) {
    return current;
  }
  const events = [...(record.events ?? []), event];
  if (record.current_run) {
    const runEvents = [...record.current_run.events, event];
    return {
      ...current,
      events,
      current_run: {
        ...record.current_run,
        status: envelope.status ?? record.current_run.status,
        events: runEvents,
      },
    };
  }
  if (record.status !== undefined) {
    return {
      ...current,
      status: envelope.status ?? record.status,
      events,
    };
  }
  return current;
}

async function readEventStream(
  url: string,
  signal: AbortSignal,
  lastEventId: number | undefined,
  onEnvelope: (envelope: RunStreamEnvelope, lastId?: number) => void,
): Promise<"ended" | "closed"> {
  const headers: Record<string, string> = { Accept: "text/event-stream" };
  if (lastEventId !== undefined) {
    headers["Last-Event-ID"] = String(lastEventId);
  }
  const response = await fetch(url, {
    method: "GET",
    headers,
    signal,
  });
  if (!response.ok) {
    const body = (await response.json().catch(() => ({}))) as { error?: string };
    throw new Error(body.error ?? `${response.status} ${url}`);
  }
  const reader = response.body?.getReader();
  if (!reader) {
    throw new Error("Event stream had no body");
  }
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) {
      return "closed";
    }
    buffer += decoder.decode(value, { stream: true });
    const parts = buffer.split(/\r?\n\r?\n/);
    buffer = parts.pop() ?? "";
    for (const block of parts) {
      const parsed = parseSseBlock(block);
      if (!parsed.data) {
        continue;
      }
      const envelope = JSON.parse(parsed.data) as RunStreamEnvelope;
      if (parsed.event && envelope.type !== parsed.event) {
        envelope.type = parsed.event as RunStreamEventType;
      }
      const lastId = parsed.id !== undefined && parsed.id !== "" ? Number(parsed.id) : undefined;
      onEnvelope(envelope, Number.isFinite(lastId) ? lastId : undefined);
      if (envelope.type === "stream_end") {
        return "ended";
      }
    }
  }
}

export async function subscribeWorkbenchEvents<T>(options: {
  runId?: string;
  conversationId?: string;
  signal: AbortSignal;
  apply: (current: T | null, envelope: RunStreamEnvelope) => T | null;
  onRecord: (record: T) => void;
}): Promise<void> {
  const params = new URLSearchParams();
  if (options.runId) {
    params.set("run_id", options.runId);
  } else if (options.conversationId) {
    params.set("conversation_id", options.conversationId);
  } else {
    throw new Error("subscribeWorkbenchEvents requires runId or conversationId");
  }
  let lastEventId: number | undefined;
  let current: T | null = null;
  while (!options.signal.aborted) {
    const url = new URL(`${backendUrl()}/v1/events`);
    params.forEach((value, key) => url.searchParams.set(key, value));
    try {
      const outcome = await readEventStream(
        url.toString(),
        options.signal,
        lastEventId,
        (envelope, id) => {
          if (id !== undefined) {
            lastEventId = id;
          }
          current = options.apply(current, envelope);
          if (current !== null) {
            options.onRecord(current);
          }
        },
      );
      if (outcome === "ended" || options.signal.aborted) {
        return;
      }
    } catch (error) {
      if (options.signal.aborted) {
        return;
      }
      const message = error instanceof Error ? error.message : String(error);
      if (message.includes("abort")) {
        return;
      }
    }
    await new Promise<void>((resolve) => {
      const timer = window.setTimeout(resolve, 1000);
      const cancel = () => {
        window.clearTimeout(timer);
        resolve();
      };
      options.signal.addEventListener("abort", cancel, { once: true });
    });
  }
}

export function applyConversationEvent(
  current: ChatConversation | null,
  envelope: RunStreamEnvelope,
): ChatConversation | null {
  const next = applyStreamEvent(current, envelope);
  if (next === null) {
    return null;
  }
  return next;
}

export function applyRunEvent(current: AgentRun | null, envelope: RunStreamEnvelope): AgentRun | null {
  return applyStreamEvent(current, envelope);
}
