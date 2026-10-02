import { useId, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Icon, type IconName } from "./Icon";

export function MessageTaskActions({ runId, held, onRetry, onEdit }: {
  runId: string;
  held: string | null;
  onRetry: () => void;
  onEdit: () => void;
}) {
  return (
    <div className="message-task-actions" role="group" aria-label="Message actions">
      <RewindButton label="Retry" icon="refresh" held={held} onActivate={onRetry} />
      <RewindButton label="Edit" icon="edit" held={held} runId={runId} onActivate={onEdit} />
    </div>
  );
}

function RewindButton({ label, icon, held, runId, onActivate }: {
  label: string;
  icon: IconName;
  held: string | null;
  runId?: string;
  onActivate: () => void;
}) {
  const tipId = useId();
  const buttonRef = useRef<HTMLButtonElement>(null);
  const tipRef = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState(false);
  const [place, setPlace] = useState<{ left: number; top: number } | null>(null);
  useLayoutEffect(() => {
    if (!open) return;
    const anchor = buttonRef.current?.getBoundingClientRect();
    const tip = tipRef.current?.getBoundingClientRect();
    if (!anchor || !tip) return;
    const header = document.querySelector(".chat-header")?.getBoundingClientRect();
    const above = anchor.top - tip.height - 8;
    const below = anchor.bottom + 8;
    const top = above >= Math.max(8, header?.bottom ?? 8) ? above : below;
    setPlace({
      left: Math.max(8, Math.min(anchor.left, window.innerWidth - tip.width - 8)),
      top: Math.max(8, Math.min(top, window.innerHeight - tip.height - 8)),
    });
  }, [open, held]);
  return (
    <>
      <button
        ref={buttonRef}
        type="button"
        className="icon-button"
        aria-label={label}
        title={held ?? label}
        aria-disabled={held ? true : undefined}
        aria-describedby={open && held ? tipId : undefined}
        data-edit-run={label === "Edit" ? runId : undefined}
        onMouseEnter={() => { if (held) setOpen(true); }}
        onMouseLeave={() => setOpen(false)}
        onFocus={(event) => { if (held && event.currentTarget.matches(":focus-visible")) setOpen(true); }}
        onBlur={() => setOpen(false)}
        onClick={() => { if (!held) onActivate(); }}
        onKeyDown={(event) => {
          if (held && (event.key === "Enter" || event.key === " ")) {
            event.preventDefault();
            event.stopPropagation();
          }
        }}
      >
        <Icon name={icon} size={14} />
      </button>
      {open && held && typeof document !== "undefined" ? createPortal(
        <div ref={tipRef} id={tipId} role="tooltip" className="rewind-tooltip" style={{ left: place?.left ?? 8, top: place?.top ?? 8, visibility: place ? "visible" : "hidden" }}>{held}</div>,
        document.body,
      ) : null}
    </>
  );
}
