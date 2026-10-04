import { useEffect, useRef, useState } from "react";
import type { AgentRun } from "./types";
import type { WorkbenchStream } from "./InteractionStream";
import { errorMessage } from "./errors";
import { InteractionCommandError } from "./interactionResume";

export interface InteractionSubmission<P> {
  id: string;
  threadId: string;
  ownerKey: string;
  observationOnly?: boolean;
  source: P;
  input: Parameters<WorkbenchStream["submit"]>[0];
  options: Parameters<WorkbenchStream["submit"]>[1];
}

type SubmissionPhase = "awaiting" | "uncertain" | "accepted" | "rejected";
interface SubmissionRecord<P> {
  request: InteractionSubmission<P>;
  phase: SubmissionPhase;
  dispatched: boolean;
  observed: boolean;
  acceptedNotified: boolean;
  error?: unknown;
  errors: Set<unknown>;
  checks: number;
  operation: number;
}

interface SubmissionOptions<P, V> {
  pending: InteractionSubmission<P> | null;
  ownerKey: string;
  isCurrentOwner: () => boolean;
  read: () => Promise<V>;
  hasAccepted: (view: V, inputId: string) => boolean;
  runInView: (view: V) => AgentRun | null | undefined;
  projectedView: (run: AgentRun, pending: P) => V | null;
  onAccepted: (pending: P, view: V) => void;
  onRejected: (pending: P, error: unknown) => void;
  onFailure: (error: unknown) => void;
  refreshObservation: () => void;
}

export interface InteractionSubmissionController {
  submit: (stream: WorkbenchStream) => void;
  observe: (run: AgentRun) => void;
  onError: (error: unknown) => void;
  recovery: { busy: boolean; checkAgain: () => void; retryOriginal: () => void } | null;
}

/** Application admission/draft recovery only. Native SDK owns live observation. */
export function useInteractionSubmission<P, V>(options: SubmissionOptions<P, V>): InteractionSubmissionController {
  const latest = useRef(options);
  latest.current = options;
  const record = useRef<SubmissionRecord<P> | null>(null);
  const streamRef = useRef<WorkbenchStream | null>(null);
  const mounted = useRef(true);
  const [, render] = useState(0);
  const [busy, setBusy] = useState(false);
  const busyRef = useRef(false);
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const stable = useRef<InteractionSubmissionController | null>(null);

  function current(item: SubmissionRecord<P>): boolean {
    return mounted.current && record.current === item && latest.current.ownerKey === item.request.ownerKey && latest.current.isCurrentOwner()
      && (!latest.current.pending || latest.current.pending.id === item.request.id);
  }
  function changed(): void { if (mounted.current) render(value => value + 1); }
  function stopTimer(): void { if (timer.current !== undefined) clearTimeout(timer.current); timer.current = undefined; }
  function ensure(): SubmissionRecord<P> | null {
    const pending = latest.current.pending;
    if (!pending) return record.current;
    if (record.current?.request.id === pending.id && record.current.request.ownerKey === pending.ownerKey) return record.current;
    stopTimer();
    record.current = { request: structuredClone(pending), phase: pending.observationOnly ? "uncertain" : "awaiting", dispatched: Boolean(pending.observationOnly), observed: false,
      acceptedNotified: false, errors: new Set(), checks: 0, operation: 0 };
    if (pending.observationOnly) { changed(); schedule(record.current, 1000); }
    return record.current;
  }
  function accept(item: SubmissionRecord<P>, view: V): void {
    if (!current(item)) return;
    item.phase = "accepted";
    stopTimer();
    if (!item.acceptedNotified) {
      item.acceptedNotified = true;
      latest.current.onAccepted(item.request.source, view);
    }
    const run = latest.current.runInView(view);
    if (run?.input_message_id === item.request.id && run.status === "failed") {
      latest.current.onFailure(new Error(run.error ?? (item.error ? errorMessage(item.error) : "The task failed.")));
    } else if (item.error && !item.observed) {
      latest.current.refreshObservation();
    }
    changed();
  }
  function denied(error: unknown): boolean {
    return error instanceof InteractionCommandError && error.status >= 400 && error.status < 500
      && Boolean(error.code) && error.code !== "duplicate_input" && error.code !== "input_identity_conflict"
      && error.code !== "submission_identity_conflict";
  }
  function schedule(item: SubmissionRecord<P>, delay = 5000): void {
    if (!current(item) || item.phase === "accepted" || item.phase === "rejected") return;
    if (timer.current !== undefined) return;
    if (item.checks >= 6) { item.phase = "uncertain"; changed(); return; }
    timer.current = setTimeout(() => { timer.current = undefined; void reconcile(item); }, delay);
  }
  async function reconcile(item: SubmissionRecord<P>): Promise<"accepted" | "rejected" | "unknown"> {
    if (!current(item)) return "unknown";
    item.checks += 1;
    const operation = ++item.operation;
    try {
      const view = await latest.current.read();
      if (!current(item) || item.operation !== operation) return "unknown";
      if (latest.current.hasAccepted(view, item.request.id)) { accept(item, view); return "accepted"; }
      if (item.error && denied(item.error)) {
        item.phase = "rejected";
        stopTimer();
        latest.current.onRejected(item.request.source, item.error);
        changed();
        return "rejected";
      }
    } catch { /* An unavailable or empty observation never proves rejection. */ }
    if (current(item) && item.operation === operation) {
      if (item.error || item.checks >= 6) item.phase = "uncertain";
      changed();
      schedule(item);
    }
    return "unknown";
  }
  function submissionError(item: SubmissionRecord<P>, error: unknown): void {
    if (!current(item) || item.errors.has(error)) return;
    if (error instanceof InteractionCommandError && (error.threadId !== item.request.threadId || error.inputId !== item.request.id)) return;
    item.errors.add(error);
    item.error = error;
    if (item.phase !== "accepted") item.phase = "uncertain";
    changed();
    void reconcile(item);
  }
  function dispatch(item: SubmissionRecord<P>, stream: WorkbenchStream): void {
    if (!current(item) || item.dispatched) return;
    item.dispatched = true;
    item.phase = "awaiting";
    item.checks = 0;
    stopTimer();
    changed();
    schedule(item, 1000);
    // submit resolves for some errors; only authoritative admission clears drafts.
    void stream.submit(item.request.input, { ...item.request.options, onError: error => submissionError(item, error) })
      .catch(error => submissionError(item, error));
  }
  async function recover(retry: boolean): Promise<void> {
    const item = record.current;
    if (!item || !current(item) || busyRef.current) return;
    busyRef.current = true;
    setBusy(true);
    try {
      item.checks = 0;
      const result = await reconcile(item);
      if (!current(item) || result === "accepted" || !retry) return;
      const stream = streamRef.current;
      if (!stream || stream.threadId !== item.request.threadId) return;
      // Explicit retries retain the exact captured input/configuration, even if
      // the editor now contains another draft. Backend admission deduplicates it.
      item.dispatched = false;
      item.error = undefined;
      dispatch(item, stream);
    } finally { busyRef.current = false; if (mounted.current) setBusy(false); }
  }

  if (!stable.current) stable.current = {
    submit(stream) { streamRef.current = stream; const item = ensure(); if (item) dispatch(item, stream); },
    observe(run) {
      const item = ensure();
      if (!item || !current(item) || run.input_message_id !== item.request.id) return;
      if (item.phase === "accepted" && item.observed) return;
      item.observed = true;
      const view = latest.current.projectedView(run, item.request.source);
      if (view) accept(item, view); else void reconcile(item);
    },
    onError(error) {
      const item = record.current;
      if (item?.errors.has(error)) return;
      if (error instanceof InteractionCommandError && error.inputId && (!item || error.inputId !== item.request.id || error.threadId !== item.request.threadId)) return;
      if (error instanceof InteractionCommandError && !error.inputId) {
        latest.current.onFailure(error); return;
      }
      if (item && current(item) && (item.phase !== "accepted" || error instanceof InteractionCommandError)) submissionError(item, error);
      else latest.current.onFailure(error);
    },
    recovery: null,
  };
  const item = record.current;
  stable.current.recovery = item && current(item) && item.phase === "uncertain"
    ? { busy, checkAgain: () => { void recover(false); }, retryOriginal: () => { void recover(true); } } : null;
  useEffect(() => {
    mounted.current = true;
    if (record.current && timer.current === undefined) schedule(record.current, 1000);
    return () => { mounted.current = false; stopTimer(); };
  }, []);
  useEffect(() => {
    if (record.current && record.current.request.ownerKey !== options.ownerKey) { stopTimer(); record.current = null; changed(); }
  }, [options.ownerKey]);
  return stable.current;
}

export function SubmissionRecoveryNotice({ controller }: { controller: InteractionSubmissionController }) {
  const recovery = controller.recovery;
  if (!recovery) return null;
  return <div className="notice" role="status">
    <p>We could not confirm whether this task was accepted. Your original task is kept for recovery.</p>
    <div className="actions">
      <button type="button" disabled={recovery.busy} onClick={recovery.checkAgain}>Check again</button>
      <button type="button" disabled={recovery.busy} onClick={recovery.retryOriginal}>Retry original task</button>
    </div>
  </div>;
}

export function cancelAcceptedInteraction(run: AgentRun, isCurrentOwner: () => boolean,
  cancel: (runId: string) => Promise<AgentRun>, update: (run: AgentRun) => void, fail: (error: unknown) => void): void {
  if (run.finalization_phase === "saving_changes" || !isCurrentOwner()) return;
  void cancel(run.id).then(next => {
    if (isCurrentOwner() && next.id === run.id) update(next);
  }).catch(error => { if (isCurrentOwner()) fail(error); });
}
