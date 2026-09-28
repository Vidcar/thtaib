# Proposal

## Why

Model settings currently resolve and render differently across setup, Chat and runtime preparation. Response choices can become loading identity, while the existing memory predictor omits selected components. One shared control contract should make model setup reliable and keep each control in its proper home.

## What Changes

- Models owns saved setups, recipes, budgets, sampling and hardware, with one primary Save; Chat keeps local Thinking and deliberate context reload only. Agents save without cross-page launch actions.
- Share typed domains, provenance, support and apply timing across the existing resolver and surfaces; remove invented Balanced/Deep presets.
- Reuse loaded native instances by artifact/runtime/loading identity independently of response recipes or saved setup IDs.
- Freeze authored settings and automatic-budget policy at acceptance, and record each role's applied allowance once at native binding.
- Add an ABI-pinned native no-allocation planner for target, projector and draft/MTP with honest component completeness and shared-pool context.
- Carry initial response selections and provenance through import retry/recovery; preserve downloaded weights and existing effective configurations.
- **BREAKING**: update specifications/tests that couple response settings to resident instances or require Chat to promote local tuning into saved setups.

## Capabilities

### New Capabilities

None; extend existing owners.

### Modified Capabilities

- `models`: shared controls, native planner, model/setup identity, import draft fidelity and local Chat tuning.
- `architecture`: immutable authored admission and once-recorded applied runtime budget facts.
- `backend-desktop`: compact control ownership, model/agent Save actions, Thinking and context reload presentation.

## Impact

Existing backend inference settings/services, accepted Chat/helper setup and model adapter/context guard; Electron/React Models, Chat, Agents and import controls; shared generated contracts. A small native companion links pinned llama.cpp APIs without replacing inference. No new agent loop, workflow engine, settings store, cloud publishing, or unrelated capability implementation.
