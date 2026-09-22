import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import ts from "typescript";

globalThis.window = { workbench: { backendUrl: "http://127.0.0.1:8000" } };
const source = await readFile(new URL("../src/renderer/api.ts", import.meta.url), "utf8");
const output = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext } }).outputText;
const { api } = await import(`data:text/javascript;base64,${Buffer.from(output).toString("base64")}`);
const pending = [];
globalThis.fetch = (url, init) => new Promise((resolve) => pending.push({ url, init, resolve }));
const original = { theme: "light", detailed_streams: false, attention_notifications: false, success_notifications: true };
const response = (value, status = 200) => new Response(JSON.stringify(value), { status });
async function nextRequest() {
  for (let count = 0; count < 20 && !pending.length; count++) await new Promise(setImmediate);
  assert.ok(pending.length, "expected a pending request");
  return pending.shift();
}

// A GET started before a save must not hydrate its obsolete response afterward.
const reading = api.presentationSettings();
const staleRead = await nextRequest();
const savingTheme = api.updatePresentationSettings({ theme: "dark" });
const themeWrite = await nextRequest();
assert.equal(themeWrite.init.method, "PATCH");
assert.deepEqual(JSON.parse(themeWrite.init.body), { theme: "dark" });
const dark = { ...original, theme: "dark" };
themeWrite.resolve(response(dark));
await savingTheme;
staleRead.resolve(response(original));
const freshRead = await nextRequest();
freshRead.resolve(response(dark));
assert.deepEqual(await reading, dark);

// Chat and Settings can submit independent updates before either is acknowledged.
const details = api.updatePresentationSettings({ detailed_streams: true });
const success = api.updatePresentationSettings({ success_notifications: false });
const detailsWrite = await nextRequest();
assert.deepEqual(JSON.parse(detailsWrite.init.body), { detailed_streams: true });
assert.equal(pending.length, 0, "second save waits for first acknowledgement");
const detailed = { ...dark, detailed_streams: true };
detailsWrite.resolve(response(detailed));
assert.deepEqual(await details, detailed);
const successWrite = await nextRequest();
assert.deepEqual(JSON.parse(successWrite.init.body), { success_notifications: false });
const final = { ...detailed, success_notifications: false };
successWrite.resolve(response(final));
assert.deepEqual(await success, final);

// A failed save must be visible to its caller without blocking future changes.
const failed = assert.rejects(api.updatePresentationSettings({ theme: "system" }), /Save failed/);
const recovered = api.updatePresentationSettings({ attention_notifications: true });
(await nextRequest()).resolve(response({ error: "Save failed" }, 503));
await failed;
(await nextRequest()).resolve(response({ ...final, attention_notifications: true }));
assert.equal((await recovered).attention_notifications, true);
console.log("Presentation preference ordering checks passed.");
