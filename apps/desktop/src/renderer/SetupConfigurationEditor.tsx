import { useEffect, useId, useState } from "react";
import { api } from "./api";
import { connectionsApi } from "./connectionsApi";
import { errorMessage } from "./errors";
import { CompactSwitch, SegmentedChoice, SettingRow } from "./CompactControls";
import { HoverHelp } from "./HoverHelp";
import { useSetupPreview } from "./effectiveSettings";
import type { Deployment, KnowledgeEntry, ModelBundle, RunProfile } from "./types";
import type { AgentSetup, SetupConfiguration } from "./workspaceApi";

interface SelectionOption { id: string; name: string; description?: string; available?: boolean; unavailable_reason?: string | null }
export interface SetupCatalogue {
  deployments: Deployment[]; bundles: ModelBundle[]; profiles: RunProfile[]; knowledge: KnowledgeEntry[];
  tools: SelectionOption[]; connections: SelectionOption[];
  toolCatalogueStatus?: "loading" | "ready" | "error";
}

export function scopedSetupConfiguration(value: SetupConfiguration, scope: "application" | "project" | "agent"): SetupConfiguration {
  const fields = scope === "application" ? ["approval_mode"]
    : scope === "project" ? ["memory_version_refs", "skill_version_refs", "embedding_deployment_id"]
      : ["instructions", "model_configuration_id", "deployment_id", "memory_version_refs", "skill_version_refs", "protected_instruction_version_refs", "helper_agent_ids", "review", "requires_project", "requires_host_shell"];
  return Object.fromEntries(fields.filter(key => Object.hasOwn(value, key)).map(key => [key, value[key as keyof SetupConfiguration]])) as SetupConfiguration;
}

// Capability grants are selected in Chat. Saving an agent, project, or app
// preference cannot accidentally retain a stale browser or Windows grant.
export function visualSetupCompatibilityIssue(_value: SetupConfiguration, _catalogue: SetupCatalogue): string | null { return null; }

export function useSetupCatalogue() {
  const [catalogue, setCatalogue] = useState<SetupCatalogue>({ deployments: [], bundles: [], profiles: [], knowledge: [], tools: [], connections: [], toolCatalogueStatus: "loading" });
  const [error, setError] = useState("");
  useEffect(() => {
    let cancelled = false;
    void Promise.allSettled([api.deployments(), api.bundles(), api.profiles(), api.knowledgeEntries(), api.agentTools(), connectionsApi.list()]).then(([deployments, bundles, profiles, knowledge, tools, connections]) => {
      if (cancelled) return;
      setCatalogue({
        deployments: deployments.status === "fulfilled" ? deployments.value : [],
        bundles: bundles.status === "fulfilled" ? bundles.value : [],
        profiles: profiles.status === "fulfilled" ? profiles.value : [],
        knowledge: knowledge.status === "fulfilled" ? knowledge.value : [],
        tools: tools.status === "fulfilled" ? tools.value.tools ?? [] : [],
        connections: connections.status === "fulfilled" ? connections.value.map(item => ({ ...item, available: !!(item.enabled && item.last_tested_at && !item.last_error) })) : [],
        toolCatalogueStatus: tools.status === "fulfilled" ? "ready" : "error",
      });
      const failures = [deployments, bundles, profiles, knowledge, tools, connections].filter(result => result.status === "rejected");
      setError(failures.map(result => errorMessage(result.reason)).join("; "));
    });
    return () => { cancelled = true; };
  }, []);
  return { catalogue, error };
}

function KnowledgeChoices({ title, values, options, disabled, onChange }: { title: string; values: string[] | null | undefined; options: SelectionOption[]; disabled: boolean; onChange: (next: string[] | null) => void }) {
  return <div className="setup-selection-group">
    <SegmentedChoice label={title} value={values == null ? "inherit" : "choose"} disabled={disabled} options={[{ value: "inherit", label: "None" }, { value: "choose", label: "Choose" }]} onChange={next => onChange(next === "inherit" ? null : [])} />
    {values != null ? <div className="setup-selection-options">{options.map(option => <CompactSwitch key={option.id} label={option.name} checked={values.includes(option.id)} disabled={disabled} onChange={checked => onChange(checked ? [...values, option.id] : values.filter(value => value !== option.id))} />)}{!options.length ? <p className="hint">Nothing available.</p> : null}</div> : null}
  </div>;
}

export function SetupConfigurationEditor({ value, onChange, catalogue, disabled = false, requirements = false, scope = "agent", projectId = null, agentOptions = [], currentAgentId = null }: { value: SetupConfiguration; onChange: (value: SetupConfiguration) => void; catalogue: SetupCatalogue; disabled?: boolean; requirements?: boolean; scope?: "application" | "project" | "agent"; projectId?: string | null; agentOptions?: AgentSetup[]; currentAgentId?: string | null }) {
  const id = useId();
  const filtered = scopedSetupConfiguration(value, scope);
  const patch = (next: Partial<SetupConfiguration>) => onChange({ ...filtered, ...next });
  const preview = useSetupPreview(filtered, projectId, null, scope);
  const modelChoice = filtered.model_configuration_id ? `configuration:${filtered.model_configuration_id}` : filtered.deployment_id ? `deployment:${filtered.deployment_id}` : "";
  const modelOptions = <>{catalogue.profiles.filter(item => item.bundle_id).map(item => <option key={item.id} value={`configuration:${item.id}`}>{catalogue.bundles.find(bundle => bundle.id === item.bundle_id)?.display_name ?? item.bundle_name ?? "Model"} · {item.display_name}</option>)}{catalogue.deployments.filter(item => item.scope === "connected").map(item => <option key={item.id} value={`deployment:${item.id}`}>{item.display_name} · connected</option>)}</>;
  const knowledgeOptions = (kind: KnowledgeEntry["kind"]) => catalogue.knowledge.filter(entry => entry.kind === kind && entry.enabled !== false && entry.scope_bound !== false).map(entry => ({ id: entry.current_version_id, name: entry.display_name || "Untitled" }));
  return <div className="setup-configuration-editor setting-rows">
    {scope === "application" ? <SegmentedChoice label="Default access for new chats" description="Each chat remembers its access choice." value={filtered.approval_mode ?? "ask"} disabled={disabled} options={[{ value: "ask", label: "Ask" }, { value: "full_access", label: "Full access" }]} onChange={next => patch({ approval_mode: next as SetupConfiguration["approval_mode"] })} /> : null}
    {scope === "agent" ? <>
      <SettingRow label="Helper model" htmlFor={`${id}-model`} help="Used when this agent runs as a helper. Selecting it as the main agent keeps the chat model."><select id={`${id}-model`} value={modelChoice} disabled={disabled} onChange={event => { const choice = event.target.value; patch({ model_configuration_id: choice.startsWith("configuration:") ? choice.slice(14) : null, deployment_id: choice.startsWith("deployment:") ? choice.slice(11) : null }); }}><option value="">Use chat model</option>{modelOptions}{modelChoice && !catalogue.profiles.some(item => `configuration:${item.id}` === modelChoice) && !catalogue.deployments.some(item => `deployment:${item.id}` === modelChoice) ? <option value={modelChoice}>Unavailable selection</option> : null}</select></SettingRow>
      <SettingRow stacked label="Instructions" htmlFor={`${id}-instructions`} help="Instructions guide this agent and do not grant permissions."><textarea id={`${id}-instructions`} value={filtered.instructions ?? ""} disabled={disabled} onChange={event => patch({ instructions: event.target.value || null })} placeholder="How should this agent work?" rows={4} /></SettingRow>
      <details className="setup-options"><summary>Agent knowledge</summary>{(["memory", "skill", "protected_instruction"] as const).map(kind => { const key = kind === "memory" ? "memory_version_refs" : kind === "skill" ? "skill_version_refs" : "protected_instruction_version_refs"; return <KnowledgeChoices key={kind} title={kind === "memory" ? "Memories" : kind === "skill" ? "Skills" : "Protected instructions"} values={filtered[key]} options={knowledgeOptions(kind)} disabled={disabled} onChange={next => patch({ [key]: next })} />; })}</details>
      <details className="setup-options"><summary>Named helpers</summary>{agentOptions.filter(agent => agent.id !== currentAgentId).map(agent => <CompactSwitch key={agent.id} label={agent.name} checked={Boolean(filtered.helper_agent_ids?.includes(agent.id))} disabled={disabled || Boolean(agent.helper_missing_dependencies?.length)} onChange={checked => patch({ helper_agent_ids: checked ? [...(filtered.helper_agent_ids ?? []), agent.id] : (filtered.helper_agent_ids ?? []).filter(id => id !== agent.id) })} description={agent.helper_missing_dependencies?.map(issue => issue.reason).join(", ") || "Available to this agent when working in Chat."} />)}{!agentOptions.some(agent => agent.id !== currentAgentId) ? <p className="hint">Create another agent to use as a helper.</p> : null}</details>
      <details className="setup-options"><summary>Review</summary><CompactSwitch label="Review before finishing" checked={filtered.review?.enabled === true} disabled={disabled} onChange={enabled => patch({ review: { enabled, criteria: filtered.review?.criteria ?? "", max_revisions: 2 } })} description="Checks the result and revises it up to twice." />{filtered.review?.enabled ? <SettingRow stacked label="Review criteria" htmlFor={`${id}-review`}><textarea id={`${id}-review`} rows={3} value={filtered.review.criteria} disabled={disabled} onChange={event => patch({ review: { enabled: true, criteria: event.target.value, max_revisions: 2 } })} placeholder="What should a good result satisfy?" /></SettingRow> : null}</details>
      {requirements ? <details className="setup-options"><summary>Workspace requirements <HoverHelp title="Requirements">Describes what this agent needs; it does not grant access.</HoverHelp></summary>{(["requires_project", "requires_host_shell"] as const).map(key => <SegmentedChoice key={key} label={key === "requires_project" ? "Project folder" : "Shell access"} disabled={disabled} value={filtered[key] == null ? "optional" : filtered[key] ? "required" : "optional"} options={[{ value: "required", label: "Required" }, { value: "optional", label: "Optional" }]} onChange={next => patch({ [key]: next === "required" })} />)}</details> : null}
    </> : null}
    {scope === "project" ? <details className="setup-options" open><summary>Project knowledge</summary>{(["memory", "skill"] as const).map(kind => { const key = kind === "memory" ? "memory_version_refs" : "skill_version_refs"; return <KnowledgeChoices key={kind} title={kind === "memory" ? "Memories" : "Skills"} values={filtered[key]} options={knowledgeOptions(kind)} disabled={disabled} onChange={next => patch({ [key]: next })} />; })}</details> : null}
    {preview.error ? <p className="hint" role="status">Settings preview: {preview.error}</p> : null}
  </div>;
}
