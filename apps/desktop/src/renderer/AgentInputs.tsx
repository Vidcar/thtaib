import { useEffect, useId, useRef, useState } from "react";
import { api } from "./api";
import { CompactDialog } from "./CompactDialog";
import { Notice } from "./Notice";
import { SettingRow, SegmentedChoice } from "./CompactControls";
import { workspaceApi, type SetupConfiguration, type InputPreviewContext } from "./workspaceApi";
import { excludeInputSource, referenceMode, type AgentInputPolicy, type AgentInputPreview, type AgentInputSource, type ReferenceLoading } from "./agentInputPolicy";
import { errorMessage } from "./errors";
import type { AgentRun, WorkbenchTab } from "./types";
import "./AgentInputs.css";

const modeLabel = (mode: string) => ({ off: "Off", when_needed: "When needed", always: "Always included", required: "Required" }[mode] ?? mode);
const estimate = (tokens?: number | null) => tokens == null ? "Cost not reported" : `~${tokens.toLocaleString()} tokens`;

export function AgentInputs(props: {
  configuration: SetupConfiguration;
  projectId?: string | null;
  conversationId?: string | null;
  context?: InputPreviewContext;
  agentSetupVersionId?: string | null;
  scope?: "agent" | "conversation";
  preview?: AgentInputPreview | null;
  run?: AgentRun | null;
  hasHistory?: boolean;
  disabled?: boolean;
  effectiveTools?: string[] | null;
  preparingFresh?: boolean;
  onChange: (configuration: SetupConfiguration) => void;
  onClose: () => void;
  onEditSource?: (tab: WorkbenchTab, id?: string) => void;
  onFreshChat?: (policy: AgentInputPolicy) => void;
  onSaveToAgent?: (name?: string) => Promise<void>;
  agentName?: string;
}) {
  const id = useId();
  const [view, setView] = useState<"next" | "actual">("next");
  const [sources, setSources] = useState<AgentInputSource[]>(props.preview?.sources ?? []);
  const [resolvedPolicy, setResolvedPolicy] = useState<AgentInputPolicy | null>(props.preview?.policy ?? null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [diagnostic, setDiagnostic] = useState<AgentRun | null>(null);
  const [requestIndex, setRequestIndex] = useState(-1);
  const [captureRevision, setCaptureRevision] = useState(0);
  const [saving, setSaving] = useState(false);
  const [saveName, setSaveName] = useState("");
  const [savedMessage, setSavedMessage] = useState("");
  const revision = useRef(0);
  const serialized = JSON.stringify(props.configuration);
  const contextKey = JSON.stringify(props.context ?? {});
  const authoredPolicy = props.configuration.input_policy ?? {};
  const inheritedPolicy = resolvedPolicy ?? props.preview?.policy ?? {};
  const policy = { ...inheritedPolicy, ...authoredPolicy, reference_loading: { ...inheritedPolicy.reference_loading, ...authoredPolicy.reference_loading } };
  const patchPolicy = (next: AgentInputPolicy) => props.onChange({ ...props.configuration, input_policy: { ...authoredPolicy, ...next, version: 1 } });
  const patchReference = (source: AgentInputSource, mode: ReferenceLoading) => patchPolicy({ reference_loading: { ...authoredPolicy.reference_loading, [source.entry_id!]: mode }, ...(mode !== "off" && policy.excluded_sources?.includes(source.id) ? { excluded_sources: policy.excluded_sources.filter(id => id !== source.id) } : {}) });
  const actual = diagnostic?.model_requests ?? [];
  const captured = actual[requestIndex < 0 ? actual.length - 1 : requestIndex];

  useEffect(() => {
    if (view !== "next") return;
    const request = ++revision.current;
    setLoading(true); setError("");
    const configuration = JSON.parse(serialized) as SetupConfiguration;
    const inspection = props.conversationId
      ? workspaceApi.chatReadiness(props.conversationId, configuration, props.agentSetupVersionId, true, JSON.parse(contextKey) as InputPreviewContext).then(result => ({ sources: result.input_preview?.sources ?? result.selection?.input_sources, policy: result.input_preview?.policy ?? result.selection?.configuration.input_policy }))
      : workspaceApi.resolveSetup(props.projectId ?? null, props.agentSetupVersionId ?? null, configuration, props.scope ?? "conversation", true).then(result => ({ sources: result.input_sources, policy: result.configuration.input_policy }));
    void inspection.then(result => {
        if (request === revision.current) { setSources(result.sources ?? props.preview?.sources ?? []); setResolvedPolicy(result.policy ?? props.preview?.policy ?? null); }
      }).catch(failure => { if (request === revision.current) setError(errorMessage(failure)); })
      .finally(() => { if (request === revision.current) setLoading(false); });
    return () => { ++revision.current; };
  }, [serialized, contextKey, props.projectId, props.conversationId, props.agentSetupVersionId, props.scope, view]);

  useEffect(() => {
    if (view !== "actual" || !props.run?.id) return;
    let cancelled = false;
    setLoading(true); setError(""); setDiagnostic(null); setRequestIndex(-1);
    void api.agentRunInputs(props.run.id).then(result => { if (!cancelled) setDiagnostic(result); })
      .catch(failure => { if (!cancelled) setError(errorMessage(failure)); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [view, props.run?.id, props.run?.status, props.run?.model_requests?.length, captureRevision]);

  function edit(source: AgentInputSource) {
    if ((source.id === "agent_instructions" || source.id === "conversation_instructions") && props.scope !== "agent") {
      patchPolicy({ instruction_override: source.content ?? "" });
    } else if (source.id === "agent_instructions" && props.scope === "agent") {
      if (typeof document !== "undefined") document.getElementById(`${id}-instructions`)?.focus();
    } else if (source.entry_id) props.onEditSource?.("knowledge", source.entry_id);
    else if (source.id === "model_instructions") props.onEditSource?.("models");
    else props.onEditSource?.("agents");
  }
  async function saveAgent() {
    if (!props.onSaveToAgent || saving) return;
    setSaving(true); setError(""); setSavedMessage("");
    try { await props.onSaveToAgent(props.agentName ? undefined : saveName.trim()); setSavedMessage("Saved to agent. Accepted work keeps its original instructions."); }
    catch (failure) { setError(errorMessage(failure)); }
    finally { setSaving(false); }
  }
  const coldSources: AgentInputSource[] = props.conversationId ? [] : [
    ...(props.context?.attachment_ids ?? []).map(assetId => ({ id: `attachment:${assetId}`, title: "Attached file", kind: "attachment", origin: "Message selection", reason: "Selected file. Exact extracted content and cost are checked when this request is prepared.", mode: "when_needed", path: assetId })),
    ...(props.context?.project_file_refs ?? []).map(path => ({ id: `project_file:${path}`, title: path, kind: "project_file", origin: "Bound project selection", reason: "Selected authorized project file. Exact content and cost are checked when this request is prepared.", mode: "when_needed", path })),
    ...(props.context?.shortcut_ids ?? []).map(shortcutId => ({ id: `task:${shortcutId}`, title: `Selected action · ${shortcutId}`, kind: "task", origin: "Message selection", reason: "Saved action instructions are frozen when this message is accepted.", mode: "always" })),
  ];
  const shownSources = view === "actual" ? captured?.input_sources ?? [] : [...sources, ...coldSources.filter(row => !sources.some(source => source.id === row.id))];
  const selectedTools = props.effectiveTools ?? props.configuration.presented_tools;
  const toolsOff = selectedTools?.length === 0;
  const referenceReaderExcluded = policy.excluded_sources?.includes("tool:read_reference") ?? false;
  const fileReaderEnabled = !policy.excluded_sources?.includes("tool:read_file") && (selectedTools == null || selectedTools.includes("read_file"));
  const deferredWithoutReading = view === "next" ? shownSources.filter(source => source.entry_id && (source.kind === "memory" || source.kind === "skill") && referenceMode(policy, source) === "when_needed" && (toolsOff || referenceReaderExcluded && (source.kind === "memory" || !fileReaderEnabled))) : [];
  const localText = props.scope === "agent" ? props.configuration.instructions ?? "" : policy.instruction_override;
  const replaced = props.scope === "agent" || localText != null;
  const sourceCost = shownSources.filter(source => source.mode !== "off").reduce((sum, source) => sum + (source.estimated_tokens ?? 0), 0);
  const excluded = Boolean(policy.excluded_sources?.length || Object.values(policy.reference_loading ?? {}).includes("off"));
  return <CompactDialog title="What the agent sees" labelledBy={`${id}-title`} onClose={props.onClose}>
    <div className="agent-inputs">
      <SegmentedChoice label="Input view" bare value={view} options={[{ value: "next", label: props.scope === "agent" ? "Agent preview" : "Next message" }, { value: "actual", label: "Actual requests" }]} onChange={next => setView(next as typeof view)} />
      <p className="hint">{view === "next" ? "Preview of your current choices. Sending freezes the saved versions; history, files and model counts are checked when the request is prepared." : "Captured at the model boundary, after context processing. Redaction and capture gaps apply."}</p>
      {error ? <Notice tone="error">{error}</Notice> : null}
      {loading ? <p className="hint" role="status">Reading inputs…</p> : null}
      {view === "actual" ? <>
        {props.run ? <button type="button" disabled={loading} onClick={() => setCaptureRevision(value => value + 1)}>Refresh captures</button> : null}
        {!props.run ? <p className="hint">Send a message to inspect its actual requests.</p> : actual.length ? <SettingRow label="Model call"><select aria-label="Captured model call" value={requestIndex < 0 ? actual.length - 1 : requestIndex} onChange={event => setRequestIndex(Number(event.target.value))}>{actual.map((call, index) => <option key={index} value={index}>Call {index + 1} · {call.at}{call.transport_attempted ? " · sent" : " · prepared"}</option>)}</select></SettingRow> : !loading ? <p className="hint">No retained request capture. Capture settings are in Knowledge.</p> : null}
        {captured?.capture_gaps?.length ? <Notice tone="warn">{captured.capture_gaps.join(" ")}</Notice> : null}
      </> : <>
        <SettingRow label="Tool definitions" help="When needed keeps enabled tools discoverable and supplies their definitions as they are needed. Always include supplies every enabled definition."><select aria-label="Tool definition loading" disabled={props.disabled} value={policy.tool_loading ?? "when_needed"} onChange={event => patchPolicy({ tool_loading: event.target.value as "when_needed" | "always" })}><option value="when_needed">When needed</option><option value="always">Always include</option></select></SettingRow>
        <details className="agent-input-instructions" open={replaced}>
          <summary>{props.scope === "agent" ? "Agent instructions" : replaced ? "Instructions for this chat · local replacement" : "Instructions for this chat"}</summary>
          {!replaced ? <button type="button" disabled={props.disabled} onClick={() => patchPolicy({ instruction_override: sources.find(source => source.id === "agent_instructions" || source.id === "conversation_instructions")?.content ?? "" })}>Replace agent instructions</button> : <>
            <SettingRow stacked label={props.scope === "agent" ? "Instructions" : "Local instructions"} htmlFor={`${id}-instructions`}><textarea id={`${id}-instructions`} rows={5} value={localText ?? ""} disabled={props.disabled} onChange={event => props.scope === "agent" ? props.onChange({ ...props.configuration, instructions: event.target.value || null }) : patchPolicy({ instruction_override: event.target.value })} placeholder="How should this agent work?" /></SettingRow>
            {props.scope !== "agent" ? <button type="button" disabled={props.disabled} onClick={() => patchPolicy({ instruction_override: null })}>{props.agentName ? "Use agent instructions" : "Reset replacement"}</button> : null}
          </>}
          {props.scope !== "agent" ? <p className="hint">Changes apply to this chat's next message. Empty replacement text supplies no agent instructions.</p> : null}
        </details>
      </>}
      {deferredWithoutReading.length ? <Notice tone="warn" action={<div className="actions"><button type="button" disabled={props.disabled} onClick={() => patchPolicy({ reference_loading: { ...authoredPolicy.reference_loading, ...Object.fromEntries(deferredWithoutReading.map(source => [source.entry_id!, "always" as const])) } })}>Include now</button><button type="button" disabled={props.disabled} onClick={() => patchPolicy({ reference_loading: { ...authoredPolicy.reference_loading, ...Object.fromEntries(deferredWithoutReading.map(source => [source.entry_id!, "off" as const])) } })}>Remove</button>{!toolsOff || props.onEditSource ? <button type="button" disabled={props.disabled} onClick={() => toolsOff ? props.onEditSource?.("agents") : patchPolicy({ excluded_sources: policy.excluded_sources?.filter(source => source !== "tool:read_reference") })}>Enable reading</button> : null}</div>}>{toolsOff ? "Tools are off. References set to When needed need reading. Include their full text, remove them from future inputs, or enable reading in the saved agent." : "References set to When needed have no enabled reading route. Include their full text, remove them from future inputs, or enable reading."}</Notice> : null}
      <div className="agent-input-sources" aria-label={view === "actual" ? "Actual input sources" : "Next input sources"}>
        {!loading && shownSources.length ? <p className="hint">Source estimate: {estimate(sourceCost)}. {props.preview?.token_counting_method ?? shownSources.find(source => source.token_counting_method)?.token_counting_method ?? "Approximate; model counts may differ."}</p> : null}
        {shownSources.map(source => {
          const isExcluded = policy.excluded_sources?.includes(source.id) || source.mode === "off";
          return <details key={source.id} className="agent-input-source" data-excluded={isExcluded && view === "next" || undefined}>
            <summary><span><strong>{source.title}</strong><small>{source.origin} · {source.required ? "Required" : modeLabel(source.mode)}</small></span><small title={source.token_counting_method}>{estimate(source.estimated_tokens)}</small></summary>
            <p className="hint">{source.reason}</p>
            {view === "next" && !source.required || source.entry_id ? <div className="agent-input-source-actions">
              {view === "next" && !source.required ? <>
                {source.entry_id && (source.kind === "memory" || source.kind === "skill") ? <select aria-label={`Loading for ${source.title}`} value={referenceMode(policy, source)} disabled={props.disabled} onChange={event => patchReference(source, event.target.value as ReferenceLoading)}><option value="off">Off</option><option value="when_needed">When needed</option><option value="always">Always include</option></select> : <button type="button" disabled={props.disabled} onClick={() => patchPolicy({ excluded_sources: excludeInputSource(policy, source.id, !isExcluded).excluded_sources, ...(isExcluded && source.entry_id ? { reference_loading: { ...authoredPolicy.reference_loading, [source.entry_id]: "always" } } : {}) })}>{isExcluded ? "Include" : "Exclude"}</button>}
                {source.tool_name ? <label className="check-row"><input type="checkbox" aria-label={`Always include ${source.title}`} disabled={props.disabled || Boolean(isExcluded)} checked={policy.pinned_tools?.includes(source.tool_name) ?? false} onChange={event => patchPolicy({ pinned_tools: event.target.checked ? [...new Set([...(policy.pinned_tools ?? []), source.tool_name!])] : policy.pinned_tools?.filter(name => name !== source.tool_name) ?? [] })} />Always include definition</label> : null}
              </> : null}
              {source.entry_id || view === "next" && source.editable && !source.required ? <button type="button" disabled={props.disabled} onClick={() => edit(source)}>{source.entry_id ? "Open in Knowledge" : (source.id === "agent_instructions" || source.id === "conversation_instructions") && props.scope !== "agent" ? "Edit for this chat" : "Edit source"}</button> : null}
            </div> : null}
            {source.history_hint ? <p className="hint">{source.history_hint}</p> : null}
            {source.available === false ? <p className="hint">Not available in this preview or capture.</p> : null}
            {source.required_tools?.length || source.required_connections?.length || source.requires_project ? <p className="hint">Needs: {[...(source.required_tools ?? []), ...(source.required_connections ?? []).map(name => `Connection ${name}`), source.requires_project ? "Project folder" : ""].filter(Boolean).join(", ")}</p> : null}
            {source.path ? <p className="hint">{source.path}</p> : null}
            {source.version_id ? <p className="hint">Version: {source.version_id}</p> : null}
            {source.content != null ? <pre className="agent-input-source-text">{source.content}</pre> : <p className="hint">{source.mode === "when_needed" ? "Full text is supplied when read." : view === "next" ? source.mode === "off" && source.entry_id ? "Open in Knowledge to view the saved text." : "Text is not loaded in this preview." : "Text is unavailable in this capture."}</p>}
          </details>;
        })}
      </div>
      {view === "actual" && captured ? <>
        <details><summary>Supplied instructions</summary><pre className="agent-input-source-text">{captured.instructions ?? "No captured system text."}</pre></details>
        <details><summary>Supplied tool definitions · {captured.tool_schemas?.length ?? captured.presented_tools?.length ?? 0}</summary>{!captured.tool_schemas ? <p className="hint">This older capture may limit the number or length of tool definitions. Reported capture gaps apply.</p> : null}<pre className="agent-input-source-text">{JSON.stringify(captured.tool_schemas ?? captured.http_payload?.tools ?? captured.presented_tools, null, 2)}</pre></details>
        <details><summary>Supplied messages</summary><pre className="agent-input-source-text">{JSON.stringify(captured.http_payload?.messages ?? "Message text unavailable in this capture.", null, 2)}</pre></details>
      </> : null}
      {props.hasHistory && (excluded || policy.instruction_override != null) ? <Notice tone="info" action={props.onFreshChat ? <button type="button" disabled={props.disabled} onClick={() => props.onFreshChat?.(policy)}>{props.preparingFresh ? "Preparing fresh chat…" : "Fresh chat with these choices"}</button> : undefined}>Earlier messages, tool results or summaries may still contain previously supplied text. Excluding a source changes future inputs; a fresh chat removes that retained history.</Notice> : null}
      {view === "next" && props.onSaveToAgent ? <div className="agent-input-save">
        {!props.agentName ? <SettingRow label="Agent name"><input aria-label="Agent name for saved instructions" value={saveName} disabled={saving} onChange={event => setSaveName(event.target.value)} placeholder="Name this reusable agent" /></SettingRow> : <p className="hint">Reusable destination: {props.agentName}</p>}
        <button type="button" disabled={props.disabled || saving || !props.agentName && !saveName.trim()} onClick={() => void saveAgent()}>{saving ? "Saving…" : "Save to agent"}</button>
      </div> : null}
      {savedMessage ? <p className="hint" role="status">{savedMessage}</p> : null}
    </div>
  </CompactDialog>;
}
