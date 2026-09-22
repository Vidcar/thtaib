# backend-desktop delta

## ADDED Requirements

### Requirement: API-010 - Present durable Chat state without duplicating or inventing work

Existing Chat SHALL support new, rename, archive, retained-title/message search and reopen. Archive changes visibility, not memory/context. Incremental answers, separate returned reasoning, tool content and partial failures SHALL reconcile by run/thread/message/call identity into one final saved result. Internal summaries MUST NOT appear as answers. After the verified `migrate-local-agent-interaction` prerequisite, consume the supported `@langchain/react` interaction boundary for message/tool/state projections and scoped subscriptions; do not extend the superseded custom `snapshot` / `run_event` / `stream_end` contract. Application-owned durable history, run identity, reconnect/hydration and authorization remain authoritative; reconcile SDK updates into one saved result and avoid rewriting the entire growing run for every token.

Expose effective setup, actual selected tools/results, observed planning, context capacity/usage/compaction, approvals and loading/empty/error/reconnect states. Provide safe Markdown/code/table rendering, copy and access-checked open/save actions, keyboard controls and scrolling that respects the user's position. Generated HTML/scripts MUST NOT execute in the trusted renderer; opening/saving is not execution authority.

The `repair-local-interaction-boundaries` prerequisite SHALL remain satisfied: selection and transport binding stay atomic, stale callbacks are generation-guarded, command configuration and draft ownership are isolated, and accepted work is never retargeted or repeated by navigation. External links SHALL retain main-owned HTTP(S) validation and requesting-document/frame authorization; neither untrusted windows nor replacement documents gain the backend token.

#### Scenario: Reconnect and terminal result

- **WHEN** a streamed turn reconnects or completes while the user switches conversations
- **THEN** snapshots/events and final hydration produce one correctly attributed saved answer with partial/tool content intact.

#### Scenario: History and rendering

- **WHEN** history is archived or generated code/HTML is displayed
- **THEN** archive does not erase execution context and content cannot execute with desktop privileges.

### Requirement: API-011 - Keep background work visible and quit deliberately

Closing the main window or event stream SHALL NOT cancel or resubmit a run. Ongoing work SHALL have visible tray/background state and a route back. Explicit Quit with active work SHALL offer keep running or stop owned work and exit. Shutdown SHALL reconcile owned runs/clients/savers/processes and retain unresolved external outcomes; externally connected engines MUST NOT be terminated as owned processes. Reopening reconnects to existing work.

#### Scenario: Close reopen and quit

- **WHEN** a user closes/reopens the desktop or explicitly quits during work
- **THEN** close/reopen preserves the same run; Quit makes the keep-running versus stop-owned-work decision explicit and reconciles its outcome.

### Requirement: API-016 - Present one conversation-led desktop shell

The desktop SHALL provide one collapsible sidebar with General chats and collapsible named projects containing their permanently scoped conversations, New chat, cross-area retained-history search, rename, archive and reopen. The conversation header SHALL show its project or General identity; choosing a different area SHALL open or create another conversation rather than move or detach the current one. Removed-project history SHALL retain its identity.

Compact destinations SHALL provide Models, Agents, Knowledge, Library, Lab and Workflows as their owning packets deliver functionality, with Settings at the bottom. Existing Agent run and its history SHALL remain accessible through the transition to Workflows. The conversation SHALL remain central with a visible composer and an on-demand right-hand panel for files, previews, changes and detailed activity. Full and half-screen windows SHALL be normal supported layouts; secondary panels SHALL collapse before compromising ordinary conversation/composer use. Primary journeys MUST NOT require interpreting raw JSON, internal identifiers or backend terminology; technical details SHALL remain available on expansion.

Light and dark themes SHALL follow Windows by default with a user override. Compact controls SHALL retain readable labels, accessible names, visible keyboard focus and usable click targets. Reduced motion SHALL be respected. Settings SHALL expose appearance, notifications, saved grants and manual backup/restore; connection management is added by Packet 04 using the same surface.

#### Scenario: Switch project without relocating a conversation

- **WHEN** a user selects another project from the shared sidebar and then reopens an earlier chat
- **THEN** each chat retains its original area, the header identifies that area and the composer/draft belongs to the selected chat.

#### Scenario: Compact window and keyboard use

- **WHEN** the application uses a half-screen window, Windows scaling or keyboard-only navigation
- **THEN** secondary panels can collapse while navigation, readable replies, composer and labelled settings remain accessible without ordinary controls requiring horizontal scrolling.

### Requirement: API-017 - Expose compact effective model controls and measurements

The conversation window SHALL visibly expose selectable model, supported reasoning effort or Thinking off, and the active setup, with compact attachment/tool/permission controls beside the composer and focused popovers for details. Existing profiles SHALL remain usable before Packet 04 delivers reusable agent setups. Changes SHALL affect future submissions without rewriting active turns or queued intended configuration. Unsupported/overridden/unverified reasoning controls SHALL be labelled truthfully; hiding returned thinking MUST NOT be represented as disabling model reasoning.

Compact status elements SHALL expose current context fill and generation speed in tok/s, with capacity, counting/measurement basis and relevant interval available on expansion. Observed measurements, labelled estimates and unavailable values SHALL remain distinguishable. Stream chunks MUST NOT be counted as tokens; absent usage MUST NOT appear as zero. Context changes/compaction and current versus completed-turn measurements SHALL remain attributable rather than silently showing stale values as current.

Context details SHALL open on pointer hover and keyboard focus, with touch access and Escape dismissal. Prefer model-reported request input/output counts over preflight estimates once available. Supported llama.cpp timing streams SHALL supply live generation speed with bounded updates and no shared-slot polling; measurements SHALL reset at each model-call boundary and retain their current/completed/interrupted status. Compact settings SHALL avoid redundant default-value cards while preserving actionable failures, meaningful choices and accessible explanations.

Sending with a stopped installed managed model SHALL load the selected setup through the existing model manager/admission path, show waiting/loading/readiness and submit once ready. Failure SHALL preserve the user's input and offer recovery. Conflicts SHALL be explained before disruptive action; active-work protections and connected-endpoint ownership MUST NOT be bypassed and models/settings MUST NOT be silently substituted.

#### Scenario: Unsupported reasoning and unavailable telemetry

- **WHEN** the selected model lacks a supported thinking-off control or supplies no usable token measurement
- **THEN** the control/measurement explicitly reflects that limitation rather than claiming thinking is off or showing an invented tok/s value.

#### Scenario: Start from Chat with a resource conflict or failure

- **WHEN** a submitted draft selects an installed stopped model and loading conflicts with existing work or fails
- **THEN** the draft remains recoverable, the conflict/failure and corrective action are visible, no protected work is silently disrupted and retry cannot duplicate accepted work.

### Requirement: API-018 - Keep answer streaming independent of detail visibility

Answer text SHALL always appear incrementally. A compact detailed-stream toggle SHALL default off and remember the user's preference across conversations/reopening. When enabled, available returned thinking, tool calls/results, file activity and other output SHALL be distinctly labelled/formatted apart from answers; absent streams MUST NOT be fabricated. When disabled, compact progress with subtle shimmer SHALL replace expanded activity while answer text continues streaming. Motion preferences SHALL be respected.

Each output section SHALL independently expand/collapse through a heading or chevron, overriding the global presentation for that section without disrupting text selection or links. Approvals, typed questions and errors SHALL remain visible in both modes. Toggling presentation MUST NOT change execution, permission, saved content or the user's scroll position. Branch, Retry task and Regenerate answer actions SHALL remain visibly distinct and obey AGT-012, including truthful unsupported states and repeated-effect disclosure.

#### Scenario: Hide details while an answer streams

- **WHEN** a user disables detailed streams during generation and expands one tool result
- **THEN** answer text continues, other detailed activity stays compact, the chosen result opens independently and execution/content identity remains unchanged.

#### Scenario: Interrupt during compact presentation

- **WHEN** an approval, typed question or error occurs with detailed streams hidden
- **THEN** the actionable card remains visible and cannot be mistaken for continuing generation or hidden by collapsing activity.

### Requirement: API-019 - Present queued work and scoped attention clearly

During active work the composer action SHALL read Queue with a separate Stop control. An expandable queue above the composer SHALL expose editable/removable messages, attachments and intended setup. AGT-010 SHALL govern persistence, dispatch and progression: only success advances automatically, failure/cancellation pauses, and approval/input waits do not advance. Header setting changes MUST NOT silently mutate queued items.

Inline approval cards SHALL show exact action/resource scope and the four AGT-008 choices, explaining broader grant scope before selection. Saved grants SHALL remain inspectable/revocable in Settings. Sidebar badges and a compact attention list SHALL identify conversations waiting for approval/input or needing failure recovery. Windows notifications SHALL default on for those events while the application is backgrounded, subject to OS/user settings; successful completion notifications SHALL default off. Notifications MUST NOT steal focus, auto-switch conversation or answer interruptions. User activation SHALL navigate to the corresponding current conversation/attention state without replaying work; in-app attention SHALL remain usable when OS notifications are unavailable.

#### Scenario: Queue with independent configuration

- **WHEN** a user queues a follow-up, changes the selected model and then the active turn fails
- **THEN** the queue pauses with its original intended model/setup visible and editable, and Stop/Queue remain distinct from approval actions.

#### Scenario: Background approval and notification navigation

- **WHEN** another conversation requests approval while the app is backgrounded
- **THEN** its badge/attention entry and allowed Windows notification identify it without moving focus, and opening it presents the current interruption rather than accepting a stale decision.

### Requirement: API-020 - Separate technical verification from human UX acceptance

Each affected packet SHALL demonstrate its end-to-end user journey in the built Windows application and record technical verification separately from Dave's UX acceptance in its existing design/PR. Reviews SHALL cover full and half-screen windows, actual Windows display scaling, keyboard navigation, long conversation/result content and at least one failure/recovery state. Screenshots alone MUST NOT count as interaction verification. Required technical/live checks SHALL remain required; UX acceptance SHALL remain pending until Dave accepts the built experience or explicitly defers review, with deferral recorded as deferred rather than accepted.

Packet 03 SHALL include an early Chat layout review after the basic arrangement is exercisable and before the remaining controls accumulate, including the existing Models-to-Chat journey. Packets 04, 05 and 07 SHALL include major everyday-workspace, Lab and Workflows reviews; 06 and 08 SHALL include focused activity/approval and media reviews. Lab and Workflows SHALL each require an approved detailed layout before substantial interface implementation. Specification approval MUST NOT be treated as visual acceptance of the built product.

#### Scenario: Technical checks pass before user review

- **WHEN** automated checks and agent-driven Windows interaction pass but Dave has not reviewed or explicitly deferred the experience
- **THEN** technical results are recorded as such while UX acceptance remains pending.

#### Scenario: Explicitly deferred review

- **WHEN** Dave explicitly defers a milestone's UX review
- **THEN** its existing design/PR records the deferral separately from technical evidence and does not claim UX acceptance or waive required live checks.
