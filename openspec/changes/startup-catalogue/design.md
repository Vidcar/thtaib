# Design

## Context

Project and chat catalogue reads are already small and independent. Finished chats use saved transcripts and snapshots, while live turns retain their raw events until terminal display publication. Startup token maintenance waits for a catalogue request. The remaining gap is in `WorkbenchSidebar`: after thirty failed reads it marks a list loaded, so empty-list copy and ready status can appear without a successful request.

## Goals / Non-Goals

Finish truthful initial-list recovery while retaining the delivered fast catalogue and token-compaction paths. This change does not warm models, delete chats, or introduce another catalogue or status authority.

## Decisions

- Each list owns its first-success state. Failure keeps it unresolved, retries with bounded backoff, and remains visible through the existing status/error treatment. A success for the other list must not erase the unresolved list's failure.
- A successful empty response is the only initial condition that permits empty-list copy. Unmount or a new list selection disposes the old retry owner; late results cannot mark the replacement ready.
- Saved turn compaction retains ordered final messages, tools, lifecycle, namespace and partial outcomes. It starts only after terminal projection is durable and preserves active subscribers and prepared reconnect seeds. Archive and remove-project remain non-destructive.
- The previous warming proposal was explicitly removed by the delivered model-residency change. Explicit selection, an authorized submitted turn or recovery of previously accepted queued work may load a model under their existing admission rules; passive launch cannot.

## Risks / Trade-offs

A retry loop must be cancellable and use bounded backoff without blocking rendering. A fake-clock regression should cover failure beyond the former thirty attempts, later success, independent lists and disposal; it must not wait thirty real seconds.

## Migration Plan

No stored-data migration. Deliver the recovery regression and fix, verify the current desktop, then archive this change. Catalogue and token requirements have been reconciled with the current main specs; do not restore the retired `MODEL-WARM` delta.

## Open Questions

None.
