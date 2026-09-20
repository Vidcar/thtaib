import { useEffect, useState } from "react";

import { api } from "./api";
import { deploymentOptionLabel, shortId } from "./display";
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

export function LabPanel() {
  const [deployments, setDeployments] = useState<Deployment[]>([]);
  const [deploymentId, setDeploymentId] = useState("");
  const [workspace, setWorkspace] = useState<LabWorkspace | null>(null);
  const [files, setFiles] = useState<Record<string, string>>({});
  const [notes, setNotes] = useState("original notes");
  const [run, setRun] = useState<AgentRun | null>(null);
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

  useEffect(() => {
    if (!liveRunId) {
      return;
    }
    const controller = new AbortController();
    void api.subscribeAgentRun(liveRunId, controller.signal, setRun).catch((error: unknown) => {
      if (controller.signal.aborted) {
        return;
      }
      setMessage(error instanceof Error ? error.message : String(error));
    });
    return () => controller.abort();
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
    <section className="panel">
      <h2>Lab</h2>
      <p className="lede">
        Capture a task, restore it into a clean workspace, and compare a live rerun with a recorded
        replay.
      </p>

      <div className="card">
        <h3>Project workspace</h3>
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
            Create workspace
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
            Change parent files
          </button>
        </div>
        {workspace ? (
          <details>
            <summary>Workspace details</summary>
            <p className="hint">
              ID: {workspace.id} · source: {workspace.origin} · path: {workspace.path}
            </p>
          </details>
        ) : null}
        <pre className="json">{JSON.stringify(files, null, 2)}</pre>
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
        <h3>Check tool use</h3>
        <p className="hint">Ask the model to echo a short message with a tool.</p>
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
          Run tool check
        </button>
        {run ? (
          <p>
            Run {shortId(run.id)}
            <span className="badge">{run.status}</span>
          </p>
        ) : null}
      </form>

      <div className="card">
        <h3>Capture / restore / rerun</h3>
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
            Capture case
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
            Restore into new workspace
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
            Engine measurement
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
          <h3>Restore / branch</h3>
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
            Task evaluation
            <span className="badge">{result.tool_mode_label}</span>
          </h3>
          <p>
            Harness: {result.harness} · second agent loop: {result.second_agent_loop ? "yes" : "no"} · recorded
            replay is supporting evidence only
          </p>
          <h3>Applied config</h3>
          <pre className="json">{JSON.stringify(result.applied_config, null, 2)}</pre>
          <h3>Evidence (not judgement)</h3>
          <pre className="json">{JSON.stringify(result.evidence, null, 2)}</pre>
          <h3>Judgement</h3>
          <pre className="json">{JSON.stringify(result.judgement, null, 2)}</pre>
        </div>
      ) : null}

      {engine ? (
        <div className="card">
          <h3>
            Engine measurement
            <span className="badge">{engine.available ? "available" : "unavailable"}</span>
          </h3>
          <p>{engine.note}</p>
          <pre className="json">{JSON.stringify(engine, null, 2)}</pre>
        </div>
      ) : null}

      {message ? <p className="status">{message}</p> : null}
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
      {label}
    </button>
  );
}
