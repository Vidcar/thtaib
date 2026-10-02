import { useState } from "react";
import { Help } from "./ModelControls";
import { LabAnswer, labDate } from "./LabResults";
import { labIsActive, labStatus } from "./labPresentation";
import type { LabChallenge, LabChallengeWrite, LabRun } from "./labTypes";

const emptyChallenge: LabChallengeWrite = { name: "", task: "", required_text: "", required_tool: null };
const toolLabel = (tool: string) => tool === "time_now" ? "Clock" : "Echo";
export function LabChallenges({ challenges, runs, busy, canRun, onRun, onSave, onDelete, onDeleteRun }: {
  challenges: LabChallenge[]; runs: LabRun[]; busy: boolean; canRun: boolean;
  onRun: (challenge: LabChallenge) => void; onSave: (body: LabChallengeWrite, id?: string) => Promise<boolean>;
  onDelete: (challenge: LabChallenge) => void; onDeleteRun: (run: LabRun) => void;
}) {
  const [editing, setEditing] = useState<string | null>(null);
  const [draft, setDraft] = useState<LabChallengeWrite>({ ...emptyChallenge });
  function edit(challenge?: LabChallenge) { setEditing(challenge?.id ?? "new"); setDraft(challenge ? { name: challenge.name, task: challenge.task, required_text: challenge.required_text, required_tool: challenge.required_tool } : { ...emptyChallenge }); }
  return <div className="lab-challenges-view"><div className="section-heading"><h3>Challenges</h3><Help label="Challenges">Add another task and an exact check. Each result keeps the task and check used when it ran.</Help><button type="button" disabled={busy} onClick={() => edit()}>Add challenge</button></div>
    {editing ? <form className="card lab-challenge-editor" onSubmit={event => { event.preventDefault(); void onSave(draft, editing === "new" ? undefined : editing).then(saved => { if (saved) setEditing(null); }); }}>
      <h3>{editing === "new" ? "Add challenge" : "Edit challenge"}<Help label="Challenge check">Require answer text, a tool, or both. Only Echo and Clock are available.</Help></h3><label>Name<input aria-label="Challenge name" value={draft.name} maxLength={160} autoFocus disabled={busy} onChange={event => setDraft({ ...draft, name: event.target.value })} /></label>
      <label>Task<textarea aria-label="Challenge task" rows={3} value={draft.task} maxLength={16000} disabled={busy} onChange={event => setDraft({ ...draft, task: event.target.value })} /></label>
      <label>Required answer text<input aria-label="Required answer text" value={draft.required_text} maxLength={4000} disabled={busy} onChange={event => setDraft({ ...draft, required_text: event.target.value })} /></label>
      <label>Required tool<select aria-label="Required tool" value={draft.required_tool ?? ""} disabled={busy} onChange={event => setDraft({ ...draft, required_tool: event.target.value === "echo" || event.target.value === "time_now" ? event.target.value : null })}><option value="">None</option><option value="echo">Echo</option><option value="time_now">Clock</option></select></label>
      <div className="actions"><button type="submit" className="primary-button" disabled={busy || !draft.name.trim() || !draft.task.trim() || !draft.required_text.trim() && !draft.required_tool}>Save challenge</button><button type="button" disabled={busy} onClick={() => setEditing(null)}>Cancel</button></div>
    </form> : null}
    {!challenges.length ? <div className="empty-state"><h3>No challenges</h3></div> : <div className="lab-challenge-cards">{challenges.map(challenge => {
      const history = runs.filter(run => run.request.challenge_id === challenge.id);
      const latest = history[0];
      const result = latest?.measurements[0];
      const running = latest && labIsActive(latest);
      const state = running ? labStatus(latest) : latest?.status === "failed" ? "Failed" : latest?.status === "stopped" ? "Stopped" : result ? result.passed ? "Passed" : "Failed" : "Not run";
      return <article className="card lab-challenge-card" key={challenge.id}><div className="section-heading"><h3>{challenge.name}</h3><span className={`badge ${state === "Passed" ? "tone-ok" : state === "Failed" ? "tone-warn" : running ? "tone-live" : ""}`}>{state}</span></div>
        <p className="lab-challenge-task">{challenge.task}</p><ChallengeCheck check={challenge} />
        <div className="actions"><button type="button" disabled={busy || !canRun} aria-label={`Run challenge ${challenge.name}`} onClick={() => onRun(challenge)}>{running ? "Running…" : "Run"}</button><button type="button" disabled={busy} aria-label={`Edit challenge ${challenge.name}`} onClick={() => edit(challenge)}>Edit</button><button type="button" className="text-button" disabled={busy || Boolean(running)} aria-label={`Delete challenge ${challenge.name}`} onClick={() => onDelete(challenge)}>Delete</button></div>
        {latest ? <ChallengeResult run={latest} onDelete={onDeleteRun} latest /> : null}
        {history.length > 1 ? <details className="lab-challenge-history"><summary>Earlier results ({history.length - 1})</summary>{history.slice(1).map(run => <ChallengeResult key={run.id} run={run} onDelete={onDeleteRun} />)}</details> : null}
      </article>;
    })}</div>}
    {runs.some(run => !challenges.some(challenge => challenge.id === run.request.challenge_id)) ? <details className="card"><summary>Results from deleted challenges</summary>{runs.filter(run => !challenges.some(challenge => challenge.id === run.request.challenge_id)).map(run => <ChallengeResult key={run.id} run={run} onDelete={onDeleteRun} />)}</details> : null}
  </div>;
}

function ChallengeCheck({ check }: { check: LabChallengeWrite }) {
  return <p className="lab-challenge-check">Check: {check.required_text ? <>answer includes <strong>{check.required_text}</strong>{check.required_tool ? " and " : ""}</> : null}{check.required_tool ? <><strong>{toolLabel(check.required_tool)}</strong> is called</> : null}</p>;
}
function ChallengeResult({ run, onDelete, latest = false }: { run: LabRun; onDelete: (run: LabRun) => void; latest?: boolean }) {
  const point = run.measurements[0];
  return <details className="lab-challenge-result" open={latest}><summary>{latest ? "Latest result" : labStatus(run)} · {labDate(run.created_at)}</summary>
    {run.error ? <p className="lab-error">{run.error}</p> : null}{point ? <><LabAnswer point={point} /><p className="hint">Tools called: {point.tool_calls.length ? point.tool_calls.map(toolLabel).join(", ") : "None"}</p>{point.missing.length ? <p className="lab-error">Missing: {point.missing.join(", ")}</p> : null}<p className={`hint ${point.passed ? "" : "lab-error"}`}>{point.passed ? "Passed" : "Failed"}</p></> : <p className="hint">{labIsActive(run) ? "Waiting for the model’s answer…" : "No answer was recorded."}</p>}
    {run.challenge_snapshot ? <details><summary>Task and check used</summary><p className="lab-challenge-task">{run.challenge_snapshot.task}</p><ChallengeCheck check={run.challenge_snapshot} /></details> : null}<button type="button" className="text-button" disabled={labIsActive(run)} onClick={() => onDelete(run)}>Delete result</button>
  </details>;
}
