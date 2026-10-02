import { useEffect, useId, useRef, useState } from "react";
import { knowledgeApi, type SkillGuidedFields, type SkillPreview, type SkillResourceChange } from "./knowledgeApi";
import { errorMessage } from "./errors";
import { Notice } from "./Notice";
import { CompactSwitch, SettingRow } from "./CompactControls";
import { HoverHelp } from "./HoverHelp";
import { api } from "./api";
import { connectionsApi, type Connection } from "./connectionsApi";
import { SkillResourceEditor } from "./SkillPackageControls";
import type { KnowledgeScope } from "./types";
import type { SchemaSkillResource } from "../generated/shared-contracts/openapi";

export function SkillEditor({ content, onChange, disabled = false, scope, scopeId, entryId, versionId, resources = [], resourceChanges, onResourceChanges, onStateChange }: {
  content: string; onChange: (value: string) => void; disabled?: boolean; scope: KnowledgeScope; scopeId?: string | null;
  entryId?: string; versionId?: string; resources?: SchemaSkillResource[]; resourceChanges: SkillResourceChange[];
  onResourceChanges: (changes: SkillResourceChange[]) => void; onStateChange: (valid: boolean) => void;
}) {
  const id = useId();
  const [tab, setTab] = useState<"guided" | "source">("guided");
  const [preview, setPreview] = useState<SkillPreview | null>(null);
  const [fields, setFields] = useState<SkillGuidedFields | null>(null);
  const [pending, setPending] = useState(true);
  const [error, setError] = useState("");
  const [requirementsOpen, setRequirementsOpen] = useState(false);
  const [tools, setTools] = useState<Array<{ id: string; name: string }>>([]);
  const [connections, setConnections] = useState<Connection[]>([]);
  const [requirementsError, setRequirementsError] = useState("");
  const serial = useRef(0);
  const unresolvedFields = useRef<SkillGuidedFields | null>(null);
  const resourcePending = useRef(false);
  const validSource = useRef(false);
  const onChangeRef = useRef(onChange); onChangeRef.current = onChange;
  const onStateRef = useRef(onStateChange); onStateRef.current = onStateChange;
  const markValid = (valid: boolean) => { validSource.current = valid; onStateRef.current(valid && !resourcePending.current); };
  useEffect(() => {
    const requestId = ++serial.current;
    unresolvedFields.current = null;
    setPending(true); markValid(false); setError("");
    void knowledgeApi.previewSkill({ content, scope, scope_id: scopeId, entry_id: entryId }).then(next => {
      if (requestId !== serial.current) return;
      setPreview(next);
      setFields(next.guided_available ? { name: next.name ?? "", description: next.description ?? "", instructions: next.instructions ?? "", required_tools: next.required_tools ?? [], required_connections: next.required_connections ?? [], requires_project: next.requires_project ?? false } : null);
      markValid(next.valid);
    }).catch(failure => { if (requestId === serial.current) setError(errorMessage(failure)); }).finally(() => { if (requestId === serial.current) setPending(false); });
    return () => { ++serial.current; };
  }, [content, scope, scopeId, entryId]);

  useEffect(() => {
    if (!requirementsOpen) return;
    let cancelled = false;
    void Promise.allSettled([api.agentTools(), connectionsApi.list()]).then(([toolResult, connectionResult]) => {
      if (cancelled) return;
      if (toolResult.status === "fulfilled") setTools(toolResult.value.tools ?? toolResult.value.enabled.map(id => ({ id, name: id })));
      if (connectionResult.status === "fulfilled") setConnections(connectionResult.value);
      setRequirementsError([toolResult, connectionResult].filter(result => result.status === "rejected").map(result => errorMessage(result.reason)).join(" · "));
    });
    return () => { cancelled = true; };
  }, [requirementsOpen]);

  function patch(nextFields: SkillGuidedFields) {
    const requestId = ++serial.current;
    unresolvedFields.current = nextFields;
    setFields(nextFields); setPending(true); markValid(false); setError("");
    void knowledgeApi.previewSkill({ content, fields: nextFields, scope, scope_id: scopeId, entry_id: entryId }).then(next => {
      if (requestId !== serial.current) return;
      unresolvedFields.current = null;
      setPreview(next);
      onChangeRef.current(next.content);
      markValid(next.valid);
    }).catch(failure => { if (requestId === serial.current) setError(errorMessage(failure)); }).finally(() => { if (requestId === serial.current) setPending(false); });
  }

  return <div className="skill-editor workspace-editor">
    <nav className="model-tabs" aria-label="Skill editor"><button type="button" aria-current={tab === "guided" ? "page" : undefined} disabled={disabled || pending || Boolean(unresolvedFields.current)} onClick={() => setTab("guided")}>Guided</button><button type="button" aria-current={tab === "source" ? "page" : undefined} disabled={disabled || Boolean(unresolvedFields.current)} onClick={() => setTab("source")}>Source</button></nav>
    {tab === "source" ? <SettingRow stacked label="SKILL.md" htmlFor={`${id}-source`}><textarea id={`${id}-source`} rows={14} disabled={disabled} value={content} onChange={event => onChange(event.target.value)} spellCheck={false} /></SettingRow> : fields ? <>
      <SettingRow label="Skill name" htmlFor={`${id}-name`} help="The native name in SKILL.md. Knowledge's display name is a separate label."><input id={`${id}-name`} value={fields.name} maxLength={64} disabled={disabled} onChange={event => patch({ ...fields, name: event.target.value })} /></SettingRow>
      <SettingRow stacked label="When to use" htmlFor={`${id}-description`}><textarea id={`${id}-description`} rows={2} value={fields.description} maxLength={1024} disabled={disabled} onChange={event => patch({ ...fields, description: event.target.value })} /></SettingRow>
      <SettingRow stacked label="Instructions" htmlFor={`${id}-instructions`}><textarea id={`${id}-instructions`} rows={7} value={fields.instructions} disabled={disabled} onChange={event => patch({ ...fields, instructions: event.target.value })} /></SettingRow>
      <details open={requirementsOpen} onToggle={event => setRequirementsOpen(event.currentTarget.open)}><summary>Requirements{fields.required_tools.length + fields.required_connections.length + Number(fields.requires_project) ? ` · ${fields.required_tools.length + fields.required_connections.length + Number(fields.requires_project)}` : ""}<span onClick={event => event.stopPropagation()}><HoverHelp title="Requirements">Declare what this skill needs. These requirements are checked before sending; selecting the skill does not enable tools, connect accounts or grant access.</HoverHelp></span></summary>
        <CompactSwitch label="Project folder required" checked={fields.requires_project} disabled={disabled} onChange={requires_project => patch({ ...fields, requires_project })} />
        <details><summary>Tools · {fields.required_tools.length}</summary>{[...new Set([...tools.map(tool => tool.id), ...fields.required_tools])].map(toolId => <CompactSwitch key={toolId} label={tools.find(tool => tool.id === toolId)?.name ?? toolId} checked={fields.required_tools.includes(toolId)} disabled={disabled} onChange={checked => patch({ ...fields, required_tools: checked ? [...fields.required_tools, toolId] : fields.required_tools.filter(id => id !== toolId) })} />)}</details>
        <details><summary>Connections · {fields.required_connections.length}</summary>{[...new Set([...connections.map(connection => connection.id), ...fields.required_connections])].map(connectionId => <CompactSwitch key={connectionId} label={connections.find(connection => connection.id === connectionId)?.name ?? `Unavailable connection · ${connectionId}`} checked={fields.required_connections.includes(connectionId)} disabled={disabled} onChange={checked => patch({ ...fields, required_connections: checked ? [...fields.required_connections, connectionId] : fields.required_connections.filter(id => id !== connectionId) })} />)}</details>
        {requirementsError ? <Notice tone="warn">Some requirement choices could not load. Existing selections are retained. {requirementsError}</Notice> : null}
      </details>
    </> : pending ? <p className="hint" role="status">Reading skill…</p> : <p className="hint">Use Source to correct this skill.</p>}
    {preview?.issues.map((issue, index) => <Notice key={`${index}:${issue}`} tone="warn">{issue}</Notice>)}
    {error ? <Notice tone="error" action={unresolvedFields.current ? <button type="button" disabled={disabled || pending} onClick={() => patch(unresolvedFields.current!)}>Retry</button> : undefined}>{error}</Notice> : null}
    <SkillResourceEditor versionId={versionId} resources={resources} changes={resourceChanges} onChange={onResourceChanges} disabled={disabled} onPendingChange={reading => { resourcePending.current = reading; onStateRef.current(validSource.current && !reading); }} />
  </div>;
}
