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
const retryable = (job: ImportJob) => ["stopped", "failed", "interrupted"].includes(job.status);
const needsAttention = (job: ImportJob) => retryable(job) || (job.status === "complete" && Boolean(job.configuration_error));
const stageNames: Record<string, string> = { queued: "Waiting", metadata: "Resolving files", transfer: "Downloading", verify: "Verifying", install: "Installing", repair: "Repairing", cleanup: "Cleaning up", done: "Complete" };

export function useImportJobs(revision: number, onCompleted: () => Promise<void>) {
  const [jobs, setJobs] = useState<ImportJob[]>([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState("");
  const actionPending = useRef(false);
  const completed = useRef(new Set<string>());
  const seeded = useRef(false);
  const onCompletedRef = useRef(onCompleted); onCompletedRef.current = onCompleted;

  useEffect(() => {
    let disposed = false, timer: number | undefined;
    async function load() {
      try {
        const next = await api.imports();
        if (disposed) return;
        setJobs(next); setError("");
        const newlyCompleted = seeded.current ? next.filter(job => job.status === "complete" && !completed.current.has(job.id)) : [];
        for (const job of next.filter(job => job.status === "complete")) completed.current.add(job.id);
        seeded.current = true;
        if (newlyCompleted.length) await onCompletedRef.current();
        if (!disposed && next.some(active)) timer = window.setTimeout(() => void load(), 1200);
      } catch (failure) {
        if (!disposed) { setError(errorMessage(failure)); timer = window.setTimeout(() => void load(), 4000); }
      }
    }
    void load();
    return () => { disposed = true; window.clearTimeout(timer); };
  }, [revision, busy]);

  async function action(job: ImportJob, operation: () => Promise<ImportJob>) {
    if (actionPending.current) return;
    actionPending.current = true;
    setBusy(job.id); setError("");
    try {
      const next = await operation();
      setJobs(current => next.status === "discarded"
        ? current.filter(item => item.id !== next.id)
        : current.map(item => item.id === next.id ? next : item));
    } catch (failure) { setError(errorMessage(failure)); }
    finally { actionPending.current = false; setBusy(""); }
  }

  return { jobs, error, busy, action, attentionCount: jobs.filter(job => active(job) || needsAttention(job)).length };
}

type ImportJobsState = ReturnType<typeof useImportJobs>;

export function ImportJobsPanel({ state, onOpenModel }: { state: ImportJobsState; onOpenModel?: (bundleId: string) => void }) {
  const { jobs, error, busy, action } = state;
  const [confirmDiscard, setConfirmDiscard] = useState("");
  const renderJob = (job: ImportJob) => {
    const total = job.progress?.bytes_total;
    const ratio = total != null && total > 0 ? Math.max(0, Math.min(1, (job.progress?.bytes_done ?? 0) / total)) : undefined;
    const status = job.status === "stopping" ? "Stopping…" : active(job) ? stageNames[job.progress?.stage ?? "queued"] ?? job.progress?.stage : ({ stopped: "Cancelled", failed: "Failed", interrupted: "Interrupted", complete: "Installed", discarded: "Discarded" }[job.status] ?? job.status);
    const name = job.display_name || job.repo_id || "Local import";
    return <li className="entity import-row" key={job.id}>
      <div className="import-row-head">
        <strong title={name}>{name}</strong>
        <span className="import-row-status hint" role="status">{status}</span>
        <div className="import-row-actions">
          {active(job) ? <button disabled={Boolean(busy) || (job.status === "stopping" && !job.error)} onClick={() => void action(job, () => api.cancelImport(job.id))}><Icon name="stop" size={14} />{job.status === "stopping" && job.error ? "Retry stop" : "Cancel"}</button> : null}
          {retryable(job) ? <><button disabled={Boolean(busy)} onClick={() => void action(job, () => api.retryImport(job.id))}><Icon name="refresh" size={14} />Retry</button><button disabled={Boolean(busy)} onClick={() => setConfirmDiscard(job.id)}><Icon name="trash" size={14} />Discard</button></> : null}
          {job.status === "complete" && job.configuration_error && job.bundle_id && onOpenModel ? <button type="button" onClick={() => onOpenModel(job.bundle_id!)}>Open model recipes</button> : null}
          {job.status === "discarded" ? <button disabled={Boolean(busy)} onClick={() => void action(job, () => api.discardImport(job.id))}>Clear</button> : null}
        </div>
      </div>
      {active(job) ? <progress aria-label={`${name}: ${status}`} max={1} value={ratio} /> : null}
      {active(job) && job.progress ? <div className="import-progress-summary hint"><span>{job.progress.message ?? "Preparing download…"}</span><span>{ratio !== undefined ? `${Math.round(ratio * 100)}% · ${formatBytes(job.progress.bytes_done)} / ${formatBytes(total!)}` : job.progress.files_total != null ? `${job.progress.files_done} / ${job.progress.files_total} files` : ""}</span></div> : null}
      {job.error && job.status !== "stopped" && job.status !== "discarded" ? <Notice tone="error">{job.error}</Notice> : null}
      {job.status === "complete" && job.configuration_error ? <Notice tone="warn">Model weights are installed. Its selected configurations need attention: {job.configuration_error}</Notice> : null}
      {confirmDiscard === job.id ? <ConfirmNote confirmLabel="Discard download" cancelLabel="Keep download" disabled={Boolean(busy)} cancelDisabled={false} onConfirm={() => { setConfirmDiscard(""); void action(job, () => api.discardImport(job.id)); }} onCancel={() => setConfirmDiscard("")}>Clear this stopped download and its eligible temporary files? Installed models, shared files and original local files stay.</ConfirmNote> : null}
      <details className="technical-details"><summary>Download details</summary><p className="hint">{name} · Job {job.id}{job.resolved_revision ? ` · revision ${job.resolved_revision}` : ""}{job.progress?.files_total != null ? ` · ${job.progress.files_done} / ${job.progress.files_total} files` : ""}</p></details>
    </li>;
  };
  const running = [...jobs].reverse().filter(active);
  const attention = [...jobs].reverse().filter(needsAttention);
  const history = [...jobs].reverse().filter(job => ["complete", "discarded"].includes(job.status) && !needsAttention(job));
  return <section className="card import-jobs" aria-label="Model downloads">
    <div className="setting-title"><h3>Downloads</h3><Help label="Downloads">Imports keep running when you leave this tab. Discard clears an incomplete job and only eligible temporary files; installed and shared files stay.</Help></div>
    {error ? <Notice tone="error">{error}</Notice> : null}
    {running.length ? <section><h4>In progress <span className="hint">{running.length}</span></h4><ul className="plain-list">{running.map(renderJob)}</ul></section> : null}
    {attention.length ? <section><h4>Needs attention <span className="hint">{attention.length}</span></h4><ul className="plain-list">{attention.map(renderJob)}</ul></section> : null}
    {!running.length && !attention.length ? <p className="hint">No downloads need attention.</p> : null}
    {history.length ? <details className="technical-details"><summary>Recent history <span>{history.length}</span></summary><ul className="plain-list">{history.map(renderJob)}</ul></details> : null}
  </section>;
}
