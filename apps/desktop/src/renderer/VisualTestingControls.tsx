import { useEffect, useState } from "react";
import { api } from "./api";
import { errorMessage } from "./errors";
import type { BrowserRuntimeStatus, BrowserSessionStatus, DesktopAccess, TestWindow, WindowAccessStatus, WindowRuntimeStatus } from "./types";
import "./VisualTestingControls.css";

export function VisualTestingControls({ conversationId, threadId, browserEnabled, onBrowserEnabled, desktopAccess, onDesktopAccess, onPrepareConversation, disabled = false, workMode = "work" }: {
  conversationId: string | null;
  threadId: string | null;
  browserEnabled: boolean;
  onBrowserEnabled: (enabled: boolean) => void;
  desktopAccess: DesktopAccess;
  onDesktopAccess: (scope: DesktopAccess) => void;
  onPrepareConversation?: () => Promise<void>;
  disabled?: boolean;
  workMode?: "work" | "plan";
}) {
  const [browserRuntime, setBrowserRuntime] = useState<BrowserRuntimeStatus | null>(null);
  const [browserSession, setBrowserSession] = useState<BrowserSessionStatus | null>(null);
  const [windowRuntime, setWindowRuntime] = useState<WindowRuntimeStatus | null>(null);
  const [windowAccess, setWindowAccess] = useState<WindowAccessStatus | null>(null);
  const [windows, setWindows] = useState<TestWindow[]>([]);
  const [choosingWindow, setChoosingWindow] = useState(false);
  const [selectedHwnd, setSelectedHwnd] = useState("");
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    let stale = false;
    setBrowserSession(null); setWindowAccess(null); setWindows([]); setChoosingWindow(false); setError("");
    void Promise.allSettled([
      api.browserRuntime(), api.windowRuntime(),
      threadId ? api.browserSession(threadId) : Promise.resolve(null),
      conversationId ? api.windowAccess(conversationId) : Promise.resolve(null),
    ]).then(([browser, native, session, access]) => {
      if (stale) return;
      if (browser.status === "fulfilled") setBrowserRuntime(browser.value);
      if (native.status === "fulfilled") setWindowRuntime(native.value);
      if (session.status === "fulfilled") setBrowserSession(session.value);
      if (access.status === "fulfilled") setWindowAccess(access.value);
      const failures = [browser, native, session, access].filter(item => item.status === "rejected");
      if (failures.length) setError(errorMessage((failures[0] as PromiseRejectedResult).reason));
    });
    return () => { stale = true; };
  }, [conversationId, threadId]);

  useEffect(() => {
    if (!threadId && !conversationId) return;
    let stale = false;
    const timer = window.setInterval(() => {
      if (threadId) void api.browserSession(threadId).then(value => { if (!stale) setBrowserSession(value); }).catch(() => {});
      if (conversationId) void api.windowAccess(conversationId).then(value => { if (!stale) setWindowAccess(value); }).catch(() => {});
    }, 5000);
    return () => { stale = true; window.clearInterval(timer); };
  }, [conversationId, threadId]);

  async function perform(label: string, action: () => Promise<void>) {
    setBusy(label); setError("");
    try { await action(); }
    catch (caught) { setError(errorMessage(caught)); }
    finally { setBusy(""); }
  }

  async function loadWindows() {
    await perform("windows", async () => {
      const choices = await api.testWindows();
      setWindows(choices);
      setSelectedHwnd(choices[0] ? String(choices[0].hwnd) : "");
      setChoosingWindow(true);
    });
  }

  async function changeWindows(next: DesktopAccess) {
    if (!conversationId) return;
    if (next === "selected") { await loadWindows(); return; }
    await perform("scope", async () => {
      const access = await api.setWindowAccess(conversationId, next);
      setWindowAccess(access); setChoosingWindow(false); onDesktopAccess(access.scope);
    });
  }

  return <section className="visual-testing-controls" aria-label="Visual testing">
    <h3>Visual testing</h3>
    <div className="visual-testing-row">
      <div className="visual-testing-description"><strong>Test browser</strong><span>Isolated pages and screenshots. A vision model is needed to judge an image; any model can inspect page structure.</span></div>
      {browserRuntime?.installed ? <label className="visual-testing-switch"><input type="checkbox" checked={browserEnabled} disabled={disabled || Boolean(busy)} onChange={event => onBrowserEnabled(event.target.checked)} /> Enable</label> : <button type="button" disabled={disabled || Boolean(busy) || browserRuntime?.supported === false} onClick={() => void perform("install-browser", async () => { setBrowserRuntime(await api.installBrowserRuntime()); })}>{busy === "install-browser" ? "Installing…" : "Install browser worker"}</button>}
    </div>
    {browserRuntime?.supported === false ? <p className="hint">The managed browser worker currently needs Windows x64.</p> : null}
    {browserRuntime?.installed && threadId ? <div className="visual-testing-session"><span>Browser session: {browserSession?.state ?? "checking"}</span><button type="button" disabled={disabled || Boolean(busy)} onClick={() => void perform("reset-browser", async () => setBrowserSession(await api.resetBrowserSession(threadId)))}>Reset</button><button type="button" disabled={disabled || Boolean(busy) || browserSession?.state === "closed"} onClick={() => void perform("close-browser", async () => setBrowserSession(await api.closeBrowserSession(threadId)))}>Close</button></div> : null}
    <div className="visual-testing-row">
      <label className="visual-testing-description" htmlFor="chat-window-access"><strong>Windows</strong><span>Control open app windows with this conversation’s access.</span></label>
      {windowRuntime?.available || windowRuntime?.installed ? <select id="chat-window-access" aria-label="Windows access" value={windowAccess?.scope ?? desktopAccess} disabled={disabled || Boolean(busy) || !conversationId} onChange={event => void changeWindows(event.target.value as DesktopAccess)}><option value="off">Off</option><option value="selected">Selected window</option><option value="all">All windows</option></select> : <button type="button" disabled={disabled || Boolean(busy)} onClick={() => void perform("install-windows", async () => { setWindowRuntime(await api.installWindowRuntime()); })}>{busy === "install-windows" ? "Installing…" : "Install Windows worker"}</button>}
    </div>
    {!conversationId && (windowRuntime?.available || windowRuntime?.installed) ? <div className="visual-testing-session"><span>Choose a live window after creating this chat.</span>{onPrepareConversation ? <button type="button" disabled={disabled || Boolean(busy)} onClick={() => void perform("prepare-chat", onPrepareConversation)}>{busy === "prepare-chat" ? "Creating…" : "Create chat"}</button> : null}</div> : null}
    {conversationId && desktopAccess === "selected" && !windowAccess?.selected_window?.hwnd && !choosingWindow ? <button type="button" disabled={disabled || Boolean(busy)} onClick={() => void loadWindows()}>Choose window</button> : null}
    {choosingWindow && conversationId ? <div className="visual-testing-picker"><label htmlFor="chat-window-choice">Window</label><select id="chat-window-choice" value={selectedHwnd} onChange={event => setSelectedHwnd(event.target.value)} disabled={Boolean(busy)}>{windows.map(window => <option key={window.hwnd} value={String(window.hwnd)}>{window.title || window.process_name} · {window.process_name} · {window.process_id}</option>)}</select><button type="button" disabled={disabled || Boolean(busy) || !selectedHwnd} onClick={() => void perform("select-window", async () => { const access = await api.setWindowAccess(conversationId, "selected", Number(selectedHwnd)); setWindowAccess(access); setChoosingWindow(false); onDesktopAccess("selected"); })}>Use window</button><button type="button" disabled={Boolean(busy)} onClick={() => setChoosingWindow(false)}>Cancel</button>{!windows.length ? <span className="hint">No open windows were found.</span> : null}</div> : null}
    {windowAccess?.scope === "selected" && windowAccess.selected_window ? <p className="hint">Selected: {windowAccess.selected_window.title || windowAccess.selected_window.process_name}</p> : null}
    {windowAccess?.scope === "all" ? <p className="hint">This chat can access open windows until you switch it off or restart Workbench.</p> : null}
    {workMode === "plan" ? <p className="hint">Switch to Work to use browser or Windows controls.</p> : null}
    {error ? <p className="visual-testing-error" role="alert">{error}</p> : null}
  </section>;
}
