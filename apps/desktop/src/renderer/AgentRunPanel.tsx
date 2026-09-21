import { useEffect, useRef, useState } from "react";

import { api } from "./api";
import { AgentMessageFeed } from "./AgentMessageFeed";
import { deploymentOptionLabel } from "./display";
import { EmptyState } from "./EmptyState";
import { errorMessage } from "./errors";
import { InteractionStream, useWorkbenchProjection, visibleApprovalInterrupt, type WorkbenchStream } from "./InteractionStream";
import { InterruptApproval } from "./InterruptApproval";
import { Notice } from "./Notice";
import { RunProgress } from "./RunProgress";
import {
  isAgentRunLive,
  isDeclaredEmbedder,
  type AgentRun,
  type Deployment,
} from "./types";

interface PendingAgentSubmit {
  id: string;
  task: string;
  deploymentId: string;
  projectPath: string;
  embeddingDeploymentId: string;
}

function AgentRunStream(props: {
  threadId: string;
  run: AgentRun | null;
  pendingSubmit: PendingAgentSubmit | null;
  clearPendingSubmit: () => void;
  setRun: (run: AgentRun) => void;
  setTask: (task: string) => void;
  setMessage: (message: string) => void;
}) {
  const { threadId, run, pendingSubmit, clearPendingSubmit, setRun, setTask, setMessage } = props;
  return (
    <InteractionStream threadId={threadId} onError={(error) => setMessage(errorMessage(error))}>
      {(stream) => (
        <AgentRunStreamContent
          stream={stream}
          run={run}
          pendingSubmit={pendingSubmit}
          clearPendingSubmit={clearPendingSubmit}
          setRun={setRun}
          setTask={setTask}
          setMessage={setMessage}
        />
      )}
    </InteractionStream>
  );
}

function AgentRunStreamContent(props: {
  stream: WorkbenchStream;
  run: AgentRun | null;
  pendingSubmit: PendingAgentSubmit | null;
  clearPendingSubmit: () => void;
  setRun: (run: AgentRun) => void;
  setTask: (task: string) => void;
  setMessage: (message: string) => void;
}) {
  const { stream, run, pendingSubmit, clearPendingSubmit, setRun, setTask, setMessage } = props;
  const projection = useWorkbenchProjection(stream);
  const displayRun = projection.run ?? run;
  const visibleInterrupt = visibleApprovalInterrupt(stream, displayRun);
  const submittedIds = useRef(new Set<string>());

  useEffect(() => {
    if (projection.run) {
      setRun(projection.run);
    }
  }, [projection.run, setRun]);

  useEffect(() => {
    if (!pendingSubmit) {
      return;
    }
    if (submittedIds.current.has(pendingSubmit.id)) {
      return;
    }
    submittedIds.current.add(pendingSubmit.id);
    clearPendingSubmit();
    void stream
      .submit(
        { messages: [{ type: "human", content: pendingSubmit.task, id: pendingSubmit.id }] },
        {
          multitaskStrategy: "reject",
          metadata: {
            workbench: {
              deployment_id: pendingSubmit.deploymentId,
              presented_tools: undefined,
              workspace_id: undefined,
              project_path: pendingSubmit.projectPath || undefined,
              embedding_deployment_id: pendingSubmit.embeddingDeploymentId || undefined,
            },
          },
        },
      )
      .then(() => setTask(""))
      .catch(fail);
  }, [clearPendingSubmit, pendingSubmit, setTask, stream]);

  function fail(error: unknown): void {
    setMessage(errorMessage(error));
  }

  return (
    <>
      {visibleInterrupt && displayRun ? (
        <InterruptApproval
          pending={visibleInterrupt.pending}
          onDecide={(type) => {
            void stream
              .respond(
                { decisions: [{ type }] },
                { interruptId: visibleInterrupt.id, namespace: visibleInterrupt.namespace },
              )
              .catch(fail);
          }}
        />
      ) : null}

      {displayRun ? (
        <div className="card">
          <AgentMessageFeed messages={projection.messages} toolCalls={projection.toolCalls} incompleteMessageIds={projection.incompleteMessageIds} />
          <RunProgress
            run={displayRun}
            title={displayRun.task}
            onCancel={() => {
              void api.cancelAgentRun(displayRun.id).then(setRun).catch(fail);
            }}
          />
        </div>
      ) : (
        <EmptyState title="No run yet">Start a model in Models, then give it a task here.</EmptyState>
      )}
    </>
  );
}

export function AgentRunPanel() {
  const [deployments, setDeployments] = useState<Deployment[]>([]);
  const [enabledTools, setEnabledTools] = useState<string[]>([]);
  const [deploymentId, setDeploymentId] = useState("");
  const [embeddingDeploymentId, setEmbeddingDeploymentId] = useState("");
  const [task, setTask] = useState("");
  const [projectPath, setProjectPath] = useState("");
  const [run, setRun] = useState<AgentRun | null>(null);
  const [threadId, setThreadId] = useState<string | null>(null);
  const [pendingSubmit, setPendingSubmit] = useState<PendingAgentSubmit | null>(null);
  const [starting, setStarting] = useState(false);
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
          Run a single task with tool approvals and progress in one place. Use Chat when you want a
          conversation.
        </p>
      </header>

      <form
        className="card"
        onSubmit={(event) => {
          event.preventDefault();
          if (!deploymentId || !task.trim() || liveRunId || starting) {
            return;
          }
          setStarting(true);
          void (async () => {
            const registered = await api.registerAgentInteractionThread({ source_surface: "agent" });
            setThreadId(registered.thread_id);
            setRun(null);
            setMessage("");
            setPendingSubmit({
              id: crypto.randomUUID(),
              task,
              deploymentId,
              projectPath,
              embeddingDeploymentId,
            });
          })()
            .catch(fail)
            .finally(() => setStarting(false));
        }}
      >
        <label>
          Deployment
          <select value={deploymentId} onChange={(event) => setDeploymentId(event.target.value)}>
            {deployments.length === 0 ? <option value="">No model available</option> : null}
            {deployments.map((deployment) => (
              <option key={deployment.id} value={deployment.id}>
                {deploymentOptionLabel(deployment)}
              </option>
            ))}
          </select>
        </label>
        <label>
          Retrieval model (optional)
          <select
            value={embeddingDeploymentId}
            onChange={(event) => setEmbeddingDeploymentId(event.target.value)}
          >
            <option value="">None</option>
            {deployments.map((deployment) => (
              <option key={deployment.id} value={deployment.id}>
                {deploymentOptionLabel(deployment)}
                {isDeclaredEmbedder(deployment) ? "" : " (not marked for retrieval)"}
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
          <button type="submit" disabled={!deploymentId || !task.trim() || Boolean(liveRunId) || starting}>
            Start
          </button>
        </div>
      </form>

      {threadId ? (
        <AgentRunStream
          key={threadId}
          threadId={threadId}
          run={run}
          pendingSubmit={pendingSubmit}
          clearPendingSubmit={() => setPendingSubmit(null)}
          setRun={setRun}
          setTask={setTask}
          setMessage={setMessage}
        />
      ) : (
        <EmptyState title="No run yet">Start a model in Models, then give it a task here.</EmptyState>
      )}
      {message ? <Notice tone="error">{message}</Notice> : null}
    </section>
  );
}
