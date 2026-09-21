# Design: Complete local delegation and shared resource coordination

## Technical Approach

Use native Deep Agents task delegation and the same agent-setup resolver/model adapter for primary and child agents. Construct supported child agents/subgraphs with child-specific middleware and knowledge backends, including any general-purpose fallback. Verify the locked version's compiled-subagent and inherited checkpointer behaviour: independent invocations need distinct state under the root recovery owner, not disabled recovery or accidental persistent-across-call state. Do not add another task tool implementation, agent service or checkpointer database.

Use explicit root/parent/child/call identities and stable invocation scratch routes. Use the native public framework namespace as the canonical execution scope where supported, then map it to durable application identities and the prerequisite's `@langchain/react` scoped selectors/subscriptions/interrupt presentation. Inspect supported framework state propagation/merge rules instead of assuming every field is private. Correlate each model request at capture time, never by slicing a global log during concurrent calls. Resume parallel interruptions against the root thread using exact interrupt IDs and typed payloads; SDK selectors do not grant access or choose child policy.

Keep three concerns distinct: a logical deployment dependency protects configuration; a short-lived inference permit covers a model call; canonical project coordination covers conflicting read-modify-write tasks. Awaiting children or human input must not retain a permit/lock those operations need. Include internal summarisation and optional selector model calls in admission. Hardware grouping must prevent two deployments independently promising the same capacity. Connected servers may have uncontrolled external clients.

## Residency transition

Persist the frozen launch configuration and pending operation identity, then follow: authorised → quiescing → source unloaded → dependent work → dependent resources released → restoring → resumed. Confirm each external transition, retain errors/unknown outcomes, and keep cancellation/restart reconcilable. Block incompatible new admissions atomically before waiting for in-flight calls. Never suspend mid-generation or evict a non-suspendable client. Release the inference permit while reserving the device opportunity. Save the dependent result before restoration and rebind an altered endpoint without repeating that effect.

The first proof uses a real managed model around a controlled owned operation. Change 08 supplies actual ComfyUI/speech integration and two-sided engine release; it is not a prerequisite here. This coordinator owns resource admission/lifecycle, not a second model/tool loop or workflow scheduler.

## UX presentation

Follow the shared UX contract in `../03-complete-shared-chat/design.md#shared-ux-contract` for activity, approvals, queues, attention and notifications. Delegation adds parent/child attribution to the same activity panel and attention list rather than a separate monitor. Each visible item must show the owner, frozen setup, current state, wait reason, approval/input need, partial result or terminal result in plain language, with technical IDs and trace evidence available in expandable details.

Cancellation controls must explain scope before action: root cancellation, owned queued children, active child/tool/model calls, handover phases and any independent sibling results that can remain. Individual-child cancellation appears only when supported by the verified execution semantics for that child path. Simultaneous approvals and questions stay inline with clear resource/action scope and use the shared attention model when the app is backgrounded.

Technical verification and Dave's UX acceptance are separate completion records. Focused delegation UX acceptance is currently pending, not accepted. It covers the built Windows journey at full-window and half-screen sizes, Windows display scaling, keyboard navigation, long child/activity content, simultaneous waits/approvals and at least one failure/recovery state. UX acceptance remains pending until Dave accepts the built journey or explicitly defers it.

## Integration references

Use the checkout's locked versions; these are integration entry points, not permission to upgrade the stack.

- [LangGraph interruption and resume](https://docs.langchain.com/oss/python/langgraph/interrupts)
