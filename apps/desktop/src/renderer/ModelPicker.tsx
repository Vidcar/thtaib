import { useEffect, useRef, useState } from "react";
import { formatBytes } from "./display";
import { presentVariant } from "./modelVariantPresentation";
import type { ModelBundle } from "./types";

function modelFileLabel(bundle: ModelBundle): string {
  const primary = bundle.files.find(file => file.path === bundle.primary_path)
    ?? bundle.files.find(file => file.role === "primary_weights")
    ?? bundle.shards?.[0];
  const name = (primary?.name || bundle.primary_path || "").split(/[\\/]/).at(-1) ?? "";
  if (!name || !/\.gguf$/i.test(name)) return bundle.quantization ?? "GGUF";
  const parsed = presentVariant({ name, files: [name], complete: true });
  return `${parsed.quant === "Unknown" ? bundle.quantization ?? "GGUF" : parsed.quant} · ${parsed.flavour} · ${name}`;
}

export function ModelPicker({ bundles, selectedId, onSelect, dirtyIds }: {
  bundles: ModelBundle[]; selectedId: string; onSelect: (id: string) => void; dirtyIds: ReadonlySet<string>;
}) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  const root = useRef<HTMLDivElement>(null);
  const search = useRef<HTMLInputElement>(null);
  const selected = bundles.find(bundle => bundle.id === selectedId);
  const filtered = bundles.filter(bundle => `${bundle.display_name} ${modelFileLabel(bundle)}`.toLowerCase().includes(query.trim().toLowerCase()));

  useEffect(() => {
    if (!open) return;
    search.current?.focus();
    const closeOutside = (event: PointerEvent) => { if (!root.current?.contains(event.target as Node)) setOpen(false); };
    document.addEventListener("pointerdown", closeOutside);
    return () => document.removeEventListener("pointerdown", closeOutside);
  }, [open]);
  function select(id: string) { onSelect(id); setOpen(false); setQuery(""); setActive(0); }
  function openPicker() { setOpen(true); setActive(Math.max(0, bundles.findIndex(bundle => bundle.id === selectedId))); }

  return <div className="model-picker" role="group" aria-label="Selected model" ref={root}>
    <span className="model-picker-label">Model</span>
    <button type="button" className="model-picker-trigger" aria-label={`Choose model, ${selected ? `${selected.display_name}, ${modelFileLabel(selected)}` : "none selected"}`} aria-expanded={open} aria-haspopup="dialog" onClick={() => open ? setOpen(false) : openPicker()} onKeyDown={event => {
      if (!open && ["ArrowDown", "ArrowUp"].includes(event.key)) { event.preventDefault(); openPicker(); }
    }}>
      <span className="model-picker-current"><strong title={selected?.display_name}>{selected?.display_name ?? "Choose a model"}</strong>{selected ? <small title={modelFileLabel(selected)}>{modelFileLabel(selected)}</small> : null}</span>
      {selected && dirtyIds.has(selected.id) ? <span className="model-picker-unsaved">Unsaved</span> : null}
      <span aria-hidden="true" className="model-picker-chevron">⌄</span>
    </button>
    {open ? <div className="model-picker-popover" role="dialog" aria-label="Choose a model">
      <input ref={search} type="search" role="combobox" aria-label="Search installed models" aria-expanded="true" aria-controls="model-picker-list" aria-activedescendant={filtered[active] ? `model-picker-option-${filtered[active].id}` : undefined} value={query} placeholder="Search installed models" onChange={event => { setQuery(event.target.value); setActive(0); }} onKeyDown={event => {
        if (event.key === "Escape") { event.preventDefault(); setOpen(false); }
        else if (event.key === "ArrowDown") { event.preventDefault(); setActive(index => Math.min(filtered.length - 1, index + 1)); }
        else if (event.key === "ArrowUp") { event.preventDefault(); setActive(index => Math.max(0, index - 1)); }
        else if (event.key === "Enter" && filtered[active]) { event.preventDefault(); select(filtered[active].id); }
      }} />
      <ul id="model-picker-list" role="listbox" aria-label="Installed models">
        {filtered.map((bundle, index) => <li id={`model-picker-option-${bundle.id}`} role="option" aria-selected={bundle.id === selectedId} className={index === active ? "active" : ""} key={bundle.id} onPointerMove={() => setActive(index)} onClick={() => select(bundle.id)}>
          <strong>{bundle.display_name}</strong>
          <span>{modelFileLabel(bundle)} · {formatBytes(bundle.files.reduce((total, file) => total + file.size_bytes, 0))}{!bundle.disk_matches ? " · Check files" : ""}{dirtyIds.has(bundle.id) ? " · Unsaved" : ""}</span>
        </li>)}
        {!filtered.length ? <li className="model-picker-empty">No models match “{query}”.</li> : null}
      </ul>
    </div> : null}
  </div>;
}
