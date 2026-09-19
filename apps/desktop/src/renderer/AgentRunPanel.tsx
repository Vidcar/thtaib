import { useEffect, useState } from "react";

import { api } from "./api";
import { InterruptApproval } from "./InterruptApproval";
import { EffectiveSetupNotes } from "./settingsNotes";
import { isAgentRunLive, visiblePendingInterrupt, type AgentRun, type Deployment } from "./types";

export function AgentRunPanel() {
  const [deployments, setDeployments] = useState<Deployment[]>([]);
  const [enabledTools, setEnabledTools] = useState<string[]>([]);
  const [deploymentId, setDeploymentId] = useState("");
  const [task, setTask] = useState("Use the echo tool to repeat: harness-ok");
  const [projectPath, setProjectPath] = useState("");
  const [run, setRun] = useState<AgentRun | null>(null);
  const [message, setMessage] = useState("");

  async function refresh(): Promise<void> {
    const [nextDeployments, tools] = await Promise.all([api.deployments(), api.agentTools()]);
    setDeployments(nextDeployments);
    setEnabledTools(tools.enabled);
    setDeploymentId((current) => current || nextDeployments[0]?.id || "");
  }

  useEffect(() => {
    void refresh().catch((error: unknown) => {
      setMessage(error instanceof Error ? error.message : String(error));
    });
  }, []);

  const liveRunId = run && isAgentRunLive(run.status) ? run.id : null;
  const pendingInterrupt = visiblePendingInterrupt(run);

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

  return (
    <section className="panel">
      <h2>Agent run</h2>
      <p className="hint">
        Embedded Deep Agents harness debug panel. This is not Chat and not Builder. The
        adapter talks only to a model-manager deployment endpoint and starts no inference
        process. Host shell execute needs a bound project cwd and pauses dangerous
        commands here for Approve or Deny.
      </p>

      <div className="card">
        <h3>Enabled tools</h3>
        <p>{enabledTools.length ? enabledTools.join(", ") : "none"}</p>
      </div>

      <form
        className="card"
        onSubmit={(event) => {
          event.preventDefault();
          void api
            .startAgentRun(deploymentId, task, undefined, undefined, projectPath || undefined)
            .then((next) => {
              setRun(next);
              setMessage(`Started ${next.id}`);
            })
            .catch((error: unknown) => setMessage(error instanceof Error ? error.message : String(error)));
        }}
      >
        <h3>Start one task</h3>
        <label>
          Deployment
          <select value={deploymentId} onChange={(event) => setDeploymentId(event.target.value)}>
            {deployments.map((deployment) => (
              <option key={deployment.id} value={deployment.id}>
                {deployment.display_name} · {deployment.status}
              </option>
            ))}
          </select>
        </label>
        <label>
          Project workspace path (required for host shell)
          <input
            value={projectPath}
            onChange={(event) => setProjectPath(event.target.value)}
            placeholder="%LOCALAPPDATA%\LocalAIWorkbench\workspaces\…"
          />
        </label>
        <label>
          Task
          <textarea value={task} onChange={(event) => setTask(event.target.value)} />
        </label>
        <div className="actions">
          <button type="submit" disabled={!deploymentId}>
            Start
          </button>
          <button
            type="button"
            disabled={!run || !isAgentRunLive(run.status)}
            onClick={() => {
              if (!run) {
                return;
              }
              void api
                .cancelAgentRun(run.id)
                .then(setRun)
                .catch((error: unknown) =>
                  setMessage(error instanceof Error ? error.message : String(error)),
                );
            }}
          >
            Cancel
          </button>
        </div>
      </form>

      {run ? (
        <div className="card">
          <h3>
            {run.id}
            <span className="badge">{run.status}</span>
          </h3>
          <p>
            harness: {run.harness} · stop: {run.stop_reason ?? "n/a"} · budgets:{" "}
            {run.budgets ? "set" : "unset"} · host shell:{" "}
            {run.host_shell?.available ? `cwd ${run.host_shell.cwd ?? ""}` : "unavailable"}
          </p>
          {pendingInterrupt ? (
            <InterruptApproval
              pending={pendingInterrupt}
              onDecide={(type) => {
                void api
                  .decideAgentRunInterrupt(run.id, type)
                  .then(setRun)
                  .catch((error: unknown) =>
                    setMessage(error instanceof Error ? error.message : String(error)),
                  );
              }}
            />
          ) : null}
          <h3>Run linkage (application records)</h3>
          <pre className="json">
            {JSON.stringify(
              {
                thread_id: run.thread_id ?? null,
                checkpoint_ids: run.checkpoint_ids ?? [],
                related_files: run.related_files ?? [],
              },
              null,
              2,
            )}
          </pre>
          <p>enabled tools: {run.enabled_tools.join(", ")}</p>
          <p>presented tools: {run.presented_tools.join(", ")}</p>
          {run.error ? <p className="status">{run.error}</p> : null}
          <h3>Effective setup (selected ≠ loaded ≠ applied)</h3>
          <EffectiveSetupNotes
            unsupportedStartup={run.effective_setup?.unsupported?.startup}
            retiredStartup={run.effective_setup?.retired?.startup}
            startupMismatches={run.effective_setup?.startup_mismatches}
          />
          <pre className="json">{JSON.stringify(run.effective_setup ?? null, null, 2)}</pre>
          <h3>Captured model request</h3>
          <pre className="json">{JSON.stringify(run.model_requests, null, 2)}</pre>
          <h3>Evidence (not judgement)</h3>
          <pre className="json">{JSON.stringify(run.completion?.evidence ?? null, null, 2)}</pre>
          <h3>Judgement</h3>
          <pre className="json">{JSON.stringify(run.completion?.judgement ?? null, null, 2)}</pre>
          <h3>Events</h3>
          <pre className="json">{JSON.stringify(run.events, null, 2)}</pre>
        </div>
      ) : (
        <p className="hint">No harness run yet.</p>
      )}
      {message ? <p className="status">{message}</p> : null}
    </section>
  );
}
