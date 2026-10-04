import { expect, type Page, type TestInfo } from "@playwright/test";
import { createHash } from "node:crypto";
import type { BackendHandle } from "./backend";
import { navigateModels, openSurface, send, type SendingSurface } from "./sending";
import { assertHistory, assertNativeReduction, enableCompletionNotice, messagesOnly, openAttentionAgent, text, type CompactionRow } from "./compaction";

interface ToolCall { id?: string; name: string; args: Record<string, unknown> }
interface InstructionSeed {
  task: string; task_sha256: string; marker: string; tools: string[];
  request_settings: Record<string, unknown>; expected_calls: ToolCall[]; write_content: string;
}
interface WorkInput {
  ordinal: number; count_ordinal: number | null; purpose: string; boundary: string; after_compaction: boolean;
  native_input_removed: boolean; task_reference_input_ids: string[];
  payload_sha256: string; tools_sha256: string | null; input_tokens: number | null; basis: string;
  messages: Array<{ role: string; content: unknown }>; task_occurrences: number; user_task_occurrences: number;
  task_message_indices: number[]; task_reference_ids: string[]; matching_count_ordinals: number[];
}
interface InstructionRow extends CompactionRow {
  accepted_task: string; accepted_task_sha256: string; accepted_input_id: string;
  calls: ToolCall[]; work_inputs: WorkInput[]; counted_inputs: WorkInput[]; input_capture_errors: unknown[];
}
interface InstructionState {
  seed: BackendHandle["seed"]; run_count: number; run_ids: string[];
  runs: Array<{ id: string; status: string }>;
  pending_interrupts: Array<{ run_id: string }>; faults: { stream_disconnects: number };
  instruction_retention: { rows: InstructionRow[] };
}
const originalTaskHash = "7300beba4d465b03749b5466dbff49e58f4e1926d3fecf7e10dd2ea2ca6cfc31";

export async function prepareInstructionRetention(backend: BackendHandle): Promise<void> {
  backend.seed = (await backend.control<InstructionState>("/__test__/scenario", { scenario: "instruction_retention" })).seed;
}

function assertInputs(row: InstructionRow, seed: InstructionSeed, real: boolean): WorkInput[] {
  expect(row.accepted_task).toBe(seed.task);
  expect(row.accepted_task_sha256).toBe(originalTaskHash);
  expect(row.accepted_input_id).toBeTruthy();
  expect(row.input_capture_errors).toEqual([]);
  const inputs = row.work_inputs.filter(input => input.boundary === (real ? "final_request" : "deterministic_inference"));
  expect(inputs.length, "Capture actual model-consumed work input").toBeGreaterThan(0);
  for (const input of inputs) {
    expect(input.task_occurrences, "The exact accepted task occurs once in each actual work input").toBe(1);
    expect(input.user_task_occurrences, "Task authority stays at user priority").toBe(1);
    expect(input.task_message_indices).toHaveLength(1);
  }
  const compacted = inputs.filter(input => input.after_compaction);
  expect(compacted.length, "Inspect actual work after native summarization").toBeGreaterThan(0);
  expect(compacted.some(input => input.native_input_removed && input.task_reference_ids.length === 1),
    "Native compaction must actually remove the active input and exercise restoration").toBe(true);
  for (const input of compacted) {
    if (input.task_reference_ids.length) {
      expect(input.task_reference_ids).toHaveLength(1);
      expect(input.task_reference_input_ids).toEqual([row.accepted_input_id]);
      expect(input.task_message_indices[0], "Original-task reference precedes summary and completed progress")
        .toBe(input.messages.findIndex(message => message.role !== "system"));
    }
    expect(input.matching_count_ordinals.length, "The same final work input must have been counted").toBeGreaterThan(0);
    for (const ordinal of input.matching_count_ordinals) {
      const count = row.counted_inputs.find(item => item.count_ordinal === ordinal);
      expect(count, "Retain the matching independent count-boundary record").toBeDefined();
      expect(count!.payload_sha256).toBe(input.payload_sha256);
      expect(count!.task_occurrences).toBe(1);
      if (real) expect(count!.basis).toBe("native");
    }
  }
  return compacted;
}

function assertSequentialActions(row: InstructionRow) {
  const exchanges: Array<{ call_message_id: string; tool_call_id: string; result_message_id: string }> = [];
  let pending: { call_message_id: string; tool_call_id: string } | undefined;
  for (const message of row.archive) {
    if (message.tool_calls?.length) {
      expect(pending, "Wait for the previous tool result before the next assistant call").toBeUndefined();
      expect(message.type).toBe("ai");
      expect(message.tool_calls, "Only one tool call in each assistant response").toHaveLength(1);
      expect(message.tool_calls[0].id).toBeTruthy();
      pending = { call_message_id: message.id, tool_call_id: message.tool_calls[0].id };
    } else if (message.type === "tool") {
      expect(pending, "Every emitted tool result has its preceding separate assistant call").toBeDefined();
      expect(message.tool_call_id).toBe(pending!.tool_call_id);
      exchanges.push({ ...pending!, result_message_id: message.id });
      pending = undefined;
    }
  }
  expect(pending, "The final assistant call has received its result").toBeUndefined();
  expect(exchanges, "Four separate assistant/result exchanges").toHaveLength(4);
  expect(exchanges.map(exchange => exchange.tool_call_id)).toEqual(row.calls.map(call => call.id));
  return exchanges;
}

export async function instructionRetention(page: Page, backend: BackendHandle, surface: SendingSurface, testInfo: TestInfo, real = false): Promise<void> {
  const seed = backend.seed.instruction_retention as InstructionSeed;
  expect(createHash("sha256").update(seed.task).digest("hex"), "Use the recovered original task unchanged").toBe(originalTaskHash);
  expect(seed.task_sha256).toBe(originalTaskHash);
  const before = await backend.state<InstructionState>();
  if (surface === "Agent run") await enableCompletionNotice(page, backend);
  await openSurface(page, backend, surface);
  const negative = {
    "instruction-missing-text": "instruction_missing_text",
    "instruction-changed-arguments": "instruction_changed_arguments",
    "instruction-repeated-action": "instruction_repeated_action",
    "instruction-batched-calls": "instruction_batched_calls",
  }[process.env.WORKBENCH_UI_NEGATIVE_CONTROL ?? ""];
  await backend.control("/__test__/scenario", { disconnect_next_stream: true, ...(negative ? { negative_control: negative } : {}) });
  if (real && surface === "Agent run") {
    const admitted = await page.request.post(`${backend.browserOrigin}/v1/agent-runs`, { data: {
      deployment_id: backend.seed.deployment_id, project_id: backend.seed.project_id, task: seed.task,
      presented_tools: seed.tools, per_request_overrides: seed.request_settings,
      approval_mode: "ask", input_policy: { tool_loading: "always" },
    } });
    expect(admitted.status()).toBe(200);
    const run = await admitted.json() as { id: string };
    await expect.poll(async () => (await backend.state<InstructionState>()).pending_interrupts.filter(item => item.run_id === run.id).length,
      { timeout: 120_000 }).toBe(1);
    await openAttentionAgent(page, run.id, "Approval needed");
  } else await send(page, surface, seed.task);
  await expect.poll(async () => (await backend.state<InstructionState>()).run_count).toBe(before.run_count + 1);
  if (surface === "Agent run") {
    const approval = page.getByRole("alertdialog", { name: /Review requested actions/ });
    await expect(approval).toBeVisible();
    await approval.getByRole("radio", { name: "Approve once", exact: true }).check();
    await approval.getByRole("button", { name: "Send decisions", exact: true }).click();
    if (negative === "instruction_repeated_action") {
      // The deliberately repeated write remains subject to the native policy.
      // Approve its separate card only in this negative-control journey, then
      // let the exact tool-trace assertion detect the executed extra action.
      await expect(approval).toBeVisible();
      await approval.getByRole("radio", { name: "Approve once", exact: true }).check();
      await approval.getByRole("button", { name: "Send decisions", exact: true }).click();
    }
  }
  await expect.poll(async () => (await backend.state<InstructionState>()).runs.at(-1)?.status,
    { timeout: real ? 420_000 : 30_000 }).toBe("completed");
  let state = await backend.state<InstructionState>();
  const runId = state.run_ids.at(-1)!;
  let row = state.instruction_retention.rows.find(item => item.run_id === runId)!;
  expect(row, "Completed run has independent instruction evidence").toBeDefined();
  expect(state.run_count).toBe(before.run_count + 1);
  expect(state.faults.stream_disconnects).toBe(before.faults.stream_disconnects + 1);
  expect(row.native_summary_count).toBeGreaterThanOrEqual(real ? 1 : 2);
  expect(row.cutoff_index).toBeGreaterThan(0);
  expect(row.offload_readable).toBe(true);
  const compactedInputs = assertInputs(row, seed, real);
  expect(row.calls.map(({ name, args }) => ({ name, args })), "Exact original tool sequence and arguments").toEqual(seed.expected_calls);
  const actionExchanges = assertSequentialActions(row);
  expect(new Set(row.calls.map(call => call.id)).size).toBe(4);
  expect(row.write_count).toBe(1); expect(row.read_count).toBe(3);
  expect(row.write_content).toBe(seed.write_content);
  expect(text(row.archive.at(-1)!)).toContain(seed.marker);
  const reductions = assertNativeReduction(row, real);
  const originalResults = row.original_tool_results.filter(message => message.type === "tool");
  expect(originalResults.filter(message => message.name === "read_file")).toHaveLength(3);
  for (const original of originalResults) {
    const archived = row.archive.find(message => message.id === original.id);
    expect(archived && messagesOnly([archived]), "Visible tool result equals its original emitted source").toEqual(messagesOnly([original]));
  }
  expect(row.archive.filter(message => text(message) === seed.task)).toHaveLength(1);
  expect(row.archive.some(message => message.id?.startsWith("current-task-reference-")
    || text(message).includes("Original user instructions for the already accepted ongoing task"))).toBe(false);
  const original = structuredClone(row.archive);
  const historyProofs = [{ stage: "completed after disconnect", proof: await assertHistory(page, backend, surface, row) }];
  await navigateModels(page); await openSurface(page, backend, surface);
  historyProofs.push({ stage: "navigation", proof: await assertHistory(page, backend, surface, row, original) });
  await page.reload();
  if (surface === "Chat") await openSurface(page, backend, surface);
  else await openAttentionAgent(page, runId);
  historyProofs.push({ stage: "reload/reopen", proof: await assertHistory(page, backend, surface, row, original) });
  if (!real) {
    const oldPid = backend.pid;
    await backend.restart(); expect(backend.pid).not.toBe(oldPid);
    state = await backend.state<InstructionState>();
    row = state.instruction_retention.rows.find(item => item.run_id === runId)!;
    expect(messagesOnly(row.archive)).toEqual(messagesOnly(original));
    expect(row.calls.map(({ name, args }) => ({ name, args }))).toEqual(seed.expected_calls);
  }
  expect((await backend.state<InstructionState>()).run_count).toBe(before.run_count + 1);
  await testInfo.attach(`instruction-retention-${surface}-proof`, { contentType: "application/json", body: Buffer.from(JSON.stringify({
    inference: real ? "actual existing local llama.cpp / no scripted model" : "deterministic inference / native graph",
    surface, recovered_task_sha256: originalTaskHash, original, final: row,
    compacted_work_inputs: compactedInputs, context_reductions: reductions, history_proofs: historyProofs,
    action_exchanges: actionExchanges,
    model_identity: backend.seed.real_model_identity,
    admission: real && surface === "Agent run" ? "Public exact setup; actual screen approval/observation" : "Actual screen composer",
  }, null, 2)) });
}
