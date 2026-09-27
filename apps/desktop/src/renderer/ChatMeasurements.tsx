import { useSyncExternalStore } from "react";

import type { AgentRun } from "./types";
import { Icon } from "./Icon";
import { HoverHelp } from "./HoverHelp";
import "./ChatMeasurements.css";

type LiveMeasurement = {
  ownerKey: string;
  runId: string;
  status: AgentRun["status"];
  activityPhase: AgentRun["activity_phase"];
  finalizationPhase: AgentRun["finalization_phase"];
  waiting: boolean;
  generation: AgentRun["generation_observation"];
  history?: AgentRun["generation_history"];
  context: AgentRun["context_observation"];
};

let liveMeasurement: LiveMeasurement | null = null;
const measurementListeners = new Set<() => void>();

export function publishLiveMeasurement(next: LiveMeasurement | null): void {
  if (liveMeasurement?.ownerKey === next?.ownerKey && liveMeasurement?.runId === next?.runId
    && liveMeasurement?.status === next?.status && liveMeasurement?.activityPhase === next?.activityPhase
    && liveMeasurement?.finalizationPhase === next?.finalizationPhase && liveMeasurement?.waiting === next?.waiting
    && liveMeasurement?.generation === next?.generation && liveMeasurement?.history === next?.history && liveMeasurement?.context === next?.context) {
    return;
  }
  liveMeasurement = next;
  measurementListeners.forEach((listener) => listener());
}

function subscribeLiveMeasurement(listener: () => void): () => void {
  measurementListeners.add(listener);
  return () => measurementListeners.delete(listener);
}

export function ChatMeasurements({ run, ownerKey, starting = false, stopping = false }: {
  run?: AgentRun | null;
  ownerKey?: string;
  starting?: boolean;
  stopping?: boolean;
}) {
  const published = useSyncExternalStore(subscribeLiveMeasurement, () => liveMeasurement, () => liveMeasurement);
  const measurement = ownerKey && published?.ownerKey === ownerKey && published.runId === run?.id ? published : null;
  const generation = measurement ? measurement.generation : run?.generation_observation;
  const history = measurement?.history ?? run?.generation_history ?? [];
  const context = measurement ? measurement.context : run?.context_observation;
  const input = count(generation?.input_tokens);
  const output = count(generation?.output_tokens);
  const reported = count(generation?.context_used_tokens) ?? (input != null && output != null ? input + output : null);
  const used = reported ?? count(context?.estimated_input_tokens);
  const capacity = count(generation?.context_limit) || count(context?.capacity_tokens);
  const speed = typeof generation?.tokens_per_second === "number" && Number.isFinite(generation.tokens_per_second) && generation.tokens_per_second >= 0 ? generation.tokens_per_second : null;
  const lifecycle = measurement?.status ?? run?.status;
  const active = lifecycle === "running" || lifecycle === "cancel_requested";
  const phase = measurement ? measurement.activityPhase : run?.activity_phase;
  const finalizing = active && (measurement ? measurement.finalizationPhase : run?.finalization_phase) === "saving_changes";
  const waiting = measurement ? measurement.waiting : Boolean(run?.pending_interrupt);
  const stoppingNow = stopping || (active && !finalizing && lifecycle === "cancel_requested");
  const modelActive = active && !starting && !stoppingNow && !finalizing && !waiting && phase !== "summarizing" && phase !== "using_tools" && phase !== "checking_images";
  const live = modelActive && generation?.phase === "generating";
  const preparing = modelActive && generation?.phase === "prompt_processing";
  const stopped = generation?.phase === "interrupted";
  const estimated = reported == null && used != null;
  const percent = used != null && capacity ? used / capacity * 100 : null;
  const stage = stoppingNow ? "Stopping" : starting || lifecycle === "queued" ? "Starting" : finalizing ? "Saving"
    : active && waiting ? "Waiting" : active && phase === "summarizing" ? "Summarizing" : active && phase === "checking_images" ? "Checking image support"
    : active && phase === "using_tools" ? "Using tools" : live ? "Generating" : preparing ? "Preparing" : active ? "Working" : null;
  const status = stage ?? (stopped ? "Stopped" : generation ? "Last work request" : estimated ? "Estimated" : "Context");
  const nativeTiming = generation?.basis === "llama_cpp_timings";
  const announcement = stage === "Saving" ? "Saving project state" : stage ?? (stopped ? "Stopped" : "");

  return <span className="chat-measurements" data-estimated-input={context?.estimated_input_tokens ?? ""} data-tokens-per-second={speed ?? ""}>
    {announcement ? <span className="sr-only" role="status">{announcement}</span> : null}
    <HoverHelp title="Context and speed" placement="above" interactive={history.length > 0} triggerClassName="chat-usage-trigger" bubbleClassName="chat-usage-bubble"
      triggerContent={<><Icon name="activity" size={16} /><span>{stage ? `${stage}${live && speed != null ? ` · ${speed.toFixed(1)} tok/s` : ""}` : speed != null ? `${speed.toFixed(1)} tok/s` : "Context"}</span>{live ? <span className="usage-live-dot" aria-hidden="true" /> : null}</>}>
      <div className="usage-heading"><strong>Context</strong><span className={live ? "usage-state is-live" : "usage-state"}>{status}</span></div>
      <div className="usage-context-value"><span>{used != null ? `${used.toLocaleString()}${capacity ? ` / ${capacity.toLocaleString()}` : " tokens"}` : "Not reported"}</span>{percent != null ? <span>{percent < 1 && percent > 0 ? "<1" : Math.round(percent)}%</span> : null}</div>
      {percent != null ? <div className="usage-meter" aria-hidden="true"><span style={{ width: `${Math.min(100, percent)}%` }} /></div> : null}
      <p className="usage-caption">{estimated ? "Estimated input · awaiting model counts" : reported != null ? `Model-reported tokens · ${live || preparing ? "current" : "last"} request` : "Send a message to measure usage"}</p>
      {input != null || output != null ? <dl className="usage-token-counts">
        {input != null ? <div><dt>Input total</dt><dd>{input.toLocaleString()}</dd></div> : null}
        {count(generation?.cached_input_tokens) != null ? <div><dt>Cached input</dt><dd>{generation!.cached_input_tokens!.toLocaleString()}</dd></div> : null}
        {count(generation?.processed_input_tokens) != null ? <div><dt>Newly processed</dt><dd>{generation!.processed_input_tokens!.toLocaleString()}</dd></div> : null}
        {output != null ? <div><dt>Output</dt><dd>{output.toLocaleString()}</dd></div> : null}
      </dl> : null}
      {count(generation?.cached_input_tokens) != null || count(generation?.processed_input_tokens) != null ? <p className="usage-caption">Cached and newly processed tokens are parts of input total.</p> : null}
      {generation ? <dl className="usage-token-counts usage-timings">
        <div><dt>Prompt processing</dt><dd>{seconds(generation.prefill_seconds)}</dd></div>
        <div><dt>First output delay</dt><dd>{seconds(generation.time_to_first_token_seconds)}</dd></div>
      </dl> : null}
      {generation ? <p className="usage-caption">Prompt time is reported by the model. First output delay includes transport and prompt processing.</p> : null}
      {run?.housekeeping_generation?.summary ? <p className="usage-caption">Summarization measured separately: {run.housekeeping_generation.summary.input_tokens?.toLocaleString() ?? "?"} input / {run.housekeeping_generation.summary.output_tokens?.toLocaleString() ?? "?"} output tokens.</p> : null}
      {run?.project_outline?.included ? <p className="usage-caption">Partial project outline: approximately {String(run.project_outline.estimated_tokens)} input tokens.</p> : run?.project_outline?.omitted_for_capacity ? <p className="usage-caption">Optional project outline omitted to preserve room.</p> : null}
      <div className="usage-speed"><span>{live ? "Generation speed" : "Last request speed"}</span><strong>{speed != null ? `${speed.toFixed(1)} tok/s` : "Not reported"}</strong></div>
      {speed != null ? <p className="usage-caption">{nativeTiming ? stopped ? "Last reading before stopping · llama.cpp" : live ? "Current generation average · llama.cpp" : "Last request generation average · llama.cpp" : `${live ? "Current" : "Last request"} average · including prompt processing`}</p> : null}
      {history.length ? <details className="usage-history">
        <summary>Recent model calls ({history.length})</summary>
        <ol aria-label="Completed model call measurements" tabIndex={0}>
          {history.slice().reverse().map((call, index) => <li key={call.request_id ?? index}>
            <div className="usage-history-heading"><strong>{purposeLabel(call.purpose)} · {call.phase === "interrupted" ? "Stopped" : "Complete"}</strong><span title={call.request_id ?? undefined}>{call.request_id?.slice(0, 8) ?? "No request ID"}</span></div>
            <dl className="usage-token-counts">
              <div><dt>Cached input</dt><dd>{tokenCount(call.cached_input_tokens)}</dd></div>
              <div><dt>Newly processed</dt><dd>{tokenCount(call.processed_input_tokens)}</dd></div>
              <div><dt>Prompt processing</dt><dd>{seconds(call.prefill_seconds)}</dd></div>
              <div><dt>First output delay</dt><dd>{seconds(call.time_to_first_token_seconds)}</dd></div>
            </dl>
          </li>)}
        </ol>
      </details> : null}
    </HoverHelp>
  </span>;
}

function count(value: unknown): number | null {
  return typeof value === "number" && Number.isSafeInteger(value) && value >= 0 ? value : null;
}

function seconds(value: unknown): string {
  return typeof value === "number" && Number.isFinite(value) && value >= 0 ? `${value.toFixed(2)} s` : "Not reported";
}

function tokenCount(value: unknown): string {
  return count(value)?.toLocaleString() ?? "Not reported";
}

function purposeLabel(purpose: string): string {
  return ({ work: "Work", summary: "Summary", review: "Review", probe: "Image check" } as Record<string, string>)[purpose] ?? purpose;
}
