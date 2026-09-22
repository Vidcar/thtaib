import { useEffect, useRef, type ReactNode } from "react";
import { Icon } from "./Icon";

export function CompactDialog(props: { title: string; labelledBy: string; busy?: boolean; onClose: () => void; children: ReactNode }) {
  const dialog = useRef<HTMLDialogElement>(null);
  useEffect(() => { dialog.current?.showModal(); }, []);
  return (
    <dialog
      ref={dialog}
      className="compact-dialog"
      aria-labelledby={props.labelledBy}
      onCancel={event => { if (props.busy) event.preventDefault(); else props.onClose(); }}
      onClose={props.onClose}
    >
      <header>
        <h3 id={props.labelledBy}>{props.title}</h3>
        <button type="button" className="icon-button" aria-label="Close" disabled={props.busy} onClick={props.onClose}><Icon name="close" /></button>
      </header>
      {props.children}
    </dialog>
  );
}
