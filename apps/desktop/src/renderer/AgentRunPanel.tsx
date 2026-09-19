import { useEffect, useState } from "react";

import { api } from "./api";
import type { AgentRun, Deployment } from "./types";

export function AgentRunPanel() {
  const [deployments, setDeployments] = useState<Deployment[]>([]);
  const [enabledTools, setEnabledTools] = useState<string[]>([]);
  const [deploymentId, setDeploymentId] = useState("");
  const [task, setTask] = useState("Use the echo tool to repeat: harness-ok");
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

  useEffect(() => {
    if (!run || (run.status !== "queued" && run.status !== "running")) {
      return;
    }
    const timer = window.setInterval(() => {
      void api
        .agentRun(run.id)
        .then(setRun)
        .catch((error: unknown) => setMessage(error instanceof Error ? error.message : String(error)));
    }, 750);
    return () => window.clearInterval(timer);
  }, [run]);

  return (
    <section className="panel">
      <h2>Agent run</h2>
      <p className="hint">
        Embedded Deep Agents harness debug panel. This is not Chat and not Builder. The
        adapter talks only to a model-manager deployment endpoint and starts no inference
        process.
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
            .startAgentRun(deploymentId, task)
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
          Task
          <textarea value={task} onChange={(event) => setTask(event.target.value)} />
        </label>
        <div className="actions">
          <button type="submit" disabled={!deploymentId}>
            Start
          </button>
          <button
            type="button"
            disabled={!run}
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
          <p>harness: {run.harness} · stop: {run.stop_reason ?? "n/a"} · budgets: {run.budgets ? "set" : "unset"}</p>
          <p>enabled tools: {run.enabled_tools.join(", ")}</p>
          <p>presented tools: {run.presented_tools.join(", ")}</p>
          {run.error ? <p className="status">{run.error}</p> : null}
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
