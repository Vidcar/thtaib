import { HoverHelp } from "./HoverHelp";
import { knowledgeKindLabel } from "./labels";
import { Notice } from "./Notice";
import { SettingsNotes } from "./settingsNotes";
import { shortId } from "./display";
import type { Deployment, KnowledgeEntry, RunProfile } from "./types";
import type { AgentSetup, ProjectRecord, ResolvedSetupSelection } from "./workspaceApi";
import { isDeclaredEmbedder } from "./types";

function chatModelLabel(deployment: Deployment): string {
  const name = deployment.display_name.replace(/^(managed|connected):/, "");
  const status = deployment.status === "running" ? "Ready" : deployment.scope === "managed" && deployment.status === "stopped" ? "Loads when sent" : deployment.status;
  return `${name} · ${status}`;
}

export function ConversationSetup(props: {
  projectId: string | null;
  projects: ProjectRecord[];
  conversation: boolean;
  selectionBusy: boolean;
  sending: boolean;
  agentSetupVersionId: string | null;
  agentSetups: AgentSetup[];
  onProject: (projectId: string | null) => void;
  onAgent: (versionId: string | null) => void;
  setupResolving: boolean;
  onManageProjects: () => void;
  onManageAgents: () => void;
  instructionLayers: ResolvedSetupSelection["instruction_layers"];
  missingDeployment: boolean;
  selectedProfile: RunProfile | null;
  embeddingDeploymentId: string;
  onEmbedding: (id: string) => void;
  embedderDeployments: Deployment[];
  deployments: Deployment[];
  knowledgeEntries: KnowledgeEntry[];
  selectedKnowledgeIds: string[];
  onToggleKnowledge: (versionId: string) => void;
  tools: string[];
  filesystemToolsAvailable: boolean | undefined;
  shellToolsAvailable: boolean | undefined;
}) {
  return (
    <div className="setup-panel">
      <div className="setup-grid">
        <label><span>Project <HoverHelp title="About projects">File tools work inside the selected folder. A chat stays with its original project.</HoverHelp></span><select aria-label="Chat project" value={props.projectId ?? ""} disabled={props.conversation || props.selectionBusy || props.sending} onChange={event => props.onProject(event.target.value || null)}><option value="">General · no project</option>{props.projects.map(project => <option key={project.id} value={project.id} disabled={project.missing}>{project.name}{project.missing ? " · folder unavailable" : ""}</option>)}{props.projectId && !props.projects.some(project => project.id === props.projectId) ? <option value={props.projectId}>Unavailable project</option> : null}</select></label>
        <label><span>Agent <HoverHelp title="About saved agents">Applies the selected saved version to the next message. Existing runs and queued messages keep their own setup.</HoverHelp></span><select aria-label="Chat agent" value={props.agentSetupVersionId ?? ""} disabled={props.selectionBusy || props.sending} onChange={event => props.onAgent(event.target.value || null)}><option value="">Default setup</option>{props.agentSetups.map(setup => <option key={setup.id} value={setup.current_version_id} disabled={Boolean(setup.missing_dependencies?.length)}>{setup.name}{setup.missing_dependencies?.length ? " · needs repair" : ""}</option>)}{props.agentSetupVersionId && !props.agentSetups.some(setup => setup.current_version_id === props.agentSetupVersionId) ? <option value={props.agentSetupVersionId}>Saved earlier agent version</option> : null}</select></label>
      </div>
      {props.setupResolving ? <p className="hint" role="status">Applying setup…</p> : null}
      <div className="actions"><button type="button" onClick={props.onManageProjects}>Manage projects</button><button type="button" onClick={props.onManageAgents}>Manage agents</button></div>
      {props.instructionLayers?.length ? <details><summary>Effective instructions · {props.instructionLayers.length} layers</summary>{props.instructionLayers.map((layer, index) => <section key={`${layer.source_id ?? layer.name}-${index}`}><h4>{layer.name}</h4><pre className="wrapped-text">{layer.content}</pre></section>)}</details> : null}
      {props.missingDeployment ? <Notice tone="warn">This conversation's model connection is unavailable. Its history is preserved. Choose a model before sending another message.</Notice> : null}
      {props.selectedProfile ? <SettingsNotes unsupported={props.selectedProfile.bags.startup.unsupported} retired={props.selectedProfile.bags.startup.retired} /> : null}
      {props.selectedProfile?.bags.agent.unsupported.length ? <Notice tone="warn">Unsupported agent settings: {props.selectedProfile.bags.agent.unsupported.join(", ")}. These saved values do not govern execution.</Notice> : null}
      <details>
        <summary>Knowledge <HoverHelp title="About conversation knowledge">Choose memories and instructions for this chat. Document search needs a running embedding model.</HoverHelp></summary>
        <label>
          Document search model
          <select value={props.embeddingDeploymentId} disabled={props.selectionBusy || props.sending} onChange={event => props.onEmbedding(event.target.value)}>
            <option value="">None — no retrieval</option>
            {props.embedderDeployments.map(deployment => <option key={deployment.id} value={deployment.id}>{chatModelLabel(deployment)}</option>)}
            {props.embedderDeployments.length === 0 ? props.deployments.filter(item => !isDeclaredEmbedder(item)).map(deployment => <option key={deployment.id} value={deployment.id}>{chatModelLabel(deployment)} (not marked for retrieval)</option>) : null}
          </select>
        </label>
        <fieldset className="choice-set">
          <legend>Knowledge versions</legend>
          {props.knowledgeEntries.length === 0 ? <p className="hint">None yet. Create them on Knowledge.</p> : props.knowledgeEntries.map(entry => (
            <label key={entry.id} className="check-row">
              <input type="checkbox" checked={props.selectedKnowledgeIds.includes(entry.current_version_id)} onChange={() => props.onToggleKnowledge(entry.current_version_id)} />
              {knowledgeKindLabel(entry.kind)} · {entry.display_name ?? shortId(entry.id)}
            </label>
          ))}
        </fieldset>
      </details>
      {props.conversation && props.tools.length > 0 ? <details><summary>{props.tools.length} {props.tools.length === 1 ? "tool available" : "tools available"}</summary><p className="hint">{props.tools.join(", ")}</p></details> : <p className="hint">{props.conversation ? "No tools available." : "Available tools depend on the project you choose."}</p>}
      {(props.filesystemToolsAvailable === false || props.shellToolsAvailable === false) ? <p className="hint">{props.filesystemToolsAvailable === false ? "Project files unavailable. " : ""}{props.shellToolsAvailable === false ? "Host shell unavailable." : ""}</p> : null}
    </div>
  );
}
