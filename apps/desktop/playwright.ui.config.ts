import { defineConfig } from "@playwright/test";
import path from "node:path";

const evidenceRoot = path.resolve(import.meta.dirname, "../../.scratch/executable-baseline/playwright-ui");
export default defineConfig({
  testDir: "./tests/ui",
  testMatch: "baseline.spec.ts",
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 90_000,
  expect: { timeout: 15_000 },
  forbidOnly: true,
  outputDir: path.join(evidenceRoot, "artifacts"),
  reporter: [["list"], ["json", { outputFile: process.env.PLAYWRIGHT_JSON_OUTPUT_NAME ?? path.join(evidenceRoot, "report.json") }]],
  use: { browserName: "chromium", viewport: { width: 1440, height: 1000 }, actionTimeout: 15_000, navigationTimeout: 20_000, trace: "retain-on-failure", screenshot: "only-on-failure", video: "off" },
  webServer: { command: "node tests/ui/shared/serve-ui.mjs", url: "http://127.0.0.1:5173", timeout: 30_000, reuseExistingServer: false },
});
