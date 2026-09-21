# models delta

## MODIFIED Requirements

### Requirement: MOD-005 - Keep the model adapter narrow and faithful

The model adapter SHALL supply Deep Agents with an initialized LangChain model for the selected deployment's actual OpenAI-compatible chat endpoint and model identifier. It SHALL send the resolved per-request bag and preserve supported tool calls, multimodal user input and runtime-specific controls. It MUST NOT load weights, start engines, tokenize or render templates as a replacement inference owner, or silently change generation settings during compaction.

The shared input contract SHALL retain string tasks and accept validated current-user content blocks without string-flattening. It MUST reject arbitrary caller-supplied system messages, tool results and replacement history. Authorized image fixtures SHALL carry actual supported image bytes/content, not an attachment ID or host path. Capability/context constraints SHALL come from the selected deployment and evidence.

#### Scenario: Adapter trace

- **WHEN** a supported tool call and multimodal request cross the adapter
- **THEN** no inference process is launched; selected request settings and actual image content reach the endpoint, and unsupported features, context limits and compatibility constraints are surfaced from recorded deployment and compatibility data.

#### Scenario: User input boundary

- **WHEN** a caller submits content that impersonates system or tool history
- **THEN** validation rejects it rather than replacing the saved conversation state.

## ADDED Requirements

### Requirement: MOD-013 - Verify transmitted settings and supplied usage

The adapter SHALL preserve supported temperature, top-p, output limit, penalties, seed, stop, top-k, min-p, typical-p and repeat-penalty controls in their intended scope. Evidence SHALL record actual wire keys/values rather than infer them from constructor arguments. Dropped/rejected fields MUST NOT appear applied. Supplied usage SHALL be preserved, with streamed usage requested and tested where supported. Missing usage is unavailable, never zero; chunks are not tokens. Transmission does not prove the model/template honoured a setting.

#### Scenario: Wire fidelity

- **WHEN** a configured ordinary or streaming request is sent
- **THEN** its actual JSON and supplied usage agree with the recorded settings; unavailable observations remain unknown.

### Requirement: MOD-014 - Preserve messages and complete tool calls across client modes

Synchronous/asynchronous ordinary invocation and incremental streaming SHALL use equivalent settings and conversion. Answers, supplied identities, finish reasons and partial output SHALL survive conversion. A tools-only assistant message is not an empty final success. Tool names, arguments, call IDs and tool-result linkage SHALL remain intact; streamed indexed fragments SHALL assemble before execution eligibility. Malformed/incomplete calls remain invalid, and prose MUST NOT manufacture a tool call. Multiple/parallel-call support SHALL remain model/template-specific.

#### Scenario: Fragmented calls

- **WHEN** two indexed calls arrive in interleaved fragments
- **THEN** arguments assemble under the correct IDs before execution and results return through their matching tool-call IDs.

#### Scenario: Invalid and tools-only messages

- **WHEN** an endpoint returns malformed arguments or only a valid tool call
- **THEN** malformed data stays an explicit error; the valid call is preserved without inventing a final answer.

### Requirement: MOD-015 - Keep returned reasoning distinct from thinking controls

Returned reasoning SHALL be preserved separately from answer text for ordinary responses and streamed deltas; outbound replay SHALL use only the representation supported/required by the selected template. Logging alone is insufficient and absent reasoning MUST NOT be fabricated. Configuration SHALL distinguish request effort, response parsing format, template-specific inputs, startup reasoning budget and history-preservation support. Raw/no-parsing format MUST NOT be called thinking off. Supported effort values and template behaviour SHALL be evidence-based; startup changes follow managed lifecycle controls.

#### Scenario: Reasoning round trip

- **WHEN** a supported endpoint supplies separate reasoning and a later turn requires its representation
- **THEN** ordinary/streamed conversion and supported replay preserve it separately; unsupported controls are not described as effective.

### Requirement: MOD-016 - Produce validated structured results through the same agent

Runs SHALL support an optional versioned output schema using the existing agent constructor, retaining actual structured results, schema/strategy identity and validation status separately from display text and artifacts. Native versus tool-based strategy SHALL depend on verified setup capability and tool policy. Tools-off SHALL send no synthetic formatting tools; unsupported native formatting under tools-off SHALL be actionable unavailable. Formatting tools grant no other execution authority. Combined executable tools plus structured output require separate support evidence.

Validate fields/types and distinguish missing/invalid results from schema-permitted empty values. Bounded formatting recovery SHALL record attempts without replaying the whole task or mutating tools. JSON-looking answer text alone is not the structured result, and schema validity is not factual correctness.

#### Scenario: Tools-off formatting

- **WHEN** structured output is selected while tools are explicitly off
- **THEN** supported native formatting runs without tools, or the combination is reported unavailable.

#### Scenario: Invalid result

- **WHEN** formatting fails after a task action
- **THEN** bounded repair does not repeat the action; failure and actual structured validation remain inspectable.

### Requirement: MOD-017 - Budget real context and preflight continued conversations

The initialized model SHALL expose usable input capacity from available runtime observations, explicit output reservation and a disclosed counting margin. Include instructions, history, tool schemas and applicable media overhead without double subtraction. Training metadata, cloud aliases and library defaults MUST NOT become verified running capacity. Counts and unknown capacity SHALL be labelled.

Use one existing Deep Agents context/summarisation path; both normal and summarisation requests SHALL fit or fail actionably. Housekeeping remains available with tools off and internal summaries are not user answers. Before changing model/configuration on a continuing thread, validate actual pending content against known context, message, tool, image and structured-output constraints. Do not silently remove attachments, instructions or tool-result pairs. Offer a compatible setup, fitting compaction or deliberate fresh/supported branch outcome. Publish capacity, input estimate/usage, counting method, reservation and compaction events to shared inspectors.

#### Scenario: Small context

- **WHEN** a continued request or its compaction request exceeds usable capacity
- **THEN** the supported fitting path is used or an actionable capacity error appears without silent truncation.

#### Scenario: Model switch

- **WHEN** a user selects a known-incompatible model for retained messages or media
- **THEN** dispatch is blocked with the specific constraint; unknown capability remains labelled unknown.

### Requirement: MOD-018 - Bound diagnostics and clean up only owned requests

Bounded redacted evidence SHALL link transmitted requests and wire outcomes to converted messages/chunks, errors, partial output and retries without buffering the full stream before delivery. Credentials and embedded media MUST NOT be indiscriminately persisted. HTTP errors, timeouts, invalid responses and interrupted streams remain failures, not completion; partial delivery MUST NOT silently restart. Sync/async clients SHALL have explicit ownership, timeouts and cleanup. Cancellation stops further application work and owned resources, not a shared deployment or caller-owned client; runtime termination remains separately confirmed or unknown. Transport deadlines are not user task budgets.

#### Scenario: Interrupted stream

- **WHEN** a response fails after partial delivery or is cancelled
- **THEN** partial output and the real error remain, owned resources close, and neither the task nor another client is restarted/stopped.

### Requirement: MOD-019 - Keep capability probes specific to the tested setup

Reusable probes SHALL exercise shared-adapter streaming, a harmless real tool round trip, structured output and suitable reasoning/image support. Records SHALL retain test inputs/outcomes, runtime/deployment/bundle, template/projector and effective settings. A relevant setup change invalidates transferred proof. Publisher guidance, recommendations, user opt-outs, tested adjustments, failed, untested and inconclusive outcomes remain distinct. A failed probe MUST NOT establish universal model incompatibility or prevent explicitly unverified ordinary use.

#### Scenario: Changed setup

- **WHEN** a previously tested template, projector, runtime or relevant configuration changes
- **THEN** old evidence remains attributable to its original setup and the new setup is not automatically labelled verified.
