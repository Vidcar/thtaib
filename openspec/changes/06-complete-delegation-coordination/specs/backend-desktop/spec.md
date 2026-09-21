# backend-desktop delta

## ADDED Requirements

### Requirement: API-012 - Coordinate canonical projects and model-call capacity separately

The backend SHALL allow concurrent read-only work on stable inputs and serialise conflicting tasks that may modify the same canonical project, including aliases/alternate records. Protect the relevant read-modify-write operation, not only the final write. A waiting parent must not hold a lock needed by its child. Separate child workspaces require explicit conflict-aware result application.

Logical deployment dependencies SHALL protect against uncoordinated stop/reload/repin, while inference permits cover only actual model requests. Release permits while waiting on children/tools/humans. Every shared call, including compaction and optional selection, SHALL use admission with shared-device capacity and supported context/output reservations. A server slot observation is not an atomic reservation or authority over unrelated connected clients.

Compatible request settings may reuse a deployment. Incompatible startup/residency requirements SHALL use coordinated lifecycle or cancellable actionable waits/unavailability, not hidden substitution, silent parent reload or an unreleasable wait. Report technical capacity/deadlines separately from optional user budgets; add no hidden step/token/iteration/child-count ceiling.

#### Scenario: Project aliases and child wait

- **WHEN** parent/child tasks reference the same folder through different paths
- **THEN** conflicting read-modify-write work is coordinated without the waiting parent deadlocking its child.

#### Scenario: Model permit while awaiting child

- **WHEN** a parent has completed a model request and awaits delegation
- **THEN** its inference permit is released; child and internal model calls still pass through shared hardware admission.

### Requirement: API-013 - Freeze and quiesce an explicitly authorised residency handover

Users SHALL have inspectable Keep loaded and Allow unloading for other local engines choices. Handover requires selected authorisation, verified management ownership and visible affected sessions/device dependencies. Persist the exact original launch inputs, logical deployment binding, pending dependent-operation identity and transition before disruptive work; retain the same run/thread.

Atomically block conflicting new admissions, then wait for in-flight model requests to complete at a safe boundary with a durably identifiable response/continuation. Do not evict mid-generation or while another session holds a non-suspendable dependency. Unload through verified owned lifecycle, preserving exact weights/runtime/startup settings. Confirm process exit or a tested unload result; an acknowledgement alone does not establish released memory.

#### Scenario: Keep loaded or active dependency

- **WHEN** handover encounters a Keep loaded policy or non-suspendable session
- **THEN** it waits or reports the conflict without silent eviction.

#### Scenario: Authorised unload

- **WHEN** all affected dependencies permit suspension and active calls reach a durable safe boundary
- **THEN** new conflicting admissions remain blocked and owned unloading is verified before dependent work starts.

### Requirement: API-014 - Retain dependent results and restore the same continuation

During handover the coordinator SHALL reserve the necessary device/residency opportunity without holding an inference permit or project lock required by the dependent work. Await the authorised real operation and durably retain its result/job identity before restoration. Release reservations on safe cancellation/failure; dependent-engine resource release requires a verified authorised management contract, not merely ownership of one submitted job.

Restore the frozen original model configuration, verify readiness and rebind the adapter if process/endpoint identity changed, retaining replacement lineage. Continue the existing run/thread with the saved result, never resubmit the completed dependent effect. Conversation continuity does not imply preserved KV/GPU cache or zero reload cost. Failed restoration SHALL preserve completed results and expose a recoverable restore action.

This change SHALL prove real managed-model unload/restore around a controlled owned operation. Fixtures may test races/failures, but cannot replace observed model unloading/restoration. Change 08 owns the real media operation and two-sided release proof.

#### Scenario: Restore with changed endpoint

- **WHEN** dependent work has completed and the restored process receives a new endpoint identity
- **THEN** the adapter rebinds to the verified frozen configuration and the same run continues with the retained result.

#### Scenario: Restoration fails

- **WHEN** dependent work succeeded but the original model cannot reload
- **THEN** its output remains available and recoverable restoration does not repeat the external effect.

### Requirement: API-015 - Expose one attributable activity and resource-wait view

Existing progress/events SHALL extend to expandable child activity and one shared activity/queue view for Chat, Lab-owned work and later Workflow/media. Show task, actual model/profile/setup, tool/access selection, approval/input state, queue owner and terminal result by invocation. Parent/child progress, waits, approvals, typed inputs and results SHALL be attributable in plain language, with technical trace details available on expansion. Waiting SHALL distinguish inference capacity, model residency, canonical project access, user input and Lab exclusivity. Handover SHALL expose quiesce, unload, dependent work and restore phases; only operations with valid ownership are offered.

Cancellation controls SHALL describe their scope before action. Root cancellation, queued owned children, active child/tool/model calls, handover phases and preserved independent sibling results must be distinguishable. Individual-child cancellation SHALL be exposed only where execution semantics have verified support for cancelling that child path without misrepresenting parent/root effects.

#### Scenario: Waiting child

- **WHEN** a child waits for model capacity while another action waits for user input
- **THEN** the activity view distinguishes the cause, owner and invocation rather than displaying both as unexplained running.
