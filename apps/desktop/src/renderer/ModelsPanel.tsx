import { useEffect, useState } from "react";

import { api } from "./api";
import type { InspectReport, ModelBundle, PathsInfo, SettingsBags } from "./types";

function parseJsonObject(raw: string, fallback: object): object {
  try {
    const value = JSON.parse(raw) as unknown;
    return value && typeof value === "object" && !Array.isArray(value) ? value : fallback;
  } catch {
    return fallback;
  }
}

export function ModelsPanel() {
  const [paths, setPaths] = useState<PathsInfo | null>(null);
  const [bundles, setBundles] = useState<ModelBundle[]>([]);
  const [selectedId, setSelectedId] = useState<string>("");
  const [inspect, setInspect] = useState<InspectReport | null>(null);
  const [localPath, setLocalPath] = useState("");
  const [repoId, setRepoId] = useState("");
  const [revision, setRevision] = useState("");
  const [startupRaw, setStartupRaw] = useState(
    '{"ctx_size": 65536, "n_gpu_layers": -1, "flash_attn": "on"}',
  );
  const [requestRaw, setRequestRaw] = useState('{"temperature": 0.7}');
  const [agentRaw, setAgentRaw] = useState('{"tools_enabled": false}');
  const [preview, setPreview] = useState<SettingsBags | null>(null);
  const [message, setMessage] = useState<string>("");

  async function refresh(): Promise<void> {
    const [nextPaths, nextBundles] = await Promise.all([api.paths(), api.bundles()]);
    setPaths(nextPaths);
    setBundles(nextBundles);
  }

  useEffect(() => {
    void refresh().catch((error: unknown) => {
      setMessage(error instanceof Error ? error.message : String(error));
    });
  }, []);

  const selected = bundles.find((bundle) => bundle.id === selectedId) ?? null;

  return (
    <section className="panel">
      <h2>Models</h2>
      <p className="hint">
        Backend-owned bundles. Files live under the managed <code>models</code> directory.
      </p>
      {paths ? (
        <dl className="meta compact">
          <div>
            <dt>models</dt>
            <dd>{paths.models}</dd>
          </div>
          <div>
            <dt>Windows layout</dt>
            <dd>{paths.windows_layout}</dd>
          </div>
        </dl>
      ) : null}

      <div className="grid">
        <form
          className="card"
          onSubmit={(event) => {
            event.preventDefault();
            void api
              .importLocal(localPath)
              .then((job) => {
                setMessage(`Local import ${job.status}${job.error ? `: ${job.error}` : ""}`);
                return refresh();
              })
              .catch((error: unknown) => setMessage(error instanceof Error ? error.message : String(error)));
          }}
        >
          <h3>Import local</h3>
          <label>
            Path
            <input value={localPath} onChange={(event) => setLocalPath(event.target.value)} />
          </label>
          <button type="submit">Import</button>
        </form>

        <form
          className="card"
          onSubmit={(event) => {
            event.preventDefault();
            void api
              .importHf(repoId, revision)
              .then((job) => {
                setMessage(`HF import ${job.status}${job.error ? `: ${job.error}` : ""}`);
                return refresh();
              })
              .catch((error: unknown) => setMessage(error instanceof Error ? error.message : String(error)));
          }}
        >
          <h3>Import Hugging Face</h3>
          <label>
            repo_id
            <input value={repoId} onChange={(event) => setRepoId(event.target.value)} />
          </label>
          <label>
            revision
            <input
              value={revision}
              onChange={(event) => setRevision(event.target.value)}
              placeholder="commit SHA or tag"
            />
          </label>
          <button type="submit">Import pinned revision</button>
        </form>
      </div>

      <div className="card">
        <h3>Bundles</h3>
        {bundles.length === 0 ? <p className="hint">No bundles yet.</p> : null}
        <ul className="list">
          {bundles.map((bundle) => (
            <li key={bundle.id}>
              <button type="button" className="linkish" onClick={() => setSelectedId(bundle.id)}>
                {bundle.display_name} · {bundle.quantization ?? "quant unknown"} ·{" "}
                {bundle.disk_matches ? "disk matches" : "disk mismatch"}
              </button>
            </li>
          ))}
        </ul>
        {selected ? (
          <pre className="json">{JSON.stringify(selected, null, 2)}</pre>
        ) : null}
        <button
          type="button"
          disabled={!selected}
          onClick={() => {
            if (!selected) return;
            void api
              .inspect(selected.id)
              .then(setInspect)
              .catch((error: unknown) => setMessage(error instanceof Error ? error.message : String(error)));
          }}
        >
          Inspect GGUF (read-only)
        </button>
        {inspect ? (
          <div>
            <p className="hint">
              reader={inspect.reader_mode} · metadata_edited={String(inspect.metadata_edited)} ·{" "}
              {inspect.architecture} / {inspect.name}
            </p>
            <pre className="json">{JSON.stringify(inspect, null, 2)}</pre>
          </div>
        ) : null}
      </div>

      <form
        className="card"
        onSubmit={(event) => {
          event.preventDefault();
          void api
            .previewSettings(
              parseJsonObject(startupRaw, {}),
              parseJsonObject(requestRaw, {}),
              parseJsonObject(agentRaw, {}),
            )
            .then(setPreview)
            .catch((error: unknown) => setMessage(error instanceof Error ? error.message : String(error)));
        }}
      >
        <h3>Settings bags</h3>
        <p className="hint">Startup, per-request and agent bags stay separate. Applied and unsupported are shown.</p>
        <label>
          Startup JSON
          <textarea value={startupRaw} onChange={(event) => setStartupRaw(event.target.value)} />
        </label>
        <label>
          Per-request JSON
          <textarea value={requestRaw} onChange={(event) => setRequestRaw(event.target.value)} />
        </label>
        <label>
          Agent JSON
          <textarea value={agentRaw} onChange={(event) => setAgentRaw(event.target.value)} />
        </label>
        <button type="submit">Resolve requested vs applied</button>
        {preview ? (
          <dl className="meta">
            <div>
              <dt>Startup applied</dt>
              <dd>{JSON.stringify(preview.startup.applied)}</dd>
            </div>
            <div>
              <dt>Startup unsupported</dt>
              <dd>{preview.startup.unsupported.join(", ") || "none"}</dd>
            </div>
            <div>
              <dt>Per-request applied</dt>
              <dd>{JSON.stringify(preview.per_request.applied)}</dd>
            </div>
            <div>
              <dt>Per-request unsupported</dt>
              <dd>{preview.per_request.unsupported.join(", ") || "none"}</dd>
            </div>
            <div>
              <dt>Agent applied</dt>
              <dd>{JSON.stringify(preview.agent.applied)}</dd>
            </div>
            <div>
              <dt>Agent unsupported</dt>
              <dd>{preview.agent.unsupported.join(", ") || "none"}</dd>
            </div>
          </dl>
        ) : null}
      </form>
      {message ? <p className="status">{message}</p> : null}
    </section>
  );
}
