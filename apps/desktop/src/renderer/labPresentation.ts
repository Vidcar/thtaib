import type { BundleConfigurationOptions, RunProfile, RuntimeControlDescriptor } from "./types";
import type { LabRun } from "./labTypes";

export const labDepths = [{ value: 0, label: "Start" }, { value: 25, label: "Quarter" }, { value: 50, label: "Halfway" }, { value: 75, label: "Three quarters" }, { value: 100, label: "Near end" }] as const;
export const labIsActive = (run: LabRun) => ["queued", "running", "stopping"].includes(run.status);
export const labLeaveOwners = (runs: LabRun[]) => runs.filter(run => labIsActive(run) || run.status === "failed").map(run => run.id);
export const labStatus = (run: LabRun) => ({ queued: "Loading model", running: "Running", stopping: "Stopping", completed: "Complete", stopped: "Stopped", failed: "Failed" })[run.status];
export function labDescriptor(options: BundleConfigurationOptions | null | undefined, key: string): RuntimeControlDescriptor | undefined {
  return key === "ctx_size" ? options?.context_size : key === "n_gpu_layers" ? options?.gpu_layers : options?.startup_defaults[key];
}
export function labSetting(profile: RunProfile | undefined, startup: Record<string, unknown>, options: BundleConfigurationOptions | null | undefined, key: string): unknown {
  if (Object.hasOwn(startup, key)) return startup[key];
  if (Object.hasOwn(profile?.bags.startup.requested ?? {}, key)) return profile?.bags.startup.requested[key];
  const descriptor = labDescriptor(options, key);
  return descriptor?.applied ?? descriptor?.default_value ?? (key === "ctx_size" ? "auto" : null);
}
export function labPromptLengths(options: BundleConfigurationOptions | null | undefined, context: unknown): number[] {
  if (!options) return [];
  const maximum = options.context_size.maximum;
  const fixed = typeof context === "number" && context > 0 ? context : maximum;
  // The Models slider accepts 1024-token steps. Its descriptor's curated
  // dropdown sizes can begin at 32k, so they are not the complete legal domain.
  const values = [1024, 2048, 4096, 8192, 16384, maximum, ...options.context_size.options.map(item => item.value)];
  return [...new Set(values.filter((value): value is number => typeof value === "number" && value > 0 && (maximum == null || value <= maximum) && (fixed == null || value <= fixed)))].sort((a, b) => a - b);
}
export function labChartSeries(runs: LabRun[], metric: "prefill" | "generation") {
  return runs.filter(run => run.kind === "performance").flatMap(run => run.series.map(series => ({
    id: `${run.id}:${series.id}`,
    name: `${series.name} · ${new Date(run.created_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}${series.concurrent_requests > 1 ? ` · ${series.concurrent_requests} requests` : ""}`,
    points: run.measurements.filter(point => point.series_id === series.id && !point.error).flatMap(point => {
      const x = metric === "prefill" ? point.prompt_tokens : point.context_tokens;
      const speed = metric === "prefill" ? point.prefill_tps : point.generation_tps;
      return typeof x === "number" && Number.isFinite(x) && typeof speed === "number" && Number.isFinite(speed) ? [{ x, speed }] : [];
    }).sort((a, b) => a.x - b.x),
  })));
}
