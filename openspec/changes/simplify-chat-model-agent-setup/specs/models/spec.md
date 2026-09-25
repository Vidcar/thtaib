# Spec Delta

## MODIFIED Requirements

### Requirement: MOD-022 - Apply managed configuration changes safely

Idle managed configurations SHALL support validated reconfiguration with expected-version and retained-history compatibility checks. Editing a loaded configuration SHALL preserve its current launch snapshot until an explicit safe reload; active, queued, waiting, cancelling, Lab and helper consumers SHALL block a disruptive configuration change with named reasons. Capacity-driven eviction of an idle model instance MAY occur between calls, including during an alternate-model helper handoff, provided no in-flight inference request is interrupted and the next call can reload its exact selected configuration. Automatic child ports SHALL be allocated and checked at launch; fixed-port conflicts fail before spawn. Ownership and observed readiness SHALL precede committing loaded values. Failure SHALL preserve prior and attempted configurations, attempt at most one safe restoration and report truthful stopped/failed state; restart SHALL reconcile interrupted changes. Connected endpoints SHALL not grant reload authority.

#### Scenario: Idle conversation context change
- **WHEN** an idle conversation applies a valid context change
- **THEN** the owned model reloads and the same conversation continues with verified capacity
- **AND** its draft and history survive.

#### Scenario: Queued consumer blocks reload
- **WHEN** a queued or waiting turn depends on a configuration being edited
- **THEN** reconfiguration identifies that consumer without discarding its selected setup.

#### Scenario: Capacity handoff between calls
- **WHEN** one loaded slot is needed by a different-model helper after the parent's model call ends
- **THEN** the helper loads its exact configuration and the parent reloads its own configuration before its next call
- **AND** neither in-flight inference request is stopped.

#### Scenario: Conflicting or failed launch
- **WHEN** the requested configuration fails to become ready
- **THEN** no unrelated process is stopped or healthy foreign endpoint claimed
- **AND** prior selection and a usable recovery path remain.

## ADDED Requirements

### Requirement: MOD-032 - Bound managed model residency

The application SHALL save one positive maximum-loaded-model count for managed llama.cpp configurations. A fresh installation SHALL default to one. Every loaded launch configuration SHALL consume one slot, even when two configurations use the same weights; the count SHALL remain distinct from each model's parallel request slots. Connected endpoints SHALL remain outside this owned count. A requested model SHALL load on explicit model selection or on the first submitted turn that needs an unloaded selection. Application launch, chat restoration, passive status reads and navigation SHALL NOT warm or load a model. Loading SHALL show pending, loaded or failed state, and MUST NOT silently substitute weights, quantization, device or settings.

#### Scenario: One-slot model switch
- **WHEN** the limit is one and a different configuration is explicitly selected
- **THEN** the previous idle instance unloads and the requested one loads; if inference is in flight, the selection waits without interrupting it.

#### Scenario: Two models remain ready
- **WHEN** the limit is two and two different installed configurations are selected
- **THEN** both can remain loaded and serve separate chats or parent/helper calls, subject to actual memory and each model's parallel request capacity.

#### Scenario: Cold launch and restored chat
- **WHEN** Workbench opens with a chat that remembers an unloaded model
- **THEN** no model starts until the person selects one or submits a turn, and that first turn loads then sends once ready.

#### Scenario: Failed load
- **WHEN** a pending model selection fails to load
- **THEN** the previous conversation binding and draft remain available and the failure names the attempted configuration.
