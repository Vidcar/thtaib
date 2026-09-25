# Proposal

## Why

Model, agent, project and conversation setup currently overlap. A saved selection can appear ready while its model is unloaded or its Windows grant is gone, and switching a model can leave unnecessary llama.cpp processes running. The Chat entry point needs one understandable setup with the Deep Agents loop intact.

## What Changes

- Give model configurations, agent definitions, projects, conversation choices and app preferences separate owners. Show the resolved choice and readiness from the same backend facts used at dispatch.
- Replace managed per-model process selection with the pinned llama.cpp router's configuration presets and a positive maximum-loaded-model count: factory default one, Dave's initial setting two. Load on explicit model selection or first Send, never on application launch. Queue a busy one-slot switch; allow a different-model helper to hand off the slot and reload its parent.
- Make model and agent direct Chat controls; put capability groups in `+`, Ask/Full access beside the composer, and Plan in a removable pill. Show helper activity in an expandable rail. Keep project folder and knowledge separate from model and access choices.
- Preflight live capability grants, including selected or all Windows scope, before a turn. Keep incompatible choices disabled with reasons and show waiting/loading/failure without changing chats implicitly.
- **BREAKING:** discard obsolete overlapping setup records and incompatible development chats/projects/model configurations rather than maintain migration or compatibility paths. Preserve downloaded weights and external project files.
- Remove automatic model warming and hide unfinished Lab/Workflows from the primary navigation while retaining existing functions and Attention recovery.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `models`: managed router residency, count policy, exact configuration routing and no launch warm.
- `agents-workflows`: independent agent and conversation ownership, helper model handoff and child presentation.
- `backend-desktop`: direct Chat controls, safe selection and access readiness instead of mandatory swap confirmation.
- `environments-tools`: conversation capability groups and live Windows grant preflight.

## Impact

FastAPI model lifecycle, setup resolution and agent admission; Electron Chat and Models controls; generated shared contracts; local OpenSpec contracts and Windows validation. llama.cpp remains inference owner and Deep Agents remains the agent-loop owner.
