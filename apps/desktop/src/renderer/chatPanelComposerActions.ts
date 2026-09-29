import type { Dispatch, SetStateAction } from "react";
import { api } from "./api";
import type { AgentInputPolicy, CapabilitySetupRequest } from "./agentInputPolicy";
import type { ChatRailPage } from "./ChatDock";
import type { ChatConversation, WorkbenchTab } from "./types";
import type { AgentSetup, SetupConfiguration } from "./workspaceApi";

export function createDraftConversation(deps: {
  selectionRequest: { current: number };
  conversationCreation: { current: { generation: number; promise: Promise<ChatConversation> } | null };
  chatCreationConfiguration: () => Parameters<typeof api.createChatConversation>[0];
}): Promise<ChatConversation> {
  const { selectionRequest, conversationCreation, chatCreationConfiguration } = deps;
  const generation = selectionRequest.current;
  if (conversationCreation.current?.generation === generation) return conversationCreation.current.promise;
  const promise = api.createChatConversation(chatCreationConfiguration()).catch(error => {
    if (conversationCreation.current?.promise === promise) conversationCreation.current = null;
    throw error;
  });
  conversationCreation.current = { generation, promise };
  return promise;
}

export function editInputs(configuration: SetupConfiguration, deps: {
  draftRevision: { current: number };
  markSetupEdited: (...keys: string[]) => void;
  setInputPolicy: (value: AgentInputPolicy | null) => void;
  setLocalInstructions: (value: string | null) => void;
  setReadinessEpoch: Dispatch<SetStateAction<number>>;
}): void {
  const { draftRevision, markSetupEdited, setInputPolicy, setLocalInstructions, setReadinessEpoch } = deps;
  draftRevision.current += 1;
  markSetupEdited("input_policy");
  setInputPolicy(configuration.input_policy ?? null);
  if (Object.hasOwn(configuration, "instructions")) {
    markSetupEdited("instructions");
    setLocalInstructions(configuration.instructions ?? "");
  }
  setReadinessEpoch(value => value + 1);
}

export function configureCapability(setup: CapabilitySetupRequest, deps: {
  openRail: (page: ChatRailPage) => void;
  setToolMenuRequest: Dispatch<SetStateAction<number>>;
  setShowInputs: (value: boolean) => void;
  navigateAway: (tab: WorkbenchTab, recordId?: string) => void;
  selectedAgent: AgentSetup | undefined;
  projectId: string | null;
}): void {
  const { openRail, setToolMenuRequest, setShowInputs, navigateAway, selectedAgent, projectId } = deps;
  if (setup.target === "browser") { openRail("browser"); return; }
  if (setup.target === "windows") { setToolMenuRequest(value => value + 1); return; }
  if (setup.target === "context") { setShowInputs(true); return; }
  if (setup.target === "settings") {
    try { sessionStorage.setItem("workbench.settings.category", "Connections"); } catch { /* Settings still opens. */ }
    navigateAway("settings", setup.target_id ?? undefined);
  } else navigateAway(setup.target === "agent" ? "agents" : setup.target === "project" ? "projects" : "knowledge", setup.target_id ?? (setup.target === "agent" ? selectedAgent?.id : setup.target === "project" ? projectId ?? undefined : undefined));
}
