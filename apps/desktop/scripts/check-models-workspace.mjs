import assert from "node:assert/strict";
import path from "node:path";
import { fileURLToPath } from "node:url";
import React from "react";
import { act, create } from "react-test-renderer";
import { createServer } from "vite";

const desktopRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const priorFetch = globalThis.fetch, priorWindow = globalThis.window;
globalThis.IS_REACT_ACT_ENVIRONMENT = true;
globalThis.window = { setTimeout, clearTimeout, setInterval, clearInterval };
const vite = await createServer({ root: desktopRoot, appType: "custom", server: { middlewareMode: true, hmr: false }, logLevel: "error" });
const response = body => ({ ok: true, status: 200, json: async () => body });
const text = node => typeof node === "string" ? node : (node?.children ?? []).map(text).join("");
const tick = async () => { for (let count = 0; count < 4; count++) await new Promise(resolve => setTimeout(resolve, 0)); };
const bag = requested => ({ requested, applied: requested, unsupported: [], retired: [], overridden: [], unverified: [] });
const bundle = (id, preferred = null) => ({ id, display_name: id + " model", default_configuration_id: preferred, source: { kind: "local" }, disk_matches: true, files: [], shards: [], companions: [], primary_path: "D:\\Models\\" + id + ".gguf" });
const profile = (id, owner, startup = {}, revision = 1) => ({ id, bundle_id: owner, display_name: id + " setup", revision, bags: { startup: bag(startup), per_request: bag({}), agent: bag({}) } });
const options = id => ({ bundle_id: id, context_size: { maximum: 32768, options: [] }, gpu_layers: { maximum: 32, options: [] }, startup_defaults: { swa_full: { supported: true, options: [{ value: true, label: "On" }, { value: false, label: "Off" }] } }, per_request_defaults: {}, metadata: {} });
const nodeMock = element => element.type === "form" ? { reportValidity: () => true } : element.type === "dialog" ? { showModal() {} } : null;
const button = (renderer, label) => { const node = renderer.root.findAllByType("button").find(item => text(item) === label); assert.ok(node, "Expected button " + label); return node; };
const control = (renderer, name, label) => { const node = renderer.root.findAll(item => item.type?.name === name && item.props.label === label)[0]; assert.ok(node, "Expected " + name + " " + label); return node; };
const previewContext = renderer => { const node = renderer.root.findAll(item => item.type === "input" && item.props.id === "preview-ctx_size")[0]; assert.ok(node, "Expected preview context input"); return node; };
const mount = async (Component, props) => { let renderer; await act(async () => { renderer = create(React.createElement(Component, props), { createNodeMock: nodeMock }); await tick(); }); return renderer; };
const unmount = async renderer => { if (renderer) await act(async () => renderer.unmount()); };
const change = async callback => act(async () => { callback(); await tick(); });
const repository = {
  repo_id: "publisher/model", resolved_revision: "pinned-sha", warnings: [], guidance_files: ["README.md"], gguf_candidates: [],
  variants: [{ name: "model-Q4_K_M.gguf", files: ["model-Q4_K_M.gguf"], quantization: "Q4_K_M", size_bytes: 4000, complete: true }, { name: "model-Q8_0.gguf", files: ["model-Q8_0.gguf"], quantization: "Q8_0", size_bytes: 8000, complete: true }],
  projectors: [{ name: "mmproj-f16.gguf", files: ["mmproj-f16.gguf"], size_bytes: 1000, complete: true }],
  response_recipes: [{ id: "careful", name: "Careful", reasoning: "preserve", per_request: { temperature: .4 } }, { id: "creative", name: "Creative", reasoning: "preserve", per_request: { temperature: .9 } }],
};

try {
  const { DeploymentsPanel } = await vite.ssrLoadModule("/src/renderer/DeploymentsPanel.tsx");
  const { ModelChecks, modelCheckKinds } = await vite.ssrLoadModule("/src/renderer/ModelChecks.tsx");
  const { capacityFit, ModelCapacityPreview } = await vite.ssrLoadModule("/src/renderer/ModelCapacityPreview.tsx");
  const { HuggingFaceImport } = await vite.ssrLoadModule("/src/renderer/HuggingFaceImport.tsx");
  await checkUnnamedSetup(DeploymentsPanel);
  await checkEmptyFixedContext(DeploymentsPanel);
  await checkExplicitSetupChoiceAndSwa(DeploymentsPanel);
  await checkLateCreateOwnership(DeploymentsPanel);
  await checkCreatePreservesDraft(DeploymentsPanel);
  for (const operation of ["create", "copy", "first-save"]) await checkAcknowledgedSetupDuringRefresh(DeploymentsPanel, operation);
  for (const operation of ["create", "copy", "first-save"]) await checkAcknowledgedSetupDuringRefresh(DeploymentsPanel, operation, true);
  await checkRenameKeepsStaleRevision(DeploymentsPanel);
  await checkRenameCancellation(DeploymentsPanel);
  await checkSavedChecks(ModelChecks, modelCheckKinds);
  await checkCapacity(capacityFit, ModelCapacityPreview);
  await checkImportBoundary(HuggingFaceImport);
  await checkEmptySearch(HuggingFaceImport);
  console.log("Models workspace saved setup, capability scope, capacity and import boundary checks passed.");
} finally { globalThis.fetch = priorFetch; globalThis.window = priorWindow; await vite.close(); }

function setupReceiver({ profiles, onSave, onRename } = {}) {
  const calls = [], unexpected = [];
  globalThis.fetch = async (url, init = {}) => {
    const path = String(url), method = init.method ?? "GET", body = init.body ? JSON.parse(init.body) : null;
    calls.push({ path, method, body });
    if (path.endsWith("/v1/runtime/models")) return response({ max_loaded_models: 1, loaded_deployment_ids: [], loading_deployment_ids: [], router_status: "stopped" });
    if (path.endsWith("/v1/runtime")) return response({ status: "ready" });
    if (path.endsWith("/v1/deployments")) return response([]);
    if (path.endsWith("/projectors")) return response({ candidates: [] });
    if (path.includes("/configuration-options")) return response(options(path.match(/bundles\/([^/]+)/)?.[1] ?? "first"));
    if (path.endsWith("/v1/setup-resolution")) return response({ configuration: body.overrides, effective_values: {}, instruction_layers: [] });
    if (path.endsWith("/v1/settings/preview")) return response({ startup: bag(body.startup), per_request: bag(body.per_request), agent: bag(body.agent ?? {}) });
    if (path.includes("/compatibility/configurations/") && method === "GET") return response({ evidence: [], current_support: {}, applicable_capabilities: [], automatic_running: false });
    if (path.endsWith("/configurations") && method === "POST") { const result = await onSave(body, path); return typeof result?.json === "function" ? result : response(result); }
    if (path.endsWith("/v1/deployments/managed")) return response({ deployment: { id: "loaded", status: "running", bundle_id: body.bundle_id, profile_id: body.profile_id, health: { healthy: true } }, outcome: "loaded", message: "Loaded" });
    if (method === "PATCH" && path.includes("/v1/bundles/")) return response(onRename?.(body, path) ?? {});
    if (path.endsWith("/v1/profiles")) return response(profiles?.() ?? []);
    unexpected.push({ path, method }); throw new Error("Unexpected models workspace request " + method + " " + path);
  };
  return { calls, unexpected };
}

async function checkUnnamedSetup(Panel) {
  let renderer, savedProfiles = [];
  const model = bundle("first");
  const receiver = setupReceiver({ profiles: () => savedProfiles, onSave: body => { const saved = { ...profile("named", model.id, body.startup), display_name: body.display_name, bags: { startup: bag(body.startup), per_request: bag(body.per_request), agent: bag(body.agent ?? {}) } }; savedProfiles = [saved]; return saved; } });
  const props = () => ({ selectedBundleId: model.id, initialBundles: [model], initialProfiles: savedProfiles, onBundlesChanged: async () => renderer.update(React.createElement(Panel, props())) });
  try {
    renderer = await mount(Panel, props());
    assert.ok(renderer.root.findByProps({ id: "model-settings-form" }), "zero saved setups still allows tuning");
    assert.equal(button(renderer, "Load").props.disabled, true, "unnamed setup cannot load");
    await change(() => renderer.root.findByProps({ "aria-label": "Context mode" }).props.onChange({ target: { value: "fixed" } }));
    await change(() => control(renderer, "NumberField", "Exact context").props.onChange(12288));
    await change(() => renderer.root.findByProps({ id: "model-settings-form" }).props.onSubmit({ preventDefault() {} }));
    assert.equal(receiver.calls.filter(item => item.path.endsWith("/configurations")).length, 0, "Save first asks for an explicit setup name");
    await change(() => renderer.root.findByProps({ id: "model-variant-name" }).props.onChange({ target: { value: "My careful setup" } }));
    await change(() => button({ root: renderer.root.findByProps({ className: "compact-dialog" }) }, "Save").props.onClick());
    const saved = receiver.calls.find(item => item.path.endsWith("/configurations"));
    assert.equal(saved.body.display_name, "My careful setup");
    assert.equal(saved.body.startup.ctx_size, 12288, "named Save includes the tuned unnamed draft");
    assert.equal(saved.body.configuration_id, undefined, "first named save creates a configuration");
    assert.equal(receiver.calls.some(item => item.path.endsWith("/v1/deployments/managed")), false, "Save leaves loading explicit");
    assert.equal(button(renderer, "Load").props.disabled, false, "saved setup can now load");
    await change(() => button(renderer, "Load").props.onClick());
    const load = receiver.calls.find(item => item.path.endsWith("/v1/deployments/managed"));
    assert.equal(load?.body.profile_id, "named", "Load uses the explicit saved setup id");
    assert.deepEqual(receiver.unexpected, []);
  } finally { await unmount(renderer); }
}

async function checkEmptyFixedContext(Panel) {
  let renderer;
  const model = bundle("first", "kept");
  const savedProfiles = [profile("kept", "first", { ctx_size: 8192 })];
  const receiver = setupReceiver({ profiles: () => savedProfiles });
  try {
    renderer = await mount(Panel, { selectedBundleId: model.id, initialBundles: [model], initialProfiles: savedProfiles, onBundlesChanged: async () => {} });
    const field = () => renderer.root.findAllByType("input").find(node => node.props.id === "model-context-number");
    const dirty = () => renderer.root.findByProps({ className: "model-save-state" }).props["data-dirty"];
    assert.equal(field().props.value, 8192);
    await change(() => field().props.onChange({ target: { value: "" } }));
    assert.equal(field().props.value, "", "an emptied fixed context stays visible while editing");
    assert.equal(control(renderer, "NumberField", "Exact context").props.value, 8192, "the saved context stays in place while the field is empty");
    assert.equal(dirty(), false, "clearing the context text does not mark the saved setup unsaved");
    await change(() => field().props.onBlur());
    assert.equal(field().props.value, 8192, "leaving an empty context restores the saved value");
    assert.equal(dirty(), false);
    assert.deepEqual(receiver.unexpected, []);
  } finally { await unmount(renderer); }
}

async function checkExplicitSetupChoiceAndSwa(Panel) {
  let renderer, savedProfiles = [profile("sole", "first", { swa_full: true })];
  const model = bundle("first");
  const receiver = setupReceiver({ profiles: () => savedProfiles, onSave: body => { const saved = { ...savedProfiles.find(item => item.id === body.configuration_id), revision: 2, bags: { startup: bag(body.startup), per_request: bag(body.per_request), agent: bag(body.agent ?? {}) } }; savedProfiles = savedProfiles.map(item => item.id === saved.id ? saved : item); return saved; } });
  const props = () => ({ selectedBundleId: model.id, initialBundles: [model], initialProfiles: savedProfiles, onBundlesChanged: async () => renderer.update(React.createElement(Panel, props())) });
  try {
    renderer = await mount(Panel, props());
    assert.equal(renderer.root.findAllByProps({ id: "model-configuration" }).length, 0, "one setup has no unnecessary selector");
    assert.ok(text(renderer.root).includes("Choose sole setup"), "a sole nonpreferred setup needs explicit selection");
    assert.equal(receiver.calls.some(item => item.path.includes("/compatibility/configurations/")), false, "no saved setup is silently selected");
    await change(() => button(renderer, "Choose sole setup").props.onClick());
    await change(() => control(renderer, "ChoiceControl", "Full sliding cache").props.onChange("false"));
    await change(() => renderer.root.findByProps({ id: "model-settings-form" }).props.onSubmit({ preventDefault() {} }));
    assert.equal(receiver.calls.findLast(item => item.path.endsWith("/configurations")).body.startup.swa_full, false, "typed cache Off saves a boolean");
    await change(() => control(renderer, "SettingRow", "Full sliding cache").props.onReset());
    await change(() => renderer.root.findByProps({ id: "model-settings-form" }).props.onSubmit({ preventDefault() {} }));
    assert.equal(Object.hasOwn(receiver.calls.findLast(item => item.path.endsWith("/configurations")).body.startup, "swa_full"), false, "reset restores canonical startup omission");
    savedProfiles = [...savedProfiles, profile("other", model.id)];
    await change(() => renderer.update(React.createElement(Panel, props())));
    const selector = renderer.root.findByProps({ "aria-label": "Saved setup" });
    assert.equal(selector.findAllByType("option").length, 3, "multiple setups receive the explicit selector and empty choice");
    assert.deepEqual(receiver.unexpected, []);
  } finally { await unmount(renderer); }
}

async function checkLateCreateOwnership(Panel) {
  let renderer, selected = "first", release;
  const models = [bundle("first"), bundle("second")], savedProfiles = [];
  const receiver = setupReceiver({ onSave: body => new Promise(resolve => { release = () => { const saved = { ...profile("late-created", "first"), display_name: body.display_name }; savedProfiles.push(saved); resolve(saved); }; }) });
  const props = () => ({ selectedBundleId: selected, initialBundles: models, initialProfiles: [...savedProfiles], onBundlesChanged: async () => renderer.update(React.createElement(Panel, props())) });
  try {
    renderer = await mount(Panel, props());
    await change(() => button(renderer, "Create").props.onClick());
    await change(() => renderer.root.findByProps({ id: "model-variant-name" }).props.onChange({ target: { value: "First setup" } }));
    await change(() => button({ root: renderer.root.findByProps({ className: "compact-dialog" }) }, "Create").props.onClick());
    assert.equal(typeof release, "function");
    await change(() => { selected = "second"; renderer.update(React.createElement(Panel, props())); });
    await change(() => release());
    assert.ok(text(renderer.root).includes("second model"));
    assert.equal(renderer.root.findAllByProps({ className: "model-single-setup text-button" }).length, 0, "late creation cannot install the first model's setup into the second model");
    assert.equal(button(renderer, "Load").props.disabled, true);
    assert.equal(receiver.calls.some(item => item.path.includes("/compatibility/configurations/late-created/")), false);
    assert.deepEqual(receiver.unexpected, []);
  } finally { await unmount(renderer); }
}

async function checkRenameCancellation(Panel) {
  let renderer, selected = "first";
  const receiver = setupReceiver(), models = [bundle("first"), bundle("second")];
  const props = () => ({ selectedBundleId: selected, initialBundles: models, initialProfiles: [] });
  try {
    renderer = await mount(Panel, props());
    const rename = () => renderer.root.findAllByType("button").find(item => item.props["aria-label"] === "Rename model");
    await change(() => rename().props.onClick());
    await change(() => renderer.root.findByProps({ className: "model-rename-input" }).props.onChange({ target: { value: "Cancelled name" } }));
    const input = renderer.root.findByProps({ className: "model-rename-input" });
    await change(() => { input.props.onKeyDown({ key: "Escape" }); input.props.onBlur(); });
    assert.equal(receiver.calls.some(item => item.method === "PATCH"), false, "Escape cancels the following blur commit");
    await change(() => rename().props.onClick());
    await change(() => renderer.root.findByProps({ className: "model-rename-input" }).props.onChange({ target: { value: "First draft name" } }));
    await change(() => { selected = "second"; renderer.update(React.createElement(Panel, props())); });
    assert.equal(renderer.root.findAllByProps({ className: "model-rename-input" }).length, 0, "switching models closes the old name editor");
    assert.equal(receiver.calls.some(item => item.method === "PATCH"), false, "navigation never commits an old name to the new model");
    assert.deepEqual(receiver.unexpected, []);
  } finally { await unmount(renderer); }
}

async function checkCreatePreservesDraft(Panel) {
  let renderer, savedProfiles = [profile("existing", "first", { ctx_size: 8192 })];
  const model = bundle("first", "existing");
  const receiver = setupReceiver({ onSave: body => { const saved = { ...profile("created", model.id), display_name: body.display_name }; savedProfiles = [...savedProfiles, saved]; return saved; } });
  const props = () => ({ selectedBundleId: model.id, initialBundles: [model], initialProfiles: savedProfiles, onBundlesChanged: async () => renderer.update(React.createElement(Panel, props())) });
  try {
    renderer = await mount(Panel, props());
    await change(() => control(renderer, "NumberField", "Exact context").props.onChange(16384));
    await change(() => button(renderer, "Create").props.onClick());
    await change(() => renderer.root.findByProps({ id: "model-variant-name" }).props.onChange({ target: { value: "Fresh blank setup" } }));
    await change(() => button({ root: renderer.root.findByProps({ className: "compact-dialog" }) }, "Create").props.onClick());
    assert.deepEqual(receiver.calls.find(item => item.path.endsWith("/configurations")).body.startup, {}, "Create intentionally starts a blank saved setup");
    assert.equal(renderer.root.findByProps({ "aria-label": "Saved setup" }).props.value, "created");
    await change(() => renderer.root.findByProps({ "aria-label": "Saved setup" }).props.onChange({ target: { value: "existing" } }));
    assert.equal(control(renderer, "NumberField", "Exact context").props.value, 16384, "Create stashes the existing setup's draft before selecting the new setup");
    assert.equal(renderer.root.findByProps({ className: "model-save-state" }).props["data-dirty"], true, "returning to the old setup restores its unsaved state");
    assert.deepEqual(receiver.unexpected, []);
  } finally { await unmount(renderer); }
}

async function checkRenameKeepsStaleRevision(Panel) {
  let renderer, savedProfiles = [profile("existing", "first", { ctx_size: 8192 })];
  savedProfiles[0].bags.per_request = bag({ temperature: .5 });
  const model = bundle("first", "existing");
  const receiver = setupReceiver({ onSave: body => {
    if (!body.configuration_id) {
      assert.equal(body.expected_revision, undefined, "Save a copy has no optimistic revision of another record");
      assert.equal(body.startup.ctx_size, 16384, "copy uses the authored startup draft");
      assert.equal(body.per_request.temperature, .7, "copy uses the authored response draft");
      const saved = { ...profile("copy", "first", body.startup), display_name: body.display_name, bags: { startup: bag(body.startup), per_request: bag(body.per_request), agent: bag(body.agent ?? {}) } };
      savedProfiles = [...savedProfiles, saved]; return saved;
    }
    if (body.display_name === "Renamed setup" && body.startup.ctx_size === 4096) {
      assert.equal(body.expected_revision, 2, "name-only save uses the current saved record");
      const saved = { ...savedProfiles[0], revision: 3, display_name: body.display_name }; savedProfiles = [saved]; return saved;
    }
    assert.equal(body.expected_revision, 1, "name-only save cannot rebase an older authored draft onto newer settings");
    return { ok: false, status: 409, json: async () => ({ detail: { code: "configuration_revision_conflict", message: "Revision changed" } }) };
  } });
  const props = () => ({ selectedBundleId: model.id, initialBundles: [model], initialProfiles: savedProfiles, onBundlesChanged: async () => renderer.update(React.createElement(Panel, props())) });
  try {
    renderer = await mount(Panel, props());
    await change(() => control(renderer, "NumberField", "Exact context").props.onChange(16384));
    await change(() => renderer.root.findAll(item => item.type?.name === "ResponseSettingsEditor" && item.props.part === "sampling")[0].props.onChange({ temperature: .7 }));
    savedProfiles = [profile("existing", "first", { ctx_size: 4096 }, 2)];
    savedProfiles[0].bags.per_request = bag({ temperature: .9 });
    await change(() => renderer.update(React.createElement(Panel, props())));
    const menu = renderer.root.findAll(item => item.type?.name === "MenuPopover" && item.props.label === "Setup actions")[0];
    await change(() => menu.props.children(() => {}).props.children.find(item => item?.props?.children === "Rename setup").props.onClick());
    await change(() => renderer.root.findByProps({ id: "model-variant-name" }).props.onChange({ target: { value: "Renamed setup" } }));
    await change(() => button({ root: renderer.root.findByProps({ className: "compact-dialog" }) }, "Save").props.onClick());
    assert.equal(control(renderer, "NumberField", "Exact context").props.value, 16384, "rename keeps the authored startup draft");
    await change(() => renderer.root.findByProps({ id: "model-settings-form" }).props.onSubmit({ preventDefault() {} }));
    assert.match(text(renderer.root), /changed elsewhere.*Revert edits.*Save a copy/, "stale authored draft still receives the actionable revision conflict");
    assert.equal(savedProfiles[0].bags.startup.requested.ctx_size, 4096, "conflicting save does not overwrite external saved settings");
    const actions = renderer.root.findAll(item => item.type?.name === "MenuPopover" && item.props.label === "Setup actions")[0];
    await change(() => actions.props.children(() => {}).props.children.find(item => item?.props?.children === "Save a copy").props.onClick());
    await change(() => renderer.root.findByProps({ id: "model-variant-name" }).props.onChange({ target: { value: "Keep my authored draft" } }));
    await change(() => button({ root: renderer.root.findByProps({ className: "compact-dialog" }) }, "Save").props.onClick());
    const copy = receiver.calls.findLast(item => item.path.endsWith("/configurations")).body;
    assert.equal(Object.hasOwn(copy, "configuration_id"), false, "copy creates a record rather than writing the externally changed original");
    assert.equal(Object.hasOwn(copy, "expected_revision"), false);
    assert.equal(savedProfiles.length, 2);
    assert.equal(savedProfiles[0].bags.startup.requested.ctx_size, 4096);
    assert.equal(savedProfiles[0].bags.per_request.requested.temperature, .9, "copy leaves the external response settings unchanged");
    assert.equal(savedProfiles[0].revision, 3, "copy leaves the renamed original revision unchanged");
    assert.equal(renderer.root.findByProps({ "aria-label": "Saved setup" }).props.value, "copy", "saved copy becomes the explicitly selected setup");
    assert.deepEqual(receiver.unexpected, []);
  } finally { await unmount(renderer); }
}

async function checkAcknowledgedSetupDuringRefresh(Panel, operation, omitAcknowledgement = false) {
  let renderer, publishedProfiles = operation === "first-save" ? [] : [profile("existing", "first", { ctx_size: 8192 })], acknowledged, publish, didPublish = false;
  const model = bundle("first", operation === "first-save" ? null : "existing");
  const expectedContext = operation === "create" ? null : 16384;
  const receiver = setupReceiver({ onSave: body => {
    acknowledged = { ...profile("acknowledged-" + operation, model.id, body.startup), display_name: body.display_name, bags: { startup: bag(body.startup), per_request: bag(body.per_request), agent: bag(body.agent ?? {}) } };
    return acknowledged;
  } });
  const props = () => ({ selectedBundleId: model.id, initialBundles: [model], initialProfiles: publishedProfiles, onBundlesChanged: () => new Promise(resolve => {
    publish = () => { didPublish = true; publishedProfiles = [...publishedProfiles, ...(omitAcknowledgement ? [] : [acknowledged])]; renderer.update(React.createElement(Panel, props())); resolve(); };
  }) });
  try {
    renderer = await mount(Panel, props());
    if (operation === "first-save") await change(() => renderer.root.findByProps({ "aria-label": "Context mode" }).props.onChange({ target: { value: "fixed" } }));
    await change(() => control(renderer, "NumberField", "Exact context").props.onChange(16384));
    if (operation === "create") await change(() => button(renderer, "Create").props.onClick());
    else if (operation === "copy") {
      const menu = renderer.root.findAll(item => item.type?.name === "MenuPopover" && item.props.label === "Setup actions")[0];
      await change(() => menu.props.children(() => {}).props.children.find(item => item?.props?.children === "Save a copy").props.onClick());
    } else await change(() => renderer.root.findByProps({ id: "model-settings-form" }).props.onSubmit({ preventDefault() {} }));
    const name = "Acknowledged " + operation;
    await change(() => renderer.root.findByProps({ id: "model-variant-name" }).props.onChange({ target: { value: name } }));
    await change(() => button({ root: renderer.root.findByProps({ className: "compact-dialog" }) }, operation === "create" ? "Create" : "Save").props.onClick());
    assert.equal(typeof publish, "function", operation + " is held at the genuinely deferred parent catalogue refresh");
    assert.ok(text(renderer.root.findByProps({ className: "model-save-state" })).includes(name), operation + " acknowledgement stays selected while the catalogue still excludes it");
    assert.equal(control(renderer, "NumberField", "Exact context").props.value, expectedContext, operation + " keeps the acknowledged saved bags during the delayed refresh");
    assert.equal(renderer.root.findByProps({ className: "model-save-state" }).props["data-dirty"], false, operation + " acknowledgement remains saved while parent data is pending");
    await change(() => publish());
    if (omitAcknowledgement) {
      assert.equal(renderer.root.findAllByProps({ className: "model-save-state" }).some(item => text(item).includes(name)), false, "a fresh catalogue omitting the acknowledged record removes its temporary selection");
      const load = renderer.root.findAllByType("button").find(item => ["Load", "Load saved"].includes(text(item)));
      assert.ok(!load || load.props.disabled, operation + " omission cannot substitute a different loadable setup");
      assert.equal(receiver.calls.some(item => item.path.endsWith("/v1/deployments/managed")), false);
      if (operation !== "first-save") {
        assert.ok(button(renderer, "Choose existing setup"), operation + " missing acknowledgement requires explicit choice of A despite its preferred status");
        await change(() => button(renderer, "Choose existing setup").props.onClick());
        const selectedLoad = renderer.root.findAllByType("button").find(item => ["Load", "Load saved"].includes(text(item)));
        assert.ok(selectedLoad && !selectedLoad.props.disabled, "explicit A selection restores its valid Load action");
        assert.equal(control(renderer, "NumberField", "Exact context").props.value, operation === "create" ? 16384 : 8192, operation === "create" ? "missing B does not erase A's stashed dirty draft" : "copy recovery keeps the original A's saved settings");
        assert.equal(renderer.root.findByProps({ className: "model-save-state" }).props["data-dirty"], operation === "create");
      }
      assert.deepEqual(receiver.unexpected, []);
      return;
    }
    assert.ok(text(renderer.root.findByProps({ className: "model-save-state" })).includes(name), operation + " remains selected when the parent publishes its catalogue");
    assert.equal(control(renderer, "NumberField", "Exact context").props.value, expectedContext);
    if (operation !== "first-save") assert.equal(renderer.root.findByProps({ "aria-label": "Saved setup" }).props.value, acknowledged.id);
    if (operation === "create") {
      await change(() => renderer.root.findByProps({ "aria-label": "Saved setup" }).props.onChange({ target: { value: "existing" } }));
      assert.equal(control(renderer, "NumberField", "Exact context").props.value, 16384, "delayed Create preserves A's dirty draft when returning from B");
      assert.equal(renderer.root.findByProps({ className: "model-save-state" }).props["data-dirty"], true);
    }
    assert.deepEqual(receiver.unexpected, []);
  } finally { if (publish && !didPublish) await change(() => publish()); await unmount(renderer); }
}

async function checkSavedChecks(Checks, kinds) {
  let renderer, selected = profile("one", "model", {}, 3), currentStatus = "passed", reloads = 0, lateRead;
  const calls = [];
  globalThis.fetch = async (url, init = {}) => {
    const path = String(url), method = init.method ?? "GET", body = init.body ? JSON.parse(init.body) : null; calls.push({ path, method, body });
    if (method === "POST") { currentStatus = "failed"; return response({ capability: body.capability, status: "passed", note: "Probe transport result is not the current report" }); }
    const report = { applicable_capabilities: ["text_stream", "tools"], current_support: { text_stream: currentStatus, tools: "untested" }, automatic_running: false, evidence: [{ capability: "text_stream", status: "passed", note: "Earlier successful evidence" }, { capability: "text_stream", status: "failed", note: "Current failed evidence" }], image_setup: {} };
    if (path.includes("/one/") && lateRead) return await lateRead;
    return response(report);
  };
  const props = () => ({ profile: selected, active: true, disabled: false, onReloaded: async () => { reloads++; } });
  try {
    renderer = await mount(Checks, props());
    assert.equal(kinds.length, 10, "header contains the ten implemented checks");
    assert.equal(kinds.some(item => /audio|video/.test(item.id)), false, "deferred audio/video have no runnable probes");
    assert.deepEqual(calls.map(item => item.method), ["GET"], "mount only reads persisted evidence");
    assert.ok(calls[0].path.endsWith("/one/probes?expected_configuration_revision=3"), "persisted evidence is scoped by setup revision");
    const textIcon = () => renderer.root.findAllByType("button").find(item => String(item.props["aria-label"]).startsWith("Check text streaming:"));
    await change(() => textIcon().props.onFocus());
    assert.ok(text(renderer.root.findByProps({ role: "tooltip" })).includes("Earlier successful evidence"), "tooltip follows authoritative support instead of the newest conflicting historical evidence");
    await change(() => textIcon().props.onClick());
    const probe = calls.find(item => item.method === "POST");
    assert.deepEqual(probe.body, { capability: "text_stream", expected_configuration_revision: 3 });
    assert.equal(textIcon().props["data-state"], "failed", "returned persisted report owns the displayed result");
    assert.ok(text(renderer.root.findByProps({ role: "tooltip" })).includes("Current failed evidence"));
    assert.equal(reloads, 1);
    await change(() => renderer.root.findByProps({ "aria-label": "Run all checks" }).props.onClick());
    assert.deepEqual(calls.filter(item => item.method === "POST").map(item => item.body.capability), ["text_stream", "text_stream", "tools"], "Run all executes only applicable implemented capabilities");
    let release;
    lateRead = new Promise(resolve => { release = resolve; });
    await change(() => renderer.update(React.createElement(Checks, { ...props(), refreshVersion: "old refresh" })));
    selected = profile("two", "model", {}, 7); lateRead = null;
    await change(() => renderer.update(React.createElement(Checks, props())));
    await change(() => release(response({ applicable_capabilities: ["text_stream"], current_support: { text_stream: "passed" }, evidence: [], automatic_running: false })));
    assert.equal(textIcon().props["data-state"], "failed", "late previous-setup evidence cannot replace the selected setup's report");
    assert.ok(calls.some(item => item.path.endsWith("/two/probes?expected_configuration_revision=7")));
  } finally { await unmount(renderer); }
}

function completeEstimate(patch = {}) {
  return { basis: "capacity", completeness: "complete", gpu_bytes: 8000, ram_bytes: 2000, weights_bytes: 7000, kv_bytes: 1000, runtime_overhead_bytes: 2000, gpu_budget_bytes: { gpu1: 10000 }, ram_budget_bytes: 20000, devices: [{ id: "gpu1", total_bytes: 8000, weights_bytes: 7000 }], hardware: { gpu_devices: [{ id: "gpu1", name: "GPU one", total_bytes: 12000 }], ram_total_bytes: 24000 }, assumptions: [], unknown_reasons: [], ...patch };
}
async function checkCapacity(fit, Preview) {
  assert.equal(fit(), "unknown");
  assert.equal(fit(completeEstimate()), "green");
  assert.equal(fit(completeEstimate({ devices: [{ id: "gpu1", total_bytes: 6000, weights_bytes: 5000 }], ram_bytes: 4000 })), "amber", "host spill is distinct from full GPU weights");
  assert.equal(fit(completeEstimate({ devices: [{ id: "gpu1", total_bytes: 11000, weights_bytes: 7000 }] })), "red", "per-GPU over-budget allocation cannot be hidden by summed capacity");
  assert.equal(fit(completeEstimate({ gpu_budget_bytes: { gpu1: null } })), "unknown", "unknown GPU capacity cannot claim a fit");
  assert.equal(fit(completeEstimate({ completeness: "partial", runtime_overhead_bytes: null })), "unknown", "missing native overhead cannot claim a fit");
  assert.equal(fit(completeEstimate({ devices: [{ id: "gpu1", total_bytes: null, known_total_bytes: 8000, weights_bytes: 7000 }] })), "unknown", "known partial GPU subtotal cannot claim a complete fit");
  let renderer;
  try {
    renderer = await mount(Preview, { estimate: completeEstimate({ completeness: "partial", gpu_bytes: null }), startup: {}, onChange() {} });
    const heading = text(renderer.root.findByType("h3"));
    assert.match(heading, /unknown|partial|≥|at least|—/i, "header identifies an incomplete total instead of counting unknown memory as zero");
    assert.ok(text(renderer.root).includes("Total hardware capacity"));
  } finally { await unmount(renderer); }
  let rejected;
  try {
    renderer = await mount(Preview, { startup: { ctx_size: 8192 }, pending: false, onChange: value => { rejected = value; } });
    assert.match(text(renderer.root.findByType("h3")), /—/, "an unselected preview does not claim estimation is still running");
    assert.ok(text(renderer.root).includes("Select a quantization"));
    await change(() => previewContext(renderer).props.onChange({ target: { value: "-1" } }));
    assert.equal(rejected, undefined, "context below 1 is not stored or sent");
    assert.equal(previewContext(renderer).props.value, "-1", "the rejected draft stays visible while editing");
    await change(() => previewContext(renderer).props.onBlur());
    assert.equal(previewContext(renderer).props.value, 8192, "leaving an invalid context restores the last accepted value");
    await change(() => previewContext(renderer).props.onChange({ target: { value: "4096" } }));
    assert.equal(rejected.ctx_size, 4096, "a whole context within bounds replaces the preview value");
  } finally { await unmount(renderer); }
}

async function checkEmptySearch(Import) {
  let renderer;
  globalThis.fetch = async url => {
    const path = String(url);
    if (path.includes("/huggingface/search")) return response([]);
    if (path.endsWith("/v1/imports")) return response([]);
    throw new Error("Unexpected import workspace request " + path);
  };
  try {
    renderer = await mount(Import, { onStarted: async () => {} });
    const find = () => renderer.root.findByProps({ "aria-label": "Find a model" });
    await change(() => find().props.onChange({ target: { value: "zzzznotamodelxyz" } }));
    assert.equal(text(renderer.root).includes("No matching models."), false, "typing a query does not claim the search finished");
    assert.ok(text(renderer.root).includes("Search by a model name or publisher."));
    await change(() => renderer.root.findByProps({ className: "models-find-search" }).props.onSubmit({ preventDefault() {} }));
    assert.ok(text(renderer.root).includes("No matching models."), "an empty search tells the user nothing matched");
    await change(() => find().props.onChange({ target: { value: "another name" } }));
    assert.equal(text(renderer.root).includes("No matching models."), false, "editing the query clears the finished empty result");
    assert.ok(text(renderer.root).includes("Search by a model name or publisher."));
  } finally { await unmount(renderer); }
}

async function checkImportBoundary(Import) {
  let renderer, jobs = [{ id: "foreign", repo_id: "other/model", kind: "huggingface", status: "failed", bundle_id: null, error: "Download failed" }];
  const calls = [], unexpected = [];
  globalThis.fetch = async (url, init = {}) => {
    const path = String(url), body = init.body ? JSON.parse(init.body) : null, method = init.method ?? "GET"; calls.push({ path, body, method });
    if (path.endsWith("/v1/imports")) return response(jobs);
    if (path.endsWith("/huggingface/inspect")) { if (body.repo_id === "publisher/failure") throw new Error("Publisher temporarily unavailable"); return response(repository); }
    if (path.endsWith("/v1/models/estimate")) return response(completeEstimate({ context_maximum: 32768, builtin_mtp: true }));
    if (path.endsWith("/v1/imports/huggingface")) { const job = { id: "selected", kind: "huggingface", repo_id: body.repo_id, status: "pending", bundle_id: null, error: null }; jobs = [...jobs, job]; return response(job); }
    if (path.endsWith("/foreign/retry")) { jobs = jobs.map(item => item.id === "foreign" ? { ...item, status: "pending" } : item); return response(jobs[0]); }
    if (path.endsWith("/selected/cancel")) { jobs = jobs.map(item => item.id === "selected" ? { ...item, status: "stopped" } : item); return response(jobs.find(item => item.id === "selected")); }
    unexpected.push(path); throw new Error("Unexpected import workspace request " + path);
  };
  const search = async value => { await change(() => renderer.root.findByProps({ "aria-label": "Find a model" }).props.onChange({ target: { value } })); await change(() => renderer.root.findByProps({ className: "models-find-search" }).props.onSubmit({ preventDefault() {} })); };
  try {
    renderer = await mount(Import, { onStarted: async () => {} });
    await search("publisher/model");
    const q4 = renderer.root.findAllByProps({ role: "radio" }).find(item => item.props["aria-label"].startsWith("Q4_K_M "));
    assert.ok(q4, "Inspected repository exposes complete quantization choices: " + text(renderer.root) + " Requests " + JSON.stringify(calls));
    await change(() => q4.props.onClick());
    await change(() => renderer.root.findByProps({ "aria-label": "Image input" }).props.onChange({ target: { value: "mmproj-f16.gguf" } }));
    const presetMenu = () => renderer.root.findAll(item => item.type?.name === "MenuPopover" && item.props.label === "Model card presets")[0];
    await change(() => presetMenu().props.children[1].props.children[0].props.onChange({ target: { checked: false } }));
    await change(() => previewContext(renderer).props.onChange({ target: { value: "4096" } }));
    await change(() => button(renderer, "Back to Find").props.onClick());
    await search("publisher/failure");
    assert.ok(text(renderer.root).includes("Publisher temporarily unavailable"));
    await change(() => button(renderer, "2Choose").props.onClick());
    assert.equal(renderer.root.findAllByProps({ role: "radio" }).find(item => item.props["aria-label"].startsWith("Q4_K_M ")).props["aria-checked"], true, "failed inspection retains the previous variant");
    assert.equal(renderer.root.findByProps({ "aria-label": "Image input" }).props.value, "mmproj-f16.gguf", "failed inspection retains the previous projector");
    assert.equal(presetMenu().props.children[0].props.children[0].props.checked, true, "failed inspection retains checked presets");
    assert.equal(previewContext(renderer).props.value, 4096, "failed inspection retains user preview edits");
    await change(() => button(renderer, "Back to Find").props.onClick());
    await change(() => button(renderer, "Retry").props.onClick());
    await change(() => button(renderer, "2Choose").props.onClick());
    assert.equal(renderer.root.findAllByProps({ className: "models-download-progress" }).length, 0, "retrying a foreign Find job cannot become the selected model's contextual progress");
    assert.ok(button(renderer, "Download"));
    await change(() => button(renderer, "Download").props.onClick());
    const download = calls.find(item => item.path.endsWith("/v1/imports/huggingface"));
    assert.deepEqual(download.body, { repo_id: "publisher/model", revision: "pinned-sha", allow_patterns: ["model-Q4_K_M.gguf", "mmproj-f16.gguf", "README.md"], recipe_ids: ["careful"], default_recipe_id: null }, "Download includes the exact files and checked recipe ids only");
    assert.equal(Object.hasOwn(download.body, "initial_startup"), false, "advisory preview is never persisted as startup");
    assert.equal(Object.hasOwn(download.body, "initial_per_request"), false);
    assert.ok(button(renderer, "Cancel"), "canonical pending import exposes cancellation");
    assert.equal(renderer.root.findAllByType("button").some(item => text(item) === "Download"), false, "pending import cannot start a duplicate contextual Download");
    await change(() => button(renderer, "Cancel").props.onClick());
    assert.ok(button(renderer, "Retry"), "canonical stopped import exposes retry");
    assert.equal(renderer.root.findAllByType("button").some(item => text(item) === "Download"), false, "stopped import retains its contextual Retry action");
    assert.deepEqual(unexpected, []);
  } finally { await unmount(renderer); }
}
