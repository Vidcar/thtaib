import { memo, useEffect, useMemo, useState, useSyncExternalStore, type CSSProperties } from "react";

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
import { CompactSlider, SegmentedChoice, SettingSection } from "./CompactControls";
import { Icon } from "./Icon";
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
      <SettingSection title="Basics" description="Quick choices. Each one writes the matching settings below.">
        <AppearanceBasics />
      </SettingSection>
      <section className="setting-section appearance-studio">
        <header className="setting-section-head">
          <div><h3>All appearance settings</h3><p>Every colour, size and spacing value the Workbench uses.</p></div>
          <div className="setting-section-actions">
            <button type="button" className="quiet-button appearance-customize" aria-expanded={customize} onClick={() => setCustomize(value => !value)}>{customize ? "Hide advanced controls" : "Customize appearance"}</button>
          </div>
        </header>
        {customize ? <div className="appearance-advanced">
          <div className="appearance-filter">
            <input className="appearance-search" type="search" value={query} placeholder="Find a setting" aria-label="Find an appearance setting" onChange={event => setQuery(event.target.value)} />
            <div className="chips appearance-groups" role="group" aria-label="Appearance groups">
              {groups.map(item => <button key={item} type="button" className="chip" aria-pressed={group === item} onClick={() => setGroup(item)}>{item}</button>)}
            </div>
            <p className="appearance-count" role="status" data-appearance-version={version}>{visible.length} shown</p>
          </div>
          <div className="appearance-rows">
            {visible.map(token => <AppearanceRow key={token.id} token={token} value={currentAppearanceValue(token)} />)}
            {visible.length === 0 ? <p className="hint appearance-empty">No setting matches “{query}”.</p> : null}
          </div>
        </div> : null}
      </section>
      <div className="appearance-bar" role="group" aria-label="Appearance changes">
        <button type="button" className="quiet-button" onClick={() => void window.workbench?.openAppearancePreview?.().then(() => syncAppearancePreview())}><Icon name="external" size={14} /> Pop out preview</button>
        <p className="appearance-bar-status" role="status">{message || (dirty ? `Unsaved changes · editing ${active} colours` : `No unsaved changes · editing ${active} colours`)}</p>
        <HoverHelp title="Appearance changes">Changes preview immediately. Apply saves them on this computer; Cancel restores the last saved values. Reset returns an individual control to its shipped value. Pop out the preview to see a sample conversation.</HoverHelp>
        <button type="button" disabled={!dirty || saving} title="Restore the last saved appearance" onClick={() => { cancelAppearance(); setMessage(""); }}>Cancel</button>
        <button type="button" className="primary-button" disabled={!dirty || saving} title="Save appearance on this computer" onClick={() => void onApply()}>{saving ? "Applying…" : "Apply"}</button>
      </div>
    </div>
  );
}

const fontPresets: Record<string, Array<{ label: string; value: string }>> = {
  "font-ui": [{ label: "Arial", value: "Arial, sans-serif" }, { label: "Verdana", value: "Verdana, sans-serif" }, { label: "Georgia", value: "Georgia, serif" }],
  "font-mono": [{ label: "Consolas", value: "Consolas, monospace" }, { label: "Courier New", value: "\"Courier New\", monospace" }],
};

const densities: Record<string, Record<string, string>> = {
  Compact: { "pad-compact": "8px", "space-compact": "8px", "control-height": "30px" },
  Comfortable: { "pad-compact": "12px", "space-compact": "12px", "control-height": "36px" },
};

function AppearanceBasics() {
  const token = (id: string) => appearanceTokens.find(item => item.id === id)!;
  const current = (id: string) => currentAppearanceValue(token(id));
  const size = parseFloat(current("text-body"));
  const density = Object.entries(densities).find(([, values]) => Object.entries(values).every(([id, value]) => current(id) === value))?.[0] ?? "Custom";
  return <div className="appearance-basics">
    <div className="appearance-basic">
      <span className="appearance-basic-label">Font</span>
      <FamilyControl token={token("font-ui")} value={current("font-ui")} label="Interface font choice" />
    </div>
    <div className="appearance-basic">
      <span className="appearance-basic-label">Interface size <output>{size}px</output></span>
      <CompactSlider hideHeading label="Interface size" value={size} values={[11, 12, 13, 14, 15, 16, 18]} formatValue={value => `${value}px`} onChange={value => updateAppearanceValue("text-body", `${value}px`)} />
    </div>
    <div className="appearance-basic">
      <span className="appearance-basic-label">Density {density === "Custom" ? <small className="control-provenance">Custom</small> : null}</span>
      <SegmentedChoice bare label="Density" value={density} options={Object.keys(densities).map(value => ({ value, label: value }))} onChange={value => Object.entries(densities[value] ?? {}).forEach(([id, next]) => updateAppearanceValue(id, next))} />
    </div>
  </div>;
}

const AppearanceRow = memo(function AppearanceRow({ token, value }: { token: AppearanceToken; value: string }) {
  const shipped = shippedValue(token, token.theme === "split" ? appearanceActiveTheme() : "dark");
  const changed = value !== shipped;
  return (
    <div className="appearance-row" data-changed={changed || undefined} onFocusCapture={() => setAppearancePreviewAim(token)} onPointerEnter={() => setAppearancePreviewAim(token)}>
      <div className="appearance-row-name">
        <span className="appearance-row-title"><strong>{token.name}</strong><HoverHelp title={`About ${token.name.toLowerCase()}`}>{token.group}. Shipped {shipped}. {token.detail}</HoverHelp>
          <button type="button" className="text-button appearance-reset" hidden={!changed} onClick={() => resetAppearanceValue(token.id)}>Reset</button></span>
        <small className="control-provenance">{changed ? `Changed · shipped ${shipped}` : `${token.group} · shipped`}</small>
      </div>
      <div className="appearance-controls" data-kind={token.kind}>
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

function FamilyControl({ token, value, label }: { token: AppearanceToken; value: string; label?: string }) {
  const presets = [{ label: "System default", value: token.shipped }, ...(fontPresets[token.id] ?? [])];
  const preset = presets.find(item => item.value === value);
  const [customOpen, setCustomOpen] = useState(false);
  const custom = customOpen || !preset;
  const [text, setText] = useState(value);
  useEffect(() => { setText(value); }, [value]);
  const choice = custom ? "custom" : preset?.value ?? "custom";
  return <div className="appearance-family">
    <select aria-label={label ?? token.name} value={choice} onChange={event => {
      if (event.target.value === "custom") { setCustomOpen(true); return; }
      setCustomOpen(false);
      updateAppearanceValue(token.id, event.target.value);
    }}>{presets.map(item => <option key={item.value} value={item.value}>{item.label}</option>)}<option value="custom">Custom…</option></select>
    {custom ? <input type="text" aria-label={`${label ?? token.name} custom`} value={text} spellCheck={false} placeholder="Font family list" onChange={event => { setText(event.target.value); updateAppearanceValue(token.id, event.target.value); }} /> : null}
  </div>;
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
    <div className="slider-field">
      <input type="range" aria-label={`${token.name} slider`} min={min} max={max} step="any" value={slider} style={rangeFill(slider, min, max)} onChange={event => commitNumber(token, event.target.value)} />
      <span className="number-field">
        <input type="number" aria-label={token.name} min={token.allowNegative ? undefined : min} max={token.max ?? undefined} step="any" value={text} onChange={event => { setText(event.target.value); commitNumber(token, event.target.value); }} />
        <span className="field-unit">{token.unit || "\u00a0"}</span>
      </span>
    </div>
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
    <div className="appearance-color">
      <input type="color" aria-label={token.name} value={rgb} onChange={event => updateAppearanceValue(token.id, composeColor(event.target.value, alpha))} />
      <input type="text" className="appearance-hex" aria-label={`${token.name} hex`} value={hex} spellCheck={false} onChange={event => { setHex(event.target.value); updateAppearanceValue(token.id, event.target.value.trim()); }} />
      <input type="range" aria-label={`${token.name} transparency`} title="Opacity" min={0} max={100} step="any" value={alpha} style={rangeFill(alpha, 0, 100)} onChange={event => updateAppearanceValue(token.id, composeColor(rgb, Number(event.target.value)))} />
      <span className="number-field">
        <input type="number" aria-label={`${token.name} transparency percent`} min={0} max={100} step="any" value={alpha} onChange={event => commitAlpha(token.id, rgb, event.target.value)} />
        <span className="field-unit">%</span>
      </span>
    </div>
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
    <div className="appearance-shadow-controls">
      <NumberBits label="Shadow offset x" value={parsed.x} onChange={x => write({ x })} />
      <NumberBits label="Shadow offset y" value={parsed.y} onChange={y => write({ y })} />
      <NumberBits label="Shadow blur" value={parsed.blur} onChange={blur => write({ blur })} />
      <ColorBits label="Shadow colour" value={parsed.color} onChange={color => write({ color })} />
    </div>
  );
}

function NumberBits({ label, value, onChange }: { label: string; value: number; onChange: (value: number) => void }) {
  const max = Math.max(256, Math.abs(value));
  return (
    <div className="slider-field">
      <input type="range" aria-label={`${label} slider`} min={-max} max={max} step="any" value={value} style={rangeFill(value, -max, max)} onChange={event => onChange(Number(event.target.value))} />
      <span className="number-field">
        <input type="number" aria-label={label} step="any" value={value} onChange={event => { const next = Number(event.target.value); if (Number.isFinite(next)) onChange(next); }} />
        <span className="field-unit">px</span>
      </span>
    </div>
  );
}

function ColorBits({ label, value, onChange }: { label: string; value: string; onChange: (value: string) => void }) {
  const { rgb, alpha } = splitColor(value);
  return (
    <div className="appearance-color appearance-color-short">
      <input type="color" aria-label={label} value={rgb} onChange={event => onChange(composeColor(event.target.value, alpha))} />
      <input type="range" aria-label={`${label} transparency`} title="Opacity" min={0} max={100} step="any" value={alpha} style={rangeFill(alpha, 0, 100)} onChange={event => onChange(composeColor(rgb, Number(event.target.value)))} />
    </div>
  );
}

function rangeFill(value: number, min: number, max: number): CSSProperties {
  const percent = max > min ? ((value - min) / (max - min)) * 100 : 0;
  return { "--range-fill": `${Math.min(100, Math.max(0, percent))}%` } as CSSProperties;
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
