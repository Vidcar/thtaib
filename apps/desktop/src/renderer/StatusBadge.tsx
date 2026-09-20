import { runStatusLabel, runStatusTone } from "./labels";
import type { AgentRunStatus } from "./types";

export function StatusBadge(props: {
  status?: AgentRunStatus | null;
  label?: string;
  tone?: "neutral" | "live" | "ok" | "warn" | "danger";
}) {
  if (!props.status && !props.label) {
    return null;
  }
  const tone = props.tone ?? (props.status ? runStatusTone(props.status) : "neutral");
  const label = props.label ?? (props.status ? runStatusLabel(props.status) : "");
  return <span className={`badge tone-${tone}`}>{label}</span>;
}
