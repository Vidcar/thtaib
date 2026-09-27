import { useChannelEffect, useMessages, useStream, useToolCalls, type AssembledToolCall } from "@langchain/react";
import type { Interrupt } from "@langchain/langgraph-sdk";
import type { BaseMessage } from "@langchain/core/messages";
import type React from "react";
import { useEffect, useMemo, useRef, useState } from "react";

import { createResumingInteractionTransport } from "./interactionResume";
import type { SchemaInteractionToolOrigin, SchemaWorkbenchInteractionMetadata } from "../generated/shared-contracts/openapi";
import type { AgentRun, PendingInterrupt, PendingInterruptAction } from "./types";

type WorkbenchInteractionMetadata = Omit<SchemaWorkbenchInteractionMetadata, "run"> & {
  run?: AgentRun | null;
};

export type WorkbenchToolOrigin = SchemaInteractionToolOrigin;

export function toolOriginIdentity(namespace: readonly string[], callId: string): string {
  return JSON.stringify([namespace, callId]);
}

export function toolOriginGeneration(origin: WorkbenchToolOrigin): string {
  return JSON.stringify([origin.run_id, origin.input_message_id ?? null, origin.namespace ?? [], origin.call_id]);
}

export interface WorkbenchInteractionValues {
  workbench?: WorkbenchInteractionMetadata;
  messages?: unknown[];
}

export type NativeInterruptValue =
  | PendingInterrupt
  | {
      pending_interrupt?: PendingInterrupt | null;
      action_requests?: PendingInterruptAction[];
      actionRequests?: PendingInterruptAction[];
      review_configs?: Array<{ action_name?: string; allowed_decisions?: string[]; allowedDecisions?: string[] }>;
      reviewConfigs?: Array<{ action_name?: string; allowed_decisions?: string[]; allowedDecisions?: string[] }>;
    };

export type WorkbenchInterrupt = NativeInterruptValue;

export type WorkbenchStream = ReturnType<typeof useStream<WorkbenchInteractionValues, WorkbenchInterrupt>>;

function interruptValue(interrupt: Interrupt<WorkbenchInterrupt> | undefined): PendingInterrupt | null {
  if (!interrupt?.value || typeof interrupt.value !== "object") {
    return null;
  }
  if ("kind" in interrupt.value && interrupt.value.kind === "browser_control") return null;
  if ("kind" in interrupt.value && interrupt.value.kind === "deepagents_interrupt_on") {
    return interrupt.value as PendingInterrupt;
  }
  if ("pending_interrupt" in interrupt.value && interrupt.value.pending_interrupt) {
    return interrupt.value.pending_interrupt.kind === "browser_control" ? null : interrupt.value.pending_interrupt;
  }
  const actionRequests =
    ("action_requests" in interrupt.value && interrupt.value.action_requests) ||
    ("actionRequests" in interrupt.value && interrupt.value.actionRequests);
  if (Array.isArray(actionRequests)) {
    return {
      kind: "deepagents_interrupt_on",
      environment: "windows_host_shell",
      isolation: "none",
      note: "Host shell command approval requested.",
      action_requests: actionRequests.map((action) => ({
        ...action,
        allowed_decisions: action.allowed_decisions ?? ["approve", "reject"],
      })),
    };
  }
  return null;
}

function runIsLive(run: AgentRun): boolean {
  return run.status === "queued" || run.status === "running" || run.status === "cancel_requested";
}

function sdkInterruptTarget(stream: WorkbenchStream): {
  id: string | undefined;
  namespace: string[];
  pending: PendingInterrupt;
} | null {
  const interrupt = stream.interrupts.find((item) => interruptValue(item));
  const pending = interruptValue(interrupt);
  if (!pending) {
    return null;
  }
  return {
    id: interrupt?.id,
    namespace: interrupt?.namespace ?? interrupt?.ns ?? [],
    pending,
  };
}

export function visibleApprovalInterrupt(stream: WorkbenchStream, authoritativeRun: AgentRun | null | undefined): {
  id: string | undefined;
  namespace: string[];
  pending: PendingInterrupt;
} | null {
  const sdk = sdkInterruptTarget(stream);
  if (!authoritativeRun) {
    return sdk;
  }
  if (!runIsLive(authoritativeRun) || !authoritativeRun.pending_interrupt || authoritativeRun.pending_interrupt.kind === "browser_control") {
    return null;
  }
  const interruptRunId = stream.values.workbench?.interrupt_run_id;
  if (interruptRunId && interruptRunId !== authoritativeRun.id) {
    return null;
  }
  if (!sdk) {
    return null;
  }
  return { ...sdk, pending: authoritativeRun.pending_interrupt };
}

export function useWorkbenchProjection(stream: WorkbenchStream): {
  run: AgentRun | null;
  workbench: WorkbenchInteractionValues["workbench"] | undefined;
  messages: BaseMessage[];
  toolCalls: AssembledToolCall[];
  toolCallOrigins: ReadonlyMap<string, string>;
  incompleteMessageIds: Set<string>;
} {
  const messages = useMessages(stream);
  const assembledToolCalls = useToolCalls(stream);
  const nativeOrigins = useRef(new Map<string, WorkbenchToolOrigin>());
  const confirmedOrigins = useRef(new Map<string, string>());
  const observationGeneration = useRef(0);
  const pendingStarts = useRef(new Map<string, object>());
  const observedThread = useRef(stream.threadId);
  const [, notifyOrigin] = useState(0);
  useEffect(() => () => { observationGeneration.current += 1; }, []);
  if (observedThread.current !== stream.threadId) {
    observedThread.current = stream.threadId;
    nativeOrigins.current = new Map();
    confirmedOrigins.current = new Map();
    pendingStarts.current = new Map();
    observationGeneration.current += 1;
  }
  const hydratedOrigins = new Map((stream.values.workbench?.tool_origins ?? []).map(origin => [toolOriginIdentity(origin.namespace ?? [], origin.call_id), origin]));
  for (const [identity, origin] of hydratedOrigins) {
    // Raw root events can be ahead of the coalesced values snapshot.
    if (!nativeOrigins.current.has(identity)) nativeOrigins.current.set(identity, origin);
  }
  useChannelEffect(stream, ["values", "tools"], { replay: false, bufferSize: 1, onEvent(event) {
    if (event.method === "values" && event.params.namespace.length === 0) {
      const data = event.params.data as WorkbenchInteractionValues;
      for (const origin of data.workbench?.tool_origins ?? []) nativeOrigins.current.set(toolOriginIdentity(origin.namespace ?? [], origin.call_id), origin);
      return;
    }
    if (event.method !== "tools") return;
    const data = event.params.data as { event?: string; tool_call_id?: string };
    if (data.event !== "tool-started" || !data.tool_call_id) return;
    const identity = toolOriginIdentity(event.params.namespace, data.tool_call_id);
    const origin = nativeOrigins.current.get(identity);
    if (!origin) return;
    const generation = observationGeneration.current;
    const originGeneration = toolOriginGeneration(origin);
    const startToken = {};
    pendingStarts.current.set(identity, startToken);
    // The SDK root bus runs before its tool assembler. Do not confirm the
    // new origin until that same event has replaced the retained old handle.
    confirmedOrigins.current = new Map(confirmedOrigins.current);
    confirmedOrigins.current.delete(identity);
    notifyOrigin(value => value + 1);
    queueMicrotask(() => {
      if (observationGeneration.current !== generation || pendingStarts.current.get(identity) !== startToken
        || toolOriginGeneration(nativeOrigins.current.get(identity) ?? origin) !== originGeneration) return;
      pendingStarts.current.delete(identity);
      confirmedOrigins.current = new Map(confirmedOrigins.current).set(identity, originGeneration);
      notifyOrigin(value => value + 1);
    });
  } });
  // The SDK root pump includes depth-one tool events for helper discovery.
  // This backend emits parent tools at root; tools:/task: branches belong only
  // to their scoped helper transcript, just like the SDK's message projection.
  const toolCalls = useMemo(() => assembledToolCalls.filter(call =>
    !(call.namespace ?? []).some(part => part.startsWith("tools:") || part.startsWith("task:"))), [assembledToolCalls]);
  const incompleteKey = (stream.values.workbench?.incomplete_message_ids ?? []).join("\0");
  const incompleteMessageIds = useMemo(
    () => new Set(stream.values.workbench?.incomplete_message_ids ?? []),
    [incompleteKey],
  );
  return {
    run: stream.values.workbench?.run ?? null,
    workbench: stream.values.workbench,
    messages,
    toolCalls,
    toolCallOrigins: confirmedOrigins.current,
    incompleteMessageIds,
  };
}

export function InteractionStream(props: {
  threadId: string;
  children: (stream: WorkbenchStream) => React.ReactNode;
  onError?: (error: unknown) => void;
}) {
  const { threadId, children, onError } = props;
  const transport = useMemo(() => createResumingInteractionTransport(threadId), [threadId]);
  const stream = useStream<WorkbenchInteractionValues, WorkbenchInterrupt>({
    transport,
    threadId,
    optimistic: true,
  });

  useEffect(() => {
    if (stream.error) {
      onError?.(stream.error);
    }
  }, [onError, stream.error]);

  const recovery = stream.values.workbench?.recovery;

  return (
    <>
      {recovery ? (
        <div className="notice" role="status">
          {recovery.message}
        </div>
      ) : null}
      {children(stream)}
    </>
  );
}
