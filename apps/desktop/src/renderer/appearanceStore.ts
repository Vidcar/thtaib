import { appearanceTokens } from "./appearanceCatalog";
import {
  appearanceValueValid,
  emptyAppearance,
  readAppearanceFile,
  resolvedAppearanceValue,
  shippedValue,
  type AppearanceFile,
  type AppearanceToken,
} from "./appearanceValue";
import { syncAppearancePreview } from "./appearancePreviewSync";
import { syncMonacoFromDocument } from "./monacoSetup";
import type { PresentationTheme } from "./types";

const STORAGE_KEY = "workbench.appearance";
const tokensById = new Map(appearanceTokens.map(token => [token.id, token]));
const listeners = new Set<() => void>();

let saved = emptyAppearance();
let draft = emptyAppearance();
let activeTheme: "light" | "dark" = "dark";
let editGeneration = 0;
let version = 0;
let media: MediaQueryList | null = null;

export function appearanceToken(id: string): AppearanceToken | undefined {
  return tokensById.get(id);
}

export function appearanceDraft(): AppearanceFile {
  return draft;
}

export function appearanceSaved(): AppearanceFile {
  return saved;
}

export function appearanceDirty(): boolean {
  return JSON.stringify(draft) !== JSON.stringify(saved);
}

export function appearanceActiveTheme(): "light" | "dark" {
  return activeTheme;
}

export function appearanceVersion(): number {
  return version;
}

export function subscribeAppearance(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function currentAppearanceValue(token: AppearanceToken): string {
  return resolvedAppearanceValue(token, draft, activeTheme);
}

export function updateAppearanceValue(id: string, value: string): void {
  const token = tokensById.get(id);
  if (!token || !appearanceValueValid(token, value)) return;
  editGeneration += 1;
  const theme = token.theme === "split" ? activeTheme : "dark";
  const target = theme === "light" ? draft.light : draft.values;
  if (value === shippedValue(token, theme)) delete target[id];
  else target[id] = value;
  publish();
}

export function resetAppearanceValue(id: string): void {
  const token = tokensById.get(id);
  if (!token) return;
  editGeneration += 1;
  if (token.theme === "split" && activeTheme === "light") delete draft.light[id];
  else delete draft.values[id];
  publish();
}

export function cancelAppearance(): void {
  editGeneration += 1;
  draft = structuredClone(saved);
  publish();
}

export async function applyAppearance(): Promise<void> {
  const next = structuredClone(draft);
  editGeneration += 1;
  const generation = editGeneration;
  await persistAppearance(next);
  if (generation !== editGeneration) return;
  saved = next;
  draft = structuredClone(saved);
  publish();
}

export async function loadAppearance(): Promise<void> {
  const generation = editGeneration;
  const raw = await readStoredAppearance();
  if (generation !== editGeneration) return;
  saved = readAppearanceFile(raw, appearanceTokens);
  draft = structuredClone(saved);
  publish();
}

export function setAppearanceTheme(preference: PresentationTheme): void {
  activeTheme = resolveTheme(preference);
  watchSystemTheme(preference === "system");
  publish();
}

function resolveTheme(preference: PresentationTheme): "light" | "dark" {
  if (preference === "light" || preference === "dark") return preference;
  return window.matchMedia?.("(prefers-color-scheme: light)")?.matches ? "light" : "dark";
}

function watchSystemTheme(system: boolean): void {
  if (!system || !window.matchMedia) {
    media?.removeEventListener("change", onSystemTheme);
    media = null;
    return;
  }
  const next = window.matchMedia("(prefers-color-scheme: light)");
  if (media === next) return;
  media?.removeEventListener("change", onSystemTheme);
  media = next;
  media.addEventListener("change", onSystemTheme);
}

function onSystemTheme(): void {
  activeTheme = media?.matches ? "light" : "dark";
  publish();
}

function publish(): void {
  version += 1;
  applyAppearanceToDocument(draft, activeTheme);
  syncMonacoFromDocument();
  syncAppearancePreview();
  for (const listener of listeners) listener();
}

function applyAppearanceToDocument(file: AppearanceFile, theme: "light" | "dark"): void {
  if (typeof document === "undefined") return;
  const root = document.documentElement;
  for (const token of appearanceTokens) {
    const value = resolvedAppearanceValue(token, file, theme);
    if (value === shippedValue(token, token.theme === "split" ? theme : "dark")) root.style.removeProperty(token.cssVar);
    else root.style.setProperty(token.cssVar, value);
  }
}

async function readStoredAppearance(): Promise<unknown> {
  try {
    if (window.workbench?.readAppearance) return await window.workbench.readAppearance();
    const stored = window.localStorage?.getItem(STORAGE_KEY);
    return stored ? JSON.parse(stored) as unknown : null;
  } catch {
    return null;
  }
}

async function persistAppearance(file: AppearanceFile): Promise<void> {
  if (window.workbench?.writeAppearance) {
    await window.workbench.writeAppearance(file);
    return;
  }
  window.localStorage?.setItem(STORAGE_KEY, JSON.stringify(file));
}
