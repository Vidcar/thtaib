import { useId } from "react";
import { HoverHelp } from "./HoverHelp";

export function CompactSwitch(props: { label: string; checked: boolean; onChange: (checked: boolean) => void; disabled?: boolean; description?: string }) {
  return <span className="compact-switch-row"><span>{props.label}{props.description ? <HoverHelp title={`About ${props.label.toLowerCase()}`}>{props.description}</HoverHelp> : null}</span><button type="button" className="compact-switch" role="switch" aria-label={props.label} aria-checked={props.checked} disabled={props.disabled} onClick={() => props.onChange(!props.checked)}><span /></button></span>;
}

export function CompactSlider(props: { label: string; value: number; values: number[]; onChange: (value: number) => void; formatValue?: (value: number) => string; disabled?: boolean; description?: string }) {
  const id = useId();
  const values = [...new Set([...props.values, props.value])].sort((a, b) => a - b);
  const format = props.formatValue ?? ((value: number) => value.toLocaleString());
  return <div className="compact-slider"><div className="compact-slider-heading"><label htmlFor={id}>{props.label}</label>{props.description ? <HoverHelp title={`About ${props.label.toLowerCase()}`}>{props.description}</HoverHelp> : null}<output htmlFor={id}>{format(props.value)}</output></div><input id={id} type="range" min={0} max={Math.max(0, values.length - 1)} step={1} list={`${id}-ticks`} value={values.indexOf(props.value)} aria-label={props.label} aria-valuetext={format(props.value)} disabled={props.disabled || values.length < 2} onChange={event => props.onChange(values[Number(event.target.value)] ?? props.value)} /><datalist id={`${id}-ticks`}>{values.map((value, index) => <option key={value} value={index} label={format(value)} />)}</datalist><div className="compact-slider-limits" aria-hidden="true"><span>{format(values[0] ?? props.value)}</span><span>{format(values.at(-1) ?? props.value)}</span></div></div>;
}
