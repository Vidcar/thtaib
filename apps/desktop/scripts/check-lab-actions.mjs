import assert from "node:assert/strict";
import path from "node:path";
import { fileURLToPath } from "node:url";
import React from "react";
import { act, create } from "react-test-renderer";
import { createServer } from "vite";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;
globalThis.window = { setInterval, clearInterval };
const desktopRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const vite = await createServer({ root: desktopRoot, appType: "custom", server: { middlewareMode: true, hmr: false }, logLevel: "error" });
let renderer;
let releaseRun;
const heldRun = new Promise(resolve => { releaseRun = resolve; });
const calls = [];
const originals = new Map();
try {
  const { LabPanel } = await vite.ssrLoadModule("/src/renderer/LabPanel.tsx");
  const { api } = await vite.ssrLoadModule("/src/renderer/api.ts");
  const { workspaceApi } = await vite.ssrLoadModule("/src/renderer/workspaceApi.ts");
  let workspaceCount = 0;
  let failSave = true;
  const patch = (object, key, fn) => { originals.set([object, key], object[key]); object[key] = fn; };
  patch(api, "deployments", async () => []);
  patch(api, "profiles", async () => [{ id: "configuration_a", name: "Model A", bundle_id: "bundle_a", is_default: true }]);
  patch(api, "modelConfiguration", async () => ({ per_request_defaults: {}, context_size: { options: [], supported: false } }));
  patch(workspaceApi, "resolveSetup", async (_project, _agent, configuration) => ({ configuration, effective_values: [], provenance: {}, problems: [] }));
  patch(api, "createWorkspace", async (_name, files) => { calls.push(["create", files]); return { id: `workspace_${++workspaceCount}`, path: `isolated/${workspaceCount}`, origin: "lab" }; });
  patch(api, "workspaceFiles", async id => ({ files: { "notes.md": id === "restored_1" ? "snapshot notes" : "original notes" } }));
  patch(api, "writeWorkspaceFiles", async (id, files) => { calls.push(["save", id, files]); if (failSave) { failSave = false; throw new Error("Source is temporarily busy"); } return { files }; });
  patch(api, "startAgentRun", (...args) => { calls.push(["start", ...args]); return heldRun; });
  patch(api, "agentRun", async id => ({ id, deployment_id: "deployment_a", status: "completed", events: [] }));
  patch(api, "captureCase", async (workspaceId, runId) => { calls.push(["capture", workspaceId, runId]); return { id: "case_1", snapshot_id: "snapshot_1", snapshot_path: "isolated/snapshot" }; });
  patch(api, "restoreCase", async id => { calls.push(["restore", id]); return { workspace: { id: "restored_1" }, parent_unchanged: true, branch: { kind: "copy" } }; });
  patch(api, "rerunCase", async (id, mode, workspaceId) => { calls.push(["rerun", id, mode, workspaceId]); return { id: `result_${mode}`, agent_run_id: `run_${mode}`, tool_mode_label: mode, evidence: { executable_checks: [{}] }, applied_config: {}, judgement: {} }; });
  patch(api, "measureEngine", async id => { calls.push(["measure", id]); return { available: false, note: "Engine unavailable" }; });
  await act(async () => { renderer = create(React.createElement(LabPanel)); });
  const model = renderer.root.findByType((await vite.ssrLoadModule("/src/renderer/ChatModelControls.tsx")).ChatModelControls);
  await act(async () => { await model.props.onApply({ model_configuration_id: "configuration_a" }); });
  await click("Create workspace");
  const submit = renderer.root.findByType("form").props.onSubmit;
  await act(async () => { submit({ preventDefault() {} }); submit({ preventDefault() {} }); });
  assert.equal(calls.filter(call => call[0] === "start").length, 1, "pending tool check blocks a second submit before the run response");
  assert.equal(button("Create workspace").props.disabled, true, "a pending start cannot switch its workspace");
  await act(async () => releaseRun({ id: "run_1", deployment_id: "deployment_a", status: "completed", events: [] }));
  const start = calls.find(call => call[0] === "start");
  assert.equal(start[4], "workspace_1");
  assert.equal(start[7].model_configuration_id, "configuration_a");
  assert.equal(start[7].approval_mode, "ask");
  await click("Capture case");
  await click("Restore a copy");
  await click("Use live tools");
  await click("Replay recorded tools");
  assert.deepEqual(calls.filter(call => call[0] === "rerun"), [["rerun", "case_1", "live-tool", "restored_1"], ["rerun", "case_1", "recorded-tool", "restored_1"]]);
  await click("Save source");
  assert.match(JSON.stringify(renderer.toJSON()), /Source is temporarily busy/);
  await click("Save source");
  assert.match(JSON.stringify(renderer.toJSON()), /Lab source saved/);
  assert.equal(calls.find(call => call[0] === "save")[1], "workspace_1", "saving source never retargets the restored branch");
  await click("Capture case");
  assert.deepEqual(calls.filter(call => call[0] === "capture").at(-1), ["capture", "workspace_1", "run_1"], "capturing source cannot associate a comparison run with the original workspace");
  await click("Measure engine");
  assert.match(JSON.stringify(renderer.toJSON()), /Engine unavailable/);
  await click("Create workspace");
  assert.equal(button("Capture case").props.disabled, true, "a new workspace clears the prior run association");
  assert.equal(button("Restore a copy").props.disabled, true, "a new workspace clears the prior captured case");
  assert.equal(button("Replay recorded tools").props.disabled, true);
  assert.doesNotMatch(JSON.stringify(renderer.toJSON()), /result_recorded-tool/);
  console.log("Lab action ownership checks passed.");
} finally {
  releaseRun({ id: "run_1", status: "completed" });
  if (renderer) await act(async () => renderer.unmount());
  for (const [[object, key], value] of originals) object[key] = value;
  await vite.close();
}
function textOf(node) { if (typeof node === "string") return node; return (node?.children ?? []).map(textOf).join(""); }
function button(label) { return renderer.root.findAll(node => node.type === "button" && textOf(node).includes(label))[0]; }
async function click(label) { assert.equal(button(label).props.disabled ?? false, false, `${label} is available`); await act(async () => { await button(label).props.onClick(); }); }
