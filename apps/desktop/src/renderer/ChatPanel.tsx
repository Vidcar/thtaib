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
  conversation_id: string;
  thread_id: string;
  selection_generation: number;
  draft_revision: number;
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
  selectionGeneration: number;
  conversation: ChatConversation;
  pendingSubmit: PendingChatSubmit | null;
  clearPendingSubmit: (pending: PendingChatSubmit) => void;
  updateConversation: (conversation: ChatConversation, owner: SelectionOwner) => void;
  updateConversationForRun: (conversation: ChatConversation, owner: SelectionOwner, runId: string) => void;
  clearSubmittedDraft: (pending: PendingChatSubmit) => void;
  setMessage: (message: string) => void;
  isCurrentOwner: (owner: SelectionOwner) => boolean;
}) {
  const {
    threadId,
    selectionGeneration,
    conversation,
    pendingSubmit,
    clearPendingSubmit,
    updateConversation,
    updateConversationForRun,
    clearSubmittedDraft,
    setMessage,
    isCurrentOwner,
  } = props;
  const owner = { conversationId: conversation.id, threadId, generation: selectionGeneration };
  return (
    <InteractionStream
      threadId={threadId}
      onError={(error) => {
        if (isCurrentOwner(owner)) {
          setMessage(errorMessage(error));
        }
      }}
    >
      {(stream) => (
        <ChatInteractionStreamContent
          stream={stream}
          owner={owner}
          conversation={conversation}
          pendingSubmit={pendingSubmit}
          clearPendingSubmit={clearPendingSubmit}
          updateConversation={updateConversation}
          updateConversationForRun={updateConversationForRun}
          clearSubmittedDraft={clearSubmittedDraft}
          setMessage={setMessage}
          isCurrentOwner={isCurrentOwner}
        />
      )}
    </InteractionStream>
  );
}

interface SelectionOwner {
  conversationId: string;
  threadId: string;
  generation: number;
}

function ChatInteractionStreamContent(props: {
  stream: WorkbenchStream;
  owner: SelectionOwner;
  conversation: ChatConversation;
  pendingSubmit: PendingChatSubmit | null;
  clearPendingSubmit: (pending: PendingChatSubmit) => void;
  updateConversation: (conversation: ChatConversation, owner: SelectionOwner) => void;
  updateConversationForRun: (conversation: ChatConversation, owner: SelectionOwner, runId: string) => void;
  clearSubmittedDraft: (pending: PendingChatSubmit) => void;
  setMessage: (message: string) => void;
  isCurrentOwner: (owner: SelectionOwner) => boolean;
}) {
  const {
    stream,
    owner,
    conversation,
    pendingSubmit,
    clearPendingSubmit,
    updateConversation,
    updateConversationForRun,
    clearSubmittedDraft,
    setMessage,
    isCurrentOwner,
  } = props;
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
    if (
      pendingSubmit &&
      pendingSubmit.conversation_id === owner.conversationId &&
      pendingSubmit.thread_id === owner.threadId &&
      pendingSubmit.selection_generation === owner.generation &&
      run.input_message_id === pendingSubmit.id
    ) {
      clearPendingSubmit(pendingSubmit);
    }
    updateConversation({
      ...conversation,
      current_run: run,
      current_run_id: run.id,
      run_ids: run && !conversation.run_ids.includes(run.id) ? [...conversation.run_ids, run.id] : conversation.run_ids,
      updated_at: new Date().toISOString(),
    }, owner);
  }, [clearPendingSubmit, conversation, owner, pendingSubmit, run, updateConversation]);

  useEffect(() => {
    if (!run || isAgentRunLive(run.status)) {
      return;
    }
    const key = `${run.id}:${run.status}`;
    if (terminalRefreshKey.current === key) {
      return;
    }
    terminalRefreshKey.current = key;
    const terminalRunId = run.id;
    void api.chatConversation(conversation.id).then((next) => {
      updateConversationForRun(next, owner, terminalRunId);
    }).catch((error: unknown) => {
      if (!isCurrentOwner(owner)) {
        return;
      }
      setMessage(errorMessage(error));
    });
  }, [conversation.id, isCurrentOwner, owner, run?.id, run?.status, setMessage, updateConversationForRun]);

  useEffect(() => {
    if (!pendingSubmit) {
      return;
    }
    if (
      pendingSubmit.conversation_id !== owner.conversationId ||
      pendingSubmit.thread_id !== owner.threadId ||
      pendingSubmit.selection_generation !== owner.generation ||
      !isCurrentOwner(owner)
    ) {
      return;
    }
    if (submittedIds.current.has(pendingSubmit.id)) {
      return;
    }
    submittedIds.current.add(pendingSubmit.id);
    const {
      id: messageId,
      task: inputTask,
      conversation_id: _conversationId,
      thread_id: _threadId,
      selection_generation: _selectionGeneration,
      draft_revision: _draftRevision,
      ...workbench
    } = pendingSubmit;
    void stream
      .submit(
        { messages: [{ type: "human", content: inputTask, id: messageId }] },
        { multitaskStrategy: "reject", metadata: { workbench } },
      )
      .then(() => clearSubmittedDraft(pendingSubmit))
      .catch((error: unknown) => {
        clearPendingSubmit(pendingSubmit);
        if (!isCurrentOwner(owner)) {
          return;
        }
        setMessage(errorMessage(error));
      });
  }, [clearPendingSubmit, clearSubmittedDraft, isCurrentOwner, owner, pendingSubmit, setMessage, stream]);

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
              .catch((error: unknown) => {
                if (isCurrentOwner(owner)) {
                  setMessage(errorMessage(error));
                }
              });
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
  const [selectionLoading, setSelectionLoading] = useState<ChatConversation | null>(null);
  const [boundGeneration, setBoundGeneration] = useState(0);
  const transcriptEnd = useRef<HTMLDivElement | null>(null);
  const selectionRequest = useRef(0);
  const draftRevision = useRef(0);
  const activeOwner = useRef<{ conversationId: string | null; threadId: string | null; generation: number }>({
    conversationId: null,
    threadId: null,
    generation: 0,
  });

  const cacheConversation = useCallback((next: ChatConversation): void => {
    setConversations((current) => {
      const others = current.filter((item) => item.id !== next.id);
      return [next, ...others];
    });
  }, []);

  const isCurrentOwner = useCallback((owner: SelectionOwner): boolean => (
    selectionRequest.current === owner.generation &&
    activeOwner.current.conversationId === owner.conversationId &&
    activeOwner.current.threadId === owner.threadId &&
    activeOwner.current.generation === owner.generation
  ), []);

  const updateConversation = useCallback((next: ChatConversation, owner: SelectionOwner): void => {
    cacheConversation(next);
    if (isCurrentOwner(owner)) {
      setConversation(next);
    }
  }, [cacheConversation, isCurrentOwner]);

  const updateConversationForRun = useCallback((next: ChatConversation, owner: SelectionOwner, runId: string): void => {
    cacheConversation(next);
    if (isCurrentOwner(owner)) {
      setConversation((current) => (
        current?.id === owner.conversationId && current.current_run_id === runId
          ? next
          : current
      ));
    }
  }, [cacheConversation, isCurrentOwner]);

  const updateTask = useCallback((next: string): void => {
    draftRevision.current += 1;
    setTask(next);
  }, []);

  const clearPendingSubmit = useCallback((pending: PendingChatSubmit): void => {
    setPendingSubmit((current) => (current?.id === pending.id ? null : current));
  }, []);

  const clearSubmittedDraft = useCallback((pending: PendingChatSubmit): void => {
    const owner = {
      conversationId: pending.conversation_id,
      threadId: pending.thread_id,
      generation: pending.selection_generation,
    };
    if (!isCurrentOwner(owner) || draftRevision.current !== pending.draft_revision) {
      return;
    }
    draftRevision.current += 1;
    setTask("");
  }, [isCurrentOwner]);

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
    activeOwner.current = { conversationId: null, threadId: null, generation: selectionRequest.current };
    setBoundGeneration(selectionRequest.current);
    setConversation(null);
    setInteractionThreadId(null);
    setSelectionLoading(null);
    setPendingSubmit(null);
    setSending(false);
    updateTask("");
    setMessage("");
  }

  const selectionBusy = Boolean(selectionLoading);
  const runBusy = (conversation?.current_run ? isAgentRunLive(conversation.current_run.status) : false) || Boolean(pendingSubmit);
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
    if (!text || !selectedDeployment || selectionBusy || sending || runBusy) {
      return;
    }
    const requestId = selectionRequest.current;
    const originConversationId = conversation?.id ?? null;
    const capturedDraftRevision = draftRevision.current;
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
      cacheConversation(created);
      if (
        selectionRequest.current !== requestId ||
        (originConversationId !== null && activeOwner.current.conversationId !== originConversationId)
      ) {
        return;
      }
      const threadId =
        interactionThreadId ??
        (await api.registerAgentInteractionThread({
          source_surface: "chat",
          conversation_id: created.id,
        })).thread_id;
      if (
        selectionRequest.current !== requestId ||
        (originConversationId !== null && activeOwner.current.conversationId !== originConversationId)
      ) {
        return;
      }
      const generation = selectionRequest.current;
      activeOwner.current = { conversationId: created.id, threadId, generation };
      setBoundGeneration(generation);
      setInteractionThreadId(threadId);
      setSelectionLoading(null);
      setConversation(created);
      setPendingSubmit({
        id: crypto.randomUUID(),
        conversation_id: created.id,
        thread_id: threadId,
        selection_generation: generation,
        draft_revision: capturedDraftRevision,
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
      if (selectionRequest.current === requestId) {
        fail(error);
      }
    } finally {
      if (selectionRequest.current === requestId) {
        setSending(false);
      }
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
                  className={item.id === conversation?.id || item.id === selectionLoading?.id ? "nav-item active" : "nav-item"}
                  onClick={() => {
                    const requestId = selectionRequest.current + 1;
                    selectionRequest.current = requestId;
                    activeOwner.current = { conversationId: null, threadId: null, generation: requestId };
                    setBoundGeneration(requestId);
                    setConversation(null);
                    setInteractionThreadId(null);
                    setSelectionLoading(item);
                    setPendingSubmit(null);
                    setSending(false);
                    void api
                      .chatConversation(item.id)
                      .then(async (next) => {
                        if (selectionRequest.current !== requestId) {
                          return;
                        }
                        cacheConversation(next);
                        const registered = await api.registerAgentInteractionThread({
                          source_surface: "chat",
                          conversation_id: next.id,
                        });
                        if (selectionRequest.current !== requestId) {
                          return;
                        }
                        activeOwner.current = { conversationId: next.id, threadId: registered.thread_id, generation: requestId };
                        setBoundGeneration(requestId);
                        setConversation(next);
                        setInteractionThreadId(registered.thread_id);
                        setSelectionLoading(null);
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
                      .catch((error: unknown) => {
                        if (selectionRequest.current === requestId) {
                          setSelectionLoading(null);
                          fail(error);
                        }
                      });
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
          ) : selectionLoading ? (
            <EmptyState title="Loading conversation">
              Opening {conversationTitle(selectionLoading)}.
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
              selectionGeneration={boundGeneration}
              conversation={conversation}
              pendingSubmit={pendingSubmit}
              clearPendingSubmit={clearPendingSubmit}
              updateConversation={updateConversation}
              updateConversationForRun={updateConversationForRun}
              clearSubmittedDraft={clearSubmittedDraft}
              setMessage={setMessage}
              isCurrentOwner={isCurrentOwner}
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
                if (!interactionThreadId) {
                  return;
                }
                const owner = {
                  conversationId: conversation.id,
                  threadId: interactionThreadId,
                  generation: boundGeneration,
                };
                const cancelledRunId = conversation.current_run.id;
                void api.cancelAgentRun(cancelledRunId)
                  .then((next) => {
                    updateConversationForRun({ ...conversation, current_run: next, current_run_id: next.id }, owner, cancelledRunId);
                  })
                  .catch((error: unknown) => {
                    if (isCurrentOwner(owner)) {
                      fail(error);
                    }
                  });
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
              onChange={(event) => updateTask(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" && !event.shiftKey) {
                  event.preventDefault();
                  void sendTurn();
                }
              }}
              placeholder="Ask or give a task. Shift+Enter for a new line."
              disabled={selectionBusy || sending}
            />
          </label>
          <div className="actions">
            <button type="submit" disabled={!selectedDeployment || !task.trim() || selectionBusy || runBusy || sending}>
              {selectionBusy || sending || runBusy ? "Sending…" : "Send"}
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
                if (!interactionThreadId) {
                  return;
                }
                const owner = {
                  conversationId: conversation.id,
                  threadId: interactionThreadId,
                  generation: boundGeneration,
                };
                const cancelledRunId = conversation.current_run.id;
                void api.cancelAgentRun(cancelledRunId)
                  .then((next) => {
                    updateConversationForRun({ ...conversation, current_run: next, current_run_id: next.id }, owner, cancelledRunId);
                  })
                  .catch((error: unknown) => {
                    if (isCurrentOwner(owner)) {
                      fail(error);
                    }
                  });
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
