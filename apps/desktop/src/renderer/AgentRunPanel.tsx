import { useEffect, useRef, useState } from "react";

import { api } from "./api";
import { AgentMessageFeed } from "./AgentMessageFeed";
import { ChatModelControls } from "./ChatModelControls";
import { ApprovalModeControl, approvalModeLabel, type ApprovalMode } from "./ApprovalModeControl";
import { MenuPopover } from "./MenuPopover";
import { workspaceApi, type SetupConfiguration } from "./workspaceApi";
import { RunActivitySummary, helperApprovalOwner } from "./RunActivitySummary";
import { deploymentOptionLabel } from "./display";
import { EmptyState } from "./EmptyState";
import { errorMessage } from "./errors";
import { HoverHelp } from "./HoverHelp";
import { Icon } from "./Icon";
import { InteractionStream, useWorkbenchProjection, visibleApprovalInterrupt, type WorkbenchStream } from "./InteractionStream";
import { InterruptApproval } from "./InterruptApproval";
import { Notice } from "./Notice";
import { RunProgress } from "./RunProgress";
import {
  isAgentRunLive,
  isDeclaredEmbedder,
  type AgentRun,
  type Deployment,
  type RunProfile,
} from "./types";

interface PendingAgentSubmit {
  id: string;
  threadId: string;
  generation: number;
  draftRevision: number;
  task: string;
  deploymentId: string;
  projectPath: string;
  embeddingDeploymentId: string;
  configuration: SetupConfiguration;
  approvalMode: ApprovalMode;
}

function AgentRunStream(props: {
  threadId: string;
  generation: number;
  run: AgentRun | null;
  pendingSubmit: PendingAgentSubmit | null;
  clearPendingSubmit: (pending: PendingAgentSubmit) => void;
  updateRun: (run: AgentRun, owner: AgentRunOwner) => void;
  clearSubmittedDraft: (pending: PendingAgentSubmit) => void;
  setMessage: (message: string) => void;
  isCurrentOwner: (owner: AgentRunOwner) => boolean;
}) {
  const { threadId, generation, run, pendingSubmit, clearPendingSubmit, updateRun, clearSubmittedDraft, setMessage, isCurrentOwner } = props;
  const owner = { threadId, generation };
  return (
    <InteractionStream
      threadId={threadId}
      onError={(error) => {
        if (isCurrentOwner(owner)) {
          setMessage(errorMessage(error));
        }
      }}
    >
      {(stream) => (
        <AgentRunStreamContent
          stream={stream}
          owner={owner}
          run={run}
          pendingSubmit={pendingSubmit}
          clearPendingSubmit={clearPendingSubmit}
          updateRun={updateRun}
          clearSubmittedDraft={clearSubmittedDraft}
          setMessage={setMessage}
          isCurrentOwner={isCurrentOwner}
        />
      )}
    </InteractionStream>
  );
}

interface AgentRunOwner {
  threadId: string;
  generation: number;
}

function AgentRunStreamContent(props: {
  stream: WorkbenchStream;
  owner: AgentRunOwner;
  run: AgentRun | null;
  pendingSubmit: PendingAgentSubmit | null;
  clearPendingSubmit: (pending: PendingAgentSubmit) => void;
  updateRun: (run: AgentRun, owner: AgentRunOwner) => void;
  clearSubmittedDraft: (pending: PendingAgentSubmit) => void;
  setMessage: (message: string) => void;
  isCurrentOwner: (owner: AgentRunOwner) => boolean;
}) {
  const { stream, owner, run, pendingSubmit, clearPendingSubmit, updateRun, clearSubmittedDraft, setMessage, isCurrentOwner } = props;
  const projection = useWorkbenchProjection(stream);
  const displayRun = projection.run ?? run;
  const visibleInterrupt = visibleApprovalInterrupt(stream, displayRun);
  const submittedIds = useRef(new Set<string>());

  useEffect(() => {
    if (projection.run) {
      if (
        pendingSubmit &&
        pendingSubmit.threadId === owner.threadId &&
        pendingSubmit.generation === owner.generation &&
        projection.run.input_message_id === pendingSubmit.id
      ) {
        clearPendingSubmit(pendingSubmit);
      }
      updateRun(projection.run, owner);
    }
  }, [clearPendingSubmit, owner, pendingSubmit, projection.run, updateRun]);

  useEffect(() => {
    if (!pendingSubmit) {
      return;
    }
    if (pendingSubmit.threadId !== owner.threadId || pendingSubmit.generation !== owner.generation || !isCurrentOwner(owner)) {
      return;
    }
    if (submittedIds.current.has(pendingSubmit.id)) {
      return;
    }
    submittedIds.current.add(pendingSubmit.id);
    void stream
      .submit(
        { messages: [{ type: "human", content: pendingSubmit.task, id: pendingSubmit.id }] },
        {
          multitaskStrategy: "reject",
          metadata: {
            workbench: {
              ...pendingSubmit.configuration,
              approval_mode: pendingSubmit.approvalMode,
              deployment_id: pendingSubmit.deploymentId,
              presented_tools: undefined,
              workspace_id: undefined,
              project_path: pendingSubmit.projectPath || undefined,
              embedding_deployment_id: pendingSubmit.embeddingDeploymentId || undefined,
            },
          },
        },
      )
      .then(() => clearSubmittedDraft(pendingSubmit))
      .catch((error: unknown) => {
        clearPendingSubmit(pendingSubmit);
        if (!isCurrentOwner(owner)) {
          return;
        }
        fail(error);
      });
  }, [clearPendingSubmit, clearSubmittedDraft, isCurrentOwner, owner, pendingSubmit, stream]);

  function fail(error: unknown): void {
    setMessage(errorMessage(error));
  }

  return (
    <>
      {visibleInterrupt && displayRun ? (
        <InterruptApproval
          ownerLabel={helperApprovalOwner(displayRun, visibleInterrupt.namespace)}
          pending={visibleInterrupt.pending}
          onRespond={(payload) => {
            void stream
              .respond(
                payload,
                { interruptId: visibleInterrupt.id, namespace: visibleInterrupt.namespace },
              )
              .catch((error: unknown) => {
                if (isCurrentOwner(owner)) {
                  fail(error);
                }
              });
          }}
        />
      ) : null}

      {displayRun ? (
        <div className="card">
          <AgentMessageFeed waiting={Boolean(visibleInterrupt)} toolAuthorizations={displayRun.tool_authorizations} live={isAgentRunLive(displayRun.status)} messages={projection.messages} toolCalls={projection.toolCalls} incompleteMessageIds={projection.incompleteMessageIds} />
          <RunActivitySummary run={displayRun} />
          <RunProgress
            run={displayRun}
            title={displayRun.task}
            onCancel={() => {
              const runId = displayRun.id;
              void api.cancelAgentRun(runId).then((next) => {
                if (next.id === runId) {
                  updateRun(next, owner);
                }
              }).catch((error: unknown) => {
                if (isCurrentOwner(owner)) {
                  fail(error);
                }
              });
            }}
          />
        </div>
      ) : (
        <EmptyState title="Ready for a task">Choose a model and describe what to do.</EmptyState>
      )}
    </>
  );
}

interface AgentRunPanelProps {
  attentionRunId?: string | null;
  onAttentionHandled?: (runId: string) => void;
}

export function AgentRunPanel({ attentionRunId, onAttentionHandled }: AgentRunPanelProps = {}) {
  const [deployments, setDeployments] = useState<Deployment[]>([]);
  const [profiles, setProfiles] = useState<RunProfile[]>([]);
  const [configuration, setConfiguration] = useState<SetupConfiguration>({});
  const [approvalMode, setApprovalMode] = useState<ApprovalMode>("ask");
  const [enabledTools, setEnabledTools] = useState<string[]>([]);
  const [deploymentId, setDeploymentId] = useState("");
  const [embeddingDeploymentId, setEmbeddingDeploymentId] = useState("");
  const [task, setTask] = useState("");
  const [projectPath, setProjectPath] = useState("");
  const [run, setRun] = useState<AgentRun | null>(null);
  const [threadId, setThreadId] = useState<string | null>(null);
  const [boundGeneration, setBoundGeneration] = useState(0);
  const [pendingSubmit, setPendingSubmit] = useState<PendingAgentSubmit | null>(null);
  const [starting, setStarting] = useState(false);
  const [message, setMessage] = useState("");
  const [loadError, setLoadError] = useState("");
  const [attentionAttempt, setAttentionAttempt] = useState(0);
  const [attentionFailed, setAttentionFailed] = useState(false);
  const draftRevision = useRef(0);
  const ownerGeneration = useRef(0);

  async function refresh(): Promise<void> {
    const [nextDeployments, tools, nextProfiles] = await Promise.all([api.deployments(), api.agentTools(), api.profiles()]);
    setDeployments(nextDeployments);
    setProfiles(nextProfiles);
    setEnabledTools(tools.enabled);
    setDeploymentId((current) => current || nextDeployments[0]?.id || "");
    setLoadError("");
  }

  useEffect(() => {
    void refresh().catch((error: unknown) => {
      setLoadError(errorMessage(error));
    });
  }, []);

  useEffect(() => {
    if (!attentionRunId) return;
    let cancelled = false;
    const generation = ++ownerGeneration.current;
    setBoundGeneration(generation);
    setThreadId(null);
    setRun(null);
    setPendingSubmit(null);
    setStarting(true);
    setAttentionFailed(false);
    setMessage("");
    void Promise.all([
      api.agentRun(attentionRunId),
      api.registerAgentInteractionThread({ source_surface: "agent", run_id: attentionRunId }),
    ]).then(([currentRun, registered]) => {
      if (cancelled || ownerGeneration.current !== generation) return;
      setRun(currentRun);
      setThreadId(registered.thread_id);
      onAttentionHandled?.(attentionRunId);
    }).catch((error: unknown) => {
      if (!cancelled && ownerGeneration.current === generation) { setMessage(errorMessage(error)); setAttentionFailed(true); }
    }).finally(() => {
      if (!cancelled && ownerGeneration.current === generation) {
        setStarting(false);
      }
    });
    return () => { cancelled = true; };
  }, [attentionRunId, onAttentionHandled, attentionAttempt]);

  const liveRunId = run && isAgentRunLive(run.status) ? run.id : null;

  function fail(error: unknown): void {
    setMessage(errorMessage(error));
  }

  function updateTask(next: string): void {
    draftRevision.current += 1;
    setTask(next);
  }

  function clearPendingSubmit(pending: PendingAgentSubmit): void {
    setPendingSubmit((current) => (current?.id === pending.id ? null : current));
  }

  function clearSubmittedDraft(pending: PendingAgentSubmit): void {
    if (
      draftRevision.current !== pending.draftRevision ||
      !isCurrentOwner({ threadId: pending.threadId, generation: pending.generation })
    ) {
      return;
    }
    draftRevision.current += 1;
    setTask("");
  }

  function isCurrentOwner(owner: AgentRunOwner): boolean {
    return ownerGeneration.current === owner.generation && threadId === owner.threadId;
  }

  function updateRun(next: AgentRun, owner: AgentRunOwner): void {
    if (isCurrentOwner(owner)) {
      setRun(next);
    }
  }

  if (loadError) {
    return (
      <section className="surface">
        <h2>Workflows</h2>
        <Notice tone="error">{loadError}</Notice>
      </section>
    );
  }

  return (
    <section className="surface workflow-surface">
      <header className="surface-head">
        <div className="entity-head"><h2>Workflows</h2><HoverHelp title="About task runs">Run a task with tools, approvals and progress in one place. Use Chat for an ongoing conversation.</HoverHelp></div>
      </header>

      <form
        className="card"
        onSubmit={(event) => {
          event.preventDefault();
          if ((!deploymentId && !configuration.model_configuration_id) || !task.trim() || liveRunId || pendingSubmit || starting) {
            return;
          }
          const capturedDraftRevision = draftRevision.current;
          const generation = ownerGeneration.current + 1;
          ownerGeneration.current = generation;
          setBoundGeneration(generation);
          setThreadId(null);
          setRun(null);
          setPendingSubmit(null);
          setStarting(true);
          setAttentionFailed(false);
          void (async () => {
            const registered = await api.registerAgentInteractionThread({ source_surface: "agent" });
            if (ownerGeneration.current !== generation) {
              return;
            }
            setThreadId(registered.thread_id);
            setMessage("");
            setPendingSubmit({
              id: crypto.randomUUID(),
              threadId: registered.thread_id,
              generation,
              draftRevision: capturedDraftRevision,
              task,
              deploymentId,
              projectPath,
              embeddingDeploymentId,
              configuration,
              approvalMode,
            });
          })()
            .catch((error: unknown) => {
              if (ownerGeneration.current === generation) {
                fail(error);
              }
            })
            .finally(() => {
              if (ownerGeneration.current === generation) {
                setStarting(false);
              }
            });
        }}
      >
        <h3>Run a task</h3>
        <div className="setup-grid">
        <div className="run-configuration-controls"><ChatModelControls deployments={deployments} profiles={profiles} selectedDeploymentId={deploymentId} configuration={configuration} disabled={starting || Boolean(pendingSubmit)} runtimeBusy={Boolean(liveRunId)} onReloaded={refresh} onApply={async next => { const resolved = await workspaceApi.resolveSetup(null, null, next); setConfiguration(next); setDeploymentId(resolved.configuration.deployment_id ?? next.deployment_id ?? (next.model_configuration_id ? "" : deploymentId)); }} /><MenuPopover label="Workflow access" trigger={<><Icon name="shield" size={16} />{approvalModeLabel(approvalMode)}</>}><ApprovalModeControl value={approvalMode} onChange={setApprovalMode} disabled={starting || Boolean(pendingSubmit)} /></MenuPopover></div>
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
          Project folder
          <input
            value={projectPath}
            onChange={(event) => setProjectPath(event.target.value)}
            placeholder="Optional project path"
          />
        </label>
        </div>
        {projectPath.trim() ? <p className="hint"><Icon name="terminal" size={14} /> Shell commands can access this computer. {approvalMode === "full_access" ? "Enabled shell tools run without approval pauses." : "Shell tools follow approval rules and saved permissions."}</p> : null}
        <label>
          Task
          <textarea value={task} onChange={(event) => updateTask(event.target.value)} placeholder="What would you like to get done?" />
        </label>
        <div className="actions">
          <button type="submit" disabled={(!deploymentId && !configuration.model_configuration_id) || !task.trim() || Boolean(liveRunId) || Boolean(pendingSubmit) || starting}>
            <Icon name="send" size={15} /> Run task
          </button>
          <HoverHelp title="Available tools">{enabledTools.length ? enabledTools.join(", ") : "No tools available."} File and shell tools need a project folder.</HoverHelp>
        </div>
      </form>

      {threadId ? (
        <AgentRunStream
          key={threadId}
          threadId={threadId}
          generation={boundGeneration}
          run={run}
          pendingSubmit={pendingSubmit}
          clearPendingSubmit={clearPendingSubmit}
          updateRun={updateRun}
          clearSubmittedDraft={clearSubmittedDraft}
          setMessage={setMessage}
          isCurrentOwner={isCurrentOwner}
        />
      ) : (
        <EmptyState title="Ready for a task">Choose a model and describe what to do.</EmptyState>
      )}
      {message ? <Notice tone="error" action={attentionFailed && attentionRunId ? <button type="button" disabled={starting} onClick={() => setAttentionAttempt(current => current + 1)}>Retry</button> : undefined}>{message}</Notice> : null}
    </section>
  );
}
