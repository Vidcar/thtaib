import type { DesktopAccess } from "./types";

export type ExecutionPreferences = { work_mode?: "work" | "plan"; desktop_access?: DesktopAccess; helper_agent_ids?: string[]; review?: { enabled?: boolean; criteria?: string; max_revisions?: number } };

export function applyExecutionPreferences(config: ExecutionPreferences, setters: {
  setWorkMode: (value: "work" | "plan") => void;
  setDesktopAccess: (value: DesktopAccess) => void;
  setHelperAgentIds: (value: string[]) => void;
  setReview: (value: { enabled: boolean; criteria: string; max_revisions: 2 }) => void;
}): void {
  const { setWorkMode, setDesktopAccess, setHelperAgentIds, setReview } = setters;
  setWorkMode(config.work_mode === "plan" ? "plan" : "work");
  setDesktopAccess(config.desktop_access ?? "off");
  setHelperAgentIds(config.helper_agent_ids ?? []);
  setReview({ enabled: config.review?.enabled === true, criteria: config.review?.criteria ?? "", max_revisions: 2 });
}
