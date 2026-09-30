import { formatBytes } from "./display";
import type { ImportJob } from "./types";
import type { ReactNode } from "react";

export function ImportJobDetails({ job, children }: { job: ImportJob; children?: ReactNode }) {
  const progress = job.progress;
  return <details className="models-job-details"><summary>{job.display_name ?? job.repo_id ?? "Local import"} · {job.status} · details</summary>
    {job.error ? <p className="models-job-error" role="status">{job.error}</p> : null}
    {job.configuration_error ? <p role="status">Model files installed; selected setups need attention: {job.configuration_error}</p> : null}
    {progress ? <p>{progress.message ?? progress.stage} · {formatBytes(progress.bytes_done)}{progress.bytes_total != null ? " / " + formatBytes(progress.bytes_total) : ""} · {progress.files_done}{progress.files_total != null ? " / " + progress.files_total : ""} files</p> : null}
    <p>{job.repo_id ?? job.source_path ?? "Local files"} · {job.resolved_revision ?? job.requested_revision ?? "Local source"}</p>
    <ul className="plain-list">{job.allow_patterns?.map(file => <li key={file}>{file}</li>)}</ul>
    {job.recipe_ids?.length ? <p>Selected model-card setups: {job.recipe_ids.join(", ")}</p> : null}
    <p>Job {job.id}{job.retry_of ? " · retry of " + job.retry_of : ""}{job.updated_at ? " · " + new Date(job.updated_at).toLocaleString() : ""}</p>{children}
  </details>;
}
