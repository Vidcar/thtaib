# Design: Complete persistent shared-agent Chat

## Technical Approach

Extend the existing Chat schemas/store/routes, harness driver, approval records and Electron Chat surface. Keep one application run per turn on the saved LangGraph thread; do not reconstruct active context from the displayed transcript. Freeze a queued item's intended setup before dispatch and keep immutable session area identity separate from selected model/profile.

Use the existing privileged SSE snapshot/event contract. Persist incremental messages/events by run/call identity, reconcile final messages once and preserve terminal hydration. Internal summarisation output must not be promoted into answer events. Do not create another token transport or checkpoint database.

Expand the shared approval service into exact-action, session and persisted matching grants. Grants are backend policy records, not prompt text. Convert decisions into supported framework resume payloads; distinguish ordered actions within one interrupt from typed questions. A pending approval remains a live run with interrupt details, consistent with the existing lifecycle enum.

Keep edit-and-retry/Retry task separate from answer-only regeneration. A branch records its source checkpoint and own head; project-state branches obey existing consistent snapshot/restore requirements, retain their project identity and use owned restored workspace bindings. Do not expose a checkpoint granularity the installed saver cannot support. Answer-only regeneration cannot silently fall back to replay.

Extend the artifact/related-file seam rather than storing arbitrary model-written paths as outputs. Retain uploaded originals by default in the session, put fitting labelled text into current-user content even with tools off, and distinguish mutable project references from immutable copies. Add one dependency-aware deletion and manual backup service for later areas to extend.

## Data and failure boundaries

Keep application rows, checkpoint bytes, scratch, project files, retained assets and diagnostic captures separate. Use supported checkpoint APIs and a consistent backup mechanism; restore to a clean data root and never restart uncertain external effects. Preserve real content and existing conversations through any supported migration. Closing the desktop does not cancel work; explicit Quit reconciles owned work and never claims to stop connected engines.

## Integration references

Use the checkout's locked versions; these are integration entry points, not permission to upgrade the stack.

- [LangGraph interrupts and resume](https://docs.langchain.com/oss/python/langgraph/interrupts)
