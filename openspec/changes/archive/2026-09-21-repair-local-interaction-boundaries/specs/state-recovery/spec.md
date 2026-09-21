## MODIFIED Requirements

### Requirement: STATE-002 - Do not confuse history with the working project

The backend SHALL own thread identities, checkpoint namespaces and displayed history. The readable archive MAY retain more history than compacted runtime context. Hydration SHALL preserve that history while identifying the checkpoint as execution authority. Deep Agents file tools SHALL target project storage; conversation-state and harness internal paths MUST NOT substitute for the working project. Editing or clearing displayed history MUST NOT restore, delete, fork or reset project files or execution state.

Legacy history without IDs SHALL preserve chronological order and repeated-message multiplicity. Runtime identity SHALL use durable identity/provenance or reliable ordered alignment, never an earlier equal-text match alone. Ambiguous records SHALL retain deterministic display-only identity and the original readable archive. Content blocks, reasoning and checkpoint tool calls/results SHALL retain their meaningful ordering relative to confidently matched turns.

#### Scenario: History edit

- WHEN displayed history is changed after a project-bound file-writing turn
- THEN project files MUST remain unchanged by that display edit
- AND harness-internal paths MUST NOT appear in the project or be reconstructed from edited display history.

#### Scenario: Existing compacted conversation

- WHEN a pre-migration conversation is reopened after its runtime context was compacted
- THEN its full retained readable history, project/settings references and checkpoint association MUST survive
- AND continuation MUST use the existing checkpoint rather than replaying the archive.

#### Scenario: Repeated text with compacted suffix

- WHEN an ID-less transcript contains repeated user or assistant text and execution retains only a suffix
- THEN registration and repeated reopening MUST preserve exact readable chronology and multiplicity
- AND stable established identities, content blocks, reasoning and tool outcomes MUST survive without duplicate outcomes or a model/tool invocation.

### Requirement: STATE-015 - Recover interaction projections without replaying effects

Interaction hydration and replay SHALL provide an atomic cutover to live events with stable identities and bounded transient buffering. Thread-level cursors SHALL remain distinct from run-local native sequences. Unavailable or expired replay positions SHALL trigger explicit resynchronization from durable application records. Restart recovery SHALL preserve real partial output and actual tool outcomes; uncertain effects MUST remain unknown and MUST NOT be repeated to repair presentation. Any required application-record migration SHALL be recoverable, idempotent and verified on isolated copies before cutover.

Already-registered faulty legacy projections SHALL be repaired narrowly and idempotently from original readable history and available durable provenance. Repair SHALL preserve subsequent turns, partial output, tool history, explicit display-only edits and replay cutovers. It SHALL NOT blindly reseed all bindings, restore deliberately hidden messages, reset runtime threads, mutate private checkpoint tables or claim uncertain reconstruction is exact.

#### Scenario: Gap and backend restart

- WHEN an observer reconnects after a replay gap or backend restart
- THEN it MUST receive controlled resynchronization and truthful persisted outcome or uncertainty
- AND neither resubscription nor hydration MUST execute a tool or create another run.

#### Scenario: Existing faulty archive and later edits

- WHEN a provably affected persisted projection is reopened after subsequent output or a display-only edit
- THEN safe repair MUST preserve later content and hidden-message/cutover semantics and be idempotent on repeat
- AND project files and checkpoint association MUST remain unchanged, with continuation on the existing runtime thread and no additional model/tool invocation from repair.
