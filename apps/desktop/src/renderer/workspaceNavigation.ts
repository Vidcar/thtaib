import type { IconName } from "./Icon";
import type { WorkbenchTab } from "./types";

export const workbenchTabs: WorkbenchTab[] = ["chat", "agents", "models", "library", "knowledge", "agent-run", "lab", "attention", "settings"];
const labels: Record<WorkbenchTab, string> = { chat: "Chat", projects: "Projects", agents: "Agents", models: "Models", library: "Library", knowledge: "Knowledge", "agent-run": "Workflows", lab: "Lab", attention: "Attention", settings: "Settings" };
export const tabIcons: Record<WorkbenchTab, IconName> = { chat: "chat", projects: "folder", agents: "sparkles", models: "models", library: "library", knowledge: "knowledge", "agent-run": "agent-run", lab: "lab", attention: "activity", settings: "settings" };
export const tabLabel = (tab: WorkbenchTab): string => labels[tab];
