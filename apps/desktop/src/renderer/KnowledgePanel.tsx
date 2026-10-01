import { useEffect, useRef, useState } from "react";

import { api } from "./api";
import { formatWhen, shortId } from "./display";
import { EmptyState } from "./EmptyState";
import { errorMessage } from "./errors";
import { HoverHelp } from "./HoverHelp";
import { Icon } from "./Icon";
import { knowledgeActorLabel, knowledgeKindLabel, redactionModeLabel } from "./labels";
import { Notice } from "./Notice";
import { LifecycleAction } from "./LifecycleAction";
import { StatusBadge } from "./StatusBadge";
import { BundledRuntimeSkills, SkillPackageImport, SkillResources } from "./SkillPackageControls";
import { knowledgeApi, type KnowledgeScopeOption, type KnowledgeProposal, type SkillResourceChange } from "./knowledgeApi";
import { SkillEditor } from "./SkillEditor";
import { MemoryProposalCard } from "./MemoryProposalCard";
import { CatalogueWorkspace } from "./CatalogueWorkspace";
import "./WorkspacePanels.css";
import "./KnowledgePanel.css";
import { CompactSwitch, SegmentedChoice, SettingRow } from "./CompactControls";
import type {
  ContextCapture,
  KnowledgeConfig,
  KnowledgeEntry,
  KnowledgeKind,
  KnowledgeScope,
  KnowledgeVersion,
  RedactionMode,
} from "./types";

const SKILL_STARTER = `---
name: my-skill
description: Describe when the assistant should use this skill.
---

# My skill

Explain the steps the assistant should follow.
`;

export function KnowledgePanel({ active = true, openEntryId, openRequest }: { active?: boolean; openEntryId?: string; openRequest?: number } = {}) {
  const [entries, setEntries] = useState<KnowledgeEntry[]>([]);
  const [selected, setSelected] = useState<KnowledgeEntry | null>(null);
  const [versions, setVersions] = useState<KnowledgeVersion[]>([]);
  const [versionsLoading, setVersionsLoading] = useState(false);
  const [config, setConfig] = useState<KnowledgeConfig | null>(null);
  const [capture, setCapture] = useState<ContextCapture | null>(null);
  const [message, setMessage] = useState("");
  const [loadError, setLoadError] = useState("");
  const [loading, setLoading] = useState(true);
  const [configError, setConfigError] = useState("");
  const [scopesError, setScopesError] = useState("");
  const [proposalsError, setProposalsError] = useState("");
  const [versionsError, setVersionsError] = useState("");
  const initialized = useRef(false);
  const openedRequest = useRef("");
  const [scope, setScope] = useState<KnowledgeScope>("user");
  const [kind, setKind] = useState<KnowledgeKind>("memory");
  const [displayName, setDisplayName] = useState("");
  const [description, setDescription] = useState("");
  const [editDescription, setEditDescription] = useState("");
  const [scopeId, setScopeId] = useState("");
  const [scopes, setScopes] = useState<KnowledgeScopeOption[]>([]);
  const [proposals, setProposals] = useState<KnowledgeProposal[]>([]);
  const [rename, setRename] = useState<string | null>(null);
  const renameDrafts = useRef<Record<string, string>>({});
  const [policyDestination, setPolicyDestination] = useState("user:");
  const [filterKind, setFilterKind] = useState<KnowledgeKind>("memory");
  const [query, setQuery] = useState("");
  const [drafts, setDrafts] = useState<Record<string, { content: string; description?: string; baseVersion: string; resourceChanges?: SkillResourceChange[] }>>({});
  const [newResources, setNewResources] = useState<SkillResourceChange[]>([]);
  const [newSkillValid, setNewSkillValid] = useState(false);
  const [editSkillValid, setEditSkillValid] = useState(false);
  const [busy, setBusy] = useState(false);
  const actionPending = useRef(false);
  const [content, setContent] = useState("");
  const [editContent, setEditContent] = useState("");
  const [captureText, setCaptureText] = useState("");
  const [redactionMode, setRedactionMode] = useState<RedactionMode>("redact_secrets");
  const redactionDirty = useRef(false);
  const [creating, setCreating] = useState(false);

  async function refresh(isCurrent = () => true): Promise<KnowledgeEntry[]> {
    const nextEntries = await api.knowledgeEntries();
    if (!isCurrent()) return nextEntries;
    setEntries(nextEntries);
    if (!initialized.current) { setCreating(nextEntries.length === 0); initialized.current = true; }
    setSelected((current) => nextEntries.find((item) => item.id === current?.id) ?? nextEntries.find(item => item.kind === filterKind) ?? null);
    setLoadError(""); setLoading(false);
    return nextEntries;
  }

  async function refreshConfig(isCurrent = () => true) {
    try { const next = await api.knowledgeConfig(); if (isCurrent()) { setConfig(next); if (!redactionDirty.current) setRedactionMode(next.context_captures.redaction_mode); setConfigError(""); } }
    catch (failure) { if (isCurrent()) setConfigError(errorMessage(failure)); }
  }
  async function refreshScopes(isCurrent = () => true) {
    try { const next = await knowledgeApi.scopes(); if (isCurrent()) { setScopes(next); setScopesError(""); } }
    catch (failure) { if (isCurrent()) setScopesError(errorMessage(failure)); }
  }
  async function refreshProposals(isCurrent = () => true) {
    try { const next = await knowledgeApi.proposals(); if (isCurrent()) { setProposals(next); setProposalsError(""); } }
    catch (failure) { if (isCurrent()) setProposalsError(errorMessage(failure)); }
  }

  useEffect(() => {
    if (!active) return;
    let cancelled = false;
    const isCurrent = () => !cancelled;
    void refresh(isCurrent).catch((error: unknown) => { if (!cancelled) { setLoadError(errorMessage(error)); setLoading(false); } });
    void refreshConfig(isCurrent); void refreshScopes(isCurrent); void refreshProposals(isCurrent);
    return () => { cancelled = true; };
  }, [active]);

  useEffect(() => {
    if (!active || !openEntryId || loading) return;
    const request = `${openRequest ?? 0}:${openEntryId}`;
    if (openedRequest.current === request) return;
    const entry = entries.find(item => item.id === openEntryId);
    if (!entry) { setMessage("This Knowledge entry is unavailable. Choose another entry."); openedRequest.current = request; return; }
    openedRequest.current = request;
    setSelected(entry); setFilterKind(entry.kind); setCreating(false); setQuery("");
  }, [active, openEntryId, openRequest, entries, loading]);

  useEffect(() => {
    if (!active) return;
    setVersions([]);
    setVersionsError("");
    setRename(selected ? renameDrafts.current[selected.id] ?? null : null);
    if (!selected) {
      setVersionsLoading(false);
      return;
    }
    setVersionsLoading(true);
    let cancelled = false;
    void api
      .knowledgeVersions(selected.id)
      .then(next => { if (!cancelled) setVersions(next); })
      .catch((error: unknown) => { if (!cancelled) setVersionsError(errorMessage(error)); })
      .finally(() => { if (!cancelled) setVersionsLoading(false); });
    setEditContent(drafts[selected.id]?.content ?? selected.content);
    setEditDescription(drafts[selected.id]?.description ?? selected.description ?? "");
    return () => { cancelled = true; };
  }, [selected, active]);

  async function action(work: () => Promise<void>) {
    if (actionPending.current) return;
    actionPending.current = true; setBusy(true); setMessage("");
    try { await work(); } catch (failure) { fail(failure); }
    finally { actionPending.current = false; setBusy(false); }
  }

  function scopeLabel(entry: KnowledgeEntry): string {
    if (entry.scope_label) return entry.scope_label;
    if (entry.scope === "user") return "Personal";
    if (!entry.scope_id) return `Unbound ${entry.scope}`;
    return scopes.find(option => option.scope === entry.scope && option.scope_id === entry.scope_id)?.label ?? `Unavailable ${entry.scope}`;
  }

  const visibleEntries = entries.filter(entry => entry.kind === filterKind && `${entry.display_name ?? ""} ${entry.content}`.toLowerCase().includes(query.toLowerCase()));

  function fail(error: unknown): void {
    setMessage(errorMessage(error));
  }

  function entryTitle(entry: KnowledgeEntry): string {
    return entry.display_name?.trim() || `Untitled ${knowledgeKindLabel(entry.kind).toLowerCase()}`;
  }

  function updateEntryDraft(value: string, resourceChanges?: SkillResourceChange[], nextDescription?: string) {
    if (!selected) return;
    setEditContent(value);
    if (nextDescription !== undefined) setEditDescription(nextDescription);
    setDrafts(current => {
      const resources = resourceChanges ?? current[selected.id]?.resourceChanges ?? [];
      const description = nextDescription ?? current[selected.id]?.description ?? selected.description ?? "";
      const next = { ...current };
      if (value === selected.content && description === (selected.description ?? "") && !resources.length) delete next[selected.id];
      else next[selected.id] = { content: value, description, baseVersion: current[selected.id]?.baseVersion ?? selected.current_version_id, resourceChanges: resources };
      return next;
    });
  }

  const creationEditor = <section className="knowledge-create-editor workspace-editor">
        <h3>New {knowledgeKindLabel(kind).toLowerCase()}</h3>
      <form
        className="compact-form"
        onSubmit={(event) => {
          event.preventDefault();
          if (!content.trim()) {
            setMessage("Write some content before creating an entry.");
            return;
          }
          if (kind === "skill" && !newSkillValid) return;
          if (scope !== "user" && !scopeId) { setMessage("Choose a real project or agent for this entry."); return; }
          void action(async () => { await knowledgeApi
            .createEntry({
              scope,
              kind,
              content,
              display_name: displayName.trim() || undefined,
              ...(kind === "memory" ? { description: description.trim() || null } : {}),
              scope_id: scope === "user" ? undefined : scopeId,
              resource_changes: kind === "skill" ? newResources : [],
            })
            .then(async (next) => {
              setMessage(`Created ${entryTitle(next)}.`);
              setContent("");
              setDescription("");
              await refresh();
              setSelected(next);
              setFilterKind(next.kind);
              setCreating(false);
            })
          });
        }}
      >
        <SegmentedChoice label="Kind" value={kind} disabled={busy} options={[{ value: "memory", label: "Memory" }, { value: "skill", label: "Skill" }, { value: "protected_instruction", label: "Instruction" }]} onChange={value => { const next = value as KnowledgeKind; setKind(next); if (next === "skill" && !content.trim()) setContent(SKILL_STARTER); }} />
        <SegmentedChoice label="Use in" value={scope} disabled={busy} options={[{ value: "user", label: "Personal" }, { value: "agent", label: "Agent" }, { value: "project", label: "Project" }]} onChange={value => { setScope(value as KnowledgeScope); setScopeId(""); }} />
        {scope !== "user" ? <SettingRow label={scope === "project" ? "Project" : "Agent"} htmlFor="knowledge-create-scope"><select id="knowledge-create-scope" value={scopeId} disabled={busy || Boolean(scopesError)} required onChange={event => setScopeId(event.target.value)}><option value="">Choose {scope === "project" ? "a project" : "an agent"}</option>{scopes.filter(option => option.scope === scope && option.active).map(record => <option key={record.scope_id} value={record.scope_id ?? ""}>{record.label}</option>)}</select></SettingRow> : null}
        <SettingRow label="Display name (optional)" htmlFor="knowledge-create-name" help={kind === "skill" ? "A label in Knowledge. The skill's native name is saved separately in SKILL.md." : undefined}><input id="knowledge-create-name" disabled={busy} value={displayName} onChange={event => setDisplayName(event.target.value)} /></SettingRow>
        {kind === "memory" ? <SettingRow stacked label="When to use (optional)" htmlFor="knowledge-create-description" help="A short description helps the agent find this memory before reading its full text."><textarea id="knowledge-create-description" rows={2} maxLength={1024} value={description} disabled={busy} onChange={event => setDescription(event.target.value)} /></SettingRow> : null}
        {kind === "skill" ? <SkillEditor content={content} onChange={value => { setContent(value); setNewSkillValid(false); }} disabled={busy} scope={scope} scopeId={scope === "user" ? null : scopeId} resourceChanges={newResources} onResourceChanges={setNewResources} onStateChange={setNewSkillValid} /> : <SettingRow stacked label="Content" htmlFor="knowledge-create-content"><textarea id="knowledge-create-content" disabled={busy} value={content} onChange={event => setContent(event.target.value)} /></SettingRow>}
        <div className="actions knowledge-save-actions"><button type="submit" className="primary-button" disabled={busy || !content.trim() || (kind === "skill" && !newSkillValid) || (scope !== "user" && (!scopeId || Boolean(scopesError)))}><Icon name="plus" size={14} /> Save</button><button type="button" disabled={busy} onClick={() => setCreating(false)}>Cancel</button></div>
      </form>
      </section>;

  return (
    <section className="surface workspace-records-surface knowledge-surface">
      <header className="surface-head">
        <div className="entity-head"><Icon name="knowledge" /><h2>Knowledge</h2><HoverHelp title="About Knowledge">Save memories, skills and instructions. New messages use the latest saved selected entries.</HoverHelp></div>
        <button type="button" disabled={busy} onClick={() => { initialized.current = true; setKind(filterKind); setDisplayName(""); setDescription(""); setContent(filterKind === "skill" ? SKILL_STARTER : ""); setNewResources([]); setNewSkillValid(false); setCreating(true); }}><Icon name="plus" size={15} />New {knowledgeKindLabel(filterKind).toLowerCase()}</button>
      </header>
      {loadError ? <Notice tone="error" action={<button type="button" disabled={busy} onClick={() => void refresh().catch(failure => setLoadError(errorMessage(failure)))}>Retry entries</button>}>{loadError}</Notice> : null}
      {scopesError ? <Notice tone="warn" action={<button type="button" onClick={() => void refreshScopes()}>Retry destinations</button>}>Project and agent destinations could not load. Personal entries remain available. {scopesError}</Notice> : null}

      <nav className="model-tabs" aria-label="Knowledge types">{([["memory", "Memories"], ["skill", "Skills"], ["protected_instruction", "Instructions"]] as const).map(([value, label]) => <button type="button" key={value} disabled={busy} aria-current={filterKind === value ? "page" : undefined} onClick={() => { setFilterKind(value); setKind(value); setCreating(false); setSelected(entries.find(entry => entry.kind === value) ?? null); }}>{label} <span>{entries.filter(entry => entry.kind === value).length}</span></button>)}</nav>
      {filterKind === "skill" ? <><BundledRuntimeSkills onImported={async next => { await refresh(); setSelected(next); setCreating(false); }} /><details className="card"><summary>Import a skill package</summary><SkillPackageImport onImported={async next => { await refresh(); setSelected(next); setCreating(false); }} /></details></> : null}

      <CatalogueWorkspace title="Knowledge" search={query} onSearch={setQuery} searchPlaceholder="Search names and content" items={visibleEntries.map(item => ({ id: item.id, name: entryTitle(item), icon: item.kind === "skill" ? "sparkles" : item.kind === "protected_instruction" ? "shield" : "knowledge", detail: scopeLabel(item), status: [item.enabled === false ? "Disabled" : "", item.scope_bound === false ? "Unavailable scope" : "", drafts[item.id] ? "Unsaved changes" : ""].filter(Boolean).join(" · "), selectorLabel: `${entryTitle(item)} · ${scopeLabel(item)}` }))} selectedId={creating ? "" : selected?.id ?? ""} onSelect={id => { if (!busy) { setSelected(entries.find(item => item.id === id) ?? null); setCreating(false); } }} loading={loading} emptyLabel={query.trim() ? "No matching entries" : "No entries yet"}>
        <div className="knowledge-editor workspace-editor">
          {creating ? creationEditor : selected ? (
            <>
              <div className="entity-head">
                <h3>{entryTitle(selected)}</h3>
                <StatusBadge label={knowledgeKindLabel(selected.kind)} />
                <StatusBadge label={knowledgeActorLabel(selected.provenance.actor)} />
              </div>
              <p className="hint">
                {scopeLabel(selected)} · updated {formatWhen(selected.updated_at)}
              </p>
              {selected.kind === "memory" ? <><p className="hint" title={selected.token_counting_method}>{selected.estimated_content_tokens != null ? `~${selected.estimated_content_tokens.toLocaleString()} tokens when read.` : "Full text is read when needed."} Choose its loading mode in Agents or Chat.</p><SettingRow stacked label="When to use (optional)" htmlFor="knowledge-edit-description" help="A short description helps the agent find this memory before reading its full text."><textarea id="knowledge-edit-description" rows={2} maxLength={1024} value={editDescription} disabled={busy} onChange={event => updateEntryDraft(editContent, undefined, event.target.value)} /></SettingRow></> : null}
              {selected.scope_bound === false ? <Notice tone="warn">This entry's project or agent is unavailable. Its history remains readable, but it cannot be used in a new run.</Notice> : null}
              <div className="actions"><button type="button" disabled={busy} onClick={() => { const value = renameDrafts.current[selected.id] ?? selected.display_name ?? ""; renameDrafts.current[selected.id] = value; setRename(value); }}>Rename</button>{selected.enabled === false ? <><button type="button" disabled={busy} onClick={() => void action(async () => { await knowledgeApi.updateEntry(selected.id, { enabled: true }); await refresh(); })}>Enable</button><StatusBadge label="Disabled" /></> : <LifecycleAction key={`disable:${selected.id}`} path={`/v1/knowledge/entries/${selected.id}`} name={entryTitle(selected)} label="Disable" confirmLabel="Disable entry" method="PATCH" body={{ enabled: false }} disabled={busy} onBusyChange={setBusy} onComplete={async () => { await refresh(); }} />}<LifecycleAction key={`remove:${selected.id}`} path={`/v1/knowledge/entries/${selected.id}`} name={entryTitle(selected)} label="Remove" confirmLabel="Remove entry" disabled={busy} onBusyChange={setBusy} onComplete={async () => { setDrafts(current => { const next = { ...current }; delete next[selected.id]; return next; }); await refresh(); }} /></div>
              {rename !== null ? <form className="knowledge-rename" onSubmit={event => { event.preventDefault(); void action(async () => { await knowledgeApi.updateEntry(selected.id, { display_name: rename.trim() }); await refresh(); delete renameDrafts.current[selected.id]; setRename(null); }); }}><SettingRow label="Display name" htmlFor="knowledge-rename-name" help={selected.kind === "skill" ? "Renaming this label does not change the native skill name in SKILL.md." : undefined}><input id="knowledge-rename-name" autoFocus value={rename} disabled={busy} onChange={event => { renameDrafts.current[selected.id] = event.target.value; setRename(event.target.value); }} /></SettingRow><div className="actions"><button type="submit" disabled={busy || !rename.trim()}>Save name</button><button type="button" disabled={busy} onClick={() => { delete renameDrafts.current[selected.id]; setRename(null); }}>Cancel</button></div></form> : null}
              <details>
                <summary>Details</summary>
                <p className="hint">
                  Entry ID: {selected.id} · current version: {selected.current_version_id}
                </p>
              </details>
              {selected.kind === "skill" ? <><SkillEditor key={selected.id} content={editContent} onChange={value => { setEditSkillValid(false); updateEntryDraft(value); }} disabled={busy} scope={selected.scope} scopeId={selected.scope_id} entryId={selected.id} versionId={selected.current_version_id} resources={selected.resources} resourceChanges={drafts[selected.id]?.resourceChanges ?? []} onResourceChanges={resourceChanges => updateEntryDraft(editContent, resourceChanges)} onStateChange={setEditSkillValid} /><details><summary>Update from a package</summary><SkillPackageImport key={selected.id} entry={selected} onImported={async next => { await refresh(); setSelected(next); setDrafts(current => { const drafts = { ...current }; delete drafts[next.id]; return drafts; }); }} /></details></> : <SettingRow stacked label="Content" htmlFor="knowledge-edit-content"><textarea id="knowledge-edit-content" disabled={busy} value={editContent} onChange={event => updateEntryDraft(event.target.value)} /></SettingRow>}
              <div className="actions knowledge-save-actions">
                <button
                  type="button"
                  disabled={busy || !editContent.trim() || (selected.kind === "skill" && !editSkillValid) || !drafts[selected.id]}
                  onClick={() => {
                    void action(async () => { await knowledgeApi
                      .editEntry(selected.id, editContent, drafts[selected.id]?.baseVersion ?? selected.current_version_id, drafts[selected.id]?.resourceChanges ?? [], selected.kind === "memory" ? editDescription.trim() || null : undefined)
                      .then(async (next) => {
                        setMessage("Saved a new version.");
                        await refresh();
                        setDrafts(current => { const drafts = { ...current }; delete drafts[next.id]; return drafts; });
                        setSelected(next);
                      })
                    });
                  }}
                >
                  <Icon name="check" size={14} /> Save
                </button>
                {drafts[selected.id] ? <button type="button" disabled={busy} onClick={() => void action(async () => { const refreshed = await refresh(); const saved = refreshed.find(item => item.id === selected.id) ?? selected; setDrafts(current => { const next = { ...current }; delete next[selected.id]; return next; }); setEditContent(saved.content); setEditDescription(saved.description ?? ""); })}>Discard edits and reload</button> : null}
              </div>
              <details><summary><Icon name="restore" size={14} /> Version history <span className="badge">{versionsError ? "Unavailable" : versionsLoading ? "Loading…" : versions.length}</span></summary>
              {versionsError ? <Notice tone="error">{versionsError}</Notice> : null}
              {versions.length === 0 ? (
                versionsLoading ? <p className="hint" role="status">Loading history…</p> : !versionsError ? <p className="hint">No saved versions.</p> : null
              ) : (
                <ul className="plain-list">
                  {versions.map((version) => (
                    <li key={version.id} className="entity">
                      <p>
                        {formatWhen(version.created_at)} · {knowledgeActorLabel(version.provenance.actor)}
                        {version.id === selected.current_version_id ? " · current" : ""}
                        {version.reverted_from_version_id ? " · restored from an earlier version" : ""}
                      </p>
                      <details><summary>Read this version</summary>{version.description ? <p className="hint">When to use: {version.description}</p> : null}<pre className="wrapped-text">{version.content}</pre></details>
                      {selected.kind === "skill" ? <SkillResources versionId={version.id} resources={version.resources} /> : null}
                      {version.id !== selected.current_version_id ? (
                        <button
                          type="button"
                          disabled={busy}
                          onClick={() => {
                            void action(async () => { await api
                              .revertKnowledgeEntry(selected.id, version.id, selected.current_version_id)
                              .then(async (next) => {
                                setMessage("Reverted; that created a new current version.");
                                await refresh();
                                setDrafts(current => { const drafts = { ...current }; delete drafts[next.id]; return drafts; });
                                setSelected(next);
                              })
                            });
                          }}
                        >
                          <Icon name="restore" size={14} /> Restore version
                        </button>
                      ) : null}
                    </li>
                  ))}
                </ul>
              )}
              </details>
            </>
          ) : (
            <EmptyState title="Select an entry">Edit content and review its history.</EmptyState>
          )}
        </div>
      </CatalogueWorkspace>

      <details className="knowledge-secondary" open={proposals.some(proposal => proposal.status === "pending") || undefined}>
        <summary>Suggested memories <small>{proposalsError ? "Unavailable" : `${proposals.filter(proposal => proposal.status === "pending").length} pending`}</small></summary>
        {proposalsError ? <Notice tone="warn" action={<button type="button" onClick={() => void refreshProposals()}>Retry suggestions</button>}>{proposalsError}</Notice> : null}
        <HoverHelp title="About suggested memories">Review what will be saved and where. Accepting a change checks that its original version is still current.</HoverHelp>
        {!proposals.length && !proposalsError ? <p className="hint">No suggestions yet.</p> : <ul className="plain-list">{proposals.map(proposal => <MemoryProposalCard key={proposal.id} proposal={proposal} destination={scopes.find(option => option.scope === proposal.scope && (option.scope_id ?? null) === (proposal.scope_id ?? null))?.label ?? "Unavailable destination"} meta={` · ${formatWhen(proposal.created_at)}`} currentContent={proposal.entry_id ? entries.find(entry => entry.id === proposal.entry_id)?.content ?? "Entry unavailable" : undefined} origin={<>{knowledgeActorLabel(proposal.provenance.actor)}{proposal.provenance.run_id ? ` · run ${proposal.provenance.run_id}` : ""}{proposal.base_version ? ` · based on ${proposal.base_version}` : ""}</>} acceptLabel="Accept" rejectLabel="Reject" busy={busy || Boolean(scopesError)} onAccept={() => void action(async () => { await knowledgeApi.review(proposal.id, "accept"); await refresh(); await refreshProposals(); })} onReject={() => void action(async () => { await knowledgeApi.review(proposal.id, "reject"); await refreshProposals(); })} />)}</ul>}
      </details>
      <details className="knowledge-secondary">
        <summary>Automatic memory saving <small>{configError ? "Unavailable" : config ? `${config.automatic_save_policies?.filter(policy => policy.automatic_agent_writes).length ?? 0} destinations on` : "Loading…"}</small></summary>
        {configError ? <Notice tone="warn" action={<button type="button" onClick={() => void refreshConfig()}>Retry settings</button>}>{configError}</Notice> : null}
        <SettingRow label="Destination" htmlFor="knowledge-policy-destination" help="Suggestions need review unless automatic saving is allowed for this exact destination. Instructions stay under your control."><select id="knowledge-policy-destination" value={policyDestination} disabled={busy || Boolean(scopesError)} onChange={event => setPolicyDestination(event.target.value)}>{scopes.filter(option => option.active).map(option => <option key={`${option.scope}:${option.scope_id ?? ""}`} value={`${option.scope}:${option.scope_id ?? ""}`}>{option.label}</option>)}</select></SettingRow>
        <CompactSwitch label="Save automatically" description="Allow agents to save memories to this destination without review." disabled={busy || !config || Boolean(configError) || !scopes.some(option => `${option.scope}:${option.scope_id ?? ""}` === policyDestination)} checked={Boolean(config?.automatic_save_policies?.find(policy => `${policy.scope}:${policy.scope_id ?? ""}` === policyDestination)?.automatic_agent_writes)} onChange={automatic => { const destination = scopes.find(option => `${option.scope}:${option.scope_id ?? ""}` === policyDestination); if (destination) void action(async () => setConfig(await knowledgeApi.automaticPolicy({ scope: destination.scope, scope_id: destination.scope_id, automatic_agent_writes: automatic }))); }} />
      </details>
      <details className="knowledge-secondary">
        <summary><Icon name="files" size={15} /> Diagnostic captures <small>{configError ? "Unavailable" : config ? redactionModeLabel(config.context_captures.redaction_mode) : "Loading…"}</small></summary>
        {configError ? <Notice tone="warn" action={<button type="button" onClick={() => void refreshConfig()}>Retry capture settings</button>}>{configError}</Notice> : null}
        <SegmentedChoice label="Redaction" description="Save request text for troubleshooting. Secrets are redacted by default." value={redactionMode} disabled={busy || !config || Boolean(configError)} options={[{ value: "redact_secrets", label: "Redact" }, { value: "retain", label: "Retain" }, { value: "discard", label: "Discard" }]} onChange={value => { redactionDirty.current = true; setRedactionMode(value as RedactionMode); }} />
        {redactionMode === "retain" ? <Notice tone="warn">Unredacted captures can include secrets.</Notice> : null}
        <SettingRow stacked label="Text to capture" htmlFor="knowledge-capture-text"><textarea id="knowledge-capture-text" value={captureText} disabled={busy} onChange={event => setCaptureText(event.target.value)} /></SettingRow>
        <div className="actions">
          <button type="button" disabled={busy || !config || Boolean(configError) || redactionMode === config.context_captures.redaction_mode} onClick={() => void action(async () => { const next = await api.updateKnowledgeConfig({ context_captures: { redaction_mode: redactionMode } }); setConfig(next); setRedactionMode(next.context_captures.redaction_mode); redactionDirty.current = false; setMessage(`Capture redaction set to ${redactionModeLabel(next.context_captures.redaction_mode)}.`); })}><Icon name="check" size={14} /> Save setting</button>
          <button type="button" disabled={busy || !config || Boolean(configError) || !captureText.trim()} onClick={() => void action(async () => { const next = await api.createContextCapture(captureText); setCapture(next); setMessage(next.discarded ? "Capture discarded by the current setting." : next.redacted ? "Capture stored with secrets redacted." : "Capture stored."); })}><Icon name="files" size={14} /> Capture</button>
        </div>
        {config ? <p className="hint">{redactionModeLabel(config.context_captures.redaction_mode)} · {config.context_captures.retention_seconds != null ? `Retain ${config.context_captures.retention_seconds}s` : "Retain until deleted"}</p> : null}
        {capture ? <p className="hint">Last capture {shortId(capture.id)}{capture.redacted ? " · redacted" : ""}{capture.discarded ? " · discarded" : ""}{capture.expired ? " · expired" : ""}</p> : null}
      </details>
      {message ? <Notice tone={/fail|error|conflict/i.test(message) ? "error" : "info"}>{message}</Notice> : null}
    </section>
  );
}
