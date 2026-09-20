import { useEffect, useState } from "react";

import { api } from "./api";
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

function actorLabel(actor: KnowledgeActor): string {
  switch (actor) {
    case "human":
      return "human";
    case "api_maintainer":
      return "API maintainer";
    case "agent":
      return "agent";
    default: {
      const unexpected: never = actor;
      return unexpected;
    }
  }
}

export function KnowledgePanel() {
  const [entries, setEntries] = useState<KnowledgeEntry[]>([]);
  const [selected, setSelected] = useState<KnowledgeEntry | null>(null);
  const [versions, setVersions] = useState<KnowledgeVersion[]>([]);
  const [config, setConfig] = useState<KnowledgeConfig | null>(null);
  const [capture, setCapture] = useState<ContextCapture | null>(null);
  const [message, setMessage] = useState("");
  const [scope, setScope] = useState<KnowledgeScope>("user");
  const [kind, setKind] = useState<KnowledgeKind>("memory");
  const [actor, setActor] = useState<KnowledgeActor>("human");
  const [content, setContent] = useState("durable note");
  const [editContent, setEditContent] = useState("");
  const [captureText, setCaptureText] = useState("API_KEY=super-secret demo");
  const [redactionMode, setRedactionMode] = useState<RedactionMode>("redact_secrets");

  async function refresh(): Promise<void> {
    const [nextEntries, nextConfig] = await Promise.all([api.knowledgeEntries(), api.knowledgeConfig()]);
    setEntries(nextEntries);
    setConfig(nextConfig);
    setRedactionMode(nextConfig.context_captures.redaction_mode);
    setSelected((current) => nextEntries.find((item) => item.id === current?.id) ?? nextEntries[0] ?? null);
  }

  useEffect(() => {
    void refresh().catch((error: unknown) => {
      setMessage(error instanceof Error ? error.message : String(error));
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
      .catch((error: unknown) => setMessage(error instanceof Error ? error.message : String(error)));
    setEditContent(selected.content);
  }, [selected]);

  function fail(error: unknown): void {
    setMessage(error instanceof Error ? error.message : String(error));
  }

  return (
    <section className="panel">
      <h2>Knowledge</h2>
      <p className="hint">
        Thin debug panel for durable knowledge versioning (STATE-005). Application-owned
        store under LocalAppData knowledge. Not Chat, not Builder, and not RAG.
      </p>

      <form
        className="card"
        onSubmit={(event) => {
          event.preventDefault();
          void api
            .createKnowledgeEntry({
              scope,
              kind,
              content,
              provenance: { actor, note: "debug-panel" },
            })
            .then(async (next) => {
              setMessage(`Created ${next.id} · ${next.current_version_id}`);
              await refresh();
              setSelected(next);
            })
            .catch(fail);
        }}
      >
        <h3>Create entry</h3>
        <label>
          Scope
          <select value={scope} onChange={(event) => setScope(event.target.value as KnowledgeScope)}>
            <option value="user">user</option>
            <option value="agent">agent</option>
            <option value="project">project</option>
          </select>
        </label>
        <label>
          Kind
          <select value={kind} onChange={(event) => setKind(event.target.value as KnowledgeKind)}>
            <option value="memory">memory</option>
            <option value="skill">skill</option>
            <option value="protected_instruction">protected_instruction</option>
          </select>
        </label>
        <label>
          Actor
          <select value={actor} onChange={(event) => setActor(event.target.value as KnowledgeActor)}>
            <option value="human">human</option>
            <option value="api_maintainer">api_maintainer</option>
            <option value="agent">agent</option>
          </select>
        </label>
        <label>
          Content
          <textarea value={content} onChange={(event) => setContent(event.target.value)} />
        </label>
        <button type="submit">Create</button>
      </form>

      <div className="card">
        <h3>Entries</h3>
        {entries.length === 0 ? <p className="hint">No durable entries yet.</p> : null}
        <ul className="list">
          {entries.map((item) => (
            <li key={item.id}>
              <button
                type="button"
                className="linkish"
                onClick={() => {
                  setSelected(item);
                }}
              >
                {item.kind} · {item.scope} · {item.current_version_id}
              </button>
            </li>
          ))}
        </ul>
        {selected ? (
          <>
            <p>
              {selected.id}
              <span className="badge">{selected.kind}</span>
              <span className="badge">{actorLabel(selected.provenance.actor)}</span>
            </p>
            <label>
              Edit content
              <textarea value={editContent} onChange={(event) => setEditContent(event.target.value)} />
            </label>
            <div className="actions">
              <button
                type="button"
                onClick={() => {
                  void api
                    .editKnowledgeEntry(selected.id, editContent, selected.current_version_id, actor)
                    .then(async (next) => {
                      setMessage(`Edited ${next.current_version_id}`);
                      await refresh();
                      setSelected(next);
                    })
                    .catch(fail);
                }}
              >
                Edit (optimistic)
              </button>
              <button
                type="button"
                disabled={versions.length < 2}
                onClick={() => {
                  const prior = versions[0];
                  if (!prior) {
                    return;
                  }
                  void api
                    .revertKnowledgeEntry(selected.id, prior.id, selected.current_version_id, actor)
                    .then(async (next) => {
                      setMessage(`Reverted from ${prior.id} → ${next.current_version_id}`);
                      await refresh();
                      setSelected(next);
                    })
                    .catch(fail);
                }}
              >
                Revert to first version
              </button>
            </div>
            <h3>History</h3>
            <pre className="json">{JSON.stringify(versions, null, 2)}</pre>
          </>
        ) : null}
      </div>

      <div className="card">
        <h3>Context capture</h3>
        <p className="hint">Default is retain with secrets redacted. This store is not the retrieval index.</p>
        <label>
          Redaction mode
          <select
            value={redactionMode}
            onChange={(event) => setRedactionMode(event.target.value as RedactionMode)}
          >
            <option value="redact_secrets">redact_secrets</option>
            <option value="retain">retain</option>
            <option value="discard">discard</option>
          </select>
        </label>
        <label>
          Capture text
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
                  setMessage(`Redaction mode ${next.context_captures.redaction_mode}`);
                })
                .catch(fail);
            }}
          >
            Save capture config
          </button>
          <button
            type="button"
            onClick={() => {
              void api
                .createContextCapture(captureText)
                .then((next) => {
                  setCapture(next);
                  setMessage(`Capture ${next.id} redacted=${String(next.redacted)}`);
                })
                .catch(fail);
            }}
          >
            Capture
          </button>
        </div>
        {config ? <pre className="json">{JSON.stringify(config, null, 2)}</pre> : null}
        {capture ? <pre className="json">{JSON.stringify(capture, null, 2)}</pre> : null}
      </div>

      {message ? <p className="status">{message}</p> : null}
    </section>
  );
}
