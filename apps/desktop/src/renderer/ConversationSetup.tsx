import { useEffect, useState } from "react";
import { api } from "./api";
import { HoverHelp } from "./HoverHelp";
import { knowledgeKindLabel } from "./labels";
import { Notice } from "./Notice";
import { SettingsNotes } from "./settingsNotes";
import { shortId } from "./display";
import type { Deployment, KnowledgeEntry, KnowledgeVersion, RunProfile } from "./types";
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
  onToggleKnowledge: (versionId: string, replacedIds?: string[]) => void;
  tools: string[];
  filesystemToolsAvailable: boolean | undefined;
  shellToolsAvailable: boolean | undefined;
}) {
  const [toolDetails, setToolDetails] = useState<Array<{ id: string; name: string; description: string }>>([]);
  const [earlierVersions, setEarlierVersions] = useState<KnowledgeVersion[]>([]);
  const earlierIds = props.selectedKnowledgeIds.filter(id => !props.knowledgeEntries.some(entry => entry.current_version_id === id));
  useEffect(() => {
    let cancelled = false;
    void Promise.allSettled(earlierIds.map(id => api.knowledgeVersion(id))).then(results => {
      if (!cancelled) setEarlierVersions(results.flatMap(result => result.status === "fulfilled" ? [result.value] : []));
    });
    return () => { cancelled = true; };
  }, [JSON.stringify(earlierIds)]);
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
        <summary>Knowledge <HoverHelp title="About conversation knowledge">Choose exact memory, skill and instruction versions for your next message. Submitted and paused turns keep their original selection. Documents support local text search; an embedding model adds similarity search.</HoverHelp></summary>
        <label>
          Similarity search model (optional)
          <select value={props.embeddingDeploymentId} disabled={props.selectionBusy || props.sending} onChange={event => props.onEmbedding(event.target.value)}>
            <option value="">None — local text search</option>
            {props.embedderDeployments.map(deployment => <option key={deployment.id} value={deployment.id}>{chatModelLabel(deployment)}</option>)}
            {props.embedderDeployments.length === 0 ? props.deployments.filter(item => !isDeclaredEmbedder(item)).map(deployment => <option key={deployment.id} value={deployment.id}>{chatModelLabel(deployment)} (not marked for retrieval)</option>) : null}
          </select>
        </label>
        <fieldset className="choice-set">
          <legend>Use on next turn</legend>
          <p className="hint">Selected memory is included in full. Saving a new version does not replace the one you selected. Estimates below use 3 characters per token and exclude prompt wrappers.</p>
          {props.knowledgeEntries.length === 0 ? <p className="hint">None yet. Create them on Knowledge.</p> : props.knowledgeEntries.map(entry => (
            <label key={entry.id} className="check-row">
              <input type="checkbox" checked={props.selectedKnowledgeIds.includes(entry.current_version_id)} disabled={props.selectionBusy || props.sending} onChange={() => props.onToggleKnowledge(entry.current_version_id, earlierVersions.filter(version => version.entry_id === entry.id).map(version => version.id))} />
              {knowledgeKindLabel(entry.kind)} · {entry.display_name ?? shortId(entry.id)}
              {entry.kind === "memory" && entry.estimated_content_tokens != null ? <small title={entry.token_counting_method}>~{entry.estimated_content_tokens.toLocaleString()} tokens</small> : null}
            </label>
          ))}
          {earlierIds.map(versionId => {
            const version = earlierVersions.find(item => item.id === versionId);
            const entry = props.knowledgeEntries.find(item => item.id === version?.entry_id);
            return <div key={versionId} className="actions"><span>{entry?.display_name ?? "Selected earlier version"} · {shortId(versionId)}{version?.estimated_content_tokens != null ? ` · ~${version.estimated_content_tokens.toLocaleString()} tokens` : ""}</span><button type="button" disabled={props.selectionBusy || props.sending} onClick={() => props.onToggleKnowledge(versionId)}>Remove from next turn</button>{entry ? <button type="button" disabled={props.selectionBusy || props.sending} onClick={() => props.onToggleKnowledge(entry.current_version_id, [versionId])}>Use latest version</button> : null}</div>;
          })}
        </fieldset>
      </details>
       <details><summary>{props.tools.length} {props.tools.length === 1 ? "tool" : "tools"} selected for the next message</summary>{props.tools.length ? <ul className="plain-list">{props.tools.map(id => { const tool = toolDetails.find(item => item.id === id); return <li key={id}>{tool?.name ?? id}<HoverHelp title={tool?.name ?? id}>{tool?.description ?? "Tool details unavailable"}</HoverHelp></li>; })}</ul> : <p className="hint">No optional tools selected. Use + beside the message to choose tools.</p>}</details>
      {(props.filesystemToolsAvailable === false || props.shellToolsAvailable === false) ? <p className="hint">{props.filesystemToolsAvailable === false ? "Project files unavailable. " : ""}{props.shellToolsAvailable === false ? "Host shell unavailable." : ""}</p> : null}
    </div>
  );
}
