import { useCallback, useEffect, useId, useLayoutEffect, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { Icon } from "./Icon";

/** Help is available to pointer, keyboard and touch without occupying the page. */
export function HoverHelp({ title = "About this setting", children, triggerContent, triggerClassName, bubbleClassName, placement = "below", interactive = false }: {
  title?: string;
  children: ReactNode;
  triggerContent?: ReactNode;
  triggerClassName?: string;
  bubbleClassName?: string;
  placement?: "above" | "below";
  interactive?: boolean;
}) {
  const id = useId();
  const trigger = useRef<HTMLButtonElement>(null);
  const bubble = useRef<HTMLDivElement>(null);
  const closeTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const hovered = useRef(false);
  const focused = useRef(false);
  const [open, setOpen] = useState(false);
  const [position, setPosition] = useState<{ left: number; top: number } | null>(null);
  const clearClose = useCallback(() => {
    if (closeTimer.current !== null) { clearTimeout(closeTimer.current); closeTimer.current = null; }
  }, []);
  const show = () => { clearClose(); setOpen(true); };
  const dismiss = useCallback(() => { clearClose(); setOpen(false); setPosition(null); }, [clearClose]);
  const leave = () => {
    clearClose();
    // Leave time to cross the small gap between the trigger and its portal.
    closeTimer.current = setTimeout(() => {
      closeTimer.current = null;
      if (!hovered.current && !focused.current) dismiss();
    }, 160);
  };
  const locate = useCallback(() => {
    const anchor = trigger.current?.getBoundingClientRect();
    const tip = bubble.current?.getBoundingClientRect();
    if (!anchor || !tip) return;
    const below = anchor.bottom + 8;
    const above = anchor.top - tip.height - 8;
    const top = placement === "above" && above >= 8 ? above : below + tip.height <= window.innerHeight - 8 ? below : above;
    const next = {
      left: Math.max(8, Math.min(anchor.left, window.innerWidth - tip.width - 8)),
      top: Math.max(8, Math.min(top, window.innerHeight - tip.height - 8)),
    };
    setPosition(current => current?.left === next.left && current.top === next.top ? current : next);
  }, [placement]);
  useLayoutEffect(() => { if (open) locate(); }, [open, children, locate]);
  useEffect(() => {
    if (!open) return;
    const outside = (event: PointerEvent) => {
      if (!trigger.current?.contains(event.target as Node) && !bubble.current?.contains(event.target as Node)) dismiss();
    };
    const escape = (event: KeyboardEvent) => { if (event.key === "Escape") { event.stopPropagation(); if (bubble.current?.contains(document.activeElement)) trigger.current?.focus(); dismiss(); } };
    window.addEventListener("resize", locate);
    document.addEventListener("scroll", locate, true);
    document.addEventListener("pointerdown", outside);
    document.addEventListener("keydown", escape);
    const observer = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(locate);
    if (bubble.current) observer?.observe(bubble.current);
    return () => {
      window.removeEventListener("resize", locate);
      document.removeEventListener("scroll", locate, true);
      document.removeEventListener("pointerdown", outside);
      document.removeEventListener("keydown", escape);
      observer?.disconnect();
    };
  }, [open, locate, dismiss]);
  useEffect(() => clearClose, [clearClose]);
  return <span className="hover-help" onMouseEnter={() => { hovered.current = true; show(); }} onMouseLeave={() => { hovered.current = false; leave(); }}>
    <button ref={trigger} type="button" className={triggerClassName ?? "help-icon"} aria-label={title} aria-describedby={open && !interactive ? id : undefined}
      aria-haspopup={interactive ? "dialog" : undefined} aria-expanded={interactive ? open : undefined} aria-controls={open && interactive ? id : undefined}
      onFocus={() => { focused.current = true; show(); }} onBlur={() => { focused.current = false; leave(); }} onClick={show}
      onKeyDown={(event) => {
        if (open && event.key === "Tab" && !event.shiftKey) {
          const control = bubble.current?.querySelector<HTMLElement>("button, a[href], input, select, textarea, summary, [tabindex='0']");
          if (control) { event.preventDefault(); control.focus(); }
        }
      }}>{triggerContent ?? <Icon name="info" size={14} />}</button>
    {open && typeof document !== "undefined" ? createPortal(<div ref={bubble} id={id} role={interactive ? "dialog" : "tooltip"} aria-label={interactive ? title : undefined} className={["hover-help-bubble", bubbleClassName].filter(Boolean).join(" ")}
      style={{ left: position?.left ?? 8, top: position?.top ?? 8, visibility: position ? "visible" : "hidden" }}
      onFocus={() => { focused.current = true; clearClose(); }} onBlur={(event) => { if (!event.currentTarget.contains(event.relatedTarget as Node | null)) { focused.current = false; leave(); } }}
      onMouseEnter={() => { hovered.current = true; clearClose(); }} onMouseLeave={() => { hovered.current = false; leave(); }}>{children}</div>, document.body) : null}
  </span>;
}
