import { useEffect, useRef, useState } from "react";
import { api } from "./api";
import { errorMessage } from "./errors";
import { Icon, type IconName } from "./Icon";
import type { RunProfile } from "./types";
import type { SchemaCapabilityProbeReport } from "../generated/shared-contracts/openapi";

export const modelCheckKinds: ReadonlyArray<{ id: string; label: string; icon: IconName }> = [
  { id: "text_stream", label: "Text streaming", icon: "chat" }, { id: "reasoning", label: "Thinking", icon: "reasoning" },
  { id: "reasoning_replay", label: "Thinking history", icon: "history" }, { id: "tools", label: "Tool round trip", icon: "wrench" },
  { id: "structured_native", label: "Native structured output", icon: "braces" }, { id: "structured_tools", label: "Structured output via a tool", icon: "fileJson" },
  { id: "structured_with_tools", label: "Native JSON after a tool", icon: "agent-run" }, { id: "structured_tools_with_tools", label: "Formatter after a task tool", icon: "listTree" },
  { id: "image", label: "Image input", icon: "image" }, { id: "tool_image", label: "Image returned by a tool", icon: "images" },
];
type Report = SchemaCapabilityProbeReport & { applicable_capabilities?: string[]; automatic_running?: boolean; running_capability?: string | null };
const statusLabel: Record<string, string> = { passed: "Passed", failed: "Failed", inconclusive: "Inconclusive", untested: "Not checked", running: "Checking", absent: "Not applicable" };

export function ModelChecks({ profile, active, disabled, onReloaded, refreshVersion }: { profile?: RunProfile; active: boolean; disabled: boolean; onReloaded: () => Promise<void>; refreshVersion?: string }) {
  const [report, setReport] = useState<Report | null>(null), [error, setError] = useState("");
  const [running, setRunning] = useState(""), [hovered, setHovered] = useState<string | null>(null);
  const scope = `${profile?.id ?? ""}:${profile?.revision ?? 0}`;
  const owner = useRef(scope); owner.current = scope;
  const pending = useRef(false);
  async function refresh(expected = scope) {
    if (!profile) return;
    try { const next = await api.configurationCapabilities(profile.id, profile.revision); if (owner.current === expected) { setReport(next); setError(""); } }
    catch (failure) { if (owner.current === expected) setError(errorMessage(failure)); }
  }
  useEffect(() => { setReport(null); setError(""); setHovered(null); setRunning(""); if (active && profile) void refresh(); }, [scope, active, refreshVersion]);
  useEffect(() => {
    if (!active || !profile || !report?.automatic_running && !running) return;
    const timer = window.setTimeout(() => void refresh(), 1000);
    return () => window.clearTimeout(timer);
  }, [active, scope, report, running]);
  const applicable = new Set(report?.applicable_capabilities ?? []);
  async function run(kinds: string[]) {
    if (!profile || !report || disabled || report.automatic_running || pending.current || kinds.some(id => !applicable.has(id))) return;
    pending.current = true; const expected = scope; setError("");
    try {
      for (const id of kinds) {
        if (owner.current !== expected) break;
        setRunning(id);
        await api.probeConfiguration(profile.id, id, profile.revision);
        await refresh(expected);
      }
      await onReloaded();
    } catch (failure) { if (owner.current === expected) setError(errorMessage(failure)); }
    finally { pending.current = false; if (owner.current === expected) setRunning(""); }
  }
  const detail = hovered ? modelCheckKinds.find(item => item.id === hovered) : undefined;
  function state(id: string) { return running === id || report?.running_capability === id ? "running" : !profile ? "absent" : !report ? "untested" : !applicable.has(id) ? "absent" : report?.current_support?.[id] ?? "untested"; }
  const evidence = report?.evidence?.slice().reverse().find(item => item.capability === hovered && item.status === report.current_support?.[hovered ?? ""]);
  return <div className="model-header-checks" role="group" aria-label="Saved setup checks">
    {modelCheckKinds.map(item => <button type="button" key={item.id} className="model-check-icon" data-state={state(item.id)} aria-disabled={!profile || !report || disabled || Boolean(running) || report?.automatic_running || !applicable.has(item.id)} aria-label={`Check ${item.label.toLowerCase()}: ${statusLabel[state(item.id)] ?? state(item.id)}`} title={`${item.label}: ${statusLabel[state(item.id)] ?? state(item.id)}`} onMouseEnter={() => setHovered(item.id)} onMouseLeave={() => setHovered(null)} onFocus={() => setHovered(item.id)} onBlur={() => setHovered(null)} onClick={() => void run([item.id])}><Icon name={item.icon} size={20} /></button>)}
    <button type="button" className="model-check-icon" aria-label="Run all checks" title="Run all checks" disabled={!profile || !report || disabled || Boolean(running) || report?.automatic_running} onClick={() => void run(modelCheckKinds.filter(item => applicable.has(item.id)).map(item => item.id))}><Icon name="checks" size={20} /></button>
    {detail ? <div className="model-check-tooltip" role="tooltip"><strong>{detail.label}</strong><span>{statusLabel[state(detail.id)] ?? state(detail.id)}</span><p>{evidence?.note ?? (profile ? "Checks the saved setup." : "Create a saved setup first.")}</p></div> : null}
    {error ? <span className="model-check-error" role="status">{error}<button type="button" className="text-button" onClick={() => void refresh()}>Retry results</button></span> : null}
  </div>;
}
