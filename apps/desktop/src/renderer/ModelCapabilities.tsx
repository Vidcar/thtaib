import { useEffect, useRef, useState } from "react";
import { api } from "./api";
import { errorMessage } from "./errors";
import { Help } from "./ModelControls";
import { Notice } from "./Notice";
import { Icon } from "./Icon";
import type { Deployment } from "./types";
import type { SchemaCapabilityProbeReport } from "../generated/shared-contracts/openapi";

const checks = [["text_stream", "Streaming"], ["tools", "Tools"], ["reasoning", "Thinking"], ["structured_native", "Structured output"], ["image", "Vision"]] as const;

export function ModelCapabilities({ deployment, busy, action }: {
  deployment: Deployment;
  busy: string;
  action: (key: string, operation: () => Promise<unknown>) => Promise<void>;
}) {
  const [report, setReport] = useState<SchemaCapabilityProbeReport | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const generation = useRef(0);
  async function load() {
    const current = ++generation.current;
    setLoading(true); setError("");
    try {
      const result = await api.capabilityStatus(deployment.id);
      if (generation.current === current) setReport(result);
    } catch (failure) { if (generation.current === current) { setReport(null); setError(errorMessage(failure)); } }
    finally { if (generation.current === current) setLoading(false); }
  }
  useEffect(() => { setReport(null); void load(); return () => { generation.current += 1; }; }, [deployment]);
  const available = Boolean(deployment.health?.healthy && deployment.status !== "stopped");
  const evidence = [...(report?.evidence ?? [])].reverse();
  return <section className="model-probes" aria-label="Model capabilities">
    <div className="setting-title"><span>Capabilities</span><Help label="Verified capabilities">Saved results apply to the exact model, engine and settings tested. A changed setup needs another check. Tests run real requests and can take a moment.</Help></div>
    {error ? <Notice tone="warn" role="status" action={<button type="button" disabled={Boolean(busy)} onClick={() => void load()}>Retry results</button>}>Saved results unavailable. {error}</Notice> : null}
    <ul className="model-capabilities">{checks.map(([capability, label]) => {
      const latest = evidence.find(item => item.capability === capability && item.fingerprint === report?.current_fingerprint) ?? evidence.find(item => item.capability === capability);
      const stale = latest && latest.fingerprint !== report?.current_fingerprint;
      const state = loading ? "loading" : error ? "unknown" : stale ? "stale" : report?.current_support[capability] ?? "untested";
      const testing = busy === `probe-${deployment.id}-${capability}`;
      const unavailable = capability === "image" && (report?.image_setup?.runtime_support ?? deployment.server_props?.modalities?.vision) === false;
      const status = testing ? "Testing…" : ({ passed: "Verified", failed: "Failed", inconclusive: "Inconclusive", stale: "Needs retest", untested: "Not tested", loading: "Loading…", unknown: "Unavailable" }[state] ?? state);
      const visionNote = capability === "image" && unavailable
        ? report?.image_setup?.selected_projector ? report.image_setup.projector_present === false ? "Selected vision file is missing. Unload and choose an available file." : "A vision file is selected, but this running setup reports no image support. Unload and start it again." : deployment.scope === "managed" ? "No vision file is loaded. Choose one in Image input below, then start the model." : "This server reports no image input. Configure vision in the app serving it."
        : "";
      return <li key={capability}>
        <strong>{label}</strong><span className="capability-status" data-state={state} role="status">{state === "passed" && !testing ? <Icon name="check" size={12} /> : null}{status}{latest ? <Help label={`${label} evidence`}>{stale ? "An earlier setup was tested. " : "Saved result: "}{latest.status} · {new Date(latest.tested_at).toLocaleString()}. {latest.note}{typeof latest.observations?.error === "string" ? ` ${latest.observations.error}` : ""}</Help> : null}</span>
        <button type="button" disabled={Boolean(busy) || loading || !available || unavailable} aria-label={`${latest ? "Retest" : "Test"} ${label.toLowerCase()}`} onClick={() => void action(`probe-${deployment.id}-${capability}`, async () => { await api.capabilityProbe(deployment.id, capability); await load(); })}>{testing ? "Testing…" : latest ? "Retest" : "Test"}</button>
        {visionNote ? <span className="model-capability-note">{visionNote}</span> : null}
      </li>;
    })}</ul>
    {!available ? <p className="hint">Load this model to run a check.</p> : null}
  </section>;
}
