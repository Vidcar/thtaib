# Models and inference

[Architecture](../architecture.md) · [Status and evidence](../catalog.json) · [Decisions](../decisions/changelog.md)

## Purpose

Import, describe, configure, start and observe local models so that every other surface uses the same bundle, profile and deployment records and can tell what settings were actually applied.

## Boundaries and ownership

The application model manager owns bundles, managed downloads and imports, compatibility records, run profiles and deployment lifecycle. `huggingface_hub` fetches revision-pinned files; `gguf-py` inspects GGUF metadata; llama.cpp (`llama-server`) performs inference and owns tokenisation, chat-template rendering and real context capacity. The manager supplies an endpoint and resolved settings to the LangChain model adapter; it never runs agent tools or holds agent context. Source: [Revision 0.5, page 4](../sources/README.md#models-and-inference).

## Interfaces and contracts

Record families: **Model bundle**, **Run profile**, **Running deployment**, **Compatibility record**, and the model-related part of a **Run record**. Routes under `/v1`: `bundles` (list, get, `inspect`, `compatibility`), `imports/huggingface`, `imports/local`, `imports/{job}`, `profiles` (CRUD), `settings/preview`, `runtime`, `runtime/pin`, `deployments` (`managed`, `connected`, `start`, `stop`, `detach`, `health`, `smoke`) and `compatibility` (`records`, `assess`, `records/{id}/overrides`). Module-local Pydantic models carry these shapes today; the semantics live in this specification, not in the models, and they are not yet on the shared-contract generation path ([contracts](../contracts.md)).

## Behaviour

- **Catalogue verification cost.** Routine bundle listings reuse an in-memory digest only while file identity, metadata and a lightweight content fingerprint match. Cache misses serialize hashing and changes during hashing retry or fail. Import, explicit inspection and model start retain full hashes. The bounded cache is an optimization, not durable verification evidence or a replacement for start-time integrity checks.
- **Model setup experience.** Models opens on the model library and active models. Imports and chat presets have separate views; engine installation, external connections, file paths, record identifiers and launch diagnostics remain available in disclosures. Main settings use labelled choices with keyboard-focusable help showing the corresponding llama.cpp flag. `GET /v1/bundles/{id}/configuration-options` uses architecture-specific GGUF metadata to offer context sizes (eight choices from 32k to 256k for a 256k model), transformer/output layer limits and an explicit CPU-thread recommendation from the host's physical core count. This metadata read uses existing catalogue verification caching; it does not repeat the explicit inspection's full file hash. Unknown model limits are reported as unknown. Existing explicit/custom values remain available. Automatic context fitting remains a choice, and requested launch settings are distinguished from observed server context and generation defaults. A deployment observation must belong to the selected bundle. Loading status is polled; an active managed model must be stopped before applying edited startup settings, and stopping does not erase those edits.
- **Record updates.** Inference JSON read/modify/write operations serialize within the single backend process and use unique temporary files for atomic replacement. Unchanged bundle checks do not rewrite the catalogue. This prevents concurrent request updates from losing records; it does not provide transactions across processes or across record families. The eventual SQLite migration remains [OQ-017](../open-questions.md#oq-017).

- **Runtime pin.** The supported managed runtime is llama.cpp **b11045**, Windows CUDA 13.4 assets extracted into `runtimes\`. NVIDIA absent is a clear error, not a silent CPU fallback. A `llama-server` on PATH is unsupported. Pin while running is refused or stops managed servers first. Non-Windows CUDA is not a supported path. `POST /v1/runtime/pin` does not re-download an archive that is already on disk and whose SHA-256 matches the expected digest (the official b11045 GitHub release-asset digest, or the last ready manifest for the same release and asset when that digest is absent). A matching ready install is left in place; a digest mismatch re-downloads that archive.
- **Settings bags.** Startup controls map through `inference/settings.py` to argument arrays for the pinned b11045 runtime: context/offload, CPU and batch threads, batching, flash attention, fit/load mode, KV-cache K/V, embeddings/pooling, templates/reasoning and speculative/draft controls. The desktop offers primary controls and an advanced object validated by the same backend preview. Invalid, retired or unknown requested startup controls fail managed creation/start before a process is spawned; preview and saved profiles retain unsupported/retired explanations. `mlock` / `no_mmap` migrate to `load_mode`. Existing valid explicit values are preserved. Per-request sampling stays in the request bag; agent configuration stays in the agent bag. Startup reasoning controls require a new managed deployment; they are runtime options, not proof that a model supports generic thinking levels. Flags and request fields remain unverified until runtime observations establish their effect. Additional controls must be added to this pin-aware mapping; there is no raw command-string escape hatch.
- **Default GPU profile.** New managed starts retain GPU offload and flash attention defaults but do not inject a fixed context size. Blank context lets b11045 derive capacity from the model and apply its fitting behavior; an explicit context or fit/offload choice remains explicit. Existing saved 65,536-context profiles and already running deployments are unchanged. This is upstream fitting, not a complete application RAM/VRAM recommendation engine; allocation can fail and must be reported without substituting a different setup. Dedicated OpenAI embeddings keep pooling limited to mean/cls/last; runtime token-embedding and reranking pooling modes need separate adapter support. The desktop does not invent a universal temperature: blank profile sampling uses runtime defaults, and an explicit temperature of zero is preserved.
- **Managed deployment lifecycle.** Start, stop, health and reconcile are serialised per deployment. Ownership is never inferred from HTTP health alone: a live record stores `process_identity` (`pid`, `create_time`, `executable`) and destructive stop verifies it first; a stale or reused PID is refused and the record cleared as unowned without killing the unmatched process. On backend restart, reconciliation re-adopts a still-matching process or clears ownership without terminating a mismatched PID; legacy PID-only records are unproven and never killed. A duplicate start of a verified-owned deployment returns the existing record. A process that exits while another process answers the endpoint is `failed`, not owned. A bundle whose companions include an `mmproj` GGUF starts with `--mmproj <path>` after `-m <primary>`; a recorded projector missing on disk is a `bundle_file_missing` failure, not a start. Currently importing the companion expresses vision intent; there is no profile opt-out yet. Persisted user opt-outs are required by the shared capability path and remain tracked in DEV-006. Create-with-`auto_start` waits up to about 30 seconds (`60 × 0.5 s`) for a warm load to become healthy and for the launched process to own the listen port; that is an honest budget for a page-cached start, not a cold 14 GB disk load. A still-loading server is returned as `unhealthy` with identity recorded, and the client must keep polling `GET /v1/deployments/{id}/health`. The start handler must not block for a multi-minute cold load. Managed `llama-server` stdout and stderr are written to `logs\llama-server-<deployment-id>.log` under the product data root (Windows: `%LOCALAPPDATA%\LocalAIWorkbench\logs\`); they are not discarded. Those files rotate at 8 MiB with three backups and the logs directory is capped at 256 MiB.
- **Server properties.** Once a managed or connected deployment reports healthy, `GET /props` is read and its build, alias, model path, slots, `n_ctx`, `modalities`, `chat_template` and `chat_template_caps` are recorded on the deployment as `server_props`. This is recorded data for compatibility work, not a compatibility record and not a capability claim; an endpoint without `/props` records nothing and stays healthy.
- **Connected endpoint.** Attaches an existing OpenAI-compatible server with `scope=connected`; health is probed; start, stop and kill are refused; detach only. Optional declared startup (`embedding`, `pooling`) is recorded without applying managed-process GPU or host/port defaults; declaration is not applied argv. Retrieval uses that declaration: a connected embedder must be recorded as `embedding: on` or the run fails closed (`embedding_not_configured`). A GGUF path under the product `models\` directory is not a connected or managed deployment.
- **Guided Hugging Face imports.** Models accepts a repository link or ID, reads metadata before any weights transfer, presents one GGUF variant with disk size and all its shards, and requires an explicit projector or text-only choice when projectors exist. An immutable commit is resolved internally and used for selected downloads. Bundle records preserve relative paths and hashes. Ambiguous weights/projectors and incomplete/mixed shards fail explicitly, including legacy ambiguous projector records at deployment start. Filename grouping only identifies candidates: projector compatibility and publisher guidance interpretation remain unverified. Non-GGUF architectures need separate runtime adapters. Cards and config files are reference data, never executed. Transfers use huggingface_hub resume metadata and stable revision/selection staging; repeated selected imports reuse the canonical bundle. The UI shows busy/completed/failed outcomes; byte progress and cancellation are not implemented. Full catalogue browsing, automatic compatibility-aware companion recommendations and hardware memory estimates remain follow-up work.
- **Compatibility records.** Current records keep `publisher_guidance`, `tested_adjustments` and `user_overrides` separate, with `unverified` | `known_incompatible` | `tested` record status (not catalogue verification). Unknown models remain usable. `/props` observations are recorded on deployments, but the automated probe pipeline and persisted feature opt-outs are not implemented. The intended shared evidence extension distinguishes publisher claims, inspected metadata, runtime/template/companion support, observed probes, and user choices. Cache probe evidence by bundle/file hashes, selected projector, template identity, runtime build, effective configuration/integration and probe version; invalidate only affected evidence. Outcomes are passed, failed, inconclusive, unavailable and untested. A tool probe requires a structured call and result round-trip; vision requires an actual image. Diagnose integration failures before blaming weights. Checks must offer progress/cancel/skip/rerun, remain bounded independently of agent budgets, and never block ordinary use or overwrite explicit feature opt-outs. Re-probes and profile changes must preserve user choices; capability enables no additional file, shell or service permission.
- **Failure.** Interrupted downloads, failed startup, settings mismatches and unavailable endpoints produce explicit outcomes, never a successful bundle or deployment record.

## Requirements

<a id="mod-001"></a>
### MOD-001: Record complete bundles

Record quantisation, shards and companion files, repository revisions, hashes, preserved relative paths and local locations. Use huggingface_hub for managed revision-pinned downloads and pass resolved local files to llama.cpp. Reused files enter the same canonical records. Never silently choose an ambiguous projector or flatten copied filenames in a way that loses identity.

**Acceptance:** Import a model with companion files and verify the recorded manifest against the resolved files, including revision, variant, shards, projector, relative paths and skipped alternatives. Repeat using existing local files without creating a parallel record format.

<a id="mod-002"></a>
### MOD-002: Inspect, do not edit GGUF metadata

Use llama.cpp's gguf-py for metadata and tensor inspection feeding compatibility assessment. Metadata editing is outside the initial scope.

**Acceptance:** Inspect representative metadata and retain its provenance. No normal import or compatibility path modifies the original model metadata.

<a id="mod-003"></a>
### MOD-003: Preserve profile fidelity

Separate server-startup, per-request inference and agent settings. Preserve explicit overrides and supported runtime-specific controls. Record actual applied configuration and expose unsupported, overridden or unverified values in Lab, Chat and Builder. Selecting a profile does not rewrite an already-loaded deployment's startup bag ([effective setup](../architecture.md#effective-setup)).

**Acceptance:** Exercise a startup setting, request setting and agent setting; compare requested and applied values across surfaces, including a deliberately unsupported value.

<a id="mod-004"></a>
### MOD-004: Track real deployments

A running deployment identifies the live process or connected service, endpoint, applied startup configuration, health and resource usage. The model manager owns managed runtime versions and loading/unloading; a saved profile alone is not a running deployment.

**Acceptance:** Start a managed deployment, observe health and applied configuration, then stop it. Separately connect to an existing endpoint and demonstrate that its management scope is accurately reported.

<a id="mod-005"></a>
### MOD-005: Keep the model adapter narrow and faithful

Supply Deep Agents with a LangChain model adapter for the deployment's OpenAI-compatible chat endpoint. Preserve supported tool calls, multimodal input and runtime-specific parameters. The adapter sends the applied per-request bag from the resolved setup; it neither loads weights nor starts another inference engine. llama.cpp owns tokenisation, template rendering and actual context capacity. Compatibility records configure supported reasoning controls and actual context limits. Context compaction must not silently change the user's chosen generation settings.

**Acceptance:** Trace a supported tool call and multimodal request through the adapter. Verify that unsupported features are surfaced, that the adapter launches no inference process, and that compaction preserves the chosen generation settings.

<a id="mod-006"></a>
### MOD-006: Separate evidence from recommendations

Compatibility records are versioned and include requirements, supported capabilities/controls, recommendations, sources and validation evidence. Keep publisher guidance, tested adjustments, probe outcomes, shared provenance keys and user opt-outs separate; do not exclude unfamiliar models merely because they are unverified.

**Acceptance:** Inspect a compatibility record with all provenance categories, one observed probe outcome, one user opt-out and an unfamiliar model. Show the distinction between unverified support and a known incompatibility.

## Status and evidence

Status is owned by rows MOD-001...006 in [the catalogue](../catalog.json).

## Open questions

[OQ-007](../open-questions.md#oq-007) compatibility evidence and setting-mapping verification; [OQ-013](../open-questions.md#oq-013) multi-model and hybrid routing; [OQ-017](../open-questions.md#oq-017) persistence of the JSON record stores.
