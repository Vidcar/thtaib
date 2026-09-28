import { useCallback, useEffect, useRef, useState, type CSSProperties } from "react";
import { usePanelWidth } from "./PanelResize";

import { AgentRunPanel } from "./AgentRunPanel";
import { AttentionPanel } from "./AttentionPanel";
import { api } from "./api";
import { ChatPanel } from "./ChatPanel";
import type { ChatWorkspaceLaunch } from "./chatSetup";
import { errorMessage } from "./errors";
import { CreateProjectDialog } from "./CreateProjectDialog";
import { ProjectsPanel } from "./ProjectsPanel";
import { AgentSetupsPanel } from "./AgentSetupsPanel";
import { KnowledgePanel } from "./KnowledgePanel";
import { LabPanel } from "./LabPanel";
import { LibraryPanel } from "./LibraryPanel";
import { ModelsPanel } from "./ModelsPanel";
import { SettingsPanel } from "./SettingsPanel";
import { WorkbenchSidebar, type ChatLaunch, type ConversationListActions, type HistoryNotice } from "./WorkbenchSidebar";
import { loadAppearance, setAppearanceTheme } from "./appearanceStore";
import type { PresentationSettings, WorkbenchSurface, WorkbenchTab } from "./types";

const fallbackPresentation: PresentationSettings = {
  theme: "system",
  detailed_streams: false,
  attention_notifications: true,
  success_notifications: false,
};

export function App() {
  const productName = window.workbench?.productName ?? "Local AI Workbench";
  const surface: WorkbenchSurface = window.workbench?.surface ?? "managed-inference";
  const [tab, setTab] = useState<WorkbenchTab>("chat");
  const activeTab = useRef(tab);
  activeTab.current = tab;
  const prepareChatNavigation = useRef<(() => Promise<boolean>) | null>(null);
  const conversationListRef = useRef<ConversationListActions | null>(null);
  const attentionRequest = useRef(0);
  const [backendStatus, setBackendStatus] = useState("Checking local services…");
  const [backendOk, setBackendOk] = useState<boolean | null>(null);
  const [listsReady, setListsReady] = useState(false);
  const [modelPhase, setModelPhase] = useState<"pending" | "starting" | "ready" | "none" | "failed">("pending");
  const dotTitle = backendOk === false
    ? "Service unavailable"
    : backendOk !== true
      ? "Checking local services"
      : !listsReady || modelPhase === "pending"
        ? "Reading chats"
        : modelPhase === "starting"
          ? "Starting the model"
          : modelPhase === "failed"
            ? "Model did not start"
            : modelPhase === "ready"
              ? "Model ready"
              : "Local";
  const dotReady = backendOk === true && listsReady && (modelPhase === "ready" || modelPhase === "none");
  const onListsReady = useCallback((ready: boolean) => setListsReady(ready), []);
  const onModelPhase = useCallback((phase: "starting" | "ready" | "none" | "failed") => setModelPhase(phase), []);
  const [presentation, setPresentation] = useState<PresentationSettings>(fallbackPresentation);
  const [attentionConversationId, setAttentionConversationId] = useState<string | null>(null);
  const [attentionRunId, setAttentionRunId] = useState<string | null>(null);
  const [visitedEditors, setVisitedEditors] = useState<Set<WorkbenchTab>>(new Set());
  const [agentReview, setAgentReview] = useState<{ id?: string; request: number }>({ request: 0 });
  const [knowledgeReview, setKnowledgeReview] = useState<{ id?: string; request: number }>({ request: 0 });
  const [modelReview, setModelReview] = useState<{ id?: string; request: number }>({ request: 0 });
  useEffect(() => { if (["models", "agents", "knowledge"].includes(tab)) setVisitedEditors(current => new Set([...current, tab])); }, [tab]);
  const [workspaceLaunch, setWorkspaceLaunch] = useState<ChatWorkspaceLaunch | null>(null);
  const [historyRevision, setHistoryRevision] = useState(0);
  const [projectRevision, setProjectRevision] = useState(0);
  useEffect(() => { if (typeof document !== "undefined") document.dispatchEvent(new Event("workbench:navigation")); }, [tab]);
  const [chatLaunch, setChatLaunch] = useState<ChatLaunch | null>(null);
  const [historyNotice, setHistoryNotice] = useState<HistoryNotice | null>(null);
  const [activeConversationId, setActiveConversationId] = useState<string | null>(null);
  const selectionStorageKey = `workbench.chat.selection:${window.workbench?.backendUrl ?? "http://127.0.0.1:8000"}`;
  const [rememberedConversationId] = useState(() => {
    try { return window.localStorage?.getItem(selectionStorageKey) || null; } catch { return null; }
  });
  const [restoringConversation, setRestoringConversation] = useState(Boolean(rememberedConversationId));
  const pendingRestoration = useRef(rememberedConversationId ? { id: rememberedConversationId } : null);
  const rememberConversation = useCallback((id: string | null) => {
    setActiveConversationId(id);
    // The Chat component starts empty while its saved selection is resolving.
    // That initial report is not an explicit request for a new conversation.
    if (!id && pendingRestoration.current) return;
    pendingRestoration.current = null;
    setRestoringConversation(false);
    try { window.localStorage?.setItem(selectionStorageKey, id ?? ""); } catch { /* Selection still works without storage. */ }
  }, [selectionStorageKey]);
  useEffect(() => {
    const pending = pendingRestoration.current;
    if (!pending || !listsReady || backendOk !== true) return;
    let cancelled = false;
    let retry: ReturnType<typeof setTimeout> | undefined;
    async function restore() {
      if (cancelled || pendingRestoration.current !== pending) return;
      try {
        const conversations = await api.chatConversations(true);
        if (cancelled || pendingRestoration.current !== pending) return;
        pendingRestoration.current = null;
        const conversation = conversations.find(item => item.id === pending!.id);
        if (conversation) setChatLaunch({ id: crypto.randomUUID(), kind: "open", conversationId: conversation.id, conversation });
        else rememberConversation(null);
      } catch {
        // A service restart cannot turn a remembered chat into New chat.
        if (!cancelled && pendingRestoration.current === pending) retry = setTimeout(() => void restore(), 1000);
      }
    }
    void restore();
    return () => { cancelled = true; clearTimeout(retry); };
  }, [backendOk, listsReady, rememberConversation]);
  const [createProjectOpen, setCreateProjectOpen] = useState(false);
  const [focusProjectId, setFocusProjectId] = useState<string | null>(null);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(() => {
    try { const saved = window.localStorage?.getItem("workbench.navigation.collapsed"); return saved === null || saved === undefined ? window.innerWidth < 900 : saved === "true"; } catch { return window.innerWidth < 900; }
  });
  const [sidebarWidth, setSidebarWidth] = usePanelWidth("workbench.navigation.width", 232, 190, 380);
  useEffect(() => { try { window.localStorage?.setItem("workbench.navigation.collapsed", String(sidebarCollapsed)); } catch { /* Optional layout preference. */ } }, [sidebarCollapsed]);

  useEffect(() => {
    document.documentElement.dataset.theme = presentation.theme;
    setAppearanceTheme(presentation.theme);
  }, [presentation.theme]);

  useEffect(() => { void loadAppearance(); }, []);

  useEffect(() => {
    let cancelled = false;
    async function check(): Promise<void> {
      try {
        await api.health();
        if (cancelled) {
          return;
        }
        setBackendOk(true);
        setBackendStatus("Local services connected");
      } catch (error: unknown) {
        if (cancelled) {
          return;
        }
        setBackendOk(false);
        setBackendStatus(`Local service unavailable · ${errorMessage(error)}`);
      }
    }
    void check();
    const timer = window.setInterval(() => {
      void check();
    }, 10000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [surface]);

  useEffect(() => {
    let cancelled = false;
    void api.presentationSettings()
      .then((next) => {
        if (!cancelled) {
          setPresentation(next);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setPresentation(fallbackPresentation);
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const openAttentionTarget = useCallback(async (conversationId: string | null, runId: string) => {
    const request = ++attentionRequest.current;
    const originTab = activeTab.current;
    if (prepareChatNavigation.current && !await prepareChatNavigation.current()) return false;
    if (attentionRequest.current !== request || activeTab.current !== originTab) return false;
    pendingRestoration.current = null;
    setRestoringConversation(false);
    if (conversationId) {
      setAttentionConversationId(conversationId);
      setTab("chat");
    } else {
      setAttentionRunId(runId);
      setTab("agent-run");
    }
    return true;
  }, []);
  const clearAttentionConversation = useCallback((id: string) => {
    setAttentionConversationId(current => current === id ? null : current);
  }, []);
  const clearAttentionRun = useCallback((id: string) => {
    setAttentionRunId(current => current === id ? null : current);
  }, []);
  const clearFocusProject = useCallback(() => setFocusProjectId(null), []);

  useEffect(() => {
    const unsubscribe = window.workbench?.onAttention?.(openAttentionTarget);
    return () => {
      unsubscribe?.();
    };
  }, [openAttentionTarget]);

  function openOwner(next: WorkbenchTab, recordId?: string) {
    if (next === "agents" && recordId) setAgentReview(previous => ({ id: recordId, request: previous.request + 1 }));
    if (next === "knowledge" && recordId) setKnowledgeReview(previous => ({ id: recordId, request: previous.request + 1 }));
    if (next === "models" && recordId) setModelReview(previous => ({ id: recordId, request: previous.request + 1 }));
    if (next === "projects" && recordId) setFocusProjectId(recordId);
    setTab(next);
  }

  function renderTab(current: WorkbenchTab) {
    switch (current) {
      case "chat":
        return (
          <ChatPanel
            restoringSelection={restoringConversation}
            workspaceLaunch={workspaceLaunch}
            onWorkspaceLaunchHandled={() => setWorkspaceLaunch(null)}
            chatLaunch={chatLaunch}
            onChatLaunchHandled={() => setChatLaunch(null)}
            historyNotice={historyNotice}
            conversationListRef={conversationListRef}
            onHistoryChanged={() => setHistoryRevision(value => value + 1)}
            onActiveConversationId={rememberConversation}
            onCreateProject={() => setCreateProjectOpen(true)}
            projectRevision={projectRevision}
            activeTab={tab}
            backendOk={backendOk}
            backendStatus={backendStatus}
            attentionConversationId={attentionConversationId}
            onAttentionHandled={clearAttentionConversation}
            navigationPreparationRef={prepareChatNavigation}
            onPresentationChange={setPresentation}
            onNavigate={openOwner}
            presentation={presentation}
            productName={productName}
            onModelPhase={onModelPhase}
          />
        );
      case "projects":
        return <ProjectsPanel contextual projectRevision={projectRevision} onProjectChanged={() => setProjectRevision(value => value + 1)} focusProjectId={focusProjectId} onFocusHandled={clearFocusProject} onAddProject={() => setCreateProjectOpen(true)} onOpenChat={project => { pendingRestoration.current = null; setRestoringConversation(false); if (!activeConversationId) rememberConversation(null); setWorkspaceLaunch({ id: crypto.randomUUID(), projectId: project.id }); setTab("chat"); }} />;
      case "agents":
        return <AgentSetupsPanel active={tab === "agents"} openAgentId={agentReview.id} openRequest={agentReview.request} onNavigate={openOwner} onUse={setup => { pendingRestoration.current = null; setRestoringConversation(false); if (!activeConversationId) rememberConversation(null); setWorkspaceLaunch({ id: crypto.randomUUID(), agentSetupVersionId: setup.current_version_id }); setTab("chat"); }} />;
      case "models":
        return <ModelsPanel active={tab === "models"} openRecordId={modelReview.id} openRequest={modelReview.request} />;
      case "knowledge":
        return <KnowledgePanel active={tab === "knowledge"} openEntryId={knowledgeReview.id} openRequest={knowledgeReview.request} />;
      case "agent-run":
        return <AgentRunPanel attentionRunId={attentionRunId} onAttentionHandled={clearAttentionRun} onNavigate={openOwner} />;
      case "lab":
        return <LabPanel />;
      case "library":
        return <LibraryPanel />;
      case "attention":
        return <AttentionPanel onOpenItem={(item) => openAttentionTarget(item.conversation_id, item.run_id)} />;
      case "settings":
        return <SettingsPanel onPreferencesChanged={setPresentation} />;
      default: {
        const unexpected: never = current;
        return unexpected;
      }
    }
  }

  function openChatLaunch(launch: ChatLaunch) {
    pendingRestoration.current = null;
    setRestoringConversation(false);
    if (launch.kind === "fresh" && !activeConversationId) rememberConversation(null);
    setChatLaunch(launch);
    setTab("chat");
  }

  return (
    <div className={`app${tab === "chat" ? " app-chat" : ""}${sidebarCollapsed ? " app-nav-collapsed" : ""}`} style={{ "--navigation-width": `${sidebarWidth}px` } as CSSProperties}>
      <CreateProjectDialog open={createProjectOpen} onClose={() => setCreateProjectOpen(false)} onCreated={() => setProjectRevision(value => value + 1)} />
      <WorkbenchSidebar
        tab={tab}
        collapsed={sidebarCollapsed}
        width={sidebarWidth}
        onCollapsedChange={setSidebarCollapsed}
        onWidthChange={setSidebarWidth}
        onNavigate={next => {
          void (async () => {
            if (activeTab.current === "chat" && next !== "chat" && prepareChatNavigation.current) {
              if (!await prepareChatNavigation.current()) return;
            }
            setTab(next);
          })();
        }}
        backendOk={backendOk}
        backendStatus={backendStatus}
        activeConversationId={activeConversationId}
        historyRevision={historyRevision}
        projectRevision={projectRevision}
        conversationListRef={conversationListRef}
        onOpenConversation={conversation => openChatLaunch({ id: crypto.randomUUID(), kind: "open", conversationId: conversation.id, conversation })}
        onNewChat={() => openChatLaunch({ id: crypto.randomUUID(), kind: "fresh" })}
        onAddProject={() => setCreateProjectOpen(true)}
        onNewChatInProject={project => {
          void (async () => {
            if (activeTab.current === "chat" && prepareChatNavigation.current && !await prepareChatNavigation.current()) return;
            pendingRestoration.current = null;
            setRestoringConversation(false);
            if (!activeConversationId) rememberConversation(null);
            setWorkspaceLaunch({ id: crypto.randomUUID(), projectId: project.id });
            setTab("chat");
          })();
        }}
        onEditProject={projectId => {
          void (async () => {
            if (activeTab.current === "chat" && prepareChatNavigation.current && !await prepareChatNavigation.current()) return;
            setFocusProjectId(projectId);
            setTab("projects");
          })();
        }}
        onProjectChanged={() => setProjectRevision(value => value + 1)}
        onHistoryNotice={notice => { setHistoryNotice(notice); setHistoryRevision(value => value + 1); }}
        onBeforeConversationChange={() => prepareChatNavigation.current?.() ?? Promise.resolve()}
        dotReady={dotReady}
        dotTitle={dotTitle}
        onListsReady={onListsReady}
      />
      <main className="app-main">
        <div className="persistent-chat" data-active={tab === "chat"} aria-hidden={tab !== "chat"} inert={tab !== "chat"}>{renderTab("chat")}</div>
        {(["models", "agents", "knowledge"] as WorkbenchTab[]).map(editor => visitedEditors.has(editor) || tab === editor ? <div key={editor} className="persistent-editor" hidden={tab !== editor} inert={tab !== editor}>{renderTab(editor)}</div> : null)}
        {tab !== "chat" && !["models", "agents", "knowledge"].includes(tab) ? renderTab(tab) : null}
      </main>
    </div>
  );
}
