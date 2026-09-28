import { useEffect, useRef, useState } from "react";
import { api, DEFAULT_EMBEDDING_STARTUP } from "./api";
import { CompactSwitch, NumberField, SettingRow, SettingSection } from "./CompactControls";
import { errorMessage } from "./errors";
import { Notice } from "./Notice";
import { StatusBadge } from "./StatusBadge";
import type { Deployment, ManagedModelsRuntime, RuntimeManifest } from "./types";

/** Shared engine policy has one home in Settings. Model setup editors only observe readiness. */
export function ModelEngineSettings() {
  const [runtime, setRuntime] = useState<RuntimeManifest | null>(null);
  const [residency, setResidency] = useState<ManagedModelsRuntime | null>(null);
  const [deployments, setDeployments] = useState<Deployment[]>([]);
  const [maximum, setMaximum] = useState(1);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [endpoint, setEndpoint] = useState("http://127.0.0.1:8080/v1");
  const [name, setName] = useState("");
  const [embeddings, setEmbeddings] = useState(false);
  const pending = useRef(false);
  async function refresh() {
    const [engine, limits, models] = await Promise.all([api.runtime(), api.managedModelsRuntime(), api.deployments()]);
    setRuntime(engine); setResidency(limits); setMaximum(limits.max_loaded_models); setDeployments(models);
  }
  useEffect(() => { let alive = true; void refresh().catch(failure => { if (alive) setError(errorMessage(failure)); }).finally(() => { if (alive) setLoading(false); }); return () => { alive = false; }; }, []);
  async function action(key: string, operation: () => Promise<void>) {
    if (pending.current) return;
    pending.current = true; setBusy(key); setError(""); setMessage("");
    try { await operation(); } catch (failure) { setError(errorMessage(failure)); }
    finally { pending.current = false; setBusy(""); }
  }
  const inUse = deployments.some(model => model.scope === "managed" && !["stopped", "failed"].includes(model.status));
  const connections = deployments.filter(model => model.scope === "connected" && model.status !== "stopped");
  const alreadyConnected = connections.some(model => model.endpoint?.replace(/\/$/, "") === endpoint.trim().replace(/\/$/, ""));
  return <>
    <SettingSection title="Local model engine" description="Shared installation and residency policy for every model setup." actions={<StatusBadge label={loading ? "Checking" : runtime?.status === "ready" ? "Ready" : "Setup required"} tone={runtime?.status === "ready" ? "ok" : "neutral"} />}>
      {error ? <Notice tone="error" action={<button type="button" disabled={Boolean(busy)} onClick={() => void action("refresh", refresh)}>Retry</button>}>{error}</Notice> : null}
      {message ? <p className="hint" role="status">{message}</p> : null}
      <SettingRow label="Maximum loaded models" help="The limit counts distinct loaded plans. Saved setups with the same weights and loading settings share a loaded model. Concurrent requests for one model are configured in its setup." hint={residency ? `${residency.loaded_deployment_ids.length} loaded · ${residency.loading_deployment_ids.length} loading` : undefined}>
        <NumberField label="Maximum loaded models" min={1} step={1} value={maximum} disabled={Boolean(busy) || loading} onChange={value => setMaximum(value ?? 1)} />
        <button type="button" disabled={Boolean(busy) || !Number.isSafeInteger(maximum) || maximum < 1 || maximum === residency?.max_loaded_models} onClick={() => void action("limit", async () => { const saved = await api.setManagedModelsRuntime(maximum); setResidency(saved); setMaximum(saved.max_loaded_models); setMessage("Loaded model limit saved."); })}>{busy === "limit" ? "Saving…" : "Save limit"}</button>
      </SettingRow>
      <SettingRow label="Installation" provenance={runtime ? `llama.cpp ${runtime.release_tag} · ${runtime.platform} · ${runtime.flavor}` : undefined} hint={inUse ? "Unload local models before changing the engine installation." : runtime?.error ?? undefined}>
        <button type="button" disabled={Boolean(busy) || inUse || loading} onClick={() => void action("engine", async () => { const next = await api.pinRuntime(); setRuntime(next); if (next.error) throw new Error(next.error); setMessage("Local engine is ready."); })}>{busy === "engine" ? "Setting up…" : runtime?.status === "ready" ? "Verify installation" : "Set up local engine"}</button>
      </SettingRow>
    </SettingSection>
    <SettingSection title="Model server connections" description="Connect a model served by another app. Start and stop it in that app.">
      {connections.map(model => <SettingRow key={model.id} label={model.display_name.replace(/^connected:/, "")} provenance={model.endpoint} hint={model.error ?? undefined}><StatusBadge label={model.health?.healthy ? "Ready" : "Needs attention"} tone={model.health?.healthy ? "ok" : "warn"} /><button type="button" disabled={Boolean(busy)} onClick={() => void action(model.id, async () => { await api.detach(model.id); await refresh(); })}>Disconnect</button></SettingRow>)}
      <form onSubmit={event => { event.preventDefault(); if (alreadyConnected) return; void action("connect", async () => { const result = await api.attachConnected(endpoint, name || undefined, embeddings ? { ...DEFAULT_EMBEDDING_STARTUP } : undefined); await refresh(); setMessage(result.health?.healthy ? "Model server connected and ready." : "Model server saved. Check that it is running at this address."); }); }}>
        <SettingRow label="Server address" htmlFor="model-server-address"><input id="model-server-address" type="url" required value={endpoint} disabled={Boolean(busy)} onChange={event => setEndpoint(event.target.value)} /></SettingRow>
        <SettingRow label="Name" htmlFor="model-server-name"><input id="model-server-name" value={name} placeholder="Optional" disabled={Boolean(busy)} onChange={event => setName(event.target.value)} /></SettingRow>
        <CompactSwitch label="Use for document search" checked={embeddings} disabled={Boolean(busy)} onChange={setEmbeddings} description="The external server must serve embeddings with last-token pooling." />
        <div className="setting-actions"><button type="submit" disabled={Boolean(busy) || alreadyConnected}>{busy === "connect" ? "Connecting…" : alreadyConnected ? "Already connected" : "Connect server"}</button></div>
      </form>
    </SettingSection>
  </>;
}
