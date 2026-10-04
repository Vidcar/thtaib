import { test as base, expect, type Page } from "@playwright/test";
import { startBackend, type BackendHandle } from "./backend";

export const test = base.extend<{ backend: BackendHandle; openWorkbench: () => Promise<void>; rendererHealth: void }>({
  rendererHealth: [async ({ page, backend }, use, testInfo) => {
    const errors: Array<{ message: string; stack?: string }> = [];
    const redact = (text: string) => text.replaceAll(backend.token, "[redacted]");
    page.on("pageerror", error => errors.push({ message: redact(error.message), stack: error.stack ? redact(error.stack) : undefined }));
    if (process.env.WORKBENCH_UI_NEGATIVE_CONTROL === "uncaught-error") {
      await page.addInitScript(() => {
        window.addEventListener("load", () => setTimeout(() => { throw new Error("Deliberate renderer gate negative control"); }, 0));
      });
    }
    try {
      await use();
    } finally {
      await testInfo.attach("uncaught-renderer-errors", { body: JSON.stringify({ errors }, null, 2), contentType: "application/json" });
      expect(errors, "The rendered application must have no uncaught browser errors").toEqual([]);
    }
  }, { auto: true }],
  backend: async ({}, use, testInfo) => {
    const backend = await startBackend();
    try {
      await use(backend);
    } finally {
      try {
        const evidence = await backend.state().catch(() => ({ diagnostics_unavailable: true }));
        const safe = JSON.stringify(evidence, (key, value) => ["token", "authorization", "x-workbench-local-token"].includes(key.toLowerCase()) ? undefined : value, 2).replaceAll(backend.token, "[redacted]");
        if (process.env.WORKBENCH_UI_NEGATIVE_CONTROL === "attachment-failure") {
          const modelPids = (evidence as { deployments?: Array<{ pid: number | null }> }).deployments?.map(deployment => deployment.pid).filter(pid => pid !== null) ?? [];
          throw new Error(`Baseline evidence attachment failed; owned identities ${JSON.stringify({ backend_pid: backend.pid, model_pids: modelPids, data_root: backend.dataRoot })}`);
        }
        await testInfo.attach("isolated-backend-state", { body: safe, contentType: "application/json" });
      } finally {
        await backend.close();
      }
    }
  },
  openWorkbench: async ({ page, backend }, use, testInfo) => {
    const attached = await fetch("http://127.0.0.1:5173/__ui__/backend", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ origin: backend.browserOrigin }), signal: AbortSignal.timeout(5000) });
    if (!attached.ok) throw new Error("The actual renderer server could not attach its isolated backend boundary.");
    // This ordinary preload-shaped public metadata includes no authentication secret.
    await page.addInitScript(({ backendUrl }) => {
      Object.defineProperty(window, "workbench", { configurable: true, value: { backendUrl, productName: "Local AI Workbench", surface: "managed-inference" } });
    }, { backendUrl: "http://127.0.0.1:5173" });
    try {
      await use(async () => {
        await page.goto("http://127.0.0.1:5173");
        await page.getByRole("button", { name: "Baseline conversation", exact: true }).click();
        await expect(page.getByText("Saved baseline answer", { exact: true })).toBeVisible();
        await expect(page.getByRole("textbox", { name: "Message", exact: true })).toBeEditable();
      });
    } finally {
      // The UI owns its SDK observer; finish it before stopping the backend dependency.
      try {
        if (!page.isClosed()) {
          const capture = testInfo.outputPath("rendered-workbench.png");
          await page.screenshot({ path: capture, timeout: 5000 });
          await testInfo.attach("rendered-workbench", { path: capture, contentType: "image/png" });
        }
      } finally {
        await page.close();
      }
    }
  },
});

export { expect };

export async function productJson<T>(page: Page, backend: BackendHandle, route: string): Promise<T> {
  if (!route.startsWith("/v1/")) throw new Error("Product evidence must read an actual product route.");
  const response = await page.request.get(backend.browserOrigin + route);
  if (!response.ok()) throw new Error(`Product read ${route} failed (${response.status()}).`);
  return await response.json() as T;
}

export async function submit(page: Page, text: string): Promise<void> {
  const message = page.getByRole("textbox", { name: "Message", exact: true });
  await expect(message).toBeEditable();
  await message.fill(text);
  const send = page.getByRole("button", { name: "Send", exact: true });
  await expect(send).toBeEnabled();
  await send.click();
}
