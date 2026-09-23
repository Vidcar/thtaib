import { useEffect, useRef, useState } from "react";

import { api } from "./api";
import { ChatModelControls } from "./ChatModelControls";
import { ApprovalModeControl, approvalModeLabel, type ApprovalMode } from "./ApprovalModeControl";
import { MenuPopover } from "./MenuPopover";
import { InterruptApproval } from "./InterruptApproval";
import { RunProgress } from "./RunProgress";
import { workspaceApi, type SetupConfiguration } from "./workspaceApi";
import { HoverHelp } from "./HoverHelp";
import { Notice } from "./Notice";
import { Icon } from "./Icon";
import { InteractionStream, useWorkbenchProjection, visibleApprovalInterrupt, type WorkbenchStream } from "./InteractionStream";
import {
  isAgentRunLive,
  type AgentRun,
  type Deployment,
  type RunProfile,
  type EngineMeasurement,
  type LabCase,
  type LabRestore,
  type LabResult,
  type LabToolMode,
  type LabWorkspace,
} from "./types";

function LabRunObserver(props: {
  threadId: string;
  runId: string;
  isActive: (runId: string, threadId: string) => boolean;
  setRun: (run: AgentRun) => void;
  setMessage: (message: string) => void;
}) {
  const { threadId, runId, isActive, setRun, setMessage } = props;
  return (
    <InteractionStream
      threadId={threadId}
      onError={(error) => {
        if (isActive(runId, threadId)) {
          setMessage(error instanceof Error ? error.message : String(error));
        }
      }}
    >
      {(stream) => <LabRunObserverContent stream={stream} runId={runId} isActive={isActive} setRun={setRun} setMessage={setMessage} />}
    </InteractionStream>
  );
}

function LabRunObserverContent(props: { stream: WorkbenchStream; runId: string; isActive: (runId: string, threadId: string) => boolean; setRun: (run: AgentRun) => void; setMessage: (message: string) => void }) {
  const { stream, runId, isActive, setRun, setMessage } = props;
  const projection = useWorkbenchProjection(stream);
  useEffect(() => {
    if (stream.threadId && isActive(runId, stream.threadId) && projection.run && projection.run.id === runId) {
      setRun(projection.run);
    }
  }, [isActive, projection.run, runId, setRun, stream.threadId]);
  const interrupt = visibleApprovalInterrupt(stream, projection.run);
  return interrupt ? <InterruptApproval pending={interrupt.pending} onRespond={payload => {
    if (!stream.threadId || !isActive(runId, stream.threadId)) return;
    void stream.respond(payload, { interruptId: interrupt.id, namespace: interrupt.namespace }).catch(error => {
      if (stream.threadId && isActive(runId, stream.threadId)) setMessage(error instanceof Error ? error.message : String(error));
    });
  }} /> : null;
}

export function LabPanel() {
  const [deployments, setDeployments] = useState<Deployment[]>([]);
  const [profiles, setProfiles] = useState<RunProfile[]>([]);
  const [configuration, setConfiguration] = useState<SetupConfiguration>({});
  const [approvalMode, setApprovalMode] = useState<ApprovalMode>("ask");
  const [deploymentId, setDeploymentId] = useState("");
  const [workspace, setWorkspace] = useState<LabWorkspace | null>(null);
  const [files, setFiles] = useState<Record<string, string>>({});
  const [restoredFiles, setRestoredFiles] = useState<Record<string, string>>({});
  const [notes, setNotes] = useState("original notes");
  const [run, setRun] = useState<AgentRun | null>(null);
  const [sourceRunId, setSourceRunId] = useState<string | null>(null);
  const [runBinding, setRunBinding] = useState<{ runId: string; threadId: string } | null>(null);
  const runBindingRef = useRef<{ runId: string; threadId: string } | null>(null);
  const liveRunIdRef = useRef<string | null>(null);
  const [labCase, setLabCase] = useState<LabCase | null>(null);
  const [restore, setRestore] = useState<LabRestore | null>(null);
  const [result, setResult] = useState<LabResult | null>(null);
  const [engine, setEngine] = useState<EngineMeasurement | null>(null);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const actionPending = useRef(false);
  async function action(work: () => Promise<void>): Promise<void> {
    if (actionPending.current) return;
    actionPending.current = true; setBusy(true); setMessage("");
    try { await work(); } catch (failure) { fail(failure); }
    finally { actionPending.current = false; setBusy(false); }
  }

  async function refresh(): Promise<void> {
    const [next, nextProfiles] = await Promise.all([api.deployments(), api.profiles()]);
    setDeployments(next);
    setProfiles(nextProfiles);
    setDeploymentId((current) => current || next[0]?.id || "");
  }

  useEffect(() => {
    void refresh().catch((error: unknown) => {
      setMessage(error instanceof Error ? error.message : String(error));
    });
  }, []);

  const liveRunId = run && isAgentRunLive(run.status) ? run.id : null;
  liveRunIdRef.current = liveRunId;

  function updateRunBinding(next: { runId: string; threadId: string } | null): void {
    runBindingRef.current = next;
    setRunBinding(next);
  }

  function isActiveRunBinding(runId: string, threadId: string): boolean {
    return liveRunIdRef.current === runId && runBindingRef.current?.runId === runId && runBindingRef.current.threadId === threadId;
  }

  useEffect(() => {
    if (!liveRunId) {
      updateRunBinding(null);
      return;
    }
    let cancelled = false;
    updateRunBinding(null);
    void api
      .registerAgentInteractionThread({ source_surface: "agent", run_id: liveRunId })
      .then((binding) => {
        if (!cancelled) {
          updateRunBinding({ runId: liveRunId, threadId: binding.thread_id });
        }
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          fail(error);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [liveRunId]);

  useEffect(() => {
    if (!result) {
      return;
    }
    const checks = result.evidence.executable_checks;
    if (Array.isArray(checks) && checks.length > 0) {
      return;
    }
    let cancelled = false;
    const timer = window.setInterval(() => {
      void api
        .labResult(result.id)
        .then(next => { if (!cancelled) setResult(current => current?.id === next.id ? next : current); })
        .catch((error: unknown) => { if (!cancelled) fail(error); });
    }, 5000);
    return () => { cancelled = true; window.clearInterval(timer); };
  }, [result]);

  function fail(error: unknown): void {
    setMessage(error instanceof Error ? error.message : String(error));
  }

  async function showResult(next: LabResult): Promise<void> {
    setResult(next);
    if (next.agent_run_id) setRun(await api.agentRun(next.agent_run_id));
  }

  function toolModeLabel(mode: LabToolMode): string {
    switch (mode) {
      case "live-tool":
        return "Use live tools";
      case "recorded-tool":
        return "Replay recorded tools";
      default: {
        const unexpected: never = mode;
        return unexpected;
      }
    }
  }

  return (
    <section className="surface">
      <header className="surface-head"><div className="entity-head"><h2>Lab</h2><HoverHelp title="About Lab">Capture a task in an isolated workspace, then compare a live rerun with recorded tool replay.</HoverHelp></div></header>

      <div className="grid">
      <div className="card">
        <div className="entity-head"><h3>Workspace</h3><HoverHelp title="About the Lab workspace">Create an isolated project containing notes.md. Saving the source changes this Lab workspace, not your everyday project.</HoverHelp></div>
        <label>
          notes.md
          <textarea disabled={busy || Boolean(liveRunId)} value={notes} onChange={(event) => setNotes(event.target.value)} />
        </label>
        <div className="actions">
          <button
            type="button"
            disabled={busy || Boolean(liveRunId)}
            onClick={() => {
              void action(async () => {
                const next = await api.createWorkspace("lab-project", { "notes.md": notes });
                setWorkspace(next);
                setRun(null); setSourceRunId(null); setLabCase(null); setResult(null); setEngine(null); setFiles({}); setRestoredFiles({});
                setRestore(null);
                const listed = await api.workspaceFiles(next.id);
                setFiles(listed.files);
                setMessage("Workspace created.");
              });
            }}
          >
            <Icon name="plus" size={14} /> Create workspace
          </button>
          <button
            type="button"
            disabled={busy || !workspace || Boolean(liveRunId)}
            onClick={() => {
              if (!workspace) {
                return;
              }
              void action(async () => {
                const next = await api.writeWorkspaceFiles(workspace.id, { "notes.md": notes });
                setFiles(next.files);
                setMessage("Lab source saved.");
              });
            }}
          >
            <Icon name="edit" size={14} /> Save source
          </button>
        </div>
        {workspace ? (
          <details>
            <summary><Icon name="folder" size={14} /> Files and location</summary>
            <p className="hint">
              ID: {workspace.id} · source: {workspace.origin} · path: {workspace.path}
            </p>
            <pre className="json">{JSON.stringify(files, null, 2)}</pre>
          </details>
        ) : null}
      </div>

      <form
        className="card"
        onSubmit={(event) => {
          event.preventDefault();
          if (!workspace) {
            setMessage("Create a workspace first");
            return;
          }
          if (liveRunId) return;
          void action(async () => {
            const next = await api.startAgentRun(deploymentId, "Echo the text harness-ok using the echo tool.", ["echo"], workspace.id, undefined, undefined, { ...configuration, approval_mode: approvalMode });
            setRun(next);
            setSourceRunId(next.id);
            if (next.deployment_id) setDeploymentId(next.deployment_id);
            setLabCase(null); setRestore(null); setResult(null); setRestoredFiles({});
            setMessage("Tool check started.");
          });
        }}
      >
        <div className="entity-head"><h3>Tool check</h3><HoverHelp title="About the tool check">Asks the selected model to echo a short message using the echo tool. This checks basic tool use, not general model quality.</HoverHelp></div>
        <div className="workflow-controls"><ChatModelControls deployments={deployments} profiles={profiles} selectedDeploymentId={deploymentId} configuration={configuration} disabled={busy || Boolean(liveRunId)} runtimeBusy={Boolean(liveRunId)} onReloaded={refresh} onApply={async next => { const resolved = await workspaceApi.resolveSetup(null, null, next); setConfiguration(next); setDeploymentId(resolved.configuration.deployment_id ?? next.deployment_id ?? (next.model_configuration_id ? "" : deploymentId)); }} />
        <MenuPopover label={`Access: ${approvalModeLabel(approvalMode)}`} trigger={<><Icon name="shield" size={16} />{approvalModeLabel(approvalMode)}</>} disabled={busy || Boolean(liveRunId)}><ApprovalModeControl value={approvalMode} onChange={setApprovalMode} /></MenuPopover></div>
        <button type="submit" disabled={busy || (!deploymentId && !configuration.model_configuration_id) || !workspace || Boolean(liveRunId)}>
          <Icon name="send" size={14} /> Run tool check
        </button>
        {run ? <RunProgress run={run} title={result ? "Comparison run" : "Tool check"} onCancel={() => void action(async () => {
          const next = await api.cancelAgentRun(run.id);
          setRun(current => current?.id === next.id ? next : current);
        })} /> : null}
        {run?.error ? <Notice tone="error">{run.error}</Notice> : null}
      </form>
      </div>

      <div className="card">
        <div className="entity-head"><h3>Compare runs</h3><HoverHelp title="About comparisons">Capture the task, restore a clean copy, then rerun with live tools or replay recorded results. Replay supports comparison; it does not prove live tool capability.</HoverHelp></div>
        <div className="actions">
          <button
            type="button"
            disabled={busy || !workspace || !sourceRunId || Boolean(liveRunId)}
            onClick={() => {
              if (!workspace || !sourceRunId || liveRunId) {
                return;
              }
              void action(async () => {
                const next = await api.captureCase(workspace.id, sourceRunId);
                setLabCase(next);
                setRestore(null); setResult(null); setRestoredFiles({});
                setMessage("Case captured.");
              });
            }}
          >
            <Icon name="copy" size={14} /> Capture case
          </button>
          <button
            type="button"
            disabled={busy || !labCase || Boolean(liveRunId)}
            onClick={() => {
              if (!labCase) {
                return;
              }
              void action(async () => {
                const next = await api.restoreCase(labCase.id);
                setRestore(next);
                setResult(null);
                const listed = await api.workspaceFiles(next.workspace.id);
                setRestoredFiles(listed.files);
                setMessage(next.parent_unchanged ? "Restored into a clean workspace." : "Restored workspace changed the parent.");
              });
            }}
          >
            <Icon name="restore" size={14} /> Restore a copy
          </button>
          <RerunButton
            label={toolModeLabel("live-tool")}
            mode="live-tool"
            labCase={labCase}
            restore={restore}
            onResult={showResult}
            action={action}
            disabled={busy || Boolean(liveRunId)}
          />
          <RerunButton
            label={toolModeLabel("recorded-tool")}
            mode="recorded-tool"
            labCase={labCase}
            restore={restore}
            onResult={showResult}
            action={action}
            disabled={busy || Boolean(liveRunId)}
          />
          <button
            type="button"
            disabled={busy || Boolean(liveRunId) || !deploymentId}
            title={!deploymentId ? "Load the selected model before measuring its engine." : undefined}
            onClick={() => {
              void action(async () => {
                const next = await api.measureEngine(deploymentId || undefined);
                setEngine(next);
                setMessage(next.available ? "Engine measurement ran." : "Engine measurement is unavailable.");
              });
            }}
          >
            <Icon name="activity" size={14} /> Measure engine
          </button>
        </div>
        {labCase ? (
          <details>
            <summary>Case details</summary>
            <p className="hint">
              Case ID: {labCase.id} · snapshot: {labCase.snapshot_id} · environment restore:{" "}
              {labCase.environment_restore}
            </p>
            <p className="hint">Snapshot path: {labCase.snapshot_path}</p>
          </details>
        ) : null}
      </div>

      {restore ? (
        <div className="card">
          <h3>Restored workspace</h3>
          <p>
            Parent workspace {restore.parent_unchanged ? "unchanged" : "changed"} · branch {restore.branch.kind}
          </p>
          <details>
            <summary>Restore details</summary>
            <pre className="json">{JSON.stringify(restore, null, 2)}</pre>
            <pre className="json">{JSON.stringify(restoredFiles, null, 2)}</pre>
          </details>
        </div>
      ) : null}

      {result ? (
        <div className="card">
          <h3>
            Results
            <span className="badge">{result.tool_mode_label}</span>
          </h3>
          <HoverHelp title="About this result">Harness: {result.harness}. Second agent loop: {result.second_agent_loop ? "yes" : "no"}. Recorded replay is supporting evidence only.</HoverHelp>
          <details><summary><Icon name="tune" size={14} /> Applied settings</summary><pre className="json">{JSON.stringify(result.applied_config, null, 2)}</pre></details>
          <details><summary><Icon name="check" size={14} /> Test evidence</summary><pre className="json">{JSON.stringify(result.evidence, null, 2)}</pre></details>
          <details><summary><Icon name="activity" size={14} /> Model assessment</summary><pre className="json">{JSON.stringify(result.judgement, null, 2)}</pre></details>
        </div>
      ) : null}

      {engine ? (
        <div className="card">
          <h3>
            Engine measurement
            <span className="badge">{engine.available ? "available" : "unavailable"}</span>
          </h3>
          <p>{engine.note}</p>
          <details><summary><Icon name="activity" size={14} /> Measurements</summary><pre className="json">{JSON.stringify(engine, null, 2)}</pre></details>
        </div>
      ) : null}

      {runBinding && liveRunId && runBinding.runId === liveRunId ? (
        <LabRunObserver
          key={`${runBinding.runId}:${runBinding.threadId}`}
          threadId={runBinding.threadId}
          runId={runBinding.runId}
          isActive={isActiveRunBinding}
          setRun={setRun}
          setMessage={setMessage}
        />
      ) : null}

      {message ? <p className="status" role="status">{message}</p> : null}
    </section>
  );
}

function RerunButton({
  label,
  mode,
  labCase,
  restore,
  onResult,
  action,
  disabled,
}: {
  label: string;
  mode: LabToolMode;
  labCase: LabCase | null;
  restore: LabRestore | null;
  onResult: (result: LabResult) => Promise<void>;
  action: (work: () => Promise<void>) => Promise<void>;
  disabled: boolean;
}) {
  return (
    <button
      type="button"
      disabled={disabled || !labCase || !restore}
      onClick={() => {
        if (!labCase || !restore) {
          return;
        }
        void action(async () => { await onResult(await api.rerunCase(labCase.id, mode, restore.workspace.id)); });
      }}
    >
      <Icon name="refresh" size={14} /> {label}
    </button>
  );
}
