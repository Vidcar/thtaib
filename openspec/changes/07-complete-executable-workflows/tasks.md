# Tasks: Complete executable visual Workflows

Prerequisites: change 06 and `migrate-local-agent-interaction` must be implemented and verified first. React Flow authors definitions; validated backend/LangGraph executes them; shared SDK observation is presentation only. SDK integration does not complete any workflow feature below, and all tasks remain unchecked until their own scope is verified. Before changing an existing path, run its relevant acceptance checks and retain passing behaviour. The implementation tasks below mean verify and complete only missing behaviour; do not rebuild a satisfied requirement. Keep the acceptance checks even when no code change is needed. Import-time source review is not execution evidence, so all tasks remain unchecked until their full scope is verified.

## 1. Verify existing behaviour and implement gaps

- [ ] 1.1 Implement versioned serialisable workflow definitions, public input forms, immutable run snapshots and dependency-safe create/open/save/rename/duplicate/import/export/delete.
- [ ] 1.2 Verify configuration-versus-execution separation in `agents/definition_compiler.py` and its existing tests; extend backend validation and the registry-driven compiler for per-node effective setup, stable typed ports, cardinality, mappings and required paths. Compiler metadata alone does not satisfy executable graph acceptance.
- [ ] 1.3 Execute ordinary and structured-output agent nodes as awaited configured nested Deep Agents with private invocation state and shared recovery.
- [ ] 1.4 Implement real sequence, exclusive branch, parallel region/join, explicit approval, typed user input, field selection, text formatting, direct integration, declared loop and reusable-workflow nodes.
- [ ] 1.5 Implement root/node/iteration/attempt events, exact typed interruption routing, compatible restart, partial failures, cancellation and external-effect reconciliation.
- [ ] 1.6 Apply shared project/model/residency admission and Lab exclusivity across every node and nested child.
- [ ] 1.7 Finish the existing React Flow editor, labelled ports, setup/input/output inspectors, validation focus, editor undo/redo, keyboard controls, unsaved handling and actual run history.

## 2. Verify

- [ ] 2.1 Test import/export preserving interfaces/mappings/layout without credentials/code/autorun, invalid or missing dependencies, frozen revisions and explicit empty tool selections.
- [ ] 2.2 Run real local agent sequence and structured-result handover; verify actual request settings, validated values and private sibling/nested context rather than returned job IDs.
- [ ] 2.3 Exercise exclusive branches and parallel joins with unequal path lengths, unselected branches, staggered arrivals, conflicting merges and a failed required branch; verify one correctly scoped join activation.
- [ ] 2.4 Exercise zero/one/multiple loop iterations and repeated nested workflow calls with frozen versions and independent state; reject undeclared cycles and unsupported recursive definitions.
- [ ] 2.5 Test simultaneous authored approvals, agent-tool approvals and typed input across restart, stale/duplicate resumes, policy changes and explicit gates unaffected by Always allow tool grants.
- [ ] 2.6 Test independent branch completion after failure, no blanket mutating retry, cancellation during waits/effects/handover and uncertain effects without duplicate dispatch.
- [ ] 2.7 Run concurrent ordinary Chat/Workflow work through shared admission, then verify unrelated workflows cannot start during Lab exclusivity.
- [ ] 2.8 On Windows, create/save/reopen/edit/run a workflow, inspect actual node inputs/outputs/iterations, use keyboard and undo/redo, and verify old Agent run history remains reachable. Mock canvas success is insufficient.

Use the repository validation commands in `AGENTS.md`. Keep actual test outcomes and any blocker in this change/its PR; do not create another tracker. Required real checks stay incomplete when the necessary runtime, endpoint or Windows device is unavailable.
