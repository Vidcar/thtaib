import { useEffect, useRef, useState } from "react";
import { api } from "./api";
import { formatBytes } from "./display";
import { errorMessage } from "./errors";
import { Notice } from "./Notice";
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
  return <section className="card import-jobs" aria-label="Model installation progress"><h3>Model installations</h3>
    <p className="hint">You can leave this page and return while an import runs. Cancelling stops work; discarding removes only stopped, owned temporary files.</p>
    {error ? <Notice tone="error">{error}</Notice> : null}
    <ul className="plain-list">{[...jobs].reverse().map(job => <li className="entity" key={job.id}>
      <strong>{job.display_name || job.repo_id || "Local model import"}</strong>
      <p role="status">{job.status === "stopping" ? "Stopping — waiting for the worker to exit" : active(job) ? stageNames[job.progress?.stage ?? "queued"] ?? job.progress?.stage : job.status === "stopped" ? "Cancelled — incomplete files retained" : job.status}</p>
      {active(job) && job.progress?.message ? <p className="hint">{job.progress.message}</p> : null}
      {active(job) && job.progress?.files_total != null ? <p className="hint">{job.progress.files_done} of {job.progress.files_total} files in this stage</p> : null}
      {active(job) && job.progress?.bytes_total != null ? <p className="hint">{formatBytes(job.progress.bytes_done)} of {formatBytes(job.progress.bytes_total)} in this stage</p> : null}
      {job.error ? <Notice tone="error">{job.error}</Notice> : null}
      <div className="actions">
        {active(job) ? <button disabled={Boolean(busy) || (job.status === "stopping" && !job.error)} onClick={() => void action(job, () => api.cancelImport(job.id))}>{job.status === "stopping" && job.error ? "Try stopping again" : "Cancel download / import"}</button> : null}
        {["stopped", "interrupted", "failed"].includes(job.status) ? <><button disabled={Boolean(busy)} onClick={() => void action(job, () => api.retryImport(job.id))}>Retry same selection</button><button disabled={Boolean(busy)} onClick={() => setConfirmDiscard(job.id)}>Discard incomplete download</button></> : null}
      </div>
      {confirmDiscard === job.id ? <div className="inline-note"><p>Discard this stopped import’s eligible temporary files? Installed models and original local files are retained.</p><button disabled={Boolean(busy)} onClick={() => void action(job, () => api.discardImport(job.id))}>Confirm discard</button><button onClick={() => setConfirmDiscard("")}>Keep files</button></div> : null}
      <details className="technical-details"><summary>Import details</summary><p>Job: <code>{job.id}</code></p><p>Recorded revision: <code>{job.resolved_revision ?? "Not yet resolved"}</code></p></details>
    </li>)}</ul>
  </section>;
}
