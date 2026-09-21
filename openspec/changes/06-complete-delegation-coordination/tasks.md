# Tasks: Complete local delegation and shared resource coordination

Prerequisites: change 05 and `migrate-local-agent-interaction` must be implemented and verified first. Use supported native namespace scope mapped to root/parent/child/call application identities and shared SDK scoped observation/interrupt presentation; do not treat a selector as authorization or completed delegation. All child execution, isolation, policy, admission and recovery work below remains required and unchecked. Before changing an existing path, run its relevant acceptance checks and retain passing behaviour. The implementation tasks below mean verify and complete only missing behaviour; do not rebuild a satisfied requirement. Keep the acceptance checks even when no code change is needed. Import-time source review is not execution evidence, so all tasks remain unchecked until their full scope is verified.

## 1. Verify existing behaviour and implement gaps

- [ ] 1.1 Wire authorised native task delegation to versioned child setups through the shared agent factory, including child middleware, permissions, knowledge/skills and the general-purpose fallback.
- [ ] 1.2 Implement unique invocation/state/scratch routing, root checkpoint linkage and per-call child event/capture attribution.
- [ ] 1.3 Route all parallel approvals and typed inputs by exact interrupt identity; preserve current policy on dispatch/resume.
- [ ] 1.4 Implement canonical project read-modify-write coordination, deployment dependency protection and per-model-call/hardware admission with cancellable waits.
- [ ] 1.5 Implement explicit residency policy and durable handover transitions, verified unload/restore, saved dependent results and endpoint rebinding on the same run/thread.
- [ ] 1.6 Complete run-tree cancellation/restart/failure handling and shared expandable activity/wait/ownership controls.
- [ ] 1.7 Run the Lab-owned independent-session and child-load comparisons defined in change 05.

## 2. Verify

- [ ] 2.1 Use a real local parent to await distinct native children with different model/request/tool/knowledge settings; verify returned results, immutable snapshots, namespaces and original task-call linkage.
- [ ] 2.2 Test tools-off/denied delegation, general-purpose fallback restrictions, changed grants, child-specific skill/memory routing, resumed scratch and concurrent capture attribution.
- [ ] 2.3 Test aliases to the same project, conflicting read-modify-write work, parent/child deadlock avoidance and independent workspace result conflicts.
- [ ] 2.4 Test multiple interrupts versus multiple actions inside one interrupt, stale/duplicate decisions, typed elicitation, changed policy and restart of paused children.
- [ ] 2.5 Test all model-call paths sharing admission, parent permit release, incompatible startup requests, cancellation during waits and no control claim over external clients.
- [ ] 2.6 Observe a real managed-model unload and exact restore around a controlled owned operation, then continue the same run with the saved result. Test each handover phase with cancellation/crash/failure fixtures and no repeated effect.
- [ ] 2.7 Test one failed child with independent successful siblings and blocked dependent work; verify root cancellation reaches owned work without cancelling unrelated clients.
- [ ] 2.8 Run controlled real serial/concurrent independent-session and child workloads under Lab ownership, recording correctness, queue/response/total time, throughput and available memory. Render the Windows child/activity views.

Use the repository validation commands in `AGENTS.md`. Keep actual test outcomes and any blocker in this change/its PR; do not create another tracker. Required real checks stay incomplete when the necessary runtime, endpoint or Windows device is unavailable.
