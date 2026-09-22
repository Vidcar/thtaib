import { useEffect, useRef, useState } from "react";

import {
  packet03Api,
  type BackupCreateResult,
  type BackupRestoreResult,
  type PermissionGrant,
} from "./packet03Api";
import type { PresentationSettings, PresentationTheme } from "./types";
import { HoverHelp } from "./HoverHelp";
import { Icon } from "./Icon";
import "./packet03Panels.css";

interface RecoverySettingsPanelProps {
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

export function RecoverySettingsPanel({ onPreferencesChanged, onRestoreCompleted }: RecoverySettingsPanelProps) {
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
    const selected = await window.workbench?.selectPath?.("folder");
    if (selected) setter(selected);
  }

  async function chooseFile(setter: (path: string) => void): Promise<void> {
    const selected = await window.workbench?.selectPath?.("file");
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
    <section className="packet03-panel" aria-label="Recovery and settings">
      <div className="packet03-row">
        <h2>Settings</h2>
        <button type="button" disabled={busy || preferencesBusy} onClick={() => void refresh()}>
          <Icon name="refresh" size={14} /> Refresh
        </button>
      </div>

      {message ? <p role="status" className="notice">{message}</p> : null}

      <div className="packet03-grid">
        <section className="packet03-item">
          <h3>Appearance</h3>
          <label>
            Theme
            <select
              value={preferences.theme}
              disabled={preferenceControlsDisabled}
              onChange={(event) => void savePreferences({ theme: event.target.value as PresentationTheme })}
            >
              <option value="system">System</option>
              <option value="light">Light</option>
              <option value="dark">Dark</option>
            </select>
          </label>
          <label className="check-row">
            <input
              type="checkbox"
              checked={preferences.detailed_streams}
              disabled={preferenceControlsDisabled}
              onChange={(event) => void savePreferences({ detailed_streams: event.target.checked })}
            />
            Expand reasoning and tool details
          </label>
          <h4>Notifications</h4>
          <label className="check-row">
            <input
              type="checkbox"
              checked={preferences.attention_notifications}
              disabled={preferenceControlsDisabled}
              onChange={(event) => void savePreferences({ attention_notifications: event.target.checked })}
            />
            Approvals, questions and failures
          </label>
          <label className="check-row">
            <input
              type="checkbox"
              checked={preferences.success_notifications}
              disabled={preferenceControlsDisabled}
              onChange={(event) => void savePreferences({ success_notifications: event.target.checked })}
            />
            Completed work
          </label>
        </section>

        <section className="packet03-item">
          <div className="entity-head"><h3>Permissions</h3><HoverHelp title="About saved permissions">Saved approvals are limited to their recorded action, arguments and project. Revoke one to require approval again.</HoverHelp></div>
          {grants.length === 0 ? (
            <p className="hint">No saved grants.</p>
          ) : (
            <ul className="packet03-list">
              {grants.map((grant) => (
                <li key={grant.id} className="packet03-item">
                  <strong>{grantLabel(grant)}</strong>
                  <p className="hint">{argumentSummary(grant.arguments)}</p>
                  {grant.project_path ? <p className="hint">Project: {grant.project_path}</p> : null}
                  <button type="button" disabled={busy} onClick={() => void revoke(grant.id)}>
                    <Icon name="close" size={14} /> Revoke
                  </button>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>

      <details className="packet03-item">
        <summary><Icon name="download" size={15} /> Backup</summary>
        <div className="entity-head"><h3>Create a backup</h3><HoverHelp title="What a backup includes">Includes app records, compatible checkpoints and retained files. Models, runtimes, project files and credentials stay in their existing locations.</HoverHelp></div>
        <label>
          Destination folder
          <input value={backupDestination} onChange={(event) => setBackupDestination(event.target.value)} placeholder="Choose a folder for the backup archive" />
        </label>
        <div className="packet03-actions">
          <button type="button" onClick={() => void chooseFolder(setBackupDestination)} disabled={!window.workbench?.selectPath}>
            <Icon name="folder" size={14} /> Choose folder
          </button>
          <button type="button" disabled={busy || !backupDestination.trim()} onClick={() => void createBackup()}>
            <Icon name="download" size={14} /> Create backup
          </button>
        </div>
        {lastBackup ? (
          <p className="hint">Created {lastBackup.archive_path}. Credentials excluded; effects will not be replayed on restore.</p>
        ) : null}
      </details>

      <details className="packet03-item">
        <summary><Icon name="restore" size={15} /> Restore</summary>
        <div className="entity-head"><h3>Restore a backup</h3><HoverHelp title="How restore works">Restores into an empty folder and reports missing models, runtimes or other external files. Switch to it using Activate restore when you're ready.</HoverHelp></div>
        <p className="hint">Restores to an empty folder. Activation restarts the app; previous actions are never replayed.</p>
        {activeRunIds.length ? (
          <p className="notice notice-warn">{activeRunIds.length} active run{activeRunIds.length === 1 ? "" : "s"} detected. Restore is safest after work is stopped or complete.</p>
        ) : null}
        <label>
          Backup archive
          <input value={restoreArchive} onChange={(event) => setRestoreArchive(event.target.value)} placeholder="Choose a backup archive" />
        </label>
        <label>
          Clean destination folder
          <input value={restoreDestination} onChange={(event) => setRestoreDestination(event.target.value)} placeholder="Choose an empty folder" />
        </label>
        <div className="packet03-actions">
          <button type="button" onClick={() => void chooseFile(setRestoreArchive)} disabled={!window.workbench?.selectPath}>
            <Icon name="files" size={14} /> Choose archive
          </button>
          <button type="button" onClick={() => void chooseFolder(setRestoreDestination)} disabled={!window.workbench?.selectPath}>
            <Icon name="folder" size={14} /> Choose destination
          </button>
          <button type="button" disabled={busy || !restoreArchive.trim() || !restoreDestination.trim()} onClick={() => void restoreBackup()}>
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
      </details>
    </section>
  );
}
