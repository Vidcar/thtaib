import { useEffect, useState } from "react";

import { ChatModelControls } from "./ChatModelControls";
import { ComposerAttachments } from "./ComposerAttachments";
import { packet03Request } from "./packet03Api";
import { isAgentRunLive, type ChatConversation, type ChatQueueItem, type Deployment, type RunProfile } from "./types";
import "./ChatQueuePanel.css";

interface ChatQueuePanelProps {
  conversation: ChatConversation;
  deployments: Deployment[];
  profiles: RunProfile[];
  disabled?: boolean;
  onUpdated: (next: ChatConversation) => void;
  onError: (message: string) => void;
}

interface QueueDraft {
  task: string;
  attachmentIds: string[];
  deploymentId: string;
  profileId: string;
  inheritDeploymentSettings: boolean;
  perRequestOverrides: Record<string, unknown>;
  dirty: boolean;
}

const EMPTY_QUEUE: ChatQueueItem[] = [];

export function ChatQueuePanel({ conversation, deployments, profiles, disabled = false, onUpdated, onError }: ChatQueuePanelProps) {
  const queue = conversation.queue ?? EMPTY_QUEUE;
  const [drafts, setDrafts] = useState<Record<string, QueueDraft>>({});
  const [busyItemId, setBusyItemId] = useState<string | null>(null);
  const [continueBusy, setContinueBusy] = useState(false);
  const [ackUncertain, setAckUncertain] = useState(false);

  useEffect(() => {
    setDrafts((current) => {
      const next: Record<string, QueueDraft> = {};
      for (const item of queue) {
        next[item.id] = current[item.id]?.dirty ? current[item.id] : draftFromQueueItem(item, conversation);
      }
      return next;
    });
  }, [conversation.id, queue]);

  const paused = queue.filter((item) => item.status === "paused");
  const hasDispatchUncertain = paused.some((item) => item.pause_reason === "dispatch_uncertain");
  const runActive = Boolean(conversation.current_run && isAgentRunLive(conversation.current_run.status)) || Boolean(conversation.pending_cancel_input_ids?.length);
  const itemBusy = busyItemId !== null;

  if (queue.length === 0) {
    return null;
  }

  async function updateQueueItem(item: ChatQueueItem): Promise<void> {
    const draft = drafts[item.id] ?? draftFromQueueItem(item, conversation);
    const locked = isQueueItemLocked(item);
    if (locked || disabled || itemBusy || !hasSendableContent(draft)) {
      return;
    }
    setBusyItemId(item.id);
    try {
      const next = await packet03Request<ChatConversation>(queueItemPath(conversation.id, item.id), {
        method: "PATCH",
        body: JSON.stringify({
          task: draft.task.trim(),
          attachment_ids: draft.attachmentIds,
          intended_config: intendedConfigFromDraft(draft),
        }),
      });
      setDrafts((current) => ({ ...current, [item.id]: { ...draftFromQueueItem(next.queue?.find((entry) => entry.id === item.id) ?? item, next), dirty: false } }));
      onUpdated(next);
    } catch (error) {
      onError(errorMessage(error));
    } finally {
      setBusyItemId(null);
    }
  }

  async function removeQueueItem(item: ChatQueueItem): Promise<void> {
    if (isQueueItemLocked(item) || disabled || itemBusy) {
      return;
    }
    setBusyItemId(item.id);
    try {
      const next = await packet03Request<ChatConversation>(queueItemPath(conversation.id, item.id), { method: "DELETE" });
      onUpdated(next);
    } catch (error) {
      onError(errorMessage(error));
    } finally {
      setBusyItemId(null);
    }
  }

  async function continueQueue(): Promise<void> {
    if (disabled || continueBusy || runActive || (hasDispatchUncertain && !ackUncertain)) {
      return;
    }
    setContinueBusy(true);
    try {
      const next = await packet03Request<ChatConversation>(`/v1/chat/conversations/${encodeURIComponent(conversation.id)}/queue/resume`, {
        method: "POST",
        body: JSON.stringify({
          resume_paused: true,
          acknowledge_uncertain_effects: hasDispatchUncertain,
        }),
      });
      setAckUncertain(false);
      onUpdated(next);
    } catch (error) {
      onError(errorMessage(error));
    } finally {
      setContinueBusy(false);
    }
  }

  return (
    <details className="chat-queue-panel" open>
      <summary>
        <span>Queue</span>
        <span className="badge">{queue.length} turn{queue.length === 1 ? "" : "s"}</span>
      </summary>

      {paused.length ? (
        <section className="notice notice-warn" aria-label="Paused queue">
          <strong>Queue paused</strong>
          <p>{hasDispatchUncertain ? "A previous dispatch may have had external effects. Review the queued work before continuing." : "Review the paused item before continuing."}</p>
          {hasDispatchUncertain ? (
            <label className="check-row">
              <input
                type="checkbox"
                checked={ackUncertain}
                disabled={disabled || continueBusy}
                onChange={(event) => setAckUncertain(event.target.checked)}
              />
              I understand continuing may repeat earlier effects.
            </label>
          ) : null}
          <div className="chat-queue-continue">
            <button type="button" disabled={disabled || continueBusy || runActive || (hasDispatchUncertain && !ackUncertain)} onClick={() => void continueQueue()}>
              {continueBusy ? "Continuing..." : "Continue queue"}
            </button>
            {runActive ? <p className="hint">Continue is available after the live turn or pending cancellation finishes. You can still edit queued items now.</p> : null}
          </div>
        </section>
      ) : null}

      <ol className="chat-queue-list">
        {queue.map((item, index) => {
          const draft = drafts[item.id] ?? draftFromQueueItem(item, conversation);
          const locked = isQueueItemLocked(item);
          const savingThisItem = busyItemId === item.id;
          const itemDisabled = disabled || itemBusy || locked;
          return (
            <li key={item.id} className={locked ? "chat-queue-item is-locked" : "chat-queue-item"}>
              <div className="chat-queue-item-head">
                <div>
                  <strong>Queued turn {index + 1}</strong>
                  <p className="chat-queue-preview">{draft.task.trim() || (draft.attachmentIds.length ? "Attachment-only queued turn" : "Empty queued turn")}</p>
                </div>
                <div className="chat-queue-status">
                  <span className="badge">{queueStatusLabel(item)}</span>
                  {item.frozen_config ? <span className="badge">Captured setup</span> : null}
                </div>
              </div>
              {item.pause_error ? <p className="notice notice-error">{item.pause_error}</p> : null}
              {item.pause_reason ? <p className="hint">{pauseReasonLabel(item)}</p> : null}
              {item.frozen_config ? <p className="chat-queue-frozen-config">{frozenConfigLabel(item)}</p> : null}

              <details className="chat-queue-edit">
                <summary>{locked ? "View queued turn" : "Edit queued turn"}</summary>
                <div className="chat-queue-editor">
                  <label>
                    Message
                    <textarea
                      value={draft.task}
                      disabled={itemDisabled}
                      onChange={(event) => updateDraft(item.id, { task: event.target.value })}
                    />
                  </label>
                  <ComposerAttachments
                    sessionId={conversation.id}
                    attachmentIds={draft.attachmentIds}
                    disabled={itemDisabled}
                    onAttachmentsChanged={(attachments) => {
                      const nextIds = attachments.map((attachment) => attachment.id);
                      if (!sameStrings(nextIds, draft.attachmentIds)) {
                        updateDraft(item.id, { attachmentIds: nextIds });
                      }
                    }}
                  />
                  <p className="chat-queue-attachment-summary">
                    {draft.attachmentIds.length
                      ? `${draft.attachmentIds.length} attachment${draft.attachmentIds.length === 1 ? "" : "s"} staged for this queued turn.`
                      : "No attachments staged for this queued turn."}
                  </p>
                  <ChatModelControls
                    deployments={deployments}
                    profiles={profiles}
                    selectedDeploymentId={draft.deploymentId}
                    selectedProfileId={draft.profileId}
                    inheritDeploymentSettings={draft.inheritDeploymentSettings}
                    perRequestOverrides={draft.perRequestOverrides}
                    disabled={itemDisabled}
                    locked={locked}
                    onDeploymentChange={(deploymentId) => updateDraft(item.id, { deploymentId })}
                    onProfileChange={(profileId) => updateDraft(item.id, { profileId })}
                    onInheritDeploymentSettingsChange={(inheritDeploymentSettings) => updateDraft(item.id, { inheritDeploymentSettings })}
                    onPerRequestOverridesChange={(perRequestOverrides) => updateDraft(item.id, { perRequestOverrides })}
                  />
                </div>

                <div className="chat-queue-actions">
                  <button type="button" disabled={itemDisabled || !draft.dirty || !hasSendableContent(draft)} onClick={() => void updateQueueItem(item)}>
                    {savingThisItem ? "Saving..." : "Save queued turn"}
                  </button>
                  <button
                    type="button"
                    className="chat-queue-danger"
                    disabled={itemDisabled}
                    onClick={() => void removeQueueItem(item)}
                  >
                    Remove queued turn
                  </button>
                </div>
              </details>
            </li>
          );
        })}
      </ol>
    </details>
  );

  function updateDraft(itemId: string, patch: Partial<Omit<QueueDraft, "dirty">>): void {
    setDrafts((current) => {
      const item = queue.find((entry) => entry.id === itemId);
      const base = current[itemId] ?? (item ? draftFromQueueItem(item, conversation) : null);
      if (!base) {
        return current;
      }
      return {
        ...current,
        [itemId]: {
          ...base,
          ...patch,
          dirty: true,
        },
      };
    });
  }
}

function draftFromQueueItem(item: ChatQueueItem, conversation: ChatConversation): QueueDraft {
  const config = (item.frozen_config ?? item.intended_config ?? {}) as Record<string, unknown>;
  const profile = typeof config.profile_id === "string" ? config.profile_id : config.profile_id === null ? "!none" : conversation.profile_id ?? "";
  return {
    task: item.task,
    attachmentIds: [...(item.attachment_ids ?? [])],
    deploymentId: typeof config.deployment_id === "string" ? config.deployment_id : conversation.deployment_id,
    profileId: profile,
    inheritDeploymentSettings: typeof config.inherit_deployment_settings === "boolean" ? config.inherit_deployment_settings : profile !== "!none",
    perRequestOverrides: objectRecord(config.per_request_overrides),
    dirty: false,
  };
}

function intendedConfigFromDraft(draft: QueueDraft): Record<string, unknown> {
  return {
    deployment_id: draft.deploymentId,
    profile_id: draft.profileId && draft.profileId !== "!none" ? draft.profileId : null,
    inherit_deployment_settings: draft.inheritDeploymentSettings,
    per_request_overrides: draft.perRequestOverrides,
  };
}

function objectRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
}

function sameStrings(left: string[], right: string[]): boolean {
  return left.length === right.length && left.every((item, index) => item === right[index]);
}

function isQueueItemLocked(item: ChatQueueItem): boolean {
  return item.status === "dispatching";
}

function hasSendableContent(draft: QueueDraft): boolean {
  return Boolean(draft.task.trim() || draft.attachmentIds.length);
}

function queueItemPath(conversationId: string, itemId: string): string {
  return `/v1/chat/conversations/${encodeURIComponent(conversationId)}/queue/${encodeURIComponent(itemId)}`;
}

function queueStatusLabel(item: ChatQueueItem): string {
  if (item.status === "dispatching") return "Running";
  if (item.status === "paused") return "Paused";
  return "Queued";
}

function pauseReasonLabel(item: ChatQueueItem): string {
  if (item.pause_reason === "dispatch_uncertain") {
    return "Paused because the last dispatch had uncertain effects.";
  }
  if (item.pause_reason === "cancelled") {
    return "Paused after cancellation.";
  }
  if (item.pause_reason === "failed") {
    return "Paused after a failed turn.";
  }
  return "Paused.";
}

function frozenConfigLabel(item: ChatQueueItem): string {
  const config = (item.frozen_config ?? item.intended_config ?? {}) as Record<string, unknown>;
  const deployment = typeof config.deployment_id === "string" ? config.deployment_id : "saved model";
  const profile = typeof config.profile_id === "string" ? config.profile_id : config.profile_id === null ? "no preset" : "saved preset";
  return `This turn is using its captured setup: ${deployment}, ${profile}. Later header changes do not affect it.`;
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}
