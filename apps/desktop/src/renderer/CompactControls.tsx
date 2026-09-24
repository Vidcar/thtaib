import { useId, type CSSProperties, type ReactNode } from "react";
import { HoverHelp } from "./HoverHelp";
import "./CompactControls.css";

function aboutTitle(label: ReactNode, helpTitle?: string) {
  return helpTitle ?? (typeof label === "string" ? `About ${label.toLowerCase()}` : "About this setting");
}

export function SettingSection({ title, description, actions, children, className }: {
  title: string; description?: ReactNode; actions?: ReactNode; children: ReactNode; className?: string;
}) {
  return <section className={className ? `setting-section ${className}` : "setting-section"}>
    <header className="setting-section-head"><div><h3>{title}</h3>{description ? <p>{description}</p> : null}</div>{actions ? <div className="setting-section-actions">{actions}</div> : null}</header>
    <div className="setting-rows">{children}</div>
  </section>;
}

export function SettingRow({ label, labelId, htmlFor, help, helpTitle, provenance, onReset, resetLabel = "Reset to inherited", hint, inline = false, stacked = false, className, children }: {
  label: ReactNode; labelId?: string; htmlFor?: string; help?: ReactNode; helpTitle?: string; provenance?: ReactNode;
  onReset?: () => void; resetLabel?: string; hint?: ReactNode; inline?: boolean; stacked?: boolean; className?: string; children: ReactNode;
}) {
  const classes = ["setting-row", inline ? "setting-row-inline" : "", stacked ? "setting-row-stacked" : "", className ?? ""].filter(Boolean).join(" ");
  return <div className={classes}>
    <div className="setting-row-label">
      <div className="setting-row-title">
        {htmlFor ? <label id={labelId} htmlFor={htmlFor}>{label}</label> : <span id={labelId} className="setting-row-name">{label}</span>}
        {help ? <HoverHelp title={aboutTitle(label, helpTitle)}>{help}</HoverHelp> : null}
        {onReset ? <button type="button" className="text-button setting-reset" onClick={onReset}>{resetLabel}</button> : null}
      </div>
      {provenance ? <small className="control-provenance">{provenance}</small> : null}
    </div>
    <div className="setting-row-control">
      {children}
      {hint ? <small className="setting-row-hint">{hint}</small> : null}
    </div>
  </div>;
}

export function CompactSwitch(props: { label: string; checked: boolean; onChange: (checked: boolean) => void; disabled?: boolean; description?: ReactNode; meta?: ReactNode; bare?: boolean; hint?: ReactNode }) {
  const control = <button type="button" className="compact-switch" role="switch" aria-label={props.label} aria-checked={props.checked} disabled={props.disabled} onClick={() => props.onChange(!props.checked)}><span /></button>;
  if (props.bare) return control;
  return <SettingRow inline label={props.label} help={props.description} provenance={props.meta} hint={props.hint}>{control}</SettingRow>;
}

export function SegmentedChoice({ id: groupId, label, value, options, onChange, disabled = false, description, meta, bare = false, onReset, hint, inheritedValue }: {
  id?: string; label: string; value: string; options: Array<{ value: string; label: string; disabled?: boolean }>;
  onChange: (value: string) => void; disabled?: boolean; description?: ReactNode; meta?: ReactNode; bare?: boolean; onReset?: () => void; hint?: ReactNode;
  /** Marks the option an empty value resolves to, without selecting it. */
  inheritedValue?: string;
}) {
  const id = useId();
  const group = <div id={groupId} className="segmented-options" role="radiogroup" aria-label={bare ? label : undefined} aria-labelledby={bare ? undefined : `${id}-label`} aria-disabled={disabled || undefined} style={{ "--segments": options.length } as CSSProperties}>
    {options.map(option => <label key={option.value} data-inherited={value === "" && option.value === inheritedValue ? "" : undefined}><input type="radio" name={id} value={option.value} checked={value === option.value} disabled={disabled || option.disabled} onChange={() => onChange(option.value)} /><span>{option.label}</span></label>)}
  </div>;
  if (bare) return group;
  return <SettingRow className="segmented-setting" label={label} labelId={`${id}-label`} help={description} provenance={meta} onReset={onReset} hint={hint}>{group}</SettingRow>;
}

function fillPercent(value: number, min: number, max: number) {
  if (!(max > min)) return "0%";
  return `${Math.min(100, Math.max(0, ((value - min) / (max - min)) * 100))}%`;
}

export function CompactSlider(props: { hideHeading?: boolean; label: string; value: number; values: number[]; onChange: (value: number) => void; formatValue?: (value: number) => string; disabled?: boolean; description?: ReactNode; inherited?: boolean }) {
  const id = useId();
  const values = [...new Set([...props.values, props.value])].sort((a, b) => a - b);
  const format = props.formatValue ?? ((value: number) => value.toLocaleString());
  const index = values.indexOf(props.value);
  const max = Math.max(0, values.length - 1);
  return <div className="compact-slider">
    <div className={props.hideHeading ? "compact-slider-heading visually-hidden" : "compact-slider-heading"}><label htmlFor={id}>{props.label}</label>{props.description ? <HoverHelp title={`About ${props.label.toLowerCase()}`}>{props.description}</HoverHelp> : null}<output htmlFor={id}>{format(props.value)}</output></div>
    <input id={id} type="range" min={0} max={max} step={1} list={`${id}-ticks`} value={index} aria-label={props.label} aria-valuetext={format(props.value)} data-inherited={props.inherited || undefined} style={{ "--range-fill": fillPercent(index, 0, max) } as CSSProperties} disabled={props.disabled || values.length < 2} onChange={event => props.onChange(values[Number(event.target.value)] ?? props.value)} />
    <datalist id={`${id}-ticks`}>{values.map((value, position) => <option key={value} value={position} label={format(value)} />)}</datalist>
    <div className="compact-slider-limits" aria-hidden="true"><span>{format(values[0] ?? props.value)}</span><span>{format(values.at(-1) ?? props.value)}</span></div>
  </div>;
}

/** Continuous slider plus exact number. `null` means inherited: the slider shows the resolved value muted and the number stays empty. */
export function SliderField({ id, label, value, resolved, min, max, step, unit, onChange, disabled }: {
  id?: string; label: string; value: number | null; resolved?: number | null; min: number; max: number; step: number; unit?: string;
  onChange: (value: number | null) => void; disabled?: boolean;
}) {
  const shown = value ?? resolved ?? min;
  const clamped = Math.min(max, Math.max(min, shown));
  return <div className="slider-field">
    <input type="range" aria-label={label} min={min} max={max} step={step} value={clamped} disabled={disabled} data-inherited={value === null || undefined} style={{ "--range-fill": fillPercent(clamped, min, max) } as CSSProperties} onChange={event => onChange(Number(event.target.value))} />
    <NumberField id={id} label={label} value={value} placeholder={resolved == null ? "" : String(resolved)} min={min} max={max} step={step} unit={unit} disabled={disabled} onChange={onChange} />
  </div>;
}

export function NumberField({ id, label, value, placeholder, min, max, step, unit, onChange, disabled, wide = false }: {
  id?: string; label: string; value: number | string | null; placeholder?: string; min?: number; max?: number; step?: number | "any"; unit?: string;
  onChange: (value: number | null) => void; disabled?: boolean; wide?: boolean;
}) {
  return <span className={wide ? "number-field number-field-wide" : "number-field"}>
    <input id={id} type="number" aria-label={id ? undefined : label} min={min} max={max} step={step} value={value ?? ""} placeholder={placeholder} disabled={disabled} onChange={event => onChange(event.target.value === "" ? null : Number(event.target.value))} />
    {unit ? <span className="field-unit">{unit}</span> : null}
  </span>;
}
