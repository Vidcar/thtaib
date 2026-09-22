import { useEffect, useMemo, useState } from "react";

import "./ChatHistoryActions.css";
import {
  chatHistoryActionsApi,
  type ChatBranchMode,
  type ChatReplyActions,
  type ConversationDeletePreview,
  type ConversationExportPayload,
} from "./chatHistoryActionsApi";
import { conversationTitle, formatWhen } from "./display";
import { Icon, type IconName } from "./Icon";
import type { ChatConversation } from "./types";

export interface ChatHistoryActionsProps {
  conversation: ChatConversation;
  onConversationCreated: (next: ChatConversation) => void;
  onDeleted: (id: string) => void;
  onError: (message: string) => void;
  disabled?: boolean;
}

type BusyAction = "branch" | "retry" | "regenerate" | "export" | "preview-delete" | "delete" | null;

interface ActionOption {
  runId: string;
  label: string;
  detail: string;
  task: string;
}

export function ChatHistoryActions({
  conversation,
  onConversationCreated,
  onDeleted,
  onError,
  disabled = false,
}: ChatHistoryActionsProps) {
  const options = useMemo(() => actionOptions(conversation), [conversation]);
  const [selectedRunId, setSelectedRunId] = useState<string>(() => options.at(-1)?.runId ?? "");
  const [actions, setActions] = useState<ChatReplyActions | null>(null);
  const [actionsError, setActionsError] = useState<string | null>(null);
  const [busy, setBusy] = useState<BusyAction>(null);
  const [deletePreview, setDeletePreview] = useState<ConversationDeletePreview | null>(null);
  const [includeDiagnostics, setIncludeDiagnostics] = useState(false);
  const [editedTask, setEditedTask] = useState("");

  useEffect(() => {
    const fallback = options.at(-1)?.runId ?? "";
    if (!selectedRunId || !options.some((item) => item.runId === selectedRunId)) {
      setSelectedRunId(fallback);
    }
  }, [options, selectedRunId]);

  useEffect(() => {
    let cancelled = false;
    setDeletePreview(null);
    if (!selectedRunId) {
      setActions(null);
      setActionsError(null);
      return;
    }
    setActions(null);
    setActionsError(null);
    chatHistoryActionsApi.replyActions(conversation.id, selectedRunId)
      .then((next) => {
        if (!cancelled) {
          setActions(next);
        }
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          setActionsError(messageOf(error));
        }
      });
    return () => {
      cancelled = true;
    };
  }, [conversation.id, conversation.current_run_id, conversation.current_run?.status, selectedRunId]);

  const selectedOption = options.find((item) => item.runId === selectedRunId) ?? null;
  const projectStateSupported = Boolean(conversation.project_path || conversation.area_project_path || conversation.workspace_id || conversation.area_workspace_id);
  const blocked = disabled || busy !== null;

  async function runAction(mode: ChatBranchMode): Promise<void> {
    if (!selectedRunId) {
      return;
    }
    if (mode === "retry") {
      const accepted = window.confirm(
        "Retry task may repeat file changes, shell commands or other external effects from this point. Continue only if repeating those effects is acceptable.",
      );
      if (!accepted) {
        return;
      }
    }
    const trimmedEdit = editedTask.trim();
    if (mode === "edit" && !trimmedEdit) {
      onError("Enter the edited task before creating an edit branch.");
      return;
    }
    if (mode === "edit") {
      const accepted = window.confirm("Create a retry branch with your edited task? This prepares the new attempt without changing the original conversation.");
      if (!accepted) {
        return;
      }
    }
    const key = mode === "regenerate" ? "regenerate" : mode === "retry" ? "retry" : "branch";
    setBusy(key);
    try {
      const next = await chatHistoryActionsApi.createBranch(conversation.id, selectedRunId, mode, mode === "retry" || mode === "edit", mode === "edit" ? trimmedEdit : undefined);
      onConversationCreated(next);
    } catch (error) {
      onError(messageOf(error));
    } finally {
      setBusy(null);
    }
  }

  async function exportConversation(): Promise<void> {
    setBusy("export");
    try {
      const payload = await chatHistoryActionsApi.exportConversation(conversation.id);
      downloadText(readableMarkdownExport(payload), `${safeFilename(conversationTitle(conversation))}.md`, "text/markdown");
    } catch (error) {
      onError(messageOf(error));
    } finally {
      setBusy(null);
    }
  }

  async function previewDelete(): Promise<void> {
    setBusy("preview-delete");
    try {
      setDeletePreview(await chatHistoryActionsApi.deletePreview(conversation.id));
    } catch (error) {
      onError(messageOf(error));
    } finally {
      setBusy(null);
    }
  }

  async function confirmDelete(): Promise<void> {
    if (!deletePreview) {
      return;
    }
    const confirmed = window.confirm(
      `Delete ${conversationTitle(conversation)} from Local AI Workbench? Project files, model files and backups are retained.`,
    );
    if (!confirmed) {
      return;
    }
    setBusy("delete");
    try {
      const result = await chatHistoryActionsApi.deleteConversation(conversation.id, includeDiagnostics);
      if (!result.can_delete && result.blockers.length) {
        setDeletePreview(result);
        onError("Conversation still has live work and cannot be deleted yet.");
        return;
      }
      onDeleted(conversation.id);
    } catch (error) {
      onError(messageOf(error));
    } finally {
      setBusy(null);
    }
  }

  return (
    <section className="chat-history-actions" aria-label="Conversation history actions">
      <div className="chat-history-actions-head">
        <div>
          <p className="chat-history-actions-kicker">History</p>
          <h3>Branch, retry, export or delete</h3>
        </div>
        <span className="chat-history-actions-badge">{options.length ? `${options.length} saved ${options.length === 1 ? "turn" : "turns"}` : "No saved turns"}</span>
      </div>

      <label className="chat-history-actions-field">
        <span>Saved checkpoint</span>
        <select value={selectedRunId} disabled={blocked || options.length === 0} onChange={(event) => setSelectedRunId(event.target.value)}>
          {options.length === 0 ? <option value="">No saved turns yet</option> : null}
          {options.map((reply) => (
            <option key={reply.runId} value={reply.runId}>{reply.label}</option>
          ))}
        </select>
      </label>
      {selectedOption ? <p className="chat-history-actions-hint">{selectedOption.detail}</p> : <p className="chat-history-actions-hint">Actions become available after a saved turn has a backend action boundary.</p>}
      {actionsError ? <p className="chat-history-actions-error">Could not load checkpoint actions: {actionsError}</p> : null}
      <label className="chat-history-actions-field">
        <span>Edit task and branch</span>
        <textarea
          value={editedTask}
          disabled={blocked || !selectedRunId || !actions?.retry_available}
          rows={3}
          placeholder={selectedOption?.task || "Write the revised task for a retry branch."}
          onChange={(event) => setEditedTask(event.target.value)}
        />
      </label>

      <div className="chat-history-action-grid">
        <HistoryActionButton
          icon="folder"
          title={projectStateSupported ? "Branch workspace" : "Branch chat"}
          description={projectStateSupported ? "Restore a supported project-state branch from this checkpoint." : "Start a separate conversation from this checkpoint."}
          disabled={blocked || !selectedRunId || !actions?.branch_available}
          unavailableReason={actions?.branch_reason ?? null}
          busy={busy === "branch"}
          onClick={() => void runAction("continue")}
        />
        <HistoryActionButton
          icon="activity"
          title="Retry task"
          description="Repeat the task from the prior safe boundary after confirmation. Effects may repeat."
          disabled={blocked || !selectedRunId || !actions?.retry_available}
          unavailableReason={actions?.retry_reason ?? null}
          busy={busy === "retry"}
          onClick={() => void runAction("retry")}
        />
        <HistoryActionButton
          icon="edit"
          title="Edit task branch"
          description="Prepare a branch with the revised task text. The original stays unchanged."
          disabled={blocked || !selectedRunId || !actions?.retry_available || !editedTask.trim()}
          unavailableReason={actions?.retry_reason ?? null}
          busy={busy === "retry"}
          onClick={() => void runAction("edit")}
        />
        <HistoryActionButton
          icon="chevron"
          title="Regenerate answer"
          description="Answer-only regeneration with tools disabled when the backend has a supported checkpoint."
          disabled={blocked || !selectedRunId || !actions?.regenerate_available}
          unavailableReason={actions?.regenerate_reason ?? null}
          busy={busy === "regenerate"}
          onClick={() => void runAction("regenerate")}
        />
        <HistoryActionButton
          icon="files"
          title="Readable export"
          description="Download a readable Markdown transcript. It is not a restore backup."
          disabled={blocked}
          unavailableReason={null}
          busy={busy === "export"}
          onClick={() => void exportConversation()}
        />
        <HistoryActionButton
          icon="panel"
          title="Advanced JSON export"
          description="Download the structured export for troubleshooting or support."
          disabled={blocked}
          unavailableReason={null}
          busy={busy === "export"}
          onClick={() => void exportJsonConversation(conversation)}
        />
        <HistoryActionButton
          icon="close"
          title="Preview delete"
          description="Review dependent runs, assets, checkpoints and blockers before deleting application-owned records."
          disabled={blocked}
          unavailableReason={null}
          busy={busy === "preview-delete"}
          onClick={() => void previewDelete()}
        />
      </div>

      {deletePreview ? (
        <div className={deletePreview.can_delete ? "chat-delete-preview" : "chat-delete-preview blocked"}>
          <div>
            <strong>{deletePreview.can_delete ? "Ready to delete" : "Delete blocked"}</strong>
            <p>{deleteSummary(deletePreview)}</p>
            <p className="chat-history-actions-hint">{deletePreview.note}</p>
          </div>
          {deletePreview.blockers.length ? (
            <ul>
              {deletePreview.blockers.map((blocker, index) => (
                <li key={`${blocker.kind ?? "blocker"}-${blocker.id ?? index}`}>{blocker.kind ?? "blocker"} {blocker.id ?? "unknown"} is {blocker.status ?? "active"}</li>
              ))}
            </ul>
          ) : null}
          <label className="chat-history-actions-check">
            <input type="checkbox" checked={includeDiagnostics} disabled={blocked} onChange={(event) => setIncludeDiagnostics(event.target.checked)} />
            <span>Also delete retained diagnostics for this conversation</span>
          </label>
          <button type="button" className="chat-history-danger" disabled={blocked || !deletePreview.can_delete} onClick={() => void confirmDelete()}>
            {busy === "delete" ? "Deleting..." : "Delete conversation"}
          </button>
        </div>
      ) : null}
    </section>
  );
}

function HistoryActionButton(props: {
  icon: IconName;
  title: string;
  description: string;
  disabled: boolean;
  unavailableReason: string | null;
  busy: boolean;
  onClick: () => void;
}) {
  const disabled = props.disabled || props.busy;
  return (
    <button type="button" className="chat-history-action" disabled={disabled} onClick={props.onClick} title={props.unavailableReason ?? props.description}>
      <Icon name={props.icon} size={18} />
      <span>
        <strong>{props.busy ? "Working..." : props.title}</strong>
        <small>{props.unavailableReason ?? props.description}</small>
      </span>
    </button>
  );
}

async function exportJsonConversation(conversation: ChatConversation): Promise<void> {
  const payload = await chatHistoryActionsApi.exportConversation(conversation.id);
  downloadText(JSON.stringify(payload, null, 2), `${safeFilename(conversationTitle(conversation))}-structured.json`, "application/json");
}

function actionOptions(conversation: ChatConversation): ActionOption[] {
  return conversation.run_ids.map((runId) => {
    const user = conversation.transcript.find((message) => message.role === "user" && message.run_id === runId);
    const assistant = conversation.transcript.find((message) => message.role === "assistant" && message.run_id === runId);
    const when = assistant?.at ?? user?.at ?? conversation.updated_at;
    const text = assistant?.content || user?.content || "Saved turn";
    return {
      runId,
      label: `${formatWhen(when)} - ${firstLine(text)}`,
      detail: `${assistant ? "Reply saved" : "No assistant reply saved"} - ${formatWhen(when)}`,
      task: user?.content ?? "",
    };
  }).filter((item, index, all) => all.findIndex((candidate) => candidate.runId === item.runId) === index);
}

function firstLine(value: string): string {
  const line = value.split(/\r?\n/).find((item) => item.trim());
  if (!line) {
    return "Saved assistant reply";
  }
  return line.length > 96 ? `${line.slice(0, 95)}...` : line;
}

function messageOf(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

function safeFilename(title: string): string {
  const cleaned = title.replace(/[^a-z0-9._-]+/gi, "-").replace(/^-+|-+$/g, "").slice(0, 80);
  return cleaned || "conversation";
}

function downloadText(text: string, filename: string, contentType: string): void {
  const blob = new Blob([text], { type: contentType });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

function readableMarkdownExport(payload: ConversationExportPayload): string {
  const conversation = payload.conversation as {
    title?: string | null;
    transcript?: Array<{ role?: string; content?: string; at?: string; run_id?: string | null }>;
    area_label?: string | null;
    area_project_path?: string | null;
  };
  const title = conversation.title?.trim() || "Conversation export";
  const lines = [
    `# ${title}`,
    "",
    `Exported: ${formatWhen(payload.exported_at)}`,
    conversation.area_label || conversation.area_project_path ? `Area: ${conversation.area_label || conversation.area_project_path}` : "",
    "",
    "> Readable export only. It is not a restore backup and does not include model files or project source files.",
    "",
  ].filter((line) => line !== "");
  for (const message of conversation.transcript ?? []) {
    const speaker = message.role === "assistant" ? "Assistant" : message.role === "user" ? "You" : "System";
    lines.push(`## ${speaker}${message.at ? ` - ${formatWhen(message.at)}` : ""}`);
    lines.push("");
    lines.push(message.content?.trim() || "_No text content._");
    lines.push("");
  }
  if (!(conversation.transcript ?? []).length) {
    lines.push("_No messages were saved in this conversation._");
    lines.push("");
  }
  if (payload.retained_assets.length) {
    lines.push("## Retained files");
    lines.push("");
    for (const asset of payload.retained_assets) {
      const filename = typeof asset.filename === "string" ? asset.filename : "retained file";
      lines.push(`- ${filename}`);
    }
    lines.push("");
  }
  return `${lines.join("\n").trim()}\n`;
}

function deleteSummary(preview: ConversationDeletePreview): string {
  const pieces = [
    `${preview.affected_runs.length} run${preview.affected_runs.length === 1 ? "" : "s"}`,
    `${preview.affected_assets.length} retained asset${preview.affected_assets.length === 1 ? "" : "s"}`,
    `${preview.checkpoint_threads_deleted.length} checkpoint thread${preview.checkpoint_threads_deleted.length === 1 ? "" : "s"}`,
  ];
  const retained = preview.retained_runs.length + preview.retained_assets.length + preview.checkpoint_threads_retained.length;
  return `${pieces.join(", ")} will be removed. ${retained} shared ${retained === 1 ? "dependency is" : "dependencies are"} retained. Project files and model files are retained.`;
}
