/** Serialize the Models form at the request boundary. */
export function startupPayload(settings: Record<string, string>, advanced: string,
  profileStartup?: Record<string, unknown>, changedKeys: ReadonlySet<string> = new Set()): Record<string, unknown> {
  let extra: Record<string, unknown> = {};
  if (advanced.trim()) {
    const parsed: unknown = JSON.parse(advanced);
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) throw new Error("Additional settings must be a JSON object.");
    extra = parsed as Record<string, unknown>;
    const duplicate = Object.keys(extra).find(key => key in settings);
    if (duplicate) throw new Error(`Use the ${duplicate.replaceAll("_", " ")} control above instead of repeating it in additional settings.`);
  }
  const numeric = ["ctx_size", "n_gpu_layers", "threads", "threads_batch", "parallel", "port", "batch_size", "ubatch_size", "reasoning_budget", "spec_draft_n_max", "spec_draft_n_min", "spec_draft_ngl", "spec_draft_threads", "spec_draft_threads_batch"];
  const decimal = ["spec_draft_p_min", "spec_draft_p_split"];
  const boolean = new Set(["kv_offload", "kv_unified", "op_offload", "mmproj_use_gpu"]);
  if (profileStartup) {
    const edits: Record<string, unknown> = {};
    for (const key of new Set([...Object.keys(extra), ...Object.keys(profileStartup).filter(key => !(key in settings))])) {
      if (JSON.stringify(extra[key]) !== JSON.stringify(profileStartup[key])) edits[key] = extra[key] ?? null;
    }
    extra = edits;
  }
  for (const [key, value] of Object.entries(settings)) {
    if (profileStartup && !changedKeys.has(key)) continue;
    if (value === "" || (key === "pooling" && settings.embedding !== "on")) {
      if (profileStartup) extra[key] = null;
      continue;
    }
    if (value === "custom") throw new Error(`Enter a value for ${key.replaceAll("_", " ")}.`);
    if (numeric.includes(key) && !["auto", "all"].includes(value) && (!Number.isFinite(Number(value)) || !Number.isInteger(Number(value)))) throw new Error(`Enter a whole number for ${key.replaceAll("_", " ")}.`);
    if (decimal.includes(key) && !Number.isFinite(Number(value))) throw new Error(`Enter a number for ${key.replaceAll("_", " ")}.`);
    extra[key] = key === "reasoning_preserve" ? value === "keep" : boolean.has(key) ? value === "true"
      : (numeric.includes(key) || decimal.includes(key)) && value !== "auto" && value !== "all" ? Number(value) : value;
  }
  return extra;
}

export function mergedStartup(profile: Record<string, unknown>, overrides: Record<string, unknown>): Record<string, unknown> {
  const result = { ...profile };
  for (const [key, value] of Object.entries(overrides)) {
    if (value === null) delete result[key];
    else result[key] = value;
  }
  return result;
}
