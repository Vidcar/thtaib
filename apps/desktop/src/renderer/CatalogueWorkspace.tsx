import { useId, type ReactNode } from "react";
import { Icon, type IconName } from "./Icon";
import "./CatalogueWorkspace.css";

export interface CatalogueItem {
  id: string;
  name: string;
  detail?: ReactNode;
  status?: ReactNode;
  icon?: IconName;
  selectorLabel?: string;
}

/** The catalogue owns navigation only; each editor keeps its requested draft. */
export function CatalogueWorkspace({ title, search, onSearch, searchPlaceholder, items, selectedId, onSelect, actions, children, emptyLabel = "No matches", loading = false }: {
  title: string; search: string; onSearch: (value: string) => void; searchPlaceholder?: string;
  items: CatalogueItem[]; selectedId: string; onSelect: (id: string) => void;
  actions?: ReactNode; children: ReactNode; emptyLabel?: string; loading?: boolean;
}) {
  const id = useId();
  const selectionVisible = items.some(item => item.id === selectedId);
  return <div className="catalogue-workspace">
    <aside className="catalogue-navigation" aria-label={title}>
      <div className="catalogue-search"><Icon name="search" /><input aria-label={`Search ${title.toLowerCase()}`} type="search" value={search} placeholder={searchPlaceholder ?? `Search ${title.toLowerCase()}`} onChange={event => onSearch(event.target.value)} /></div>
      {actions ? <div className="catalogue-actions">{actions}</div> : null}
      <div className="catalogue-narrow"><label htmlFor={id}>{title}</label><select id={id} value={selectionVisible ? selectedId : ""} onChange={event => onSelect(event.target.value)}>
        {!selectionVisible ? <option value="">{loading ? "Loading…" : items.length ? "Choose a record" : emptyLabel}</option> : null}
        {items.map(item => <option key={item.id} value={item.id}>{item.selectorLabel ?? item.name}</option>)}
      </select></div>
      <div className="catalogue-list">
        {loading ? <p className="hint" role="status">Loading…</p> : items.length ? items.map(item => <button type="button" className="catalogue-row" key={item.id} aria-current={selectedId === item.id ? "true" : undefined} onClick={() => onSelect(item.id)}>
          {item.icon ? <Icon name={item.icon} /> : null}<span className="catalogue-row-text"><strong>{item.name}</strong>{item.detail ? <small>{item.detail}</small> : null}{item.status ? <small className="catalogue-row-status">{item.status}</small> : null}</span>
        </button>) : <p className="hint" role="status">{emptyLabel}</p>}
      </div>
    </aside>
    <div className="catalogue-editor">{children}</div>
  </div>;
}
