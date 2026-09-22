import type { ReactNode } from "react";

export function ConfirmNote(props: {
  className?: string;
  children: ReactNode;
  confirmLabel: string;
  cancelLabel: string;
  disabled?: boolean;
  cancelDisabled?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  return (
    <div className={props.className ?? "inline-note"}>
      <p>{props.children}</p>
      <div className="actions">
        <button type="button" disabled={props.disabled} onClick={props.onConfirm}>{props.confirmLabel}</button>
        <button type="button" disabled={props.cancelDisabled ?? props.disabled} onClick={props.onCancel}>{props.cancelLabel}</button>
      </div>
    </div>
  );
}
