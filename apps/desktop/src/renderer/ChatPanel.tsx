import { useCallback, useEffect, useRef, useState } from "react";

import { api } from "./api";
import { AgentMessageFeed } from "./AgentMessageFeed";
import { conversationTitle, displayedTranscript, formatWhen, shortId } from "./display";
import { EmptyState } from "./EmptyState";
import { errorMessage } from "./errors";
import { InteractionStream, useWorkbenchProjection, visibleApprovalInterrupt, type WorkbenchStream } from "./InteractionStream";
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

interface PendingChatSubmit {
  id: string;
  task: string;
  deployment_id: string;
  profile_id: string | null;
  inherit_deployment_settings: boolean;
  project_path: string | null;
  workspace_id: string | null;
  memory_version_refs?: string[];
  skill_version_refs?: string[];
  protected_instruction_version_refs?: string[];
  knowledge_version_refs?: string[];
  embedding_deployment_id: string | null;
  retrieval_project_paths?: string[];
}

function ChatInteractionStream(props: {
  threadId: string;
  conversation: ChatConversation;
  pendingSubmit: PendingChatSubmit | null;
  clearPendingSubmit: () => void;
  rememberConversation: (conversation: ChatConversation) => void;
  setTask: (task: string) => void;
  setMessage: (message: string) => void;
}) {
  const { threadId, conversation, pendingSubmit, clearPendingSubmit, rememberConversation, setTask, setMessage } = props;
  return (
    <InteractionStream threadId={threadId} onError={(error) => setMessage(errorMessage(error))}>
      {(stream) => (
        <ChatInteractionStreamContent
          stream={stream}
          conversation={conversation}
          pendingSubmit={pendingSubmit}
          clearPendingSubmit={clearPendingSubmit}
          rememberConversation={rememberConversation}
          setTask={setTask}
          setMessage={setMessage}
        />
      )}
    </InteractionStream>
  );
}

function ChatInteractionStreamContent(props: {
  stream: WorkbenchStream;
  conversation: ChatConversation;
  pendingSubmit: PendingChatSubmit | null;
  clearPendingSubmit: () => void;
  rememberConversation: (conversation: ChatConversation) => void;
  setTask: (task: string) => void;
  setMessage: (message: string) => void;
}) {
  const { stream, conversation, pendingSubmit, clearPendingSubmit, rememberConversation, setTask, setMessage } = props;
  const projection = useWorkbenchProjection(stream);
  const run = projection.run;
  const visibleInterrupt = visibleApprovalInterrupt(stream, run ?? conversation.current_run);
  const projectionSignature = useRef("");
  const terminalRefreshKey = useRef("");
  const submittedIds = useRef(new Set<string>());

  useEffect(() => {
    if (!run) {
      return;
    }
    const signature = JSON.stringify({
      runId: run?.id ?? null,
      runStatus: run?.status ?? null,
      eventCount: run?.events.length ?? null,
    });
    if (projectionSignature.current === signature) {
      return;
    }
    projectionSignature.current = signature;
    rememberConversation({
      ...conversation,
      current_run: run,
      current_run_id: run.id,
      run_ids: run && !conversation.run_ids.includes(run.id) ? [...conversation.run_ids, run.id] : conversation.run_ids,
      updated_at: new Date().toISOString(),
    });
  }, [conversation, rememberConversation, run]);

  useEffect(() => {
    if (!run || isAgentRunLive(run.status)) {
      return;
    }
    const key = `${run.id}:${run.status}`;
    if (terminalRefreshKey.current === key) {
      return;
    }
    terminalRefreshKey.current = key;
    void api.chatConversation(conversation.id).then(rememberConversation).catch((error: unknown) => {
      setMessage(errorMessage(error));
    });
  }, [conversation.id, rememberConversation, run?.id, run?.status, setMessage]);

  useEffect(() => {
    if (!pendingSubmit) {
      return;
    }
    if (submittedIds.current.has(pendingSubmit.id)) {
      return;
    }
    submittedIds.current.add(pendingSubmit.id);
    const { id: messageId, task: inputTask, ...workbench } = pendingSubmit;
    clearPendingSubmit();
    void stream
      .submit(
        { messages: [{ type: "human", content: inputTask, id: messageId }] },
        { multitaskStrategy: "reject", metadata: { workbench } },
      )
      .then(() => setTask(""))
      .catch((error: unknown) => setMessage(errorMessage(error)));
  }, [clearPendingSubmit, pendingSubmit, setMessage, setTask, stream]);

  return (
    <>
      <AgentMessageFeed messages={projection.messages} toolCalls={projection.toolCalls} incompleteMessageIds={projection.incompleteMessageIds} />
      {visibleInterrupt ? (
        <InterruptApproval
          pending={visibleInterrupt.pending}
          busy={stream.isLoading}
          onDecide={(type) => {
            void stream
              .respond(
                { decisions: [{ type }] },
                { interruptId: visibleInterrupt.id, namespace: visibleInterrupt.namespace },
              )
              .catch((error: unknown) => setMessage(errorMessage(error)));
          }}
        />
      ) : null}
    </>
  );
}

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

function transcriptMessageContent(item: ChatMessage): string {
  const parts = [item.content, ...(item.content_blocks ?? [])
    .filter((block) => block.type === "text")
    .map((block) => block.text)]
    .filter((part) => part.trim());
  const imageCount = (item.content_blocks ?? []).filter((block) => block.type === "image_url").length;
  if (imageCount > 0) {
    parts.push(`📎 ${imageCount} image ${imageCount === 1 ? "attached" : "attachments"}`);
  }
  return parts.join("\n");
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
  const [pendingSubmit, setPendingSubmit] = useState<PendingChatSubmit | null>(null);
  const [interactionThreadId, setInteractionThreadId] = useState<string | null>(null);
  const transcriptEnd = useRef<HTMLDivElement | null>(null);
  const selectionRequest = useRef(0);

  const rememberConversation = useCallback((next: ChatConversation): void => {
    setConversation(next);
    setConversations((current) => {
      const others = current.filter((item) => item.id !== next.id);
      return [next, ...others];
    });
  }, []);

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

  const liveRunId =
    conversation?.current_run && isAgentRunLive(conversation.current_run.status)
      ? conversation.current_run.id
      : null;

  const transcript = conversation ? displayedTranscript(conversation) : [];

  useEffect(() => {
    transcriptEnd.current?.scrollIntoView({ block: "end" });
  }, [transcript.length, liveRunId]);

  function fail(error: unknown): void {
    setMessage(errorMessage(error));
  }

  function startFresh(): void {
    selectionRequest.current += 1;
    setConversation(null);
    setInteractionThreadId(null);
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
      const threadId =
        interactionThreadId ??
        (await api.registerAgentInteractionThread({
          source_surface: "chat",
          conversation_id: created.id,
        })).thread_id;
      setInteractionThreadId(threadId);
      rememberConversation(created);
      setPendingSubmit({
        id: crypto.randomUUID(),
        task: text,
        deployment_id: deploymentId,
        profile_id: profileId && profileId !== "!none" ? profileId : null,
        inherit_deployment_settings: profileId !== "!none",
        project_path: projectPath.trim() || null,
        workspace_id: null,
        embedding_deployment_id: embeddingDeploymentId || null,
        ...refs,
      });
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
                    const requestId = selectionRequest.current + 1;
                    selectionRequest.current = requestId;
                    void api
                      .chatConversation(item.id)
                      .then(async (next) => {
                        if (selectionRequest.current !== requestId) {
                          return;
                        }
                        rememberConversation(next);
                        const registered = await api.registerAgentInteractionThread({
                          source_surface: "chat",
                          conversation_id: next.id,
                        });
                        if (selectionRequest.current !== requestId) {
                          return;
                        }
                        setInteractionThreadId(registered.thread_id);
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
          ) : interactionThreadId && conversation ? (
            <ChatInteractionStream
              key={`${conversation.id}:${interactionThreadId}`}
              threadId={interactionThreadId}
              conversation={conversation}
              pendingSubmit={pendingSubmit}
              clearPendingSubmit={() => setPendingSubmit(null)}
              rememberConversation={rememberConversation}
              setTask={setTask}
              setMessage={setMessage}
            />
          ) : (
            transcript.map((item, index) => (
              <article key={`${item.at}-${item.role}-${index}`} className={`bubble bubble-${item.role}`}>
                <header>
                  <strong>{messageRoleLabel(item.role)}</strong>
                  <time>{formatWhen(item.at)}</time>
                </header>
                <p>{transcriptMessageContent(item)}</p>
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

        {conversation?.current_run ? (
          <details className="card chat-run-details">
            <summary>
              Run progress <StatusBadge status={conversation.current_run.status} />
            </summary>
            <RunProgress
              run={conversation.current_run}
              onCancel={() => {
                if (!conversation.current_run) {
                  return;
                }
                void api.cancelAgentRun(conversation.current_run.id)
                  .then((next) => rememberConversation({ ...conversation, current_run: next, current_run_id: next.id }))
                  .catch(fail);
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
                if (!conversation.current_run) {
                  return;
                }
                void api.cancelAgentRun(conversation.current_run.id)
                  .then((next) => rememberConversation({ ...conversation, current_run: next, current_run_id: next.id }))
                  .catch(fail);
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
