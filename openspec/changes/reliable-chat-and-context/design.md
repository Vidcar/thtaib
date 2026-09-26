# Design

## Context

See proposal.md and the approved user plan. Installed Deep Agents 0.7.19 and llama.cpp b11045 already provide recovery, compaction, memory injection and per-request thinking limits. Real failures show application integration gaps, not a need for a replacement runtime.

## Goals / Non-Goals

Deliver reliable general assistance in the existing desktop/backend and preserve permission, persistence and model-weight guarantees. Do not introduce another model/tool loop, document store, repository index service, scheduler or compatibility layer for disposable development records. The unrelated Lab proposal remains separate.

## Decisions

- Keep native tools. Normalize resolved Windows representations at the backend containment seam while preserving original I/O paths and link escape checks. Expected validation/I/O errors become individual ToolMessages; application persistence and unknown effects remain distinct.
- Track structured per-call outcomes and durable parent failure/recovery data. Allow native terminal pair normalization before final protocol validation, never by replaying old effects. Inspect unknown file outcomes using recorded desired content and current bytes; unresolved effects require a user decision.
- Project-family admission uses persisted runs plus short admission reservations and the existing ApplicationStore Chat coordinator/queues. Canonical actual execution roots and overlaps are authoritative. Reserve before model load/snapshot, retain through interrupts/finalization, and reconcile on startup. Chat retains frozen input with durable FIFO order; direct Agent/Lab APIs reject a busy root before side effects. Lab capture shares the reservation. No new scheduler.
- One pure inference adapter projection supplies counting and actual transmission. Preserve reasoning according to capabilities; exclude duplicate native representations. Native compaction runs before the final guard and receives recognizable overflow errors. Separate work/summary usage and failure evidence.
- Add canonical per-request reasoning_budget_tokens. Balanced uses medium/2048/8192; Deep uses xhigh/8192/16384 for effort/thinking/total output. Preserve startup settings and keep product presets separate from publisher recipes. Unsupported thinking limits are explicit.
- Explicitly applying a separate response configuration with the identical frozen launch identity can reuse the existing healthy owned deployment without unloading. The existing reconfigure owner retains busy and revision guards, checks fresh health and process identity, and changes only configuration/response binding; different launch settings retain the established reload path. Automatic ports use the existing identity normalization. Local delivery preserves the publisher Thinking recipe and creates a separate normal Balanced configuration.
- Conversation.document_asset_ids persists document selection. Submissions freeze selections; new attachments join it, explicit removal affects future submissions. Inject a compact catalogue and reuse read_attachment/extracted sections. Local lexical search and optional lazy semantic search share source facts and no durable index. Keep memory/skills/protected instructions out of embeddings.
- New turns receive native memory_contents built from exact frozen version selections, including an empty map on deselection. A thin native before-agent state binding is required because upstream treats this map as private state rather than graph invocation input. Immutable version IDs appear in native source paths and a compact current-user selection notice; native middleware remains the only automatic full-content formatter. Helpers use their own selected versions, and interrupt resumes do not refresh frozen paths or contents. Explicit Use latest and Use next turn controls make changes visible.
- A bounded optional project outline uses existing confined reads/exclusions, Python AST, lightweight JS/TS declaration and Markdown-heading extraction, and filename fallback. At most 1024 estimated tokens; bounded process-local cache, invalidated after changes; fail open and omit before losing user context.
- Static preview entry mode and existing command mode share owned process lifecycle, permitted root and Ask/Full access permission policy without enabling shell/browser capabilities implicitly. Browser receives the exact loopback entry URL; active content never inherits desktop backend authority. Windows stop retains the job and member synchronization handles until all children have finished, including a venv Python launcher child.
- Native Windows host-shell commands reuse the same process-job lifecycle at the backend boundary. Commands start suspended until the job owns them; cancellation/timeout/normal exit reap descendants before a settled result. File capture avoids inherited-pipe reader hangs. An unconfirmed stop, timeout or cancellation preserves uncertain effects and project ownership: stopped processes do not establish partial file/external effects. Further model/tool dispatch requires inspection acknowledgement, while already dispatched siblings settle. Ordinary nonzero exits remain correctable command failures. Native tools, approvals and the agent loop remain framework-owned.

## Risks / Trade-offs

- Path normalization could weaken confinement: compare resolved filesystem identity, retain original I/O form, and test aliases, UNC, links and escapes.
- Recovery could repeat effects: independently persist call outcomes, preserve successful siblings, never resume terminal tool nodes blindly, and keep unknown effects gated.
- Project serialization reduces same-folder concurrency: helpers share their task family and independent roots continue.
- Bounded responses can truncate calls: incomplete input remains inert and terminal status explains the response limit.
- Outlines and document indexes may stale: revalidate source identity/content and treat them as disposable derived context.

## Migration Plan

Implement ordered slices with focused regressions; generate contracts; run default/integration/desktop/OpenSpec gates and isolated Windows app acceptance. Merge and refresh established local build only after validation. Disposable product records may be reset without compatibility shims; preserve weights and unrelated project files. Record progress in tasks and the existing handover, then sync/archive the completed change.
