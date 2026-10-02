import { useEffect, useRef, useState } from "react";
import { api } from "./api";
import { ChoiceControl, ContextSlider, tokenLabel } from "./ModelControls";
import { SettingRow } from "./CompactControls";
import { errorMessage } from "./errors";
import { labDescriptor, labSetting } from "./labPresentation";
import type { LabConfiguration } from "./labTypes";
import type { BundleConfigurationOptions, ModelBundle, RunProfile } from "./types";

export interface LabSelection extends LabConfiguration { key: string; bundleId: string; options: BundleConfigurationOptions | null; ready: boolean }
export const newLabSelection = (): LabSelection => ({ key: crypto.randomUUID(), bundleId: "", configuration_id: "", startup: {}, concurrent_requests: 1, options: null, ready: false });

export function LabConfigurationControls({ selection, models, profiles, disabled, concurrent, detailed, index, onChange, onRemove }: {
  selection: LabSelection; models: ModelBundle[]; profiles: RunProfile[]; disabled: boolean; concurrent: boolean; detailed: boolean; index: number;
  onChange: (value: LabSelection) => void; onRemove?: () => void;
}) {
  const [error, setError] = useState("");
  const [revision, setRevision] = useState(0);
  const latest = useRef({ selection, onChange }); latest.current = { selection, onChange };
  const profile = profiles.find(item => item.id === selection.configuration_id);
  const configurations = profiles.filter(item => item.bundle_id === selection.bundleId);
  const serialized = JSON.stringify(selection.startup);
  useEffect(() => {
    if (!selection.bundleId || !selection.configuration_id) return;
    let disposed = false;
    setError("");
    void api.modelConfiguration(selection.bundleId, undefined, false, { configuration_id: selection.configuration_id, startup: selection.startup }).then(options => {
      if (!disposed) latest.current.onChange({ ...latest.current.selection, options, ready: true });
    }).catch(reason => { if (!disposed) setError(errorMessage(reason)); });
    return () => { disposed = true; };
  }, [selection.bundleId, selection.configuration_id, serialized, revision]);

  function edit(key: string, value: unknown) {
    onChange({ ...selection, startup: { ...selection.startup, [key]: value }, ready: false });
  }
  function field(key: string, label: string) {
    const descriptor = labDescriptor(selection.options, key);
    if (!descriptor || descriptor.supported === false) return null;
    const value = labSetting(profile, selection.startup, selection.options, key);
    if (key === "ctx_size") {
      const contextMode = value === 0 ? "full" : typeof value === "number" && value > 0 ? "fixed" : "auto";
      const shown = contextMode === "full" ? descriptor.maximum : typeof value === "number" && value > 0 ? value : null;
      return <SettingRow label="Context" htmlFor={`lab-${selection.key}-ctx_size`} help={descriptor.description}><div className="lab-context-control"><select aria-label={index ? `Context mode ${index + 1}` : "Context mode"} value={contextMode} disabled={disabled} onChange={event => edit("ctx_size", event.target.value === "auto" ? "auto" : event.target.value === "full" ? 0 : Math.min(8192, descriptor.maximum ?? 8192))}><option value="auto">Auto</option><option value="fixed">Fixed</option><option value="full" disabled={!descriptor.maximum}>Full</option></select><ContextSlider id={`lab-${selection.key}-ctx_size`} label={index ? `Context ${index + 1}` : "Context"} value={shown} maximum={descriptor.maximum} unknownLabel="Auto" disabled={disabled} onChange={tokens => edit("ctx_size", tokens)} /></div></SettingRow>;
    }
    const options = descriptor.options.filter(option => option.value !== null && (typeof option.value !== "number" || descriptor.maximum == null || option.value <= descriptor.maximum));
    const shown = key === "n_gpu_layers" && value === -1 ? "auto" : String(value ?? "");
    return <SettingRow key={key} label={label} htmlFor={`lab-${selection.key}-${key}`} help={descriptor.description}>
      <ChoiceControl id={`lab-${selection.key}-${key}`} label={label} value={shown} options={options.map(option => ({ value: String(option.value), label: key === "ctx_size" && typeof option.value === "number" && option.value > 0 ? tokenLabel(option.value) : option.label }))}
        disabled={disabled || !selection.options} custom={false} segmented={false} onChange={next => {
          const option = options.find(item => String(item.value) === next);
          if (option) edit(key, option.value);
        }} />
    </SettingRow>;
  }
  const declaredRequests = selection.options?.startup_defaults.parallel?.options.map(option => option.value).filter((value): value is number => typeof value === "number" && value > 0) ?? [];
  const requestChoices = declaredRequests.length ? declaredRequests : [1, 2, 4, 8];
  return <section className="lab-configuration" aria-label={`Benchmark configuration ${index + 1}`}>
    {concurrent ? <div className="section-heading"><h3>Configuration {index + 1}</h3>{onRemove ? <button type="button" className="text-button" disabled={disabled} onClick={onRemove}>Remove</button> : null}</div> : null}
    <label>Model<select aria-label={index ? `Lab model ${index + 1}` : "Lab model"} value={selection.bundleId} disabled={disabled} onChange={event => {
      const bundleId = event.target.value;
      const model = models.find(item => item.id === bundleId);
      const saved = profiles.filter(item => item.bundle_id === bundleId);
      const configuration_id = saved.find(item => item.id === model?.default_configuration_id)?.id ?? "";
      onChange({ ...selection, bundleId, configuration_id, startup: {}, options: null, ready: false });
    }}><option value="">Choose an installed model…</option>{models.map(model => <option key={model.id} value={model.id}>{model.display_name}</option>)}</select></label>
    <label>Configuration<select aria-label={index ? `Lab configuration ${index + 1}` : "Lab configuration"} value={selection.configuration_id} disabled={disabled || !selection.bundleId} onChange={event => onChange({ ...selection, configuration_id: event.target.value, startup: {}, options: null, ready: false })}>
      <option value="">{configurations.length ? "Choose a saved setup" : selection.bundleId ? "No saved configurations" : "Choose a model first"}</option>
      {configurations.map(item => <option key={item.id} value={item.id}>{item.display_name}</option>)}
    </select></label>
    {error ? <div className="notice notice-error" role="alert">Model choices could not load: {error} <button type="button" className="text-button" onClick={() => setRevision(value => value + 1)}>Retry choices</button></div> : null}
    {selection.configuration_id && !selection.options && !error ? <p className="hint">Reading legal model choices…</p> : null}
    {concurrent ? <SettingRow label="Concurrent requests" htmlFor={`lab-${selection.key}-requests`} help="Requests run together on this configuration. These are the same request counts offered in Models; context is shared between requests."><select id={`lab-${selection.key}-requests`} aria-label={index ? `Concurrent requests ${index + 1}` : "Concurrent requests"} value={selection.concurrent_requests} disabled={disabled} onChange={event => onChange({ ...selection, concurrent_requests: Number(event.target.value) })}>{requestChoices.map(value => <option key={value} value={value}>{value}</option>)}</select></SettingRow> : null}
    {selection.options ? <div className="lab-load-controls">{field("ctx_size", "Context")}{detailed ? <details><summary>Load controls</summary><div className="setting-rows">{field("n_gpu_layers", "GPU layers")}{field("fit", "Memory fitting")}{field("flash_attn", "Flash attention")}{field("cache_type_k", "Key cache")}{field("cache_type_v", "Value cache")}{field("spec_type", "Speculative decoding")}{field("spec_draft_n_max", "Draft tokens")}</div></details> : null}</div> : null}
  </section>;
}
