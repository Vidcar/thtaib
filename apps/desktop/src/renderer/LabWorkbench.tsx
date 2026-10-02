import { useCallback, useEffect, useRef, useState, type KeyboardEvent } from "react";
import { api } from "./api";
import { labApi } from "./labApi";
import { CompactDialog } from "./CompactDialog";
import { Help, tokenLabel } from "./ModelControls";
import { SegmentedChoice } from "./CompactControls";
import { Notice } from "./Notice";
import { errorMessage } from "./errors";
import { LabConfigurationControls, newLabSelection, type LabSelection } from "./LabConfigurationControls";
import { LabCharts } from "./LabCharts";
import { LabChallenges } from "./LabChallenges";
import { LabRunStatus, MemoryResults, PerformanceResults } from "./LabResults";
import { labDepths, labIsActive, labLeaveOwners, labPromptLengths, labSetting } from "./labPresentation";
import type { LabChallenge, LabChallengeWrite, LabDepth, LabKind, LabRun, LabRunRequest } from "./labTypes";
import type { ModelBundle, RunProfile } from "./types";
import "./LabWorkbench.css";

const tabs = [{ id: "performance", label: "Performance" }, { id: "memory", label: "Memory" }, { id: "challenge", label: "Challenges" }] as const;
const newestFirst = (runs: LabRun[]) => [...runs].sort((a, b) => b.created_at.localeCompare(a.created_at));

export function LabWorkbench() {
  const [view, setView] = useState<LabKind>("performance");
  const [models, setModels] = useState<ModelBundle[]>([]);
  const [profiles, setProfiles] = useState<RunProfile[]>([]);
  const [runs, setRuns] = useState<LabRun[]>([]);
  const [challenges, setChallenges] = useState<LabChallenge[]>([]);
  const [selections, setSelections] = useState<LabSelection[]>(() => [newLabSelection()]);
  const [mode, setMode] = useState<"single" | "concurrent">("single");
  const [promptLengths, setPromptLengths] = useState<number[]>([]);
  const [generation, setGeneration] = useState<256 | 512 | 1024>(512);
  const [memoryTest, setMemoryTest] = useState<LabRunRequest["memory_test"]>("uuid");
  const [depths, setDepths] = useState<LabDepth[]>([0, 25, 50, 75, 100]);
  const [hidden, setHidden] = useState<ReadonlySet<string>>(new Set());
  const [loading, setLoading] = useState(true);
  const [readErrors, setReadErrors] = useState<Record<string, string>>({});
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [uncertainStart, setUncertainStart] = useState(false);
  const [confirmation, setConfirmation] = useState<{ kind: "run"; record: LabRun } | { kind: "challenge"; record: LabChallenge } | null>(null);
  const mounted = useRef(false);
  const actionPending = useRef(false);
  const initialGeneration = useRef(0);
  const runsRef = useRef(runs); runsRef.current = runs;
  const pollPending = useRef(false);
  const hadVisit = useRef(false);
  const runReadRevision = useRef(0);
  const challengeReadRevision = useRef(0);
  const deletedRuns = useRef(new Set<string>());

  const saveRun = useCallback((run: LabRun) => {
    if (!mounted.current || deletedRuns.current.has(run.id)) return;
    setRuns(current => {
      const previous = current.find(item => item.id === run.id);
      if (previous && previous.updated_at > run.updated_at) return current;
      return newestFirst([run, ...current.filter(item => item.id !== run.id)]);
    });
  }, []);
  const setReadError = useCallback((key: string, message: string) => setReadErrors(current => {
    const next = { ...current }; if (message) next[key] = message; else delete next[key]; return next;
  }), []);

  const refreshRuns = useCallback(async () => {
    const readRevision = ++runReadRevision.current;
    try {
      const records = await labApi.runs();
      if (!mounted.current || readRevision !== runReadRevision.current) return;
      setRuns(newestFirst(records.filter(run => !deletedRuns.current.has(run.id)))); setReadError("runs", ""); setUncertainStart(false);
    } catch (reason) { if (mounted.current && readRevision === runReadRevision.current) setReadError("runs", `Saved runs could not load: ${errorMessage(reason)}`); }
  }, [setReadError]);

  const refresh = useCallback(async () => {
    const generation = ++initialGeneration.current;
    const readRevision = ++runReadRevision.current;
    const challengeRevision = ++challengeReadRevision.current;
    const outcomes = await Promise.allSettled([api.bundles(), api.profiles(), labApi.runs(), labApi.challenges()]);
    if (!mounted.current || generation !== initialGeneration.current) return;
    const [bundleResult, profileResult, runResult, challengeResult] = outcomes;
    if (bundleResult.status === "fulfilled") { setModels(bundleResult.value.filter(model => model.primary_path && model.disk_matches)); setReadError("models", ""); }
    else setReadError("models", `Models could not load: ${errorMessage(bundleResult.reason)}`);
    if (profileResult.status === "fulfilled") { setProfiles(profileResult.value); setReadError("configurations", ""); }
    else setReadError("configurations", `Configurations could not load: ${errorMessage(profileResult.reason)}`);
    if (readRevision === runReadRevision.current) {
      if (runResult.status === "fulfilled") { setRuns(newestFirst(runResult.value.filter(run => !deletedRuns.current.has(run.id)))); setReadError("runs", ""); setUncertainStart(false); }
      else setReadError("runs", `Saved runs could not load: ${errorMessage(runResult.reason)}`);
    }
    if (challengeRevision === challengeReadRevision.current) {
      if (challengeResult.status === "fulfilled") { setChallenges(challengeResult.value); setReadError("challenges", ""); }
      else setReadError("challenges", `Challenges could not load: ${errorMessage(challengeResult.reason)}`);
    }
    setLoading(false);
  }, [setReadError]);

  useEffect(() => {
    mounted.current = true; hadVisit.current = true;
    void refresh();
    const beforeUnload = () => { void labApi.leave(labLeaveOwners(runsRef.current)).catch(() => {}); };
    window.addEventListener("pagehide", beforeUnload);
    return () => {
      mounted.current = false; initialGeneration.current++;
      window.removeEventListener("pagehide", beforeUnload);
      // React's development effect replay is not a destination exit.
      const leavingRunIds = labLeaveOwners(runsRef.current);
      queueMicrotask(() => { if (!mounted.current && hadVisit.current) void labApi.leave(leavingRunIds).catch(() => {}); });
    };
  }, [refresh]);

  const poll = useCallback(async () => {
    if (pollPending.current) return;
    pollPending.current = true;
    const readRevision = ++runReadRevision.current;
    const active = runsRef.current.filter(labIsActive);
    try {
      const results = await Promise.allSettled(active.map(run => labApi.run(run.id)));
      if (!mounted.current || readRevision !== runReadRevision.current) return;
      results.forEach((result, index) => {
        const id = active[index].id;
        if (result.status === "fulfilled") { saveRun(result.value); setReadError(`run:${id}`, ""); }
        else setReadError(`run:${id}`, `Run status could not load. Finished measurements remain saved. ${errorMessage(result.reason)}`);
      });
    } finally { pollPending.current = false; }
  }, [saveRun, setReadError]);
  const activeKey = runs.filter(labIsActive).map(run => run.id).join(":");
  useEffect(() => {
    if (!activeKey) return;
    const timer = window.setInterval(() => { void poll(); }, 750);
    return () => window.clearInterval(timer);
  }, [activeKey, poll]);

  const activeRuns = runs.filter(labIsActive);
  const locked = busy || activeRuns.length > 0 || uncertainStart;
  const relevant = view === "performance" && mode === "concurrent" ? selections : selections.slice(0, 1);
  const ladders = relevant.map(selection => labPromptLengths(selection.options, labSetting(profiles.find(profile => profile.id === selection.configuration_id), selection.startup, selection.options, "ctx_size")));
  const legalLengths = (ladders[0] ?? []).filter(length => ladders.every(ladder => ladder.includes(length)));
  const legalKey = legalLengths.join(":");
  const allChoicesReady = relevant.every(selection => selection.ready);
  useEffect(() => { if (allChoicesReady) setPromptLengths(current => current.filter(length => legalKey.split(":").includes(String(length)))); }, [legalKey, allChoicesReady]);
  const modelReady = relevant.every(selection => selection.configuration_id && selection.ready) && !loading && !readErrors.models && !readErrors.configurations && !readErrors.runs;
  const reason = loading ? "Loading Lab…" : readErrors.runs ? "Restore saved run status before starting another run." : !relevant.every(selection => selection.configuration_id) ? "Choose a model and a saved configuration." : !modelReady ? "Waiting for legal model choices." : view === "performance" && !promptLengths.length ? "Choose at least one prompt length." : view === "memory" && !depths.length ? "Choose at least one depth." : uncertainStart ? "Checking whether the previous run started." : activeRuns.length ? "A Lab run is already in progress." : "";

  function replaceSelection(index: number, value: LabSelection) { setSelections(current => current.map((item, position) => position === index ? value : item)); }
  async function start(challenge?: LabChallenge) {
    if (actionPending.current || locked || !modelReady || !challenge && reason) return;
    actionPending.current = true; setBusy(true); setError("");
    runReadRevision.current++;
    const request: LabRunRequest = {
      kind: challenge ? "challenge" : view,
      mode: view === "performance" ? mode : "single",
      configurations: relevant.map(selection => ({ configuration_id: selection.configuration_id, startup: selection.startup, concurrent_requests: view === "performance" && mode === "concurrent" ? selection.concurrent_requests : 1 })),
      prompt_lengths: promptLengths.filter(length => legalLengths.includes(length)), generation_length: generation, memory_test: memoryTest, depths, challenge_id: challenge?.id,
    };
    try {
      const run = await labApi.start(request);
      runReadRevision.current++;
      if (mounted.current) saveRun(run);
      else { await labApi.stop(run.id); await labApi.leave([run.id]); }
    } catch (reason) {
      if (mounted.current) { setError(errorMessage(reason)); setUncertainStart(true); await refreshRuns(); }
    } finally { actionPending.current = false; if (mounted.current) setBusy(false); }
  }
  async function stop(run: LabRun) {
    if (actionPending.current) return;
    actionPending.current = true; setBusy(true); setError("");
    runReadRevision.current++;
    try { const stopped = await labApi.stop(run.id); runReadRevision.current++; saveRun(stopped); }
    catch (reason) { if (mounted.current) setError(`Stop could not be confirmed: ${errorMessage(reason)}`); }
    finally { actionPending.current = false; if (mounted.current) setBusy(false); }
  }
  async function saveChallenge(body: LabChallengeWrite, id?: string): Promise<boolean> {
    if (actionPending.current) return false;
    actionPending.current = true; setBusy(true); setError("");
    challengeReadRevision.current++;
    try { const saved = await labApi.saveChallenge(body, id); challengeReadRevision.current++; if (mounted.current) setChallenges(current => id ? current.map(item => item.id === id ? saved : item) : [...current, saved]); return true; }
    catch (reason) { if (mounted.current) setError(errorMessage(reason)); return false; }
    finally { actionPending.current = false; if (mounted.current) setBusy(false); }
  }
  async function confirmDelete() {
    if (!confirmation || actionPending.current) return;
    actionPending.current = true; setBusy(true); setError("");
    runReadRevision.current++;
    if (confirmation.kind === "challenge") challengeReadRevision.current++;
    try {
      if (confirmation.kind === "run") { await labApi.deleteRun(confirmation.record.id); runReadRevision.current++; deletedRuns.current.add(confirmation.record.id); if (mounted.current) setRuns(current => current.filter(run => run.id !== confirmation.record.id)); }
      else { await labApi.deleteChallenge(confirmation.record.id); challengeReadRevision.current++; if (mounted.current) setChallenges(current => current.filter(item => item.id !== confirmation.record.id)); }
      if (mounted.current) setConfirmation(null);
    } catch (reason) { if (mounted.current) setError(errorMessage(reason)); }
    finally { actionPending.current = false; if (mounted.current) setBusy(false); }
  }
  function tabKeys(event: KeyboardEvent<HTMLButtonElement>, current: LabKind) {
    const index = tabs.findIndex(tab => tab.id === current);
    const next = event.key === "ArrowRight" ? tabs[(index + 1) % tabs.length] : event.key === "ArrowLeft" ? tabs[(index + tabs.length - 1) % tabs.length] : event.key === "Home" ? tabs[0] : event.key === "End" ? tabs.at(-1) : null;
    if (!next) return;
    event.preventDefault(); setView(next.id); document.getElementById(`lab-tab-${next.id}`)?.focus();
  }
  const performanceRuns = runs.filter(run => run.kind === "performance");
  return <div className="surface lab-workbench"><header className="surface-head"><h2>Lab</h2><span className="hint">Saved on this computer</span></header>
    <div className="tabs" role="tablist" aria-label="Lab views">{tabs.map(tab => <button type="button" id={`lab-tab-${tab.id}`} role="tab" key={tab.id} aria-selected={view === tab.id} aria-controls={`lab-panel-${tab.id}`} tabIndex={view === tab.id ? 0 : -1} onClick={() => setView(tab.id)} onKeyDown={event => tabKeys(event, tab.id)}>{tab.label}</button>)}</div>
    {Object.keys(readErrors).length ? <Notice tone="error"><div className="lab-read-error">{Object.entries(readErrors).map(([key, message]) => <p key={key}>{message}</p>)}<button type="button" onClick={() => { void (Object.keys(readErrors).some(key => key.startsWith("run:")) ? poll() : refresh()); }}>Retry status</button></div></Notice> : null}
    {error ? <Notice tone="error">{error}</Notice> : null}
    {uncertainStart ? <Notice tone="warn">The run request could not be confirmed. Check saved runs before trying again. <button type="button" onClick={() => void refreshRuns()}>Check saved runs</button></Notice> : null}
    {activeRuns.map(run => <LabRunStatus key={run.id} run={run} onStop={run => void stop(run)} busy={busy} />)}
    <div id={`lab-panel-${view}`} role="tabpanel" aria-labelledby={`lab-tab-${view}`} className="lab-layout"><aside className="card lab-run-controls" aria-label="Lab run controls"><div className="section-heading"><h3>{view === "performance" ? "Benchmark" : view === "memory" ? "Needle test" : "Run with"}</h3><span className="hint">This run only <Help label="Lab settings">Changes here do not alter saved model configurations, Chat, or your saved loaded-model limit.</Help></span></div>
      {view === "performance" ? <SegmentedChoice bare label="Performance mode" value={mode} options={[{ value: "single", label: "Single stream" }, { value: "concurrent", label: "Concurrent serving" }]} onChange={next => setMode(next as typeof mode)} disabled={locked} /> : null}
      {relevant.map((selection, index) => <LabConfigurationControls key={selection.key} selection={selection} models={models} profiles={profiles} disabled={locked} concurrent={view === "performance" && mode === "concurrent"} detailed={view === "performance"} index={index} onChange={value => replaceSelection(index, value)} onRemove={index ? () => setSelections(current => current.filter(item => item.key !== selection.key)) : undefined} />)}
      {view === "performance" && mode === "concurrent" ? <button type="button" title="Extra models above your saved limit are temporary and unload when you stop or leave Lab." disabled={locked || selections.length >= 16} onClick={() => setSelections(current => [...current, newLabSelection()])}>Add configuration</button> : null}
      {view === "performance" ? <><div className="lab-switch-group"><div className="section-heading"><span>Prompt lengths</span><Help label="Prompt lengths">Legal sizes for the selected context. Room is reserved for generation; charts use the model's reported lengths. Choose a model to see its legal prompt lengths.</Help></div><div className="lab-length-switches" role="group" aria-label="Prompt lengths">{legalLengths.map(length => <button type="button" role="switch" aria-label={`Prompt length ${length} tokens`} aria-checked={promptLengths.includes(length)} key={length} disabled={locked} onClick={() => setPromptLengths(current => current.includes(length) ? current.filter(value => value !== length) : [...current, length].sort((a, b) => a - b))}>{tokenLabel(length)}</button>)}</div></div><SegmentedChoice label="Generation length" value={String(generation)} options={[256, 512, 1024].map(value => ({ value: String(value), label: String(value) }))} onChange={next => setGeneration(Number(next) as typeof generation)} disabled={locked} description="Exact output tokens, including thinking. End-of-sequence does not shorten the measurement." /></> : null}
      {view === "memory" ? <><label>Test<select aria-label="Memory test" value={memoryTest} disabled={locked} onChange={event => setMemoryTest(event.target.value as typeof memoryTest)}><option value="uuid">Single UUID</option><option value="multi_key">Multi-key</option><option value="multi_value">Multi-value</option></select></label><div className="lab-switch-group"><div className="section-heading"><span>Depths</span><Help label="Needle depths">The deepest position leaves room for the question and a short answer. Values are checked by exact text.</Help></div><div className="lab-length-switches" role="group" aria-label="Needle depths">{labDepths.map(depth => <button type="button" role="switch" key={depth.value} aria-label={`Depth ${depth.label}`} aria-checked={depths.includes(depth.value)} disabled={locked} onClick={() => setDepths(current => current.includes(depth.value) ? current.filter(value => value !== depth.value) : [...current, depth.value].sort((a, b) => a - b))}>{depth.label}</button>)}</div></div></> : null}
      {view !== "challenge" ? <button type="button" className="primary-button" disabled={locked || Boolean(reason)} onClick={() => void start()}>{busy ? "Starting…" : view === "performance" ? "Run benchmark" : "Run test"}</button> : null}{reason ? <p className="hint" role="status">{!relevant[0]?.configuration_id && view === "performance" ? "Choose a model and at least one prompt length." : reason}</p> : null}
    </aside><div className="lab-results">
      {view === "performance" ? <><LabCharts runs={performanceRuns.filter(run => !hidden.has(run.id))} /><PerformanceResults runs={performanceRuns} hidden={hidden} onToggle={id => setHidden(current => { const next = new Set(current); if (next.has(id)) next.delete(id); else next.add(id); return next; })} onDelete={record => setConfirmation({ kind: "run", record })} /></> : view === "memory" ? <MemoryResults runs={runs.filter(run => run.kind === "memory")} onDelete={record => setConfirmation({ kind: "run", record })} /> : <LabChallenges challenges={challenges} runs={runs.filter(run => run.kind === "challenge")} busy={busy} canRun={Boolean(modelReady) && !locked} onRun={challenge => void start(challenge)} onSave={saveChallenge} onDelete={record => setConfirmation({ kind: "challenge", record })} onDeleteRun={record => setConfirmation({ kind: "run", record })} />}
    </div></div>
    {confirmation ? <CompactDialog title={confirmation.kind === "run" ? "Delete this result?" : `Delete ${confirmation.record.name}?`} labelledBy="lab-delete-title" busy={busy} onClose={() => setConfirmation(null)}><p>{confirmation.kind === "run" ? "This run and its measurements will be removed. Other results will stay." : "This challenge will be removed from the list. Stored results keep the task and check they used."}</p>{error ? <p className="lab-error" role="alert">{error}</p> : null}<div className="actions"><button type="button" disabled={busy} onClick={() => setConfirmation(null)}>Cancel</button><button type="button" className="danger-button" disabled={busy} onClick={() => void confirmDelete()}>{confirmation.kind === "run" ? "Delete result" : "Delete challenge"}</button></div></CompactDialog> : null}
  </div>;
}
