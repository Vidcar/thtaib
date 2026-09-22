import { useEffect, useRef, useState } from "react";

import { api } from "./api";
import { deploymentOptionLabel, shortId } from "./display";
import { HoverHelp } from "./HoverHelp";
import { Notice } from "./Notice";
import { Icon } from "./Icon";
import { InteractionStream, useWorkbenchProjection, type WorkbenchStream } from "./InteractionStream";
import {
  isAgentRunLive,
  type AgentRun,
  type Deployment,
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
      {(stream) => <LabRunObserverContent stream={stream} runId={runId} isActive={isActive} setRun={setRun} />}
    </InteractionStream>
  );
}

function LabRunObserverContent(props: { stream: WorkbenchStream; runId: string; isActive: (runId: string, threadId: string) => boolean; setRun: (run: AgentRun) => void }) {
  const { stream, runId, isActive, setRun } = props;
  const projection = useWorkbenchProjection(stream);
  useEffect(() => {
    if (stream.threadId && isActive(runId, stream.threadId) && projection.run && projection.run.id === runId) {
      setRun(projection.run);
    }
  }, [isActive, projection.run, runId, setRun, stream.threadId]);
  return null;
}

export function LabPanel() {
  const [deployments, setDeployments] = useState<Deployment[]>([]);
  const [deploymentId, setDeploymentId] = useState("");
  const [workspace, setWorkspace] = useState<LabWorkspace | null>(null);
  const [files, setFiles] = useState<Record<string, string>>({});
  const [notes, setNotes] = useState("original notes");
  const [run, setRun] = useState<AgentRun | null>(null);
  const [runBinding, setRunBinding] = useState<{ runId: string; threadId: string } | null>(null);
  const runBindingRef = useRef<{ runId: string; threadId: string } | null>(null);
  const liveRunIdRef = useRef<string | null>(null);
  const [labCase, setLabCase] = useState<LabCase | null>(null);
  const [restore, setRestore] = useState<LabRestore | null>(null);
  const [result, setResult] = useState<LabResult | null>(null);
  const [engine, setEngine] = useState<EngineMeasurement | null>(null);
  const [message, setMessage] = useState("");

  async function refresh(): Promise<void> {
    const next = await api.deployments();
    setDeployments(next);
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
    const timer = window.setInterval(() => {
      void api
        .labResult(result.id)
        .then(setResult)
        .catch((error: unknown) => setMessage(error instanceof Error ? error.message : String(error)));
    }, 5000);
    return () => window.clearInterval(timer);
  }, [result]);

  function fail(error: unknown): void {
    setMessage(error instanceof Error ? error.message : String(error));
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
          <textarea value={notes} onChange={(event) => setNotes(event.target.value)} />
        </label>
        <div className="actions">
          <button
            type="button"
            onClick={() => {
              void api
                .createWorkspace("lab-project", { "notes.md": notes })
                .then(async (next) => {
                  setWorkspace(next);
                  setRestore(null);
                  const listed = await api.workspaceFiles(next.id);
                  setFiles(listed.files);
                  setMessage("Workspace created.");
                })
                .catch(fail);
            }}
          >
            <Icon name="plus" size={14} /> Create workspace
          </button>
          <button
            type="button"
            disabled={!workspace}
            onClick={() => {
              if (!workspace) {
                return;
              }
              void api
                .writeWorkspaceFiles(workspace.id, { "notes.md": notes })
                .then((next) => {
                  setFiles(next.files);
                  setMessage("Parent project files updated");
                })
                .catch(fail);
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
          void api
            .startAgentRun(deploymentId, "Echo the text harness-ok using the echo tool.", ["echo"], workspace.id)
            .then((next) => {
              setRun(next);
              setMessage("Tool check started.");
            })
            .catch(fail);
        }}
      >
        <div className="entity-head"><h3>Tool check</h3><HoverHelp title="About the tool check">Asks the selected model to echo a short message using the echo tool. This checks basic tool use, not general model quality.</HoverHelp></div>
        <label>
          Model
          <select value={deploymentId} onChange={(event) => setDeploymentId(event.target.value)}>
            {deployments.map((deployment) => (
              <option key={deployment.id} value={deployment.id}>
                {deploymentOptionLabel(deployment)}
              </option>
            ))}
          </select>
        </label>
        <button type="submit" disabled={!deploymentId || !workspace}>
          <Icon name="send" size={14} /> Run tool check
        </button>
        {run ? (
          <p>
            Run {shortId(run.id)}
            <span className="badge">{run.status}</span>
          </p>
        ) : null}
        {run?.error ? <Notice tone="error">{run.error}</Notice> : null}
      </form>
      </div>

      <div className="card">
        <div className="entity-head"><h3>Compare runs</h3><HoverHelp title="About comparisons">Capture the task, restore a clean copy, then rerun with live tools or replay recorded results. Replay supports comparison; it does not prove live tool capability.</HoverHelp></div>
        <div className="actions">
          <button
            type="button"
            disabled={!workspace || !run}
            onClick={() => {
              if (!workspace || !run) {
                return;
              }
              void api
                .captureCase(workspace.id, run.id)
                .then((next) => {
                  setLabCase(next);
                  setMessage("Case captured.");
                })
                .catch(fail);
            }}
          >
            <Icon name="copy" size={14} /> Capture case
          </button>
          <button
            type="button"
            disabled={!labCase}
            onClick={() => {
              if (!labCase) {
                return;
              }
              void api
                .restoreCase(labCase.id)
                .then(async (next) => {
                  setRestore(next);
                  const listed = await api.workspaceFiles(next.workspace.id);
                  setFiles(listed.files);
                  setMessage(
                    next.parent_unchanged ? "Restored into a clean workspace." : "Restored workspace changed the parent.",
                  );
                })
                .catch(fail);
            }}
          >
            <Icon name="restore" size={14} /> Restore a copy
          </button>
          <RerunButton
            label={toolModeLabel("live-tool")}
            mode="live-tool"
            labCase={labCase}
            restore={restore}
            onResult={setResult}
            onError={fail}
          />
          <RerunButton
            label={toolModeLabel("recorded-tool")}
            mode="recorded-tool"
            labCase={labCase}
            restore={restore}
            onResult={setResult}
            onError={fail}
          />
          <button
            type="button"
            onClick={() => {
              void api
                .measureEngine(deploymentId || undefined)
                .then((next) => {
                  setEngine(next);
                  setMessage(next.available ? "Engine measurement ran." : "Engine measurement is unavailable.");
                })
                .catch(fail);
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
  onError,
}: {
  label: string;
  mode: LabToolMode;
  labCase: LabCase | null;
  restore: LabRestore | null;
  onResult: (result: LabResult) => void;
  onError: (error: unknown) => void;
}) {
  return (
    <button
      type="button"
      disabled={!labCase || !restore}
      onClick={() => {
        if (!labCase || !restore) {
          return;
        }
        void api.rerunCase(labCase.id, mode, restore.workspace.id).then(onResult).catch(onError);
      }}
    >
      <Icon name="refresh" size={14} /> {label}
    </button>
  );
}
