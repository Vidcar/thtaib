# Design

## Context

The application owns run outcome, project snapshots and its durable interaction log. LangGraph owns checkpoints and the pinned React SDK owns message/tool projections. See the proposal for the failure modes and the delta specs for required behavior.

## Goals / Non-Goals

**Goals:** Preserve one authoritative execution outcome through slow or failed finalization, keep generated output independent of replaceable measurements, and make replay correct and bounded for every subscriber.

**Non-Goals:** Reconstruct already deleted nested events exactly, promise an atomic whole-folder view while other runs edit the same project, or replace the upstream projection engine.

## Decisions

1. **Persist settlement before capture.** Claim finalization once under the harness lock, save the settled status and saving phase, then release the lock for filesystem capture. Stage, verify and atomically publish the snapshot before writing one terminal event. Restart sees the saved settlement and resumes finalization without graph dispatch. A failed capture leaves the settled execution result and an explicit unavailable branch. Stop during saving returns `run_finalizing`.
2. **Capture a verified set of bytes.** Prune excluded directories before descent, use lexical root-relative paths and reject links that escape the root or change during capture. An explicit empty allowlist differs from an omitted allowlist. Final branch capture includes safe new project files. A concurrent same-project writer can affect which bytes are captured, so the manifest asserts verified captured bytes rather than a whole-folder instant.
3. **Keep a latest-value measurement mailbox.** The inference stream writes a request-scoped sample without awaiting callbacks. A separate publisher coalesces live samples, and finalization reads the latest valid one synchronously. Native events remain ordered; persistence exceptions stop dispatch with a distinct interaction error.
4. **Keep scalar interaction cutovers.** Extend the existing SQLite migration for cursor, projected status and display cutover. Update those scalars transactionally with the snapshot. The SSE generator moves blocking reads and replay work off the event loop. A batch resolves its binding once and carries the resulting snapshot forward; partial reconstruction is seeded once and then updated from new events.
5. **Page checkpoint history from a known boundary.** Save the pre-run head; subsequent linkage requests at most 64 items per page and stops at the pre-run or last linked checkpoint. An absent saved boundary is a linkage error, not permission to scan and attach unrelated history.
6. **Patch the pinned SDK narrowly.** The initial hydrated root stream and wildcard lifecycle watcher begin after the state cursor. Each later subscription has its own replay cutoff; a union stream begins at the minimum requested cutoff, and fanout skips older events for subscribers that already have them. HTTP reconnect position belongs to each stream handle and advances only after a complete parsed event. The application transport no longer overwrites all `since` values. Stable event IDs protect synthetic seeds and replay overlap.
7. **Compact only completed token deltas.** Keep raw interaction events during a live run. After completion, replace token deltas with ordered final message replay while retaining tool, lifecycle and namespace identities. The backend bridges only known compaction gaps. Existing deleted history remains unavailable and is labelled as such.

## Risks / Trade-offs

- **Pinned dependency patch drift** → Keep the patch small, pin its exact version and test through the actual installed SDK; revisit it on SDK upgrades.
- **Concurrent project writes** → Verify each captured copy and state the snapshot's byte manifest truthfully; do not imply an atomic folder transaction.
- **Restart between settlement and snapshot publication** → Use durable settlement and owned staging cleanup; recovery completes once without tool replay.
- **Long legacy histories** → Add scalar metadata through migration and keep a compatible backfill; benchmark an isolated long conversation and excluded tree.

## Migration Plan

Apply the SQLite migration in the existing application database. The new run fields are optional so older records load. Backfill scalar metadata from existing snapshots where needed. Preserve existing chats and model weights. Validate against isolated data first, then update the established local application after local gates and live checks. Rollback of application binaries retains the prior database backup; it does not claim restoration of old deleted event detail.
