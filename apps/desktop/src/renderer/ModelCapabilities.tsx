import { useEffect, useRef, useState, type ReactNode } from "react";
import { api } from "./api";
import { errorMessage } from "./errors";
import { Help } from "./ModelControls";
import { Notice } from "./Notice";
import { CapabilityIconRow, type CapabilityIconItem, type CapabilityIconState } from "./CapabilityIcons";
import type { Deployment } from "./types";
import type { SchemaCapabilityProbeReport } from "../generated/shared-contracts/openapi";

const AUTO_PROBES = ["text_stream", "tools", "structured_native", "reasoning", "reasoning_replay", "image", "tool_image"] as const;
type ProbeName = typeof AUTO_PROBES[number];
const startedProbes = new Set<string>();

function recorded(report: SchemaCapabilityProbeReport | null, capability: string): CapabilityIconState | null {
  const value = report?.current_support?.[capability];
  return value === "passed" || value === "failed" || value === "inconclusive" || value === "untested" ? value : null;
}

function vision(deployment: Deployment, report: SchemaCapabilityProbeReport | null): boolean | null {
  const runtime = report?.image_setup?.runtime_support;
  if (runtime === true || runtime === false) return runtime;
  const modality = deployment.server_props?.modalities?.vision;
  return modality === true || modality === false ? modality : null;
}

function projectorSelected(report: SchemaCapabilityProbeReport | null): boolean {
  return Boolean(report?.image_setup?.selected_projector) || report?.image_setup?.projector_present === true;
}

function imageAdmitted(deployment: Deployment, report: SchemaCapabilityProbeReport | null): boolean {
  const seen = vision(deployment, report);
  return seen === true || (projectorSelected(report) && seen !== false);
}

function shouldProbe(deployment: Deployment, report: SchemaCapabilityProbeReport, capability: ProbeName): boolean {
  if (String(deployment.applied_startup?.embedding ?? "").toLowerCase() === "on") return false;
  const caps = deployment.server_props?.chat_template_caps;
  if (capability === "reasoning") return caps?.supports_thinking === true;
  if (capability === "reasoning_replay") return caps?.supports_preserve_reasoning === true;
  if (capability === "image" || capability === "tool_image") return imageAdmitted(deployment, report);
  return capability === "text_stream" || capability === "tools" || capability === "structured_native";
}

function noteFor(report: SchemaCapabilityProbeReport | null, capability: string, fallback: string): string {
  const latest = [...(report?.evidence ?? [])].reverse().find(item => item.capability === capability);
  if (!latest) return fallback;
  const error = typeof latest.observations?.error === "string" ? ` ${latest.observations.error}` : "";
  return `${latest.note}${error}`.trim() || fallback;
}

export function ModelCapabilities({ deployment, busy, action }: {
  deployment: Deployment;
  busy: string;
  action: (key: string, operation: () => Promise<unknown>) => Promise<void>;
}) {
  const [report, setReport] = useState<SchemaCapabilityProbeReport | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [retesting, setRetesting] = useState("");
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
  useEffect(() => {
    if (!report || error || !available) return;
    const fingerprint = report.current_fingerprint;
    const pending = AUTO_PROBES.filter(capability => {
      if (report.current_support?.[capability] !== "untested" || !shouldProbe(deployment, report, capability)) return false;
      const key = `${deployment.id}:${capability}:${fingerprint}`;
      if (startedProbes.has(key)) return false;
      startedProbes.add(key);
      return true;
    });
    if (!pending.length) return;
    const current = generation.current;
    let cancelled = false;
    void (async () => {
      for (const capability of pending) {
        if (cancelled || generation.current !== current) return;
        try { await api.capabilityProbe(deployment.id, capability); } catch { /* The refreshed report keeps the outcome. */ }
      }
      if (cancelled || generation.current !== current) return;
      try {
        const next = await api.capabilityStatus(deployment.id);
        if (!cancelled && generation.current === current) setReport(next);
      } catch (failure) {
        if (!cancelled && generation.current === current) { setReport(null); setError(errorMessage(failure)); }
      }
    })();
    return () => { cancelled = true; };
  }, [report, error, available, deployment]);

  function retest(capability: ProbeName) {
    if (!available || busy || retesting) return;
    void action(`probe-${deployment.id}-${capability}`, async () => {
      setRetesting(capability);
      try { await api.capabilityProbe(deployment.id, capability); await load(); }
      finally { setRetesting(""); }
    });
  }

  const embedder = String(deployment.applied_startup?.embedding ?? "").toLowerCase() === "on";
  const seenVision = vision(deployment, report);
  const hasProjector = projectorSelected(report);
  const thinking = deployment.server_props?.chat_template_caps?.supports_thinking;
  const preserve = deployment.server_props?.chat_template_caps?.supports_preserve_reasoning === true;
  const modalities = deployment.server_props?.modalities;
  function shown(capability: string, present: boolean, absentDetail: string): { state: CapabilityIconState; detail: string } {
    const status = !error && present ? recorded(report, capability) : null;
    if (!status || status === "untested" && !present) return { state: "absent", detail: absentDetail };
    return { state: status, detail: status === "untested" ? "Not checked yet." : noteFor(report, capability, "Not checked yet.") };
  }
  const text = shown("text_stream", !embedder, "This setup does not serve chat text.");
  const tools = shown("tools", !embedder, "Checked after a chat model loads.");
  const structured = shown("structured_native", !embedder, "Checked after a chat model loads.");
  const thinkingState = shown("reasoning", thinking === true, thinking === false ? "This model does not report thinking." : "Thinking support is not reported yet.");
  const imagePresent = seenVision === true || hasProjector;
  const image = shown("image", imagePresent, "No image input.");
  if (seenVision === false && hasProjector) image.detail = "A vision file is selected, but this running setup reports no image input.";
  const items: CapabilityIconItem[] = [
    { id: "text", label: "Text", icon: "chat", ...text, onRetest: available && !embedder ? () => retest("text_stream") : undefined, retestDisabled: Boolean(busy) || !available, retesting: retesting === "text_stream" },
    { id: "tools", label: "Tools", icon: "wrench", ...tools, onRetest: available && !embedder ? () => retest("tools") : undefined, retestDisabled: Boolean(busy) || !available, retesting: retesting === "tools" },
    { id: "thinking", label: "Thinking", icon: "reasoning", ...thinkingState, detail: <>{thinkingState.detail}{preserve ? <span> {noteFor(report, "reasoning_replay", "Thinking history is not checked yet.")}</span> : null}</>, onRetest: available && thinking === true ? () => retest("reasoning") : undefined, retestDisabled: Boolean(busy) || !available, retesting: retesting === "reasoning" },
    { id: "structured", label: "Structured output", icon: "braces", ...structured, onRetest: available && !embedder ? () => retest("structured_native") : undefined, retestDisabled: Boolean(busy) || !available, retesting: retesting === "structured_native" },
    { id: "image", label: "Image", icon: "image", ...image, detail: <ImageDetail detail={image.detail} report={report} canRetest={available && imageAdmitted(deployment, report)} busy={Boolean(busy) || Boolean(retesting)} retesting={retesting === "tool_image"} onRetest={() => retest("tool_image")} />, onRetest: available && imageAdmitted(deployment, report) ? () => retest("image") : undefined, retestDisabled: Boolean(busy) || !available, retesting: retesting === "image" },
    { id: "video", label: "Video", icon: "video", state: modalities?.video === true ? "untested" : "absent", detail: modalities?.video === true ? "The running model reports video input." : "No video input reported." },
    { id: "audio", label: "Audio", icon: "audio", state: modalities?.audio === true ? "untested" : "absent", detail: modalities?.audio === true ? "The running model reports audio input." : "No audio input reported." },
  ];
  return <section className="model-probes" aria-label="Model capabilities">
    <div className="setting-title"><span>Capabilities</span><Help label="Verified capabilities">Checks follow the model weights and vision file. Context, cache, GPU placement and MTP do not clear a saved check.</Help></div>
    {loading && !report && !error ? <p className="hint" role="status">Loading saved checks…</p> : null}
    {error ? <Notice tone="warn" role="status" action={<button type="button" disabled={Boolean(busy)} onClick={() => void load()}>Retry results</button>}>Saved results unavailable. {error}</Notice> : null}
    <CapabilityIconRow items={items} />
    {!available ? <p className="hint">Load this model to run a check.</p> : null}
  </section>;
}

function ImageDetail({ detail, report, canRetest, busy, retesting, onRetest }: {
  detail: ReactNode; report: SchemaCapabilityProbeReport | null; canRetest: boolean; busy: boolean; retesting: boolean; onRetest: () => void;
}) {
  return <>
    <span>{detail}</span>
    {canRetest ? <><span>{noteFor(report, "tool_image", "Screenshot reading is not checked yet.")}</span><button type="button" disabled={busy} onClick={onRetest}>{retesting ? "Checking…" : "Retest screenshot reading"}</button></> : null}
  </>;
}
