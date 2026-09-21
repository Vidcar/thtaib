# Design: Complete persistent shared-agent Chat

## Technical Approach

Prerequisite: deliver and verify `repair-local-interaction-boundaries` before starting this packet. Retain its atomic selection/transport binding, generation-guarded hydration/cancellation/registration/command acknowledgements and draft isolation when adding the persistent queue. Preserve main-owned validated external navigation and requesting-document/frame token authorization. Retain repeated-text legacy chronology, conservative idempotent projection repair, display-edit cutovers and continuation without effect replay. This is a post-delivery repair of the completed migration, not a replacement architecture. Packet 04 still owns the coherent async transition.

Extend the existing Chat schemas/store/routes, harness driver, approval records and Electron Chat surface. Keep one application run per turn on the saved LangGraph thread; do not reconstruct active context from the displayed transcript. Freeze a queued item's intended setup before dispatch and keep immutable session area identity separate from selected model/profile.

After `migrate-local-agent-interaction` is implemented and verified, use its supported `@langchain/react` interaction boundary for message/tool/state projections, scoped subscriptions and interrupts. Do not extend or depend on the superseded custom `snapshot` / `run_event` / `stream_end` protocol. Keep application-owned run/thread identity, durable transcript/history, checkpoint linkage, authorization, reconnect/hydration and final reconciliation authoritative; map SDK events to those identities and ensure internal summarisation is not shown as an answer. Do not create another token transport or checkpoint database. The SDK integration does not implement the Chat features in this change.

Expand the shared approval service into exact-action, session and persisted matching grants. Grants are backend policy records, not prompt text. Convert decisions into supported framework resume payloads; distinguish ordered actions within one interrupt from typed questions. A pending approval remains a live run with interrupt details, consistent with the existing lifecycle enum.

Keep edit-and-retry/Retry task separate from answer-only regeneration. A branch records its source checkpoint and own head; project-state branches obey existing consistent snapshot/restore requirements, retain their project identity and use owned restored workspace bindings. Do not expose a checkpoint granularity the installed saver cannot support. Answer-only regeneration cannot silently fall back to replay.

Extend the artifact/related-file seam rather than storing arbitrary model-written paths as outputs. Retain uploaded originals by default in the session, put fitting labelled text into current-user content even with tools off, and distinguish mutable project references from immutable copies. Add one dependency-aware deletion and manual backup service for later areas to extend.

## Data and failure boundaries

Keep application rows, checkpoint bytes, scratch, project files, retained assets and diagnostic captures separate. Use supported checkpoint APIs and a consistent backup mechanism; restore to a clean data root and never restart uncertain external effects. Preserve real content and existing conversations through any supported migration. Closing the desktop does not cancel work; explicit Quit reconciles owned work and never claims to stop connected engines.

## Integration references

Use the checkout's locked versions; these are integration entry points, not permission to upgrade the stack.

- [LangGraph interrupts and resume](https://docs.langchain.com/oss/python/langgraph/interrupts)
