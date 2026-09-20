import { useId, type ReactNode } from "react";

export function Help({ label, flag, children }: { label: string; flag?: string; children: ReactNode }) {
  const id = useId();
  return <span className="setting-help"><button type="button" className="help-button" aria-label={`About ${label}`} aria-describedby={id}>i</button><span id={id} role="tooltip" className="help-popover">{children}{flag ? <code>{flag}</code> : null}</span></span>;
}

export function tokenLabel(value: number): string {
  return value >= 1024 && value % 1024 === 0 ? `${value / 1024}k` : value.toLocaleString();
}

export function Choice({ id, label, help, flag, value, options, onChange, custom = true, min = 0, max, step = 1, disabled = false }: {
  id: string; label: string; help: string; flag?: string; value: string;
  options: Array<{ value: string; label: string }>; onChange: (value: string) => void;
  custom?: boolean; min?: number; max?: number; step?: number; disabled?: boolean;
}) {
  const isCustom = value === "custom" || !options.some(option => option.value === value);
  return <div className="model-field"><div className="setting-title"><label htmlFor={id}>{label}</label><Help label={label} flag={flag}>{help}</Help></div>
    <select id={id} value={isCustom ? "custom" : value} onChange={event => onChange(event.target.value)} disabled={disabled}>
      {options.map(option => <option key={option.value} value={option.value}>{option.label}</option>)}
      {custom ? <option value="custom">Custom…</option> : null}
    </select>
    {custom && isCustom ? <input aria-label={`Custom ${label.toLowerCase()}`} type="number" min={min} max={max} step={step} required disabled={disabled} value={value === "custom" ? "" : value} onChange={event => onChange(event.target.value || "custom")} /> : null}
  </div>;
}

export function numberChoices(values: number[], unit = ""): Array<{ value: string; label: string }> {
  return values.map(value => ({ value: String(value), label: `${value.toLocaleString()}${unit}` }));
}
