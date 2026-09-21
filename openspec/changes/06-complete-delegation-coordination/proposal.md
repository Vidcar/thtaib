# Complete local delegation and shared resource coordination

## Why

Native child agents and simultaneous sessions need correct per-invocation state, permissions and resource ownership; unloading a model must preserve the actual continuation.

## What Changes

Integrate awaited native delegation, child-specific setup/state/evidence, exact parallel interrupts, project and inference admission, explicit model-memory handover, run-tree recovery and the deferred Lab concurrency checks.

## Capabilities

### Modified Capabilities

- `agents-workflows`: Add real native child invocation, isolated loading state, event attribution and failure semantics.
- `backend-desktop`: Add shared admission, residency transitions and activity controls.
- `lab-evaluation`: Complete the previously defined serial-versus-concurrent checks.

## Impact

Work order **06 of 08**. Change 05 must be implemented and verified first. Reuse existing services and current contracts; an existing passing implementation satisfies a task without being rebuilt. The deltas specify the required end state, not a claim that every listed behaviour is absent.

## Non-goals

No remote agent service, replacement delegation loop, implicit child-count budget, blanket retry of mutating work or claim that child context isolation is a filesystem sandbox. Individual-child cancellation remains optional until native parent semantics are verified.
