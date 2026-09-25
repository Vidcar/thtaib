/** Check that a running backend can serve this desktop's visual testing tools. */

export type BackendCompatibility = "compatible" | "incompatible" | "unavailable";

const REQUIRED_VISUAL_TOOLS = [
  "browser_take_screenshot",
  "desktop_screenshot",
  "start_preview",
] as const;

export async function probeBackendCompatibility(
  origin: string,
  localToken: string,
  fetcher: typeof fetch = fetch,
): Promise<BackendCompatibility> {
  let healthResponse: Response;
  try {
    healthResponse = await fetcher(`${origin}/health`, { signal: AbortSignal.timeout(1500) });
  } catch {
    return "unavailable";
  }
  if (!healthResponse.ok) return "unavailable";
  try {
    const health: unknown = await healthResponse.json();
    if (!isRecord(health) || health.status !== "ok" || health.product !== "Local AI Workbench") {
      return "incompatible";
    }

    const toolsResponse = await fetcher(`${origin}/v1/agent-tools`, {
      headers: { "X-Workbench-Local-Token": localToken },
      signal: AbortSignal.timeout(3000),
    });
    if (!toolsResponse.ok) return "incompatible";
    const catalogue: unknown = await toolsResponse.json();
    if (!isRecord(catalogue) || !Array.isArray(catalogue.enabled)) return "incompatible";
    const enabled = new Set(catalogue.enabled.filter((name): name is string => typeof name === "string"));
    return REQUIRED_VISUAL_TOOLS.every(name => enabled.has(name)) ? "compatible" : "incompatible";
  } catch {
    return "incompatible";
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
