import assert from "node:assert/strict";
import { readdirSync, readFileSync, statSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const dist = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../dist");
const files = [];
function walk(directory) {
  for (const name of readdirSync(directory)) {
    const full = path.join(directory, name);
    if (statSync(full).isDirectory()) walk(full);
    else files.push(full);
  }
}
walk(dist);
const names = files.map(file => path.basename(file));
const html = files.filter(file => file.endsWith(".html")).map(file => readFileSync(file, "utf8")).join("\n");
const setup = readFileSync(path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../src/renderer/monacoSetup.ts"), "utf8");
assert.ok(names.some(name => /worker/i.test(name)), "Monaco's worker shipped inside the desktop package");
assert.match(setup, /loader\.config\(\{ monaco \}\)/, "the editor is configured from the local Monaco package before it opens");
assert.doesNotMatch(html, /cdn\.jsdelivr\.net|unpkg\.com\/monaco|cdnjs\.cloudflare\.com/, "the desktop page does not load Monaco from a CDN");
console.log("Monaco bundle check passed.");
