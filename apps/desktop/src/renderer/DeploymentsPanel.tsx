import { useEffect, useState } from "react";

import { api, DEFAULT_EMBEDDING_STARTUP, DEFAULT_GPU_STARTUP } from "./api";
import { formatBytes } from "./display";
import { EmptyState } from "./EmptyState";
import { errorMessage } from "./errors";
import { deploymentHealthLabel } from "./labels";
import { Notice } from "./Notice";
import { SettingsNotes } from "./settingsNotes";
import { StatusBadge } from "./StatusBadge";
import type { Deployment, ModelBundle, RuntimeManifest } from "./types";

function resourceLabel(deployment: Deployment): string {
  const usage = deployment.resource_usage;
  if (!usage) {
    return "Resources unknown";
  }
  if (!usage.available) {
    return usage.reason ?? "Resources unavailable";
  }
  const cpu = usage.cpu_percent == null ? "?" : `${usage.cpu_percent.toFixed(0)}% CPU`;
  const rss = formatBytes(usage.rss_bytes);
  return `${cpu} · ${rss}`;
}

function propsSummary(deployment: Deployment): string | null {
  const props = deployment.server_props;
  if (!props) {
    return null;
  }
  const parts = [
    props.model_alias,
    props.n_ctx != null ? `context ${props.n_ctx}` : null,
    props.build_info,
  ].filter((item): item is string => Boolean(item));
  return parts.length ? parts.join(" · ") : null;
}

function visibleHealthLabel(deployment: Deployment): string {
  if (deployment.status === "stopped") {
    return "Stopped";
  }
  return deploymentHealthLabel(deployment.health?.healthy);
}

function visibleHealthTone(deployment: Deployment): "neutral" | "ok" | "danger" {
  if (deployment.status === "stopped") {
    return "neutral";
  }
  if (deployment.health?.healthy === true) {
    return "ok";
  }
  if (deployment.health?.healthy === false) {
    return "danger";
  }
  return "neutral";
}

export function DeploymentsPanel() {
  const [runtime, setRuntime] = useState<RuntimeManifest | null>(null);
  const [bundles, setBundles] = useState<ModelBundle[]>([]);
  const [deployments, setDeployments] = useState<Deployment[]>([]);
  const [bundleId, setBundleId] = useState("");
  const [endpoint, setEndpoint] = useState("http://127.0.0.1:8080/v1");
  const [managedEmbedder, setManagedEmbedder] = useState(false);
  const [connectedEmbedder, setConnectedEmbedder] = useState(false);
  const [message, setMessage] = useState("");
  const [loadError, setLoadError] = useState("");
  const [busy, setBusy] = useState(false);

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
    setLoadError("");
  }

  useEffect(() => {
    void refresh().catch((error: unknown) => {
      setLoadError(errorMessage(error));
    });
  }, []);

  function fail(error: unknown): void {
    setMessage(errorMessage(error));
  }

  if (loadError) {
    return (
      <section className="panel">
        <h3>Deployments</h3>
        <Notice tone="error">{loadError}</Notice>
      </section>
    );
  }

  return (
    <section className="panel">
      <div className="card">
        <h3>Managed runtime</h3>
        {runtime ? (
          <p>
            {runtime.status} · {runtime.platform}
            {runtime.flavor ? ` · ${runtime.flavor}` : ""} · {runtime.release_tag}
            {runtime.error ? ` · ${runtime.error}` : ""}
          </p>
        ) : (
          <p className="hint">No runtime pinned yet. Pin is Windows CUDA 13.4 only.</p>
        )}
        <button
          type="button"
          disabled={busy}
          onClick={() => {
            setBusy(true);
            void api
              .pinRuntime()
              .then((manifest) => {
                setRuntime(manifest);
                setMessage(
                  manifest.error
                    ? `Runtime pin ${manifest.status}: ${manifest.error}`
                    : `Runtime pin ${manifest.status}`,
                );
              })
              .catch(fail)
              .finally(() => setBusy(false));
          }}
        >
          Pin Windows CUDA 13.4 runtime
        </button>
      </div>

      <div className="grid">
        <form
          className="card"
          onSubmit={(event) => {
            event.preventDefault();
            setBusy(true);
            void api
              .startManaged(
                bundleId,
                undefined,
                managedEmbedder ? { ...DEFAULT_GPU_STARTUP, ...DEFAULT_EMBEDDING_STARTUP } : undefined,
              )
              .then((deployment) => {
                setMessage(
                  deployment.health?.healthy === false
                    ? `${deployment.display_name} started but is still unhealthy. Refresh health while it loads.`
                    : `${deployment.display_name} · ${deployment.status}`,
                );
                return refresh();
              })
              .catch(fail)
              .finally(() => setBusy(false));
          }}
        >
          <h3>Start managed</h3>
          <p className="hint">
            Uses ctx_size {DEFAULT_GPU_STARTUP.ctx_size}, all GPU layers, flash attention on. A file
            under models is not a bundle — import it first. PATH llama-server is unsupported.
          </p>
          <label>
            Bundle
            <select value={bundleId} onChange={(event) => setBundleId(event.target.value)}>
              {bundles.length === 0 ? <option value="">No bundles</option> : null}
              {bundles.map((bundle) => (
                <option key={bundle.id} value={bundle.id}>
                  {bundle.display_name}
                </option>
              ))}
            </select>
          </label>
          <label className="check-row">
            <input
              type="checkbox"
              checked={managedEmbedder}
              onChange={(event) => setManagedEmbedder(event.target.checked)}
            />
            Dedicated embedder (embedding on, pooling last). Chat models are not embedders.
          </label>
          <button type="submit" disabled={!bundleId || busy}>
            Start
          </button>
        </form>

        <form
          className="card"
          onSubmit={(event) => {
            event.preventDefault();
            setBusy(true);
            void api
              .attachConnected(
                endpoint,
                undefined,
                connectedEmbedder ? { ...DEFAULT_EMBEDDING_STARTUP } : undefined,
              )
              .then((deployment) => {
                setMessage(`Attached ${deployment.display_name} · ${deployment.status}`);
                return refresh();
              })
              .catch(fail)
              .finally(() => setBusy(false));
          }}
        >
          <h3>Attach connected</h3>
          <p className="hint">Attach-only. The workbench will not start or stop that process.</p>
          <label>
            OpenAI-compatible endpoint
            <input value={endpoint} onChange={(event) => setEndpoint(event.target.value)} />
          </label>
          <label className="check-row">
            <input
              type="checkbox"
              checked={connectedEmbedder}
              onChange={(event) => setConnectedEmbedder(event.target.checked)}
            />
            Declare embedding on and pooling last. Does not start llama-server.
          </label>
          <button type="submit" disabled={busy}>
            Attach
          </button>
        </form>
      </div>

      <div className="card">
        <h3>Running and attached</h3>
        {deployments.length === 0 ? (
          <EmptyState title="No deployments">
            Start a managed llama-server from an imported bundle, or attach an endpoint that is
            already running.
          </EmptyState>
        ) : (
          <ul className="list">
            {deployments.map((deployment) => (
              <li key={deployment.id} className="entity">
                <div className="entity-head">
                  <strong>{deployment.display_name}</strong>
                  <StatusBadge
                    label={deployment.scope === "managed" ? "Managed" : "Connected"}
                    tone={deployment.scope === "managed" ? "live" : "warn"}
                  />
                  <StatusBadge label={deployment.status} tone={deployment.status === "failed" ? "danger" : "neutral"} />
                  <StatusBadge
                    label={visibleHealthLabel(deployment)}
                    tone={visibleHealthTone(deployment)}
                  />
                </div>
                <p className="hint">
                  {deployment.endpoint ?? "No endpoint"} · {resourceLabel(deployment)}
                </p>
                {propsSummary(deployment) ? <p className="hint">{propsSummary(deployment)}</p> : null}
                {deployment.health?.detail ? <p className="hint">{deployment.health.detail}</p> : null}
                {deployment.error ? <Notice tone="error">{deployment.error}</Notice> : null}
                <SettingsNotes
                  unsupported={deployment.settings?.startup.unsupported}
                  retired={deployment.settings?.startup.retired}
                />
                <div className="actions">
                  <button
                    type="button"
                    onClick={() => {
                      void api
                        .healthOf(deployment.id)
                        .then(() => refresh())
                        .catch(fail);
                    }}
                  >
                    Refresh health
                  </button>
                  {deployment.scope === "managed" ? (
                    <button
                      type="button"
                      disabled={deployment.status === "stopped" || busy}
                      onClick={() => {
                        void api.stop(deployment.id).then(() => refresh()).catch(fail);
                      }}
                    >
                      Stop
                    </button>
                  ) : (
                    <button
                      type="button"
                      onClick={() => {
                        void api.detach(deployment.id).then(() => refresh()).catch(fail);
                      }}
                    >
                      Detach
                    </button>
                  )}
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
      {message ? <Notice tone={message.toLowerCase().includes("fail") || message.toLowerCase().includes("error") ? "error" : "info"}>{message}</Notice> : null}
    </section>
  );
}
