import { RecoverySettingsPanel } from "./RecoverySettingsPanel";
import { ConnectionsPanel } from "./ConnectionsPanel";
import { ApplicationDefaultsPanel } from "./ApplicationDefaultsPanel";
import { WorkerSettings } from "./WorkerSettings";
import { ModelEngineSettings } from "./ModelEngineSettings";
import { ModelStoragePanel } from "./ModelStoragePanel";
import type { PresentationSettings } from "./types";

interface SettingsPanelProps {
  onPreferencesChanged?: (preferences: PresentationSettings) => void;
}

export function SettingsPanel({ onPreferencesChanged }: SettingsPanelProps) {
  return <RecoverySettingsPanel onPreferencesChanged={onPreferencesChanged} defaultsPanel={<ApplicationDefaultsPanel />} connectionsPanel={<><ModelEngineSettings /><ModelStoragePanel /><WorkerSettings /><ConnectionsPanel /></>} />;
}
