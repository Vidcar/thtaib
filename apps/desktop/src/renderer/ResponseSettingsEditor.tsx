import { CompactSwitch, CompactSlider, NumberField, SegmentedChoice, SettingRow, SliderField } from "./CompactControls";
import { HoverHelp } from "./HoverHelp";
import { effectiveSettingDisplay, settingSource, settingValue, type EffectiveSetting } from "./effectiveSettings";
import type { BundleConfigurationOptions } from "./types";

export function ResponseSettingsEditor({ value, onChange, facts, options, disabled = false, compact = false, inheritance = "layer", loading = false, part = "thinking" }: {
  value: Record<string, unknown>; onChange: (value: Record<string, unknown>) => void;
  facts: Record<string, EffectiveSetting>; options: BundleConfigurationOptions | null; disabled?: boolean; compact?: boolean; inheritance?: "layer" | "model"; loading?: boolean;
  part?: "thinking" | "sampling";
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
    const state = (key: string) => fact(key)?.source === "Unsaved changes" ? "Unsaved change" : Object.prototype.hasOwnProperty.call(value, key) ? "Set in configuration" : "Inherited";
    const readout = (key: string) => {
      const display = effectiveSettingDisplay(fact(key), loading);
      return <span className="model-effective-readout" data-state={state(key) === "Inherited" ? "inherited" : "set"}><strong>{display.value}</strong> · {display.source}{!loading ? ` · ${state(key)}` : ""}</span>;
    };
    const set = (key: string) => Object.prototype.hasOwnProperty.call(value, key);
    const resolvedNumber = (key: string) => { const resolved = current(key); return typeof resolved === "number" ? resolved : null; };
    const numberValue = (key: string) => typeof value[key] === "number" ? Number(value[key]) : null;
    const commit = (key: string) => (next: number | null) => next === null ? inherit(key) : patch(key, next);
    if (part === "thinking") {
      const effortValues = effortOptions.map(item => ({ value: String(item.value), label: item.label }));
      const inheritedEffort = typeof effectiveEffort === "string" ? effectiveEffort : undefined;
      return <>
        {modes?.supported ? <SegmentedChoice label="Thinking" description="Whether the model generates thinking for future turns." value={String(value.reasoning ?? "auto") === "auto" ? "" : String(value.reasoning)} meta={readout("reasoning")}
          options={[{ value: "", label: "Inherited" }, { value: "on", label: "On" }, { value: "off", label: "Off" }]} onChange={next => next === "" ? inherit("reasoning") : patch("reasoning", next)} disabled={disabled} /> : null}
        {efforts?.supported && value.reasoning !== "off" && effectiveMode !== "off" ? (effortValues.length && effortValues.length <= 5
          ? <SegmentedChoice label="Thinking level" description="Only levels declared by this model template are offered." value={typeof value.reasoning_effort === "string" && value.reasoning_effort !== "default" ? value.reasoning_effort : ""} inheritedValue={inheritedEffort} meta={readout("reasoning_effort")}
              options={effortValues} onChange={next => patch("reasoning_effort", next)} onReset={set("reasoning_effort") && !disabled ? () => inherit("reasoning_effort") : undefined} disabled={disabled} />
          : <SettingRow label="Thinking level" htmlFor="model-thinking-level" help="Only levels declared by this model template are offered." provenance={readout("reasoning_effort")} onReset={set("reasoning_effort") && !disabled ? () => inherit("reasoning_effort") : undefined}>
              <select id="model-thinking-level" value={String(value.reasoning_effort ?? "default")} disabled={disabled} onChange={event => event.target.value === "default" ? inherit("reasoning_effort") : patch("reasoning_effort", event.target.value)}><option value="default" hidden>{effectiveEffort == null ? "Not reported" : settingValue(effectiveEffort)}</option>{effortOptions.map(item => <option key={String(item.value)} value={String(item.value)}>{item.label}</option>)}</select>
            </SettingRow>) : null}
        {!modes?.supported && !efforts?.supported ? <p className="hint">Thinking controls unavailable for this model.</p> : null}
        <SettingRow label="Reply limit" htmlFor="model-response-max_tokens" help="Maximum tokens in one reply. Empty uses the inherited setting." provenance={readout("max_tokens")} onReset={set("max_tokens") && !disabled ? () => inherit("max_tokens") : undefined}>
          <NumberField id="model-response-max_tokens" label="Reply limit" value={numberValue("max_tokens")} placeholder={resolvedNumber("max_tokens") == null ? "Not reported" : String(resolvedNumber("max_tokens"))} min={1} step={1} unit="tokens" disabled={disabled} onChange={commit("max_tokens")} />
        </SettingRow>
      </>;
    }
    const sampling = [
      { key: "temperature", label: "Temperature", min: 0, max: 2, step: 0.05, help: "Higher values give more varied replies; lower values are more focused." },
      { key: "top_p", label: "Top P", min: 0, max: 1, step: 0.01, help: "Samples from the smallest set of tokens whose probability adds up to this value." },
      { key: "top_k", label: "Top K", min: 0, max: 200, step: 1, help: "Samples from this many of the most likely tokens. 0 turns the limit off." },
      { key: "min_p", label: "Min P", min: 0, max: 1, step: 0.01, help: "Drops tokens less likely than this share of the most likely token." },
      { key: "presence_penalty", label: "Presence penalty", min: -2, max: 2, step: 0.05, help: "Encourages new topics by penalising tokens already used." },
      { key: "repeat_penalty", label: "Repetition penalty", min: 0, max: 2, step: 0.05, help: "Discourages repeating recent tokens. 1 turns it off." },
      { key: "frequency_penalty", label: "Frequency penalty", min: -2, max: 2, step: 0.05, help: "Penalises tokens in proportion to how often they appear." },
    ] as const;
    return <>{sampling.map(item => <SettingRow key={item.key} label={item.label} htmlFor={`model-response-${item.key}`} help={`${item.help} Empty uses the inherited setting.`} provenance={readout(item.key)} onReset={set(item.key) && !disabled ? () => inherit(item.key) : undefined}>
      <SliderField id={`model-response-${item.key}`} label={item.label} value={numberValue(item.key)} resolved={resolvedNumber(item.key)} min={item.min} max={item.max} step={item.step} disabled={disabled} onChange={commit(item.key)} />
    </SettingRow>)}</>;
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
