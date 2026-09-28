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
  const fact = (key: string) => facts[`per_request.${key}`] ?? facts[key];
  const current = (key: string) => fact(key)?.known ? fact(key)?.value : null;
  const number = (key: string) => typeof current(key) === "number" ? Number(current(key)) : null;
  const requestedNumber = (key: string) => typeof value[key] === "number" ? Number(value[key]) : null;
  const target = (key: string) => defaultSettingDisplay(fact(key), inheritance === "model" ? "model" : "configuration", key);
  const reset = (key: string) => ({ onReset: Object.hasOwn(value, key) && !disabled ? () => follow(key) : undefined, resetLabel: target(key).label, resetTitle: target(key).title });
  const readout = (key: string) => {
    const display = effectiveSettingDisplay(fact(key), loading);
    return <span className="model-effective-readout" title={fact(key)?.source} data-state={Object.hasOwn(value, key) ? "set" : "following"}><strong>{display.value}</strong>{display.source ? ` · ${display.source}` : ""}</span>;
  };
  const optionsFor = (key: string) => (options?.per_request_defaults[key]?.options ?? []).filter(item => typeof item.value === "string" && !["auto", "default"].includes(String(item.value)));
  const modes = options?.per_request_defaults.reasoning;
  const efforts = options?.per_request_defaults.reasoning_effort;
  const effortOptions = optionsFor("reasoning_effort");
  const budget = options?.per_request_defaults.reasoning_budget_tokens;
  const presets = options?.response_presets ?? [];
  const selectedPreset = presets.find(preset => Object.entries(preset.per_request).every(([key, expected]) => (Object.hasOwn(value, key) ? value[key] : current(key)) === expected));
  const choosePreset = (id: string) => {
    const preset = presets.find(item => item.id === id);
    if (!preset) return;
    const next = { ...value };
    for (const key of ["reasoning", "reasoning_effort", "reasoning_budget_tokens", "max_tokens"]) delete next[key];
    onChange({ ...next, ...preset.per_request });
  };
  const resetChoices = (key: string) => {
    const model = defaultSettingDisplay(fact(key), "model", key);
    const parent = defaultSettingDisplay(fact(key), "configuration", key);
    return <span className="setting-reset-actions">
      <button type="button" className="text-button" disabled={disabled} title={model.title} aria-label={`${model.label}: ${model.title}`} onClick={() => patch(key, key === "reasoning" ? "auto" : "default")}>{model.label}</button>
      {Object.hasOwn(value, key) ? <button type="button" className="text-button" disabled={disabled} title={parent.title} aria-label={`${parent.label}: ${parent.title}`} onClick={() => follow(key)}>{parent.label}</button> : null}
    </span>;
  };
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
    const render = (item: typeof sampling[number]) => <SettingRow key={item.key} label={item.label} htmlFor={`model-response-${item.key}`} help={`${item.help} Clearing the value uses the model default.`} provenance={readout(item.key)} {...reset(item.key)}>
      <SliderField id={`model-response-${item.key}`} label={item.label} value={requestedNumber(item.key)} resolved={number(item.key)} min={item.min} max={item.max} step={item.step} exact={"exact" in item ? item.exact : undefined} disabled={disabled} onChange={next => next === null ? follow(item.key) : patch(item.key, next)} />
    </SettingRow>;
    return <>{sampling.slice(0, 2).map(render)}<details className="technical-details advanced-sampling"><summary>Advanced sampling <span className="hint">5 controls</span></summary><div className="setting-rows">{sampling.slice(2).map(render)}</div></details></>;
  }
  const effortDefault = target("reasoning_effort");
  const effortValue = typeof value.reasoning_effort === "string" && value.reasoning_effort !== "default" ? value.reasoning_effort : "";
  const responseLimitId = inheritance === "model" ? "model-response-max_tokens" : "chat-response-max_tokens";
  return <div className="response-settings-editor setting-rows">
    {presets.length ? <SegmentedChoice label="Response mode" description="Balanced for everyday replies; Deep for more demanding tasks." value={selectedPreset?.id ?? ""} meta={selectedPreset?.description ?? "Custom settings"} options={presets.map(preset => ({ value: preset.id, label: preset.label }))} onChange={choosePreset} disabled={disabled} /> : null}
    {modes?.supported ? inheritance === "model" ? <SegmentedChoice label="Thinking" description="Whether the model generates thinking." value={String(value.reasoning ?? "auto") === "auto" ? "" : String(value.reasoning)} meta={readout("reasoning")} options={[{ value: "", label: `${target("reasoning").value} · Model default` }, { value: "on", label: "On" }, { value: "off", label: "Off" }]} onChange={next => next === "" ? follow("reasoning") : patch("reasoning", next)} disabled={disabled} /> : <CompactSwitch label="Thinking" checked={current("reasoning") === "on" || current("reasoning") === true} onChange={enabled => patch("reasoning", enabled ? "on" : "off")} disabled={disabled || current("reasoning") == null} meta={readout("reasoning")} hint={<>{current("reasoning") == null ? <SegmentedChoice bare label="Thinking choice" value={String(value.reasoning ?? "")} disabled={disabled} onChange={next => next === "" ? follow("reasoning") : patch("reasoning", next)} options={[{ value: "", label: `${target("reasoning").value} · ${target("reasoning").source}` }, { value: "on", label: "On" }, { value: "off", label: "Off" }]} /> : null}{resetChoices("reasoning")}</>} /> : null}
    {efforts?.supported && current("reasoning") !== "off" ? <SettingRow label="Thinking level" htmlFor={`response-thinking-level-${inheritance}`} help="Only levels declared by this model template are offered." provenance={readout("reasoning_effort")} {...(inheritance === "model" ? reset("reasoning_effort") : {})} hint={inheritance === "layer" ? resetChoices("reasoning_effort") : undefined}>
      <select id={`response-thinking-level-${inheritance}`} value={effortValue} disabled={disabled || !effortOptions.length} onChange={event => event.target.value === "" ? follow("reasoning_effort") : patch("reasoning_effort", event.target.value)}>
        <option value="">{effortDefault.value} · {effortDefault.source}</option>
        {effortValue && !effortOptions.some(item => item.value === effortValue) ? <option value={effortValue}>{effortValue} · unavailable</option> : null}
        {effortOptions.map(item => <option key={String(item.value)} value={String(item.value)}>{item.label}</option>)}
      </select>
    </SettingRow> : null}
    {!modes?.supported && !efforts?.supported ? <span className="hint">Thinking controls unavailable</span> : null}
    <SettingRow label="Thinking limit" htmlFor={`response-thinking-budget-${inheritance}`} help="Maximum thinking tokens in each response. The response limit includes thinking and the answer." provenance={readout("reasoning_budget_tokens")} hint={budget?.supported !== true ? budget?.description ?? "Support not reported" : undefined} {...reset("reasoning_budget_tokens")}>
      <NumberField id={`response-thinking-budget-${inheritance}`} label="Thinking limit" min={0} step={1} unit="tokens" value={requestedNumber("reasoning_budget_tokens")} placeholder={number("reasoning_budget_tokens") == null ? "Not reported" : String(number("reasoning_budget_tokens"))} disabled={disabled || budget?.supported === false} onChange={next => next === null ? follow("reasoning_budget_tokens") : patch("reasoning_budget_tokens", next)} />
    </SettingRow>
    <SettingRow label="Response limit" htmlFor={responseLimitId} help="Maximum tokens per response, including thinking and the answer." provenance={readout("max_tokens")} {...reset("max_tokens")}>
      <NumberField id={responseLimitId} label="Response limit" value={requestedNumber("max_tokens")} placeholder={number("max_tokens") == null ? "Not reported" : String(number("max_tokens"))} min={1} step={1} unit="tokens" disabled={disabled} onChange={next => next === null ? follow("max_tokens") : patch("max_tokens", next)} />
    </SettingRow>
  </div>;
}
