import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { App } from "./App";
import { AppearancePreviewApp } from "./AppearancePreview";
import "./styles.css";
import "./chatPolish.css";
import "./workbenchTheme.css";
import "./surfacePolish.css";
import "./appearanceDefaults.css";
import "./workbenchCohesion.css";

const root = document.getElementById("root");
if (!root) {
  throw new Error("Local AI Workbench renderer root is missing.");
}

createRoot(root).render(
  <StrictMode>
    {window.location.hash === "#appearance-preview" ? <AppearancePreviewApp /> : <App />}
  </StrictMode>,
);
