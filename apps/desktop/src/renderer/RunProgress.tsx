import { formatWhen, eventDetailSummary, relatedFileLabel } from "./display";
import { eventKindLabel } from "./labels";
import { EffectiveSetupNotes } from "./settingsNotes";
import { StatusBadge } from "./StatusBadge";
import { isAgentRunLive, type AgentRun } from "./types";

export function RunProgress(props: {
  run: AgentRun | null;
  title?: string;
  onCancel?: () => void;
  cancelBusy?: boolean;
}) {
  const { run, title, onCancel, cancelBusy } = props;
  if (!run) {
    return null;
  }
  const live = isAgentRunLive(run.status);
  const retrieved = run.retrieved_material ?? [];
  const related = run.related_files ?? [];
  const context = run.context_observation;
  const structured = run.structured_output;
  const contextFit = context?.fits === true
    ? "Estimate fits observed capacity"
    : context?.fits === false
      ? "Estimate exceeds observed capacity"
      : "Capacity fit is unknown";
  const structuredStrategy = structured?.strategy === "provider"
    ? "Provider strategy"
    : structured?.strategy === "tool"
      ? "Tool strategy"
      : "Not selected";
  const validationStatus = structured?.validation_status ?? "not_requested";

  return (
    <div className="run-progress">
      <div className="run-progress-head">
        <h3>
          {title ?? "Run"}
          <StatusBadge status={run.status} />
        </h3>
        {onCancel ? (
          <button type="button" disabled={!live || cancelBusy} onClick={onCancel}>
            {run.status === "cancel_requested" ? "Stopping…" : "Cancel"}
          </button>
        ) : null}
      </div>
      <p className="hint">
        {run.stop_reason ? `Stop reason: ${run.stop_reason}. ` : null}
        {run.host_shell?.available
          ? `Host shell cwd ${run.host_shell.cwd ?? "(bound project)"}. No isolation.`
          : "Host shell unavailable (no project folder)."}
      </p>
      {run.error ? <p className="notice notice-error">{run.error}</p> : null}
      {run.effective_setup ? (
        <EffectiveSetupNotes
          unsupportedStartup={run.effective_setup.unsupported?.startup}
          retiredStartup={run.effective_setup.retired?.startup}
          startupMismatches={run.effective_setup.startup_mismatches}
          gaps={run.effective_setup.gaps}
        />
      ) : null}
      {run.effective_setup?.retrieval_requested ? (
        <p className="hint">
          Retrieval {run.effective_setup.retrieval_presented ? "presented" : "requested but not presented"}
          {run.effective_setup.retrieval_corpus_documents != null
            ? ` · ${run.effective_setup.retrieval_corpus_documents} documents`
            : ""}
        </p>
      ) : null}
      {context || structured ? (
        <details className="run-inspection">
          <summary>Request and model details</summary>
          {context ? (
            <section aria-label="Context estimate">
              <h4>Context estimate</h4>
              <p className="hint">
                {context.capacity_tokens == null
                  ? "Observed context capacity: unknown"
                  : `Observed context capacity: ${context.capacity_tokens.toLocaleString()} tokens`}
                {context.capacity_source === "server_props.n_ctx" ? " (reported by the running model server)" : ""}
              </p>
              <ul className="plain-list">
                <li>Estimated input: {context.estimated_input_tokens.toLocaleString()} tokens</li>
                <li>Safety margin: {context.margin_tokens.toLocaleString()} tokens</li>
                <li>Reserved for output: {context.output_reservation_tokens.toLocaleString()} tokens</li>
                <li>{contextFit}</li>
              </ul>
              <p className="hint">Estimate method: {context.counting_method}</p>
              {context.notes.map((note, index) => <p className="hint" key={`${index}-${note}`}>{note}</p>)}
            </section>
          ) : null}
          {structured ? (
            <section aria-label="Structured output result">
              <h4>Structured result</h4>
              <p className="hint">
                Schema: {structured.schema_name} · Strategy: {structuredStrategy} · Validation: {validationStatus}
              </p>
              <p className="hint">This value is separate from the assistant’s written reply.</p>
              <h5>Requested schema</h5>
              <pre>{JSON.stringify(structured.requested_json_schema, null, 2)}</pre>
              <h5>Structured value</h5>
              {structured.result == null
                ? <p className="hint">No structured value was returned.</p>
                : <pre>{JSON.stringify(structured.result, null, 2)}</pre>}
              {structured.error ? <p className="notice notice-warn">{structured.error}</p> : null}
            </section>
          ) : null}
        </details>
      ) : null}
      {run.events.length === 0 ? (
        <p className="hint">{live ? "Waiting for the first event…" : "No events recorded."}</p>
      ) : (
        <ol className="timeline">
          {run.events.map((event, index) => {
            const summary = eventDetailSummary(event.kind, event.detail);
            return (
              <li key={`${event.at}-${event.kind}-${index}`}>
                <span className="timeline-kind">{eventKindLabel(event.kind)}</span>
                <span className="timeline-when">{formatWhen(event.at)}</span>
                {summary ? <p className="timeline-detail">{summary}</p> : null}
              </li>
            );
          })}
        </ol>
      )}
      {retrieved.length > 0 ? (
        <div>
          <h4>Retrieved</h4>
          <ul className="plain-list">
            {retrieved.map((item) => (
              <li key={item}>
                <code>{item}</code>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
      {related.length > 0 ? (
        <div>
          <h4>Related files</h4>
          <ul className="plain-list">
            {related.map((item) => (
              <li key={`${item.kind}:${item.path}`}>
                {relatedFileLabel(item.kind)} · <code>{item.path}</code>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  );
}
