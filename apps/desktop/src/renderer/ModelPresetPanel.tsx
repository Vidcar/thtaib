import { useEffect, useRef, useState } from "react";
import { api } from "./api";
import { errorMessage } from "./errors";
import { settingValue } from "./effectiveSettings";
import { Notice } from "./Notice";
import type { BundleConfigurationOptions, ModelBundle, ResponseRecipe, ResponseRecipeOrigin } from "./types";

const labels: Record<string, string> = { reasoning: "Thinking", reasoning_effort: "Thinking level", temperature: "Temperature", top_p: "Top P", top_k: "Top K", min_p: "Min P", max_tokens: "Response budget", presence_penalty: "Presence penalty", repeat_penalty: "Repetition penalty", frequency_penalty: "Frequency penalty" };
export function presetValues(recipe: ResponseRecipe) { return { ...recipe.per_request, ...(recipe.reasoning === "preserve" ? {} : { reasoning: recipe.reasoning }) }; }
export function ModelPresetPanel({ bundle, value, origin, options, onApply, onChanged, disabled = false }: {
  bundle: ModelBundle; value: Record<string, unknown>; origin: ResponseRecipeOrigin | null; options: BundleConfigurationOptions | null;
  onApply: (value: Record<string, unknown>, origin: ResponseRecipeOrigin) => void; onChanged?: () => Promise<void>;
  disabled?: boolean;
}) {
  const [selected, setSelected] = useState(origin?.recipe_id ?? ""), [busy, setBusy] = useState(false), [error, setError] = useState("");
  const generation = useRef(0);
  const pending = useRef(false);
  const blocked = busy || disabled;
  useEffect(() => {
    setSelected(origin?.recipe_id ?? ""); setError(""); setBusy(false);
    return () => { generation.current++; };
  }, [bundle.id]);
  const hidden = bundle.huggingface_configuration?.hidden_response_recipe_ids ?? [];
  const recipes = (bundle.huggingface_configuration?.response_recipes ?? []).filter(recipe => !hidden.includes(recipe.id));
  const recipe = recipes.find(item => item.id === selected);
  const incompatible = recipe && (recipe.reasoning !== "preserve" && options?.per_request_defaults.reasoning?.supported === false || Object.keys(recipe.per_request).some(key => options?.per_request_defaults[key]?.supported === false));
  async function update(operation: () => Promise<unknown>, onSuccess?: () => void) {
    if (pending.current || disabled) return;
    pending.current = true;
    const owner = generation.current; setBusy(true); setError("");
    try {
      await operation();
      if (owner === generation.current) onSuccess?.();
      // This updates the catalogue, including a completed removal after closing
      // the panel. Models owns preserving the user's current selection/draft.
      await onChanged?.();
    } catch (failure) { if (owner === generation.current) setError(errorMessage(failure)); }
    finally { pending.current = false; if (owner === generation.current) setBusy(false); }
  }
  return <section className="model-preset-panel">
    <p className="hint">Apply publisher response values to this draft, then Save.</p>
    <div className="actions"><button type="button" disabled={blocked || bundle.source.kind !== "huggingface"} onClick={() => void update(() => api.refreshResponseRecipes(bundle.id))}>Refresh from model card</button><button type="button" disabled={blocked || !hidden.length} onClick={() => void update(() => api.refreshResponseRecipes(bundle.id, true))}>Restore presets from model card</button></div>
    {error ? <Notice tone="error">{error}</Notice> : null}
    <div className="model-preset-choices" role="radiogroup" aria-label="Model-card preset">{recipes.map(item => <label key={item.id}><input type="radio" name={`card-preset-${bundle.id}`} value={item.id} checked={selected === item.id} disabled={blocked} onChange={() => setSelected(item.id)} /><span><strong>{item.name}</strong><small>{item.reasoning === "preserve" ? "Thinking unchanged" : `Thinking ${item.reasoning}`}</small></span></label>)}</div>
    {!recipes.length ? <p className="hint">{hidden.length ? "All presets were removed from this list. Restore them from the model card." : "No compatible publisher presets are recorded for this model."}</p> : null}
    {recipe ? <><h4>Values to apply</h4><table className="model-preset-diff"><thead><tr><th>Setting</th><th>Current draft</th><th>Preset</th></tr></thead><tbody>{Object.entries(presetValues(recipe)).map(([key, next]) => <tr key={key}><th>{labels[key] ?? key.replaceAll("_", " ")}</th><td>{Object.hasOwn(value, key) ? settingValue(value[key], key) : "Model default"}</td><td>{settingValue(next, key)}</td></tr>)}</tbody></table>
      <p className="hint">Loading settings and response values outside this list stay as they are.</p><p className="hint">{recipe.source_repo_id} · {recipe.source_revision.slice(0, 12)}<br />{recipe.section}</p>
      {incompatible ? <Notice tone="warn">This preset contains settings unavailable for the selected template.</Notice> : null}
      <div className="actions"><button type="button" className="primary-button" disabled={blocked || Boolean(incompatible) || !options} onClick={() => onApply({ ...value, ...presetValues(recipe) }, { recipe_id: recipe.id, name: recipe.name, source_repo_id: recipe.source_repo_id, source_revision: recipe.source_revision, card_sha256: recipe.card_sha256, section: recipe.section })}>Apply to draft</button><button type="button" disabled={blocked} onClick={() => void update(() => api.setResponseRecipeVisibility(bundle.id, recipe.id, false), () => setSelected(""))}>Remove from list</button></div>
    </> : null}
  </section>;
}
