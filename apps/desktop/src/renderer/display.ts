import { isAgentRunLive } from "./types";
import type { ChatConversation, ChatMessage, Deployment, PendingInterruptAction } from "./types";

export function formatWhen(iso: string | null | undefined): string {
  if (!iso) {
    return "";
  }
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) {
    return iso;
  }
  return date.toLocaleString();
}

export function formatBytes(bytes: number | null | undefined): string {
  if (bytes == null || !Number.isFinite(bytes)) {
    return "unknown size";
  }
  if (bytes < 1024) {
    return `${bytes} B`;
  }
  if (bytes < 1024 * 1024) {
    return `${(bytes / 1024).toFixed(1)} KB`;
  }
  if (bytes < 1024 * 1024 * 1024) {
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  }
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`;
}

export function conversationTitle(conversation: ChatConversation): string {
  const firstUser = conversation.transcript.find((item) => item.role === "user" && item.content.trim());
  if (!firstUser) {
    return "New conversation";
  }
  const text = firstUser.content.trim().replace(/\s+/g, " ");
  return text.length > 52 ? `${text.slice(0, 51)}…` : text;
}

function detailText(value: unknown): string | null {
  if (typeof value === "string" && value.trim()) {
    return value;
  }
  return null;
}

export function displayedTranscript(conversation: ChatConversation): ChatMessage[] {
  const messages = [...conversation.transcript];
  const run = conversation.current_run;
  if (!run || !isAgentRunLive(run.status)) {
    return messages;
  }
  if (messages.some((item) => item.run_id === run.id && item.role === "assistant")) {
    return messages;
  }
  let latest: string | null = null;
  let at = run.events.at(-1)?.at ?? new Date().toISOString();
  for (const event of run.events) {
    if (event.kind !== "assistant_message") {
      continue;
    }
    const content = detailText(event.detail.content);
    if (content) {
      latest = content;
      at = event.at;
    }
  }
  if (!latest) {
    return messages;
  }
  return [
    ...messages,
    {
      role: "assistant",
      content: latest,
      at,
      run_id: run.id,
    },
  ];
}

export function interruptCommand(action: PendingInterruptAction): string | null {
  const command = action.args.command ?? action.args.cmd ?? action.args.command_line;
  return typeof command === "string" && command.trim() ? command : null;
}

export function shortId(id: string): string {
  if (id.length <= 16) {
    return id;
  }
  return `${id.slice(0, 10)}…`;
}

export function deploymentOptionLabel(deployment: Deployment): string {
  const name = deployment.display_name.replace(/^(managed|connected):/, "");
  const status = deployment.status === "running" ? "Ready" : deployment.status === "starting" ? "Loading" : deployment.status === "stopped" ? "Stopped" : "Not ready";
  const role = String(deployment.applied_startup?.embedding ?? "").toLowerCase() === "on" ? " · Document search" : "";
  return `${name} · ${status}${role}`;
}

export function relatedFileLabel(kind: "project_root" | "written_file" | "artifact"): string {
  switch (kind) {
    case "project_root":
      return "Project folder";
    case "written_file":
      return "Written file";
    case "artifact":
      return "Artifact";
    default: {
      const unexpected: never = kind;
      return unexpected;
    }
  }
}

export function eventDetailSummary(kind: string, detail: Record<string, unknown>): string {
  const name = typeof detail.name === "string" ? detail.name : null;
  const command = typeof detail.command === "string" ? detail.command : null;
  const content = detailText(detail.content);
  const error = detailText(detail.error);
  switch (kind) {
    case "tool_call":
      return name ? (command ? `${name}: ${command}` : name) : "Tool";
    case "tool_result":
      if (name && content) {
        const clipped = content.length > 140 ? `${content.slice(0, 139)}…` : content;
        return `${name} → ${clipped}`;
      }
      return name ?? "Result";
    case "assistant_message":
      return content ? (content.length > 160 ? `${content.slice(0, 159)}…` : content) : "Reply";
    case "failed":
    case "recorded_replay_failed":
      return error ?? "Failed";
    default:
      if (name) {
        return name;
      }
      if (error) {
        return error;
      }
      return "";
  }
}
