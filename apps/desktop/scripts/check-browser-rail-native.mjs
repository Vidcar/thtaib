import { createRequire } from "node:module";
import { spawn } from "node:child_process";
import path from "node:path";
import fs from "node:fs";
import { fileURLToPath } from "node:url";
const desktop = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const repo = path.resolve(desktop, "../..");
const scratch = path.join(repo, ".scratch/browser-rail-native");
fs.mkdirSync(scratch, { recursive: true });
const main = path.join(scratch, "browser-rail-main.cjs");
fs.copyFileSync(path.join(desktop, "scripts/fixtures/check-browser-rail.cjs"), main);
const require = createRequire(path.join(desktop, "package.json"));
const { createServer } = require("vite");
const vite = await createServer({ configFile: false, root: path.join(desktop, "scripts/fixtures"), server: { host: "127.0.0.1", port: 0, watch: null, fs: { allow: [repo] } }, resolve: { dedupe: ["react", "react-dom"], alias: { react: path.join(desktop, "node_modules/react"), "react-dom": path.join(desktop, "node_modules/react-dom") } }, esbuild: { jsx: "automatic" }, logLevel: "error" });
try {
  await vite.listen();
  const child = spawn(require("electron"), [main, `${vite.resolvedUrls.local[0]}browser-rail.html`], { cwd: scratch, env: { ...process.env, WORKBENCH_BROWSER_RAIL_SCRATCH: scratch }, stdio: "inherit", windowsHide: true });
  const timeout = setTimeout(() => child.kill(), 60000);
  try { process.exitCode = await new Promise((resolve, reject) => { child.on("error", reject); child.on("exit", code => resolve(code ?? 1)); }); }
  finally { clearTimeout(timeout); }
} finally { await vite.close(); }
