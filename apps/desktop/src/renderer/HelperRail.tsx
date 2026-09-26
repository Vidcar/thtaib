import { useMessages, useToolCalls } from "@langchain/react";
import { useEffect, useMemo, useState } from "react";
import { AgentMessageFeed, helperKey } from "./AgentMessageFeed";
import { InteractionStream, type WorkbenchStream } from "./InteractionStream";
import type { AgentRun } from "./types";

type Discovery = WorkbenchStream["subagents"] extends ReadonlyMap<string, infer Value> ? Value : never;

export interface HelperEntry {
  key: string;
  runId: string;
  id: string;
  name: string;
  request?: string;
  recordedToolCount?: number;
  namespace: string[];
  status: string;
  error?: string;
}

export function helperIsActive(status: string): boolean {
  return ["queued", "starting", "waiting_for_model", "waiting for model", "running", "working", "cancel_requested", "waiting_approval", "waiting for approval or answer"].includes(status);
}

export function helperEntries(runs: AgentRun[], discoveries: Iterable<Discovery>, currentRunId?: string): HelperEntry[] {
  const entries = new Map<string, HelperEntry>();
  const currentRun = runs.find(run => run.id === currentRunId);
  // SDK discovery timestamps are local replay arrival times, not run ownership.
  // A parent-owned task or child reference is required before attaching a card.
  const ownedTaskIds = new Set([
    ...(currentRun?.child_runs ?? []).map(child => child.tool_call_id),
    ...(currentRun?.events ?? []).filter(event => event.kind === "tool_call" && event.detail.name === "task").map(event => event.detail.id),
  ]);
  const earlierTaskIds = new Set(runs.filter(run => run.id !== currentRunId).flatMap(run =>
    (run.child_runs ?? []).map(child => child.tool_call_id)));
  const allowDiscovery = !currentRun?.status || helperIsActive(currentRun.status);
  for (const run of runs) {
    for (const child of run.child_runs ?? []) {
      const id = child.tool_call_id || child.run_id;
      const snapshot = run.helper_snapshots?.find(item => item.agent_id === child.agent_id && item.version_id === child.version_id);
      const key = helperKey(run.id, id);
      const args = run.events?.find(event => event.kind === "tool_call" && event.detail.id === id)?.detail.args;
      const request = args && typeof args === "object" && "description" in args && typeof args.description === "string" ? args.description : undefined;
      const recordedToolCount = Object.entries(run.tool_outcomes ?? {}).filter(([outcomeKey, outcome]) =>
        outcomeKey.startsWith(`${child.run_id}:`) && outcome.outcome !== "running").length;
      entries.set(key, { key, runId: run.id, id, name: snapshot?.name ?? child.name, request, recordedToolCount,
        namespace: child.namespace, status: child.status, error: child.error });
    }
  }
  for (const discovered of currentRunId && allowDiscovery ? discoveries : []) {
    if (discovered.parentId || !ownedTaskIds.has(discovered.id)) continue;
    // A reused call ID in the SDK map may still describe the earlier turn.
    // Its new parent's durable child reference remains authoritative instead.
    if (earlierTaskIds.has(discovered.id)) continue;
    const key = helperKey(currentRunId!, discovered.id);
    const saved = entries.get(key);
    entries.set(key, {
      key,
      runId: currentRunId!,
      id: discovered.id,
      name: saved?.name ?? discovered.name,
      request: saved?.request ?? discovered.taskInput,
      recordedToolCount: saved?.recordedToolCount,
      namespace: saved?.namespace?.length ? saved.namespace : [...discovered.namespace],
      status: saved?.status ?? discovered.status,
      error: saved?.error ?? discovered.error,
    });
  }
  return [...entries.values()];
}

function HelperTranscript({ stream, helper, conversationId, detailedStreams }: { stream: WorkbenchStream; helper: HelperEntry; conversationId: string; detailedStreams: boolean }) {
  const messages = useMessages(stream, helper.namespace);
  const toolCalls = useToolCalls(stream, helper.namespace);
  // The exact delegation is available once in its disclosure above. The first
  // native human message repeats it (plus internal context notices).
  const transcript = useMemo(() => helper.request && messages[0]?.getType() === "human" ? messages.slice(1) : messages, [messages, helper.request]);
  const loading = <p className="hint" role="status">{stream.error ? "Helper activity could not be loaded." : "Loading helper activity…"}
    {helper.recordedToolCount ? ` ${helper.recordedToolCount} tool ${helper.recordedToolCount === 1 ? "result" : "results"} recorded.` : ""}</p>;
  return <>
    {helper.error ? <p className="tool-call-error" role="status">{helper.error}</p> : null}
    <AgentMessageFeed messages={transcript} toolCalls={toolCalls} live={helperIsActive(helper.status)} detailedStreams={detailedStreams} sourceScope={{ sessionId: conversationId }} fallback={loading} />
  </>;
}

export function HelperRequest({ request }: { request: string }) {
  const long = request.length > 240 || request.split("\n").length > 3;
  return long ? <details className="helper-request-disclosure"><summary>Delegated request</summary><p className="helper-rail-request">{request}</p></details>
    : <p className="helper-rail-request">{request}</p>;
}

function HelperRailContent({ stream, runs, currentRunId, selectedHelperKey, conversationId, detailedStreams }: { stream: WorkbenchStream; runs: AgentRun[]; currentRunId?: string; selectedHelperKey?: string; conversationId: string; detailedStreams: boolean }) {
  const [selectedId, setSelectedId] = useState(selectedHelperKey ?? "");
  useEffect(() => setSelectedId(selectedHelperKey ?? ""), [selectedHelperKey]);
  const streamedRun = stream.values.workbench?.run;
  const visibleRuns = streamedRun ? [...runs.filter(run => run.id !== streamedRun.id), streamedRun] : runs;
  const children = helperEntries(visibleRuns, stream.subagents.values(), streamedRun?.id ?? currentRunId);
  const selected = children.find(child => child.key === selectedId);
  if (!children.length) return <p className="hint">Helpers used in this chat will appear here.</p>;
  if (selected) return <div className="helper-rail helper-rail-detail">
    <button type="button" className="quiet-button helper-rail-back" onClick={() => setSelectedId("")}>← All helpers</button>
    <div className="helper-rail-heading"><strong>{selected.name}</strong><span>{selected.status.replaceAll("_", " ")}</span></div>
    {selected.request ? <HelperRequest request={selected.request} /> : null}
    {selected.namespace.length && !(selected.namespace.length === 1 && selected.namespace[0] === "tools") ? <HelperTranscript key={`${selected.key}:${selected.namespace.join("|")}`} stream={stream} helper={selected} conversationId={conversationId} detailedStreams={detailedStreams} /> : <p className="hint">{helperIsActive(selected.status) ? "Waiting for helper output…" : "This earlier helper run has no recoverable public transcript."}</p>}
  </div>;
  const active = children.filter(child => helperIsActive(child.status));
  const done = children.filter(child => !helperIsActive(child.status));
  const group = (label: string, entries: HelperEntry[]) => <section className="helper-rail-group" aria-label={`${label} helpers`}><h3>{label} · {entries.length}</h3>{entries.length ? entries.map(child => <button type="button" key={child.key} onClick={() => setSelectedId(child.key)}><strong>{child.name}</strong><span>{child.status.replaceAll("_", " ")}</span></button>) : <p className="hint">No {label.toLowerCase()} helpers</p>}</section>;
  return <div className="helper-rail helper-rail-list">{group("Active", active)}{group("Done", done)}</div>;
}

export function HelperRail({ runs, currentRunId, threadId, conversationId, selectedHelperKey, detailedStreams = false }: { runs: AgentRun[]; currentRunId?: string; threadId: string | null; conversationId: string; selectedHelperKey?: string; detailedStreams?: boolean }) {
  if (!threadId) return <p className="hint">Helpers used in this chat will appear here.</p>;
  return <InteractionStream threadId={threadId}>{stream => <HelperRailContent stream={stream} runs={runs} currentRunId={currentRunId} selectedHelperKey={selectedHelperKey} conversationId={conversationId} detailedStreams={detailedStreams} />}</InteractionStream>;
}
