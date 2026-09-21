# Tasks: Complete exclusive Lab evaluation and configuration comparison

Before changing an existing path, run its relevant acceptance checks and retain passing behaviour. The implementation tasks below mean verify and complete only missing behaviour; do not rebuild a satisfied requirement. Keep the acceptance checks even when no code change is needed. Import-time source review is not execution evidence, so all tasks remain unchecked until their full scope is verified.

## 1. Verify existing behaviour and implement gaps

- [ ] 1.1 Implement backend-owned exclusive Lab reservation, visible admission/wait reasons and release on confirmed completion/cancellation/recovery.
- [ ] 1.2 Verify existing `lab/service.py` capture/restore/rerun, starting-snapshot integrity, parent isolation and strict recorded replay; complete missing versioned editing and comparison overrides with immutable effective setup snapshots.
- [ ] 1.3 Integrate real Inspect evaluation around the existing shared async agent driver, including run/sample/epoch/log links and ordinary interrupts.
- [ ] 1.4 Add the six required outcome-based case families and deterministic scorers; preserve recorded replay as a separately labelled mode.
- [ ] 1.5 Verify the existing `lab/engine.py` runner and unavailable/failure handling; extend its parsing to required structured samples, supported setting mapping and defined end-to-end/timing/memory observations without replacing the runner.
- [ ] 1.6 Finish result history, expected-versus-actual/source views, side-by-side comparison, case lifecycle and deliberate tested-profile reuse.
- [ ] 1.7 Save independent-session and media-handover test definitions; run the real serial baseline now and leave their later execution to changes 06 and 08.

## 2. Verify

- [ ] 2.1 Test concurrent admission attempts, existing unrelated work, Lab-owned child work, interrupted approvals, cancellation/failure/restart and reservation release without falsely stopping external jobs.
- [ ] 2.2 Test capture before/after project changes, missing original snapshots, explicit empty tools, startup overrides, changed knowledge/settings and unchanged source-project fingerprints after terminal evaluation.
- [ ] 2.3 Run real Inspect evaluations through the local model for known-answer text, harmless tool execution, disposable file editing, document evidence, structured expected values and instruction retention through compaction. Inspect real logs and application links.
- [ ] 2.4 Test scorer revision history, incorrect/schema-valid-but-wrong/unassessable/error outcomes, fixture mismatch with no live fallback and secret-safe case export.
- [ ] 2.5 Run and parse a real managed llama-bench workload; verify repetition data, failed/invalid output, benchmark/server setting differences and labelled timing/memory boundaries.
- [ ] 2.6 Test deliberate Use in Chat against the tested snapshot and subsequent actual request, including later profile edits and unapplied startup differences. Render the changed Windows Lab views.

Use the repository validation commands in `AGENTS.md`. Keep actual test outcomes and any blocker in this change/its PR; do not create another tracker. Required real checks stay incomplete when the necessary runtime, endpoint or Windows device is unavailable.
