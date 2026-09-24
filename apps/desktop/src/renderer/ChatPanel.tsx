import { useCallback, useEffect, useRef, useState, type ComponentProps, type CSSProperties, type RefObject } from "react";
import { PanelResize, usePanelWidth } from "./PanelResize";
import { AnswerActions } from "./AnswerActions";
import { areaLabel, newestConversationFirst } from "./conversationAreas";
import { MenuPopover } from "./MenuPopover";
import { CompactSwitch } from "./CompactControls";
import { HoverHelp } from "./HoverHelp";

import { api, ApiError } from "./api";
import { workspaceApi, type ProjectRecord, type AgentSetup, type SetupConfiguration, type ResolvedSetupSelection } from "./workspaceApi";
import { setupOverrides, sparseChatSetup, type ChatWorkspaceLaunch } from "./chatSetup";
import { ApprovalModeControl, approvalModeLabel, approvalModeOf, type ApprovalMode } from "./ApprovalModeControl";
import { Icon } from "./Icon";
import type { ChatLaunch, ConversationListActions, HistoryNotice } from "./WorkbenchSidebar";
import { ComposerAttachments } from "./ComposerAttachments";
import { ChatDock, type DockPage } from "./ChatDock";
import { ConversationSetup } from "./ConversationSetup";

type RailPage = "setup" | DockPage | "actions";

function readRailPage(): RailPage {
  try {
    const saved = sessionStorage.getItem("workbench.chat.rail.page");
    if (saved === "setup" || saved === "files" || saved === "library" || saved === "actions") return saved;
  } catch { /* Keep the default page. */ }
  return "files";
}
import { ChatDockContext } from "./chatDockContext";
import { packet03Api } from "./packet03Api";
import { ChatModelControls } from "./ChatModelControls";
import { ChatMeasurements, publishLiveMeasurement } from "./ChatMeasurements";
import { ChatRetainedFiles, useChatRetainedAssets } from "./ChatRetainedFiles";
import { ChatDraftWriter, sameDraftValue } from "./chatDraftWriter";
import { notifyAttentionChanged } from "./AttentionPanel";
import { ChatHistoryActions } from "./ChatHistoryActions";
import { ChatQueuePanel } from "./ChatQueuePanel";
import { AgentMessageFeed } from "./AgentMessageFeed";
import { RunActivitySummary, helperApprovalOwner } from "./RunActivitySummary";
import { conversationTitle, displayedTranscript, formatWhen } from "./display";
import { EmptyState } from "./EmptyState";
import { errorMessage } from "./errors";
import { InteractionStream, useWorkbenchProjection, visibleApprovalInterrupt, type WorkbenchStream } from "./InteractionStream";
import { InterruptApproval } from "./InterruptApproval";
import { Notice } from "./Notice";
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
  model_configuration_id?: string | null;
  startup_overrides?: Record<string, unknown>;
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
  work_mode?: "work" | "plan";
  helper_agent_ids?: string[];
  review?: { enabled: boolean; criteria: string; max_revisions: 2 };
}

type ExecutionPreferences = { work_mode?: "work" | "plan"; helper_agent_ids?: string[]; review?: { enabled?: boolean; criteria?: string; max_revisions?: number } };

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
  const savingProjectState = projectionRunOwned && run?.finalization_phase === "saving_changes";
  const visibleInterrupt = visibleApprovalInterrupt(stream, run ?? conversation.current_run);
  const inputId = pendingSubmit?.id ?? run?.input_message_id;
  const reverseInputIndex = [...projection.messages].reverse().findIndex(message => inputId ? message.id === inputId : message.getType() === "human");
  const inputIndex = reverseInputIndex < 0 ? -1 : projection.messages.length - reverseInputIndex - 1;
  const hasTurnOutput = inputIndex >= 0 && projection.messages.slice(inputIndex + 1).some(message =>
    message.getType() !== "human" && (message.content.length > 0 || Boolean((message as { tool_calls?: unknown[] }).tool_calls?.length)),
  ) || projection.toolCalls.some(call => (call.status as string) === "preparing" || call.status === "running");
  const waitingForOutput = projectionRunOwned && !savingProjectState && !visibleInterrupt && !hasTurnOutput &&
    Boolean(pendingSubmit || (run && isAgentRunLive(run.status)));
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
      finalizationPhase: run?.finalization_phase ?? null,
      eventCount: run?.events.length ?? null,
    });
    publishLiveMeasurement({
      runId: run.id,
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
        <AgentMessageFeed waiting={Boolean(visibleInterrupt)} toolAuthorizations={run?.tool_authorizations} toolAuthorizationGrants={run?.tool_authorization_grants} live={run ? isAgentRunLive(run.status) : stream.isLoading} sourceScope={{ sessionId: conversation.id, projectPath: conversation.project_path ?? undefined }} messages={projection.messages} toolCalls={projection.toolCalls} incompleteMessageIds={projection.incompleteMessageIds} detailedStreams={props.detailedStreams} renderMessageFooter={props.renderMessageFooter} renderAnswerActions={props.renderAnswerActions} userMessageText={message => {
          const retained = conversation.transcript.find(item => item.id === message.id && item.role === "user" && item.attachment_ids?.length);
          return retained?.content;
        }} />
      ) : null}
      {projectionRunOwned ? <RunActivitySummary run={run} /> : null}
      {savingProjectState ? <div className="chat-waiting" role="status">Saving project state…</div> : null}
      {waitingForOutput ? <div className="chat-waiting" role="status"><span className="chat-waiting-dot" aria-hidden="true" />{pendingSubmit ? "Preparing reply…" : run?.status === "cancel_requested" ? "Stopping…" : "Thinking…"}</div> : null}
      {projectionRunOwned && visibleInterrupt ? (
        <InterruptApproval
          ownerLabel={helperApprovalOwner(run, visibleInterrupt.namespace)}
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

function knowledgePayload(entries: KnowledgeEntry[], selectedVersionIds: string[], pinnedMemoryRefs?: string[]) {
  const selected = entries.filter((entry) => selectedVersionIds.includes(entry.current_version_id));
  const memoryVersionRefs = pinnedMemoryRefs ?? selected
    .filter((entry) => entry.kind === "memory")
    .map((entry) => entry.current_version_id);
  const skillVersionRefs = selected
    .filter((entry) => entry.kind === "skill")
    .map((entry) => entry.current_version_id);
  const protectedInstructionVersionRefs = selected
    .filter((entry) => entry.kind === "protected_instruction")
    .map((entry) => entry.current_version_id);
  return {
    knowledge_version_refs: [...memoryVersionRefs, ...skillVersionRefs, ...protectedInstructionVersionRefs],
    memory_version_refs: memoryVersionRefs,
    skill_version_refs: skillVersionRefs,
    protected_instruction_version_refs: protectedInstructionVersionRefs,
  };
}

function hasFixedMemory(conversation: ChatConversation | null): boolean {
  return Boolean(conversation && (conversation.source_checkpoint_id || conversation.current_run_id || conversation.run_ids.length));
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

function chatDeployHealthNotice(conversation: ChatConversation | null, selectedDeployment: Deployment | undefined): { tone: "info" | "warn" | "error"; message: string } | null {
  const health = conversation?.deploy_health;
  if (!conversation || !health?.message) {
    return null;
  }
  const selectedIsBound = selectedDeployment?.id === conversation.deployment_id && health.deployment_id === conversation.deployment_id;
  if (selectedIsBound && selectedDeployment?.scope === "managed" && (selectedDeployment.status === "stopped" || selectedDeployment.status === "starting")) {
    return null;
  }
  return { tone: health.healthy === false ? "error" : "warn", message: health.message };
}

export function preferredChatDeploymentId(deployments: Deployment[], current: string, selectedConfigurationId = ""): string {
  // A saved model configuration with no matching deployment is intentional.
  // Refresh must not pair it with an arbitrary older deployment.
  if (!current && selectedConfigurationId) return "";
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
  restoringSelection?: boolean;
  onCreateProject?: () => void;
  projectRevision?: number;
  onModelPhase?: (phase: "starting" | "ready" | "none" | "failed") => void;
}

export function ChatPanel(props: ChatPanelProps = {}) {
  const {
    attentionConversationId = null,
    onAttentionHandled,
    onNavigate,
    presentation = fallbackPresentation,
  } = props;
  const [filesWidth, setFilesWidth] = usePanelWidth("workbench.inspector.width", 320, 280, 720);
  const [railPage, setRailPage] = useState<RailPage>(() => readRailPage());
  const [railOpen, setRailOpen] = useState(() => {
    try { return sessionStorage.getItem("workbench.chat.rail") === "open"; } catch { return false; }
  });
  const [selectedPath, setSelectedPath] = useState("");
  const historyMutations = useRef(new Map<string, boolean | "deleted">());
  const [deployments, setDeployments] = useState<Deployment[]>([]);
  const [deploymentsLoaded, setDeploymentsLoaded] = useState(false);
  const modelWarm = useRef(false);
  const [profiles, setProfiles] = useState<RunProfile[]>([]);
  const [enabledTools, setEnabledTools] = useState<string[]>([]);
  const [deploymentId, setDeploymentId] = useState("");
  const [embeddingDeploymentId, setEmbeddingDeploymentId] = useState("");
  const [profileId, setProfileId] = useState("");
  const profileIdRef = useRef(profileId);
  const [startupOverrides, setStartupOverrides] = useState<Record<string, unknown>>({});
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
  const filePicker = useRef<HTMLInputElement>(null);
  const [workMode, setWorkMode] = useState<"work" | "plan">("work");
  const [helperAgentIds, setHelperAgentIds] = useState<string[]>([]);
  const [review, setReview] = useState({ enabled: false, criteria: "", max_revisions: 2 as const });
  const [incomingDrop, setIncomingDrop] = useState<{ id: string; sessionId: string; files: File[] } | null>(null);
  const [fileDragActive, setFileDragActive] = useState(false);
  const [approvalMode, setApprovalMode] = useState<ApprovalMode>("ask");
  const [perRequestOverrides, setPerRequestOverrides] = useState<Record<string, unknown>>({});

  const reuseClaim = useRef<string | null>(null);
  const [conversation, setConversation] = useState<ChatConversation | null>(null);
  const retainedAssets = useChatRetainedAssets(conversation?.id ?? "");
  const openRail = useCallback((page: RailPage) => {
    setRailOpen(true);
    setRailPage(page);
    try {
      sessionStorage.setItem("workbench.chat.rail", "open");
      sessionStorage.setItem("workbench.chat.rail.page", page);
    } catch { /* The rail still opens for this view. */ }
  }, []);
  const openFile = useCallback((path: string) => {
    openRail("files");
    setSelectedPath(path);
  }, [openRail]);
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
        setDeploymentId((current) => current || preferredChatDeploymentId(next, current, profileIdRef.current));
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
      setDeploymentId((current) => current || preferredChatDeploymentId(nextDeployments.value, current, profileIdRef.current));
    }
    setDeploymentsLoaded(true);
    if (nextProfiles.status === "fulfilled") {
      setProfiles(nextProfiles.value);
      setProfileId((current) => {
        const next = nextProfiles.value.some((profile) => profile.id === current) ? current : "";
        profileIdRef.current = next;
        return next;
      });
    }
    if (tools.status === "fulfilled") setEnabledTools(tools.value.enabled);
    if (nextConversations.status === "fulfilled") setConversations(newestConversationFirst(reconcileHistory(nextConversations.value)));
    if (nextKnowledge.status === "fulfilled") setKnowledgeEntries(nextKnowledge.value);
    setLoadError([...new Set(results.filter(result => result.status === "rejected").map(result => errorMessage(result.reason)))].join(" · "));
  }

  useEffect(() => {
    let cancelled = false;
    if (props.activeTab && props.activeTab !== "chat") return;
    void Promise.all([workspaceApi.projects(), workspaceApi.agentSetups()]).then(([nextProjects, nextAgents]) => {
      if (!cancelled) { setProjects(nextProjects); setAgentSetups(nextAgents); }
    }).catch(error => { if (!cancelled) setSetupError(errorMessage(error)); });
    return () => { cancelled = true; };
  }, [props.projectRevision, props.activeTab]);

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
    const pinnedMemory = hasFixedMemory(conversation) ? conversation?.memory_version_refs ?? [] : undefined;
    const selectedKnowledge = knowledgePayload(knowledgeEntries, selectedKnowledgeIds, pinnedMemory);
    const values = sparseChatSetup({
      deployment_id: deploymentId,
      model_configuration_id: profileId || null,
      startup_overrides: startupOverrides,
      embedding_deployment_id: embeddingDeploymentId || null,
      ...(setupEditedFields.current.has("presented_tools") ? { presented_tools: conversation?.draft?.intended_config?.presented_tools ?? conversation?.setup_overrides?.presented_tools ?? null } : {}),
      ...(setupEditedFields.current.has("approval_mode") ? { approval_mode: approvalMode } : {}),
      per_request_overrides: perRequestOverrides,
      ...selectedKnowledge,
    }, setupEditedFields.current, layered);
    if (pinnedMemory) Object.assign(values, selectedKnowledge);
    return { ...values, work_mode: workMode, helper_agent_ids: helperAgentIds, review, ...(projectId ? { project_id: projectId } : {}),
      ...(agentSetupVersionId || conversation?.agent_setup_version_id ? { agent_setup_version_id: agentSetupVersionId } : {}),
      ...(!projectId ? { project_path: projectPath.trim() || null } : {}),
      ...(!projectId || conversation?.workspace_id ? { workspace_id: conversation?.workspace_id ?? null } : {}) };
  }

  function applyResolvedSetup(selection: ResolvedSetupSelection, memoryRefs = hasFixedMemory(conversation) ? conversation?.memory_version_refs ?? [] : null) {
    const config = selection.configuration;
    if (config.deployment_id) setDeploymentId(config.deployment_id);
    else if (config.model_configuration_id) setDeploymentId("");
    else { const loaded = preferredChatDeploymentId(deployments, ""); setDeploymentId(loaded); }
    profileIdRef.current = config.model_configuration_id ?? config.profile_id ?? "";
    setProfileId(profileIdRef.current);
    setStartupOverrides(config.startup_overrides ?? {});
    setEmbeddingDeploymentId(config.embedding_deployment_id ?? "");
    if (!setupEditedFields.current.has("approval_mode")) setApprovalMode(approvalModeOf(config.approval_mode));
    setPerRequestOverrides(config.per_request_overrides ?? {});
    setSelectedKnowledgeIds([...(memoryRefs ?? config.memory_version_refs ?? []), ...(config.skill_version_refs ?? []), ...(config.protected_instruction_version_refs ?? [])]);
    setInstructionLayers(selection.instruction_layers ?? []);
    applyExecutionPreferences(config as ExecutionPreferences);
  }

  function applyExecutionPreferences(config: ExecutionPreferences) {
    setWorkMode(config.work_mode === "plan" ? "plan" : "work");
    setHelperAgentIds(config.helper_agent_ids ?? []);
    setReview({ enabled: config.review?.enabled === true, criteria: config.review?.criteria ?? "", max_revisions: 2 });
  }

  async function chooseSetup(nextProjectId: string | null, nextVersionId: string | null, overrides: SetupConfiguration = {}, preserveWorkspace = false, rejectOnFailure = false) {
    const request = ++setupRequest.current;
    const generation = selectionRequest.current;
    setSetupResolving(true); setSetupError("");
    try {
      const resolved = await workspaceApi.resolveSetup(nextProjectId, nextVersionId, overrides);
      if (request !== setupRequest.current || generation !== selectionRequest.current) {
        if (rejectOnFailure) throw new Error("The selected Chat changed while applying model settings. Try again.");
        return;
      }
      setupEditedFields.current = new Set(Object.keys(overrides));
      if (overrides.approval_mode == null) setupEditedFields.current.delete("approval_mode");
      setProjectId(nextProjectId); setAgentSetupVersionId(nextVersionId);
      if (!preserveWorkspace) setProjectPath(projects.find(project => project.id === nextProjectId)?.canonical_path ?? "");
      applyResolvedSetup(resolved);
    } catch (error) {
      if (request === setupRequest.current && generation === selectionRequest.current) setSetupError(errorMessage(error));
      if (rejectOnFailure) throw error;
    } finally {
      if (request === setupRequest.current) setSetupResolving(false);
    }
  }

  useEffect(() => {
    if (props.activeTab && props.activeTab !== "chat") return;
    void refresh().catch((error: unknown) => {
      setLoadError(errorMessage(error));
      setDeploymentsLoaded(true);
    });
  }, [props.activeTab]);

  useEffect(() => {
    if (!deploymentsLoaded || setupDefaultsLoading || modelWarm.current) return;
    modelWarm.current = true;
    const report = props.onModelPhase;
    if (window.workbench?.productName !== "Local AI Workbench") {
      report?.("none");
      return;
    }
    const preferred = preferredChatDeploymentId(deployments, deploymentId, profileIdRef.current);
    const selected = deployments.find(item => item.id === preferred);
    if (!selected || selected.scope !== "managed") {
      report?.(selected?.status === "running" ? "ready" : "none");
      return;
    }
    if (selected.status === "running") {
      report?.("ready");
      return;
    }
    if (selected.status !== "stopped") {
      report?.(selected.status === "starting" ? "starting" : "failed");
      return;
    }
    report?.("starting");
    void api.start(selected.id).then(next => {
      setDeployments(current => current.map(item => item.id === next.id ? next : item));
      report?.(next.status === "running" ? "ready" : "starting");
    }).catch(() => {
      report?.("failed");
      setMessage("The model did not start.");
    });
  }, [deploymentsLoaded, setupDefaultsLoading]);

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
    startupOverrides,
    projectPath,
    selectionLoading,
    sending,
    task,
    attachmentIds,
    approvalMode,
    workMode, helperAgentIds, review,
    perRequestOverrides,
    selectedKnowledgeIds,
    knowledgeEntries,
    projectId, agentSetupVersionId, setupResolving, hasApplicationDefaults,
  ]);

  const transcript = conversation ? displayedTranscript(conversation) : [];

  useEffect(() => {
    if (conversation?.current_run && !isAgentRunLive(conversation.current_run.status)) retainedAssets.refresh();
  }, [conversation?.current_run?.id, conversation?.current_run?.status]);

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
    applyExecutionPreferences({});
    setMessage("");
  }

  const selectionBusy = Boolean(props.restoringSelection) || Boolean(selectionLoading) || setupResolving || setupDefaultsLoading;
  const hasPendingCancelInput = Boolean(conversation?.pending_cancel_input_ids?.length);
  const runBusy = (conversation?.current_run ? isAgentRunLive(conversation.current_run.status) : false) || Boolean(pendingSubmit) || hasPendingCancelInput;
  const pendingSubmissionActive = Boolean(
    pendingSubmit &&
    conversation?.id === pendingSubmit.conversation_id &&
    interactionThreadId === pendingSubmit.thread_id &&
    boundGeneration === pendingSubmit.selection_generation,
  );
  const savingProjectState = conversation?.current_run?.finalization_phase === "saving_changes" && !pendingSubmissionActive;
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
  const hasModelChoice = Boolean(selectedProfile || deployments.some(item => item.id === deploymentId));
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
        // Selecting another saved agent resets the previous agent's overrides,
        // just as dispatch does. A restored draft keeps only its own new edits.
        const priorOverrides = nextVersionId === (next.agent_setup_version_id ?? null) ? next.setup_overrides ?? {} : {};
        const overrides = setupOverrides({ ...priorOverrides, ...draftConfig });
        let resolutionFailure = "";
        const resolved = nextProjectId || nextVersionId || hasApplicationDefaults ? await workspaceApi.resolveSetup(nextProjectId, nextVersionId, overrides).catch(error => { resolutionFailure = errorMessage(error); return null; }) : null;
        if (selectionRequest.current !== requestId || historyMutations.current.get(item.id) === "deleted") return;
        setupRequest.current += 1;
        setSetupResolving(false); setSetupError(resolutionFailure);
        setProjectId(nextProjectId); setAgentSetupVersionId(nextVersionId);
        setupEditedFields.current = new Set(Object.keys(overrides));
        if (overrides.approval_mode == null) setupEditedFields.current.delete("approval_mode");
        activeOwner.current = { conversationId: next.id, threadId: registered.thread_id, generation: requestId };
        setBoundGeneration(requestId);
        setConversation(next);
        setInteractionThreadId(registered.thread_id);
        setSelectionLoading(null);
        setDeploymentId(typeof draftConfig.deployment_id === "string" ? draftConfig.deployment_id : next.deployment_id);
        setEmbeddingDeploymentId(typeof draftConfig.embedding_deployment_id === "string" ? draftConfig.embedding_deployment_id : next.embedding_deployment_id ?? "");
        profileIdRef.current = typeof draftConfig.model_configuration_id === "string" ? draftConfig.model_configuration_id : typeof draftConfig.profile_id === "string" ? draftConfig.profile_id : next.setup_overrides?.model_configuration_id ?? next.profile_id ?? "";
        setProfileId(profileIdRef.current);
        setStartupOverrides(overrides.startup_overrides ?? {});
        setApprovalMode(approvalModeOf(overrides.approval_mode ?? (resolved ? resolved.configuration.approval_mode : next.approval_mode)));
        setPerRequestOverrides(draftConfig.per_request_overrides && typeof draftConfig.per_request_overrides === "object" ? draftConfig.per_request_overrides as Record<string, unknown> : {});
        applyExecutionPreferences({ ...(next as ExecutionPreferences), ...draftConfig } as ExecutionPreferences);
        setProjectPath(next.project_path ?? "");
        setSelectedKnowledgeIds([
          ...(next.memory_version_refs ?? []),
          ...(next.skill_version_refs ?? []),
          ...(next.protected_instruction_version_refs ?? []),
        ]);
        if (resolved) applyResolvedSetup(resolved, hasFixedMemory(next) ? next.memory_version_refs ?? [] : null);
        else setInstructionLayers([]);
        serverDraftRevision.current = next.draft?.revision ?? 0;
        draftRevision.current += 1;
        setTask(next.draft?.content ?? "");
        setAttachmentIds(next.draft?.attachment_ids ?? []);
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

  function reconcileHistory(items: ChatConversation[]): ChatConversation[] {
    return items.filter(item => historyMutations.current.get(item.id) !== "deleted").map(item => {
      const archived = historyMutations.current.get(item.id);
      return typeof archived === "boolean" ? { ...item, archived } : item;
    });
  }

  function removeConversation(id: string): void {
    historyMutations.current.set(id, "deleted");
    notifyAttentionChanged();
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
    if (conversation.current_run?.finalization_phase === "saving_changes") {
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
    if ((!text && !attachmentIds.length) || !hasModelChoice || selectionBusy || sending || (runBusy && !conversation) || (pendingSubmit && draftRevision.current === pendingSubmit.draft_revision)) {
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
    if (!conversation && (!task.trim() && !attachmentIds.length || !hasModelChoice)) return null;
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

  function openPermissions(): void {
    try { sessionStorage.setItem("workbench.settings.category", "Permissions"); } catch { /* Navigation still works without storage. */ }
    navigateAway("settings");
  }

  function helperModelLabel(agent: AgentSetup): string {
    const configuration = (agent.configuration ?? {}) as Record<string, unknown>;
    const selectedProfile = profiles.find(profile => profile.id === (configuration.model_configuration_id || configuration.profile_id));
    if (selectedProfile) return selectedProfile.display_name;
    const model = deployments.find(deployment => deployment.id === configuration.deployment_id);
    return model?.display_name ?? "Uses this chat's model";
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
        if (!cancelled) props.onWorkspaceLaunchHandled?.();
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
    if (conversation || !task.trim() || !hasModelChoice || sending || selectionBusy) return;
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
  }, [conversation?.id, task, selectedDeployment?.id, profileId, sending, selectionBusy]);

  async function openAttachments(files?: File[]): Promise<void> {
    if (conversation) {
      if (files) setIncomingDrop({ id: crypto.randomUUID(), sessionId: conversation.id, files });
      return;
    }
    if (!hasModelChoice || sending || selectionBusy) return;
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
          if (error instanceof ApiError && error.status === 404) {
            setMessage("That chat is no longer available.");
            return;
          }
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
    }).catch(fail).finally(() => props.onReuseAssetHandled?.());
  }, [props.reuseAssetId, props.reuseAssetIds, conversation?.id, selectedDeployment?.id, sending, selectionBusy]);

  return (
    <ChatDockContext.Provider value={{ openFile }}>
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
          if (!hasModelChoice || selectionBusy || sending) {
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
            <h2>{conversation ? conversationTitle(conversation) : selectionLoading ? conversationTitle(selectionLoading) : props.restoringSelection ? "Opening conversation…" : "New conversation"}</h2>
          </div>
          <div className="chat-header-actions"><MenuPopover label="Conversation view" align="end" placement="below" trigger={<Icon name="tune" size={16} />}><CompactSwitch label="Reasoning and tools" checked={presentation.detailed_streams} description="Show the model's reasoning and detailed tool activity. This does not change how the model thinks." onChange={checked => { void api.updatePresentationSettings({ detailed_streams: checked }).then(saved => props.onPresentationChange?.(saved)).catch(fail); }} /></MenuPopover>
          <button type="button" className={`icon-button${railOpen ? " is-on" : ""}`} aria-pressed={railOpen} aria-label={railOpen ? "Close conversation rail" : "Open conversation rail"} title={railOpen ? "Close the side rail" : "Setup, files, library, and actions"} onClick={() => {
            const next = !railOpen;
            setRailOpen(next);
            try { sessionStorage.setItem("workbench.chat.rail", next ? "open" : "closed"); } catch { /* The toggle still applies. */ }
          }}><Icon name="panelRight" /></button></div>
        </header>
        <div className={`chat-workspace${railOpen ? " files-open" : ""}`}>
        <div className="chat-conversation">
        {loadError ? <Notice tone="error" action={<button type="button" onClick={() => void refresh().catch((error: unknown) => setLoadError(errorMessage(error)))}>Retry</button>}>{loadError}</Notice> : null}
        <div className="transcript">
          {props.restoringSelection ? <EmptyState title="Opening conversation">Restoring your last conversation.</EmptyState> : deploymentsLoaded && deployments.length === 0 && !conversation ? (
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
          {runBusy && !pendingInterrupt && (pendingStopActive || !canObserveInteraction) ? (
            <p className="hint" role="status">
              {savingProjectState ? "Saving project state…" : "Working…"} {pendingStopActive ? (
                <StatusBadge label="Stopping submission" tone="warn" />
              ) : savingProjectState ? null : pendingSubmissionActive ? (
                <StatusBadge label="Loading model" tone="live" />
              ) : (
                <StatusBadge status={conversation?.current_run?.status} />
              )}
            </p>
          ) : null}
        </div>

        {deployHealthNotice && !runBusy ? (
          <Notice tone={deployHealthNotice.tone}>
            {deployHealthNotice.message}
          </Notice>
        ) : null}
        {message && message !== conversation?.deploy_health?.message ? (
          <Notice tone="error">{message}</Notice>
        ) : null}
        {setupError ? <Notice tone="error">{setupError}</Notice> : null}

        </div>
        <aside className="chat-files-panel chat-rail" aria-label="Conversation rail" hidden={!railOpen}>
          <PanelResize label="Resize conversation rail" width={filesWidth} onResize={setFilesWidth} min={280} max={720} reset={320} reverse />
          <div className="chat-rail-tabs" role="tablist" aria-label="Conversation rail pages">
            {(["setup", "files", "library", "actions"] as const).map(page => (
              <button key={page} type="button" role="tab" aria-selected={railPage === page} onClick={() => openRail(page)}>{page === "setup" ? "Setup" : page === "files" ? "Files" : page === "library" ? "Library" : "Actions"}</button>
            ))}
            <button type="button" className="icon-button chat-rail-close" aria-label="Close conversation rail" title="Close" onClick={() => { setRailOpen(false); try { sessionStorage.setItem("workbench.chat.rail", "closed"); } catch { /* Closed for this view. */ } }}><Icon name="close" size={14} /></button>
          </div>
          <div className="chat-rail-body">
            <div hidden={railPage !== "setup"}><ConversationSetup
              projectId={projectId}
              projects={projects}
              conversation={Boolean(conversation)}
              selectionBusy={selectionBusy}
              sending={sending}
              agentSetupVersionId={agentSetupVersionId}
              agentSetups={agentSetups}
              onProject={value => void chooseSetup(value, agentSetupVersionId)}
              onAgent={value => void chooseSetup(projectId, value, {}, Boolean(conversation))}
              setupResolving={setupResolving}
              onManageAgents={() => navigateAway("agents")}
              instructionLayers={instructionLayers}
              missingDeployment={missingDeployment}
              selectedProfile={selectedProfile}
              embeddingDeploymentId={embeddingDeploymentId}
              onEmbedding={value => { markSetupEdited("embedding_deployment_id"); setEmbeddingDeploymentId(value); }}
              embedderDeployments={embedderDeployments}
              deployments={deployments}
              knowledgeEntries={knowledgeEntries}
              selectedKnowledgeIds={selectedKnowledgeIds}
              memoryLocked={hasFixedMemory(conversation) || Boolean(pendingSubmit && pendingSubmit.conversation_id === conversation?.id)}
              pinnedMemoryVersionIds={conversation?.memory_version_refs ?? []}
              onToggleKnowledge={versionId => {
                if (hasFixedMemory(conversation) && knowledgeEntries.some(entry => entry.kind === "memory" && entry.current_version_id === versionId)) return;
                markSetupEdited("memory_version_refs", "skill_version_refs", "protected_instruction_version_refs", "knowledge_version_refs");
                setSelectedKnowledgeIds(current => current.includes(versionId) ? current.filter(item => item !== versionId) : [...current, versionId]);
              }}
              tools={tools}
              filesystemToolsAvailable={conversation?.filesystem_tools_available}
              shellToolsAvailable={conversation?.shell_tools_available}
            /></div>
            {railPage === "actions" ? conversation ? <ChatHistoryActions
              key={conversation.id}
              conversation={conversation}
              disabled={runBusy || selectionBusy || sending}
              onConversationCreated={(next) => {
                cacheConversation(next);
                if (activeOwner.current.conversationId === conversation.id) chooseConversation(next);
              }}
              onDeleted={removeConversation}
              onError={setMessage}
            /> : <p className="hint">Start a chat to rename, export, or delete it.</p> : null}
            {railPage === "files" || railPage === "library" ? <ChatDock
              page={railPage}
              showPages={false}
              onPage={page => openRail(page)}
              projectId={conversation?.project_id ?? projectId}
              runIds={conversation?.run_ids ?? []}
              currentRunId={conversation?.current_run_id}
              currentRunStatus={conversation?.current_run?.status}
              selectedPath={selectedPath}
              onSelectPath={setSelectedPath}
              conversationId={conversation?.id}
              projectPath={conversation?.project_path}
              onOpenKnowledge={() => navigateAway("knowledge")}
              onReuseAssets={assets => {
                draftRevision.current += 1;
                setAttachmentIds(current => [...new Set([...current, ...assets.map(asset => asset.id)])]);
              }}
            /> : null}
          </div>
        </aside>

        <form
          className="compose"
          onSubmit={(event) => {
            event.preventDefault();
            event.currentTarget.querySelectorAll<HTMLDetailsElement>("details[open]").forEach(menu => { menu.open = false; });
            void sendTurn();
          }}
        >
          {conversation ? <ChatQueuePanel
            key={conversation.id}
            conversation={conversation}
            deployments={modelChoices}
            profiles={profiles}
            disabled={selectionBusy || sending}
            onUpdated={applyConversationUpdate}
            onError={setMessage}
          /> : null}
          <input ref={filePicker} className="sr-only" type="file" multiple aria-label="Choose files to attach" disabled={!hasModelChoice || sending || selectionBusy} onChange={event => { const files = Array.from(event.target.files ?? []); event.currentTarget.value = ""; if (files.length) void openAttachments(files); }} />
          {conversation ? <div><ComposerAttachments
            compact
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
            <MenuPopover label="Add to message" trigger={<Icon name="plus" />} disabled={!hasModelChoice || sending || selectionBusy}>{close => <>
              <button type="button" className="menu-action" onClick={() => { close(); filePicker.current?.click(); }}><Icon name="files" />Attach files or images</button>
              <button type="button" className="menu-action" onClick={() => { close(); openRail("library"); }}><Icon name="library" />Choose from Library</button>
              <button type="button" className="menu-action" onClick={() => { close(); openRail("setup"); }}><Icon name="knowledge" />Skills and context</button>
              <div className="menu-section"><CompactSwitch label="Review before finishing" checked={review.enabled} onChange={enabled => { markSetupEdited("review"); setReview(current => ({ ...current, enabled })); }} description="Checks the result against your criteria and revises it up to twice." />{review.enabled ? <><label>Review criteria<textarea rows={2} value={review.criteria} placeholder="What should a good result satisfy?" onChange={event => { markSetupEdited("review"); setReview(current => ({ ...current, criteria: event.target.value })); }} /></label><small className="hint">Up to 2 revisions</small></> : null}</div>
            </>}</MenuPopover>
            <MenuPopover label="Approval mode" trigger={<><Icon name="shield" /><span>{approvalModeLabel(approvalMode)}</span></>}>
                <ApprovalModeControl value={approvalMode} disabled={selectionBusy || sending} onChange={mode => { markSetupEdited("approval_mode"); setApprovalMode(mode); }} />
                <div className="menu-section"><HoverHelp title="When access changes">Applies to your next message. Running and queued messages keep their chosen access. Tools that are off stay off. Plan mode stays read-only at every access level.</HoverHelp></div>
                <button type="button" className="chat-tools-permissions" onClick={openPermissions}><Icon name="settings" size={14} /> Saved permissions</button>
            </MenuPopover>
            <MenuPopover label="Work mode" trigger={<><Icon name={workMode === "plan" ? "knowledge" : "agent-run"} size={16} /><span>{workMode === "plan" ? "Plan" : "Work"}</span></>} disabled={selectionBusy || sending}>{close => <div className="chat-mode-options" role="radiogroup" aria-label="Work mode">{(["work", "plan"] as const).map(mode => <button type="button" className="menu-action" role="radio" aria-checked={workMode === mode} key={mode} onClick={() => { markSetupEdited("work_mode"); setWorkMode(mode); close(); }}><Icon name={mode === "plan" ? "knowledge" : "agent-run"} /><span>{mode === "plan" ? "Plan" : "Work"}<small>{mode === "plan" ? "Read-only investigation and planning" : "Use tools with the selected access"}</small></span></button>)}</div>}</MenuPopover>
            <ChatModelControls deployments={modelChoices} profiles={profiles} selectedDeploymentId={deploymentId} selectedConfigurationId={profileId || undefined} configuration={setupOverrides(chatConfiguration())} projectId={projectId} agentSetupVersionId={agentSetupVersionId} conversationId={conversation?.id} runtimeBusy={runBusy || Boolean(conversation?.queue?.length)} disabled={selectionBusy || sending} onReloaded={refresh} onApply={async configuration => {
              await chooseSetup(projectId, agentSetupVersionId, configuration, true, true);
              await refresh();
            }} />
            <MenuPopover label="Named helpers" align="end" trigger={<><Icon name="sparkles" size={16} />{helperAgentIds.length ? <span>{helperAgentIds.length}</span> : null}</>} disabled={selectionBusy || sending}><h3>Helpers</h3>{agentSetups.length ? agentSetups.map(agent => <label className="helper-choice" key={agent.id}><input type="checkbox" checked={helperAgentIds.includes(agent.id)} disabled={Boolean(agent.missing_dependencies?.length)} title={agent.missing_dependencies?.map(issue => issue.reason).join(", ")} onChange={event => { markSetupEdited("helper_agent_ids"); setHelperAgentIds(current => event.target.checked ? [...current, agent.id] : current.filter(id => id !== agent.id)); }} /><span>{agent.name}<small>{helperModelLabel(agent)}</small></span></label>) : <p className="hint">Create an agent to choose a helper.</p>}<div className="menu-section"><small className="hint">Only selected helpers can run. Helpers cannot delegate again.</small><button type="button" className="menu-action" onClick={() => navigateAway("agents")}>Manage agents</button></div></MenuPopover>
            <span className="composer-spacer" />
            <ChatMeasurements run={conversation?.current_run} />
            <button
              type="button"
              aria-label={savingProjectState ? "Saving project state" : pendingStopActive ? "Stopping…" : "Stop"}
              className="stop-button"
              data-idle={!runBusy && !pendingStopActive}
              disabled={!conversation || !runBusy || pendingStopActive || savingProjectState}
              title={savingProjectState ? "Execution finished; saving project state" : undefined}
              onClick={stopCurrentWork}
            >
              <Icon name="stop" size={16} /><span className="sr-only">{savingProjectState ? "Saving project state" : pendingStopActive ? "Stopping…" : "Stop"}</span>
            </button>
            <button
              type="submit"
              aria-label={props.restoringSelection || selectionLoading ? "Opening conversation…" : selectionBusy ? "Loading settings…" : sending ? "Sending…" : runBusy ? "Queue message" : "Send"}
              className="send-button"
              title={runBusy ? "Queue this message" : "Send message"}
              disabled={!hasModelChoice || (!task.trim() && !attachmentIds.length) || selectionBusy || sending || Boolean(pendingSubmit && draftRevision.current === pendingSubmit.draft_revision)}
            >
              <Icon name="send" /><span className="sr-only">{props.restoringSelection || selectionLoading ? "Opening conversation…" : selectionBusy ? "Loading settings…" : sending ? "Sending…" : runBusy ? "Queue message" : "Send"}</span>
            </button>
          </div>
        </form>
        </div>
      </div>
    </section>
    </ChatDockContext.Provider>
  );
}
