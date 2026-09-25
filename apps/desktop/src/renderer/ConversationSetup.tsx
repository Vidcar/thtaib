import { useEffect, useState } from "react";
import { api } from "./api";
import { HoverHelp } from "./HoverHelp";
import { knowledgeKindLabel } from "./labels";
import { Notice } from "./Notice";
import { SettingsNotes } from "./settingsNotes";
import { shortId } from "./display";
import type { Deployment, KnowledgeEntry, RunProfile } from "./types";
import type { ProjectRecord, ResolvedSetupSelection } from "./workspaceApi";
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
  onProject: (projectId: string | null) => void;
  setupResolving: boolean;
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
  memoryLocked: boolean;
  pinnedMemoryVersionIds: string[];
  onToggleKnowledge: (versionId: string) => void;
  tools: string[];
  filesystemToolsAvailable: boolean | undefined;
  shellToolsAvailable: boolean | undefined;
}) {
  const [toolDetails, setToolDetails] = useState<Array<{ id: string; name: string; description: string }>>([]);
  useEffect(() => { let cancelled = false; void api.agentTools().then(result => { if (!cancelled) setToolDetails(result.tools ?? []); }).catch(() => {}); return () => { cancelled = true; }; }, []);
  return (
    <div className="setup-panel">
      <div className="setup-grid">
        <label><span>Project <HoverHelp title="About projects">File tools work inside the selected folder. A chat stays with its original project.</HoverHelp></span><select aria-label="Chat project" value={props.projectId ?? ""} disabled={props.conversation || props.selectionBusy || props.sending} onChange={event => props.onProject(event.target.value || null)}><option value="">General · no project</option>{props.projects.map(project => <option key={project.id} value={project.id} disabled={project.missing}>{project.name}{project.missing ? " · folder unavailable" : ""}</option>)}{props.projectId && !props.projects.some(project => project.id === props.projectId) ? <option value={props.projectId}>Unavailable project</option> : null}</select></label>
      </div>
      {props.setupResolving ? <p className="hint" role="status">Applying setup…</p> : null}
      <div className="actions"><button type="button" onClick={props.onManageAgents}>Manage agents</button></div>
      {props.instructionLayers?.length ? <details><summary>Effective instructions · {props.instructionLayers.length} layers</summary>{props.instructionLayers.map((layer, index) => <section key={`${layer.source_id ?? layer.name}-${index}`}><h4>{layer.name}</h4><pre className="wrapped-text">{layer.content}</pre></section>)}</details> : null}
      {props.missingDeployment ? <Notice tone="warn">This conversation's model connection is unavailable. Its history is preserved. Choose a model before sending another message.</Notice> : null}
      {props.selectedProfile ? <SettingsNotes unsupported={props.selectedProfile.bags.startup.unsupported} retired={props.selectedProfile.bags.startup.retired} /> : null}
      <details>
        <summary>Knowledge <HoverHelp title="About conversation knowledge">Choose skills and instructions for the next turn. Memory is fixed after the first turn; start a new chat to use changed memories. Document search needs a running embedding model.</HoverHelp></summary>
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
          {props.memoryLocked ? <p className="hint">Memory is fixed for this conversation. Start a new chat to use another memory or a newer version.</p> : null}
          {props.knowledgeEntries.length === 0 ? <p className="hint">None yet. Create them on Knowledge.</p> : props.knowledgeEntries.map(entry => (
            <label key={entry.id} className="check-row">
              <input type="checkbox" checked={entry.kind === "memory" && props.memoryLocked ? props.pinnedMemoryVersionIds.includes(entry.current_version_id) : props.selectedKnowledgeIds.includes(entry.current_version_id)} disabled={entry.kind === "memory" && props.memoryLocked} onChange={() => props.onToggleKnowledge(entry.current_version_id)} />
              {knowledgeKindLabel(entry.kind)} · {entry.display_name ?? shortId(entry.id)}
            </label>
          ))}
          {props.memoryLocked ? props.pinnedMemoryVersionIds.filter(versionId => !props.knowledgeEntries.some(entry => entry.kind === "memory" && entry.current_version_id === versionId)).map(versionId => (
            <p key={versionId} className="hint">Pinned earlier memory version · {shortId(versionId)}</p>
          )) : null}
        </fieldset>
      </details>
      {props.conversation && props.tools.length > 0 ? <details><summary>{props.tools.length} {props.tools.length === 1 ? "tool available" : "tools available"}</summary><ul className="plain-list">{props.tools.map(id => { const tool = toolDetails.find(item => item.id === id); return <li key={id}>{tool?.name ?? id}<HoverHelp title={tool?.name ?? id}>{tool?.description ?? "Tool details unavailable"}</HoverHelp></li>; })}</ul></details> : <p className="hint">{props.conversation ? "No tools available." : "Available tools depend on the project you choose."}</p>}
      {(props.filesystemToolsAvailable === false || props.shellToolsAvailable === false) ? <p className="hint">{props.filesystemToolsAvailable === false ? "Project files unavailable. " : ""}{props.shellToolsAvailable === false ? "Host shell unavailable." : ""}</p> : null}
    </div>
  );
}
