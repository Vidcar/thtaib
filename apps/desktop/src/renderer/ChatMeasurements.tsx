import type { AgentRun } from "./types";
import { Icon } from "./Icon";

export function ChatMeasurements({ run }: { run?: AgentRun | null }) {
  const generation = run?.generation_observation;
  const context = run?.context_observation;
  const speed = generation?.tokens_per_second;
  return <details className="composer-menu chat-measurements">
    <summary title="Context and generation measurements"><Icon name="activity" size={18} /><span>{speed != null ? `${speed.toFixed(1)} tok/s` : "Usage"}</span></summary>
    <div className="composer-popover">
      <h3>Latest turn measurements</h3>
      <p>{generation?.input_tokens != null ? `${generation.input_tokens.toLocaleString()} input tokens reported by the model.` : "Input token count has not been reported."}</p>
      <p>{generation?.output_tokens != null ? `${generation.output_tokens.toLocaleString()} output tokens reported by the model.` : "Output token count has not been reported."}</p>
      <p>{context ? `Estimated input: ${context.estimated_input_tokens.toLocaleString()} tokens${context.capacity_tokens != null ? ` of ${context.capacity_tokens.toLocaleString()} context capacity` : "; capacity is not reported"}.` : "Context estimate is available after a model request is prepared."}</p>
      <p className="hint">{speed != null ? `${speed.toFixed(1)} tokens/second for the last completed model call, including prompt processing. This is a completed observation, not live generation speed.` : "Generation speed will appear when the model reports token usage for a completed call."}</p>
    </div>
  </details>;
}
