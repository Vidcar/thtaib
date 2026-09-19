# Models and inference

[Specification index](../README.md) · [Status and evidence](../catalog.json)

## Ownership, scope and source

The application model manager owns bundles, managed downloads, installation records, compatibility profiles, run profiles and deployment lifecycle. huggingface_hub fetches selected files; gguf-py inspects GGUF data; llama.cpp performs inference. Source: [revision 0.5, page 4](../sources/README.md#models-and-inference).

## Public contracts and collaboration

The semantic contract families are **Model bundle**, **Run profile**, **Running deployment**, **Compatibility profile** and the model-related portion of **Run record**. These names are not promises of implemented classes. Locate future canonical code through [the repository map](../repository-map.json), following [contracts](../contracts.md).

The manager supplies a deployment endpoint and resolved settings to the LangChain model adapter. It does not execute agent tools or own agent context. The backend coordinates shared resources and presents health/events; persistent records link to files rather than place weights in application tables.

## Lifecycle and failure

Cover download, import/reuse, compatibility assessment, load, health reporting, switching and unload. A connected endpoint and a managed process have different ownership; the source does not define the full external-service control policy. Resolve that policy before implementing destructive external lifecycle actions. Interrupted downloads, failed startup, settings mismatches and unavailable endpoints need explicit outcomes, not a successful deployment record.

<a id="locked-milestone-defaults-issue-21-partial-oq-007"></a>
## Locked milestone defaults (Issue #21; partial OQ-007)

These defaults are authorised by [Issue #21](https://github.com/Vidcar/thtaib/issues/21). They do not close [OQ-007](../open-questions.md#oq-007) or [OQ-013](../open-questions.md#oq-013). They do not add a second inference engine.

- **Pin revision:** llama.cpp **b11045**.
- **Windows NVIDIA assets:** `llama-b11045-bin-win-cuda-13.4-x64.zip` and `cudart-llama-bin-win-cuda-13.4-x64.zip` extracted into managed `runtimes\`. This is the supported GPU path. Prefer the CUDA flavor when NVIDIA is present.
- **NVIDIA absent:** clear error. Do not install CPU-only as a silent GPU path. PATH llama-server remains unsupported.
- **Default GPU profile:** `ctx_size` ≥ 65536 (65536 for 3090/24GB), `n_gpu_layers: -1`, `flash_attn` as a valued enum (`on` / `off` / `auto`). Desktop Start managed binds this profile; it must not send empty `startup: {}` as the product default.
- **Valued startup enums:** `flash_attn` serializes as `--flash-attn on|off|auto` only. Never emit a bare `--flash-attn`. Other current STARTUP_KEYS stay flags (`mlock`, `no_mmap`) or valued scalars.
- **Local pin:** `local_executable` copies the full runtime directory (executable plus CUDA DLLs), not the exe alone.
- **Pin while running:** reject, or stop managed servers first. A half-finished pin is not success.
- **Non-Windows CUDA** is not a day-one supported path.

## Requirements and acceptance checks

<a id="mod-001"></a>
### MOD-001: Record complete bundles

Record quantisation, shards and companion files, repository revisions, hashes and local locations. Use huggingface_hub for managed revision-pinned downloads and pass resolved local files to llama.cpp. Reused files enter the same canonical records.

**Acceptance:** Import a model with companion files and verify the recorded manifest against the resolved files. Repeat using existing local files without creating a parallel record format.

<a id="mod-002"></a>
### MOD-002: Inspect, do not edit GGUF metadata

Use llama.cpp's gguf-py for metadata and tensor inspection feeding compatibility assessment. Metadata editing is outside the initial scope.

**Acceptance:** Inspect representative metadata and retain its provenance. No normal import or compatibility path modifies the original model metadata.

<a id="mod-003"></a>
### MOD-003: Preserve profile fidelity

Separate server-startup, per-request inference and agent settings. Preserve explicit overrides and supported runtime-specific controls. Record actual applied configuration and expose unsupported, overridden or unverified values in Lab, Chat and Builder.

**Acceptance:** Exercise a startup setting, request setting and agent setting; compare requested and applied values across surfaces, including a deliberately unsupported value.

<a id="mod-004"></a>
### MOD-004: Track real deployments

A running deployment identifies the live process or connected service, endpoint, applied startup configuration, health and resource usage. The model manager owns managed runtime versions and loading/unloading; a saved profile alone is not a running deployment.

**Acceptance:** Start a managed deployment, observe health and applied configuration, then stop it. Separately connect to an existing endpoint and demonstrate that its management scope is accurately reported.

<a id="mod-005"></a>
### MOD-005: Keep the model adapter narrow and faithful

Supply Deep Agents with a LangChain model adapter for the deployment's OpenAI-compatible chat endpoint. Preserve supported tool calls, multimodal input and runtime-specific parameters. The adapter neither loads weights nor starts another inference engine. llama.cpp owns tokenisation, template rendering and actual context capacity. Compatibility profiles configure supported reasoning controls and actual context limits; context compaction must not silently change the user's chosen generation settings.

**Acceptance:** Trace a supported tool call and multimodal request through the adapter. Verify that unsupported features are surfaced, that the adapter launches no inference process, and that compaction preserves the chosen generation settings.

<a id="mod-006"></a>
### MOD-006: Separate evidence from recommendations

Compatibility profiles are versioned and include requirements, supported capabilities/controls, recommendations, sources and validation evidence. Keep publisher guidance, tested adjustments and user overrides separate; do not exclude unfamiliar models merely because they are unverified.

**Acceptance:** Inspect a compatibility record with all three provenance categories and an unfamiliar model. Show the distinction between unverified support and a known incompatibility.

<a id="locked-milestone-defaults-issue-31-partial-oq-007"></a>
## Locked milestone defaults (Issue #31; partial OQ-007)

These defaults are authorised by [Issue #31](https://github.com/Vidcar/thtaib/issues/31). They satisfy the [MOD-006](#mod-006) provenance-separation and unverified≠incompatible checks. They do **not** close [OQ-007](../open-questions.md#oq-007): full compatibility evidence, capability claims and complete setting-mapping verification stay open. They are not a catalogue `verified` claim.

- **Records:** versioned `compatibility-record` documents under the bound `compatibility-records` directory. Each record carries requirements, supported capabilities/controls, recommendations, sources and validation evidence.
- **Provenance categories:** `publisher_guidance`, `tested_adjustments` and `user_overrides` are separate inspectable lists. An item cannot sit in the wrong list. User overrides written at runtime are stored under LocalAppData `state\compatibility\` and merged only into `user_overrides`.
- **Support status:** `unverified` | `known_incompatible` | `tested`. `tested` is a record status, not catalogue `verified`.
- **Unverified ≠ incompatible:** an unfamiliar model without a matching record is assessed `unverified`, `usable=true`, `incompatible=false`, `excluded=false`. Unverified is never treated as known incompatible and is not a reason to refuse managed-deployment create.
- **Surfaces:** `GET /v1/compatibility/records`, `POST /v1/compatibility/assess`, `GET /v1/bundles/{id}/compatibility`. No Builder canvas.
- **Not claimed:** David-PC capability UAT, complete setting-mapping verification, or that a `tested` fixture is a supported-capability product claim.

## Unresolved details

[OQ-001](../open-questions.md#oq-001) covers pinned dependencies and code locations; [OQ-007](../open-questions.md#oq-007) covers remaining compatibility evidence, startup/request settings and external lifecycle control. Issue #31 lands provenance-capable records and the unverified≠incompatible distinction without closing that question. [OQ-013](../open-questions.md#oq-013) covers multi-model routing and hybrid local/remote deployments; the model manager owns them and no second inference engine is implied. Do not invent universal runtime flags or model capability guarantees while these are unresolved. Requirement wording for MOD-001…004 is unchanged; Issue #3 implements the manager and Issue #21 lands the Windows CUDA pin and default GPU profile without claiming `verified` or closing OQ-007.
