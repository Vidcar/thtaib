import type {
  AgentRunStatus,
  KnowledgeActor,
  KnowledgeKind,
  KnowledgeScope,
  RedactionMode,
} from "./types";

export function runStatusLabel(status: AgentRunStatus): string {
  switch (status) {
    case "queued":
      return "Queued";
    case "running":
      return "Running";
    case "cancel_requested":
      return "Stopping…";
    case "cancelled":
      return "Cancelled";
    case "completed":
      return "Completed";
    case "failed":
      return "Failed";
    default: {
      const unexpected: never = status;
      return unexpected;
    }
  }
}

export function runStatusTone(status: AgentRunStatus): "neutral" | "live" | "ok" | "warn" | "danger" {
  switch (status) {
    case "queued":
      return "neutral";
    case "running":
      return "live";
    case "cancel_requested":
      return "warn";
    case "cancelled":
      return "warn";
    case "completed":
      return "ok";
    case "failed":
      return "danger";
    default: {
      const unexpected: never = status;
      return unexpected;
    }
  }
}

export function knowledgeKindLabel(kind: KnowledgeKind): string {
  switch (kind) {
    case "memory":
      return "Memory";
    case "skill":
      return "Skill";
    case "protected_instruction":
      return "Protected instruction";
    default: {
      const unexpected: never = kind;
      return unexpected;
    }
  }
}

export function knowledgeScopeLabel(scope: KnowledgeScope): string {
  switch (scope) {
    case "user":
      return "User";
    case "agent":
      return "Agent";
    case "project":
      return "Project";
    default: {
      const unexpected: never = scope;
      return unexpected;
    }
  }
}

export function knowledgeActorLabel(actor: KnowledgeActor): string {
  switch (actor) {
    case "human":
      return "You";
    case "api_maintainer":
      return "Maintainer";
    case "agent":
      return "Agent";
    default: {
      const unexpected: never = actor;
      return unexpected;
    }
  }
}

export function redactionModeLabel(mode: RedactionMode): string {
  switch (mode) {
    case "redact_secrets":
      return "Redact secrets";
    case "retain":
      return "Keep original text";
    case "discard":
      return "Discard";
    default: {
      const unexpected: never = mode;
      return unexpected;
    }
  }
}

export function eventKindLabel(kind: string): string {
  switch (kind) {
    case "started":
      return "Started";
    case "tool_call":
      return "Tool call";
    case "tool_result":
      return "Tool result";
    case "assistant_message":
      return "Reply";
    case "interrupt":
      return "Needs approval";
    case "interrupt_resolved":
      return "Decision recorded";
    case "cancel_requested":
      return "Cancel requested";
    case "cancelled":
      return "Cancelled";
    case "completed":
      return "Completed";
    case "failed":
      return "Failed";
    case "queued":
      return "Queued";
    case "running":
      return "Running";
    case "recorded_replay_failed":
      return "Replay failed";
    case "recorded_reconstruction":
      return "Replay reconstruction";
    case "recorded_reconstruction_note":
      return "Replay note";
    default:
      return kind.replaceAll("_", " ");
  }
}

export function deploymentHealthLabel(healthy: boolean | null | undefined): string {
  if (healthy === true) {
    return "Healthy";
  }
  if (healthy === false) {
    return "Unhealthy";
  }
  return "Health unknown";
}
