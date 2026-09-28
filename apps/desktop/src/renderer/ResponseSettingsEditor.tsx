import { CompactSwitch, NumberField, SegmentedChoice, SettingRow, SliderField } from "./CompactControls";
import { defaultSettingDisplay, effectiveSettingDisplay, type EffectiveSetting } from "./effectiveSettings";
import type { BundleConfigurationOptions } from "./types";

export function ResponseSettingsEditor({ value, onChange, facts, options, disabled = false, inheritance = "layer", loading = false, part = "thinking" }: {
  value: Record<string, unknown>; onChange: (value: Record<string, unknown>) => void;
  facts: Record<string, EffectiveSetting>; options: BundleConfigurationOptions | null; disabled?: boolean; inheritance?: "layer" | "model"; loading?: boolean;
  part?: "thinking" | "sampling";
}) {
  const patch = (key: string, next: unknown) => onChange({ ...value, [key]: next });
  const follow = (key: string) => { const next = { ...value }; delete next[key]; onChange(next); };
  const descriptor = (key: string) => options?.per_request_defaults[key];
  const fact = (key: string) => facts[`per_request.${key}`] ?? facts[key];
  const current = (key: string) => fact(key)?.known ? fact(key)?.value : null;
  const number = (key: string) => typeof current(key) === "number" ? Number(current(key)) : null;
  const requestedNumber = (key: string) => typeof value[key] === "number" ? Number(value[key]) : null;
  const target = (key: string) => defaultSettingDisplay(fact(key), inheritance === "model" ? "model" : "configuration", key);
  const reset = (key: string) => ({ onReset: Object.hasOwn(value, key) && !disabled ? () => follow(key) : undefined, resetLabel: "Reset", resetTitle: target(key).title });
  const supported = (key: string) => descriptor(key)?.supported !== false;
  const unavailable = (key: string) => descriptor(key)?.supported === false ? descriptor(key)?.description ?? "Unavailable for this model." : undefined;
  const readout = (key: string) => {
    const display = effectiveSettingDisplay(fact(key), loading, key);
    return <span className="model-effective-readout" title={fact(key)?.source} data-state={Object.hasOwn(value, key) ? "set" : "following"}><strong>{display.value}</strong>{display.source ? ` · ${display.source}` : ""}</span>;
  };
  const exact = (key: string, fallback: { min?: number; max?: number; step?: number | "any" } = {}) => ({
    min: descriptor(key)?.minimum ?? fallback.min,
    max: descriptor(key)?.maximum ?? fallback.max,
    step: descriptor(key)?.domain === "integer" ? 1 : descriptor(key)?.step ?? fallback.step ?? "any" as const,
  });
  if (part === "sampling") {
    const sampling = [
      { key: "temperature", label: "Temperature", min: 0, max: 2, step: 0.05, exact: { min: 0 }, help: "Higher values give more varied replies; lower values are more focused." },
      { key: "top_p", label: "Top P", min: 0, max: 1, step: 0.01, exact: { min: 0, max: 1 }, help: "Samples from the smallest set of tokens whose probability adds up to this value." },
      { key: "top_k", label: "Top K", min: 0, max: 200, step: 1, exact: { min: 0, step: 1 }, help: "Samples from this many of the most likely tokens. 0 turns the limit off." },
      { key: "min_p", label: "Min P", min: 0, max: 1, step: 0.01, exact: { min: 0, max: 1 }, help: "Drops tokens less likely than this share of the most likely token." },
      { key: "presence_penalty", label: "Presence penalty", min: -2, max: 2, step: 0.05, help: "Encourages new topics by penalising tokens already used." },
      { key: "repeat_penalty", label: "Repetition penalty", min: 0, max: 2, step: 0.05, exact: { min: 0 }, help: "Discourages repeating recent tokens. 1 turns it off." },
      { key: "frequency_penalty", label: "Frequency penalty", min: -2, max: 2, step: 0.05, help: "Penalises tokens in proportion to how often they appear." },
    ] as const;
    const render = (item: typeof sampling[number]) => <SettingRow key={item.key} label={item.label} htmlFor={`model-response-${item.key}`} help={`${item.help} The slider covers common values; exact entry follows the model's supported range.`} provenance={readout(item.key)} hint={unavailable(item.key)} {...reset(item.key)}>
      <SliderField id={`model-response-${item.key}`} label={item.label} value={requestedNumber(item.key)} resolved={number(item.key)} min={descriptor(item.key)?.suggested_minimum ?? item.min} max={descriptor(item.key)?.suggested_maximum ?? item.max} step={item.step} exact={exact(item.key, "exact" in item ? item.exact : {})} disabled={disabled || !supported(item.key)} onChange={next => next === null ? follow(item.key) : patch(item.key, next)} />
    </SettingRow>;
    return <details className="technical-details advanced-sampling"><summary>Sampling <span className="hint">{sampling.length} controls</span></summary><div className="setting-rows">{sampling.map(render)}</div></details>;
  }
  const modes = descriptor("reasoning"), efforts = descriptor("reasoning_effort"), budget = descriptor("reasoning_budget_tokens");
  const effortOptions = (efforts?.options ?? []).filter(item => typeof item.value === "string" && !["auto", "default"].includes(String(item.value)));
  const effortDefault = target("reasoning_effort");
  const effortValue = typeof value.reasoning_effort === "string" && value.reasoning_effort !== "default" ? value.reasoning_effort : "";
  const hasEfforts = efforts?.supported && effortOptions.length > 0;
  const responseLimitId = inheritance === "model" ? "model-response-max_tokens" : "chat-response-max_tokens";
  const thinkingOn = current("reasoning") === "on" || current("reasoning") === true;
  const history = descriptor("reasoning_preserve");
  return <div className="response-settings-editor setting-rows">
    {hasEfforts ? <SegmentedChoice label="Thinking" description="Only levels effective for this model's template are offered." value={value.reasoning === "off" ? "off" : effortValue} meta={readout("reasoning_effort")} options={[{ value: "", label: "Default" }, ...(modes?.supported ? [{ value: "off", label: "Off" }] : []), ...effortOptions.map(item => ({ value: String(item.value), label: item.label }))]} onChange={next => {
      const updated = { ...value }; delete updated.reasoning; delete updated.reasoning_effort;
      if (next === "off") updated.reasoning = "off";
      else if (next) { if (modes?.supported) updated.reasoning = "on"; updated.reasoning_effort = next; }
      onChange(updated);
    }} disabled={disabled} hint={effortValue && !effortOptions.some(item => item.value === effortValue) ? `${effortValue} is unavailable for this template.` : `Default: ${effortDefault.value}`} onReset={Object.hasOwn(value, "reasoning") || Object.hasOwn(value, "reasoning_effort") ? () => { const next = { ...value }; delete next.reasoning; delete next.reasoning_effort; onChange(next); } : undefined} resetLabel="Reset" resetTitle={effortDefault.title} /> : modes?.supported && current("reasoning") == null ? <SegmentedChoice label="Thinking" value={String(value.reasoning ?? "")} options={[{ value: "", label: "Default" }, { value: "on", label: "On" }, { value: "off", label: "Off" }]} onChange={next => next ? patch("reasoning", next) : follow("reasoning")} disabled={disabled} meta={readout("reasoning")} description="Whether the model generates thinking. Changes apply to future messages." hint="The template's default is not reported. Choose On or Off to set it explicitly." {...reset("reasoning")} /> : modes?.supported ? <CompactSwitch label="Thinking" checked={thinkingOn} onChange={enabled => patch("reasoning", enabled ? "on" : "off")} disabled={disabled} meta={readout("reasoning")} description="Whether the model generates thinking. Changes apply to future messages." hint={Object.hasOwn(value, "reasoning") ? <button type="button" className="text-button" disabled={disabled} onClick={() => follow("reasoning")} title={target("reasoning").title}>Reset</button> : undefined} /> : <span className="hint">Thinking controls unavailable for this template.</span>}
    <SettingRow label="Response budget" htmlFor={requestedNumber("max_tokens") === -1 ? undefined : responseLimitId} help="Maximum tokens for thinking and answer together. An empty value follows compatible publisher guidance, or Workbench Auto: half the usable conversation capacity with Thinking enabled or unknown, one quarter with it disabled, after an 8% safety margin. The allowance is fixed when work first binds to the loaded model." provenance={readout("max_tokens")} hint={requestedNumber("max_tokens") === null ? "Workbench Auto is an allowance, not a guaranteed answer length." : unavailable("max_tokens")} {...reset("max_tokens")}>
      {requestedNumber("max_tokens") === -1 ? <div className="model-unlimited-budget"><strong>Unlimited</strong><span className="hint">Native output limit</span><button type="button" disabled={disabled || !supported("max_tokens")} onClick={() => patch("max_tokens", 2048)}>Set budget</button></div> : <SliderField id={responseLimitId} label="Response budget" value={requestedNumber("max_tokens")} resolved={number("max_tokens")} min={descriptor("max_tokens")?.suggested_minimum ?? 256} max={descriptor("max_tokens")?.suggested_maximum ?? 32768} step={256} exact={exact("max_tokens", { min: 1, step: 1 })} unit="tokens" disabled={disabled || !supported("max_tokens")} onChange={next => next === null ? follow("max_tokens") : patch("max_tokens", next)} />}
    </SettingRow>
    <details className="technical-details response-advanced"><summary>Advanced response</summary><div className="setting-rows">
      {budget?.supported || Object.hasOwn(value, "reasoning_budget_tokens") ? <SettingRow label="Thinking limit" htmlFor={`response-thinking-budget-${inheritance}`} help="Maximum thinking tokens within the total response budget." provenance={readout("reasoning_budget_tokens")} hint={unavailable("reasoning_budget_tokens")} {...reset("reasoning_budget_tokens")}><NumberField id={`response-thinking-budget-${inheritance}`} label="Thinking limit" {...exact("reasoning_budget_tokens", { min: 0, step: 1 })} unit="tokens" value={requestedNumber("reasoning_budget_tokens")} placeholder={number("reasoning_budget_tokens") == null ? "Automatic" : String(number("reasoning_budget_tokens"))} disabled={disabled || budget?.supported !== true} onChange={next => next === null ? follow("reasoning_budget_tokens") : patch("reasoning_budget_tokens", next)} /></SettingRow> : null}
      {history?.supported && current("reasoning_preserve") == null ? <SegmentedChoice label="Keep thinking history" value={value.reasoning_preserve === true ? "keep" : value.reasoning_preserve === false ? "drop" : ""} options={[{ value: "", label: "Default" }, { value: "keep", label: "Keep" }, { value: "drop", label: "Drop" }]} onChange={next => next ? patch("reasoning_preserve", next === "keep") : follow("reasoning_preserve")} disabled={disabled} meta={readout("reasoning_preserve")} description="Include earlier thinking in later messages. It uses conversation capacity alongside your messages and the model's answers." hint="The template's default is not reported." {...reset("reasoning_preserve")} /> : history?.supported ? <CompactSwitch label="Keep thinking history" checked={current("reasoning_preserve") === true} onChange={enabled => patch("reasoning_preserve", enabled)} disabled={disabled} meta={readout("reasoning_preserve")} description="Include earlier thinking in later messages. It uses conversation capacity alongside your messages and the model's answers." hint={Object.hasOwn(value, "reasoning_preserve") ? <button type="button" className="text-button" disabled={disabled} onClick={() => follow("reasoning_preserve")}>Reset</button> : undefined} /> : null}
    </div></details>
  </div>;
}
