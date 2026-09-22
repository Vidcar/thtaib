import { useCallback, useEffect, useRef, useState, type ComponentProps, type CSSProperties, type RefObject } from "react";
import { PanelResize, usePanelWidth } from "./PanelResize";
import { AnswerActions } from "./AnswerActions";
import { areaLabel, newestConversationFirst } from "./conversationAreas";
import { HoverHelp } from "./HoverHelp";
import { useDismissibleDetails } from "./useDismissibleDetails";

import { api, ApiError } from "./api";
import { workspaceApi, type ProjectRecord, type AgentSetup, type SetupConfiguration, type ResolvedSetupSelection } from "./workspaceApi";
import { setupOverrides, sparseChatSetup, type ChatWorkspaceLaunch } from "./chatSetup";
import { ApprovalModeControl, approvalModeLabel, approvalModeOf, type ApprovalMode } from "./ApprovalModeControl";
import { Icon } from "./Icon";
import type { ChatLaunch, ConversationListActions, HistoryNotice } from "./WorkbenchSidebar";
import { ComposerAttachments } from "./ComposerAttachments";
import { LibraryPanel } from "./LibraryPanel";
import { FileChangesPanel } from "./FileChangesPanel";
import { RunMemoryProposals } from "./RunMemoryProposals";
import { packet03Api } from "./packet03Api";
import { ChatModelControls } from "./ChatModelControls";
import { ChatMeasurements } from "./ChatMeasurements";
import { ChatRetainedFiles, useChatRetainedAssets } from "./ChatRetainedFiles";
import { ChatDraftWriter, sameDraftValue } from "./chatDraftWriter";
import { ChatHistoryActions } from "./ChatHistoryActions";
import { ChatQueuePanel } from "./ChatQueuePanel";
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
  deployment_id?: string;
  profile_id?: string | null;
  inherit_deployment_settings?: boolean;
  project_path?: string | null;
  project_id?: string | null;
  agent_setup_version_id?: string | null;
  workspace_id?: string | null;
  memory_version_refs?: string[];
  skill_version_refs?: string[];
  protected_instruction_version_refs?: string[];
  knowledge_version_refs?: string[];
  embedding_deployment_id?: string | null;
  retrieval_project_paths?: string[];
}

function ChatInteractionStream(props: {
  detailedStreams?: boolean;
  renderMessageFooter?: ComponentProps<typeof AgentMessageFeed>["renderMessageFooter"];
  renderAnswerActions?: ComponentProps<typeof AgentMessageFeed>["renderAnswerActions"];
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
          renderAnswerActions={props.renderAnswerActions}
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
  renderAnswerActions?: ComponentProps<typeof AgentMessageFeed>["renderAnswerActions"];
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
      generation: run.generation_observation,
      context: run.context_observation,
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
        <AgentMessageFeed sourceScope={{ sessionId: conversation.id, projectPath: conversation.project_path ?? undefined }} messages={projection.messages} toolCalls={projection.toolCalls} incompleteMessageIds={projection.incompleteMessageIds} detailedStreams={props.detailedStreams} renderMessageFooter={props.renderMessageFooter} renderAnswerActions={props.renderAnswerActions} userMessageText={message => {
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

function sameAnswer(left: string, right: string): boolean {
  const normalize = (value: string) => value.replace(/\s+/g, " ").trim();
  const normalized = normalize(left);
  return normalized.length > 0 && normalized === normalize(right);
}

function savedAnswer(conversation: ChatConversation, messageId: string | undefined, incomplete: boolean, visibleText = ""): { runId: string; text: string } | null {
  if (incomplete) return null;
  const assistants = conversation.transcript.filter(item => item.role === "assistant" && item.run_id);
  const lastForRun = new Map<string, ChatMessage>();
  for (const item of assistants) if (item.run_id) lastForRun.set(item.run_id, item);
  const usable = [...lastForRun.values()].filter(item => !(conversation.current_run && isAgentRunLive(conversation.current_run.status) && conversation.current_run.id === item.run_id));
  const byId = messageId ? usable.find(item => item.id === messageId) : undefined;
  const byText = [...usable].reverse().find(entry => sameAnswer(entry.content, visibleText));
  const item = byId ?? byText;
  if (!item?.run_id) return null;
  return { runId: item.run_id, text: item.content };
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

const fallbackPresentation: PresentationSettings = {
  theme: "system",
  detailed_streams: false,
  attention_notifications: true,
  success_notifications: false,
};

interface ChatPanelProps {
  workspaceLaunch?: ChatWorkspaceLaunch | null;
  onWorkspaceLaunchHandled?: () => void;
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
  chatLaunch?: ChatLaunch | null;
  onChatLaunchHandled?: () => void;
  historyNotice?: HistoryNotice | null;
  conversationListRef?: RefObject<ConversationListActions | null>;
  onHistoryChanged?: () => void;
  onActiveConversationId?: (id: string | null) => void;
  onCreateProject?: () => void;
  projectRevision?: number;
}

export function ChatPanel(props: ChatPanelProps = {}) {
  const toolsMenuRef = useDismissibleDetails();
  const {
    attentionConversationId = null,
    onAttentionHandled,
    onNavigate,
    presentation = fallbackPresentation,
  } = props;
  const [filesWidth, setFilesWidth] = usePanelWidth("workbench.inspector.width", 380, 280, 720);
  const [filesExpanded, setFilesExpanded] = useState(false);
  const historyMutations = useRef(new Map<string, boolean | "deleted">());
  const [deployments, setDeployments] = useState<Deployment[]>([]);
  const [profiles, setProfiles] = useState<RunProfile[]>([]);
  const [enabledTools, setEnabledTools] = useState<string[]>([]);
  const [deploymentId, setDeploymentId] = useState("");
  const [embeddingDeploymentId, setEmbeddingDeploymentId] = useState("");
  const [profileId, setProfileId] = useState("");
  const [projectPath, setProjectPath] = useState("");
  const [projects, setProjects] = useState<ProjectRecord[]>([]);
  const [agentSetups, setAgentSetups] = useState<AgentSetup[]>([]);
  const [projectId, setProjectId] = useState<string | null>(null);
  const [agentSetupVersionId, setAgentSetupVersionId] = useState<string | null>(null);
  const [setupResolving, setSetupResolving] = useState(false);
  const [setupDefaultsLoading, setSetupDefaultsLoading] = useState(true);
  const [hasApplicationDefaults, setHasApplicationDefaults] = useState(false);
  const [setupError, setSetupError] = useState("");
  const [instructionLayers, setInstructionLayers] = useState<ResolvedSetupSelection["instruction_layers"]>([]);
  const setupEditedFields = useRef(new Set<string>());
  const setupRequest = useRef(0);
  const workspaceLaunchClaim = useRef<string | null>(null);
  const chatLaunchClaim = useRef<string | null>(null);
  const historyNoticeClaim = useRef<string | null>(null);
  const [task, setTask] = useState("");
  const [attachmentIds, setAttachmentIds] = useState<string[]>([]);
  const [attachmentsOpen, setAttachmentsOpen] = useState(false);
  const [incomingDrop, setIncomingDrop] = useState<{ id: string; sessionId: string; files: File[] } | null>(null);
  const [fileDragActive, setFileDragActive] = useState(false);
  const [approvalMode, setApprovalMode] = useState<ApprovalMode>("ask");
  const [perRequestOverrides, setPerRequestOverrides] = useState<Record<string, unknown>>({});
  const [setupOpen, setSetupOpen] = useState(false);
  const [filesOpen, setFilesOpen] = useState(false);
  const reuseClaim = useRef<string | null>(null);
  const [conversation, setConversation] = useState<ChatConversation | null>(null);
  const retainedAssets = useChatRetainedAssets(conversation?.id ?? "");
  const [conversations, setConversations] = useState<ChatConversation[]>([]);
  const historySignature = conversations.map(item => `${item.id}:${item.title ?? ""}:${item.archived ? 1 : 0}`).join("|");
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
    const results = await Promise.allSettled([
      api.deployments(),
      api.profiles(),
      api.agentTools(),
      api.chatConversations(false),
      api.knowledgeEntries(),
    ]);
    const [nextDeployments, nextProfiles, tools, nextConversations, nextKnowledge] = results;
    if (nextDeployments.status === "fulfilled") {
      setDeployments(nextDeployments.value);
      setDeploymentId((current) => current || preferredChatDeploymentId(nextDeployments.value, current));
    }
    if (nextProfiles.status === "fulfilled") {
      setProfiles(nextProfiles.value);
      setProfileId((current) => (current === "!none" || nextProfiles.value.some((profile) => profile.id === current) ? current : ""));
    }
    if (tools.status === "fulfilled") setEnabledTools(tools.value.enabled);
    if (nextConversations.status === "fulfilled") setConversations(newestConversationFirst(reconcileHistory(nextConversations.value)));
    if (nextKnowledge.status === "fulfilled") setKnowledgeEntries(nextKnowledge.value);
    setLoadError([...new Set(results.filter(result => result.status === "rejected").map(result => errorMessage(result.reason)))].join(" · "));
  }

  useEffect(() => {
    let cancelled = false;
    void Promise.all([workspaceApi.projects(), workspaceApi.agentSetups()]).then(([nextProjects, nextAgents]) => {
      if (!cancelled) { setProjects(nextProjects); setAgentSetups(nextAgents); }
    }).catch(error => { if (!cancelled) setSetupError(errorMessage(error)); });
    return () => { cancelled = true; };
  }, [props.projectRevision]);

  useEffect(() => {
    let cancelled = false;
    const generation = selectionRequest.current;
    const request = setupRequest.current;
    void workspaceApi.resolveSetup(null, null).then(resolved => {
      if (cancelled) return;
      const configured = Object.values(resolved.configuration).some(value => value != null) || Boolean(resolved.instruction_layers?.length);
      setHasApplicationDefaults(configured);
      if (configured && generation === selectionRequest.current && request === setupRequest.current && setupEditedFields.current.size === 0) applyResolvedSetup(resolved);
    }).catch(error => { if (!cancelled && generation === selectionRequest.current) setSetupError(errorMessage(error)); }).finally(() => { if (!cancelled) setSetupDefaultsLoading(false); });
    return () => { cancelled = true; };
  }, []);

  function markSetupEdited(...keys: string[]) { keys.forEach(key => setupEditedFields.current.add(key)); }

  function chatConfiguration(): Record<string, unknown> {
    const layered = Boolean(hasApplicationDefaults || projectId || agentSetupVersionId || conversation?.agent_setup_version_id || conversation?.project_id);
    const values = sparseChatSetup({
      deployment_id: deploymentId,
      profile_id: profileId && profileId !== "!none" ? profileId : null,
      inherit_deployment_settings: profileId !== "!none",
      embedding_deployment_id: embeddingDeploymentId || null,
      ...(setupEditedFields.current.has("presented_tools") ? { presented_tools: conversation?.draft?.intended_config?.presented_tools ?? conversation?.setup_overrides?.presented_tools ?? null } : {}),
      ...(setupEditedFields.current.has("approval_mode") ? { approval_mode: approvalMode } : {}),
      per_request_overrides: perRequestOverrides,
      ...knowledgePayload(knowledgeEntries, selectedKnowledgeIds),
    }, setupEditedFields.current, layered);
    return { ...values, ...(projectId ? { project_id: projectId } : {}),
      ...(agentSetupVersionId || conversation?.agent_setup_version_id ? { agent_setup_version_id: agentSetupVersionId } : {}),
      ...(!projectId ? { project_path: projectPath.trim() || null } : {}),
      ...(!projectId || conversation?.workspace_id ? { workspace_id: conversation?.workspace_id ?? null } : {}) };
  }

  function applyResolvedSetup(selection: ResolvedSetupSelection) {
    const config = selection.configuration;
    if (config.deployment_id) setDeploymentId(config.deployment_id);
    else markSetupEdited("deployment_id"); // Use the visibly selected model when the setup inherits it.
    setProfileId(config.profile_id ?? (config.inherit_deployment_settings === false ? "!none" : ""));
    setEmbeddingDeploymentId(config.embedding_deployment_id ?? "");
    if (!setupEditedFields.current.has("approval_mode")) setApprovalMode(approvalModeOf(config.approval_mode));
    setPerRequestOverrides(config.per_request_overrides ?? {});
    setSelectedKnowledgeIds([...(config.memory_version_refs ?? []), ...(config.skill_version_refs ?? []), ...(config.protected_instruction_version_refs ?? [])]);
    setInstructionLayers(selection.instruction_layers ?? []);
  }

  async function chooseSetup(nextProjectId: string | null, nextVersionId: string | null, overrides: SetupConfiguration = {}) {
    const request = ++setupRequest.current;
    const generation = selectionRequest.current;
    setSetupResolving(true); setSetupError("");
    try {
      const resolved = await workspaceApi.resolveSetup(nextProjectId, nextVersionId, overrides);
      if (request !== setupRequest.current || generation !== selectionRequest.current) return;
      setupEditedFields.current = new Set(Object.keys(overrides));
      setProjectId(nextProjectId); setAgentSetupVersionId(nextVersionId);
      setProjectPath(projects.find(project => project.id === nextProjectId)?.canonical_path ?? "");
      applyResolvedSetup(resolved);
    } catch (error) {
      if (request === setupRequest.current && generation === selectionRequest.current) setSetupError(errorMessage(error));
    } finally {
      if (request === setupRequest.current) setSetupResolving(false);
    }
  }

  useEffect(() => {
    void refresh().catch((error: unknown) => {
      setLoadError(errorMessage(error));
    });
  }, []);

  useEffect(() => { props.onHistoryChanged?.(); }, [historySignature]);
  useEffect(() => { props.onActiveConversationId?.(conversation?.id ?? selectionLoading?.id ?? null); }, [conversation?.id, selectionLoading?.id]);

  useEffect(() => {
    if (!conversation) {
      serverDraftRevision.current = 0;
      return;
    }
    serverDraftRevision.current = conversation.draft?.revision ?? 0;
    draftWriter.current.observe(conversation);
  }, [conversation?.id, conversation?.draft?.revision]);

  useEffect(() => {
    if (!conversation || selectionLoading || setupResolving || sending || pendingSubmit) {
      return;
    }
    const content = task;
    const intendedConfig = chatConfiguration();
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
    approvalMode,
    perRequestOverrides,
    selectedKnowledgeIds,
    knowledgeEntries,
    projectId, agentSetupVersionId, setupResolving, hasApplicationDefaults,
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
    setupRequest.current += 1;
    setSetupResolving(false);
    setSetupError("");
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

  const selectionBusy = Boolean(selectionLoading) || setupResolving || setupDefaultsLoading;
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
        const draftConfig = next.draft?.intended_config ?? {};
        const nextProjectId = typeof draftConfig.project_id === "string" ? draftConfig.project_id : next.project_id ?? null;
        const nextVersionId = Object.hasOwn(draftConfig, "agent_setup_version_id") ? typeof draftConfig.agent_setup_version_id === "string" ? draftConfig.agent_setup_version_id : null : next.agent_setup_version_id ?? null;
        const overrides = setupOverrides({ ...(next.setup_overrides ?? {}), ...draftConfig });
        let resolutionFailure = "";
        const resolved = nextProjectId || nextVersionId || hasApplicationDefaults ? await workspaceApi.resolveSetup(nextProjectId, nextVersionId, overrides).catch(error => { resolutionFailure = errorMessage(error); return null; }) : null;
        if (selectionRequest.current !== requestId || historyMutations.current.get(item.id) === "deleted") return;
        setupRequest.current += 1;
        setSetupResolving(false); setSetupError(resolutionFailure);
        setProjectId(nextProjectId); setAgentSetupVersionId(nextVersionId);
        setupEditedFields.current = new Set(Object.keys(overrides));
        activeOwner.current = { conversationId: next.id, threadId: registered.thread_id, generation: requestId };
        setBoundGeneration(requestId);
        setConversation(next);
        setInteractionThreadId(registered.thread_id);
        setSelectionLoading(null);
        setDeploymentId(typeof draftConfig.deployment_id === "string" ? draftConfig.deployment_id : next.deployment_id);
        setEmbeddingDeploymentId(typeof draftConfig.embedding_deployment_id === "string" ? draftConfig.embedding_deployment_id : next.embedding_deployment_id ?? "");
        setProfileId(typeof draftConfig.profile_id === "string" ? draftConfig.profile_id : draftConfig.inherit_deployment_settings === false ? "!none" : next.profile_id ?? (next.inherit_deployment_settings === false ? "!none" : ""));
        if (draftConfig.approval_mode != null) setApprovalMode(approvalModeOf(draftConfig.approval_mode));
        setPerRequestOverrides(draftConfig.per_request_overrides && typeof draftConfig.per_request_overrides === "object" ? draftConfig.per_request_overrides as Record<string, unknown> : {});
        setProjectPath(next.project_path ?? "");
        setSelectedKnowledgeIds([
          ...(next.memory_version_refs ?? []),
          ...(next.skill_version_refs ?? []),
          ...(next.protected_instruction_version_refs ?? []),
        ]);
        if (resolved) applyResolvedSetup(resolved);
        else setInstructionLayers([]);
        serverDraftRevision.current = next.draft?.revision ?? 0;
        draftRevision.current += 1;
        setTask(next.draft?.content ?? "");
        setAttachmentIds(next.draft?.attachment_ids ?? []);
        setAttachmentsOpen(Boolean(next.draft?.attachment_ids?.length));
        setMessage("");
      })
      .catch((error: unknown) => {
        if (selectionRequest.current === requestId) {
          if (error instanceof ApiError && error.status === 404 && error.code === "chat_missing") {
            historyMutations.current.set(item.id, "deleted");
            setConversations(current => current.filter(value => value.id !== item.id));
            props.conversationListRef?.current?.forget(item.id);
            startFresh();
            setMessage("That conversation is no longer available. You can start a new chat.");
            return;
          }
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
    markSetupEdited("deployment_id", "per_request_overrides");
    setDeploymentId(nextId);
    setPerRequestOverrides(current => {
      const next = { ...current };
      delete next.reasoning;
      delete next.reasoning_effort;
      delete next.reasoning_format;
      return next;
    });
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
      const payload = {
        ...chatConfiguration(),
        task: text,
        draft_revision: savedDraft?.draft?.revision ?? conversation?.draft?.revision ?? null,
        attachment_ids: attachmentIds,
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
    const promise = api.createChatConversation(chatConfiguration()).catch(error => {
      if (conversationCreation.current?.promise === promise) conversationCreation.current = null;
      throw error;
    });
    conversationCreation.current = { generation, promise };
    return promise;
  }

  async function persistBeforeLeaving(): Promise<ChatConversation | null> {
    if (selectionLoading || setupResolving || sending || (pendingSubmit && draftRevision.current === pendingSubmit.draft_revision)) return null;
    if (!conversation && (!task.trim() && !attachmentIds.length || !selectedDeployment)) return null;
    const target = conversation ?? await createDraftConversation();
    const payload = {
      content: task,
      attachment_ids: attachmentIds,
      intended_config: chatConfiguration(),
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
    const launch = props.workspaceLaunch;
    if (!launch || workspaceLaunchClaim.current === launch.id) return;
    let cancelled = false;
    void Promise.resolve().then(async () => {
      if (cancelled) return;
      workspaceLaunchClaim.current = launch.id;
      try {
        await persistBeforeLeaving();
        if (cancelled) return;
        startFresh();
        await chooseSetup(launch.projectId ?? null, launch.agentSetupVersionId ?? null);
        if (!cancelled) { setSetupOpen(true); props.onWorkspaceLaunchHandled?.(); }
      } catch (error) { if (!cancelled) { fail(error); props.onWorkspaceLaunchHandled?.(); } }
    });
    return () => { cancelled = true; };
  }, [props.workspaceLaunch?.id]);

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

  useEffect(() => {
    const launch = props.chatLaunch;
    if (!launch || chatLaunchClaim.current === launch.id) return;
    chatLaunchClaim.current = launch.id;
    if (launch.kind === "fresh") {
      void persistBeforeLeaving().then(startFresh).catch(fail).finally(() => props.onChatLaunchHandled?.());
      return;
    }
    if (!launch.conversationId) { props.onChatLaunchHandled?.(); return; }
    chooseConversation(launch.conversation ?? { id: launch.conversationId } as ChatConversation);
    props.onChatLaunchHandled?.();
  }, [props.chatLaunch?.id]);

  useEffect(() => {
    const notice = props.historyNotice;
    if (!notice || historyNoticeClaim.current === notice.token) return;
    historyNoticeClaim.current = notice.token;
    if (notice.deletedId) removeConversation(notice.deletedId);
    else if (notice.conversation) {
      applyConversationUpdate(notice.conversation);
      if (notice.leave) startFresh();
    }
  }, [props.historyNotice?.token]);

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

  return (
    <section className="chat-layout" style={{ "--inspector-width": `${filesWidth}px` } as CSSProperties}>
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
        {loadError ? <Notice tone="error" action={<button type="button" onClick={() => void refresh().catch((error: unknown) => setLoadError(errorMessage(error)))}>Retry</button>}>{loadError}</Notice> : null}
        <details className="chat-setup" open={setupOpen} onToggle={(event) => setSetupOpen(event.currentTarget.open)} hidden={!setupOpen}>
          <summary><Icon name="settings" size={16} /> Setup</summary>
          <div className="setup-grid">
            <label><span>Project <HoverHelp title="About projects">File tools work inside the selected folder. A chat stays with its original project.</HoverHelp></span><select aria-label="Chat project" value={projectId ?? ""} disabled={Boolean(conversation) || selectionBusy || sending} onChange={event => void chooseSetup(event.target.value || null, agentSetupVersionId)}><option value="">General · no project</option>{projects.map(project => <option key={project.id} value={project.id} disabled={project.missing}>{project.name}{project.missing ? " · folder unavailable" : ""}</option>)}{projectId && !projects.some(project => project.id === projectId) ? <option value={projectId}>Unavailable project</option> : null}</select></label>
            <label><span>Agent <HoverHelp title="About saved agents">Applies the selected saved version to the next message. Existing runs and queued messages keep their own setup.</HoverHelp></span><select aria-label="Chat agent" value={agentSetupVersionId ?? ""} disabled={selectionBusy || sending} onChange={event => void chooseSetup(projectId, event.target.value || null)}><option value="">Default setup</option>{agentSetups.map(setup => <option key={setup.id} value={setup.current_version_id} disabled={Boolean(setup.missing_dependencies?.length)}>{setup.name}{setup.missing_dependencies?.length ? " · needs repair" : ""}</option>)}{agentSetupVersionId && !agentSetups.some(setup => setup.current_version_id === agentSetupVersionId) ? <option value={agentSetupVersionId}>Saved earlier agent version</option> : null}</select></label>
          </div>
          {setupResolving ? <p className="hint" role="status">Applying setup…</p> : null}
          <div className="actions"><button type="button" onClick={() => navigateAway("projects")}>Manage projects</button><button type="button" onClick={() => navigateAway("agents")}>Manage agents</button></div>
          {instructionLayers?.length ? <details><summary>Effective instructions · {instructionLayers.length} layers</summary>{instructionLayers.map((layer, index) => <section key={`${layer.source_id ?? layer.name}-${index}`}><h4>{layer.name}</h4><pre className="wrapped-text">{layer.content}</pre></section>)}</details> : null}
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
                disabled={selectionBusy || sending}
                onChange={(event) => { markSetupEdited("embedding_deployment_id"); setEmbeddingDeploymentId(event.target.value); }}
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
                        markSetupEdited("memory_version_refs", "skill_version_refs", "protected_instruction_version_refs", "knowledge_version_refs");
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
          {conversation && tools.length > 0 ? (
            <details>
              <summary>{tools.length} {tools.length === 1 ? "tool available" : "tools available"}</summary>
              <p className="hint">{tools.join(", ")}</p>
            </details>
          ) : <p className="hint">{conversation ? "No tools available." : "Available tools depend on the project you choose."}</p>}
          {(conversation?.filesystem_tools_available === false || conversation?.shell_tools_available === false) && <p className="hint">
            {conversation && conversation.filesystem_tools_available === false
              ? "Project files unavailable. "
              : ""}
            {conversation && conversation.shell_tools_available === false ? "Host shell unavailable." : ""}
          </p>}
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
              {projectId || projectPath ? <span>Start a conversation in {projects.find(project => project.id === projectId)?.name ?? projectPath.split(/[\\/]/).filter(Boolean).at(-1) ?? "this project"}.</span> : <button type="button" className="quiet-button" onClick={() => props.onCreateProject?.()}><Icon name="folder" size={16} /> Add a project</button>}
            </EmptyState>
          ) : canObserveInteraction && interactionThreadId && conversation ? (
            <ChatInteractionStream
              detailedStreams={presentation.detailed_streams}
              renderAnswerActions={(nativeMessage, incomplete, answerText) => {
                const saved = savedAnswer(conversation, nativeMessage.id, incomplete, answerText);
                if (!saved) return null;
                return <AnswerActions conversation={conversation} runId={saved.runId} answerText={saved.text} disabled={selectionBusy || sending} onError={setMessage} onConversationCreated={next => { cacheConversation(next); chooseConversation(next); }} />;
              }}
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
                {conversation && item.role === "assistant" ? (() => {
                  const saved = savedAnswer(conversation, item.id ?? undefined, false, item.content);
                  return saved ? <AnswerActions conversation={conversation} runId={saved.runId} answerText={saved.text} disabled={selectionBusy || sending} onError={setMessage} onConversationCreated={next => { cacheConversation(next); chooseConversation(next); }} /> : null;
                })() : null}
              </article>
            ))
          )}
          {runBusy && !pendingInterrupt && (pendingStopActive || pendingSubmissionActive || !(canObserveInteraction && conversation?.current_run && isAgentRunLive(conversation.current_run.status))) ? (
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
        {setupError ? <Notice tone="error">{setupError}</Notice> : null}

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
          {conversation ? <FileChangesPanel key={conversation.id} runIds={conversation.run_ids} currentRunId={conversation.current_run_id} currentRunStatus={conversation.current_run?.status} /> : null}
          {conversation ? <LibraryPanel sessionId={conversation.id} projectPath={conversation.project_path} onReuseAssets={(_result, assets) => {
            draftRevision.current += 1;
            setAttachmentIds(current => [...new Set([...current, ...assets.map(asset => asset.id)])]);
            setAttachmentsOpen(true);
            setFilesOpen(false);
          }} /> : <p className="hint">Files you attach or create will appear here.</p>}
          {conversation?.current_run ? <details><summary>Activity</summary><RunProgress run={conversation.current_run} onCancel={stopCurrentWork} /></details> : null}
          {conversation?.current_run ? <RunMemoryProposals key={conversation.current_run.id} runId={conversation.current_run.id} status={conversation.current_run.status} onOpenKnowledge={() => navigateAway("knowledge")} /> : null}
        </aside> : null}

        <form
          className="compose"
          onSubmit={(event) => {
            event.preventDefault();
            event.currentTarget.querySelectorAll<HTMLDetailsElement>("details[open]").forEach(menu => { menu.open = false; });
            void sendTurn();
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
            <details ref={toolsMenuRef} name="chat-composer-controls" className="composer-menu">
              <summary title="Approval mode" aria-label="Approval mode"><Icon name="shield" /><span>{approvalModeLabel(approvalMode)}</span></summary>
              <div className="composer-popover chat-tools-popover" role="group" aria-label="Approval mode choices">
                <ApprovalModeControl value={approvalMode} disabled={selectionBusy || sending} onChange={mode => { markSetupEdited("approval_mode"); setApprovalMode(mode); }} />
                <button type="button" className="chat-tools-permissions" onClick={() => navigateAway("settings")}><Icon name="settings" size={14} /> Saved permissions</button>
              </div>
            </details>
            <ChatModelControls deployments={modelChoices} profiles={profiles} selectedDeploymentId={deploymentId} selectedProfileId={profileId} inheritDeploymentSettings={profileId !== "!none"} onDeploymentChange={chooseDeployment} onProfileChange={value => { markSetupEdited("profile_id", "inherit_deployment_settings"); setProfileId(value); }} perRequestOverrides={perRequestOverrides} onPerRequestOverridesChange={value => { markSetupEdited("per_request_overrides"); setPerRequestOverrides(value); }} onInheritDeploymentSettingsChange={inherit => { markSetupEdited("profile_id", "inherit_deployment_settings"); if (!inherit) setProfileId("!none"); else if (profileId === "!none") setProfileId(""); }} disabled={selectionBusy || sending} />
            <button type="button" className={`icon-button${presentation.detailed_streams ? " is-pressed" : ""}`} aria-pressed={presentation.detailed_streams} aria-label="Detailed activity" title="Show reasoning and tool detail" disabled={selectionBusy} onClick={() => { const next = { detailed_streams: !presentation.detailed_streams }; void api.updatePresentationSettings(next).then(saved => props.onPresentationChange?.(saved)).catch(fail); }}><Icon name="activity" size={16} /></button>
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
