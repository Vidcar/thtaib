import { useEffect, useRef, useState } from "react";
import { api } from "./api";
import { errorMessage } from "./errors";
import type { BrowserRuntimeStatus, BrowserSessionStatus, DesktopAccess, TestWindow, WindowAccessStatus, WindowRuntimeStatus } from "./types";
import "./VisualTestingControls.css";

/** Runtime details for the Browser and Windows rows in the Chat + menu. */
export function VisualTestingControls({ conversationId, threadId, browserEnabled, onBrowserEnabled, desktopAccess, onDesktopAccess, onPrepareConversation, canPrepareConversation = true, onReadinessChange, disabled = false, workMode = "work", focusSection, focusNonce = 0 }: {
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
  const needsWindowGrant = desktopAccess !== "off" && Boolean(conversationId) && (windowAccess?.scope !== desktopAccess || windowAccess?.stale || (desktopAccess === "selected" && !windowAccess?.selected_window?.hwnd));
  const lastRuntimeState = useRef<string | null>(null);
  const runtimeState = JSON.stringify([browserRuntime?.supported, browserRuntime?.installed, browserSession?.state, windowRuntime?.available, windowRuntime?.installed, windowAccess?.scope, windowAccess?.stale, windowAccess?.selected_window?.hwnd]);

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
    let stale = false;
    const timer = window.setInterval(() => {
      void api.browserRuntime().then(value => { if (!stale) setBrowserRuntime(value); }).catch(() => {});
      void api.windowRuntime().then(value => { if (!stale) setWindowRuntime(value); }).catch(() => {});
      if (threadId) void api.browserSession(threadId).then(value => { if (!stale) setBrowserSession(value); }).catch(() => {});
      if (conversationId) void api.windowAccess(conversationId).then(value => { if (!stale) setWindowAccess(value); }).catch(() => {});
    }, 5000);
    return () => { stale = true; window.clearInterval(timer); };
  }, [conversationId, threadId]);

  useEffect(() => {
    if (!conversationId || !pendingWindowChoice || desktopAccess !== "selected") return;
    setPendingWindowChoice(false);
    void loadWindows();
  }, [conversationId, pendingWindowChoice, desktopAccess]);

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

  async function changeWindows(next: DesktopAccess) {
    if (!conversationId) {
      onDesktopAccess(next);
      setPendingWindowChoice(next === "selected");
      return;
    }
    if (next === "selected") {
      await perform("narrow-window", async () => {
        // Narrow the live grant before showing the picker. A cancelled picker
        // must never leave a previous All-windows grant in force.
        setWindowAccess(await api.setWindowAccess(conversationId, "off"));
        onDesktopAccess("selected"); onReadinessChange?.();
        const choices = await api.testWindows();
        setWindows(choices);
        setSelectedHwnd(choices[0] ? String(choices[0].hwnd) : "");
        setChoosingWindow(true);
        setExpanded("windows");
      });
      return;
    }
    await perform("scope", async () => {
      const access = await api.setWindowAccess(conversationId, next);
      setWindowAccess(access); setChoosingWindow(false); onDesktopAccess(access.scope); onReadinessChange?.();
    });
  }

  const browserStatus = browserRuntime?.supported === false ? "Unsupported" : browserRuntime?.installed ? browserSession?.state ?? "Installed" : browserRuntime ? "Needs install" : "Checking";
  const windowsStatus = windowRuntime?.available ? desktopAccess === "off" ? "Off" : needsWindowGrant || !conversationId ? "Needs grant" : desktopAccess === "selected" ? "Selected" : "All" : windowRuntime?.installed ? "Unavailable" : windowRuntime ? "Needs install" : "Checking";

  return <div className="visual-testing-controls" role="group" aria-label="Browser and Windows tools">
    <div className="visual-testing-capability">
      <div className="visual-testing-row">
        <button ref={browserButton} type="button" className="visual-testing-disclosure" aria-expanded={expanded === "browser"} onClick={() => setExpanded(current => current === "browser" ? null : "browser")}><strong>Browser</strong><small>{browserStatus}</small></button>
        <label className="visual-testing-switch"><input type="checkbox" aria-label="Browser tools" checked={browserEnabled} disabled={disabled || Boolean(busy)} onChange={event => { onBrowserEnabled(event.target.checked); onReadinessChange?.(); }} />{browserEnabled ? "On" : "Off"}</label>
      </div>
      {expanded === "browser" ? <div className="visual-testing-detail">
        <p className="hint">Isolated pages and screenshots. A vision model is needed to judge an image; any model can inspect page structure.</p>
        {browserRuntime?.supported === false ? <p className="hint">The managed browser worker currently needs Windows x64.</p> : null}
        {!browserRuntime?.installed && browserRuntime?.supported !== false ? <button type="button" disabled={disabled || Boolean(busy)} onClick={() => void perform("install-browser", async () => { setBrowserRuntime(await api.installBrowserRuntime()); onReadinessChange?.(); })}>{busy === "install-browser" ? "Installing…" : "Install browser worker"}</button> : null}
        {browserRuntime?.installed ? <div className="visual-testing-session"><span>Session: {threadId ? browserSession?.state ?? "checking" : "starts with this chat"}</span>{threadId ? <><button type="button" disabled={disabled || Boolean(busy)} onClick={() => void perform("reset-browser", async () => { setBrowserSession(await api.resetBrowserSession(threadId)); onReadinessChange?.(); })}>Reset</button><button type="button" disabled={disabled || Boolean(busy) || browserSession?.state === "closed"} onClick={() => void perform("close-browser", async () => { setBrowserSession(await api.closeBrowserSession(threadId)); onReadinessChange?.(); })}>Close</button></> : null}</div> : null}
      </div> : null}
    </div>
    <div className="visual-testing-capability">
      <button ref={windowsButton} type="button" className="visual-testing-disclosure" aria-expanded={expanded === "windows"} onClick={() => setExpanded(current => current === "windows" ? null : "windows")}><strong>Windows</strong><small>{windowsStatus}</small></button>
      {expanded === "windows" ? <div className="visual-testing-detail">
        <p className="hint">Control open app windows with this conversation’s access.</p>
        {!windowRuntime?.available && !windowRuntime?.installed ? <button type="button" disabled={disabled || Boolean(busy)} onClick={() => void perform("install-windows", async () => { setWindowRuntime(await api.installWindowRuntime()); onReadinessChange?.(); })}>{busy === "install-windows" ? "Installing…" : "Install Windows worker"}</button> : null}
        {windowRuntime?.installed && windowRuntime.available === false ? <p className="hint">Windows worker unavailable{windowRuntime.reason ? `: ${windowRuntime.reason}` : "."}</p> : null}
        <label>Windows access <select aria-label="Windows access" value={desktopAccess} disabled={disabled || Boolean(busy)} onChange={event => void changeWindows(event.target.value as DesktopAccess)}><option value="off">Off</option><option value="selected">Selected window</option><option value="all">All windows</option></select></label>
        {needsWindowGrant ? <div className="visual-testing-session" role="status"><span>This chat needs a fresh Windows grant before sending.</span><button type="button" disabled={disabled || Boolean(busy)} onClick={() => void changeWindows(desktopAccess)}>{desktopAccess === "selected" ? "Choose window" : "Grant all windows"}</button></div> : null}
        {!conversationId && desktopAccess !== "off" ? <div className="visual-testing-session"><span>{canPrepareConversation ? "Create this chat to grant live window access." : "Choose a model before creating this chat."}</span>{onPrepareConversation ? <button type="button" disabled={disabled || Boolean(busy) || !canPrepareConversation} onClick={() => { if (desktopAccess === "selected") setPendingWindowChoice(true); void perform("prepare-chat", onPrepareConversation); }}>{busy === "prepare-chat" ? "Creating…" : "Create chat"}</button> : null}</div> : null}
        {conversationId && desktopAccess === "selected" && !windowAccess?.selected_window?.hwnd && !choosingWindow ? <button type="button" disabled={disabled || Boolean(busy)} onClick={() => void loadWindows()}>Choose window</button> : null}
        {choosingWindow && conversationId ? <div className="visual-testing-picker"><label htmlFor="chat-window-choice">Window</label><select id="chat-window-choice" value={selectedHwnd} onChange={event => setSelectedHwnd(event.target.value)} disabled={Boolean(busy)}>{windows.map(item => <option key={item.hwnd} value={String(item.hwnd)}>{item.title || item.process_name} · {item.process_name} · {item.process_id}</option>)}</select><button type="button" disabled={disabled || Boolean(busy) || !selectedHwnd} onClick={() => void perform("select-window", async () => { const access = await api.setWindowAccess(conversationId, "selected", Number(selectedHwnd)); setWindowAccess(access); setChoosingWindow(false); onDesktopAccess("selected"); onReadinessChange?.(); })}>Use window</button><button type="button" disabled={Boolean(busy)} onClick={() => setChoosingWindow(false)}>Cancel</button>{!windows.length ? <span className="hint">No open windows were found.</span> : null}</div> : null}
        {windowAccess?.scope === "selected" && windowAccess.selected_window ? <p className="hint">Selected: {windowAccess.selected_window.title || windowAccess.selected_window.process_name}</p> : null}
        {windowAccess?.scope === "all" ? <p className="hint">This chat can access open windows until you switch it off or restart Workbench.</p> : null}
      </div> : null}
    </div>
    {workMode === "plan" ? <p className="hint">Switch to Work to use browser or Windows controls.</p> : null}
    {error ? <p className="visual-testing-error" role="alert">{error}</p> : null}
  </div>;
}
