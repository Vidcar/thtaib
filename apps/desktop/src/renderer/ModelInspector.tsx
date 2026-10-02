import { useEffect, useLayoutEffect, useRef, useState, type ReactNode } from "react";
import { Icon } from "./Icon";
import "./ModelInspector.css";

export type ModelInspectorView = "presets" | "checks" | "memory" | "runtime" | "card" | "files" | "setup";
export type ModelInspectorConnection = { view: ModelInspectorView | null; target: HTMLElement | null; open: (view: ModelInspectorView) => void; close: () => void };
const titles: Record<ModelInspectorView, string> = { presets: "Model card", checks: "Checked setup", memory: "Memory details", runtime: "Loaded model", card: "Read model card", files: "Files & model information", setup: "Manage saved setup" };

export function ModelInspector({ view, onClose, onTarget, content, children }: {
  view: ModelInspectorView | null; onClose: () => void; onTarget: (target: HTMLDivElement | null) => void; content?: ReactNode; children: ReactNode;
}) {
  const frame = useRef<HTMLDivElement>(null), panel = useRef<HTMLElement>(null), trigger = useRef<HTMLElement | null>(null);
  const [docked, setDocked] = useState(false);
  useLayoutEffect(() => {
    const node = frame.current;
    if (!node) return;
    const measure = () => setDocked(node.getBoundingClientRect().width >= 1164);
    measure();
    if (typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(measure); observer.observe(node);
    return () => observer.disconnect();
  }, []);
  useEffect(() => {
    if (!view || typeof document === "undefined") return;
    trigger.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const panelNode = panel.current;
    if (!docked) panel.current?.querySelector<HTMLButtonElement>("button")?.focus({ preventScroll: true });
    const key = (event: KeyboardEvent) => {
      if (event.key === "Escape") { event.preventDefault(); onClose(); }
      if (event.key !== "Tab" || docked) return;
      const controls = Array.from(panel.current?.querySelectorAll<HTMLElement>('button:not(:disabled),a[href],input:not(:disabled),select:not(:disabled),textarea:not(:disabled),summary,[tabindex="0"]') ?? []).filter(node => node.getClientRects().length > 0);
      const first = controls[0], last = controls.at(-1);
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
    };
    document.addEventListener("keydown", key);
    return () => {
      document.removeEventListener("keydown", key);
      const focused = document.activeElement;
      if (focused === document.body || focused === trigger.current || panelNode?.contains(focused)) trigger.current?.isConnected && trigger.current.focus({ preventScroll: true });
    };
  }, [Boolean(view), docked, onClose]);
  useLayoutEffect(() => {
    if (view && typeof document !== "undefined" && document.activeElement instanceof HTMLElement
      && frame.current?.querySelector(".model-editor-main")?.contains(document.activeElement)) trigger.current = document.activeElement;
  }, [view]);
  return <div ref={frame} className="model-editor-layout" data-panel-open={Boolean(view)} data-panel-docked={docked}>
    <div className="model-editor-main" inert={view && !docked ? true : undefined}>{children}</div>
    {view && !docked ? <div className="model-inspector-backdrop" onClick={onClose} /> : null}
    {view ? <aside ref={panel} className="model-inspector" role={docked ? "complementary" : "dialog"} aria-modal={!docked || undefined} aria-labelledby="model-inspector-title">
      <header><h3 id="model-inspector-title">{titles[view]}</h3><button type="button" className="icon-button" aria-label="Close model details" title="Close model details" onClick={onClose}><Icon name="close" /></button></header>
      <div ref={onTarget} className="model-inspector-body">{content}</div>
    </aside> : null}
  </div>;
}
