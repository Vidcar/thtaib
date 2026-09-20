import { useEffect, useState } from "react";

import { api } from "./api";
import { DeploymentsPanel } from "./DeploymentsPanel";
import { formatBytes } from "./display";
import { EmptyState } from "./EmptyState";
import { errorMessage } from "./errors";
import { Notice } from "./Notice";
import { SettingsNotes } from "./settingsNotes";
import { StatusBadge } from "./StatusBadge";
import type { InspectReport, ModelBundle, PathsInfo, RunProfile } from "./types";

export function ModelsPanel() {
  const [paths, setPaths] = useState<PathsInfo | null>(null);
  const [bundles, setBundles] = useState<ModelBundle[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [inspect, setInspect] = useState<InspectReport | null>(null);
  const [localPath, setLocalPath] = useState("");
  const [localName, setLocalName] = useState("");
  const [repoId, setRepoId] = useState("");
  const [revision, setRevision] = useState("");
  const [profiles, setProfiles] = useState<RunProfile[]>([]);
  const [profileName, setProfileName] = useState("Default chat");
  const [temperature, setTemperature] = useState("0.7");
  const [maxTokens, setMaxTokens] = useState("");
  const [systemPrompt, setSystemPrompt] = useState("");
  const [message, setMessage] = useState("");
  const [loadError, setLoadError] = useState("");

  async function refresh(): Promise<void> {
    const [nextPaths, nextBundles, nextProfiles] = await Promise.all([
      api.paths(),
      api.bundles(),
      api.profiles(),
    ]);
    setPaths(nextPaths);
    setBundles(nextBundles);
    setProfiles(nextProfiles);
    setLoadError("");
  }

  useEffect(() => {
    void refresh().catch((error: unknown) => {
      setLoadError(errorMessage(error));
    });
  }, []);

  const selected = bundles.find((bundle) => bundle.id === selectedId) ?? null;

  function fail(error: unknown): void {
    setMessage(errorMessage(error));
  }

  if (loadError) {
    return (
      <section className="surface">
        <h2>Models</h2>
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
        <h2>Models</h2>
        <p className="lede">
          Bundles, profiles and deployments. Chat uses a running deployment, not a file on disk.
        </p>
        {paths ? (
          <p className="hint">
            Files live in <code>{paths.models}</code>
          </p>
        ) : null}
      </header>

      <div className="grid">
        <form
          className="card"
          onSubmit={(event) => {
            event.preventDefault();
            void api
              .importLocal(localPath, localName || undefined)
              .then((job) => {
                setMessage(
                  job.error
                    ? `Local import ${job.status}: ${job.error}`
                    : `Local import ${job.status}${job.bundle_id ? ` · ${job.bundle_id}` : ""}`,
                );
                return refresh();
              })
              .catch(fail);
          }}
        >
          <h3>Import local GGUF</h3>
          <label>
            Path
            <input
              value={localPath}
              onChange={(event) => setLocalPath(event.target.value)}
              placeholder="C:\Users\…\Qwen3.8-27B-UD-IQ4_XS.gguf"
            />
          </label>
          <label>
            Display name (optional)
            <input value={localName} onChange={(event) => setLocalName(event.target.value)} />
          </label>
          <button type="submit" disabled={!localPath.trim()}>
            Import
          </button>
        </form>

        <form
          className="card"
          onSubmit={(event) => {
            event.preventDefault();
            void api
              .importHf(repoId, revision)
              .then((job) => {
                setMessage(
                  job.error
                    ? `Hugging Face import ${job.status}: ${job.error}`
                    : `Hugging Face import ${job.status}`,
                );
                return refresh();
              })
              .catch(fail);
          }}
        >
          <h3>Import from Hugging Face</h3>
          <label>
            Repository
            <input
              value={repoId}
              onChange={(event) => setRepoId(event.target.value)}
              placeholder="unsloth/Qwen3.8-27B-GGUF"
            />
          </label>
          <label>
            Pinned revision
            <input
              value={revision}
              onChange={(event) => setRevision(event.target.value)}
              placeholder="commit SHA or tag"
            />
          </label>
          <button type="submit" disabled={!repoId.trim() || !revision.trim()}>
            Import pinned revision
          </button>
        </form>
      </div>

      <div className="card">
        <h3>Bundles</h3>
        {bundles.length === 0 ? (
          <EmptyState title="No bundles">
            Import a local GGUF or a pinned Hugging Face revision. The product will not invent a
            bundle from a file that merely exists under models.
          </EmptyState>
        ) : (
          <ul className="list">
            {bundles.map((bundle) => (
              <li key={bundle.id}>
                <button
                  type="button"
                  className={bundle.id === selectedId ? "nav-item active" : "nav-item"}
                  onClick={() => {
                    setSelectedId(bundle.id);
                    setInspect(null);
                  }}
                >
                  <span className="nav-item-title">{bundle.display_name}</span>
                  <span className="nav-item-meta">
                    {bundle.quantization ?? "quant unknown"} ·{" "}
                    {bundle.disk_matches ? "files match" : "disk mismatch"}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        )}
        {selected ? (
          <div className="entity">
            <p>
              {selected.files.length} files
              {selected.companions.length ? ` · ${selected.companions.length} companions` : ""}
              {selected.primary_path ? (
                <>
                  {" "}
                  · <code>{selected.primary_path}</code>
                </>
              ) : null}
            </p>
            {selected.source.kind === "huggingface" ? (
              <p className="hint">
                {selected.source.repo_id} @ {selected.source.resolved_revision ?? selected.source.requested_revision}
              </p>
            ) : (
              <p className="hint">{selected.source.original_path}</p>
            )}
            {!selected.disk_matches ? (
              <Notice tone="warn">Recorded files do not match what is on disk.</Notice>
            ) : null}
            <ul className="plain-list">
              {selected.files.map((file) => (
                <li key={file.path}>
                  {file.role} · {file.name} · {formatBytes(file.size_bytes)}
                </li>
              ))}
            </ul>
            <button
              type="button"
              onClick={() => {
                void api.inspect(selected.id).then(setInspect).catch(fail);
              }}
            >
              Inspect GGUF (read-only)
            </button>
            {inspect && inspect.bundle_id === selected.id ? (
              <dl className="meta compact">
                <div>
                  <dt>Architecture</dt>
                  <dd>{inspect.architecture ?? "unknown"}</dd>
                </div>
                <div>
                  <dt>Name</dt>
                  <dd>{inspect.name ?? "unnamed"}</dd>
                </div>
                <div>
                  <dt>Tensors</dt>
                  <dd>{inspect.tensors.length}</dd>
                </div>
                <div>
                  <dt>Reader</dt>
                  <dd>
                    {inspect.reader_mode} · metadata edited {String(inspect.metadata_edited)}
                  </dd>
                </div>
              </dl>
            ) : null}
          </div>
        ) : null}
      </div>

      <form
        className="card"
        onSubmit={(event) => {
          event.preventDefault();
          const perRequest: Record<string, unknown> = {
            temperature: Number(temperature) || 0.7,
          };
          if (maxTokens.trim()) {
            perRequest.max_tokens = Number(maxTokens);
          }
          void api
            .createProfile({
              display_name: profileName.trim() || "Untitled profile",
              bundle_id: selectedId || undefined,
              startup: { ctx_size: 65536, n_gpu_layers: -1, flash_attn: "on" },
              per_request: perRequest,
              agent: systemPrompt.trim() ? { system_prompt: systemPrompt } : {},
            })
            .then((profile) => {
              setMessage(`Saved profile ${profile.display_name}`);
              return refresh();
            })
            .catch(fail);
        }}
      >
        <h3>New profile</h3>
        <p className="hint">
          Profiles store requested settings. Starting a deployment is what actually loads the model.
        </p>
        <label>
          Name
          <input value={profileName} onChange={(event) => setProfileName(event.target.value)} />
        </label>
        <div className="setup-grid">
          <label>
            Temperature
            <input value={temperature} onChange={(event) => setTemperature(event.target.value)} />
          </label>
          <label>
            Max tokens (optional)
            <input value={maxTokens} onChange={(event) => setMaxTokens(event.target.value)} />
          </label>
        </div>
        <label>
          System prompt (optional)
          <textarea value={systemPrompt} onChange={(event) => setSystemPrompt(event.target.value)} />
        </label>
        <button type="submit">Save profile</button>
      </form>

      <div className="card">
        <h3>Saved profiles</h3>
        {profiles.length === 0 ? (
          <EmptyState title="No profiles">Save one above, or Chat can run without a profile.</EmptyState>
        ) : (
          <ul className="list">
            {profiles.map((profile) => (
              <li key={profile.id} className="entity">
                <div className="entity-head">
                  <strong>{profile.display_name}</strong>
                  <StatusBadge label={profile.id} />
                </div>
                <SettingsNotes
                  unsupported={profile.bags.startup.unsupported}
                  retired={profile.bags.startup.retired}
                />
              </li>
            ))}
          </ul>
        )}
      </div>

      <DeploymentsPanel />
      {message ? (
        <Notice tone={/fail|error|mismatch/i.test(message) ? "error" : "info"}>{message}</Notice>
      ) : null}
    </section>
  );
}
