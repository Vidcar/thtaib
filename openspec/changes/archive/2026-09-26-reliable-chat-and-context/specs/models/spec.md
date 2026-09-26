## MODIFIED Requirements

### Requirement: MOD-017 - Budget real context and preflight continued conversations

The initialized model SHALL expose usable input capacity from available runtime observations, explicit output reservation and a disclosed counting margin. Include instructions, history, tool schemas and applicable media overhead without double subtraction. Training metadata, cloud aliases and library defaults MUST NOT become verified running capacity. Counts and unknown capacity SHALL be labelled.

Use one existing Deep Agents context/summarisation path; both normal and summarisation requests SHALL fit or fail actionably. Housekeeping remains available with tools off and internal summaries are not user answers. Before changing model/configuration on a continuing thread, validate actual pending content against known context, message, tool, image and structured-output constraints. Do not silently remove attachments, instructions or tool-result pairs. Offer a compatible setup, fitting compaction or deliberate fresh/supported branch outcome. Publish capacity, input estimate/usage, counting method, reservation and compaction events to shared inspectors.

#### Scenario: Small context

- **WHEN** a continued request or its compaction request exceeds usable capacity
- **THEN** the supported fitting path is used or an actionable capacity error appears without silent truncation.

#### Scenario: Model switch

- **WHEN** a user selects a known-incompatible model for retained messages or media
- **THEN** dispatch is blocked with the specific constraint; unknown capability remains labelled unknown.

Accounting SHALL use the same outbound representation as dispatch and count each reasoning, content, tool argument and schema once. Native reduction SHALL run before rejecting reducible history. Work and summarization measurements SHALL remain separately attributable, including the evidence responsible for an overflow.

Reasoning replay capability SHALL be distinct from preservation of earlier user turns. A replay-capable template with history preservation disabled SHALL still receive the current tool cycle's reasoning. Explicit full-history preservation SHALL retain earlier reasoning; unsupported replay SHALL send none. Thinking generation on/off SHALL remain a separate setting. The same pure projection SHALL supply transport, preflight and compaction counting without changing checkpoints or the selected runtime settings. Application-supplied tool images SHALL remain tool-response context rather than becoming a new user-query boundary in templates that distinguish that boundary.

#### Scenario: History preservation disabled during a tool cycle
- **WHEN** a replay-capable model has completed an earlier user turn and is continuing the current turn after tools return
- **THEN** current-cycle reasoning SHALL remain in the outbound request and earlier-turn reasoning SHALL follow the selected native history policy
- **AND** tool-image projection SHALL preserve that distinction, while estimates SHALL count exactly the transmitted representation once.

#### Scenario: Thinking generation switched off
- **WHEN** the user disables new thinking generation on a replay-capable setup
- **THEN** that setting SHALL NOT erase reasoning needed to continue the current tool cycle or silently change its history-preservation policy.


The product SHALL offer explicit Balanced (medium effort, 2048 thinking tokens, 8192 total output tokens) and Deep (extra-high effort, 8192 thinking tokens, 16384 total output tokens) presets separate from publisher recipes. Balanced SHALL seed ordinary new Chat use. Unsupported independent thinking limits SHALL be labelled as response-limit-only; startup settings and saved publisher recipes SHALL remain distinct.

#### Scenario: Duplicate reasoning representation
- **WHEN** one reasoning string exists in both native content and additional metadata
- **THEN** context accounting SHALL count only the outbound representation and SHALL NOT trigger compaction due to duplicate storage.

#### Scenario: Response limit interrupts tool input
- **WHEN** generation reaches its configured limit during tool arguments
- **THEN** partial arguments SHALL remain inert and the chat SHALL offer an actionable continuation instead of becoming permanently blocked.

### Requirement: MOD-022 - Apply managed configuration changes safely

Idle managed configurations SHALL support validated reconfiguration with expected-version and retained-history compatibility checks. Startup edits SHALL preserve the current launch snapshot until an explicit safe reload; active, queued, waiting, cancelling, Lab and helper consumers SHALL block a configuration binding change with named reasons. An explicit response-only configuration switch MAY update the existing deployment binding without reloading only when the selected configuration and requested operation match its frozen launch identity, the owned process still matches and fresh runtime observations confirm health. Automatic listen ports SHALL use the established configuration identity normalization; the actual frozen startup and process identity SHALL remain unchanged. Saved publisher recipes SHALL not be repurposed as product presets.

Capacity-driven eviction of an idle model instance MAY occur between calls, including during an alternate-model helper handoff, provided no in-flight inference request is interrupted and the next call can reload its exact selected configuration. Automatic child ports SHALL be allocated and checked at launch; fixed-port conflicts fail before spawn. Ownership and observed readiness SHALL precede committing loaded values. Failure SHALL preserve prior and attempted configurations, attempt at most one safe restoration and report truthful stopped/failed state; restart SHALL reconcile interrupted changes. Connected endpoints SHALL not grant reload authority.

#### Scenario: Response-only Balanced selection
- **WHEN** an idle healthy owned model selects a separate saved Balanced configuration with the same frozen launch identity
- **THEN** the same deployment and process SHALL use that configuration's response values for the next request without stop or start
- **AND** actual startup, model files, publisher recipe configuration and its provenance SHALL remain unchanged.

#### Scenario: Idle conversation context change
- **WHEN** an idle conversation applies a valid context change
- **THEN** the owned model reloads and the same conversation continues with verified capacity
- **AND** its draft and history survive.

#### Scenario: Queued consumer blocks reload
- **WHEN** a queued or waiting turn depends on a configuration being edited
- **THEN** reconfiguration identifies that consumer without discarding its selected setup.

#### Scenario: Capacity handoff between calls
- **WHEN** one loaded slot is needed by a different-model helper after the parent's model call ends
- **THEN** the helper loads its exact configuration and the parent reloads its own configuration before its next call
- **AND** neither in-flight inference request is stopped.

#### Scenario: Conflicting or failed launch
- **WHEN** the requested configuration fails to become ready
- **THEN** no unrelated process is stopped or healthy foreign endpoint claimed
- **AND** prior selection and a usable recovery path remain.
