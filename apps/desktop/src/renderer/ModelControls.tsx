import { type ReactNode } from "react";
import { HoverHelp } from "./HoverHelp";
import { CompactSlider, SegmentedChoice } from "./CompactControls";

export function Help({ label, flag, children }: { label: string; flag?: string; children: ReactNode }) {
  return <HoverHelp title={`About ${label}`}>{children}{flag ? <code>{flag}</code> : null}</HoverHelp>;
}

export function tokenLabel(value: number): string {
  return value >= 1024 && value % 1024 === 0 ? `${value / 1024}k` : value.toLocaleString();
}

type Option = { value: string; label: string };
const SEGMENT_LABEL_BUDGET = 30;

/** Discrete numeric slider with an exact number beside it. An empty value is inherited and shows the resolved value muted. */
export function DiscreteSliderField({ id, label, value, resolved, values, format, unit, min, max, step = 1, disabled, onChange }: {
  id?: string; label: string; value: string; resolved: number | null; values: number[]; format: (value: number) => string; unit?: string;
  min?: number; max?: number; step?: number | "any"; disabled?: boolean; onChange: (value: string) => void;
}) {
  const numeric = value !== "" && Number.isFinite(Number(value)) ? Number(value) : null;
  const shown = numeric ?? resolved ?? values[0] ?? 0;
  return <div className="slider-field">
    <CompactSlider hideHeading label={label} value={shown} values={values} formatValue={format} inherited={numeric === null} disabled={disabled} onChange={next => onChange(String(next))} />
    <span className="number-field">
      <input id={id} type="number" aria-label={`Exact ${label.toLowerCase()}`} min={min} max={max} step={step} disabled={disabled} value={value === "custom" ? "" : value} placeholder={resolved == null ? "" : String(resolved)} onChange={event => onChange(event.target.value)} />
      {unit ? <span className="field-unit">{unit}</span> : null}
    </span>
  </div>;
}

/** The control half of a launch setting row. `""` always means inherited. */
export function ChoiceControl({ id, label, value, options, onChange, custom = true, min = 0, max, step = 1, disabled = false, resolvedLabel, resolvedValue, segmented }: {
  id: string; label: string; value: string; options: Option[]; onChange: (value: string) => void;
  custom?: boolean; min?: number; max?: number; step?: number; disabled?: boolean; resolvedLabel?: string; resolvedValue?: unknown; segmented?: boolean;
}) {
  const explicit = options.filter(option => option.value !== "");
  const labelLength = explicit.reduce((total, option) => total + option.label.length, 0) + "Inherited".length;
  const numeric = explicit.filter(option => Number.isFinite(Number(option.value)) && Number(option.value) >= min).map(option => Number(option.value));
  const inList = value === "" || options.some(option => option.value === value);
  const useSegments = segmented ?? (explicit.length <= 4 && labelLength <= SEGMENT_LABEL_BUDGET && numeric.length < 3);
  if (useSegments && inList) {
    return <SegmentedChoice bare label={label} value={value} options={[{ value: "", label: "Inherited" }, ...explicit]} onChange={onChange} disabled={disabled} />;
  }
  if (custom && numeric.length >= 3 && (value === "" || value === "custom" || Number.isFinite(Number(value)))) {
    const resolved = typeof resolvedValue === "number" ? resolvedValue : Number.isFinite(Number(resolvedValue)) && resolvedValue !== null && resolvedValue !== "" ? Number(resolvedValue) : null;
    const format = (number: number) => options.find(option => option.value === String(number))?.label ?? number.toLocaleString();
    return <DiscreteSliderField id={id} label={label} value={value} resolved={resolved} values={numeric} format={format} min={min} max={max} step={step} disabled={disabled} onChange={next => onChange(next === "" ? "" : next)} />;
  }
  const isCustom = value === "custom" || !inList;
  return <div className="field-group">
    <select id={id} value={isCustom ? "custom" : value} onChange={event => onChange(event.target.value)} disabled={disabled}>
      <option value="" hidden>{resolvedLabel ?? "Inherited"}</option>
      {!custom && isCustom ? <option value="custom">{value} · saved setting</option> : null}
      {explicit.map(option => <option key={option.value} value={option.value}>{option.label}</option>)}
      {custom ? <option value="custom">Custom…</option> : null}
    </select>
    {custom && isCustom ? <input aria-label={`Custom ${label.toLowerCase()}`} type="number" min={min} max={max} step={step} required disabled={disabled} value={value === "custom" ? "" : value} onChange={event => onChange(event.target.value || "custom")} /> : null}
  </div>;
}

export function numberChoices(values: number[], unit = ""): Option[] {
  return values.map(value => ({ value: String(value), label: `${value.toLocaleString()}${unit}` }));
}
