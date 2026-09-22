import { useEffect, useState } from "react";

import { api } from "./api";
import { formatWhen, shortId } from "./display";
import { EmptyState } from "./EmptyState";
import { errorMessage } from "./errors";
import { HoverHelp } from "./HoverHelp";
import { Icon } from "./Icon";
import { knowledgeActorLabel, knowledgeKindLabel, knowledgeScopeLabel, redactionModeLabel } from "./labels";
import { Notice } from "./Notice";
import { StatusBadge } from "./StatusBadge";
import type {
  ContextCapture,
  KnowledgeActor,
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
  const [actor, setActor] = useState<KnowledgeActor>("human");
  const [content, setContent] = useState("");
  const [editContent, setEditContent] = useState("");
  const [captureText, setCaptureText] = useState("");
  const [redactionMode, setRedactionMode] = useState<RedactionMode>("redact_secrets");
  const [creating, setCreating] = useState(false);

  async function refresh(): Promise<void> {
    const [nextEntries, nextConfig] = await Promise.all([api.knowledgeEntries(), api.knowledgeConfig()]);
    setEntries(nextEntries);
    if (!config) setCreating(nextEntries.length === 0);
    setConfig(nextConfig);
    setRedactionMode(nextConfig.context_captures.redaction_mode);
    setSelected((current) => nextEntries.find((item) => item.id === current?.id) ?? nextEntries[0] ?? null);
    setLoadError("");
  }

  useEffect(() => {
    void refresh().catch((error: unknown) => {
      setLoadError(errorMessage(error));
    });
  }, []);

  useEffect(() => {
    if (!selected) {
      setVersions([]);
      return;
    }
    void api
      .knowledgeVersions(selected.id)
      .then(setVersions)
      .catch((error: unknown) => setMessage(errorMessage(error)));
    setEditContent(selected.content);
  }, [selected]);

  function fail(error: unknown): void {
    setMessage(errorMessage(error));
  }

  function entryTitle(entry: KnowledgeEntry): string {
    return entry.display_name?.trim() || `${knowledgeKindLabel(entry.kind)} ${shortId(entry.id)}`;
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
    <section className="surface">
      <header className="surface-head">
        <div className="entity-head"><h2>Knowledge</h2><HoverHelp title="About Knowledge">Save memories, skills and instructions here. Choose which entries each chat uses.</HoverHelp></div>
      </header>

      <details className="card" open={creating}>
        <summary onClick={event => { event.preventDefault(); setCreating(!creating); }} aria-expanded={creating}><Icon name="plus" size={15} /> New entry</summary>
      <form
        className="compact-form"
        onSubmit={(event) => {
          event.preventDefault();
          if (!content.trim()) {
            setMessage("Write some content before creating an entry.");
            return;
          }
          void api
            .createKnowledgeEntry({
              scope,
              kind,
              content,
              display_name: displayName.trim() || undefined,
              provenance: { actor, note: "desktop" },
            })
            .then(async (next) => {
              setMessage(`Created ${entryTitle(next)}.`);
              setContent("");
              await refresh();
              setSelected(next);
              setCreating(false);
            })
            .catch(fail);
        }}
      >
        <div className="setup-grid">
          <label>
            Kind
            <select value={kind} onChange={(event) => setKind(event.target.value as KnowledgeKind)}>
              <option value="memory">Memory</option>
              <option value="skill">Skill</option>
              <option value="protected_instruction">Protected instruction</option>
            </select>
          </label>
          <label>
            Scope
            <select value={scope} onChange={(event) => setScope(event.target.value as KnowledgeScope)}>
              <option value="user">User</option>
              <option value="agent">Agent</option>
              <option value="project">Project</option>
            </select>
          </label>
          <label>
            Recorded as
            <select value={actor} onChange={(event) => setActor(event.target.value as KnowledgeActor)}>
              <option value="human">You</option>
              <option value="api_maintainer">API maintainer</option>
              <option value="agent">Agent</option>
            </select>
          </label>
        </div>
        <label>
          Name (optional)
          <input value={displayName} onChange={(event) => setDisplayName(event.target.value)} />
        </label>
        <label>
          Content
          <textarea value={content} onChange={(event) => setContent(event.target.value)} />
        </label>
        <button type="submit"><Icon name="plus" size={14} /> Create</button>
      </form>
      </details>

      <div className="grid">
        <div className="card">
          <h3>Entries</h3>
          {entries.length === 0 ? (
            <EmptyState title="No entries yet">
              Add a memory, skill or instruction.
            </EmptyState>
          ) : (
            <ul className="nav-list">
              {entries.map((item) => (
                <li key={item.id}>
                  <button
                    type="button"
                    className={item.id === selected?.id ? "nav-item active" : "nav-item"}
                    onClick={() => setSelected(item)}
                  >
                    <span className="nav-item-title">{item.display_name ?? shortId(item.id)}</span>
                    <span className="nav-item-meta">
                      {knowledgeKindLabel(item.kind)} · {knowledgeScopeLabel(item.scope)}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div className="card">
          {selected ? (
            <>
              <div className="entity-head">
                <h3>{entryTitle(selected)}</h3>
                <StatusBadge label={knowledgeKindLabel(selected.kind)} />
                <StatusBadge label={knowledgeActorLabel(selected.provenance.actor)} />
              </div>
              <p className="hint">
                {knowledgeScopeLabel(selected.scope)} · updated {formatWhen(selected.updated_at)}
              </p>
              <details>
                <summary>Details</summary>
                <p className="hint">
                  Entry ID: {selected.id} · current version: {selected.current_version_id}
                </p>
              </details>
              <label>
                Content
                <textarea value={editContent} onChange={(event) => setEditContent(event.target.value)} />
              </label>
              <div className="actions">
                <button
                  type="button"
                  onClick={() => {
                    void api
                      .editKnowledgeEntry(selected.id, editContent, selected.current_version_id, actor)
                      .then(async (next) => {
                        setMessage("Saved a new version.");
                        await refresh();
                        setSelected(next);
                      })
                      .catch(fail);
                  }}
                >
                  <Icon name="check" size={14} /> Save
                </button>
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
                      <p className="hint">
                        {version.content.length > 160 ? `${version.content.slice(0, 159)}…` : version.content}
                      </p>
                      {version.id !== selected.current_version_id ? (
                        <button
                          type="button"
                          onClick={() => {
                            void api
                              .revertKnowledgeEntry(selected.id, version.id, selected.current_version_id, actor)
                              .then(async (next) => {
                                setMessage("Reverted; that created a new current version.");
                                await refresh();
                                setSelected(next);
                              })
                              .catch(fail);
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
