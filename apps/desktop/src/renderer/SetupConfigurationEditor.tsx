import { useEffect, useId, useState } from "react";
import { api } from "./api";
import { connectionsApi } from "./connectionsApi";
import { errorMessage } from "./errors";
import { CompactSwitch, SegmentedChoice, SettingRow } from "./CompactControls";
import { HoverHelp } from "./HoverHelp";
import { Notice } from "./Notice";
import { useSetupPreview } from "./effectiveSettings";
import { browserToolNames, desktopToolNames, previewToolNames, defaultNextTurnTools } from "./chatSetup";
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
    : scope === "project" ? ["memory_entry_ids", "skill_entry_ids", "embedding_deployment_id"]
      : ["instructions", "model_configuration_id", "deployment_id", "presented_tools", "connection_ids", "memory_entry_ids", "skill_entry_ids", "protected_instruction_entry_ids", "helper_agent_ids", "review", "requires_project", "requires_host_shell"];
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

export function SetupConfigurationEditor({ value, onChange, catalogue, disabled = false, requirements = false, scope = "agent", projectId = null, agentOptions = [], currentAgentId = null, sections }: { value: SetupConfiguration; onChange: (value: SetupConfiguration) => void; catalogue: SetupCatalogue; disabled?: boolean; requirements?: boolean; scope?: "application" | "project" | "agent"; projectId?: string | null; agentOptions?: AgentSetup[]; currentAgentId?: string | null; sections?: Array<"instructions" | "model" | "tools" | "knowledge" | "helpers" | "review" | "requirements"> }) {
  const id = useId();
  const filtered = scopedSetupConfiguration(value, scope);
  const patch = (next: Partial<SetupConfiguration>) => onChange({ ...filtered, ...next });
  const preview = useSetupPreview(filtered, projectId, null, scope);
  const modelChoice = filtered.model_configuration_id ? `configuration:${filtered.model_configuration_id}` : filtered.deployment_id ? `deployment:${filtered.deployment_id}` : "";
  const modelOptions = <>{catalogue.profiles.filter(item => item.bundle_id).map(item => <option key={item.id} value={`configuration:${item.id}`}>{catalogue.bundles.find(bundle => bundle.id === item.bundle_id)?.display_name ?? item.bundle_name ?? "Model"} · {item.display_name}</option>)}{catalogue.deployments.filter(item => item.scope === "connected").map(item => <option key={item.id} value={`deployment:${item.id}`}>{item.display_name} · connected</option>)}</>;
  const visible = (section: NonNullable<typeof sections>[number]) => !sections || sections.includes(section);
  const knowledgeOptions = (kind: KnowledgeEntry["kind"]) => catalogue.knowledge.filter(entry => entry.kind === kind && entry.enabled !== false && entry.scope_bound !== false).map(entry => ({ id: entry.id, name: entry.display_name || "Untitled" }));
  const selectedTools = filtered.presented_tools ?? defaultNextTurnTools(catalogue.tools.map(tool => tool.id), true, true, true);
  const toolGroups = [
    { name: "Project files", names: ["ls", "read_file", "glob", "grep", "write_file", "edit_file", "read_attachment", "search_knowledge"] as readonly string[] },
    { name: "Host shell", names: ["execute", ...previewToolNames] as readonly string[] },
    { name: "Browser", names: browserToolNames as readonly string[] },
    { name: "Windows control", names: desktopToolNames as readonly string[] },
  ];
  const groupNames = new Set(toolGroups.flatMap(group => [...group.names]));
  const grouped = [...toolGroups, { name: "Other tools", names: catalogue.tools.filter(tool => !groupNames.has(tool.id)).map(tool => tool.id) }];
  const selectTools = (names: string[], enabled: boolean) => patch({ presented_tools: enabled ? [...new Set([...selectedTools, ...names])] : selectedTools.filter(name => !names.includes(name)) });
  return <div className="setup-configuration-editor setting-rows">
    {scope === "application" ? <SegmentedChoice label="Default access for new chats" description="Each chat remembers its access choice." value={filtered.approval_mode ?? "ask"} disabled={disabled} options={[{ value: "ask", label: "Ask" }, { value: "full_access", label: "Full access" }]} onChange={next => patch({ approval_mode: next as SetupConfiguration["approval_mode"] })} /> : null}
    {scope === "agent" ? <>
      {visible("model") ? <SettingRow label="Model" htmlFor={`${id}-model`} help="An assigned model is selected when you use this agent. Access stays with Chat."><select id={`${id}-model`} value={modelChoice} disabled={disabled} onChange={event => { const choice = event.target.value; patch({ model_configuration_id: choice.startsWith("configuration:") ? choice.slice(14) : null, deployment_id: choice.startsWith("deployment:") ? choice.slice(11) : null }); }}><option value="">Use Chat model</option>{modelOptions}{modelChoice && !catalogue.profiles.some(item => `configuration:${item.id}` === modelChoice) && !catalogue.deployments.some(item => `deployment:${item.id}` === modelChoice) ? <option value={modelChoice}>Unavailable selection</option> : null}</select></SettingRow> : null}
      {visible("instructions") ? <SettingRow stacked label="Instructions" htmlFor={`${id}-instructions`} help="Instructions guide this agent and do not grant permissions."><textarea id={`${id}-instructions`} value={filtered.instructions ?? ""} disabled={disabled} onChange={event => patch({ instructions: event.target.value || null })} placeholder="How should this agent work?" rows={4} /></SettingRow> : null}
      {visible("tools") ? <details className="setup-options" open><summary>Tools <HoverHelp title="Tool access">Chat's access, mode and live grants still apply.</HoverHelp></summary><div className="actions"><button type="button" disabled={disabled} onClick={() => patch({ presented_tools: null })}>Standard tools</button><button type="button" disabled={disabled} onClick={() => patch({ presented_tools: [] })}>Turn all off</button></div>{catalogue.toolCatalogueStatus === "error" ? <Notice tone="warn">Tool choices unavailable. Open Settings or retry this screen.</Notice> : null}{grouped.map(group => { const options = catalogue.tools.filter(tool => group.names.includes(tool.id)); if (!options.length) return null; const all = options.every(tool => selectedTools.includes(tool.id)); const count = options.filter(tool => selectedTools.includes(tool.id)).length; return <div key={group.name}><CompactSwitch label={group.name} checked={all} disabled={disabled} onChange={checked => selectTools(options.map(tool => tool.id), checked)} description={`${count}/${options.length} selected`} /><details><summary>Individual {group.name.toLowerCase()} tools</summary>{options.map(tool => <CompactSwitch key={tool.id} label={tool.name} checked={selectedTools.includes(tool.id)} disabled={disabled} onChange={checked => selectTools([tool.id], checked)} description={tool.available === false ? tool.unavailable_reason ?? "Needs setup in Settings" : tool.description} />)}</details></div>; })}<details><summary>Connections</summary>{catalogue.connections.map(connection => <CompactSwitch key={connection.id} label={connection.name} checked={Boolean(filtered.connection_ids?.includes(connection.id))} disabled={disabled} onChange={checked => patch({ connection_ids: checked ? [...(filtered.connection_ids ?? []), connection.id] : (filtered.connection_ids ?? []).filter(id => id !== connection.id) })} description={connection.available === false ? "Needs a successful test in Settings" : undefined} />)}{!catalogue.connections.length ? <p className="hint">Add connections in Settings.</p> : null}</details></details> : null}
      {visible("knowledge") ? <details className="setup-options"><summary>Knowledge</summary>{(["memory", "skill", "protected_instruction"] as const).map(kind => { const key = kind === "memory" ? "memory_entry_ids" : kind === "skill" ? "skill_entry_ids" : "protected_instruction_entry_ids"; return <KnowledgeChoices key={kind} title={kind === "memory" ? "Memories" : kind === "skill" ? "Skills" : "Instructions"} values={filtered[key]} options={knowledgeOptions(kind)} disabled={disabled} onChange={next => patch({ [key]: next })} />; })}</details> : null}
      {visible("helpers") ? <details className="setup-options"><summary>Helpers</summary>{agentOptions.filter(agent => agent.id !== currentAgentId).map(agent => <CompactSwitch key={agent.id} label={agent.name} checked={Boolean(filtered.helper_agent_ids?.includes(agent.id))} disabled={disabled || Boolean(agent.helper_missing_dependencies?.length)} onChange={checked => patch({ helper_agent_ids: checked ? [...(filtered.helper_agent_ids ?? []), agent.id] : (filtered.helper_agent_ids ?? []).filter(id => id !== agent.id) })} description={agent.helper_missing_dependencies?.map(issue => issue.reason).join(", ") || (catalogue.profiles.find(profile => profile.id === agent.configuration.model_configuration_id)?.display_name ?? catalogue.deployments.find(deployment => deployment.id === agent.configuration.deployment_id)?.display_name ?? "Use Chat model")} />)}{!agentOptions.some(agent => agent.id !== currentAgentId) ? <p className="hint">No helpers. Create another agent to add one.</p> : null}</details> : null}
      {visible("review") ? <details className="setup-options"><summary>Review</summary><CompactSwitch label="Review before finishing" checked={filtered.review?.enabled === true} disabled={disabled} onChange={enabled => patch({ review: { enabled, criteria: filtered.review?.criteria ?? "", max_revisions: 2 } })} description="Checks and revises up to twice." />{filtered.review?.enabled ? <SettingRow stacked label="Review criteria" htmlFor={`${id}-review`}><textarea id={`${id}-review`} rows={3} value={filtered.review.criteria} disabled={disabled} onChange={event => patch({ review: { enabled: true, criteria: event.target.value, max_revisions: 2 } })} placeholder="What should a good result satisfy?" /></SettingRow> : null}</details> : null}
      {requirements && visible("requirements") ? <details className="setup-options"><summary>Requirements <HoverHelp title="Requirements">Describes what this agent needs; it does not grant access.</HoverHelp></summary>{(["requires_project", "requires_host_shell"] as const).map(key => <SegmentedChoice key={key} label={key === "requires_project" ? "Project folder" : "Shell access"} disabled={disabled} value={filtered[key] == null ? "optional" : filtered[key] ? "required" : "optional"} options={[{ value: "required", label: "Required" }, { value: "optional", label: "Optional" }]} onChange={next => patch({ [key]: next === "required" })} />)}</details> : null}
    </> : null}
    {scope === "project" ? <details className="setup-options" open><summary>Project knowledge</summary>{(["memory", "skill"] as const).map(kind => { const key = kind === "memory" ? "memory_entry_ids" : "skill_entry_ids"; return <KnowledgeChoices key={kind} title={kind === "memory" ? "Memories" : "Skills"} values={filtered[key]} options={knowledgeOptions(kind)} disabled={disabled} onChange={next => patch({ [key]: next })} />; })}</details> : null}
    {preview.error ? <p className="hint" role="status">Settings preview: {preview.error}</p> : null}
  </div>;
}
