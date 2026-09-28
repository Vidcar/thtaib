import { useEffect, useRef, useState } from "react";
import { formatBytes } from "./display";
import { errorMessage } from "./errors";
import { settingValue } from "./effectiveSettings";
import { estimateModel, type ModelEstimateSelection, type ModelMemoryEstimate } from "./modelEstimateApi";
import "./ModelHardwareEstimate.css";

const bytes = (value: number | null | undefined) => value == null ? "Unknown" : formatBytes(value);

export function ModelHardwareEstimate({ selection, onEstimate, active = true }: { selection: ModelEstimateSelection; onEstimate?: (estimate: ModelMemoryEstimate) => void; active?: boolean }) {
  const onResult = useRef(onEstimate); onResult.current = onEstimate;
  const key = JSON.stringify(selection);
  const [epoch, setEpoch] = useState(0);
  const refreshRequest = useRef<{ key: string; epoch: number } | null>(null);
  const [answer, setAnswer] = useState<{ key: string; data?: ModelMemoryEstimate; error?: string } | null>(null);
  const [loading, setLoading] = useState(false);
  useEffect(() => {
    if (!active) return;
    const controller = new AbortController();
    setLoading(true);
    const timer = window.setTimeout(() => {
      const refresh = refreshRequest.current?.key === key && refreshRequest.current?.epoch === epoch;
      refreshRequest.current = null;
      void estimateModel(JSON.parse(key) as ModelEstimateSelection, refresh, controller.signal).then(data => {
        if (!controller.signal.aborted) { setAnswer({ key, data }); onResult.current?.(data); }
      }).catch(failure => {
        if (!controller.signal.aborted) setAnswer({ key, error: errorMessage(failure) });
      }).finally(() => { if (!controller.signal.aborted) setLoading(false); });
    }, selection.bundle_id ? 500 : 250);
    return () => { window.clearTimeout(timer); controller.abort(); };
  }, [key, epoch, selection.bundle_id, active]);
  const result = answer?.key === key ? answer.data : undefined;
  const error = answer?.key === key ? answer.error : undefined;
  const devices = result?.hardware.gpu_devices ?? [];
  const gpuAvailable = devices.length === 1 && !result?.hardware.stale ? devices[0].available_bytes : null;
  const shortage = gpuAvailable != null && result?.gpu_bytes != null ? Math.max(0, result.gpu_bytes - gpuAvailable) : 0;
  const observed = result?.observed_runtime;
  const observedStartup = observed?.startup as Record<string, unknown> | undefined;
  const observedUsage = observed?.resource_usage as { rss_bytes?: number | null } | undefined;
  const evaluated = result?.evaluated_startup;
  return <section className="model-memory-estimate" aria-label="Advisory hardware estimate" aria-busy={loading}>
    <div className="estimate-heading"><strong>Memory estimate <small className="hint">Approximate</small></strong><button type="button" className="text-button" onClick={() => { refreshRequest.current = { key, epoch: epoch + 1 }; setEpoch(epoch + 1); }} disabled={loading} aria-label="Refresh hardware estimate">Refresh</button></div>
    {loading && !result ? <span className="hint" role="status">Estimating…</span> : null}
    {error ? <span className="hint" role="status">Estimate unavailable · {error}</span> : null}
    {result ? <>
      <div className="estimate-availability" aria-label="Available memory">{devices.length ? devices.map(device => <span key={device.id}>{devices.length === 1 ? "GPU" : device.name} <strong>{bytes(device.available_bytes)} / {bytes(device.total_bytes)}</strong>{result.hardware.stale ? " · stale" : ""}</span>) : <span>GPU <strong>Not reported</strong></span>}<span>RAM <strong>{bytes(result.hardware.ram_available_bytes)} / {bytes(result.hardware.ram_total_bytes)}</strong></span><small className="hint">Available / total</small></div>
      <div className="estimate-summary"><span>Weights <strong>{bytes(result.weights_bytes)}</strong></span><span>{result.source === "native_prediction" ? "Context memory" : "KV cache"} <strong>{bytes(result.kv_bytes)}</strong></span><span>Overhead <strong>{bytes(result.runtime_overhead_bytes)}</strong></span></div>
      <div className="estimate-summary"><span>GPU <strong>{bytes(result.gpu_bytes)}</strong></span><span>RAM <strong>{bytes(result.ram_bytes)}</strong></span><span>Model files <strong>{bytes(result.model_disk_bytes)}</strong></span>{result.projector_disk_bytes ? <span>Vision file <strong>{bytes(result.projector_disk_bytes)}</strong></span> : null}</div>
      {shortage ? <p className="estimate-shortage">{result.runtime_overhead_bytes == null ? "At least " : "Approximately "}{bytes(shortage)} above available GPU memory. You can keep these settings.</p> : null}
      {result.context_marker != null ? <p className="hint">{result.context_marker_kind === "upper_bound" ? "GPU context upper bound" : "Native automatic context estimate"}: {result.context_marker.toLocaleString()} tokens{result.context_marker_kind === "upper_bound" ? " · excludes unknown overhead" : ""}</p> : null}
      <details><summary>Hardware &amp; assumptions{result.unknown_reasons?.length ? " · incomplete estimate" : ""}</summary>
        <p className="hint">Observed {new Date(result.hardware.observed_at).toLocaleTimeString()} · {result.hardware.source}</p>
        <p className="hint">{result.source === "native_prediction" ? "Pinned native prediction" : "GGUF metadata estimate"} · {result.architecture ?? "Architecture unknown"} · calculated {new Date(result.estimated_at).toLocaleTimeString()}</p>
        {result.source === "native_prediction" && evaluated ? <p className="hint">Prediction settings: context {settingValue(evaluated.ctx_size, "ctx_size")} · GPU layers {settingValue(evaluated.n_gpu_layers, "n_gpu_layers")} · slots {settingValue(evaluated.parallel)}.</p> : null}
        {(result.devices ?? []).map((device, index) => <p key={index}>{String(device.id)}: weights {bytes(device.weights_bytes as number)} · context {bytes(device.kv_bytes as number)} · compute {bytes(device.runtime_overhead_bytes as number)}</p>)}
        {[...(result.assumptions ?? []), ...(result.unknown_reasons ?? [])].map((message, index) => <p className="hint" key={index}>{message}</p>)}
        {observed ? <><p className="hint">Loaded process RAM: {bytes(observedUsage?.rss_bytes)} · context request: {settingValue(observedStartup?.ctx_size, "ctx_size")} · KV: {settingValue(observedStartup?.kv_offload, "kv_offload")}</p><p className="hint">Loaded observations belong to that launch; GPU allocation has not been observed here.</p></> : null}
      </details>
    </> : null}
  </section>;
}
