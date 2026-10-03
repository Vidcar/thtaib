import { defineConfig } from "@playwright/test";
import path from "node:path";
import { fileURLToPath } from "node:url";

const repositoryRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const results = path.join(repositoryRoot, ".scratch", "ui-baseline", "electron-results");

export default defineConfig({
  testDir: "./tests",
  testMatch: "electron.spec.ts",
  fullyParallel: false,
  workers: 1,
  retries: 0,
  forbidOnly: true,
  timeout: 60_000,
  expect: { timeout: 15_000 },
  outputDir: path.join(results, "artifacts"),
  reporter: [["list"], ["json", { outputFile: process.env.PLAYWRIGHT_JSON_OUTPUT_NAME ?? path.join(results, "report.json") }]],
  // Native authentication is injected by main; never record its network headers.
  use: { trace: "off", video: "off", screenshot: "only-on-failure" },
});
