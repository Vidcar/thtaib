import { createRequire } from "node:module";
import { spawn } from "node:child_process";
import path from "node:path";
import fs from "node:fs";
import { fileURLToPath } from "node:url";
import { orderingHarness } from "./check-live-chat-ordering.mjs";
import { deferred, json } from "./check-chat-interaction-boundaries.mjs";

const desktop = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const repo = path.resolve(desktop, "../..");
const scratch = path.join(repo, ".scratch/live-chat-ordering-native");
fs.mkdirSync(scratch, { recursive: true });
const main = path.join(scratch, "ordering-main.cjs");
fs.copyFileSync(path.join(desktop, "scripts/fixtures/check-live-chat-ordering.cjs"), main);
let admission;
let metadata;
const scenario = orderingHarness({ browser: true, requestOverride: async ({ req, res, url, body, scenario }) => {
  if (url.pathname !== "/fixture/action" || req.method !== "POST") return false;
  const { action, number, line } = JSON.parse(body);
  if (action === "beginHeld") {
    admission = deferred(); metadata = scenario.holdMetadata("order_run_1");
    scenario.harness.state.barriers.chatConversation.set("conv_a", admission);
    scenario.begin(number);
  } else if (action === "releaseAdmission") {
    scenario.harness.state.barriers.chatConversation.delete("conv_a"); admission.resolve();
    scenario.emit("values", scenario.values());
  } else if (action === "releaseMetadata") metadata.gate.resolve();
  else if (action === "begin") scenario.begin(number);
  else if (action === "text") scenario.text(number);
  else if (action === "tool") scenario.tool(number, number === 2 ? { callId: "read_1", outcome: "failed" } : number === 3 ? { outcome: "stopped" } : {});
  else if (action === "startFinal") scenario.startFinal(number);
  else if (action === "appendFinal") scenario.appendFinal(number, line);
  else if (action === "settle") scenario.settle(number, number === 2 ? "failed" : number === 3 ? "cancelled" : "completed");
  else if (action === "state") { json(res, 200, { streams: scenario.harness.state.allStreams.size, chatGets: scenario.harness.state.requests.chatGets.length }); return true; }
  else throw new Error(`Unknown fixture action: ${action}`);
  json(res, 200, {}); return true;
} });
await new Promise(resolve => scenario.harness.server.listen(0, "127.0.0.1", resolve));
const backend = `http://127.0.0.1:${scenario.harness.server.address().port}`;
const require = createRequire(path.join(desktop, "package.json"));
const { createServer } = require("vite");
const vite = await createServer({ configFile: false, root: path.join(desktop, "scripts/fixtures"),
  server: { host: "127.0.0.1", port: 0, watch: null, fs: { allow: [repo] } },
  resolve: { dedupe: ["react", "react-dom"], alias: { react: path.join(desktop, "node_modules/react"), "react-dom": path.join(desktop, "node_modules/react-dom") } },
  esbuild: { jsx: "automatic" }, logLevel: "error" });
try {
  await vite.listen();
  const url = `${vite.resolvedUrls.local[0]}live-chat-ordering.html?backend=${encodeURIComponent(backend)}`;
  const child = spawn(require("electron"), [main, url], { cwd: scratch, env: { ...process.env, WORKBENCH_ORDERING_SCRATCH: scratch }, stdio: "inherit", windowsHide: true });
  const timeout = setTimeout(() => child.kill(), 60000);
  try { process.exitCode = await new Promise((resolve, reject) => { child.on("error", reject); child.on("exit", code => resolve(code ?? 1)); }); }
  finally { clearTimeout(timeout); }
} finally {
  scenario.releaseAll();
  for (const stream of scenario.harness.state.allStreams.keys()) stream.end();
  scenario.harness.server.closeAllConnections?.();
  await new Promise(resolve => scenario.harness.server.close(resolve));
  await vite.close();
}
