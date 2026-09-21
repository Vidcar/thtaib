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
  type PresentationSettings,
  type PresentationTheme,
  type RunProfile,
  type WorkbenchTab,
} from "./types";

interface PendingStopRequest {
  id: string;
  conversation_id: string;
  thread_id: string;
  selection_generation: number;
}

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
  updateConversationIfCurrentRun: (conversation: ChatConversation, owner: SelectionOwner, expectedRunId: string | null) => void;
  updateConversationForRun: (conversation: ChatConversation, owner: SelectionOwner, runId: string) => void;
  clearSubmittedDraft: (pending: PendingChatSubmit) => void;
  refreshDeployments: () => void;
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
    updateConversationIfCurrentRun,
    updateConversationForRun,
    clearSubmittedDraft,
    refreshDeployments,
    setMessage,
    isCurrentOwner,
  } = props;
  const owner = { conversationId: conversation.id, threadId, generation: selectionGeneration };
  return (
    <InteractionStream
      threadId={threadId}
      onError={(error) => {
        if (isCurrentOwner(owner)) {
          if (
            pendingSubmit &&
            pendingSubmit.conversation_id === owner.conversationId &&
            pendingSubmit.thread_id === owner.threadId &&
            pendingSubmit.selection_generation === owner.generation
          ) {
            clearPendingSubmit(pendingSubmit);
            void api.chatConversation(pendingSubmit.conversation_id)
              .then((next) => {
                if (!isCurrentOwner(owner)) {
                  return;
                }
                updateConversation(next, owner);
                if (chatHasAcceptedInputMessage(next, pendingSubmit.id)) {
                  clearSubmittedDraft(pendingSubmit);
                  refreshDeployments();
                  setMessage("");
                  return;
                }
                setMessage(errorMessage(error));
              })
              .catch(() => {
                if (isCurrentOwner(owner)) {
                  setMessage(errorMessage(error));
                }
              });
            return;
          }
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
          updateConversationIfCurrentRun={updateConversationIfCurrentRun}
          updateConversationForRun={updateConversationForRun}
          clearSubmittedDraft={clearSubmittedDraft}
          refreshDeployments={refreshDeployments}
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
  updateConversationIfCurrentRun: (conversation: ChatConversation, owner: SelectionOwner, expectedRunId: string | null) => void;
  updateConversationForRun: (conversation: ChatConversation, owner: SelectionOwner, runId: string) => void;
  clearSubmittedDraft: (pending: PendingChatSubmit) => void;
  refreshDeployments: () => void;
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
    updateConversationIfCurrentRun,
    updateConversationForRun,
    clearSubmittedDraft,
    refreshDeployments,
    setMessage,
    isCurrentOwner,
  } = props;
  const projection = useWorkbenchProjection(stream);
  const run = projection.run;
  const projectionMatchesPendingSubmit = Boolean(
    run &&
    pendingSubmit?.conversation_id === owner.conversationId &&
    pendingSubmit.thread_id === owner.threadId &&
    pendingSubmit.selection_generation === owner.generation &&
    run.input_message_id === pendingSubmit.id
  );
  const pendingCancelInputIds = conversation.pending_cancel_input_ids ?? [];
  const projectionBlockedByPendingCancel = Boolean(
    run &&
    pendingCancelInputIds.length > 0 &&
    (!run.input_message_id || !pendingCancelInputIds.includes(run.input_message_id))
  );
  const projectionRunOwned = !run || (!projectionBlockedByPendingCancel && (
    conversation.current_run_id === run.id || projectionMatchesPendingSubmit || (
    conversation.run_ids.includes(run.id) &&
    !conversation.current_run_id &&
    !conversation.current_run
    )
  ));
  const visibleInterrupt = visibleApprovalInterrupt(stream, run ?? conversation.current_run);
  const projectionSignature = useRef("");
  const ownershipLookupKey = useRef("");
  const terminalRefreshKey = useRef("");
  const submittedIds = useRef(new Set<string>());

  useEffect(() => {
    if (!run || projectionRunOwned || projectionMatchesPendingSubmit) {
      return;
    }
    const key = `${owner.conversationId}:${owner.threadId}:${owner.generation}:${run.id}:${run.status}`;
    if (ownershipLookupKey.current === key) {
      return;
    }
    ownershipLookupKey.current = key;
    const originCurrentRunId = conversation.current_run_id ?? null;
    void api.chatConversation(conversation.id).then((next) => {
      if (next.current_run_id !== run.id) {
        return;
      }
      updateConversationIfCurrentRun(next, owner, originCurrentRunId);
    }).catch((error: unknown) => {
      if (!isCurrentOwner(owner)) {
        return;
      }
      setMessage(errorMessage(error));
    });
  }, [conversation.current_run_id, conversation.id, isCurrentOwner, owner, projectionMatchesPendingSubmit, projectionRunOwned, run, setMessage, updateConversationIfCurrentRun]);

  useEffect(() => {
    if (!run || !projectionRunOwned) {
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
      projectionMatchesPendingSubmit
    ) {
      clearSubmittedDraft(pendingSubmit);
      clearPendingSubmit(pendingSubmit);
      refreshDeployments();
    }
    updateConversation({
      ...conversation,
      current_run: run,
      current_run_id: run.id,
      run_ids: run && !conversation.run_ids.includes(run.id) ? [...conversation.run_ids, run.id] : conversation.run_ids,
      updated_at: new Date().toISOString(),
    }, owner);
  }, [clearPendingSubmit, clearSubmittedDraft, conversation, owner, pendingSubmit, projectionMatchesPendingSubmit, projectionRunOwned, refreshDeployments, run, updateConversation]);

  useEffect(() => {
    if (!run || !projectionRunOwned || isAgentRunLive(run.status)) {
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
  }, [conversation.id, isCurrentOwner, owner, projectionRunOwned, run?.id, run?.status, setMessage, updateConversationForRun]);

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
      .then(() => refreshDeployments())
      .catch((error: unknown) => {
        clearPendingSubmit(pendingSubmit);
        if (!isCurrentOwner(owner)) {
          return;
        }
        void api.chatConversation(pendingSubmit.conversation_id)
          .then((next) => {
            if (!isCurrentOwner(owner)) {
              return;
            }
            updateConversation(next, owner);
            if (chatHasAcceptedInputMessage(next, pendingSubmit.id)) {
              clearSubmittedDraft(pendingSubmit);
              setMessage("");
              return;
            }
            setMessage(errorMessage(error));
          })
          .catch(() => {
            if (isCurrentOwner(owner)) {
              setMessage(errorMessage(error));
            }
          });
      });
  }, [clearPendingSubmit, clearSubmittedDraft, isCurrentOwner, owner, pendingSubmit, setMessage, stream, updateConversation]);

  return (
    <>
      {projectionRunOwned ? (
        <AgentMessageFeed messages={projection.messages} toolCalls={projection.toolCalls} incompleteMessageIds={projection.incompleteMessageIds} />
      ) : null}
      {projectionRunOwned && visibleInterrupt ? (
        <InterruptApproval
          pending={visibleInterrupt.pending}
          busy={stream.isLoading}
          onRespond={(payload) => {
            void stream
              .respond(
                payload,
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

function chatDeployHealthNotice(conversation: ChatConversation | null, selectedDeployment: Deployment | undefined): { tone: "info" | "warn" | "error"; message: string } | null {
  const health = conversation?.deploy_health;
  if (!conversation || !health?.message) {
    return null;
  }
  const selectedIsBound = selectedDeployment?.id === conversation.deployment_id && health.deployment_id === conversation.deployment_id;
  if (selectedIsBound && selectedDeployment?.scope === "managed" && selectedDeployment.status === "stopped") {
    return { tone: "info", message: "This saved model setup will load when you send a message." };
  }
  return { tone: health.healthy === false ? "error" : "warn", message: health.message };
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

function chatHasAcceptedInputMessage(conversation: ChatConversation, messageId: string): boolean {
  const acceptedRunIds = new Set([
    ...conversation.run_ids,
    ...(conversation.current_run_id ? [conversation.current_run_id] : []),
    ...(conversation.current_run?.id ? [conversation.current_run.id] : []),
  ]);
  return conversation.transcript.some((item) => {
    const message = item as ChatMessage & { id?: string | null };
    return item.role === "user" && message.id === messageId && Boolean(item.run_id && acceptedRunIds.has(item.run_id));
  });
}

function areaLabel(conversation: ChatConversation | null): string {
  if (!conversation || areaKind(conversation) !== "project") {
    return "General";
  }
  if (conversation.area_label?.trim()) {
    return conversation.area_label;
  }
  const path = conversation.area_project_path ?? conversation.project_path;
  if (!path) {
    return "Project";
  }
  const normalized = path.replace(/\\/g, "/");
  return normalized.split("/").filter(Boolean).at(-1) ?? path;
}

function areaKind(conversation: ChatConversation): "general" | "project" {
  return conversation.area_kind ?? (conversation.project_path ? "project" : "general");
}

function areaKey(conversation: ChatConversation): string {
  if (areaKind(conversation) !== "project") {
    return "general";
  }
  return conversation.area_id ?? conversation.area_project_path ?? conversation.project_path ?? conversation.id;
}

function tabLabel(tab: WorkbenchTab): string {
  switch (tab) {
    case "chat":
      return "Chat";
    case "models":
      return "Models";
    case "knowledge":
      return "Knowledge";
    case "agent-run":
      return "Agent run";
    case "lab":
      return "Lab";
    default: {
      const unexpected: never = tab;
      return unexpected;
    }
  }
}

const fallbackPresentation: PresentationSettings = {
  theme: "system",
  detailed_streams: false,
  attention_notifications: true,
  success_notifications: false,
};

interface ChatPanelProps {
  activeTab?: WorkbenchTab;
  attentionConversationId?: string | null;
  backendOk?: boolean | null;
  backendStatus?: string;
  onNavigate?: (tab: WorkbenchTab) => void;
  onThemeChange?: (theme: PresentationTheme) => void;
  presentation?: PresentationSettings;
  productName?: string;
}

export function ChatPanel(props: ChatPanelProps = {}) {
  const {
    activeTab = "chat",
    attentionConversationId = null,
    backendOk = null,
    backendStatus = "",
    onNavigate,
    onThemeChange,
    presentation = fallbackPresentation,
    productName = "Local AI Workbench",
  } = props;
  const [sidebarCollapsed, setSidebarCollapsed] = useState(() => window.innerWidth <= 860);
  const [deployments, setDeployments] = useState<Deployment[]>([]);
  const [profiles, setProfiles] = useState<RunProfile[]>([]);
  const [enabledTools, setEnabledTools] = useState<string[]>([]);
  const [deploymentId, setDeploymentId] = useState("");
  const [embeddingDeploymentId, setEmbeddingDeploymentId] = useState("");
  const [profileId, setProfileId] = useState("");
  const [projectPath, setProjectPath] = useState("");
  const [task, setTask] = useState("");
  const [searchQuery, setSearchQuery] = useState("");
  const [includeArchived, setIncludeArchived] = useState(false);
  const [searchResults, setSearchResults] = useState<ChatConversation[] | null>(null);
  const [conversation, setConversation] = useState<ChatConversation | null>(null);
  const [conversations, setConversations] = useState<ChatConversation[]>([]);
  const [knowledgeEntries, setKnowledgeEntries] = useState<KnowledgeEntry[]>([]);
  const [selectedKnowledgeIds, setSelectedKnowledgeIds] = useState<string[]>([]);
  const [message, setMessage] = useState("");
  const [loadError, setLoadError] = useState("");
  const [sending, setSending] = useState(false);
  const [pendingSubmit, setPendingSubmit] = useState<PendingChatSubmit | null>(null);
  const [pendingStop, setPendingStop] = useState<PendingStopRequest | null>(null);
  const [interactionThreadId, setInteractionThreadId] = useState<string | null>(null);
  const [selectionLoading, setSelectionLoading] = useState<ChatConversation | null>(null);
  const [boundGeneration, setBoundGeneration] = useState(0);
  const transcriptEnd = useRef<HTMLDivElement | null>(null);
  const selectionRequest = useRef(0);
  const draftRevision = useRef(0);
  const serverDraftRevision = useRef(0);
  const draftSaveRequest = useRef(0);
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

  const updateConversationIfCurrentRun = useCallback((next: ChatConversation, owner: SelectionOwner, expectedRunId: string | null): void => {
    cacheConversation(next);
    if (isCurrentOwner(owner)) {
      setConversation((current) => (
        current?.id === owner.conversationId && (current.current_run_id ?? null) === expectedRunId
          ? next
          : current
      ));
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

  const refreshDeployments = useCallback((): void => {
    void api.deployments()
      .then((next) => {
        setDeployments(next);
        setDeploymentId((current) => current || preferredChatDeploymentId(next, current));
      })
      .catch(() => {
        // Chat state remains authoritative for the run; a later refresh will update model status.
      });
  }, []);

  const clearPendingSubmit = useCallback((pending: PendingChatSubmit): void => {
    setPendingSubmit((current) => (current?.id === pending.id ? null : current));
    setPendingStop((current) => (current?.id === pending.id ? null : current));
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
      api.chatConversations(includeArchived),
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
  }, [includeArchived]);

  useEffect(() => {
    const query = searchQuery.trim();
    if (!query) {
      setSearchResults(null);
      return;
    }
    let cancelled = false;
    const timer = setTimeout(() => {
      void api.searchChatConversations(query, includeArchived)
        .then((results) => {
          if (!cancelled) {
            setSearchResults(newestConversationFirst(results.map((item) => item.conversation as ChatConversation)));
          }
        })
        .catch((error: unknown) => {
          if (!cancelled) {
            setMessage(errorMessage(error));
          }
        });
    }, 250);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [includeArchived, searchQuery]);

  useEffect(() => {
    if (!conversation) {
      serverDraftRevision.current = 0;
      return;
    }
    serverDraftRevision.current = conversation.draft?.revision ?? 0;
  }, [conversation?.id, conversation?.draft?.revision]);

  useEffect(() => {
    if (!conversation || selectionLoading || sending || pendingSubmit) {
      return;
    }
    const content = task;
    if ((conversation.draft?.content ?? "") === content) {
      return;
    }
    const revision = serverDraftRevision.current;
    const requestId = draftSaveRequest.current + 1;
    draftSaveRequest.current = requestId;
    const timer = setTimeout(() => {
      void api.updateChatDraft(conversation.id, {
        content,
        expected_revision: revision,
        intended_config: {
          deployment_id: deploymentId,
          profile_id: profileId && profileId !== "!none" ? profileId : null,
          inherit_deployment_settings: profileId !== "!none",
          project_path: projectPath.trim() || null,
          embedding_deployment_id: embeddingDeploymentId || null,
        },
      }).then((next) => {
        if (
          draftSaveRequest.current !== requestId ||
          selectionRequest.current !== activeOwner.current.generation ||
          activeOwner.current.conversationId !== conversation.id ||
          task !== content
        ) {
          cacheConversation(next);
          return;
        }
        serverDraftRevision.current = next.draft?.revision ?? serverDraftRevision.current;
        cacheConversation(next);
        if (activeOwner.current.conversationId === conversation.id) {
          setConversation(next);
        }
      }).catch((error: unknown) => {
        if (draftSaveRequest.current === requestId && activeOwner.current.conversationId === conversation.id) {
          setMessage(errorMessage(error));
        }
      });
    }, 450);
    return () => {
      clearTimeout(timer);
    };
  }, [
    cacheConversation,
    conversation,
    deploymentId,
    embeddingDeploymentId,
    pendingSubmit,
    profileId,
    projectPath,
    selectionLoading,
    sending,
    task,
  ]);

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
    setPendingStop(null);
    setSending(false);
    serverDraftRevision.current = 0;
    updateTask("");
    setMessage("");
  }

  const selectionBusy = Boolean(selectionLoading);
  const hasPendingCancelInput = Boolean(conversation?.pending_cancel_input_ids?.length);
  const runBusy = (conversation?.current_run ? isAgentRunLive(conversation.current_run.status) : false) || Boolean(pendingSubmit) || hasPendingCancelInput;
  const pendingSubmissionActive = Boolean(
    pendingSubmit &&
    conversation?.id === pendingSubmit.conversation_id &&
    interactionThreadId === pendingSubmit.thread_id &&
    boundGeneration === pendingSubmit.selection_generation,
  );
  const localPendingStopActive = Boolean(
    pendingStop &&
    pendingSubmit &&
    pendingStop.id === pendingSubmit.id &&
    pendingStop.conversation_id === pendingSubmit.conversation_id &&
    conversation?.id === pendingStop.conversation_id &&
    interactionThreadId === pendingStop.thread_id &&
    boundGeneration === pendingStop.selection_generation,
  );
  const pendingStopActive = localPendingStopActive || hasPendingCancelInput;
  const selectedProfile = profiles.find((profile) => profile.id === profileId) ?? null;
  const pendingInterrupt = visiblePendingInterrupt(conversation?.current_run);
  const embedderDeployments = deployments.filter((item) => isDeclaredEmbedder(item));
  const chatDeployments = deployments.filter((item) => !isDeclaredEmbedder(item));
  const modelChoices = chatDeployments.length > 0 ? chatDeployments : deployments;
  const selectedDeployment = modelChoices.find((item) => item.id === deploymentId);
  const missingDeployment = Boolean(deploymentId && !selectedDeployment);
  const tools = conversation?.enabled_tools ?? enabledTools;
  const deployHealthNotice = chatDeployHealthNotice(conversation, selectedDeployment);
  const canObserveInteraction = Boolean(interactionThreadId && conversation);
  const destinations: WorkbenchTab[] = ["chat", "models", "knowledge", "agent-run", "lab"];
  const visibleConversations = searchResults ?? conversations;
  const generalConversations = newestConversationFirst(visibleConversations.filter((item) => areaKind(item) !== "project"));
  const projectGroups = newestConversationFirst(visibleConversations.filter((item) => areaKind(item) === "project")).reduce(
    (groups, item) => {
      const key = areaKey(item);
      const existing = groups.get(key) ?? [];
      groups.set(key, [...existing, item]);
      return groups;
    },
    new Map<string, ChatConversation[]>(),
  );
  const currentArea = selectionLoading ? areaLabel(selectionLoading) : areaLabel(conversation);

  function chooseConversation(item: ChatConversation): void {
    const requestId = selectionRequest.current + 1;
    selectionRequest.current = requestId;
    activeOwner.current = { conversationId: null, threadId: null, generation: requestId };
    setBoundGeneration(requestId);
    setConversation(null);
    setInteractionThreadId(null);
    setSelectionLoading(item);
    setPendingSubmit(null);
    setPendingStop(null);
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
        serverDraftRevision.current = next.draft?.revision ?? 0;
        draftRevision.current += 1;
        setTask(next.draft?.content ?? "");
        setMessage("");
      })
      .catch((error: unknown) => {
        if (selectionRequest.current === requestId) {
          setSelectionLoading(null);
          fail(error);
        }
      });
  }

  function applyConversationUpdate(next: ChatConversation): void {
    cacheConversation(next);
    if (conversation?.id === next.id) {
      setConversation(next);
    }
  }

  function renameConversation(item: ChatConversation): void {
    const nextTitle = window.prompt("Rename conversation", conversationTitle(item))?.trim();
    if (!nextTitle) {
      return;
    }
    void api.renameChatConversation(item.id, nextTitle)
      .then(applyConversationUpdate)
      .catch(fail);
  }

  function setConversationArchived(item: ChatConversation, archived: boolean): void {
    const request = archived ? api.archiveChatConversation(item.id, true) : api.reopenChatConversation(item.id);
    void request
      .then((next) => {
        applyConversationUpdate(next);
        if (archived && conversation?.id === item.id && !includeArchived) {
          startFresh();
        }
        if (!archived) {
          setIncludeArchived(true);
        }
      })
      .catch(fail);
  }

  function stopCurrentWork(): void {
    if (!conversation || !interactionThreadId) {
      return;
    }
    const owner = {
      conversationId: conversation.id,
      threadId: interactionThreadId,
      generation: boundGeneration,
    };
    if (pendingSubmissionActive && pendingSubmit) {
      const stopRequest = {
        id: pendingSubmit.id,
        conversation_id: pendingSubmit.conversation_id,
        thread_id: pendingSubmit.thread_id,
        selection_generation: pendingSubmit.selection_generation,
      };
      setPendingStop(stopRequest);
      void api.cancelChat(conversation.id, pendingSubmit.id)
        .then((next) => {
          if (!isCurrentOwner(owner)) {
            cacheConversation(next);
            return;
          }
          cacheConversation(next);
          setConversation(next);
          // This response acknowledges the stop claim. The submission owner
          // still resolves acceptance or failure while model loading unwinds.
        })
        .catch((error: unknown) => {
          if (isCurrentOwner(owner)) {
            setPendingStop((current) => (current?.id === stopRequest.id ? null : current));
            fail(error);
          }
        });
      return;
    }
    if (!conversation.current_run) {
      return;
    }
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
  }

  async function sendTurn(): Promise<void> {
    const text = task.trim();
    if (!text || !selectedDeployment || selectionBusy || sending || (runBusy && !conversation)) {
      return;
    }
    const requestId = selectionRequest.current;
    const originConversationId = conversation?.id ?? null;
    const capturedDraftRevision = draftRevision.current;
    setSending(true);
    setMessage("");
    try {
      const refs = knowledgePayload(knowledgeEntries, selectedKnowledgeIds);
      const payload = {
        task: text,
        deployment_id: deploymentId,
        profile_id: profileId && profileId !== "!none" ? profileId : null,
        inherit_deployment_settings: profileId !== "!none",
        project_path: projectPath.trim() || null,
        workspace_id: null,
        embedding_deployment_id: embeddingDeploymentId || null,
        ...refs,
      };
      if (runBusy && conversation) {
        const queued = await api.enqueueChatTurn(conversation.id, payload);
        if (selectionRequest.current !== requestId || activeOwner.current.conversationId !== conversation.id) {
          cacheConversation(queued);
          return;
        }
        cacheConversation(queued);
        setConversation(queued);
        if (draftRevision.current === capturedDraftRevision) {
          draftRevision.current += 1;
          setTask("");
        }
        return;
      }
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
        ...payload,
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

  function renderConversationButton(item: ChatConversation) {
    return (
      <div className={item.archived ? "conversation-row archived" : "conversation-row"}>
        <button
          type="button"
          className={item.id === conversation?.id || item.id === selectionLoading?.id ? "nav-item active" : "nav-item"}
          onClick={() => chooseConversation(item)}
        >
          <span className="nav-item-title">{conversationTitle(item)}</span>
          <span className="nav-item-meta">
            {item.archived ? "Archived · " : ""}{formatWhen(item.updated_at)}
          </span>
        </button>
        <div className="conversation-actions" aria-label={`${conversationTitle(item)} actions`}>
          <button type="button" onClick={() => renameConversation(item)}>Rename</button>
          {item.archived ? (
            <button type="button" onClick={() => setConversationArchived(item, false)}>Reopen</button>
          ) : (
            <button type="button" onClick={() => setConversationArchived(item, true)}>Archive</button>
          )}
        </div>
      </div>
    );
  }

  useEffect(() => {
    if (!attentionConversationId || attentionConversationId === conversation?.id) {
      return;
    }
    let cancelled = false;
    void api.chatConversation(attentionConversationId)
      .then((next) => {
        if (!cancelled) {
          chooseConversation(next);
        }
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          fail(error);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [attentionConversationId, conversation?.id]);

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
    <section className={sidebarCollapsed ? "chat-layout chat-sidebar-collapsed" : "chat-layout"}>
      <aside className="chat-list" aria-label="Chat workspace">
        <div className="chat-brand">
          <div>
            <p className="eyebrow">Local AI Workbench</p>
            <h1>{productName}</h1>
          </div>
          <button
            type="button"
            className="nav-collapse"
            aria-label={sidebarCollapsed ? "Expand chat sidebar" : "Collapse chat sidebar"}
            aria-expanded={!sidebarCollapsed}
            onClick={() => setSidebarCollapsed((value) => !value)}
          >
            {sidebarCollapsed ? "›" : "‹"}
          </button>
        </div>
        <nav className="chat-destinations" aria-label="Destinations">
          {destinations.map((item) => (
            <button
              key={item}
              type="button"
              className={item === activeTab ? "tab destination-current" : "tab"}
              aria-label={tabLabel(item)}
              title={tabLabel(item)}
              onClick={() => onNavigate?.(item)}
            >
              {sidebarCollapsed ? tabLabel(item).slice(0, 1) : tabLabel(item)}
            </button>
          ))}
        </nav>
        <div className="chat-list-head">
          <h2>Chats</h2>
          <button type="button" onClick={startFresh}>
            New
          </button>
        </div>
        <label className="chat-search">
          Search
          <input
            value={searchQuery}
            onChange={(event) => setSearchQuery(event.target.value)}
            placeholder="Search titles and messages"
          />
        </label>
        <label className="check-row include-archived">
          <input
            type="checkbox"
            checked={includeArchived}
            onChange={(event) => setIncludeArchived(event.target.checked)}
          />
          Show archived
        </label>
        {visibleConversations.length === 0 ? (
          <p className="hint">{searchQuery.trim() ? "No matching conversations." : "No conversations yet."}</p>
        ) : (
          <div className="chat-groups">
            <section className="chat-group">
              <h3>General</h3>
              <ul className="nav-list">
                {generalConversations.map((item) => (
                  <li key={item.id}>{renderConversationButton(item)}</li>
                ))}
              </ul>
            </section>
            {[...projectGroups.entries()].map(([project, items]) => (
              <details key={project} className="chat-group" open>
                <summary>{areaLabel(items[0])}</summary>
                <ul className="nav-list">
                  {items.map((item) => (
                    <li key={item.id}>{renderConversationButton(item)}</li>
                  ))}
                </ul>
              </details>
            ))}
          </div>
        )}
        <div className="sidebar-footer">
          <label>
            Theme
            <select value={presentation.theme} onChange={(event) => onThemeChange?.(event.target.value as PresentationTheme)}>
              <option value="system">System</option>
              <option value="light">Light</option>
              <option value="dark">Dark</option>
            </select>
          </label>
          {backendStatus ? <p className={backendOk === false ? "notice notice-error" : "hint"}>{backendStatus}</p> : null}
        </div>
      </aside>

      <div className="chat-main">
        <header className="chat-header">
          <div>
            <p className="eyebrow">{currentArea} chat</p>
            <h2>{conversation ? conversationTitle(conversation) : selectionLoading ? conversationTitle(selectionLoading) : "New conversation"}</h2>
          </div>
          <div className="chat-header-status">
            <span className="badge">{conversation?.project_path ? "Project session" : "General session"}</span>
            <span className="badge">Context unavailable</span>
            <span className="badge">tok/s unavailable</span>
          </div>
        </header>
        <div className="chat-setup">
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
                readOnly={Boolean(conversation)}
                onChange={(event) => setProjectPath(event.target.value)}
                placeholder="Leave empty to chat without a project"
              />
            </label>
          </div>
          {missingDeployment ? (
            <Notice tone="warn">This conversation's model connection is unavailable. Its history is preserved. Choose a model before sending another message.</Notice>
          ) : null}
          {conversation ? (
            <p className="hint">This conversation stays in its original area. Start a new conversation to choose another project.</p>
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
            {conversation ? `Tools: ${tools.length ? tools.join(", ") : "none"}` : "Available tools depend on the project you choose."}
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
          ) : canObserveInteraction && interactionThreadId && conversation ? (
            <ChatInteractionStream
              key={`${conversation.id}:${interactionThreadId}`}
              threadId={interactionThreadId}
              selectionGeneration={boundGeneration}
              conversation={conversation}
              pendingSubmit={pendingSubmit}
              clearPendingSubmit={clearPendingSubmit}
              updateConversation={updateConversation}
              updateConversationIfCurrentRun={updateConversationIfCurrentRun}
              updateConversationForRun={updateConversationForRun}
              clearSubmittedDraft={clearSubmittedDraft}
              refreshDeployments={refreshDeployments}
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
              Working… {pendingStopActive ? (
                <StatusBadge label="Stopping submission" tone="warn" />
              ) : pendingSubmissionActive ? (
                <StatusBadge label="Loading model" tone="live" />
              ) : (
                <StatusBadge status={conversation?.current_run?.status} />
              )} This can continue if
              the window disconnects.
            </p>
          ) : null}
          <div ref={transcriptEnd} />
        </div>

        {canObserveInteraction && conversation?.current_run ? (
          <details className="card chat-run-details">
            <summary>
              Run progress <StatusBadge status={conversation.current_run.status} />
            </summary>
            <RunProgress
              run={conversation.current_run}
              onCancel={stopCurrentWork}
            />
          </details>
        ) : null}

        {deployHealthNotice && !runBusy ? (
          <Notice tone={deployHealthNotice.tone}>
            {deployHealthNotice.message}
          </Notice>
        ) : null}
        {message && message !== conversation?.deploy_health?.message && !liveRunId ? (
          <Notice tone="error">{message}</Notice>
        ) : null}

        {conversation?.queue?.length ? (
          <details className="queue-panel" open>
            <summary>Queue</summary>
            <ul className="plain-list">
              {conversation.queue.map((item) => (
                <li key={item.id} className="queue-item">
                  <p>{item.task}</p>
                  <span className="badge">{item.status}{item.pause_reason ? ` · ${item.pause_reason}` : ""}</span>
                  <div className="actions">
                    <button
                      type="button"
                      disabled={item.status === "dispatching"}
                      onClick={() => {
                        const nextTask = window.prompt("Edit queued message", item.task)?.trim();
                        if (!nextTask || !conversation) {
                          return;
                        }
                        void api.updateChatQueueItem(conversation.id, item.id, { task: nextTask })
                          .then(applyConversationUpdate)
                          .catch(fail);
                      }}
                    >
                      Edit
                    </button>
                    <button
                      type="button"
                      disabled={item.status === "dispatching"}
                      onClick={() => {
                        if (!conversation) {
                          return;
                        }
                        void api.removeChatQueueItem(conversation.id, item.id)
                          .then(applyConversationUpdate)
                          .catch(fail);
                      }}
                    >
                      Remove
                    </button>
                  </div>
                </li>
              ))}
            </ul>
          </details>
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
            <button
              type="submit"
              disabled={!selectedDeployment || !task.trim() || selectionBusy || sending}
            >
              {runBusy ? "Queue" : selectionBusy || sending ? "Sending…" : "Send"}
            </button>
            <button
              type="button"
              disabled={!conversation || !runBusy || pendingStopActive}
              onClick={stopCurrentWork}
            >
              {pendingStopActive ? "Stopping…" : "Stop"}
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
