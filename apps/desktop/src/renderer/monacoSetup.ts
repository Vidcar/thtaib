/** Load Monaco from this desktop package. Never from a CDN. */

let configured = false;

export async function ensureMonaco(): Promise<void> {
  if (configured || typeof window === "undefined") return;
  configured = true;
  const [{ loader }, monaco, worker] = await Promise.all([
    import("@monaco-editor/react"),
    import("monaco-editor/editor/editor.api"),
    import("monaco-editor/editor/editor.worker?worker"),
  ]);
  self.MonacoEnvironment = {
    getWorker() {
      return new worker.default();
    },
  };
  loader.config({ monaco });
}

export function editorTheme(): "vs" | "vs-dark" {
  if (typeof document === "undefined") return "vs-dark";
  const explicit = document.documentElement.dataset.theme;
  if (explicit === "light") return "vs";
  if (explicit === "dark") return "vs-dark";
  return window.matchMedia?.("(prefers-color-scheme: light)").matches ? "vs" : "vs-dark";
}
