export type AppearanceGroup = "Colours" | "Text" | "Corners" | "Spacing" | "Layout" | "Lines" | "Effects";

export type AppearanceKind = "length" | "number" | "color" | "family" | "shadow";

export interface AppearanceToken {
  id: string;
  cssVar: string;
  group: AppearanceGroup;
  name: string;
  detail: string;
  kind: AppearanceKind;
  unit: string;
  shipped: string;
  shippedLight: string | null;
  property: string;
  allowNegative: boolean;
  theme?: "all" | "split";
  min?: number | null;
  max?: number | null;
}

export interface AppearanceFile {
  version: 1;
  values: Record<string, string>;
  light: Record<string, string>;
}

export function shippedValue(token: AppearanceToken, theme: "light" | "dark"): string {
  if (token.theme === "split" && theme === "light" && token.shippedLight) return token.shippedLight;
  return token.shipped;
}

export function appearanceValueValid(token: AppearanceToken, value: string): boolean {
  if (token.kind === "family") return familyValid(value);
  if (token.kind === "shadow") return shadowValid(value);
  if (token.kind === "color") return colorValid(value);
  return numberValid(token, value);
}

export function colorValid(value: string): boolean {
  return /^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{4}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$/.test(value);
}

export function familyValid(value: string): boolean {
  return value.trim().length > 0 && value.length <= 300 && !/[;{}<>]/.test(value);
}

export function shadowValid(value: string): boolean {
  return value.trim().length > 0 && value.length <= 400 && !/[;{}<>]/.test(value);
}

export function numberValid(token: AppearanceToken, value: string): boolean {
  const match = /^([+-]?(?:\d+\.?\d*|\.\d+))([a-z%]*)$/i.exec(value.trim());
  if (!match || match[2] !== token.unit) return false;
  const number = Number(match[1]);
  if (!Number.isFinite(number)) return false;
  if (!token.allowNegative && number < 0) return false;
  if (token.min != null && number < token.min) return false;
  if (token.max != null && number > token.max) return false;
  return true;
}

export function emptyAppearance(): AppearanceFile {
  return { version: 1, values: {}, light: {} };
}

export function readAppearanceFile(raw: unknown, tokens: AppearanceToken[]): AppearanceFile {
  const file = emptyAppearance();
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) return file;
  const record = raw as Record<string, unknown>;
  const values = record.values;
  const light = record.light;
  if (values && typeof values === "object" && !Array.isArray(values)) copyValid(file.values, values as Record<string, unknown>, tokens, "dark");
  if (light && typeof light === "object" && !Array.isArray(light)) copyValid(file.light, light as Record<string, unknown>, tokens, "light");
  return file;
}

const retiredAppearance: Record<string, string> = {
  "space-hairline": "space-tight",
  "space-row": "space-compact",
  "pad-hairline": "pad-tight",
  "pad-row": "pad-compact",
  "text-micro": "text-small",
  "text-caption": "text-small",
  "text-compact": "text-body",
  "text-subhead": "text-heading",
  "leading-relaxed": "leading-body",
  "radius-small": "radius-control",
  "icon-sm": "icon-md",
};

function copyValid(target: Record<string, string>, source: Record<string, unknown>, tokens: AppearanceToken[], theme: "light" | "dark"): void {
  const retired: Array<[string, string]> = [];
  for (const [id, value] of Object.entries(source)) {
    if (typeof value !== "string") continue;
    const successor = retiredAppearance[id];
    if (successor) retired.push([successor, value]);
    else acceptAppearanceValue(target, tokens, theme, id, value);
  }
  for (const [id, value] of retired) {
    if (target[id]) continue;
    acceptAppearanceValue(target, tokens, theme, id, value);
  }
}

function acceptAppearanceValue(target: Record<string, string>, tokens: AppearanceToken[], theme: "light" | "dark", id: string, value: string): void {
  const token = tokens.find(item => item.id === id);
  if (!token) return;
  if (token.theme === "split" && theme === "dark" && !appearanceValueValid(token, value)) return;
  if (token.theme !== "split" && theme === "light") return;
  if (!appearanceValueValid(token, value)) return;
  if (value === shippedValue(token, theme)) return;
  target[id] = value;
}

export function resolvedAppearanceValue(token: AppearanceToken, file: AppearanceFile, theme: "light" | "dark"): string {
  if (token.theme === "split" && theme === "light") return file.light[token.id] ?? shippedValue(token, "light");
  return file.values[token.id] ?? shippedValue(token, theme);
}
