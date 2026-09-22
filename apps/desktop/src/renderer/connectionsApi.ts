import type { SchemaConnectionRecord, SchemaConnectionWrite } from "../generated/shared-contracts/openapi";
import { request } from "./api";

export type Connection = SchemaConnectionRecord;

export const connectionsApi = {
  list: () => request<Connection[]>("/v1/connections"),
  create: (payload: SchemaConnectionWrite) => request<Connection>("/v1/connections", { method: "POST", body: JSON.stringify(payload) }),
  update: (id: string, payload: SchemaConnectionWrite & { expected_version?: number }) => request<Connection>(`/v1/connections/${id}`, { method: "PATCH", body: JSON.stringify(payload) }),
  test: (id: string) => request<Connection>(`/v1/connections/${id}/test`, { method: "POST" }),
  saveCredential: (id: string, secret: string) => request<Connection>(`/v1/connections/${id}/credential`, { method: "PUT", body: JSON.stringify({ secret }) }),
};
