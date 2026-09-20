import { useEffect, useState } from "react";

import { api, DEFAULT_EMBEDDING_STARTUP } from "./api";
import { formatBytes } from "./display";
import { EmptyState } from "./EmptyState";
import { errorMessage } from "./errors";
import { deploymentHealthLabel } from "./labels";
import { Notice } from "./Notice";
import { SettingsNotes } from "./settingsNotes";
import { StatusBadge } from "./StatusBadge";
import type { Deployment, ModelBundle, RuntimeManifest, SettingsBags } from "./types";

const KV_CACHE_TYPES = ["", "f16", "q8_0", "q4_0", "q4_1", "q5_0", "q5_1", "bf16", "f32", "iq4_nl"] as const;
const FLASH_ATTN_VALUES = ["on", "off", "auto"] as const;
const FIT_VALUES = ["", "on", "off"] as const;

function parseOptionalNumber(label: string, value: string): number | undefined {
  const trimmed = value.trim();
  if (!trimmed) {
    return undefined;
  }
  const parsed = Number(trimmed);
  if (!Number.isFinite(parsed)) {
    throw new Error(`${label} must be a number.`);
  }
  return parsed;
}

function parseAdvancedStartup(value: string): Record<string, unknown> {
  const trimmed = value.trim();
  if (!trimmed) {
    return {};
  }
  const parsed = JSON.parse(trimmed) as unknown;
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
    throw new Error("Advanced startup must be a JSON object.");
  }
  return parsed as Record<string, unknown>;
}

function compactStartup(startup: Record<string, unknown>): string {
  const entries = Object.entries(startup);
  if (!entries.length) {
    return "none";
  }
  return entries.map(([key, value]) => `${key}: ${String(value)}`).join(" | ");
}

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

export function DeploymentsPanel({ selectedBundleId = "", bundlesVersion = "" }: { selectedBundleId?: string; bundlesVersion?: string } = {}) {
  const [runtime, setRuntime] = useState<RuntimeManifest | null>(null);
  const [bundles, setBundles] = useState<ModelBundle[]>([]);
  const [deployments, setDeployments] = useState<Deployment[]>([]);
  const [bundleId, setBundleId] = useState("");
  const [endpoint, setEndpoint] = useState("http://127.0.0.1:8080/v1");
  const [managedEmbedder, setManagedEmbedder] = useState(false);
  const [connectedEmbedder, setConnectedEmbedder] = useState(false);
  const [contextSize, setContextSize] = useState("");
  const [gpuLayers, setGpuLayers] = useState("-1");
  const [flashAttn, setFlashAttn] = useState<(typeof FLASH_ATTN_VALUES)[number]>("on");
  const [fit, setFit] = useState<(typeof FIT_VALUES)[number]>("");
  const [threadsBatch, setThreadsBatch] = useState("");
  const [cacheTypeK, setCacheTypeK] = useState<(typeof KV_CACHE_TYPES)[number]>("");
  const [cacheTypeV, setCacheTypeV] = useState<(typeof KV_CACHE_TYPES)[number]>("");
  const [advancedStartup, setAdvancedStartup] = useState("");
  const [settingsPreview, setSettingsPreview] = useState<SettingsBags | null>(null);
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
  }, [bundlesVersion]);

  useEffect(() => {
    if (selectedBundleId) setBundleId(selectedBundleId);
  }, [selectedBundleId]);

  function fail(error: unknown): void {
    setMessage(errorMessage(error));
  }

  function managedStartup(): Record<string, unknown> {
    const startup: Record<string, unknown> = {
      ...parseAdvancedStartup(advancedStartup),
      n_gpu_layers: gpuLayers.trim() || "auto",
      flash_attn: flashAttn,
    };
    const parsedContext = parseOptionalNumber("Context size", contextSize);
    if (parsedContext !== undefined) startup.ctx_size = parsedContext;
    if (fit) startup.fit = fit;
    const parsedThreadsBatch = parseOptionalNumber("Batch threads", threadsBatch);
    if (parsedThreadsBatch !== undefined) startup.threads_batch = parsedThreadsBatch;
    if (cacheTypeK) startup.cache_type_k = cacheTypeK;
    if (cacheTypeV) startup.cache_type_v = cacheTypeV;
    if (managedEmbedder) Object.assign(startup, DEFAULT_EMBEDDING_STARTUP);
    return startup;
  }

  async function previewManagedStartup(): Promise<SettingsBags> {
    const preview = await api.previewSettings(managedStartup(), {}, {});
    setSettingsPreview(preview);
    if (preview.startup.unsupported.length || preview.startup.retired.length) {
      throw new Error(
        `Startup settings need correction: ${[
          ...preview.startup.unsupported,
          ...preview.startup.retired.map((item) => item.key),
        ].join(", ")}`,
      );
    }
    return preview;
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
            void previewManagedStartup()
              .then(() => api.startManaged(bundleId, undefined, managedStartup()))
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
            Context is blank by default so llama.cpp can use the model and fit behavior. A file
            under models is not a bundle; import it first. PATH llama-server is unsupported.
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
          <div className="setup-grid">
            <label>
              Context size
              <input
                type="number"
                min="1"
                step="1"
                placeholder="Model default"
                value={contextSize}
                onChange={(event) => {
                  setContextSize(event.target.value);
                  setSettingsPreview(null);
                }}
              />
            </label>
            <label>
              GPU layers
              <input
                value={gpuLayers}
                onChange={(event) => {
                  setGpuLayers(event.target.value);
                  setSettingsPreview(null);
                }}
                placeholder="auto, all, -1, or a number"
              />
            </label>
            <label>
              Fit memory
              <select
                value={fit}
                onChange={(event) => {
                  setFit(event.target.value as (typeof FIT_VALUES)[number]);
                  setSettingsPreview(null);
                }}
              >
                <option value="">Runtime default</option>
                <option value="on">On</option>
                <option value="off">Off</option>
              </select>
            </label>
            <label>
              Flash attention
              <select
                value={flashAttn}
                onChange={(event) => {
                  setFlashAttn(event.target.value as (typeof FLASH_ATTN_VALUES)[number]);
                  setSettingsPreview(null);
                }}
              >
                <option value="on">On</option>
                <option value="off">Off</option>
                <option value="auto">Auto</option>
              </select>
            </label>
            <label>
              KV cache K
              <select
                value={cacheTypeK}
                onChange={(event) => {
                  setCacheTypeK(event.target.value as (typeof KV_CACHE_TYPES)[number]);
                  setSettingsPreview(null);
                }}
              >
                <option value="">Runtime default</option>
                {KV_CACHE_TYPES.filter(Boolean).map((value) => (
                  <option key={value} value={value}>
                    {value}
                  </option>
                ))}
              </select>
            </label>
            <label>
              KV cache V
              <select
                value={cacheTypeV}
                onChange={(event) => {
                  setCacheTypeV(event.target.value as (typeof KV_CACHE_TYPES)[number]);
                  setSettingsPreview(null);
                }}
              >
                <option value="">Runtime default</option>
                {KV_CACHE_TYPES.filter(Boolean).map((value) => (
                  <option key={value} value={value}>
                    {value}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Batch threads
              <input
                type="number"
                min="1"
                step="1"
                placeholder="Same as generation"
                value={threadsBatch}
                onChange={(event) => {
                  setThreadsBatch(event.target.value);
                  setSettingsPreview(null);
                }}
              />
            </label>
          </div>
          <label className="check-row">
            <input
              type="checkbox"
              checked={managedEmbedder}
              onChange={(event) => {
                setManagedEmbedder(event.target.checked);
                setSettingsPreview(null);
              }}
            />
            Dedicated embedder (embedding on, pooling last). Chat models are not embedders.
          </label>
          <details>
            <summary>Advanced startup JSON</summary>
            <p className="hint">
              Preview checks startup keys with the backend. Visible controls above win when keys overlap.
            </p>
            <textarea
              value={advancedStartup}
              onChange={(event) => {
                setAdvancedStartup(event.target.value);
                setSettingsPreview(null);
              }}
              placeholder='{"reasoning":"auto","cache_type_k":"q8_0"}'
            />
          </details>
          <div className="actions">
            <button
              type="button"
              disabled={busy}
              onClick={() => {
                setBusy(true);
                void previewManagedStartup()
                  .then((preview) => {
                    setMessage(`Startup preview: ${compactStartup(preview.startup.applied)}`);
                  })
                  .catch(fail)
                  .finally(() => setBusy(false));
              }}
            >
              Preview settings
            </button>
            <button type="submit" disabled={!bundleId || busy}>
              Start
            </button>
          </div>
          {settingsPreview ? (
            <>
              <p className="hint">Resolved startup preview: {compactStartup(settingsPreview.startup.applied)}. Nothing has been applied to a running model.</p>
              <SettingsNotes
                unsupported={settingsPreview.startup.unsupported}
                retired={settingsPreview.startup.retired}
              />
            </>
          ) : null}
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
