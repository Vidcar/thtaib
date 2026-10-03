import { test } from "@playwright/test";
import { withNativeWorkbench } from "./ui/shared/native";
import { acceptedLostResponse, reconnectAcceptedWork, stopOwnedCommand } from "./ui/shared/sending";

test("actual Windows sending recovers both screens and cleans owned commands", async ({}, testInfo) => {
  await withNativeWorkbench(testInfo, "deterministic", async (page, backend) => {
    for (const surface of ["Chat", "Agent run"] as const) {
      await acceptedLostResponse(page, backend, surface);
      await reconnectAcceptedWork(page, backend, surface);
      await stopOwnedCommand(page, backend, surface);
    }
  });
});
