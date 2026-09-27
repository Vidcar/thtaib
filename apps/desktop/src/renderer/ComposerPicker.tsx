import { Icon } from "./Icon";

export interface ComposerChoice { id: string; kind: "memory" | "instruction" | "skill" | "shortcut" | "asset" | "project"; name: string; description?: string; unavailable?: string; repairTo?: "agents" | "knowledge" }
export function composerMatches(choices: ComposerChoice[], query: string) {
  const term = query.trim().toLocaleLowerCase();
  return choices.filter(item => !term || (item.name + " " + (item.description ?? "")).toLocaleLowerCase().includes(term));
}
export function ComposerPicker({ kind, query, choices, highlighted, onQuery, onHighlight, onSelect, onClose, onRepair, autocomplete = false }: {
  kind: "context" | "skills"; query: string; choices: ComposerChoice[]; highlighted: number;
  onQuery: (query: string) => void; onHighlight: (index: number) => void; onSelect: (choice: ComposerChoice) => void;
  onClose: () => void; onRepair: (choice: ComposerChoice) => void; autocomplete?: boolean;
}) {
  return <section className="composer-picker" aria-label={kind === "context" ? "Add context" : "Skills and actions"}>
    <div className="composer-picker-head">{autocomplete ? <span>{kind === "context" ? "Add context" : "Skills & actions"}</span> : <input aria-label={kind === "context" ? "Search context" : "Search skills and actions"} placeholder="Search" autoFocus value={query} onChange={event => onQuery(event.target.value)} onKeyDown={event => {
      if (event.key === "ArrowDown" || event.key === "ArrowUp") { event.preventDefault(); onHighlight(Math.max(0, Math.min(choices.length - 1, highlighted + (event.key === "ArrowDown" ? 1 : -1)))); }
      else if (event.key === "Enter" && choices[highlighted]) { event.preventDefault(); onSelect(choices[highlighted]); }
      else if (event.key === "Escape") { event.preventDefault(); onClose(); }
    }} />}<button type="button" className="icon-button" aria-label="Close picker" onClick={onClose}><Icon name="close" size={14} /></button></div>
    <div id="composer-suggestions" className="composer-picker-list" role="listbox" aria-label="Suggestions">
      {choices.map((item, index) => <button id={"composer-option-" + index} key={item.kind + ":" + item.id} type="button" role="option" aria-selected={highlighted === index} aria-disabled={Boolean(item.unavailable)} className={highlighted === index ? "is-highlighted" : ""} onPointerMove={() => onHighlight(index)} onClick={() => item.unavailable ? onRepair(item) : onSelect(item)}><span>{item.name}</span><small>{item.unavailable ?? item.description ?? item.kind}</small></button>)}
      {!choices.length ? <p className="hint">No matches</p> : null}
    </div>
  </section>;
}
