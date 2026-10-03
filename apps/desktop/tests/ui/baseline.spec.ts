import { test, expect, productJson, submit } from "./shared/fixtures";
import { readFile } from "node:fs/promises";

interface Conversation {
  draft?: { content?: string };
  transcript: Array<{ id: string; role: string; text?: string; content?: string; run_id?: string }>;
  run_ids: string[];
  current_run?: { id: string; status: string; pending_interrupt?: { interrupt_id: string; namespace?: string[] } } | null;
}

interface Deployment {
  id: string;
  status: string;
  profile_id: string | null;
  pid: number | null;
  process_identity: { pid: number; create_time: number } | null;
  applied_startup: Record<string, unknown>;
  profile_snapshot: { startup: { applied: Record<string, unknown> } } | null;
}

test("restored history and unsent draft survive reopening", async ({ page, backend, openWorkbench }) => {
  await openWorkbench();
  await expect(page.getByText("Saved baseline question", { exact: true })).toBeVisible();
  const draft = "Unsent draft must survive reopening";
  await page.getByRole("textbox", { name: "Message", exact: true }).fill(draft);
  await page.getByRole("button", { name: "Models", exact: true }).click();
  await expect.poll(async () => (await productJson<Conversation>(page, backend, `/v1/chat/conversations/${backend.seed.conversation_id}`)).draft?.content).toBe(draft);
  if (process.env.WORKBENCH_UI_NEGATIVE_CONTROL === "lose-draft") await backend.control("/__test__/scenario", { negative_control: "lose_draft" });
  await page.reload();
  await page.getByRole("button", { name: "Chat", exact: true }).click();
  await expect(page.getByText("Saved baseline answer", { exact: true })).toBeVisible();
  await expect(page.getByText("Saved baseline question", { exact: true })).toBeVisible();
  await expect(page.getByRole("textbox", { name: "Message", exact: true })).toHaveValue(draft);
  const saved = await productJson<Conversation>(page, backend, `/v1/chat/conversations/${backend.seed.conversation_id}`);
  expect(saved.transcript.filter(message => message.role === "user")).toHaveLength(1);
  expect((await backend.state<{ run_count: number }>()).run_count).toBe(0);
});

test("accepted lost acknowledgement and reconnect execute once", async ({ page, backend, openWorkbench }) => {
  await openWorkbench();
  const before = await productJson<Conversation>(page, backend, `/v1/chat/conversations/${backend.seed.conversation_id}`);
  await backend.control("/__test__/scenario", { scenario: "lost_ack", lose_next_ack: true });
  const text = "Execute this accepted input exactly once";
  await submit(page, text);
  await expect.poll(async () => (await productJson<Conversation>(page, backend, `/v1/chat/conversations/${backend.seed.conversation_id}`)).run_ids.length).toBe(before.run_ids.length + 1);
  await page.reload();
  await expect(page.getByText(text, { exact: true })).toHaveCount(1);
  await expect(page.getByText("Baseline response completed", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Send", exact: true })).toBeVisible();
  const after = await productJson<Conversation>(page, backend, `/v1/chat/conversations/${backend.seed.conversation_id}`);
  expect(after.run_ids).toHaveLength(before.run_ids.length + 1);
  const accepted = after.transcript.filter(message => message.role === "user" && (message.text ?? message.content) === text);
  expect(accepted).toHaveLength(1);
  expect(new Set(accepted.map(message => message.id)).size).toBe(1);
  const acknowledged = await backend.state<{ run_count: number; run_ids: string[]; input_ids: string[]; model_factory_run_ids: string[]; faults: { lost_acknowledgements: number } }>();
  expect(acknowledged.run_count).toBe(1);
  expect(acknowledged.input_ids).toHaveLength(1);
  for (const runId of acknowledged.run_ids) expect(acknowledged.model_factory_run_ids.filter(id => id === runId)).toHaveLength(1);
  expect(acknowledged.faults.lost_acknowledgements).toBe(1);
  const reconnectText = "Reconnect this running input without duplicating it";
  await backend.control("/__test__/scenario", { disconnect_next_stream: true, hold_model: true });
  await submit(page, reconnectText);
  await expect.poll(async () => (await backend.state<{ run_count: number }>()).run_count).toBe(2);
  await expect.poll(async () => (await backend.state<{ faults: { stream_disconnects: number } }>()).faults.stream_disconnects).toBe(1);
  await backend.control("/__test__/scenario", { release_model: true });
  // Completion must recover through the installed SDK without a manual page reload.
  await expect(page.getByText(reconnectText, { exact: true })).toHaveCount(1);
  await expect(page.getByText("Baseline response completed", { exact: true })).toHaveCount(2);
  await expect(page.getByRole("button", { name: "Send", exact: true })).toBeVisible();
  const faults = await backend.state<{ run_count: number; run_ids: string[]; input_ids: string[]; model_factory_run_ids: string[]; faults: { stream_disconnects: number } }>();
  expect(faults.run_count).toBe(2);
  expect(new Set(faults.input_ids).size).toBe(2);
  for (const runId of faults.run_ids) expect(faults.model_factory_run_ids.filter(id => id === runId)).toHaveLength(1);
  expect(faults.faults.stream_disconnects).toBe(1);
});

test("scoped approval and Stop govern actual owned effects", async ({ page, backend, openWorkbench }) => {
  await openWorkbench();
  await backend.control("/__test__/scenario", { scenario: "approval" });
  await submit(page, "Write the approved baseline file");
  const approval = page.getByRole("alertdialog", { name: /Review requested actions/ });
  await expect(approval).toBeVisible();
  await expect(approval).toContainText("approved.txt");
  const pending = await backend.state<{ approved_file_exists: boolean }>();
  expect(pending.approved_file_exists).toBe(false);
  const pendingConversation = await productJson<Conversation>(page, backend, `/v1/chat/conversations/${backend.seed.conversation_id}`);
  expect(pendingConversation.current_run?.pending_interrupt?.interrupt_id).toBeTruthy();
  const foreignDecision = await page.request.post(`${backend.browserOrigin}/v1/agent-runs/${pendingConversation.current_run!.id}/interrupt-decision`, {
    data: { interrupt_id: pendingConversation.current_run!.pending_interrupt!.interrupt_id, namespace: ["foreign"], decisions: [{ type: "approve" }] },
  });
  expect(foreignDecision.status()).toBe(409);
  expect((await backend.state<{ approved_file_exists: boolean }>()).approved_file_exists).toBe(false);
  await expect(approval).toBeVisible();
  await approval.getByRole("radio", { name: "Approve once", exact: true }).check();
  await approval.getByRole("button", { name: "Send decisions", exact: true }).click();
  await expect(approval).toBeHidden();
  await expect.poll(async () => readFile(String(backend.seed.owned_effect_path), "utf8").catch(() => "")).toBe("Approved baseline output");
  await expect(page.getByText("Baseline file operation completed", { exact: true })).toBeVisible();
  await backend.control("/__test__/scenario", { scenario: "command", hold_model: true });
  await submit(page, "Start the owned baseline command");
  const commandApproval = page.getByRole("alertdialog", { name: /Review requested actions/ });
  await expect(commandApproval).toBeVisible();
  await commandApproval.getByRole("radio", { name: "Approve once", exact: true }).check();
  await commandApproval.getByRole("button", { name: "Send decisions", exact: true }).click();
  await expect.poll(async () => (await backend.state<{ commands: Array<{ pid: number; alive: boolean }> }>()).commands.filter(command => command.alive).length).toBe(1);
  await page.getByRole("button", { name: "Stop", exact: true }).click();
  await expect.poll(async () => (await backend.state<{ commands: Array<{ pid: number; alive: boolean }> }>()).commands.filter(command => command.alive).length).toBe(0);
  await expect(page.getByRole("button", { name: "Send", exact: true })).toBeVisible();
  const stopped = await productJson<Conversation>(page, backend, `/v1/chat/conversations/${backend.seed.conversation_id}`);
  expect(stopped.current_run?.status).toBe("cancelled");
});

test("model load reload and failure remain truthful", async ({ page, backend, openWorkbench }) => {
  await openWorkbench();
  await page.getByRole("button", { name: "Models", exact: true }).click();
  // The installed fixture has one genuine managed configuration; no connected-endpoint substitution.
  await expect(page.getByRole("heading", { name: "Baseline model", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Baseline setup", exact: true })).toBeVisible();
  const selectedModel = page.getByRole("region", { name: "Selected model", exact: true });
  const runtimeStatus = selectedModel.locator(".model-runtime-pill");
  await page.locator("summary").filter({ hasText: /^Loaded model/ }).click();
  const unload = page.getByRole("button", { name: "Unload", exact: true });
  await expect(unload).toBeVisible();
  await unload.click();
  await expect(runtimeStatus).toHaveText("Not loaded");
  await backend.control("/__test__/scenario", { hold_model_load: true });
  await page.getByRole("button", { name: "Load", exact: true }).click();
  await expect(page.getByRole("button", { name: "Loading…", exact: true })).toBeVisible();
  await expect(runtimeStatus).not.toHaveText("Ready");
  await backend.control("/__test__/scenario", { release_model_load: true });
  await expect(runtimeStatus).toHaveText("Ready");
  const beforeReload = (await productJson<Deployment[]>(page, backend, "/v1/deployments")).find(deployment => deployment.status === "running" && deployment.profile_id === backend.seed.profile_id);
  expect(beforeReload?.process_identity).toBeTruthy();
  await page.getByRole("button", { name: "Reload saved setup", exact: true }).click();
  await expect(page.getByText("Model reloaded.", { exact: true })).toBeVisible();
  const deployments = await productJson<Deployment[]>(page, backend, "/v1/deployments");
  const reloaded = deployments.find(deployment => deployment.status === "running" && deployment.profile_id === backend.seed.profile_id);
  expect(reloaded).toBeDefined();
  expect(reloaded!.pid).toBeGreaterThan(0);
  expect(reloaded!.process_identity?.pid).toBe(reloaded!.pid);
  expect(reloaded!.process_identity).not.toEqual(beforeReload!.process_identity);
  await expect.poll(async () => (await backend.state<{ model_processes: Array<{ pid: number; create_time: number; alive: boolean }> }>()).model_processes.find(identity => identity.pid === beforeReload!.process_identity!.pid && identity.create_time === beforeReload!.process_identity!.create_time)?.alive).toBe(false);
  expect(reloaded!.applied_startup).toEqual(reloaded!.profile_snapshot?.startup.applied);
  expect((await backend.state<{ deployments: Array<{ id: string; process_alive: boolean }> }>()).deployments.find(deployment => deployment.id === reloaded!.id)?.process_alive).toBe(true);
  await page.getByRole("button", { name: "Unload", exact: true }).click();
  await expect(runtimeStatus).toHaveText("Not loaded");
  await backend.control("/__test__/scenario", { fail_model_start: true });
  await page.getByRole("button", { name: "Load", exact: true }).click();
  await expect(selectedModel.getByRole("status")).toContainText("Baseline model load failed");
  await expect(runtimeStatus).not.toHaveText("Ready");
  const failed = await backend.state<{ deployments: Array<{ status: string; pid: number | null; process_alive: boolean; error: string | null }> }>();
  const failedAttempt = failed.deployments.find(deployment => deployment.error?.includes("Baseline model load failed"));
  expect(failedAttempt).toBeDefined();
  expect(failedAttempt?.status).toBe("failed");
  expect(failedAttempt?.process_alive).toBe(false);
  await backend.control("/__test__/scenario", { fail_model_start: false });
  await page.getByRole("button", { name: "Load", exact: true }).click();
  await expect(runtimeStatus).toHaveText("Ready");
});

test("retained output reopens after restart and source change", async ({ page, backend, openWorkbench }) => {
  backend.seed = await backend.control("/__test__/seed", { scenario: "retained" });
  await openWorkbench();
  await page.getByRole("button", { name: "Open conversation rail", exact: true }).click();
  const rail = page.getByRole("complementary", { name: "Conversation rail", exact: true });
  await rail.getByRole("tab", { name: "Files", exact: true }).click();
  const retained = rail.getByRole("region", { name: "Retained files", exact: true });
  await expect(retained.getByRole("button", { name: /^baseline-output\.txt/ }).first()).toBeVisible();
  await retained.getByRole("button", { name: /^baseline-output\.txt/ }).first().click();
  await expect(retained.getByText("Retained baseline output", { exact: true })).toBeVisible();
  const retainedId = (backend.seed.retained_asset_ids as string[])[0];
  const foreignPreview = await page.request.get(`${backend.browserOrigin}/v1/assets/${retainedId}/preview?session_id=foreign-session`);
  expect([403, 404]).toContain(foreignPreview.status());
  const permittedPreview = await productJson<{ preview: string }>(page, backend, `/v1/assets/${retainedId}/preview?session_id=${backend.seed.conversation_id}`);
  expect(permittedPreview.preview).toBe("Retained baseline output");
  const before = await productJson<Conversation>(page, backend, `/v1/chat/conversations/${backend.seed.conversation_id}`);
  await backend.control("/__test__/scenario", { change_source: true });
  await backend.restart();
  await page.reload();
  await expect(page.getByText("Saved baseline answer", { exact: true })).toBeVisible();
  await retained.getByRole("button", { name: /^baseline-output\.txt/ }).first().click();
  await expect(retained.getByText("Retained baseline output", { exact: true })).toBeVisible();
  await expect(retained.getByText("Source changed; retained copy preserved", { exact: true }).first()).toBeVisible();
  await expect(page.getByText("Changed source after retention", { exact: true })).toHaveCount(0);
  const after = await productJson<Conversation>(page, backend, `/v1/chat/conversations/${backend.seed.conversation_id}`);
  expect(after.run_ids).toEqual(before.run_ids);
});
