import { useEffect, useId, useState } from "react";
import { api } from "./api";
import { connectionsApi } from "./connectionsApi";
import { errorMessage } from "./errors";
import { CompactSwitch, SegmentedChoice, SettingRow } from "./CompactControls";
import { HoverHelp } from "./HoverHelp";
import { Notice } from "./Notice";
import { Icon } from "./Icon";
import { useSetupPreview } from "./effectiveSettings";
import { standardToolSelection, type ToolCatalogueProjection } from "./chatSetup";
import type { Deployment, KnowledgeEntry, ModelBundle, RunProfile } from "./types";
import type { AgentSetup, SetupConfiguration } from "./workspaceApi";
import type { ReferenceLoading } from "./agentInputPolicy";
import "./SetupConfigurationEditor.css";

interface SelectionOption { id: string; name: string; description?: string; available?: boolean; unavailable_reason?: string | null; group?: string; prerequisites?: string[]; opt_in?: boolean; plan_eligible?: boolean }
export interface SetupCatalogue extends ToolCatalogueProjection {
  deployments: Deployment[]; bundles: ModelBundle[]; profiles: RunProfile[]; knowledge: KnowledgeEntry[];
  tools: SelectionOption[]; connections: SelectionOption[];
  toolCatalogueStatus?: "loading" | "ready" | "error";
}

export function scopedSetupConfiguration(value: SetupConfiguration, scope: "application" | "project" | "agent"): SetupConfiguration {
  const fields = scope === "application" ? ["approval_mode"]
    : scope === "project" ? ["input_policy", "memory_entry_ids", "skill_entry_ids", "embedding_deployment_id"]
      : ["instructions", "input_policy", "model_configuration_id", "deployment_id", "presented_tools", "connection_ids", "memory_entry_ids", "skill_entry_ids", "protected_instruction_entry_ids", "helper_agent_ids", "review", "requires_project", "requires_host_shell"];
  return Object.fromEntries(fields.filter(key => Object.hasOwn(value, key)).map(key => [key, value[key as keyof SetupConfiguration]])) as SetupConfiguration;
}

// Capability grants are selected in Chat. Saving an agent, project, or app
// preference cannot accidentally retain a stale browser or Windows grant.
export function visualSetupCompatibilityIssue(_value: SetupConfiguration, _catalogue: SetupCatalogue): string | null { return null; }

export function useSetupCatalogue(active = true) {
  const [catalogue, setCatalogue] = useState<SetupCatalogue>({ deployments: [], bundles: [], profiles: [], knowledge: [], tools: [], connections: [], toolCatalogueStatus: "loading" });
  const [error, setError] = useState("");
  useEffect(() => {
    if (!active) return;
    let cancelled = false;
    void Promise.allSettled([api.deployments(), api.bundles(), api.profiles(), api.knowledgeEntries(), api.agentTools(), connectionsApi.list()]).then(([deployments, bundles, profiles, knowledge, tools, connections]) => {
      if (cancelled) return;
      setCatalogue({
        deployments: deployments.status === "fulfilled" ? deployments.value : [],
        bundles: bundles.status === "fulfilled" ? bundles.value : [],
        profiles: profiles.status === "fulfilled" ? profiles.value : [],
        knowledge: knowledge.status === "fulfilled" ? knowledge.value : [],
        tools: tools.status === "fulfilled" ? tools.value.tools ?? [] : [],
        groups: tools.status === "fulfilled" ? tools.value.groups ?? [] : [],
        defaults: tools.status === "fulfilled" ? tools.value.defaults : undefined,
        plan_tools: tools.status === "fulfilled" ? tools.value.plan_tools : undefined,
        plan_public_web_remote_names: tools.status === "fulfilled" ? tools.value.plan_public_web_remote_names : undefined,
        connections: connections.status === "fulfilled" ? connections.value.map(item => ({ ...item, available: !!(item.enabled && item.last_tested_at && !item.last_error) })) : [],
        toolCatalogueStatus: tools.status === "fulfilled" ? "ready" : "error",
      });
      const failures = [deployments, bundles, profiles, knowledge, tools, connections].filter(result => result.status === "rejected");
      setError(failures.map(result => errorMessage(result.reason)).join("; "));
    });
    return () => { cancelled = true; };
  }, [active]);
  return { catalogue, error };
}

export function setupModelLabel(value: SetupConfiguration, catalogue: SetupCatalogue): string {
  if (value.model_configuration_id) {
    const profile = catalogue.profiles.find(item => item.id === value.model_configuration_id);
    if (!profile) return "Assigned model unavailable";
    const model = catalogue.bundles.find(item => item.id === profile.bundle_id)?.display_name ?? profile.bundle_name;
    return model && model !== profile.display_name ? `${model} · ${profile.display_name}` : profile.display_name;
  }
  if (value.deployment_id) return catalogue.deployments.find(item => item.id === value.deployment_id)?.display_name.replace(/^(connected|managed):/, "") ?? "Assigned model unavailable";
  return "Use Chat model";
}

function KnowledgeChoices({ title, values, options, disabled, onChange, loading, onLoading }: { title: string; values: string[] | null | undefined; options: SelectionOption[]; disabled: boolean; onChange: (next: string[] | null) => void; loading?: Record<string, ReferenceLoading>; onLoading?: (id: string, mode: ReferenceLoading) => void }) {
  const choices = [...options, ...(values ?? []).filter(value => !options.some(option => option.id === value)).map(id => ({ id, name: `Unavailable ${title.toLowerCase()}`, available: false, unavailable_reason: "Remove this selection or restore it in Knowledge." }))];
  return <div className="setup-selection-group">
    <SegmentedChoice label={title} meta={values?.length ? `${values.length} selected` : "None selected"} value={values == null ? "inherit" : "choose"} disabled={disabled} options={[{ value: "inherit", label: "None" }, { value: "choose", label: "Choose" }]} onChange={next => onChange(next === "inherit" ? null : [])} />
    {values != null ? <div className="setup-selection-options">{choices.map(option => <div key={option.id} className="setup-context-choice"><CompactSwitch label={option.name} checked={values.includes(option.id)} disabled={disabled || (option.available === false && !values.includes(option.id))} meta={option.available === false ? option.unavailable_reason : undefined} onChange={checked => onChange(checked ? [...new Set([...values, option.id])] : values.filter(value => value !== option.id))} />{onLoading && values.includes(option.id) ? <select aria-label={`Loading for ${option.name}`} disabled={disabled} value={loading?.[option.id] ?? "when_needed"} onChange={event => onLoading(option.id, event.target.value as ReferenceLoading)}><option value="when_needed">When needed</option><option value="always">Always include</option><option value="off">Off</option></select> : null}</div>)}{!choices.length ? <p className="hint">Nothing available.</p> : null}</div> : null}
  </div>;
}

function ToolGroupChoices({ name, tools, selected, disabled, onChange, pins, onPin }: { name: string; tools: SelectionOption[]; selected: string[]; disabled: boolean; onChange: (names: string[], enabled: boolean) => void; pins: string[]; onPin: (name: string, pin: boolean) => void }) {
  const id = useId();
  const [expanded, setExpanded] = useState(false);
  const count = tools.filter(tool => selected.includes(tool.id)).length;
  return <div className="setup-tool-group">
    <div className="setup-tool-group-head">
      <button type="button" className="setup-tool-group-expand" aria-expanded={expanded} aria-controls={`${id}-tools`} onClick={() => setExpanded(current => !current)}>
        <span className="setup-tool-group-name" id={`${id}-name`}>{name}</span>
        <small className="setup-tool-group-count">{count} of {tools.length} selected</small>
      </button>
      <CompactSwitch bare label={name} checked={count === tools.length} disabled={disabled} onChange={enabled => onChange(tools.map(tool => tool.id), enabled)} />
    </div>
    <div className="setup-tool-choices" id={`${id}-tools`} role="group" aria-labelledby={`${id}-name`} hidden={!expanded}>
      {tools.map(tool => <div key={tool.id} className="setup-tool-choice"><CompactSwitch label={tool.name} checked={selected.includes(tool.id)} disabled={disabled} onChange={enabled => onChange([tool.id], enabled)} description={tool.description} meta={tool.available === false ? tool.unavailable_reason ?? "Needs setup in Settings" : undefined} /><label className="check-row setup-tool-pin"><input type="checkbox" aria-label={`Always include ${tool.name}`} checked={pins.includes(tool.id)} disabled={disabled || !selected.includes(tool.id)} onChange={event => onPin(tool.id, event.target.checked)} />Always include definition</label></div>)}
    </div>
  </div>;
}

export function SetupConfigurationEditor({ value, onChange, catalogue, disabled = false, requirements = false, scope = "agent", projectId = null, agentOptions = [], currentAgentId = null, sections, active = true }: { value: SetupConfiguration; onChange: (value: SetupConfiguration) => void; catalogue: SetupCatalogue; disabled?: boolean; requirements?: boolean; scope?: "application" | "project" | "agent"; projectId?: string | null; agentOptions?: AgentSetup[]; currentAgentId?: string | null; sections?: Array<"instructions" | "model" | "tools" | "knowledge" | "helpers" | "review" | "requirements">; active?: boolean }) {
  const id = useId();
  const [helperQuery, setHelperQuery] = useState("");
  const [helperToAdd, setHelperToAdd] = useState("");
  const filtered = scopedSetupConfiguration(value, scope);
  const patch = (next: Partial<SetupConfiguration>) => onChange({ ...filtered, ...next });
  const policy = filtered.input_policy ?? {};
  const patchPolicy = (next: typeof policy) => patch({ input_policy: { ...policy, ...next, version: 1 } });
  const preview = useSetupPreview(filtered, projectId, null, scope, "", active);
  const modelChoice = filtered.model_configuration_id ? `configuration:${filtered.model_configuration_id}` : filtered.deployment_id ? `deployment:${filtered.deployment_id}` : "";
  const modelOptions = <>{catalogue.profiles.filter(item => item.bundle_id).map(item => <option key={item.id} value={`configuration:${item.id}`}>{catalogue.bundles.find(bundle => bundle.id === item.bundle_id)?.display_name ?? item.bundle_name ?? "Model"} · {item.display_name}</option>)}{catalogue.deployments.filter(item => item.scope === "connected").map(item => <option key={item.id} value={`deployment:${item.id}`}>{item.display_name} · connected</option>)}</>;
  const visible = (section: NonNullable<typeof sections>[number]) => !sections || sections.includes(section);
  const knowledgeOptions = (kind: KnowledgeEntry["kind"]) => catalogue.knowledge.filter(entry => entry.kind === kind).map(entry => ({ id: entry.id, name: entry.display_name || "Untitled", available: entry.enabled !== false && entry.active !== false && entry.scope_bound !== false, unavailable_reason: entry.scope_bound === false ? "Its project or agent is unavailable." : "Disabled or removed in Knowledge." }));
  const projectBound = Boolean(projectId) || filtered.requires_project === true;
  const catalogueBlocked = catalogue.toolCatalogueStatus === "loading" || catalogue.toolCatalogueStatus === "error";
  const standardTools = catalogueBlocked ? null : standardToolSelection(catalogue, projectBound, false, false);
  const selectedTools = filtered.presented_tools ?? standardTools ?? [];
  const groupLabels: Record<string, string> = { project: "Project files", shell: "This computer", browser: "Browser", windows: "One window", preview: "Preview", diagnostics: "Diagnostics", planning: "Planning", input: "Questions", knowledge: "Knowledge", connections: "Connections" };
  const groupOrder = [...(catalogue.groups ?? []).map(group => group.id)];
  for (const tool of catalogue.tools) if (tool.group && !groupOrder.includes(tool.group)) groupOrder.push(tool.group);
  const labelFor = (id: string) => catalogue.groups?.find(group => group.id === id)?.label ?? groupLabels[id] ?? id;
  const grouped = [
    ...groupOrder.map(id => ({ name: labelFor(id), tools: catalogue.tools.filter(tool => tool.group === id) })).filter(group => group.tools.length),
    ...((() => { const other = catalogue.tools.filter(tool => !tool.group); return other.length ? [{ name: "Other tools", tools: other }] : []; })()),
  ];
  const selectTools = (names: string[], enabled: boolean) => {
    if (catalogueBlocked) return;
    const base = filtered.presented_tools ?? standardTools;
    if (base == null) return;
    patch({ presented_tools: enabled ? [...new Set([...base, ...names])] : base.filter(name => !names.includes(name)) });
  };
  const explicitOptIn = (filtered.presented_tools ?? []).flatMap(name => {
    const tool = catalogue.tools.find(item => item.id === name);
    return tool?.opt_in ? [tool.name || name] : [];
  });
  const knowledgeCount = (filtered.memory_entry_ids?.length ?? 0) + (filtered.skill_entry_ids?.length ?? 0) + (filtered.protected_instruction_entry_ids?.length ?? 0);
  const helperIds = filtered.helper_agent_ids ?? [];
  const helpersToAdd = agentOptions.filter(agent => agent.id !== currentAgentId && agent.active !== false && !helperIds.includes(agent.id) && `${agent.name} ${agent.role ?? ""} ${setupModelLabel(agent.configuration, catalogue)}`.toLowerCase().includes(helperQuery.toLowerCase()));
  const candidateHelper = helpersToAdd.find(agent => agent.id === helperToAdd);
  const candidateIssue = candidateHelper?.helper_missing_dependencies?.map(issue => issue.reason).join(", ");
  const selectedConnections = filtered.connection_ids ?? [];
  const connectionOptions = [...catalogue.connections, ...selectedConnections.filter(connection => !catalogue.connections.some(option => option.id === connection)).map(id => ({ id, name: "Unavailable connection", available: false }))];
  const unavailableTools = selectedTools.filter(name => !catalogue.tools.some(tool => tool.id === name));
  const expanded = sections ? true : undefined;
  return <div className="setup-configuration-editor setting-rows">
    {scope === "application" ? <SegmentedChoice label="Default access for new chats" description="Each chat remembers its access choice." value={filtered.approval_mode ?? "ask"} disabled={disabled} options={[{ value: "ask", label: "Ask" }, { value: "full_access", label: "Full access" }]} onChange={next => patch({ approval_mode: next as SetupConfiguration["approval_mode"] })} /> : null}
    {scope === "agent" ? <>
      {visible("model") ? <SettingRow label="Model" htmlFor={`${id}-model`} help="An assigned model is selected when you use this agent. Access stays with Chat."><select id={`${id}-model`} value={modelChoice} disabled={disabled} onChange={event => { const choice = event.target.value; patch({ model_configuration_id: choice.startsWith("configuration:") ? choice.slice(14) : null, deployment_id: choice.startsWith("deployment:") ? choice.slice(11) : null }); }}><option value="">Use Chat model</option>{modelOptions}{modelChoice && !catalogue.profiles.some(item => `configuration:${item.id}` === modelChoice) && !catalogue.deployments.some(item => `deployment:${item.id}` === modelChoice) ? <option value={modelChoice}>Unavailable selection</option> : null}</select></SettingRow> : null}
      {visible("instructions") ? <SettingRow stacked label="Instructions" htmlFor={`${id}-instructions`} help="Instructions guide this agent and do not grant permissions."><textarea id={`${id}-instructions`} value={filtered.instructions ?? ""} disabled={disabled} onChange={event => patch({ instructions: event.target.value || null })} placeholder="How should this agent work?" rows={4} /></SettingRow> : null}
      {visible("tools") ? <details className="setup-options" open><summary><span>Tools</span><small>{filtered.presented_tools == null ? "Standard" : selectedTools.length ? `${selectedTools.length} selected` : "All off"}</small><HoverHelp title="Tool access">Chat's access, mode and live grants still apply.</HoverHelp></summary>
        <SettingRow label="Tool definitions" help="Keep selected tools discoverable and load definitions when needed. Pins always include individual definitions."><select aria-label="Agent tool definition loading" disabled={disabled} value={policy.tool_loading ?? "when_needed"} onChange={event => patchPolicy({ ...policy, tool_loading: event.target.value as "when_needed" | "always" })}><option value="when_needed">When needed</option><option value="always">Always include all</option></select></SettingRow>
        <div className="actions"><button type="button" disabled={disabled} onClick={() => patch({ presented_tools: null })}>Standard tools</button><button type="button" disabled={disabled} onClick={() => patch({ presented_tools: [] })}>Turn all off</button></div>
        {catalogue.toolCatalogueStatus === "loading" ? <p className="hint" role="status">Loading tool choices…</p> : catalogue.toolCatalogueStatus === "error" ? <Notice tone="warn">Tool choices unavailable. Open Settings or retry this screen.</Notice> : null}
        {explicitOptIn.length ? <Notice tone="warn">This saved selection includes tools that Standard leaves off ({explicitOptIn.join(", ")}). Review them before use. Saving again keeps this list as you set it.</Notice> : null}
        {filtered.presented_tools == null && standardTools == null && catalogue.toolCatalogueStatus === "ready" ? <Notice tone="warn">Tool defaults are unavailable, so changing a checkbox will not create a selection.</Notice> : null}
        {grouped.map(group => <ToolGroupChoices key={group.name} name={group.name} tools={group.tools} selected={selectedTools} disabled={disabled || (filtered.presented_tools == null && standardTools == null)} onChange={selectTools} pins={policy.pinned_tools ?? []} onPin={(name, pin) => patchPolicy({ ...policy, pinned_tools: pin ? [...new Set([...(policy.pinned_tools ?? []), name])] : (policy.pinned_tools ?? []).filter(tool => tool !== name) })} />)}
        {unavailableTools.length ? <details className="setup-unavailable-selections" open><summary>Unavailable tools <small>{unavailableTools.length} selected</small></summary>{unavailableTools.map(name => <CompactSwitch key={name} label={name} checked disabled={disabled} meta="Remove this choice or restore its connection in Settings." onChange={() => selectTools([name], false)} />)}</details> : null}
        <details><summary>Connections <small>{selectedConnections.length ? `${selectedConnections.length} selected` : "None selected"}</small></summary>{connectionOptions.map(connection => <CompactSwitch key={connection.id} label={connection.name} checked={selectedConnections.includes(connection.id)} disabled={disabled} onChange={checked => patch({ connection_ids: checked ? [...new Set([...selectedConnections, connection.id])] : selectedConnections.filter(id => id !== connection.id) })} meta={connection.available === false ? "Needs a successful test in Settings" : undefined} />)}{!connectionOptions.length ? <p className="hint">Add connections in Settings.</p> : null}</details>
      </details> : null}
      {visible("knowledge") ? <details className="setup-options" open={expanded}><summary><span>Knowledge</span><small>{knowledgeCount ? `${knowledgeCount} selected` : "None selected"}</small></summary>{(["memory", "skill", "protected_instruction"] as const).map(kind => { const key = kind === "memory" ? "memory_entry_ids" : kind === "skill" ? "skill_entry_ids" : "protected_instruction_entry_ids"; return <KnowledgeChoices key={kind} title={kind === "memory" ? "Memories" : kind === "skill" ? "Skills" : "Instructions"} values={filtered[key]} options={knowledgeOptions(kind)} disabled={disabled} onChange={next => patch({ [key]: next })} loading={policy.reference_loading} onLoading={kind !== "protected_instruction" ? (entryId, mode) => patchPolicy({ ...policy, reference_loading: { ...policy.reference_loading, [entryId]: mode } }) : undefined} />; })}</details> : null}
      {visible("helpers") ? <details className="setup-options" open={expanded}><summary><span>Helpers</span><small>{helperIds.length ? `${helperIds.length} selected` : "None selected"}</small></summary>
        {helperIds.length ? <ul className="setup-helper-list">{helperIds.map((helperId, index) => {
          const helper = agentOptions.find(agent => agent.id === helperId);
          const name = helper?.name ?? `Unavailable helper${helperIds.filter(id => !agentOptions.some(agent => agent.id === id)).length > 1 ? ` ${index + 1}` : ""}`;
          const issue = !helper || helper.active === false ? "This helper was removed or is unavailable." : helper.helper_missing_dependencies?.map(item => item.reason).join(", ");
          return <li key={helperId}><Icon name="agents" /><div><strong>{name}</strong><small>{issue || setupModelLabel(helper!.configuration, catalogue)}</small>{helper?.configuration.requires_project || helper?.configuration.requires_host_shell ? <small>{[helper.configuration.requires_project ? "Project required" : "", helper.configuration.requires_host_shell ? "Shell required" : ""].filter(Boolean).join(" · ")}</small> : null}</div><button type="button" disabled={disabled} aria-label={`Remove ${name}`} onClick={() => patch({ helper_agent_ids: helperIds.filter(id => id !== helperId) })}>Remove</button></li>;
        })}</ul> : <p className="hint">No helpers selected.</p>}
        <div className="setup-helper-add"><input type="search" aria-label="Search helpers" placeholder="Search helpers" value={helperQuery} disabled={disabled} onChange={event => { setHelperQuery(event.target.value); setHelperToAdd(""); }} />
          <div className="actions"><select aria-label="Add helper" value={candidateHelper ? helperToAdd : ""} disabled={disabled || !helpersToAdd.length} onChange={event => setHelperToAdd(event.target.value)}><option value="">{helpersToAdd.length ? "Choose a helper" : helperQuery ? "No matching helpers" : "No helpers available"}</option>{helpersToAdd.map(helper => <option key={helper.id} value={helper.id}>{helper.name} · {helper.helper_missing_dependencies?.length ? "Needs attention" : setupModelLabel(helper.configuration, catalogue)}</option>)}</select><button type="button" disabled={disabled || !candidateHelper || Boolean(candidateIssue)} title={candidateIssue || "Add the selected helper"} onClick={() => { if (candidateHelper && !candidateIssue) { patch({ helper_agent_ids: [...helperIds, candidateHelper.id] }); setHelperToAdd(""); setHelperQuery(""); } }}><Icon name="plus" size={14} />Add helper</button></div>
          {candidateIssue ? <p className="hint" role="status">{candidateIssue}. Repair this agent before adding it.</p> : !agentOptions.some(agent => agent.id !== currentAgentId && agent.active !== false) ? <p className="hint">Create another agent to add a helper.</p> : null}
        </div>
      </details> : null}
      {visible("review") ? <details className="setup-options" open={expanded}><summary><span>Review</span><small>{filtered.review?.enabled ? "On · up to 2 revisions" : "Off"}</small></summary><CompactSwitch label="Review before finishing" checked={filtered.review?.enabled === true} disabled={disabled} onChange={enabled => patch({ review: { enabled, criteria: filtered.review?.criteria ?? "", max_revisions: 2 } })} description="Checks and revises up to twice." />{filtered.review?.enabled ? <SettingRow stacked label="Review criteria" htmlFor={`${id}-review`}><textarea id={`${id}-review`} rows={3} value={filtered.review.criteria} disabled={disabled} onChange={event => patch({ review: { enabled: true, criteria: event.target.value, max_revisions: 2 } })} placeholder="What should a good result satisfy?" /></SettingRow> : null}</details> : null}
      {requirements && visible("requirements") ? <details className="setup-options" open={expanded}><summary><span>Requirements</span><small>{[filtered.requires_project ? "Project required" : "", filtered.requires_host_shell ? "Shell required" : ""].filter(Boolean).join(" · ") || "None"}</small><HoverHelp title="Requirements">Describes what this agent needs; it does not grant access.</HoverHelp></summary>{(["requires_project", "requires_host_shell"] as const).map(key => <SegmentedChoice key={key} label={key === "requires_project" ? "Project folder" : "Shell access"} disabled={disabled} value={filtered[key] == null ? "optional" : filtered[key] ? "required" : "optional"} options={[{ value: "required", label: "Required" }, { value: "optional", label: "Optional" }]} onChange={next => patch({ [key]: next === "required" })} />)}</details> : null}
    </> : null}
    {scope === "project" ? <details className="setup-options" open><summary>Project knowledge</summary>{(["memory", "skill"] as const).map(kind => { const key = kind === "memory" ? "memory_entry_ids" : "skill_entry_ids"; return <KnowledgeChoices key={kind} title={kind === "memory" ? "Memories" : "Skills"} values={filtered[key]} options={knowledgeOptions(kind)} disabled={disabled} onChange={next => patch({ [key]: next })} loading={policy.reference_loading} onLoading={(entryId, mode) => patchPolicy({ reference_loading: { ...policy.reference_loading, [entryId]: mode } })} />; })}</details> : null}
    {preview.error ? <p className="hint" role="status">Settings preview: {preview.error}</p> : null}
  </div>;
}
