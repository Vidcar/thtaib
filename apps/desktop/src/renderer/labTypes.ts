import type { SchemaChallengeWrite, SchemaLabChallenge, SchemaLabConfiguration, SchemaLabMeasurement, SchemaLabRun, SchemaLabRunRequest, SchemaLabSeries } from "../generated/shared-contracts/openapi";

/** Backend defaults are made concrete once at the Lab read boundary. */
type WithDefaults<T, K extends keyof T> = Omit<T, K> & Required<Pick<T, K>>;
export type LabKind = SchemaLabRun["kind"];
export type LabDepth = NonNullable<SchemaLabRunRequest["depths"]>[number];
export type LabConfiguration = WithDefaults<SchemaLabConfiguration, "startup">;
export type LabRunRequest = Omit<WithDefaults<SchemaLabRunRequest, "depths" | "prompt_lengths">, "configurations"> & { configurations: LabConfiguration[] };
export type LabChallengeWrite = SchemaChallengeWrite;
export type LabChallenge = SchemaLabChallenge;
export type LabSeries = WithDefaults<SchemaLabSeries, "startup">;
export type LabMeasurement = WithDefaults<SchemaLabMeasurement, "expected" | "missing" | "tool_calls" | "samples">;
export type LabRun = Omit<SchemaLabRun, "series" | "measurements" | "request"> & { series: LabSeries[]; measurements: LabMeasurement[]; request: LabRunRequest };

export function normalizeLabRun(run: SchemaLabRun): LabRun {
  return { ...run,
    request: { ...run.request, configurations: run.request.configurations.map(item => ({ ...item, startup: item.startup ?? {} })), prompt_lengths: run.request.prompt_lengths ?? [], depths: run.request.depths ?? [0, 25, 50, 75, 100] },
    series: (run.series ?? []).map(item => ({ ...item, startup: item.startup ?? {} })),
    measurements: (run.measurements ?? []).map(item => ({ ...item, expected: item.expected ?? [], missing: item.missing ?? [], tool_calls: item.tool_calls ?? [], samples: item.samples ?? [] })),
  };
}
