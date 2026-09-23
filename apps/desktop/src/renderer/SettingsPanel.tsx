import { RecoverySettingsPanel } from "./RecoverySettingsPanel";
import { ConnectionsPanel } from "./ConnectionsPanel";
import { ApplicationDefaultsPanel } from "./ApplicationDefaultsPanel";
import type { PresentationSettings } from "./types";

interface SettingsPanelProps {
  onPreferencesChanged?: (preferences: PresentationSettings) => void;
}

export function SettingsPanel({ onPreferencesChanged }: SettingsPanelProps) {
  return <RecoverySettingsPanel onPreferencesChanged={onPreferencesChanged} defaultsPanel={<ApplicationDefaultsPanel />} connectionsPanel={<ConnectionsPanel />} />;
}
