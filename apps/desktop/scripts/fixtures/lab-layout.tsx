import React from "react";
import { createRoot } from "react-dom/client";
import { LabWorkbench } from "../../src/renderer/LabWorkbench";
import { api } from "../../src/renderer/api";
import { labApi } from "../../src/renderer/labApi";
import "../../src/renderer/appearanceDefaults.css";
import "../../src/renderer/styles.css";

const choices = values => values.map(value => ({ value, label: String(value) }));
const descriptor = (key, values) => ({ key, label: key, description: "Lab layout fixture.", maximum: null, options: choices(values), default_value: values[0], supported: true });
const bag = requested => ({ requested, applied: requested, unsupported: [], retired: [], overridden: [], unverified: [] });
api.bundles = async () => [{ id: "model", display_name: "Model with a long local name", primary_path: "fixture.gguf", disk_matches: true, default_configuration_id: "configuration" }];
api.profiles = async () => [{ id: "configuration", display_name: "Balanced saved configuration", bundle_id: "model", bags: { startup: bag({ ctx_size: 8192 }), per_request: bag({}), agent: bag({}) } }];
api.modelConfiguration = async () => ({ bundle_id: "model", context_size: { ...descriptor("ctx_size", [32768, 65536]), maximum: 65536 }, gpu_layers: descriptor("n_gpu_layers", ["auto", "all", 0, 8]), startup_defaults: { fit: descriptor("fit", ["on", "off"]), flash_attn: descriptor("flash_attn", ["auto", "on", "off"]), cache_type_k: descriptor("cache_type_k", ["f16", "q8_0"]), cache_type_v: descriptor("cache_type_v", ["f16", "q8_0"]), spec_type: descriptor("spec_type", ["none", "ngram-simple"]), spec_draft_n_max: descriptor("spec_draft_n_max", [1, 2, 3, 4, 8]), parallel: descriptor("parallel", [-1, 1, 2, 4, 8]) }, per_request_defaults: {}, metadata: {} });
labApi.runs = async () => [];
labApi.challenges = async () => [];
labApi.leave = async () => [];
createRoot(document.getElementById("root")).render(<div style={{ display: "grid", gridTemplateColumns: "54px minmax(0,1fr)", minHeight: "100vh" }}><aside style={{ background: "var(--bg-nav)" }} /><main style={{ minWidth: 0 }}><LabWorkbench /></main></div>);
