export const APPROVAL_MODES = [
  { id: "ask", label: "Ask", summary: "Ask", hint: "Rename, delete, shell, and external tools stop for a decision." },
  { id: "approve_for_me", label: "Approve for me", summary: "Approve", hint: "File changes proceed. Shell and external tools still stop." },
  { id: "full_access", label: "Full access", summary: "Full", hint: "Selected shell and external tools proceed. Questions still wait." },
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
  const selected = APPROVAL_MODES.find(item => item.id === props.value) ?? APPROVAL_MODES[0];
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
            {mode.label}
          </button>
        ))}
      </div>
      <p className="hint">{selected.hint}</p>
    </div>
  );
}
