import { useEffect, useState } from "react";

import { AgentRunPanel } from "./AgentRunPanel";
import { AttentionPanel } from "./AttentionPanel";
import { api } from "./api";
import { ChatPanel } from "./ChatPanel";
import { errorMessage } from "./errors";
import { Icon, type IconName } from "./Icon";
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

function surfaceLabel(surface: WorkbenchSurface): string {
  switch (surface) {
    case "managed-inference":
      return "Local models";
    default: {
      const unexpected: never = surface;
      return unexpected;
    }
  }
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

const tabIcons: Record<WorkbenchTab, IconName> = {
  chat: "chat",
  library: "library",
  attention: "activity",
  models: "models",
  knowledge: "knowledge",
  "agent-run": "agent-run",
  lab: "lab",
  settings: "settings",
};

export function App() {
  const productName = window.workbench?.productName ?? "Local AI Workbench";
  const surface: WorkbenchSurface = window.workbench?.surface ?? "managed-inference";
  const [tab, setTab] = useState<WorkbenchTab>("chat");
  const [backendStatus, setBackendStatus] = useState("Checking local services…");
  const [backendOk, setBackendOk] = useState<boolean | null>(null);
  const [presentation, setPresentation] = useState<PresentationSettings>(fallbackPresentation);
  const [attentionConversationId, setAttentionConversationId] = useState<string | null>(null);
  const [reuseAssetIds, setReuseAssetIds] = useState<string[]>([]);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);

  useEffect(() => {
    document.documentElement.dataset.theme = presentation.theme;
  }, [presentation.theme]);

  useEffect(() => {
    let cancelled = false;
    async function check(): Promise<void> {
      try {
        const health = await api.health();
        if (cancelled) {
          return;
        }
        setBackendOk(true);
        setBackendStatus(`${health.product} · ${surfaceLabel(surface)}`);
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

  useEffect(() => {
    const unsubscribe = window.workbench?.onAttention?.((conversationId) => {
      setTab("chat");
      setAttentionConversationId(conversationId);
    });
    return () => {
      unsubscribe?.();
    };
  }, []);

  function openAttentionConversation(conversationId: string | null): void {
    setAttentionConversationId(conversationId);
    setTab("chat");
  }

  function handleLibraryReuseMany(assets: RetainedAsset[]): void {
    setReuseAssetIds([...new Set(assets.map((asset) => asset.id))]);
    setTab("chat");
  }

  function renderTab(current: WorkbenchTab) {
    switch (current) {
      case "chat":
        return (
          <ChatPanel
            activeTab="chat"
            backendOk={backendOk}
            backendStatus={backendStatus}
            attentionConversationId={attentionConversationId}
            onPresentationChange={setPresentation}
            onNavigate={(next) => setTab(next)}
            reuseAssetId={reuseAssetIds[0] ?? null}
            reuseAssetIds={reuseAssetIds}
            onReuseAssetHandled={() => setReuseAssetIds([])}
            presentation={presentation}
            productName={productName}
          />
        );
      case "models":
        return <ModelsPanel />;
      case "knowledge":
        return <KnowledgePanel />;
      case "agent-run":
        return <AgentRunPanel />;
      case "lab":
        return <LabPanel />;
      case "library":
        return (
          <LibraryPanel
            onReuseSelectedAssets={handleLibraryReuseMany}
          />
        );
      case "attention":
        return <AttentionPanel onOpenConversation={openAttentionConversation} />;
      case "settings":
        return <SettingsPanel onPreferencesChanged={setPresentation} />;
      default: {
        const unexpected: never = current;
        return unexpected;
      }
    }
  }

  const tabs: WorkbenchTab[] = ["chat", "library", "attention", "models", "knowledge", "agent-run", "lab", "settings"];

  return (
    <div className={`${tab === "chat" ? "app app-chat" : "app"}${sidebarCollapsed ? " app-nav-collapsed" : ""}`}>
      {tab === "chat" ? null : (
        <aside className="app-nav" aria-label="Workbench">
          <div className="app-nav-head">
            <div>
              <p className="eyebrow">Local AI Workbench</p>
              <h1>{productName}</h1>
            </div>
            <button
              type="button"
              className="nav-collapse"
              aria-label={sidebarCollapsed ? "Expand sidebar" : "Collapse sidebar"}
              aria-expanded={!sidebarCollapsed}
              onClick={() => setSidebarCollapsed((value) => !value)}
            >
              {sidebarCollapsed ? "›" : "‹"}
            </button>
          </div>
          <nav className="side-tabs">
            {tabs.map((item) => (
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
          <p className={backendOk === false ? "notice notice-error" : "hint"}>{backendStatus}</p>
        </aside>
      )}
      <main className="app-main">{renderTab(tab)}</main>
    </div>
  );
}
