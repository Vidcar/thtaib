import { configurationLabel, findConfiguration } from "./configurationLabel";
import { useEffect, useId, useState } from "react";
import { api } from "./api";
import { connectionsApi } from "./connectionsApi";
import { errorMessage } from "./errors";
import { CompactSwitch, SegmentedChoice, SettingRow } from "./CompactControls";
import { HoverHelp } from "./HoverHelp";
import { settingValue, useSetupPreview, type EffectiveSetting } from "./effectiveSettings";
import { browserToolNames, desktopToolNames, optionalVisualToolNames, withBrowserTools, withDesktopTools } from "./chatSetup";
import type { Deployment, KnowledgeEntry, ModelBundle, RunProfile } from "./types";
import type { SetupConfiguration } from "./workspaceApi";

interface SelectionOption { id: string; name: string; description?: string; available?: boolean; unavailable_reason?: string | null }
export interface SetupCatalogue {
  deployments: Deployment[]; bundles: ModelBundle[]; profiles: RunProfile[]; knowledge: KnowledgeEntry[];
  tools: SelectionOption[]; connections: SelectionOption[];
  toolCatalogueStatus?: "loading" | "ready" | "error";
}

export function visualSetupCompatibilityIssue(value: SetupConfiguration, catalogue: SetupCatalogue): string | null {
  const selectedVisualTools = (value.presented_tools ?? []).filter(name => optionalVisualToolNames.has(name));
  if (!selectedVisualTools.length && value.desktop_access == null) return null;
  if (catalogue.toolCatalogueStatus === "loading") return "Checking which visual testing tools the active backend offers before saving.";
  if (catalogue.toolCatalogueStatus === "error") return "Workbench could not load the active backend's tool list. Reload Workbench before saving; your selections remain in this editor.";
  const available = new Set(catalogue.tools.map(tool => tool.id));
  const missing = selectedVisualTools.filter(name => !available.has(name));
  const desktopUnsupported = value.desktop_access != null && !desktopToolNames.every(name => available.has(name));
  if (!missing.length && !desktopUnsupported) return null;
  return "The active Workbench backend does not support this visual testing setup. Restart Workbench to load the updated backend before saving; your selections remain in this editor.";
}
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
        tools: tools.status === "fulfilled" ? tools.value.tools ?? tools.value.enabled.map(id => ({ id, name: id, description: "Tool details unavailable" })) : [],
        connections: connections.status === "fulfilled" ? connections.value.map(item => ({ ...item, available: !!(item.enabled && item.last_tested_at && !item.last_error), unavailable_reason: item.last_error || (!item.enabled ? "Connection is disabled" : !item.last_tested_at ? "Test this connection first" : null) })) : [],
        toolCatalogueStatus: tools.status === "fulfilled" ? "ready" : "error",
      });
      const failures = [deployments, bundles, profiles, knowledge, tools, connections].filter(result => result.status === "rejected");
      setError(failures.map(result => errorMessage(result.reason)).join("; "));
    });
    return () => { cancelled = true; };
  }, []);
  return { catalogue, error };
}

function inheritedLabel(fact?: EffectiveSetting) {
  if (fact?.inherited_source) return `${settingValue(fact.inherited_value)} · ${fact.inherited_source}`;
  return fact?.known ? `${settingValue(fact.value)} · ${fact.source}` : "Inherited";
}

function SelectionList({ title, values, options, fact, disabled, onChange }: { title: string; values: string[] | null | undefined; options: SelectionOption[]; fact?: EffectiveSetting; disabled: boolean; onChange: (values: string[] | null) => void }) {
  const missing = [...new Set((values ?? []).filter(value => !options.some(option => option.id === value)))];
  return <div className="setup-selection-group">
    <SegmentedChoice label={title} meta={values == null ? inheritedLabel(fact) : values.length ? `${values.length} selected` : "None"} value={values == null ? "inherit" : "choose"} disabled={disabled}
      options={[{ value: "inherit", label: "Inherited" }, { value: "choose", label: "Choose" }]} onChange={next => onChange(next === "inherit" ? null : [])} />
    {values != null ? <div className="setup-selection-options">{options.length || missing.length ? <>
      {options.map(option => <CompactSwitch key={option.id} label={option.name} description={option.description || option.unavailable_reason ? <>{option.description}{option.unavailable_reason ? ` ${option.unavailable_reason}.` : ""}</> : undefined} checked={values.includes(option.id)} disabled={disabled || (option.available === false && !values.includes(option.id))} onChange={checked => onChange(checked ? [...values, option.id] : values.filter(value => value !== option.id))} />)}
      {missing.length ? <details className="setup-unavailable-selections"><summary>{missing.length} unavailable selection{missing.length === 1 ? "" : "s"}</summary>
        {missing.map(value => <CompactSwitch key={value} label={value.replaceAll("_", " ")} description={`Tool or record ID: ${value}. Remove this selection or restore its source.`} checked disabled={disabled} onChange={() => onChange(values.filter(item => item !== value))} />)}
      </details> : null}
    </> : <p className="hint">Nothing available.</p>}</div> : null}
  </div>;
}

export function SetupConfigurationEditor({ value, onChange, catalogue, disabled = false, requirements = false, scope = "agent", projectId = null }: { value: SetupConfiguration; onChange: (value: SetupConfiguration) => void; catalogue: SetupCatalogue; disabled?: boolean; requirements?: boolean; scope?: "application" | "project" | "agent"; projectId?: string | null }) {
  const id = useId();
  const patch = (next: Partial<SetupConfiguration>) => onChange({ ...value, ...next });
  const compatibilityIssue = visualSetupCompatibilityIssue(value, catalogue);
  const preview = useSetupPreview(value, projectId, null, scope, "", !compatibilityIssue);
  const facts = preview.data?.effective_values ?? {};
  const modelChoice = value.model_configuration_id ? `configuration:${findConfiguration(catalogue.profiles, value.model_configuration_id)?.id ?? value.model_configuration_id}` : value.deployment_id ? `deployment:${value.deployment_id}` : "";
  const configurations = catalogue.profiles.filter(item => item.bundle_id);
  const external = catalogue.deployments.filter(item => item.scope === "connected");
  const knownModel = !modelChoice || configurations.some(item => modelChoice === `configuration:${item.id}`) || external.some(item => modelChoice === `deployment:${item.id}`);
  const knowledge = (kind: KnowledgeEntry["kind"]) => catalogue.knowledge.filter(entry => entry.kind === kind && entry.enabled !== false && entry.scope_bound !== false).map(entry => ({ id: entry.current_version_id, name: entry.display_name || (kind === "memory" ? "Untitled memory" : kind === "skill" ? "Untitled skill" : "Untitled instruction") }));
  const count = (key: keyof SetupConfiguration) => value[key] == null ? inheritedLabel(facts[key]) : settingValue(value[key]);
  const inheritedTools = Array.isArray(facts.presented_tools?.value) ? facts.presented_tools.value.filter((name): name is string => typeof name === "string") : catalogue.tools.filter(item => item.available !== false && !optionalVisualToolNames.has(item.id)).map(item => item.id);
  const availableToolNames = new Set(catalogue.tools.map(tool => tool.id));
  const browserSupported = browserToolNames.every(name => availableToolNames.has(name));
  const desktopSupported = desktopToolNames.every(name => availableToolNames.has(name));
  const browserValue = (value.presented_tools ?? inheritedTools).some(name => browserToolNames.some(browserName => browserName === name)) ? "on" : "off";
  const projectBound = Boolean(projectId);
  const knowledgeRoutes = Boolean(value.memory_version_refs?.length || value.skill_version_refs?.length);
  const modelOptions = <>{configurations.map(item => <option key={item.id} value={`configuration:${item.id}`}>{configurationLabel(item, catalogue.bundles.find(bundle => bundle.id === item.bundle_id)?.display_name)}</option>)}{external.map(item => <option key={item.id} value={`deployment:${item.id}`}>{item.display_name} · connected</option>)}{!knownModel ? <option value={modelChoice}>Unavailable configuration</option> : null}</>;
  return <div className="setup-configuration-editor setting-rows">
    <SettingRow label="Model" htmlFor={`${id}-model`}><select id={`${id}-model`} value={modelChoice} disabled={disabled} onChange={event => { const choice = event.target.value; patch({ model_configuration_id: choice.startsWith("configuration:") ? choice.slice(14) : null, deployment_id: choice.startsWith("deployment:") ? choice.slice(11) : null, bundle_id: null, profile_id: null, inherit_deployment_settings: null }); }}><option value="">{scope === "agent" ? "Use chat’s model" : scope === "application" ? "Use loaded model" : "Use application default"}</option>{modelOptions}</select></SettingRow>
    <SegmentedChoice label="Access" description="Ask pauses before edits, shell commands and external effects. Full access permits enabled tools. Saved permissions are named exceptions. Host shell runs with your Windows user’s authority."
      meta={value.approval_mode ? undefined : inheritedLabel(facts.approval_mode)} value={value.approval_mode ?? ""} disabled={disabled} inheritedValue={typeof facts.approval_mode?.value === "string" ? facts.approval_mode.value : undefined}
      options={[{ value: "", label: "Inherited" }, { value: "ask", label: "Ask" }, { value: "full_access", label: "Full access" }]} onChange={next => patch({ approval_mode: (next || null) as SetupConfiguration["approval_mode"] })} />
    <SegmentedChoice label="Test browser" description="Uses an isolated browser. Screenshots need a vision-capable model to inspect visually; page structure remains available to text models." meta={value.presented_tools == null ? inheritedLabel(facts.presented_tools) : undefined} value={browserValue} disabled={disabled || !browserSupported} hint={!browserSupported && catalogue.tools.length ? "The active backend does not offer test browser tools. Restart Workbench." : undefined}
      options={[{ value: "off", label: "Off" }, { value: "on", label: "On" }]}
      onChange={next => patch({ presented_tools: withBrowserTools(value.presented_tools ?? inheritedTools, next === "on", projectBound, knowledgeRoutes) })} />
    <SegmentedChoice label="Windows" description="Selected window requires a live choice in each chat. All windows grants that conversation access to open windows until revoked or Workbench restarts." meta={value.desktop_access == null ? inheritedLabel(facts.desktop_access) : undefined} value={value.desktop_access ?? "inherit"} disabled={disabled || !desktopSupported} hint={!desktopSupported && catalogue.tools.length ? "The active backend does not offer window testing tools. Restart Workbench." : undefined}
      options={[{ value: "inherit", label: "Inherited" }, { value: "off", label: "Off" }, { value: "selected", label: "Selected" }, { value: "all", label: "All windows" }]}
      onChange={next => patch({ desktop_access: next === "inherit" ? null : next as SetupConfiguration["desktop_access"], presented_tools: next === "inherit" && value.presented_tools == null ? null : withDesktopTools(value.presented_tools ?? inheritedTools, next === "inherit" ? inheritedTools.some(name => desktopToolNames.some(desktopName => desktopName === name)) : next !== "off", projectBound, knowledgeRoutes) })} />
    <SettingRow stacked label="Instructions" htmlFor={`${id}-instructions`} help="Adds guidance at this level. Instructions never grant additional permissions."><textarea id={`${id}-instructions`} value={value.instructions ?? ""} disabled={disabled} onChange={event => patch({ instructions: event.target.value || null })} placeholder={scope === "agent" ? "How should this agent work?" : scope === "project" ? "Guidance for conversations in this project" : "Guidance for new conversations"} rows={4} /></SettingRow>
    {preview.error ? <p className="hint" role="status">Settings preview: {preview.error}</p> : null}
    {compatibilityIssue ? <p className="hint" role="status">{compatibilityIssue}</p> : null}
    <details className="setup-options"><summary>Tools and connections <span className="hint">{count("presented_tools")}</span></summary><SelectionList title="Tools" values={value.presented_tools} options={catalogue.tools} fact={facts.presented_tools} disabled={disabled} onChange={presented_tools => patch({ presented_tools })} /><SelectionList title="Connections" values={value.connection_ids} options={catalogue.connections} fact={facts.connection_ids} disabled={disabled} onChange={connection_ids => patch({ connection_ids })} /></details>
    <details className="setup-options"><summary>Knowledge</summary>{(["memory", "skill", "protected_instruction"] as const).map(kind => { const key = kind === "memory" ? "memory_version_refs" : kind === "skill" ? "skill_version_refs" : "protected_instruction_version_refs"; return <SelectionList key={kind} title={kind === "memory" ? "Memories" : kind === "skill" ? "Skills" : "Instructions"} values={value[key]} options={knowledge(kind)} fact={facts[key]} disabled={disabled} onChange={next => patch({ [key]: next })} />; })}</details>
    {requirements ? <details className="setup-options"><summary>Workspace requirements<HoverHelp title="Requirements">Describes what this agent needs; does not grant access.</HoverHelp></summary>{(["requires_project", "requires_host_shell"] as const).map(key => <SegmentedChoice key={key} label={key === "requires_project" ? "Project folder" : "Shell access"} meta={value[key] == null ? inheritedLabel(facts[key]) : undefined} disabled={disabled} value={value[key] == null ? "inherit" : value[key] ? "required" : "optional"}
      options={[{ value: "inherit", label: "Inherited" }, { value: "required", label: "Required" }, { value: "optional", label: "Not required" }]} onChange={next => patch({ [key]: next === "inherit" ? null : next === "required" })} />)}</details> : null}
  </div>;
}
