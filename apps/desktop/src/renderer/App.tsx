import { useCallback, useEffect, useRef, useState, type CSSProperties } from "react";
import { PanelResize, usePanelWidth } from "./PanelResize";

import { AgentRunPanel } from "./AgentRunPanel";
import { AttentionPanel, AttentionButton } from "./AttentionPanel";
import { api } from "./api";
import { ChatPanel } from "./ChatPanel";
import type { ChatWorkspaceLaunch } from "./chatSetup";
import { errorMessage } from "./errors";
import { Icon } from "./Icon";
import { ProjectsPanel } from "./ProjectsPanel";
import { AgentSetupsPanel } from "./AgentSetupsPanel";
import { workbenchTabs, tabIcons, tabLabel } from "./workspaceNavigation";
import { KnowledgePanel } from "./KnowledgePanel";
import { LabPanel } from "./LabPanel";
import { LibraryPanel } from "./LibraryPanel";
import { ModelsPanel } from "./ModelsPanel";
import { SettingsPanel } from "./SettingsPanel";
import type { RetainedAsset } from "./packet03Api";
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
  const attentionRequest = useRef(0);
  const [backendStatus, setBackendStatus] = useState("Checking local services…");
  const [backendOk, setBackendOk] = useState<boolean | null>(null);
  const [presentation, setPresentation] = useState<PresentationSettings>(fallbackPresentation);
  const [attentionConversationId, setAttentionConversationId] = useState<string | null>(null);
  const [attentionRunId, setAttentionRunId] = useState<string | null>(null);
  const [reuseAssetIds, setReuseAssetIds] = useState<string[]>([]);
  const [workspaceLaunch, setWorkspaceLaunch] = useState<ChatWorkspaceLaunch | null>(null);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(() => {
    try { const saved = window.localStorage?.getItem("workbench.navigation.collapsed"); return saved === null || saved === undefined ? window.innerWidth < 900 : saved === "true"; } catch { return window.innerWidth < 900; }
  });
  const [sidebarWidth, setSidebarWidth] = usePanelWidth("workbench.navigation.width", 232, 190, 380);
  useEffect(() => { try { window.localStorage?.setItem("workbench.navigation.collapsed", String(sidebarCollapsed)); } catch { /* Optional layout preference. */ } }, [sidebarCollapsed]);

  useEffect(() => {
    document.documentElement.dataset.theme = presentation.theme;
  }, [presentation.theme]);

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
    if (prepareChatNavigation.current && !await prepareChatNavigation.current()) return;
    if (attentionRequest.current !== request || activeTab.current !== originTab) return;
    if (conversationId) {
      setAttentionConversationId(conversationId);
      setTab("chat");
    } else {
      setAttentionRunId(runId);
      setTab("agent-run");
    }
  }, []);
  const clearAttentionConversation = useCallback((id: string) => {
    setAttentionConversationId(current => current === id ? null : current);
  }, []);
  const clearAttentionRun = useCallback((id: string) => {
    setAttentionRunId(current => current === id ? null : current);
  }, []);

  useEffect(() => {
    const unsubscribe = window.workbench?.onAttention?.(openAttentionTarget);
    return () => {
      unsubscribe?.();
    };
  }, [openAttentionTarget]);

  function handleLibraryReuseMany(assets: RetainedAsset[]): void {
    setReuseAssetIds([...new Set(assets.map((asset) => asset.id))]);
    setTab("chat");
  }

  function renderTab(current: WorkbenchTab) {
    switch (current) {
      case "chat":
        return (
          <ChatPanel
            workspaceLaunch={workspaceLaunch}
            onWorkspaceLaunchHandled={() => setWorkspaceLaunch(null)}
            navigationCollapsed={sidebarCollapsed}
            onNavigationCollapsedChange={setSidebarCollapsed}
            navigationWidth={sidebarWidth}
            onNavigationWidthChange={setSidebarWidth}
            activeTab="chat"
            backendOk={backendOk}
            backendStatus={backendStatus}
            attentionConversationId={attentionConversationId}
            onAttentionHandled={clearAttentionConversation}
            navigationPreparationRef={prepareChatNavigation}
            onPresentationChange={setPresentation}
            onNavigate={(next) => setTab(next)}
            reuseAssetId={reuseAssetIds[0] ?? null}
            reuseAssetIds={reuseAssetIds}
            onReuseAssetHandled={() => setReuseAssetIds([])}
            presentation={presentation}
            productName={productName}
          />
        );
      case "projects":
        return <ProjectsPanel onOpenChat={project => { setWorkspaceLaunch({ id: crypto.randomUUID(), projectId: project.id }); setTab("chat"); }} />;
      case "agents":
        return <AgentSetupsPanel onUse={setup => { setWorkspaceLaunch({ id: crypto.randomUUID(), agentSetupVersionId: setup.current_version_id }); setTab("chat"); }} />;
      case "models":
        return <ModelsPanel />;
      case "knowledge":
        return <KnowledgePanel />;
      case "agent-run":
        return <AgentRunPanel attentionRunId={attentionRunId} onAttentionHandled={clearAttentionRun} />;
      case "lab":
        return <LabPanel />;
      case "library":
        return (
          <LibraryPanel
            onReuseSelectedAssets={handleLibraryReuseMany}
          />
        );
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

  const tabs = workbenchTabs;

  return (
    <div className={`${tab === "chat" ? "app app-chat" : "app"}${sidebarCollapsed ? " app-nav-collapsed" : ""}`} style={{ "--navigation-width": `${sidebarWidth}px` } as CSSProperties}>
      {tab === "chat" ? null : (
        <aside className="app-nav" aria-label="Workbench">
          <div className="app-nav-head">
            <div>
              <h1>Workbench</h1>
            </div>
            <button
              type="button"
              className="nav-collapse"
              aria-label={sidebarCollapsed ? "Expand sidebar" : "Collapse sidebar"}
              aria-expanded={!sidebarCollapsed}
              onClick={() => setSidebarCollapsed((value) => !value)}
            >
              <Icon name="panel" size={18} />
            </button>
          </div>
          <nav className="side-tabs">
            {tabs.map((item) => item === "attention" ? <AttentionButton key={item} active={tab === item} collapsed={sidebarCollapsed} onOpen={() => setTab("attention")} /> : (
              <button
                key={item}
                type="button"
                className={item === tab ? "tab active" : "tab"}
                aria-label={tabLabel(item)}
                title={tabLabel(item)}
                onClick={() => setTab(item)}
              >
                <Icon name={tabIcons[item]} size={18} />
                {sidebarCollapsed ? <span className="sr-only">{tabLabel(item)}</span> : <span>{tabLabel(item)}</span>}
              </button>
            ))}
          </nav>
          <div className="service-indicator" title={backendStatus}><span className={`status-dot${backendOk ? " ready" : ""}`} /><span>{backendOk === false ? "Service unavailable" : "Local"}</span></div>
          {!sidebarCollapsed ? <PanelResize label="Resize navigation" width={sidebarWidth} onResize={setSidebarWidth} reset={232} /> : null}
        </aside>
      )}
      <main className="app-main">{renderTab(tab)}</main>
    </div>
  );
}
