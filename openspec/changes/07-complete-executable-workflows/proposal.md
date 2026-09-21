# Complete executable visual Workflows

## Why

The existing configuration/compiler boundaries must become real durable LangGraph execution, with typed outputs and a canvas that represents actual supported behaviour.

## What Changes

Complete versioned definitions and public inputs, per-node setup, nested agents, sequence/branch/parallel/join/loop/subworkflow patterns, explicit approvals and input nodes, direct actions, recovery and the existing visual editor.

## Capabilities

### Modified Capabilities

- `agents-workflows`: Extend the existing WF contracts into real executable typed graphs and everyday workflow use.

## Impact

Work order **07 of 08**. Changes 06 and `migrate-local-agent-interaction` must be implemented and verified first. React Flow remains the authoring/editor surface for serialisable application workflow definitions; the validated backend compiler and LangGraph execute them. Use the shared SDK boundary only to present scoped execution observations, never as the workflow editor, graph compiler or execution engine. SDK integration does not satisfy any workflow feature below. Reuse existing services and current contracts; an existing passing implementation satisfies a task without being rebuilt. The deltas specify the required end state, not a claim that every listed behaviour is absent.

## Non-goals

No second workflow engine, arbitrary code/expression execution from imported graphs, compulsory configuration-node clutter, speculative media placeholders or automatic scheduling/triggers.
