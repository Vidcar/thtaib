import assert from "node:assert/strict";
import path from "node:path";
import { fileURLToPath } from "node:url";
import React from "react";
import { act, create } from "react-test-renderer";
import { createServer } from "vite";
import { makeHarness, run, json as respond, renderChat, closeHarness, button, textarea, textOf, waitFor } from "./check-chat-interaction-boundaries.mjs";

const desktopRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const vite = await createServer({ root: desktopRoot, appType: "custom", server: { middlewareMode: true, hmr: false }, logLevel: "error" });
const originalFetch = globalThis.fetch;
globalThis.IS_REACT_ACT_ENVIRONMENT = true;
const json = body => ({ ok: true, status: 200, json: async () => body });
const sourceRows = policy => [
  { id: "workbench_core", title: "Operating rules", kind: "instructions", origin: "Workbench", mode: "always", reason: "Required operating rules", required: true, estimated_tokens: 16, token_counting_method: "estimate", content: "Full automatic operating rules." },
  { id: "native_template", title: "Native formatting", kind: "instructions", origin: "Model template", mode: "always", reason: "Available after model load", required: true, available: false, content: null },
  { id: "agent_instructions", title: "Saved behaviour", kind: "instructions", origin: "Saved agent", mode: policy.excluded_sources?.includes("agent_instructions") ? "off" : "always", reason: "Saved instructions", editable: true, estimated_tokens: 8, content: policy.instruction_override ?? "Saved full agent instructions." },
  { id: "memory:notes", title: "Reference notes", kind: "memory", origin: "Project Knowledge", mode: policy.reference_loading?.notes ?? "when_needed", reason: "Full original available at its frozen version", entry_id: "notes", version_id: "notes-v1", editable: false, estimated_tokens: 12, content: policy.reference_loading?.notes === "off" ? null : "Complete original memory body." },
  { id: "tool:echo", title: "Echo", kind: "tool", origin: "Saved capability", mode: "when_needed", reason: "Discoverable within accepted tools", tool_name: "echo", editable: true, estimated_tokens: 5, content: '{"name":"echo","parameters":{"message":{"type":"string"}}}' },
];
try {
  const { AgentInputs } = await vite.ssrLoadModule("/src/renderer/AgentInputs.tsx");
  await checkInspector(AgentInputs);
  await checkDeferredReaders(AgentInputs);
  globalThis.fetch = originalFetch;
  await checkReadinessInspectorRoute();
  await checkMountedChat();
  await checkFreshRetainedChoices();
  await checkFreshScopeFailure();
  await checkChatSaveToAgent();
  await checkChatCreateAgent();
} finally { globalThis.fetch = originalFetch; await vite.close(); }
console.log("Agent input inspection, scoped edits, actual schemas and mounted Chat snapshot checks passed.");

async function checkInspector(AgentInputs) {
  globalThis.window = { setTimeout, clearTimeout, setInterval, clearInterval, workbench: { backendUrl: "http://127.0.0.1:8000" } };
  const calls = [], saved = [], routes = [];
  let current, renderer, fresh = 0;
  const originalRun = { id: "frozen-run", status: "succeeded", model_requests: [] };
  const fullSchema = { type: "function", function: { name: "echo", description: "Complete supplied description ".repeat(30), parameters: { type: "object", properties: { message: { type: "string", description: "Untruncated schema tail marker." } } } } };
  globalThis.fetch = async (url, init = {}) => {
    const address = new URL(String(url)), payload = init.body ? JSON.parse(init.body) : null;
    calls.push({ path: address.pathname, search: address.search, payload });
    if (address.pathname === "/v1/setup-resolution") {
      const effective = { ...payload.overrides.input_policy, reference_loading: { inherited_other: "always", ...payload.overrides.input_policy?.reference_loading } };
      return json({ configuration: { ...payload.overrides, input_policy: effective }, input_sources: sourceRows(effective), instruction_layers: [] });
    }
    if (address.pathname === "/v1/agent-runs/frozen-run") return json({ ...originalRun, model_requests: [{ at: "2026-09-28", transport_attempted: true, instructions: "Captured [redacted] instructions", capture_gaps: ["Image bytes omitted by capture policy."], presented_tools: ["echo"], input_sources: [sourceRows({})[1], { ...sourceRows({})[3], mode: "always", observed: true }], tool_schemas: [fullSchema], http_payload: { tools: [{ function: { name: "echo", description: "Truncated" } }], messages: [{ role: "user", content: "Captured user message" }] } }] });
    throw new Error(`Inspection made an unexpected call: ${address}`);
  };
  function Host() {
    const [configuration, setConfiguration] = React.useState({ input_policy: { version: 1, tool_loading: "when_needed" } });
    current = configuration;
    return React.createElement(AgentInputs, { configuration, run: originalRun, hasHistory: true, agentName: "Reusable assistant", onChange: setConfiguration, onClose() {}, onEditSource: (...route) => routes.push(route), onFreshChat: () => fresh++, onSaveToAgent: async () => saved.push(structuredClone(current)) });
  }
  try {
    await act(async () => { renderer = create(React.createElement(Host)); });
    await waitFor(() => assert.match(textOf(renderer.root), /Complete original memory body/), "lazy original source inspection");
    assert.equal(calls[0].payload.include_input_content, true);
    assert.equal(renderer.root.findAll(node => node.type === "button" && textOf(node) === "Exclude" && node.parent.parent.findAll(node => node.type === "strong" && textOf(node) === "Operating rules").length).length, 0, "required automatic rules cannot be excluded");
    assert.match(textOf(renderer.root), /Not available in this preview or capture/);
    assert.match(textOf(renderer.root), /Text is not loaded in this preview/);
    assert.doesNotMatch(textOf(renderer.root), /Text is unavailable in this capture/);
    await act(async () => renderer.root.findByProps({ "aria-label": "Loading for Reference notes" }).props.onChange({ target: { value: "off" } }));
    await waitFor(() => assert.equal(current.input_policy.reference_loading.notes, "off"), "explicit inherited Off");
    await waitFor(() => assert.match(textOf(renderer.root), /Open in Knowledge to view the saved text/), "Off preview preserves an owning-editor route without reading the body");
    await act(async () => button(renderer, "Replace agent instructions").props.onClick());
    await act(async () => renderer.root.findAllByType("textarea")[0].props.onChange({ target: { value: "" } }));
    assert.equal(current.input_policy.instruction_override, "", "empty replacement remains explicit rather than reverting to saved text");
    await act(async () => renderer.root.findByProps({ "aria-label": "Always include Echo" }).props.onChange({ target: { checked: true } }));
    assert.deepEqual(current.input_policy.pinned_tools, ["echo"]);
    assert.equal(current.input_policy.reference_loading.notes, "off", "pinning preserves reference modes");
    assert.equal(Object.hasOwn(current.input_policy.reference_loading, "inherited_other"), false, "editing a pin or one source does not author unrelated inherited choices");
    await act(async () => renderer.root.findByProps({ "aria-label": "Tool definition loading" }).props.onChange({ target: { value: "always" } }));
    assert.deepEqual(current.input_policy.pinned_tools, ["echo"]);
    await act(async () => button(renderer, "Open in Knowledge").props.onClick());
    assert.deepEqual(routes.at(-1), ["knowledge", "notes"]);
    assert.equal(saved.length, 0, "local edits never implicitly save an agent");
    await act(async () => button(renderer, "Save to agent").props.onClick());
    assert.equal(saved.length, 1); assert.equal(saved[0].input_policy.instruction_override, "");
    await act(async () => button(renderer, "Fresh chat with these choices").props.onClick());
    assert.equal(fresh, 1); assert.match(textOf(renderer.root), /Earlier messages, tool results or summaries/);
    assert.equal(calls.filter(call => call.path.includes("agent-runs")).length, 0, "actual diagnostic context is not fetched for next-message preview");
    await act(async () => renderer.root.findAllByType("input").find(node => node.props.value === "actual").props.onChange());
    await waitFor(() => assert.match(textOf(renderer.root), /Untruncated schema tail marker/), "actual full tool schema visible");
    assert.equal(calls.find(call => call.path.includes("agent-runs")).search, "?view=diagnostic");
    assert.match(textOf(renderer.root), /Image bytes omitted by capture policy/);
    assert.match(textOf(renderer.root), /Captured \[redacted\] instructions/);
    assert.match(textOf(renderer.root), /Text is unavailable in this capture/);
    assert.doesNotMatch(textOf(renderer.root), /Text is not loaded in this preview/);
    assert.equal(renderer.root.findAll(node => node.type === "button" && textOf(node) === "Exclude").length, 0, "historical actual inputs cannot be edited");
    await act(async () => button(renderer, "Open in Knowledge").props.onClick());
    assert.deepEqual(routes.at(-1), ["knowledge", "notes"], "captured Knowledge sources still open their owning editor for future versions");
    assert.deepEqual(originalRun.model_requests, [], "inspection never rewrites the accepted run");
  } finally { if (renderer) await act(async () => renderer.unmount()); }
}

async function checkDeferredReaders(AgentInputs) {
  const references = [sourceRows({})[3], { id: "skill:steps", title: "Project skill", kind: "skill", origin: "Knowledge", mode: "when_needed", reason: "Selected skill", entry_id: "steps" }];
  for (const test of [
    { tools: ["echo", "read_file"], excluded: ["tool:read_reference"], action: "Include now", loading: { notes: "always" } },
    { tools: ["echo"], excluded: ["tool:read_reference"], action: "Remove", loading: { notes: "off", steps: "off" } },
    { tools: ["echo", "read_file"], excluded: ["tool:read_reference", "tool:read_file"], action: "Enable reading", remaining: ["tool:read_file"] },
    { tools: [], excluded: [], action: "Enable reading", route: "agents" },
  ]) {
    let renderer, current; const routes = [];
    globalThis.fetch = async (_url, init) => { const payload = JSON.parse(init.body); return json({ configuration: payload.overrides, input_sources: references }); };
    function Host() {
      const [configuration, setConfiguration] = React.useState({ input_policy: { version: 1, excluded_sources: test.excluded } });
      current = configuration;
      return React.createElement(AgentInputs, { configuration, effectiveTools: test.tools, onChange: setConfiguration, onClose() {}, onEditSource: owner => routes.push(owner) });
    }
    try {
      await act(async () => { renderer = create(React.createElement(Host)); });
      await waitFor(() => button(renderer, test.action), "blocked reader offers an explicit remedy");
      assert.deepEqual(current.input_policy.excluded_sources, test.excluded, "inspection never silently restores an excluded reader");
      await act(async () => button(renderer, test.action).props.onClick());
      if (test.loading) assert.deepEqual(current.input_policy.reference_loading, test.loading, "the remedy affects only references lacking a reading route");
      if (test.remaining) assert.deepEqual(current.input_policy.excluded_sources, test.remaining, "reference reading is restored without changing the file-reader choice");
      if (test.route) { assert.deepEqual(routes, [test.route]); assert.deepEqual(current.input_policy.excluded_sources, test.excluded); }
    } finally { if (renderer) await act(async () => renderer.unmount()); }
  }
}

async function checkReadinessInspectorRoute() {
  for (const issue of [
    { code: "deferred_reference_reader_excluded", message: "Reference reading is excluded.", label: "Review reference loading" },
    { code: "skill_selection_required", message: "Update selected tools, connections or project.", label: "Review skill requirements" },
  ]) await checkReadinessInspectorIssue(issue);
}

async function checkReadinessInspectorIssue(issue) {
  const routes = [];
  const skill = { id: "skill:steps", title: "Project skill", kind: "skill", origin: "Project Knowledge", mode: "always", reason: "Selected skill", entry_id: "steps", required_tools: ["browser_snapshot"], required_connections: ["browser"], requires_project: true };
  const sources = policy => issue.code === "skill_selection_required" ? [{ ...skill, mode: policy.reference_loading?.steps ?? "always" }] : sourceRows(policy);
  const harness = makeHarness({ aRun: null, threadARun: null, threadNewRun: null,
    readiness: ({ payload }) => ({ status: "needs_setup", can_send: false, issues: [{ code: issue.code, message: issue.message }], selection: null, input_preview: { policy: payload.overrides.input_policy ?? {}, sources: sources(payload.overrides.input_policy ?? {}), token_counting_method: "estimate" } }),
  });
  harness.state.conversations.conv_a.draft = { revision: 1, content: "Next question", attachment_ids: [], intended_config: { presented_tools: ["echo"], input_policy: { version: 1, excluded_sources: ["tool:read_reference"] } } };
  let renderer;
  try {
    renderer = await renderChat(vite, harness, { onNavigate: owner => routes.push(owner) });
    await waitFor(() => button(renderer, "Conversation A"), "blocked reader Chat history");
    await act(async () => button(renderer, "Conversation A").props.onClick());
    await waitFor(() => button(renderer, issue.label), `${issue.code} readiness action`);
    await act(async () => button(renderer, issue.label).props.onClick());
    if (issue.code === "skill_selection_required") {
      await waitFor(() => assert.match(textOf(renderer.root), /Needs: browser_snapshot, Connection browser, Project folder/), "the source inspector shows exact declared skill requirements");
      const loading = () => renderer.root.findByProps({ "aria-label": "Loading for Project skill" });
      assert.equal(loading().props.value, "always");
      assert.ok(button(renderer, "Open in Knowledge"), "declared skill requirements retain their owning editor link");
      await act(async () => loading().props.onChange({ target: { value: "when_needed" } }));
      await waitFor(() => assert.equal(loading().props.value, "when_needed"), "blocked Always skill can be deferred explicitly");
    } else await waitFor(() => button(renderer, "Include now"), "readiness opens the actionable source inspector");
    assert.deepEqual(routes, [], "an input policy remedy does not send the user to an unrelated editor");
    assert.equal(harness.state.requests.commands.length, 0);
  } finally { if (renderer) await closeHarness(renderer, harness); }
}

async function checkFreshRetainedChoices() {
  const asset = (id, kind = "text") => ({ id, filename: `${id}.${kind === "document" ? "pdf" : "txt"}`, session_id: "conv_a", project_path: null, origin: "upload", scope: "session", access_scope: "session", content_type: kind === "document" ? "application/pdf" : "text/plain", content_kind: kind, encoding: kind === "document" ? "base64" : "utf-8", deleted_at: null, observed_at: "2026-09-28", size_bytes: 12, sha256: `hash-${id}` });
  const originals = [asset("direct"), asset("document", "document"), asset("excluded"), asset("unselected")];
  const reads = [];
  const accepted = run("fresh-original", "completed"); accepted.effective_setup = { instructions: "Frozen instructions" };
  const harness = makeHarness({ aRun: accepted, threadARun: accepted, threadNewRun: null, assets: originals,
    resolveSetup: payload => ({ configuration: payload.overrides, instruction_layers: [], input_sources: sourceRows(payload.overrides.input_policy ?? {}) }),
    readiness: ({ payload }) => ({ status: "ready", can_send: true, issues: [], selection: null, input_preview: { policy: payload.overrides.input_policy ?? {}, sources: sourceRows(payload.overrides.input_policy ?? {}), prepared: false, token_counting_method: "estimate" } }),
    requestOverride: ({ req, res, url }) => {
      if (req.method === "GET" && /^\/v1\/assets\/[^/]+\/content$/.test(url.pathname)) {
        const id = url.pathname.split("/")[3]; reads.push({ id, sessionId: url.searchParams.get("session_id"), projectPath: url.searchParams.get("project_path") });
        const original = originals.find(item => item.id === id); assert.ok(original); assert.equal(url.searchParams.get("session_id"), "conv_a");
        respond(res, 200, { id, filename: original.filename, content_type: original.content_type, encoding: original.encoding, text: id === "direct" ? "Exact Unicode original · β" : "Extracted preview is not original bytes", content_base64: id === "document" ? Buffer.from("Exact PDF original bytes").toString("base64") : null }); return true;
      }
    },
  });
  const originalDraft = { revision: 1, content: "Old unsent question", attachment_ids: ["direct", "excluded"], intended_config: { input_policy: { version: 1, instruction_override: "Fresh local instructions", excluded_sources: ["attachment:excluded"] }, document_asset_ids: ["document", "excluded"], memory_entry_ids: ["notes"], project_file_refs: ["allowed.txt"] } };
  harness.state.conversations.conv_a.document_asset_ids = ["document", "excluded"];
  harness.state.conversations.conv_a.draft = originalDraft;
  const frozen = structuredClone(harness.state.conversations.conv_a);
  let renderer;
  try {
    renderer = await renderChat(vite, harness);
    await waitFor(() => button(renderer, "Conversation A"), "fresh retained history");
    await act(async () => button(renderer, "Conversation A").props.onClick());
    await waitFor(() => assert.equal(textarea(renderer).props.disabled, false), "original retained Chat bound");
    await act(async () => renderer.root.find(node => node.type?.name === "ChatMeasurements").props.onInspect());
    await waitFor(() => button(renderer, "Fresh chat with these choices"), "fresh choice action");
    await act(async () => button(renderer, "Fresh chat with these choices").props.onClick());
    await waitFor(() => assert.ok(harness.state.conversations.conv_new?.draft?.intended_config.document_asset_ids?.length), "fresh selected files have new owned copies");
    const next = harness.state.conversations.conv_new, copies = harness.state.requests.assetUploads;
    assert.deepEqual(reads.map(item => item.id), ["direct", "document"], "Off and unselected documents are neither read nor copied");
    assert.deepEqual(copies.map(item => item.session_id), ["conv_new", "conv_new"]);
    assert.equal(Buffer.from(copies[0].content_base64, "base64").toString("utf8"), "Exact Unicode original · β");
    assert.equal(Buffer.from(copies[1].content_base64, "base64").toString("utf8"), "Exact PDF original bytes");
    assert.deepEqual(copies.map(item => item.content_kind), ["text", "document"]);
    assert.deepEqual(next.draft.attachment_ids, ["asset_1"]); assert.deepEqual(next.draft.intended_config.document_asset_ids, ["asset_2"]);
    assert.equal(next.draft.content, ""); assert.equal(next.draft.intended_config.input_policy.instruction_override, "Fresh local instructions");
    assert.deepEqual(next.draft.intended_config.memory_entry_ids, ["notes"]); assert.deepEqual(next.draft.intended_config.project_file_refs, ["allowed.txt"]);
    assert.deepEqual(harness.state.conversations.conv_a.transcript, frozen.transcript); assert.deepEqual(harness.state.conversations.conv_a.current_run, frozen.current_run);
    assert.equal(harness.state.requests.commands.length, 0, "fresh copies cannot dispatch model work");
    await waitFor(() => assert.equal(textarea(renderer).props.value, ""), "fresh owner activated without old task/history");
    assert.ok([...harness.state.assets.values()].filter(item => item.session_id === "conv_new").every(item => !originals.some(original => original.id === item.id)));
  } finally { if (renderer) await closeHarness(renderer, harness); }
}

async function checkFreshScopeFailure() {
  const harness = makeHarness({ aRun: null, threadARun: null, threadNewRun: null,
    readiness: ({ payload }) => ({ status: "ready", can_send: true, issues: [], selection: null, input_preview: { policy: payload.overrides.input_policy ?? {}, sources: sourceRows({}), token_counting_method: "estimate" } }),
  });
  harness.state.conversations.conv_a.draft = { revision: 1, content: "Keep my current task", attachment_ids: [], intended_config: { document_asset_ids: ["unavailable-in-this-chat"], input_policy: { version: 1, instruction_override: "Keep this behaviour" } } };
  let renderer;
  try {
    renderer = await renderChat(vite, harness);
    await waitFor(() => button(renderer, "Conversation A"), "scope failure history");
    await act(async () => button(renderer, "Conversation A").props.onClick());
    await waitFor(() => assert.equal(textarea(renderer).props.disabled, false), "original scope selected");
    await act(async () => renderer.root.find(node => node.type?.name === "ChatMeasurements").props.onInspect());
    await waitFor(() => button(renderer, "Fresh chat with these choices"), "scope checked before copying");
    await act(async () => button(renderer, "Fresh chat with these choices").props.onClick());
    await waitFor(() => assert.match(textOf(renderer.root), /selected file is no longer available in this chat/), "unavailable scope is explained");
    assert.equal(harness.state.requests.creates.length, 0, "an unavailable file cannot create or broaden a new Chat owner");
    assert.equal(harness.state.requests.assetUploads.length, 0); assert.equal(harness.state.requests.commands.length, 0);
    assert.equal(textarea(renderer).props.value, "Keep my current task");
    assert.equal(renderer.root.findAll(node => node.type?.name === "AgentInputs").length, 1, "failed copying keeps the original inspector and choices");
  } finally { if (renderer) await closeHarness(renderer, harness); }
}

async function checkMountedChat() {
  const accepted = run("accepted-run", "running");
  accepted.effective_setup = { input_sources: sourceRows({}), policy: "frozen" };
  const queued = { id: "queued", revision: 1, status: "queued", task: "Saved queued task", attachment_ids: [], intended_config: {}, frozen_config: { input_policy: { version: 1, tool_loading: "always" } } };
  const harness = makeHarness({ aRun: accepted, threadARun: accepted, commandProjectsRun: true,
    resolveSetup: payload => ({ configuration: payload.overrides, instruction_layers: [], input_sources: sourceRows(payload.overrides.input_policy ?? {}) }),
    readiness: ({ payload }) => ({ status: "ready", can_send: true, issues: [], selection: null, input_preview: { policy: payload.overrides.input_policy ?? {}, sources: sourceRows(payload.overrides.input_policy ?? {}), prepared: false, token_counting_method: "estimate" } }),
  });
  harness.state.conversations.conv_a.queue = [queued];
  harness.state.conversations.conv_a.draft = { revision: 1, content: "Next question", attachment_ids: [], intended_config: { input_policy: { version: 1, tool_loading: "when_needed", instruction_override: "Existing local instructions" } } };
  const frozenRun = structuredClone(accepted), frozenQueue = structuredClone(queued);
  let renderer;
  try {
    renderer = await renderChat(vite, harness);
    await waitFor(() => button(renderer, "Conversation A"), "history ready");
    await act(async () => button(renderer, "Conversation A").props.onClick());
    await waitFor(() => assert.equal(textarea(renderer).props.disabled, false), "running Chat selected");
    await act(async () => renderer.root.find(node => node.type?.name === "ChatMeasurements").props.onInspect());
    await waitFor(() => assert.ok(renderer.root.findAllByType("textarea").some(node => node.props.value === "Existing local instructions")), "restored local override visible");
    await waitFor(() => renderer.root.findByProps({ "aria-label": "Loading for Reference notes" }), "lazy Chat sources loaded");
    await act(async () => renderer.root.findAllByType("textarea").find(node => node.props.value === "Existing local instructions").props.onChange({ target: { value: "Lean local behaviour" } }));
    await act(async () => renderer.root.findByProps({ "aria-label": "Loading for Reference notes" }).props.onChange({ target: { value: "off" } }));
    await act(async () => renderer.root.findByProps({ "aria-label": "Always include Echo" }).props.onChange({ target: { checked: true } }));
    assert.equal(harness.state.requests.commands.length, 0, "source editing cannot dispatch model work");
    await act(async () => renderer.root.findAllByType("button").find(node => node.props["aria-label"] === "Close" && node.parent.type === "header").props.onClick());
    await act(async () => button(renderer, "Conversation B").props.onClick());
    await waitFor(() => assert.equal(harness.state.conversations.conv_a.draft.intended_config.input_policy.instruction_override, "Lean local behaviour"), "navigation persists input policy");
    const policy = harness.state.conversations.conv_a.draft.intended_config.input_policy;
    assert.equal(policy.reference_loading.notes, "off"); assert.deepEqual(policy.pinned_tools, ["echo"]);
    assert.deepEqual(harness.state.conversations.conv_a.current_run.effective_setup, frozenRun.effective_setup, "running admission is unchanged");
    assert.deepEqual(harness.state.conversations.conv_a.queue[0].frozen_config, frozenQueue.frozen_config, "queued admission is unchanged");
    await act(async () => button(renderer, "Conversation A").props.onClick());
    await waitFor(() => assert.equal(textarea(renderer).props.disabled, false), "restored Chat bound");
    await act(async () => renderer.root.find(node => node.type?.name === "ChatMeasurements").props.onInspect());
    await waitFor(() => assert.ok(renderer.root.findAllByType("textarea").some(node => node.props.value === "Lean local behaviour")), "policy survives multiple mounted Chat switches");
    await act(async () => button(renderer, "Fresh chat with these choices").props.onClick());
    await waitFor(() => assert.equal(renderer.root.findAll(node => node.type?.name === "AgentInputs").length, 0), "fresh Chat closes inspector");
    await act(async () => renderer.root.find(node => node.type?.name === "ChatMeasurements").props.onInspect());
    await waitFor(() => assert.ok(renderer.root.findAllByType("textarea").some(node => node.props.value === "Lean local behaviour")), "fresh Chat keeps chosen instructions");
    assert.deepEqual(harness.state.conversations.conv_a.queue[0].frozen_config, frozenQueue.frozen_config);
  } finally { if (renderer) await closeHarness(renderer, harness); }
}

async function checkChatSaveToAgent() {
  let agents = [{ id: "saved-agent", current_version_id: "agent-v1", name: "Reusable researcher", role: "Research", configuration: { instructions: "Saved behaviour", presented_tools: ["echo"], connection_ids: ["retained-connection"], helper_agent_ids: ["retained-helper"], input_policy: { version: 1, tool_loading: "when_needed" } } }];
  const writes = [];
  const accepted = run("save-snapshot", "running");
  accepted.effective_setup = { selected_agent_setup_version_id: "agent-v1", instructions: "Frozen instructions" };
  const harness = makeHarness({ aRun: accepted, threadARun: accepted, agentSetups: agents,
    resolveSetup: payload => ({ configuration: { ...(payload.agent_setup_version_id || payload.agent_setup_id ? agents[0].configuration : {}), ...payload.overrides }, instruction_layers: [], input_sources: sourceRows(payload.overrides.input_policy ?? {}) }),
    readiness: ({ payload }) => ({ status: "ready", can_send: true, issues: [], selection: null, input_preview: { policy: payload.overrides.input_policy ?? {}, sources: sourceRows(payload.overrides.input_policy ?? {}), prepared: false, token_counting_method: "estimate" } }),
    requestOverride: ({ req, res, url, body }) => {
      if (req.method === "PATCH" && url.pathname === "/v1/agent-setups/saved-agent") {
        const payload = JSON.parse(body); writes.push(payload);
        agents[0] = { ...agents[0], configuration: payload.configuration, current_version_id: "agent-v2" };
        respond(res, 200, agents[0]); return true;
      }
    },
  });
  harness.state.conversations.conv_a.agent_setup_id = "saved-agent";
  harness.state.conversations.conv_a.agent_setup_version_id = "agent-v1";
  harness.state.conversations.conv_a.draft = { revision: 1, content: "Continue research", attachment_ids: [], intended_config: { input_policy: { version: 1, instruction_override: "My local full instructions", reference_loading: { notes: "off" } } } };
  let renderer;
  try {
    renderer = await renderChat(vite, harness);
    await waitFor(() => button(renderer, "Conversation A"), "save history ready");
    await act(async () => button(renderer, "Conversation A").props.onClick());
    await waitFor(() => assert.equal(textarea(renderer).props.disabled, false), "saved agent Chat bound");
    await act(async () => renderer.root.find(node => node.type?.name === "ChatMeasurements").props.onInspect());
    await waitFor(() => assert.match(textOf(renderer.root), /Reusable destination: Reusable researcher/), "explicit reusable destination visible");
    assert.equal(writes.length, 0);
    await act(async () => button(renderer, "Save to agent").props.onClick());
    await waitFor(() => assert.equal(writes.length, 1), "explicit agent version save");
    assert.equal(writes[0].base_version, "agent-v1");
    assert.equal(writes[0].configuration.instructions, "My local full instructions");
    assert.equal(writes[0].configuration.input_policy.instruction_override, null, "local replacement becomes reusable authored instructions");
    assert.equal(writes[0].configuration.input_policy.reference_loading.notes, "off");
    assert.deepEqual(writes[0].configuration.connection_ids, ["retained-connection"]);
    assert.deepEqual(writes[0].configuration.helper_agent_ids, ["retained-helper"]);
    assert.equal(Object.hasOwn(writes[0].configuration, "approval_mode"), false, "saving behaviour cannot move Chat-owned access into an agent");
    assert.equal(harness.state.conversations.conv_a.current_run.effective_setup.selected_agent_setup_version_id, "agent-v1", "saving affects future work while accepted versions stay frozen");
  } finally { if (renderer) await closeHarness(renderer, harness); }
}

async function checkChatCreateAgent() {
  const writes = [], agents = [];
  const accepted = run("new-agent-snapshot", "running");
  const harness = makeHarness({ aRun: accepted, threadARun: accepted, agentSetups: agents,
    resolveSetup: payload => ({ configuration: payload.overrides, instruction_layers: [], input_sources: sourceRows(payload.overrides.input_policy ?? {}) }),
    readiness: ({ payload }) => ({ status: "ready", can_send: true, issues: [], selection: null, input_preview: { policy: payload.overrides.input_policy ?? {}, sources: sourceRows(payload.overrides.input_policy ?? {}), prepared: false, token_counting_method: "estimate" } }),
    requestOverride: ({ req, res, url, body }) => {
      if (req.method === "POST" && url.pathname === "/v1/agent-setups") {
        const payload = JSON.parse(body); writes.push(payload);
        const saved = { ...payload, id: "new-agent", current_version_id: "new-agent-v1" }; agents.push(saved);
        respond(res, 200, saved); return true;
      }
    },
  });
  harness.state.conversations.conv_a.draft = { revision: 1, content: "Keep these choices", attachment_ids: [], intended_config: { presented_tools: ["echo"], memory_entry_ids: ["notes"], input_policy: { version: 1, instruction_override: "Reusable instructions", excluded_sources: ["conversation_instructions"], reference_loading: { notes: "always" } } } };
  let renderer;
  try {
    renderer = await renderChat(vite, harness);
    await waitFor(() => button(renderer, "Conversation A"), "new-agent history ready");
    await act(async () => button(renderer, "Conversation A").props.onClick());
    await waitFor(() => assert.equal(textarea(renderer).props.disabled, false), "new-agent Chat bound");
    await act(async () => renderer.root.find(node => node.type?.name === "ChatMeasurements").props.onInspect());
    await waitFor(() => renderer.root.findByProps({ "aria-label": "Agent name for saved instructions" }), "new reusable destination is explicit");
    await act(async () => renderer.root.findByProps({ "aria-label": "Agent name for saved instructions" }).props.onChange({ target: { value: "Lean reusable agent" } }));
    await act(async () => button(renderer, "Save to agent").props.onClick());
    await waitFor(() => assert.equal(writes.length, 1), "new agent saved explicitly");
    const configuration = writes[0].configuration;
    assert.equal(writes[0].name, "Lean reusable agent");
    assert.equal(configuration.instructions, "Reusable instructions");
    assert.deepEqual(configuration.input_policy.excluded_sources, ["agent_instructions"], "promoted behaviour exclusions follow their new owner");
    assert.deepEqual(configuration.memory_entry_ids, ["notes"]);
    assert.deepEqual(configuration.presented_tools, ["echo"]);
    assert.equal(Object.hasOwn(configuration, "approval_mode"), false);
    assert.equal(Object.hasOwn(configuration, "model_configuration_id"), false, "a new reusable agent uses the Chat model");
    await act(async () => renderer.root.findAllByType("button").find(node => node.props["aria-label"] === "Close" && node.parent.type === "header").props.onClick());
    await act(async () => button(renderer, "Conversation B").props.onClick());
    await waitFor(() => assert.deepEqual(harness.state.conversations.conv_a.draft.intended_config.input_policy.excluded_sources, ["agent_instructions"]), "the current Chat keeps promoted exclusion ownership");
  } finally { if (renderer) await closeHarness(renderer, harness); }
}
