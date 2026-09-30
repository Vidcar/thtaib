# Design

## Context

See proposal.md for the accepted scope. The editable mock under `.scratch/models-design-20260930/prototype/` is the usability reference; its sample jobs, machine capacities and rough allocation formulas are not runtime evidence. Models statically imports styles, so unscoped resets affect every page. Existing model configurations, imports and capability evidence already have backend owners.

## Goals / Non-Goals

**Goals:** Reuse the existing native manager, durable jobs, lifecycle protections, configuration resolver and application evidence store; reduce ordinary UI space and steps while keeping valid native behavior accessible.

**Non-Goals:** Audio/video probes, every llama.cpp CLI option, a second runtime or settings owner, byte-resumable downloads, model-weight changes, unrelated Workflows delivery.

## Decisions

1. Scope Models styles under `.models-surface`, including its overlays. Use existing appearance tokens and bounded internal scrolling. Shared controls receive opt-in compact presentation; retain all consumers' default behavior. Preserve the 54px rail and resource rings.
2. Common Generation/Loading rows stay mounted and compact; specialist groups collapse. Context has one mode/slider/exact owner; GPU layers has one Auto/All/CPU/Exact row with a reserved count slot; speculation has one `spec_type` owner. Optional flags remain absent until set; reset removes overrides. Short help states native mapping, source and apply timing. Typed startup fields replace raw JSON without adding an unrestricted command escape hatch.
3. Named configurations remain canonical backend records. Zero setups and a null preferred pointer are real states. Selected card recipes create records directly from the native/template baseline and recipe values. First manual save becomes preferred. Deletion retains active-use guards, clears a deleted preferred pointer and never silently substitutes saved references. No synthetic default is recreated during reads.
4. Bundle rename changes `display_name` only. Compatibility uses stable bundle/source/artifact facts; catalogue refresh updates current labels across consumers while historical snapshots remain historical.
5. Find → Choose owns exact quantization/shard/projector selection, selected card recipe IDs and Download/Add. Preview controls are advisory and never saved as startup overrides. Cancel confirms worker stop; Retry uses a linked immutable-selection job. Native local browse and copy/original ownership remain. Maintenance and detailed jobs stay in compact disclosures; storage destination/cleanup belongs to Settings.
6. Extend the shared estimate boundary with an explicit capacity basis and local source preview. Discovery subtracts visible GPU/RAM headroom from physical totals; Chat/admission/live rings retain available-memory semantics. Use bounded GGUF headers/tensor shapes; unknown allocation remains partial and cannot establish a green fit. Highest model-supported preview bounds/cache precision and verified MTP are advisory only.
7. Persist capability evidence in application.sqlite under normalized behavioral scope: artifacts, selected projector/template, runtime pin and effective response/Thinking/history. Exclude labels, revision-only changes, process/endpoint IDs and memory-only loading knobs. One backend coordinator schedules missing applicable checks sequentially after healthy saved-load readiness. Existing lazy image checks share deduplication/reservations. GET reads never infer or load. Selected setup identity/revision resolves response bags server-side. Manual icon retests force one check; failure/inconclusive remains normal evidence, with text use available.

## Risks / Trade-offs

- Shared CSS/control regressions → opt-in presentation, consumer checks and native cross-page geometry.
- Setup removal leaves references → actionable missing references and immutable historical snapshots, never silent remapping.
- Existing synthetic defaults cannot always be distinguished from authored work → versioned conservative migration removes only demonstrably untouched synthetic records and obsolete product fields; preserves meaningful native settings/instructions.
- Background probes race runs/deletion/shutdown → existing lifecycle reservations, per-scope deduplication and bounded cleanup; unrun checks remain retryable.
- Metadata prediction excludes native overhead/unsupported architectures → explicit partial/unknown results; native checks remain deliberate and non-disruptive.

## Migration Plan

Ship backend/public schemas, regenerated contracts and desktop together. Run a versioned idempotent metadata migration, preserve weights and protected chats, invalidate obsolete proof instead of adding a shim. Verify isolated records/native Windows first, then refresh the established local deployment. A rollback restores code and backed-up metadata; never rewrite weights or historical snapshots.
