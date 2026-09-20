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
import type { SchemaHubRepository } from "../generated/shared-contracts/openapi";

export function ModelsPanel() {
  const [paths, setPaths] = useState<PathsInfo | null>(null);
  const [bundles, setBundles] = useState<ModelBundle[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [inspect, setInspect] = useState<InspectReport | null>(null);
  const [localPath, setLocalPath] = useState("");
  const [localName, setLocalName] = useState("");
  const [repoId, setRepoId] = useState("");
  const [hub, setHub] = useState<SchemaHubRepository | null>(null);
  const [variant, setVariant] = useState("");
  const [projector, setProjector] = useState("");
  const [hubBusy, setHubBusy] = useState(false);
  const [hubMessage, setHubMessage] = useState("");
  const [profiles, setProfiles] = useState<RunProfile[]>([]);
  const [profileName, setProfileName] = useState("Default chat");
  const [temperature, setTemperature] = useState("");
  const [maxTokens, setMaxTokens] = useState("");
  const [systemPrompt, setSystemPrompt] = useState("");
  const [message, setMessage] = useState("");
  const [loadError, setLoadError] = useState("");
  const [loading, setLoading] = useState(true);

  async function refresh(): Promise<void> {
    setLoading(true);
    try {
      const [nextPaths, nextBundles, nextProfiles] = await Promise.all([
        api.paths(),
        api.bundles(),
        api.profiles(),
      ]);
      setPaths(nextPaths);
      setBundles(nextBundles);
      setProfiles(nextProfiles);
      setLoadError("");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void refresh().catch((error: unknown) => {
      setLoadError(errorMessage(error));
    });
  }, []);

  const selected = bundles.find((bundle) => bundle.id === selectedId) ?? null;
  const selectedVariant = hub?.variants.find((item) => item.name === variant);
  const selectedProjector = hub?.projectors.find((item) => item.name === projector);
  const selectedHubFiles = [...(selectedVariant?.files ?? []), ...(selectedProjector?.files ?? []), ...(hub?.guidance_files ?? [])];

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
                if (job.bundle_id) setSelectedId(job.bundle_id);
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
            setHubBusy(true);
            setHubMessage("Reading available model files…");
            setHub(null);
            void api.inspectHf(repoId).then((result) => {
              setHub(result);
              setVariant(result.variants.length === 1 && result.variants[0].complete ? result.variants[0].name : "");
              setProjector(result.projectors.length ? "" : "text-only");
              setHubMessage("");
            }).catch((error: unknown) => setHubMessage(errorMessage(error))).finally(() => setHubBusy(false));
          }}
        >
          <h3>Import from Hugging Face</h3>
          <label>
            Hugging Face link or repository
            <input
              value={repoId}
              onChange={(event) => { setRepoId(event.target.value); setHub(null); }}
              disabled={hubBusy}
              placeholder="unsloth/Qwen3.8-27B-GGUF"
            />
          </label>
          <button type="submit" disabled={!repoId.trim() || hubBusy}>
            Find model files
          </button>
          {hub ? <>
            <label>Model variant
              <select value={variant} disabled={hubBusy} onChange={(event) => setVariant(event.target.value)}>
                <option value="">Choose a GGUF variant</option>
                {hub.variants.map((item) => <option key={item.name} value={item.name} disabled={!item.complete}>
                  {item.name} · {item.size_bytes == null ? "size unknown" : formatBytes(item.size_bytes)}{item.complete ? "" : " · missing shards"}
                </option>)}
              </select>
            </label>
            {hub.projectors.length ? <label>Vision companion
              <select value={projector} disabled={hubBusy} onChange={(event) => setProjector(event.target.value)}>
                <option value="">Choose a projector or text-only</option>
                <option value="text-only">Text-only — no projector</option>
                {hub.projectors.map((item) => <option key={item.name} value={item.name}>{item.name}</option>)}
              </select>
            </label> : null}
            {hub.warnings.map((warning) => <p className="hint" key={warning}>{warning}</p>)}
            <p className="hint">Publisher guidance: <a href={`https://huggingface.co/${hub.repo_id}/blob/${hub.resolved_revision}/README.md`} target="_blank" rel="noreferrer">model card</a>. Downloading does not establish tool or vision capability.</p>
            <details><summary>Files and recorded revision</summary>
              <p className="hint">{hub.resolved_revision}</p>
              <ul>{selectedHubFiles.map((file) => <li key={file}>{file}</li>)}</ul>
            </details>
            <button type="button" disabled={hubBusy || !selectedVariant || !projector} onClick={() => {
              setHubBusy(true);
              setHubMessage("Downloading selected files and checking the bundle. This can take several minutes. Retry an interrupted download to resume it.");
              const exactFiles = selectedHubFiles.map((file) => file.replaceAll("[", "[[]").replaceAll("?", "[?]").replaceAll("*", "[*]"));
              void api.importHf(hub.repo_id, hub.resolved_revision, exactFiles).then((job) => {
                setHubMessage(job.error ? `Import ${job.status}: ${job.error}` : "Model imported. Start it below, then open Chat.");
                if (job.bundle_id) setSelectedId(job.bundle_id);
                return refresh();
              }).catch((error: unknown) => setHubMessage(errorMessage(error))).finally(() => setHubBusy(false));
            }}>Download selected variant</button>
          </> : null}
          {hubMessage ? <p role="status">{hubMessage}</p> : null}
        </form>
      </div>

      <div className="card">
        <h3>Bundles</h3>
        {loading ? (
          <EmptyState title="Loading bundles">
            Reading the model catalogue and checking recorded files. Large local models can take a
            moment on first load.
          </EmptyState>
        ) : bundles.length === 0 ? (
          <EmptyState title="No bundles">
            Import a local GGUF or choose a Hugging Face model variant. The product will not invent a
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
          const perRequest: Record<string, unknown> = {};
          if (temperature.trim()) perRequest.temperature = Number(temperature);
          if (maxTokens.trim()) {
            perRequest.max_tokens = Number(maxTokens);
          }
          void api
            .createProfile({
              display_name: profileName.trim() || "Untitled profile",
              bundle_id: selectedId || undefined,
              startup: {},
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
            Temperature (optional override)
            <input type="number" min="0" step="0.01" placeholder="Runtime default" value={temperature} onChange={(event) => setTemperature(event.target.value)} />
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

      <DeploymentsPanel selectedBundleId={selectedId} bundlesVersion={bundles.map((bundle) => bundle.id).join(",")} />
      {message ? (
        <Notice tone={/fail|error|mismatch/i.test(message) ? "error" : "info"}>{message}</Notice>
      ) : null}
    </section>
  );
}
