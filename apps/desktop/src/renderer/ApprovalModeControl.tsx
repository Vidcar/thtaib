import { Icon } from "./Icon";

export const APPROVAL_MODES = [
  { id: "ask", label: "Ask", summary: "Ask", hint: "Ask before file edits, shell commands, and external effects. Saved permissions can allow matching actions." },
  { id: "full_access", label: "Full access", summary: "Full access", hint: "Allow selected file, shell, and external tools without approval pauses. Questions still wait for your answer." },
] as const;

export type ApprovalMode = (typeof APPROVAL_MODES)[number]["id"];

export function approvalModeOf(value: unknown): ApprovalMode {
  return value === "full_access" ? value : "ask";
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
            <Icon name={mode.id === "full_access" ? "shield" : "attention"} size={16} />
            <span><strong>{mode.label}</strong><small>{mode.hint}</small></span>
            <Icon name={props.value === mode.id ? "check" : "minus"} size={14} />
          </button>
        ))}
      </div>
    </div>
  );
}
