import { useCallback, useEffect, useRef, useState, type PointerEvent as ReactPointerEvent } from "react";
import { api, streamBrowserEvents } from "./api";
import { errorMessage } from "./errors";
import { Icon } from "./Icon";
import type { BrowserAction, BrowserActionRequest, BrowserFrame, BrowserSessionStatus, BrowserViewport } from "./types";
import "./BrowserRail.css";

const DESKTOP = { width: 1440, height: 900 };
const PRESETS = { desktop: DESKTOP, tablet: { width: 768, height: 1024 }, phone: { width: 390, height: 844 } };

/** Match object-fit: contain, including its letterbox, in viewport CSS pixels. */
export function browserPoint(rect: { left: number; top: number; width: number; height: number }, viewport: BrowserViewport, clientX: number, clientY: number, clamp = false): { x: number; y: number } | null {
  if (rect.width <= 0 || rect.height <= 0 || viewport.width <= 0 || viewport.height <= 0) return null;
  const scale = Math.min(rect.width / viewport.width, rect.height / viewport.height);
  const x = (clientX - rect.left - (rect.width - viewport.width * scale) / 2) / scale;
  const y = (clientY - rect.top - (rect.height - viewport.height * scale) / 2) / scale;
  if (!clamp && (x < 0 || y < 0 || x >= viewport.width || y >= viewport.height)) return null;
  return { x: Math.max(0, Math.min(viewport.width - 1, x)), y: Math.max(0, Math.min(viewport.height - 1, y)) };
}

export function browserFrameMatches(frame: BrowserFrame | null, status: BrowserSessionStatus | null): boolean {
  return Boolean(frame && status?.state === "active" && frame.session_id === status.session_id && frame.page_id === status.active_page_id && frame.revision === status.revision && frame.viewport.width === status.viewport.width && frame.viewport.height === status.viewport.height);
}

/** Activity is observable without opening the user's dock. */
export function useBrowserRailActivity(threadId: string | null, enabled: boolean, onActivity: (active: boolean) => void): void {
  const activityRef = useRef(onActivity);
  activityRef.current = onActivity;
  useEffect(() => {
    activityRef.current(false);
    if (!threadId || !enabled) return;
    let observed = false;
    let stale = false;
    let polling = false;
    async function poll() {
      if (polling) return;
      polling = true;
      try {
        const state = await api.browserSession(threadId!);
        if (!stale && observed !== (state.state === "active")) { observed = state.state === "active"; activityRef.current(observed); }
      } catch { /* Readiness and the Browser tab own actionable failures. */ }
      finally { polling = false; }
    }
    void poll();
    const timer = window.setInterval(() => void poll(), 1500);
    return () => { stale = true; window.clearInterval(timer); };
  }, [threadId, enabled]);
}

interface BrowserRailProps {
  threadId: string | null;
  visible: boolean;
  enabled: boolean;
  projectBound: boolean;
  attachments: Array<{ id: string; filename: string }>;
  onConfigure: () => void;
  onSettings?: () => void;
  onOpenFiles: () => void;
  onDownloadsChanged?: () => void;
  onReadinessChange?: () => void;
}

export function BrowserRail({ threadId, visible, enabled, projectBound, attachments, onConfigure, onSettings = onConfigure, onOpenFiles, onDownloadsChanged, onReadinessChange }: BrowserRailProps) {
  const [status, setStatus] = useState<BrowserSessionStatus | null>(null);
  const statusRef = useRef(status);
  const statusVersion = useRef(0);
  const [frame, setFrame] = useState<BrowserFrame | null>(null);
  const [, setLoadedFrame] = useState("");
  const displayedFrame = useRef<BrowserFrame | null>(null);
  const pendingFrame = useRef<BrowserFrame | null>(null);
  const lastFrameTimestamp = useRef(-Infinity);
  const frameTimer = useRef<number | null>(null);
  const generation = useRef(0);
  const [address, setAddress] = useState("");
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [connection, setConnection] = useState("Idle");
  const [resetConfirm, setResetConfirm] = useState(false);
  const [custom, setCustom] = useState(false);
  const [width, setWidth] = useState(String(DESKTOP.width));
  const [height, setHeight] = useState(String(DESKTOP.height));
  const [prompt, setPrompt] = useState("");
  const [uploadAssets, setUploadAssets] = useState<string[]>([]);
  const [uploadPaths, setUploadPaths] = useState("");
  const viewportRef = useRef<HTMLDivElement>(null);
  const pressed = useRef<{ button: "left" | "middle" | "right"; x: number; y: number } | null>(null);
  const actionQueue = useRef<Array<{ request: BrowserActionRequest; generation: number; threadId: string }>>([]);
  const actionFlight = useRef(false);
  const downloadSignature = useRef("");
  const downloadsChanged = useRef(onDownloadsChanged);
  downloadsChanged.current = onDownloadsChanged;
  const readinessChanged = useRef(onReadinessChange);
  readinessChanged.current = onReadinessChange;

  const clearFrame = useCallback(() => {
    displayedFrame.current = null;
    pendingFrame.current = null;
    lastFrameTimestamp.current = -Infinity;
    setFrame(null);
    setLoadedFrame("");
    pressed.current = null;
  }, []);
  const acceptStatus = useCallback((next: BrowserSessionStatus) => {
    const previous = statusRef.current;
    if (next.thread_id !== threadId) return;
    if (previous?.session_id === next.session_id && next.revision < previous.revision) return;
    if (previous?.session_id !== next.session_id || previous?.active_page_id !== next.active_page_id || previous?.revision !== next.revision || next.state !== "active") clearFrame();
    if (previous?.control !== next.control) { actionQueue.current = []; pressed.current = null; }
    if (previous && (previous.state !== next.state || previous.control !== next.control || previous.worker.installed !== next.worker.installed || previous.worker.chrome_available !== next.worker.chrome_available)) readinessChanged.current?.();
    statusVersion.current += 1;
    statusRef.current = next;
    setStatus(next);
    if (next.state !== "active") setConnection(next.state === "lost" ? "Connection lost" : "Idle");
    const tab = next.tabs.find(item => item.page_id === next.active_page_id);
    if (previous?.session_id !== next.session_id || previous?.active_page_id !== next.active_page_id || previous?.tabs.find(item => item.page_id === previous.active_page_id)?.url !== tab?.url) setAddress(tab?.url ?? "");
    if (previous?.dialog?.message !== next.dialog?.message || previous?.dialog?.default_value !== next.dialog?.default_value) setPrompt(next.dialog?.default_value ?? "");
    if (previous?.viewport.width !== next.viewport.width || previous?.viewport.height !== next.viewport.height) { setWidth(String(next.viewport.width)); setHeight(String(next.viewport.height)); }
    const signature = (next.downloads ?? []).map(item => item.asset_id).join("|");
    if (signature !== downloadSignature.current) { downloadSignature.current = signature; downloadsChanged.current?.(); }
  }, [threadId, clearFrame]);

  useEffect(() => {
    const currentGeneration = ++generation.current;
    statusRef.current = null; setStatus(null); clearFrame();
    actionQueue.current = []; setBusy(""); setError(""); setResetConfirm(false); setUploadAssets([]); setUploadPaths(""); setAddress(""); downloadSignature.current = "";
    if (!threadId || !visible) { setConnection("Idle"); return; }
    const controller = new AbortController();
    let retryTimer: number | null = null;
    const initialStatusVersion = statusVersion.current;
    void api.browserSession(threadId).then(next => {
      if (generation.current === currentGeneration && !controller.signal.aborted && statusVersion.current === initialStatusVersion) acceptStatus(next);
    }).catch(failure => {
      if (!controller.signal.aborted && statusVersion.current === initialStatusVersion) setError(errorMessage(failure));
    });
    async function connect() {
      setConnection("Connecting…");
      try {
        await streamBrowserEvents(threadId!, event => {
          if (controller.signal.aborted || generation.current !== currentGeneration) return;
          if (event.type === "state") { acceptStatus(event.data); return; }
          setConnection("Live");
          const incoming = event.data;
          if (!browserFrameMatches(incoming, statusRef.current) || !/^[A-Za-z0-9+/=]+$/.test(incoming.data) || incoming.data.length > 4_000_000 || !Number.isFinite(incoming.timestamp) || incoming.timestamp <= lastFrameTimestamp.current) return;
          lastFrameTimestamp.current = incoming.timestamp;
          // One pending frame. Superseded arrivals never queue behind decoding.
          pendingFrame.current = incoming;
          if (frameTimer.current === null) frameTimer.current = window.requestAnimationFrame(() => {
            frameTimer.current = null;
            const latest = pendingFrame.current;
            pendingFrame.current = null;
            if (latest && browserFrameMatches(latest, statusRef.current) && !controller.signal.aborted) setFrame(latest);
          });
        }, controller.signal);
        if (!controller.signal.aborted) setConnection(statusRef.current?.state === "active" ? "Reconnecting…" : "Idle");
      } catch (failure) {
        if (!controller.signal.aborted) { setConnection(statusRef.current?.state === "active" ? "Reconnecting…" : statusRef.current?.state === "lost" ? "Connection lost" : "Unavailable"); setError(errorMessage(failure)); }
      }
      if (!controller.signal.aborted) retryTimer = window.setTimeout(() => void connect(), 2000);
    }
    void connect();
    return () => {
      generation.current += 1;
      controller.abort();
      if (retryTimer !== null) window.clearTimeout(retryTimer);
      if (frameTimer.current !== null) window.cancelAnimationFrame(frameTimer.current);
      frameTimer.current = null; actionQueue.current = []; clearFrame();
    };
  }, [threadId, visible, acceptStatus, clearFrame]);

  async function perform(label: string, action: () => Promise<BrowserSessionStatus>) {
    const currentGeneration = generation.current;
    setBusy(label); setError("");
    try { const next = await action(); if (generation.current === currentGeneration) acceptStatus(next); }
    catch (failure) { if (generation.current === currentGeneration) setError(errorMessage(failure)); }
    finally { if (generation.current === currentGeneration) setBusy(""); }
  }
  const active = status?.state === "active";
  const canControl = Boolean(enabled && active && status.control === "user" && !busy);
  const canPoint = canControl && Boolean(displayedFrame.current && browserFrameMatches(displayedFrame.current, status));

  function send(action: BrowserAction, needsFrame = false) {
    const current = statusRef.current;
    if (!threadId || !enabled || busy || current?.state !== "active" || current.control !== "user" || !current.session_id || !current.active_page_id) return;
    if (needsFrame && !browserFrameMatches(displayedFrame.current, current)) return;
    const request = { session_id: current.session_id, page_id: current.active_page_id, revision: current.revision, action };
    const queued = { request, generation: generation.current, threadId };
    const last = actionQueue.current.at(-1);
    if (action.type === "pointer" && action.event === "move" && last?.request.action.type === "pointer" && last.request.action.event === "move") actionQueue.current[actionQueue.current.length - 1] = queued;
    else if (actionQueue.current.length < 64) actionQueue.current.push(queued);
    else setError("Browser input is busy. Wait for the page to settle before sending more input.");
    void drainActions();
  }
  async function drainActions() {
    if (actionFlight.current || !threadId) return;
    actionFlight.current = true;
    try {
      let queued;
      while ((queued = actionQueue.current.shift())) {
        if (queued.generation !== generation.current || !statusRef.current || queued.request.session_id !== statusRef.current.session_id || queued.request.page_id !== statusRef.current.active_page_id || queued.request.revision !== statusRef.current.revision || statusRef.current.control !== "user") continue;
        try { const next = await api.browserAction(queued.threadId, queued.request); if (queued.generation === generation.current) acceptStatus(next); }
        catch (failure) { if (queued.generation === generation.current) { setError(errorMessage(failure)); actionQueue.current = []; } }
      }
    } finally { actionFlight.current = false; }
  }
  function point(event: { clientX: number; clientY: number }, clamp = false) {
    if (!viewportRef.current || !displayedFrame.current || !browserFrameMatches(displayedFrame.current, statusRef.current)) return null;
    return browserPoint(viewportRef.current.getBoundingClientRect(), displayedFrame.current.viewport, event.clientX, event.clientY, clamp);
  }
  function pointerDown(event: ReactPointerEvent<HTMLDivElement>) {
    if (!canPoint || event.button > 2) return;
    const location = point(event);
    if (!location) return;
    event.preventDefault(); event.currentTarget.focus(); event.currentTarget.setPointerCapture(event.pointerId);
    const button = event.button === 1 ? "middle" : event.button === 2 ? "right" : "left";
    pressed.current = { button, ...location };
    send({ type: "pointer", event: "down", ...location, button, delta_x: 0, delta_y: 0 }, true);
  }
  function releasePointer(event: ReactPointerEvent<HTMLDivElement>) {
    if (!pressed.current) return;
    const location = point(event, true) ?? pressed.current;
    const button = pressed.current.button;
    pressed.current = null;
    send({ type: "pointer", event: "up", ...location, button, delta_x: 0, delta_y: 0 }, true);
    if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId);
  }
  const viewport = status?.viewport ?? DESKTOP;
  const preset = Object.entries(PRESETS).find(([, value]) => value.width === viewport.width && value.height === viewport.height)?.[0] ?? "custom";

  return <div className="browser-rail" aria-label="Chat browser">
    <div className="browser-lifecycle">
      <span className="browser-state" role="status">{active ? status.control === "user" ? "You have control" : status.control === "taking_control" ? "Pausing task and helpers…" : "Agent has control" : status?.state === "lost" ? status.control === "user" ? "Browser connection lost · Task paused" : "Browser connection lost" : status?.control === "user" ? "Browser closed · Task paused" : status?.control === "taking_control" ? "Browser closed · Pausing task…" : "Browser closed"}</span>
      {!active ? <button type="button" disabled={!threadId || !enabled || Boolean(busy) || status?.state === "lost" || status?.worker.installed === false || status?.worker.chrome_available === false} onClick={() => threadId && void perform("start", () => api.startBrowserSession(threadId))}>{busy === "start" ? "Starting…" : "Start browser"}</button> : null}
      {active || status?.control === "user" || status?.control === "taking_control" ? <button type="button" disabled={Boolean(busy) || status.control === "taking_control"} onClick={() => threadId && void perform("control", () => api.controlBrowserSession(threadId, status.control === "user" ? "return" : "take"))}>{busy === "control" || status.control === "taking_control" ? "Please wait…" : status.control === "user" ? "Return to agent" : "Take control"}</button> : null}
      {active || status?.state === "lost" ? <button type="button" disabled={Boolean(busy)} onClick={() => threadId && void perform("close", () => api.closeBrowserSession(threadId))}>Close</button> : null}
      <button type="button" disabled={!threadId || Boolean(busy)} onClick={() => setResetConfirm(true)}>Reset</button>
    </div>
    {!threadId ? <p className="hint">Create a chat to start its browser.</p> : null}
    {!enabled ? <p className="hint">Enable Browser tools in <button type="button" onClick={onConfigure}>Agents</button> and switch to Work to start or control pages.</p> : null}
    {status?.worker.chrome_available === false ? <p role="alert">Chrome is unavailable. Install Chrome, then reopen this tab.</p> : null}
    {status?.worker.installed === false ? <p className="hint">Install the browser worker in <button type="button" onClick={onSettings}>Settings</button>.</p> : null}
    {status?.state === "lost" ? <p className="hint">Close this session, then start Chrome again to keep this chat’s sign-ins. The new session opens fresh pages.</p> : null}
    {resetConfirm ? <div className="browser-confirm" role="alertdialog" aria-label="Reset this chat browser"><p>Reset closes Chrome and clears this chat’s sign-ins and browser data.</p><button type="button" disabled={Boolean(busy)} onClick={() => { setResetConfirm(false); if (threadId) void perform("reset", () => api.resetBrowserSession(threadId)); }}>Clear sign-ins and reset</button><button type="button" onClick={() => setResetConfirm(false)}>Cancel</button></div> : null}
    <div className="browser-navigation">
      <button type="button" aria-label="Browser back" title="Back" disabled={!canControl} onClick={() => send({ type: "back" })}><Icon name="back" size={14} /></button>
      <button type="button" aria-label="Browser forward" title="Forward" disabled={!canControl} onClick={() => send({ type: "forward" })}><Icon name="forward" size={14} /></button>
      <button type="button" aria-label="Reload browser page" title="Reload" disabled={!canControl} onClick={() => send({ type: "reload" })}>↻</button>
      <form onSubmit={event => { event.preventDefault(); send({ type: "navigate", url: address }); }}><input aria-label="Browser address" value={address} spellCheck={false} disabled={!canControl} onChange={event => setAddress(event.target.value)} placeholder="https://" /><button type="submit" disabled={!canControl || !address.trim()}>Go</button></form>
    </div>
    <div className="browser-page-tabs" role="tablist" aria-label="Browser pages">
      {(status?.tabs ?? []).map(tab => <div className="browser-page-tab" key={tab.page_id}><button type="button" role="tab" aria-selected={tab.page_id === status?.active_page_id} disabled={!canControl} title={tab.url} onClick={() => send({ type: "select_tab", page_id: tab.page_id })}>{tab.title || tab.url || "New tab"}</button><button type="button" aria-label={`Close page ${tab.title || tab.url || "New tab"}`} disabled={!canControl} onClick={() => send({ type: "close_tab", page_id: tab.page_id })}>×</button></div>)}
      <button type="button" aria-label="New browser tab" title="New tab" disabled={!canControl} onClick={() => send({ type: "new_tab" })}>+</button>
    </div>
    <div className="browser-resolution">
      <label>Resolution <select aria-label="Browser resolution" value={custom ? "custom" : preset} disabled={!canControl} onChange={event => { const value = event.target.value; setCustom(value === "custom"); if (value !== "custom") send({ type: "resize", ...PRESETS[value as keyof typeof PRESETS] }); }}><option value="desktop">Desktop 1440 × 900</option><option value="tablet">Tablet 768 × 1024</option><option value="phone">Phone 390 × 844</option><option value="custom">Custom</option></select></label>
      <small>{viewport.width} × {viewport.height} · {connection}</small>
      {custom ? <form onSubmit={event => { event.preventDefault(); send({ type: "resize", width: Number(width), height: Number(height) }); }}><input aria-label="Browser viewport width" type="number" min={240} max={3840} value={width} disabled={!canControl} onChange={event => setWidth(event.target.value)} /><span>×</span><input aria-label="Browser viewport height" type="number" min={240} max={2160} value={height} disabled={!canControl} onChange={event => setHeight(event.target.value)} /><button type="submit" disabled={!canControl}>Apply</button></form> : null}
    </div>
    {status?.dialog ? <div className="browser-dialog" role="dialog" aria-label="Page dialog"><p>{status.dialog.message}</p>{status.dialog.type === "prompt" ? <input aria-label="Page dialog response" value={prompt} onChange={event => setPrompt(event.target.value)} disabled={!canControl} /> : null}<button type="button" disabled={!canControl} onClick={() => send({ type: "dialog", accept: true, prompt_text: prompt })}>Accept</button><button type="button" disabled={!canControl} onClick={() => send({ type: "dialog", accept: false })}>Dismiss</button></div> : null}
    {status?.file_chooser ? <div className="browser-upload" role="dialog" aria-label="Choose browser upload"><strong>Choose files to upload</strong>{attachments.map(asset => <label key={asset.id}><input type="checkbox" disabled={!canControl} checked={uploadAssets.includes(asset.id)} onChange={event => setUploadAssets(current => event.target.checked ? status.file_chooser?.multiple ? [...current, asset.id] : [asset.id] : current.filter(id => id !== asset.id))} />{asset.filename}</label>)}{!attachments.length ? <p className="hint">Attach files to this chat to select them here.</p> : null}{projectBound ? <label>Project file paths<textarea aria-label="Browser upload project paths" placeholder="One project-relative path per line" value={uploadPaths} disabled={!canControl} onChange={event => setUploadPaths(event.target.value)} /></label> : null}<button type="button" disabled={!canControl || !uploadAssets.length && !uploadPaths.trim()} onClick={() => send({ type: "upload", asset_ids: uploadAssets, project_paths: uploadPaths.split(/\r?\n/).map(value => value.trim()).filter(Boolean) })}>Upload selected files</button><button type="button" disabled={!canControl} onClick={() => send({ type: "upload", asset_ids: [], project_paths: [] })}>Cancel file selection</button></div> : null}
    {error || status?.error ? <p className="browser-error" role="alert">{error || status?.error}</p> : null}
    <div ref={viewportRef} className={`browser-viewport${canPoint ? " has-control" : ""}`} tabIndex={canControl ? 0 : -1} role="application" aria-label="Live browser page" aria-disabled={!canPoint}
      onContextMenu={event => event.preventDefault()} onPointerDown={pointerDown} onPointerUp={releasePointer} onPointerCancel={releasePointer}
      onPointerMove={event => { if (!canPoint) return; const location = point(event, Boolean(pressed.current)); if (location) { if (pressed.current) pressed.current = { ...pressed.current, ...location }; send({ type: "pointer", event: "move", ...location, button: pressed.current?.button ?? "left", delta_x: 0, delta_y: 0 }, true); } }}
      onWheel={event => { if (!canPoint) return; const location = point(event); if (!location) return; event.preventDefault(); const multiplier = event.deltaMode === 1 ? 16 : event.deltaMode === 2 ? viewport.height : 1; send({ type: "pointer", event: "wheel", ...location, button: "left", delta_x: event.deltaX * multiplier, delta_y: event.deltaY * multiplier }, true); }}
      onKeyDown={event => {
        if (!canControl || event.nativeEvent.isComposing || event.key === "Process" || ["Control", "Shift", "Alt", "Meta"].includes(event.key)) return;
        if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "v") return;
        event.preventDefault();
        if (event.key.length === 1 && !event.ctrlKey && !event.metaKey && !event.altKey) send({ type: "text", text: event.key });
        else { const key = event.key === " " ? "Space" : event.key; send({ type: "key", key: [event.ctrlKey ? "Control" : "", event.metaKey ? "Meta" : "", event.altKey ? "Alt" : "", event.shiftKey ? "Shift" : "", key].filter(Boolean).join("+") }); }
      }}
      onCompositionEnd={event => { if (canControl && event.data) send({ type: "text", text: event.data }); }}
      onPaste={event => { if (!canControl) return; event.preventDefault(); const text = event.clipboardData.getData("text/plain"); if (text) send({ type: "text", text }); }}>
      {frame ? <img draggable={false} alt="Live Chrome page" src={`data:image/jpeg;base64,${frame.data}`} onLoad={() => { if (browserFrameMatches(frame, statusRef.current)) { displayedFrame.current = frame; setLoadedFrame(`${frame.session_id}:${frame.page_id}:${frame.revision}:${frame.timestamp}`); } }} /> : <span className="browser-empty">{active ? "Waiting for the live page…" : "Chrome will appear here."}</span>}
    </div>
    {active && status.control === "agent" ? <p className="browser-hint">Take control to click or type. The task and its helpers pause first.</p> : null}
    {(status?.downloads ?? []).length ? <div className="browser-downloads"><span>Saved downloads: {(status?.downloads ?? []).map(item => item.name).join(", ")}</span><button type="button" onClick={onOpenFiles}>Show in Files</button></div> : null}
  </div>;
}
