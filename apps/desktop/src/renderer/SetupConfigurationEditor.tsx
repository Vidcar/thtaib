import { configurationLabel, findConfiguration } from "./configurationLabel";
import { useEffect, useId, useState } from "react";
import { api } from "./api";
import { connectionsApi } from "./connectionsApi";
import { errorMessage } from "./errors";
import { HoverHelp } from "./HoverHelp";
import { settingValue, useSetupPreview, type EffectiveSetting } from "./effectiveSettings";
import type { Deployment, KnowledgeEntry, ModelBundle, RunProfile } from "./types";
import type { SetupConfiguration } from "./workspaceApi";

interface SelectionOption { id: string; name: string; description?: string; available?: boolean; unavailable_reason?: string | null }
export interface SetupCatalogue {
  deployments: Deployment[]; bundles: ModelBundle[]; profiles: RunProfile[]; knowledge: KnowledgeEntry[];
  tools: SelectionOption[]; connections: SelectionOption[];
}
export function useSetupCatalogue() {
  const [catalogue, setCatalogue] = useState<SetupCatalogue>({ deployments: [], bundles: [], profiles: [], knowledge: [], tools: [], connections: [] });
  const [error, setError] = useState("");
  useEffect(() => {
    let cancelled = false;
    void Promise.all([api.deployments(), api.bundles(), api.profiles(), api.knowledgeEntries(), api.agentTools(), connectionsApi.list()]).then(([deployments, bundles, profiles, knowledge, tools, connections]) => {
      if (!cancelled) setCatalogue({ deployments, bundles, profiles, knowledge, tools: tools.tools ?? tools.enabled.map(id => ({ id, name: id, description: "Tool details unavailable" })), connections: connections.map(item => ({ ...item, available: !!(item.enabled && item.last_tested_at && !item.last_error), unavailable_reason: item.last_error || (!item.enabled ? "Connection is disabled" : !item.last_tested_at ? "Test this connection first" : null) })) });
    }).catch(failure => { if (!cancelled) setError(errorMessage(failure)); });
    return () => { cancelled = true; };
  }, []);
  return { catalogue, error };
}

function inheritedLabel(fact?: EffectiveSetting) {
  if (fact?.inherited_source) return `${settingValue(fact.inherited_value)} · ${fact.inherited_source}`;
  return fact?.known ? `${settingValue(fact.value)} · ${fact.source}` : "Use inherited value";
}

function SelectionList({ title, values, options, fact, disabled, onChange }: { title: string; values: string[] | null | undefined; options: SelectionOption[]; fact?: EffectiveSetting; disabled: boolean; onChange: (values: string[] | null) => void }) {
  const id = useId();
  const missing = (values ?? []).filter(value => !options.some(option => option.id === value));
  return <div className="setup-selection-group"><div className="setup-selection-heading"><label htmlFor={id}>{title}</label><select id={id} value={values == null ? "inherit" : "choose"} disabled={disabled} onChange={event => onChange(event.target.value === "inherit" ? null : [])}><option value="inherit">{inheritedLabel(fact)}</option><option value="choose">Choose explicitly</option></select></div>
    {values != null ? <div className="setup-selection-options">{options.length || missing.length ? <>{options.map(option => <label className="check-row" key={option.id}><input type="checkbox" checked={values.includes(option.id)} disabled={disabled || (option.available === false && !values.includes(option.id))} onChange={event => onChange(event.target.checked ? [...values, option.id] : values.filter(value => value !== option.id))} /><span>{option.name}{option.description || option.unavailable_reason ? <HoverHelp title={option.name}>{option.description}{option.unavailable_reason ? ` ${option.unavailable_reason}.` : ""}</HoverHelp> : null}</span></label>)}{missing.map(value => <label className="check-row" key={value}><input type="checkbox" checked disabled={disabled} onChange={() => onChange(values.filter(item => item !== value))} /><span>Unavailable selection <HoverHelp title="Unavailable dependency">{value}. Remove this selection or restore the record.</HoverHelp></span></label>)}</> : <span className="hint">Nothing available.</span>}<span className="hint">{values.length ? `${values.length} selected` : "None"}</span></div> : null}
  </div>;
}

export function SetupConfigurationEditor({ value, onChange, catalogue, disabled = false, requirements = false, scope = "agent", projectId = null }: { value: SetupConfiguration; onChange: (value: SetupConfiguration) => void; catalogue: SetupCatalogue; disabled?: boolean; requirements?: boolean; scope?: "application" | "project" | "agent"; projectId?: string | null }) {
  const patch = (next: Partial<SetupConfiguration>) => onChange({ ...value, ...next });
  const preview = useSetupPreview(value, projectId, null, scope);
  const facts = preview.data?.effective_values ?? {};
  const modelChoice = value.model_configuration_id ? `configuration:${findConfiguration(catalogue.profiles, value.model_configuration_id)?.id ?? value.model_configuration_id}` : value.deployment_id ? `deployment:${value.deployment_id}` : "";
  const configurations = catalogue.profiles.filter(item => item.bundle_id);
  const external = catalogue.deployments.filter(item => item.scope === "connected");
  const knownModel = !modelChoice || configurations.some(item => modelChoice === `configuration:${item.id}`) || external.some(item => modelChoice === `deployment:${item.id}`);
  const knowledge = (kind: KnowledgeEntry["kind"]) => catalogue.knowledge.filter(entry => entry.kind === kind && entry.enabled !== false && entry.scope_bound !== false).map(entry => ({ id: entry.current_version_id, name: entry.display_name || (kind === "memory" ? "Untitled memory" : kind === "skill" ? "Untitled skill" : "Untitled instruction") }));
  const count = (key: keyof SetupConfiguration) => value[key] == null ? inheritedLabel(facts[key]) : settingValue(value[key]);
  return <div className="setup-configuration-editor">
    <div className="setup-form-grid"><label>Model<select value={modelChoice} disabled={disabled} onChange={event => { const choice = event.target.value; patch({ model_configuration_id: choice.startsWith("configuration:") ? choice.slice(14) : null, deployment_id: choice.startsWith("deployment:") ? choice.slice(11) : null, bundle_id: null, profile_id: null, inherit_deployment_settings: null }); }}><option value="">{scope === "agent" ? "Use chat’s model" : scope === "application" ? "Use loaded model" : "Use application default"}</option>{configurations.map(item => <option key={item.id} value={`configuration:${item.id}`}>{configurationLabel(item, catalogue.bundles.find(bundle => bundle.id === item.bundle_id)?.display_name)}</option>)}{external.map(item => <option key={item.id} value={`deployment:${item.id}`}>{item.display_name} · connected</option>)}{!knownModel ? <option value={modelChoice}>Unavailable configuration</option> : null}</select></label>
    <label>Access<HoverHelp title="Access">Ask pauses before edits, shell commands and external effects. Approve for me permits project edits with verified recovery. Full access permits enabled tools. Saved permissions are named exceptions. Host shell runs with your Windows user’s authority.</HoverHelp><select value={value.approval_mode ?? ""} disabled={disabled} onChange={event => patch({ approval_mode: (event.target.value || null) as SetupConfiguration["approval_mode"] })}><option value="">{inheritedLabel(facts.approval_mode)}</option><option value="ask">Ask for approval</option><option value="approve_for_me">Approve for me</option><option value="full_access">Full access</option></select></label></div>
    <label>Instructions<HoverHelp title="Instructions">Adds to application and project guidance. Instructions never grant additional permissions.</HoverHelp><textarea value={value.instructions ?? ""} disabled={disabled} onChange={event => patch({ instructions: event.target.value || null })} placeholder="How should this agent work?" rows={4} /></label>
    {preview.error ? <p className="hint" role="status">Settings preview: {preview.error}</p> : null}
    <details className="setup-options"><summary>Tools and connections <span className="hint">{count("presented_tools")}</span></summary><SelectionList title="Tools" values={value.presented_tools} options={catalogue.tools} fact={facts.presented_tools} disabled={disabled} onChange={presented_tools => patch({ presented_tools })} /><SelectionList title="Connections" values={value.connection_ids} options={catalogue.connections} fact={facts.connection_ids} disabled={disabled} onChange={connection_ids => patch({ connection_ids })} /></details>
    <details className="setup-options"><summary>Knowledge</summary>{(["memory", "skill", "protected_instruction"] as const).map(kind => { const key = kind === "memory" ? "memory_version_refs" : kind === "skill" ? "skill_version_refs" : "protected_instruction_version_refs"; return <SelectionList key={kind} title={kind === "memory" ? "Memories" : kind === "skill" ? "Skills" : "Instructions"} values={value[key]} options={knowledge(kind)} fact={facts[key]} disabled={disabled} onChange={next => patch({ [key]: next })} />; })}</details>
    {requirements ? <details className="setup-options"><summary>Workspace requirements<HoverHelp title="Requirements">Describes what this agent needs; does not grant access.</HoverHelp></summary><div className="setup-form-grid">{(["requires_project", "requires_host_shell"] as const).map(key => <label key={key}>{key === "requires_project" ? "Project folder" : "Shell access"}<select disabled={disabled} value={value[key] == null ? "inherit" : value[key] ? "required" : "optional"} onChange={event => patch({ [key]: event.target.value === "inherit" ? null : event.target.value === "required" })}><option value="inherit">{inheritedLabel(facts[key])}</option><option value="required">Required</option><option value="optional">Not required</option></select></label>)}</div></details> : null}
  </div>;
}
