import { defineConfig } from "@playwright/test";
import path from "node:path";
import { fileURLToPath } from "node:url";

const repositoryRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const realModel = process.env.WORKBENCH_NATIVE_REAL_MODEL === "required";
const results = path.join(repositoryRoot, ".scratch", "ui-baseline", realModel ? "electron-real-model-results" : "electron-results");

export default defineConfig({
  testDir: "./tests",
  testMatch: realModel ? "electron-real-model.spec.ts" : ["electron.spec.ts", "electron-sending.spec.ts", "electron-compaction.spec.ts"],
  fullyParallel: false,
  workers: 1,
  retries: 0,
  forbidOnly: true,
  timeout: realModel ? 300_000 : 120_000,
  expect: { timeout: 15_000 },
  outputDir: path.join(results, "artifacts"),
  reporter: [["list"], ["json", { outputFile: process.env.PLAYWRIGHT_JSON_OUTPUT_NAME ?? path.join(results, "report.json") }]],
  // Native authentication is injected by main; never record its network headers.
  use: { trace: "off", video: "off", screenshot: "only-on-failure" },
});
