import { useEffect, useRef, useState, type KeyboardEvent } from "react";
import { api } from "./api";
import { errorMessage } from "./errors";
import { formatBytes } from "./display";
import { Icon, type IconName } from "./Icon";
import { ImportJobDetails } from "./ImportJobDetails";
import { MenuPopover } from "./MenuPopover";
import { CompactSwitch } from "./CompactControls";
import { PathBrowseButton } from "./PathField";
import { variantFamilies } from "./modelVariantPresentation";
import { ModelCapacityPreview, capacityFit, useCapacityEstimates } from "./ModelCapacityPreview";
import type { ImportJob } from "./types";
import type { SchemaHubRepository } from "../generated/shared-contracts/openapi";
import type { ModelEstimateSelection } from "./modelEstimateApi";

type SearchResult = Awaited<ReturnType<typeof api.searchHf>>[number];
const capabilityIcons: Record<string, { label: string; icon: IconName }> = { text: { label: "Text", icon: "chat" }, reasoning: { label: "Thinking", icon: "reasoning" }, image: { label: "Image", icon: "image" }, video: { label: "Video", icon: "video" }, audio: { label: "Audio", icon: "audio" } };
const activeJob = (job: ImportJob) => ["pending", "running", "stopping"].includes(job.status);

export function HuggingFaceImport({ onStarted, active = true, onOpenModel, onBrowseModels }: { onStarted: (job: ImportJob) => Promise<void>; active?: boolean; onOpenModel?: (id: string) => void; onBrowseModels?: () => void }) {
  const [step, setStep] = useState<0 | 1>(0), [query, setQuery] = useState("");
  const [results, setResults] = useState<SearchResult[]>([]), [hub, setHub] = useState<SchemaHubRepository | null>(null);
  const [, setSelectedRepo] = useState("");
  const [variant, setVariant] = useState(""), [projector, setProjector] = useState("");
  const [recipeIds, setRecipeIds] = useState<string[]>([]), [sourcePath, setSourcePath] = useState("");
  const [local, setLocal] = useState(false), [copyLocal, setCopyLocal] = useState(true);
  const [busy, setBusy] = useState(""), [error, setError] = useState("");
  const [job, setJob] = useState<ImportJob | null>(null), [jobs, setJobs] = useState<ImportJob[]>([]);
  const [speed, setSpeed] = useState<number | null>(null);
  const speedSample = useRef<{ bytes: number; time: number } | null>(null);
  const generation = useRef(0), pending = useRef(false), inspected = useRef("");
  const [startup, setStartup] = useState<Record<string, unknown>>({ cache_type_k: "f32", cache_type_v: "f32", flash_attn: "off" });
  const previewEdited = useRef(false), highestApplied = useRef("");
  const selected = hub?.variants.find(item => item.name === variant);
  const vision = hub?.projectors.find(item => item.name === projector);
  const exactFiles = [...new Set([...(selected?.files ?? []), ...(vision?.files ?? []), ...(hub?.guidance_files ?? [])])];
  const filesIdentity = JSON.stringify([local ? sourcePath : hub?.repo_id, hub?.resolved_revision, variant, projector]);
  const [jobIdentity, setJobIdentity] = useState("");
  const selections: Array<{ key: string; selection: ModelEstimateSelection }> = local ? sourcePath ? [{ key: "local", selection: { source_path: sourcePath, startup: {} } }] : [] : (hub?.variants.filter(item => item.complete) ?? []).map(item => ({ key: item.name, selection: { repo_id: hub!.repo_id, revision: hub!.resolved_revision, primary_files: item.files, projector_files: vision?.files ?? [], startup: {} } }));
  const estimates = useCapacityEstimates(selections, startup, active && step === 1);
  const estimate = estimates.answers[local ? "local" : variant];
  const initialEstimate = estimate ?? Object.values(estimates.answers)[0];
  useEffect(() => {
    if (!initialEstimate || previewEdited.current || highestApplied.current === inspected.current) return;
    highestApplied.current = inspected.current;
    const next: Record<string, unknown> = { cache_type_k: "f32", cache_type_v: "f32", flash_attn: "off", ...(initialEstimate.context_maximum ? { ctx_size: initialEstimate.context_maximum } : {}), ...(initialEstimate.builtin_mtp ? { spec_type: "draft-mtp" } : initialEstimate.mtp_draft_files?.length ? { spec_type: "draft-mtp", spec_draft_model: initialEstimate.mtp_draft_files[0] } : {}) };
    setStartup(next);
  }, [initialEstimate]);
  useEffect(() => { generation.current += 1; return () => { generation.current += 1; }; }, []);
  useEffect(() => {
    if (!active) return;
    let disposed = false;
    async function poll() {
      try {
        const next = await api.imports(); if (disposed) return; setJobs(next);
        if (job) {
          const updated = next.find(item => item.id === job.id);
          if (updated) {
            setJob(updated);
            const bytes = updated.progress?.bytes_done ?? 0, time = Date.now(), prior = speedSample.current;
            if (prior && bytes >= prior.bytes && time > prior.time) setSpeed((bytes - prior.bytes) / ((time - prior.time) / 1000));
            speedSample.current = { bytes, time };
            if (updated.status === "complete" && job.status !== "complete") await onStarted(updated);
          }
        }
      } catch (failure) { if (!disposed && job) setError(errorMessage(failure)); }
    }
    void poll(); const timer = window.setInterval(() => void poll(), 1200);
    return () => { disposed = true; window.clearInterval(timer); };
  }, [active, job?.id, job?.status]);

  function resetPreview(identity: string) { inspected.current = identity; highestApplied.current = ""; previewEdited.current = false; setStartup({ cache_type_k: "f32", cache_type_v: "f32", flash_attn: "off" }); }
  async function inspectRepository(repo: string) {
    if (pending.current) return;
    if (hub && inspected.current === repo && !local) { setStep(1); return; }
    const owner = ++generation.current; setBusy("inspect"); setError(""); setSelectedRepo(repo);
    try {
      const next = await api.inspectHf(repo); if (owner !== generation.current) return;
      setHub(next); setLocal(false); setRecipeIds((next.response_recipes ?? []).map(item => item.id)); setJob(null); setJobIdentity(""); setSelectedRepo(next.repo_id); resetPreview(next.repo_id);
      const hint = (next as SchemaHubRepository & { file_hint?: string | null }).file_hint;
      const hinted = hint ? next.variants.find(item => item.name === hint || item.files.includes(hint)) : undefined;
      setVariant(hinted?.complete ? hinted.name : next.variants.length === 1 && next.variants[0].complete ? next.variants[0].name : "");
      setProjector(next.projectors.length ? "" : "text-only"); setStep(1);
      setResults(current => current.map(item => item.repo_id === next.repo_id ? { ...item, complete_variants: next.variants.filter(item => item.complete).length } : item));
    } catch (failure) { if (owner === generation.current) setError(errorMessage(failure)); }
    finally { if (owner === generation.current) setBusy(""); }
  }
  async function search() {
    const value = query.trim(); if (!value || pending.current) return;
    if (/^https?:\/\//i.test(value) || /^[\w.-]+\/[\w.-]+$/.test(value)) { await inspectRepository(value); return; }
    const owner = ++generation.current; setBusy("search"); setError("");
    try { const next = await api.searchHf(value); if (owner === generation.current) setResults(next); }
    catch (failure) { if (owner === generation.current) setError(errorMessage(failure)); }
    finally { if (owner === generation.current) setBusy(""); }
  }
  function chooseLocal() { if (!sourcePath.trim() || pending.current) return; setLocal(true); setHub(null); setRecipeIds([]); setProjector("text-only"); setVariant(""); setJob(null); resetPreview(sourcePath.trim()); setStep(1); }
  async function download() {
    if (pending.current || !local && (!hub || !selected?.complete || !projector)) return;
    pending.current = true; const owner = generation.current; setBusy("download"); setError("");
    try {
      const next = local ? await api.importLocal(sourcePath.trim(), undefined, copyLocal) : await api.importHf(hub!.repo_id, hub!.resolved_revision, exactFiles.map(file => file.replaceAll("[", "[[]").replaceAll("?", "[?]").replaceAll("*", "[*]")), recipeIds);
      if (owner === generation.current) { setJob(next); setJobIdentity(filesIdentity); speedSample.current = null; setSpeed(null); }
      await onStarted(next);
    } catch (failure) { if (owner === generation.current) setError(errorMessage(failure)); }
    finally { pending.current = false; if (owner === generation.current) setBusy(""); }
  }
  async function changeJob(operation: "cancel" | "retry" | "discard", item = job) {
    if (!item || pending.current) return; pending.current = true; setBusy(operation); setError("");
    try { const next = operation === "cancel" ? await api.cancelImport(item.id) : operation === "discard" ? await api.discardImport(item.id) : await api.retryImport(item.id); setJob(next); if (item.id !== job?.id) setJobIdentity(""); await onStarted(next); }
    catch (failure) { setError(errorMessage(failure)); }
    finally { pending.current = false; setBusy(""); }
  }
  function quantKey(event: KeyboardEvent<HTMLButtonElement>) {
    if (!["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown", "Home", "End"].includes(event.key)) return;
    event.preventDefault(); const controls = Array.from(event.currentTarget.closest(".model-quant-grid")!.querySelectorAll<HTMLButtonElement>("button:not(:disabled)"));
    const index = controls.indexOf(event.currentTarget), next = event.key === "Home" ? 0 : event.key === "End" ? controls.length - 1 : (index + (["ArrowLeft", "ArrowUp"].includes(event.key) ? controls.length - 1 : 1)) % controls.length;
    controls[next]?.click(); controls[next]?.focus();
  }
  const sameJob = jobIdentity === filesIdentity ? job : null;
  const jobRunning = Boolean(sameJob && activeJob(sameJob));
  const progress = sameJob?.progress;
  const percent = progress?.bytes_total ? Math.min(100, Math.round(progress.bytes_done / progress.bytes_total * 100)) : null;
  const canAdd = local ? Boolean(sourcePath.trim()) : Boolean(selected?.complete && projector);
  return <section className="models-add-journey" aria-label="Add a model">
    <header className="models-journey-header"><div className="models-journey-title"><button type="button" className="icon-button models-browse-button" aria-label="Browse model sections" onClick={onBrowseModels}><Icon name="panel" /></button><div><h2>Add a model</h2><p>Find and choose.</p></div></div><nav className="models-flow-steps" aria-label="Find and choose"><button type="button" aria-current={step === 0 ? "step" : undefined} onClick={() => setStep(0)}><span>1</span>Find</button><button type="button" aria-current={step === 1 ? "step" : undefined} disabled={!hub && !local} onClick={() => setStep(1)}><span>2</span>Choose</button></nav></header>
    <div className="models-journey-scroll">{sameJob?.error ? <p className="models-job-error" role="status">{sameJob.error}</p> : null}{sameJob?.configuration_error ? <p className="hint" role="status">Model files are installed. Selected setups need attention: {sameJob.configuration_error}</p> : null}{error ? <p role="status" className="models-flow-error">{error}</p> : null}
      {step === 0 ? <>
        <section className="models-find"><h3>Model name, repository or exact file link</h3><form className="models-find-search" onSubmit={event => { event.preventDefault(); void search(); }}><input type="search" aria-label="Find a model" value={query} onChange={event => setQuery(event.target.value)} placeholder="Search models or paste a Hugging Face link" /><button type="submit" className="primary-button" disabled={!query.trim() || Boolean(busy)}>{busy === "search" ? "Finding…" : "Find model"}</button></form></section>
        {results.length ? <div className="models-repository-table-wrap"><table className="models-repository-table"><thead><tr><th>Repository</th><th>Downloads</th><th>Likes</th><th>Variants</th><th>Capabilities</th></tr></thead><tbody>{results.map(item => <tr key={item.repo_id}><td><button type="button" disabled={Boolean(busy)} onClick={() => void inspectRepository(item.repo_id)}>{item.repo_id}</button></td><td>{item.downloads?.toLocaleString() ?? "—"}</td><td>{item.likes?.toLocaleString() ?? "—"}</td><td>{item.complete_variants?.toLocaleString() ?? "—"}</td><td><span className="models-advertised-icons" title={item.metadata_source ?? "Publisher metadata"}>{item.advertised_capabilities?.length ? item.advertised_capabilities.map(id => capabilityIcons[id] ? <span key={id} role="img" aria-label={capabilityIcons[id].label + ", advertised by publisher"} title={capabilityIcons[id].label + " · advertised by publisher"}><Icon name={capabilityIcons[id].icon} size={16} /></span> : null) : "—"}</span></td></tr>)}</tbody></table></div> : query && !busy ? <p className="hint">Search by a model name or publisher.</p> : null}
        <section className="models-local-import"><h3>Already on your computer?</h3><form onSubmit={event => { event.preventDefault(); chooseLocal(); }}><input aria-label="Model file or folder" value={sourcePath} onChange={event => setSourcePath(event.target.value)} placeholder="Choose a GGUF file or folder" /><PathBrowseButton kind="file" label="Browse file" icon="files" disabled={Boolean(busy)} onPicked={setSourcePath} onError={failure => setError(errorMessage(failure))} /><PathBrowseButton kind="folder" label="Browse folder" icon="folder" disabled={Boolean(busy)} onPicked={setSourcePath} onError={failure => setError(errorMessage(failure))} /><button type="submit" disabled={!sourcePath.trim() || Boolean(busy)}>Choose</button></form></section>
        {jobs.some(item => activeJob(item) || ["failed", "stopped", "interrupted"].includes(item.status)) ? <details className="models-disclosure"><summary>Downloads in progress <span className="models-show-hide" /></summary>{jobs.filter(item => activeJob(item) || ["failed", "stopped", "interrupted"].includes(item.status)).map(item => <div key={item.id} className="models-pending-job"><span>{item.display_name ?? item.repo_id ?? "Local import"} · {item.status}</span><button type="button" disabled={Boolean(busy)} onClick={() => void changeJob(activeJob(item) ? "cancel" : "retry", item)}>{activeJob(item) ? "Cancel" : "Retry"}</button><ImportJobDetails job={item}>{!activeJob(item) ? <button type="button" disabled={Boolean(busy)} onClick={() => void changeJob("discard", item)}>Discard temporary files</button> : null}</ImportJobDetails></div>)}</details> : null}
        {jobs.some(item => item.status === "complete") ? <details className="models-disclosure"><summary>Recent downloads <span className="models-show-hide" /></summary>{jobs.filter(item => item.status === "complete").slice(-10).reverse().map(item => <ImportJobDetails key={item.id} job={item} />)}</details> : null}
      </> : <>
        <div className="models-choice-heading"><div><h3>{local ? sourcePath.split(/[\\/]/).at(-1) : hub?.repo_id.split("/").at(-1)}</h3><p>{local ? "Local GGUF" : hub?.repo_id}</p></div>{!local && hub ? <a href={"https://huggingface.co/" + hub.repo_id + "/blob/" + hub.resolved_revision + "/README.md"} target="_blank" rel="noopener noreferrer">Model guide <Icon name="knowledge" size={16} /></a> : null}</div>
        <div className="models-choice-grid"><section className="models-quant-panel"><div className="models-quant-heading"><h3>{local ? "Local file" : "Quantization"}</h3>{hub ? <div className="models-quant-tools"><select aria-label="Image input" value={projector} onChange={event => setProjector(event.target.value)}><option value="" disabled>Image input</option><option value="text-only">Text only</option>{hub.projectors.map(item => <option key={item.name} value={item.name}>{item.name}</option>)}</select><MenuPopover label="Model card presets" panelClassName="models-menu" placement="below" trigger={<>Model card</>}>{hub.response_recipes?.length ? hub.response_recipes.map(item => <label className="models-recipe-choice" key={item.id}><input type="checkbox" checked={recipeIds.includes(item.id)} onChange={event => setRecipeIds(current => event.target.checked ? [...current, item.id] : current.filter(id => id !== item.id))} /><span><strong>{item.name}</strong><small>{item.reasoning === "preserve" ? "Thinking unchanged" : "Thinking " + item.reasoning}</small></span></label>) : <p className="hint">No model-card setups.</p>}</MenuPopover></div> : null}</div>
          {local ? <p className="model-local-filename">{sourcePath}</p> : <><div className="models-quant-legend"><span><i className="model-fit-dot" data-fit="green" />Fits VRAM</span><span><i className="model-fit-dot" data-fit="amber" />RAM spill</span><span><i className="model-fit-dot" data-fit="red" />Unlikely</span></div><div className="model-quant-grid" role="radiogroup" aria-label="Quantization">{variantFamilies(hub?.variants ?? [], "all", "asc").map(group => <div className="models-quant-row" key={group.family}><span className="models-quant-axis">{group.family}</span><div className="models-quant-cells">{group.items.map(({ variant: item, quant, flavour }) => { const fit = capacityFit(estimates.answers[item.name]); return <button type="button" key={item.name} role="radio" aria-checked={item.name === variant} tabIndex={item.name === variant || !variant && item === hub?.variants.find(item => item.complete) ? 0 : -1} aria-label={quant + " " + flavour + ", " + (item.size_bytes == null ? "size unknown" : formatBytes(item.size_bytes)) + (item.complete ? "" : ", missing shards")} title={item.name + " · " + (fit === "unknown" ? "Memory estimate unknown" : "Advisory memory estimate")} className="models-quant-tile" disabled={!item.complete || jobRunning} onClick={() => setVariant(item.name)} onKeyDown={quantKey}><strong>{quant}{item.name === variant ? <Icon name="check" size={12} /> : null}</strong>{flavour !== "Standard" ? <small className="models-quant-flavour">{flavour}</small> : null}<span className="models-quant-size" data-fit={fit}>{item.size_bytes == null ? "—" : formatBytes(item.size_bytes)}{!item.complete ? " !" : ""}</span></button>; })}</div></div>)}</div></>}
          <details className="models-disclosure"><summary>Files &amp; source <span className="models-show-hide" /></summary><p className="hint">{local ? sourcePath : hub?.repo_id + " @ " + hub?.resolved_revision}</p><ul className="plain-list">{exactFiles.map(file => <li key={file}>{file}</li>)}</ul>{local ? <CompactSwitch label="Copy into model storage" checked={copyLocal} onChange={setCopyLocal} description="Turn off to use original files without making a copy." /> : null}{hub?.warnings.map((warning, index) => <p className="hint" key={index}>{warning}</p>)}{hub?.gguf_candidates?.map(candidate => <button type="button" key={candidate.repo_id} onClick={() => void inspectRepository(candidate.repo_id)}>Inspect GGUF · {candidate.repo_id}</button>)}</details>
          {sameJob ? <ImportJobDetails job={sameJob} /> : null}
        </section><ModelCapacityPreview estimate={estimate} startup={startup} onChange={next => { previewEdited.current = true; if (next.spec_type === "draft-mtp" && !estimate?.builtin_mtp && estimate?.mtp_draft_files?.length) next.spec_draft_model = estimate.mtp_draft_files[0]; else delete next.spec_draft_model; setStartup(next); }} error={estimates.error} /></div>
      </>}
    </div>
    <footer className="models-add-footer"><div>{step ? <button type="button" className="text-button" onClick={() => setStep(0)}><Icon name="back" size={16} />Back to Find</button> : <span className="hint">Find a model or choose a local file.</span>}</div>{step === 1 ? <div className="models-download-action">{sameJob ? <span className="models-download-progress" role="status">{progress ? <><progress max={100} value={percent ?? undefined} />{formatBytes(progress.bytes_done)}{speed != null && jobRunning ? " · " + (speed * 8 / 1_000_000).toFixed(1) + " Mb/s" : ""}{percent != null ? " · " + percent + "%" : ""}</> : sameJob.status}</span> : null}{jobRunning ? <button type="button" disabled={Boolean(busy)} onClick={() => void changeJob("cancel")}>Cancel</button> : sameJob?.status === "failed" || ["stopped", "interrupted"].includes(sameJob?.status ?? "") ? <button type="button" className="primary-button" disabled={Boolean(busy)} onClick={() => void changeJob("retry")}>Retry</button> : sameJob?.status === "complete" && sameJob.bundle_id ? <button type="button" className="primary-button" onClick={() => onOpenModel?.(sameJob.bundle_id!)}>Open model</button> : <button type="button" className="primary-button" disabled={!canAdd || Boolean(busy)} onClick={() => void download()}>{busy === "download" ? "Starting…" : local ? "Add model" : "Download"}</button>}</div> : null}</footer>
  </section>;
}
