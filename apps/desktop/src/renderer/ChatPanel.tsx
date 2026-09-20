import { useEffect, useState } from "react";

import { api } from "./api";
import { InterruptApproval } from "./InterruptApproval";
import { EffectiveSetupNotes, SettingsNotes } from "./settingsNotes";
import {
  isAgentRunLive,
  visiblePendingInterrupt,
  isDeclaredEmbedder,
  type ChatConversation,
  type Deployment,
  type KnowledgeEntry,
  type LabWorkspace,
  type RunProfile,
} from "./types";

export function ChatPanel() {
  const [deployments, setDeployments] = useState<Deployment[]>([]);
  const [profiles, setProfiles] = useState<RunProfile[]>([]);
  const [workspaces, setWorkspaces] = useState<LabWorkspace[]>([]);
  const [enabledTools, setEnabledTools] = useState<string[]>([]);
  const [deploymentId, setDeploymentId] = useState("");
  const [embeddingDeploymentId, setEmbeddingDeploymentId] = useState("");
  const [profileId, setProfileId] = useState("");
  const [workspaceId, setWorkspaceId] = useState("");
  const [projectPath, setProjectPath] = useState("");
  const [task, setTask] = useState("Ask a question or complete a task. File tools need a project path.");
  const [conversation, setConversation] = useState<ChatConversation | null>(null);
  const [conversations, setConversations] = useState<ChatConversation[]>([]);
  const [knowledgeEntries, setKnowledgeEntries] = useState<KnowledgeEntry[]>([]);
  const [selectedKnowledgeIds, setSelectedKnowledgeIds] = useState<string[]>([]);
  const [message, setMessage] = useState("");

  async function refresh(): Promise<void> {
    const [nextDeployments, nextProfiles, nextWorkspaces, tools, nextConversations, nextKnowledge] =
      await Promise.all([
        api.deployments(),
        api.profiles(),
        api.workspaces(),
        api.agentTools(),
        api.chatConversations(),
        api.knowledgeEntries(),
      ]);
    setDeployments(nextDeployments);
    setProfiles(nextProfiles);
    setWorkspaces(nextWorkspaces);
    setEnabledTools(tools.enabled);
    setConversations(nextConversations);
    setKnowledgeEntries(nextKnowledge);
    setDeploymentId((current) => current || nextDeployments[0]?.id || "");
    setProfileId((current) => current || nextProfiles[0]?.id || "");
  }

  useEffect(() => {
    void refresh().catch((error: unknown) => {
      setMessage(error instanceof Error ? error.message : String(error));
    });
  }, []);

  const conversationId = conversation?.id ?? null;
  const liveRunId =
    conversation?.current_run && isAgentRunLive(conversation.current_run.status)
      ? conversation.current_run.id
      : null;

  useEffect(() => {
    if (!conversationId || !liveRunId) {
      return;
    }
    const controller = new AbortController();
    void api
      .subscribeChatConversation(conversationId, controller.signal, (next) => {
        setConversation(next);
        if (next.deploy_health?.message) {
          setMessage(next.deploy_health.message);
        } else if (next.current_run?.error) {
          setMessage(next.current_run.error);
        }
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) {
          return;
        }
        setMessage(error instanceof Error ? error.message : String(error));
      });
    return () => controller.abort();
  }, [conversationId, liveRunId]);

  function fail(error: unknown): void {
    setMessage(error instanceof Error ? error.message : String(error));
  }

  const runBusy = conversation?.current_run ? isAgentRunLive(conversation.current_run.status) : false;
  const selectedProfile = profiles.find((profile) => profile.id === profileId) ?? null;
  const pendingInterrupt = visiblePendingInterrupt(conversation?.current_run);

  return (
    <section className="panel">
      <h2>Chat</h2>
      <p className="hint">
        Debug-quality Chat. Follow-ups reuse the conversation LangGraph thread on the embedded Deep
        Agents harness. Selected profile per-request settings and selected knowledge versions are
        resolved before the run (selected ≠ loaded ≠ applied). Transcript is displayed history, not
        harness context and not the working project. New conversation allocates a new thread;
        project files and permitted durable knowledge stay. A project folder is optional; file
        tools and the host shell are unavailable until one is bound. Dangerous host-shell
        commands pause here for Approve or Deny (Deep Agents interrupt_on, not a durable
        inbox). History edits are display-only. A model/profile change applies to the next run
        on the same thread. A profile agent.system_prompt is the identity; Chat surface
        instructions are composed under it, not a silent replacement. Live assistant
        completion requires a healthy managed/connected llama.cpp — harness model_requests /
        thread reuse prove continuity only. This is not Builder polish.
      </p>

      <div className="card">
        <h3>Enabled tools</h3>
        <p>
          {(conversation?.enabled_tools ?? enabledTools).length
            ? (conversation?.enabled_tools ?? enabledTools).join(", ")
            : "none"}
        </p>
        {conversation && conversation.filesystem_tools_available === false ? (
          <p className="hint">File tools are unavailable until a project folder is bound.</p>
        ) : null}
        {conversation && conversation.shell_tools_available === false ? (
          <p className="hint">
            Host shell (execute) is unavailable until a project folder is bound as cwd. A
            home-directory default is not invented.
          </p>
        ) : null}
      </div>

      <form
        className="card"
        onSubmit={(event) => {
          event.preventDefault();
          void (async () => {
            const knowledgeRefs = selectedKnowledgeIds;
            const created =
              conversation ??
              (await api.createChatConversation({
                deployment_id: deploymentId,
                profile_id: profileId || undefined,
                project_path: projectPath || undefined,
                workspace_id: workspaceId || undefined,
                knowledge_version_refs: knowledgeRefs,
                embedding_deployment_id: embeddingDeploymentId || undefined,
              }));
            setConversation(created);
            const next = await api.startChat(created.id, {
              task,
              deployment_id: deploymentId,
              profile_id: profileId || undefined,
              project_path: projectPath || undefined,
              workspace_id: workspaceId || undefined,
              knowledge_version_refs: knowledgeRefs,
              embedding_deployment_id: embeddingDeploymentId || undefined,
            });
            setConversation(next);
            setConversations((current) => {
              const others = current.filter((item) => item.id !== next.id);
              return [next, ...others];
            });
            setMessage(
              next.deploy_health?.message ??
                `Started harness run ${next.current_run?.id ?? next.id} on thread ${next.thread_id ?? "unassigned"}`,
            );
          })().catch(fail);
        }}
      >
        <h3>Compose</h3>
        <label>
          Reopen conversation
          <select
            value={conversation?.id ?? ""}
            onChange={(event) => {
              const nextId = event.target.value;
              if (!nextId) {
                setConversation(null);
                setMessage("Fresh conversation. Project files and durable knowledge are unchanged.");
                return;
              }
              void api
                .chatConversation(nextId)
                .then((next) => {
                  setConversation(next);
                  setDeploymentId(next.deployment_id);
                  setEmbeddingDeploymentId(next.embedding_deployment_id ?? "");
                  setProfileId(next.profile_id ?? "");
                  setWorkspaceId(next.workspace_id ?? "");
                  setProjectPath(next.project_path ?? "");
                  setSelectedKnowledgeIds([
                    ...(next.memory_version_refs ?? []),
                    ...(next.skill_version_refs ?? []),
                    ...(next.protected_instruction_version_refs ?? []),
                  ]);
                  setMessage(`Reopened ${next.id} on thread ${next.thread_id ?? "unassigned"}.`);
                })
                .catch(fail);
            }}
          >
            <option value="">New conversation</option>
            {conversations.map((item) => (
              <option key={item.id} value={item.id}>
                {item.id} · thread {item.thread_id ?? "unassigned"}
              </option>
            ))}
          </select>
        </label>
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
          Embedding deployment (optional retrieval)
          <select
            value={embeddingDeploymentId}
            onChange={(event) => setEmbeddingDeploymentId(event.target.value)}
          >
            <option value="">None — knowledge stays prompt-append; no retrieval</option>
            {deployments.map((deployment) => (
              <option key={deployment.id} value={deployment.id}>
                {deployment.display_name} · {deployment.status}
                {isDeclaredEmbedder(deployment) ? " · embedding:on" : ""}
              </option>
            ))}
          </select>
        </label>
        <p className="hint">
          Retrieval is requested only when an embedding deployment is selected. That
          deployment must already be loaded with embedding:on and pooling other than
          none. A GGUF file on disk is not a deployment. Empty keeps knowledge as
          always-load context and does not fail closed.
        </p>
        <label>
          Profile
          <select value={profileId} onChange={(event) => setProfileId(event.target.value)}>
            <option value="">None</option>
            {profiles.map((profile) => (
              <option key={profile.id} value={profile.id}>
                {profile.display_name}
                {profile.bags.startup.unsupported.length || profile.bags.startup.retired.length
                  ? " · has unsupported/retired startup"
                  : ""}
              </option>
            ))}
          </select>
        </label>
        {selectedProfile ? (
          <SettingsNotes
            unsupported={selectedProfile.bags.startup.unsupported}
            retired={selectedProfile.bags.startup.retired}
          />
        ) : null}
        <label>
          Lab workspace (optional)
          <select
            value={workspaceId}
            onChange={(event) => {
              const nextId = event.target.value;
              setWorkspaceId(nextId);
              const selected = workspaces.find((item) => item.id === nextId);
              if (selected) {
                setProjectPath(selected.path);
              }
            }}
          >
            <option value="">Use project path</option>
            {workspaces.map((workspace) => (
              <option key={workspace.id} value={workspace.id}>
                {workspace.display_name} · {workspace.path}
              </option>
            ))}
          </select>
        </label>
        <label>
          Project workspace path
          <input
            value={projectPath}
            onChange={(event) => setProjectPath(event.target.value)}
            placeholder="%LOCALAPPDATA%\LocalAIWorkbench\workspaces\…"
          />
        </label>
        <fieldset>
          <legend>Knowledge versions (content is loaded; id-only does not apply)</legend>
          {knowledgeEntries.length === 0 ? (
            <p className="hint">No knowledge entries. Create them on the Knowledge panel.</p>
          ) : (
            knowledgeEntries.map((entry) => (
              <label key={entry.id}>
                <input
                  type="checkbox"
                  checked={selectedKnowledgeIds.includes(entry.current_version_id)}
                  onChange={() => {
                    const versionId = entry.current_version_id;
                    setSelectedKnowledgeIds((current) =>
                      current.includes(versionId)
                        ? current.filter((item) => item !== versionId)
                        : [...current, versionId],
                    );
                  }}
                />{" "}
                {entry.kind} · {entry.display_name ?? entry.id} · {entry.current_version_id}
              </label>
            ))
          )}
        </fieldset>
        <label>
          Task
          <textarea value={task} onChange={(event) => setTask(event.target.value)} />
        </label>
        <div className="actions">
          <button type="submit" disabled={!deploymentId || runBusy}>
            Start
          </button>
          <button
            type="button"
            disabled={!conversation || !runBusy}
            onClick={() => {
              if (!conversation) {
                return;
              }
              void api
                .cancelChat(conversation.id)
                .then(setConversation)
                .catch(fail);
            }}
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={() => {
              setConversation(null);
              setMessage("Fresh conversation. Project files and durable knowledge are unchanged.");
            }}
          >
            New conversation
          </button>
          <button
            type="button"
            disabled={!conversation}
            onClick={() => {
              if (!conversation) {
                return;
              }
              void api
                .replaceChatTranscript(conversation.id, [])
                .then(setConversation)
                .catch(fail);
            }}
          >
            Clear transcript
          </button>
        </div>
      </form>

      {conversation ? (
        <div className="card">
          <h3>
            {conversation.id}
            <span className="badge">{conversation.current_run?.status ?? "idle"}</span>
          </h3>
          <p>
            harness: {conversation.harness} · second loop: {String(conversation.second_agent_loop)} ·
            project: {conversation.project_path ?? "(none)"} · file tools:{" "}
            {conversation.filesystem_tools_available ? "available" : "unavailable"} · host
            shell: {conversation.shell_tools_available ? "available" : "unavailable"}
          </p>
          {pendingInterrupt ? (
            <InterruptApproval
              pending={pendingInterrupt}
              onDecide={(type) => {
                void api.decideChatInterrupt(conversation.id, type).then(setConversation).catch(fail);
              }}
            />
          ) : null}
          <p>
            conversation: {conversation.id} · thread: {conversation.thread_id ?? "unassigned"} ·
            deployment: {conversation.deployment_id} · embedder:{" "}
            {conversation.embedding_deployment_id ?? "none"} · profile:{" "}
            {conversation.profile_id ?? "none"}
          </p>
          <h3>Transcript (display only — not harness context)</h3>
          <pre className="json">{JSON.stringify(conversation.transcript, null, 2)}</pre>
          {conversation.deploy_health?.message ? (
            <p className="status">{conversation.deploy_health.message}</p>
          ) : conversation.current_run?.error ? (
            <p className="status">{conversation.current_run.error}</p>
          ) : null}
          <h3>Deploy health (live completion ≠ continuity)</h3>
          <pre className="json">{JSON.stringify(conversation.deploy_health ?? null, null, 2)}</pre>
          <h3>Continuity (conversation ↔ thread ↔ run)</h3>
          <pre className="json">
            {JSON.stringify(
              conversation.continuity ?? {
                conversation_id: conversation.id,
                thread_id: conversation.thread_id,
                run_ids: conversation.run_ids,
                current_run_id: conversation.current_run_id,
              },
              null,
              2,
            )}
          </pre>
          <h3>Run linkage (application records)</h3>
          <pre className="json">
            {JSON.stringify(
              {
                conversation_id: conversation.id,
                conversation_thread_id: conversation.thread_id ?? null,
                run_thread_id: conversation.current_run?.thread_id ?? null,
                checkpoint_ids: conversation.current_run?.checkpoint_ids ?? [],
                related_files: conversation.current_run?.related_files ?? [],
              },
              null,
              2,
            )}
          </pre>
          <h3>Effective setup (selected ≠ loaded ≠ applied)</h3>
          <EffectiveSetupNotes
            unsupportedStartup={conversation.current_run?.effective_setup?.unsupported?.startup}
            retiredStartup={conversation.current_run?.effective_setup?.retired?.startup}
            startupMismatches={conversation.current_run?.effective_setup?.startup_mismatches}
          />
          <pre className="json">
            {JSON.stringify(conversation.current_run?.effective_setup ?? null, null, 2)}
          </pre>
          <h3>Captured model requests</h3>
          <pre className="json">
            {JSON.stringify(conversation.current_run?.model_requests ?? [], null, 2)}
          </pre>
          <h3>Harness events</h3>
          <pre className="json">{JSON.stringify(conversation.events, null, 2)}</pre>
          <h3>Evidence (not judgement)</h3>
          <pre className="json">
            {JSON.stringify(conversation.current_run?.completion?.evidence ?? null, null, 2)}
          </pre>
        </div>
      ) : (
        <p className="hint">
          No Chat conversation yet. Bind a deployment, then Start. A project path is optional; file
          tools need one.
        </p>
      )}
      {message ? <p className="status">{message}</p> : null}
    </section>
  );
}
