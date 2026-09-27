# Design

## Context

See proposal.md for the requested behavior. BrowserSessionService already owns one MCP adapter per graph thread and serialized calls. The worker pins Playwright MCP 0.0.82 but launches headed isolated Edge; Chat has no browser viewer. ExecutionControl is shared by inline helpers. Assets, Windows process jobs and local-secret authentication have existing owners.

## Goals / Non-Goals

**Goals:** keep one Chrome context shared by tools and human viewing; retain chat-specific sign-ins; enforce whole-task handoff, bounded live frames, viewport truth and scoped browser files.

**Non-Goals:** ordinary Chrome-profile access, an additional browser framework or agent loop, unrestricted scripts, remote browser hosting, or a new asset store.

## Decisions

- A thin owned Node worker launches Playwright's persistent Chrome context and supplies it to official MCP createConnection. Official SDK stdio transport preserves MCPAdapter. A token-authenticated random-loopback management API exposes only typed browser metadata/input/events to the backend; no worker address, credentials or raw browser protocol reaches the desktop. This shares public Page objects and avoids a duplicate embedded page or competing CDP client.
- Persistent profiles live under state/browser-profiles/<safe-thread>. Close/expiry retain profiles, reset removes only the confirmed stopped profile, normal shutdown closes cleanly, and unexpected loss preserves an explicit lost marker. Chrome starts with fresh tabs. Existing WindowsJob owns the Node/Chrome tree. Optional installation pins worker/SDK; runs never install packages.
- Shared state uses unique session_id and page_id, a revision changed by navigation/viewport/tab changes, actual viewport dimensions, active tab, controller (agent/taking_control/user) and observed timestamp. BrowserSessionService reconciles MCP current-tab indexes against that same context's ordered Page objects; IDs, never URLs, own frames/input. Manual navigation/tab changes go through the same browser service and upstream tools where available.
- Backend HTTP extends /v1/browser/sessions/{thread_id}: POST /start, POST /control (take/return), POST /actions (typed pointer/key/text/navigation/tab/resize/dialog/upload operations), GET /events (SSE state/frame), plus existing close/reset. Each action includes session_id, page_id and revision; stale input is rejected. Routes validate a real owning chat and its effective Browser selection. Closed/off sessions remain inspectable for recovery but cannot act.
- Playwright page.screencast supplies temporary JPEG frames: quality 75, max 1280x960, 10fps and latest-frame-only queues. Subscriptions are active only while the rail is visible. Rendering is a scaled image/canvas; external documents never inherit Electron trust. Main Chat does not rerender on frames. Input coordinates map letterboxing and stream scaling back to CSS viewport pixels.
- Takeover sets the root shared dispatch barrier immediately, drains active side-effect/model operations (excluding waiting delegation wrappers), and uses the native LangGraph interruption boundary for continuation. Manual control begins only when settled. Stop remains authoritative, pending approvals stay distinct, and returning control refreshes structural/visual observation and invalidates stale proposed browser mutations. User keystrokes/clipboard contents are not recorded. Restart retains the interruption without replaying effects.
- The group presents existing structural tools plus upstream drag, mouse/scroll and upload tools. File uploads use backend-resolved project-relative paths or explicitly selected asset identities and confined worker staging; no arbitrary absolute path authority. Downloads are completed into owned staging then retained through RetainedAssetService with browser provenance. Screenshots retain existing image guards and byte bounds. Agent policy still applies to every tool/helper invocation.
- Browser rail opens when a session starts in the currently selected chat and has navigation, tabs, actual resolution, lifecycle and takeover controls. Default viewport is 1440x900; presets 1440x900, 768x1024 and 390x844 plus bounded custom dimensions. Rail resizing changes display scale only.

## Risks / Trade-offs

- Asynchronous popups or identical URLs can confuse selection -> reconcile ordered upstream tab state with stable Page identity and reject mismatched revision input.
- Takeover can deadlock inline helpers -> share one root barrier and exclude passive delegation waits; validate concurrent helper/model/tool dispatch and Stop.
- Persistent profiles contain authentication -> keep them local, quiesce before backup, preserve explicit sensitive-backup behavior, and clear only through reset/deletion.
- Site or OS authentication may reject automation -> show the truthful reason in the rail; do not silently fall back to an external desktop window.

## Migration Plan

Install the updated optional worker explicitly during local delivery, preserving existing weights/settings and unrelated data. Existing ephemeral Edge sessions are closed before the new worker runs. Validate isolated native/model scenarios before refreshing the normal application. Rollback restores the prior code/worker without deleting persistent browser profiles or replaying actions.
