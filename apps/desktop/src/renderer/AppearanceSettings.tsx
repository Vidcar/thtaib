import { memo, useEffect, useMemo, useState, useSyncExternalStore } from "react";

import { appearanceTokens } from "./appearanceCatalog";
import {
  appearanceActiveTheme,
  appearanceDirty,
  appearanceVersion,
  applyAppearance,
  cancelAppearance,
  currentAppearanceValue,
  resetAppearanceValue,
  setAppearanceTheme,
  subscribeAppearance,
  updateAppearanceValue,
} from "./appearanceStore";
import { shippedValue, type AppearanceGroup, type AppearanceToken } from "./appearanceValue";
import type { PresentationTheme } from "./types";
import "./appearancePanel.css";

const groups: Array<AppearanceGroup | "All"> = ["All", "Colours", "Text", "Corners", "Spacing", "Lines", "Effects"];

export function AppearanceSettings({ theme }: { theme: PresentationTheme }) {
  const version = useSyncExternalStore(subscribeAppearance, appearanceVersion, appearanceVersion);
  const [query, setQuery] = useState("");
  const [group, setGroup] = useState<(typeof groups)[number]>("All");
  const [message, setMessage] = useState("");
  const [saving, setSaving] = useState(false);
  const active = appearanceActiveTheme();
  const dirty = appearanceDirty();
  const visible = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return appearanceTokens.filter(token => {
      if (group !== "All" && token.group !== group) return false;
      if (!needle) return true;
      return `${token.name} ${token.detail} ${token.group} ${token.id}`.toLowerCase().includes(needle);
    });
  }, [group, query]);

  useEffect(() => { setAppearanceTheme(theme); }, [theme]);

  async function onApply(): Promise<void> {
    setSaving(true);
    setMessage("");
    try {
      await applyAppearance();
      setMessage("Appearance saved on this computer.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : String(error));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="appearance-editor">
      <div className="appearance-bar">
        <p className="hint">{dirty ? "Unsaved changes" : "No unsaved changes"} · editing {active} colours</p>
        <button type="button" disabled={!dirty || saving} onClick={() => { cancelAppearance(); setMessage(""); }}>Cancel</button>
        <button type="button" className="primary-button" disabled={!dirty || saving} onClick={() => void onApply()}>Apply</button>
      </div>
      {message ? <p className="hint" role="status">{message}</p> : null}
      <p className="appearance-note hint">Each row is one value used somewhere on the screen, including this page. The window follows the draft. Apply saves it in appearance.json on this computer. Cancel puts the last saved values back. Reset on a row returns that shipped value. A slider covers a wide range; the number beside it accepts any valid value, including sizes for very wide or very small windows. Layout breakpoints stay fixed, because a browser cannot take a custom value in a window-size condition.</p>
      <input className="appearance-search" type="search" value={query} placeholder="Find a setting" aria-label="Find an appearance setting" onChange={event => setQuery(event.target.value)} />
      <div className="appearance-groups" role="group" aria-label="Appearance groups">
        {groups.map(item => (
          <button key={item} type="button" aria-pressed={group === item} onClick={() => setGroup(item)}>{item}</button>
        ))}
      </div>
      <p className="hint" data-appearance-version={version}>{visible.length} shown</p>
      {visible.map(token => <AppearanceRow key={token.id} token={token} value={currentAppearanceValue(token)} />)}
    </div>
  );
}

const AppearanceRow = memo(function AppearanceRow({ token, value }: { token: AppearanceToken; value: string }) {
  const shipped = shippedValue(token, token.theme === "split" ? appearanceActiveTheme() : "dark");
  return (
    <div className="appearance-row">
      <div className="appearance-row-name">
        <strong>{token.name}</strong>
        <span className="hint">{token.group}. Shipped {shipped}. {token.detail}</span>
        <button type="button" className="appearance-reset" hidden={value === shipped} onClick={() => resetAppearanceValue(token.id)}>Reset</button>
      </div>
      <div className="appearance-controls">
        <AppearanceControl token={token} value={value} />
      </div>
      <div className="appearance-sample" style={sampleStyle(token, value)}>{sampleText(token)}</div>
    </div>
  );
});

function AppearanceControl({ token, value }: { token: AppearanceToken; value: string }) {
  if (token.kind === "color") return <ColorControl token={token} value={value} />;
  if (token.kind === "shadow") return <ShadowControl value={value} onChange={next => updateAppearanceValue(token.id, next)} />;
  if (token.kind === "family") return <FamilyControl token={token} value={value} />;
  return <NumberControl token={token} value={value} />;
}

function FamilyControl({ token, value }: { token: AppearanceToken; value: string }) {
  const [text, setText] = useState(value);
  useEffect(() => { setText(value); }, [value]);
  return <input type="text" aria-label={token.name} value={text} onChange={event => { setText(event.target.value); updateAppearanceValue(token.id, event.target.value); }} />;
}

function NumberControl({ token, value }: { token: AppearanceToken; value: string }) {
  const numeric = Number(value.slice(0, value.length - token.unit.length));
  const shippedNumber = Number(shippedValue(token, "dark").slice(0, shippedValue(token, "dark").length - token.unit.length));
  const [text, setText] = useState(() => String(numeric));
  useEffect(() => { setText(String(numeric)); }, [value, numeric]);
  const min = token.allowNegative ? Math.min(token.min ?? numeric, -64) : (token.min ?? 0);
  const span = token.max ?? (token.property === "font-size" ? 96 : token.unit === "%" ? 100 : token.property.includes("width") || token.property.includes("height") ? 8192 : 256);
  const max = Math.max(span, Number.isFinite(numeric) ? numeric : 0, Number.isFinite(shippedNumber) ? shippedNumber : 0);
  const slider = Math.min(max, Math.max(min, Number.isFinite(numeric) ? numeric : min));
  return (
    <>
      <input type="range" aria-label={`${token.name} slider`} min={min} max={max} step="any" value={slider} onChange={event => commitNumber(token, event.target.value)} />
      <input type="number" aria-label={token.name} min={token.allowNegative ? undefined : min} max={token.max ?? undefined} step="any" value={text} onChange={event => { setText(event.target.value); commitNumber(token, event.target.value); }} />
      {token.unit ? <span className="hint">{token.unit}</span> : null}
    </>
  );
}

function commitNumber(token: AppearanceToken, raw: string): void {
  if (raw.trim() === "" || raw === "-" || raw === "." || raw === "-.") return;
  const numeric = Number(raw);
  if (!Number.isFinite(numeric)) return;
  updateAppearanceValue(token.id, `${numeric}${token.unit}`);
}

function ColorControl({ token, value }: { token: AppearanceToken; value: string }) {
  const { rgb, alpha } = splitColor(value);
  const [hex, setHex] = useState(value);
  useEffect(() => { setHex(value); }, [value]);
  return (
    <>
      <input type="color" aria-label={token.name} value={rgb} onChange={event => updateAppearanceValue(token.id, composeColor(event.target.value, alpha))} />
      <input type="text" aria-label={`${token.name} hex`} value={hex} spellCheck={false} onChange={event => { setHex(event.target.value); updateAppearanceValue(token.id, event.target.value.trim()); }} />
      <input type="range" aria-label={`${token.name} transparency`} min={0} max={100} step="any" value={alpha} onChange={event => updateAppearanceValue(token.id, composeColor(rgb, Number(event.target.value)))} />
      <input type="number" aria-label={`${token.name} transparency percent`} min={0} max={100} step="any" value={alpha} onChange={event => commitAlpha(token.id, rgb, event.target.value)} />
    </>
  );
}

function commitAlpha(id: string, rgb: string, raw: string): void {
  const alpha = Number(raw);
  if (!Number.isFinite(alpha)) return;
  updateAppearanceValue(id, composeColor(rgb, alpha));
}

function ShadowControl({ value, onChange }: { value: string; onChange: (value: string) => void }) {
  const parsed = parseShadow(value);
  if (!parsed) {
    return <input type="text" aria-label="Shadow" value={value} onChange={event => onChange(event.target.value)} />;
  }
  function write(part: Partial<typeof parsed>): void {
    if (!parsed) return;
    const next = { ...parsed, ...part };
    const spread = next.spread == null ? "" : ` ${next.spread}px`;
    onChange(`${next.x}px ${next.y}px ${next.blur}px${spread} ${next.color}`);
  }
  return (
    <>
      <NumberBits label="Shadow offset x" value={parsed.x} onChange={x => write({ x })} />
      <NumberBits label="Shadow offset y" value={parsed.y} onChange={y => write({ y })} />
      <NumberBits label="Shadow blur" value={parsed.blur} onChange={blur => write({ blur })} />
      <ColorBits label="Shadow colour" value={parsed.color} onChange={color => write({ color })} />
    </>
  );
}

function NumberBits({ label, value, onChange }: { label: string; value: number; onChange: (value: number) => void }) {
  const max = Math.max(256, Math.abs(value));
  return (
    <>
      <input type="range" aria-label={`${label} slider`} min={-max} max={max} step="any" value={value} onChange={event => onChange(Number(event.target.value))} />
      <input type="number" aria-label={label} step="any" value={value} onChange={event => { const next = Number(event.target.value); if (Number.isFinite(next)) onChange(next); }} />
    </>
  );
}

function ColorBits({ label, value, onChange }: { label: string; value: string; onChange: (value: string) => void }) {
  const { rgb, alpha } = splitColor(value);
  return (
    <>
      <input type="color" aria-label={label} value={rgb} onChange={event => onChange(composeColor(event.target.value, alpha))} />
      <input type="range" aria-label={`${label} transparency`} min={0} max={100} step="any" value={alpha} onChange={event => onChange(composeColor(rgb, Number(event.target.value)))} />
    </>
  );
}

function splitColor(value: string): { rgb: string; alpha: number } {
  const body = value.startsWith("#") ? value.slice(1) : "";
  const expanded = body.length === 3 || body.length === 4 ? [...body].map(char => char + char).join("") : body;
  const rgb = `#${(expanded.slice(0, 6) || "000000").padEnd(6, "0")}`.slice(0, 7);
  const alpha = expanded.length >= 8 ? Math.round(Number.parseInt(expanded.slice(6, 8), 16) / 255 * 1000) / 10 : 100;
  return { rgb, alpha: Number.isFinite(alpha) ? alpha : 100 };
}

function composeColor(rgb: string, alpha: number): string {
  const clamped = Math.min(100, Math.max(0, alpha));
  if (clamped >= 99.9) return rgb.toLowerCase();
  const channel = Math.round(clamped / 100 * 255).toString(16).padStart(2, "0");
  return `${rgb.toLowerCase()}${channel}`;
}

function parseShadow(value: string): { x: number; y: number; blur: number; spread: number | null; color: string } | null {
  const match = /^(-?(?:\d+\.?\d*|\.\d+))(?:px)?\s+(-?(?:\d+\.?\d*|\.\d+))px\s+(-?(?:\d+\.?\d*|\.\d+))px(?:\s+(-?(?:\d+\.?\d*|\.\d+))px)?\s+(#[0-9a-fA-F]{3,8})$/.exec(value.trim());
  if (!match) return null;
  return { x: Number(match[1]), y: Number(match[2]), blur: Number(match[3]), spread: match[4] == null ? null : Number(match[4]), color: match[5] };
}

function sampleStyle(token: AppearanceToken, value: string): { background?: string; color?: string; fontSize?: string; borderRadius?: string; padding?: string; opacity?: string; fontFamily?: string; boxShadow?: string } {
  if (token.kind === "color") return token.property === "color" ? { color: value, background: "var(--bg)" } : { background: value };
  if (token.kind === "family") return { fontFamily: value };
  if (token.kind === "shadow") return { boxShadow: value, background: "var(--bg-panel)" };
  if (token.property === "font-size") return { fontSize: value };
  if (token.property.includes("radius")) return { borderRadius: value, background: "var(--bg-panel)" };
  if (token.property === "opacity") return { opacity: value, background: "var(--accent)" };
  if (token.property.includes("padding") || token.property === "gap") return { padding: value, background: "var(--bg-panel)" };
  return { background: "var(--bg-panel)" };
}

function sampleText(token: AppearanceToken): string {
  if (token.property === "font-size" || token.kind === "family") return "Text";
  if (token.kind === "color" && token.property === "color") return "Text";
  return "";
}
