# Design

## Context

See proposal.md for motivation. Baseline is merged revision fdea336. Three implementation owners have separate source areas; the root owns live Qwen use, OpenSpec, handover, and delivery. The baseline desktop acceptance build passed before mutations. Its owned processes were stopped before loading the corrected service.

## Decisions

- Rewind uses a narrow upstream graph middleware hook with Deep Agents' native summarization state schema. Clearing a message list alone leaves stale compaction metadata; supplying private keys as invocation input is filtered upstream. Reset only the first-turn rewind path, preserving ordinary continuation.
- Queue retries retain one input identity and exact authored payload. A failed response triggers a read of saved acceptance; an unavailable read leaves the same identity available for a deliberate retry. A newer draft remains untouched. Backend admission remains the sole owner of scheduling and deduplication.
- One action-dependent host-command policy covers native execute, managed start, skill scripts and custom-preview argv. Static HTML remains a confined preview. First-use approval and grants bind the resolved starting folder and actual action arguments. Full access retains the mandatory first card; later behavior follows the chosen mode.
- A timed-out managed command reports a durable uncertain ToolOutcome through the existing execution-control and inspection acknowledgement path. Process-lifecycle ledger evidence is distinct from arbitrary partial file/external effects; no second recovery authority is introduced.
- Helper finalization and asynchronous job publication acquire execution authority before the harness owner lock. Late uncertainty updates the source child and parent activity, and their persisted run rows share one transaction before notification. Fault tests cover lock inversion, late terminal updates and partial writes across restart.
- Failed preview stop retains its process-tree handle and owner. Status and the existing preview control expose pending cleanup and offer Retry Stop. Delete performs cleanup before destructive record changes and refuses success while stop remains unconfirmed.
- UI preview start shares lifecycle admission and the conversation lock with deletion, then rechecks membership and selected permissions. Either ordering cannot create a process owned by a deleted conversation.
- Model diagnostics reuse the adapter's model identity resolution. Native router smoke uses its exact preset with autoload disabled. Connected endpoints require an observed alias or one unambiguous model. Shared router RSS never becomes a per-model measurement.
- Compact projection preserves the official native task description, including its selected helper identities and roles. The existing native middleware remains the helper catalogue authority; no rendered-list parser or duplicate registry is introduced.
- Shared startup resolution defaults managed parallelism to one, with Workbench provenance. The engine owns queued requests; explicit Auto or positive counts remain unchanged. Native defaults and historical omitted/Auto loading identities still mean the four shared slots they actually used. Live b11045 logs establish that a repeated-snapshot helper plus two other requests exhausted the unified pool and failed all processing slots together. Full observed capacity and Unlimited generation remain unchanged.

## Risks and validation

- Private upstream compaction state: exercise the real compiled graph/checkpointer and installed native summarizer, proving both Retry and Edit discard old summary and include the new request.
- Lost network acknowledgements: mounted desktop tests model a committed Queue followed by response failure, unavailable reconciliation, and newer drafts.
- Process termination failure: isolated process and native API fault tests prove ownership survives until confirmation and deletion remains retryable. Live normal Stop is separate evidence.
- Model task quality: record exact natural prompts, tool/result traces and produced artifacts; independently test browser behavior. Distinguish application defects, model choices, and features that were not exercised.

## Delivery

Run affected focused regressions, fresh independent review, backend default and integration acceptance, desktop build, shared-contract freshness, OpenSpec validation and diff checks. Then restart the owned baseline processes onto the built revision, repeat relevant live checks and Qwen journeys, and verify process/bundle identity and launcher compatibility. Preserve downloaded weights and runtimes; disposable test chats/projects need no migration.
