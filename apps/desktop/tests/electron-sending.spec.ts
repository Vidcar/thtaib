import { test } from "@playwright/test";
import { withNativeWorkbench } from "./ui/shared/native";
import { acceptedLostResponse, reconnectAcceptedWork, stopOwnedCommand } from "./ui/shared/sending";
import { parallelHelperApprovals, prepareParallelHelpers } from "./ui/shared/helperApprovals";

test("actual Windows sending recovers both screens and cleans owned commands", async ({}, testInfo) => {
  for (const surface of ["Chat", "Agent run"] as const) {
    // Stopping an owned command may leave an uncertain project effect. Preserve
    // that guard and give the other screen its own disposable effect scope.
    await withNativeWorkbench(testInfo, "deterministic", async (page, backend) => {
      await acceptedLostResponse(page, backend, surface);
      await reconnectAcceptedWork(page, backend, surface);
      await stopOwnedCommand(page, backend, surface);
    });
  }
});

test("actual Windows parallel helper approvals preserve both screens and scoped effects", async ({}, testInfo) => {
  for (const surface of ["Chat", "Agent run"] as const) {
    await withNativeWorkbench(testInfo, "deterministic", async (page, backend) => {
      await prepareParallelHelpers(backend);
      await parallelHelperApprovals(page, backend, surface);
    });
  }
});
