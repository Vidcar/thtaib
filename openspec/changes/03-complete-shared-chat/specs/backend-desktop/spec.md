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
