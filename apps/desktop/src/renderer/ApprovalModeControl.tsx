import { Icon } from "./Icon";

export const APPROVAL_MODES = [
  { id: "ask", label: "Ask", summary: "Ask", hint: "Ask before renaming, deleting, or using tools that need approval. Read-only commands and saved permissions can proceed." },
  { id: "approve_for_me", label: "Approve for me", summary: "Approve for me", hint: "Allow selected file changes, including rename and delete. Shell and external tools still follow saved permissions and approval rules." },
  { id: "full_access", label: "Full access", summary: "Full access", hint: "Allow selected file, shell, and external tools without approval pauses. Questions still wait for your answer." },
] as const;

export type ApprovalMode = (typeof APPROVAL_MODES)[number]["id"];

export function approvalModeOf(value: unknown): ApprovalMode {
  return value === "approve_for_me" || value === "full_access" ? value : "ask";
}

export function approvalModeLabel(mode: ApprovalMode): string {
  return APPROVAL_MODES.find(item => item.id === mode)?.summary ?? "Ask";
}

export function ApprovalModeControl(props: {
  value: ApprovalMode;
  disabled?: boolean;
  onChange: (mode: ApprovalMode) => void;
}) {
  return (
    <div className="approval-mode-field">
      <div className="approval-mode" role="radiogroup" aria-label="Approval mode">
        {APPROVAL_MODES.map(mode => (
          <button
            key={mode.id}
            type="button"
            role="radio"
            aria-label={mode.label}
            aria-checked={props.value === mode.id}
            className={props.value === mode.id ? "is-selected" : ""}
            disabled={props.disabled}
            onClick={() => props.onChange(mode.id)}
          >
            <Icon name={mode.id === "full_access" ? "shield" : mode.id === "approve_for_me" ? "sparkles" : "attention"} size={16} />
            <span><strong>{mode.label}</strong><small>{mode.hint}</small></span>
            <Icon name={props.value === mode.id ? "check" : "minus"} size={14} />
          </button>
        ))}
      </div>
    </div>
  );
}
