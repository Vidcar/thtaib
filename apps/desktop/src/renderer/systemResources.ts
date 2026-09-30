import type { SchemaHardwareMemoryObservation } from "../generated/shared-contracts/openapi";

export type SystemResources = SchemaHardwareMemoryObservation;
export type ResourceReading = { percent: number | null; observedAt: number | null; name: string; stale: boolean };
export type ResourceReadings = { gpu: ResourceReading; ram: ResourceReading };
export const RESOURCE_REFRESH_MS = 2_000;
export const RESOURCE_TIMEOUT_MS = 4_000;
export const RESOURCE_STALE_MS = 10_000;

export function emptyResourceReadings(): ResourceReadings {
  return { gpu: { percent: null, observedAt: null, name: "GPU memory", stale: true }, ram: { percent: null, observedAt: null, name: "System RAM", stale: true } };
}

function percentage(used: unknown, total: unknown): number | null {
  return typeof used === "number" && typeof total === "number" && Number.isFinite(used) && Number.isFinite(total)
    && total > 0 && used >= 0 && used <= total ? used / total * 100 : null;
}

function reading(previous: ResourceReading, percent: number | null, timestamp: string | null | undefined, stale: boolean, name: string, now: number): ResourceReading {
  const observedAt = timestamp ? Date.parse(timestamp) : NaN;
  if (percent === null || !Number.isFinite(observedAt) || stale) return previous.stale ? previous : { ...previous, stale: true };
  return { percent, observedAt, name, stale: now - observedAt >= RESOURCE_STALE_MS };
}

export function observeResourceReadings(previous: ResourceReadings, snapshot: SystemResources, now: number): ResourceReadings {
  const devices = (snapshot.gpu_devices ?? []).map(device => ({ device, percent: percentage(device.used_bytes, device.total_bytes) }))
    .filter((item): item is typeof item & { percent: number } => item.percent !== null)
    .sort((left, right) => right.percent - left.percent || left.device.id.localeCompare(right.device.id));
  const highest = devices[0];
  const total = snapshot.ram_total_bytes;
  const available = snapshot.ram_available_bytes;
  const ramPercent = typeof total === "number" && typeof available === "number" ? percentage(total - available, total) : null;
  return {
    gpu: reading(previous.gpu, highest?.percent ?? null, snapshot.gpu_observed_at, snapshot.gpu_stale === true,
      highest ? `GPU memory (${highest.device.name})` : previous.gpu.name, now),
    ram: reading(previous.ram, ramPercent, snapshot.ram_observed_at, snapshot.ram_stale === true, "System RAM", now),
  };
}

export function staleResourceReadings(previous: ResourceReadings, now = Infinity): ResourceReadings {
  const expire = (metric: ResourceReading) => !metric.stale && (metric.observedAt === null || now - metric.observedAt >= RESOURCE_STALE_MS) ? { ...metric, stale: true } : metric;
  const gpu = expire(previous.gpu), ram = expire(previous.ram);
  return gpu === previous.gpu && ram === previous.ram ? previous : { gpu, ram };
}

export function resourceUsageColour(percent: number): string {
  const red = "color-mix(in oklab, var(--danger) 75%, var(--muted))";
  if (percent <= 50) return "var(--ok)";
  if (percent < 80) return `color-mix(in oklab, var(--ok), var(--warn) ${((percent - 50) / 30 * 100).toFixed(2)}%)`;
  if (percent < 95) return `color-mix(in oklab, var(--warn), ${red} ${((percent - 80) / 15 * 100).toFixed(2)}%)`;
  return red;
}
