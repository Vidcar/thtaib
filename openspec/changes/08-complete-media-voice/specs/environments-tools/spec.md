# environments-tools delta

## MODIFIED Requirements

### Requirement: ENV-004 - Reuse the creative job adapter

One shared ComfyUI adapter SHALL submit jobs, track real progress, retrieve verified artifacts and serve agent tools, children and LangGraph nodes. The product MUST NOT implement separate job-control paths for the same creative capability. Use versioned API-format generation templates with explicit parameter-to-node/input mappings and expected final output-node contracts. A visual layout is not an executable API prompt; ComfyUI owns its internal graph, not thtaib sampler nodes. Deliver one working image-generation template; extra templates require validated dependencies/output contracts.

Before submission, inspect required server node classes/inputs and model selections where discoverable; validate mappings and freeze known template/integration/dependency revisions. Preserve server validation errors and supplied licence/model-card information without assuming distribution rights. Do not automatically install custom nodes/setup code or change endpoint model paths. A local path does not establish remote file access.

All invocation paths SHALL share selected configuration, current policy, cancellation and typed result/artifact contracts, awaiting actual results. An explicitly asynchronous handle API needs a wait/result operation; a bare job ID cannot satisfy an image/audio output port. Root/node/iteration/attempt identities remain distinct from ComfyUI internal nodes.

#### Scenario: Creative job from two entry points

- **WHEN** the same generation is invoked by an agent tool and a Workflow node
- **THEN** both await the shared adapter with matching policy, job ownership, progress, cancellation and verified artifact references.

#### Scenario: Template dependency missing

- **WHEN** a template names an unavailable node/model or invalid mapped input
- **THEN** submission fails actionably without installing code, guessing paths or pretending the template is ready.

## ADDED Requirements

### Requirement: ENV-014 - Connect external media engines without owning their files

The product SHALL support documented manual setup of user-provided compatible ComfyUI, transcription and speech-generation endpoints. Connections SHALL retain integration type, endpoint, configuration revision, credential reference, observed capability/server information and known model/template/voice selections. Freeze selected supported settings in jobs; unavailable identity/capability observations stay unknown. Use shared add/edit/test/disconnect and credential lifecycle.

Endpoints own diffusion/voice files and dependencies. Connecting MUST NOT install packages, copy/manage endpoint weights, alter model paths, replace runtimes or imply process ownership. A compatible configured endpoint is sufficient without thtaib inventory import. Managed GGUF ownership remains unchanged; diffusion/speech settings do not pass through GGUF readers or llama-server serializers.

#### Scenario: Connect media endpoint

- **WHEN** a compatible external engine is added and tested
- **THEN** its supported settings and observed identity are recorded without importing its weights or acquiring process-management rights.

#### Scenario: Unknown engine identity

- **WHEN** an endpoint does not report a model/version detail
- **THEN** the job records it as unknown instead of inventing a matching managed-GGUF identity.

### Requirement: ENV-015 - Validate and transmit real media with retained lineage

Shared picker/drag-and-drop intake SHALL support valid image/audio and attachment-only turns, checking actual bytes/decoder support against disclosed size/dimension/duration limits. Staged inputs remain distinct from verified retained assets; model-supplied paths/URLs grant no file/network access. Extend existing artifact identities with established dimensions/duration/original-derived lineage, not a separate gallery store.

Image understanding SHALL send authorised actual supported image content blocks through the shared harness/adapter with appropriate compatibility/context preflight. Attachment IDs, Windows paths and preview URLs do not replace image content; do not enable broad server filesystem access to avoid transmitting validated bytes. A text-only model may generate images through an authorised tool without being labelled able to see them. Return generated images as model-visible content only through a verified compatible route, otherwise return accurate tool metadata/artifact references. Shared media context accounting applies; compaction may remove active media without deleting retained originals or promising permanent visual memory.

Originals, derivatives, composer links and temporary previews follow shared ownership/access/dependency/manual-backup rules. Keep verified bytes, avoid unnecessary repeated embedding in checkpoints/events/diagnostics and distinguish unlink, original deletion and derivative deletion. Local deletion is not erasure of historical embedded state, remote uploads or older backups. Reuse rechecks access and never moves a session to another area.

#### Scenario: Image request

- **WHEN** a retained image is submitted to a suitable selected model
- **THEN** actual validated image content reaches the adapter rather than a local path or preview URL.

#### Scenario: Text-only generator

- **WHEN** a text-only model invokes image generation
- **THEN** it receives honest artifact/result data without fabricated visual analysis.

#### Scenario: Media lifecycle

- **WHEN** a composer attachment is removed or a derivative is deleted
- **THEN** the action follows explicit ownership/reference semantics and does not falsely promise remote or backup erasure.

### Requirement: ENV-016 - Correlate media jobs and verify whole-job outputs

The adapter SHALL persist media submission intent before dispatch, linking root/tool/node invocation, connection/template revision and pending external operation; then record acknowledgement and engine prompt/job identity. Establish supported event subscription/correlation and retain validation failures. Client-generated IDs are not idempotency guarantees without a verified server contract. Queue acceptance, execution and output retrieval remain distinct; an ID is not completion.

Interpret verified ComfyUI events for the intended prompt: start, cached execution, current-node progress/output, whole-job success/error/interruption and binary previews. Node output/preview is not whole-job success or a final artifact; node progress and queue position are not measured total-job percentages.

After actual completion, resolve expected final output nodes through supported history/results, retrieve bytes and validate them into shared retained artifacts. A filename/success response/preview does not prove image content. Distinguish execution success from partial/failed retrieval and preserve recoverable output access.

#### Scenario: Preview before completion

- **WHEN** a node emits UI output or a binary preview while the graph is still executing
- **THEN** progress remains associated with that node/prompt and no verified final artifact or whole-job success is claimed.

#### Scenario: Partial output retrieval

- **WHEN** the engine succeeds but one expected output cannot be downloaded or decoded
- **THEN** execution and retrieval outcomes remain distinct, retaining verified outputs and an actionable recovery path.

### Requirement: ENV-017 - Reconcile existing media jobs and cancel only with authority

After stream disconnect, restart or resume, query the same recorded job through supported queue/history/result interfaces and recover outputs where possible. Absent history does not prove a dispatched job never ran; stream exhaustion cannot trigger resubmission. Preserve unresolved outcomes instead of automatic replay.

Cancellation SHALL use capabilities verified on the configured endpoint, reconciling targeted cancellation/no-op responses and queue-removal-versus-start races. Acknowledgement or client disconnect does not prove stop. Global interrupt, queue clear, model unload or process kill MUST NOT be used to cancel one job on a shared server. Global action requires verified exclusive management, not a preliminary empty queue. Report safe cancellation as unavailable where the endpoint cannot provide it.

#### Scenario: Reconnect after dispatch

- **WHEN** the client disconnects after submission and later reconnects
- **THEN** it reconciles the original prompt identity and recovers outputs without duplicate generation.

#### Scenario: Shared-server cancellation

- **WHEN** one owned job is running beside possible unrelated clients
- **THEN** only verified safe targeted cancellation is offered; the product does not globally interrupt or unload the shared engine.

### Requirement: ENV-018 - Capture trusted microphone audio and prepare it correctly

Voice input SHALL provide explicit start/stop, recording indication, cancel and uploaded-audio alternative. Request/check audio permission only for the trusted intended application document/frame in supported packaged/development contexts, not unrelated origins or camera. Negotiate supported MIME recording format and retain renderer isolation. Stop/cancel/closing the capture surface SHALL release tracks, meters and processing resources.

After permission, expose microphone selection, live level and device/language controls. Report device changes, no input/mute and language limitations without silent substitution or invented confidence. Decode and, when required by the chosen endpoint, perform a verified owned conversion, retaining recording → normalised audio → transcript lineage. Renaming encoded bytes is not conversion; verify codec/converter availability rather than assume it comes with llama.cpp.

#### Scenario: Trusted capture lifecycle

- **WHEN** a user records from a selected microphone and closes or cancels capture
- **THEN** only intended audio permission is used, actual levels/errors are shown and tracks/processing are released.

#### Scenario: Endpoint requires conversion

- **WHEN** recorded bytes are in a different supported format from the transcription contract
- **THEN** an available verified converter produces actual valid audio with lineage, or the incompatibility is reported.

### Requirement: ENV-019 - Transcribe through one real endpoint into an editable draft

Integrate at least one concrete compatible user-configured speech-to-text endpoint with verified input/output, supported language/settings and available engine/model evidence. Send authorised validated audio and return its actual transcript/source artifact or real failure/no-speech outcome. Transcription and translation remain distinct. Dictation SHALL enter an editable draft before ordinary Chat send, never automatically submit a turn.

Native audio support in the conversational model is not required and no cloud recogniser may be substituted silently. Recording/upload/conversion/inference cancellation remain distinct, including explicit uncertainty about remote termination. A URL field without actual endpoint transcription does not satisfy delivery.

#### Scenario: Dictation result

- **WHEN** real microphone or uploaded audio is successfully transcribed
- **THEN** the returned transcript and source lineage appear in an editable unsent draft with actual language/settings evidence.

#### Scenario: No speech or failure

- **WHEN** the endpoint returns no speech or a conversion/inference error
- **THEN** the real outcome is shown without invented text, automatic send or silent recogniser substitution.

### Requirement: ENV-020 - Synthesize final answers through a separate real speech endpoint

Spoken replies SHALL use at least one concrete compatible user-configured text-to-speech endpoint, separate from transcription. Send final intended user-visible answer text and supported selected voice/language/settings; retain verified decodable audio with connection/voice/settings provenance. Selections must come from verified capability or supported explicit configuration, not unsupported generic controls. Endpoint-managed voice files need no thtaib inventory or owned synthesis worker; successful dictation alone does not satisfy TTS.

Spoken generation SHALL be opt-in and exclude reasoning streams, internal messages and raw tool arguments. Text generation, synthesis and playback have separate states. TTS failure must not erase a successful text answer; Stop playback is not confirmed synthesis cancellation. Audio remains savable/reusable with truthful navigation/restart state. Voice cloning and real-time duplex are not required.

#### Scenario: Opt-in spoken answer

- **WHEN** a final visible answer is synthesised with a supported selected voice
- **THEN** actual decoded audio and provenance are retained without sending private reasoning or requiring imported voice weights.

#### Scenario: Playback stop or synthesis failure

- **WHEN** playback is stopped or TTS fails after text completion
- **THEN** the text answer survives and playback/synthesis states do not misrepresent each other.

### Requirement: ENV-021 - Complete authorised two-sided same-run media handover

Media SHALL use shared permissions/admission/residency and Lab exclusivity. Outside Lab, coexistence requires actual resource/ownership checks; insufficient capacity yields visible waiting or authorised handover, not hidden model/device/settings substitution. During Lab, only batch-owned media executes. Releasing an inference permit is not unloading weights/cache.

For a suitable explicitly authorised local exclusive-residency setup, quiesce the managed Chat model at the saved safe boundary, unload it, execute actual authorised media, retain verified outputs, release necessary media residency with verified authority, restore Chat's exact frozen configuration and continue the same run/thread with that result. Never regenerate media or reconstruct context from displayed history. Label a deliberately enforced exclusive-residency test as such, not proof of a measured out-of-memory event.

Global media unload requires a supported verified management contract and exclusive authority, distinct from ownership of files or one job. A connection/empty queue cannot prevent another client submitting. Leave shared endpoints untouched when safe release is unavailable and expose blocked handover/manual action. Targeted cancellation is separate. GPU speech needs its own verified release contract when relevant; CPU execution or HTTP acknowledgement does not prove freed GPU memory.

Every phase SHALL reconcile cancellation/failure/restart/restore failure, preserve completed outputs and release safe owned reservations without evicting unrelated work. Restore retry uses the existing output, not a new generation. Unknown telemetry/external termination remains explicit; continuation does not promise retained KV/GPU cache.

#### Scenario: Real round trip

- **WHEN** an authorised setup requires Chat and media not to reside together
- **THEN** actual Chat unload, media generation/retrieval, verified necessary media release and exact Chat restore lead to the same continuation with retained outputs.

#### Scenario: Shared endpoint lacks release authority

- **WHEN** the connected engine cannot safely guarantee exclusive unloading
- **THEN** its models remain untouched and the handover reports the blocked dependency rather than claiming successful release.

#### Scenario: Restore failure after media success

- **WHEN** the original Chat setup cannot reload after successful generation
- **THEN** the verified output survives and recovery retries restoration without repeating media effects.

### Requirement: ENV-022 - Expose safe media controls and require real end-to-end evidence

Existing Chat, Models/runtime, progress and Workflow inspectors SHALL expose supported previews, endpoint/template/voice selections, effective settings, phases, errors and actual cancellation outcomes. Serve image/audio through authorised backend boundaries; never forward application trust tokens to external engines or place secrets in preview URLs. Generated HTML cannot execute as trusted UI. The shared output browser SHALL inspect/open/save elsewhere/reuse/delete with original-derived lineage and source run/engine/settings, using existing artifact storage. Text/document Chat/history remains usable with media disabled.

Required delivery SHALL include actual image understanding/generation, dictation, spoken replies, artifact lifecycle/reuse and managed two-sided handover, with real local/endpoint and Windows microphone/playback/desktop evidence. Missing required concrete engines or an authorised workable handover blocks the affected change 08 check, not earlier changes. Execute the saved Lab round-trip case and retain actual queue/unload/media/retrieval/restore timing and output. Optional image-to-image requires authorised retained input, validated mappings/dependencies and lineage; omission remains explicitly optional/not implemented, never a working placeholder.

#### Scenario: Authorised preview and reuse

- **WHEN** a generated image/audio output is inspected, saved elsewhere or reused
- **THEN** shared access and lineage are preserved, with no secret-bearing external preview URLs or trusted execution of generated HTML.

#### Scenario: Delivery evidence

- **WHEN** media completion is assessed without real endpoint, microphone or handover execution
- **THEN** the missing affected checks remain incomplete rather than being passed by mocks, previews or job IDs.
