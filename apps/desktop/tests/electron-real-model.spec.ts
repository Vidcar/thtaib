import { expect, test } from "@playwright/test";
import { withNativeWorkbench } from "./ui/shared/native";
import { acceptedLostResponse, assertRealFile, openSurface, reconnectAcceptedWork, send, type SendingState } from "./ui/shared/sending";
import { parallelHelperApprovals, prepareParallelHelpers } from "./ui/shared/helperApprovals";
import { compactionHistory } from "./ui/shared/compaction";

test("actual Windows real model sending survives lost responses and writes one file", async ({}, testInfo) => {
  expect(process.env.WORKBENCH_NATIVE_REAL_MODEL).toBe("required");
  await withNativeWorkbench(testInfo, "real", async (page, backend) => {
    for (const surface of ["Chat", "Agent run"] as const) {
      await acceptedLostResponse(page, backend, surface, true);
      await reconnectAcceptedWork(page, backend, surface, true);
    }
    await openSurface(page, backend, "Chat");
    const beforeWrite = (await backend.state<SendingState>()).run_count;
    const fileTask = "Call write_file once. Set file_path to exactly /hello.txt. Content must be exactly: hello from qwen";
    const messages = page.locator(".persistent-chat .message-feed");
    const answersBefore = await messages.locator(".bubble-assistant .message-answer").count();
    await send(page, "Chat", fileTask);
    // Waiting for a new admission prevents an earlier completed Agent turn from
    // satisfying this turn's terminal check before the command has been accepted.
    await expect.poll(async () => (await backend.state<SendingState>()).run_count).toBe(beforeWrite + 1);
    await expect.poll(async () => (await backend.state<SendingState>()).runs.at(-1)?.status, { timeout: 120_000 }).toBe("completed");
    await expect(messages.locator(".user-message-text").getByText(fileTask, { exact: true })).toHaveCount(1);
    // A tool turn renders its created-file outcome and its final response; it
    // need not have the single assistant bubble of a text-only turn.
    await expect.poll(async () => messages.locator(".bubble-assistant .message-answer").count()).toBeGreaterThan(answersBefore);
    await expect(messages.locator(".bubble-assistant .message-answer").last()).not.toHaveText("");
    await expect(messages.getByText("Created hello.txt", { exact: true })).toBeVisible();
    await assertRealFile(backend);
    const runs = await backend.state<SendingState & { runs: Array<{ tool_invocations: Array<{ name: string }> }> }>();
    expect(runs.runs.at(-1)?.tool_invocations.filter(tool => tool.name === "write_file")).toHaveLength(1);
    const identity = backend.seed.real_model_identity as { pid: number; create_time: number; runtime_sha256: string; model_sha256: string; inference: string };
    expect(identity.pid).toBeGreaterThan(0); expect(identity.create_time).toBeGreaterThan(0);
    expect(identity.runtime_sha256).toMatch(/^[a-f0-9]{64}$/i); expect(identity.model_sha256).toMatch(/^[a-f0-9]{64}$/i);
    expect(identity.inference).toContain("no scripted model");
  });
});

test("actual Windows real model parallel helpers approve one write and reject the other", async ({}, testInfo) => {
  expect(process.env.WORKBENCH_NATIVE_REAL_MODEL).toBe("required");
  const previousModel = process.env.WORKBENCH_SMOKE_MODEL_PATH;
  expect(process.env.WORKBENCH_HELPER_MODEL_PATH, "The helper capability case requires an existing explicitly selected local model").toBeTruthy();
  process.env.WORKBENCH_SMOKE_MODEL_PATH = process.env.WORKBENCH_HELPER_MODEL_PATH;
  try { await withNativeWorkbench(testInfo, "real", async (page, backend) => {
    await prepareParallelHelpers(backend);
    await parallelHelperApprovals(page, backend, "Chat", true);
    const identity = backend.seed.real_model_identity as { pid: number; runtime_sha256: string; model_sha256: string; inference: string };
    expect(identity.pid).toBeGreaterThan(0);
    expect(identity.runtime_sha256).toMatch(/^[a-f0-9]{64}$/i);
    expect(identity.model_sha256).toMatch(/^[a-f0-9]{64}$/i);
    expect(identity.inference).toContain("no scripted model");
  }); } finally {
    if (previousModel === undefined) delete process.env.WORKBENCH_SMOKE_MODEL_PATH;
    else process.env.WORKBENCH_SMOKE_MODEL_PATH = previousModel;
  }
});

test("actual Windows real model compaction retains facts and complete original history", async ({}, testInfo) => {
  test.setTimeout(900_000);
  expect(process.env.WORKBENCH_NATIVE_REAL_MODEL).toBe("required");
  expect(process.env.WORKBENCH_HELPER_MODEL_PATH, "The compaction case requires the existing local 4B model").toBeTruthy();
  const previousModel = process.env.WORKBENCH_SMOKE_MODEL_PATH;
  process.env.WORKBENCH_SMOKE_MODEL_PATH = process.env.WORKBENCH_HELPER_MODEL_PATH;
  try {
    for (const surface of ["Chat", "Agent run"] as const) {
      await withNativeWorkbench(testInfo, "real", async (page, backend) => {
        const identity = backend.seed.real_model_identity as { pid: number; runtime_sha256: string; model_sha256: string; model_name: string; inference: string };
        expect(identity.pid).toBeGreaterThan(0);
        expect(identity.runtime_sha256).toMatch(/^[a-f0-9]{64}$/i);
        expect(identity.model_sha256).toMatch(/^[a-f0-9]{64}$/i);
        expect(identity.model_name).toMatch(/qwen3\.5.*4b/i);
        expect(identity.inference).toContain("no scripted model");
        await compactionHistory(page, backend, surface, testInfo, true);
      }, { scenario: "compaction_history" });
    }
  } finally {
    if (previousModel === undefined) delete process.env.WORKBENCH_SMOKE_MODEL_PATH;
    else process.env.WORKBENCH_SMOKE_MODEL_PATH = previousModel;
  }
});
