import { CompactSwitch, CompactSlider, SegmentedChoice } from "./CompactControls";
import { HoverHelp } from "./HoverHelp";
import { effectiveSettingDisplay, settingSource, settingValue, type EffectiveSetting } from "./effectiveSettings";
import type { BundleConfigurationOptions } from "./types";

export function ResponseSettingsEditor({ value, onChange, facts, options, disabled = false, compact = false, inheritance = "layer", loading = false }: {
  value: Record<string, unknown>; onChange: (value: Record<string, unknown>) => void;
  facts: Record<string, EffectiveSetting>; options: BundleConfigurationOptions | null; disabled?: boolean; compact?: boolean; inheritance?: "layer" | "model"; loading?: boolean;
}) {
  const patch = (key: string, next: unknown) => onChange({ ...value, [key]: next });
  const inherit = (key: string) => { const next = { ...value }; delete next[key]; onChange(next); };
  const fact = (key: string) => facts[`per_request.${key}`] ?? facts[key];
  const current = (key: string) => fact(key)?.known ? fact(key)?.value : null;
  const source = (key: string) => settingSource(fact(key)?.source);
  const modes = options?.per_request_defaults.reasoning;
  const efforts = options?.per_request_defaults.reasoning_effort;
  const effortOptions = (efforts?.options ?? []).filter(item => typeof item.value === "string" && item.value !== "default");
  const effectiveEffort = current("reasoning_effort");
  const effectiveMode = current("reasoning");
  if (inheritance === "model") {
    const readout = (key: string) => {
      const resolved = fact(key);
      const display = effectiveSettingDisplay(resolved, loading);
      const state = resolved?.source === "Unsaved changes" ? "Unsaved change" : Object.prototype.hasOwnProperty.call(value, key) ? "Set in configuration" : "Inherited";
      return <div className="model-effective-readout"><strong>{display.value}</strong><small>{display.source}{!loading ? ` · ${state}` : ""}</small></div>;
    };
    const numbers = [
      { key: "max_tokens", label: "Reply limit", min: 1, step: 1 },
      { key: "temperature", label: "Temperature", min: 0, step: "any" },
      { key: "top_p", label: "Top P", min: 0, max: 1, step: "any" },
      { key: "top_k", label: "Top K", min: 0, step: 1 },
      { key: "min_p", label: "Min P", min: 0, max: 1, step: "any" },
      { key: "presence_penalty", label: "Presence penalty", step: "any" },
      { key: "repeat_penalty", label: "Repetition penalty", min: 0, step: "any" },
      { key: "frequency_penalty", label: "Frequency penalty", step: "any" },
    ] as const;
    return <div className="response-settings-editor model-response-editor">
      {modes?.supported ? <div className="model-response-setting"><SegmentedChoice label="Thinking" value={String(value.reasoning ?? "auto")} options={[{ value: "auto", label: "Use inherited" }, { value: "on", label: "On" }, { value: "off", label: "Off" }]} onChange={next => next === "auto" ? inherit("reasoning") : patch("reasoning", next)} disabled={disabled} description="Control whether the model generates thinking for future turns." />{readout("reasoning")}</div> : null}
      {efforts?.supported && value.reasoning !== "off" && effectiveMode !== "off" ? <div className="model-response-setting"><div className="setting-title"><label htmlFor="model-thinking-level">Thinking level</label><HoverHelp title="Thinking level">Only levels declared by this model template are offered.</HoverHelp></div><select id="model-thinking-level" value={String(value.reasoning_effort ?? "default")} disabled={disabled} onChange={event => event.target.value === "default" ? inherit("reasoning_effort") : patch("reasoning_effort", event.target.value)}><option value="default">Use inherited</option>{effortOptions.map(item => <option key={String(item.value)} value={String(item.value)}>{item.label}</option>)}</select>{readout("reasoning_effort")}</div> : null}
      {!modes?.supported && !efforts?.supported ? <span className="hint">Thinking controls unavailable for this model.</span> : null}
      {!compact ? <div className="response-numeric-grid">{numbers.map(item => <div className="model-response-setting" key={item.key}><div className="setting-title"><label htmlFor={`model-response-${item.key}`}>{item.label}</label><HoverHelp title={item.label}>Empty uses the inherited setting.</HoverHelp></div><input id={`model-response-${item.key}`} type="number" min={"min" in item ? item.min : undefined} max={"max" in item ? item.max : undefined} step={item.step} disabled={disabled} value={typeof value[item.key] === "number" ? Number(value[item.key]) : ""} placeholder="Use inherited" onChange={event => event.target.value === "" ? inherit(item.key) : patch(item.key, Number(event.target.value))} />{readout(item.key)}{Object.prototype.hasOwnProperty.call(value, item.key) ? <button type="button" className="quiet-button model-setting-reset" disabled={disabled} onClick={() => inherit(item.key)}>Reset to inherited</button> : null}</div>)}</div> : null}
    </div>;
  }
  return <div className="response-settings-editor">
    {modes?.supported ? <div className="setting-row"><CompactSwitch label="Thinking" checked={effectiveMode === "on" || effectiveMode === true} onChange={enabled => patch("reasoning", enabled ? "on" : "off")} disabled={disabled || effectiveMode == null} description={effectiveMode == null ? "Default not reported. Choose an explicit value below." : source("reasoning")} />
      {effectiveMode == null ? <select className="thinking-explicit-choice" aria-label="Thinking" value={String(value.reasoning ?? "auto")} disabled={disabled} onChange={event => patch("reasoning", event.target.value)}><option value="auto">Model default · unknown</option><option value="on">On</option><option value="off">Off</option></select> : null}
      <div className="setting-reset-actions">{effectiveMode != null ? <span className="hint">{`${settingValue(effectiveMode)} · ${source("reasoning")}`}</span> : null}<button type="button" className="quiet-button" disabled={disabled} onClick={() => patch("reasoning", "auto")}>Model default</button>{"reasoning" in value ? <button type="button" className="quiet-button" disabled={disabled} onClick={() => inherit("reasoning")}>Use inherited</button> : null}</div></div> : null}
    {efforts?.supported && effectiveMode !== "off" ? <div className="setting-row"><label>Thinking level <strong>{effectiveEffort == null ? "Default not reported" : `${settingValue(effectiveEffort)} · ${source("reasoning_effort")}`}</strong><HoverHelp title="Thinking level">{source("reasoning_effort")}. Active and queued turns retain their resolved settings.</HoverHelp></label>
      {effortOptions.some(item => item.value === effectiveEffort) ? <CompactSlider hideHeading label="Thinking level" values={effortOptions.map((_, index) => index)} value={effortOptions.findIndex(item => item.value === effectiveEffort)} onChange={index => patch("reasoning_effort", effortOptions[index]?.value)} formatValue={index => effortOptions[index]?.label ?? "Unknown"} disabled={disabled || !effortOptions.length} /> : <select aria-label="Thinking level" value="" disabled={disabled || !effortOptions.length} onChange={event => { if (event.target.value) patch("reasoning_effort", event.target.value); }}><option value="">{effectiveEffort == null ? "Model default · unknown" : `${settingValue(effectiveEffort)} · unavailable`}</option>{effortOptions.map(item => <option key={String(item.value)} value={String(item.value)}>{item.label}</option>)}</select>}
      <div className="setting-reset-actions"><button type="button" className="quiet-button" disabled={disabled} onClick={() => patch("reasoning_effort", "default")}>Model default</button>{"reasoning_effort" in value ? <button type="button" className="quiet-button" disabled={disabled} onClick={() => inherit("reasoning_effort")}>Use inherited</button> : null}</div></div> : null}
    {!compact ? <div className="response-numeric-grid">{([
      { key: "temperature", label: "Temperature", min: 0, step: 0.05 },
      { key: "top_p", label: "Top P", min: 0, max: 1, step: 0.05 },
      { key: "top_k", label: "Top K", min: 0, step: 1 },
      { key: "min_p", label: "Min P", min: 0, max: 1, step: 0.01 },
      { key: "presence_penalty", label: "Presence penalty", step: 0.05 },
      { key: "repeat_penalty", label: "Repetition penalty", min: 0, step: 0.05 },
      { key: "max_tokens", label: "Reply limit", min: 1, step: 1 },
    ] as const).map(item => <label key={item.key}><span className="setting-title">{item.label}<HoverHelp title={item.label}>{source(item.key)}. Empty uses the inherited setting.</HoverHelp></span><input type="number" min={"min" in item ? item.min : undefined} max={"max" in item ? item.max : undefined} step={item.step} disabled={disabled} value={typeof value[item.key] === "number" ? Number(value[item.key]) : ""} placeholder={current(item.key) == null ? "Default not reported" : String(current(item.key))} onChange={event => event.target.value === "" ? inherit(item.key) : patch(item.key, Number(event.target.value))} /><span className="hint">{current(item.key) == null ? "Default not reported" : `${settingValue(current(item.key))} · ${source(item.key)}`}</span></label>)}</div> : null}
    {!modes?.supported && !efforts?.supported ? <span className="hint">Thinking controls unavailable<HoverHelp title="Thinking availability">This model does not report configurable thinking. Its template controls reasoning.</HoverHelp></span> : null}
  </div>;
}
