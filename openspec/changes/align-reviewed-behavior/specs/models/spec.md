# Spec Delta

## MODIFIED Requirements

### Requirement: MOD-018 - Bound diagnostics and clean up only owned requests

The product MUST NOT persist a copy of the request the model received and MUST NOT require a stored copy of the transmitted request. The request body MUST NOT be stored. Operational errors, partial output, HTTP errors, timeouts, invalid responses, and interrupted streams SHALL remain visible as failures, not completion, without buffering the full stream before delivery. Partial delivery MUST NOT silently restart. Visible partial output and the error SHALL stay linked to the message. Credentials and embedded media MUST NOT be persisted in any diagnostic store. Sync/async clients SHALL have explicit ownership, timeouts and cleanup. Cancellation stops further application work and owned resources, not a shared deployment or caller-owned client; runtime termination remains separately confirmed or unknown. Transport deadlines are not user task budgets.

#### Scenario: Interrupted stream

- **WHEN** a response fails after partial delivery or is cancelled
- **THEN** partial output and the real error remain linked to the message, owned resources close, and neither the task nor another client is restarted or stopped
- **AND** the request body is not stored, credentials and embedded media are not persisted in any diagnostic store, and the product does not require a stored copy of the transmitted request.

### Requirement: MOD-017 - Budget real context and preflight continued conversations

The initialized model SHALL expose full per-request context capacity from available runtime observations. Upstream context management SHALL own output reservations and headroom once; the application MUST NOT reduce the advertised profile by its own output allowance or percentage margin. Include instructions, history, tool schemas and applicable media overhead without double subtraction. Training metadata, cloud aliases and library defaults MUST NOT become verified running capacity. Counts and unknown capacity SHALL be labelled.

The application SHALL keep one compaction path, owned by the existing Deep Agents agent loop, using the full observed context size and that loop's own trigger and recovery. The application MUST NOT add a second summarizer, an earlier cutoff, or its own percentage margin. Both normal and summarisation requests SHALL fit or fail actionably. Housekeeping remains available with tools off and internal summaries are not user answers. Messages on screen SHALL stay. The summary SHALL be what the model receives, not a new chat message. Before reconfiguration, retained content SHALL receive known message, tool and image compatibility checks. Before native dispatch on a continuing thread, validate message, tool, image, and structured-output compatibility. That check MUST NOT reject the send because of size before the agent loop's own recovery. A context reduction SHALL NOT be refused merely because retained history exists; the existing agent loop SHALL reduce the active prompt or fail actionably at dispatch without rewriting canonical checkpoint history. Do not silently remove attachments, instructions or tool-result pairs. The application MUST NOT silently truncate. If the reply still cannot fit after that recovery, the send SHALL fail, the chat SHALL stay, and the reason SHALL be available on the send control. The application MUST NOT offer a second conversation, a branch, or a new chat for this failure. Publish full capacity, input estimate/usage, counting basis, configured output and compaction events to shared inspectors. Approximate application observations MUST NOT independently reject a request or establish a hidden early compaction limit.

#### Scenario: Small context

- **WHEN** a continued request or its compaction request exceeds usable capacity
- **THEN** the existing agent loop uses its own recovery, or the send fails, without silent truncation
- **AND** messages on screen stay, the summary is what the model receives rather than a new chat message, and the app does not offer a second conversation, a branch, or a new chat.

#### Scenario: Reply still cannot fit

- **WHEN** the existing agent loop has recovered and the reply still cannot fit
- **THEN** the send fails, the chat stays, and the reason is available on the send control
- **AND** the app does not silently truncate or offer a second conversation, a branch, or a new chat.

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

The product SHALL use compatible pinned-card recommendations and template-effective Thinking choices without invented response bundles. Explicit total-output limits SHALL remain exact; absent an explicit finite setting, native generation SHALL use Unlimited. Publisher metadata MUST NOT silently impose an output ceiling. Accepted exact settings SHALL remain frozen across queues, helpers, retries and resumes. Thinking on/off MUST NOT change advertised capacity or introduce an automatic fraction-based output reservation.

#### Scenario: Duplicate reasoning representation
- **WHEN** one reasoning string exists in both native content and additional metadata
- **THEN** context accounting SHALL count only the outbound representation and SHALL NOT trigger compaction due to duplicate storage.

#### Scenario: Response limit interrupts tool input
- **WHEN** generation reaches its configured limit during tool arguments
- **THEN** partial arguments SHALL remain inert and the chat SHALL offer an actionable continuation instead of becoming permanently blocked.

### Requirement: MOD-019 - Keep capability probes specific to the tested setup

The ten checks SHALL be short requests to the existing local model server, in this order, using these labels: Text streaming, Tool round trip, Native structured output, Structured output via a tool, Native JSON after a tool, Formatter after a task tool, Thinking, Thinking history, Image input, and Image returned by a tool. Reusable probes SHALL exercise shared-adapter streaming, a harmless real tool round trip, structured output and suitable reasoning/image support through those checks. Records SHALL retain test inputs/outcomes, runtime/deployment/bundle, template/projector and effective response/Thinking/history settings. Behavioral evidence SHALL persist in user data and be reusable across replacement deployments when the weight files, projector, template and runtime match. Mutable labels, revision-only changes, process IDs and endpoint changes SHALL NOT invalidate managed proof. Changing Thinking on the saved setup SHALL make the Thinking and Thinking history results no longer apply and SHALL leave the other eight checks in place. After the next healthy load, those missing checks SHALL run. A chat-menu Thinking change SHALL apply to the next message, SHALL NOT change the saved setup, and SHALL NOT run a check. Changing sampling (temperature, top-k, top-p, min-p, repeat penalty, presence penalty, and frequency penalty) or the maximum answer length SHALL leave all ten results in place. A chat Thinking change or a sampling change MUST NOT launch probes by itself. Proof follows the weight files, projector, template and runtime. Changing context, key or value cache precision, cache location, GPU layers, flash attention or MTP on the same weights and projector SHALL NOT discard that proof. Changing the weight files, projector, template or runtime SHALL. Publisher guidance, recommendations, user opt-outs, tested adjustments, failed, untested and inconclusive outcomes remain distinct. A failed probe MUST NOT establish universal model incompatibility or prevent explicitly unverified ordinary use. A failed check MUST NOT block ordinary chat.

The model header SHALL show these ten checks with status and individual icon retests, plus Run all. Names SHALL appear on hover. Sound and video SHALL stay off this row and stay deferred, with no verified claim from an indicator. Failure/inconclusive SHALL be normal evidence rather than an error banner. After a healthy load, every applicable check with no saved result SHALL run on its own through the backend and SHALL NOT block chat; saved matching results SHALL be reused and SHALL prevent repeated testing on later loads. Passive reads/navigation SHALL NOT infer or load. A click SHALL update only the clicked check. Explicit retests SHALL replace only the requested check's evidence. Concurrent automatic, manual and dependent image checks SHALL share lifecycle protection and deduplication; cancelled unrun checks SHALL remain missing and retryable.

#### Scenario: Changed setup

- **WHEN** a previously tested template, projector, runtime or weight selection changes
- **THEN** old evidence remains attributable to its original setup and the new setup is not automatically labelled verified.

#### Scenario: Loading adjustments keep weight and projector proof

- **WHEN** context, cache precision, cache location, GPU layers, flash attention or MTP change on the same weights and projector
- **THEN** existing proof for those weights remains applicable.

#### Scenario: Reload reuses evidence
- **WHEN** a saved setup loads again after restart with unchanged behavioral inputs
- **THEN** its persisted pass, fail or inconclusive results are reused without running those checks again.

#### Scenario: Selected response recipe and manual retest
- **WHEN** two response recipes share one native child and a person retests one check for the selected saved setup
- **THEN** the saved setup identity/revision resolves its actual response values server-side and only that clicked check is updated
- **AND** the retest does not launch the other checks.

#### Scenario: Named checks on the header
- **WHEN** the model header shows capability checks
- **THEN** it shows Text streaming, Tool round trip, Native structured output, Structured output via a tool, Native JSON after a tool, Formatter after a task tool, Thinking, Thinking history, Image input, and Image returned by a tool, in that order, each with status, plus Run all
- **AND** names appear on hover, sound and video stay off this row, and a click updates only the clicked check.

#### Scenario: Saved Thinking change
- **WHEN** Thinking changes on the saved setup and that setup next reaches a healthy load
- **THEN** only the Thinking and Thinking history results no longer apply, and the other eight checks remain
- **AND** those missing checks run on their own and do not block ordinary chat.

#### Scenario: Chat Thinking or sampling does not probe
- **WHEN** a person changes Thinking in the chat menu, or changes temperature, top-k, top-p, min-p, repeat penalty, presence penalty, frequency penalty, or the maximum answer length
- **THEN** that change MUST NOT launch probes by itself
- **AND** a chat-menu Thinking change applies to the next message, does not change the saved setup, and does not run a check, while a sampling or answer-length change leaves all ten results in place.

### Requirement: MOD-026 - Compare complete primary GGUF variants

Repository inspection SHALL present complete primary variants with exact file membership, known disk size, file count and a clearly identified filename-derived quantization and nominal bit-family hint. A known quantization token SHALL show even when it is separated from the rest of the filename by a dot, as in `Qwen3.5-0.8B.Q4_K_M.gguf`. The quantization label SHALL be unknown only when no known token is present. The existing known-token set SHALL remain unchanged. The application MUST NOT invent a new quant type. This identification SHALL be display only, and the application MUST NOT requantize. Unknown labels or sizes SHALL remain unknown; the bit family and disk size MUST NOT be represented as verified effective precision or memory fit. Incomplete selections SHALL explain why they cannot be downloaded. Obvious auxiliary MTP and imatrix GGUF files SHALL be reported separately and MUST NOT be accepted as the primary model selection. Projector or text-only choice and immutable revision SHALL remain explicit before transfer.

#### Scenario: Mixed repository contents
- **WHEN** a repository lists Q4 and BF16 primary weights, split shards and an `MTP/mtp-*` file
- **THEN** primary rows show the respective nominal families, exact quantization hints, aggregate disk sizes and shard completeness
- **AND** the MTP file appears as auxiliary rather than a selectable primary weight.

#### Scenario: Quantization token after a dot
- **WHEN** a primary filename is `Qwen3.5-0.8B.Q4_K_M.gguf` or otherwise contains a known quantization token separated by a dot
- **THEN** the display shows that known token
- **AND** the app does not invent a new quant type or requantize the file.

#### Scenario: Unrecognized or incomplete variant
- **WHEN** a filename does not declare a recognized quantization or a shard is missing
- **THEN** the label remains unknown or the selection remains unavailable with a reason
- **AND** the app does not invent a quality, compatibility or memory-fitting claim.

### Requirement: MOD-037 - Preview the selected model candidate faithfully

Models readouts SHALL resolve the selected model, configuration and unsaved draft through the existing model-capable resolver boundary. Application-default editing SHALL remain access-only. Chat and the one-task page SHALL use one menu for model, quantization, saved setups, the loaded model's own Thinking levels, and a context slider. That menu's preview SHALL use the same candidate, including removed overrides, and default labels SHALL use the correct parent/model value and source. The menu SHALL NOT include Apply this chat's settings, a Stage button, or a separate tuning icon. The menu SHALL let the person choose a saved setup. Sampling, GPU, and editing the saved setup SHALL stay on Models. Editing SHALL remain available during validation. No validation result SHALL enable Apply this chat's settings, because that control SHALL NOT exist. Readiness SHALL use the resolver's exact selected live configuration identity and distinguish quantization/configuration labels.

#### Scenario: Preview advanced startup edits
- **WHEN** the selected configuration requests All GPU layers, memory fitting Off and q4_0 key precision, then edits and resets them
- **THEN** requested and effective readouts agree with the real resolver for that candidate and the reset target value is correct.

#### Scenario: Preview completes out of order
- **WHEN** typing changes the candidate while an earlier check completes
- **THEN** editing stays uninterrupted and that earlier result cannot apply chat settings or enable Apply this chat's settings for the newer candidate
- **AND** Chat and the one-task page do not show that button.

#### Scenario: One menu without Apply
- **WHEN** a person opens model controls in Chat or on the one-task page
- **THEN** both use one menu and neither offers Apply this chat's settings, Stage, or a separate tuning icon
- **AND** sampling, GPU, and the saved setup remain on Models.

#### Scenario: Saved setup changes while Chat stays mounted
- **WHEN** a selected saved configuration gains a new revision while Chat remains mounted
- **THEN** its readiness, Thinking and context preview SHALL be reverified for that revision without passively loading a model
- **AND** explicitly selecting the changed saved startup SHALL apply that exact selection rather than treat an older running configuration as current.

#### Scenario: Model and agent preparation share setup ownership
- **WHEN** an explicit model or main-agent choice is still preparing its resolved setup
- **THEN** shared setup controls SHALL remain visibly busy until that owned action settles, so a competing choice cannot be silently discarded by its later callback
- **AND** disposal or replacement of the selection owner SHALL release its UI gate without allowing obsolete completion to overwrite the replacement.

### Requirement: MOD-039 - Share validated model controls and effective Thinking

Model import, save, preview and execution SHALL use one definition of supported control domains, units, dependencies, named defaults, provenance and apply timing. Numeric inputs SHALL reject nonfinite values and enforce whole counts where required. Slider spans SHALL remain distinguishable from actual supported bounds. Normal controls SHALL show actual resolved values and named native Auto/Off/Unlimited states, not raw sentinel numbers or redundant Default positions. Each help disclosure SHALL expose its actual native flag or request path, source and apply timing. Thinking SHALL offer only template-effective modes/levels and deduplicate aliases; unknown models SHALL remain usable with truthful unknown/default support. Chat Thinking SHALL offer only the loaded model's own levels. It SHALL apply to the next message, SHALL NOT reload the model, and SHALL NOT change the saved setup. The selected level SHALL be sent to the existing local model server on that next message. There SHALL be no separate Apply or Stage button. Sampling SHALL stay on the Models page. Invented generic Balanced/Deep response bundles SHALL be removed. Chat Thinking SHALL preserve explicit saved sampling choices; paired response recipes SHALL be deliberately selected in Models.

#### Scenario: Same choice across boundaries
- **WHEN** the same control is imported, saved, previewed and transmitted
- **THEN** its domain, source and effective setting agree and an invalid value fails before disruptive loading.

#### Scenario: Effective template levels
- **WHEN** a template supports binary Thinking or aliases High to Extra high
- **THEN** the normal control offers only effective distinct positions and no generic unsupported level.

#### Scenario: Chat Thinking applies to the next message
- **WHEN** a person changes Thinking in the chat menu
- **THEN** that level applies to the next message, the model does not reload, and the saved setup is unchanged
- **AND** there is no separate Apply or Stage button, sampling stays on the Models page, and explicit saved sampling choices remain.

### Requirement: MOD-040 - Reuse native instances independently from response choices

Native residency SHALL identify the exact runtime, weights, selected template/projector and normalized loading settings. Equivalent saved setups and response recipes SHALL reuse a compatible healthy instance; response defaults or setup ID SHALL NOT force another native child. Two setups that share a load and differ in Thinking SHALL share the loaded model. A saved Thinking change SHALL invalidate only Thinking and Thinking history proof, not the other eight checks. Sampling and answer-length differences SHALL NOT invalidate the ten checks. Context and GPU differences SHALL NOT invalidate them. Each accepted run SHALL resolve its own response values and SHALL NOT inherit another setup's response snapshot from that child. Those settings SHALL be sent to the existing local model server. Save and record preparation SHALL remain possible while active work exists and SHALL NOT start or modify resident processes. Loading/replacement SHALL retain existing admission and ownership protections.

#### Scenario: Same loading plan and different response recipes
- **WHEN** two saved setups share one loading plan and differ in Thinking, sampling or output allowance
- **THEN** they share the loaded model while each request transmits its own frozen settings
- **AND** a saved Thinking difference invalidates only Thinking and Thinking history proof, while sampling and answer-length differences leave all ten results in place.

#### Scenario: Context or GPU does not drop proof
- **WHEN** context or GPU layers differ between setups or from a previously tested load
- **THEN** the ten capability results remain applicable
- **AND** those differences do not invalidate proof.

#### Scenario: Prepare during generation
- **WHEN** a future setup is saved/prepared during active generation
- **THEN** preparation succeeds without replacing the active child's settings or process.
