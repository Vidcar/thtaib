import { useEffect, useRef, useState } from "react";

import { api } from "./api";
import { conversationTitle, displayedTranscript, formatWhen, shortId } from "./display";
import { EmptyState } from "./EmptyState";
import { errorMessage } from "./errors";
import { InterruptApproval } from "./InterruptApproval";
import { knowledgeKindLabel } from "./labels";
import { Notice } from "./Notice";
import { RunProgress } from "./RunProgress";
import { SettingsNotes } from "./settingsNotes";
import { StatusBadge } from "./StatusBadge";
import {
  isAgentRunLive,
  isDeclaredEmbedder,
  visiblePendingInterrupt,
  type ChatConversation,
  type ChatMessage,
  type Deployment,
  type KnowledgeEntry,
  type RunProfile,
} from "./types";

function knowledgePayload(entries: KnowledgeEntry[], selectedVersionIds: string[]) {
  const selected = entries.filter((entry) => selectedVersionIds.includes(entry.current_version_id));
  return {
    knowledge_version_refs: selectedVersionIds,
    memory_version_refs: selected
      .filter((entry) => entry.kind === "memory")
      .map((entry) => entry.current_version_id),
    skill_version_refs: selected
      .filter((entry) => entry.kind === "skill")
      .map((entry) => entry.current_version_id),
    protected_instruction_version_refs: selected
      .filter((entry) => entry.kind === "protected_instruction")
      .map((entry) => entry.current_version_id),
  };
}

function messageRoleLabel(role: ChatMessage["role"]): string {
  switch (role) {
    case "user":
      return "You";
    case "assistant":
      return "Assistant";
    case "system":
      return "System";
    default: {
      const unexpected: never = role;
      return unexpected;
    }
  }
}

function isDeploymentAvailable(deployment: Deployment): boolean {
  return deployment.status === "running";
}

function chatModelLabel(deployment: Deployment): string {
  const name = deployment.display_name.replace(/^(managed|connected):/, "");
  const status = deployment.status === "running" ? "Ready" : deployment.scope === "managed" && deployment.status === "stopped" ? "Loads when sent" : deployment.status;
  return `${name} · ${status}`;
}

function preferredChatDeploymentId(deployments: Deployment[], current: string): string {
  const chatDeployments = deployments.filter((deployment) => !isDeclaredEmbedder(deployment));
  if (chatDeployments.some((deployment) => deployment.id === current)) {
    return current;
  }
  return (
    chatDeployments.find(isDeploymentAvailable)?.id ??
    chatDeployments[0]?.id ??
    deployments.find(isDeploymentAvailable)?.id ??
    deployments[0]?.id ??
    ""
  );
}

function newestConversationFirst(items: ChatConversation[]): ChatConversation[] {
  return [...items].sort((left, right) => Date.parse(right.updated_at) - Date.parse(left.updated_at));
}

export function ChatPanel() {
  const [deployments, setDeployments] = useState<Deployment[]>([]);
  const [profiles, setProfiles] = useState<RunProfile[]>([]);
  const [enabledTools, setEnabledTools] = useState<string[]>([]);
  const [deploymentId, setDeploymentId] = useState("");
  const [embeddingDeploymentId, setEmbeddingDeploymentId] = useState("");
  const [profileId, setProfileId] = useState("");
  const [projectPath, setProjectPath] = useState("");
  const [task, setTask] = useState("");
  const [conversation, setConversation] = useState<ChatConversation | null>(null);
  const [conversations, setConversations] = useState<ChatConversation[]>([]);
  const [knowledgeEntries, setKnowledgeEntries] = useState<KnowledgeEntry[]>([]);
  const [selectedKnowledgeIds, setSelectedKnowledgeIds] = useState<string[]>([]);
  const [message, setMessage] = useState("");
  const [loadError, setLoadError] = useState("");
  const [sending, setSending] = useState(false);
  const transcriptEnd = useRef<HTMLDivElement | null>(null);
  const streamRef = useRef<{ key: string; controller: AbortController } | null>(null);

  function rememberConversation(next: ChatConversation): void {
    setConversation(next);
    setConversations((current) => {
      const others = current.filter((item) => item.id !== next.id);
      return [next, ...others];
    });
  }

  async function refresh(): Promise<void> {
    const [nextDeployments, nextProfiles, tools, nextConversations, nextKnowledge] = await Promise.all([
      api.deployments(),
      api.profiles(),
      api.agentTools(),
      api.chatConversations(),
      api.knowledgeEntries(),
    ]);
    setDeployments(nextDeployments);
    setProfiles(nextProfiles);
    setEnabledTools(tools.enabled);
    setConversations(newestConversationFirst(nextConversations));
    setKnowledgeEntries(nextKnowledge);
    setDeploymentId((current) => current || preferredChatDeploymentId(nextDeployments, current));
    setProfileId((current) => (current === "!none" || nextProfiles.some((profile) => profile.id === current) ? current : ""));
    setLoadError("");
  }

  useEffect(() => {
    void refresh().catch((error: unknown) => {
      setLoadError(errorMessage(error));
    });
  }, []);

  const conversationId = conversation?.id ?? null;
  const liveRunId =
    conversation?.current_run && isAgentRunLive(conversation.current_run.status)
      ? conversation.current_run.id
      : null;

  useEffect(() => {
    if (!conversationId || !liveRunId) {
      return;
    }
    const key = `${conversationId}:${liveRunId}`;
    if (streamRef.current?.key === key) {
      return;
    }
    streamRef.current?.controller.abort();
    const controller = new AbortController();
    streamRef.current = { key, controller };
    void api
      .subscribeChatConversation(conversationId, controller.signal, (next) => {
        rememberConversation(next);
        if (next.deploy_health?.message) {
          setMessage(next.deploy_health.message);
        } else if (next.current_run?.error) {
          setMessage(next.current_run.error);
        }
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) {
          return;
        }
        setMessage(errorMessage(error));
      })
      .finally(() => {
        if (streamRef.current?.key === key) {
          streamRef.current = null;
        }
      });
  }, [conversationId, liveRunId]);

  useEffect(() => {
    return () => {
      streamRef.current?.controller.abort();
      streamRef.current = null;
    };
  }, [conversationId]);

  const transcript = conversation ? displayedTranscript(conversation) : [];

  useEffect(() => {
    transcriptEnd.current?.scrollIntoView({ block: "end" });
  }, [transcript.length, liveRunId]);

  function fail(error: unknown): void {
    setMessage(errorMessage(error));
  }

  function startFresh(): void {
    setConversation(null);
    setTask("");
    setMessage("");
  }

  const runBusy = conversation?.current_run ? isAgentRunLive(conversation.current_run.status) : false;
  const selectedProfile = profiles.find((profile) => profile.id === profileId) ?? null;
  const pendingInterrupt = visiblePendingInterrupt(conversation?.current_run);
  const embedderDeployments = deployments.filter((item) => isDeclaredEmbedder(item));
  const chatDeployments = deployments.filter((item) => !isDeclaredEmbedder(item));
  const modelChoices = chatDeployments.length > 0 ? chatDeployments : deployments;
  const selectedDeployment = modelChoices.find((item) => item.id === deploymentId);
  const missingDeployment = Boolean(deploymentId && !selectedDeployment);
  const tools = conversation?.enabled_tools ?? enabledTools;

  async function sendTurn(): Promise<void> {
    const text = task.trim();
    if (!text || !selectedDeployment || sending || runBusy) {
      return;
    }
    setSending(true);
    setMessage("");
    try {
      const refs = knowledgePayload(knowledgeEntries, selectedKnowledgeIds);
      const created =
        conversation ??
        (await api.createChatConversation({
          deployment_id: deploymentId,
          profile_id: profileId && profileId !== "!none" ? profileId : undefined,
          inherit_deployment_settings: profileId !== "!none",
          project_path: projectPath || undefined,
          embedding_deployment_id: embeddingDeploymentId || undefined,
          ...refs,
        }));
      rememberConversation(created);
      const next = await api.startChat(created.id, {
        task: text,
        deployment_id: deploymentId,
        profile_id: profileId && profileId !== "!none" ? profileId : null,
        inherit_deployment_settings: profileId !== "!none",
        project_path: projectPath.trim() || null,
        embedding_deployment_id: embeddingDeploymentId || null,
        ...refs,
      });
      rememberConversation(next);
      setTask("");
      if (next.deploy_health?.message) {
        setMessage(next.deploy_health.message);
      }
    } catch (error: unknown) {
      fail(error);
    } finally {
      setSending(false);
    }
  }

  if (loadError) {
    return (
      <section className="surface">
        <h2>Chat</h2>
        <Notice tone="error">{loadError}</Notice>
        <button type="button" onClick={() => void refresh().catch((error: unknown) => setLoadError(errorMessage(error)))}>
          Retry
        </button>
      </section>
    );
  }

  return (
    <section className="chat-layout">
      <aside className="chat-list" aria-label="Conversations">
        <div className="chat-list-head">
          <h2>Chat</h2>
          <button type="button" onClick={startFresh}>
            New
          </button>
        </div>
        {conversations.length === 0 ? (
          <p className="hint">No conversations yet.</p>
        ) : (
          <ul className="nav-list">
            {conversations.map((item) => (
              <li key={item.id}>
                <button
                  type="button"
                  className={item.id === conversation?.id ? "nav-item active" : "nav-item"}
                  onClick={() => {
                    void api
                      .chatConversation(item.id)
                      .then((next) => {
                        rememberConversation(next);
                        setDeploymentId(next.deployment_id);
                        setEmbeddingDeploymentId(next.embedding_deployment_id ?? "");
                        setProfileId(next.profile_id ?? (next.inherit_deployment_settings === false ? "!none" : ""));
                        setProjectPath(next.project_path ?? "");
                        setSelectedKnowledgeIds([
                          ...(next.memory_version_refs ?? []),
                          ...(next.skill_version_refs ?? []),
                          ...(next.protected_instruction_version_refs ?? []),
                        ]);
                        setMessage("");
                      })
                      .catch(fail);
                  }}
                >
                  <span className="nav-item-title">{conversationTitle(item)}</span>
                  <span className="nav-item-meta">{formatWhen(item.updated_at)}</span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </aside>

      <div className="chat-main">
        <div className="chat-setup card">
          <div className="setup-grid">
            <label>
              Model
              <select value={deploymentId} onChange={(event) => setDeploymentId(event.target.value)}>
                {missingDeployment ? <option value={deploymentId}>Connection unavailable — choose a model</option> : null}
                {modelChoices.length === 0 ? <option value="">No model available</option> : null}
                {modelChoices.map((deployment) => (
                  <option key={deployment.id} value={deployment.id}>
                    {chatModelLabel(deployment)}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Preset
              <select value={profileId} onChange={(event) => setProfileId(event.target.value)}>
                <option value="">Use saved setup settings</option>
                <option value="!none">No preset — ignore saved response settings and instructions</option>
                {profiles.map((profile) => (
                  <option key={profile.id} value={profile.id}>
                    {profile.display_name}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Project folder (optional)
              <input
                value={projectPath}
                onChange={(event) => setProjectPath(event.target.value)}
                placeholder="Leave empty to chat without a project"
              />
            </label>
          </div>
          {missingDeployment ? (
            <Notice tone="warn">This conversation's model connection is unavailable. Its history is preserved. Choose a model before sending another message.</Notice>
          ) : null}
          {conversation?.project_path && !projectPath.trim() ? (
            <p className="hint">The next message will detach project file and shell access. Earlier messages and saved model context remain.</p>
          ) : null}
          {selectedProfile ? (
            <SettingsNotes
              unsupported={selectedProfile.bags.startup.unsupported}
              retired={selectedProfile.bags.startup.retired}
            />
          ) : null}
          {selectedProfile?.bags.agent.unsupported.length ? (
            <Notice tone="warn">Unsupported agent settings: {selectedProfile.bags.agent.unsupported.join(", ")}. These saved values do not govern execution.</Notice>
          ) : null}
          <details>
            <summary>Knowledge and retrieval</summary>
            <p className="hint">
              Choose the memories and instructions this conversation should use. Retrieval needs a
              running embedding model.
            </p>
            <label>
              Document search model
              <select
                value={embeddingDeploymentId}
                onChange={(event) => setEmbeddingDeploymentId(event.target.value)}
              >
                <option value="">None — no retrieval</option>
                {embedderDeployments.map((deployment) => (
                  <option key={deployment.id} value={deployment.id}>
                    {chatModelLabel(deployment)}
                  </option>
                ))}
                {embedderDeployments.length === 0
                  ? deployments
                      .filter((item) => !isDeclaredEmbedder(item))
                      .map((deployment) => (
                        <option key={deployment.id} value={deployment.id}>
                          {chatModelLabel(deployment)} (not marked for retrieval)
                        </option>
                      ))
                  : null}
              </select>
            </label>
            <fieldset className="choice-set">
              <legend>Knowledge versions</legend>
              {knowledgeEntries.length === 0 ? (
                <p className="hint">None yet. Create them on Knowledge.</p>
              ) : (
                knowledgeEntries.map((entry) => (
                  <label key={entry.id} className="check-row">
                    <input
                      type="checkbox"
                      checked={selectedKnowledgeIds.includes(entry.current_version_id)}
                      onChange={() => {
                        const versionId = entry.current_version_id;
                        setSelectedKnowledgeIds((current) =>
                          current.includes(versionId)
                            ? current.filter((item) => item !== versionId)
                            : [...current, versionId],
                        );
                      }}
                    />
                    {knowledgeKindLabel(entry.kind)} · {entry.display_name ?? shortId(entry.id)}
                  </label>
                ))
              )}
            </fieldset>
          </details>
          <p className="hint">
            Tools: {tools.length ? tools.join(", ") : "none"}
            {conversation && conversation.filesystem_tools_available === false
              ? " · project files unavailable"
              : ""}
            {conversation && conversation.shell_tools_available === false ? " · host shell unavailable" : ""}
          </p>
        </div>

        <div className="transcript" aria-live="polite">
          {deployments.length === 0 && !conversation ? (
            <EmptyState title="Choose a model setup">
              Open Models and save a setup for Chat, start a model, or connect a server. A saved local setup loads automatically when you send a message.
            </EmptyState>
          ) : !conversation && transcript.length === 0 ? (
            <EmptyState title="Start a conversation">
              Send a message. A project folder is optional. Without one, the assistant can talk but
              cannot use file tools or the host shell.
            </EmptyState>
          ) : (
            transcript.map((item, index) => (
              <article key={`${item.at}-${item.role}-${index}`} className={`bubble bubble-${item.role}`}>
                <header>
                  <strong>{messageRoleLabel(item.role)}</strong>
                  <time>{formatWhen(item.at)}</time>
                </header>
                <p>{item.content}</p>
              </article>
            ))
          )}
          {runBusy && !pendingInterrupt ? (
            <p className="hint">
              Working… <StatusBadge status={conversation?.current_run?.status} /> This can continue if
              the window disconnects.
            </p>
          ) : null}
          <div ref={transcriptEnd} />
        </div>

        {pendingInterrupt && conversation ? (
          <InterruptApproval
            pending={pendingInterrupt}
            busy={sending}
            onDecide={(type) => {
              void api.decideChatInterrupt(conversation.id, type).then(rememberConversation).catch(fail);
            }}
          />
        ) : null}

        {conversation?.current_run ? (
          <details className="card">
            <summary>
              Run progress <StatusBadge status={conversation.current_run.status} />
            </summary>
            <RunProgress
              run={conversation.current_run}
              onCancel={() => {
                void api.cancelChat(conversation.id).then(rememberConversation).catch(fail);
              }}
            />
          </details>
        ) : null}

        {conversation?.deploy_health?.message ? (
          <Notice tone={conversation.deploy_health.healthy === false ? "error" : "warn"}>
            {conversation.deploy_health.message}
          </Notice>
        ) : null}
        {message && message !== conversation?.deploy_health?.message ? (
          <Notice tone="error">{message}</Notice>
        ) : null}

        <form
          className="compose"
          onSubmit={(event) => {
            event.preventDefault();
            void sendTurn();
          }}
        >
          <label>
            Message
            <textarea
              value={task}
              onChange={(event) => setTask(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" && !event.shiftKey) {
                  event.preventDefault();
                  void sendTurn();
                }
              }}
              placeholder="Ask or give a task. Shift+Enter for a new line."
              disabled={sending}
            />
          </label>
          <div className="actions">
            <button type="submit" disabled={!selectedDeployment || !task.trim() || runBusy || sending}>
              {sending || runBusy ? "Sending…" : "Send"}
            </button>
            <button
              type="button"
              disabled={!conversation || !runBusy}
              onClick={() => {
                if (!conversation) {
                  return;
                }
                void api.cancelChat(conversation.id).then(rememberConversation).catch(fail);
              }}
            >
              Cancel
            </button>
            <button type="button" onClick={startFresh}>
              New conversation
            </button>
          </div>
        </form>
      </div>
    </section>
  );
}
