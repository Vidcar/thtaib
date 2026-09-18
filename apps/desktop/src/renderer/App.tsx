import { useEffect, useState } from "react";

import { api } from "./api";
import { DeploymentsPanel } from "./DeploymentsPanel";
import { ModelsPanel } from "./ModelsPanel";
import type { WorkbenchSurface, WorkbenchTab } from "./types";

function surfaceLabel(surface: WorkbenchSurface): string {
  switch (surface) {
    case "managed-inference":
      return "Managed inference";
    default: {
      const unexpected: never = surface;
      return unexpected;
    }
  }
}

function tabLabel(tab: WorkbenchTab): string {
  switch (tab) {
    case "models":
      return "Models";
    case "deployments":
      return "Deployments";
    default: {
      const unexpected: never = tab;
      return unexpected;
    }
  }
}

export function App() {
  const productName = window.workbench?.productName ?? "Local AI Workbench";
  const surface: WorkbenchSurface = window.workbench?.surface ?? "managed-inference";
  const [tab, setTab] = useState<WorkbenchTab>("models");
  const [backendStatus, setBackendStatus] = useState("checking backend…");

  useEffect(() => {
    void api
      .health()
      .then((health) => setBackendStatus(`${health.product} · ${health.surface}`))
      .catch(() => setBackendStatus("Backend not reachable on 127.0.0.1:8000"));
  }, []);

  function renderTab(current: WorkbenchTab) {
    switch (current) {
      case "models":
        return <ModelsPanel />;
      case "deployments":
        return <DeploymentsPanel />;
      default: {
        const unexpected: never = current;
        return unexpected;
      }
    }
  }

  const tabs: WorkbenchTab[] = ["models", "deployments"];

  return (
    <main className="shell">
      <p className="eyebrow">Local AI Workbench</p>
      <h1>{productName}</h1>
      <p className="lede">
        {surfaceLabel(surface)}. Chat, Lab, and Builder are not part of this
        milestone.
      </p>
      <p className="hint">{backendStatus}</p>
      <nav className="tabs" aria-label="Workbench surfaces">
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
      {renderTab(tab)}
    </main>
  );
}
