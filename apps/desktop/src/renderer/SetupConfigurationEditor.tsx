import { useEffect, useId, useState } from "react";
import { api, request } from "./api";
import { errorMessage } from "./errors";
import { HoverHelp } from "./HoverHelp";
import type { Deployment, KnowledgeEntry, ModelBundle, RunProfile } from "./types";
import type { SetupConfiguration } from "./workspaceApi";
import type { SchemaConnectionRecord } from "../generated/shared-contracts/openapi";

interface SelectionOption { id: string; name: string; }
export interface SetupCatalogue {
  deployments: Deployment[];
  bundles: ModelBundle[];
  profiles: RunProfile[];
  knowledge: KnowledgeEntry[];
  tools: SelectionOption[];
  connections: SelectionOption[];
}
export function useSetupCatalogue() {
  const [catalogue, setCatalogue] = useState<SetupCatalogue>({ deployments: [], bundles: [], profiles: [], knowledge: [], tools: [], connections: [] });
  const [error, setError] = useState("");
  useEffect(() => {
    let cancelled = false;
    void Promise.all([api.deployments(), api.bundles(), api.profiles(), api.knowledgeEntries(), api.agentTools(), request<SchemaConnectionRecord[]>("/v1/connections")]).then(([deployments, bundles, profiles, knowledge, tools, connections]) => {
      if (!cancelled) setCatalogue({ deployments, bundles, profiles, knowledge, tools: tools.enabled.map(id => ({ id, name: id.replaceAll("_", " ") })), connections: connections.filter(item => item.enabled && item.last_tested_at && !item.last_error) });
    }).catch(failure => { if (!cancelled) setError(errorMessage(failure)); });
    return () => { cancelled = true; };
  }, []);
  return { catalogue, error };
}

function SelectionList({ title, values, options, disabled, onChange }: { title: string; values: string[] | null | undefined; options: SelectionOption[]; disabled: boolean; onChange: (values: string[] | null) => void }) {
  const id = useId();
  const missing = (values ?? []).filter(value => !options.some(option => option.id === value));
  return <div className="setup-selection-group"><div className="setup-selection-heading"><label htmlFor={id}>{title}</label><select id={id} value={values == null ? "inherit" : "choose"} disabled={disabled} onChange={event => onChange(event.target.value === "inherit" ? null : [])}><option value="inherit">Inherit</option><option value="choose">Choose</option></select></div>
    {values != null ? <div className="setup-selection-options">{options.length || missing.length ? <>{options.map(option => <label className="check-row" key={option.id}><input type="checkbox" checked={values.includes(option.id)} disabled={disabled} onChange={event => onChange(event.target.checked ? [...values, option.id] : values.filter(value => value !== option.id))} />{option.name}</label>)}{missing.map(value => <label className="check-row" key={value}><input type="checkbox" checked disabled={disabled} onChange={() => onChange(values.filter(item => item !== value))} /><span>Unavailable saved selection <HoverHelp title="Unavailable dependency">{value}. Remove this selection or restore the missing record before using the setup.</HoverHelp></span></label>)}</> : <p className="hint">Nothing available to select.</p>}<p className="hint">{values.length ? `${values.length} selected` : "None selected; inherited choices will be cleared."}</p></div> : null}
  </div>;
}

export function SetupConfigurationEditor({ value, onChange, catalogue, disabled = false, requirements = false }: { value: SetupConfiguration; onChange: (value: SetupConfiguration) => void; catalogue: SetupCatalogue; disabled?: boolean; requirements?: boolean }) {
  const patch = (next: Partial<SetupConfiguration>) => onChange({ ...value, ...next });
  const modelChoice = value.deployment_id ? `deployment:${value.deployment_id}` : value.bundle_id ? `bundle:${value.bundle_id}` : "";
  const knownModel = !modelChoice || catalogue.deployments.some(item => modelChoice === `deployment:${item.id}`);
  const profileChoice = value.profile_id ?? (value.inherit_deployment_settings === false ? "!none" : "");
  const knowledge = (kind: KnowledgeEntry["kind"]) => catalogue.knowledge.filter(entry => entry.kind === kind && entry.enabled !== false && entry.scope_bound !== false).map(entry => ({ id: entry.current_version_id, name: entry.display_name || (kind === "memory" ? "Untitled memory" : kind === "skill" ? "Untitled skill" : "Untitled instruction") }));
  return <div className="setup-configuration-editor">
    <div className="setup-form-grid"><label>Model<select value={modelChoice} disabled={disabled} onChange={event => { const choice = event.target.value; patch({ deployment_id: choice.startsWith("deployment:") ? choice.slice(11) : null, bundle_id: choice.startsWith("bundle:") ? choice.slice(7) : null }); }}><option value="">Inherit model</option>{catalogue.deployments.length ? <optgroup label="Saved model setups">{catalogue.deployments.map(item => <option key={item.id} value={`deployment:${item.id}`}>{item.display_name || item.id}{item.status === "stopped" ? " · loads when needed" : ""}</option>)}</optgroup> : null}{!knownModel ? <option value={modelChoice}>Unavailable model setup — choose a saved setup</option> : null}</select></label>
    <label>Response preset<select value={profileChoice} disabled={disabled} onChange={event => patch({ profile_id: event.target.value && event.target.value !== "!none" ? event.target.value : null, inherit_deployment_settings: event.target.value === "!none" ? false : null })}><option value="">Inherit preset</option><option value="!none">No preset</option>{catalogue.profiles.map(item => <option key={item.id} value={item.id}>{item.display_name}</option>)}{value.profile_id && !catalogue.profiles.some(item => item.id === value.profile_id) ? <option value={value.profile_id}>Unavailable preset</option> : null}</select></label></div>
    <label>Instructions<textarea value={value.instructions ?? ""} disabled={disabled} onChange={event => patch({ instructions: event.target.value || null })} placeholder="How should the agent approach its work?" rows={4} /></label>
    <p className="hint">Instructions add to application and project guidance. Permissions still apply.</p>
    <details className="setup-options"><summary>Tools and connections</summary><SelectionList title="Tools" values={value.presented_tools} options={catalogue.tools} disabled={disabled} onChange={presented_tools => patch({ presented_tools })} /><SelectionList title="Connections" values={value.connection_ids} options={catalogue.connections} disabled={disabled} onChange={connection_ids => patch({ connection_ids })} /></details>
    <details className="setup-options"><summary>Knowledge</summary><SelectionList title="Memories" values={value.memory_version_refs} options={knowledge("memory")} disabled={disabled} onChange={memory_version_refs => patch({ memory_version_refs })} /><SelectionList title="Skills" values={value.skill_version_refs} options={knowledge("skill")} disabled={disabled} onChange={skill_version_refs => patch({ skill_version_refs })} /><SelectionList title="Instructions" values={value.protected_instruction_version_refs} options={knowledge("protected_instruction")} disabled={disabled} onChange={protected_instruction_version_refs => patch({ protected_instruction_version_refs })} /></details>
    {requirements ? <details className="setup-options"><summary>Workspace requirements</summary><div className="setup-form-grid">{(["requires_project", "requires_host_shell"] as const).map(key => <label key={key}>{key === "requires_project" ? "Project folder" : "Shell access"}<select disabled={disabled} value={value[key] == null ? "inherit" : value[key] ? "required" : "optional"} onChange={event => patch({ [key]: event.target.value === "inherit" ? null : event.target.value === "required" })}><option value="inherit">Inherit</option><option value="required">Required</option><option value="optional">Not required</option></select></label>)}</div><p className="hint">Requirements describe what this agent needs; they do not grant access.</p></details> : null}
  </div>;
}
