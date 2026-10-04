import { test, expect } from "./shared/fixtures";
import { acceptedLostResponse, assertOneExecution, editor, navigateModels, openSurface, reconnectAcceptedWork, send, sendButton, stopOwnedCommand, type SendingState, type SendingSurface } from "./shared/sending";
import { readFile } from "node:fs/promises";
import path from "node:path";
import { parallelHelperApprovals, prepareParallelHelpers } from "./shared/helperApprovals";

for (const surface of ["Chat", "Agent run"] as SendingSurface[]) {
  test(`${surface} parallel helper approvals preserve scoped effects through navigation and reconnect`, async ({ page, backend, openWorkbench }) => {
    await prepareParallelHelpers(backend);
    await openWorkbench();
    await parallelHelperApprovals(page, backend, surface);
  });

  test(`${surface} rejected and uncertain original submissions preserve drafts`, async ({ page, backend, openWorkbench }) => {
    await openWorkbench();
    await openSurface(page, backend, surface);
    const rejected = `Rejected ${surface} task stays authored`;
    await backend.control("/__test__/scenario", { reject_next_submit: true });
    await send(page, surface, rejected);
    await expect(page.getByText("Baseline task rejected before acceptance", { exact: false })).toBeVisible();
    await expect(editor(page, surface)).toHaveValue(rejected);
    await expect(sendButton(page, surface)).toBeEnabled();
    expect((await backend.state<SendingState>()).run_count).toBe(0);

    const original = `Original ${surface} intent remains frozen`;
    const newer = `Newer ${surface} draft must survive original acceptance`;
    await backend.control("/__test__/scenario", { hold_submit: true, fail_state_reads: 2 });
    backend.loseNextCommandResponseBeforeAcceptance();
    await send(page, surface, original);
    await expect(page.getByRole("button", { name: "Retry original task", exact: true })).toBeVisible();
    await expect.poll(async () => (await backend.state<SendingState>()).submissions.length).toBe(2);
    expect((await backend.state<SendingState>()).run_count).toBe(0);
    await editor(page, surface).fill(newer);
    await expect.poll(async () => (await backend.state<SendingState>()).faults.state_lookup_failures).toBeGreaterThan(0);
    await backend.control("/__test__/scenario", { fail_state_reads: 0 });
    if (surface === "Chat") {
      const expand = page.getByRole("button", { name: "Expand sidebar", exact: true });
      if (await expand.isVisible()) await expand.click();
      await page.getByRole("button", { name: "Other baseline conversation", exact: true }).click();
      await expect(page.getByRole("heading", { name: "Other baseline conversation", exact: true })).toBeVisible();
      await editor(page, surface).fill("Other chat draft stays scoped");
      await page.getByRole("button", { name: "Baseline conversation", exact: true }).click();
      await expect(editor(page, surface)).toHaveValue(newer);
      await expect(page.getByRole("button", { name: "Retry original task", exact: true })).toBeVisible();
    } else {
      await navigateModels(page);
      await openSurface(page, backend, surface);
      await expect(editor(page, surface)).toHaveValue(newer);
      await expect(page.getByRole("button", { name: "Retry original task", exact: true })).toBeVisible();
    }
    await page.getByRole("button", { name: "Check again", exact: true }).click();
    await expect(editor(page, surface)).toHaveValue(newer);
    expect((await backend.state<SendingState>()).run_count).toBe(0);
    await page.getByRole("button", { name: "Retry original task", exact: true }).click();
    await expect.poll(async () => (await backend.state<SendingState>()).submissions.length).toBe(3);
    await backend.control("/__test__/scenario", { release_submit: true });
    await expect.poll(async () => (await backend.state<SendingState>()).runs.at(-1)?.status).toBe("completed");
    await expect(editor(page, surface)).toHaveValue(newer);
    await expect(page.getByRole("button", { name: "Retry original task", exact: true })).toBeHidden();
    const state = await assertOneExecution(backend, 0);
    const first = state.submissions[1];
    const retry = state.submissions[2];
    expect(retry.thread_id).toBe(first.thread_id);
    expect(retry.payload.params.input.messages[0]).toEqual(first.payload.params.input.messages[0]);
    expect(retry.payload.params.metadata).toEqual(first.payload.params.metadata);
    expect(retry.payload.params.input.messages[0].content).toBe(original);
    expect(state.faults.state_lookup_failures).toBeGreaterThan(0);
    if (surface === "Chat") expect(state.failed_lookup_paths).toContain(`/v1/chat/conversations/${backend.seed.conversation_id}`);
  });

  test(`${surface} accepted lost response and reconnect execute once without reload`, async ({ page, backend, openWorkbench }) => {
    await openWorkbench();
    await acceptedLostResponse(page, backend, surface);
    await reconnectAcceptedWork(page, backend, surface);
  });

  test(`${surface} navigation preserves drafts and cancellation cleans owned work`, async ({ page, backend, openWorkbench }) => {
    await openWorkbench();
    await openSurface(page, backend, surface);
    const text = `Unsent ${surface} task survives navigation`;
    await editor(page, surface).fill(text);
    await navigateModels(page);
    await openSurface(page, backend, surface);
    await expect(editor(page, surface)).toHaveValue(text);
    expect((await backend.state<SendingState>()).run_count).toBe(0);
    await stopOwnedCommand(page, backend, surface);
  });
}

test("uncertain native effects pause continuation across observation", async ({ page, backend, openWorkbench }) => {
  await openWorkbench();
  await backend.control("/__test__/scenario", { scenario: "partial_effect" });
  await send(page, "Chat", "Run the bounded partial command and inspect its result");
  const approval = page.getByRole("alertdialog", { name: /Review requested actions/ });
  await expect(approval).toBeVisible();
  await approval.getByRole("radio", { name: "Approve once", exact: true }).check();
  await approval.getByRole("button", { name: "Send decisions", exact: true }).click();
  await page.getByRole("button", { name: "Inspect effects", exact: true }).click();
  await expect(page.getByRole("region", { name: "Uncertain effects", exact: true })).toBeVisible();
  const marker = path.join(String(backend.seed.project_path), "partial-marker.txt");
  expect((await readFile(marker, "utf8")).split(/\r?\n/).filter(Boolean)).toEqual(["once"]);
  const before = await backend.state<SendingState>();
  expect(before.runs.at(-1)?.status).toBe("failed");
  await page.reload();
  await page.getByRole("button", { name: "Inspect effects", exact: true }).click();
  await expect(page.getByRole("region", { name: "Uncertain effects", exact: true })).toBeVisible();
  await send(page, "Chat", "Continue without inspecting the previous effect");
  await expect(page.getByRole("region", { name: "Uncertain effects", exact: true })).toBeVisible();
  expect((await backend.state<SendingState>()).run_count).toBe(before.run_count);
  expect((await readFile(marker, "utf8")).split(/\r?\n/).filter(Boolean)).toEqual(["once"]);
});
