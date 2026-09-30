import { request } from "./api";
import type { SchemaModelEstimateRequest, SchemaModelMemoryEstimate } from "../generated/shared-contracts/openapi";

export type ModelEstimateSelection = Omit<SchemaModelEstimateRequest, "refresh" | "revision" | "method" | "basis"> & { revision?: string; method?: "metadata" | "native"; basis?: "available" | "capacity"; source_path?: string };
export type ModelMemoryEstimate = SchemaModelMemoryEstimate;

export function estimateModel(selection: ModelEstimateSelection, refresh = false, signal?: AbortSignal): Promise<ModelMemoryEstimate> {
  return request("/v1/models/estimate", { method: "POST", body: JSON.stringify({ ...selection, method: selection.method ?? "metadata", refresh }), signal });
}
