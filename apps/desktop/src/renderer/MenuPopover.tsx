import { useEffect, useId, useLayoutEffect, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";

/** An overlay never contributes to the size of the row that opens it. */
export function MenuPopover(props: {
  label: string;
  trigger: ReactNode;
  children: ReactNode | ((close: () => void) => ReactNode);
  className?: string;
  panelClassName?: string;
  align?: "start" | "end";
  placement?: "above" | "below";
  disabled?: boolean;
  role?: "dialog" | "menu" | "group";
}) {
  const id = useId();
  const trigger = useRef<HTMLButtonElement>(null);
  const panel = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState(false);
  const [position, setPosition] = useState({ left: 8, top: 8, ready: false });
  const close = () => { setOpen(false); trigger.current?.focus({ preventScroll: true }); };

  useLayoutEffect(() => {
    if (!open || typeof window === "undefined") return;
    const place = () => {
      const anchor = trigger.current?.getBoundingClientRect();
      const box = panel.current?.getBoundingClientRect();
      if (!anchor || !box) return;
      const gap = 8;
      const above = anchor.top - box.height - gap;
      const below = anchor.bottom + gap;
      const preferAbove = props.placement !== "below";
      const top = preferAbove ? (above >= gap ? above : below) : (below + box.height <= window.innerHeight - gap ? below : above);
      setPosition({
        left: Math.max(gap, Math.min(props.align === "end" ? anchor.right - box.width : anchor.left, window.innerWidth - box.width - gap)),
        top: Math.max(gap, Math.min(top, window.innerHeight - box.height - gap)),
        ready: true,
      });
    };
    place();
    window.addEventListener("resize", place);
    window.addEventListener("scroll", place, true);
    const observer = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(place);
    if (panel.current) observer?.observe(panel.current);
    panel.current?.querySelector<HTMLElement>('button:not(:disabled), input:not(:disabled), select:not(:disabled), [tabindex="0"]')?.focus({ preventScroll: true });
    return () => { window.removeEventListener("resize", place); window.removeEventListener("scroll", place, true); observer?.disconnect(); };
  }, [open, props.align, props.placement]);

  useEffect(() => {
    if (typeof document === "undefined") return;
    const outside = (event: PointerEvent) => {
      const target = event.target as Node;
      if (open && !panel.current?.contains(target) && !trigger.current?.contains(target)) setOpen(false);
    };
    const escape = (event: KeyboardEvent) => {
      if (open && event.key === "Escape") { event.preventDefault(); close(); }
    };
    const other = (event: Event) => { if ((event as CustomEvent<string>).detail !== id) setOpen(false); };
    const navigation = () => setOpen(false);
    const focusOutside = (event: FocusEvent) => { if (open && !panel.current?.contains(event.target as Node) && !trigger.current?.contains(event.target as Node)) setOpen(false); };
    document.addEventListener("pointerdown", outside);
    document.addEventListener("keydown", escape);
    document.addEventListener("workbench:popover-open", other);
    document.addEventListener("workbench:navigation", navigation);
    document.addEventListener("focusin", focusOutside);
    return () => { document.removeEventListener("pointerdown", outside); document.removeEventListener("keydown", escape); document.removeEventListener("workbench:popover-open", other); document.removeEventListener("workbench:navigation", navigation); document.removeEventListener("focusin", focusOutside); };
  }, [open, id]);

  const contents = typeof props.children === "function" ? props.children(close) : props.children;
  const overlay = <div ref={panel} id={id} hidden={!open} role={props.role ?? "dialog"} aria-label={props.label} className={`menu-popover-panel ${props.panelClassName ?? ""}`} style={{ left: position.left, top: position.top, visibility: position.ready ? "visible" : "hidden" }}>{contents}</div>;
  return <span className={`menu-popover-anchor ${props.className ?? ""}`}>
    <button ref={trigger} type="button" className="menu-popover-trigger" aria-label={props.label} aria-haspopup={props.role === "menu" ? "menu" : "dialog"} aria-expanded={open} aria-controls={open ? id : undefined} disabled={props.disabled} onClick={() => {
      if (!open) { setPosition(current => ({ ...current, ready: false })); if (typeof document !== "undefined") document.dispatchEvent(new CustomEvent("workbench:popover-open", { detail: id })); }
      setOpen(current => !current);
    }}>{props.trigger}</button>
    {typeof document !== "undefined" ? createPortal(overlay, document.body) : <span hidden>{contents}</span>}
  </span>;
}
