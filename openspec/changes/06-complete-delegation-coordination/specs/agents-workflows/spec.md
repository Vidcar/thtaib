# agents-workflows delta

## ADDED Requirements

### Requirement: AGT-015 - Await native delegation with frozen child setup and policy

Authorised delegation SHALL use native Deep Agents task handling and await the actual child result linked to its original task-tool call. A background run ID is not completed delegation. Tools-off or current policy excluding delegation SHALL keep it unavailable.

Each child SHALL resolve the shared versioned setup into an immutable invocation snapshot: role, actual local deployment/profile/request settings/context capacity, composed instructions, tools, knowledge and workspace relationship. Resolve application IDs into supported framework fields, not unrelated provider strings. Every child, including automatic general-purpose fallback, SHALL receive child-configured selection/execution, capture, diagnostics, recorded-tool, approval and cancellation middleware where applicable. Revalidate authorised child types and scoped grants at dispatch/resume; child selection cannot broaden mandatory restrictions or permissions. Later setup edits do not change a live/paused child.

#### Scenario: Native child result

- **WHEN** a parent invokes an authorised child
- **THEN** the original task call awaits its real result using the frozen local setup, with no competing task implementation or background-ID success.

#### Scenario: Fallback restrictions

- **WHEN** the framework exposes a general-purpose child or a saved child resumes after access changes
- **THEN** the same child-specific policy is enforced; neither fallback nor a saved definition gains broader authority.

### Requirement: AGT-016 - Isolate child invocation state and scoped loading resources

Independent delegated tasks SHALL have unique invocation identity and state under the root graph's checkpoint/recovery owner, linking root, parent, child, task call and native framework namespace. Where supported, the native namespace is the canonical execution scope; map it explicitly to durable application IDs and the shared SDK's scoped selector/subscription identity. A child name or UI selector is not an invocation ID or authorization. Deliberately scope framework-copied/merged custom state; do not accidentally enable persistent-across-call children or a competing checkpoint store.

Child tools, selected memory/protected instructions and full skill packages SHALL bind the child's actual versions/scopes, not parent closures or cached loading state. Materialised knowledge and scratch/offloads SHALL use stable invocation-scoped routing retained on resume. Sibling loading/cleanup must not overwrite packages, expose deselected knowledge or delete another invocation's history/results. Transfer executable resources only through the authorised environment path. Message/context isolation does not imply knowledge isolation, separate project access or a host sandbox.

#### Scenario: Parallel same-type children

- **WHEN** two invocations use the same child type with different selected knowledge
- **THEN** unique state/scratch routes load the correct versions and preserve root recovery without sibling contamination.

#### Scenario: Resume and cleanup

- **WHEN** a paused child resumes while a sibling finishes
- **THEN** its materialised resources/history remain available and cleanup affects only the correct invocation.

### Requirement: AGT-017 - Attribute child evidence and route every interrupt exactly

Shared run observations, including the prerequisite's SDK-scoped projections, SHALL attribute child messages, reasoning, model/tool calls/results, approvals and artifacts to root/parent/child/call identity. Correlate concurrent captures per call, not overlapping global log slices. Child output SHALL be independently inspectable; only the actual returned child result must reach the parent, not every private child message. Selectors scope observation/display and do not authorize a child or imply its completion.

Represent all pending interruptions and distinguish several actions in one interrupt from several independent interrupts. Route decisions to the saved root graph/thread by exact interrupt identity and checkpoint/child association. Preserve ordered allowed tool decisions and separately validated question/elicitation values. Reject stale/duplicate decisions and recheck access before resume.

#### Scenario: Concurrent child capture

- **WHEN** two children make overlapping model/tool calls
- **THEN** each capture/result is attributed to its own invocation and the result returned to the parent is traceable.

#### Scenario: Parallel decisions

- **WHEN** several children pause with different approval or input requests
- **THEN** each validated decision resumes only its matching interrupt against the root thread; stale decisions fail.

### Requirement: AGT-018 - Cancel owned run trees and preserve independent child outcomes

Root cancellation SHALL stop new dispatch and propagate through owned queued children, model calls, tools, MCP resources and handover phases. Confirm application cancellation only after owned application work stops; retain uncertainty about host/remote effects. Cleanup must not cancel unrelated clients. Restart SHALL reconstruct frozen definitions and genuine interrupts, reconcile orphaned work and never replay an uncertain effect blindly.

A failed child SHALL retain real failure/partial evidence while independent useful children may finish. Dependent work remains blocked unless an explicit authorised recovery handles it. A qualified parent result is allowed only where task requirements permit; missing required output is not complete success. Do not blanket-retry mutating tools/runs. Individual-child cancellation is optional until its parent semantics are verified. Restore a suspended shared deployment only when still needed and safe, not solely to resume an already-cancelled turn; restoration failures remain actionable.

#### Scenario: One child fails

- **WHEN** a required child fails while independent siblings are still useful
- **THEN** siblings may finish, dependent steps remain blocked and the parent cannot claim missing required work succeeded.

#### Scenario: Root cancellation and restart

- **WHEN** the root is cancelled or restarts during child or handover activity
- **THEN** owned work is reconciled without affecting unrelated clients or repeating unknown effects.
