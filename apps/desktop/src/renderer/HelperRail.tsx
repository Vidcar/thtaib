import { useMessages, useToolCalls } from "@langchain/react";
import { useEffect, useState } from "react";
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
  const runStart = Date.parse(currentRun?.events?.find(event => event.kind === "started")?.at ?? "");
  const allowDiscovery = !currentRun?.status || helperIsActive(currentRun.status);
  for (const run of runs) {
    for (const child of run.child_runs ?? []) {
      const id = child.tool_call_id || child.run_id;
      const snapshot = run.helper_snapshots?.find(item => item.agent_id === child.agent_id && item.version_id === child.version_id);
      const key = helperKey(run.id, id);
      entries.set(key, { key, runId: run.id, id, name: snapshot?.name ?? child.name, namespace: child.namespace, status: child.status, error: child.error });
    }
  }
  for (const discovered of currentRunId && allowDiscovery ? discoveries : []) {
    if (discovered.parentId) continue;
    if (Number.isFinite(runStart) && discovered.startedAt instanceof Date && discovered.startedAt.getTime() < runStart) continue;
    const key = helperKey(currentRunId!, discovered.id);
    const saved = entries.get(key);
    entries.set(key, {
      key,
      runId: currentRunId!,
      id: discovered.id,
      name: saved?.name ?? discovered.name,
      request: discovered.taskInput ?? saved?.request,
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
  const hasTranscript = messages.length > 0 || toolCalls.length > 0;
  const incompleteHistory = !helperIsActive(helper.status) && !hasTranscript;
  return <>
    {helper.error ? <p className="tool-call-error" role="status">{helper.error}</p> : null}
    {incompleteHistory ? <p className="hint">This earlier helper run has no recoverable public transcript.</p> : null}
    <AgentMessageFeed messages={messages} toolCalls={toolCalls} live={helperIsActive(helper.status)} detailedStreams={detailedStreams} sourceScope={{ sessionId: conversationId }} fallback={incompleteHistory ? null : <p className="hint" role="status">{helperIsActive(helper.status) ? "Helper is working…" : "No public helper messages were emitted."}</p>} />
  </>;
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
    {selected.request ? <p className="helper-rail-request">{selected.request}</p> : null}
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
