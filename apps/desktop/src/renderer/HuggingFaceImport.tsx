import { useEffect, useRef, useState } from "react";
import { api } from "./api";
import { formatBytes } from "./display";
import { errorMessage } from "./errors";
import { Help } from "./ModelControls";
import { Icon } from "./Icon";
import { Notice } from "./Notice";
import { presentVariant, variantFamilies } from "./modelVariantPresentation";
import type { ImportJob, ResponseRecipe } from "./types";
import type { SchemaHubRepository } from "../generated/shared-contracts/openapi";
import "./HuggingFaceImport.css";

type InspectedRepository = Omit<SchemaHubRepository, "response_recipes"> & {
  file_hint?: string | null;
  response_recipes: ResponseRecipe[];
};

const recipeFields = new Set([
  "temperature", "top_p", "top_k", "min_p", "typical_p",
  "presence_penalty", "frequency_penalty", "repeat_penalty",
]);

function usableRecipe(value: unknown): ResponseRecipe | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  const recipe = value as Record<string, unknown>;
  const settings = recipe.per_request;
  if (!settings || typeof settings !== "object" || Array.isArray(settings)) return null;
  if (!Object.entries(settings).length || !Object.entries(settings).every(([key, entry]) =>
    recipeFields.has(key) && typeof entry === "number" && Number.isFinite(entry))) return null;
  if (["id", "name", "section", "source_repo_id", "source_revision", "card_sha256"].some(key =>
    typeof recipe[key] !== "string" || !(recipe[key] as string).trim())) return null;
  if (recipe.reasoning !== "on" && recipe.reasoning !== "off" && recipe.reasoning !== "preserve") return null;
  if (recipe.notes !== undefined && (!Array.isArray(recipe.notes) || !recipe.notes.every(note => typeof note === "string"))) return null;
  return recipe as unknown as ResponseRecipe;
}

function inspectedRepository(value: SchemaHubRepository): InspectedRepository {
  return {
    ...value,
    response_recipes: (value.response_recipes ?? []).map(usableRecipe).filter((recipe): recipe is ResponseRecipe => recipe !== null),
  };
}

const recipeSettingLabels: Record<string, string> = {
  temperature: "Temp", top_p: "Top P", top_k: "Top K", min_p: "Min P",
  presence_penalty: "Presence penalty", frequency_penalty: "Frequency penalty", repeat_penalty: "Repetition penalty", repetition_penalty: "Repetition penalty",
};

function recipeSummary(recipe: ResponseRecipe): string {
  const values = Object.entries(recipe.per_request).map(([key, value]) => `${recipeSettingLabels[key] ?? key}: ${value}`);
  return [recipe.reasoning === "preserve" ? "Thinking unchanged" : `Thinking ${recipe.reasoning}`, ...values].join(" · ");
}

export function HuggingFaceImport({ onStarted }: { onStarted: (job: ImportJob) => Promise<void> }) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<Array<{ repo_id: string; downloads: number | null }>>([]);
  const [selectedRepo, setSelectedRepo] = useState("");
  const [hub, setHub] = useState<InspectedRepository | null>(null);
  const [variant, setVariant] = useState("");
  const [projector, setProjector] = useState("");
  const [recipeIds, setRecipeIds] = useState<string[]>([]);
  const [defaultRecipeId, setDefaultRecipeId] = useState("");
  const [bitFilter, setBitFilter] = useState<number | "all" | "unknown">("all");
  const [sizeOrder, setSizeOrder] = useState<"asc" | "desc">("asc");
  const [busy, setBusy] = useState<"search" | "inspect" | "download" | "">("");
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const generation = useRef(0);
  const downloadPending = useRef(false);
  useEffect(() => () => { generation.current += 1; }, []);

  async function inspectRepository(repo: string) {
    if (downloadPending.current) return;
    const current = ++generation.current;
    setSelectedRepo(repo); setHub(null); setVariant(""); setProjector(""); setBitFilter("all");
    setRecipeIds([]); setDefaultRecipeId("");
    setError(""); setMessage(""); setBusy("inspect");
    try {
      const next = inspectedRepository(await api.inspectHf(repo));
      if (current !== generation.current) return;
      setHub(next); setSelectedRepo(next.repo_id);
      const hint = next.file_hint;
      const hinted = hint ? next.variants.find(item => item.name === hint || item.files.includes(hint)) : undefined;
      setVariant(next.file_hint ? (hinted?.complete ? hinted.name : "") : next.variants.length === 1 && next.variants[0].complete ? next.variants[0].name : "");
      setProjector(next.projectors.length ? "" : "text-only");
    } catch (failure) { if (current === generation.current) setError(errorMessage(failure)); }
    finally { if (current === generation.current) setBusy(""); }
  }

  async function search() {
    const value = query.trim();
    if (!value || downloadPending.current) return;
    if (/^https?:\/\//i.test(value) || /^[\w.-]+\/[\w.-]+$/.test(value)) {
      setResults([]);
      await inspectRepository(value);
      return;
    }
    const current = ++generation.current;
    setBusy("search"); setError(""); setMessage(""); setHub(null); setSelectedRepo(""); setResults([]);
    try {
      const next = await api.searchHf(value);
      if (current !== generation.current) return;
      setResults(next);
      if (!next.length) setMessage("No matching repositories. Try a model name, publisher, or Hugging Face link.");
    } catch (failure) { if (current === generation.current) setError(errorMessage(failure)); }
    finally { if (current === generation.current) setBusy(""); }
  }

  const selectedVariant = hub?.variants.find(item => item.name === variant);
  const selectedPresentation = selectedVariant ? presentVariant(selectedVariant) : null;
  const selectedProjector = hub?.projectors.find(item => item.name === projector);
  const files = [...new Set([...(selectedVariant?.files ?? []), ...(selectedProjector?.files ?? []), ...(hub?.guidance_files ?? [])])];
  const size = selectedVariant?.size_bytes == null || (selectedProjector && selectedProjector.size_bytes == null)
    ? null : selectedVariant.size_bytes + (selectedProjector?.size_bytes ?? 0);
  const bits = [...new Set(hub?.variants.map(item => presentVariant(item).bits) ?? [])].sort((a, b) => a == null ? 1 : b == null ? -1 : a - b);
  const families = variantFamilies(hub?.variants ?? [], bitFilter, sizeOrder);
  const recipes = hub?.response_recipes ?? [];
  const selectedRecipes = recipes.filter(recipe => recipeIds.includes(recipe.id));

  function toggleRecipe(id: string, checked: boolean) {
    setRecipeIds(current => checked ? [...current, id] : current.filter(item => item !== id));
    if (!checked && defaultRecipeId === id) setDefaultRecipeId("");
  }

  async function download() {
    if (!hub || !selectedVariant?.complete || !projector || downloadPending.current) return;
    downloadPending.current = true;
    const current = ++generation.current;
    setBusy("download"); setError(""); setMessage("");
    try {
      const exactFiles = files.map(file => file.replaceAll("[", "[[]").replaceAll("?", "[?]").replaceAll("*", "[*]"));
      const job = await api.importHf(hub.repo_id, hub.resolved_revision, exactFiles, recipeIds, defaultRecipeId || null);
      if (current !== generation.current) return;
      setMessage(job.error ? `Download ${job.status}: ${job.error}` : job.status === "complete" ? "Model added to your library." : "Download started. Track progress in Downloads.");
      await onStarted(job);
    } catch (failure) { if (current === generation.current) setError(errorMessage(failure)); }
    finally { downloadPending.current = false; if (current === generation.current) setBusy(""); }
  }

  return <section className="card model-finder" aria-label="Find a model">
    <div className="setting-title"><h3>Hugging Face</h3><Help label="Find a model">Search by model or publisher, or paste a repository link. Choose one complete GGUF variant; image input also needs a compatible vision file.</Help></div>
    <form className="model-search" onSubmit={event => { event.preventDefault(); void search(); }}>
      <label htmlFor="model-search-query" className="visually-hidden">Model name or Hugging Face repository</label>
      <input id="model-search-query" maxLength={2048} value={query} disabled={busy === "download"} onChange={event => setQuery(event.target.value)} placeholder="Search models or paste a Hugging Face link" />
      <button type="submit" disabled={!query.trim() || Boolean(busy)}><Icon name="search" size={15} />{busy === "search" ? "Searching…" : "Find model"}</button>
    </form>
    {results.length ? <ul className="model-search-results" aria-label="Matching repositories">{results.map(result => <li key={result.repo_id} className={selectedRepo === result.repo_id ? "is-selected" : ""}>
      <div><strong>{result.repo_id}</strong>{result.downloads != null ? <span className="hint">{result.downloads.toLocaleString()} downloads</span> : null}</div>
      <button type="button" disabled={busy === "download"} aria-pressed={selectedRepo === result.repo_id} onClick={() => void inspectRepository(result.repo_id)}>{selectedRepo === result.repo_id ? "Selected" : "Select repository"}</button>
    </li>)}</ul> : null}
    {busy === "inspect" ? <p role="status">Loading model files for <strong>{selectedRepo}</strong>…</p> : null}
    {error ? <Notice tone="error" action={selectedRepo && !hub ? <button type="button" disabled={Boolean(busy)} onClick={() => void inspectRepository(selectedRepo)}>Retry loading files</button> : undefined}>{error}</Notice> : null}
    {hub ? <section className="model-download-selection" aria-label="Repository files">
      <div className="section-heading"><strong>{hub.repo_id}</strong><a href={`https://huggingface.co/${hub.repo_id}/blob/${hub.resolved_revision}/README.md`} target="_blank" rel="noreferrer">Model guide ↗</a></div>
      {hub.file_hint ? <p className="hint" role="status">{selectedVariant?.files.includes(hub.file_hint) ? "Linked GGUF file selected: " : "Linked GGUF file unavailable; choose a listed variant: "}<strong>{hub.file_hint}</strong></p> : null}
      {hub.source ? <p className="hint">Publisher settings: {hub.source.repo_id}{hub.source.resolved_revision ? ` @ ${hub.source.resolved_revision.slice(0, 8)}` : ""} · {hub.source.verified ? "source commit verified" : "source unverified; publisher settings will not be applied"}</p> : null}
      {hub.variants.length ? <div className="variant-picker">
        <div className="variant-picker-heading"><div><h4>Choose a GGUF variant</h4><p className="hint">Quantization and variant labels come from filenames; capabilities are checked after loading. Size is disk usage, not a RAM or GPU estimate.</p></div><label>Size within groups<select value={sizeOrder} onChange={event => setSizeOrder(event.target.value as "asc" | "desc")}><option value="asc">Smallest first</option><option value="desc">Largest first</option></select></label></div>
        <div className="variant-filters" role="group" aria-label="Filter by bit family"><button type="button" aria-pressed={bitFilter === "all"} onClick={() => setBitFilter("all")}>All <span>{hub.variants.length}</span></button>{bits.map(bit => <button key={bit ?? "unknown"} type="button" aria-pressed={bitFilter === (bit ?? "unknown")} onClick={() => setBitFilter(bit ?? "unknown")}>{bit == null ? "Unknown" : `${bit}-bit`}</button>)}</div>
        <div className="variant-table-scroll"><table className="variant-table"><thead><tr><th scope="col"><span className="visually-hidden">Select</span></th><th scope="col">Variant</th><th scope="col">Disk size</th><th scope="col">Files</th><th scope="col">Availability</th></tr></thead>{families.map(group => <tbody key={group.family}><tr className="variant-family"><th scope="rowgroup" colSpan={5}>{group.family}</th></tr>{group.items.map(({ variant: item, quant, flavour }) => <tr key={item.name} className={variant === item.name ? "is-selected" : undefined}><td><input type="radio" name="model-variant" value={item.name} aria-label={`${quant} ${flavour}, ${item.name}, ${item.size_bytes == null ? "size unknown" : formatBytes(item.size_bytes)}, ${item.complete ? "complete" : "missing files"}`} checked={variant === item.name} disabled={Boolean(busy) || !item.complete} onChange={() => setVariant(item.name)} /></td><td><label title={item.name} onClick={() => { if (!busy && item.complete) setVariant(item.name); }}><strong>{quant} · {flavour}</strong><small>{item.name}</small></label></td><td>{item.size_bytes == null ? "Unknown" : formatBytes(item.size_bytes)}</td><td>{item.files.length} {item.files.length === 1 ? "file" : "files"}</td><td><span className={item.complete ? "variant-ready" : "variant-missing"}>{item.complete ? "Complete" : "Missing shards"}</span></td></tr>)}</tbody>)}</table></div>
        {hub.projectors.length ? <fieldset className="projector-choices"><legend>Image input</legend><p className="hint">Choose a vision file explicitly or use text only. Listed files may still be incompatible.</p><label><input type="radio" name="image-input" value="text-only" checked={projector === "text-only"} disabled={Boolean(busy)} onChange={() => setProjector("text-only")} />Text only</label>{hub.projectors.map(item => <label key={item.name} title={item.name}><input type="radio" name="image-input" value={item.name} checked={projector === item.name} disabled={Boolean(busy) || !item.complete} onChange={() => setProjector(item.name)} /><span>{item.name}</span><small>{item.size_bytes == null ? "Size unknown" : formatBytes(item.size_bytes)}{item.complete ? "" : " · missing files"}</small></label>)}</fieldset> : null}
      </div> : <><Notice tone="warn">This repository has no primary GGUF weights. Choose a GGUF conversion to download.</Notice>
        {hub.gguf_candidates?.length ? <ul className="model-search-results" aria-label="GGUF conversions">{hub.gguf_candidates.map(candidate => <li key={candidate.repo_id}>
          <strong>{candidate.repo_id}</strong><button type="button" disabled={Boolean(busy)} onClick={() => void inspectRepository(candidate.repo_id)}>Inspect GGUF</button>
        </li>)}</ul> : <p className="hint">No GGUF conversion declared this exact publisher model. Search by model name to inspect other repositories.</p>}</>}
      {hub.warnings.length ? <details className="technical-details"><summary>Repository notes ({hub.warnings.length})</summary>{hub.warnings.map(warning => <p key={warning}>{warning}</p>)}</details> : null}
      {hub.auxiliary_ggufs?.length ? <details className="technical-details auxiliary-files"><summary>Auxiliary GGUF files <span>{hub.auxiliary_ggufs.length}</span></summary><p className="hint">MTP and imatrix files are separate from primary model weights. Listing an MTP file does not establish draft-head compatibility.</p><ul>{hub.auxiliary_ggufs.map(item => <li key={item.name}>{item.name} · {item.size_bytes == null ? "size unknown" : formatBytes(item.size_bytes)}{item.complete ? "" : " · missing shards"}</li>)}</ul></details> : null}
      {recipes.length ? <fieldset className="response-recipe-choices"><legend>Response recipes</legend><p className="hint">Optional model-card recommendations. Choose recipes to create saved Model configurations when the download completes.</p>{recipes.map(recipe => <label key={recipe.id}><input type="checkbox" checked={recipeIds.includes(recipe.id)} disabled={Boolean(busy)} onChange={event => toggleRecipe(recipe.id, event.target.checked)} /><span><strong>{recipe.name}</strong><small>{recipeSummary(recipe)}</small><small>From {recipe.source_repo_id} · {recipe.section} · revision {recipe.source_revision.slice(0, 8)}</small>{recipe.notes?.length ? <small>{recipe.notes.join(" · ")}</small> : null}</span></label>)}{selectedRecipes.length ? <fieldset><legend>Default Model configuration</legend><label><input type="radio" name="recipe-default" value="" checked={!defaultRecipeId} disabled={Boolean(busy)} onChange={() => setDefaultRecipeId("")} />Keep the current default</label>{selectedRecipes.map(recipe => <label key={recipe.id}><input type="radio" name="recipe-default" value={recipe.id} checked={defaultRecipeId === recipe.id} disabled={Boolean(busy)} onChange={() => setDefaultRecipeId(recipe.id)} />{recipe.name}</label>)}</fieldset> : null}</fieldset> : null}
      {selectedVariant ? <><div className="model-download-footer"><span className="hint">{size == null ? "Size unknown" : formatBytes(size)} · {selectedVariant.files.length} model file{selectedVariant.files.length === 1 ? "" : "s"}{selectedProjector ? " + vision file" : ""}</span><Help label="Download and vision files">Allow room for temporary and installed copies, roughly twice the selected size. Vision compatibility is checked after loading the model; a file being listed does not prove it is compatible.</Help><button type="button" className="primary-button" disabled={Boolean(busy) || !selectedVariant.complete || !projector} onClick={() => void download()}><Icon name="download" size={15} />{busy === "download" ? "Starting…" : "Download model"}</button></div>
        <div className="selected-download-files"><strong>Download selection: {selectedPresentation?.quant} · {selectedPresentation?.flavour}</strong><span className="hint">Pinned revision <code>{hub.resolved_revision}</code></span><ul>{files.map(file => <li key={file}>{file}</li>)}{hub.source?.verified ? (hub.source.guidance_files ?? []).map(file => <li key={`source-${file}`}>{hub.source?.repo_id} / {file}</li>) : null}</ul>{selectedRecipes.length ? <p className="hint">Create {selectedRecipes.length} Model configuration{selectedRecipes.length === 1 ? "" : "s"}: {selectedRecipes.map(item => item.name).join(", ")}. Default: {selectedRecipes.find(item => item.id === defaultRecipeId)?.name ?? "keep current"}.</p> : null}</div></> : null}
    </section> : null}
    {message ? <p role="status">{message}</p> : null}
  </section>;
}
