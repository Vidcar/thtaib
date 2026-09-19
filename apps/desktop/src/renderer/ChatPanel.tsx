import { useEffect, useState } from "react";

import { api } from "./api";
import {
  isAgentRunLive,
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
  const [profileId, setProfileId] = useState("");
  const [workspaceId, setWorkspaceId] = useState("");
  const [projectPath, setProjectPath] = useState("");
  const [task, setTask] = useState("Edit a real file in the selected project workspace.");
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

  useEffect(() => {
    const run = conversation?.current_run;
    if (!conversation || !run || !isAgentRunLive(run.status)) {
      return;
    }
    const timer = window.setInterval(() => {
      void api
        .chatConversation(conversation.id)
        .then(setConversation)
        .catch((error: unknown) => setMessage(error instanceof Error ? error.message : String(error)));
    }, 750);
    return () => window.clearInterval(timer);
  }, [conversation]);

  function fail(error: unknown): void {
    setMessage(error instanceof Error ? error.message : String(error));
  }

  const runBusy = conversation?.current_run ? isAgentRunLive(conversation.current_run.status) : false;

  return (
    <section className="panel">
      <h2>Chat</h2>
      <p className="hint">
        Debug-quality Chat. Follow-ups reuse the conversation LangGraph thread on the embedded Deep
        Agents harness. Selected profile per-request settings and selected knowledge versions are
        resolved before the run (selected ≠ loaded ≠ applied). Transcript is displayed history, not
        harness context and not the working project. New conversation allocates a new thread;
        project files and permitted durable knowledge stay. History edits are display-only. A
        model/profile change applies to the next run on the same thread. This is not Builder
        polish.
      </p>

      <div className="card">
        <h3>Enabled tools</h3>
        <p>{enabledTools.length ? enabledTools.join(", ") : "none"}</p>
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
              }));
            setConversation(created);
            const next = await api.startChat(created.id, {
              task,
              deployment_id: deploymentId,
              profile_id: profileId || undefined,
              project_path: projectPath || undefined,
              workspace_id: workspaceId || undefined,
              knowledge_version_refs: knowledgeRefs,
            });
            setConversation(next);
            setConversations((current) => {
              const others = current.filter((item) => item.id !== next.id);
              return [next, ...others];
            });
            setMessage(
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
                  setProfileId(next.profile_id ?? "");
                  setWorkspaceId(next.workspace_id ?? "");
                  setProjectPath(next.project_path);
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
          Profile
          <select value={profileId} onChange={(event) => setProfileId(event.target.value)}>
            <option value="">None</option>
            {profiles.map((profile) => (
              <option key={profile.id} value={profile.id}>
                {profile.display_name}
              </option>
            ))}
          </select>
        </label>
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
            project: {conversation.project_path}
          </p>
          <p>
            conversation: {conversation.id} · thread: {conversation.thread_id ?? "unassigned"} ·
            deployment: {conversation.deployment_id} · profile: {conversation.profile_id ?? "none"}
          </p>
          <h3>Transcript (display only — not harness context)</h3>
          <pre className="json">{JSON.stringify(conversation.transcript, null, 2)}</pre>
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
        <p className="hint">No Chat conversation yet. Bind a deployment and project path, then Start.</p>
      )}
      {message ? <p className="status">{message}</p> : null}
    </section>
  );
}
