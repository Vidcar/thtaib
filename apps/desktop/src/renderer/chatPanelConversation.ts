import type { Dispatch, RefObject, SetStateAction } from "react";
import { api, ApiError } from "./api";
import { approvalModeOf, type ApprovalMode } from "./ApprovalModeControl";
import type { AgentInputPolicy } from "./agentInputPolicy";
import { notifyAttentionChanged } from "./AttentionPanel";
import type { ExecutionPreferences } from "./chatPanelExecution";
import { setupOverrides } from "./chatSetup";
import { errorMessage } from "./errors";
import type { ChatConversation } from "./types";
import type { ConversationListActions } from "./WorkbenchSidebar";
import { workspaceApi, type AgentSetup, type ResolvedSetupSelection, type SetupConfiguration } from "./workspaceApi";

type HistoryMutations = { current: Map<string, boolean | "deleted"> };
type ActiveOwner = { current: { conversationId: string | null; threadId: string | null; generation: number } };

export function chooseConversation(item: ChatConversation, deps: {
  persistBeforeLeaving: () => Promise<ChatConversation | null>;
  selectConversation: (item: ChatConversation) => void;
  fail: (error: unknown) => void;
}): void {
  const { persistBeforeLeaving, selectConversation, fail } = deps;
  void persistBeforeLeaving().then(() => selectConversation(item)).catch(fail);
}

export function selectConversation(item: ChatConversation, deps: {
  historyMutations: HistoryMutations;
  setShowInputs: (value: boolean) => void;
  selectionRequest: { current: number };
  setupRequest: { current: number };
  activeOwner: ActiveOwner;
  setBoundGeneration: (value: number) => void;
  setConversation: (value: ChatConversation | null) => void;
  setInteractionThreadId: (value: string | null) => void;
  setSelectionLoading: (value: ChatConversation | null) => void;
  setSelectionFailure: (value: { id: string; message: string } | null) => void;
  setMessage: (value: string) => void;
  setPendingSubmit: (value: null) => void;
  setPendingStop: (value: null) => void;
  setSending: (value: boolean) => void;
  cacheConversation: (next: ChatConversation) => void;
  setModelOverrides: (value: NonNullable<SetupConfiguration["model_overrides"]>) => void;
  setInheritedModelConfiguration: (value: SetupConfiguration | null) => void;
  setContextEntryIds: (value: string[]) => void;
  setContextKinds: (value: Record<string, "memory" | "instruction">) => void;
  setMessageSkillIds: (value: string[]) => void;
  setShortcutIds: (value: string[]) => void;
  setProjectFileRefs: (value: string[]) => void;
  setPicker: (value: null) => void;
  setAgentSetupId: (value: string | null) => void;
  agentSetups: AgentSetup[];
  setProjectId: (value: string | null) => void;
  setAgentSetupVersionId: (value: string | null) => void;
  boundDeploymentForModelIntent: (conversation: ChatConversation, configurationId: string, startup: unknown) => string;
  setDeploymentId: (value: string) => void;
  profileIdRef: { current: string };
  setProfileId: (value: string) => void;
  setTask: (value: string) => void;
  setAttachmentIds: (value: string[]) => void;
  setDocumentAssetIds: (value: string[] | null) => void;
  setSetupResolving: (value: boolean) => void;
  hasApplicationDefaults: boolean;
  setSetupError: (value: string) => void;
  setupEditedFields: { current: Set<string> };
  setEmbeddingDeploymentId: (value: string) => void;
  setStartupOverrides: (value: Record<string, unknown>) => void;
  setApprovalMode: (value: ApprovalMode) => void;
  setPerRequestOverrides: (value: Record<string, unknown>) => void;
  setSelectedTools: (value: string[] | null) => void;
  setInputPolicy: (value: AgentInputPolicy | null) => void;
  setLocalInstructions: (value: string | null) => void;
  applyExecutionPreferences: (config: ExecutionPreferences) => void;
  setProjectPath: (value: string) => void;
  setSelectedKnowledgeIds: (value: string[]) => void;
  applyResolvedSetup: (selection: ResolvedSetupSelection, memoryRefs?: string[] | null) => void;
  setInstructionLayers: (value: ResolvedSetupSelection["instruction_layers"]) => void;
  serverDraftRevision: { current: number };
  draftRevision: { current: number };
  setConversations: Dispatch<SetStateAction<ChatConversation[]>>;
  props: { conversationListRef?: RefObject<ConversationListActions | null> };
  startFresh: () => void;
}): void {
  const {
    historyMutations, setShowInputs, selectionRequest, setupRequest, activeOwner, setBoundGeneration, setConversation,
    setInteractionThreadId, setSelectionLoading, setSelectionFailure, setMessage, setPendingSubmit, setPendingStop, setSending,
    cacheConversation, setModelOverrides, setInheritedModelConfiguration, setContextEntryIds, setContextKinds, setMessageSkillIds,
    setShortcutIds, setProjectFileRefs, setPicker, setAgentSetupId, agentSetups, setProjectId, setAgentSetupVersionId,
    boundDeploymentForModelIntent, setDeploymentId, profileIdRef, setProfileId, setTask, setAttachmentIds, setDocumentAssetIds,
    setSetupResolving, hasApplicationDefaults, setSetupError, setupEditedFields, setEmbeddingDeploymentId, setStartupOverrides,
    setApprovalMode, setPerRequestOverrides, setSelectedTools, setInputPolicy, setLocalInstructions, applyExecutionPreferences,
    setProjectPath, setSelectedKnowledgeIds, applyResolvedSetup, setInstructionLayers, serverDraftRevision, draftRevision,
    setConversations, props, startFresh,
  } = deps;
  if (historyMutations.current.get(item.id) === "deleted") return;
  setShowInputs(false);
  const requestId = selectionRequest.current + 1;
  selectionRequest.current = requestId;
  setupRequest.current += 1;
  activeOwner.current = { conversationId: null, threadId: null, generation: requestId };
  setBoundGeneration(requestId);
  setConversation(null);
  setInteractionThreadId(null);
  setSelectionLoading(item);
  setSelectionFailure(null);
  setMessage("");
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
      const draftConfig = next.draft?.intended_config ?? {};
      setModelOverrides((draftConfig.model_overrides ?? {}) as NonNullable<SetupConfiguration["model_overrides"]>);
      setInheritedModelConfiguration((draftConfig.inherited_model_configuration ?? null) as SetupConfiguration | null);
      setContextEntryIds([...(draftConfig.memory_entry_ids as string[] ?? []), ...(draftConfig.protected_instruction_entry_ids as string[] ?? [])]);
      setContextKinds(Object.fromEntries([...(draftConfig.memory_entry_ids as string[] ?? []).map(id => [id, "memory"]), ...(draftConfig.protected_instruction_entry_ids as string[] ?? []).map(id => [id, "instruction"])]));
      setMessageSkillIds((draftConfig.skill_entry_ids as string[]) ?? []); setShortcutIds((draftConfig.shortcut_ids as string[]) ?? []);
      setProjectFileRefs((draftConfig.project_file_refs as string[]) ?? []); setPicker(null);
      const restoredAgentId = Object.hasOwn(draftConfig, "agent_setup_id") ? typeof draftConfig.agent_setup_id === "string" ? draftConfig.agent_setup_id : null : next.agent_setup_id ?? null;
      setAgentSetupId(restoredAgentId);
      const nextProjectId = typeof draftConfig.project_id === "string" ? draftConfig.project_id : next.project_id ?? null;
      const nextVersionId = Object.hasOwn(draftConfig, "agent_setup_id") ? agentSetups.find(item => item.id === restoredAgentId)?.current_version_id ?? null : Object.hasOwn(draftConfig, "agent_setup_version_id") ? typeof draftConfig.agent_setup_version_id === "string" ? draftConfig.agent_setup_version_id : null : next.agent_setup_version_id ?? null;
      const draftSelectsConfiguration = Object.hasOwn(draftConfig, "model_configuration_id") || Object.hasOwn(draftConfig, "profile_id");
      const nextConfigurationId = draftSelectsConfiguration
        ? typeof draftConfig.model_configuration_id === "string" ? draftConfig.model_configuration_id
          : typeof draftConfig.profile_id === "string" ? draftConfig.profile_id : ""
        : next.setup_overrides?.model_configuration_id ?? next.profile_id ?? "";
      const boundDraftDeploymentId = boundDeploymentForModelIntent(next, nextConfigurationId, draftConfig.startup_overrides);
      const nextDeploymentId = Object.hasOwn(draftConfig, "deployment_id")
        ? typeof draftConfig.deployment_id === "string" && draftConfig.deployment_id ? draftConfig.deployment_id : boundDraftDeploymentId
        : draftSelectsConfiguration ? boundDraftDeploymentId : next.deployment_id;
      // Selecting another saved agent resets the previous agent's overrides,
      // just as dispatch does. A restored draft keeps only its own new edits.
      const priorOverrides = nextVersionId === (next.agent_setup_version_id ?? null) ? next.setup_overrides ?? {} : {};
      const overrides = setupOverrides({ ...priorOverrides, ...draftConfig,
        deployment_id: nextDeploymentId || null, model_configuration_id: nextConfigurationId || null });
      // The fetched chat and draft can be shown while thread registration
      // and setup resolution finish. Selection ownership still prevents a
      // late response from rebinding a different chat.
      setConversation(next);
      setProjectId(nextProjectId); setAgentSetupVersionId(nextVersionId);
      setDeploymentId(nextDeploymentId);
      profileIdRef.current = nextConfigurationId;
      setProfileId(nextConfigurationId);
      setTask(next.draft?.content ?? "");
      setAttachmentIds(next.draft?.attachment_ids ?? []);
      setDocumentAssetIds(Array.isArray(draftConfig.document_asset_ids) ? draftConfig.document_asset_ids as string[] : null);
      setSetupResolving(true);
      const registration = api.registerAgentInteractionThread({ source_surface: "chat", conversation_id: next.id });
      let resolutionFailure = "";
      const resolution = nextProjectId || nextVersionId || hasApplicationDefaults || (nextConfigurationId && !nextDeploymentId)
        ? workspaceApi.resolveSetup(nextProjectId, nextVersionId, overrides).catch(error => { resolutionFailure = errorMessage(error); return null; })
        : Promise.resolve(null);
      const [registered, resolved] = await Promise.all([registration, resolution]);
      if (selectionRequest.current !== requestId || historyMutations.current.get(item.id) === "deleted") return;
      setupRequest.current += 1;
      setSetupResolving(false); setSetupError(resolutionFailure);
      setupEditedFields.current = new Set(Object.keys(overrides));
      if (overrides.approval_mode == null) setupEditedFields.current.delete("approval_mode");
      activeOwner.current = { conversationId: next.id, threadId: registered.thread_id, generation: requestId };
      setBoundGeneration(requestId);
      setInteractionThreadId(registered.thread_id);
      setSelectionLoading(null);
      setEmbeddingDeploymentId(typeof draftConfig.embedding_deployment_id === "string" ? draftConfig.embedding_deployment_id : next.embedding_deployment_id ?? "");
      setStartupOverrides(overrides.startup_overrides ?? {});
      setApprovalMode(approvalModeOf(overrides.approval_mode ?? (resolved ? resolved.configuration.approval_mode : next.approval_mode)));
      setPerRequestOverrides(draftConfig.per_request_overrides && typeof draftConfig.per_request_overrides === "object" ? draftConfig.per_request_overrides as Record<string, unknown> : {});
      setSelectedTools(overrides.presented_tools ?? null);
      setInputPolicy(overrides.input_policy ?? null);
      setLocalInstructions(overrides.instructions ?? null);
      applyExecutionPreferences({ ...(next as ExecutionPreferences), ...draftConfig } as ExecutionPreferences);
      setProjectPath(next.project_path ?? "");
      setSelectedKnowledgeIds([
        ...((draftConfig.knowledge_version_refs as string[] | undefined) ?? [
          ...(next.memory_version_refs ?? []), ...(next.skill_version_refs ?? []), ...(next.protected_instruction_version_refs ?? []),
        ]),
      ]);
      if (resolved) {
        applyResolvedSetup(resolved, next.memory_version_refs ?? []);
        if (Array.isArray(draftConfig.knowledge_version_refs)) setSelectedKnowledgeIds(draftConfig.knowledge_version_refs as string[]);
      }
      else setInstructionLayers([]);
      const resolvedDeploymentId = nextConfigurationId && resolved?.configuration.model_configuration_id === nextConfigurationId
        ? resolved.configuration.deployment_id || nextDeploymentId : nextDeploymentId;
      setDeploymentId(resolvedDeploymentId);
      profileIdRef.current = nextConfigurationId;
      setProfileId(nextConfigurationId);
      serverDraftRevision.current = next.draft?.revision ?? 0;
      draftRevision.current += 1;
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
        setSetupResolving(false);
        // Keep the fetched transcript visible, but do not enable Send until
        // a retry establishes the interaction thread and selection owner.
        setSelectionFailure({ id: item.id, message: `Could not open this chat: ${errorMessage(error)}` });
      }
    });
}

export function applyConversationUpdate(next: ChatConversation, deps: {
  historyMutations: HistoryMutations;
  cacheConversation: (next: ChatConversation) => void;
  setConversation: Dispatch<SetStateAction<ChatConversation | null>>;
}): void {
  const { historyMutations, cacheConversation, setConversation } = deps;
  if (historyMutations.current.get(next.id) === "deleted") return;
  cacheConversation(next);
  setConversation(current => current?.id === next.id ? next : current);
}

export function reconcileHistory(items: ChatConversation[], deps: { historyMutations: HistoryMutations }): ChatConversation[] {
  const { historyMutations } = deps;
  return items.filter(item => historyMutations.current.get(item.id) !== "deleted").map(item => {
    const archived = historyMutations.current.get(item.id);
    return typeof archived === "boolean" ? { ...item, archived } : item;
  });
}

export function removeConversation(id: string, deps: {
  historyMutations: HistoryMutations;
  setConversations: Dispatch<SetStateAction<ChatConversation[]>>;
  activeOwner: ActiveOwner;
  selectionLoading: ChatConversation | null;
  conversation: ChatConversation | null;
  startFresh: () => void;
}): void {
  const { historyMutations, setConversations, activeOwner, selectionLoading, conversation, startFresh } = deps;
  historyMutations.current.set(id, "deleted");
  notifyAttentionChanged();
  setConversations(current => current.filter(item => item.id !== id));
  if (activeOwner.current.conversationId === id || selectionLoading?.id === id || conversation?.id === id) startFresh();
}
