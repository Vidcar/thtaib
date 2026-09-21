import { useEffect, useState } from "react";

import {
  packet03Api,
  type BackupCreateResult,
  type BackupRestoreResult,
  type PermissionGrant,
} from "./packet03Api";
import type { PresentationSettings, PresentationTheme } from "./types";
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
  const [grants, setGrants] = useState<PermissionGrant[]>([]);
  const [activeRunIds, setActiveRunIds] = useState<string[]>([]);
  const [backupDestination, setBackupDestination] = useState("");
  const [restoreArchive, setRestoreArchive] = useState("");
  const [restoreDestination, setRestoreDestination] = useState("");
  const [lastBackup, setLastBackup] = useState<BackupCreateResult | null>(null);
  const [lastRestore, setLastRestore] = useState<BackupRestoreResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");

  async function refresh(): Promise<void> {
    setBusy(true);
    setMessage("");
    try {
      const [nextPreferences, nextGrants, work] = await Promise.all([
        packet03Api.presentation(),
        packet03Api.grants(),
        packet03Api.activeWork(),
      ]);
      setPreferences(nextPreferences);
      setGrants(nextGrants);
      setActiveRunIds(work.active_run_ids);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : String(error));
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    void refresh();
  }, []);

  async function savePreferences(next: PresentationSettings): Promise<void> {
    setPreferences(next);
    setMessage("");
    try {
      const saved = await packet03Api.savePresentation(next);
      setPreferences(saved);
      onPreferencesChanged?.(saved);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : String(error));
      void refresh();
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
      const result = await packet03Api.createBackup(backupDestination.trim());
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

  return (
    <section className="packet03-panel" aria-label="Recovery and settings">
      <div className="packet03-row">
        <div>
          <p className="eyebrow">Settings</p>
          <h2>Recovery and permissions</h2>
        </div>
        <button type="button" disabled={busy} onClick={() => void refresh()}>
          Refresh
        </button>
      </div>

      {message ? <p role="status" className="notice">{message}</p> : null}

      <div className="packet03-grid">
        <section className="packet03-item">
          <h3>Appearance and notifications</h3>
          <label>
            Theme
            <select
              value={preferences.theme}
              onChange={(event) => void savePreferences({ ...preferences, theme: event.target.value as PresentationTheme })}
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
              onChange={(event) => void savePreferences({ ...preferences, detailed_streams: event.target.checked })}
            />
            Show detailed streams by default
          </label>
          <label className="check-row">
            <input
              type="checkbox"
              checked={preferences.attention_notifications}
              onChange={(event) => void savePreferences({ ...preferences, attention_notifications: event.target.checked })}
            />
            Notify for approvals, questions and failures
          </label>
          <label className="check-row">
            <input
              type="checkbox"
              checked={preferences.success_notifications}
              onChange={(event) => void savePreferences({ ...preferences, success_notifications: event.target.checked })}
            />
            Notify when work succeeds
          </label>
        </section>

        <section className="packet03-item">
          <h3>Saved permission grants</h3>
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
                    Revoke
                  </button>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>

      <section className="packet03-item">
        <h3>Manual backup</h3>
        <p className="hint">Backups include application records, compatible checkpoints and retained assets. Models, runtimes, projects and credentials remain external references.</p>
        <label>
          Destination folder
          <input value={backupDestination} onChange={(event) => setBackupDestination(event.target.value)} placeholder="Choose a folder for the backup archive" />
        </label>
        <div className="packet03-actions">
          <button type="button" onClick={() => void chooseFolder(setBackupDestination)} disabled={!window.workbench?.selectPath}>
            Choose folder
          </button>
          <button type="button" disabled={busy || !backupDestination.trim()} onClick={() => void createBackup()}>
            Create backup
          </button>
        </div>
        {lastBackup ? (
          <p className="hint">Created {lastBackup.archive_path}. Credentials excluded; effects will not be replayed on restore.</p>
        ) : null}
      </section>

      <section className="packet03-item">
        <h3>Restore to clean destination</h3>
        <p className="hint">Restore writes to a clean root and reports missing external dependencies. It does not activate the restored workspace or replay effects.</p>
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
            Choose archive
          </button>
          <button type="button" onClick={() => void chooseFolder(setRestoreDestination)} disabled={!window.workbench?.selectPath}>
            Choose destination
          </button>
          <button type="button" disabled={busy || !restoreArchive.trim() || !restoreDestination.trim()} onClick={() => void restoreBackup()}>
            Restore backup
          </button>
        </div>
        {lastRestore ? (
          <div className="notice">
            <p>Restored to {lastRestore.destination_root}. Activated: no.</p>
            <p>Effect replay: no.</p>
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
                Activate restore and restart
              </button>
            ) : null}
          </div>
        ) : null}
      </section>
    </section>
  );
}
