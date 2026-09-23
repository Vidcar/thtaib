import { type ReactNode } from "react";
import { HoverHelp } from "./HoverHelp";
import { CompactSwitch, CompactSlider } from "./CompactControls";

export function Help({ label, flag, children }: { label: string; flag?: string; children: ReactNode }) {
  return <HoverHelp title={`About ${label}`}>{children}{flag ? <code>{flag}</code> : null}</HoverHelp>;
}

export function tokenLabel(value: number): string {
  return value >= 1024 && value % 1024 === 0 ? `${value / 1024}k` : value.toLocaleString();
}

export function Choice({ id, label, help, flag, value, options, onChange, custom = true, min = 0, max, step = 1, disabled = false }: {
  id: string; label: string; help: string; flag?: string; value: string;
  options: Array<{ value: string; label: string }>; onChange: (value: string) => void;
  custom?: boolean; min?: number; max?: number; step?: number; disabled?: boolean;
}) {
  const binary = options.length === 2 && options.every(option => ["on", "off"].includes(option.value)) && options.every(option => ["On", "Off"].includes(option.label));
  if (binary) return <div className="model-field"><CompactSwitch label={label} description={help} checked={value === "on"} disabled={disabled} onChange={checked => onChange(checked ? "on" : "off")} /></div>;
  const numeric = options.filter(option => option.value !== "" && Number.isFinite(Number(option.value)) && Number(option.value) >= min).map(option => Number(option.value));
  if (custom && numeric.length >= 3 && value !== "custom" && value !== "" && Number.isFinite(Number(value))) {
    const automatic = options.filter(option => option.value === "" || !Number.isFinite(Number(option.value)));
    return <div className="model-field"><CompactSlider label={label} description={help} value={Number(value)} values={numeric} disabled={disabled} formatValue={number => label.toLowerCase().includes("context") ? `${tokenLabel(number)} tokens` : number.toLocaleString()} onChange={number => onChange(String(number))} /><div className="actions"><input aria-label={`Exact ${label.toLowerCase()}`} type="number" min={min} max={max} step={step} disabled={disabled} value={value} onChange={event => onChange(event.target.value || "custom")} />{automatic.map(option => <button key={option.value} type="button" className="quiet-button" disabled={disabled} onClick={() => onChange(option.value)}>{option.label}</button>)}</div></div>;
  }
  const isCustom = value === "custom" || !options.some(option => option.value === value);
  return <div className="model-field"><div className="setting-title"><label htmlFor={id}>{label}</label><Help label={label} flag={flag}>{help}</Help></div>
    <select id={id} value={isCustom ? "custom" : value} onChange={event => onChange(event.target.value)} disabled={disabled}>
      {!custom && isCustom ? <option value="custom">{value} · saved setting</option> : null}
      {options.map(option => <option key={option.value} value={option.value}>{option.label}</option>)}
      {custom ? <option value="custom">Custom…</option> : null}
    </select>
    {custom && isCustom ? <input aria-label={`Custom ${label.toLowerCase()}`} type="number" min={min} max={max} step={step} required disabled={disabled} value={value === "custom" ? "" : value} onChange={event => onChange(event.target.value || "custom")} /> : null}
  </div>;
}

export function numberChoices(values: number[], unit = ""): Array<{ value: string; label: string }> {
  return values.map(value => ({ value: String(value), label: `${value.toLocaleString()}${unit}` }));
}
