import { NumberField, SegmentedChoice, SettingRow, type SettingLayout } from "./CompactControls";
import { defaultSettingDisplay, effectiveSettingDisplay, type EffectiveSetting } from "./effectiveSettings";
import type { BundleConfigurationOptions } from "./types";

/** Render resolved values without writing an override merely to display them. */
export function ResponseSettingsEditor({ value, onChange, facts, presentationFacts, options, disabled = false, inheritance = "layer", loading = false, part = "thinking", layout = "default" }: {
  value: Record<string, unknown>; onChange: (value: Record<string, unknown>) => void;
  facts: Record<string, EffectiveSetting>; presentationFacts?: Record<string, EffectiveSetting>; options: BundleConfigurationOptions | null; disabled?: boolean; inheritance?: "layer" | "model"; loading?: boolean;
  part?: "thinking" | "thinking-only" | "sampling"; layout?: SettingLayout;
}) {
  const patch = (key: string, next: unknown) => onChange({ ...value, [key]: next });
  const follow = (key: string) => { const next = { ...value }; delete next[key]; onChange(next); };
  const descriptor = (key: string) => options?.per_request_defaults[key];
  const fact = (key: string) => facts[`per_request.${key}`] ?? facts[key];
  const presentation = (key: string) => fact(key) ?? presentationFacts?.[`per_request.${key}`] ?? presentationFacts?.[key];
  const current = (key: string) => Object.hasOwn(value, key) ? value[key] : presentation(key)?.known ? presentation(key)?.value : descriptor(key)?.applied ?? descriptor(key)?.default_value ?? null;
  const number = (key: string, fallback: number | null = null) => typeof current(key) === "number" ? Number(current(key)) : fallback;
  const target = (key: string) => defaultSettingDisplay(presentation(key), inheritance === "model" ? "model" : "configuration", key);
  const reset = (key: string) => ({ onReset: Object.hasOwn(value, key) && !disabled ? () => follow(key) : undefined, resetLabel: "Reset", resetTitle: target(key).title });
  const supported = (key: string) => descriptor(key)?.supported !== false;
  const readout = (key: string) => {
    if (part === "thinking-only") return undefined;
    const shown = Object.hasOwn(value, key) ? { value: value[key], source: "Set value", known: true, inherited: false, requires_reload: false } : presentation(key);
    const display = effectiveSettingDisplay(shown, false, key);
    return <span className="model-effective-readout"><strong>{display.value}</strong>{display.source ? ` · ${loading && !Object.hasOwn(value, key) ? "Last checked" : display.source}` : ""}</span>;
  };
  const help = (key: string, description: string, paths?: string[]) => <>
    <span>{description}</span>
    {(paths ?? [descriptor(key)?.request_path ?? key]).map(path => <code key={path}>{path}</code>)}
    <span>Applies to future messages.</span>
  </>;
  const row = (key: string) => ({ layout, provenance: readout(key), hint: descriptor(key)?.supported === false ? descriptor(key)?.description : undefined, status: loading ? "Checking…" : undefined, ...reset(key) });
  const exact = (key: string, fallback: { min?: number; max?: number; step?: number | "any" } = {}) => ({
    min: descriptor(key)?.minimum ?? fallback.min,
    max: descriptor(key)?.maximum ?? fallback.max,
    step: descriptor(key)?.domain === "integer" || fallback.step === 1 ? 1 : "any" as const,
  });
  if (part === "sampling") {
    const sampling: Array<{ key: string; label: string; min?: number; max?: number; step?: number; help: string }> = [
      { key: "temperature", label: "Temperature", min: 0, help: "Higher values give more varied replies; lower values are more focused." },
      { key: "top_p", label: "Top P", min: 0, max: 1, help: "Samples from the smallest set of tokens whose probability adds up to this value." },
      { key: "top_k", label: "Top K", min: 0, step: 1, help: "Samples from this many of the most likely tokens. 0 turns the limit off." },
      { key: "min_p", label: "Min P", min: 0, max: 1, help: "Drops tokens less likely than this share of the most likely token." },
      { key: "presence_penalty", label: "Presence penalty", help: "Encourages new topics by penalising tokens already used." },
      { key: "repeat_penalty", label: "Repetition penalty", min: 0, help: "Discourages repeating recent tokens. 1 turns it off." },
      { key: "frequency_penalty", label: "Frequency penalty", help: "Penalises tokens in proportion to how often they appear." },
    ];
    return <section className="response-sampling" aria-label="Sampling"><h4>Sampling</h4><div className="response-sampling-grid">{sampling.map(item => {
      const bounds = exact(item.key, item);
      return <SettingRow key={item.key} className="sampling-setting" label={item.label} htmlFor={`model-response-${item.key}`} help={help(item.key, item.help)} {...row(item.key)}>
        <NumberField id={`model-response-${item.key}`} label={item.label} value={number(item.key)} {...bounds} disabled={disabled || !supported(item.key)} onChange={next => next === null ? follow(item.key) : patch(item.key, next)} />
      </SettingRow>;
    })}</div>{descriptor("typical_p") || descriptor("seed") || Object.hasOwn(value, "typical_p") || Object.hasOwn(value, "seed") ? <details className="technical-details"><summary>Advanced sampling</summary><div className="setting-rows">
      {[{ key: "typical_p", label: "Typical P", help: "Limits sampling to tokens with typical information content. 1 turns it off." }, { key: "seed", label: "Seed", help: "The random sampling seed. -1 chooses a random seed for each request." }].map(item => <SettingRow key={item.key} label={item.label} htmlFor={`model-response-${item.key}`} help={help(item.key, item.help)} {...row(item.key)}><NumberField id={`model-response-${item.key}`} label={item.label} value={number(item.key)} {...exact(item.key)} disabled={disabled || !supported(item.key)} onChange={next => next === null ? follow(item.key) : patch(item.key, next)} /></SettingRow>)}
    </div></details> : null}</section>;
  }
  const modes = descriptor("reasoning"), efforts = descriptor("reasoning_effort"), budget = descriptor("reasoning_budget_tokens");
  const effortOptions = (efforts?.options ?? []).filter(item => typeof item.value === "string" && !["auto", "default"].includes(String(item.value)));
  const hasEfforts = efforts?.supported !== false && effortOptions.length > 0;
  const thinkingValue = current("reasoning") === "off" || current("reasoning") === false ? "off" : hasEfforts ? String(current("reasoning_effort") ?? "") : current("reasoning") === true ? "on" : String(current("reasoning") ?? "");
  const thinkingOptions = hasEfforts ? [...(modes?.supported !== false ? [{ value: "off", label: "Off" }] : []), ...effortOptions.map(item => ({ value: String(item.value), label: item.label }))] : [{ value: "on", label: "On" }, { value: "off", label: "Off" }];
  if (!thinkingValue) thinkingOptions.unshift({ value: "", label: "Not reported" });
  else if (!thinkingOptions.some(item => item.value === thinkingValue)) thinkingOptions.push({ value: thinkingValue, label: thinkingValue });
  const thinkingReset = Object.hasOwn(value, "reasoning") || Object.hasOwn(value, "reasoning_effort");
  const responseLimitId = inheritance === "model" ? "model-response-max_tokens" : "chat-response-max_tokens";
  const outputLimit = number("max_tokens", -1)!;
  const thinkingLimit = number("reasoning_budget_tokens", -1)!;
  const limitId = `response-thinking-budget-${inheritance}`;
  const historyValue = current("reasoning_preserve") === true ? "keep" : current("reasoning_preserve") === false ? "drop" : "";
  const historyOptions = [...(!historyValue ? [{ value: "", label: "Not reported" }] : []), { value: "keep", label: "Keep" }, { value: "drop", label: "Drop" }];
  const formatValue = String(current("reasoning_format") ?? "auto");
  const formatOptions = (descriptor("reasoning_format")?.options ?? [{ value: "auto", label: "Auto" }, { value: "none", label: "No separation" }]).filter(item => typeof item.value === "string" && item.value !== "default");
  const thinkingControl = <SegmentedChoice layout={layout} label="Thinking" value={thinkingValue} options={thinkingOptions} meta={readout(hasEfforts && thinkingValue !== "off" ? "reasoning_effort" : "reasoning")} description={help("reasoning", "Whether the model generates thinking. Levels follow its template. Changing Thinking keeps sampling unchanged.", [modes?.request_path ?? "chat_template_kwargs.enable_thinking", ...(hasEfforts ? [efforts?.request_path ?? "reasoning_effort"] : [])])} status={loading ? "Checking…" : undefined} disabled={disabled || !hasEfforts && modes?.supported === false} hint={!supported(hasEfforts ? "reasoning_effort" : "reasoning") ? descriptor(hasEfforts ? "reasoning_effort" : "reasoning")?.description : undefined} onChange={next => {
      const updated = { ...value }; delete updated.reasoning; delete updated.reasoning_effort;
      if (next === "off" || !hasEfforts && next === "on") updated.reasoning = next;
      else if (next) { if (modes?.supported !== false) updated.reasoning = "on"; updated.reasoning_effort = next; }
      onChange(updated);
    }} onReset={!disabled && thinkingReset ? () => { const next = { ...value }; delete next.reasoning; delete next.reasoning_effort; onChange(next); } : undefined} resetLabel="Reset" resetTitle={target(hasEfforts ? "reasoning_effort" : "reasoning").title} />;
  if (part === "thinking-only") return <div className="response-settings-editor setting-rows">{thinkingControl}</div>;
  return <div className="response-settings-editor setting-rows">
    {thinkingControl}
    <SegmentedChoice label="Thinking history" value={historyValue} options={historyOptions} onChange={next => next ? patch("reasoning_preserve", next === "keep") : follow("reasoning_preserve")} disabled={disabled || !supported("reasoning_preserve")} description={help("reasoning_preserve", "Include earlier thinking in later messages. It shares Context with messages and answers.", [descriptor("reasoning_preserve")?.request_path ?? "chat_template_kwargs.preserve_reasoning"])} meta={readout("reasoning_preserve")} layout={layout} status={loading ? "Checking…" : undefined} {...reset("reasoning_preserve")} />
    <SettingRow label="Maximum output tokens" htmlFor={responseLimitId} help={help("max_tokens", "Maximum tokens for thinking and answer together. Unlimited adds no output ceiling; the loaded Context still bounds the request. A deliberate finite limit is reserved by Deep Agents.")} {...row("max_tokens")}>
      <div className="output-limit-control"><select aria-label="Maximum output tokens mode" value={outputLimit === -1 ? "unlimited" : "custom"} disabled={disabled || !supported("max_tokens")} onChange={event => patch("max_tokens", event.target.value === "unlimited" ? -1 : outputLimit >= 0 ? outputLimit : 2048)}><option value="unlimited">Unlimited</option><option value="custom">Limit</option></select><span className="output-limit-exact" data-inactive={outputLimit === -1 || undefined}><NumberField id={responseLimitId} label="Maximum output tokens" value={outputLimit >= 0 ? outputLimit : null} placeholder={outputLimit === -1 ? "No limit" : undefined} {...exact("max_tokens", { min: 0, step: 1 })} min={0} unit="tokens" disabled={disabled || !supported("max_tokens") || outputLimit === -1} onChange={next => next === null ? follow("max_tokens") : patch("max_tokens", next)} /></span></div>
    </SettingRow>
    <details className="technical-details response-advanced"><summary>Advanced generation</summary><div className="setting-rows">
      <SettingRow label="Thinking limit" htmlFor={limitId} help={help("reasoning_budget_tokens", "Maximum thinking tokens within the output allowance. No separate limit lets thinking use available output.")} {...row("reasoning_budget_tokens")}>
        <div className="thinking-limit-control"><select aria-label="Thinking limit mode" value={thinkingLimit === -1 ? "unlimited" : "custom"} disabled={disabled || budget?.supported === false} onChange={event => patch("reasoning_budget_tokens", event.target.value === "unlimited" ? -1 : thinkingLimit >= 0 ? thinkingLimit : 1024)}><option value="unlimited">No separate limit</option><option value="custom">Limit</option></select><NumberField id={limitId} label="Thinking limit" {...exact("reasoning_budget_tokens", { min: 0, step: 1 })} min={0} unit="tokens" value={thinkingLimit >= 0 ? thinkingLimit : null} placeholder={thinkingLimit === -1 ? "No limit" : undefined} disabled={disabled || budget?.supported === false} onChange={next => next === null ? follow("reasoning_budget_tokens") : patch("reasoning_budget_tokens", next)} /></div>
      </SettingRow>
      <SettingRow label="Thinking format" htmlFor="model-response-reasoning-format" help={help("reasoning_format", "How thinking is separated from the answer. No separation keeps raw output; it does not disable thinking.")} {...row("reasoning_format")}><select id="model-response-reasoning-format" value={formatValue} disabled={disabled || !supported("reasoning_format")} onChange={event => patch("reasoning_format", event.target.value)}>{formatOptions.map(item => <option key={String(item.value)} value={String(item.value)}>{item.value === "none" ? "No separation" : item.label}</option>)}{!formatOptions.some(item => item.value === formatValue) ? <option value={formatValue}>{formatValue}</option> : null}</select></SettingRow>
      {descriptor("reasoning_budget_message") || Object.hasOwn(value, "reasoning_budget_message") ? <SettingRow label="Thinking limit message" htmlFor="model-response-budget-message" help={help("reasoning_budget_message", "Message supplied to the model when its thinking budget is reached.")} {...row("reasoning_budget_message")}><input id="model-response-budget-message" value={String(current("reasoning_budget_message") ?? "")} disabled={disabled || !supported("reasoning_budget_message")} onChange={event => event.target.value ? patch("reasoning_budget_message", event.target.value) : follow("reasoning_budget_message")} /></SettingRow> : null}
    </div></details>
  </div>;
}
