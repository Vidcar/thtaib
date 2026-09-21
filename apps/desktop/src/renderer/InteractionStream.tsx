import { HttpAgentServerAdapter, useMessages, useStream, useToolCalls, type AssembledToolCall } from "@langchain/react";
import type { Interrupt } from "@langchain/langgraph-sdk";
import type { BaseMessage } from "@langchain/core/messages";
import type React from "react";
import { useEffect, useMemo } from "react";

import { backendUrl } from "./api";
import type { SchemaWorkbenchInteractionMetadata } from "../generated/shared-contracts/openapi";
import type { AgentRun, PendingInterrupt, PendingInterruptAction } from "./types";

type WorkbenchInteractionMetadata = Omit<SchemaWorkbenchInteractionMetadata, "run"> & {
  run?: AgentRun | null;
};

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
  if ("kind" in interrupt.value && (interrupt.value.kind === "deepagents_interrupt_on" || interrupt.value.kind === "ask_user")) {
    return interrupt.value as PendingInterrupt;
  }
  if ("pending_interrupt" in interrupt.value && interrupt.value.pending_interrupt) {
    return interrupt.value.pending_interrupt;
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
  if (!runIsLive(authoritativeRun) || !authoritativeRun.pending_interrupt) {
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
  incompleteMessageIds: Set<string>;
} {
  const messages = useMessages(stream);
  const toolCalls = useToolCalls(stream);
  return {
    run: stream.values.workbench?.run ?? null,
    workbench: stream.values.workbench,
    messages,
    toolCalls,
    incompleteMessageIds: new Set(stream.values.workbench?.incomplete_message_ids ?? []),
  };
}

export function InteractionStream(props: {
  threadId: string;
  children: (stream: WorkbenchStream) => React.ReactNode;
  onError?: (error: unknown) => void;
}) {
  const { threadId, children, onError } = props;
  const transport = useMemo(
    () => new HttpAgentServerAdapter({ apiUrl: `${backendUrl()}/v1/agent-interaction`, threadId }),
    [threadId],
  );
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
