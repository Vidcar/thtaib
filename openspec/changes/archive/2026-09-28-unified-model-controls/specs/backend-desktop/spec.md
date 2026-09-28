## ADDED Requirements

### Requirement: API-054 - Keep unified controls in their owning surface

Models SHALL own saved model setups, response recipes/budgets/sampling, memory and hardware controls. Its primary Save action SHALL record settings without starting/reloading a model or navigating to Chat. Model load/unload SHALL be separate lifecycle actions. Naming/copy actions SHALL be secondary. Agents SHALL own agent settings and save without a cross-page launch action. Settings SHALL own shared engine connections/residency. Lab and Workflows SHALL reuse saved setups and display executed settings with their task-specific controls.

Chat SHALL expose model/setup selection and chat-local Thinking and context-size adjustments. Thinking SHALL apply to the next accepted input without changing the saved setup, explicit saved samplers or already accepted work. Context changes SHALL show an impact preview and require a deliberate reload when idle; active work SHALL stage the next submission through safe admission. Detailed budget/sampling/hardware editing SHALL stay in Models. No Chat promotion action SHALL change model defaults.

#### Scenario: Save stays in Models
- **WHEN** a model setup is edited and saved
- **THEN** its revision and response/loading choices are saved without loading, reloading or navigation.

#### Scenario: Local chat tuning
- **WHEN** Thinking or context is changed in one chat
- **THEN** that chat retains the local choice, other chats and saved setups remain unchanged, and already accepted work retains its snapshot.

#### Scenario: Busy context choice
- **WHEN** a context change is made during active work
- **THEN** the candidate is staged for the next submission and no active model call is interrupted.

#### Scenario: Compact accessible controls
- **WHEN** controls are used in either theme, a narrow container or scaled Windows layout
- **THEN** their labels, values, source/timing, focus and actionable errors remain readable; slider values permit exact keyboard input and drafts survive closing/navigation.

## MODIFIED Requirements

### Requirement: API-017 - Expose compact effective model controls and measurements

Opening a conversation SHALL restore that conversation's explicit Ask or Full access choice. An application preference SHALL seed new conversations and SHALL default to Ask on a fresh installation; project and agent definitions SHALL NOT override access. A chat's explicit choice SHALL survive unrelated preference changes and MUST NOT leak from the previously viewed chat. Access labels SHALL show Ask or Full access in full; supporting policy detail SHALL be available on demand without standing explanatory prose. Descriptions and model instructions SHALL reflect saved permission grants and the actual selected mode, while explicit questions and disabled-tool boundaries remain enforced.

The composer SHALL contain, in order, `+`, access, Plan only while enabled as a removable pill, the model selector with an adjacent tuning icon, the agent selector, compact context/speed and one combined Send/Stop control. A microphone SHALL NOT be shown before speech is delivered. Agent selection SHALL follow AGT-024, including its explicitly assigned-model exception. Grouped and individual tool choices SHALL be managed only in Agents setup, not in the agent dropdown or `+`. The shield selects Ask or Full access for later messages in that chat, does not enable tools and owns live window-grant controls. Changes prepare future submissions without rewriting running or already queued work. Unsupported, overridden or unverified reasoning controls SHALL be labelled truthfully; hiding returned thinking MUST NOT be represented as disabling model reasoning.

The bounded searchable model picker SHALL show one row per model, expanding named configurations only when more than one exists. Expansion SHALL NOT load a model. Ready, loading/waiting, attention and idle dots SHALL reflect the exact configuration's observed state, with equivalent accessible hover/focus labels. Saved configurations alone SHALL NOT imply residency. The tuning icon SHALL open a compact Thinking and Conversation capacity editor. Effective Thinking changes apply to the next accepted message immediately; context choices show memory impact and require one deliberate Reload when idle or Stage for the next submission during active work. Applied chat-local overrides SHALL be remembered separately per model within that chat; first use starts with saved model defaults and returning restores those overrides. Permanent defaults, response-length controls and thinking-token-limit controls SHALL remain in Models. Applying startup changes SHALL reload only when safe and preserve the draft, attachments, history and reading position; active-work changes SHALL use the staging rule in API-028.

Compact status elements SHALL expose current context fill and generation speed in tok/s, with capacity, counting/measurement basis and relevant interval available on expansion. Observed measurements, labelled estimates and unavailable values SHALL remain distinguishable. Stream chunks MUST NOT be counted as tokens; absent usage MUST NOT appear as zero. Context changes/compaction and current versus completed-turn measurements SHALL remain attributable rather than silently showing stale values as current.

Context details SHALL open on pointer hover and keyboard focus, with touch access and Escape dismissal. Prefer model-reported request input/output counts over preflight estimates once available. Supported llama.cpp timing streams SHALL supply live generation speed with bounded updates and no shared-slot polling; measurements SHALL reset at each model-call boundary and retain their current/completed/interrupted status. Compact settings SHALL avoid redundant default-value cards while preserving actionable failures, meaningful choices and accessible explanations.

Opening the application or restoring a chat SHALL NOT warm its selected model. Sending with an unloaded installed managed model SHALL load the selected setup through the existing manager and admission path, show waiting/loading/readiness, then submit once ready. Failure SHALL preserve input and offer recovery. A passive status probe MUST NOT cause loading. Active-work protections and connected-endpoint ownership MUST NOT be bypassed and models/settings MUST NOT be silently substituted.

Chat SHALL expose one live activity status beside the composer Stop control. Model output SHALL be labelled Generating without inferring current reasoning from retained content. Current tool execution, prompt preparation, summarization, approval waiting, finalization and cancellation SHALL remain distinguishable; pending admission SHALL show Starting and unknown active activity SHALL show Working. Activity-only changes SHALL update the status even without a new audit event. Terminal work SHALL NOT retain a live activity label, and late observations from another selection or run SHALL NOT replace the selected status. Measurement updates SHALL remain isolated from transcript rendering.

The context/speed hover panel SHALL retain total context, capacity, percentage and available input-total, cached-input, newly-processed-input and output counts in aligned label/value rows. Numbers SHALL remain intact at narrow widths and larger text sizes. Cached and newly processed input SHALL be identified as subdivisions of input total. Current and last-request speed, estimates and unavailable measurements SHALL remain explicit.

#### Scenario: Unsupported reasoning and unavailable telemetry
- **WHEN** the selected model lacks a supported thinking-off control or supplies no usable token measurement
- **THEN** the control/measurement explicitly reflects that limitation rather than claiming thinking is off or showing an invented tok/s value.

#### Scenario: Cold launch and first Send
- **WHEN** Workbench opens a chat whose selected model is unloaded, then the person submits a draft
- **THEN** launch remains cold, Send shows loading and submits once that exact configuration is ready, while failure preserves the draft and cannot duplicate accepted work.

#### Scenario: Start from Chat with a resource conflict or failure
- **WHEN** a submitted draft needs an unloaded model while another request holds the only slot or loading fails
- **THEN** Chat shows waiting or the failure with a corrective action, preserves the draft and cannot duplicate accepted work.

#### Scenario: Setup stays off the transcript
- **WHEN** a person opens tuning beside the selected model
- **THEN** one bounded editor shows effective Thinking choices and context with deliberate Reload or Stage, and no response-length or thinking-token-limit control.

#### Scenario: Inherited access follows its named source
- **WHEN** the application preference changes after a chat explicitly selected Ask
- **THEN** that chat remains Ask while a new chat takes the current application preference, and Chat names the preference source when no explicit choice exists.

#### Scenario: Bounded everyday reasoning and scoped measurements
- **WHEN** the user selects a template-effective Thinking level and later an internal summary runs
- **THEN** Chat SHALL show the supported effective effort and distinguish work, summary, cached input, current measurements and completed measurements without inventing unavailable values or adding response/thinking-token-limit controls.

#### Scenario: Tool activity changes without an audit event

- **WHEN** an owned live run changes from tools to model generation without increasing its audit event count
- **THEN** the composer status changes from Using tools to Generating with the current measurements
- **AND** late events from another conversation or completed run cannot restore stale activity.

#### Scenario: Read measurements in a narrow panel

- **WHEN** all four token counts are available in a narrow window or with larger text
- **THEN** each label and intact number occupies a readable aligned row
- **AND** the panel explains input subdivisions and whether the speed is current or from the last request.

#### Scenario: Return to a model in the same chat

- **WHEN** the person applies chat-local tuning to model A, uses model B, then returns to A
- **THEN** A's chat-local tuning is restored without changing either model's permanent defaults or another chat's overrides.
