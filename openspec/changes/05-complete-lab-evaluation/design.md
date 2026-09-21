# Design: Complete exclusive Lab evaluation and configuration comparison

## Technical Approach

Extend the existing Lab services/panels and shared run, snapshot, profile and artifact records. Reserve execution for the Lab batch before changing deployments or spawning benchmark processes. Wait for existing unrelated work to finish, or obtain explicit cancellation and confirmed stop; do not seize its model. Block new unrelated Chat, Workflows and media while the reservation is active. Required human input and the batch's own work remain possible.

Require successful implementation and verification of `migrate-local-agent-interaction` before this change. Reuse its shared SDK run observation for live status/message/tool presentation. Lab remains the owner of Inspect orchestration, local case inputs and deterministic scorers, benchmark measurements, Lab reservations, evidence/sample/run linkage and durable result history. SDK presentation is not evaluation execution, a scorer, or proof of correctness.

Use an actual Inspect evaluation with a solver that awaits the shared Deep Agents driver. Explicitly bind the intended local setup; do not let Inspect pick another model from environment defaults or invoke a separate generate loop. Link Inspect samples/epochs/logs to application runs and adapter captures through supported APIs. Start with serial evaluation and verify the locked version's cancellation and logging APIs.

Restore immutable starting snapshots to owned test workspaces. Capture the source deployment's actual settings, not the latest mutable profile. A comparison override changes the next effective setup, with startup changes routed through the shared lifecycle. Recorded replay remains separate from live-tool tests and retains the existing strict fixture/no-live-fallback rules.

Run the installed llama-bench against inventoried weights and parse structured per-result/repetition output. Build a pin-aware benchmark mapping rather than forwarding server flags. Store evidence and unit-labelled timing/memory observations; only live task/model checks establish capability.

## Delivery boundary

This change includes reproducible load-test definitions and a real independent-session serial baseline. Change 06 implements the corresponding concurrent tests. Save the Chat → media → Chat measurement definition now; change 08 performs the real media/residency test. These later executions are not unchecked completion tasks for change 05. Missing optional selector or unsuitable MTP/reasoning/vision setups remain not applicable or untested, not fabricated results.

Keep trait measurements separate from task cases in the UI. Allow an explicit Use in Chat action to create/reuse a shared profile from a tested immutable snapshot with provenance; it must not modify an active deployment or silently rewrite an existing profile.

## Integration references

Use the checkout's locked versions; these are integration entry points, not permission to upgrade the stack.

- [Inspect solver integration](https://inspect.aisi.org.uk/solvers.html)
