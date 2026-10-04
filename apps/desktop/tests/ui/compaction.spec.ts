import { test } from "./shared/fixtures";
import { compactionHistory, prepareCompaction } from "./shared/compaction";
import { instructionRetention, prepareInstructionRetention } from "./shared/instructionRetention";

for (const surface of ["Chat", "Agent run"] as const) {
  test(`${surface} native compaction preserves complete history through reconnect and restart`, async ({ page, backend, openWorkbench }, testInfo) => {
    await prepareCompaction(backend);
    await openWorkbench();
    await compactionHistory(page, backend, surface, testInfo);
  });
}

for (const surface of ["Chat", "Agent run"] as const) {
  test(`${surface} current task instructions survive native compaction and reopening`, async ({ page, backend, openWorkbench }, testInfo) => {
    await prepareInstructionRetention(backend);
    await openWorkbench();
    await instructionRetention(page, backend, surface, testInfo);
  });
}
