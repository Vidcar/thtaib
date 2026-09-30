import { useEffect, useState } from "react";
import { request } from "./api";
import { emptyResourceReadings, observeResourceReadings, RESOURCE_REFRESH_MS, RESOURCE_TIMEOUT_MS, resourceUsageColour, staleResourceReadings, type ResourceReading, type SystemResources } from "./systemResources";
import "./SystemResourceMonitor.css";

function ResourceRing({ metric, label, resource }: { metric: ResourceReading; label: string; resource: string }) {
  const known = metric.percent !== null;
  const state = known ? metric.stale ? "stale" : "current" : "unavailable";
  const percentage = known ? Math.round(metric.percent!) : null;
  const colour = metric.stale || !known ? "var(--muted)" : resourceUsageColour(metric.percent!);
  return <div className="system-resource-metric" data-resource={resource} data-state={state}
    role={known ? "meter" : "img"} aria-label={known ? metric.name : `${metric.name} unavailable`}
    aria-valuemin={known ? 0 : undefined} aria-valuemax={known ? 100 : undefined} aria-valuenow={percentage ?? undefined}
    aria-valuetext={known ? `${percentage}% used, ${metric.stale ? "last reading is stale" : "current reading"}` : undefined}
    style={{ color: colour }}>
    <span className="system-resource-label" aria-hidden="true">{label}</span>
    <span className="system-resource-ring" aria-hidden="true">
      <svg viewBox="0 0 36 36" focusable="false"><circle className="system-resource-track" cx="18" cy="18" r="16" />
        <circle className="system-resource-fill" cx="18" cy="18" r="16" pathLength="100" strokeDasharray={`${metric.percent ?? 0} 100`} transform="rotate(-90 18 18)" visibility={known && metric.percent! > 0 ? "visible" : "hidden"} /></svg>
      <span className="system-resource-percent">{percentage === null ? "—" : `${percentage}%`}</span>
    </span>
  </div>;
}

export function SystemResourceMonitor() {
  const [readings, setReadings] = useState(emptyResourceReadings);
  useEffect(() => {
    if (typeof document === "undefined") return;
    let disposed = false, generation = 0;
    let controller: AbortController | null = null;
    let pollTimer: ReturnType<typeof setTimeout> | undefined;
    let requestTimer: ReturnType<typeof setTimeout> | undefined;
    let expiryTimer: ReturnType<typeof setInterval> | undefined;
    const visible = () => document.visibilityState !== "hidden";
    const poll = async () => {
      if (disposed || !visible()) return;
      const epoch = generation;
      const pending = new AbortController();
      controller = pending;
      const active = () => !disposed && generation === epoch && visible();
      requestTimer = setTimeout(() => { if (active()) setReadings(previous => staleResourceReadings(previous)); pending.abort(); }, RESOURCE_TIMEOUT_MS);
      try {
        const snapshot = await request<SystemResources>("/v1/system/resources", { signal: pending.signal, cache: "no-store" });
        if (active() && !pending.signal.aborted) setReadings(previous => observeResourceReadings(previous, snapshot, Date.now()));
      } catch {
        if (active()) setReadings(previous => staleResourceReadings(previous));
      } finally {
        // Old callbacks may finish after a new visible-window observer starts.
        if (controller === pending) { clearTimeout(requestTimer); controller = null; requestTimer = undefined; }
        if (active()) pollTimer = setTimeout(poll, RESOURCE_REFRESH_MS);
      }
    };
    const pause = () => {
      generation += 1;
      clearTimeout(pollTimer); clearTimeout(requestTimer); clearInterval(expiryTimer);
      controller?.abort(); controller = null;
      pollTimer = requestTimer = expiryTimer = undefined;
    };
    const visibility = () => {
      pause();
      if (!visible() || disposed) return;
      setReadings(previous => staleResourceReadings(previous, Date.now()));
      expiryTimer = setInterval(() => setReadings(previous => staleResourceReadings(previous, Date.now())), 1_000);
      void poll();
    };
    document.addEventListener("visibilitychange", visibility);
    visibility();
    return () => { disposed = true; document.removeEventListener("visibilitychange", visibility); pause(); };
  }, []);
  return <div className="system-resource-monitor" aria-label="System memory">
    <ResourceRing metric={readings.gpu} label="GPU" resource="gpu" />
    <ResourceRing metric={readings.ram} label="RAM" resource="ram" />
  </div>;
}
