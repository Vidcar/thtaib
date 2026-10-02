import { useEffect, useRef, useState } from "react";
import { api } from "./api";
import { errorMessage } from "./errors";
import type { BrowserRuntimeStatus, BrowserSessionStatus, DesktopAccess, TestWindow, WindowAccessStatus, WindowRuntimeStatus } from "./types";
import "./VisualTestingControls.css";

/** Runtime details for the Browser and Windows rows in the Chat + menu. */
export function VisualTestingControls({ conversationId, threadId, browserEnabled, onBrowserEnabled, desktopAccess, onDesktopAccess, onPrepareConversation, canPrepareConversation = true, onReadinessChange, disabled = false, workMode = "work", focusSection, focusNonce = 0, windowsOnly = false, onSettings }: {
  conversationId: string | null;
  threadId: string | null;
  browserEnabled: boolean;
  onBrowserEnabled: (enabled: boolean) => void;
  desktopAccess: DesktopAccess;
  onDesktopAccess: (scope: DesktopAccess) => void;
  onPrepareConversation?: () => Promise<void>;
  canPrepareConversation?: boolean;
  onReadinessChange?: () => void;
  disabled?: boolean;
  workMode?: "work" | "plan";
  focusSection?: "browser" | "windows" | null;
  focusNonce?: number;
  windowsOnly?: boolean;
  onSettings?: () => void;
}) {
  const [expanded, setExpanded] = useState<"browser" | "windows" | null>(focusSection ?? null);
  const browserButton = useRef<HTMLButtonElement>(null);
  const windowsButton = useRef<HTMLButtonElement>(null);
  const [browserRuntime, setBrowserRuntime] = useState<BrowserRuntimeStatus | null>(null);
  const [browserSession, setBrowserSession] = useState<BrowserSessionStatus | null>(null);
  const [windowRuntime, setWindowRuntime] = useState<WindowRuntimeStatus | null>(null);
  const [windowAccess, setWindowAccess] = useState<WindowAccessStatus | null>(null);
  const [windows, setWindows] = useState<TestWindow[]>([]);
  const [choosingWindow, setChoosingWindow] = useState(false);
  const [pendingWindowChoice, setPendingWindowChoice] = useState(false);
  const [selectedHwnd, setSelectedHwnd] = useState("");
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [confirmBrowserReset, setConfirmBrowserReset] = useState(false);
  const lastRuntimeState = useRef<string | null>(null);
  const runtimeState = JSON.stringify([browserRuntime?.supported, browserRuntime?.installed, browserRuntime?.chrome_available, browserRuntime?.chrome_version, browserSession?.state, windowRuntime?.available, windowRuntime?.installed, windowAccess?.scope, windowAccess?.stale, windowAccess?.selected_window?.hwnd]);

  useEffect(() => {
    if (lastRuntimeState.current !== null && lastRuntimeState.current !== runtimeState) onReadinessChange?.();
    lastRuntimeState.current = runtimeState;
  }, [runtimeState, onReadinessChange]);

  useEffect(() => {
    if (!focusSection) return;
    setExpanded(focusSection);
    const target = focusSection === "browser" ? browserButton : windowsButton;
    if (typeof window.requestAnimationFrame === "function") window.requestAnimationFrame(() => target.current?.focus({ preventScroll: true }));
  }, [focusSection, focusNonce]);

  // This component mounts only while the + menu is open. Its status requests and
  // polling therefore stop when the menu closes.
  useEffect(() => {
    let stale = false;
    setBrowserSession(null); setWindowAccess(null); setWindows([]); setChoosingWindow(false); setError(""); setConfirmBrowserReset(false);
    void Promise.allSettled([
      windowsOnly ? Promise.resolve(null) : api.browserRuntime(), api.windowRuntime(),
      threadId && !windowsOnly ? api.browserSession(threadId) : Promise.resolve(null),
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
  }, [conversationId, threadId, windowsOnly]);

  useEffect(() => {
    let stale = false;
    const timer = window.setInterval(() => {
      const showPollFailure = (failure: unknown) => { if (!stale) setError(errorMessage(failure)); };
      if (!windowsOnly) void api.browserRuntime().then(value => { if (!stale) setBrowserRuntime(value); }).catch(showPollFailure);
      void api.windowRuntime().then(value => { if (!stale) setWindowRuntime(value); }).catch(showPollFailure);
      if (threadId && !windowsOnly) void api.browserSession(threadId).then(value => { if (!stale) setBrowserSession(value); }).catch(showPollFailure);
      if (conversationId) void api.windowAccess(conversationId).then(value => { if (!stale) setWindowAccess(value); }).catch(showPollFailure);
    }, 5000);
    return () => { stale = true; window.clearInterval(timer); };
  }, [conversationId, threadId, windowsOnly]);

  useEffect(() => {
    if (!conversationId || !pendingWindowChoice) return;
    setPendingWindowChoice(false);
    void loadWindows();
  }, [conversationId, pendingWindowChoice]);

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
      setExpanded("windows");
    });
  }

  async function chooseWindow() {
    if (!conversationId) {
      if (!onPrepareConversation) return;
      setPendingWindowChoice(true);
      await perform("prepare-chat", onPrepareConversation);
      return;
    }
    await loadWindows();
  }

  const browserStatus = browserRuntime?.supported === false ? "Unsupported" : browserRuntime?.chrome_available === false ? "Needs Chrome" : browserRuntime?.installed ? browserSession?.state ?? "Installed" : browserRuntime ? "Needs install" : "Checking";
  const oneWindow = desktopAccess === "selected" && Boolean(windowAccess?.selected_window?.hwnd) && !windowAccess?.stale;
  const windowsStatus = windowRuntime?.available ? oneWindow ? "One window" : "Choose a window" : windowRuntime?.installed ? "Unavailable" : windowRuntime ? "Needs install" : "Checking";

  return <div className="visual-testing-controls" role="group" aria-label={windowsOnly ? "Live Windows access" : "Browser and Windows tools"}>
    {!windowsOnly ? <div className="visual-testing-capability">
      <div className="visual-testing-row">
        <button ref={browserButton} type="button" className="visual-testing-disclosure" aria-expanded={expanded === "browser"} onClick={() => setExpanded(current => current === "browser" ? null : "browser")}><strong>Browser</strong><small>{browserStatus}</small></button>
        <label className="visual-testing-switch"><input type="checkbox" aria-label="Browser tools" checked={browserEnabled} disabled={disabled || Boolean(busy)} onChange={event => { onBrowserEnabled(event.target.checked); onReadinessChange?.(); }} />{browserEnabled ? "On" : "Off"}</label>
      </div>
      {expanded === "browser" ? <div className="visual-testing-detail">
        <p className="hint">Chrome runs inside the Browser tab. This chat retains its own sign-ins. Any model can inspect page structure; screenshots need image support.</p>
        {browserRuntime?.chrome_available === false ? <p className="hint">Install Chrome to use the browser. Worker installation is separate.</p> : browserRuntime?.chrome_version ? <p className="hint">Chrome {browserRuntime.chrome_version}</p> : null}
        {browserRuntime?.supported === false ? <p className="hint">The managed browser worker currently needs Windows x64.</p> : null}
        {!browserRuntime?.installed && browserRuntime?.supported !== false ? <button type="button" disabled={disabled || Boolean(busy)} onClick={() => void perform("install-browser", async () => { setBrowserRuntime(await api.installBrowserRuntime()); onReadinessChange?.(); })}>{busy === "install-browser" ? "Installing…" : "Install browser worker"}</button> : null}
        {browserRuntime?.installed ? <div className="visual-testing-session"><span>Session: {threadId ? browserSession?.state ?? "checking" : "starts with this chat"}</span>{threadId ? <><button type="button" disabled={disabled || Boolean(busy)} onClick={() => setConfirmBrowserReset(true)}>Reset</button><button type="button" disabled={disabled || Boolean(busy) || browserSession?.state === "closed"} onClick={() => void perform("close-browser", async () => { setBrowserSession(await api.closeBrowserSession(threadId)); onReadinessChange?.(); })}>Close</button></> : null}</div> : null}
        {confirmBrowserReset && threadId ? <div className="visual-testing-session" role="alertdialog" aria-label="Reset this chat browser"><p>Reset closes Chrome and clears this chat’s sign-ins and browser data.</p><button type="button" disabled={disabled || Boolean(busy)} onClick={() => { setConfirmBrowserReset(false); void perform("reset-browser", async () => { setBrowserSession(await api.resetBrowserSession(threadId)); onReadinessChange?.(); }); }}>Clear sign-ins and reset</button><button type="button" onClick={() => setConfirmBrowserReset(false)}>Cancel</button></div> : null}
      </div> : null}
    </div> : null}
    <div className="visual-testing-capability">
      <button ref={windowsButton} type="button" className="visual-testing-disclosure" aria-expanded={expanded === "windows"} onClick={() => setExpanded(current => current === "windows" ? null : "windows")}><strong>One window</strong><small>{windowsStatus}</small></button>
      {expanded === "windows" ? <div className="visual-testing-detail">
        {!windowRuntime?.available && !windowRuntime?.installed ? windowsOnly ? <button type="button" onClick={onSettings}>Install worker in Settings</button> : <button type="button" disabled={disabled || Boolean(busy)} onClick={() => void perform("install-windows", async () => { setWindowRuntime(await api.installWindowRuntime()); onReadinessChange?.(); })}>{busy === "install-windows" ? "Installing…" : "Install Windows worker"}</button> : null}
        {windowRuntime?.installed && windowRuntime.available === false ? <p className="hint">Windows worker unavailable{windowRuntime.reason ? `: ${windowRuntime.reason}` : "."}</p> : null}
        {!conversationId && !canPrepareConversation ? <p className="hint">Choose a model before creating this chat.</p> : null}
        {!choosingWindow ? <button type="button" disabled={disabled || Boolean(busy) || (!conversationId && !canPrepareConversation)} onClick={() => void chooseWindow()}>Choose window</button> : null}
        {choosingWindow && conversationId ? <div className="visual-testing-picker"><label htmlFor="chat-window-choice">Window</label><select id="chat-window-choice" value={selectedHwnd} onChange={event => setSelectedHwnd(event.target.value)} disabled={Boolean(busy)}>{windows.map(item => <option key={item.hwnd} value={String(item.hwnd)}>{item.title || item.process_name} · {item.process_name} · {item.process_id}</option>)}</select><button type="button" disabled={disabled || Boolean(busy) || !selectedHwnd} onClick={() => void perform("select-window", async () => { const access = await api.setWindowAccess(conversationId, "selected", Number(selectedHwnd)); setWindowAccess(access); setChoosingWindow(false); onDesktopAccess("selected"); onReadinessChange?.(); })}>Use window</button><button type="button" disabled={Boolean(busy)} onClick={() => setChoosingWindow(false)}>Cancel</button>{!windows.length ? <span className="hint">No open windows were found.</span> : null}</div> : null}
        {oneWindow && windowAccess?.selected_window ? <p className="hint">One window: {windowAccess.selected_window.title || windowAccess.selected_window.process_name}</p> : null}
      </div> : null}
    </div>
    {workMode === "plan" ? <p className="hint">Switch to Work to use browser or Windows controls.</p> : null}
    {error ? <p className="visual-testing-error" role="alert">{error}</p> : null}
  </div>;
}
