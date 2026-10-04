import { test } from "@playwright/test";
import { withNativeWorkbench } from "./ui/shared/native";
import { compactionHistory } from "./ui/shared/compaction";
import { instructionRetention } from "./ui/shared/instructionRetention";

test("actual Windows native compaction preserves both screens and complete history after restart", async ({}, testInfo) => {
  for (const surface of ["Chat", "Agent run"] as const) {
    await withNativeWorkbench(testInfo, "deterministic", async (page, backend) => {
      await compactionHistory(page, backend, surface, testInfo);
    }, { scenario: "compaction_history", restartingBackend: true });
  }
});

test("actual Windows current task instructions survive native compaction on both screens", async ({}, testInfo) => {
  for (const surface of ["Chat", "Agent run"] as const) {
    await withNativeWorkbench(testInfo, "deterministic", async (page, backend) => {
      await instructionRetention(page, backend, surface, testInfo);
    }, { scenario: "instruction_retention", restartingBackend: true });
  }
});
