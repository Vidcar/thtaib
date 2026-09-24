import { useId } from "react";
import { HoverHelp } from "./HoverHelp";

export function CompactSwitch(props: { label: string; checked: boolean; onChange: (checked: boolean) => void; disabled?: boolean; description?: string; meta?: string }) {
  return <span className="compact-switch-row"><span>{props.label}{props.description ? <HoverHelp title={`About ${props.label.toLowerCase()}`}>{props.description}</HoverHelp> : null}{props.meta ? <small className="control-provenance">{props.meta}</small> : null}</span><button type="button" className="compact-switch" role="switch" aria-label={props.label} aria-checked={props.checked} disabled={props.disabled} onClick={() => props.onChange(!props.checked)}><span /></button></span>;
}

export function SegmentedChoice({ label, value, options, onChange, disabled = false, description, meta }: {
  label: string; value: string; options: Array<{ value: string; label: string }>;
  onChange: (value: string) => void; disabled?: boolean; description?: string; meta?: string;
}) {
  const id = useId();
  return <fieldset className="segmented-setting" disabled={disabled}><legend>{label}{description ? <HoverHelp title={`About ${label.toLowerCase()}`}>{description}</HoverHelp> : null}{meta ? <small className="control-provenance">{meta}</small> : null}</legend><div className="segmented-options">{options.map(option => <label key={option.value}><input type="radio" name={id} value={option.value} checked={value === option.value} onChange={() => onChange(option.value)} /><span>{option.label}</span></label>)}</div></fieldset>;
}

export function CompactSlider(props: { hideHeading?: boolean; label: string; value: number; values: number[]; onChange: (value: number) => void; formatValue?: (value: number) => string; disabled?: boolean; description?: string }) {
  const id = useId();
  const values = [...new Set([...props.values, props.value])].sort((a, b) => a - b);
  const format = props.formatValue ?? ((value: number) => value.toLocaleString());
  return <div className="compact-slider"><div className={props.hideHeading ? "compact-slider-heading visually-hidden" : "compact-slider-heading"}><label htmlFor={id}>{props.label}</label>{props.description ? <HoverHelp title={`About ${props.label.toLowerCase()}`}>{props.description}</HoverHelp> : null}<output htmlFor={id}>{format(props.value)}</output></div><input id={id} type="range" min={0} max={Math.max(0, values.length - 1)} step={1} list={`${id}-ticks`} value={values.indexOf(props.value)} aria-label={props.label} aria-valuetext={format(props.value)} disabled={props.disabled || values.length < 2} onChange={event => props.onChange(values[Number(event.target.value)] ?? props.value)} /><datalist id={`${id}-ticks`}>{values.map((value, index) => <option key={value} value={index} label={format(value)} />)}</datalist><div className="compact-slider-limits" aria-hidden="true"><span>{format(values[0] ?? props.value)}</span><span>{format(values.at(-1) ?? props.value)}</span></div></div>;
}
