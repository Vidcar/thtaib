---
name: diagnose-failure
description: Reproduce and diagnose bugs, failing checks, performance regressions or repeated unsuccessful fixes before changing code. Use evidence to distinguish defects from intended behaviour and test gaps.
---

# Diagnose failure

Read the relevant project instructions and existing checks. Reproduce the reported operation with isolated data where possible; retain the error, inputs and state needed to explain it without retaining secrets. If reproduction is unavailable, say what is unverified rather than presenting a hypothesis as a defect.

Separate confirmed defects, hypotheses, intentional behaviour and coverage gaps. Trace the earliest incorrect transition and seek evidence that could disprove the explanation. Distinguish requested, saved, accepted and applied state. An operation that succeeds followed by a failed refresh needs different handling from a failed operation; retrying the operation can duplicate effects.

Fix the smallest coherent cause. Prefer a regression that fails before the fix and proves the user outcome afterward. For recovery, assert progress or an actionable state, not just a surviving pending record. Challenge a passing test with the intended violation in an isolated fixture or disposable copy. Do not weaken assertions, wipe state, or add silent fallbacks to produce green output.

For performance work, compare equivalent before/after workloads and outputs. Reduced functionality, artificial limits and shifted work are not demonstrated optimisation. When repeated fixes fail, revisit the reproduction and causal model instead of piling on exceptions.

Return the evidence, cause, fix and remaining limits in the task or pull request; use the project's verification entry point for the affected scope.
