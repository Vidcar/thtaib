import { useEffect, useRef, useState } from "react";
import { workspaceApi, type AgentSetup, type AgentSetupTemplate, type AgentSetupVersion, type SetupConfiguration } from "./workspaceApi";
import { SetupConfigurationEditor, scopedSetupConfiguration, setupModelLabel, useSetupCatalogue, visualSetupCompatibilityIssue, type SetupCatalogue } from "./SetupConfigurationEditor";
import { CatalogueWorkspace } from "./CatalogueWorkspace";
import { SettingRow } from "./CompactControls";
import { errorMessage } from "./errors";
import { formatWhen } from "./display";
import { EmptyState } from "./EmptyState";
import { HoverHelp } from "./HoverHelp";
import { Icon } from "./Icon";
import { Notice } from "./Notice";
import { LifecycleAction } from "./LifecycleAction";
import { AgentInputs } from "./AgentInputs";
import type { WorkbenchTab } from "./types";
import "./WorkspacePanels.css";
import "./AgentSetupsPanel.css";

interface SetupDraft { name: string; role: string; configuration: SetupConfiguration; base_version: string; }
type AgentTab = "role" | "model" | "knowledge" | "helpers" | "review";
const draftOf = (record?: AgentSetup): SetupDraft => ({ name: record?.name ?? "", role: record?.role ?? "", configuration: record?.configuration ?? {}, base_version: record?.current_version_id ?? "" });
function templateConfiguration(current: SetupConfiguration, template: SetupConfiguration): SetupConfiguration {
  const modelFields = ["deployment_id", "bundle_id", "model_configuration_id", "startup_overrides", "profile_id", "inherit_deployment_settings", "per_request_overrides"] as const;
  return { ...template, ...Object.fromEntries(modelFields.filter(key => Object.hasOwn(current, key)).map(key => [key, current[key]])) };
}
function comparable(value: unknown): string {
  if (Array.isArray(value)) return JSON.stringify(value.map(item => comparable(item)).sort());
  if (value && typeof value === "object") return JSON.stringify(Object.entries(value).sort(([left], [right]) => left.localeCompare(right)).map(([key, item]) => [key, comparable(item)]));
  return JSON.stringify(value) ?? "undefined";
}
function isChanged(draft: SetupDraft, record: AgentSetup) {
  return draft.name !== record.name || draft.role !== (record.role ?? "") || comparable(scopedSetupConfiguration(draft.configuration, "agent")) !== comparable(scopedSetupConfiguration(record.configuration, "agent"));
}

function AgentReview({ draft, catalogue, agents }: { draft: SetupDraft; catalogue: SetupCatalogue; agents: AgentSetup[] }) {
  const configuration = draft.configuration;
  const names = (ids: string[] | null | undefined, kind: "memory" | "skill" | "protected_instruction") => ids?.length ? ids.map(id => catalogue.knowledge.find(entry => entry.id === id && entry.kind === kind)?.display_name ?? "Unavailable selection").join(", ") : "None selected";
  const toolNames = configuration.presented_tools == null ? "Standard tools" : configuration.presented_tools.length ? configuration.presented_tools.map(id => catalogue.tools.find(tool => tool.id === id)?.name ?? id).join(", ") : "All off";
  return <dl className="agent-review">
    <div><dt>Name</dt><dd>{draft.name}</dd></div><div><dt>Role</dt><dd>{draft.role || "General assistant"}</dd></div>
    <div><dt>Instructions</dt><dd className="workspace-text">{configuration.instructions || "No additional instructions"}</dd></div>
    <div><dt>Model</dt><dd>{setupModelLabel(configuration, catalogue)}</dd></div>
    <div><dt>Tools</dt><dd>{toolNames}</dd></div>
    <div><dt>Connections</dt><dd>{configuration.connection_ids?.length ? configuration.connection_ids.map(id => catalogue.connections.find(connection => connection.id === id)?.name ?? "Unavailable connection").join(", ") : "None selected"}</dd></div>
    <div><dt>Memories</dt><dd>{names(configuration.memory_entry_ids, "memory")}</dd></div>
    <div><dt>Skills</dt><dd>{names(configuration.skill_entry_ids, "skill")}</dd></div>
    <div><dt>Instructions from Knowledge</dt><dd>{names(configuration.protected_instruction_entry_ids, "protected_instruction")}</dd></div>
    <div><dt>Helpers</dt><dd>{configuration.helper_agent_ids?.length ? <ul>{configuration.helper_agent_ids.map(id => {
      const helper = agents.find(agent => agent.id === id);
      return <li key={id}><strong>{helper?.name ?? "Unavailable helper"}</strong>{helper ? <> · {setupModelLabel(helper.configuration, catalogue)}{helper.active === false || helper.helper_missing_dependencies?.length ? " · Needs attention" : ""}<small>{[helper.configuration.requires_project ? "Project required" : "", helper.configuration.requires_host_shell ? "Shell required" : ""].filter(Boolean).join(" · ") || "No additional requirements"}</small></> : null}</li>;
    })}</ul> : "None selected"}</dd></div>
    <div><dt>Review</dt><dd>{configuration.review?.enabled ? <>On · up to 2 revisions{configuration.review.criteria ? <p className="workspace-text">{configuration.review.criteria}</p> : null}</> : "Off"}</dd></div>
    <div><dt>Requirements</dt><dd>{[configuration.requires_project ? "Project folder required" : "", configuration.requires_host_shell ? "Shell access required" : ""].filter(Boolean).join(" · ") || "No additional requirements"}</dd></div>
  </dl>;
}

export function AgentSetupsPanel({ openAgentId, openRequest, active = true, onNavigate }: { onUse?: (setup: AgentSetup) => void; openAgentId?: string; openRequest?: number; active?: boolean; onNavigate?: (tab: WorkbenchTab, id?: string) => void }) {
  const [records, setRecords] = useState<AgentSetup[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [creating, setCreating] = useState(false);
  const [step, setStep] = useState(0);
  const [tab, setTab] = useState<AgentTab>("role");
  const [query, setQuery] = useState("");
  const [drafts, setDrafts] = useState<Record<string, SetupDraft>>({});
  const [newDraft, setNewDraft] = useState<SetupDraft>(() => draftOf());
  const [templates, setTemplates] = useState<AgentSetupTemplate[]>([]);
  const [templateId, setTemplateId] = useState("");
  const [appliedTemplateId, setAppliedTemplateId] = useState("");
  const [versions, setVersions] = useState<AgentSetupVersion[]>([]);
  const [versionsLoading, setVersionsLoading] = useState(false);
  const [versionsError, setVersionsError] = useState("");
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [showInputs, setShowInputs] = useState(false);
  const actionPending = useRef(false);
  const openedRequest = useRef("");
  const initialized = useRef(false);
  const { catalogue, error: catalogueError } = useSetupCatalogue(active);
  const activeRecords = records.filter(record => record.active !== false);
  const selected = activeRecords.find(record => record.id === selectedId);
  const draft = creating ? newDraft : selected ? drafts[selected.id] ?? draftOf(selected) : newDraft;
  const visualCompatibilityIssue = visualSetupCompatibilityIssue(draft.configuration, catalogue);
  useEffect(() => {
    if (!active || !creating) return;
    let cancelled = false;
    void workspaceApi.agentSetupTemplates().then(next => { if (!cancelled) setTemplates(next); }).catch(failure => { if (!cancelled) setError(errorMessage(failure)); });
    return () => { cancelled = true; };
  }, [active, creating]);
  async function refresh(preferredId?: string) {
    const next = await workspaceApi.agentSetups(true);
    const available = next.filter(record => record.active !== false);
    setRecords(next); setLoading(false);
    setSelectedId(current => available.some(record => record.id === (preferredId ?? current)) ? preferredId ?? current : available[0]?.id ?? "");
  }
  useEffect(() => {
    if (!active) return;
    let cancelled = false;
    void workspaceApi.agentSetups(true).then(next => {
      if (cancelled) return;
      const available = next.filter(record => record.active !== false);
      setRecords(next); setError("");
      setSelectedId(current => available.some(record => record.id === current) ? current : available[0]?.id ?? "");
      if (!initialized.current) { setCreating(!available.length); initialized.current = true; }
    }).catch(failure => { if (!cancelled) setError(errorMessage(failure)); }).finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [active]);
  useEffect(() => {
    if (!openAgentId || loading) return;
    const request = `${openRequest ?? 0}:${openAgentId}`;
    if (openedRequest.current === request) return;
    openedRequest.current = request;
    if (records.some(record => record.id === openAgentId && record.active !== false)) { setSelectedId(openAgentId); setCreating(false); setTab("role"); setQuery(""); }
    else setMessage("This agent is unavailable. Choose another saved agent.");
  }, [openAgentId, openRequest, records, loading]);
  useEffect(() => {
    if (!active) return;
    setVersions([]); setVersionsError("");
    if (!selected || creating) { setVersionsLoading(false); return; }
    setVersionsLoading(true);
    let cancelled = false;
    void workspaceApi.agentSetupVersions(selected.id).then(next => { if (!cancelled) setVersions(next); }).catch(failure => { if (!cancelled) setVersionsError(errorMessage(failure)); }).finally(() => { if (!cancelled) setVersionsLoading(false); });
    return () => { cancelled = true; };
  }, [selected?.id, selected?.current_version_id, creating, active]);
  const updateDraft = (patch: Partial<SetupDraft>) => {
    if (creating) setNewDraft(current => ({ ...current, ...patch }));
    else if (selected) setDrafts(current => {
      const next = { ...(current[selected.id] ?? draftOf(selected)), ...patch };
      const all = { ...current };
      if (isChanged(next, selected)) all[selected.id] = next; else delete all[selected.id];
      return all;
    });
  };
  async function action(work: () => Promise<void>) {
    if (actionPending.current) return;
    actionPending.current = true; setBusy(true); setError(""); setMessage("");
    try { await work(); } catch (failure) { setError(errorMessage(failure)); }
    finally { actionPending.current = false; setBusy(false); }
  }
  async function save() {
    if (!draft.name.trim()) return;
    if (visualCompatibilityIssue) { setError(visualCompatibilityIssue); return; }
    await action(async () => {
      const payload = { name: draft.name.trim(), role: draft.role.trim() || null, configuration: scopedSetupConfiguration(draft.configuration, "agent") };
      const next = creating ? await workspaceApi.createAgentSetup(payload) : await workspaceApi.updateAgentSetup(selected!.id, { ...payload, base_version: draft.base_version });
      await refresh(next.id); setCreating(false); setStep(0); setTab("role"); setNewDraft(draftOf());
      setDrafts(current => { const nextDrafts = { ...current }; delete nextDrafts[next.id]; return nextDrafts; }); setMessage("Agent saved.");
    });
  }
  const sections = creating ? step === 0 ? ["instructions"] as const : step === 1 ? ["model", "tools", "knowledge", "helpers", "requirements"] as const : ["review"] as const
    : tab === "role" ? ["instructions"] as const : tab === "model" ? ["model", "tools"] as const : tab === "knowledge" ? ["knowledge"] as const : tab === "helpers" ? ["helpers"] as const : ["review", "requirements"] as const;
  const visibleRecords = activeRecords.filter(record => `${record.name} ${record.role ?? ""} ${setupModelLabel(record.configuration, catalogue)}`.toLowerCase().includes(query.toLowerCase()));
  const appliedTemplate = templates.find(item => item.id === appliedTemplateId);
  const roleFields = <div className="agent-role-fields"><SettingRow label="Name" htmlFor="agent-draft-name"><input id="agent-draft-name" required maxLength={200} value={draft.name} disabled={busy} onChange={event => updateDraft({ name: event.target.value })} /></SettingRow><SettingRow label="Role" htmlFor="agent-draft-role"><input id="agent-draft-role" value={draft.role} disabled={busy} onChange={event => updateDraft({ role: event.target.value })} /></SettingRow></div>;
  return <section className="surface workspace-records-surface agents-surface">
    <header className="surface-head"><div className="entity-head"><Icon name="agents" /><h2>Agents</h2><HoverHelp title="About agents">Save instructions, model, tools and knowledge. Chat controls access.</HoverHelp></div><button type="button" disabled={busy} onClick={() => { initialized.current = true; setCreating(true); setStep(0); }}><Icon name="plus" size={15} /> New agent</button></header>
    {error ? <Notice tone="error" action={!activeRecords.length && !creating ? <button type="button" onClick={() => void action(() => refresh())}>Retry</button> : undefined}>{error}</Notice> : null}
    {catalogueError ? <Notice tone="warn">Some setup choices could not load: {catalogueError}</Notice> : null}
    {message ? <p className="hint" role="status">{message}</p> : null}
    <CatalogueWorkspace title="Agents" search={query} onSearch={setQuery} items={visibleRecords.map(record => ({ id: record.id, name: record.name, icon: "agents", detail: <>{record.role || "General assistant"}<br />{setupModelLabel(record.configuration, catalogue)}</>, status: [record.missing_dependencies?.length ? "Needs attention" : "", drafts[record.id] ? "Unsaved changes" : ""].filter(Boolean).join(" · "), selectorLabel: `${record.name} · ${setupModelLabel(record.configuration, catalogue)}` }))} selectedId={creating ? "" : selectedId} onSelect={id => { if (!busy) { setSelectedId(id); setCreating(false); } }} emptyLabel={query ? "No matching agents" : "No agents yet"} loading={loading}>
      {creating || selected ? <>
        <form className="agent-editor workspace-editor" onKeyDown={event => {
          if (event.key !== "Enter" || event.shiftKey || event.nativeEvent.isComposing || event.repeat) return;
          const type = (event.target as HTMLInputElement | null)?.type;
          const tag = (event.target as HTMLElement | null)?.tagName;
          if (tag === "INPUT" && (type === "search" || type === "checkbox" || type === "radio")) event.preventDefault();
        }} onSubmit={event => { event.preventDefault(); if (creating && step < 2) { if (draft.name.trim()) setStep(current => current + 1); } else void save(); }}>
          <div className="section-heading"><h3>{creating ? "New agent" : selected!.name}</h3><button type="button" disabled={busy} title="Instructions, memories, skills, and files for the next message." onClick={() => setShowInputs(true)}>Inputs</button></div>
          {creating && step === 0 ? <div className="setup-options"><label>Starting template<HoverHelp title="Starting template">Templates populate this draft for review. Save when ready; model settings and live grants stay under their existing owners.</HoverHelp><select value={templateId} disabled={busy} onChange={event => setTemplateId(event.target.value)}><option value="">Start from an empty draft</option>{templates.map(template => <option key={template.id} value={template.id}>{template.name}</option>)}</select></label><button type="button" disabled={busy || !templateId} onClick={() => { const template = templates.find(item => item.id === templateId); if (!template) return; setNewDraft(current => ({ name: template.name, role: template.role, configuration: templateConfiguration(current.configuration, template.configuration), base_version: "" })); setAppliedTemplateId(template.id); }}>Use template</button>{appliedTemplate ? <p className="hint" role="status">Template applied<HoverHelp title="Template applied">{`${appliedTemplate.note} Recommended skills: ${appliedTemplate.recommended_skills.join(", ")}. ${appliedTemplate.configuration.skill_entry_ids?.length ?? 0} already installed personal skills selected; add others through Knowledge when useful. Chat access remains your current choice.`}</HoverHelp></p> : null}</div> : null}
          {selected?.missing_dependencies?.length && !creating ? <Notice tone="warn">This setup needs attention.<ul>{selected.missing_dependencies.map((issue, index) => <li key={`${issue.kind}-${issue.id}-${index}`}>{issue.kind.includes("model") || issue.kind.includes("deployment") || issue.kind.includes("bundle") ? "Assigned model" : issue.kind === "connection" ? "Connection" : issue.kind === "tool" ? "Tool" : "Knowledge selection"}: {issue.reason}</li>)}</ul><div className="actions"><button type="button" onClick={() => setTab(selected.missing_dependencies?.some(issue => /memory|skill|instruction/.test(issue.kind)) ? "knowledge" : "model")}>Review selections</button></div></Notice> : null}
          {selected?.helper_missing_dependencies?.length && !creating ? <Notice tone="warn">Needs attention when used as a helper.<ul>{selected.helper_missing_dependencies.map((issue, index) => <li key={`${issue.kind}-${issue.id}-${index}`}>{issue.reason}</li>)}</ul></Notice> : null}
          {creating ? <nav className="model-tabs agent-steps" aria-label="Agent creation steps">{["Role", "Setup", "Review"].map((label, index) => <span key={label} aria-current={step === index ? "step" : undefined}>{index + 1}. {label}</span>)}</nav>
            : <nav className="model-tabs" aria-label="Agent sections">{([["role", "Role"], ["model", "Model & tools"], ["knowledge", "Knowledge"], ["helpers", "Helpers"], ["review", "Review"]] as const).map(([value, label]) => <button type="button" key={value} aria-current={tab === value ? "page" : undefined} onClick={() => setTab(value)}>{label}</button>)}</nav>}
          {(creating && step === 0) || (!creating && tab === "role") ? roleFields : null}
          {(creating && step === 2) || (!creating && tab === "review") ? <AgentReview draft={draft} catalogue={catalogue} agents={records} /> : null}
          <SetupConfigurationEditor value={draft.configuration} catalogue={catalogue} disabled={busy} active={active} requirements agentOptions={records} currentAgentId={creating ? null : selected?.id} sections={[...sections]} onChange={configuration => updateDraft({ configuration })} />
          <div className="actions agent-editor-actions">{creating && step > 0 ? <button type="button" disabled={busy} onClick={() => setStep(current => current - 1)}><Icon name="back" size={14} />Back</button> : null}<button type="submit" className="primary-button" disabled={busy || !draft.name.trim() || Boolean(visualCompatibilityIssue)} onClick={event => { if (event.detail > 1) event.preventDefault(); }}>{creating && step < 2 ? <>Next<Icon name="forward" size={14} /></> : <><Icon name="check" size={14} />{busy ? "Saving…" : "Save agent"}</>}</button>{!creating && drafts[selected!.id] ? <button type="button" disabled={busy} onClick={() => setDrafts(current => { const next = { ...current }; delete next[selected!.id]; return next; })}>Discard edits</button> : null}{creating && activeRecords.length ? <button type="button" disabled={busy} onClick={() => setCreating(false)}>Cancel</button> : null}{!creating && drafts[selected!.id] ? <span className="hint">Unsaved changes</span> : null}</div>
        </form>
        {!creating && selected ? <>
          <details className="workspace-versions"><summary><Icon name="restore" size={14} />Version history <small>{versionsError ? "Unavailable" : versionsLoading ? "Loading…" : `${versions.length} saved`}</small></summary>{versionsError ? <Notice tone="error">{versionsError}</Notice> : null}<ul className="plain-list">{versions.map(version => <li key={version.id}><div className="section-heading"><strong>{formatWhen(version.created_at)}</strong><span className="hint">{version.id === selected.current_version_id ? "Current" : "Earlier version"}</span></div><details><summary>{version.name}{version.role ? ` · ${version.role}` : ""}</summary><p className="workspace-text">{version.configuration?.instructions || "No additional instructions."}</p></details>{version.id !== selected.current_version_id ? <button type="button" disabled={busy} onClick={() => { setDrafts(current => ({ ...current, [selected.id]: { name: version.name, role: version.role ?? "", configuration: version.configuration ?? {}, base_version: selected.current_version_id } })); setTab("role"); setMessage("Earlier version loaded into the editor. Save to create a new current version."); }}>Load into editor</button> : null}</li>)}</ul></details>
          <div className="actions agent-lifecycle-actions"><button type="button" disabled={busy} onClick={() => void action(async () => { const next = await workspaceApi.duplicateAgentSetup(selected.id); await refresh(next.id); setTab("role"); setMessage("Agent duplicated."); })}><Icon name="copy" size={14} />Duplicate</button><LifecycleAction key={selected.id} path={`/v1/agent-setups/${selected.id}`} name={selected.name} label="Remove agent" disabled={busy} onBusyChange={setBusy} onComplete={async () => { await refresh(); setMessage("Agent removed from future selection."); }} /></div>
        </> : null}
      </> : <EmptyState title="Choose an agent" />}
    </CatalogueWorkspace>
    {showInputs ? <AgentInputs scope="agent" configuration={draft.configuration} disabled={busy} onChange={configuration => updateDraft({ configuration })} onClose={() => setShowInputs(false)} onEditSource={(owner, recordId) => { setShowInputs(false); onNavigate?.(owner, recordId ?? (owner === "models" ? draft.configuration.model_configuration_id ?? undefined : selected?.id)); }} /> : null}
  </section>;
}
