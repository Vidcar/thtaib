import { CompactSwitch, NumberField, SegmentedChoice, SettingRow, SliderField, type SettingLayout } from "./CompactControls";
import { defaultSettingDisplay, effectiveSettingDisplay, type EffectiveSetting } from "./effectiveSettings";
import type { BundleConfigurationOptions } from "./types";

export function ResponseSettingsEditor({ value, onChange, facts, presentationFacts, options, disabled = false, inheritance = "layer", loading = false, part = "thinking", layout = "default" }: {
  value: Record<string, unknown>; onChange: (value: Record<string, unknown>) => void;
  facts: Record<string, EffectiveSetting>; presentationFacts?: Record<string, EffectiveSetting>; options: BundleConfigurationOptions | null; disabled?: boolean; inheritance?: "layer" | "model"; loading?: boolean;
  part?: "thinking" | "sampling"; layout?: SettingLayout;
}) {
  const models = layout === "models";
  const patch = (key: string, next: unknown) => onChange({ ...value, [key]: next });
  const follow = (key: string) => { const next = { ...value }; delete next[key]; onChange(next); };
  const descriptor = (key: string) => options?.per_request_defaults[key];
  const fact = (key: string) => facts[`per_request.${key}`] ?? facts[key];
  // A parent may retain facts from the same model/setup only. They position an
  // inherited control while checking; they never establish current support.
  const presentation = (key: string) => fact(key) ?? (models && loading ? presentationFacts?.[`per_request.${key}`] ?? presentationFacts?.[key] : undefined);
  const current = (key: string) => fact(key)?.known ? fact(key)?.value : null;
  const number = (key: string) => typeof (models && loading ? presentation(key)?.value : current(key)) === "number" ? Number(models && loading ? presentation(key)?.value : current(key)) : null;
  const requestedNumber = (key: string) => typeof value[key] === "number" ? Number(value[key]) : null;
  const target = (key: string) => {
    const result = defaultSettingDisplay(presentation(key), inheritance === "model" ? "model" : "configuration", key);
    if (models && key === "reasoning_budget_tokens" && result.value === "-1") { result.value = "No separate limit"; result.title = result.title.replace(/^-1(?= ·)/, result.value); }
    return result;
  };
  const reset = (key: string) => ({ onReset: Object.hasOwn(value, key) && !disabled ? () => follow(key) : undefined, resetLabel: "Reset", resetTitle: target(key).title });
  const supported = (key: string) => descriptor(key)?.supported !== false;
  const unavailable = (key: string) => descriptor(key)?.supported === false ? descriptor(key)?.description ?? "Unavailable for this model." : undefined;
  const status = (key: string) => models ? loading ? "Checking…" : descriptor(key)?.supported === false ? "Unavailable" : descriptor(key)?.supported == null ? "Support not verified" : undefined : undefined;
  const readout = (key: string) => {
    const shown = models && loading ? Object.hasOwn(value, key) ? { value: value[key], source: "Set value", known: true, inherited: false, requires_reload: false } : presentation(key) : fact(key);
    const display = effectiveSettingDisplay(shown, loading && !models, key);
    if (models && key === "reasoning_budget_tokens" && shown?.value === -1) display.value = "No separate limit";
    if (models && loading && !Object.hasOwn(value, key) && shown?.known) display.source = "Last checked";
    return <span className="model-effective-readout" title={shown?.source} data-state={Object.hasOwn(value, key) ? "set" : "following"} data-pending={models && loading || undefined}><strong>{display.value}</strong>{display.source ? ` · ${display.source}` : ""}</span>;
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
    const render = (item: typeof sampling[number]) => <SettingRow key={item.key} layout={layout} label={item.label} htmlFor={`model-response-${item.key}`} help={`${item.help} The slider covers common values; exact entry follows the model's supported range.`} provenance={readout(item.key)} hint={unavailable(item.key)} status={status(item.key)} {...reset(item.key)}>
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
  const format = descriptor("reasoning_format");
  const thinkingOptions = hasEfforts ? [{ value: "", label: "Default" }, ...(modes?.supported ? [{ value: "off", label: "Off" }] : []), ...effortOptions.map(item => ({ value: String(item.value), label: item.label }))] : [{ value: "", label: "Default" }, { value: "on", label: "On" }, { value: "off", label: "Off" }];
  const thinkingValue = hasEfforts ? value.reasoning === "off" ? "off" : effortValue : String(value.reasoning ?? "");
  if (models && thinkingValue && !thinkingOptions.some(item => item.value === thinkingValue)) thinkingOptions.push({ value: thinkingValue, label: `${thinkingValue} · saved` });
  const limitValue = requestedNumber("reasoning_budget_tokens");
  const limitMode = limitValue === -1 ? "unlimited" : limitValue === null ? "" : "custom";
  const limitId = `response-thinking-budget-${inheritance}`;
  const formatValue = typeof value.reasoning_format === "string" ? value.reasoning_format : "";
  const formatOptions = (format?.options ?? []).filter(item => typeof item.value === "string");
  return <div className="response-settings-editor setting-rows">
    {models ? <SegmentedChoice layout={layout} label="Thinking" description="Whether the model generates thinking. Only levels effective for its template are offered. Default follows the model's template." value={thinkingValue} meta={readout(hasEfforts && value.reasoning !== "off" ? "reasoning_effort" : "reasoning")} options={thinkingOptions} status={status(hasEfforts ? "reasoning_effort" : "reasoning")} hint={unavailable(hasEfforts ? "reasoning_effort" : "reasoning")} onChange={next => {
      const updated = { ...value }; delete updated.reasoning; delete updated.reasoning_effort;
      if (next === "off" || !hasEfforts && next === "on") updated.reasoning = next;
      else if (next) { if (modes?.supported) updated.reasoning = "on"; updated.reasoning_effort = next; }
      onChange(updated);
    }} disabled={disabled || !hasEfforts && modes?.supported !== true} onReset={!disabled && (Object.hasOwn(value, "reasoning") || Object.hasOwn(value, "reasoning_effort")) ? () => { const next = { ...value }; delete next.reasoning; delete next.reasoning_effort; onChange(next); } : undefined} resetLabel="Reset" resetTitle={hasEfforts ? effortDefault.title : target("reasoning").title} /> : hasEfforts ? <SegmentedChoice label="Thinking" description="Only levels effective for this model's template are offered." value={value.reasoning === "off" ? "off" : effortValue} meta={readout("reasoning_effort")} options={[{ value: "", label: "Default" }, ...(modes?.supported ? [{ value: "off", label: "Off" }] : []), ...effortOptions.map(item => ({ value: String(item.value), label: item.label }))]} onChange={next => {
      const updated = { ...value }; delete updated.reasoning; delete updated.reasoning_effort;
      if (next === "off") updated.reasoning = "off";
      else if (next) { if (modes?.supported) updated.reasoning = "on"; updated.reasoning_effort = next; }
      onChange(updated);
    }} disabled={disabled} hint={effortValue && !effortOptions.some(item => item.value === effortValue) ? `${effortValue} is unavailable for this template.` : `Default: ${effortDefault.value}`} onReset={Object.hasOwn(value, "reasoning") || Object.hasOwn(value, "reasoning_effort") ? () => { const next = { ...value }; delete next.reasoning; delete next.reasoning_effort; onChange(next); } : undefined} resetLabel="Reset" resetTitle={effortDefault.title} /> : modes?.supported && current("reasoning") == null ? <SegmentedChoice label="Thinking" value={String(value.reasoning ?? "")} options={[{ value: "", label: "Default" }, { value: "on", label: "On" }, { value: "off", label: "Off" }]} onChange={next => next ? patch("reasoning", next) : follow("reasoning")} disabled={disabled} meta={readout("reasoning")} description="Whether the model generates thinking. Changes apply to future messages." hint="The template's default is not reported. Choose On or Off to set it explicitly." {...reset("reasoning")} /> : modes?.supported ? <CompactSwitch label="Thinking" checked={thinkingOn} onChange={enabled => patch("reasoning", enabled ? "on" : "off")} disabled={disabled} meta={readout("reasoning")} description="Whether the model generates thinking. Changes apply to future messages." hint={Object.hasOwn(value, "reasoning") ? <button type="button" className="text-button" disabled={disabled} onClick={() => follow("reasoning")} title={target("reasoning").title}>Reset</button> : undefined} /> : <span className="hint">Thinking controls unavailable for this template.</span>}
    <SettingRow layout={layout} label="Response budget" htmlFor={requestedNumber("max_tokens") === -1 ? undefined : responseLimitId} help="Maximum tokens for thinking and answer together. An empty value follows compatible publisher guidance, or Workbench Auto: half the usable conversation capacity with Thinking enabled or unknown, one quarter with it disabled, after an 8% safety margin. The allowance is fixed when work first binds to the loaded model." provenance={readout("max_tokens")} hint={requestedNumber("max_tokens") === null ? "Workbench Auto is an allowance, not a guaranteed answer length." : unavailable("max_tokens")} status={status("max_tokens")} {...reset("max_tokens")}>
      {requestedNumber("max_tokens") === -1 ? <div className="model-unlimited-budget"><strong>Unlimited</strong><span className="hint">Native output limit</span><button type="button" disabled={disabled || !supported("max_tokens")} onClick={() => patch("max_tokens", 2048)}>Set budget</button></div> : <SliderField id={responseLimitId} label="Response budget" value={requestedNumber("max_tokens")} resolved={number("max_tokens")} min={descriptor("max_tokens")?.suggested_minimum ?? 256} max={descriptor("max_tokens")?.suggested_maximum ?? 32768} step={256} exact={exact("max_tokens", { min: 1, step: 1 })} unit="tokens" disabled={disabled || !supported("max_tokens")} onChange={next => next === null ? follow("max_tokens") : patch("max_tokens", next)} />}
    </SettingRow>
    <details className="technical-details response-advanced"><summary>Advanced response</summary><div className="setting-rows">
      {models || budget?.supported || Object.hasOwn(value, "reasoning_budget_tokens") ? <SettingRow layout={layout} label="Thinking limit" htmlFor={limitId} help="Maximum thinking tokens within the total response budget. No separate limit lets thinking use the total response allowance. Default follows the model." provenance={readout("reasoning_budget_tokens")} hint={unavailable("reasoning_budget_tokens")} status={status("reasoning_budget_tokens")} {...reset("reasoning_budget_tokens")}>{models ? <div className="thinking-limit-control"><select aria-label="Thinking limit mode" value={limitMode} disabled={disabled || budget?.supported !== true} onChange={event => {
        if (!event.target.value) follow("reasoning_budget_tokens");
        else if (event.target.value === "unlimited") patch("reasoning_budget_tokens", -1);
        else { const inherited = number("reasoning_budget_tokens"); patch("reasoning_budget_tokens", inherited != null && inherited >= 0 ? inherited : 1024); }
      }}><option value="">Default</option><option value="unlimited">No separate limit</option><option value="custom">Custom</option></select><NumberField id={limitId} label="Thinking limit" {...exact("reasoning_budget_tokens", { min: 0, step: 1 })} min={Math.max(0, exact("reasoning_budget_tokens").min ?? 0)} unit="tokens" value={limitValue !== null && limitValue >= 0 ? limitValue : null} placeholder={limitMode === "unlimited" || limitValue === null && number("reasoning_budget_tokens") === -1 ? "No limit" : number("reasoning_budget_tokens") == null ? "Automatic" : String(number("reasoning_budget_tokens"))} disabled={disabled || budget?.supported !== true} onChange={next => next === null ? follow("reasoning_budget_tokens") : patch("reasoning_budget_tokens", next)} /></div> : <NumberField id={limitId} label="Thinking limit" {...exact("reasoning_budget_tokens", { min: 0, step: 1 })} unit="tokens" value={limitValue} placeholder={number("reasoning_budget_tokens") == null ? "Automatic" : String(number("reasoning_budget_tokens"))} disabled={disabled || budget?.supported !== true} onChange={next => next === null ? follow("reasoning_budget_tokens") : patch("reasoning_budget_tokens", next)} />}</SettingRow> : null}
      {models ? <SegmentedChoice layout={layout} label="Keep thinking history" value={value.reasoning_preserve === true ? "keep" : value.reasoning_preserve === false ? "drop" : ""} options={[{ value: "", label: "Default" }, { value: "keep", label: "Keep" }, { value: "drop", label: "Drop" }]} onChange={next => next ? patch("reasoning_preserve", next === "keep") : follow("reasoning_preserve")} disabled={disabled || history?.supported !== true} meta={readout("reasoning_preserve")} description="Include earlier thinking in later messages. It uses conversation capacity alongside your messages and the model's answers." hint={unavailable("reasoning_preserve")} status={status("reasoning_preserve")} {...reset("reasoning_preserve")} /> : history?.supported && current("reasoning_preserve") == null ? <SegmentedChoice label="Keep thinking history" value={value.reasoning_preserve === true ? "keep" : value.reasoning_preserve === false ? "drop" : ""} options={[{ value: "", label: "Default" }, { value: "keep", label: "Keep" }, { value: "drop", label: "Drop" }]} onChange={next => next ? patch("reasoning_preserve", next === "keep") : follow("reasoning_preserve")} disabled={disabled} meta={readout("reasoning_preserve")} description="Include earlier thinking in later messages. It uses conversation capacity alongside your messages and the model's answers." hint="The template's default is not reported." {...reset("reasoning_preserve")} /> : history?.supported ? <CompactSwitch label="Keep thinking history" checked={current("reasoning_preserve") === true} onChange={enabled => patch("reasoning_preserve", enabled)} disabled={disabled} meta={readout("reasoning_preserve")} description="Include earlier thinking in later messages. It uses conversation capacity alongside your messages and the model's answers." hint={Object.hasOwn(value, "reasoning_preserve") ? <button type="button" className="text-button" disabled={disabled} onClick={() => follow("reasoning_preserve")}>Reset</button> : undefined} /> : null}
      {models ? <SettingRow layout={layout} label="Thinking format" htmlFor="model-response-reasoning-format" help="How thinking is separated from the answer. No separation keeps raw output; it does not disable thinking." provenance={readout("reasoning_format")} hint={unavailable("reasoning_format")} status={status("reasoning_format")} {...reset("reasoning_format")}><select id="model-response-reasoning-format" value={formatValue} disabled={disabled || !supported("reasoning_format")} onChange={event => event.target.value ? patch("reasoning_format", event.target.value) : follow("reasoning_format")}><option value="">Default</option>{formatOptions.map(item => <option key={String(item.value)} value={String(item.value)}>{item.value === "none" ? "No separation" : item.label}</option>)}{formatValue && !formatOptions.some(item => item.value === formatValue) ? <option value={formatValue}>{formatValue} · saved setting</option> : null}</select></SettingRow> : null}
    </div></details>
  </div>;
}
