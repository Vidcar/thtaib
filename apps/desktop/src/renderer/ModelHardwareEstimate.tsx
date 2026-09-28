import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { formatBytes } from "./display";
import { errorMessage } from "./errors";
import { settingValue } from "./effectiveSettings";
import { estimateModel, type ModelEstimateSelection, type ModelMemoryEstimate } from "./modelEstimateApi";
import "./ModelHardwareEstimate.css";

const bytes = (value: number | null | undefined) => value == null ? "Unknown" : formatBytes(value);

type ModelHardwareEstimateProps = {
  selection: ModelEstimateSelection;
  onEstimate?: (estimate: ModelMemoryEstimate) => void;
  active?: boolean;
  compact?: boolean;
  onDetails?: () => void;
  detailsTarget?: HTMLElement | null;
};

type EstimateAnswer = { key: string; epoch: number; data?: ModelMemoryEstimate; error?: string };

function gpuShortage(result?: ModelMemoryEstimate): number {
  const devices = result?.hardware.gpu_devices ?? [];
  const available = devices.length === 1 && !result?.hardware.stale ? devices[0].available_bytes : null;
  return available != null && result?.gpu_bytes != null && result.completeness === "complete" ? Math.max(0, result.gpu_bytes - available) : 0;
}

function EstimateContents({ result, expanded = false }: { result: ModelMemoryEstimate; expanded?: boolean }) {
  const devices = result.hardware.gpu_devices ?? [];
  const shortage = gpuShortage(result);
  const observed = result.observed_runtime;
  const observedStartup = observed?.startup as Record<string, unknown> | undefined;
  const observedUsage = observed?.resource_usage as { rss_bytes?: number | null } | undefined;
  const evaluated = result.evaluated_startup;
  const completeness = result.completeness ?? "partial";
  return <>
    <div className="estimate-availability" aria-label="Available memory">{devices.length ? devices.map(device => <span key={device.id}>{devices.length === 1 ? "GPU" : device.name} <strong>{bytes(device.available_bytes)} / {bytes(device.total_bytes)}</strong>{result.hardware.stale ? " · stale" : ""}</span>) : <span>GPU <strong>Not reported</strong></span>}<span>RAM <strong>{bytes(result.hardware.ram_available_bytes)} / {bytes(result.hardware.ram_total_bytes)}</strong></span><small className="hint">Available / total</small></div>
    <dl className="estimate-totals" data-completeness={completeness}><div><dt>Estimated GPU</dt><dd>{bytes(result.gpu_bytes)}</dd></div><div><dt>Estimated RAM</dt><dd>{bytes(result.ram_bytes)}</dd></div></dl>
    <div className="estimate-summary"><span>Weights <strong>{bytes(result.weights_bytes)}</strong></span><span>Cache and model state <strong>{bytes(result.kv_bytes)}</strong></span><span>Compute <strong>{bytes(result.runtime_overhead_bytes)}</strong></span>{result.projector_disk_bytes ? <span>Vision <strong>{bytes(result.projector_bytes)}</strong></span> : null}</div>
    {result.speculation_bytes != null && result.speculation_bytes > 0 ? <p className="hint">Speculation: {bytes(result.speculation_bytes)} included in the measured components.</p> : null}
    <p className="estimate-completeness hint">{completeness === "complete" ? "Selected model components measured." : completeness === "unavailable" ? "Native measurement unavailable." : "Some selected components could not be measured."} Driver, operating system and host-cache costs remain unknown.</p>
    {shortage ? <p className="estimate-shortage">At least {bytes(shortage)} above available GPU memory, before unknown dynamic costs.</p> : null}
    {result.effective_context != null ? <p className="estimate-context">Shared context pool: <strong>{result.effective_context.toLocaleString()} tokens</strong>{result.effective_parallel != null ? ` · ${result.effective_parallel} request slots` : ""}{result.effective_context_per_slot != null && result.effective_parallel !== 1 ? <small>Up to {result.effective_context_per_slot.toLocaleString()} tokens per request. Slots share the pool.</small> : null}</p> : result.context_marker != null ? <p className="hint">{result.context_marker_kind === "upper_bound" ? "Context upper bound" : "Automatic context estimate"}: {result.context_marker.toLocaleString()} tokens · dynamic costs excluded.</p> : null}
    {observed ? <p className="estimate-observed"><span>Observed</span><strong>{bytes(observedUsage?.rss_bytes)} process RAM</strong>{typeof observed.observed_at === "string" ? <small>{new Date(observed.observed_at).toLocaleTimeString()}</small> : null}</p> : <p className="hint">Observed: no matching loaded model.</p>}
    <details open={expanded || undefined}><summary>Allocation details &amp; assumptions{completeness !== "complete" ? " · incomplete" : ""}</summary>
      <p className="hint">Available memory observed {new Date(result.hardware.observed_at).toLocaleTimeString()} · {result.hardware.source}</p>
      <p className="hint">{result.source === "native_prediction" ? "Pinned native prediction" : "GGUF metadata estimate"} · {result.architecture ?? "Architecture unknown"} · calculated {new Date(result.estimated_at).toLocaleTimeString()}</p>
      {result.source === "native_prediction" && evaluated ? <p className="hint">Prediction settings: context {settingValue(evaluated.ctx_size, "ctx_size")} · GPU layers {settingValue(evaluated.n_gpu_layers, "n_gpu_layers")} · slots {settingValue(evaluated.parallel)}.</p> : null}
      {(result.devices ?? []).map((device, index) => <p key={index}>{String(device.id)}: weights {bytes(device.weights_bytes as number)} · cache and model state {bytes(device.kv_bytes as number)} · compute {bytes(device.runtime_overhead_bytes as number)}{device.projector_bytes != null ? ` · vision ${bytes(device.projector_bytes as number)}` : ""} · total {bytes(device.total_bytes as number)}</p>)}
      {[...(result.assumptions ?? []), ...(result.unknown_reasons ?? [])].map((message, index) => <p className="hint" key={index}>{message}</p>)}
      {result.plan_identity ? <p className="hint">Plan <code>{result.plan_identity.slice(0, 16)}</code> · model files {bytes(result.model_disk_bytes)}{result.projector_disk_bytes ? ` · vision file ${bytes(result.projector_disk_bytes)}` : ""}</p> : null}
      {observed ? <p className="hint">Observed loading request: context {settingValue(observedStartup?.ctx_size, "ctx_size")} · cache {settingValue(observedStartup?.kv_offload, "kv_offload")}. GPU process allocation is not reported.</p> : null}
    </details>
  </>;
}

export function ModelHardwareEstimate({ selection, onEstimate, active = true, compact = false, onDetails, detailsTarget }: ModelHardwareEstimateProps) {
  const onResult = useRef(onEstimate); onResult.current = onEstimate;
  const key = JSON.stringify(selection);
  const [epoch, setEpoch] = useState(0);
  const identity = useRef({ key, epoch, active }); identity.current = { key, epoch, active };
  const refreshRequest = useRef<{ key: string; epoch: number } | null>(null);
  const [answer, setAnswer] = useState<EstimateAnswer | null>(null);
  const [pending, setPending] = useState<{ key: string; epoch: number } | null>(null);
  const completed = answer?.key === key && answer.epoch === epoch;
  const loading = active && (!completed || pending?.key === key && pending.epoch === epoch);
  useEffect(() => {
    if (!active) return;
    const controller = new AbortController();
    setPending({ key, epoch });
    const current = () => !controller.signal.aborted && identity.current.key === key && identity.current.epoch === epoch && identity.current.active;
    const timer = window.setTimeout(() => {
      const refresh = refreshRequest.current?.key === key && refreshRequest.current?.epoch === epoch;
      refreshRequest.current = null;
      void estimateModel(JSON.parse(key) as ModelEstimateSelection, refresh, controller.signal).then(data => {
        if (current()) { setAnswer({ key, epoch, data }); setPending(null); onResult.current?.(data); }
      }).catch(failure => {
        if (current()) { setAnswer({ key, epoch, error: errorMessage(failure) }); setPending(null); }
      });
    }, selection.bundle_id ? 500 : 250);
    return () => { window.clearTimeout(timer); controller.abort(); };
  }, [key, epoch, selection.bundle_id, active]);
  const result = answer?.key === key && (!compact || completed && !loading) ? answer.data : undefined;
  const error = completed && !loading ? answer?.error : undefined;
  const refresh = () => { refreshRequest.current = { key, epoch: epoch + 1 }; setEpoch(epoch + 1); };
  const shortage = gpuShortage(result);
  const status = loading ? "Checking…" : error || result?.completeness === "unavailable" ? "Unavailable" : !result ? "Paused" : shortage ? "GPU shortfall" : result.completeness === "complete" ? "Measured" : "Partial estimate";
  const statusDetail = loading ? "Estimating memory" : error || result?.completeness === "unavailable" ? "See details" : !result ? "Open to estimate" : shortage ? `At least ${bytes(shortage)} over` : result.hardware.stale ? "Available memory stale" : "Some costs unknown";
  const value = (amount?: number | null) => loading || !result && !error ? "—" : bytes(amount);
  const refreshButton = <button type="button" className="text-button" onClick={refresh} disabled={loading || !active} aria-label="Refresh hardware estimate">Refresh</button>;
  if (compact) return <>
    <section className="model-memory-estimate model-memory-estimate-compact" aria-label="Advisory hardware estimate" aria-busy={loading} data-estimate-state={loading ? "pending" : error ? "error" : result?.completeness ?? "idle"}>
      <div className="estimate-heading"><strong>Memory preview <small className="hint">Estimated</small></strong><div className="estimate-actions">{refreshButton}<button type="button" className="text-button" onClick={onDetails} disabled={!onDetails} aria-label="Memory estimate details">Details</button></div></div>
      <dl className="estimate-compact-totals"><div><dt>GPU</dt><dd title={value(result?.gpu_bytes)}>{value(result?.gpu_bytes)}</dd><small>Estimated</small></div><div><dt>RAM</dt><dd title={value(result?.ram_bytes)}>{value(result?.ram_bytes)}</dd><small>Estimated</small></div><div className="estimate-compact-status" data-shortage={shortage > 0} role="status" aria-atomic="true"><dt>Status</dt><dd title={status}>{status}</dd><small title={statusDetail}>{statusDetail}</small></div></dl>
    </section>
    {detailsTarget ? createPortal(<section className="model-memory-estimate model-memory-estimate-details" aria-label="Memory estimate details" aria-busy={loading}><div className="estimate-heading"><strong>Memory details</strong>{refreshButton}</div>{loading ? <p className="hint" role="status">Estimating the selected loading settings…</p> : null}{error ? <p className="estimate-error" role="status">Estimate unavailable · {error}</p> : null}{result ? <EstimateContents result={result} expanded /> : !loading && !error ? <p className="hint" role="status">No estimate is available for the selected loading settings.</p> : null}</section>, detailsTarget) : null}
  </>;
  return <section className="model-memory-estimate" aria-label="Advisory hardware estimate" aria-busy={loading}>
    <div className="estimate-heading"><strong>Memory preview <small className="hint">Estimated</small></strong>{refreshButton}</div>
    {loading && !result ? <span className="hint" role="status">Estimating…</span> : null}
    {error ? <span className="hint" role="status">Estimate unavailable · {error}</span> : null}
    {result ? <EstimateContents result={result} /> : null}
  </section>;
}
