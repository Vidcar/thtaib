import { useEffect, useRef, useState, type ReactNode } from "react";

import {
  packet03Api,
  type BackupCreateResult,
  type BackupRestoreResult,
  type PermissionGrant,
} from "./packet03Api";
import type { PresentationSettings, PresentationTheme } from "./types";
import { AppearanceSettings } from "./AppearanceSettings";
import { CompactSwitch, SegmentedChoice, SettingRow, SettingSection } from "./CompactControls";
import { HoverHelp } from "./HoverHelp";
import { pickWorkbenchPath } from "./PathField";
import { Icon } from "./Icon";
import "./packet03Panels.css";
import "./RecoverySettingsPanel.css";

interface RecoverySettingsPanelProps {
  children?: ReactNode;
  defaultsPanel?: ReactNode;
  connectionsPanel?: ReactNode;
  onPreferencesChanged?: (preferences: PresentationSettings) => void;
  onRestoreCompleted?: (result: BackupRestoreResult) => void;
}

const fallbackPresentation: PresentationSettings = {
  theme: "system",
  detailed_streams: false,
  attention_notifications: true,
  success_notifications: false,
};

function backupArchivePath(destinationFolder: string, now = new Date()): string {
  const folder = destinationFolder.trim();
  const separator = folder.includes("\\") ? "\\" : "/";
  const normalizedFolder = folder.replace(/[\\/]+$/, "");
  const stamp = now.toISOString().replaceAll(":", "-").replace(/\.\d{3}Z$/, "Z");
  return `${normalizedFolder}${separator}local-ai-workbench-${stamp}.workbench-backup.zip`;
}

function grantLabel(grant: PermissionGrant): string {
  const scope = grant.scope === "always" ? "Always allow" : "This session";
  return `${scope}: ${grant.action}`;
}

function argumentSummary(value: Record<string, unknown>): string {
  const entries = Object.entries(value);
  if (entries.length === 0) return "No arguments recorded";
  return entries.slice(0, 4).map(([key, item]) => `${key}: ${String(item)}`).join(", ");
}

export function RecoverySettingsPanel({ onPreferencesChanged, onRestoreCompleted, children, defaultsPanel, connectionsPanel }: RecoverySettingsPanelProps) {
  const [category, setCategory] = useState(() => {
    try {
      const saved = sessionStorage.getItem("workbench.settings.category");
      if (saved && ["Appearance", "Notifications", "Defaults", "Connections", "Permissions", "Backup"].includes(saved)) return saved;
    } catch { /* Use the first category when storage is unavailable. */ }
    return "Appearance";
  });
  useEffect(() => { try { sessionStorage.setItem("workbench.settings.category", category); } catch { /* Optional preference. */ } }, [category]);
  const [preferences, setPreferences] = useState<PresentationSettings>(fallbackPresentation);
  const [preferencesLoaded, setPreferencesLoaded] = useState(false);
  const [preferencesBusy, setPreferencesBusy] = useState(false);
  const [grants, setGrants] = useState<PermissionGrant[]>([]);
  const [activeRunIds, setActiveRunIds] = useState<string[]>([]);
  const [backupDestination, setBackupDestination] = useState("");
  const [restoreArchive, setRestoreArchive] = useState("");
  const [restoreDestination, setRestoreDestination] = useState("");
  const [lastBackup, setLastBackup] = useState<BackupCreateResult | null>(null);
  const [lastRestore, setLastRestore] = useState<BackupRestoreResult | null>(null);
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
      const [nextPreferencesResult, nextGrants, work] = await Promise.allSettled([
        packet03Api.presentation(),
        packet03Api.grants(),
        packet03Api.activeWork(),
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
      if (work.status !== "fulfilled") {
        throw work.reason;
      }
      setGrants(nextGrants.value);
      setActiveRunIds(work.value.active_run_ids);
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

  async function chooseFolder(setter: (path: string) => void): Promise<void> {
    const selected = await pickWorkbenchPath("folder");
    if (selected) setter(selected);
  }

  async function chooseFile(setter: (path: string) => void): Promise<void> {
    const selected = await pickWorkbenchPath("file");
    if (selected) setter(selected);
  }

  async function createBackup(): Promise<void> {
    if (!backupDestination.trim()) return;
    setBusy(true);
    setMessage("");
    try {
      const result = await packet03Api.createBackup(backupArchivePath(backupDestination));
      setLastBackup(result);
      setMessage("Backup created.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : String(error));
    } finally {
      setBusy(false);
    }
  }

  async function restoreBackup(): Promise<void> {
    if (!restoreArchive.trim() || !restoreDestination.trim()) return;
    setBusy(true);
    setMessage("");
    try {
      const result = await packet03Api.restoreBackup(restoreArchive.trim(), restoreDestination.trim());
      setLastRestore(result);
      onRestoreCompleted?.(result);
      setMessage("Backup restored to a clean destination. It has not been activated.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : String(error));
    } finally {
      setBusy(false);
    }
  }

  async function activateRestore(destination: string): Promise<void> {
    if (!destination.trim() || !window.workbench?.activateRestore) return;
    setBusy(true);
    setMessage("");
    try {
      await window.workbench.activateRestore(destination.trim());
      setMessage("Restore activation started. The app will restart and reload the restored workspace.");
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

      <nav className="settings-categories" aria-label="Settings categories">{["Appearance", "Notifications", "Defaults", "Connections", "Permissions", "Backup"].map(item => <button type="button" key={item} aria-current={category === item ? "page" : undefined} onClick={() => setCategory(item)}>{item}</button>)}</nav>

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
        <SettingSection title="Saved permissions" description="Each approval is limited to its recorded action, arguments and project. Revoke one to be asked again." actions={<span className="badge">{grants.length || "None"}</span>}>
          {grants.length === 0 ? (
            <p className="hint">No saved approvals. Tools will ask when permission is needed.</p>
          ) : grants.map((grant) => (
            <SettingRow key={grant.id} inline label={grantLabel(grant)} provenance={<>{argumentSummary(grant.arguments)}{grant.project_path ? <> · Project: {grant.project_path}</> : null}</>}>
              <button type="button" disabled={busy} onClick={() => void revoke(grant.id)}>
                <Icon name="close" size={14} /> Revoke
              </button>
            </SettingRow>
          ))}
        </SettingSection>
      </div>

      <div className="settings-category-content" hidden={category !== "Backup"}>
        <SettingSection title="Create a backup" description="App records, compatible checkpoints and retained files. Models, runtimes, project files and credentials stay where they are.">
          <SettingRow stacked label="Destination folder" htmlFor="backup-destination" hint={lastBackup ? `Created ${lastBackup.archive_path}. Credentials excluded; effects will not be replayed on restore.` : undefined}>
            <div className="path-field">
              <input id="backup-destination" value={backupDestination} onChange={(event) => setBackupDestination(event.target.value)} placeholder="Choose a folder for the backup archive" />
              <button type="button" onClick={() => void chooseFolder(setBackupDestination)} disabled={!window.workbench?.selectPath}>
                <Icon name="folder" size={14} /> Choose folder
              </button>
            </div>
          </SettingRow>
          <div className="setting-actions">
            <button type="button" className="primary-button" disabled={busy || !backupDestination.trim()} onClick={() => void createBackup()}>
              <Icon name="download" size={14} /> Create backup
            </button>
          </div>
        </SettingSection>

        <SettingSection title="Restore a backup" description="Restores into an empty folder. Activation restarts the app; previous actions are never replayed." actions={<HoverHelp title="Restore dependencies">Missing models, runtimes and external files are reported before activation.</HoverHelp>}>
          {activeRunIds.length ? (
            <p className="notice notice-warn">{activeRunIds.length} active run{activeRunIds.length === 1 ? "" : "s"} detected. Restore is safest after work is stopped or complete.</p>
          ) : null}
          <SettingRow stacked label="Backup archive" htmlFor="restore-archive">
            <div className="path-field">
              <input id="restore-archive" value={restoreArchive} onChange={(event) => setRestoreArchive(event.target.value)} placeholder="Choose a backup archive" />
              <button type="button" onClick={() => void chooseFile(setRestoreArchive)} disabled={!window.workbench?.selectPath}>
                <Icon name="files" size={14} /> Choose archive
              </button>
            </div>
          </SettingRow>
          <SettingRow stacked label="Clean destination folder" htmlFor="restore-destination">
            <div className="path-field">
              <input id="restore-destination" value={restoreDestination} onChange={(event) => setRestoreDestination(event.target.value)} placeholder="Choose an empty folder" />
              <button type="button" onClick={() => void chooseFolder(setRestoreDestination)} disabled={!window.workbench?.selectPath}>
                <Icon name="folder" size={14} /> Choose destination
              </button>
            </div>
          </SettingRow>
          <div className="setting-actions">
            <button type="button" className="primary-button" disabled={busy || !restoreArchive.trim() || !restoreDestination.trim()} onClick={() => void restoreBackup()}>
              <Icon name="restore" size={14} /> Restore backup
            </button>
          </div>
          {lastRestore ? (
            <div className="notice">
              <p>Restored to {lastRestore.destination_root}. Not yet active; no actions replayed.</p>
              {lastRestore.missing_dependencies.length ? (
                <ul>
                  {lastRestore.missing_dependencies.map((item, index) => (
                    <li key={`${item.kind}-${item.path ?? item.id ?? index}`}>{item.kind}: {item.path ?? item.id ?? "missing reference"}</li>
                  ))}
                </ul>
              ) : (
                <p>No missing external dependencies reported.</p>
              )}
              {window.workbench?.activateRestore ? (
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => void activateRestore(lastRestore.destination_root)}
                >
                  <Icon name="restore" size={14} /> Activate restore and restart
                </button>
              ) : null}
            </div>
          ) : null}
        </SettingSection>
      </div>
    </section>
  );
}
