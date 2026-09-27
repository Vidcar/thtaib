import { useEffect, useRef, useState } from "react";
import { workspaceApi, type AgentSetup, type AgentSetupVersion, type SetupConfiguration } from "./workspaceApi";
import { SetupConfigurationEditor, scopedSetupConfiguration, useSetupCatalogue, visualSetupCompatibilityIssue } from "./SetupConfigurationEditor";
import { errorMessage } from "./errors";
import { formatWhen } from "./display";
import { EmptyState } from "./EmptyState";
import { HoverHelp } from "./HoverHelp";
import { Icon } from "./Icon";
import { Notice } from "./Notice";
import { LifecycleAction } from "./LifecycleAction";
import "./WorkspacePanels.css";

interface SetupDraft { name: string; role: string; configuration: SetupConfiguration; base_version: string; }
const draftOf = (record?: AgentSetup): SetupDraft => ({ name: record?.name ?? "", role: record?.role ?? "", configuration: record?.configuration ?? {}, base_version: record?.current_version_id ?? "" });

export function AgentSetupsPanel({ onUse }: { onUse?: (setup: AgentSetup) => void }) {
  const [records, setRecords] = useState<AgentSetup[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [creating, setCreating] = useState(false);
  const [step, setStep] = useState(0);
  const [drafts, setDrafts] = useState<Record<string, SetupDraft>>({});
  const [newDraft, setNewDraft] = useState<SetupDraft>(() => draftOf());
  const [versions, setVersions] = useState<AgentSetupVersion[]>([]);
  const [versionsError, setVersionsError] = useState("");
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const actionPending = useRef(false);
  const { catalogue, error: catalogueError } = useSetupCatalogue();
  const selected = records.find(record => record.id === selectedId);
  const draft = creating ? newDraft : selected ? drafts[selected.id] ?? draftOf(selected) : newDraft;
  const visualCompatibilityIssue = visualSetupCompatibilityIssue(draft.configuration, catalogue);
  async function refresh(preferredId?: string) {
    const next = await workspaceApi.agentSetups();
    setRecords(next); setLoading(false);
    setSelectedId(current => next.some(record => record.id === (preferredId ?? current)) ? preferredId ?? current : next[0]?.id ?? "");
  }
  useEffect(() => { let cancelled = false; void workspaceApi.agentSetups().then(next => { if (!cancelled) { setRecords(next); setSelectedId(next[0]?.id ?? ""); setCreating(!next.length); } }).catch(failure => { if (!cancelled) setError(errorMessage(failure)); }).finally(() => { if (!cancelled) setLoading(false); }); return () => { cancelled = true; }; }, []);
  useEffect(() => {
    setVersions([]); setVersionsError("");
    if (!selected || creating) return;
    let cancelled = false;
    void workspaceApi.agentSetupVersions(selected.id).then(next => { if (!cancelled) setVersions(next); }).catch(failure => { if (!cancelled) setVersionsError(errorMessage(failure)); });
    return () => { cancelled = true; };
  }, [selected?.id, selected?.current_version_id, creating]);
  const updateDraft = (patch: Partial<SetupDraft>) => { if (creating) setNewDraft(current => ({ ...current, ...patch })); else if (selected) setDrafts(current => ({ ...current, [selected.id]: { ...(current[selected.id] ?? draftOf(selected)), ...patch } })); };
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
      await refresh(next.id); setCreating(false); setStep(0); setNewDraft(draftOf()); setDrafts(current => { const nextDrafts = { ...current }; delete nextDrafts[next.id]; return nextDrafts; }); setMessage("Agent saved.");
    });
  }
  return <section className="surface workspace-records-surface">
    <header className="surface-head"><div className="entity-head"><h2>Agents</h2><HoverHelp title="About agents">Save instructions, model, tools and knowledge. Chat controls access.</HoverHelp></div><button type="button" disabled={busy} onClick={() => { setCreating(true); setStep(0); }}><Icon name="plus" size={15} /> New agent</button></header>
    {error ? <Notice tone="error" action={!records.length && !creating ? <button type="button" onClick={() => void action(() => refresh())}>Retry</button> : undefined}>{error}</Notice> : null}
    {catalogueError ? <Notice tone="warn">Some setup choices could not load: {catalogueError}</Notice> : null}
    {message ? <p className="hint" role="status">{message}</p> : null}
    <div className="workspace-records-layout"><aside className="workspace-record-list" aria-label="Saved agents">{loading ? <p className="hint">Loading agents…</p> : !records.length ? <EmptyState title="No agents yet">Create a setup you can reuse in Chat.</EmptyState> : <ul className="nav-list">{records.map(record => <li key={record.id}><button type="button" className={!creating && selectedId === record.id ? "nav-item active" : "nav-item"} disabled={busy} onClick={() => { setSelectedId(record.id); setCreating(false); }}><span className="nav-item-title">{record.name}</span><span className="nav-item-meta">{record.role || "Reusable setup"}{record.missing_dependencies?.length ? " · Needs attention" : ""}{drafts[record.id] ? " · Unsaved changes" : ""}</span></button></li>)}</ul>}</aside>
    <div className="workspace-record-detail">{creating || selected ? <>
      <form className="card workspace-editor" onSubmit={event => { event.preventDefault(); if (creating && step < 2) { if (draft.name.trim()) setStep(current => current + 1); } else void save(); }}>
        <div className="section-heading"><h3>{creating ? "New agent" : selected!.name}</h3>{!creating && onUse ? <button type="button" disabled={busy || Boolean(selected?.missing_dependencies?.length)} onClick={() => onUse(selected!)}><Icon name="chat" size={15} /> Use in Chat</button> : null}</div>
        {selected?.missing_dependencies?.length && !creating ? <Notice tone="warn">This setup needs attention.<ul>{selected.missing_dependencies.map((issue, index) => <li key={`${issue.kind}-${issue.id}-${index}`}>{issue.reason}</li>)}</ul></Notice> : null}
        {selected?.helper_missing_dependencies?.length && !creating ? <Notice tone="warn">This agent needs attention before it can run as a helper.<ul>{selected.helper_missing_dependencies.map((issue, index) => <li key={`${issue.kind}-${issue.id}-${index}`}>{issue.reason}</li>)}</ul></Notice> : null}
        {creating ? <nav className="model-tabs" aria-label="Agent creation steps">{["Role", "Setup", "Review"].map((label, index) => <span key={label} aria-current={step === index ? "step" : undefined}>{index + 1}. {label}</span>)}</nav> : null}
        {!creating || step === 0 ? <div className="setup-form-grid"><label>Name<input required maxLength={200} value={draft.name} disabled={busy} onChange={event => updateDraft({ name: event.target.value })} placeholder="Research assistant" /></label><label>Role<input value={draft.role} disabled={busy} onChange={event => updateDraft({ role: event.target.value })} placeholder="Read sources and compare findings" /></label></div> : null}
        {creating && step === 2 ? <dl className="setting-rows"><div><dt>Name</dt><dd>{draft.name}</dd></div><div><dt>Role</dt><dd>{draft.role || "General assistant"}</dd></div><div><dt>Model</dt><dd>{catalogue.profiles.find(profile => profile.id === draft.configuration.model_configuration_id)?.display_name ?? catalogue.deployments.find(deployment => deployment.id === draft.configuration.deployment_id)?.display_name ?? "Use Chat model"}</dd></div><div><dt>Tools</dt><dd>{draft.configuration.presented_tools == null ? "Standard tools" : `${draft.configuration.presented_tools.length} selected`}</dd></div><div><dt>Knowledge</dt><dd>{(draft.configuration.memory_entry_ids?.length ?? 0) + (draft.configuration.skill_entry_ids?.length ?? 0) + (draft.configuration.protected_instruction_entry_ids?.length ?? 0)} selected</dd></div></dl> : null}
        <SetupConfigurationEditor value={draft.configuration} catalogue={catalogue} disabled={busy} requirements agentOptions={records} currentAgentId={creating ? null : selected?.id} sections={creating ? step === 0 ? ["instructions"] : step === 1 ? ["model", "tools", "knowledge", "helpers", "requirements"] : ["review"] : undefined} onChange={configuration => updateDraft({ configuration })} />
        <div className="actions">{creating && step > 0 ? <button type="button" disabled={busy} onClick={() => setStep(current => current - 1)}>Back</button> : null}<button type="submit" className="primary-button" disabled={busy || !draft.name.trim() || Boolean(visualCompatibilityIssue)}>{creating && step < 2 ? "Next" : <><Icon name="check" size={14} />{busy ? "Saving…" : "Save agent"}</>}</button>{!creating && drafts[selected!.id] ? <button type="button" disabled={busy} onClick={() => setDrafts(current => { const next = { ...current }; delete next[selected!.id]; return next; })}>Discard edits</button> : null}{creating && records.length ? <button type="button" disabled={busy} onClick={() => setCreating(false)}>Cancel</button> : null}</div>
      </form>
      {!creating && selected ? <>
        <div className="actions"><button type="button" disabled={busy} onClick={() => void action(async () => { const next = await workspaceApi.duplicateAgentSetup(selected.id); await refresh(next.id); setMessage("Agent duplicated."); })}><Icon name="copy" size={14} />Duplicate</button></div>
        <LifecycleAction key={selected.id} path={`/v1/agent-setups/${selected.id}`} name={selected.name} label="Remove agent" disabled={busy} onBusyChange={setBusy} onComplete={async () => { await refresh(); setMessage("Agent removed from future selection."); }} />
        <details className="card workspace-versions"><summary>Version history <span>{versions.length}</span></summary>{versionsError ? <Notice tone="error">{versionsError}</Notice> : null}<ul className="plain-list">{versions.map(version => <li key={version.id}><div className="section-heading"><strong>{formatWhen(version.created_at)}</strong><span className="hint">{version.id === selected.current_version_id ? "Current" : "Earlier version"}</span></div><details><summary>{version.name}{version.role ? ` · ${version.role}` : ""}</summary><p className="workspace-text">{version.configuration?.instructions || "No additional instructions."}</p></details>{version.id !== selected.current_version_id ? <button type="button" disabled={busy} onClick={() => { setDrafts(current => ({ ...current, [selected.id]: { name: version.name, role: version.role ?? "", configuration: version.configuration ?? {}, base_version: selected.current_version_id } })); setMessage("Earlier version loaded into the editor. Save to create a new current version."); }}>Load into editor</button> : null}</li>)}</ul></details>
      </> : null}
    </> : <EmptyState title="Choose an agent">Select a saved setup or create one.</EmptyState>}</div></div>
  </section>;
}
