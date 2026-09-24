import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import "./appearanceDefaults.css";
import "./styles.css";
import { App } from "./App";
import { AppearancePreviewApp } from "./AppearancePreview";

const root = document.getElementById("root");
if (!root) {
  throw new Error("Local AI Workbench renderer root is missing.");
}

createRoot(root).render(
  <StrictMode>
    {window.location.hash === "#appearance-preview" ? <AppearancePreviewApp /> : <App />}
  </StrictMode>,
);
