# Design

## Context

See proposal.md for motivation. Existing model/setup records, inference settings descriptors, lifecycle admission and durable accepted input snapshots remain the owners. The Windows runtime is llama.cpp b11045 / 2b1847030. Its bundled fit helper lacks projector, speculative and unified-pool support, while its native APIs can expose these allocations.

## Goals / Non-Goals

**Goals:** consistent controls and native load identity; one authoritative settings resolution; exact authored admission and once-bound runtime output allowance; complete native selected-component preview; usable Windows delivery.

**Non-Goals:** a second inference/agent/workflow runtime, allocation simulator, new settings store, or new LoRA/transcription/reranking/research integrations.

## Decisions

- Extend existing typed inference descriptors and validators rather than create a parallel registry. Domains, support, source, reset, dependency and timing facts are shared by preview, save and execution.
- Saved setup identity is separate from runtime/artifact/template/projector/normalized-startup residency identity. Response defaults never create another child or leak from its originating profile.
- Save/preparation records are revision protected but do not start or alter a resident process. Actual load/reload remains with existing admission and ownership checks. Chat Thinking applies locally; context changes are deliberate and busy edits stage a future input.
- Freeze authored setup, recipe/customizations and automatic-budget policy at acceptance. Bind each role atomically to one observed per-slot capacity and finite output allowance before its first model request; persist that binding in existing run/effective-setup records and retain it through retry/resume. This supports cold helpers without preloading every model together.
- Explicit response limits retain their value. Compatible pinned total-output caps win; otherwise Workbench Auto uses floor((capacity - floor(0.08 * capacity)) / 2) for Thinking On/unknown or /4 for Off. These are visible Workbench defaults, not measured model optima. The adapter, context guard and existing Deep Agents compaction consume that same allowance once.
- Fresh managed plans explicitly use parallel=4 and unified KV, Auto GPU plus fit On, omitted Auto context and Flash Attention Auto. Existing effective saved plans receive a narrow cutover retaining prior defaults; frozen history is never rewritten.
- Compile a thin bounded native subprocess against exact pinned DLL/header ABI. Mirror server preprocessing and native no-allocation contexts; measure projector, target and draft/MTP through native APIs. Count shared MTP weights once. Manifest records helper protocol/hash/runtime fingerprint. Unsupported/missing measurements remain partial and inference remains usable.
- Models keeps Save plus separate lifecycle actions; Chat exposes only saved selection, Thinking and context; Agents owns its settings; shared engine editors move to Settings. Reuse theme/control tokens and compact layouts, not a new application/prototype.
- Import jobs preserve initial startup/response and selected recipe intent across retries. Actual installed template validation precedes committing the initial configuration; setup failure keeps installed weights.

## Risks / Trade-offs

- Native ABI/private extension changes -> pin exact source/DLL identity, build gate, isolated process, explicit unsupported fallback.
- Auto preview differs from later available memory -> distinguish requested/evaluated/observed and retain native load authority.
- Dynamic driver/host caches are not static allocations -> list unknown/budgeted overhead and never promise a successful load.
- Shared pool is not per-slot reservation -> report maximum per chat and aggregate contention; native scheduling remains owner.
- Bound budget cannot fit after reload -> actionable recovery, never mutate frozen settings or silently clamp explicit limits.
- UI/preview races -> candidate identity and stale-result rejection, preserve per-model/chat drafts.

## Migration Plan

1. Prove native adapter build/parity before completing memory preview presentation.
2. Add shared types, validation, compatible residency reuse and narrow effective-default cutover.
3. Add automatic-budget binding and import draft fidelity; integrate the existing desktop surfaces.
4. Run isolated deterministic/integration and live Windows/model gates, synchronize/archive OpenSpec, merge and refresh local deployment. Preserve weights and unrelated active changes.
