import type { AgentRun } from "./types";
import { Icon } from "./Icon";
import { HoverHelp } from "./HoverHelp";
import "./ChatMeasurements.css";

export function ChatMeasurements({ run }: { run?: AgentRun | null }) {
  const generation = run?.generation_observation;
  const context = run?.context_observation;
  const input = count(generation?.input_tokens);
  const output = count(generation?.output_tokens);
  const reported = count(generation?.context_used_tokens) ?? (input != null && output != null ? input + output : null);
  const used = reported ?? count(context?.estimated_input_tokens);
  const capacity = count(generation?.context_limit) || count(context?.capacity_tokens);
  const speed = typeof generation?.tokens_per_second === "number" && Number.isFinite(generation.tokens_per_second) && generation.tokens_per_second >= 0 ? generation.tokens_per_second : null;
  const live = generation?.phase === "generating";
  const preparing = generation?.phase === "prompt_processing";
  const stopped = generation?.phase === "interrupted";
  const estimated = reported == null && used != null;
  const percent = used != null && capacity ? used / capacity * 100 : null;
  const status = live ? "Live" : preparing ? "Preparing" : stopped ? "Stopped" : generation ? "Last request" : estimated ? "Estimated" : "Context";
  const nativeTiming = generation?.basis === "llama_cpp_timings";

  return <span className="chat-measurements">
    <HoverHelp title="Context and speed" placement="above" triggerClassName="chat-usage-trigger" bubbleClassName="chat-usage-bubble"
      triggerContent={<><Icon name="activity" size={16} /><span>{speed != null ? `${speed.toFixed(1)} tok/s` : preparing ? "Preparing" : "Context"}</span>{live ? <span className="usage-live-dot" aria-hidden="true" /> : null}</>}>
      <div className="usage-heading"><strong>Context</strong><span className={live ? "usage-state is-live" : "usage-state"}>{status}</span></div>
      <div className="usage-context-value"><span>{used != null ? `${used.toLocaleString()}${capacity ? ` / ${capacity.toLocaleString()}` : " tokens"}` : "Not reported"}</span>{percent != null ? <span>{percent < 1 && percent > 0 ? "<1" : Math.round(percent)}%</span> : null}</div>
      {percent != null ? <div className="usage-meter" aria-hidden="true"><span style={{ width: `${Math.min(100, percent)}%` }} /></div> : null}
      <p className="usage-caption">{estimated ? "Estimated input · awaiting model counts" : reported != null ? "Model-reported tokens · latest request" : "Send a message to measure usage"}</p>
      {input != null || output != null ? <dl className="usage-token-counts">
        {input != null ? <div><dt>Input</dt><dd>{input.toLocaleString()}</dd></div> : null}
        {output != null ? <div><dt>Output</dt><dd>{output.toLocaleString()}</dd></div> : null}
      </dl> : null}
      <div className="usage-speed"><span>{live ? "Generating" : preparing ? "Processing prompt" : "Speed"}</span><strong>{speed != null ? `${speed.toFixed(1)} tok/s` : "—"}</strong></div>
      {speed != null ? <p className="usage-caption">{nativeTiming ? stopped ? "Last reading before stopping" : live ? "Current generation average · llama.cpp" : "Generation average · llama.cpp" : "Including prompt processing"}</p> : null}
    </HoverHelp>
  </span>;
}

function count(value: unknown): number | null {
  return typeof value === "number" && Number.isSafeInteger(value) && value >= 0 ? value : null;
}
