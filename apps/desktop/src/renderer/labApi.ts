import { request } from "./api";
import { normalizeLabRun, type LabChallenge, type LabChallengeWrite, type LabRunRequest } from "./labTypes";
import type { SchemaLabRun } from "../generated/shared-contracts/openapi";

const base = "/v1/lab/workbench";
export const labApi = {
  runs: async () => (await request<SchemaLabRun[]>(`${base}/runs`)).map(normalizeLabRun),
  run: async (id: string) => normalizeLabRun(await request<SchemaLabRun>(`${base}/runs/${encodeURIComponent(id)}`)),
  start: async (body: LabRunRequest) => normalizeLabRun(await request<SchemaLabRun>(`${base}/runs`, { method: "POST", body: JSON.stringify(body) })),
  stop: async (id: string) => normalizeLabRun(await request<SchemaLabRun>(`${base}/runs/${encodeURIComponent(id)}/stop`, { method: "POST" })),
  deleteRun: (id: string) => request<unknown>(`${base}/runs/${encodeURIComponent(id)}`, { method: "DELETE" }),
  leave: (run_ids: string[]) => Promise.all(Array.from({ length: Math.ceil(run_ids.length / 1000) }, (_, index) => request<unknown>(`${base}/leave`, { method: "POST", body: JSON.stringify({ run_ids: run_ids.slice(index * 1000, (index + 1) * 1000) }), keepalive: true }))),
  challenges: () => request<LabChallenge[]>(`${base}/challenges`),
  saveChallenge: (body: LabChallengeWrite, id?: string) => request<LabChallenge>(`${base}/challenges${id ? `/${encodeURIComponent(id)}` : ""}`, { method: id ? "PUT" : "POST", body: JSON.stringify(body) }),
  deleteChallenge: (id: string) => request<unknown>(`${base}/challenges/${encodeURIComponent(id)}`, { method: "DELETE" }),
};
