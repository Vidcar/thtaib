import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { App } from "./App";
import "./styles.css";
import "./chatPolish.css";
import "./workbenchTheme.css";
import "./surfacePolish.css";
import "./appearanceDefaults.css";

const root = document.getElementById("root");
if (!root) {
  throw new Error("Local AI Workbench renderer root is missing.");
}

createRoot(root).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
