import { useCallback, useEffect, useLayoutEffect, useRef, useState, type ComponentProps, type CSSProperties, type RefObject } from "react";
import { PanelResize, usePanelWidth } from "./PanelResize";
import { AnswerActions } from "./AnswerActions";
import { areaLabel, newestConversationFirst } from "./conversationAreas";
import { MenuPopover } from "./MenuPopover";
import { CompactSwitch } from "./CompactControls";
import { HoverHelp } from "./HoverHelp";

import { api, ApiError, request } from "./api";
import { workspaceApi, type ProjectRecord, type AgentSetup, type SetupConfiguration, type ResolvedSetupSelection, type ChatReadiness } from "./workspaceApi";
import { browserToolNames, buildChatConfiguration, creationConfiguration, executionConfiguration, setupOverrides, standardToolSelection, type ChatWorkspaceLaunch, type ToolCatalogueProjection } from "./chatSetup";
import { ApprovalModeControl, approvalModeLabel, approvalModeOf, type ApprovalMode } from "./ApprovalModeControl";
import { Icon } from "./Icon";
import type { ChatLaunch, ConversationListActions, HistoryNotice } from "./WorkbenchSidebar";
import { ComposerAttachments } from "./ComposerAttachments";
import { acceptedProjectFilePath, ChatDock, chatDockGeometry, isRefusedProjectPathNotice, refusedProjectPathNotice, useConversationDockView, type ChatRailPage } from "./ChatDock";
import { ComposerPicker, composerMatches, type ComposerChoice } from "./ComposerPicker";
import { MessageTaskActions } from "./MessageTaskActions";
import { VisualTestingControls } from "./VisualTestingControls";
import { BrowserRail, useBrowserRailActivity } from "./BrowserRail";

type RailPage = ChatRailPage;
import { ChatDockContext } from "./chatDockContext";
import { packet03Api, packet03Request } from "./packet03Api";
import { ChatModelControls } from "./ChatModelControls";
import { HelperRail, helperEntries, helperIsActive } from "./HelperRail";
import { ChatMeasurements, publishLiveMeasurement, readLiveMeasurement, useLiveMeasurement } from "./ChatMeasurements";
import { AgentInputs } from "./AgentInputs";
import { scopedSetupConfiguration } from "./SetupConfigurationEditor";
import type { AgentInputPolicy, CapabilitySetupRequest } from "./agentInputPolicy";
import { ChatRetainedFiles, useChatRetainedAssets } from "./ChatRetainedFiles";
import { copyRetainedAsset } from "./retainedFiles";
import { ChatDraftWriter, sameDraftValue } from "./chatDraftWriter";
import { ChatHistoryActions } from "./ChatHistoryActions";
import { applyExecutionPreferences as applyExecutionPreferencesAction, type ExecutionPreferences } from "./chatPanelExecution";
import { applyConversationUpdate as applyConversationUpdateAction, chooseConversation as chooseConversationAction, reconcileHistory as reconcileHistoryAction, removeConversation as removeConversationAction, selectConversation as selectConversationAction } from "./chatPanelConversation";
import { recoverRun as recoverRunAction, stopCurrentWork as stopCurrentWorkAction } from "./chatPanelRunControls";
import { configureCapability as configureCapabilityAction, createDraftConversation as createDraftConversationAction, editInputs as editInputsAction } from "./chatPanelComposerActions";
import { ChatQueuePanel } from "./ChatQueuePanel";
import { AgentMessageFeed, helperKey } from "./AgentMessageFeed";
import { RunActivitySummary, helperApprovalOwner } from "./RunActivitySummary";
import { conversationTitle, displayedTranscript, formatWhen } from "./display";
import { EmptyState } from "./EmptyState";
import { errorMessage } from "./errors";
import { InteractionStream, useWorkbenchProjection, visibleApprovalInterrupt, type WorkbenchStream } from "./InteractionStream";
import { InterruptApproval } from "./InterruptApproval";
import { Notice } from "./Notice";
import {
  isAgentRunLive,
  isDeclaredEmbedder,
  type ChatConversation,
  type ChatMessage,
  type AgentRun,
  type Deployment,
  type KnowledgeEntry,
  type ModelBundle,
  type PresentationSettings,
  type RunProfile,
  type DesktopAccess,
  type WorkbenchTab,
} from "./types";
import "./ChatPanel.css";

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
  document_asset_ids?: string[];
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
  rewind_source_run_id?: string;
  rewind_mode?: "retry" | "edit";
}

function rewindFailureNotice(pending: PendingChatSubmit, accepted: boolean, fallback: string): string {
  if (accepted || !pending.rewind_mode) return fallback;
  return pending.rewind_mode === "edit"
    ? "This edit did not start. The chat was left as it is."
    : "This retry did not start. The chat was left as it is.";
}

const nonBlockingReadinessIssues = new Set(["chat_turn_active", "model_load_required", "readiness_unavailable"]);

function readinessBlocksSend(value: ChatReadiness | null): boolean {
  if (!value || value.can_send || value.status === "unverified") return false;
  return !value.issues.length || value.issues.some(issue => !nonBlockingReadinessIssues.has(issue.code));
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
  onHelperOpen: (runId: string, toolCallId: string) => void;
  onHelperActivity: (conversationId: string, active: number, total: number) => void;
  historicalRuns: AgentRun[];
  onRecoverRun?: (run: AgentRun) => void;
  onConfigureSetup?: (setup: CapabilitySetupRequest) => void;
  noteRewindResult: (pending: PendingChatSubmit, accepted: boolean) => void;
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
    noteRewindResult,
  } = props;
  const owner = { conversationId: conversation.id, threadId, generation: selectionGeneration };
  const reconciledSubmissionErrors = useRef(new Set<string>());
  const submissionErrorOwner = useRef<string | null>(null);
  const submissionFailure = useRef<{ inputId: string; message: string; accepted?: boolean } | null>(null);
  const [observationEpoch, setObservationEpoch] = useState(0);
  const queueActive = conversation.queue?.some(item => item.status === "queued" || item.status === "dispatching") ?? false;
  const queuePresent = Boolean(conversation.queue?.length);
  const queueHasRun = conversation.queue?.some(item => item.run_id || Boolean(conversation.current_run?.input_message_id && item.input_message_id === conversation.current_run.input_message_id)) ?? false;
  const observedQueue = useRef({ active: queueActive, present: queuePresent, hasRun: queueHasRun });
  const currentSubmissionView = useRef({ conversation, pendingSubmit, observationEpoch });
  currentSubmissionView.current = { conversation, pendingSubmit, observationEpoch };
  if (pendingSubmit && submissionErrorOwner.current !== pendingSubmit.id) {
    submissionErrorOwner.current = pendingSubmit.id;
    reconciledSubmissionErrors.current.clear();
    submissionFailure.current = null;
  }
  useEffect(() => {
    if (pendingSubmit || !submissionFailure.current?.accepted) return;
    // The SDK can abandon its deferred subscription when the command response
    // fails. Rehydrate confirmed accepted work without resubmitting its input.
    submissionFailure.current = null;
    setObservationEpoch(value => value + 1);
  }, [pendingSubmit]);
  useEffect(() => {
    const previous = observedQueue.current;
    observedQueue.current = { active: queueActive, present: queuePresent, hasRun: queueHasRun };
    if (pendingSubmit || (conversation.current_run && isAgentRunLive(conversation.current_run.status))) return;
    if (previous.active !== queueActive && (previous.active || previous.present) && (queueActive || !previous.hasRun)) {
      // A waiting input can be removed or paused without producing a run
      // lifecycle event. Retire its SDK wait, or observe a resumed queue.
      setObservationEpoch(value => value + 1);
    }
  }, [queueActive, queuePresent, queueHasRun, pendingSubmit, conversation.current_run]);
  return (
    <InteractionStream
      key={observationEpoch}
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
            submissionFailure.current = { inputId: pendingSubmit.id, message: errorText };
            void api.chatConversation(pendingSubmit.conversation_id)
              .then((next) => {
                if (!isCurrentOwner(owner)) {
                  return;
                }
                updateConversation(next, owner);
                clearPendingSubmit(pendingSubmit);
                if (chatHasAcceptedInputMessage(next, pendingSubmit.id)) {
                  submissionFailure.current = { inputId: pendingSubmit.id, message: errorText, accepted: true };
                  noteRewindResult(pendingSubmit, true);
                  clearSubmittedDraft(pendingSubmit);
                  refreshDeployments();
                  setMessage("");
                  return;
                }
                noteRewindResult(pendingSubmit, false);
                setMessage(rewindFailureNotice(pendingSubmit, false, errorMessage(error)));
              })
              .catch(() => {
                if (isCurrentOwner(owner)) {
                  setMessage("Connection interrupted. Checking whether the message was accepted.");
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
          submissionFailure={submissionFailure}
          onSubmissionError={(submitted, error, runObserved) => {
            const stillOwned = () => isCurrentOwner(owner) && submissionErrorOwner.current === submitted.id
              && currentSubmissionView.current.observationEpoch === observationEpoch;
            if (!stillOwned()) return;
            const current = currentSubmissionView.current;
            // Admission can be confirmed before the command response arrives.
            // The SDK reports a late command rejection through onError rather
            // than rejecting submit(), so keep its exact input attribution.
            if (current.pendingSubmit || (!runObserved && !chatHasAcceptedInputMessage(current.conversation, submitted.id))) return;
            const errorText = errorMessage(error);
            reconciledSubmissionErrors.current.add(errorText);
            if (runObserved) {
              // A warm SDK stream can observe the accepted run before its
              // command response. Distinguish that late response failure from
              // a real failed run without replacing the working observer.
              void api.chatConversation(submitted.conversation_id).then(next => {
                if (!stillOwned()) return;
                const failed = next.current_run?.input_message_id === submitted.id && next.current_run.status === "failed";
                const accepted = chatHasAcceptedInputMessage(next, submitted.id);
                noteRewindResult(submitted, accepted);
                setMessage(failed || !accepted ? rewindFailureNotice(submitted, accepted, errorText) : "");
              }).catch(() => { if (stillOwned()) setMessage(errorText); });
              return;
            }
            submissionFailure.current = null;
            setMessage("");
            setObservationEpoch(value => value + 1);
          }}
          clearPendingSubmit={clearPendingSubmit}
          updateConversation={updateConversation}
          updateConversationIfCurrentRun={updateConversationIfCurrentRun}
          updateConversationForRun={updateConversationForRun}
          clearSubmittedDraft={clearSubmittedDraft}
          refreshDeployments={refreshDeployments}
          setMessage={setMessage}
          isCurrentOwner={isCurrentOwner}
          onHelperOpen={props.onHelperOpen}
          onHelperActivity={props.onHelperActivity}
          historicalRuns={props.historicalRuns}
          onRecoverRun={props.onRecoverRun}
          noteRewindResult={noteRewindResult}
          onConfigureSetup={props.onConfigureSetup}
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
  submissionFailure: RefObject<{ inputId: string; message: string; accepted?: boolean } | null>;
  onSubmissionError: (submitted: PendingChatSubmit, error: unknown, runObserved: boolean) => void;
  clearPendingSubmit: (pending: PendingChatSubmit) => void;
  updateConversation: (conversation: ChatConversation, owner: SelectionOwner) => void;
  updateConversationIfCurrentRun: (conversation: ChatConversation, owner: SelectionOwner, expectedRunId: string | null) => void;
  updateConversationForRun: (conversation: ChatConversation, owner: SelectionOwner, runId: string) => void;
  clearSubmittedDraft: (pending: PendingChatSubmit) => void;
  refreshDeployments: () => void;
  setMessage: (message: string) => void;
  isCurrentOwner: (owner: SelectionOwner) => boolean;
  onHelperOpen: (runId: string, toolCallId: string) => void;
  onHelperActivity: (conversationId: string, active: number, total: number) => void;
  historicalRuns: AgentRun[];
  onRecoverRun?: (run: AgentRun) => void;
  onConfigureSetup?: (setup: CapabilitySetupRequest) => void;
  noteRewindResult: (pending: PendingChatSubmit, accepted: boolean) => void;
}) {
  const {
    stream,
    owner,
    conversation,
    pendingSubmit,
    submissionFailure,
    clearPendingSubmit,
    updateConversation,
    updateConversationIfCurrentRun,
    updateConversationForRun,
    clearSubmittedDraft,
    refreshDeployments,
    setMessage,
    isCurrentOwner,
    noteRewindResult,
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
  // Admission and stream publication are separate observations. Keep the
  // verified transcript mounted while the next run catches up; unverified
  // projections still cannot target controls or update conversation state.
  const verifiedProjection = useRef<typeof projection | null>(null);
  if (projectionRunOwned) verifiedProjection.current = projection;
  const displayProjection = projectionRunOwned ? projection : verifiedProjection.current;
  const displayRun = displayProjection?.run ?? null;
  const visibleInterrupt = visibleApprovalInterrupt(stream, run ?? conversation.current_run);
  const currentParentRun = displayRun ?? (projectionRunOwned ? conversation.current_run : null);
  const helperRuns = [...props.historicalRuns, ...(currentParentRun ? [currentParentRun] : [])];
  const helpers = helperEntries(helperRuns, projectionRunOwned ? stream.subagents.values() : [], currentParentRun?.id);
  const helperById = new Map(helpers.map(helper => [helper.key, helper]));
  useEffect(() => {
    if (projectionRunOwned) props.onHelperActivity(conversation.id, helpers.filter(helper => helperIsActive(helper.status)).length, helpers.length);
  }, [conversation.id, helpers.map(helper => `${helper.key}:${helper.status}`).join("|"), projectionRunOwned, props.onHelperActivity]);
  const helperName: NonNullable<ComponentProps<typeof AgentMessageFeed>["helperName"]> = (tool, runId) => {
    const args = typeof tool.args === "object" && tool.args ? tool.args as Record<string, unknown> : {};
    const agentId = typeof args.subagent_type === "string" ? args.subagent_type : "";
    const parent = helperRuns.find(item => item.id === runId);
    return (helperById.get(runId && tool.id ? helperKey(runId, tool.id) : "")?.name ?? parent?.helper_snapshots?.find(item => item.agent_id === agentId)?.name ?? agentId) || "Helper";
  };
  const helperStatus: NonNullable<ComponentProps<typeof AgentMessageFeed>["helperStatus"]> = (tool, runId) => {
    const status = helperById.get(runId && tool.id ? helperKey(runId, tool.id) : "")?.status;
    return status ? status.replaceAll("_", " ") : tool.status === "error" ? "Failed" : tool.status === "finished" ? "Done" : "Working";
  };
  const projectionSignature = useRef("");
  const ownershipLookupKey = useRef("");
  const terminalRefreshKey = useRef("");
  const submittedIds = useRef(new Set<string>());
  const observerMounted = useRef(true);
  useEffect(() => {
    observerMounted.current = true;
    return () => { observerMounted.current = false; };
  }, []);

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
    if (!run || !projectionRunOwned || !isCurrentOwner(owner)) {
      return;
    }
    const signature = JSON.stringify({
      runId: run?.id ?? null,
      runStatus: run?.status ?? null,
      finalizationPhase: run?.finalization_phase ?? null,
      eventCount: run?.events.length ?? null,
      childRuns: run?.child_runs?.map(child => `${child.tool_call_id}:${child.status}:${child.namespace.join("|")}`) ?? [],
    });
    publishLiveMeasurement({
      ownerKey: JSON.stringify([owner.conversationId, owner.threadId, owner.generation]),
      runId: run.id,
      status: run.status,
      activityPhase: run.activity_phase,
      finalizationPhase: run.finalization_phase,
      waiting: Boolean(run.pending_interrupt),
      generation: run.generation_observation,
      history: run.generation_history,
      context: run.context_observation,
    });
    if (projectionSignature.current === signature) {
      return;
    }
    projectionSignature.current = signature;
    if (pendingSubmit && projectionMatchesPendingSubmit && pendingSubmit.rewind_source_run_id) {
      const submitted = pendingSubmit;
      // The server cut has to land before pendingSubmit clears. Clearing it cancels the reconcile fetch.
      void api.chatConversation(conversation.id).then((next) => {
        if (!isCurrentOwner(owner) || !chatHasAcceptedInputMessage(next, submitted.id)) return;
        noteRewindResult(submitted, true);
        updateConversation(next, owner);
        clearSubmittedDraft(submitted);
        clearPendingSubmit(submitted);
        refreshDeployments();
      }).catch((error: unknown) => {
        if (isCurrentOwner(owner)) setMessage(errorMessage(error));
      });
      return;
    }
    if (pendingSubmit && projectionMatchesPendingSubmit) {
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
  }, [clearPendingSubmit, clearSubmittedDraft, conversation, isCurrentOwner, noteRewindResult, owner, pendingSubmit, projectionMatchesPendingSubmit, projectionRunOwned, refreshDeployments, run, setMessage, updateConversation]);

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
        { multitaskStrategy: "reject", metadata: { workbench: { ...workbench, draft_revision: submittedDraftRevision } },
          onError: error => {
            if (observerMounted.current) props.onSubmissionError(pendingSubmit, error,
              verifiedProjection.current?.run?.input_message_id === pendingSubmit.id);
          } },
      )
      .then(() => refreshDeployments())
      .catch((error: unknown) => {
        if (!isCurrentOwner(owner)) {
          return;
        }
        submissionFailure.current = { inputId: pendingSubmit.id, message: errorMessage(error) };
        void api.chatConversation(pendingSubmit.conversation_id)
          .then((next) => {
            if (!isCurrentOwner(owner)) {
              return;
            }
            const acceptedInput = chatHasAcceptedInputMessage(next, pendingSubmit.id);
            if (acceptedInput) noteRewindResult(pendingSubmit, true);
            updateConversation(next, owner);
            clearPendingSubmit(pendingSubmit);
            if (acceptedInput) {
              submissionFailure.current = { inputId: pendingSubmit.id, message: errorMessage(error), accepted: true };
              clearSubmittedDraft(pendingSubmit);
              setMessage("");
              return;
            }
            noteRewindResult(pendingSubmit, false);
            setMessage(rewindFailureNotice(pendingSubmit, false, errorMessage(error)));
          })
          .catch(() => {
            if (isCurrentOwner(owner)) {
              setMessage("Connection interrupted. Checking whether the message was accepted.");
            }
          });
      });
  }, [clearPendingSubmit, clearSubmittedDraft, isCurrentOwner, owner, pendingSubmit, setMessage, stream, submissionFailure, updateConversation]);

  useEffect(() => {
    if (!pendingSubmit || !isCurrentOwner(owner)) return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const reconcile = async () => {
      try {
        const next = await api.chatConversation(pendingSubmit.conversation_id);
        if (cancelled || !isCurrentOwner(owner)) return;
        if (chatHasAcceptedInputMessage(next, pendingSubmit.id)) {
          if (submissionFailure.current?.inputId === pendingSubmit.id) submissionFailure.current.accepted = true;
          noteRewindResult(pendingSubmit, true);
          updateConversationIfCurrentRun(next, owner, conversation.current_run_id ?? null);
          clearSubmittedDraft(pendingSubmit);
          clearPendingSubmit(pendingSubmit);
          refreshDeployments();
          setMessage("");
          return;
        }
        if (submissionFailure.current?.inputId === pendingSubmit.id) {
          updateConversationIfCurrentRun(next, owner, conversation.current_run_id ?? null);
          clearPendingSubmit(pendingSubmit);
          setMessage(submissionFailure.current.message);
          return;
        }
      } catch {
        // The interaction stream still owns submission errors and reconnects.
      }
      if (!cancelled) timer = setTimeout(() => void reconcile(), 5000);
    };
    timer = setTimeout(() => void reconcile(), 1000);
    return () => {
      cancelled = true;
      if (timer !== undefined) clearTimeout(timer);
    };
  }, [pendingSubmit, owner.conversationId, owner.threadId, owner.generation, conversation.current_run_id,
    isCurrentOwner, noteRewindResult, updateConversationIfCurrentRun, clearSubmittedDraft, clearPendingSubmit, refreshDeployments, setMessage, submissionFailure]);

  return (
    <>
        <AgentMessageFeed showLiveMessageStatus={false} waiting={Boolean(projectionRunOwned && visibleInterrupt)} onHelperOpen={props.onHelperOpen} helperName={helperName} helperStatus={helperStatus} hiddenHelperResultIds={new Set(helpers.map(helper => helper.key))} helperRuns={helperRuns} currentRunId={currentParentRun?.id} currentInputMessageId={currentParentRun?.input_message_id} toolOrigins={displayProjection?.workbench?.tool_origins} toolCallOrigins={displayProjection?.toolCallOrigins} toolAuthorizations={displayRun?.tool_authorizations} toolAuthorizationGrants={displayRun?.tool_authorization_grants} live={displayRun ? isAgentRunLive(displayRun.status) : projectionRunOwned && stream.isLoading} sourceScope={{ sessionId: conversation.id, projectPath: conversation.project_path ?? undefined }} messages={displayProjection?.messages ?? []} toolCalls={displayProjection?.toolCalls ?? []} incompleteMessageIds={displayProjection?.incompleteMessageIds} detailedStreams={props.detailedStreams} renderMessageFooter={props.renderMessageFooter} renderAnswerActions={props.renderAnswerActions} userMessageContent={message => {
          const retained = conversation.transcript.find(item => item.id === message.id && item.role === "user");
          if (!retained) return undefined;
          // Model-only context is never part of the submitted user message.
          // Retained attachments already have their own file cards.
          return retained.attachment_ids?.length ? retained.content : [
            { type: "text", text: retained.content }, ...(retained.content_blocks ?? []),
          ];
        }} />
      {projectionRunOwned ? <RunActivitySummary run={run} showHelpers={false} onRecover={props.onRecoverRun} /> : null}
      {projectionRunOwned && visibleInterrupt ? (
        <InterruptApproval
          ownerLabel={helperApprovalOwner(run, visibleInterrupt.namespace)}
          pending={visibleInterrupt.pending}
          onConfigureSetup={props.onConfigureSetup}
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

function boundDeploymentForModelIntent(conversation: ChatConversation, configurationId: string, startup: unknown): string {
  if (!configurationId || !conversation.deployment_id) return "";
  const boundConfigurationId = conversation.model_configuration_id ?? conversation.setup_overrides?.model_configuration_id ?? conversation.profile_id;
  const boundStartup = conversation.startup_overrides ?? conversation.setup_overrides?.startup_overrides ?? {};
  return configurationId === boundConfigurationId && (startup === undefined || sameDraftValue(startup, boundStartup))
    ? conversation.deployment_id : "";
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
  if (conversation.queue?.some(item => item.input_message_id === messageId)) return true;
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
  onNavigate?: (tab: WorkbenchTab, recordId?: string) => void;
  onPresentationChange?: (settings: PresentationSettings) => void;
  presentation?: PresentationSettings;
  productName?: string;
  chatLaunch?: ChatLaunch | null;
  onChatLaunchHandled?: () => void;
  historyNotice?: HistoryNotice | null;
  conversationListRef?: RefObject<ConversationListActions | null>;
  onHistoryChanged?: () => void;
  onActiveConversationId?: (id: string | null) => void;
  restoringSelection?: boolean;
  restorationError?: string;
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
  const [dockWidth, setDockWidth] = usePanelWidth("workbench.chat.dock.width", 320, 280, 1100, "workbench.inspector.width");
  const [helperActivity, setHelperActivity] = useState({ conversationId: "", active: 0, total: 0 });
  const recordHelperActivity = useCallback((conversationId: string, active: number, total: number) => {
    setHelperActivity(current => current.conversationId === conversationId && current.active === active && current.total === total ? current : { conversationId, active, total });
  }, []);
  const historyMutations = useRef(new Map<string, boolean | "deleted">());
  const [deployments, setDeployments] = useState<Deployment[]>([]);
  const [bundles, setBundles] = useState<ModelBundle[]>([]);
  const [deploymentsLoaded, setDeploymentsLoaded] = useState(false);
  const [bundlesLoaded, setBundlesLoaded] = useState(false);
  const [profiles, setProfiles] = useState<RunProfile[]>([]);
  const [toolCatalogue, setToolCatalogue] = useState<ToolCatalogueProjection | null>(null);
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
  const [agentSetupId, setAgentSetupId] = useState<string | null>(null);
  const [modelOverrides, setModelOverrides] = useState<NonNullable<SetupConfiguration["model_overrides"]>>({});
  const [inheritedModelConfiguration, setInheritedModelConfiguration] = useState<SetupConfiguration | null>(null);
  const [inputPolicy, setInputPolicy] = useState<AgentInputPolicy | null>(null);
  const [localInstructions, setLocalInstructions] = useState<string | null>(null);
  const [showInputs, setShowInputs] = useState(false);
  const [contextEntryIds, setContextEntryIds] = useState<string[]>([]);
  const [contextKinds, setContextKinds] = useState<Record<string, "memory" | "instruction">>({});
  const [messageSkillIds, setMessageSkillIds] = useState<string[]>([]);
  const [shortcutIds, setShortcutIds] = useState<string[]>([]);
  const [projectFileRefs, setProjectFileRefs] = useState<string[]>([]);
  const [shortcuts, setShortcuts] = useState<Array<{ id: string; name: string; description: string }>>([]);
  const [projectContextFiles, setProjectContextFiles] = useState<Array<{ path: string; name: string }>>([]);
  const [picker, setPicker] = useState<{ kind: "context" | "skills"; query: string; highlighted: number; start?: number; end?: number } | null>(null);
  const [browserActive, setBrowserActive] = useState(false);
  const chatMainRef = useRef<HTMLDivElement>(null);
  const [chatWidth, setChatWidth] = useState(1000);
  useEffect(() => {
    const element = chatMainRef.current;
    if (!element || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(entries => setChatWidth(entries[0]?.contentRect.width ?? 1000));
    observer.observe(element);
    return () => observer.disconnect();
  }, []);
  const [setupResolving, setSetupResolving] = useState(false);
  const [setupDefaultsLoading, setSetupDefaultsLoading] = useState(true);
  const [hasApplicationDefaults, setHasApplicationDefaults] = useState(false);
  const [setupError, setSetupError] = useState("");
  const [shortcutError, setShortcutError] = useState("");
  const [permissionsError, setPermissionsError] = useState("");
  const [readinessSnapshot, setReadinessSnapshot] = useState<{ key: string; value: ChatReadiness } | null>(null);
  const [readinessEpoch, setReadinessEpoch] = useState(0);
  const [, setInstructionLayers] = useState<ResolvedSetupSelection["instruction_layers"]>([]);
  const applicationDefaults = useRef<ResolvedSetupSelection | null>(null);
  const setupEditedFields = useRef(new Set<string>());
  const setupRequest = useRef(0);
  const agentChoiceRequest = useRef(0);
  const [agentChoicePending, setAgentChoicePending] = useState<{ request: number; generation: number } | null>(null);
  const [modelChoiceGeneration, setModelChoiceGeneration] = useState<number | null>(null);
  const workspaceLaunchClaim = useRef<string | null>(null);
  const chatLaunchClaim = useRef<string | null>(null);
  const historyNoticeClaim = useRef<string | null>(null);
  const [task, setTask] = useState("");
  const [editing, setEditing] = useState<{ runId: string } | null>(null);
  const [editToken, setEditToken] = useState(0);
  const [recoveryRun, setRecoveryRun] = useState<AgentRun | null>(null);
  const [recoveringEffects, setRecoveringEffects] = useState(false);
  const [attachmentIds, setAttachmentIds] = useState<string[]>([]);
  const [documentAssetIds, setDocumentAssetIds] = useState<string[] | null>(null);
  const [copyingInputFiles, setCopyingInputFiles] = useState(false);
  const filePicker = useRef<HTMLInputElement>(null);
  const [workMode, setWorkMode] = useState<"work" | "plan">("work");
  const [desktopAccess, setDesktopAccess] = useState<DesktopAccess>("off");
  const [selectedTools, setSelectedTools] = useState<string[] | null>(null);
  const [toolMenuOpen, setToolMenuOpen] = useState(false);
  const [toolMenuRequest, setToolMenuRequest] = useState(0);
  const [hasSavedPermissions, setHasSavedPermissions] = useState(false);
  useEffect(() => {
    setHasSavedPermissions(false);
    if (!toolMenuOpen) return;
    let cancelled = false;
    setPermissionsError("");
    void packet03Api.grants().then(grants => {
      if (!cancelled) setHasSavedPermissions(grants.length > 0);
    }).catch((failure: unknown) => { if (!cancelled) setPermissionsError(errorMessage(failure)); });
    return () => { cancelled = true; };
  }, [toolMenuOpen]);

  const [helperAgentIds, setHelperAgentIds] = useState<string[]>([]);
  const [review, setReview] = useState({ enabled: false, criteria: "", max_revisions: 2 as const });
  const [incomingDrop, setIncomingDrop] = useState<{ id: string; sessionId: string; files: File[] } | null>(null);
  const [fileDragActive, setFileDragActive] = useState(false);
  const [approvalMode, setApprovalMode] = useState<ApprovalMode>("ask");
  const [perRequestOverrides, setPerRequestOverrides] = useState<Record<string, unknown>>({});

  const [conversation, setConversation] = useState<ChatConversation | null>(null);
  const [dockView, updateDockView] = useConversationDockView(conversation?.id ?? "");
  const railPage = dockView.page;
  const dockGeometry = chatDockGeometry(dockWidth, chatWidth);
  const dockVisible = dockView.open && dockGeometry.canOpen;
  const displayedDockMax = dockGeometry.max;
  const displayedDockWidth = dockGeometry.width;
  const railBody = useRef<HTMLDivElement>(null);
  const restoringRailScroll = useRef(false);
  useLayoutEffect(() => {
    if (!dockVisible || railPage === "browser") return;
    const element = railBody.current;
    if (!element) return;
    const target = railPage === "files" ? dockView.filesScroll : dockView.helpersScroll;
    restoringRailScroll.current = true;
    const restore = () => { if (restoringRailScroll.current) element.scrollTop = target; };
    restore();
    const observer = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(restore);
    if (element.firstElementChild) observer?.observe(element.firstElementChild);
    return () => { observer?.disconnect(); restoringRailScroll.current = false; };
  }, [conversation?.id, railPage, dockVisible]);
  const [runMetadata, setRunMetadata] = useState<{ conversationId: string; runs: Map<string, AgentRun> }>(() => ({ conversationId: "", runs: new Map() }));
  const runMetadataRef = useRef(runMetadata);
  runMetadataRef.current = runMetadata;
  const historicalRunIds = conversation?.run_ids.filter(id => id !== conversation.current_run_id && id !== conversation.current_run?.id).join("|") ?? "";
  const historicalRuns = runMetadata.conversationId === conversation?.id
    ? [...runMetadata.runs.values()].filter(run => historicalRunIds.split("|").includes(run.id)) : [];
  useEffect(() => {
    const conversationId = conversation?.id ?? "";
    const currentRun = conversation?.current_run;
    setRunMetadata(current => {
      const sameConversation = current.conversationId === conversationId;
      if (sameConversation && (!currentRun || current.runs.get(currentRun.id) === currentRun)) return current;
      const runs = new Map(sameConversation ? current.runs : []);
      if (currentRun) runs.set(currentRun.id, currentRun);
      return { conversationId, runs };
    });
  }, [conversation?.id, conversation?.current_run]);
  useEffect(() => {
    if (!conversation?.id || !historicalRunIds) return;
    const conversationId = conversation.id;
    const cached = runMetadataRef.current.conversationId === conversationId ? runMetadataRef.current.runs : new Map<string, AgentRun>();
    // A queued successor can be admitted before the predecessor's terminal
    // projection arrives. Retain its rows, then refresh that unfinished record.
    const missing = historicalRunIds.split("|").filter(id => !cached.has(id) || isAgentRunLive(cached.get(id)!.status));
    if (!missing.length) return;
    let cancelled = false;
    void Promise.allSettled(missing.map(id => api.agentRun(id))).then(results => {
      if (cancelled) return;
      setRunMetadata(current => {
        if (current.conversationId !== conversationId) return current;
        const runs = new Map(current.runs);
        for (const result of results) if (result.status === "fulfilled") runs.set(result.value.id, result.value);
        return { conversationId, runs };
      });
    });
    return () => { cancelled = true; };
  }, [conversation?.id, historicalRunIds]);
  const retainedAssets = useChatRetainedAssets(conversation?.id ?? "");
  const openRail = useCallback((page: RailPage) => {
    if (!dockGeometry.canOpen) {
      setMessage("Widen this window to open Files, Browser or Helpers beside the conversation.");
      return;
    }
    updateDockView({ open: true, page });
  }, [dockGeometry.canOpen, updateDockView]);
  const openHelper = useCallback((runId: string, toolCallId: string) => {
    updateDockView({ helper: helperKey(runId, toolCallId) });
    openRail("helpers");
  }, [openRail, updateDockView]);
  const openToolMenu = useCallback((section: "browser" | "windows") => {
    if (section === "browser") { openRail("browser"); return; }
    setToolMenuRequest(current => current + 1);
  }, [openRail]);
  const fileProjectId = conversation?.project_id ?? projectId;
  const selectedPath = dockView.projectId === fileProjectId ? dockView.path : "";
  const [message, setMessage] = useState("");
  const selectFile = useCallback((path: string) => {
    const accepted = acceptedProjectFilePath(path);
    if (!accepted) {
      const refusal = refusedProjectPathNotice(path);
      if (refusal) setMessage(refusal);
      return;
    }
    setMessage(current => isRefusedProjectPathNotice(current) ? "" : current);
    updateDockView({ projectId: fileProjectId, path: accepted });
  }, [fileProjectId, updateDockView]);
  const openFile = useCallback((path: string) => {
    const accepted = acceptedProjectFilePath(path);
    if (!accepted) {
      const refusal = refusedProjectPathNotice(path);
      if (refusal) setMessage(refusal);
      return;
    }
    openRail("files");
    selectFile(accepted);
  }, [openRail, selectFile]);
  const [conversations, setConversations] = useState<ChatConversation[]>([]);
  const historySignature = conversations.map(item => `${item.id}:${item.title ?? ""}:${item.display_title ?? ""}:${item.archived ? 1 : 0}`).join("|");
  const [knowledgeEntries, setKnowledgeEntries] = useState<KnowledgeEntry[]>([]);
  const [selectedKnowledgeIds, setSelectedKnowledgeIds] = useState<string[]>([]);
  const [loadErrors, setLoadErrors] = useState<Record<string, string>>({});
  const loadError = Object.entries(loadErrors).map(([label, error]) => `${label}: ${error}`).join(" · ");
  const catalogueActive = useRef(false);
  const catalogueReads = useRef(new Map<string, { cancel: () => void; promise: Promise<void> }>());
  const [sending, setSending] = useState(false);
  const [pendingSubmit, setPendingSubmit] = useState<PendingChatSubmit | null>(null);
  const [pendingStop, setPendingStop] = useState<PendingStopRequest | null>(null);
  const [interactionThreadId, setInteractionThreadId] = useState<string | null>(null);
  const [selectionLoading, setSelectionLoading] = useState<ChatConversation | null>(null);
  const [selectionFailure, setSelectionFailure] = useState<{ id: string; message: string } | null>(null);
  const [boundGeneration, setBoundGeneration] = useState(0);
  const selectionRequest = useRef(0);
  const modelBusyChanged = useCallback((busy: boolean) => setModelChoiceGeneration(busy ? selectionRequest.current : null), []);
  const draftRevision = useRef(0);
  const preEditDraft = useRef<{ task: string; attachmentIds: string[] } | null>(null);
  const acceptedEditRun = useRef<string | null>(null);
  const keptRetryEdit = useRef<{ sourceRunId: string; inputId: string } | null>(null);
  const rewindGuard = useRef({ hold: null as string | null, ownerKey: "", runId: "" });
  const composerRef = useRef<HTMLTextAreaElement>(null);
  const noteRewindResult = useCallback((pending: PendingChatSubmit, accepted: boolean) => {
    if (pending.rewind_mode === "edit" && !accepted && acceptedEditRun.current === pending.rewind_source_run_id) acceptedEditRun.current = null;
    if (pending.rewind_mode === "retry" && accepted && pending.rewind_source_run_id) {
      keptRetryEdit.current = { sourceRunId: pending.rewind_source_run_id, inputId: pending.id };
    }
  }, []);
  useLayoutEffect(() => {
    if (!editing) return;
    const box = composerRef.current;
    if (!box) return;
    box.focus();
    const end = box.value.length;
    box.setSelectionRange(end, end);
  }, [editToken, editing]);
  useEffect(() => {
    if (!editing || !conversation) return;
    const present = conversation.transcript.some(item => item.role === "user" && item.run_id === editing.runId);
    if (present) return;
    const kept = keptRetryEdit.current;
    if (kept?.sourceRunId === editing.runId) {
      // Retry replaces this run id and appends the same message. Keep the unsent edit on that new run.
      const replacement = conversation.transcript.find(item => item.role === "user" && item.id === kept.inputId && item.run_id);
      if (replacement?.run_id) setEditing({ runId: replacement.run_id });
      return;
    }
    keptRetryEdit.current = null;
    const accepted = acceptedEditRun.current === editing.runId;
    const draft = preEditDraft.current;
    preEditDraft.current = null;
    if (accepted) acceptedEditRun.current = null;
    setEditing(null);
    if (!accepted && draft) {
      draftRevision.current += 1;
      setTask(draft.task);
      setAttachmentIds(draft.attachmentIds);
    }
  }, [conversation, editing]);
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
    // Polling shares the initial read's owner and error. It cannot overtake an
    // in-flight read or erase a failure from another catalogue.
    void readCatalogue("Models", api.deployments, next => { setDeployments(next); setDeploymentsLoaded(true); }, false);
  }, []);
  useEffect(() => {
    if (props.activeTab && props.activeTab !== "chat") return;
    const timer = window.setInterval(refreshDeployments, 5000);
    return () => window.clearInterval(timer);
  }, [props.activeTab, refreshDeployments]);

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
    setDocumentAssetIds([...new Set([...(pending.document_asset_ids ?? []), ...(pending.attachment_ids ?? [])])]);
    setAttachmentIds([]);
    setMessageSkillIds([]);
    setShortcutIds([]);
  }, [isCurrentOwner]);

  function readCatalogue<T>(label: string, read: () => Promise<T>, apply: (value: T) => void, replace = true): Promise<void> {
    if (!catalogueActive.current) return Promise.resolve();
    const previous = catalogueReads.current.get(label);
    if (previous && !replace) return previous.promise;
    previous?.cancel();
    let cancelled = false;
    let retry: ReturnType<typeof setTimeout> | undefined;
    let delay = 1000;
    const owner = { cancel: () => { cancelled = true; clearTimeout(retry); }, promise: Promise.resolve() };
    catalogueReads.current.set(label, owner);
    const current = () => !cancelled && catalogueActive.current && catalogueReads.current.get(label) === owner;
    async function attempt(): Promise<void> {
      try {
        const value = await read();
        if (!current()) return;
        apply(value);
        catalogueReads.current.delete(label);
        setLoadErrors(errors => { const next = { ...errors }; delete next[label]; return next; });
      } catch (failure) {
        if (!current()) return;
        setLoadErrors(errors => ({ ...errors, [label]: errorMessage(failure) }));
        retry = setTimeout(() => void attempt(), delay);
        delay = Math.min(delay * 2, 8000);
      }
    }
    owner.promise = attempt();
    return owner.promise;
  }

  function refreshDefaults(): Promise<void> {
    if (applicationDefaults.current) return Promise.resolve();
    const generation = selectionRequest.current;
    const request = setupRequest.current;
    return readCatalogue("Defaults", () => workspaceApi.resolveSetup(null, null), resolved => {
      applicationDefaults.current = resolved;
      const configured = Object.values(resolved.configuration).some(value => value != null) || Boolean(resolved.instruction_layers?.length);
      setHasApplicationDefaults(configured);
      if (configured && !activeOwner.current.conversationId && generation === selectionRequest.current && request === setupRequest.current && setupEditedFields.current.size === 0) applyResolvedSetup(resolved);
      // A failed read does not establish defaults. In particular, do not turn
      // passive model fallback into an edit that blocks their later recovery.
      setSetupDefaultsLoading(false);
    }, false);
  }

  async function refresh(): Promise<void> {
    await Promise.all([
      readCatalogue("Models", api.deployments, next => { setDeployments(next); setDeploymentsLoaded(true); }),
      readCatalogue("Model files", api.bundles, next => { setBundles(next); setBundlesLoaded(true); }),
      readCatalogue("Saved setups", api.profiles, next => {
        setProfiles(next);
        setProfileId(current => { const id = next.some(profile => profile.id === current) ? current : ""; profileIdRef.current = id; return id; });
      }),
      readCatalogue("Tools", api.agentTools, setToolCatalogue),
      readCatalogue("Chats", () => api.chatConversations(false, true), next => setConversations(newestConversationFirst(reconcileHistory(next)))),
      readCatalogue("Knowledge", api.knowledgeEntries, setKnowledgeEntries),
      refreshDefaults(),
    ]);
  }

  useEffect(() => {
    if (props.activeTab && props.activeTab !== "chat") return;
    catalogueActive.current = true;
    void refresh();
    return () => {
      catalogueActive.current = false;
      for (const read of catalogueReads.current.values()) read.cancel();
      catalogueReads.current.clear();
    };
  }, [props.activeTab]);

  useEffect(() => {
    void readCatalogue("Projects", workspaceApi.projects, setProjects);
    void readCatalogue("Agents", workspaceApi.agentSetups, setAgentSetups);
  }, [props.projectRevision, props.activeTab]);

  function markSetupEdited(...keys: string[]) { keys.forEach(key => setupEditedFields.current.add(key)); }

  function selectedModelOverrides(): SetupConfiguration {
    if (!deploymentId && !profileId) return {};
    return { deployment_id: deploymentId || null, model_configuration_id: profileId || null };
  }

  function chatConfiguration(): Record<string, unknown> {
    return buildChatConfiguration({
      hasApplicationDefaults, projectId, agentSetupVersionId, agentSetupId,
      conversationAgentSetupVersionId: conversation?.agent_setup_version_id,
      conversationProjectId: conversation?.project_id,
      conversationWorkspaceId: conversation?.workspace_id,
      knowledgeEntries, selectedKnowledgeIds, editedFields: setupEditedFields.current,
      deploymentId, profileId, startupOverrides, embeddingDeploymentId, selectedTools,
      desktopAccess, approvalMode, perRequestOverrides, workMode, helperAgentIds, review,
      inputPolicy, localInstructions, modelOverrides, inheritedModelConfiguration,
      contextEntryIds, contextKinds, messageSkillIds, shortcutIds, projectFileRefs,
      documentAssetIds, projectPath,
    });
  }

  function chatExecutionConfiguration(): Record<string, unknown> {
    return executionConfiguration(chatConfiguration());
  }

  function chatCreationConfiguration(): Record<string, unknown> {
    return creationConfiguration(chatConfiguration());
  }

  function applyResolvedSetup(selection: ResolvedSetupSelection, memoryRefs: string[] | null = null) {
    const config = selection.configuration;
    if (config.deployment_id) setDeploymentId(config.deployment_id);
    else if (config.model_configuration_id) setDeploymentId("");
    else setDeploymentId("");
    profileIdRef.current = config.model_configuration_id ?? config.profile_id ?? "";
    setProfileId(profileIdRef.current);
    setStartupOverrides(config.startup_overrides ?? {});
    setSelectedTools(config.presented_tools ?? null);
    setEmbeddingDeploymentId(config.embedding_deployment_id ?? "");
    if (!setupEditedFields.current.has("approval_mode")) setApprovalMode(approvalModeOf(config.approval_mode));
    setPerRequestOverrides(config.per_request_overrides ?? {});
    setSelectedKnowledgeIds([...(memoryRefs ?? config.memory_version_refs ?? []), ...(config.skill_version_refs ?? []), ...(config.protected_instruction_version_refs ?? [])]);
    setInstructionLayers(selection.instruction_layers ?? []);
    applyExecutionPreferences(config as ExecutionPreferences);
  }

  function applyExecutionPreferences(config: ExecutionPreferences) {
    applyExecutionPreferencesAction(config, { setWorkMode, setDesktopAccess, setHelperAgentIds, setReview });
  }

  async function chooseSetup(nextProjectId: string | null, nextVersionId: string | null, overrides: SetupConfiguration = {}, preserveWorkspace = false, rejectOnFailure = false) {
    const request = ++setupRequest.current;
    const generation = selectionRequest.current;
    const modelOverrides = Object.hasOwn(overrides, "deployment_id") || Object.hasOwn(overrides, "model_configuration_id")
      ? {} : selectedModelOverrides();
    const nextAgentId = overrides.agent_setup_id !== undefined ? overrides.agent_setup_id : agentSetups.find(item => item.current_version_id === nextVersionId)?.id ?? (nextVersionId === agentSetupVersionId ? agentSetupId : null);
    const effectiveOverrides = { ...modelOverrides, ...overrides, agent_setup_id: nextAgentId };
    setSetupResolving(true); setSetupError("");
    try {
      const resolved = await workspaceApi.resolveSetup(nextProjectId, nextVersionId, effectiveOverrides);
      if (request !== setupRequest.current || generation !== selectionRequest.current) {
        if (rejectOnFailure) throw new Error("The selected Chat changed while applying model settings. Try again.");
        return;
      }
      setupEditedFields.current = new Set(Object.keys(effectiveOverrides));
      if (effectiveOverrides.approval_mode == null) setupEditedFields.current.delete("approval_mode");
      setProjectId(nextProjectId); setAgentSetupVersionId(nextVersionId);
      setAgentSetupId(nextAgentId ?? null);
      if (!preserveWorkspace) setProjectPath(projects.find(project => project.id === nextProjectId)?.canonical_path ?? "");
      applyResolvedSetup(resolved);
      setInputPolicy(effectiveOverrides.input_policy ?? null);
      if (overrides.model_overrides) setModelOverrides(overrides.model_overrides);
      if (overrides.inherited_model_configuration !== undefined) setInheritedModelConfiguration(overrides.inherited_model_configuration ?? null);
      if (overrides.agent_setup_id !== undefined) setAgentSetupId(overrides.agent_setup_id ?? null);
    } catch (error) {
      if (request === setupRequest.current && generation === selectionRequest.current) setSetupError(errorMessage(error));
      if (rejectOnFailure) throw error;
    } finally {
      if (request === setupRequest.current) setSetupResolving(false);
    }
  }

  useEffect(() => {
    if (!deploymentsLoaded || setupDefaultsLoading) return;
    const selected = deployments.find(item => item.id === deploymentId);
    props.onModelPhase?.(selected?.status === "running" ? "ready" : "none");
  }, [deploymentsLoaded, setupDefaultsLoading, deployments, deploymentId, props.onModelPhase]);

  useEffect(() => {
    if (!deploymentsLoaded || setupDefaultsLoading || conversation || selectionLoading || setupResolving || deploymentId || profileId) return;
    const healthy = deployments.filter(item => !isDeclaredEmbedder(item) && item.status === "running" && item.health?.healthy === true);
    if (healthy.length !== 1) return;
    const only = healthy[0];
    const configurationId = only.profile_id ?? "";
    markSetupEdited("deployment_id", "model_configuration_id");
    setDeploymentId(only.id);
    profileIdRef.current = configurationId;
    setProfileId(configurationId);
  }, [deploymentsLoaded, setupDefaultsLoading, conversation?.id, selectionLoading?.id, setupResolving, deploymentId, profileId, deployments]);

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
    documentAssetIds,
    approvalMode,
    workMode, desktopAccess, selectedTools, helperAgentIds, review,
    perRequestOverrides,
    selectedKnowledgeIds,
    knowledgeEntries,
    projectId, agentSetupVersionId, setupResolving, hasApplicationDefaults,
    agentSetupId, modelOverrides, inheritedModelConfiguration, contextEntryIds, contextKinds, messageSkillIds, shortcutIds, projectFileRefs, inputPolicy, localInstructions,
  ]);

  const transcript = conversation ? displayedTranscript(conversation) : [];

  useEffect(() => {
    if (conversation?.current_run && !isAgentRunLive(conversation.current_run.status)) retainedAssets.refresh();
  }, [conversation?.current_run?.id, conversation?.current_run?.status]);

  function fail(error: unknown): void {
    setMessage(error instanceof ApiError && error.code === "browser_control_active" ? "Return browser control in Browser. " + errorMessage(error) : errorMessage(error));
  }

  function startFresh(): void {
    const keepModelChoice = Boolean(deploymentId || profileId);
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
    setSelectionFailure(null);
    setPendingSubmit(null);
    setPendingStop(null);
    setSending(false);
    setEditing(null);
    preEditDraft.current = null;
    acceptedEditRun.current = null;
    keptRetryEdit.current = null;
    serverDraftRevision.current = 0;
    updateTask("");
    setAttachmentIds([]);
    setDocumentAssetIds(null);
    setInputPolicy(null); setLocalInstructions(null); setShowInputs(false);
    setModelOverrides({}); setContextEntryIds([]); setContextKinds({}); setMessageSkillIds([]); setShortcutIds([]); setProjectFileRefs([]); setPicker(null);
    setupEditedFields.current = keepModelChoice ? new Set(["deployment_id", "model_configuration_id"]) : new Set();
    setApprovalMode(approvalModeOf(applicationDefaults.current?.configuration.approval_mode));
    setPerRequestOverrides({});
    setSelectedTools(null);
    applyExecutionPreferences((agentSetups.find(agent => agent.current_version_id === agentSetupVersionId)?.configuration ?? {}) as ExecutionPreferences);
    setMessage("");
  }

  const selectionBusy = Boolean(props.restoringSelection) || Boolean(selectionLoading) || setupResolving || setupDefaultsLoading || copyingInputFiles
    || modelChoiceGeneration === selectionRequest.current || agentChoicePending?.generation === selectionRequest.current;
  const hasPendingCancelInput = Boolean(conversation?.pending_cancel_input_ids?.length);
  const currentRunLive = Boolean(conversation?.current_run && isAgentRunLive(conversation.current_run.status));
  const awaitingRunAdmission = Boolean(pendingSubmit && !currentRunLive);
  const measurementOwnerKey = JSON.stringify([conversation?.id, interactionThreadId, boundGeneration]);
  const publishedMeasurement = useLiveMeasurement();
  const measuredRun = publishedMeasurement && conversation?.current_run && publishedMeasurement.ownerKey === measurementOwnerKey && publishedMeasurement.runId === conversation.current_run.id ? publishedMeasurement : null;
  // The store can still say this run is generating after the conversation record has settled.
  const measuredTurnLive = Boolean(measuredRun && isAgentRunLive(measuredRun.status));
  const runBusy = currentRunLive || measuredTurnLive || Boolean(pendingSubmit) || hasPendingCancelInput || Boolean(conversation?.current_run?.finalization_phase);
  const rewindHold = currentRunLive || measuredTurnLive || Boolean(conversation?.current_run?.finalization_phase) || hasPendingCancelInput
    ? "Wait until this turn finishes"
    : selectionBusy || sending || awaitingRunAdmission
      ? "Wait until this chat is ready"
      : null;
  rewindGuard.current = { hold: rewindHold, ownerKey: measurementOwnerKey, runId: conversation?.current_run?.id ?? "" };
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
  const selectedAgent = agentSetups.find(setup => setup.id === agentSetupId || setup.current_version_id === agentSetupVersionId);
  const agentFixedModel = Boolean(selectedAgent?.configuration?.model_configuration_id || selectedAgent?.configuration?.bundle_id || selectedAgent?.configuration?.deployment_id);
  const hasModelChoice = Boolean(selectedProfile || deployments.some(item => item.id === deploymentId));
  const chatDeployments = deployments.filter((item) => !isDeclaredEmbedder(item));
  const modelChoices = chatDeployments.length > 0 ? chatDeployments : deployments;
  const selectedDeployment = modelChoices.find((item) => item.id === deploymentId);
  useEffect(() => {
    if (!conversation || selectionLoading || setupResolving || runBusy || sending || pendingSubmit || deploymentId === conversation.deployment_id) return;
    // A queued turn may rebind the conversation after its own exact snapshot
    // runs. Adopt that observed binding only when the composer still selects
    // the same model and startup; a staged different choice keeps its intent.
    if (boundDeploymentForModelIntent(conversation, profileId, startupOverrides) === conversation.deployment_id) {
      setDeploymentId(conversation.deployment_id);
    }
  }, [conversation?.id, conversation?.deployment_id, conversation?.model_configuration_id, conversation?.startup_overrides,
    selectionLoading, setupResolving, runBusy, sending, pendingSubmit, deploymentId, profileId, startupOverrides]);
  const selectedDocumentIds = documentAssetIds ?? conversation?.document_asset_ids ?? [];
  const inheritedTools = applicationDefaults.current?.configuration.presented_tools;
  const standardTools = standardToolSelection(toolCatalogue, Boolean(projectId || projectPath), Boolean(selectedKnowledgeIds.length), Boolean(attachmentIds.length || selectedDocumentIds.length));
  const tools = selectedTools ?? (Array.isArray(inheritedTools) ? inheritedTools : standardTools ?? []);
  const browserGroups = new Set((toolCatalogue?.tools ?? []).filter(tool => tool.group === "browser").map(tool => tool.id));
  const browserEnabled = workMode === "work" && tools.some(name => browserGroups.has(name) || browserToolNames.some(browserName => browserName === name));
  useBrowserRailActivity(conversation?.thread_id ?? null, browserEnabled && (!props.activeTab || props.activeTab === "chat"), setBrowserActive);
  const deployHealthNotice = chatDeployHealthNotice(conversation, selectedDeployment);
  const canObserveInteraction = Boolean(interactionThreadId && conversation);
  const currentArea = selectionLoading ? areaLabel(selectionLoading) : areaLabel(conversation);
  useEffect(() => {
    if (props.activeTab && props.activeTab !== "chat") return;
    let stale = false;
    void workspaceApi.shortcuts().then(items => { if (!stale) { setShortcuts(items); setShortcutError(""); } }).catch((failure: unknown) => { if (!stale) setShortcutError(errorMessage(failure)); });
    return () => { stale = true; };
  }, [props.activeTab]);
  useEffect(() => {
    if (picker?.kind !== "context" || !fileProjectId) return;
    let stale = false;
    void (async () => {
      const files: Array<{ path: string; name: string }> = [];
      const pendingPaths = [""];
      let directoriesRead = 0;
      while (pendingPaths.length && files.length < 1000 && directoriesRead++ < 250) {
        const path = pendingPaths.shift()!;
        const listing = await request<{ entries: Array<{ path: string; name: string; kind: string }> }>("/v1/projects/" + encodeURIComponent(fileProjectId) + "/files" + (path ? "?path=" + encodeURIComponent(path) : ""));
        if (stale) return;
        for (const item of listing.entries) {
          if (item.kind === "file") files.push(item);
          else if (item.path.split("/").length < 6) pendingPaths.push(item.path);
        }
      }
      if (!stale) setProjectContextFiles(files);
    })().catch(error => { if (!stale) setMessage(errorMessage(error)); });
    return () => { stale = true; };
  }, [picker?.kind, fileProjectId]);
  const contextChoices: ComposerChoice[] = [
    ...knowledgeEntries.filter(item => item.kind !== "skill").map(item => ({ id: item.id, name: item.display_name ?? item.id, kind: item.kind === "memory" ? "memory" as const : "instruction" as const, repairTo: "knowledge" as const, unavailable: item.enabled === false || item.active === false ? "Enable this in Knowledge" : item.scope_bound === false ? "Available in its own project" : undefined })),
    ...retainedAssets.records.filter(item => !item.deleted_at).map(item => ({ id: item.id, name: item.filename, kind: "asset" as const, description: "Chat file" })),
    ...projectContextFiles.map(item => ({ id: item.path, name: item.path, kind: "project" as const, description: "Project file", unavailable: tools.includes("read_file") ? undefined : "Enable file reading in Agents" })),
  ];
  const skillChoices: ComposerChoice[] = [
    ...knowledgeEntries.filter(item => item.kind === "skill").map(item => ({ id: item.id, name: item.display_name ?? item.id, kind: "skill" as const, repairTo: "knowledge" as const, unavailable: item.enabled === false || item.active === false ? "Enable this in Knowledge" : item.scope_bound === false ? "Available in its own project" : undefined })),
    ...shortcuts.map(item => ({ id: item.id, name: item.name, kind: "shortcut" as const, description: item.description })),
  ];
  const pickerChoices = picker ? composerMatches(picker.kind === "context" ? contextChoices : skillChoices, picker.query) : [];
  function closePicker() { setPicker(null); if (typeof document !== "undefined") document.querySelector<HTMLTextAreaElement>('.compose textarea')?.focus({ preventScroll: true }); }
  function selectComposerChoice(choice: ComposerChoice) {
    if (choice.unavailable) { navigateAway(choice.repairTo ?? "agents", choice.repairTo === "knowledge" ? choice.id : selectedAgent?.id); return; }
    draftRevision.current += 1;
    if (choice.kind === "asset") setDocumentAssetIds(current => [...new Set([...(current ?? selectedDocumentIds), choice.id])]);
    else if (choice.kind === "project") setProjectFileRefs(current => [...new Set([...current, choice.id])]);
    else if (choice.kind === "shortcut") setShortcutIds(current => [...new Set([...current, choice.id])]);
    else if (choice.kind === "skill") setMessageSkillIds(current => [...new Set([...current, choice.id])]);
    else { setContextEntryIds(current => [...new Set([...current, choice.id])]); setContextKinds(current => ({ ...current, [choice.id]: choice.kind === "instruction" ? "instruction" : "memory" })); }
    if (picker?.start !== undefined) updateTask(task.slice(0, picker.start) + task.slice(picker.end ?? task.length));
    closePicker();
  }
  function updateComposer(value: string, caret = value.length) {
    updateTask(value);
    const match = value.slice(0, caret).match(/(?:^|\s)([@/])([^\s@/]{0,80})$/);
    if (match) setPicker({ kind: match[1] === "@" ? "context" : "skills", query: match[2], highlighted: 0, start: (match.index ?? 0) + match[0].indexOf(match[1]), end: caret });
    else if (picker?.start !== undefined) setPicker(null);
  }

  function chooseConversation(item: ChatConversation): void {
    chooseConversationAction(item, { persistBeforeLeaving, selectConversation, fail });
  }

  function selectConversation(item: ChatConversation): void {
    selectConversationAction(item, {
      historyMutations, setShowInputs, selectionRequest, setupRequest, activeOwner, setBoundGeneration, setConversation,
      setInteractionThreadId, setSelectionLoading, setSelectionFailure, setMessage, setPendingSubmit, setPendingStop, setSending,
      cacheConversation, setModelOverrides, setInheritedModelConfiguration, setContextEntryIds, setContextKinds, setMessageSkillIds,
      setShortcutIds, setProjectFileRefs, setPicker, setAgentSetupId, agentSetups, setProjectId, setAgentSetupVersionId,
      boundDeploymentForModelIntent, setDeploymentId, profileIdRef, setProfileId, setTask, setAttachmentIds, setDocumentAssetIds,
      setSetupResolving, hasApplicationDefaults, setSetupError, setupEditedFields, setEmbeddingDeploymentId, setStartupOverrides,
      setApprovalMode, setPerRequestOverrides, setSelectedTools, setInputPolicy, setLocalInstructions, applyExecutionPreferences,
      setProjectPath, setSelectedKnowledgeIds, applyResolvedSetup, setInstructionLayers, serverDraftRevision, draftRevision,
      setConversations, props, startFresh,
    });
  }

  function applyConversationUpdate(next: ChatConversation): void {
    applyConversationUpdateAction(next, { historyMutations, cacheConversation, setConversation });
  }

  function reconcileHistory(items: ChatConversation[]): ChatConversation[] {
    return reconcileHistoryAction(items, { historyMutations });
  }

  function removeConversation(id: string): void {
    removeConversationAction(id, { historyMutations, setConversations, activeOwner, selectionLoading, conversation, startFresh });
  }

  function stopCurrentWork(): void {
    stopCurrentWorkAction({
      conversation, interactionThreadId, boundGeneration, pendingSubmissionActive, pendingSubmit, setPendingStop,
      isCurrentOwner, cacheConversation, setConversation, fail, updateConversationForRun,
    });
  }

  function recoverRun(run: AgentRun) {
    recoverRunAction(run, { setRecoveryRun, openRail, navigateAway, task, updateTask });
  }

  async function acknowledgeEffects() {
    if (!recoveryRun || !conversation || recoveringEffects) return;
    const id = conversation.id;
    setRecoveringEffects(true);
    try {
      const next = await packet03Request<ChatConversation>(`/v1/chat/conversations/${encodeURIComponent(id)}/runs/${encodeURIComponent(recoveryRun.id)}/acknowledge-effects`, {method: "POST"});
      cacheConversation(next);
      if (activeOwner.current.conversationId === id) { applyConversationUpdate(next); setRecoveryRun(null); }
    } catch (error) { setMessage(errorMessage(error)); }
    finally { setRecoveringEffects(false); }
  }

  async function useMemoryNextTurn(versionId: string) {
    const { conversationId, threadId, generation } = activeOwner.current;
    if (!conversationId || !threadId || conversationId !== conversation?.id) return;
    const owner = { conversationId, threadId, generation };
    const version = await api.knowledgeVersion(versionId);
    const entries = await api.knowledgeEntries();
    if (!isCurrentOwner(owner)) return;
    const selected = await Promise.all(selectedKnowledgeIds.map(id => api.knowledgeVersion(id)));
    if (!isCurrentOwner(owner)) return;
    setKnowledgeEntries(entries);
    setSelectedKnowledgeIds([...selected.filter(item => item.entry_id !== version.entry_id).map(item => item.id), versionId]);
    setContextEntryIds(current => [...new Set([...current, version.entry_id])]);
    setContextKinds(current => ({ ...current, [version.entry_id]: "memory" }));
    draftRevision.current += 1;
  }

  async function sendTurn(): Promise<void> {
    const text = task.trim();
    if (editing && (runBusy || queueIntent || selectionBusy || sending || awaitingRunAdmission || readinessBlocked || !hasModelChoice || (!text && !attachmentIds.length))) return;
    if ((!text && !attachmentIds.length) || !hasModelChoice || selectionBusy || sending || awaitingRunAdmission || (runBusy && !conversation) || (pendingSubmit && draftRevision.current === pendingSubmit.draft_revision)) {
      return;
    }
    if (conversation && !runBusy && readinessBlocksSend(readiness)) {
      setMessage(readiness?.issues[0]?.message ?? "This chat needs a setup change before sending.");
      if (readiness?.issues.some(issue => /window|desktop|grant/.test(issue.code))) openToolMenu("windows");
      return;
    }
    if (desktopAccess !== "off" && !conversation) {
      try {
        const created = await persistBeforeLeaving();
        if (created) {
          selectConversation(created);
          openToolMenu("windows");
          setMessage("Choose a live Windows grant for this chat, then send your message.");
        }
      } catch (error) { fail(error); }
      return;
    }
    const requestId = selectionRequest.current;
    const originConversationId = conversation?.id ?? null;
    const capturedDraftRevision = draftRevision.current;
    const queueAfterRunId = conversation && (
      (conversation.current_run && isAgentRunLive(conversation.current_run.status)) ||
      readiness?.issues.some(issue => issue.code === "chat_turn_active")
    ) ? conversation.current_run_id ?? conversation.current_run?.id ?? null : null;
    setSending(true);
    setMessage("");
    try {
      const savedDraft = await persistBeforeLeaving();
      const payload = {
        ...chatExecutionConfiguration(),
        task: text,
        draft_revision: savedDraft?.draft?.revision ?? conversation?.draft?.revision ?? null,
        attachment_ids: attachmentIds,
        document_asset_ids: selectedDocumentIds,
        ...(editing ? { rewind_source_run_id: editing.runId, rewind_mode: "edit" as const } : {}),
      };
      if (queueIntent && conversation && !editing) {
        const queued = await api.enqueueChatTurn(conversation.id, {
          ...payload, ...(queueAfterRunId ? { queue_after_run_id: queueAfterRunId } : {}),
        });
        draftWriter.current.observe(queued);
        if (selectionRequest.current !== requestId || activeOwner.current.conversationId !== conversation.id) {
          cacheConversation(queued);
          return;
        }
        cacheConversation(queued);
        setConversation(queued);
        setDocumentAssetIds(queued.document_asset_ids ?? []);
        if (draftRevision.current === capturedDraftRevision) {
          draftRevision.current += 1;
          setTask("");
          setAttachmentIds([]);
          setMessageSkillIds([]); setShortcutIds([]);
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
      if (editing) acceptedEditRun.current = editing.runId;
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

  function rewindBlocked(): boolean {
    if (rewindGuard.current.hold) return true;
    const published = readLiveMeasurement();
    const guard = rewindGuard.current;
    return Boolean(published && published.ownerKey === guard.ownerKey && published.runId && published.runId === guard.runId && isAgentRunLive(published.status));
  }

  function beginEdit(runId: string) {
    if (rewindBlocked() || !conversation) return;
    const message = conversation.transcript.find(item => item.role === "user" && item.run_id === runId);
    if (!message) return;
    if (!preEditDraft.current) preEditDraft.current = { task, attachmentIds: [...attachmentIds] };
    setEditing({ runId });
    setEditToken(token => token + 1);
    updateTask(message.content);
    setAttachmentIds([...(message.attachment_ids ?? [])]);
  }

  function cancelEdit() {
    const runId = editing?.runId;
    const draft = preEditDraft.current;
    preEditDraft.current = null;
    acceptedEditRun.current = null;
    keptRetryEdit.current = null;
    setEditing(null);
    if (draft) {
      updateTask(draft.task);
      setAttachmentIds(draft.attachmentIds);
    }
    if (runId) queueMicrotask(() => document.querySelector<HTMLButtonElement>(`[data-edit-run="${CSS.escape(runId)}"]`)?.focus());
  }

  function retryTurn(runId: string) {
    if (rewindBlocked() || !conversation || !interactionThreadId) return;
    const message = conversation.transcript.find(item => item.role === "user" && item.run_id === runId);
    if (!message) return;
    setPendingSubmit({
      id: crypto.randomUUID(),
      conversation_id: conversation.id,
      thread_id: interactionThreadId,
      selection_generation: boundGeneration,
      draft_revision: -1,
      submitted_draft_revision: null,
      ...chatExecutionConfiguration(),
      task: message.content,
      attachment_ids: message.attachment_ids ?? [],
      document_asset_ids: message.attachment_ids ?? [],
      rewind_source_run_id: runId,
      rewind_mode: "retry",
    });
  }

  function createDraftConversation(): Promise<ChatConversation> {
    return createDraftConversationAction({ selectionRequest, conversationCreation, chatCreationConfiguration });
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

  function navigateAway(tab: WorkbenchTab, recordId?: string): void {
    void persistBeforeLeaving().then(() => onNavigate?.(tab, recordId)).catch(fail);
  }

  function editInputs(configuration: SetupConfiguration): void {
    editInputsAction(configuration, { draftRevision, markSetupEdited, setInputPolicy, setLocalInstructions, setReadinessEpoch });
  }

  async function saveInputsToAgent(name?: string): Promise<void> {
    const generation = selectionRequest.current;
    const basePolicy: AgentInputPolicy = selectedAgent?.configuration.input_policy ?? {};
    const promoteExclusions = (ids: string[] | undefined) => ids?.map(id => !selectedAgent && id === "conversation_instructions" ? "agent_instructions" : id);
    const policy = { ...basePolicy, ...(inputPolicy ?? {}), reference_loading: { ...basePolicy.reference_loading, ...inputPolicy?.reference_loading }, version: 1 as const, instruction_override: null };
    if (policy.excluded_sources) policy.excluded_sources = promoteExclusions(policy.excluded_sources);
    const instructions = inputPolicy?.instruction_override ?? selectedAgent?.configuration.instructions ?? localInstructions ?? null;
    const base = selectedAgent?.configuration ?? {
      memory_entry_ids: contextEntryIds.filter(id => contextKinds[id] !== "instruction"),
      protected_instruction_entry_ids: contextEntryIds.filter(id => contextKinds[id] === "instruction"),
      skill_entry_ids: messageSkillIds,
      ...(selectedTools !== null ? { presented_tools: selectedTools } : {}),
    };
    const configuration = scopedSetupConfiguration({ ...base, instructions, input_policy: policy }, "agent");
    const saved = selectedAgent
      ? await workspaceApi.updateAgentSetup(selectedAgent.id, { name: selectedAgent.name, role: selectedAgent.role, configuration, base_version: selectedAgent.current_version_id })
      : await workspaceApi.createAgentSetup({ name: name?.trim() || "Chat agent", configuration });
    setAgentSetups(current => [...current.filter(agent => agent.id !== saved.id), saved]);
    if (generation !== selectionRequest.current) return;
    setAgentSetupId(saved.id); setAgentSetupVersionId(saved.current_version_id);
    markSetupEdited("agent_setup_id", "input_policy");
    setInputPolicy({ ...inputPolicy, ...(inputPolicy?.excluded_sources ? { excluded_sources: promoteExclusions(inputPolicy.excluded_sources) } : {}), version: 1, instruction_override: null });
    setReadinessEpoch(value => value + 1);
  }

  async function freshWithInputs(effectivePolicy: AgentInputPolicy): Promise<void> {
    const generation = selectionRequest.current;
    const intent = chatConfiguration();
    const configuration = setupOverrides(chatConfiguration());
    const context = [...contextEntryIds], kinds = { ...contextKinds }, skills = [...messageSkillIds], actions = [...shortcutIds], files = [...projectFileRefs];
    const path = projectPath;
    const included = (id: string) => !effectivePolicy.excluded_sources?.includes(`attachment:${id}`);
    const attachments = attachmentIds.filter(included), documents = selectedDocumentIds.filter(included);
    const selectedAssets = [...new Set([...attachments, ...documents])];
    setCopyingInputFiles(true);
    try {
      const source = await persistBeforeLeaving() ?? conversation;
      if (generation !== selectionRequest.current) return;
      if (selectedAssets.length) {
        if (!source) throw new Error("The selected files need a saved Chat owner before they can be reused.");
        const available = await packet03Api.assets({ sessionId: source.id });
        const originals = selectedAssets.map(id => {
          const asset = available.find(item => item.id === id && !item.deleted_at);
          if (!asset) throw new Error("A selected file is no longer available in this chat.");
          return asset;
        });
        if (generation !== selectionRequest.current) return;
        const target = await api.createChatConversation(chatCreationConfiguration());
        const copies = new Map<string, string>();
        for (const asset of originals) {
          if (generation !== selectionRequest.current) return;
          const copied = await copyRetainedAsset(asset, target.id, { sessionId: source.id, ...(source.project_path ? { projectPath: source.project_path } : {}) });
          copies.set(asset.id, copied.id);
        }
        const saved = await draftWriter.current.save(target, { content: "", attachment_ids: attachments.map(id => copies.get(id)!), intended_config: { ...intent, document_asset_ids: documents.map(id => copies.get(id)!) } });
        cacheConversation(saved);
        if (generation === selectionRequest.current) selectConversation(saved);
        return;
      }
      startFresh();
      setProjectPath(path);
      setContextEntryIds(context); setContextKinds(kinds); setMessageSkillIds(skills); setShortcutIds(actions); setProjectFileRefs(files);
      setLocalInstructions(localInstructions);
      await chooseSetup(projectId, agentSetupVersionId, configuration, true, true);
    } catch (failure) { fail(failure); }
    finally { setCopyingInputFiles(false); }
  }

  function configureCapability(setup: CapabilitySetupRequest): void {
    configureCapabilityAction(setup, { openRail, setToolMenuRequest, setShowInputs, navigateAway, selectedAgent, projectId });
  }

  function openPermissions(): void {
    try { sessionStorage.setItem("workbench.settings.category", "Permissions"); } catch { /* Navigation still works without storage. */ }
    navigateAway("settings");
  }

  const readinessKey = conversation && !selectionLoading && !setupResolving && !runBusy
    ? JSON.stringify([conversation.id, projectId, setupOverrides(chatConfiguration()), agentSetupVersionId,
      conversation.current_run_id, conversation.current_run?.status, selectedDeployment?.status,
      selectedDeployment?.health?.healthy, attachmentIds, selectedDocumentIds, shortcutIds, projectFileRefs, readinessEpoch]) : "";
  const readiness = readinessSnapshot?.key === readinessKey ? readinessSnapshot.value : null;
  const readinessBlocked = readinessBlocksSend(readiness);
  const queueIntent = currentRunLive || hasPendingCancelInput || Boolean(conversation?.queue?.length) || Boolean(conversation?.current_run?.finalization_phase) || Boolean(readiness?.issues.some(issue => issue.code === "chat_turn_active"));
  useEffect(() => {
    if (!conversation || !readinessKey) { setReadinessSnapshot(null); return; }
    let cancelled = false;
    void workspaceApi.chatReadiness(conversation.id, setupOverrides(chatConfiguration()), agentSetupVersionId, false, { attachment_ids: attachmentIds, document_asset_ids: selectedDocumentIds, shortcut_ids: shortcutIds, project_file_refs: projectFileRefs }).then(result => {
      if (!cancelled) setReadinessSnapshot({ key: readinessKey, value: result });
    }).catch(failure => {
      if (!cancelled) setReadinessSnapshot({ key: readinessKey, value: { status: "unverified", can_send: false,
        issues: [{ code: "readiness_unavailable", message: errorMessage(failure) }], selection: null } });
    });
    return () => { cancelled = true; };
  }, [readinessKey]);

  async function chooseMainAgent(nextVersionId: string | null): Promise<void> {
    if (selectionBusy || sending) return;
    const request = ++agentChoiceRequest.current;
    const generation = selectionRequest.current;
    setAgentChoicePending({ request, generation });
    const setupGeneration = setupRequest.current;
    const ownsChoice = () => request === agentChoiceRequest.current && generation === selectionRequest.current && setupGeneration === setupRequest.current;
    try {
      const agent = agentSetups.find(item => item.current_version_id === nextVersionId);
      const fixed = Boolean(agent?.configuration?.model_configuration_id || agent?.configuration?.bundle_id || agent?.configuration?.deployment_id);
      const currentModel: SetupConfiguration = { deployment_id: deploymentId || null, model_configuration_id: profileId || null, startup_overrides: startupOverrides, per_request_overrides: perRequestOverrides };
      const inherited = agentFixedModel ? inheritedModelConfiguration ?? currentModel : currentModel;
      const fixedProfile = profiles.find(item => item.id === agent?.configuration?.model_configuration_id);
      const fixedDeployment = deployments.find(item => item.id === agent?.configuration?.deployment_id);
      const fixedKey = fixedProfile?.bundle_id ?? agent?.configuration?.bundle_id ?? fixedDeployment?.bundle_id ?? fixedDeployment?.id;
      const rememberedFixed = fixedKey ? modelOverrides[fixedKey] : undefined;
      const binding = fixed ? { model_configuration_id: agent?.configuration?.model_configuration_id ?? null, deployment_id: agent?.configuration?.deployment_id ?? null, bundle_id: agent?.configuration?.bundle_id ?? null, ...(rememberedFixed ? { startup_overrides: rememberedFixed.startup_overrides, per_request_overrides: rememberedFixed.per_request_overrides } : {}) } : inherited;
      const candidate: SetupConfiguration = { ...binding, agent_setup_id: agent?.id ?? null, approval_mode: approvalMode, desktop_access: desktopAccess, work_mode: workMode, inherited_model_configuration: inherited, model_overrides: modelOverrides };
      if (conversation) {
        const readiness = await workspaceApi.chatReadiness(conversation.id, candidate, nextVersionId);
        if (!ownsChoice()) return;
        if (readiness.status === "incompatible") throw new Error(readiness.issues[0]?.message ?? "This agent cannot continue this chat.");
      }
      const resolved = await workspaceApi.resolveSetup(projectId, nextVersionId, candidate);
      if (!ownsChoice()) return;
      const profile = profiles.find(item => item.id === resolved.configuration.model_configuration_id);
      const resolvedDeployment = deployments.find(item => item.id === resolved.configuration.deployment_id);
      if (!runBusy && profile?.bundle_id && (resolvedDeployment?.status !== "running" || !resolvedDeployment.health?.healthy)) {
        const loaded = await api.applyChatStartupOverrides(profile.bundle_id, profile.id, resolved.configuration.startup_overrides ?? {});
        if (!ownsChoice()) return;
        if (loaded.status !== "running" || !loaded.health?.healthy) throw new Error(loaded.error ?? "Model did not become ready.");
        candidate.deployment_id = loaded.id; await refresh();
      }
      if (!ownsChoice()) return;
      await chooseSetup(projectId, nextVersionId, candidate, true, true);
    } catch (failure) { if (ownsChoice()) setMessage(errorMessage(failure)); }
    finally { setAgentChoicePending(current => current?.request === request ? null : current); }
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
      void persistBeforeLeaving().then(async () => {
        startFresh();
        setProjectId(null);
        setProjectPath("");
        await chooseSetup(null, agentSetupVersionId);
      }).catch(fail).finally(() => props.onChatLaunchHandled?.());
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

  return (
    <ChatDockContext.Provider value={{ openFile }}>
    <section className="chat-layout" style={{ "--inspector-width": `${displayedDockWidth}px` } as CSSProperties}>
      <div className="chat-main" ref={chatMainRef}
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
          <div className="chat-header-actions">{conversation ? <MenuPopover label="Chat actions" align="end" placement="below" trigger={<Icon name="more" size={16} />} panelClassName="chat-actions-menu"><ChatHistoryActions conversation={conversation} onDeleted={removeConversation} onError={setMessage} /></MenuPopover> : null}<MenuPopover label="Conversation view" align="end" placement="below" trigger={<Icon name="tune" size={16} />}><CompactSwitch label="Reasoning and tools" checked={presentation.detailed_streams} description="Show returned reasoning and tool details." onChange={checked => { void api.updatePresentationSettings({ detailed_streams: checked }).then(saved => props.onPresentationChange?.(saved)).catch(fail); }} /></MenuPopover>
          <button type="button" className={`icon-button chat-rail-toggle${dockVisible ? " is-on" : ""}`} aria-pressed={dockVisible} aria-label={dockVisible ? "Close conversation rail" : "Open conversation rail"} title={!dockGeometry.canOpen ? "Widen window to open Files, Browser or Helpers" : helperActivity.conversationId === conversation?.id && helperActivity.active ? `${helperActivity.active} active helpers` : browserActive ? "Browser active" : dockVisible ? "Close dock" : "Files, Browser, Helpers"} onClick={() => {
            if (!dockGeometry.canOpen) { setMessage("Widen this window to open Files, Browser or Helpers beside the conversation."); return; }
            updateDockView({ open: !dockView.open });
          }}><Icon name="panelRight" />{helperActivity.conversationId === conversation?.id && helperActivity.total ? <span className={`chat-rail-count${helperActivity.active ? " is-live" : ""}`} aria-label={`${helperActivity.active} active helpers`}>{helperActivity.active || helperActivity.total}</span> : browserActive ? <span className="chat-rail-count is-live" aria-label="Browser active">·</span> : retainedAssets.records.length ? <span className="chat-rail-count" aria-label="Files available">·</span> : null}</button></div>
        </header>
        <div className={`chat-workspace${dockVisible ? " files-open" : ""}${dockVisible && railPage === "browser" ? " browser-open" : ""}`}>
        <div className="chat-conversation">
        {loadError ? <Notice tone="error" action={<button type="button" onClick={() => { void refresh(); void readCatalogue("Projects", workspaceApi.projects, setProjects); void readCatalogue("Agents", workspaceApi.agentSetups, setAgentSetups); }}>Retry</button>}>{loadError}</Notice> : null}
        <div className="transcript">
          {props.restoringSelection ? <EmptyState title="Opening conversation" /> : !conversation && (!deploymentsLoaded || !bundlesLoaded || loadErrors.Models || loadErrors["Model files"]) ? (
            <EmptyState title={loadErrors.Models || loadErrors["Model files"] ? "Models unavailable" : "Checking models"} />
          ) : deploymentsLoaded && bundlesLoaded && bundles.length === 0 && deployments.length === 0 && !conversation ? (
            <EmptyState title="No models">
              <button type="button" onClick={() => navigateAway("models")}><Icon name="plus" size={16} /> Add a model</button>
            </EmptyState>
          ) : selectionLoading && !conversation ? (
            <EmptyState title="Loading conversation">{conversationTitle(selectionLoading)}</EmptyState>
          ) : !conversation && transcript.length === 0 ? (
            <EmptyState title={profileId || deploymentId ? "No messages" : "Choose a model to start"}>
              {(profileId || deploymentId) && !(projectId || projectPath) ? <button type="button" className="quiet-button" onClick={() => props.onCreateProject?.()}><Icon name="folder" size={16} /> Add a project</button> : null}
            </EmptyState>
          ) : canObserveInteraction && interactionThreadId && conversation ? (
            <ChatInteractionStream
              detailedStreams={presentation.detailed_streams}
              renderAnswerActions={(nativeMessage, incomplete, answerText) => {
                const saved = savedAnswer(conversation, nativeMessage.id, incomplete, answerText);
                if (!saved) return null;
                return <AnswerActions answerText={saved.text} />;
              }}
              renderMessageFooter={(nativeMessage) => {
                const item = conversation.transcript.find(entry => entry.id === nativeMessage.id);
                if (!item) return null;
                const records = retainedAssets.records.filter(asset => item.role === "assistant" ? asset.source_run_id === item.run_id : item.attachment_ids?.includes(asset.id));
                return <>{item.role === "user" && item.run_id ? <MessageTaskActions runId={item.run_id} held={rewindHold} onRetry={() => retryTurn(item.run_id!)} onEdit={() => beginEdit(item.run_id!)} /> : null}{records.length ? <ChatRetainedFiles compact records={records} conversationId={conversation.id} currentRunId={item.run_id} currentRunStatus={conversation.current_run?.status} onReuse={ids => {
                  draftRevision.current += 1;
                  setAttachmentIds(current => [...new Set([...current, ...ids])]);
                }} /> : null}</>;
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
              onHelperOpen={openHelper}
              onHelperActivity={recordHelperActivity}
              historicalRuns={historicalRuns}
              onRecoverRun={recoverRun}
              onConfigureSetup={configureCapability}
              noteRewindResult={noteRewindResult}
            />
          ) : (
            transcript.map((item, index) => (
              <article key={`${item.at}-${item.role}-${index}`} className={`bubble bubble-${item.role}`} data-markdown-source={item.role === "assistant" ? item.content : undefined}>
                <header>
                  <strong>{messageRoleLabel(item.role)}</strong>
                  <time>{formatWhen(item.at)}</time>
                </header>
                {item.role === "user" ? <p className="user-message-text">{transcriptMessageContent(item)}</p> : <p>{transcriptMessageContent(item)}</p>}
                {conversation && item.role === "user" && item.run_id ? <MessageTaskActions runId={item.run_id} held={rewindHold} onRetry={() => retryTurn(item.run_id!)} onEdit={() => beginEdit(item.run_id!)} /> : null}
                {conversation && item.role === "assistant" ? (() => {
                  const saved = savedAnswer(conversation, item.id ?? undefined, false, item.content);
                  return saved ? <AnswerActions answerText={saved.text} /> : null;
                })() : null}
              </article>
            ))
          )}
        </div>

        {recoveryRun && conversation?.run_ids.includes(recoveryRun.id) ? <section className="run-failure" aria-label="Uncertain effects">
          <strong>Uncertain effects</strong>
          <HoverHelp title="Uncertain effects">Available file evidence has been checked. Review these actions before continuing. Previous actions will not be replayed.</HoverHelp>
          <ul>{Object.values(recoveryRun.tool_outcomes ?? {}).filter(item => item.outcome === "uncertain" && !item.evidence?.acknowledged_at).map(item => <li key={item.call_id}><strong>{item.name}</strong>{item.evidence?.path ? ` · ${String(item.evidence?.path)}` : ""}<p>{item.detail}</p></li>)}</ul>
          <button type="button" disabled={recoveringEffects} onClick={() => void acknowledgeEffects()}>Continue with current state</button>
          <button type="button" disabled={recoveringEffects} onClick={() => setRecoveryRun(null)}>Keep paused</button>
        </section> : null}
        {deployHealthNotice && !runBusy ? (
          <Notice tone={deployHealthNotice.tone}>
            {deployHealthNotice.message}
          </Notice>
        ) : null}
        {shortcutError ? <Notice tone="error">{shortcutError}</Notice> : null}
        {props.restorationError ? <Notice tone="error">{props.restorationError}</Notice> : null}
        {conversation && !readinessBlocked && !runBusy && readiness?.status === "unverified" && readiness.issues[0]?.message ? <Notice tone="warn">{readiness.issues[0].message}</Notice> : null}
        {conversation && readinessBlocked && !runBusy ? <Notice tone={readiness?.status === "incompatible" ? "error" : "warn"} action={<button type="button" onClick={() => {
          const code = readiness?.issues[0]?.code ?? "";
          if (["deferred_reference_tools_off", "deferred_reference_reader_excluded", "skill_selection_required"].includes(code)) setShowInputs(true);
          else if (code === "browser_control_active") openRail("browser");
          else if (code === "browser_worker_missing") { try { sessionStorage.setItem("workbench.settings.category", "Connections"); } catch {} navigateAway("settings"); }
          else if (/browser/.test(code)) openToolMenu("browser");
          else if (/window|desktop|grant/.test(code)) openToolMenu("windows");
          else navigateAway("agents");
        }}>{readiness?.issues[0]?.code === "skill_selection_required" ? "Review skill requirements" : ["deferred_reference_tools_off", "deferred_reference_reader_excluded"].includes(readiness?.issues[0]?.code ?? "") ? "Review reference loading" : readiness?.issues[0]?.code === "browser_control_active" ? "Return to agent in Browser" : readiness?.issues[0]?.code === "browser_worker_missing" ? "Install browser worker" : readiness?.issues[0]?.code === "browser_session_lost" ? "Reset browser" : /window|desktop|grant/.test(readiness?.issues[0]?.code ?? "") ? "Review Windows access" : "Review setup"}</button>}>{readiness?.issues[0]?.message ?? "This chat needs a setup change before sending."}</Notice> : null}
        {message && message !== conversation?.deploy_health?.message ? (
          <Notice tone="error" action={/^Return (browser control|to agent in the Browser)/.test(message) ? <button type="button" onClick={() => openRail("browser")}>Return to agent in Browser</button> : undefined}>{message}</Notice>
        ) : null}
        {selectionFailure && selectionLoading?.id === selectionFailure.id ? (
          <Notice tone="error" action={<button type="button" onClick={() => selectConversation(selectionLoading)}>Retry opening chat</button>}>
            {selectionFailure.message}
          </Notice>
        ) : null}
        {setupError ? <Notice tone="error">{setupError}</Notice> : null}

        </div>
        <aside className="chat-files-panel chat-rail" aria-label="Conversation rail" hidden={!dockVisible}>
          <PanelResize label="Resize conversation rail" width={displayedDockWidth} onResize={width => setDockWidth(Math.max(280, Math.min(displayedDockMax, width)))} min={280} max={displayedDockMax} reset={320} reverse />
          <div className="chat-rail-tabs" role="tablist" aria-label="Conversation rail pages">
            {(["files", "browser", "helpers"] as const).map(page => (
              <button key={page} type="button" role="tab" aria-selected={railPage === page} onClick={() => openRail(page)}>{page === "helpers" ? "Helpers" : page === "browser" ? "Browser" : "Files"}</button>
            ))}
            <button type="button" className="icon-button chat-rail-close" aria-label="Close conversation rail" title="Close" onClick={() => updateDockView({ open: false })}><Icon name="close" size={14} /></button>
          </div>
          <div className="chat-rail-body" ref={railBody} onWheel={() => { restoringRailScroll.current = false; }} onPointerDown={() => { restoringRailScroll.current = false; }} onKeyDown={() => { restoringRailScroll.current = false; }} onScroll={event => { if (dockVisible && railPage !== "browser" && !restoringRailScroll.current) updateDockView(railPage === "files" ? { filesScroll: event.currentTarget.scrollTop } : { helpersScroll: event.currentTarget.scrollTop }); }}>
            {railPage === "browser" ? <BrowserRail key={conversation?.thread_id ?? "new"} threadId={conversation?.thread_id ?? null} visible={dockVisible && (!props.activeTab || props.activeTab === "chat")} enabled={browserEnabled} projectBound={Boolean(fileProjectId || conversation?.project_path)} attachments={retainedAssets.records.filter(asset => !asset.deleted_at && (attachmentIds.includes(asset.id) || selectedDocumentIds.includes(asset.id)))} onConfigure={() => navigateAway("agents", selectedAgent?.id)} onSettings={() => { try { sessionStorage.setItem("workbench.settings.category", "Connections"); } catch {} navigateAway("settings"); }} onOpenFiles={() => openRail("files")} onDownloadsChanged={() => retainedAssets.refresh()} onReadinessChange={() => setReadinessEpoch(current => current + 1)} /> : null}
            {railPage === "helpers" ? <HelperRail key={conversation?.id ?? "new"} runs={[...historicalRuns, ...(conversation?.current_run ? [conversation.current_run] : [])]} currentRunId={conversation?.current_run?.id} threadId={interactionThreadId} conversationId={conversation?.id ?? ""} selectedHelperKey={dockView.helper} onSelectHelper={helper => updateDockView({ helper })} detailedStreams={presentation.detailed_streams} /> : null}
            {railPage === "files" ? <ChatDock
              page={railPage}
              view={dockView}
              onViewChange={updateDockView}
              threadId={conversation?.thread_id ?? null}
              previewEnabled={workMode === "work" && Boolean(selectedTools?.includes("start_preview"))}
              fileRevision={String(conversation?.current_run?.events.filter(event => event.kind === "tool_result").length ?? 0)}
              onUseMemoryVersion={useMemoryNextTurn}
              showPages={false}
              onPage={page => openRail(page)}
              projectId={fileProjectId}
              runIds={conversation?.run_ids ?? []}
              currentRunId={conversation?.current_run_id}
              currentRunStatus={conversation?.current_run?.status}
              selectedPath={selectedPath}
              onSelectPath={selectFile}
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
          {editing ? <div className="composer-queue-pause" role="status"><p>Editing an earlier message</p><button type="button" className="composer-edit-cancel" onClick={cancelEdit}>Cancel</button></div> : null}
          {conversation ? <ChatQueuePanel
            key={conversation.id}
            conversation={conversation}
            deployments={modelChoices}
            profiles={profiles}
            getCurrentSetup={chatExecutionConfiguration}
            disabled={selectionBusy || sending}
            onUpdated={applyConversationUpdate}
            onOpenOwner={threadId => { const selected = conversations.find(item => item.thread_id === threadId); if (selected) selectConversation(selected); else void api.chatConversations().then(items => { const found = items.find(item => item.thread_id === threadId); if (found) selectConversation(found); }).catch(error => setMessage(errorMessage(error))); }}
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
          {contextEntryIds.length || messageSkillIds.length || shortcutIds.length || projectFileRefs.length || selectedDocumentIds.length ? <div className="composer-chips" aria-label="Selected context">
            {[...contextEntryIds, ...messageSkillIds].map(id => <button type="button" className="composer-chip" key={id} disabled={selectionBusy || sending} aria-label={"Remove " + (knowledgeEntries.find(item => item.id === id)?.display_name ?? "context")} onClick={() => { draftRevision.current += 1; setContextEntryIds(items => items.filter(item => item !== id)); setMessageSkillIds(items => items.filter(item => item !== id)); }}>{knowledgeEntries.find(item => item.id === id)?.display_name ?? "Context"}<Icon name="close" size={12} /></button>)}
            {shortcutIds.map(id => <button type="button" className="composer-chip" key={id} disabled={selectionBusy || sending} aria-label={"Remove " + (shortcuts.find(item => item.id === id)?.name ?? id)} onClick={() => { draftRevision.current += 1; setShortcutIds(items => items.filter(item => item !== id)); }}>{shortcuts.find(item => item.id === id)?.name ?? id}<Icon name="close" size={12} /></button>)}
            {projectFileRefs.map(path => <button type="button" className="composer-chip" key={path} disabled={selectionBusy || sending} title={path} aria-label={"Remove " + path} onClick={() => { draftRevision.current += 1; setProjectFileRefs(items => items.filter(item => item !== path)); }}>{path.split("/").pop()}<Icon name="close" size={12} /></button>)}
            {selectedDocumentIds.map(id => <button type="button" className="composer-chip" key={id} disabled={selectionBusy || sending} aria-label={"Remove " + (retainedAssets.records.find(item => item.id === id)?.filename ?? "file")} onClick={() => { draftRevision.current += 1; setDocumentAssetIds(selectedDocumentIds.filter(item => item !== id)); }}>{retainedAssets.records.find(item => item.id === id)?.filename ?? "File"}<Icon name="close" size={12} /></button>)}
          </div> : null}
          {picker ? <ComposerPicker kind={picker.kind} query={picker.query} choices={pickerChoices} highlighted={Math.min(picker.highlighted, Math.max(0, pickerChoices.length - 1))} autocomplete={picker.start !== undefined} onQuery={query => setPicker({ ...picker, query, highlighted: 0 })} onHighlight={highlighted => setPicker({ ...picker, highlighted })} onSelect={selectComposerChoice} onClose={closePicker} onRepair={choice => navigateAway(choice.repairTo ?? "agents", choice.repairTo === "knowledge" ? choice.id : selectedAgent?.id)} /> : null}
          <label>
            <span className="sr-only">Message</span>
            <textarea
              ref={composerRef}
              value={task}
              onChange={(event) => updateComposer(event.target.value, event.target.selectionStart ?? event.target.value.length)}
              onKeyDown={(event) => {
                if (!event.nativeEvent.isComposing && picker && !event.shiftKey) {
                  if (event.key === "ArrowDown" || event.key === "ArrowUp") { event.preventDefault(); setPicker({ ...picker, highlighted: Math.max(0, Math.min(pickerChoices.length - 1, picker.highlighted + (event.key === "ArrowDown" ? 1 : -1))) }); return; }
                  if (event.key === "Escape") { event.preventDefault(); closePicker(); return; }
                  if (event.key === "Enter" && pickerChoices[picker.highlighted]) { event.preventDefault(); selectComposerChoice(pickerChoices[picker.highlighted]); return; }
                }
                if (event.key === "Escape" && editing) { event.preventDefault(); cancelEdit(); return; }
                if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
                  event.preventDefault();
                  event.currentTarget.form?.requestSubmit();
                }
              }}
              placeholder="Message your local model…"
              aria-autocomplete="list"
              aria-controls={picker ? "composer-suggestions" : undefined}
              aria-activedescendant={picker && pickerChoices.length ? "composer-option-" + picker.highlighted : undefined}
              title={queueIntent ? "Enter queues · Shift+Enter inserts a newline" : "Enter sends · Shift+Enter inserts a newline"}
              disabled={selectionBusy || sending}
            />
          </label>
          <div className="actions">
            <MenuPopover label="Add to message" trigger={<Icon name="plus" />} panelClassName="chat-tools-popover-panel" disabled={sending || selectionBusy}>{close => <>
              <button type="button" className="menu-action" disabled={!hasModelChoice} onClick={() => { close(); filePicker.current?.click(); }}><Icon name="files" />Attachments</button>
              <button type="button" className="menu-action" onClick={() => { close(); setPicker({ kind: "context", query: "", highlighted: 0 }); }}><Icon name="knowledge" />Add context</button>
              <button type="button" className="menu-action" onClick={() => { close(); setPicker({ kind: "skills", query: "", highlighted: 0 }); }}><Icon name="sparkles" />Skills & actions</button>
              <button type="button" className="menu-action" onClick={() => { markSetupEdited("work_mode"); setWorkMode("plan"); close(); }} disabled={workMode === "plan"}><Icon name="knowledge" />Plan</button>
            </>}</MenuPopover>
            <MenuPopover label="Approval mode" panelClassName="chat-access-panel" trigger={<><Icon name="shield" /><span>{approvalModeLabel(approvalMode)}</span></>} disabled={selectionBusy || sending} openRequest={toolMenuRequest} onOpenChange={setToolMenuOpen}>
                <div className="chat-access-heading"><span>Access</span><HoverHelp title="When access changes">Changes apply to your next message. Running and queued messages keep their access. Plan stays read-only; disabled tools stay off.</HoverHelp></div>
                <ApprovalModeControl value={approvalMode} disabled={selectionBusy || sending} onChange={mode => { markSetupEdited("approval_mode"); setApprovalMode(mode); }} />
                {permissionsError ? <p className="hint">{permissionsError}</p> : null}
                {hasSavedPermissions ? <button type="button" className="chat-tools-permissions" onClick={openPermissions}><Icon name="settings" size={14} /> Saved permissions</button> : null}
                {toolMenuOpen ? <VisualTestingControls windowsOnly conversationId={conversation?.id ?? null} threadId={conversation?.thread_id ?? null} browserEnabled={browserEnabled} onBrowserEnabled={() => {}} desktopAccess={desktopAccess} workMode={workMode} focusSection="windows" focusNonce={toolMenuRequest} disabled={selectionBusy || sending} canPrepareConversation={hasModelChoice} onSettings={() => { try { sessionStorage.setItem("workbench.settings.category", "Connections"); } catch {} navigateAway("settings"); }} onReadinessChange={() => setReadinessEpoch(value => value + 1)} onPrepareConversation={async () => { const created = await persistBeforeLeaving() ?? await createDraftConversation(); cacheConversation(created); selectConversation(created); }} onDesktopAccess={scope => { setDesktopAccess(scope); markSetupEdited("desktop_access"); setReadinessEpoch(value => value + 1); }} /> : null}
            </MenuPopover>
            {workMode === "plan" ? <button type="button" className="chat-plan-pill" aria-label="Turn off Plan mode" title="Turn off Plan mode" onClick={() => { markSetupEdited("work_mode"); setWorkMode("work"); }} disabled={selectionBusy || sending}><Icon name="close" size={12} /> Plan</button> : null}
            <ChatModelControls bundles={bundles} deployments={modelChoices} profiles={profiles} selectedDeploymentId={deploymentId} selectedConfigurationId={profileId || undefined} configuration={{ ...setupOverrides(chatConfiguration()), agent_setup_id: agentSetupId, model_overrides: modelOverrides, inherited_model_configuration: inheritedModelConfiguration }} projectId={projectId} agentSetupVersionId={agentSetupVersionId} conversationId={conversation?.id} selectionGeneration={selectionRequest.current} onBusyChange={modelBusyChanged} runtimeBusy={runBusy || Boolean(conversation?.queue?.length)} fixedModel={agentFixedModel} onManageAgent={() => navigateAway("agents", selectedAgent?.id)} disabled={selectionBusy || sending} onReloaded={refresh} onApply={async configuration => {
              await chooseSetup(projectId, agentSetupVersionId, configuration, true, true);
            }} />
            <MenuPopover label="Main agent" trigger={<><Icon name="agents" size={16} /><span className="chat-agent-label">{selectedAgent?.name ?? (agentSetupVersionId ? "Saved agent" : "Default agent")}</span></>} disabled={selectionBusy || sending}>{close => <div className="chat-agent-options" role="group" aria-label="Main agent">
              <button type="button" className="menu-action" aria-pressed={!agentSetupVersionId} onClick={() => { void chooseMainAgent(null); close(); }}>Default agent</button>
              {agentSetups.map(agent => <div key={agent.id} className="chat-agent-option"><button type="button" className="menu-action" aria-pressed={agent.current_version_id === agentSetupVersionId} disabled={Boolean(agent.missing_dependencies?.length)} title={agent.missing_dependencies?.map(issue => issue.reason).join(", ")} onClick={() => { void chooseMainAgent(agent.current_version_id); close(); }}>{agent.name}</button>{agent.missing_dependencies?.length ? <><small className="hint">{agent.missing_dependencies.map(issue => issue.reason).join(" · ")}</small><button type="button" className="text-button" onClick={() => { close(); navigateAway("agents", agent.id); }}>Review in Agents</button></> : null}</div>)}
            </div>}</MenuPopover>
            <span className="composer-spacer" />
            <ChatMeasurements run={conversation?.current_run} ownerKey={JSON.stringify([conversation?.id, interactionThreadId, boundGeneration])} starting={pendingSubmissionActive || (sending && !currentRunLive)} stopping={pendingStopActive} onInspect={() => setShowInputs(true)} />
            <button
              type={runBusy ? "button" : "submit"}
              aria-label={runBusy ? savingProjectState ? "Finishing" : pendingStopActive ? "Stopping…" : "Stop" : props.restoringSelection || selectionLoading ? "Opening conversation…" : selectionBusy ? "Loading settings…" : sending ? "Sending…" : "Send"}
              className={runBusy ? "send-button stop-button combined-action" : "send-button combined-action"}
              title={runBusy ? savingProjectState ? "Saving project state" : pendingStopActive ? "Stopping" : "Stop this turn" : "Send message"}
              disabled={runBusy ? pendingStopActive || savingProjectState || !conversation : !hasModelChoice || (!task.trim() && !attachmentIds.length) || selectionBusy || sending || awaitingRunAdmission || readinessBlocked || Boolean(pendingSubmit && draftRevision.current === pendingSubmit.draft_revision)}
              onClick={runBusy ? stopCurrentWork : undefined}
            ><Icon name={runBusy ? "stop" : "send"} size={16} /></button>
          </div>
        </form>
        </div>
      </div>
    </section>
    {showInputs ? <AgentInputs configuration={{ ...setupOverrides(chatConfiguration()), input_policy: inputPolicy, ...(localInstructions !== null ? { instructions: localInstructions } : {}) }} conversationId={conversation?.id} projectId={projectId} agentSetupVersionId={agentSetupVersionId} context={{ attachment_ids: attachmentIds, document_asset_ids: selectedDocumentIds, shortcut_ids: shortcutIds, project_file_refs: projectFileRefs }} preview={readiness?.input_preview} hasHistory={transcript.length > 0} disabled={selectionBusy || sending} effectiveTools={selectedTools} preparingFresh={copyingInputFiles} onChange={editInputs} onClose={() => setShowInputs(false)} agentName={selectedAgent?.name} onSaveToAgent={saveInputsToAgent} onFreshChat={policy => void freshWithInputs(policy)} onEditSource={(owner, recordId) => { setShowInputs(false); navigateAway(owner, recordId ?? (owner === "models" ? profileId || selectedDeployment?.bundle_id || undefined : owner === "agents" ? selectedAgent?.id : undefined)); }} /> : null}
    </ChatDockContext.Provider>
  );
}
