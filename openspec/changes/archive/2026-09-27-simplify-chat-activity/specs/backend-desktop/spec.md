# Spec Delta

## MODIFIED Requirements

### Requirement: API-017 - Expose compact effective model controls and measurements

Opening a conversation SHALL restore that conversation's explicit Ask or Full access choice. An application preference SHALL seed new conversations and SHALL default to Ask on a fresh installation; project and agent definitions SHALL NOT override access. A chat's explicit choice SHALL survive unrelated preference changes and MUST NOT leak from the previously viewed chat. Access labels SHALL show Ask or Full access in full and explain that running and already queued messages keep their selected policy. Descriptions and model instructions SHALL reflect saved permission grants and the actual selected mode, while explicit questions and disabled-tool boundaries remain enforced.

The conversation SHALL visibly expose separate main-model and main-agent selectors beside the composer, supported reasoning effort or Thinking off, a removable Plan pill, compact attachments, capability groups and access. One model picker row SHALL represent one installed model; its named configurations SHALL be secondary choices. Changing an agent SHALL NOT silently change the main model. The shield selects Ask or Full access for later messages in that chat and does not turn tools on or off. The `+` menu SHALL expose optional capability groups and attachments without a list of individual tool toggles; project files remain available in project chats, while shell, browser and Windows control require explicit conversation choices. The setup rail SHALL start closed and MUST NOT take height from the transcript while closed. Changes SHALL affect future submissions without rewriting active turns or queued intended configuration. Unsupported, overridden or unverified reasoning controls SHALL be labelled truthfully; hiding returned thinking MUST NOT be represented as disabling model reasoning.

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
- **WHEN** a person opens the conversation rail to Setup
- **THEN** setup sits in that rail and the transcript remains readable beside or above it.

#### Scenario: Inherited access follows its named source
- **WHEN** the application preference changes after a chat explicitly selected Ask
- **THEN** that chat remains Ask while a new chat takes the current application preference, and Chat names the preference source when no explicit choice exists.

#### Scenario: Bounded everyday reasoning and scoped measurements
- **WHEN** the user selects Balanced or Deep and later an internal summary runs
- **THEN** Chat SHALL show the effective supported thinking/response limits and distinguish work, summary, cached input, current measurements and completed measurements without inventing unavailable values.

#### Scenario: Tool activity changes without an audit event

- **WHEN** an owned live run changes from tools to model generation without increasing its audit event count
- **THEN** the composer status changes from Using tools to Generating with the current measurements
- **AND** late events from another conversation or completed run cannot restore stale activity.

#### Scenario: Read measurements in a narrow panel

- **WHEN** all four token counts are available in a narrow window or with larger text
- **THEN** each label and intact number occupies a readable aligned row
- **AND** the panel explains input subdivisions and whether the speed is current or from the last request.

### Requirement: API-018 - Keep answer streaming independent of detail visibility

Answer text SHALL always appear incrementally, including through a long reply. Painting the reply MUST stay with generation: earlier finished messages, and finished parts of the same reply, stay in place and remain readable. A compact Reasoning and tools switch in the header's Conversation view menu SHALL default off and remember the user's preference across conversations/reopening. Its presentation controls stay distinct from model Thinking and effort controls. Changing this switch SHALL only change the visibility of returned detail, never model reasoning or tool permissions. The composer Stop control is the only stop. Chat does not show a separate Activity row with its own cancel control. When enabled, available returned thinking, tool input, tool output and other raw detail SHALL be distinctly labelled apart from answers; absent streams MUST NOT be fabricated. When disabled, that expanded detail stays collapsed while answer text continues streaming. The planning checklist and the one-line activity rows in API-026 remain visible in both modes. Motion preferences SHALL be respected.

While a reply is running and the person is already at the bottom, the transcript SHALL follow the newest line immediately. Scrolling away stops following. Returning to the bottom follows again. Following sets the position directly. Smooth scrolling is reserved for an explicit jump, such as opening a chat or a notice, and reduced motion stays immediate. A text selection inside the transcript MUST be left in place. An open reasoning section follows the newest line the same way until the person scrolls inside that section, and the full reasoning text stays reachable by scrolling. Token growth MUST NOT be announced as a stream of accessibility updates. The composer status is the sole generic live activity announcement. Main Chat SHALL NOT repeat it as active response badges or generic transcript progress lines. Returned reasoning and named tool/helper activity SHALL remain visible according to the presentation preference; interrupted historical responses SHALL retain their Partial markers.

A speed or context measurement SHALL update its readout only. It MUST NOT rebuild the transcript, move the scroll position, delay the next tokens, or change execution.

Each output section SHALL independently expand/collapse through a heading or chevron, overriding the global presentation for that section without disrupting text selection or links. Approvals, typed questions and errors SHALL remain visible in both modes. Toggling presentation MUST NOT change execution, permission, saved content or the user's scroll position. Copy, Regenerate answer and Branch SHALL appear on each saved assistant answer and SHALL NOT appear while that answer is still streaming. Copy on an answer SHALL copy that answer's text. Chat code blocks, tool input and tool output SHALL each provide a copy icon. Unavailable Regenerate answer or Branch SHALL stay disabled with the truthful reason rather than retrying the task. Retry task, edit-the-task, export and delete SHALL remain on the Actions page of the conversation rail. That page MUST NOT cover the transcript. Retry task SHALL disclose possible repeated effects before it runs. Branch, Retry task and Regenerate answer SHALL remain visibly distinct and obey AGT-012.

#### Scenario: Hide details while an answer streams

- **WHEN** a user disables detailed streams during generation and expands one tool result
- **THEN** answer text continues, other raw tool input and output stay collapsed, the chosen result opens independently and execution/content identity remains unchanged.

#### Scenario: Interrupt during compact presentation

- **WHEN** an approval, typed question or error occurs with detailed streams hidden
- **THEN** the actionable card remains visible and cannot be mistaken for continuing generation or hidden by collapsing activity.

#### Scenario: Actions on a saved answer

- **WHEN** a saved assistant answer is shown
- **THEN** Copy, Regenerate answer and Branch are on that answer, and Retry task stays in the conversation menu until the user confirms the possible repeated effects.

#### Scenario: Copy a presented chat block

- **WHEN** a user copies a chat code block, tool input or tool output
- **THEN** that block's text is copied without changing the conversation.

#### Scenario: Planning stays visible while details are hidden

- **WHEN** detailed streams are off and the agent updates its todo list or edits a file
- **THEN** the checklist and the one-line activity row stay visible
- **AND** the raw tool arguments stay collapsed.

#### Scenario: Follow the newest line while a reply is written

- **WHEN** a long reply is streaming and the person is at the bottom of the transcript
- **THEN** the newest text stays in view as it arrives
- **AND** earlier finished messages stay where they were.

#### Scenario: Scrolling away keeps the person's place

- **WHEN** the person scrolls up during a reply, or selects text in the transcript
- **THEN** the view stays where they left it until they return to the bottom
- **AND** the selected text is not cleared by the next tokens.

#### Scenario: Speed updates leave the text alone

- **WHEN** generation speed or context usage updates during a long reply
- **THEN** the readout changes and the transcript text, scroll position, and next tokens are undisturbed.

#### Scenario: Open reasoning stays fully readable

- **WHEN** reasoning is open during a long trace and the person then scrolls up inside that section
- **THEN** the section was following the newest line until that scroll
- **AND** the earlier reasoning remains reachable.

#### Scenario: One live status with retained reasoning

- **WHEN** a response emits reasoning, executes tools and then generates an answer
- **THEN** the composer alone shows the generic current activity while reasoning and named tool details remain inspectable
- **AND** cancellation retains partial content, its Partial marker and actionable failures or approvals.
