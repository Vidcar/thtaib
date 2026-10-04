import { expect, type Page } from "@playwright/test";
import { readFile } from "node:fs/promises";
import path from "node:path";
import type { BackendHandle } from "./backend";

export type SendingSurface = "Chat" | "Agent run";
export interface SendingState {
  run_count: number;
  run_ids: string[];
  input_ids: string[];
  model_factory_run_ids: string[];
  failed_lookup_paths: string[];
  submissions: Array<{ thread_id: string; payload: { params: { input: { messages: Array<{ id: string; content: string }> }; metadata: unknown } } }>;
  runs: Array<{ id: string; status: string; input_message_id: string; stop_reason: string | null; tool_invocations: Array<{ name: string }> }>;
  commands: Array<{ pid: number; alive: boolean }>;
  faults: { lost_acknowledgements: number; stream_disconnects: number; state_lookup_failures: number };
}

export async function openSurface(page: Page, backend: BackendHandle, surface: SendingSurface): Promise<void> {
  await page.getByRole("button", { name: surface === "Chat" ? "Chat" : "Workflows", exact: true }).click();
  if (surface === "Chat") {
    const title = backend.seed.real_model_identity ? "Real model conversation" : "Baseline conversation";
    if (!await page.getByRole("heading", { name: title, exact: true }).isVisible()) await page.getByRole("button", { name: title, exact: true }).click();
    await expect(page.getByRole("heading", { name: title, exact: true })).toBeVisible();
  } else {
    await page.getByRole("textbox", { name: "Project folder", exact: true }).fill(String(backend.seed.project_path));
  }
  await expect(editor(page, surface)).toBeEditable();
}
export const editor = (page: Page, surface: SendingSurface) => page.getByRole("textbox", { name: surface === "Chat" ? "Message" : "Task", exact: true });
export const sendButton = (page: Page, surface: SendingSurface) => page.getByRole("button", { name: surface === "Chat" ? "Send" : "Run task", exact: true });
export async function navigateModels(page: Page): Promise<void> {
  await page.getByRole("button", { name: "Models", exact: true }).click();
  // Chat navigation persists the current draft asynchronously; wait until that
  // destination opens before requesting another navigation.
  await expect(page.getByRole("heading", { name: "Models", exact: true })).toBeVisible();
}
export async function send(page: Page, surface: SendingSurface, text: string): Promise<void> {
  await editor(page, surface).fill(text);
  await expect(sendButton(page, surface)).toBeEnabled();
  await sendButton(page, surface).click();
}
export async function assertOneExecution(backend: BackendHandle, before: number): Promise<SendingState> {
  const state = await backend.state<SendingState>();
  expect(state.run_count).toBe(before + 1);
  expect(new Set(state.input_ids).size).toBe(state.run_count);
  const id = state.run_ids.at(-1)!;
  expect(state.model_factory_run_ids.filter(runId => runId === id)).toHaveLength(1);
  return state;
}

export async function acceptedLostResponse(page: Page, backend: BackendHandle, surface: SendingSurface, real = false): Promise<void> {
  await openSurface(page, backend, surface);
  const messages = page.locator(surface === "Chat" ? ".persistent-chat .message-feed" : ".workflow-surface .message-feed");
  const answersBefore = await messages.locator(".bubble-assistant .message-answer").count();
  const before = (await backend.state<SendingState>()).run_count;
  const text = real ? `Reply with the single word PONG. Sending check ${surface}.` : `Execute this ${surface} accepted input exactly once`;
  await backend.control("/__test__/scenario", { scenario: "lost_ack", lose_next_ack: true, ...(real ? {} : { hold_model: true }),
    ...(process.env.WORKBENCH_UI_NEGATIVE_CONTROL === "duplicate-execution" ? { negative_control: "duplicate_execution" } : {}) });
  await send(page, surface, text);
  await expect.poll(async () => (await backend.state<SendingState>()).run_count).toBe(before + 1);
  // No reload may conceal a stale error, an erased newer draft or unresolved acceptance.
  await expect(editor(page, surface)).toHaveValue("");
  await expect(page.getByText("Baseline acknowledgement lost after acceptance", { exact: false })).toHaveCount(0);
  await backend.control("/__test__/scenario", { release_model: true });
  await expect.poll(async () => (await backend.state<SendingState>()).runs.at(-1)?.status, { timeout: real ? 120_000 : 15_000 }).toBe("completed");
  if (!real) await expect(page.locator(surface === "Chat" ? ".persistent-chat .message-feed" : ".workflow-surface .message-feed").getByText("Baseline response completed", { exact: true })).toBeVisible();
  const state = await assertOneExecution(backend, before);
  expect(state.faults.lost_acknowledgements).toBeGreaterThan(0);
  const acceptedId = state.input_ids.at(-1)!;
  const original = state.submissions.at(-1)!;
  expect(original.payload.params.input.messages[0].id).toBe(acceptedId);
  // The Agent task appears twice (message + activity heading); scope the transcript.
  await expect(messages.locator(".user-message-text").getByText(text, { exact: true })).toHaveCount(1);
  if (real) {
    // Chat retains older replies; a nonempty old answer cannot prove this turn.
    await expect(messages.locator(".bubble-assistant .message-answer")).toHaveCount(surface === "Chat" ? answersBefore + 1 : 1);
    await expect(messages.locator(".bubble-assistant .message-answer").last()).not.toHaveText("");
  }
  await navigateModels(page);
  await openSurface(page, backend, surface);
  await expect(editor(page, surface)).toHaveValue("");
  expect((await backend.state<SendingState>()).run_count).toBe(before + 1);
}

export async function reconnectAcceptedWork(page: Page, backend: BackendHandle, surface: SendingSurface, real = false): Promise<void> {
  const messages = page.locator(surface === "Chat" ? ".persistent-chat .message-feed" : ".workflow-surface .message-feed");
  const answersBefore = await messages.locator(".bubble-assistant .message-answer").count();
  const before = (await backend.state<SendingState>()).run_count;
  const faultsBefore = (await backend.state<SendingState>()).faults.stream_disconnects;
  const text = real ? `Reply with the single word PONG. Reconnect check ${surface}.` : `Reconnect this ${surface} running input once`;
  await backend.control("/__test__/scenario", { scenario: "baseline", disconnect_next_stream: true, ...(real ? {} : { hold_model: true }) });
  await send(page, surface, text);
  await expect.poll(async () => (await backend.state<SendingState>()).faults.stream_disconnects).toBe(faultsBefore + 1);
  await backend.control("/__test__/scenario", { release_model: true });
  await expect.poll(async () => (await backend.state<SendingState>()).runs.at(-1)?.status, { timeout: real ? 120_000 : 15_000 }).toBe("completed");
  await expect(editor(page, surface)).toHaveValue("");
  if (!real) await expect(page.locator(surface === "Chat" ? ".persistent-chat .message-feed" : ".workflow-surface .message-feed").getByText("Baseline response completed", { exact: true }).last()).toBeVisible();
  await expect(messages.locator(".user-message-text").getByText(text, { exact: true })).toHaveCount(1);
  if (real) {
    await expect(messages.locator(".bubble-assistant .message-answer")).toHaveCount(surface === "Chat" ? answersBefore + 1 : 1);
    await expect(messages.locator(".bubble-assistant .message-answer").last()).not.toHaveText("");
  }
  await expect(sendButton(page, surface)).toBeDisabled();
  await assertOneExecution(backend, before);
}

export async function stopOwnedCommand(page: Page, backend: BackendHandle, surface: SendingSurface): Promise<void> {
  await openSurface(page, backend, surface);
  await backend.control("/__test__/scenario", { scenario: "command", hold_model: true });
  const task = `Start the owned ${surface} command`;
  if (surface === "Chat") await send(page, surface, task);
  else {
    // Existing saved Agent runs can have explicit tools. Seed that authored
    // selection through the public admission API and reopen via real Attention;
    // the legacy task form's default tool policy is outside this sending slice.
    const started = await page.request.post(`${backend.browserOrigin}/v1/agent-runs`, { data: {
      deployment_id: backend.seed.deployment_id, project_path: backend.seed.project_path, task,
      presented_tools: ["start_command", "command_status", "stop_command"], approval_mode: "ask", input_policy: { tool_loading: "always" },
    } });
    expect(started.status()).toBe(200);
    const run = await started.json() as { id: string };
    await expect.poll(async () => {
      const response = await page.request.get(`${backend.browserOrigin}/v1/agent-runs/${run.id}?view=diagnostic`);
      expect(response.status()).toBe(200);
      return Boolean((await response.json()).pending_interrupt);
    }).toBe(true);
    await page.getByRole("button", { name: /^Attention,/ }).click();
    // Attention's existing title is "Agent run", not the authored task text.
    const item = page.getByRole("region", { name: "Attention", exact: true }).getByRole("listitem").filter({ hasText: "Approval needed" });
    await expect(item).toHaveCount(1);
    await expect(item).toBeVisible();
    await item.getByRole("button", { name: "Open", exact: true }).click();
    await expect(page.locator(".workflow-surface .message-feed .user-message-text").getByText(task, { exact: true })).toHaveCount(1);
  }
  const approval = page.getByRole("alertdialog", { name: /Review requested actions/ });
  await expect(approval).toBeVisible();
  await approval.getByRole("radio", { name: "Approve once", exact: true }).check();
  await approval.getByRole("button", { name: "Send decisions", exact: true }).click();
  await expect.poll(async () => (await backend.state<SendingState>()).commands.filter(command => command.alive).length).toBe(1);
  await navigateModels(page);
  await openSurface(page, backend, surface);
  await page.getByRole("button", { name: surface === "Chat" ? "Stop" : "Cancel", exact: true }).click();
  await expect.poll(async () => (await backend.state<SendingState>()).commands.filter(command => command.alive).length).toBe(0);
  await expect.poll(async () => (await backend.state<SendingState>()).runs.at(-1)?.status).toBe("cancelled");
}

export async function assertRealFile(backend: BackendHandle): Promise<void> {
  const content = await readFile(path.join(String(backend.seed.project_path), "hello.txt"), "utf8");
  expect(content.trim()).toBe("hello from qwen");
}
