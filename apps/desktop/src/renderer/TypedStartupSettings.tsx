import { SettingRow } from "./CompactControls";
import { PathBrowseButton } from "./PathField";
import type { BundleConfigurationOptions } from "./types";

const extras = [
  { key: "chat_template", label: "Template name", flag: "--chat-template", file: false },
  { key: "chat_template_file", label: "Template file", flag: "--chat-template-file", file: true },
  { key: "spec_draft_model", label: "Draft model", flag: "--spec-draft-model", file: true },
] as const;

/** Named controls cover the supported fields formerly entered as startup JSON. */
export function TypedStartupSettings({ value, onChange, options, disabled, onError }: { value: string; onChange: (value: string) => void; options: BundleConfigurationOptions | null; disabled: boolean; onError: (message: string) => void }) {
  let settings: Record<string, unknown> = {};
  try { settings = value ? JSON.parse(value) : {}; } catch { /* An old invalid draft remains visible as a validation failure at Save. */ }
  function set(key: string, next: unknown) { const updated = { ...settings }; if (next === "" || next == null) delete updated[key]; else updated[key] = next; onChange(Object.keys(updated).length ? JSON.stringify(updated) : ""); }
  let kwargs: Record<string, unknown> = {};
  try { const input = settings.chat_template_kwargs; kwargs = typeof input === "string" ? JSON.parse(input) : input && typeof input === "object" ? input as Record<string, unknown> : {}; } catch { /* Show no invented values. */ }
  const argumentsList = Object.entries(kwargs);
  function argumentsChanged(entries: Array<[string, unknown]>) {
    const duplicate = entries.find(([key]) => ["enable_thinking", "thinking", "reasoning", "reasoning_effort", "preserve_reasoning", "reasoning_preserve"].includes(key.trim()));
    if (duplicate) { onError("Use the Thinking and history controls for " + duplicate[0] + "."); return; }
    set("chat_template_kwargs", entries.length ? JSON.stringify(Object.fromEntries(entries.filter(([key]) => key.trim()))) : undefined); }
  return <div className="setting-rows model-extra-controls">
    {extras.map(item => <SettingRow key={item.key} layout="models" label={item.label} htmlFor={`model-extra-${item.key}`} help={<><span>{options?.startup_defaults[item.key]?.description ?? "Optional setting for the next load."}</span><code>{item.flag}</code></>} onReset={!disabled && Object.hasOwn(settings, item.key) ? () => set(item.key, undefined) : undefined}>
      <div className="model-path-control"><input id={`model-extra-${item.key}`} value={String(settings[item.key] ?? "")} disabled={disabled} onChange={event => set(item.key, event.target.value)} />{item.file ? <PathBrowseButton kind="file" label={`Choose ${item.label.toLowerCase()}`} icon="files" disabled={disabled} onPicked={path => set(item.key, path)} onError={failure => onError(String(failure))} /> : null}</div>
    </SettingRow>)}
    <details className="models-disclosure"><summary>Template arguments</summary><p className="hint">Thinking and history use the Generation controls above.</p>{argumentsList.map(([key, entry], index) => <div className="model-template-argument" key={index}><input aria-label={`Template argument name ${index + 1}`} value={key} disabled={disabled} onChange={event => argumentsChanged(argumentsList.map((pair, i) => i === index ? [event.target.value, pair[1]] : pair))} /><select aria-label={`Template argument type ${index + 1}`} value={typeof entry} disabled={disabled} onChange={event => argumentsChanged(argumentsList.map((pair, i) => i === index ? [pair[0], event.target.value === "boolean" ? false : event.target.value === "number" ? 0 : ""] : pair))}><option value="string">Text</option><option value="number">Number</option><option value="boolean">On / Off</option></select>{typeof entry === "boolean" ? <select aria-label={`Template argument value ${index + 1}`} value={String(entry)} disabled={disabled} onChange={event => argumentsChanged(argumentsList.map((pair, i) => i === index ? [pair[0], event.target.value === "true"] : pair))}><option value="true">On</option><option value="false">Off</option></select> : <input aria-label={`Template argument value ${index + 1}`} type={typeof entry === "number" ? "number" : "text"} step="any" value={String(entry)} disabled={disabled} onChange={event => argumentsChanged(argumentsList.map((pair, i) => i === index ? [pair[0], typeof entry === "number" ? Number(event.target.value) : event.target.value] : pair))} />}<button type="button" className="icon-button" aria-label={`Remove template argument ${index + 1}`} disabled={disabled} onClick={() => argumentsChanged(argumentsList.filter((_, i) => i !== index))}>×</button></div>)}<button type="button" className="text-button" disabled={disabled} onClick={() => argumentsChanged([...argumentsList, [`argument_${argumentsList.length + 1}`, ""]])}>Add argument</button></details>
  </div>;
}
