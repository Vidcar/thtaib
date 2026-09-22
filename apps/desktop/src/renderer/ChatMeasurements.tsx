import type { AgentRun } from "./types";
import { Icon } from "./Icon";
import { HoverHelp } from "./HoverHelp";

export function ChatMeasurements({ run }: { run?: AgentRun | null }) {
  const generation = run?.generation_observation;
  const context = run?.context_observation;
  const speed = generation?.tokens_per_second;
  const used = context?.estimated_input_tokens;
  const capacity = context?.capacity_tokens;
  return <details className="composer-menu chat-measurements">
    <summary title={used != null && capacity ? `Estimated context: ${Math.round(used / capacity * 100)}% · ${used.toLocaleString()} / ${capacity.toLocaleString()} tokens` : "Context and generation measurements"}><Icon name="activity" size={16} /><span>{speed != null ? `${speed.toFixed(1)} tok/s` : "Usage"}</span></summary>
    <div className="composer-popover">
      <h3>Context & usage <HoverHelp title="About usage">Context is an estimate for the latest prepared request. Token counts are reported by the model. Speed includes prompt processing for the last completed call.</HoverHelp></h3>
      <dl className="settings-readout">
        <div><dt>Estimated context</dt><dd>{used != null ? `${used.toLocaleString()}${capacity ? ` / ${capacity.toLocaleString()}` : " tokens"}` : "Not reported"}</dd></div>
        <div><dt>Input tokens</dt><dd>{generation?.input_tokens?.toLocaleString() ?? "Not reported"}</dd></div>
        <div><dt>Output tokens</dt><dd>{generation?.output_tokens?.toLocaleString() ?? "Not reported"}</dd></div>
        <div><dt>Last call</dt><dd>{speed != null ? `${speed.toFixed(1)} tok/s` : "Not reported"}</dd></div>
      </dl>
    </div>
  </details>;
}
