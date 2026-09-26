# Design

## Context

See proposal.md for motivation. The installed SDK intentionally retains tool handles for a thread's lifetime. AgentMessageFeed currently places unmatched handles into the current run, keys messages through asynchronously loaded run records, and samples messages separately from tools. ChatPanel clears all historical metadata on each run and removes the feed while ownership is reconciling. Backend stream-page sanitization strips run_started_seq before ResumeProjection can reset.

## Goals / Non-Goals

**Goals:** Repair display identity, scoped tool reconciliation, continuous history and internal replay boundaries using existing owners; validate the complete warm-session path.

**Non-Goals:** Replace SDK assembly/transport, change model execution or permission policy, introduce a second durable history/runtime, or change downloaded models and everyday settings.

## Decisions

- Row/disclosure identity uses conversation/namespace, originating input-message ID and message ID, never loaded run-detail availability. Keep existing run metadata while fetching only missing/new details and reject stale selection callbacks.
- Add typed tool origin records under the existing public Workbench metadata: run ID, input-message ID, namespace and call ID. Backend native projection owns these records. Handle reuse must never overlay a previous handle/result onto a newer turn; frontend reconciles by scoped origin and keeps unmatched old handles out of current activity. Publish origin before its native tool event without altering tool execution identity. Historical message blocks/results remain authoritative for settled content.
- Observe native tool-start on the existing SDK root bus to confirm a handle's origin after the SDK processes that event. An origin frame alone cannot confirm a retained handle, since historical values can replace its object before the new start. Pending observations are invalidated on disposal, thread switch and superseding starts.
- Keep once-per-call origin frames through values compaction. Privately compress their exact message payload with standard-library zlib/base64 and decode before public replay: the SDK requires coherent full values, while uncompressed repeated histories violate existing storage bounds. Referencing the latest archive is unsafe because even complete same-ID messages may later be revised. Private flags/compressed data never enter public metadata.
- Sample message/tool/origin/current-turn display state as one unit. Keep verified transcript mounted during run admission; independently gate mutable controls, status and side effects. One transcript scroll owner observes growth without disturbing reading/selection.
- Consume raw internal run-boundary metadata before public sanitization, preserving public wire filtering and durable event cursor semantics. Reconstruction clears open-message/tool state at a boundary and never reruns work.
- Tests begin with current failing cases. A persistent SDK + mounted ChatPanel exercises sequential replies, tools and delayed acknowledgements; backend tests inspect replay boundaries/order and native Electron checks inspect DOM order/identity/layout before refresh.

## Risks / Trade-offs

- Reused call IDs or tools arriving before an assistant block can alias retained SDK handles: explicit backend ownership and phase-controlled tests must prevent cross-turn status/result leakage.
- Frozen history during admission can mask a genuine switch: scope retained display by selection generation, conversation and interaction thread; immediately dispose it on navigation.
- More metadata can increase projection work: add origins once per scoped call and retain compact records; measurements do not rebuild transcript.
- Tests that supply preordered arrays can miss integration defects: acceptance requires actual SDK/native streaming, exact row order, one-call counts and DOM stability.

## Migration Plan

Additive generated metadata contracts; no database schema or model migration. Build and validate locally, restart only the established backend when needed while preserving loaded model processes, and preserve unsaved renderer edits. Archive the completed change into current specs, merge validated delivery and update HANDOVER.md.
