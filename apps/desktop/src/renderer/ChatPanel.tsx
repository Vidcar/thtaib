import { useEffect, useState } from "react";

import { api } from "./api";
import type { ChatConversation, Deployment, LabWorkspace, RunProfile } from "./types";

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
  const [message, setMessage] = useState("");

  async function refresh(): Promise<void> {
    const [nextDeployments, nextProfiles, nextWorkspaces, tools] = await Promise.all([
      api.deployments(),
      api.profiles(),
      api.workspaces(),
      api.agentTools(),
    ]);
    setDeployments(nextDeployments);
    setProfiles(nextProfiles);
    setWorkspaces(nextWorkspaces);
    setEnabledTools(tools.enabled);
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
    if (!conversation || !run || (run.status !== "queued" && run.status !== "running")) {
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

  const runBusy =
    conversation?.current_run?.status === "queued" || conversation?.current_run?.status === "running";

  return (
    <section className="panel">
      <h2>Chat</h2>
      <p className="hint">
        Debug-quality Chat. Start calls the same embedded Deep Agents harness as Agent-run. Filesystem
        tools write the selected project workspace. Transcript is displayed history, not the working
        project. This is not Builder polish.
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
            const created =
              conversation ??
              (await api.createChatConversation({
                deployment_id: deploymentId,
                profile_id: profileId || undefined,
                project_path: projectPath || undefined,
                workspace_id: workspaceId || undefined,
              }));
            setConversation(created);
            const next = await api.startChat(created.id, {
              task,
              deployment_id: deploymentId,
              profile_id: profileId || undefined,
              project_path: projectPath || undefined,
              workspace_id: workspaceId || undefined,
            });
            setConversation(next);
            setMessage(`Started harness run ${next.current_run?.id ?? next.id}`);
          })().catch(fail);
        }}
      >
        <h3>Compose</h3>
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
              setMessage("Fresh conversation. Project files are unchanged.");
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
            deployment: {conversation.deployment_id} · profile: {conversation.profile_id ?? "none"}
          </p>
          <h3>Transcript (not the working project)</h3>
          <pre className="json">{JSON.stringify(conversation.transcript, null, 2)}</pre>
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
