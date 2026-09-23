import { appearanceTokens } from "./appearanceCatalog";
import type { AppearanceToken } from "./appearanceValue";

export interface AppearancePreviewState {
  theme: "" | "light" | "dark";
  activeId: string;
  activeName: string;
  activeDetail: string;
  overrides: Record<string, string>;
}

let aimed: Pick<AppearanceToken, "id" | "name" | "detail"> | null = null;

export function setAppearancePreviewAim(token: AppearanceToken): void {
  if (aimed?.id === token.id) return;
  aimed = { id: token.id, name: token.name, detail: token.detail };
  syncAppearancePreview();
}

export function syncAppearancePreview(): void {
  const publish = window.workbench?.publishAppearancePreview;
  if (!publish || typeof document === "undefined") return;
  const root = document.documentElement;
  const theme = root.dataset.theme === "light" || root.dataset.theme === "dark" ? root.dataset.theme : "";
  const overrides: Record<string, string> = {};
  for (const token of appearanceTokens) {
    const value = root.style.getPropertyValue(token.cssVar).trim();
    if (value) overrides[token.cssVar] = value;
  }
  void publish({
    theme,
    activeId: aimed?.id ?? "",
    activeName: aimed?.name ?? "",
    activeDetail: aimed?.detail ?? "",
    overrides,
  });
}

const applied = new Set<string>();

export function applyAppearancePreviewState(state: AppearancePreviewState): void {
  const root = document.documentElement;
  if (state.theme) root.dataset.theme = state.theme;
  else delete root.dataset.theme;
  for (const name of applied) {
    if (!(name in state.overrides)) root.style.removeProperty(name);
  }
  applied.clear();
  for (const [name, value] of Object.entries(state.overrides)) {
    root.style.setProperty(name, value);
    applied.add(name);
  }
}
