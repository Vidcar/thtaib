import { test } from "@playwright/test";
import { withNativeWorkbench } from "./ui/shared/native";
import { acceptedLostResponse, reconnectAcceptedWork, stopOwnedCommand } from "./ui/shared/sending";

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
