import { useEffect, useRef, useState } from "react";
import { api } from "./api";
import { formatBytes } from "./display";
import { errorMessage } from "./errors";
import { Notice } from "./Notice";
import { Help } from "./ModelControls";
import { Icon } from "./Icon";
import type { ImportJob } from "./types";

const active = (job: ImportJob) => ["pending", "running", "stopping"].includes(job.status);
const stageNames: Record<string, string> = { queued: "Waiting", metadata: "Resolving selected files", transfer: "Downloading", verify: "Verifying files", install: "Installing", repair: "Repairing", cleanup: "Cleaning up", done: "Complete" };

export function ImportJobsPanel({ revision, onCompleted }: { revision: number; onCompleted: () => Promise<void> }) {
  const [jobs, setJobs] = useState<ImportJob[]>([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState("");
  const [confirmDiscard, setConfirmDiscard] = useState("");
  const completed = useRef(new Set<string>());
  const onCompletedRef = useRef(onCompleted); onCompletedRef.current = onCompleted;

  useEffect(() => {
    let disposed = false, timer: number | undefined;
    async function load() {
      try {
        const next = await api.imports();
        if (disposed) return;
        setJobs(next); setError("");
        const newlyCompleted = next.filter(job => job.status === "complete" && !completed.current.has(job.id));
        for (const job of newlyCompleted) completed.current.add(job.id);
        if (newlyCompleted.length) await onCompletedRef.current();
        if (!disposed && next.some(active)) timer = window.setTimeout(() => void load(), 1200);
      } catch (failure) { if (!disposed) { setError(errorMessage(failure)); timer = window.setTimeout(() => void load(), 4000); } }
    }
    void load();
    return () => { disposed = true; window.clearTimeout(timer); };
  }, [revision, busy]);

  async function action(job: ImportJob, operation: () => Promise<ImportJob>) {
    setBusy(job.id); setError("");
    try { await operation(); setConfirmDiscard(""); } catch (failure) { setError(errorMessage(failure)); } finally { setBusy(""); }
  }
  if (!jobs.length && !error) return null;
  const renderJob = (job: ImportJob) => <li className="entity import-row" key={job.id}>
      <div className="section-heading"><strong>{job.display_name || job.repo_id || "Local import"}</strong>
      <span className="hint" role="status">{job.status === "stopping" ? "Stopping…" : active(job) ? stageNames[job.progress?.stage ?? "queued"] ?? job.progress?.stage : job.status === "stopped" ? "Cancelled" : job.status}</span></div>
      {active(job) && job.progress?.message ? <p className="hint">{job.progress.message}</p> : null}
      {active(job) && job.progress?.files_total != null ? <p className="hint">{job.progress.files_done} of {job.progress.files_total} files in this stage</p> : null}
      {active(job) && job.progress?.bytes_total != null ? <p className="hint">{formatBytes(job.progress.bytes_done)} of {formatBytes(job.progress.bytes_total)} in this stage</p> : null}
      {job.error ? <Notice tone="error">{job.error}</Notice> : null}
      <div className="actions">
        {active(job) ? <button disabled={Boolean(busy) || (job.status === "stopping" && !job.error)} onClick={() => void action(job, () => api.cancelImport(job.id))}><Icon name="stop" size={14} />{job.status === "stopping" && job.error ? "Retry stop" : "Cancel"}</button> : null}
        {["stopped", "interrupted", "failed"].includes(job.status) ? <><button disabled={Boolean(busy)} onClick={() => void action(job, () => api.retryImport(job.id))}><Icon name="refresh" size={14} />Retry</button><button disabled={Boolean(busy)} onClick={() => setConfirmDiscard(job.id)}><Icon name="trash" size={14} />Discard</button></> : null}
      </div>
      {confirmDiscard === job.id ? <div className="inline-note"><p>Discard this stopped import’s eligible temporary files? Installed models and original local files are retained.</p><button disabled={Boolean(busy)} onClick={() => void action(job, () => api.discardImport(job.id))}>Confirm discard</button><button onClick={() => setConfirmDiscard("")}>Keep files</button></div> : null}
      {job.resolved_revision ? <span className="hint" title={`Job ${job.id} · revision ${job.resolved_revision}`}>Revision {job.resolved_revision.slice(0, 8)}</span> : null}
    </li>;
  const ongoing = [...jobs].reverse().filter(job => !["complete", "discarded"].includes(job.status));
  const history = [...jobs].reverse().filter(job => ["complete", "discarded"].includes(job.status));
  return <section className="card import-jobs" aria-label="Model installation progress"><div className="setting-title"><h3>Downloads</h3><Help label="Downloads">Imports continue when you leave this page. Cancel stops work; discard removes only stopped temporary files.</Help></div>
    {error ? <Notice tone="error">{error}</Notice> : null}
    {ongoing.length ? <ul className="plain-list">{ongoing.map(renderJob)}</ul> : null}
    {history.length ? <details className="technical-details"><summary>Completed <span>{history.length}</span></summary><ul className="plain-list">{history.map(renderJob)}</ul></details> : null}
  </section>;
}
