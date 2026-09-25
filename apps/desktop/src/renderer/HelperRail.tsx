import { useMessages, useToolCalls } from "@langchain/react";
import { useEffect, useState } from "react";
import { api } from "./api";
import { AgentMessageFeed } from "./AgentMessageFeed";
import { InteractionStream, type WorkbenchStream } from "./InteractionStream";
import type { AgentRun } from "./types";

type ChildRun = NonNullable<AgentRun["child_runs"]>[number];

function HelperTranscript({ stream, child }: { stream: WorkbenchStream; child: ChildRun }) {
  const messages = useMessages(stream, child.namespace);
  const toolCalls = useToolCalls(stream, child.namespace);
  return <AgentMessageFeed messages={messages} toolCalls={toolCalls} live={["queued", "running", "working"].includes(child.status)} fallback={<p className="hint">{child.status === "working" ? "Helper is working…" : "No helper transcript is available yet."}</p>} />;
}

export function HelperRail({ run, runIds, threadId }: { run: AgentRun | null | undefined; runIds: string[]; threadId: string | null }) {
  const [earlierRuns, setEarlierRuns] = useState<AgentRun[]>([]);
  const earlierIds = runIds.filter(id => id !== run?.id).join("|");
  useEffect(() => {
    setEarlierRuns([]);
    if (!threadId || !earlierIds) return;
    let cancelled = false;
    void Promise.allSettled(earlierIds.split("|").map(id => api.agentRun(id))).then(results => {
      if (!cancelled) setEarlierRuns(results.flatMap(result => result.status === "fulfilled" ? [result.value] : []));
    });
    return () => { cancelled = true; };
  }, [threadId, earlierIds]);
  const children = [...new Map([...earlierRuns, ...(run ? [run] : [])].flatMap(item => item.child_runs ?? []).map(child => [child.run_id, child])).values()];
  const [selectedId, setSelectedId] = useState("");
  const selected = children.find(child => child.run_id === selectedId) ?? children.at(-1);
  if (!children.length) return <p className="hint">Helpers used in this chat will appear here.</p>;
  return <div className="helper-rail">
    <div className="helper-rail-list" role="tablist" aria-label="Helper runs">
      {children.map(child => <button type="button" role="tab" aria-selected={selected?.run_id === child.run_id} key={child.run_id} onClick={() => setSelectedId(child.run_id)}><strong>{child.name}</strong><span>{child.status}</span></button>)}
    </div>
    {selected?.error ? <p className="tool-call-error">{selected.error}</p> : null}
    {threadId && selected ? <InteractionStream threadId={threadId}>{stream => <HelperTranscript key={selected.run_id} stream={stream} child={selected} />}</InteractionStream> : null}
  </div>;
}
