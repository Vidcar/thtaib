import { useEffect, useRef, useState } from "react";
import { api } from "./api";
import { formatBytes } from "./display";
import { errorMessage } from "./errors";
import { ConfirmNote } from "./ConfirmNote";
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
  const actionPending = useRef(false);
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
    if (actionPending.current) return;
    actionPending.current = true;
    setBusy(job.id); setError("");
    try { const next = await operation(); setJobs(current => current.map(item => item.id === next.id ? next : item)); setConfirmDiscard(""); } catch (failure) { setError(errorMessage(failure)); } finally { actionPending.current = false; setBusy(""); }
  }
  if (!jobs.length && !error) return null;
  const renderJob = (job: ImportJob) => {
    const total = job.progress?.bytes_total;
    const ratio = total != null && total > 0 ? Math.max(0, Math.min(1, (job.progress?.bytes_done ?? 0) / total)) : undefined;
    const status = job.status === "stopping" ? "Stopping…" : active(job) ? stageNames[job.progress?.stage ?? "queued"] ?? job.progress?.stage : ({ stopped: "Cancelled", failed: "Failed", interrupted: "Interrupted", complete: "Installed", discarded: "Discarded" }[job.status] ?? job.status);
    return <li className="entity import-row" key={job.id}>
      <div className="section-heading"><strong>{job.display_name || job.repo_id || "Local import"}</strong>
      <span className="hint" role="status">{status}</span></div>
      {active(job) ? <progress aria-label={`${job.display_name || job.repo_id || "Model"}: ${status}`} max={1} value={ratio} /> : null}
      {active(job) && job.progress ? <div className="import-progress-summary hint"><span>{job.progress.message ?? "Preparing download…"}</span><span>{ratio !== undefined ? `${Math.round(ratio * 100)}% · ${formatBytes(job.progress.bytes_done)} / ${formatBytes(total!)}` : job.progress.files_total != null ? `${job.progress.files_done} / ${job.progress.files_total} files` : ""}</span></div> : null}
      {job.error ? <Notice tone="error">{job.error}</Notice> : null}
      <div className="actions">
        {active(job) ? <button disabled={Boolean(busy) || (job.status === "stopping" && !job.error)} onClick={() => void action(job, () => api.cancelImport(job.id))}><Icon name="stop" size={14} />{job.status === "stopping" && job.error ? "Retry stop" : "Cancel"}</button> : null}
        {["stopped", "interrupted", "failed"].includes(job.status) ? <><button disabled={Boolean(busy)} onClick={() => void action(job, () => api.retryImport(job.id))}><Icon name="refresh" size={14} />Retry</button><button disabled={Boolean(busy)} onClick={() => setConfirmDiscard(job.id)}><Icon name="trash" size={14} />Discard</button></> : null}
      </div>
      {confirmDiscard === job.id ? <ConfirmNote confirmLabel="Confirm discard" cancelLabel="Keep files" disabled={Boolean(busy)} cancelDisabled={false} onConfirm={() => void action(job, () => api.discardImport(job.id))} onCancel={() => setConfirmDiscard("")}>Discard this stopped import’s eligible temporary files? Installed models and original local files are retained.</ConfirmNote> : null}
      <details className="technical-details"><summary>Download details</summary><p className="hint">Job {job.id}{job.resolved_revision ? ` · revision ${job.resolved_revision}` : ""}{job.progress?.files_total != null ? ` · ${job.progress.files_done} / ${job.progress.files_total} files` : ""}</p></details>
    </li>;
  };
  const ongoing = [...jobs].reverse().filter(job => !["complete", "discarded"].includes(job.status));
  const history = [...jobs].reverse().filter(job => ["complete", "discarded"].includes(job.status));
  return <section className="card import-jobs" aria-label="Model installation progress"><div className="setting-title"><h3>Downloads</h3><Help label="Downloads">Imports continue when you leave this page. Cancel stops work; discard removes only stopped temporary files.</Help></div>
    {error ? <Notice tone="error">{error}</Notice> : null}
    {ongoing.length ? <ul className="plain-list">{ongoing.map(renderJob)}</ul> : null}
    {history.length ? <details className="technical-details"><summary>Download history <span>{history.length}</span></summary><ul className="plain-list">{history.map(renderJob)}</ul></details> : null}
  </section>;
}
