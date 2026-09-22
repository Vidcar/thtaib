import { useState } from "react";
import { api } from "./api";
import { EmptyState } from "./EmptyState";
import { errorMessage } from "./errors";
import { Notice } from "./Notice";
import { SettingsNotes } from "./settingsNotes";
import { ModelDeletion } from "./ModelDeletion";
import { Help } from "./ModelControls";
import { Icon } from "./Icon";
import type { ModelBundle, RunProfile } from "./types";

function objectFrom(text: string): Record<string, unknown> {
  const value: unknown = JSON.parse(text || "{}");
  if (!value || Array.isArray(value) || typeof value !== "object") throw new Error("Settings must be a JSON object.");
  return value as Record<string, unknown>;
}

export function ProfilesPanel({ profiles, bundles, refresh }: { profiles: RunProfile[]; bundles: ModelBundle[]; refresh: () => Promise<void> }) {
  const [editing, setEditing] = useState("");
  const [name, setName] = useState("My preset");
  const [bundle, setBundle] = useState("");
  const [temperature, setTemperature] = useState("");
  const [limit, setLimit] = useState("");
  const [instructions, setInstructions] = useState("");
  const [startup, setStartup] = useState("{}");
  const [requestExtra, setRequestExtra] = useState("{}");
  const [agentExtra, setAgentExtra] = useState("{}");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [failed, setFailed] = useState(false);

  function edit(profile?: RunProfile) {
    setEditing(profile?.id ?? ""); setName(profile?.display_name ?? "My preset"); setBundle(profile?.bundle_id ?? "");
    const request = { ...profile?.bags.per_request.requested }, agent = { ...profile?.bags.agent.requested };
    setTemperature(request.temperature == null ? "" : String(request.temperature));
    setLimit(request.max_tokens == null ? "" : String(request.max_tokens));
    setInstructions(agent.system_prompt == null ? "" : String(agent.system_prompt));
    delete request.temperature; delete request.max_tokens; delete agent.system_prompt;
    setStartup(JSON.stringify(profile?.bags.startup.requested ?? {}, null, 2));
    setRequestExtra(JSON.stringify(request, null, 2)); setAgentExtra(JSON.stringify(agent, null, 2));
    setMessage("");
  }

  async function action(work: () => Promise<void>) {
    setBusy(true); setMessage(""); setFailed(false);
    try { await work(); await refresh(); } catch (error) { setFailed(true); setMessage(errorMessage(error)); } finally { setBusy(false); }
  }

  return <div className="presets-layout">
    <form className="card" onSubmit={event => {
      event.preventDefault(); void action(async () => {
        const per_request = objectFrom(requestExtra), agent = objectFrom(agentExtra);
        if ("temperature" in per_request || "max_tokens" in per_request || "system_prompt" in agent) throw new Error("Use the named controls for creativity, reply length and instructions.");
        if (temperature !== "") per_request.temperature = Number(temperature);
        if (limit !== "") per_request.max_tokens = Number(limit);
        if (instructions.trim()) agent.system_prompt = instructions;
        const payload = { display_name: name.trim(), bundle_id: bundle || null, startup: objectFrom(startup), per_request, agent };
        const saved = editing ? await api.updateProfile(editing, payload) : await api.createProfile({ ...payload, bundle_id: bundle || undefined });
        setEditing(saved.id); setMessage(`Saved ${saved.display_name}. Running models keep their original launch settings.`);
      });
    }}>
      <div className="setting-title"><h3>{editing ? "Edit preset" : "New preset"}</h3><Help label="Presets">Reusable model, response and instruction settings. Edits affect future work; running models keep their launch settings.</Help></div>
      <label>Name<input required value={name} onChange={event => setName(event.target.value)} /></label>
      <label>Use with<select value={bundle} onChange={event => setBundle(event.target.value)}>
        <option value="">Any compatible model</option>
        {bundle && !bundles.some(item => item.id === bundle) ? <option value={bundle}>Model unavailable</option> : null}
        {bundles.map(item => <option key={item.id} value={item.id}>{item.display_name}</option>)}
      </select></label>
      <div className="setup-grid">
        <label>Creativity (temperature)<input type="number" min="0" step="0.01" value={temperature} onChange={event => setTemperature(event.target.value)} placeholder="Use model setting" /></label>
        <label>Reply limit (tokens)<input type="number" min="1" step="1" value={limit} onChange={event => setLimit(event.target.value)} placeholder="No preset limit" /></label>
      </div>
      <label>Instructions<textarea value={instructions} onChange={event => setInstructions(event.target.value)} /></label>
      <details className="technical-details"><summary>Additional settings</summary>
        <label>Startup settings (JSON)<textarea spellCheck={false} value={startup} onChange={event => setStartup(event.target.value)} /></label>
        <label>Additional response settings (JSON)<textarea spellCheck={false} value={requestExtra} onChange={event => setRequestExtra(event.target.value)} /></label>
        <label>Additional agent settings (JSON)<textarea spellCheck={false} value={agentExtra} onChange={event => setAgentExtra(event.target.value)} /></label>
      </details>
      <div className="actions"><button className="primary-button" disabled={busy || !name.trim()}>{busy ? "Saving…" : "Save preset"}</button><button type="button" disabled={busy} onClick={() => edit()}>New preset</button></div>
      {message ? <Notice tone={failed ? "error" : "info"}>{message}</Notice> : null}
    </form>
    <div className="card"><h3>Saved presets</h3>
      {!profiles.length ? <EmptyState title="Save a preset for the way you like to work." /> : <ul className="list">{profiles.map(profile => <li className="entity" key={profile.id}>
        <strong>{profile.display_name}</strong>
        <p className="hint">{profile.bundle_id ? bundles.find(item => item.id === profile.bundle_id)?.display_name ?? "Model unavailable" : "Reusable across compatible models"}</p>
        <div className="actions"><button type="button" className="icon-button" aria-label={`Edit ${profile.display_name}`} title="Edit preset" disabled={busy} onClick={() => edit(profile)}><Icon name="edit" size={16} /></button>
          <button type="button" className="icon-button" aria-label={`Duplicate ${profile.display_name}`} title="Duplicate preset" disabled={busy} onClick={() => void action(async () => { const copy = await api.duplicateProfile(profile.id); edit(copy); setMessage(`Created ${copy.display_name}.`); })}><Icon name="copy" size={16} /></button>
        </div>
        <SettingsNotes unsupported={profile.bags.startup.unsupported} retired={profile.bags.startup.retired} />
        <ModelDeletion kind="profile" id={profile.id} name={profile.display_name} onDeleted={async () => { if (editing === profile.id) edit(); await refresh(); }} />
      </li>)}</ul>}
    </div>
  </div>;
}
