import { useCallback, useEffect, useId, useLayoutEffect, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { Icon } from "./Icon";

/** Help is available to pointer, keyboard and touch without occupying the page. */
export function HoverHelp({ title = "About this setting", children, triggerContent, triggerClassName, bubbleClassName, placement = "below", interactive = false, mode = "hover", label, held = null, onActivate, editRunId, clearanceSelector, visibleFocusOnly = false }: {
  title?: string;
  children: ReactNode;
  triggerContent?: ReactNode;
  triggerClassName?: string;
  bubbleClassName?: string;
  placement?: "above" | "below";
  interactive?: boolean;
  mode?: "hover" | "click";
  label?: string;
  held?: string | null;
  onActivate?: () => void;
  editRunId?: string;
  clearanceSelector?: string;
  visibleFocusOnly?: boolean;
}) {
  const id = useId();
  const trigger = useRef<HTMLButtonElement>(null);
  const bubble = useRef<HTMLDivElement>(null);
  const closeTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const hovered = useRef(false);
  const focused = useRef(false);
  const [open, setOpen] = useState(false);
  const action = onActivate !== undefined;
  const suppressed = action && !held;
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
    const headerBottom = clearanceSelector && typeof document !== "undefined" && typeof document.querySelector === "function"
      ? document.querySelector(clearanceSelector)?.getBoundingClientRect().bottom
      : undefined;
    const floor = Math.max(8, headerBottom ?? 8);
    const top = placement === "above" && above >= floor ? above : below + tip.height <= window.innerHeight - 8 ? below : above;
    const next = {
      left: Math.max(8, Math.min(anchor.left, window.innerWidth - tip.width - 8)),
      top: Math.max(8, Math.min(top, window.innerHeight - tip.height - 8)),
    };
    setPosition(current => current?.left === next.left && current.top === next.top ? current : next);
  }, [placement, clearanceSelector]);
  useLayoutEffect(() => {
    if (!open) return;
    const tip = bubble.current;
    // A modal dialog paints above document.body. A manual popover joins the top layer so the bubble stays visible.
    if (tip && tip.getAttribute?.("popover") === "manual" && typeof tip.showPopover === "function" && !tip.matches?.(":popover-open")) {
      try { tip.showPopover(); } catch { /* The portaled bubble remains when the popover API is unavailable. */ }
    }
    locate();
  }, [open, children, locate]);
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
  return <span className="hover-help" onMouseEnter={() => { if (mode === "hover" && !suppressed) { hovered.current = true; show(); } }} onMouseLeave={() => { if (mode === "hover") { hovered.current = false; leave(); } }}>
    <button ref={trigger} type="button" className={triggerClassName ?? "help-icon"} aria-label={label ?? title} title={action ? held ?? label : undefined} aria-disabled={action && held ? true : undefined} data-edit-run={editRunId} aria-describedby={open && !interactive ? id : undefined}
      aria-haspopup={interactive ? "dialog" : undefined} aria-expanded={interactive ? open : undefined} aria-controls={open && interactive ? id : undefined}
      onFocus={(event) => { focused.current = true; if (mode !== "hover" || suppressed) return; if (visibleFocusOnly && !event?.currentTarget?.matches?.(":focus-visible")) return; show(); }} onBlur={() => { focused.current = false; if (mode === "hover") leave(); }} onClick={(event) => { if (action) { if (!held && event?.currentTarget?.getAttribute?.("aria-disabled") !== "true") onActivate(); return; } if (mode === "click" && open) dismiss(); else show(); }}
      onKeyDown={(event) => {
        if (action && (held || event.currentTarget?.getAttribute?.("aria-disabled") === "true") && (event.key === "Enter" || event.key === " ")) { event.preventDefault(); event.stopPropagation(); return; }
        if (open && event.key === "Tab" && !event.shiftKey) {
          const control = bubble.current?.querySelector<HTMLElement>("button:not(:disabled), a[href], input:not(:disabled), select:not(:disabled), textarea:not(:disabled), summary, [tabindex='0']");
          if (control) { event.preventDefault(); control.focus(); }
        }
      }}>{triggerContent ?? <Icon name="info" size={14} />}</button>
    {open && typeof document !== "undefined" ? createPortal(<div ref={bubble} id={id} role={interactive ? "dialog" : "tooltip"} aria-label={interactive ? title : undefined} popover={trigger.current?.closest?.("dialog") ? "manual" : undefined} className={["hover-help-bubble", bubbleClassName].filter(Boolean).join(" ")}
      style={{ left: position?.left ?? 8, top: position?.top ?? 8, right: "auto", bottom: "auto", margin: 0, visibility: position ? "visible" : "hidden" }}
      onFocus={() => { focused.current = true; clearClose(); }} onBlur={(event) => { if (!event.currentTarget.contains(event.relatedTarget as Node | null)) { focused.current = false; leave(); } }}
      onMouseEnter={() => { hovered.current = true; clearClose(); }} onMouseLeave={() => { hovered.current = false; leave(); }}>{children}</div>, document.body) : null}
  </span>;
}
