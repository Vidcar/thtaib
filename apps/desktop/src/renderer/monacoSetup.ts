/** Load Monaco from this desktop package. Never from a CDN. */

let configured = false;
let monacoApi: typeof import("monaco-editor/editor/editor.api") | null = null;

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
  monacoApi = monaco;
  syncMonacoFromDocument();
}

export function editorTheme(): string {
  return "workbench";
}

export function editorFontSize(): number {
  if (typeof document === "undefined") return 14;
  const parsed = Number.parseFloat(getComputedStyle(document.documentElement).getPropertyValue("--font-editor"));
  return Number.isFinite(parsed) && parsed > 0 ? parsed : 14;
}

export function syncMonacoFromDocument(): void {
  if (!monacoApi || typeof document === "undefined") return;
  const style = getComputedStyle(document.documentElement);
  const read = (name: string) => style.getPropertyValue(name).trim();
  const explicit = document.documentElement.dataset.theme;
  const light = explicit === "light" || (explicit !== "dark" && window.matchMedia?.("(prefers-color-scheme: light)").matches);
  try {
    monacoApi.editor.defineTheme("workbench", {
      base: light ? "vs" : "vs-dark",
      inherit: true,
      rules: [],
      colors: {
        "editor.background": read("--bg-panel") || (light ? "#fafafa" : "#252525"),
        "editor.foreground": read("--text") || (light ? "#222222" : "#ececec"),
        "editorLineNumber.foreground": read("--muted") || (light ? "#6b6b6b" : "#a4a4a4"),
        "editor.selectionBackground": read("--accent") || (light ? "#7250b8" : "#b5a2ed"),
        "editorCursor.foreground": read("--text") || (light ? "#222222" : "#ececec"),
      },
    });
    monacoApi.editor.setTheme("workbench");
    const fontSize = editorFontSize();
    for (const editor of monacoApi.editor.getEditors()) editor.updateOptions({ fontSize });
  } catch {
    // The editor keeps the previous theme when a colour value is not ready.
  }
}
