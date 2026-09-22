import { RecoverySettingsPanel } from "./RecoverySettingsPanel";
import type { PresentationSettings } from "./types";

interface SettingsPanelProps {
  onPreferencesChanged?: (preferences: PresentationSettings) => void;
}

export function SettingsPanel({ onPreferencesChanged }: SettingsPanelProps) {
  return <RecoverySettingsPanel onPreferencesChanged={onPreferencesChanged} />;
}
