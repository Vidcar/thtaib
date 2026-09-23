import { memo, useEffect, useMemo, useState, useSyncExternalStore } from "react";

import { appearanceTokens } from "./appearanceCatalog";
import { setAppearancePreviewAim, syncAppearancePreview } from "./appearancePreviewSync";
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
import { HoverHelp } from "./HoverHelp";
import { CompactSlider } from "./CompactControls";
import "./appearancePanel.css";

const groups: Array<AppearanceGroup | "All"> = ["All", "Colours", "Text", "Corners", "Spacing", "Layout", "Lines", "Effects"];

export function AppearanceSettings({ theme }: { theme: PresentationTheme }) {
  const version = useSyncExternalStore(subscribeAppearance, appearanceVersion, appearanceVersion);
  const [query, setQuery] = useState("");
  const [group, setGroup] = useState<(typeof groups)[number]>("All");
  const [message, setMessage] = useState("");
  const [saving, setSaving] = useState(false);
  const [customize, setCustomize] = useState(false);
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
        <button type="button" onClick={() => void window.workbench?.openAppearancePreview?.().then(() => syncAppearancePreview())}>Pop out preview</button>
        <button type="button" disabled={!dirty || saving} title="Restore the last saved appearance" onClick={() => { cancelAppearance(); setMessage(""); }}>Cancel</button>
        <button type="button" className="primary-button" disabled={!dirty || saving} title="Save appearance on this computer" onClick={() => void onApply()}>Apply</button>
        <HoverHelp title="Appearance changes">Changes preview immediately. Apply saves them on this computer; Cancel restores the last saved values. Reset returns an individual control to its shipped value. Open Preview to see a sample conversation.</HoverHelp>
      </div>
      {message ? <p className="hint" role="status">{message}</p> : null}
      <AppearanceBasics />
      <button type="button" className="appearance-customize" aria-expanded={customize} onClick={() => setCustomize(value => !value)}>{customize ? "Hide advanced controls" : "Customize appearance"}</button>
      {customize ? <div className="appearance-advanced">
      <input className="appearance-search" type="search" value={query} placeholder="Find a setting" aria-label="Find an appearance setting" onChange={event => setQuery(event.target.value)} />
      <div className="appearance-groups" role="group" aria-label="Appearance groups">
        {groups.map(item => (
          <button key={item} type="button" aria-pressed={group === item} onClick={() => setGroup(item)}>{item}</button>
        ))}
      </div>
      <p className="hint" data-appearance-version={version}>{visible.length} shown</p>
      {visible.map(token => <AppearanceRow key={token.id} token={token} value={currentAppearanceValue(token)} />)}
      </div> : null}
    </div>
  );
}

function AppearanceBasics() {
  const token = (id: string) => appearanceTokens.find(item => item.id === id)!;
  const current = (id: string) => currentAppearanceValue(token(id));
  const font = current("font-ui");
  const fonts = [{ label: "System", value: token("font-ui").shipped }, { label: "Arial", value: "Arial, sans-serif" }, { label: "Verdana", value: "Verdana, sans-serif" }];
  const densities: Record<string, Record<string, string>> = { Compact: { "pad-compact": "8px", "space-compact": "8px", "control-height": "30px" }, Comfortable: { "pad-compact": "12px", "space-compact": "12px", "control-height": "36px" } };
  const density = Object.entries(densities).find(([, values]) => Object.entries(values).every(([id, value]) => current(id) === value))?.[0] ?? "Custom";
  return <div className="appearance-basics"><label>Font<select aria-label="Interface font choice" value={font} onChange={event => updateAppearanceValue("font-ui", event.target.value)}>{!fonts.some(item => item.value === font) ? <option value={font}>Custom</option> : null}{fonts.map(item => <option key={item.value} value={item.value}>{item.label}</option>)}</select></label><CompactSlider label="Interface size" value={parseFloat(current("text-body"))} values={[11, 12, 13, 14, 15, 16, 18]} formatValue={value => `${value}px`} onChange={value => updateAppearanceValue("text-body", `${value}px`)} /><label>Density<select aria-label="Density" value={density} onChange={event => Object.entries(densities[event.target.value] ?? {}).forEach(([id, value]) => updateAppearanceValue(id, value))}>{density === "Custom" ? <option>Custom</option> : null}{Object.keys(densities).map(value => <option key={value}>{value}</option>)}</select></label></div>;
}

const AppearanceRow = memo(function AppearanceRow({ token, value }: { token: AppearanceToken; value: string }) {
  const shipped = shippedValue(token, token.theme === "split" ? appearanceActiveTheme() : "dark");
  return (
    <div className="appearance-row" onFocusCapture={() => setAppearancePreviewAim(token)} onPointerEnter={() => setAppearancePreviewAim(token)}>
      <div className="appearance-row-name">
        <strong>{token.name}<HoverHelp title={`About ${token.name.toLowerCase()}`}>{token.group}. Shipped {shipped}. {token.detail}</HoverHelp></strong>
        <button type="button" className="appearance-reset" hidden={value === shipped} onClick={() => resetAppearanceValue(token.id)}>Reset</button>
      </div>
      <div className="appearance-controls">
        <AppearanceControl token={token} value={value} />
      </div>
      <AppearanceSample token={token} value={value} />
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

function AppearanceSample({ token, value }: { token: AppearanceToken; value: string }) {
  return <div className="appearance-sample" aria-hidden="true">{sampleBody(token, value)}</div>;
}

function sampleBody(token: AppearanceToken, value: string) {
  if (token.kind === "color") {
    if (token.id === "palette-text" || token.id === "palette-muted") {
      return <span className="appearance-swatch writes" style={{ background: "var(--bg)", color: value }}>Text</span>;
    }
    if (token.id === "palette-border") {
      return <span className="appearance-swatch" style={{ background: "var(--bg-panel)", borderColor: value }} />;
    }
    return <span className="appearance-swatch" style={{ background: value }} />;
  }
  if (token.kind === "family") return <span className="appearance-type" style={{ fontFamily: value }}>Ag</span>;
  if (token.kind === "shadow") return <span className="appearance-shadow" style={{ boxShadow: value }} />;
  if (token.property === "font-size") return <span className="appearance-type" style={{ fontSize: value }}>Ag</span>;
  if (token.property === "font-weight") return <span className="appearance-type" style={{ fontWeight: value }}>Ag</span>;
  if (token.property === "line-height") {
    return <span className="appearance-type appearance-leading" style={{ lineHeight: value }}>Line<br />spacing</span>;
  }
  if (token.property === "letter-spacing") return <span className="appearance-type" style={{ letterSpacing: value }}>Wide</span>;
  if (token.property.includes("radius")) {
    return <span className="appearance-radius" style={{ borderRadius: value }} />;
  }
  if (token.id.startsWith("pad-")) {
    return <span className="appearance-pad" style={{ padding: capLength(value, 40) }}><b>Inset</b></span>;
  }
  if (token.id.startsWith("space-")) {
    return <span className="appearance-gap" style={{ gap: capLength(value, 32) }}><i /><i /></span>;
  }
  if (token.id.startsWith("icon-") && token.id !== "icon-stroke") {
    const size = Math.min(lengthAmount(value) ?? 16, 40);
    return <span className="appearance-icon" style={{ width: size, height: size }} />;
  }
  if (token.id.startsWith("control-height")) {
    return <span className="appearance-control" style={{ height: capLength(value, 48) }} />;
  }
  if (token.id.startsWith("layout-")) {
    return <span className="appearance-meter"><i style={{ width: meterWidth(value) }} /></span>;
  }
  if (token.id === "line-hairline" || token.id === "line-strong" || token.id === "line-mark" || token.id === "focus-ring" || token.id === "icon-stroke") {
    return <span className="appearance-line" style={{ borderTopWidth: token.unit === "px" ? capLength(value, 8) : "2px" }} />;
  }
  if (token.id === "focus-offset") {
    return <span className="appearance-offset" style={{ outlineOffset: capLength(value, 8) }} />;
  }
  if (token.property === "opacity" || token.id.startsWith("fade-")) {
    return <span className="appearance-fade" style={{ opacity: value }} />;
  }
  if (token.id.startsWith("tint-")) {
    return <span className="appearance-wash" style={{ background: `color-mix(in srgb, var(--accent) ${value}, var(--bg-panel))` }} />;
  }
  if (token.id === "effect-blur") {
    return <span className="appearance-blur" style={{ filter: `blur(${capLength(value, 8)})` }} />;
  }
  return <span className="appearance-swatch" style={{ background: "var(--bg-panel)" }} />;
}

function lengthAmount(value: string): number | null {
  const match = /^(-?(?:\d+\.?\d*|\.\d+))([a-z%]*)$/i.exec(value.trim());
  if (!match) return null;
  const amount = Number(match[1]);
  if (!Number.isFinite(amount)) return null;
  if (match[2] === "rem") return amount * 14;
  if (match[2] === "%") return amount;
  return amount;
}

function capLength(value: string, cap: number): string {
  const amount = lengthAmount(value);
  if (amount == null) return value;
  return `${Math.min(Math.max(amount, 0), cap)}px`;
}

function meterWidth(value: string): string {
  const match = /^(-?(?:\d+\.?\d*|\.\d+))([a-z%]*)$/i.exec(value.trim());
  const amount = match ? Number(match[1]) : 0;
  if (match?.[2] === "%") return `${Math.max(8, Math.min(100, amount))}%`;
  return `${Math.max(8, Math.min(100, (amount / 1500) * 100))}%`;
}
