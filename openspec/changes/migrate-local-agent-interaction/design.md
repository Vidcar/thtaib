# Design

## Context

See proposal.md for motivation and scope. Verified starting checkout: clean main at `98c77cc` (PR #113), 21 September 2026. Packet 02 is archived; 03–08 are proposed. The harness owns background workers and drives synchronous `agent.stream(..., stream_mode="updates")`. Chat serializes starts per conversation and passes its stable runtime thread to that harness. `event_stream.py` projects recorded application events; renderer `sse.ts` parses, merges, deduplicates and reconnects them. ChatPanel and AgentRunPanel are its current consumers. Checkpoints remain behind `state/checkpointer.py` and public graph APIs.

## Goals / Non-Goals

Use one upstream frontend interaction runtime and one backend execution invocation per run. Keep the existing adapter, saver and application store. Replacement is conditional on demonstrable removal of generic interaction responsibilities and a real local integration proof. No subsequent packet feature work, second backend, independent scheduler, browser privileged tools or wholesale Agent Chat UI dependency transplant.

## Decisions

### Published compatibility gate

Published tarballs inspected: `@langchain/react@1.1.1` depends on `@langchain/langgraph-sdk@1.11.1`; peers require React `^18 || ^19` and `@langchain/core ^1.1.48`. SDK also requires react-dom 18/19 and depends on `@langchain/protocol ^0.0.19`. Isolated installation succeeded with React/react-dom 19.3.0, core 1.2.9 and protocol 0.0.19. Existing Python lock/runtime resolves Deep Agents 0.7.15, LangChain 1.4.2, LangGraph 1.2.11, langchain-openai 1.6.2 and langchain-protocol 0.0.19. Matching type-package versions and installation are not yet the end-to-end compatibility gate. Keep React/Electron/Python and unrelated dependencies unchanged; pin this minimal tested frontend set only after proof passes.

Both public sync `stream_events(version="v3")` and async `astream_events(version="v3")` are candidates. Prefer retaining the existing sync owner if a complete public sync integration works; async API availability alone does not require moving Packet 04's coherent async transition. If the proof needs async, move invocation, middleware, saver/state access, resume, cancellation and shutdown together into this change before replacement; update Packet 04 instead of leaving another driver migration. Experimental v3 semantics require release-specific tests; never import framework private internals.

### Shared HTTP boundary

Prefer stock HttpAgentServerAdapter under authenticated `/v1/agent-interaction/threads/...` paths. Read its actual creation/binding, command, subscription, state/history and cancellation requests; implement only operations exercised by the product. Unsupported commands fail explicitly. A narrow documented custom adapter is allowed only after demonstrating a materially simpler, safer fix for a specific incompatibility; a broad imitation server facade fails the gate.

Released SDK source (`dist/client/stream/transport/http.js`) defaults to POST commands, POST `/stream/events` and GET state paths under `/threads/{id}`; override these with the privileged prefix. The current main-branch guide's `/stream` is an example, not this release's default. `send` accepts correlated success/error JSON or 202/204; SSE parses protocol JSON in `data`, not SSE id/event fields. Subscription requests include channels and optional namespace/depth/since; source switches/opens streams when requested projections change. State returns controlled values plus next/tasks/checkpoint metadata. Dynamic paths follow binding, and closing adapters aborts observation.

SDK controller `stop()` calls its separate Client's `/threads/{thread}/runs/{run}/cancel?wait=0&action=interrupt`, outside adapter path overrides, and swallows cancellation failures. Product Cancel therefore explicitly awaits the existing authenticated application cancel operation and continues observing authoritative cancellation; do not rely on SDK stop for that action. Navigation uses disposal or `stop({cancel:false})`. This retains the stock transport without manufacturing a broad platform facade. Test this actual separation in the SDK proof.

Application registration must precede execution. Resolve a backend-owned conversation or standalone run scope to its immutable runtime thread/project binding; SDK-generated identifiers cannot manufacture scope or overwrite that binding. Route starts through Chat/Harness admission and effective setup, and approvals/cancel through existing service ownership. Validate allowed message/content, application setup and resume fields. Reject arbitrary config, state mutation, checkpoint choice and workflow jumps. Keep reject-while-active in both frontend and backend; disable implicit rollback/queue behavior.

### One event-producing execution and controlled projection

Drive the existing compiled Deep Agent once using public native event normalization. Preserve upstream message/block/call IDs, execution IDs, native namespaces and parent/child identity. Use upstream protocol types, with explicit runtime validation/serialization at the FastAPI boundary. Filter private graph values, internal summaries, credentials and unselected state. Existing application audit, settings, context estimates and validated-result records remain projections of this invocation. Do not generate native-looking events from the old completed-message stream as a substitute for true incremental output.

Keep actual reasoning separate from answer, tool data and internal compaction. Tools-off and capability gates must still reach WorkbenchChatOpenAI and Packet 02 context/structured-result mechanisms. Native projections cannot repair an unknown tool effect by re-execution.

### Persistence, replay and existing data

Reuse application.sqlite for durable interaction mapping/public projection records if required; LangGraph checkpoints remain untouched except via supported APIs. Keep the readable archive distinct from compacted runtime values. Define a thread-level cursor over durable public records, with native run-local sequence retained as metadata rather than reused across turns. Hydration captures a snapshot and its cutover cursor atomically; live replay starts strictly after that cursor. Bound transient subscriber buffers. Validate and honor supported channel/namespace/depth filters. A cursor outside retention produces explicit resynchronization; it never silently omits output or invokes execution. Final hydration uses persisted application outcomes and retained history, not SDK loading state.

Use recoverable idempotent application-record migrations only if the bridge requires them, test isolated copies before real cutover, and preserve project references, settings, files and checkpoint IDs. Do not add permanent compatibility for synthetic fixtures. Validate observer races, restart and missing/expired cursors against real installed SDK behavior before selecting exact wire responses.

### Frontend lifecycle and presentation

Share one interaction provider/abstraction per selected thread across Chat, live Agent-run, progress, tools and approval selectors. Memoize transports for the selected thread; recreate them on existing-thread switches as required by the installed binding/disposal contract. Disposal disconnects observation only. Explicit cancel routes to the backend; `stop()` alone is not worker-stop evidence. Product cancellation stays cancel_requested until confirmed.

Let the SDK assemble messages/tools/state; reconcile archive and current messages by stable upstream identity without parallel custom reducers. Retain model/profile/setup controls, accessible composer, scrolling and Packet 02 detail views. Latest-value named extensions carry typed product projections; durable audit history stays in records. Agent Chat UI inspection reference is commit `41926d89c9798cebe45a26886d6e437acc5201c1`; its Markdown/code rendering is a candidate for selective adaptation with license attribution. Its old stream provider is not adopted. Disable raw model HTML and arbitrary executable UI.

Interrupt decisions include authoritative thread, application run, interrupt ID and namespace, translated to installed Deep Agents decisions. Keep existing continuation reservations and stale/duplicate/wrong-run protections. No privileged headless browser tools. All HTTP methods and SSE requests use Electron-main token injection; renderer never holds the secret.

## Risks / Trade-offs

- Experimental Python events or protocol version mismatch → inspect exact source, run SDK plus FastAPI proof and fail the replacement gate if public interfaces cannot satisfy it.
- Frontend finality differs from worker finality → application lifecycle extension and durable final hydration remain authoritative.
- Native state is smaller than readable archive or exposes private material → controlled projection, retained archive and stable identity reconciliation.
- Replay/interrupt races → deterministic interleavings, durable state and actual side-effect checks, then real-model Windows proof.
- Added dependencies without reduced ownership → remove generic parser/reducers/controllers and legacy contracts only after all consumers migrate; compare responsibilities, not raw line counts.

## Migration Plan

1. Finish artifacts and align proposed packets before expanding implementation; current main specs remain unchanged until delivery.
2. Reproduce baseline checks and verify published/installed source. Build reversible isolated proof using actual FastAPI services, compiled agent, installed local model and React SDK. Require incremental reply, tool, approval/denial, continuation and confirmed cancellation before replacement.
3. Implement the bounded bridge, persistence/replay policy and shared consumers; test real SDK lifecycle, data migration and Packet 01/02 through the new path.
4. Remove all unused legacy interaction consumers, parsing, merge/controller and contract code; retain application audit meanings and confirmed outcome records. Regenerate owned contracts and preserve behavioral SSE checks in new form.
5. Run default/integration backend, contract freshness, desktop build and OpenSpec checks; exercise rebuilt Windows app and real model under isolated data. Only after these gates sync/archive this change, merge and deliver locally. Next feature packet remains 03.

Before replacement, rollback is simply retaining the current app; proof data is disposable. After new durable writes, do not claim rollback without a tested export/replay or reverse migration. A failed compatibility gate leaves the active change and precise blocker here, with all replacement/live checks incomplete.

## Evidence and remaining gate

- Baseline desktop build/typecheck and existing SSE/settings checks passed on 21 September 2026.
- Baseline 315 default and 142 integration backend tests and generated-contract freshness passed. Initial uv command encountered the ordinary running backend's executable lock; `uv run --no-sync` ran the same installed test runner without disturbing that app.
- Published tarballs, exports and request implementation inspected under `.scratch/interaction-compat`; public sync/async effect-free graph probes passed, including values/output projections. Strict OpenSpec validation passed 16/16.
- Scratch native harness proof preserved actual existing start/persistence/interrupt/resume/cancel owners with one public v3 invocation. Deterministic approve/deny completed with one audit call/result pair; cancellation transitioned from cancel_requested to worker-confirmed cancelled and closed the native generator. Native seq restarts on resume too.
- Real Qwen3.8-27B / b11045 / context8192 / reasoning-preserve proof using WorkbenchChatOpenAI completed with one captured model request through public v3 events. Evidence in `.scratch/interaction-native-proof`. This proves native execution, not yet the full SDK/FastAPI/Windows gate. Isolated model owns port8127/root `.scratch/interaction-model`; ordinary data untouched.
- Full SDK/FastAPI real-model proof remains pending. No product behavior, dependencies, data or current contracts have been replaced.

Release/source entry points: [React package](https://www.npmjs.com/package/@langchain/react/v/1.1.1), [custom transport reference](https://github.com/langchain-ai/langgraphjs/blob/main/libs/sdk-react/docs/custom-transport.md), [Python public events](https://docs.langchain.com/oss/python/langgraph/event-streaming), [Agent Chat UI revision](https://github.com/langchain-ai/agent-chat-ui/tree/41926d89c9798cebe45a26886d6e437acc5201c1). Published tarball and installed release source take precedence over main-branch examples.
