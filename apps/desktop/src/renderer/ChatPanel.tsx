import { useCallback, useEffect, useMemo, useRef, useState, type ComponentProps, type CSSProperties, type RefObject } from "react";
import { PanelResize, usePanelWidth } from "./PanelResize";
import { HoverHelp } from "./HoverHelp";
import { DeleteChatDialog } from "./DeleteChatDialog";

import { api } from "./api";
import { Icon } from "./Icon";
import { AttentionButton } from "./AttentionPanel";
import { ComposerAttachments } from "./ComposerAttachments";
import { LibraryPanel } from "./LibraryPanel";
import { packet03Api } from "./packet03Api";
import { ChatModelControls } from "./ChatModelControls";
import { ChatMeasurements } from "./ChatMeasurements";
import { ChatRetainedFiles, useChatRetainedAssets } from "./ChatRetainedFiles";
import { ChatDraftWriter, sameDraftValue } from "./chatDraftWriter";
import { ChatHistoryActions } from "./ChatHistoryActions";
import { ChatQueuePanel } from "./ChatQueuePanel";
import { ConversationRename } from "./ConversationRename";
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
  submitted_draft_revision?: number | null;
  task: string;
  attachment_ids?: string[];
  presented_tools?: string[];
  per_request_overrides?: Record<string, unknown>;
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
  detailedStreams?: boolean;
  renderMessageFooter?: ComponentProps<typeof AgentMessageFeed>["renderMessageFooter"];
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
  const reconciledSubmissionErrors = useRef(new Set<string>());
  const submissionErrorOwner = useRef<string | null>(null);
  if (pendingSubmit && submissionErrorOwner.current !== pendingSubmit.id) {
    submissionErrorOwner.current = pendingSubmit.id;
    reconciledSubmissionErrors.current.clear();
  }
  return (
    <InteractionStream
      threadId={threadId}
      onError={(error) => {
        if (isCurrentOwner(owner)) {
          const errorText = errorMessage(error);
          if (reconciledSubmissionErrors.current.has(errorText)) return;
          if (
            pendingSubmit &&
            pendingSubmit.conversation_id === owner.conversationId &&
            pendingSubmit.thread_id === owner.threadId &&
            pendingSubmit.selection_generation === owner.generation
          ) {
            reconciledSubmissionErrors.current.add(errorText);
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
          detailedStreams={props.detailedStreams}
          renderMessageFooter={props.renderMessageFooter}
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
  detailedStreams?: boolean;
  renderMessageFooter?: ComponentProps<typeof AgentMessageFeed>["renderMessageFooter"];
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
    if (!run || projectionRunOwned || projectionMatchesPendingSubmit || projectionBlockedByPendingCancel) {
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
  }, [conversation.current_run_id, conversation.id, isCurrentOwner, owner, projectionBlockedByPendingCancel, projectionMatchesPendingSubmit, projectionRunOwned, run, setMessage, updateConversationIfCurrentRun]);

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
      submitted_draft_revision: submittedDraftRevision,
      ...workbench
    } = pendingSubmit;
    void stream
      .submit(
        { messages: [{ type: "human", content: inputTask, id: messageId }] },
        { multitaskStrategy: "reject", metadata: { workbench: { ...workbench, draft_revision: submittedDraftRevision } } },
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
        <AgentMessageFeed messages={projection.messages} toolCalls={projection.toolCalls} incompleteMessageIds={projection.incompleteMessageIds} detailedStreams={props.detailedStreams} renderMessageFooter={props.renderMessageFooter} userMessageText={message => {
          const retained = conversation.transcript.find(item => item.id === message.id && item.role === "user" && item.attachment_ids?.length);
          return retained?.content;
        }} />
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
      return "Workflows";
    case "lab":
      return "Lab";
    case "library":
      return "Library";
    case "attention":
      return "Attention";
    case "settings":
      return "Settings";
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
  onAttentionHandled?: (conversationId: string) => void;
  navigationPreparationRef?: RefObject<(() => Promise<boolean>) | null>;
  backendOk?: boolean | null;
  backendStatus?: string;
  onNavigate?: (tab: WorkbenchTab) => void;
  onPresentationChange?: (settings: PresentationSettings) => void;
  reuseAssetId?: string | null;
  reuseAssetIds?: string[];
  onReuseAssetHandled?: () => void;
  presentation?: PresentationSettings;
  productName?: string;
  navigationCollapsed?: boolean;
  onNavigationCollapsedChange?: (value: boolean) => void;
  navigationWidth?: number;
  onNavigationWidthChange?: (value: number) => void;
}

export function ChatPanel(props: ChatPanelProps = {}) {
  const {
    activeTab = "chat",
    attentionConversationId = null,
    onAttentionHandled,
    backendOk = null,
    backendStatus = "",
    onNavigate,
    presentation = fallbackPresentation,
  } = props;
  const [localCollapsed, setLocalCollapsed] = useState(() => window.innerWidth <= 860);
  const sidebarCollapsed = props.navigationCollapsed ?? localCollapsed;
  const setSidebarCollapsed = (value: boolean) => { setLocalCollapsed(value); props.onNavigationCollapsedChange?.(value); };
  const [localWidth, setLocalWidth] = usePanelWidth("workbench.navigation.width", 232, 190, 380);
  const sidebarWidth = props.navigationWidth ?? localWidth;
  const setSidebarWidth = props.onNavigationWidthChange ?? setLocalWidth;
  const [filesWidth, setFilesWidth] = usePanelWidth("workbench.inspector.width", 380, 280, 720);
  const [filesExpanded, setFilesExpanded] = useState(false);
  const [deletingConversation, setDeletingConversation] = useState<ChatConversation | null>(null);
  const historyMutations = useRef(new Map<string, boolean | "deleted">());
  const [deployments, setDeployments] = useState<Deployment[]>([]);
  const [profiles, setProfiles] = useState<RunProfile[]>([]);
  const [enabledTools, setEnabledTools] = useState<string[]>([]);
  const [deploymentId, setDeploymentId] = useState("");
  const [embeddingDeploymentId, setEmbeddingDeploymentId] = useState("");
  const [profileId, setProfileId] = useState("");
  const [projectPath, setProjectPath] = useState("");
  const [task, setTask] = useState("");
  const [attachmentIds, setAttachmentIds] = useState<string[]>([]);
  const [attachmentsOpen, setAttachmentsOpen] = useState(false);
  const [incomingDrop, setIncomingDrop] = useState<{ id: string; sessionId: string; files: File[] } | null>(null);
  const [fileDragActive, setFileDragActive] = useState(false);
  const [toolsAllowed, setToolsAllowed] = useState(true);
  const [perRequestOverrides, setPerRequestOverrides] = useState<Record<string, unknown>>({});
  const [setupOpen, setSetupOpen] = useState(false);
  const [filesOpen, setFilesOpen] = useState(false);
  const reuseClaim = useRef<string | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [renamingConversationId, setRenamingConversationId] = useState<string | null>(null);
  const [includeArchived, setIncludeArchived] = useState(false);
  const [searchResults, setSearchResults] = useState<ChatConversation[] | null>(null);
  const [conversation, setConversation] = useState<ChatConversation | null>(null);
  const retainedAssets = useChatRetainedAssets(conversation?.id ?? "");
  const [conversations, setConversations] = useState<ChatConversation[]>([]);
  // Search covers retained titles/messages, not draft or streaming progress.
  // Invalidate after branch, rename, deletion, archive or durable turn changes.
  const searchableRevision = useMemo(() => JSON.stringify(conversations.map((item) => [
    item.id, item.title, item.archived, item.transcript.map((message) => message.content),
  ])), [conversations]);
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
  const draftWriter = useRef(new ChatDraftWriter());
  const conversationCreation = useRef<{ generation: number; promise: Promise<ChatConversation> } | null>(null);
  const activeOwner = useRef<{ conversationId: string | null; threadId: string | null; generation: number }>({
    conversationId: null,
    threadId: null,
    generation: 0,
  });

  const cacheConversation = useCallback((next: ChatConversation): void => {
    setConversations((current) => {
      if (historyMutations.current.get(next.id) === "deleted") return current;
      const others = current.filter((item) => item.id !== next.id);
      return [next, ...others];
    });
  }, []);

  const isCurrentOwner = useCallback((owner: SelectionOwner): boolean => (
    historyMutations.current.get(owner.conversationId) !== "deleted" &&
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
    const nextRunId = next.current_run_id ?? next.current_run?.id ?? null;
    const nextRunIndex = next.run_ids.indexOf(nextRunId ?? "");
    const expectedRunIndex = next.run_ids.indexOf(runId);
    const responseMatchesRun = nextRunId === runId || (
      nextRunId !== null &&
      nextRunIndex >= 0 &&
      expectedRunIndex >= 0 &&
      nextRunIndex > expectedRunIndex
    );
    if (!responseMatchesRun) {
      return;
    }
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
    draftWriter.current.accepted(pending.conversation_id, pending.submitted_draft_revision);
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
    setAttachmentIds([]);
    setAttachmentsOpen(false);
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
    setConversations(newestConversationFirst(reconcileHistory(nextConversations)));
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
            setSearchResults(newestConversationFirst(reconcileHistory(results.map((item) => item.conversation as ChatConversation))));
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
  }, [includeArchived, searchQuery, searchableRevision]);

  useEffect(() => {
    if (!conversation) {
      serverDraftRevision.current = 0;
      return;
    }
    serverDraftRevision.current = conversation.draft?.revision ?? 0;
    draftWriter.current.observe(conversation);
  }, [conversation?.id, conversation?.draft?.revision]);

  useEffect(() => {
    if (!conversation || selectionLoading || sending || pendingSubmit) {
      return;
    }
    const content = task;
    const intendedConfig = {
      deployment_id: deploymentId,
      profile_id: profileId && profileId !== "!none" ? profileId : null,
      inherit_deployment_settings: profileId !== "!none",
      project_path: projectPath.trim() || null,
      workspace_id: conversation.workspace_id ?? null,
      embedding_deployment_id: embeddingDeploymentId || null,
      presented_tools: toolsAllowed ? null : [],
      per_request_overrides: perRequestOverrides,
      ...knowledgePayload(knowledgeEntries, selectedKnowledgeIds),
    };
    if ((conversation.draft?.content ?? "") === content && sameDraftValue(conversation.draft?.attachment_ids ?? [], attachmentIds) && sameDraftValue(conversation.draft?.intended_config ?? {}, intendedConfig)) {
      return;
    }
    const revision = serverDraftRevision.current;
    const requestId = draftSaveRequest.current + 1;
    draftSaveRequest.current = requestId;
    const timer = setTimeout(() => {
      void draftWriter.current.save(conversation, {
        content,
        attachment_ids: attachmentIds,
        expected_revision: revision,
        intended_config: intendedConfig,
      }).then((next) => {
        // A draft acknowledgement owns only the draft. A newer stream/run may
        // have arrived while this response was in flight.
        setConversations(current => current.map(item => item.id === next.id && (item.draft?.revision ?? 0) <= (next.draft?.revision ?? 0) ? { ...item, draft: next.draft } : item));
        if (activeOwner.current.conversationId === conversation.id) {
          serverDraftRevision.current = Math.max(serverDraftRevision.current, next.draft?.revision ?? 0);
        }
        if (
          draftSaveRequest.current !== requestId ||
          selectionRequest.current !== activeOwner.current.generation ||
          activeOwner.current.conversationId !== conversation.id ||
          task !== content
        ) {
          return;
        }
        if (activeOwner.current.conversationId === conversation.id) {
          setConversation(current => current?.id === next.id ? { ...current, draft: next.draft } : current);
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
    attachmentIds,
    toolsAllowed,
    perRequestOverrides,
    selectedKnowledgeIds,
    knowledgeEntries,
  ]);

  const liveRunId =
    conversation?.current_run && isAgentRunLive(conversation.current_run.status)
      ? conversation.current_run.id
      : null;

  const transcript = conversation ? displayedTranscript(conversation) : [];

  useEffect(() => {
    if (conversation?.current_run && !isAgentRunLive(conversation.current_run.status)) retainedAssets.refresh();
  }, [conversation?.current_run?.id, conversation?.current_run?.status]);

  useEffect(() => {
    transcriptEnd.current?.scrollIntoView({ block: "end" });
  }, [transcript.length, liveRunId]);

  function fail(error: unknown): void {
    setMessage(errorMessage(error));
  }

  function startFresh(): void {
    selectionRequest.current += 1;
    conversationCreation.current = null;
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
    setAttachmentIds([]);
    setAttachmentsOpen(false);
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
  const destinations: WorkbenchTab[] = ["chat", "models", "library", "knowledge", "agent-run", "lab", "attention", "settings"];
  const visibleConversations = reconcileHistory(searchResults ?? conversations).filter(item => includeArchived || !item.archived);
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
    void persistBeforeLeaving().then(() => selectConversation(item)).catch(fail);
  }

  function selectConversation(item: ChatConversation): void {
    if (historyMutations.current.get(item.id) === "deleted") return;
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
        if (selectionRequest.current !== requestId || historyMutations.current.get(item.id) === "deleted") {
          return;
        }
        cacheConversation(next);
        const registered = await api.registerAgentInteractionThread({
          source_surface: "chat",
          conversation_id: next.id,
        });
        if (selectionRequest.current !== requestId || historyMutations.current.get(item.id) === "deleted") {
          return;
        }
        activeOwner.current = { conversationId: next.id, threadId: registered.thread_id, generation: requestId };
        setBoundGeneration(requestId);
        setConversation(next);
        setInteractionThreadId(registered.thread_id);
        setSelectionLoading(null);
        const draftConfig = next.draft?.intended_config ?? {};
        setDeploymentId(typeof draftConfig.deployment_id === "string" ? draftConfig.deployment_id : next.deployment_id);
        setEmbeddingDeploymentId(typeof draftConfig.embedding_deployment_id === "string" ? draftConfig.embedding_deployment_id : next.embedding_deployment_id ?? "");
        setProfileId(typeof draftConfig.profile_id === "string" ? draftConfig.profile_id : draftConfig.inherit_deployment_settings === false ? "!none" : next.profile_id ?? (next.inherit_deployment_settings === false ? "!none" : ""));
        setToolsAllowed(!Array.isArray(draftConfig.presented_tools) || draftConfig.presented_tools.length > 0);
        setPerRequestOverrides(draftConfig.per_request_overrides && typeof draftConfig.per_request_overrides === "object" ? draftConfig.per_request_overrides as Record<string, unknown> : {});
        setProjectPath(next.project_path ?? "");
        setSelectedKnowledgeIds([
          ...(next.memory_version_refs ?? []),
          ...(next.skill_version_refs ?? []),
          ...(next.protected_instruction_version_refs ?? []),
        ]);
        serverDraftRevision.current = next.draft?.revision ?? 0;
        draftRevision.current += 1;
        setTask(next.draft?.content ?? "");
        setAttachmentIds(next.draft?.attachment_ids ?? []);
        setAttachmentsOpen(Boolean(next.draft?.attachment_ids?.length));
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
    if (historyMutations.current.get(next.id) === "deleted") return;
    cacheConversation(next);
    setConversation(current => current?.id === next.id ? next : current);
  }

  function chooseDeployment(nextId: string): void {
    if (nextId === deploymentId) return;
    setDeploymentId(nextId);
    setPerRequestOverrides(current => {
      const next = { ...current };
      delete next.reasoning;
      delete next.reasoning_effort;
      delete next.reasoning_format;
      return next;
    });
  }

  function setConversationArchived(item: ChatConversation, archived: boolean): void {
    const saveDraft = archived && activeOwner.current.conversationId === item.id
      ? persistBeforeLeaving()
      : Promise.resolve();
    const request = saveDraft.then(() => historyMutations.current.get(item.id) === "deleted"
      ? null
      : archived ? api.archiveChatConversation(item.id, true) : api.reopenChatConversation(item.id));
    void request
      .then((next) => {
        if (!next) return;
        if (historyMutations.current.get(next.id) === "deleted") return;
        historyMutations.current.set(next.id, next.archived ?? archived);
        setSearchResults(current => current?.map(value => value.id === next.id ? next : value) ?? null);
        applyConversationUpdate(next);
        if (archived && activeOwner.current.conversationId === item.id && !includeArchived) {
          startFresh();
        }
        if (!archived) {
          setIncludeArchived(true);
        }
      })
      .catch(fail);
  }

  function reconcileHistory(items: ChatConversation[]): ChatConversation[] {
    return items.filter(item => historyMutations.current.get(item.id) !== "deleted").map(item => {
      const archived = historyMutations.current.get(item.id);
      return typeof archived === "boolean" ? { ...item, archived } : item;
    });
  }

  function removeConversation(id: string): void {
    historyMutations.current.set(id, "deleted");
    setConversations(current => current.filter(item => item.id !== id));
    setSearchResults(current => current?.filter(item => item.id !== id) ?? null);
    if (activeOwner.current.conversationId === id || selectionLoading?.id === id || conversation?.id === id) startFresh();
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
    if ((!text && !attachmentIds.length) || !selectedDeployment || selectionBusy || sending || (runBusy && !conversation) || (pendingSubmit && draftRevision.current === pendingSubmit.draft_revision)) {
      return;
    }
    const requestId = selectionRequest.current;
    const originConversationId = conversation?.id ?? null;
    const capturedDraftRevision = draftRevision.current;
    setSending(true);
    setMessage("");
    try {
      const savedDraft = await persistBeforeLeaving();
      const refs = knowledgePayload(knowledgeEntries, selectedKnowledgeIds);
      const payload = {
        task: text,
        draft_revision: savedDraft?.draft?.revision ?? conversation?.draft?.revision ?? null,
        attachment_ids: attachmentIds,
        per_request_overrides: perRequestOverrides,
        ...(toolsAllowed ? {} : { presented_tools: [] }),
        deployment_id: deploymentId,
        profile_id: profileId && profileId !== "!none" ? profileId : null,
        inherit_deployment_settings: profileId !== "!none",
        project_path: projectPath.trim() || null,
        workspace_id: conversation?.workspace_id ?? null,
        embedding_deployment_id: embeddingDeploymentId || null,
        ...refs,
      };
      if (runBusy && conversation) {
        const queued = await api.enqueueChatTurn(conversation.id, payload);
        draftWriter.current.observe(queued);
        if (selectionRequest.current !== requestId || activeOwner.current.conversationId !== conversation.id) {
          cacheConversation(queued);
          return;
        }
        cacheConversation(queued);
        setConversation(queued);
        if (draftRevision.current === capturedDraftRevision) {
          draftRevision.current += 1;
          setTask("");
          setAttachmentIds([]);
          setAttachmentsOpen(false);
        }
        return;
      }
      const created =
        savedDraft ?? conversation ??
        (await createDraftConversation());
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
      const { draft_revision: submittedDraftRevision, ...submissionPayload } = payload;
      setPendingSubmit({
        id: crypto.randomUUID(),
        conversation_id: created.id,
        thread_id: threadId,
        selection_generation: generation,
        draft_revision: capturedDraftRevision,
        submitted_draft_revision: submittedDraftRevision,
        ...submissionPayload,
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

  function createDraftConversation(): Promise<ChatConversation> {
    const generation = selectionRequest.current;
    if (conversationCreation.current?.generation === generation) return conversationCreation.current.promise;
    const promise = api.createChatConversation({
      deployment_id: deploymentId,
      profile_id: profileId && profileId !== "!none" ? profileId : undefined,
      inherit_deployment_settings: profileId !== "!none",
      project_path: projectPath.trim() || undefined,
      embedding_deployment_id: embeddingDeploymentId || undefined,
      ...knowledgePayload(knowledgeEntries, selectedKnowledgeIds),
    }).catch(error => {
      if (conversationCreation.current?.promise === promise) conversationCreation.current = null;
      throw error;
    });
    conversationCreation.current = { generation, promise };
    return promise;
  }

  async function persistBeforeLeaving(): Promise<ChatConversation | null> {
    if (selectionLoading || sending || (pendingSubmit && draftRevision.current === pendingSubmit.draft_revision)) return null;
    if (!conversation && (!task.trim() && !attachmentIds.length || !selectedDeployment)) return null;
    const target = conversation ?? await createDraftConversation();
    const payload = {
      content: task,
      attachment_ids: attachmentIds,
      intended_config: {
        deployment_id: deploymentId,
        profile_id: profileId && profileId !== "!none" ? profileId : null,
        inherit_deployment_settings: profileId !== "!none",
        project_path: projectPath.trim() || null,
        workspace_id: target.workspace_id ?? null,
        embedding_deployment_id: embeddingDeploymentId || null,
        presented_tools: toolsAllowed ? null : [],
        per_request_overrides: perRequestOverrides,
        ...knowledgePayload(knowledgeEntries, selectedKnowledgeIds),
      },
    };
    if ((target.draft?.content ?? "") === payload.content && sameDraftValue(target.draft?.attachment_ids ?? [], payload.attachment_ids) && sameDraftValue(target.draft?.intended_config ?? {}, payload.intended_config)) return target;
    const saved = await draftWriter.current.save(target, payload);
    cacheConversation(saved);
    return saved;
  }

  function navigateAway(tab: WorkbenchTab): void {
    void persistBeforeLeaving().then(() => onNavigate?.(tab)).catch(fail);
  }

  useEffect(() => {
    if (!props.navigationPreparationRef) return;
    props.navigationPreparationRef.current = async () => {
      const selection = selectionRequest.current;
      try {
        await persistBeforeLeaving();
        return selectionRequest.current === selection;
      } catch (error) {
        fail(error);
        return false;
      }
    };
  });

  useEffect(() => () => {
    if (props.navigationPreparationRef) props.navigationPreparationRef.current = null;
  }, [props.navigationPreparationRef]);

  function startFreshAfterSaving(): void {
    void persistBeforeLeaving().then(startFresh).catch(fail);
  }

  useEffect(() => {
    if (conversation || !task.trim() || !selectedDeployment || sending || selectionBusy) return;
    const generation = selectionRequest.current;
    const timer = setTimeout(() => {
      void createDraftConversation().then(async created => {
        cacheConversation(created);
        if (selectionRequest.current !== generation || activeOwner.current.conversationId) return;
        const registered = await api.registerAgentInteractionThread({ source_surface: "chat", conversation_id: created.id });
        if (selectionRequest.current !== generation || activeOwner.current.conversationId) return;
        activeOwner.current = { conversationId: created.id, threadId: registered.thread_id, generation };
        setBoundGeneration(generation);
        setInteractionThreadId(registered.thread_id);
        setConversation(created);
      }).catch(error => { if (selectionRequest.current === generation) fail(error); });
    }, 450);
    return () => clearTimeout(timer);
  }, [conversation?.id, task, selectedDeployment?.id, sending, selectionBusy]);

  async function openAttachments(files?: File[]): Promise<void> {
    if (conversation) {
      setAttachmentsOpen(value => files ? true : !value);
      if (files) setIncomingDrop({ id: crypto.randomUUID(), sessionId: conversation.id, files });
      return;
    }
    if (!selectedDeployment || sending || selectionBusy) return;
    const generation = selectionRequest.current;
    setSending(true);
    try {
      const created = await createDraftConversation();
      cacheConversation(created);
      if (generation !== selectionRequest.current) return;
      const registered = await api.registerAgentInteractionThread({ source_surface: "chat", conversation_id: created.id });
      if (generation !== selectionRequest.current) return;
      activeOwner.current = { conversationId: created.id, threadId: registered.thread_id, generation };
      setBoundGeneration(generation);
      setInteractionThreadId(registered.thread_id);
      setConversation(created);
      setAttachmentsOpen(true);
      if (files) setIncomingDrop({ id: crypto.randomUUID(), sessionId: created.id, files });
    } catch (error) {
      if (generation === selectionRequest.current) fail(error);
    } finally {
      if (generation === selectionRequest.current) setSending(false);
    }
  }

  function renderConversationButton(item: ChatConversation) {
    return (
      <div className={item.archived ? "conversation-row archived" : "conversation-row"}>
        {renamingConversationId === item.id ? <ConversationRename
          key={item.id}
          conversation={item}
          onRename={async title => {
            const next = await api.renameChatConversation(item.id, title);
            applyConversationUpdate(next);
            setRenamingConversationId(current => current === item.id ? null : current);
          }}
          onCancel={() => setRenamingConversationId(null)}
        /> : <>
        <button
          type="button"
          className={item.id === conversation?.id || item.id === selectionLoading?.id ? "nav-item active" : "nav-item"}
          title={`${conversationTitle(item)} · ${formatWhen(item.updated_at)}`}
          onClick={() => chooseConversation(item)}
        >
          <span className="nav-item-title">{conversationTitle(item)}</span>
          <span className="nav-item-meta">
            {item.archived ? "Archived · " : ""}{formatWhen(item.updated_at)}
          </span>
        </button>
        <div className="conversation-actions" aria-label={`${conversationTitle(item)} actions`}>
          <button type="button" className="icon-button" aria-label="Rename chat" title="Rename chat" onClick={() => setRenamingConversationId(item.id)}><Icon name="edit" size={14} /></button>
          {item.archived ? (
            <button type="button" className="icon-button" aria-label="Reopen chat" title="Reopen chat" onClick={() => setConversationArchived(item, false)}><Icon name="restore" size={14} /></button>
          ) : (
            <button type="button" className="icon-button" aria-label="Archive chat" title="Archive chat" onClick={() => setConversationArchived(item, true)}><Icon name="archive" size={14} /></button>
          )}
          <button type="button" className="icon-button" aria-label="Delete chat" title="Delete chat" onClick={() => setDeletingConversation(item)}><Icon name="trash" size={14} /></button>
        </div>
        </>}
      </div>
    );
  }

  useEffect(() => {
    if (!attentionConversationId) return;
    if (attentionConversationId === conversation?.id || historyMutations.current.get(attentionConversationId) === "deleted") {
      onAttentionHandled?.(attentionConversationId);
      return;
    }
    let cancelled = false;
    const requestedSelection = selectionRequest.current;
    void api.chatConversation(attentionConversationId)
      .then((next) => {
        if (!cancelled && selectionRequest.current === requestedSelection && historyMutations.current.get(attentionConversationId) !== "deleted") {
          chooseConversation(next);
        }
      })
      .catch((error: unknown) => {
        if (!cancelled && selectionRequest.current === requestedSelection && historyMutations.current.get(attentionConversationId) !== "deleted") {
          fail(error);
        }
      })
      .finally(() => {
        if (!cancelled) onAttentionHandled?.(attentionConversationId);
      });
    return () => {
      cancelled = true;
    };
  }, [attentionConversationId, onAttentionHandled]);

  useEffect(() => {
    const assetIds = props.reuseAssetIds?.length ? props.reuseAssetIds : props.reuseAssetId ? [props.reuseAssetId] : [];
    const claim = assetIds.join(":");
    if (!assetIds.length || !selectedDeployment || reuseClaim.current === claim || sending || selectionBusy) return;
    if (!conversation) {
      void openAttachments();
      return;
    }
    reuseClaim.current = claim;
    const owner = { ...activeOwner.current };
    void packet03Api.reuseAssets({ asset_ids: assetIds, session_id: conversation.id, allow_cross_session_reuse: true }).then(() => {
      if (activeOwner.current.conversationId !== owner.conversationId || activeOwner.current.generation !== owner.generation) return;
      draftRevision.current += 1;
      setAttachmentIds(current => [...new Set([...current, ...assetIds])]);
      setAttachmentsOpen(true);
    }).catch(fail).finally(() => props.onReuseAssetHandled?.());
  }, [props.reuseAssetId, props.reuseAssetIds, conversation?.id, selectedDeployment?.id, sending, selectionBusy]);

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
    <section className={sidebarCollapsed ? "chat-layout chat-sidebar-collapsed" : "chat-layout"} style={{ "--navigation-width": `${sidebarWidth}px`, "--inspector-width": `${filesWidth}px` } as CSSProperties}>
      {deletingConversation ? <DeleteChatDialog key={deletingConversation.id} conversation={deletingConversation} onClose={() => setDeletingConversation(null)} onDeleted={removeConversation} /> : null}
      <aside className="chat-list" aria-label="Chat workspace">
        <div className="chat-brand">
          <div>
            <h1>Workbench</h1>
          </div>
          <button
            type="button"
            className="nav-collapse"
            aria-label={sidebarCollapsed ? "Expand chat sidebar" : "Collapse chat sidebar"}
            aria-expanded={!sidebarCollapsed}
            onClick={() => setSidebarCollapsed(!sidebarCollapsed)}
          >
            <Icon name="panel" size={18} />
          </button>
        </div>
        <button type="button" className="new-chat-button" aria-label="New chat" title="New chat" onClick={startFreshAfterSaving}><Icon name="edit" size={18} /><span>New chat</span></button>
        <nav className="chat-destinations" aria-label="Destinations">
          {destinations.map((item) => item === "attention" ? <AttentionButton key={item} collapsed={sidebarCollapsed} onOpen={() => navigateAway("attention")} /> : (
            <button
              key={item}
              type="button"
              className={item === activeTab ? "tab destination-current" : "tab"}
              aria-label={tabLabel(item)}
              title={tabLabel(item)}
              onClick={() => navigateAway(item)}
            >
              <Icon name={item} /><span className="destination-label">{tabLabel(item)}</span>
            </button>
          ))}
        </nav>
        <div className="chat-list-head">
          <h2>Conversations</h2>
          <label className="archive-filter" title="Include archived chats"><input type="checkbox" aria-label="Show archived" checked={includeArchived} onChange={event => setIncludeArchived(event.target.checked)} /><Icon name="archive" size={14} /></label>
        </div>
        <label className="chat-search">
          <span className="sr-only">Search chats</span><Icon name="search" size={15} />
          <input
            value={searchQuery}
            onChange={(event) => setSearchQuery(event.target.value)}
            placeholder="Search chats"
          />
        </label>
        {visibleConversations.length === 0 ? (
          <p className="hint">{searchQuery.trim() ? "No matching conversations." : "No conversations yet."}</p>
        ) : (
          <div className="chat-groups">
            <section className="chat-group">
              <h3>Recent</h3>
              <ul className="nav-list">
                {generalConversations.map((item) => (
                  <li key={item.id}>{renderConversationButton(item)}</li>
                ))}
              </ul>
            </section>
            {[...projectGroups.entries()].map(([project, items]) => (
              <details key={project} className="chat-group" open>
                <summary><Icon name="folder" size={14} />{areaLabel(items[0])}</summary>
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
          <div className="service-indicator" title={backendStatus}><span className={`status-dot${backendOk ? " ready" : ""}`} /><span>{backendOk === false ? "Service unavailable" : "Local"}</span></div>
        </div>
        {!sidebarCollapsed ? <PanelResize label="Resize chat navigation" width={sidebarWidth} onResize={setSidebarWidth} reset={232} /> : null}
      </aside>

      <div className="chat-main"
        onDragEnter={event => {
          if (!Array.from(event.dataTransfer.types).includes("Files")) return;
          event.preventDefault();
          setFileDragActive(true);
        }}
        onDragOver={event => {
          if (!Array.from(event.dataTransfer.types).includes("Files")) return;
          event.preventDefault();
          event.dataTransfer.dropEffect = selectedDeployment && !selectionBusy && !sending ? "copy" : "none";
        }}
        onDragLeave={event => {
          if (!event.currentTarget.contains(event.relatedTarget as Node | null)) setFileDragActive(false);
        }}
        onDrop={event => {
          if (!Array.from(event.dataTransfer.types).includes("Files")) return;
          setFileDragActive(false);
          if (event.defaultPrevented) return;
          event.preventDefault();
          event.stopPropagation();
          if (!selectedDeployment || selectionBusy || sending) {
            setMessage(!selectedDeployment ? "Choose a model before attaching files." : "Wait for the conversation to finish opening or sending, then drop the files again.");
            return;
          }
          const files = Array.from(event.dataTransfer.files);
          if (files.length) void openAttachments(files);
        }}
      >
        {fileDragActive ? <div className="chat-file-drop-indicator" role="status"><Icon name="files" size={28} /><strong>Drop files to attach to this conversation</strong><span>Text and code · up to 1 MB per file</span></div> : null}
        <header className="chat-header">
          <div>
            {conversation?.project_path ? <p className="eyebrow">{currentArea}</p> : null}
            <h2>{conversation ? conversationTitle(conversation) : selectionLoading ? conversationTitle(selectionLoading) : "New conversation"}</h2>
          </div>
          <div className="chat-header-status">
            <button type="button" className="icon-button" aria-label="Conversation setup" title="Conversation setup" aria-expanded={setupOpen} onClick={() => setSetupOpen(value => !value)}><Icon name="tune" /></button>
          </div>
          <button type="button" className="icon-button" aria-label="Files and activity" title="Files and activity" onClick={() => setFilesOpen(value => !value)}><Icon name="files" /></button>
          {conversation ? <details className="history-menu"><summary aria-label="Conversation actions" title="Conversation actions"><Icon name="more" /></summary><div className="history-menu-panel"><ChatHistoryActions
            key={conversation.id}
            conversation={conversation}
            disabled={runBusy || selectionBusy || sending}
            onConversationCreated={(next) => {
              cacheConversation(next);
              if (activeOwner.current.conversationId === conversation.id) chooseConversation(next);
            }}
            onDeleted={removeConversation}
            onError={setMessage}
          /></div></details> : null}
        </header>
        <div className={`chat-workspace${filesOpen ? " files-open" : ""}${filesOpen && filesExpanded ? " files-expanded" : ""}`}>
        <div className="chat-conversation">
        <details className="chat-setup" open={setupOpen} onToggle={(event) => setSetupOpen(event.currentTarget.open)} hidden={!setupOpen}>
          <summary><Icon name="settings" size={16} /> Setup</summary>
          <div className="setup-grid">
            <label>
              <span>Project folder <HoverHelp title="About project folders">File tools work inside this folder. A chat stays with its original project.</HoverHelp></span>
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
            <summary>Knowledge <HoverHelp title="About conversation knowledge">Choose memories and instructions for this chat. Document search needs a running embedding model.</HoverHelp></summary>
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
        </details>

        <div className="transcript" aria-live="polite">
          {deployments.length === 0 && !conversation ? (
            <EmptyState title="Your workspace for local AI">
              <button type="button" onClick={() => navigateAway("models")}><Icon name="plus" size={16} /> Add a model</button>
            </EmptyState>
          ) : selectionLoading ? (
            <EmptyState title="Loading conversation">
              Opening {conversationTitle(selectionLoading)}.
            </EmptyState>
          ) : !conversation && transcript.length === 0 ? (
            <EmptyState title="What are we working on?">
              <button type="button" className="quiet-button" onClick={() => setSetupOpen(true)}><Icon name="folder" size={16} /> Add a project</button>
            </EmptyState>
          ) : canObserveInteraction && interactionThreadId && conversation ? (
            <ChatInteractionStream
              detailedStreams={presentation.detailed_streams}
              renderMessageFooter={(nativeMessage) => {
                const item = conversation.transcript.find(entry => entry.id === nativeMessage.id);
                if (!item) return null;
                const records = retainedAssets.records.filter(asset => item.role === "assistant" ? asset.source_run_id === item.run_id : item.attachment_ids?.includes(asset.id));
                if (!records.length) return null;
                return <ChatRetainedFiles compact records={records} conversationId={conversation.id} currentRunId={item.run_id} currentRunStatus={conversation.current_run?.status} onReuse={ids => {
                  draftRevision.current += 1;
                  setAttachmentIds(current => [...new Set([...current, ...ids])]);
                  setAttachmentsOpen(true);
                }} />;
              }}
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
              )}
            </p>
          ) : null}
          <div ref={transcriptEnd} />
        </div>

        {canObserveInteraction && conversation?.current_run && (isAgentRunLive(conversation.current_run.status) || (!runBusy && conversation.current_run.status === "failed")) ? (
          <details className="card chat-run-details">
            <summary>
              <Icon name="activity" size={14} /> Activity <StatusBadge status={conversation.current_run.status} />
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
        {message && message !== conversation?.deploy_health?.message ? (
          <Notice tone="error">{message}</Notice>
        ) : null}

        {conversation ? <ChatQueuePanel
          key={conversation.id}
          conversation={conversation}
          deployments={modelChoices}
          profiles={profiles}
          disabled={selectionBusy || sending}
          onUpdated={applyConversationUpdate}
          onError={setMessage}
        /> : null}

        </div>
        {filesOpen ? <aside className={`chat-files-panel${filesExpanded ? " expanded" : ""}`} aria-label="Files and activity">
          {!filesExpanded ? <PanelResize label="Resize Files and activity" width={filesWidth} onResize={setFilesWidth} min={280} max={720} reset={380} reverse /> : null}
          <header><h3>Files & activity</h3><button type="button" className="icon-button" aria-label={filesExpanded ? "Restore panel size" : "Expand panel"} onClick={() => setFilesExpanded(value => !value)}><Icon name={filesExpanded ? "shrink" : "expand"} size={16} /></button><button type="button" className="icon-button" aria-label="Close Files and activity" onClick={() => setFilesOpen(false)}><Icon name="close" size={16} /></button></header>
          {conversation ? <LibraryPanel sessionId={conversation.id} projectPath={conversation.project_path} onReuseAssets={(_result, assets) => {
            draftRevision.current += 1;
            setAttachmentIds(current => [...new Set([...current, ...assets.map(asset => asset.id)])]);
            setAttachmentsOpen(true);
            setFilesOpen(false);
          }} /> : <p className="hint">Files you attach or create will appear here.</p>}
          {conversation?.current_run ? <details><summary>Activity</summary><RunProgress run={conversation.current_run} onCancel={stopCurrentWork} /></details> : null}
        </aside> : null}

        <form
          className="compose"
          onSubmit={(event) => {
            event.preventDefault();
            event.currentTarget.querySelectorAll<HTMLDetailsElement>("details[open]").forEach(menu => { menu.open = false; });
            void sendTurn();
          }}
          onKeyDown={event => {
            if (event.key === "Escape") {
              event.currentTarget.querySelectorAll<HTMLDetailsElement>("details[open]").forEach(menu => { menu.open = false; });
            }
          }}
        >
          {conversation ? <div hidden={!attachmentsOpen}><ComposerAttachments
            key={conversation.id}
            sessionId={conversation.id}
            attachmentIds={attachmentIds}
            disabled={selectionBusy || sending}
            incomingDrop={incomingDrop}
            onDropHandled={id => setIncomingDrop(current => current?.id === id ? null : current)}
            onAttachmentsChanged={(items) => {
              const next = items.map(item => item.id);
              if (JSON.stringify(next) !== JSON.stringify(attachmentIds)) {
                draftRevision.current += 1;
                setAttachmentIds(next);
              }
            }}
          /></div> : null}
          <label>
            <span className="sr-only">Message</span>
            <textarea
              value={task}
              onChange={(event) => updateTask(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
                  event.preventDefault();
                  event.currentTarget.form?.requestSubmit();
                }
              }}
              placeholder="Message your local model…"
              title="Enter to send · Shift+Enter for a new line"
              disabled={selectionBusy || sending}
            />
          </label>
          <div className="actions">
            <button type="button" className="icon-button" aria-label="Attach files" title="Attach files" aria-expanded={attachmentsOpen} disabled={!selectedDeployment || sending || selectionBusy} onClick={() => void openAttachments()}><Icon name="plus" /></button>
            <details className="composer-menu">
              <summary title="Tools and permissions"><Icon name="shield" /><span>{toolsAllowed ? "Ask for approval" : "Tools off"}</span></summary>
              <div className="composer-popover">
                <h3>Tools and permissions</h3>
                <label className="check-row"><input type="checkbox" checked={toolsAllowed} onChange={event => setToolsAllowed(event.target.checked)} /> Allow available tools for future messages</label>
                <p className="hint">Sensitive actions ask first unless you have saved a matching permission. Turning tools off also disables previously allowed actions.</p>
                <button type="button" onClick={() => navigateAway("settings")}>Review saved permissions</button>
                <label className="check-row"><input type="checkbox" checked={presentation.detailed_streams} onChange={event => {
                  const next = { detailed_streams: event.target.checked };
                  void api.updatePresentationSettings(next).then(saved => props.onPresentationChange?.(saved)).catch(fail);
                }} /> Show detailed activity by default</label>
              </div>
            </details>
            <ChatModelControls deployments={modelChoices} profiles={profiles} selectedDeploymentId={deploymentId} selectedProfileId={profileId} inheritDeploymentSettings={profileId !== "!none"} onDeploymentChange={chooseDeployment} onProfileChange={setProfileId} perRequestOverrides={perRequestOverrides} onPerRequestOverridesChange={setPerRequestOverrides} onInheritDeploymentSettingsChange={inherit => { if (!inherit) setProfileId("!none"); else if (profileId === "!none") setProfileId(""); }} disabled={selectionBusy || sending} />
            <span className="composer-spacer" />
            <ChatMeasurements run={conversation?.current_run} />
            <button
              type="submit"
              aria-label={runBusy ? "Queue" : selectionBusy || sending ? "Sending…" : "Send"}
              className="send-button"
              title={runBusy ? "Add to queue" : "Send message"}
              disabled={!selectedDeployment || (!task.trim() && !attachmentIds.length) || selectionBusy || sending || Boolean(pendingSubmit && draftRevision.current === pendingSubmit.draft_revision)}
            >
              {runBusy ? <span>Queue</span> : <Icon name="send" />}<span className="sr-only">{runBusy ? "Queue" : selectionBusy || sending ? "Sending…" : "Send"}</span>
            </button>
            <button
              type="button"
              aria-label={pendingStopActive ? "Stopping…" : "Stop"}
              className="stop-button"
              disabled={!conversation || !runBusy || pendingStopActive}
              onClick={stopCurrentWork}
            >
              <Icon name="stop" size={16} /><span className="sr-only">{pendingStopActive ? "Stopping…" : "Stop"}</span>
            </button>
          </div>
        </form>
        </div>
      </div>
    </section>
  );
}
