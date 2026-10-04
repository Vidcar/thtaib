import { test } from "./shared/fixtures";
import { compactionHistory, prepareCompaction } from "./shared/compaction";

for (const surface of ["Chat", "Agent run"] as const) {
  test(`${surface} native compaction preserves complete history through reconnect and restart`, async ({ page, backend, openWorkbench }, testInfo) => {
    await prepareCompaction(backend);
    await openWorkbench();
    await compactionHistory(page, backend, surface, testInfo);
  });
}
