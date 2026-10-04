import { expect, type Page, type TestInfo } from "@playwright/test";
import { createHash } from "node:crypto";
import type { BackendHandle } from "./backend";
import { navigateModels, openSurface, send, type SendingSurface } from "./sending";

interface Message {
  id: string; type: string; content: string | Array<{ type: string; text?: string }>;
  tool_call_id?: string; name?: string; tool_calls?: Array<{ id: string; name: string; args: unknown }>;
}
interface CompactionSeed {
  task: string; followup_task: string; marker: string; internal_summary_marker: string;
  tools: string[]; request_settings: Record<string, unknown>; expected_read_count: number;
  write_path: string; write_content: string; tool_start_marker: string; tool_end_marker: string;
}
interface CompactionRow {
  thread_id: string; source_surface: string; run_id: string;
  archive: Message[]; canonical: Message[]; cutoff_index: number; native_summary_count: number;
  offload_readable: boolean; read_count: number; write_count: number;
  write_content: string; original_tool_results: Message[];
  model_calls: Array<{ purpose: string; input_tokens?: number; message_ids?: string[]; phase?: string }>;
  native_input_counts: Array<{ ordinal: number; run_id: string; purpose: string; input_tokens: number | null; tools_sha256: string | null; basis: "native" | "estimated" | "unavailable" }>;
  native_input_capture_errors: unknown[];
}
interface CompactionState {
  seed: BackendHandle["seed"]; run_count: number; run_ids: string[]; input_ids: string[];
  runs: Array<{ id: string; status: string; input_message_id: string; tool_invocations: Array<{ name: string }> }>;
  faults: { stream_disconnects: number }; compaction: { rows: CompactionRow[] };
  pending_interrupts: Array<{ run_id: string }>;
}
const text = (message: Message) => typeof message.content === "string" ? message.content
  : message.content.filter(block => block.type === "text").map(block => block.text ?? "").join("");
const transcript = (page: Page, surface: SendingSurface) => page.locator(surface === "Chat" ? ".persistent-chat .message-feed" : ".workflow-surface .message-feed");
const messagesOnly = (messages: Message[]) => messages.map(message => ({
  id: message.id, type: message.type, content: message.content,
  ...(message.tool_calls?.length ? { tool_calls: message.tool_calls } : {}),
  ...(message.tool_call_id ? { tool_call_id: message.tool_call_id } : {}),
}));

export async function prepareCompaction(backend: BackendHandle): Promise<void> {
  backend.seed = (await backend.control<CompactionState>("/__test__/scenario", { scenario: "compaction_history" })).seed;
}

async function rowFor(backend: BackendHandle, runId: string): Promise<CompactionRow> {
  const rows = (await backend.state<CompactionState>()).compaction.rows;
  const row = rows.find(item => item.run_id === runId);
  expect(row, "The actual run must have independently observed native compaction evidence").toBeDefined();
  return row!;
}

async function readPublic(page: Page, backend: BackendHandle, thread: string): Promise<Message[]> {
  const response = await page.request.get(`${backend.browserOrigin}/v1/agent-interaction/threads/${encodeURIComponent(thread)}/state`);
  expect(response.status()).toBe(200);
  return (await response.json() as { values: { messages: Message[] } }).values.messages;
}

/** Exact public IDs/content and actual rendered source text are separate checks.
 * Tool results render under their matching assistant call, rather than a second bubble. */
async function assertHistory(page: Page, backend: BackendHandle, surface: SendingSurface, row: CompactionRow, expected = row.archive) {
  const published = await readPublic(page, backend, row.thread_id);
  expect(messagesOnly(published)).toEqual(messagesOnly(expected));
  const bubbles = expected.filter(message => message.type !== "tool" && message.type !== "system"
    && (text(message) || message.tool_calls?.length));
  const feed = transcript(page, surface);
  await expect.poll(async () => feed.locator("article[data-message-id]").evaluateAll(elements => elements.map(element => ({
    id: element.getAttribute("data-message-id"),
    content: element.querySelector(".message-answer")?.getAttribute("data-markdown-source")
      ?? element.querySelector(".user-message-text")?.textContent ?? "",
  })))).toEqual(bubbles.map(message => ({ id: message.id, content: text(message) })));
  // Expand ordinary tool detail disclosures, preserving their actual display order.
  const details = feed.locator("details.message-tools");
  for (let index = 0; index < await details.count(); index++) {
    const detail = details.nth(index);
    if (await detail.getAttribute("open") === null) await detail.locator(":scope > summary").click();
  }
  const results = expected.filter(message => message.type === "tool").map(text);
  await expect.poll(async () => feed.locator('section[aria-label="Tool output"] code').allTextContents()).toEqual(results);
  expect(new Set(expected.map(message => message.id)).size, "Visible history identities stay unique").toBe(expected.length);
  return { public_ids: published.map(message => message.id),
    rendered_ids: await feed.locator("article[data-message-id]").evaluateAll(elements => elements.map(element => element.getAttribute("data-message-id"))),
    public_sha256: createHash("sha256").update(JSON.stringify(messagesOnly(published))).digest("hex"),
    expected_sha256: createHash("sha256").update(JSON.stringify(messagesOnly(expected))).digest("hex"),
    tool_result_sha256: createHash("sha256").update(JSON.stringify(await feed.locator('section[aria-label="Tool output"] code').allTextContents())).digest("hex"),
  };
}

async function openAttentionAgent(page: Page, runId: string, kind: "Completed" | "Approval needed" = "Completed"): Promise<void> {
  await page.getByRole("button", { name: /^Attention,/ }).click();
  const attention = page.getByRole("region", { name: "Attention", exact: true });
  await expect(attention).toBeVisible();
  const items = attention.getByRole("listitem").filter({ hasText: kind });
  await expect(items.first()).toBeVisible();
  let opened = false;
  for (let index = 0; index < await items.count(); index++) {
    const item = items.nth(index);
    // The previous actual help bubble can cover the following item's trigger.
    await attention.getByRole("heading", { name: "Attention", exact: true }).hover();
    await expect(page.getByRole("tooltip")).toHaveCount(0);
    await item.getByRole("button", { name: "Item details", exact: true }).hover();
    await expect(page.getByRole("tooltip")).toBeVisible();
    if (await page.getByRole("tooltip").filter({ hasText: `Run: ${runId}` }).isVisible()) {
      await attention.getByRole("heading", { name: "Attention", exact: true }).hover();
      await expect(page.getByRole("tooltip")).toHaveCount(0);
      await item.getByRole("button", { name: "Open", exact: true }).click();
      opened = true; break;
    }
  }
  expect(opened, "Open this retained run through its actual Attention identity").toBe(true);
}

async function enableCompletionNotice(page: Page, backend: BackendHandle): Promise<void> {
  // Completed Agent runs are offered by the existing opt-in notification owner.
  // This notice is opened once, after reload/restart; Open then dismisses it.
  await page.getByRole("button", { name: "Settings", exact: true }).click();
  const settings = page.getByRole("region", { name: "Recovery and settings", exact: true });
  await settings.getByRole("button", { name: "Notifications", exact: true }).click();
  const completion = settings.getByRole("switch", { name: "Notify when work finishes", exact: true });
  await expect(completion).toBeEnabled();
  if (await completion.getAttribute("aria-checked") !== "true") await completion.click();
  await expect(completion).toHaveAttribute("aria-checked", "true");
  await expect.poll(async () => {
    const response = await page.request.get(`${backend.browserOrigin}/v1/settings/presentation`);
    expect(response.status()).toBe(200);
    return (await response.json() as { success_notifications: boolean }).success_notifications;
  }).toBe(true);
}

function assertNativeReduction(row: CompactionRow, real: boolean) {
  expect(row.native_input_capture_errors, "Counter observation must retain complete evidence").toEqual([]);
  const counts = [...row.native_input_counts].sort((left, right) => left.ordinal - right.ordinal);
  const reductions: Array<{ before: number; after: number; before_ordinal: number; after_ordinal: number; basis: string; tools_sha256: string }> = [];
  let previousWork: typeof counts[number] | undefined, summarized = false;
  for (const count of counts) {
    if (count.purpose === "summary") { summarized = true; continue; }
    // Partial retention slices omit tools; only complete schema-bearing work
    // projections/counters can establish before/after active request pressure.
    if (count.purpose !== "work" || !count.tools_sha256 || count.input_tokens === null) continue;
    if (summarized && previousWork?.input_tokens != null && count.input_tokens < previousWork.input_tokens
      && count.tools_sha256 === previousWork.tools_sha256 && count.basis === previousWork.basis) {
      reductions.push({ before: previousWork.input_tokens, after: count.input_tokens,
        before_ordinal: previousWork.ordinal, after_ordinal: count.ordinal, basis: count.basis, tools_sha256: count.tools_sha256 });
    }
    previousWork = count; summarized = false;
  }
  expect(reductions.length, "Observed prospective work context must shrink across a native summary boundary").toBeGreaterThan(0);
  if (real) expect(reductions.some(reduction => reduction.basis === "native"), "Actual work uses the runtime's existing native counter").toBe(true);
  return reductions;
}

function assertOriginalToolResult(row: CompactionRow, seed: CompactionSeed) {
  const originals = row.original_tool_results.filter(message => message.type === "tool" && text(message).includes(seed.tool_start_marker));
  expect(originals, "Capture the actual original emitted result independently of the display archive").toHaveLength(1);
  const original = originals[0];
  expect(text(original)).toContain(seed.tool_end_marker);
  const displayed = row.archive.find(message => message.id === original.id);
  expect(displayed && messagesOnly([displayed])).toEqual(messagesOnly([original]));
  const clipped = row.canonical.find(message => message.id === original.id);
  expect(clipped, "The native checkpoint must retain the same result identity").toBeDefined();
  expect(text(clipped!).length).toBeLessThan(text(original).length);
  expect(text(clipped!)).not.toContain(seed.tool_end_marker);
  return { id: original.id, original_length: text(original).length, canonical_length: text(clipped!).length,
    original_sha256: createHash("sha256").update(text(original)).digest("hex"),
    canonical_sha256: createHash("sha256").update(text(clipped!)).digest("hex"),
    original_contains_end_marker: text(original).includes(seed.tool_end_marker),
    canonical_contains_end_marker: text(clipped!).includes(seed.tool_end_marker) };
}

/** Stock graph summarization, real file tools and durable history run in both
 * modes; deterministic inference alone is scripted. */
export async function compactionHistory(page: Page, backend: BackendHandle, surface: SendingSurface, testInfo: TestInfo, real = false): Promise<void> {
  const seed = backend.seed.compaction as CompactionSeed;
  expect(seed.task).toBeTruthy();
  const before = await backend.state<CompactionState>();
  if (surface === "Agent run") await enableCompletionNotice(page, backend);
  await openSurface(page, backend, surface);
  const negative = {
    "overwritten-history": "compaction_overwritten_history", "visible-summary": "compaction_visible_summary",
    "duplicate-compaction-execution": "compaction_duplicate_execution",
  }[process.env.WORKBENCH_UI_NEGATIVE_CONTROL ?? ""];
  await backend.control("/__test__/scenario", { disconnect_next_stream: true, ...(negative ? { negative_control: negative } : {}) });
  if (real && surface === "Agent run") {
    // The task form cannot author an exact tool/request configuration. Admit it
    // through the public owner, then open/approve/observe the actual Agent screen.
    const admitted = await page.request.post(`${backend.browserOrigin}/v1/agent-runs`, { data: {
      deployment_id: backend.seed.deployment_id, project_id: backend.seed.project_id,
      task: seed.task, presented_tools: seed.tools, per_request_overrides: seed.request_settings,
      approval_mode: "ask", input_policy: { tool_loading: "always" },
    } });
    expect(admitted.status()).toBe(200);
    const run = await admitted.json() as { id: string };
    await expect.poll(async () => (await backend.state<CompactionState>()).pending_interrupts.filter(item => item.run_id === run.id).length,
      { timeout: 120_000 }).toBe(1);
    await openAttentionAgent(page, run.id, "Approval needed");
  } else await send(page, surface, seed.task);
  await expect.poll(async () => (await backend.state<CompactionState>()).run_count).toBe(before.run_count + 1);
  if (surface === "Agent run") {
    const approval = page.getByRole("alertdialog", { name: /Review requested actions/ });
    await expect(approval).toBeVisible();
    await approval.getByRole("radio", { name: "Approve once", exact: true }).check();
    await approval.getByRole("button", { name: "Send decisions", exact: true }).click();
  }
  await expect.poll(async () => (await backend.state<CompactionState>()).runs.at(-1)?.status,
    { timeout: real ? 240_000 : 30_000 }).toBe("completed");
  let state = await backend.state<CompactionState>();
  const runId = state.run_ids.at(-1)!;
  expect(state.run_count).toBe(before.run_count + 1);
  expect(new Set(state.input_ids).size).toBe(state.run_count);
  expect(state.faults.stream_disconnects).toBe(before.faults.stream_disconnects + 1);
  let row = await rowFor(backend, runId);
  const historyProofs: Array<{ stage: string; proof: Awaited<ReturnType<typeof assertHistory>> }> = [];
  expect(row.native_summary_count).toBeGreaterThanOrEqual(real ? 1 : 2);
  expect(row.cutoff_index).toBeGreaterThan(0);
  expect(row.offload_readable).toBe(true);
  expect(row.write_count).toBe(1);
  expect(row.read_count).toBe(seed.expected_read_count);
  expect(row.model_calls.some(call => call.purpose === "summary")).toBe(true);
  expect(row.model_calls.some(call => call.purpose === "work")).toBe(true);
  const contextReductions = assertNativeReduction(row, real);
  const originalResult = assertOriginalToolResult(row, seed);
  expect(row.write_content).toBe(seed.write_content);
  expect(JSON.stringify(row.canonical)).not.toBe(JSON.stringify(row.archive));
  expect(JSON.stringify(row.archive)).not.toContain(seed.internal_summary_marker);
  if (real) expect(text(row.archive.at(-1)!)).toContain(seed.marker);
  historyProofs.push({ stage: "completed after disconnect", proof: await assertHistory(page, backend, surface, row) });
  const original = structuredClone(row.archive);
  await navigateModels(page);
  await openSurface(page, backend, surface);
  historyProofs.push({ stage: "navigation", proof: await assertHistory(page, backend, surface, row, original) });
  if (surface === "Chat") {
    await page.reload();
    await openSurface(page, backend, surface);
    historyProofs.push({ stage: "reload", proof: await assertHistory(page, backend, surface, row, original) });
    if (real) {
      await send(page, surface, seed.followup_task);
      await expect.poll(async () => (await backend.state<CompactionState>()).run_count).toBe(before.run_count + 2);
      await expect.poll(async () => (await backend.state<CompactionState>()).runs.at(-1)?.status, { timeout: 120_000 }).toBe("completed");
      state = await backend.state<CompactionState>();
      row = await rowFor(backend, state.run_ids.at(-1)!);
      expect(messagesOnly(row.archive.slice(0, original.length))).toEqual(messagesOnly(original));
      expect(text(row.archive.at(-1)!)).toContain(seed.marker);
      expect(row.write_count).toBe(1);
      historyProofs.push({ stage: "retained fact followup", proof: await assertHistory(page, backend, surface, row) });
    }
  }
  if (!real) {
    const preserved = structuredClone(row.archive), previousPid = backend.pid;
    await backend.restart();
    expect(backend.pid).not.toBe(previousPid);
    await page.reload();
    if (surface === "Chat") await openSurface(page, backend, surface);
    else await openAttentionAgent(page, runId);
    historyProofs.push({ stage: "completed backend restart and reload", proof: await assertHistory(page, backend, surface, row, preserved) });
    state = await backend.state<CompactionState>();
    expect(state.run_ids).toEqual(before.run_ids.concat(runId));
    expect(state.run_count).toBe(before.run_count + 1);
    row = await rowFor(backend, runId);
    expect(row.write_count).toBe(1);
    expect(row.read_count).toBe(seed.expected_read_count);
    expect(row.write_content).toBe(seed.write_content);
    assertOriginalToolResult(row, seed);
  } else if (surface === "Agent run") {
    // The task form deliberately starts a new thread. Reopen the retained
    // completed run through Attention rather than submitting another task.
    await page.reload();
    await openAttentionAgent(page, runId);
    historyProofs.push({ stage: "reload and completed Attention reopen", proof: await assertHistory(page, backend, surface, row, original) });
    expect((await backend.state<CompactionState>()).run_count).toBe(before.run_count + 1);
  }
  await testInfo.attach(`compaction-${surface}-history`, { contentType: "application/json", body: Buffer.from(JSON.stringify({
    inference: real ? "actual local llama.cpp" : "deterministic inference / native graph", surface,
    original, final: row, context_reductions: contextReductions, original_tool_result: originalResult,
    history_proofs: historyProofs, model_identity: backend.seed.real_model_identity,
    reopening: surface === "Agent run"
      ? "Existing completion notifications explicitly enabled in Settings; one undismissed Completed notice opened after reload/restart, then dismissed by Open"
      : "Existing saved Chat selection",
    admission: real && surface === "Agent run" ? "Authored exact setup through public API, approved and observed in actual Agent screen" : "Actual screen composer",
  }, null, 2)) });
}
