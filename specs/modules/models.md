# Models and inference

[Specification index](../README.md) · [Status and evidence](../catalog.json)

## Ownership, scope and source

The application model manager owns bundles, managed downloads, installation records, compatibility profiles, run profiles and deployment lifecycle. huggingface_hub fetches selected files; gguf-py inspects GGUF data; llama.cpp performs inference. Source: [revision 0.5, page 4](../sources/README.md#models-and-inference).

## Public contracts and collaboration

The semantic contract families are **Model bundle**, **Run profile**, **Running deployment**, **Compatibility profile** and the model-related portion of **Run record**. These names are not promises of implemented classes. Locate future canonical code through [the repository map](../repository-map.json), following [contracts](../contracts.md).

The manager supplies a deployment endpoint and resolved settings to the LangChain model adapter. It does not execute agent tools or own agent context. The backend coordinates shared resources and presents health/events; persistent records link to files rather than place weights in application tables.

## Lifecycle and failure

Cover download, import/reuse, compatibility assessment, load, health reporting, switching and unload. A connected endpoint and a managed process have different ownership; the source does not define the full external-service control policy. Resolve that policy before implementing destructive external lifecycle actions. Interrupted downloads, failed startup, settings mismatches and unavailable endpoints need explicit outcomes, not a successful deployment record.

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

## Unresolved details

[OQ-001](../open-questions.md#oq-001) covers pinned dependencies and code locations; [OQ-007](../open-questions.md#oq-007) covers compatibility evidence, startup/request settings and external lifecycle control. [OQ-013](../open-questions.md#oq-013) covers multi-model routing and hybrid local/remote deployments; the model manager owns them and no second inference engine is implied. Do not invent universal runtime flags or model capability guarantees while these are unresolved. Requirement wording for MOD-001…004 is unchanged; Issue #3 implements the manager without claiming `verified` or closing OQ-007.
