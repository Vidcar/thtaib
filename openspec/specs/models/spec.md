# Models

## Purpose

Specify how Local AI Workbench imports, describes, configures, starts, observes, and reports local and connected models so every surface can use the same bundle, profile, deployment, compatibility, and applied-setting records.

## Requirements

### Requirement: MOD-001 - Record complete bundles

Model bundle records SHALL preserve quantization, shards, companion files, immutable repository revisions, hashes, relative paths, and local locations. Managed downloads SHALL use `huggingface_hub` with revision-pinned selections, and the model manager SHALL pass resolved local files to llama.cpp. The product MUST NOT silently choose ambiguous projectors or flatten copied filenames so identity is lost.

#### Scenario: Import with companions

- WHEN a GGUF variant with shards and companion projector files is imported
- THEN the recorded manifest MUST include revision, selected variant, shards, projector choice, relative paths, hashes, and skipped alternatives
- AND repeated imports from existing files MUST reuse the canonical record format.

### Requirement: MOD-002 - Inspect, do not edit GGUF metadata

The model manager SHALL use llama.cpp `gguf-py` for metadata and tensor inspection feeding compatibility assessment. Normal import, inspection, and compatibility paths MUST NOT modify original model metadata.

#### Scenario: Metadata inspection

- WHEN representative GGUF metadata is inspected
- THEN provenance MUST be retained
- AND the source model file MUST remain unchanged.

### Requirement: MOD-003 - Preserve profile fidelity

Profiles SHALL separate server-startup, per-request inference, and agent settings. Explicit overrides and supported runtime-specific controls SHALL be preserved. Requested, selected, loaded, and applied values SHALL be recorded separately and exposed across Lab, Chat, and Workflows. Selecting a profile MUST NOT rewrite an already-loaded deployment's startup bag.

#### Scenario: Three settings bags

- WHEN a startup setting, request setting, and agent setting are exercised
- THEN each MUST reach its intended consumer only
- AND unsupported, overridden, or unverified values MUST remain visible rather than silently moved or discarded.

### Requirement: MOD-004 - Track real deployments

A running deployment SHALL identify the live managed process or connected endpoint, endpoint URL, applied startup configuration, health, server properties when available, and resource observations. The model manager SHALL own managed runtime start, stop, health, and reconcile. Saved profiles alone MUST NOT be treated as running deployments.

#### Scenario: Managed and connected deployment

- WHEN a managed deployment is started and stopped
- THEN process identity, health, applied startup settings, logs, and ownership MUST be recorded and verified before destructive stop
- AND a connected endpoint MUST be reported as connected scope with start, stop, and kill refused.

### Requirement: MOD-005 - Keep the model adapter narrow and faithful

The model adapter SHALL supply Deep Agents with a LangChain model adapter for the deployment's OpenAI-compatible endpoint. It SHALL send the applied per-request bag from the resolved setup and preserve supported tool calls, multimodal input, and runtime-specific parameters. The adapter MUST NOT load weights, start an inference engine, own tokenization, own template rendering, or silently change user generation settings during compaction.

#### Scenario: Adapter trace

- WHEN a supported tool call and multimodal request flow through the adapter
- THEN the adapter MUST launch no inference process
- AND unsupported features, context limits, and compatibility constraints MUST be surfaced from recorded deployment and compatibility data.

### Requirement: MOD-006 - Separate evidence from recommendations

Compatibility records SHALL be versioned and SHALL keep publisher guidance, inspected metadata, tested adjustments, observed probe outcomes, shared provenance keys, recommendations, and user opt-outs separate. Unfamiliar models MUST remain usable when unverified. Known incompatibility MUST be distinguishable from unknown or inconclusive support.

#### Scenario: Compatibility record categories

- WHEN a compatibility record includes publisher guidance, probe evidence, and a user opt-out
- THEN each category MUST remain distinct
- AND an unverified model MUST not be excluded merely because no probe has passed.

### Requirement: MOD-007 - Pin and observe managed runtime honestly

Managed runtime installation SHALL use the supported pinned llama.cpp runtime and verify matching archives before reuse. NVIDIA absence on the supported Windows CUDA path SHALL be a clear error, not a silent CPU fallback. Runtime flags SHALL be produced through pin-aware settings mapping; there MUST be no raw command-string escape hatch.

#### Scenario: Runtime pin and settings preview

- WHEN startup controls are previewed and a managed server is started
- THEN invalid, retired, or unknown controls MUST fail before spawn
- AND requested launch settings MUST remain distinguishable from observed server context and generation defaults.

### Requirement: MOD-008 - Import Hugging Face bundles by explicit selection

Guided Hugging Face imports SHALL read repository metadata before weight transfer, present GGUF variants with disk size and all shards, require explicit projector or text-only choice when projectors exist, resolve an immutable commit internally, and preserve relative paths and hashes. Ambiguous weights, ambiguous projectors, incomplete shards, and mixed shards MUST fail explicitly.

#### Scenario: Ambiguous projector

- WHEN a repository contains more than one plausible projector
- THEN import or deployment MUST require an explicit selection or text-only choice
- AND legacy ambiguous projector records MUST fail at deployment start rather than guessing.
