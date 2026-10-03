import type { AgentRun } from "./types";
import { Icon } from "./Icon";
import { HoverHelp } from "./HoverHelp";

export function helperApprovalOwner(run: AgentRun | null | undefined, namespace: string[]): string | undefined {
  if (!namespace.length) return undefined;
  return run?.child_runs?.find(child => child.namespace?.length && child.namespace.every((part, index) => namespace[index] === part))?.name;
}

export function RunActivitySummary({ run, showHelpers = true, onRecover }: { run?: AgentRun | null; showHelpers?: boolean; onRecover?: (run: AgentRun) => void }) {
  const children = showHelpers ? run?.child_runs ?? [] : [];
  const review = run?.review_observation;
  const evaluation = review?.evaluations?.at(-1);
  const gaps = evaluation?.criteria?.filter(item => !item.passed) ?? [];
  const reviewed = Boolean(review?.enabled && review.status !== "not_requested");
  const finished = run && !["queued", "running", "cancel_requested"].includes(run.status);
  const failure = finished && (run.failure?.message || run.error);
  const action = run?.failure?.recovery_action;
  const contextPoolFailure = run?.failure?.code === "context_pool_exhausted";
  const recoveryHint = action === "inspect_effects" || action === "ask" ? "Check the affected actions before continuing."
    : contextPoolFailure ? "Wait for other work to finish, or reduce Parallel in the model setup before retrying."
    : action === "change_limit" ? "Adjust the response or context limit before continuing."
    : action === "correct_setup" ? "Correct this chat's setup before continuing."
    : "Completed results are retained. You can continue in this chat.";
  if (!children.length && !reviewed && !failure) return null;
  return <div className="run-activity-summary">
    {failure ? <div className="run-failure" role="status"><p>{failure}</p>{onRecover && run ? <button type="button" onClick={() => onRecover(run)}>{action === "inspect_effects" || action === "ask" ? "Inspect effects" : contextPoolFailure ? "Review parallel setting" : action === "change_limit" ? "Change response limit" : action === "correct_setup" ? "Correct setup" : "Continue from results"}</button> : <small className="hint">{recoveryHint}</small>}</div> : null}
    {children.length ? <ul className="helper-activity" aria-label="Helper activity">{children.map(child => <li key={child.run_id}><Icon name="agent-run" size={14} /><strong>{child.name}</strong><span>{child.status}</span>{child.error ? <span className="tool-call-error">{child.error}</span> : null}</li>)}</ul> : null}
    {reviewed && review ? <details className="review-result" open={review.status === "max_iterations_reached" || undefined}><summary><Icon name="check" size={14} />{review.status === "satisfied" ? "Review passed" : review.status === "max_iterations_reached" ? "Review limit reached" : finished ? "Review incomplete" : "Review in progress"}<HoverHelp title="Review evidence">{review.evidence_scope || "A model review of the result. Executable checks are reported separately."}</HoverHelp></summary>{evaluation?.explanation ? <p>{evaluation.explanation}</p> : null}{gaps.length ? <ul>{gaps.map((gap, index) => <li key={`${gap.name}:${index}`}><strong>{gap.name}</strong>{gap.gap ? ` — ${gap.gap}` : " — unresolved"}</li>)}</ul> : null}<small className="hint">Up to {review.max_revisions} revisions</small></details> : null}
  </div>;
}
