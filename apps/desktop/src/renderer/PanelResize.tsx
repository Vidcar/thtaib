import { useEffect, useRef, useState } from "react";

export function usePanelWidth(key: string, initial: number, min: number, max: number) {
  const [width, setWidth] = useState(() => {
    try { const saved = Number(window.localStorage?.getItem(key)); return saved > 0 ? Math.max(min, Math.min(max, saved)) : initial; } catch { return initial; }
  });
  const update = (value: number) => setWidth(Math.max(min, Math.min(max, value)));
  useEffect(() => { try { window.localStorage?.setItem(key, String(width)); } catch { /* Layout persistence is optional. */ } }, [key, width]);
  return [width, update] as const;
}

export function PanelResize({ label, width, onResize, min = 190, max = 380, reset = 240, reverse = false }: {
  label: string; width: number; onResize: (width: number) => void; min?: number; max?: number; reset?: number; reverse?: boolean;
}) {
  const drag = useRef<{ x: number; width: number } | null>(null);
  return <div className="panel-resize" role="separator" aria-label={label} aria-orientation="vertical" tabIndex={0}
    aria-valuenow={Math.round(width)} aria-valuemin={min} aria-valuemax={max} title="Drag to resize · Double-click to reset"
    onDoubleClick={() => onResize(reset)}
    onKeyDown={event => {
      if (event.key === "ArrowLeft" || event.key === "ArrowRight") { event.preventDefault(); onResize(width + (event.key === "ArrowLeft" ? -16 : 16) * (reverse ? -1 : 1)); }
      if (event.key === "Home" || event.key === "End") { event.preventDefault(); onResize(event.key === "Home" ? min : max); }
    }}
    onPointerDown={event => { if (event.button !== 0) return; event.preventDefault(); drag.current = { x: event.clientX, width }; event.currentTarget.setPointerCapture(event.pointerId); }}
    onPointerMove={event => { if (drag.current) onResize(drag.current.width + (event.clientX - drag.current.x) * (reverse ? -1 : 1)); }}
    onPointerUp={event => { drag.current = null; if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId); }}
    onPointerCancel={() => { drag.current = null; }} onLostPointerCapture={() => { drag.current = null; }} />;
}
