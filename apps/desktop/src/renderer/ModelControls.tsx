import { type CSSProperties, type ReactNode } from "react";
import { HoverHelp } from "./HoverHelp";
import { SegmentedChoice } from "./CompactControls";

export function Help({ label, flag, children }: { label: string; flag?: string; children: ReactNode }) {
  return <HoverHelp title={`About ${label}`}>{children}{flag ? <code>{flag}</code> : null}</HoverHelp>;
}

export function tokenLabel(value: number): string {
  return value >= 1024 && value % 1024 === 0 ? `${value / 1024}k` : value.toLocaleString();
}

type Option = { value: string; label: string };
const SEGMENT_LABEL_BUDGET = 30;

/** The control half of a launch setting row. `""` always means inherited. */
export function ChoiceControl({ id, label, value, options, onChange, custom = true, min = 0, max, step = 1, disabled = false, resolvedLabel, resolvedValue, segmented, stable = false, numericControl = false }: {
  id: string; label: string; value: string; options: Option[]; onChange: (value: string) => void;
  custom?: boolean; min?: number; max?: number; step?: number | "any"; disabled?: boolean; resolvedLabel?: string; resolvedValue?: unknown; segmented?: boolean; stable?: boolean; numericControl?: boolean;
}) {
  const explicit = options.filter(option => option.value !== "");
  const shown = value === "" && resolvedValue != null ? String(resolvedValue) : value;
  const labelLength = explicit.reduce((total, option) => total + option.label.length, 0);
  const numeric = explicit.filter(option => Number.isFinite(Number(option.value)) && Number(option.value) >= min).map(option => Number(option.value));
  // Numeric sentinels with named modes (Auto, Full, etc.) must stay selectable.
  const namedNumericMode = explicit.some(option => Number.isFinite(Number(option.value)) && !/^[+-]?\d/.test(option.label.trim()));
  const inList = options.some(option => option.value === shown);
  const useSegments = segmented ?? (explicit.length <= 4 && (stable ? !custom && explicit.reduce((total, option) => total + option.label.length, 0) <= SEGMENT_LABEL_BUDGET : labelLength <= SEGMENT_LABEL_BUDGET) && numeric.length < 3);
  if (!numericControl && useSegments && (stable || inList)) {
    return <SegmentedChoice bare id={id} label={label} value={shown} options={[...(!shown ? [{ value: "", label: "Not reported" }] : []), ...explicit, ...(shown && !inList ? [{ value: shown, label: resolvedLabel ?? shown }] : [])]} onChange={onChange} disabled={disabled} />;
  }
  if (!namedNumericMode && (numericControl || custom && numeric.length >= 3 && explicit.every(option => Number.isFinite(Number(option.value))) && (stable || value === "" || value === "custom" || Number.isFinite(Number(value))))) {
    const resolved = typeof resolvedValue === "number" ? resolvedValue : Number.isFinite(Number(resolvedValue)) && resolvedValue !== null && resolvedValue !== "" ? Number(resolvedValue) : null;
    return <span className="number-field"><input id={id} type="number" aria-label={label} min={min} max={max} step={step} value={value === "custom" ? "" : shown || resolved || ""} disabled={disabled} onChange={event => onChange(event.target.value)} /></span>;
  }
  const isCustom = shown === "custom" || Boolean(shown && !inList);
  return <div className={stable && custom ? "field-group choice-control-stable" : "field-group"}>
    <select id={id} value={isCustom ? "custom" : shown} onChange={event => onChange(event.target.value)} disabled={disabled}>
      {!shown ? <option value="">Not reported</option> : null}
      {!custom && isCustom ? <option value="custom">{resolvedLabel ?? shown}</option> : null}
      {explicit.map(option => <option key={option.value} value={option.value}>{option.label}</option>)}
      {custom ? <option value="custom">Custom…</option> : null}
    </select>
    {stable && custom ? <span className="choice-custom-slot" data-inactive={!isCustom || undefined}><input aria-label={`Custom ${label.toLowerCase()}`} type="number" min={min} max={max} step={step} required={isCustom} disabled={disabled || !isCustom} placeholder="Exact" value={isCustom && shown !== "custom" ? shown : ""} onChange={event => onChange(event.target.value || "custom")} /></span> : custom && isCustom ? <input aria-label={`Custom ${label.toLowerCase()}`} type="number" min={min} max={max} step={step} required disabled={disabled} value={shown === "custom" ? "" : shown} onChange={event => onChange(event.target.value || "custom")} /> : null}
  </div>;
}

export function numberChoices(values: number[], unit = ""): Option[] {
  return values.map(value => ({ value: String(value), label: `${value.toLocaleString()}${unit}` }));
}

export function contextSliderValues(maximum: number | null, shown: number | null, span = 262144): number[] {
  const upper = Math.max(1, maximum ?? Math.max(span, shown ?? 0));
  const lower = Math.min(1024, upper);
  const values: number[] = [];
  for (let tokens = lower; tokens <= upper; tokens += 1024) values.push(tokens);
  if (values.at(-1) !== upper) values.push(upper);
  // Keep a previously explicit/native value visible without changing it.
  if (shown != null && shown > 0 && !values.includes(shown)) values.push(shown);
  return values.sort((a, b) => a - b);
}

/** One 1024-token slider, with the exact metadata maximum as its final endpoint. */
export function ContextSlider({ id, label = "Context", value, maximum, span, unknownLabel = "Not reported", disabled, title, onChange }: {
  id?: string; label?: string; value: number | null; maximum: number | null; span?: number; unknownLabel?: string; disabled?: boolean; title?: string; onChange: (tokens: number) => void;
}) {
  const values = contextSliderValues(maximum, value, span);
  const index = value == null ? 0 : Math.max(0, values.indexOf(value));
  return <div className="context-slider-control">
    <CompactSliderInput id={id} label={label} values={values} index={index} value={value} disabled={disabled} title={title} onChange={onChange} />
    <output htmlFor={id}>{value == null ? unknownLabel : `${tokenLabel(value)} tokens`}</output>
  </div>;
}

function CompactSliderInput({ id, label, values, index, value, disabled, title, onChange }: {
  id?: string; label: string; values: number[]; index: number; value: number | null; disabled?: boolean; title?: string; onChange: (tokens: number) => void;
}) {
  const maximum = Math.max(0, values.length - 1);
  const fill = maximum > 0 ? Math.min(100, Math.max(0, index / maximum * 100)) : 0;
  return <input id={id} type="range" min={0} max={maximum} step={1} value={index} style={{ "--range-fill": `${fill}%` } as CSSProperties} data-token-value={value ?? undefined} aria-label={label} aria-valuetext={value == null ? "Not reported" : `${value.toLocaleString()} tokens`} title={title} disabled={disabled || values.length < 2} onChange={event => { const next = values[Number(event.target.value)]; if (next != null) onChange(next); }} />;
}
