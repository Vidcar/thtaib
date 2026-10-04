import { expect, type Page } from "@playwright/test";
import type { BackendHandle } from "./backend";
import { navigateModels, openSurface, send, type SendingSurface } from "./sending";

interface HelperSelection { id: string; name: string; file_path: string; content: string; task: string }
interface Pending { run_id: string; interrupt_id: string; namespace: string[]; action_requests: Array<{ name: string; args: { file_path: string; content: string } }> }
interface HelperRun { id: string; parent_run_id: string; agent_setup_id: string; status: string; tool_invocations: Array<{ name: string; id: string }>; tool_outcomes: Record<string, { outcome: string }>; events: Array<{ kind: string; detail: { id?: string; tool_call_id?: string } }> }
interface HelperState {
  seed: BackendHandle["seed"];
  run_count: number; run_ids: string[];
  runs: Array<{ id: string; status: string; tool_invocations: Array<{ name: string }> }>;
  helper_runs: HelperRun[]; pending_interrupts: Pending[]; helper_files: Record<string, string | null>;
  faults: { stream_disconnects: number };
}

export async function prepareParallelHelpers(backend: BackendHandle): Promise<void> {
  backend.seed = (await backend.control<HelperState>("/__test__/scenario", { scenario: "parallel_helpers" })).seed;
}

/** Native graph, checkpoint, admission, scoped approvals and effects are real in both modes.
 * Deterministic mode scripts inference only; real mode never installs that model. */
export async function parallelHelperApprovals(page: Page, backend: BackendHandle, surface: SendingSurface, real = false): Promise<void> {
  const helpers = backend.seed.parallel_helpers as HelperSelection[];
  expect(helpers).toHaveLength(2);
  const before = (await backend.state<HelperState>()).run_count;
  await openSurface(page, backend, surface);
  if (surface === "Chat") {
    await send(page, surface, String(backend.seed.parallel_helper_task));
  } else {
    // The existing Agent form has no helper selector. Admit an authored saved
    // configuration through its public owner, then open it through real Attention.
    const admission = await page.request.post(`${backend.browserOrigin}/v1/agent-runs`, { data: {
      deployment_id: backend.seed.deployment_id, project_id: backend.seed.project_id,
      task: backend.seed.parallel_helper_task, helper_agent_ids: helpers.map(helper => helper.id),
      presented_tools: ["write_file"], approval_mode: "ask", input_policy: { tool_loading: "always" },
      per_request_overrides: backend.seed.parallel_request_settings,
    } });
    expect(admission.status()).toBe(200);
  }
  const timeout = real ? 120_000 : 15_000;
  await expect.poll(async () => (await backend.state<HelperState>()).pending_interrupts.length, { timeout }).toBe(2);
  let state = await backend.state<HelperState>();
  expect(state.run_count).toBe(before + 1);
  const runId = state.run_ids.at(-1)!;
  if (surface === "Agent run") {
    await page.getByRole("button", { name: /^Attention,/ }).click();
    const attention = page.getByRole("region", { name: "Attention", exact: true });
    const items = attention.getByRole("listitem").filter({ hasText: "Approval needed" });
    await expect(items).toHaveCount(3); // Parent and the two independently retained children.
    let opened = false;
    for (let index = 0; index < await items.count(); index++) {
      const item = items.nth(index);
      await item.getByRole("button", { name: "Item details", exact: true }).hover();
      const details = page.getByRole("tooltip").filter({ hasText: `Run: ${runId}` });
      if (await details.isVisible()) {
        await item.getByRole("button", { name: "Open", exact: true }).click();
        opened = true;
        break;
      }
    }
    expect(opened, "Open the retained parent run identified by its own Attention details").toBe(true);
  }
  const approval = page.getByRole("alertdialog", { name: /Review requested actions/ });
  await expect(approval).toBeVisible();
  await expect(approval).toContainText("2 requests waiting");
  state = await backend.state<HelperState>();
  expect(state.helper_runs).toHaveLength(2);
  expect(state.pending_interrupts.every(item => item.action_requests.length === 1)).toBe(true);
  expect(new Set(state.pending_interrupts.map(item => item.action_requests[0].args.file_path)).size).toBe(2);
  expect(new Set(state.pending_interrupts.map(item => item.interrupt_id)).size).toBe(2);
  expect(new Set(state.pending_interrupts.map(item => JSON.stringify(item.namespace))).size).toBe(2);
  expect(Object.values(state.helper_files)).toEqual([null, null]);
  if (!real) expect(state.helper_runs.map(child => child.tool_invocations[0].id)).toEqual(["shared-helper-write", "shared-helper-write"]);

  // Attach the actual SDK helper observer after both children have paused. Its
  // replay must contain this helper's earlier activity without the sibling's text.
  if (surface === "Chat") {
    for (const helper of helpers) await expect(page.getByRole("button", { name: `Open helper ${helper.name}`, exact: true })).toHaveCount(1);
    await page.getByRole("button", { name: `Open helper ${helpers[0].name}`, exact: true }).click();
    const detail = page.locator(".helper-rail-detail");
    await expect(detail).toBeVisible();
    await expect(detail).toContainText(helpers[0].file_path);
    if (!real) await expect(detail).toContainText(`${helpers[0].name} requests its own write`);
    await expect(detail).not.toContainText(helpers[1].file_path);
  } else {
    await expect(page.getByRole("list", { name: "Helper activity", exact: true }).getByRole("listitem")).toHaveCount(2);
  }

  const pendingResponse = await page.request.get(`${backend.browserOrigin}/v1/agent-runs/${runId}?view=diagnostic`);
  expect(pendingResponse.status()).toBe(200);
  const selected = (await pendingResponse.json()).pending_interrupt as Pending;
  const first = state.pending_interrupts.find(item => item.interrupt_id === selected.interrupt_id)!;
  const sibling = state.pending_interrupts.find(item => item.interrupt_id !== first.interrupt_id)!;
  const firstHelper = helpers.find(helper => helper.file_path === first.action_requests[0].args.file_path)!;
  await expect(approval).toContainText(firstHelper.name);
  for (const invalid of [
    { interrupt_id: "unowned-interrupt", namespace: first.namespace },
    { interrupt_id: first.interrupt_id, namespace: sibling.namespace },
    { interrupt_id: first.interrupt_id, namespace: ["foreign-helper"] },
  ]) {
    const rejected = await page.request.post(`${backend.browserOrigin}/v1/agent-runs/${runId}/interrupt-decision`, { data: { ...invalid, decisions: [{ type: "approve", scope: "once" }] } });
    expect(rejected.status()).toBe(409);
    expect(Object.values((await backend.state<HelperState>()).helper_files)).toEqual([null, null]);
    await expect(approval).toContainText("2 requests waiting");
  }

  const disconnects = state.faults.stream_disconnects;
  await navigateModels(page);
  await backend.control("/__test__/scenario", { disconnect_next_stream: true });
  await openSurface(page, backend, surface);
  await expect.poll(async () => (await backend.state<HelperState>()).faults.stream_disconnects).toBe(disconnects + 1);
  await expect(approval).toContainText(firstHelper.name);
  await expect(approval).toContainText("2 requests waiting");
  expect(Object.values((await backend.state<HelperState>()).helper_files)).toEqual([null, null]);

  await approval.getByRole("radio", { name: "Approve once", exact: true }).check();
  await approval.getByRole("button", { name: "Send decisions", exact: true }).click();
  await expect.poll(async () => (await backend.state<HelperState>()).pending_interrupts.length, { timeout }).toBe(1);
  const remaining = (await backend.state<HelperState>()).pending_interrupts[0];
  expect([remaining.interrupt_id, remaining.namespace]).toEqual([sibling.interrupt_id, sibling.namespace]);
  await expect(approval).toContainText("1 request waiting");
  const otherHelper = helpers.find(helper => helper.file_path === remaining.action_requests[0].args.file_path)!;
  await expect(approval).toContainText(otherHelper.name);
  await expect.poll(async () => (await backend.state<HelperState>()).helper_files[firstHelper.file_path]).toBe(firstHelper.content);
  expect((await backend.state<HelperState>()).helper_files[otherHelper.file_path]).toBeNull();
  // A consumed identity must not approve the still waiting sibling.
  const stale = await page.request.post(`${backend.browserOrigin}/v1/agent-runs/${runId}/interrupt-decision`, { data: {
    interrupt_id: first.interrupt_id, namespace: first.namespace, decisions: [{ type: "approve", scope: "once" }],
  } });
  expect(stale.status()).toBe(409);
  expect((await backend.state<HelperState>()).helper_files[otherHelper.file_path]).toBeNull();
  await approval.getByRole("radio", { name: "Reject", exact: true }).check();
  await approval.getByRole("button", { name: "Send decisions", exact: true }).click();
  await expect.poll(async () => (await backend.state<HelperState>()).runs.at(-1)?.status, { timeout }).toBe("completed");
  await expect(approval).toBeHidden();
  const final = await backend.state<HelperState>();
  expect(final.run_count).toBe(before + 1);
  expect(final.pending_interrupts).toEqual([]);
  expect(final.helper_runs).toHaveLength(2);
  expect(final.helper_runs.every(child => child.status === "completed")).toBe(true);
  expect(final.helper_files).toEqual({ [firstHelper.file_path]: firstHelper.content, [otherHelper.file_path]: null });
  expect(final.runs.at(-1)?.tool_invocations.filter(call => call.name === "task")).toHaveLength(2);
  for (const child of final.helper_runs) {
    const writes = child.tool_invocations.filter(call => call.name === "write_file");
    expect(writes).toHaveLength(1);
    expect(child.events.filter(event => event.kind === "tool_call" && event.detail.id === writes[0].id)).toHaveLength(1);
    expect(child.events.filter(event => event.kind === "tool_result" && event.detail.tool_call_id === writes[0].id)).toHaveLength(1);
  }
  await navigateModels(page);
  await openSurface(page, backend, surface);
  await expect(approval).toBeHidden();
  expect((await backend.state<HelperState>()).run_count).toBe(before + 1);
}
