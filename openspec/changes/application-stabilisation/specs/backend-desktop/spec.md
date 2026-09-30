## MODIFIED Requirements

### Requirement: API-004 - Expose real state and evidence

The backend and desktop SHALL present run hierarchy, streamed progress, approvals, artifacts, checks, applied configuration, and relevant context or knowledge information from records and events. Active, queued, resource-constrained, failing, `cancel_requested`, and `cancelled` states SHALL be distinguishable. Model confidence, preview text, service readiness, or disconnected clients MUST NOT be treated as completed work.

#### Scenario: Cancellation visibility

- WHEN a live run is cancelled
- THEN visible state MUST show `cancel_requested` until the worker records confirmed `cancelled`
- AND a later persisted outcome MUST match execution records.

#### Scenario: Accepted action followed by failed observation
- **WHEN** a Lab or Chat action has been accepted but its immediate status read fails
- **THEN** the desktop SHALL retain its accepted identity, show observation as unavailable, and retry observing the same work
- **AND** it SHALL NOT present a different completed run or encourage repeating the accepted action as a refresh.

#### Scenario: Observations complete out of order
- **WHEN** an initial Browser read or earlier attention refresh completes after newer accepted state
- **THEN** it SHALL NOT replace that newer state, suppress current frames, or erase its error and attention count.

### Requirement: API-007 - Launch locally and keep desktop state honest

The Windows launcher SHALL reuse a healthy product backend or start it hidden, then open the built Electron desktop. The first screen SHALL request projects and chats independently. Each list SHALL be readable before either request finishes. A list that has not finished SHALL NOT be presented as empty. Failure to reach the service SHALL retry until the first success. Chat SHALL keep the composer visible while transcript and history scroll independently. Recent conversations SHALL appear first. New Chat SHALL retain an explicit current Chat model choice. When no choice exists, it SHALL select the sole healthy running chat deployment; with several healthy running choices it SHALL request an explicit choice. It MUST NOT apply unrelated saved profiles. Stopped deployments MUST NOT gain healthy labels from stale probes.

The lower-left status dot is the only startup status. Its hover is one short phrase for reading the catalogue, starting the model, ready, or the service being unavailable. The visible word stays "Local" while the service is up, including while the rail is collapsed down to the dot.

Opening a finished chat SHALL show its saved transcript and latest display snapshot. It MUST NOT scan that chat's token log. The chat list MUST NOT include transcripts, run bodies, or model-request logs.

Each catalogue list SHALL retain its own loading and failure state. Only a successful response for the current list selection SHALL permit its empty-list state. Failed reads SHALL retry with capped backoff until first success or disposal; success for one list MUST NOT clear another list's failure. Unmounting or changing the relevant selection SHALL cancel obsolete retries, and late responses MUST NOT overwrite the replacement state.

#### Scenario: Initial catalogue failure outlasts thirty reads

- **WHEN** one or both initial catalogue reads fail more than thirty times
- **THEN** each failed list remains unresolved with its own visible failure and continues retrying with capped backoff
- **AND** a later success recovers that list without clearing another list's failure or presenting it as empty or ready.

#### Scenario: A catalogue reader is replaced or unmounted

- **WHEN** the relevant list selection changes or the sidebar unmounts while a read or retry is pending
- **THEN** its obsolete retries are cancelled and its late success or failure cannot change the replacement list's content, error or readiness.

#### Scenario: Desktop launch and model state

- WHEN the launcher opens the application and a stopped deployment has an old probe
- THEN the desktop MUST present current backend state
- AND catalogue loading MUST be explicit rather than shown as an empty catalogue
- AND projects MAY appear before chats

#### Scenario: Finished chat opens from the saved transcript

- WHEN a person opens a chat whose answer is already saved
- THEN the saved answer is shown
- AND the token log is not read to paint it

#### Scenario: New Chat with a running model

- **WHEN** no Chat model has been chosen and exactly one healthy chat deployment is running
- **THEN** New Chat shows and submits that deployment's exact configuration without starting it again.

#### Scenario: Several running models

- **WHEN** no Chat model has been chosen and several healthy chat deployments are running
- **THEN** New Chat asks for an explicit model choice rather than silently selecting one.

#### Scenario: Chat startup reads recover independently
- **WHEN** Chat's model, setup, project or history reads fail and later recover independently
- **THEN** only successful model and bundle reads SHALL permit an empty-workspace state, and each failed resource SHALL retain its own error until recovery
- **AND** retries SHALL be bounded in frequency and cancelled on owner disposal; obsolete responses SHALL NOT overwrite newer state or user edits, and passive reads SHALL NOT start a model.

### Requirement: API-010 - Present durable Chat state without duplicating or inventing work

Every displayed snapshot SHALL pair message text, run state and resume cursor from the same observation. Completion and token-log compaction MUST NOT remove a message while hydration or reconnect prepares it. A native finished message SHALL remain readable until its authoritative graph message arrives. The desktop MUST advance its resume cursor only after a complete event frame has arrived; disconnecting inside a frame MUST replay that frame.

Existing Chat SHALL support new, rename, archive, retained-title/message search and reopen. Archive changes visibility, not memory/context. Incremental answers, separate returned reasoning, tool content and partial failures SHALL reconcile by run/thread/message/call identity into one final saved result. Internal summaries MUST NOT appear as answers. After the verified `migrate-local-agent-interaction` prerequisite, consume the supported `@langchain/react` interaction boundary for message/tool/state projections and scoped subscriptions; do not extend the superseded custom `snapshot` / `run_event` / `stream_end` contract. Application-owned durable history, run identity, reconnect/hydration and authorization remain authoritative; reconcile SDK updates into one saved result and avoid rewriting the entire growing run for every token.

Submitted user text SHALL display literally with original backslashes, punctuation, line breaks and indentation preserved, while long text wraps within the bubble. Model-only context additions MUST NOT appear as user-authored text. Assistant replies SHALL retain safe Markdown, code and table rendering.

Expose effective setup, actual selected tools/results, observed planning, context capacity/usage/compaction, approvals and loading/empty/error/reconnect states. Provide safe Markdown/code/table rendering, copy and access-checked open/save actions, keyboard controls and scrolling that respects the user's position. Generated HTML/scripts MUST NOT execute in the trusted renderer; opening/saving is not execution authority.

The `repair-local-interaction-boundaries` prerequisite SHALL remain satisfied: selection and transport binding stay atomic, stale callbacks are generation-guarded, command configuration and draft ownership are isolated, and accepted work is never retargeted or repeated by navigation. External links SHALL retain main-owned HTTP(S) validation and requesting-document/frame authorization; neither untrusted windows nor replacement documents gain the backend token.

#### Scenario: Reconnect and terminal result

- **WHEN** a streamed turn reconnects or completes while the user switches conversations
- **THEN** snapshots/events and final hydration produce one correctly attributed saved answer with partial/tool content intact.

#### Scenario: History and rendering

- **WHEN** history is archived or generated code/HTML is displayed
- **THEN** archive does not erase execution context and content cannot execute with desktop privileges.


#### Scenario: Exact submitted user text
- **WHEN** a person submits a Windows path, backticks, Markdown punctuation, blank lines or indented text
- **THEN** the user bubble SHALL retain those characters and spacing literally without interpreting them as Markdown or HTML
- **AND** assistant Markdown and code remain formatted, attachments remain accessible, and model-only context notices remain outside the user bubble.

#### Scenario: Submission accepted into a busy project's queue
- **WHEN** Send is durably accepted while another task owns the project folder
- **THEN** acknowledgement and desktop reconciliation SHALL identify that exact queued input without inventing a run or associating a previous completed run
- **AND** recovery after a lost acknowledgement SHALL recognise that same accepted identity, clear only its submitted draft revision, and observe its later execution without submitting it again.


### Requirement: API-011 - Keep background work visible and quit deliberately

Closing the main window or event stream SHALL NOT cancel or resubmit a run. Ongoing work SHALL have visible tray/background state and a route back. Explicit Quit with active work SHALL offer keep running or stop owned work and exit. Shutdown SHALL reconcile owned runs/clients/savers/processes and retain unresolved external outcomes; externally connected engines MUST NOT be terminated as owned processes. Reopening reconnects to existing work.

#### Scenario: Close reopen and quit

- **WHEN** a user closes/reopens the desktop or explicitly quits during work
- **THEN** close/reopen preserves the same run; Quit makes the keep-running versus stop-owned-work decision explicit and reconciles its outcome.

#### Scenario: Quit with retained paused input
- **WHEN** deliberate Quit has paused queued input and confirmed that owned workers have stopped
- **THEN** retained paused input SHALL NOT prevent shutdown of the owned managed engine
- **AND** the queued input, frozen setup, cancellation identity and unresolved outcome evidence SHALL remain retained for deliberate later recovery; live work that has not confirmed stopping SHALL still block shutdown, and connected engines SHALL remain untouched.
