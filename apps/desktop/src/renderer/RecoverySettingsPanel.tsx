import { useEffect, useRef, useState, type ReactNode } from "react";

import {
  packet03Api,
  type PermissionGrant,
} from "./packet03Api";
import type { PresentationSettings, PresentationTheme } from "./types";
import { AppearanceSettings } from "./AppearanceSettings";
import { CompactSwitch, SegmentedChoice, SettingRow, SettingSection } from "./CompactControls";
import { Icon } from "./Icon";
import { ProjectFileGrantControls } from "./ProjectFileGrantControls";
import "./packet03Panels.css";
import "./RecoverySettingsPanel.css";

interface RecoverySettingsPanelProps {
  children?: ReactNode;
  defaultsPanel?: ReactNode;
  connectionsPanel?: ReactNode;
  onPreferencesChanged?: (preferences: PresentationSettings) => void;
}

const SETTINGS_CATEGORIES = ["Appearance", "Notifications", "Defaults", "Connections", "Permissions"] as const;
type SettingsCategory = (typeof SETTINGS_CATEGORIES)[number];

const fallbackPresentation: PresentationSettings = {
  theme: "system",
  detailed_streams: false,
  attention_notifications: true,
  success_notifications: false,
};

function grantLabel(grant: PermissionGrant): string {
  const scope = grant.scope === "always" ? "Always allow" : "This session";
  return `${scope}: ${grant.kind === "project_files" ? "Project file changes" : grant.action}`;
}

function argumentSummary(value: Record<string, unknown>): string {
  const entries = Object.entries(value);
  if (entries.length === 0) return "No arguments recorded";
  return entries.slice(0, 4).map(([key, item]) => `${key}: ${String(item)}`).join(", ");
}

export function RecoverySettingsPanel({ onPreferencesChanged, children, defaultsPanel, connectionsPanel }: RecoverySettingsPanelProps) {
  const [category, setCategory] = useState<SettingsCategory>(() => {
    try {
      const saved = sessionStorage.getItem("workbench.settings.category");
      if (saved && (SETTINGS_CATEGORIES as readonly string[]).includes(saved)) return saved as SettingsCategory;
    } catch { /* Use the first category when storage is unavailable. */ }
    return "Appearance";
  });
  useEffect(() => { try { sessionStorage.setItem("workbench.settings.category", category); } catch { /* Optional preference. */ } }, [category]);
  const [preferences, setPreferences] = useState<PresentationSettings>(fallbackPresentation);
  const [preferencesLoaded, setPreferencesLoaded] = useState(false);
  const [preferencesBusy, setPreferencesBusy] = useState(false);
  const [grants, setGrants] = useState<PermissionGrant[]>([]);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const preferencesRef = useRef(preferences);
  const preferencesLoadedRef = useRef(false);
  const refreshInFlight = useRef(false);
  const saveInFlight = useRef(false);
  const preferencesGeneration = useRef(0);

  function applyPreferences(next: PresentationSettings): void {
    preferencesRef.current = next;
    setPreferences(next);
  }

  function markPreferencesLoaded(): void {
    preferencesLoadedRef.current = true;
    setPreferencesLoaded(true);
  }

  async function refresh(): Promise<void> {
    if (refreshInFlight.current || saveInFlight.current) return;
    refreshInFlight.current = true;
    const generation = preferencesGeneration.current;
    setBusy(true);
    setMessage("");
    try {
      const [nextPreferencesResult, nextGrants] = await Promise.allSettled([
        packet03Api.presentation(),
        packet03Api.grants(),
      ]);
      if (nextPreferencesResult.status === "fulfilled") {
        if (generation === preferencesGeneration.current && !saveInFlight.current) {
          applyPreferences(nextPreferencesResult.value);
          markPreferencesLoaded();
        }
      } else {
        setMessage(nextPreferencesResult.reason instanceof Error ? nextPreferencesResult.reason.message : String(nextPreferencesResult.reason));
      }
      if (nextGrants.status !== "fulfilled") {
        throw nextGrants.reason;
      }
      setGrants(nextGrants.value);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : String(error));
    } finally {
      refreshInFlight.current = false;
      setBusy(false);
    }
  }

  useEffect(() => {
    void refresh();
  }, []);

  async function savePreferences(patch: Partial<PresentationSettings>): Promise<void> {
    if (!preferencesLoadedRef.current || saveInFlight.current || refreshInFlight.current) return;
    saveInFlight.current = true;
    const generation = preferencesGeneration.current + 1;
    preferencesGeneration.current = generation;
    const previous = preferencesRef.current;
    const optimistic = { ...previous, ...patch };
    applyPreferences(optimistic);
    setPreferencesBusy(true);
    setMessage("");
    try {
      const saved = await packet03Api.savePresentation(patch);
      if (preferencesGeneration.current === generation) {
        applyPreferences(saved);
        markPreferencesLoaded();
        onPreferencesChanged?.(saved);
      }
    } catch (error) {
      if (preferencesGeneration.current === generation) {
        applyPreferences(previous);
        setMessage(error instanceof Error ? error.message : String(error));
      }
    } finally {
      saveInFlight.current = false;
      if (preferencesGeneration.current === generation) {
        setPreferencesBusy(false);
      }
    }
  }

  async function revoke(grantId: string): Promise<void> {
    setBusy(true);
    setMessage("");
    try {
      await packet03Api.revokeGrant(grantId);
      setGrants((current) => current.filter((grant) => grant.id !== grantId));
      setMessage("Grant revoked.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : String(error));
    } finally {
      setBusy(false);
    }
  }

  const preferenceControlsDisabled = !preferencesLoaded || preferencesBusy || refreshInFlight.current;

  return (
    <section className="packet03-panel settings-surface" aria-label="Recovery and settings">
      <header className="settings-head">
        <div><h2>Settings</h2><p className="hint">How the Workbench looks, notifies and keeps your work safe on this computer.</p></div>
        <button type="button" className="quiet-button" disabled={busy || preferencesBusy} onClick={() => void refresh()}>
          <Icon name="refresh" size={14} /> Refresh
        </button>
      </header>

      <nav className="settings-categories" aria-label="Settings categories">{SETTINGS_CATEGORIES.map(item => <button type="button" key={item} aria-current={category === item ? "page" : undefined} onClick={() => setCategory(item)}>{item}</button>)}</nav>

      {message ? <p role="status" className="notice">{message}</p> : null}

      <div className="settings-category-content" hidden={category !== "Notifications"}>
        <SettingSection title="Notifications" description="Shown while the app is in the background. Select one to return to the work.">
          <CompactSwitch label="Notify when work needs attention" description="Approvals, questions and failures." checked={preferences.attention_notifications} disabled={preferenceControlsDisabled} onChange={attention_notifications => void savePreferences({ attention_notifications })} />
          <CompactSwitch label="Notify when work finishes" description="Completed chats and workflow runs. Works independently of attention notifications." checked={preferences.success_notifications} disabled={preferenceControlsDisabled} onChange={success_notifications => void savePreferences({ success_notifications })} />
        </SettingSection>
      </div>

      <div className="settings-category-content settings-appearance" hidden={category !== "Appearance"}>
        <SettingSection title="Theme and display" description="Saved with your preferences.">
          <SegmentedChoice label="Theme" description="System follows your computer's light or dark setting." value={preferences.theme} disabled={preferenceControlsDisabled} options={[{ value: "system", label: "System" }, { value: "dark", label: "Dark" }, { value: "light", label: "Light" }]} onChange={theme => void savePreferences({ theme: theme as PresentationTheme })} />
          <CompactSwitch label="Show reasoning and tool details by default" description="Each conversation can still show or hide them from its view menu." checked={preferences.detailed_streams} disabled={preferenceControlsDisabled} onChange={detailed_streams => void savePreferences({ detailed_streams })} />
        </SettingSection>
        <AppearanceSettings theme={preferences.theme} />
      </div>

      <div hidden={category !== "Defaults"} className="settings-category-content">{defaultsPanel ?? children}</div>
      <div hidden={category !== "Connections"} className="settings-category-content">{connectionsPanel}</div>

      <div className="settings-category-content settings-permissions" hidden={category !== "Permissions"}>
        <SettingSection title="Saved permissions" description="Exact approvals retain their original inputs. Project file grants cover only the listed native operations and paths. Revoke one to be asked again in Ask mode." actions={<span className="badge">{grants.length || "None"}</span>}>
          {category === "Permissions" ? <ProjectFileGrantControls onSaved={async () => { setGrants(await packet03Api.grants()); setMessage("Project file grant saved."); }} /> : null}
          {grants.length === 0 ? (
            <p className="hint">In Ask mode, choose <strong>Allow for this session</strong> or <strong>Always allow</strong> on an action's approval card to save it here. Approve once and Full access do not save permissions.</p>
          ) : grants.map((grant) => (
            <SettingRow key={grant.id} inline label={grantLabel(grant)} provenance={<>{grant.kind === "project_files" ? <>{grant.operations?.join(", ")} · Excludes: {grant.excluded_paths?.join(", ") || "None"}</> : argumentSummary(grant.arguments)}{grant.project_path ? <> · Project: {grant.project_path}</> : null}</>}>
              <button type="button" disabled={busy} onClick={() => void revoke(grant.id)}>
                <Icon name="close" size={14} /> Revoke
              </button>
            </SettingRow>
          ))}
        </SettingSection>
      </div>
    </section>
  );
}
