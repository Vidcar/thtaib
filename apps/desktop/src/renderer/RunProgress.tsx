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
