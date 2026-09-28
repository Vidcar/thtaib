import { useEffect, useId, useRef, useState } from "react";
import { knowledgeApi, type SkillGuidedFields, type SkillPreview, type SkillResourceChange } from "./knowledgeApi";
import { errorMessage } from "./errors";
import { Notice } from "./Notice";
import { SettingRow } from "./CompactControls";
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
      setFields(next.guided_available ? { name: next.name ?? "", description: next.description ?? "", instructions: next.instructions ?? "" } : null);
      markValid(next.valid);
    }).catch(failure => { if (requestId === serial.current) setError(errorMessage(failure)); }).finally(() => { if (requestId === serial.current) setPending(false); });
    return () => { ++serial.current; };
  }, [content, scope, scopeId, entryId]);

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
    </> : pending ? <p className="hint" role="status">Reading skill…</p> : <p className="hint">Use Source to correct this skill.</p>}
    {preview?.issues.map((issue, index) => <Notice key={`${index}:${issue}`} tone="warn">{issue}</Notice>)}
    {error ? <Notice tone="error" action={unresolvedFields.current ? <button type="button" disabled={disabled || pending} onClick={() => patch(unresolvedFields.current!)}>Retry</button> : undefined}>{error}</Notice> : null}
    <SkillResourceEditor versionId={versionId} resources={resources} changes={resourceChanges} onChange={onResourceChanges} disabled={disabled} onPendingChange={reading => { resourcePending.current = reading; onStateRef.current(validSource.current && !reading); }} />
  </div>;
}
