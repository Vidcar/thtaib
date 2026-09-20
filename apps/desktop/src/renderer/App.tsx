import { useEffect, useState } from "react";

import { AgentRunPanel } from "./AgentRunPanel";
import { api } from "./api";
import { ChatPanel } from "./ChatPanel";
import { errorMessage } from "./errors";
import { KnowledgePanel } from "./KnowledgePanel";
import { LabPanel } from "./LabPanel";
import { ModelsPanel } from "./ModelsPanel";
import type { WorkbenchSurface, WorkbenchTab } from "./types";

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
    default: {
      const unexpected: never = tab;
      return unexpected;
    }
  }
}

export function App() {
  const productName = window.workbench?.productName ?? "Local AI Workbench";
  const surface: WorkbenchSurface = window.workbench?.surface ?? "managed-inference";
  const [tab, setTab] = useState<WorkbenchTab>("chat");
  const [backendStatus, setBackendStatus] = useState("Checking local services…");
  const [backendOk, setBackendOk] = useState<boolean | null>(null);

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

  function renderTab(current: WorkbenchTab) {
    switch (current) {
      case "chat":
        return <ChatPanel />;
      case "models":
        return <ModelsPanel />;
      case "knowledge":
        return <KnowledgePanel />;
      case "agent-run":
        return <AgentRunPanel />;
      case "lab":
        return <LabPanel />;
      default: {
        const unexpected: never = current;
        return unexpected;
      }
    }
  }

  const tabs: WorkbenchTab[] = ["chat", "models", "knowledge", "agent-run", "lab"];

  return (
    <div className="app">
      <aside className="app-nav" aria-label="Workbench">
        <p className="eyebrow">Local AI Workbench</p>
        <h1>{productName}</h1>
        <nav className="side-tabs">
          {tabs.map((item) => (
            <button
              key={item}
              type="button"
              className={item === tab ? "tab active" : "tab"}
              onClick={() => setTab(item)}
            >
              {tabLabel(item)}
            </button>
          ))}
        </nav>
        <p className={backendOk === false ? "notice notice-error" : "hint"}>{backendStatus}</p>
      </aside>
      <main className="app-main">{renderTab(tab)}</main>
    </div>
  );
}
