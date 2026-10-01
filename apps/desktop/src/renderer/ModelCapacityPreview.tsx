import { useEffect, useRef, useState } from "react";
import { estimateModel, type ModelEstimateSelection, type ModelMemoryEstimate } from "./modelEstimateApi";
import { formatBytes } from "./display";
import { errorMessage } from "./errors";
import { NumberField, SettingRow } from "./CompactControls";

type CapacityEstimate = ModelMemoryEstimate & { basis?: string; gpu_budget_bytes?: Record<string, number | null>; ram_budget_bytes?: number | null; gpu_headroom_bytes?: number; ram_headroom_bytes?: number };
export type CapacityFit = "green" | "amber" | "red" | "unknown";
export function capacityFit(value?: CapacityEstimate): CapacityFit {
  if (!value) return "unknown";
  const ramBudget = value.ram_budget_bytes;
  if (value.ram_bytes != null && ramBudget != null && value.ram_bytes > ramBudget) return "red";
  const devices = (value.devices ?? []).filter(device => device.id !== "Host");
  let allocationKnown = value.gpu_bytes === 0;
  for (const device of devices) {
    const id = String(device.id ?? ""), budget = value.gpu_budget_bytes?.[id];
    const total = typeof device.total_bytes === "number" ? device.total_bytes : typeof device.known_total_bytes === "number" ? device.known_total_bytes : null;
    if (budget != null && total != null && total > budget) return "red";
  }
  if (devices.length) allocationKnown = devices.every(device => value.gpu_budget_bytes?.[String(device.id ?? "")] != null && typeof device.total_bytes === "number");
  if (value.completeness !== "complete" || value.runtime_overhead_bytes == null || value.gpu_bytes == null || value.ram_bytes == null || value.weights_bytes == null || value.kv_bytes == null || ramBudget == null || !allocationKnown) return "unknown";
  const gpuWeights = devices.reduce((sum, device) => sum + (typeof device.weights_bytes === "number" ? device.weights_bytes : 0), 0);
  return gpuWeights >= value.weights_bytes * .99 ? "green" : "amber";
}

function advisoryStartupSendable(startup: Record<string, unknown>) {
  return Object.entries(startup).every(([key, value]) => {
    if (typeof value !== "number" || !Number.isFinite(value)) return typeof value !== "number";
    return key !== "ctx_size" || Number.isInteger(value) && value >= 1;
  });
}

/** Advisory state never reaches an import or saved configuration request. */
export function useCapacityEstimates(selections: Array<{ key: string; selection: ModelEstimateSelection }>, startup: Record<string, unknown>, active: boolean) {
  const [answers, setAnswers] = useState<Record<string, CapacityEstimate>>({});
  const [error, setError] = useState("");
  const identity = JSON.stringify([selections, startup]);
  const owner = useRef(identity); owner.current = identity;
  useEffect(() => {
    if (!active) return;
    if (!advisoryStartupSendable(startup)) { setAnswers({}); setError("Check the selected launch settings."); return; }
    const controller = new AbortController(); setAnswers({}); setError("");
    const queue = [...selections];
    async function worker() {
      for (;;) {
        const item = queue.shift(); if (!item || controller.signal.aborted) return;
        try { const answer = await estimateModel({ ...item.selection, startup, basis: "capacity", method: "metadata" }, false, controller.signal); if (!controller.signal.aborted && owner.current === identity) setAnswers(current => ({ ...current, [item.key]: answer })); }
        catch (failure) { if (!controller.signal.aborted && owner.current === identity) setError(errorMessage(failure)); }
      }
    }
    const timer = window.setTimeout(() => { void Promise.all([worker(), worker(), worker()]); }, 200);
    return () => { window.clearTimeout(timer); controller.abort(); };
  }, [identity, active]);
  return { answers, error };
}

export function ModelCapacityPreview({ estimate, startup, onChange, error, pending = true }: { estimate?: CapacityEstimate; startup: Record<string, unknown>; onChange: (value: Record<string, unknown>) => void; error?: string; pending?: boolean }) {
  const patch = (key: string, value: unknown) => { const next = { ...startup }; if (value === "" || value == null) delete next[key]; else next[key] = value; onChange(next); };
  const fit = capacityFit(estimate);
  const size = (bytes?: number | null) => bytes == null ? "—" : formatBytes(bytes);
  const summary = estimate ? estimate.gpu_bytes != null && estimate.ram_bytes != null ? "≈ " + size(estimate.gpu_bytes + estimate.ram_bytes) + (estimate.completeness === "complete" ? "" : " known subtotal") : "—" : error || !pending ? "—" : "Estimating…";
  const number = (key: string, label: string, flag: string, min: number, defaultValue?: number) => <SettingRow layout="models" label={label} htmlFor={"preview-" + key} help={<><span>Memory preview only.</span><code>{flag}</code></>} onReset={Object.hasOwn(startup, key) ? () => patch(key, null) : undefined}><NumberField id={"preview-" + key} label={label} min={min} step={1} value={typeof startup[key] === "number" ? Number(startup[key]) : null} placeholder={defaultValue == null ? "" : String(defaultValue)} onChange={next => patch(key, next)} /></SettingRow>;
  const choice = (key: string, label: string, flag: string, options: string[]) => <SettingRow layout="models" label={label} htmlFor={"preview-" + key} help={<><span>Memory preview only.</span><code>{flag}</code></>} onReset={Object.hasOwn(startup, key) ? () => patch(key, null) : undefined}><select id={"preview-" + key} value={String(startup[key] ?? "")} onChange={event => patch(key, ["kv_offload", "swa_full"].includes(key) ? event.target.value === "" ? null : event.target.value === "true" : key === "n_gpu_layers" && event.target.value === "0" ? 0 : event.target.value)}><option value="">Default</option>{options.map(value => <option key={value} value={value}>{value === "true" ? key === "kv_offload" ? "GPU" : "On" : value === "false" ? key === "kv_offload" ? "CPU" : "Off" : value === "none" ? "Off" : value === "draft-mtp" ? "On" : value}</option>)}</select></SettingRow>;
  return <section className="model-capacity-preview" aria-label="Memory preview">
    <h3><i className="model-fit-dot" data-fit={fit} />Memory preview <small>{summary}</small></h3>
    <p className="hint">{!estimate && !error && !pending ? "Select a quantization to preview memory." : "Total hardware capacity · advisory"}</p>
    <dl className="model-capacity-totals"><div><dt>GPU</dt><dd>{size(estimate?.gpu_bytes)}</dd></div><div><dt>RAM</dt><dd>{size(estimate?.ram_bytes)}</dd></div></dl>
    <div className="setting-rows">
      {number("ctx_size", "Context", "--ctx-size", 1, estimate?.context_maximum ?? undefined)}
      {choice("cache_type_k", "K precision", "--cache-type-k", ["f32", "f16", "bf16", "q8_0", "q4_0", "q4_1", "q5_0", "q5_1", "iq4_nl"])}
      {choice("cache_type_v", "V precision", "--cache-type-v", ["f32", "f16", "bf16", "q8_0", "q4_0", "q4_1", "q5_0", "q5_1", "iq4_nl"])}
      {choice("n_gpu_layers", "GPU layers", "--n-gpu-layers", ["auto", "all", "0"])}
      {choice("kv_offload", "Cache placement", "--kv-offload", ["true", "false"])}
      {choice("flash_attn", "Flash attention", "--flash-attn", ["auto", "on", "off"])}
      {(estimate?.builtin_mtp || estimate?.mtp_draft_files?.length) ? choice("spec_type", "MTP", "--spec-type", ["none", "draft-mtp"]) : null}
      <details className="models-disclosure"><summary>Processing <span className="models-show-hide" /></summary>{number("batch_size", "Prompt batch", "--batch-size", 1, 2048)}{number("ubatch_size", "Physical batch", "--ubatch-size", 0, 512)}{number("parallel", "Parallel slots", "--parallel", -1, -1)}{startup.spec_type === "draft-mtp" ? number("spec_draft_n_max", "Draft tokens", "--spec-draft-n-max", 1, 3) : null}</details>
    </div>
    {error ? <p className="hint" role="status">Estimate unavailable · {error}</p> : null}
    <details className="models-disclosure"><summary>Estimate details <span className="models-show-hide" /></summary><p className="hint">Weights {size(estimate?.weights_bytes)} · cache/state {size(estimate?.kv_bytes)} · compute {size(estimate?.runtime_overhead_bytes)}</p><p className="hint">{estimate?.hardware.gpu_devices?.map(device => device.name + " " + size(device.total_bytes)).join(" · ") ?? "GPU unknown"} · RAM {size(estimate?.hardware.ram_total_bytes)}</p><p className="hint">Headroom: GPU {size(estimate?.gpu_headroom_bytes)} · RAM {size(estimate?.ram_headroom_bytes)}. Available memory and loaded models do not affect these colours.</p>{[...(estimate?.assumptions ?? []), ...(estimate?.unknown_reasons ?? [])].map((text, index) => <p className="hint" key={index}>{text}</p>)}</details>
  </section>;
}
