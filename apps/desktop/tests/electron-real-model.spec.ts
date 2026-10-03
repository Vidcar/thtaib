import { expect, test } from "@playwright/test";
import { withNativeWorkbench } from "./ui/shared/native";
import { acceptedLostResponse, assertRealFile, openSurface, reconnectAcceptedWork, send, type SendingState } from "./ui/shared/sending";

test("actual Windows real model sending survives lost responses and writes one file", async ({}, testInfo) => {
  expect(process.env.WORKBENCH_NATIVE_REAL_MODEL).toBe("required");
  await withNativeWorkbench(testInfo, "real", async (page, backend) => {
    for (const surface of ["Chat", "Agent run"] as const) {
      await acceptedLostResponse(page, backend, surface, true);
      await reconnectAcceptedWork(page, backend, surface, true);
    }
    await openSurface(page, backend, "Chat");
    await send(page, "Chat", "Call write_file once. Set file_path to exactly /hello.txt. Content must be exactly: hello from qwen");
    await expect.poll(async () => (await backend.state<SendingState>()).runs.at(-1)?.status, { timeout: 120_000 }).toBe("completed");
    await assertRealFile(backend);
    const runs = await backend.state<SendingState & { runs: Array<{ tool_invocations: Array<{ name: string }> }> }>();
    expect(runs.runs.at(-1)?.tool_invocations.filter(tool => tool.name === "write_file")).toHaveLength(1);
    const identity = backend.seed.real_model_identity as { pid: number; create_time: number; runtime_sha256: string; model_sha256: string; inference: string };
    expect(identity.pid).toBeGreaterThan(0); expect(identity.create_time).toBeGreaterThan(0);
    expect(identity.runtime_sha256).toMatch(/^[a-f0-9]{64}$/i); expect(identity.model_sha256).toMatch(/^[a-f0-9]{64}$/i);
    expect(identity.inference).toContain("no scripted model");
  });
});
