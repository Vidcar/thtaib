import { useEffect, useState } from "react";

import { api } from "./api";
import type { Deployment, ModelBundle, RuntimeManifest } from "./types";

export function DeploymentsPanel() {
  const [runtime, setRuntime] = useState<RuntimeManifest | null>(null);
  const [bundles, setBundles] = useState<ModelBundle[]>([]);
  const [deployments, setDeployments] = useState<Deployment[]>([]);
  const [bundleId, setBundleId] = useState("");
  const [endpoint, setEndpoint] = useState("http://127.0.0.1:8080/v1");
  const [message, setMessage] = useState("");

  async function refresh(): Promise<void> {
    const [nextRuntime, nextBundles, nextDeployments] = await Promise.all([
      api.runtime(),
      api.bundles(),
      api.deployments(),
    ]);
    setRuntime(nextRuntime);
    setBundles(nextBundles);
    setDeployments(nextDeployments);
    setBundleId((current) => current || nextBundles[0]?.id || "");
  }

  useEffect(() => {
    void refresh().catch((error: unknown) => {
      setMessage(error instanceof Error ? error.message : String(error));
    });
  }, []);

  return (
    <section className="panel">
      <h2>Deployments</h2>
      <p className="hint">
        Managed llama-server is started and stopped by the backend. Connected endpoints are attach-only.
        PATH llama-server is unsupported.
      </p>

      <div className="card">
        <h3>Managed runtime</h3>
        {runtime ? (
          <p>
            {runtime.status} · {runtime.platform} · {runtime.release_tag} · path fallback{" "}
            {runtime.path_fallback}
          </p>
        ) : (
          <p className="hint">No runtime pinned yet.</p>
        )}
        <button
          type="button"
          onClick={() => {
            void api
              .pinRuntime()
              .then((manifest) => {
                setRuntime(manifest);
                setMessage(`Runtime pin ${manifest.status}`);
              })
              .catch((error: unknown) => setMessage(error instanceof Error ? error.message : String(error)));
          }}
        >
          Pin Windows llama-server
        </button>
      </div>

      <div className="grid">
        <form
          className="card"
          onSubmit={(event) => {
            event.preventDefault();
            void api
              .startManaged(bundleId)
              .then((deployment) => {
                setMessage(`Managed ${deployment.status} ${deployment.endpoint ?? ""}`);
                return refresh();
              })
              .catch((error: unknown) => setMessage(error instanceof Error ? error.message : String(error)));
          }}
        >
          <h3>Start managed</h3>
          <label>
            Bundle
            <select value={bundleId} onChange={(event) => setBundleId(event.target.value)}>
              {bundles.map((bundle) => (
                <option key={bundle.id} value={bundle.id}>
                  {bundle.display_name}
                </option>
              ))}
            </select>
          </label>
          <button type="submit" disabled={!bundleId}>
            Start
          </button>
        </form>

        <form
          className="card"
          onSubmit={(event) => {
            event.preventDefault();
            void api
              .attachConnected(endpoint)
              .then((deployment) => {
                setMessage(`Connected ${deployment.scope} ${deployment.status}`);
                return refresh();
              })
              .catch((error: unknown) => setMessage(error instanceof Error ? error.message : String(error)));
          }}
        >
          <h3>Attach connected</h3>
          <label>
            OpenAI-compatible endpoint
            <input value={endpoint} onChange={(event) => setEndpoint(event.target.value)} />
          </label>
          <button type="submit">Attach (no kill)</button>
        </form>
      </div>

      <div className="card">
        <h3>Running and attached</h3>
        {deployments.length === 0 ? <p className="hint">No deployments.</p> : null}
        <ul className="list">
          {deployments.map((deployment) => (
            <li key={deployment.id} className="deployment">
              <strong>{deployment.display_name}</strong>
              <span className={`badge scope-${deployment.scope}`}>{deployment.scope}</span>
              <span className="badge">{deployment.status}</span>
              <p>endpoint: {deployment.endpoint ?? "none"}</p>
              <p>applied startup: {JSON.stringify(deployment.applied_startup)}</p>
              <p>
                health: {deployment.health ? String(deployment.health.healthy) : "n/a"} · resources:{" "}
                {deployment.resource_usage?.available
                  ? `${deployment.resource_usage.cpu_percent ?? "?"} cpu / ${deployment.resource_usage.rss_bytes ?? "?"} rss`
                  : deployment.resource_usage?.reason ?? "n/a"}
              </p>
              {deployment.scope === "managed" ? (
                <div className="actions">
                  <button
                    type="button"
                    onClick={() => {
                      void api.healthOf(deployment.id).then(() => refresh());
                    }}
                  >
                    Refresh health
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      void api
                        .stop(deployment.id)
                        .then(() => refresh())
                        .catch((error: unknown) =>
                          setMessage(error instanceof Error ? error.message : String(error)),
                        );
                    }}
                  >
                    Stop
                  </button>
                </div>
              ) : (
                <div className="actions">
                  <button
                    type="button"
                    onClick={() => {
                      void api
                        .detach(deployment.id)
                        .then(() => refresh())
                        .catch((error: unknown) =>
                          setMessage(error instanceof Error ? error.message : String(error)),
                        );
                    }}
                  >
                    Detach
                  </button>
                  <span className="hint">No stop/kill of the external process.</span>
                </div>
              )}
            </li>
          ))}
        </ul>
      </div>
      {message ? <p className="status">{message}</p> : null}
    </section>
  );
}
