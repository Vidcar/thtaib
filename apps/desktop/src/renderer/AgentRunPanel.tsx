import { useEffect, useState } from "react";

import { api } from "./api";
import { deploymentOptionLabel } from "./display";
import { EmptyState } from "./EmptyState";
import { errorMessage } from "./errors";
import { InterruptApproval } from "./InterruptApproval";
import { Notice } from "./Notice";
import { RunProgress } from "./RunProgress";
import {
  isAgentRunLive,
  isDeclaredEmbedder,
  visiblePendingInterrupt,
  type AgentRun,
  type Deployment,
} from "./types";

export function AgentRunPanel() {
  const [deployments, setDeployments] = useState<Deployment[]>([]);
  const [enabledTools, setEnabledTools] = useState<string[]>([]);
  const [deploymentId, setDeploymentId] = useState("");
  const [embeddingDeploymentId, setEmbeddingDeploymentId] = useState("");
  const [task, setTask] = useState("");
  const [projectPath, setProjectPath] = useState("");
  const [run, setRun] = useState<AgentRun | null>(null);
  const [message, setMessage] = useState("");
  const [loadError, setLoadError] = useState("");

  async function refresh(): Promise<void> {
    const [nextDeployments, tools] = await Promise.all([api.deployments(), api.agentTools()]);
    setDeployments(nextDeployments);
    setEnabledTools(tools.enabled);
    setDeploymentId((current) => current || nextDeployments[0]?.id || "");
    setLoadError("");
  }

  useEffect(() => {
    void refresh().catch((error: unknown) => {
      setLoadError(errorMessage(error));
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
      setMessage(errorMessage(error));
    });
    return () => controller.abort();
  }, [liveRunId]);

  function fail(error: unknown): void {
    setMessage(errorMessage(error));
  }

  if (loadError) {
    return (
      <section className="surface">
        <h2>Agent run</h2>
        <Notice tone="error">{loadError}</Notice>
      </section>
    );
  }

  return (
    <section className="surface">
      <header className="surface-head">
        <h2>Agent run</h2>
        <p className="lede">
          One-off harness task. Prefer Chat for conversation. Approvals here are the same Deep Agents
          interrupt, not a durable inbox.
        </p>
      </header>

      <form
        className="card"
        onSubmit={(event) => {
          event.preventDefault();
          void api
            .startAgentRun(
              deploymentId,
              task,
              undefined,
              undefined,
              projectPath || undefined,
              embeddingDeploymentId || undefined,
            )
            .then((next) => {
              setRun(next);
              setMessage("");
            })
            .catch(fail);
        }}
      >
        <label>
          Deployment
          <select value={deploymentId} onChange={(event) => setDeploymentId(event.target.value)}>
            {deployments.length === 0 ? <option value="">No deployment</option> : null}
            {deployments.map((deployment) => (
              <option key={deployment.id} value={deployment.id}>
                {deploymentOptionLabel(deployment)}
              </option>
            ))}
          </select>
        </label>
        <label>
          Embedding deployment (optional)
          <select
            value={embeddingDeploymentId}
            onChange={(event) => setEmbeddingDeploymentId(event.target.value)}
          >
            <option value="">None — no retrieval</option>
            {deployments.map((deployment) => (
              <option key={deployment.id} value={deployment.id}>
                {deploymentOptionLabel(deployment)}
                {isDeclaredEmbedder(deployment) ? "" : " (not declared embedding:on)"}
              </option>
            ))}
          </select>
        </label>
        <label>
          Project folder (required for host shell)
          <input
            value={projectPath}
            onChange={(event) => setProjectPath(event.target.value)}
            placeholder="Leave empty for visibility tools only"
          />
        </label>
        <label>
          Task
          <textarea value={task} onChange={(event) => setTask(event.target.value)} />
        </label>
        <p className="hint">Tools: {enabledTools.length ? enabledTools.join(", ") : "none"}</p>
        <div className="actions">
          <button type="submit" disabled={!deploymentId || !task.trim() || Boolean(liveRunId)}>
            Start
          </button>
        </div>
      </form>

      {pendingInterrupt && run ? (
        <InterruptApproval
          pending={pendingInterrupt}
          onDecide={(type) => {
            void api.decideAgentRunInterrupt(run.id, type).then(setRun).catch(fail);
          }}
        />
      ) : null}

      {run ? (
        <div className="card">
          <RunProgress
            run={run}
            title={run.task}
            onCancel={() => {
              void api.cancelAgentRun(run.id).then(setRun).catch(fail);
            }}
          />
        </div>
      ) : (
        <EmptyState title="No run yet">Start a task after a deployment is available.</EmptyState>
      )}
      {message ? <Notice tone="error">{message}</Notice> : null}
    </section>
  );
}
