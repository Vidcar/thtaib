import assert from "node:assert/strict";
import { readdirSync, readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import ts from "typescript";

const desktopRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const renderer = path.join(desktopRoot, "src/renderer");
const catalog = readFileSync(path.join(renderer, "appearanceCatalog.ts"), "utf8");
const ids = [...catalog.matchAll(/"id": "([^"]+)"/g)].map(match => match[1]);
const cssVars = new Set([...catalog.matchAll(/"cssVar": "(--[^"]+)"/g)].map(match => match[1]));
assert.equal(new Set(ids).size, ids.length, "appearance ids are unique");
assert.ok(ids.includes("palette-bg"), "window colour is listed");
assert.ok(ids.includes("font-editor"), "file editor text is listed");
assert.ok(ids.includes("text-body"), "body text is listed");
assert.ok(ids.includes("pad-page"), "page inset is listed");
assert.ok(ids.includes("space-compact"), "the space between items is listed separately from inset");
assert.ok(ids.includes("layout-message"), "a person's message width is its own control");
for (const retired of ["space-hairline", "space-row", "pad-hairline", "pad-row", "text-micro", "text-caption", "text-compact", "text-subhead", "radius-small", "icon-sm", "font-serif", "tracking-tight", "tracking-open", "leading-relaxed"]) {
  assert.ok(!ids.includes(retired), `${retired} is folded into a control a person can tell apart`);
}
assert.ok(ids.length < 160, `appearance stays a shared set, not one control per element (${ids.length})`);

const aliases = new Set(["--bg", "--bg-nav", "--bg-panel", "--bg-raised", "--bg-input", "--border", "--text", "--muted", "--accent", "--warn", "--danger", "--ok", "--live", "--hover", "--shadow", "--navigation-width", "--inspector-width"]);
const lengthRe = /(?<![\w-])(?!0(?:px|rem|em)\b)(?:\d+\.?\d*|\.\d+)(?:px|rem|em)\b/g;
const hexRe = /#[0-9a-fA-F]{3,8}\b/g;
const leftovers = [];
const unknownVars = [];

for (const name of readdirSync(renderer).filter(item => item.endsWith(".css") && item !== "appearanceDefaults.css")) {
  const text = readFileSync(path.join(renderer, name), "utf8");
  assert.doesNotMatch(text, /(?:^|[;{])\s*(?:max-width|min-width|width)\s*:[^;{]*var\(--tint-/, `${name} must not use a colour mix as a width`);
  const stripped = stripVars(stripComments(text));
  for (const match of stripped.matchAll(lengthRe)) leftovers.push(`${name}: ${match[0]} in ${lineOf(stripped, match.index).trim()}`);
  for (const match of stripped.matchAll(hexRe)) leftovers.push(`${name}: ${match[0]} in ${lineOf(stripped, match.index).trim()}`);
  for (const match of text.matchAll(/var\((--[a-z0-9-]+)/g)) {
    if (!cssVars.has(match[1]) && !aliases.has(match[1])) unknownVars.push(`${name}: ${match[1]}`);
  }
}

const strayColours = leftovers.filter(item => item.includes("#") && !/@media|@container/.test(item));
assert.deepEqual(strayColours, [], `colours must use the shared palette:\n${strayColours.join("\n")}`);
assert.deepEqual([...new Set(unknownVars)], [], `unknown appearance variables:\n${[...new Set(unknownVars)].join("\n")}`);

const defaults = readFileSync(path.join(renderer, "appearanceDefaults.css"), "utf8");
assert.match(defaults, /--palette-bg:\s*#212121/, "dark window colour stays the shipped dark value");
assert.match(defaults, /--palette-bg:\s*#ffffff/, "light window colour stays the shipped light value");

const valueSource = readFileSync(path.join(renderer, "appearanceValue.ts"), "utf8");
const compiled = ts.transpileModule(valueSource, { compilerOptions: { module: ts.ModuleKind.ESNext } }).outputText;
const { appearanceValueValid, readAppearanceFile, resolvedAppearanceValue } = await import(`data:text/javascript;base64,${Buffer.from(compiled).toString("base64")}`);
const length = { id: "wide", kind: "length", unit: "px", shipped: "14px", shippedLight: null, theme: "all", allowNegative: false, min: null, max: null };
const weight = { id: "weight", kind: "number", unit: "", shipped: "600", shippedLight: null, theme: "all", allowNegative: false, min: 1, max: 1000 };
const colour = { id: "palette-bg", kind: "color", unit: "", shipped: "#212121", shippedLight: "#ffffff", theme: "split", allowNegative: false };
assert.equal(appearanceValueValid(length, "12000px"), true, "a very wide measurement is valid");
assert.equal(appearanceValueValid(length, "-4px"), false, "negative padding is not a valid length");
assert.equal(appearanceValueValid(weight, "1001"), false, "font weight stays inside the valid range");
assert.equal(appearanceValueValid(colour, "#ff00aa80"), true, "colour transparency is valid");
assert.equal(appearanceValueValid(colour, "red"), false);
const stored = readAppearanceFile({ version: 1, values: { wide: "12000px", missing: "4px", weight: "nope" }, light: { "palette-bg": "#010101" } }, [length, weight, colour]);
assert.equal(stored.values.wide, "12000px");
assert.equal(stored.values.missing, undefined);
assert.equal(stored.values.weight, undefined);
assert.equal(resolvedAppearanceValue(colour, stored, "light"), "#010101");
assert.equal(resolvedAppearanceValue(colour, stored, "dark"), "#212121");
const itemSpace = { id: "space-compact", kind: "length", unit: "px", shipped: "8px", shippedLight: null, theme: "all", allowNegative: false, min: null, max: null };
const smallText = { id: "text-small", kind: "length", unit: "px", shipped: "11px", shippedLight: null, theme: "all", allowNegative: false, min: null, max: null };
const retired = readAppearanceFile({ version: 1, values: { "space-row": "18px", "space-compact": "9px", "text-caption": "15px", "font-serif": "Georgia, serif" } }, [itemSpace, smallText]);
assert.equal(retired.values["space-compact"], "9px", "an explicit survivor wins over a folded control");
assert.equal(retired.values["text-small"], "15px", "a folded text size keeps its saved override");
assert.equal(retired.values["font-serif"], undefined);
console.log(`Appearance catalogue checks passed (${ids.length} controls).`);

function stripComments(text) {
  return text.replace(/\/\*[\s\S]*?\*\//g, "");
}

function stripVars(text) {
  let out = "";
  for (let index = 0; index < text.length; index += 1) {
    if (text.startsWith("var(", index) || text.startsWith("url(", index)) {
      const end = matchingParen(text, text.indexOf("(", index));
      index = end;
      continue;
    }
    out += text[index];
  }
  return out;
}

function matchingParen(value, openIndex) {
  let depth = 0;
  for (let index = openIndex; index < value.length; index += 1) {
    if (value[index] === "(") depth += 1;
    else if (value[index] === ")") {
      depth -= 1;
      if (depth === 0) return index;
    }
  }
  return value.length - 1;
}

function lineOf(text, index) {
  const start = text.lastIndexOf("\n", index) + 1;
  const end = text.indexOf("\n", index);
  return text.slice(start, end === -1 ? text.length : end);
}
