import { test } from "@playwright/test";
import { withNativeWorkbench } from "./ui/shared/native";
import { compactionHistory } from "./ui/shared/compaction";

test("actual Windows native compaction preserves both screens and complete history after restart", async ({}, testInfo) => {
  for (const surface of ["Chat", "Agent run"] as const) {
    await withNativeWorkbench(testInfo, "deterministic", async (page, backend) => {
      await compactionHistory(page, backend, surface, testInfo);
    }, { scenario: "compaction_history", restartingBackend: true });
  }
});
