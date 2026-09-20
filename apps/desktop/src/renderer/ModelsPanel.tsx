import { useEffect, useState } from "react";

import { api } from "./api";
import { DeploymentsPanel } from "./DeploymentsPanel";
import { formatBytes } from "./display";
import { EmptyState } from "./EmptyState";
import { errorMessage } from "./errors";
import { Notice } from "./Notice";
import { SettingsNotes } from "./settingsNotes";
import { Choice, Help, numberChoices } from "./ModelControls";
import type { Deployment, InspectReport, ModelBundle, PathsInfo, RunProfile } from "./types";
import type { SchemaHubRepository } from "../generated/shared-contracts/openapi";

export function ModelsPanel() {
  const [view, setView] = useState<"library" | "add" | "presets">("library");
  const [localBusy, setLocalBusy] = useState(false);
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
  const [deployments, setDeployments] = useState<Deployment[]>([]);
  const [presetBusy, setPresetBusy] = useState(false);
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
      const [nextPaths, nextBundles, nextProfiles, nextDeployments] = await Promise.all([
        api.paths(),
        api.bundles(),
        api.profiles(),
        api.deployments(),
      ]);
      setPaths(nextPaths);
      setBundles(nextBundles);
      setSelectedId(current => nextBundles.some(bundle => bundle.id === current) ? current : nextBundles[0]?.id ?? "");
      setProfiles(nextProfiles);
      setDeployments(nextDeployments);
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
  const currentGeneration = deployments.find(deployment => deployment.bundle_id === selectedId && deployment.health?.healthy)?.server_props?.default_generation_settings?.params;
  const currentTemperature = typeof currentGeneration?.temperature === "number" ? currentGeneration.temperature : null;
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
    <section className="surface models-surface">
      <header className="models-heading">
        <div><p className="eyebrow">YOUR WORKSPACE</p><h2>Models</h2>
        <p className="lede">Find your model. Make it your own.</p></div>
        <button type="button" className="primary-button" onClick={() => setView(view === "add" ? "library" : "add")}>{view === "add" ? "Back to library" : "+ Add model"}</button>
      </header>
      <nav className="model-tabs" aria-label="Model sections">
        <button type="button" aria-current={view === "library" ? "page" : undefined} onClick={() => setView("library")}>My models <span>{bundles.length}</span></button>
        <button type="button" aria-current={view === "presets" ? "page" : undefined} onClick={() => { setView("presets"); void refresh().catch(fail); }}>Saved presets <span>{profiles.length}</span></button>
      </nav>
      {message ? <Notice tone={/fail|error|mismatch/i.test(message) ? "error" : "info"}>{message}</Notice> : null}
      {view === "add" ? <>
      <div className="grid">
        <form
          className="card"
          onSubmit={(event) => {
            event.preventDefault();
            setLocalBusy(true);
            void api
              .importLocal(localPath, localName || undefined)
              .then((job) => {
                if (job.bundle_id) setSelectedId(job.bundle_id);
                setMessage(
                  job.error
                    ? `Local import ${job.status}: ${job.error}`
                    : "Model added to your library.",
                );
                if (job.bundle_id) setView("library");
                return refresh();
              })
              .catch(fail).finally(() => setLocalBusy(false));
          }}
        >
          <h3>Add from your computer</h3>
          <p className="hint">Use a GGUF model you’ve already downloaded.</p>
          <label>
            Model file or folder
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
          <button type="submit" className="primary-button" disabled={!localPath.trim() || localBusy}>
            {localBusy ? "Adding model…" : "Add model"}
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
          <h3>Download from Hugging Face</h3>
          <p className="hint">Choose the version and size that suit your computer.</p>
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
            <p className="hint">Read the publisher’s <a href={`https://huggingface.co/${hub.repo_id}/blob/${hub.resolved_revision}/README.md`} target="_blank" rel="noreferrer">model guide</a> for recommended settings and supported features.</p>
            <details><summary>Files and recorded revision</summary>
              <p className="hint">{hub.resolved_revision}</p>
              <ul>{selectedHubFiles.map((file) => <li key={file}>{file}</li>)}</ul>
            </details>
            <button type="button" disabled={hubBusy || !selectedVariant || !projector} onClick={() => {
              setHubBusy(true);
              setHubMessage("Downloading selected files and checking the bundle. This can take several minutes. Retry an interrupted download to resume it.");
              const exactFiles = selectedHubFiles.map((file) => file.replaceAll("[", "[[]").replaceAll("?", "[?]").replaceAll("*", "[*]"));
              void api.importHf(hub.repo_id, hub.resolved_revision, exactFiles).then((job) => {
                setHubMessage(job.error ? `Import ${job.status}: ${job.error}` : "Model added to your library.");
                if (job.bundle_id) { setSelectedId(job.bundle_id); setView("library"); setMessage("Model added to your library."); }
                return refresh();
              }).catch((error: unknown) => setHubMessage(errorMessage(error))).finally(() => setHubBusy(false));
            }}>Download selected variant</button>
          </> : null}
          {hubMessage ? <p role="status">{hubMessage}</p> : null}
        </form>
      </div>
      </> : null}
      {view === "library" ? <div className="models-workspace">
      <aside className="model-library" aria-label="Your models">
        <div className="section-heading"><h3>Your library</h3><span className="hint">{bundles.length} models</span></div>
        {loading ? (
          <EmptyState title="Loading your models">
            Checking model files. This may take a moment.
          </EmptyState>
        ) : bundles.length === 0 ? (
          <EmptyState title="Your first model starts here">
            Add a model from your computer or download one from Hugging Face.
          </EmptyState>
        ) : (
          <ul className="model-list">
            {bundles.map((bundle) => (
              <li key={bundle.id}>
                <button
                  type="button"
                  className={bundle.id === selectedId ? "model-tile selected" : "model-tile"}
                  aria-pressed={bundle.id === selectedId}
                  onClick={() => {
                    setSelectedId(bundle.id);
                    setInspect(null);
                  }}
                >
                  <span className="nav-item-title">{bundle.display_name}</span>
                  <span className="nav-item-meta">
                    {bundle.quantization ?? "GGUF"} · {formatBytes(bundle.files.reduce((total, file) => total + file.size_bytes, 0))}
                    {!bundle.disk_matches ? " · Check files" : ""}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        )}
        {paths ? <details className="library-storage"><summary>Storage location</summary><code>{paths.models}</code></details> : null}
      </aside>
      <div className="model-detail">
      <DeploymentsPanel selectedBundleId={selectedId} bundlesVersion={bundles.map((bundle) => bundle.id).join(",")} />
      {selected ? (
          <details className="card technical-details"><summary>Model files &amp; technical details</summary>
            <p className="hint">Model ID: <code>{selected.id}</code></p>
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
              Read model metadata
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
          </details>
        ) : null}
      </div></div> : null}
      {view === "presets" ? <div className="presets-layout">
      <form
        className="card"
        onSubmit={(event) => {
          event.preventDefault();
          setPresetBusy(true);
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
              setMessage(`Saved preset ${profile.display_name}`);
              return refresh();
            })
            .catch(fail).finally(() => setPresetBusy(false));
        }}
      >
        <h3>Create a chat preset</h3>
        <p className="hint">Save your preferred response style and instructions for Chat.</p>
        <label>
          Name
          <input value={profileName} onChange={(event) => setProfileName(event.target.value)} />
        </label>
        <div className="setup-grid">
          <Choice id="preset-temperature" label="Creativity (temperature)" help="Lower values make replies more predictable; higher values encourage variety. A preset override is sent with each reply." flag="temperature" value={temperature} onChange={setTemperature} min={0} step={0.01} options={[{ value: "", label: currentTemperature !== null ? `${currentTemperature} · current model setting` : "Use model setting · not reported" }, ...numberChoices([0, 0.2, 0.4, 0.6, 0.8, 1, 1.2, 1.5, 2])]} />
          <Choice id="preset-max-tokens" label="Reply length (tokens)" help="Maximum length of each generated reply. The running model’s available context may impose a smaller limit." flag="max_tokens" value={maxTokens} onChange={setMaxTokens} min={1} options={[{ value: "", label: "No preset limit" }, ...numberChoices([512, 1024, 2048, 4096, 8192, 16384, 32768])]} />
        </div>
        <label>
          Instructions (optional)
          <textarea value={systemPrompt} onChange={(event) => setSystemPrompt(event.target.value)} />
        </label>
        <button type="submit" className="primary-button" disabled={presetBusy}>{presetBusy ? "Saving…" : "Save preset"}</button>
      </form>

      <div className="card">
        <h3>Saved presets</h3>
        <p className="hint">Select a preset in Chat to use it.</p>
        {profiles.length === 0 ? (
          <EmptyState title="Make yourself at home">Save a preset for the way you like to work.</EmptyState>
        ) : (
          <ul className="list">
            {profiles.map((profile) => (
              <li key={profile.id} className="entity">
                <div className="entity-head">
                  <strong>{profile.display_name}</strong>
                  <Help label={`${profile.display_name} identifier`}>Preset ID: <code>{profile.id}</code></Help>
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

      </div> : null}
    </section>
  );
}
