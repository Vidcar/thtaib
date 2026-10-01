import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { execFileSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import React from "react";
import { act, create } from "react-test-renderer";
import { createServer as createViteServer } from "vite";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;
globalThis.window = { workbench: { backendUrl: "http://tool-catalogue.test" } };
globalThis.fetch = async (url) => {
  const target = String(url);
  if (target.endsWith("/v1/setup-resolution")) {
    return { ok: true, json: async () => ({ configuration: {}, effective_values: {}, instruction_layers: [] }) };
  }
  throw new Error(`Unexpected catalogue check request ${target}`);
};

const desktopRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const repoRoot = path.resolve(desktopRoot, "../..");
const dataRoot = fs.mkdtempSync(path.join(os.tmpdir(), "tool-catalogue-"));
const projection = JSON.parse(execFileSync("uv", ["run", "--project", "apps/backend", "python", "-c", "import json; from workbench_backend.agents.tools import catalogue_projection; print(json.dumps(catalogue_projection()))"], {
  cwd: repoRoot,
  encoding: "utf8",
  env: { ...process.env, WORKBENCH_DATA_ROOT: dataRoot },
}));
const optIn = new Set(projection.tools.filter(tool => tool.opt_in).map(tool => tool.id));
const projectlessKey = "projectless-noknowledge-noattachments-nocapture";
const projectKey = "project-noknowledge-noattachments-nocapture";

function text(node) {
  return typeof node === "string" ? node : node?.children?.map(text).join("") ?? "";
}

const vite = await createViteServer({ root: desktopRoot, appType: "custom", server: { middlewareMode: true, hmr: false }, logLevel: "error" });
try {
  const { SetupConfigurationEditor } = await vite.ssrLoadModule("/src/renderer/SetupConfigurationEditor.tsx");
  const { effectiveNextTurnTools } = await vite.ssrLoadModule("/src/renderer/chatSetup.ts");
  const catalogue = {
    deployments: [], bundles: [], profiles: [], knowledge: [], connections: [],
    tools: projection.tools, groups: projection.groups, defaults: projection.defaults,
    plan_tools: projection.plan_tools, plan_public_web_remote_names: projection.plan_public_web_remote_names,
    toolCatalogueStatus: "ready",
  };
  const emptyCatalogue = { deployments: [], bundles: [], profiles: [], knowledge: [], connections: [], tools: [], toolCatalogueStatus: "ready" };

  async function edit(value, extra = {}) {
    const edits = [];
    let renderer;
    function Host() {
      const [current, setCurrent] = React.useState(value);
      return React.createElement(SetupConfigurationEditor, {
        value: current, catalogue, sections: ["tools"], scope: "agent",
        onChange: next => { edits.push(next); setCurrent(next); }, ...extra,
      });
    }
    await act(async () => { renderer = create(React.createElement(Host)); });
    return { edits, renderer };
  }
  const disclosure = (renderer, name) => renderer.root.findAllByType("button").find(node => node.props.className === "setup-tool-group-expand" && text(node).startsWith(name));
  const choice = (renderer, name) => renderer.root.findByProps({ role: "switch", "aria-label": name });
  const click = async node => { await act(async () => { node.props.onClick(); }); };

  const projectless = await edit({ instructions: "Research" });
  assert.equal(projectless.edits.length, 0, "opening Standard does not persist a derived list");
  await click(disclosure(projectless.renderer, "Diagnostics"));
  await click(choice(projectless.renderer, "Current time"));
  const projectlessSaved = projectless.edits.at(-1).presented_tools;
  assert.deepEqual(projectlessSaved, projection.defaults[projectlessKey].filter(name => name !== "time_now"));
  assert.equal(projectlessSaved.some(name => optIn.has(name)), false, "turning off Current time does not keep opt-in tools");
  assert.equal(projectless.edits.at(-1).connection_ids, undefined);
  assert.equal(projectless.edits.at(-1).desktop_access, undefined);
  await act(async () => projectless.renderer.unmount());

  const bound = await edit({ instructions: "Research" }, { projectId: "bound-project" });
  await click(disclosure(bound.renderer, "Diagnostics"));
  await click(choice(bound.renderer, "Current time"));
  const boundSaved = bound.edits.at(-1).presented_tools;
  assert.deepEqual(boundSaved, projection.defaults[projectKey].filter(name => name !== "time_now"));
  assert.ok(boundSaved.includes("read_file") && boundSaved.includes("ls"));
  assert.equal(boundSaved.some(name => optIn.has(name)), false);
  await click(disclosure(bound.renderer, "Browser"));
  const browserText = text(disclosure(bound.renderer, "Browser").parent.parent);
  assert.match(browserText, /Request details/);
  assert.match(browserText, /Media emulation/);
  assert.equal(boundSaved.includes("browser_network_request") || boundSaved.includes("browser_emulate_media"), false);
  await act(async () => bound.renderer.unmount());

  const deliberate = await edit({ instructions: "Keep", presented_tools: ["echo", "delete"] });
  assert.equal(deliberate.edits.length, 0, "an existing explicit selection is not rewritten on open");
  assert.match(text(deliberate.renderer.root), /Review them before use/);
  assert.doesNotMatch(text(deliberate.renderer.root), /accidental/);
  await act(async () => deliberate.renderer.unmount());

  const cleared = await edit({ presented_tools: [] });
  await click(disclosure(cleared.renderer, "Diagnostics"));
  await click(choice(cleared.renderer, "Current time"));
  assert.deepEqual(cleared.edits.at(-1).presented_tools, ["time_now"], "an explicit empty selection adds only the chosen tool");
  await act(async () => cleared.renderer.unmount());

  const loadingEdits = [];
  let loading;
  await act(async () => {
    loading = create(React.createElement(SetupConfigurationEditor, {
      value: { presented_tools: null }, catalogue: { ...catalogue, toolCatalogueStatus: "loading" }, sections: ["tools"],
      onChange: next => loadingEdits.push(next),
    }));
  });
  assert.match(text(loading.root), /Loading tool choices/);
  const loadingChoice = loading.root.findAll(node => node.props["aria-label"] === "Current time")[0];
  if (loadingChoice) await click(loadingChoice);
  assert.equal(loadingEdits.length, 0, "a loading catalogue cannot be saved as a derived selection");
  await act(async () => loading.unmount());

  const missingEdits = [];
  let missing;
  await act(async () => {
    missing = create(React.createElement(SetupConfigurationEditor, {
      value: {}, catalogue: emptyCatalogue, sections: ["tools"],
      onChange: next => missingEdits.push(next),
    }));
  });
  assert.match(text(missing.root), /Tool defaults are unavailable/);
  await act(async () => missing.root.findAllByType("button").find(node => text(node) === "Turn all off").props.onClick());
  assert.deepEqual(missingEdits.at(-1).presented_tools, [], "turning tools off stays an explicit empty selection");
  await act(async () => missing.unmount());

  const trusted = "cx_public_search_web_" + "ab".repeat(8);
  const planned = effectiveNextTurnTools(["execute", "delete", "read_tool_result", "read_reference", "find_tools", "web_search", trusted], "plan", projection.plan_tools, projection.plan_public_web_remote_names);
  assert.deepEqual(planned, ["read_tool_result", "read_reference", "find_tools", trusted]);
  assert.ok(projection.plan_tools.includes("read_reference") && projection.plan_tools.includes("read_tool_result") && projection.plan_tools.includes("find_tools"));
  assert.equal(projection.plan_tools.includes("web_search"), false);
} finally {
  await vite.close();
  fs.rmSync(dataRoot, { recursive: true, force: true });
}
