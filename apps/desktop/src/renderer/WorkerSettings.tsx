import { useEffect, useState } from "react";
import { api } from "./api";
import { Notice } from "./Notice";
import { errorMessage } from "./errors";
import type { BrowserRuntimeStatus, WindowRuntimeStatus } from "./types";

export function WorkerSettings() {
  const [browser, setBrowser] = useState<BrowserRuntimeStatus | null>(null);
  const [windows, setWindows] = useState<WindowRuntimeStatus | null>(null);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  useEffect(() => {
    let stale = false;
    void Promise.allSettled([api.browserRuntime(), api.windowRuntime()]).then(([browserResult, windowsResult]) => {
      if (stale) return;
      if (browserResult.status === "fulfilled") setBrowser(browserResult.value);
      if (windowsResult.status === "fulfilled") setWindows(windowsResult.value);
      const failure = [browserResult, windowsResult].find(result => result.status === "rejected");
      if (failure?.status === "rejected") setError(errorMessage(failure.reason));
    });
    return () => { stale = true; };
  }, []);
  async function install(kind: "browser" | "windows") {
    setBusy(kind); setError("");
    try { if (kind === "browser") setBrowser(await api.installBrowserRuntime()); else setWindows(await api.installWindowRuntime()); }
    catch (failure) { setError(errorMessage(failure)); }
    finally { setBusy(""); }
  }
  return <section className="setting-section worker-settings"><header className="setting-section-head"><h3>Browser & Windows</h3></header><div className="setting-rows">
    <div className="setting-row"><span>Browser worker</span><span className="hint">{browser?.supported === false ? "Unsupported" : browser?.installed ? browser.chrome_available === false ? "Needs Chrome" : "Installed" : browser ? "Not installed" : "Checking"}</span>{browser && !browser.installed && browser.supported !== false ? <button type="button" disabled={Boolean(busy)} onClick={() => void install("browser")}>{busy === "browser" ? "Installing…" : "Install browser worker"}</button> : null}</div>
    <div className="setting-row"><span>Windows worker</span><span className="hint">{windows?.available ? "Ready" : windows?.installed ? windows.reason ?? "Unavailable" : windows ? "Not installed" : "Checking"}</span>{windows && !windows.installed ? <button type="button" disabled={Boolean(busy)} onClick={() => void install("windows")}>{busy === "windows" ? "Installing…" : "Install Windows worker"}</button> : null}</div>
    {error ? <Notice tone="error">{error}</Notice> : null}
  </div></section>;
}
