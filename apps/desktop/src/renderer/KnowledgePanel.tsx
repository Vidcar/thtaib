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
import { SkillPackageImport, SkillResources } from "./SkillPackageControls";
import { knowledgeApi, type KnowledgeScopeOption, type KnowledgeProposal } from "./knowledgeApi";
import "./WorkspacePanels.css";
import type {
  ContextCapture,
  KnowledgeConfig,
  KnowledgeEntry,
  KnowledgeKind,
  KnowledgeScope,
  KnowledgeVersion,
  RedactionMode,
} from "./types";

export function KnowledgePanel() {
  const [entries, setEntries] = useState<KnowledgeEntry[]>([]);
  const [selected, setSelected] = useState<KnowledgeEntry | null>(null);
  const [versions, setVersions] = useState<KnowledgeVersion[]>([]);
  const [config, setConfig] = useState<KnowledgeConfig | null>(null);
  const [capture, setCapture] = useState<ContextCapture | null>(null);
  const [message, setMessage] = useState("");
  const [loadError, setLoadError] = useState("");
  const [scope, setScope] = useState<KnowledgeScope>("user");
  const [kind, setKind] = useState<KnowledgeKind>("memory");
  const [displayName, setDisplayName] = useState("");
  const [scopeId, setScopeId] = useState("");
  const [scopes, setScopes] = useState<KnowledgeScopeOption[]>([]);
  const [proposals, setProposals] = useState<KnowledgeProposal[]>([]);
  const [rename, setRename] = useState<string | null>(null);
  const [policyDestination, setPolicyDestination] = useState("user:");
  const [filterKind, setFilterKind] = useState<KnowledgeKind>("memory");
  const [query, setQuery] = useState("");
  const [drafts, setDrafts] = useState<Record<string, { content: string; baseVersion: string }>>({});
  const [busy, setBusy] = useState(false);
  const actionPending = useRef(false);
  const [content, setContent] = useState("");
  const [editContent, setEditContent] = useState("");
  const [captureText, setCaptureText] = useState("");
  const [redactionMode, setRedactionMode] = useState<RedactionMode>("redact_secrets");
  const [creating, setCreating] = useState(false);

  async function refresh(): Promise<KnowledgeEntry[]> {
    const [nextEntries, nextConfig, nextProposals, nextScopes] = await Promise.all([api.knowledgeEntries(), api.knowledgeConfig(), knowledgeApi.proposals(), knowledgeApi.scopes()]);
    setEntries(nextEntries);
    if (!config) setCreating(nextEntries.length === 0);
    setConfig(nextConfig);
    setProposals(nextProposals); setScopes(nextScopes);
    setRedactionMode(nextConfig.context_captures.redaction_mode);
    setSelected((current) => nextEntries.find((item) => item.id === current?.id) ?? nextEntries.find(item => item.kind === filterKind) ?? null);
    setLoadError("");
    return nextEntries;
  }

  useEffect(() => {
    void refresh().catch((error: unknown) => {
      setLoadError(errorMessage(error));
    });
  }, []);

  useEffect(() => {
    setVersions([]);
    setRename(null);
    if (!selected) {
      return;
    }
    let cancelled = false;
    void api
      .knowledgeVersions(selected.id)
      .then(next => { if (!cancelled) setVersions(next); })
      .catch((error: unknown) => { if (!cancelled) setMessage(errorMessage(error)); });
    setEditContent(drafts[selected.id]?.content ?? selected.content);
    return () => { cancelled = true; };
  }, [selected]);

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

  if (loadError) {
    return (
      <section className="surface">
        <h2>Knowledge</h2>
        <Notice tone="error">{loadError}</Notice>
        <button type="button" onClick={() => void refresh().catch((error: unknown) => setLoadError(errorMessage(error)))}>
          Retry
        </button>
      </section>
    );
  }

  return (
    <section className="surface workspace-records-surface knowledge-surface">
      <header className="surface-head">
        <div className="entity-head"><h2>Knowledge</h2><HoverHelp title="About Knowledge">Save memories, skills and instructions here. Choose which entries each chat uses.</HoverHelp></div>
        <button type="button" disabled={busy} onClick={() => { setKind(filterKind); setCreating(true); }}><Icon name="plus" size={15} />New {knowledgeKindLabel(filterKind).toLowerCase()}</button>
      </header>

      <nav className="model-tabs" aria-label="Knowledge types">{([["memory", "Memories"], ["skill", "Skills"], ["protected_instruction", "Instructions"]] as const).map(([value, label]) => <button type="button" key={value} disabled={busy} aria-current={filterKind === value ? "page" : undefined} onClick={() => { setFilterKind(value); setKind(value); setCreating(false); setSelected(entries.find(entry => entry.kind === value) ?? null); }}>{label} <span>{entries.filter(entry => entry.kind === value).length}</span></button>)}</nav>
      <p className="hint">{filterKind === "memory" ? "Facts and preferences to use again." : filterKind === "skill" ? "Reusable ways of working and their supporting files." : "Guidance you control. Agents cannot rewrite these instructions."}</p>
      {filterKind === "skill" ? <details className="card"><summary>Import a skill package</summary><SkillPackageImport onImported={async next => { await refresh(); setSelected(next); setCreating(false); }} /></details> : null}

      {creating ? <section className="card">
        <h3>New {knowledgeKindLabel(kind).toLowerCase()}</h3>
      <form
        className="compact-form"
        onSubmit={(event) => {
          event.preventDefault();
          if (!content.trim()) {
            setMessage("Write some content before creating an entry.");
            return;
          }
          if (scope !== "user" && !scopeId) { setMessage("Choose a real project or agent for this entry."); return; }
          void action(async () => { await api
            .createKnowledgeEntry({
              scope,
              kind,
              content,
              display_name: displayName.trim() || undefined,
              scope_id: scope === "user" ? undefined : scopeId,
            })
            .then(async (next) => {
              setMessage(`Created ${entryTitle(next)}.`);
              setContent("");
              await refresh();
              setSelected(next);
              setFilterKind(next.kind);
              setCreating(false);
            })
          });
        }}
      >
        <div className="setup-form-grid">
          <label>
            Kind
            <select disabled={busy} value={kind} onChange={(event) => setKind(event.target.value as KnowledgeKind)}>
              <option value="memory">Memory</option>
              <option value="skill">Skill</option>
              <option value="protected_instruction">Instruction</option>
            </select>
          </label>
          <label>
            Use in
            <select disabled={busy} value={scope} onChange={(event) => { setScope(event.target.value as KnowledgeScope); setScopeId(""); }}>
              <option value="user">Personal</option>
              <option value="agent">Agent</option>
              <option value="project">Project</option>
            </select>
          </label>
          {scope !== "user" ? <label>{scope === "project" ? "Project" : "Agent"}<select value={scopeId} disabled={busy} required onChange={event => setScopeId(event.target.value)}><option value="">Choose {scope === "project" ? "a project" : "an agent"}</option>{scopes.filter(option => option.scope === scope && option.active).map(record => <option key={record.scope_id} value={record.scope_id ?? ""}>{record.label}</option>)}</select></label> : null}
        </div>
        <label>
          Name (optional)
          <input disabled={busy} value={displayName} onChange={(event) => setDisplayName(event.target.value)} />
        </label>
        <label>
          Content
          <textarea disabled={busy} value={content} onChange={(event) => setContent(event.target.value)} />
        </label>
        <div className="actions"><button type="submit" className="primary-button" disabled={busy || !content.trim() || (scope !== "user" && !scopeId)}><Icon name="plus" size={14} /> Save</button><button type="button" disabled={busy} onClick={() => setCreating(false)}>Cancel</button></div>
      </form>
      </section> : null}

      <label className="knowledge-search">Search<input value={query} onChange={event => setQuery(event.target.value)} placeholder="Search names and content" /></label>
      <div className="workspace-records-layout">
        <aside className="workspace-record-list">
          {visibleEntries.length === 0 ? (
            <EmptyState title="No entries yet">
              Add a memory, skill or instruction.
            </EmptyState>
          ) : (
            <ul className="nav-list">
              {visibleEntries.map((item) => (
                <li key={item.id}>
                  <button
                    type="button"
                    disabled={busy}
                    className={item.id === selected?.id ? "nav-item active" : "nav-item"}
                    onClick={() => setSelected(item)}
                  >
                    <span className="nav-item-title">{entryTitle(item)}</span>
                    <span className="nav-item-meta">
                      {scopeLabel(item)}{drafts[item.id] ? " · Unsaved changes" : ""}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </aside>

        <div className="card">
          {selected ? (
            <>
              <div className="entity-head">
                <h3>{entryTitle(selected)}</h3>
                <StatusBadge label={knowledgeKindLabel(selected.kind)} />
                <StatusBadge label={knowledgeActorLabel(selected.provenance.actor)} />
              </div>
              <p className="hint">
                {scopeLabel(selected)} · updated {formatWhen(selected.updated_at)}
              </p>
              {selected.scope_bound === false ? <Notice tone="warn">This entry's project or agent is unavailable. Its history remains readable, but it cannot be used in a new run.</Notice> : null}
              <div className="actions"><button type="button" disabled={busy} onClick={() => setRename(selected.display_name ?? "")}>Rename</button>{selected.enabled === false ? <><button type="button" disabled={busy} onClick={() => void action(async () => { await knowledgeApi.updateEntry(selected.id, { enabled: true }); await refresh(); })}>Enable</button><StatusBadge label="Disabled" /></> : <LifecycleAction key={`disable:${selected.id}`} path={`/v1/knowledge/entries/${selected.id}`} name={entryTitle(selected)} label="Disable" confirmLabel="Disable entry" method="PATCH" body={{ enabled: false }} disabled={busy} onBusyChange={setBusy} onComplete={async () => { await refresh(); }} />}<LifecycleAction key={`remove:${selected.id}`} path={`/v1/knowledge/entries/${selected.id}`} name={entryTitle(selected)} label="Remove" confirmLabel="Remove entry" disabled={busy} onBusyChange={setBusy} onComplete={async () => { setDrafts(current => { const next = { ...current }; delete next[selected.id]; return next; }); await refresh(); }} /></div>
              {rename !== null ? <form className="actions" onSubmit={event => { event.preventDefault(); void action(async () => { await knowledgeApi.updateEntry(selected.id, { display_name: rename.trim() }); await refresh(); setRename(null); }); }}><label>Name<input autoFocus value={rename} disabled={busy} onChange={event => setRename(event.target.value)} /></label><button type="submit" disabled={busy || !rename.trim()}>Save name</button><button type="button" disabled={busy} onClick={() => setRename(null)}>Cancel</button></form> : null}
              <details>
                <summary>Details</summary>
                <p className="hint">
                  Entry ID: {selected.id} · current version: {selected.current_version_id}
                </p>
              </details>
              {selected.kind === "skill" ? <><SkillResources key={selected.current_version_id} versionId={selected.current_version_id} resources={selected.resources} /><details><summary>Update from a package</summary><SkillPackageImport key={selected.id} entry={selected} onImported={async next => { await refresh(); setSelected(next); setDrafts(current => { const drafts = { ...current }; delete drafts[next.id]; return drafts; }); }} /></details></> : null}
              <label>
                Content
                <textarea disabled={busy} value={editContent} onChange={(event) => { const value = event.target.value; setEditContent(value); setDrafts(current => ({ ...current, [selected.id]: { content: value, baseVersion: current[selected.id]?.baseVersion ?? selected.current_version_id } })); }} />
              </label>
              <div className="actions">
                <button
                  type="button"
                  disabled={busy || !editContent.trim() || editContent === selected.content}
                  onClick={() => {
                    void action(async () => { await api
                      .editKnowledgeEntry(selected.id, editContent, drafts[selected.id]?.baseVersion ?? selected.current_version_id)
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
                {drafts[selected.id] ? <button type="button" disabled={busy} onClick={() => void action(async () => { const refreshed = await refresh(); setDrafts(current => { const next = { ...current }; delete next[selected.id]; return next; }); setEditContent(refreshed.find(item => item.id === selected.id)?.content ?? selected.content); })}>Discard edits and reload</button> : null}
              </div>
              <details><summary><Icon name="restore" size={14} /> Version history <span className="badge">{versions.length}</span></summary>
              {versions.length === 0 ? (
                <p className="hint">No versions loaded.</p>
              ) : (
                <ul className="plain-list">
                  {versions.map((version) => (
                    <li key={version.id} className="entity">
                      <p>
                        {formatWhen(version.created_at)} · {knowledgeActorLabel(version.provenance.actor)}
                        {version.id === selected.current_version_id ? " · current" : ""}
                        {version.reverted_from_version_id ? " · restored from an earlier version" : ""}
                      </p>
                      <details><summary>Read this version</summary><pre className="wrapped-text">{version.content}</pre></details>
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
      </div>

      <details className="card" open={proposals.some(proposal => proposal.status === "pending") || undefined}><summary>Suggested memories <span className="badge">{proposals.filter(proposal => proposal.status === "pending").length}</span></summary>
        <p className="hint">Review what will be saved and where. Accepting a change checks that its original version is still current.</p>
        {proposals.length === 0 ? <p className="hint">No suggestions yet.</p> : <ul className="plain-list">{proposals.map(proposal => <li className="entity" key={proposal.id}><div className="entity-head"><strong>{proposal.display_name || "Memory suggestion"}</strong><StatusBadge label={proposal.status} /></div><p className="hint">{scopes.find(option => option.scope === proposal.scope && (option.scope_id ?? null) === (proposal.scope_id ?? null))?.label ?? "Unavailable destination"} · {formatWhen(proposal.created_at)}{proposal.automatic ? " · saved automatically" : ""}</p>{proposal.entry_id ? <details><summary>Current saved content</summary><pre className="wrapped-text">{entries.find(entry => entry.id === proposal.entry_id)?.content ?? "Entry unavailable"}</pre></details> : null}<pre className="wrapped-text">{proposal.content}</pre><details><summary>Origin</summary><p className="hint">{knowledgeActorLabel(proposal.provenance.actor)}{proposal.provenance.run_id ? ` · run ${proposal.provenance.run_id}` : ""}{proposal.base_version ? ` · based on ${proposal.base_version}` : ""}</p></details>{proposal.status === "pending" ? <div className="actions"><button type="button" disabled={busy} onClick={() => void action(async () => { await knowledgeApi.review(proposal.id, "accept"); await refresh(); })}>Accept</button><button type="button" disabled={busy} onClick={() => void action(async () => { await knowledgeApi.review(proposal.id, "reject"); await refresh(); })}>Reject</button></div> : null}</li>)}</ul>}
      </details>
      <details className="card"><summary>Automatic memory saving</summary><p className="hint">Suggestions need review unless you allow automatic saving for a specific destination. Instructions always remain under your control.</p><label>Destination<select value={policyDestination} disabled={busy} onChange={event => setPolicyDestination(event.target.value)}>{scopes.filter(option => option.active).map(option => <option key={`${option.scope}:${option.scope_id ?? ""}`} value={`${option.scope}:${option.scope_id ?? ""}`}>{option.label}</option>)}</select></label><label className="check-row"><input type="checkbox" disabled={busy || !scopes.some(option => `${option.scope}:${option.scope_id ?? ""}` === policyDestination)} checked={Boolean(config?.automatic_save_policies?.find(policy => `${policy.scope}:${policy.scope_id ?? ""}` === policyDestination)?.automatic_agent_writes)} onChange={event => { const automatic = event.target.checked; const destination = scopes.find(option => `${option.scope}:${option.scope_id ?? ""}` === policyDestination); if (destination) void action(async () => setConfig(await knowledgeApi.automaticPolicy({ scope: destination.scope, scope_id: destination.scope_id, automatic_agent_writes: automatic }))); }} />Allow agents to save memories here automatically</label></details>

      <details className="card">
        <summary><Icon name="files" size={15} /> Context capture</summary>
        <div className="entity-head"><h3>Capture settings</h3><HoverHelp title="About context capture">Save request text for troubleshooting. Secrets are redacted by default.</HoverHelp></div>
        <label>
          Redaction
          <select
            value={redactionMode}
            onChange={(event) => setRedactionMode(event.target.value as RedactionMode)}
          >
            <option value="redact_secrets">{redactionModeLabel("redact_secrets")}</option>
            <option value="retain">{redactionModeLabel("retain")}</option>
            <option value="discard">{redactionModeLabel("discard")}</option>
          </select>
        </label>
        {redactionMode === "retain" ? <p className="notice notice-warn">Unredacted captures can include secrets.</p> : null}
        <label>
          Text to capture
          <textarea value={captureText} onChange={(event) => setCaptureText(event.target.value)} />
        </label>
        <div className="actions">
          <button
            type="button"
            onClick={() => {
              void api
                .updateKnowledgeConfig({ context_captures: { redaction_mode: redactionMode } })
                .then((next) => {
                  setConfig(next);
                  setMessage(`Capture redaction set to ${redactionModeLabel(next.context_captures.redaction_mode)}.`);
                })
                .catch(fail);
            }}
          >
            <Icon name="check" size={14} /> Save setting
          </button>
          <button
            type="button"
            disabled={!captureText.trim()}
            onClick={() => {
              void api
                .createContextCapture(captureText)
                .then((next) => {
                  setCapture(next);
                  setMessage(
                    next.discarded
                      ? "Capture discarded by the current setting."
                      : next.redacted
                        ? "Capture stored with secrets redacted."
                        : "Capture stored.",
                  );
                })
                .catch(fail);
            }}
          >
            <Icon name="files" size={14} /> Capture
          </button>
        </div>
        {config ? (
          <p className="hint">
            Mode: {redactionModeLabel(config.context_captures.redaction_mode)}
            {config.context_captures.retention_seconds != null
              ? ` · retain ${config.context_captures.retention_seconds}s`
              : " · retain until deleted"}
          </p>
        ) : null}
        {capture ? (
          <p className="hint">
            Last capture {shortId(capture.id)}
            {capture.redacted ? " · redacted" : ""}
            {capture.discarded ? " · discarded" : ""}
            {capture.expired ? " · expired" : ""}
          </p>
        ) : null}
      </details>

      {message ? <Notice tone={/fail|error|conflict/i.test(message) ? "error" : "info"}>{message}</Notice> : null}
    </section>
  );
}
