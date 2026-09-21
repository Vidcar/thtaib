# Complete executable visual Workflows

## Why

The existing configuration/compiler boundaries must become real durable LangGraph execution, with typed outputs and a canvas that represents actual supported behaviour.

## What Changes

Complete versioned definitions and public inputs, per-node setup, nested agents, sequence/branch/parallel/join/loop/subworkflow patterns, explicit approvals and input nodes, direct actions, recovery and a React Flow workflow editor implemented within the existing desktop.

## Capabilities

### Modified Capabilities

- `agents-workflows`: Extend the existing WF contracts into real executable typed graphs and everyday workflow use.

## Impact

Work order **07 of 08**. Changes 06 and `migrate-local-agent-interaction` must be implemented and verified first. Implement a React Flow editor within the existing desktop as the authoring surface for serialisable application workflow definitions; the current desktop baseline is a single-task Agent run surface, not an existing React Flow editor. The validated backend compiler and LangGraph execute workflows. Use the shared SDK boundary only to present scoped execution observations, never as the workflow editor, graph compiler or execution engine. SDK integration does not satisfy any workflow feature below. Reuse existing services and current contracts; an existing passing implementation satisfies a task without being rebuilt. The deltas specify the required end state, not a claim that every listed behaviour is absent.

Before substantial editor implementation, obtain Dave's approval of the editor layout for create/save/reopen/run, node palette, canvas, inspectors, validation, run history and historical Agent run access. UX acceptance remains separate from technical verification and is currently pending, not accepted, until Dave accepts the built Workflows journey or explicitly defers review.

## Non-goals

No second workflow engine, arbitrary code/expression execution from imported graphs, compulsory configuration-node clutter, speculative media placeholders or automatic scheduling/triggers.
