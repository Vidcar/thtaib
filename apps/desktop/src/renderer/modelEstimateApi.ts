import { request } from "./api";
import type { SchemaModelEstimateRequest, SchemaModelMemoryEstimate } from "../generated/shared-contracts/openapi";

export type ModelEstimateSelection = Omit<SchemaModelEstimateRequest, "refresh" | "revision"> & { revision?: string };
export type ModelMemoryEstimate = SchemaModelMemoryEstimate;

export function estimateModel(selection: ModelEstimateSelection, refresh = false, signal?: AbortSignal): Promise<ModelMemoryEstimate> {
  return request("/v1/models/estimate", { method: "POST", body: JSON.stringify({ ...selection, refresh }), signal });
}
