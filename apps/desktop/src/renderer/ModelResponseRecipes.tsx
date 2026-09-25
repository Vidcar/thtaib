import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { api } from "./api";
import { errorMessage } from "./errors";
import { settingValue } from "./effectiveSettings";
import { Notice } from "./Notice";
import type { ModelBundle, ModelCard, ResponseRecipe, RunProfile } from "./types";

const fieldNames: Record<string, string> = {
  temperature: "Temperature", top_p: "Top P", top_k: "Top K", min_p: "Min P",
  presence_penalty: "Presence penalty", repeat_penalty: "Repetition penalty",
  frequency_penalty: "Frequency penalty", max_tokens: "Reply limit",
};

function cardUrl(recipe: ResponseRecipe): string {
  return pinnedCardUrl(recipe.source_repo_id, recipe.source_revision);
}

function pinnedCardUrl(repoId: string, revision: string): string {
  const repo = repoId.split("/").map(encodeURIComponent).join("/");
  return `https://huggingface.co/${repo}/blob/${encodeURIComponent(revision)}/README.md`;
}

function safeCardHref(raw: string, repoId: string, revision: string): string {
  if (!raw || raw.startsWith("//") || raw.startsWith("/") || raw.includes("\\") || /%(?:2f|5c)/i.test(raw)) return "";
  if (/^[a-z][\w+.-]*:/i.test(raw)) {
    try {
      const url = new URL(raw);
      return url.protocol === "https:" || url.protocol === "http:" ? url.href : "";
    } catch { return ""; }
  }
  try {
    const base = pinnedCardUrl(repoId, revision);
    const url = new URL(raw, base);
    const pinnedRoot = new URL(base).pathname.replace(/README\.md$/, "");
    return url.origin === "https://huggingface.co" && url.pathname.startsWith(pinnedRoot) ? url.href : "";
  } catch { return ""; }
}

export function ModelResponseRecipes({ bundle, profiles, onChanged }: {
  bundle: ModelBundle; profiles: RunProfile[]; onChanged: () => Promise<void>;
}) {
  const recipes = bundle.huggingface_configuration?.response_recipes ?? [];
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [defaultId, setDefaultId] = useState("");
  const [busy, setBusy] = useState<"refresh" | "create" | "">("");
  const [notice, setNotice] = useState<{ tone: "ok" | "error"; text: string } | null>(null);
  const [cardOpen, setCardOpen] = useState(false);
  const [cardBusy, setCardBusy] = useState(false);
  const [card, setCard] = useState<ModelCard | null>(null);
  const [cardError, setCardError] = useState("");
  const cardGeneration = useRef(0);
  const mounted = useRef(true);
  const selectedRecipes = recipes.filter(recipe => selectedIds.includes(recipe.id));
  const repoId = bundle.source.repo_id;
  const revision = bundle.source.resolved_revision;
  const pinnedUrl = repoId && revision ? pinnedCardUrl(repoId, revision) : null;

  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; cardGeneration.current += 1; };
  }, []);

  async function loadCard() {
    const generation = ++cardGeneration.current;
    setCardBusy(true); setCardError(""); setCard(null);
    try {
      const result = await api.modelCard(bundle.id);
      if (generation !== cardGeneration.current) return;
      if (result.bundle_id !== bundle.id || result.repo_id !== repoId || result.revision !== revision) {
        throw new Error("The returned card does not match the selected model and installed revision.");
      }
      setCard(result);
    } catch (error) {
      if (generation === cardGeneration.current) setCardError(errorMessage(error));
    } finally {
      if (generation === cardGeneration.current) setCardBusy(false);
    }
  }

  function toggleCard() {
    if (cardOpen) {
      cardGeneration.current += 1;
      setCardBusy(false);
      setCardOpen(false);
    } else {
      setCardOpen(true);
      if (!card) void loadCard();
    }
  }

  async function updateLibrary(success: string) {
    setNotice({ tone: "ok", text: success });
    try { await onChanged(); } catch (error) {
      setNotice({ tone: "error", text: `The model was updated, but the library could not refresh: ${errorMessage(error)}` });
    }
  }

  async function refreshCard() {
    setBusy("refresh"); setNotice(null);
    try {
      const updated = await api.refreshResponseRecipes(bundle.id);
      setSelectedIds([]); setDefaultId("");
      await updateLibrary(updated.huggingface_configuration?.response_recipes?.length
        ? "Response recipes refreshed from this model's pinned repository card."
        : "The pinned repository card has no clear response recipes to offer.");
      if (cardOpen && mounted.current) await loadCard();
    } catch (error) { setNotice({ tone: "error", text: `Card refresh failed: ${errorMessage(error)}` }); }
    finally { setBusy(""); }
  }

  async function createConfigurations() {
    setBusy("create"); setNotice(null);
    try {
      await api.createRecipeConfigurations(bundle.id, selectedIds, defaultId || null);
      await updateLibrary(defaultId
        ? "Selected response recipes are available as model configurations. The chosen configuration is now the model default."
        : "Selected response recipes are available as model configurations. The model default was kept.");
    } catch (error) { setNotice({ tone: "error", text: `Configuration creation failed: ${errorMessage(error)}` }); }
    finally { setBusy(""); }
  }

  return <section className="card model-recipe-library" aria-labelledby="model-recipes-heading">
    <div className="model-card-heading"><div><h3>Model card</h3><p className="hint">{repoId ?? "Hugging Face repository unavailable"}{revision ? ` · installed revision ${revision.slice(0, 12)}` : " · installed revision unavailable"}</p></div><div className="model-card-actions">{pinnedUrl ? <a href={pinnedUrl} target="_blank" rel="noreferrer noopener">View pinned card ↗</a> : null}<button type="button" aria-expanded={cardOpen} aria-controls={`model-card-content-${bundle.id}`} onClick={toggleCard}>{cardOpen ? "Hide model card" : "Show model card"}</button></div></div>
    {cardOpen ? <div id={`model-card-content-${bundle.id}`} className="model-card-content" aria-label="Selected model card">
      {cardBusy ? <p role="status">Loading this model's pinned card…</p> : null}
      {cardError ? <Notice tone="error" action={<button type="button" onClick={() => void loadCard()}>Retry card</button>}>Model card unavailable: {cardError}</Notice> : null}
      {card ? <><p className="model-card-provenance hint">{card.origin === "saved" ? "Verified saved card" : "Fetched from pinned Hugging Face revision"} · SHA-256 <code>{card.sha256}</code></p><div className="model-card-markdown"><ReactMarkdown remarkPlugins={[remarkGfm]} urlTransform={url => safeCardHref(url, card.repo_id, card.revision)} components={{
        a({ children, href }) { return href ? <a href={href} target="_blank" rel="noreferrer noopener">{children}</a> : <span>{children}</span>; },
        img({ alt }) { return <span className="hint">{alt ? `[Image omitted: ${alt}]` : "[Image omitted]"}</span>; },
      }}>{card.markdown}</ReactMarkdown></div></> : null}
    </div> : null}
    <div className="section-heading"><div><h3 id="model-recipes-heading">Response recipes</h3><p className="hint">Suggestions from this GGUF repository's model card. A recipe affects requests when its configuration is selected.</p></div><button type="button" disabled={Boolean(busy)} onClick={() => void refreshCard()}>{busy === "refresh" ? "Refreshing…" : "Refresh model card"}</button></div>
    <p className="hint">Refresh reads the recorded revision of the card without downloading model weights. New configurations copy the current model default's saved launch settings and remain independent after creation.</p>
    {notice ? <Notice tone={notice.tone}>{notice.text}</Notice> : null}
    {recipes.length ? <>
      <fieldset className="model-recipe-choices" disabled={Boolean(busy)}><legend>Choose recipes to make configurations</legend>
        {recipes.map(recipe => {
          const existing = profiles.find(profile => profile.bundle_id === bundle.id && profile.recipe_origin?.recipe_id === recipe.id
            && profile.recipe_origin.source_repo_id === recipe.source_repo_id
            && profile.recipe_origin.source_revision === recipe.source_revision && profile.recipe_origin.card_sha256 === recipe.card_sha256);
          return <div key={recipe.id} className="model-recipe-choice"><label><input type="checkbox" checked={selectedIds.includes(recipe.id)} onChange={event => {
            const next = event.target.checked ? [...selectedIds, recipe.id] : selectedIds.filter(id => id !== recipe.id);
            setSelectedIds(next);
            if (!next.includes(defaultId)) setDefaultId("");
          }} /><span><strong>{recipe.name}</strong><small>{recipe.reasoning === "off" ? "Non-thinking" : recipe.reasoning === "on" ? "Thinking" : "Thinking unchanged"} · {Object.entries(recipe.per_request).map(([key, value]) => `${fieldNames[key] ?? key.replaceAll("_", " ")} ${settingValue(value)}`).join(" · ")}</small>{existing ? <small>Created from model card as “{existing.display_name}”</small> : null}{recipe.notes?.length ? <small>{recipe.notes.join(" · ")}</small> : null}</span></label><small className="model-recipe-source">Repository card · {recipe.source_repo_id} @ {recipe.source_revision.slice(0, 12)} · {recipe.section} · card {recipe.card_sha256.slice(0, 12)} · <a href={cardUrl(recipe)} target="_blank" rel="noreferrer">View pinned card</a></small></div>;
        })}
      </fieldset>
      <div className="model-recipe-actions"><label htmlFor={`model-recipe-default-${bundle.id}`}>Model default<select id={`model-recipe-default-${bundle.id}`} value={defaultId} disabled={Boolean(busy) || !selectedRecipes.length} onChange={event => setDefaultId(event.target.value)}><option value="">Keep current default</option>{selectedRecipes.map(recipe => <option key={recipe.id} value={recipe.id}>{recipe.name}</option>)}</select></label><button type="button" className="primary-button" disabled={Boolean(busy) || !selectedRecipes.length} onClick={() => void createConfigurations()}>{busy === "create" ? "Creating…" : "Create selected configurations"}</button></div>
      {!bundle.disk_matches ? <p className="hint">Some saved files need verification. The configuration check will confirm whether this model's template supports the selected recipes.</p> : null}
    </> : <p className="hint">No clear response recipes are saved for this model. Refresh its pinned model card to check for recommendations.</p>}
  </section>;
}
