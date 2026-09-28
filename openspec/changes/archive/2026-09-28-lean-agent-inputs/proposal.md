# Proposal

## Why

The audited agent request spends most of its instruction/schema text on tools it may never use, with additional duplicated guidance. Users cannot inspect all input sources or reliably exclude inherited content, and an unavailable optional feature can block ordinary chat.

## What Changes

- Default new accepted inputs to on-demand tools and reference material; retain explicit pins and Always include choices.
- Compact automatic instructions and schema descriptions through the existing Deep Agents/LangChain middleware, without rewriting authored text or changing execution validation.
- Provide one shared What the agent sees panel for previews, source edits/exclusions, chat-local instruction replacement, Save to agent and actual request inspection.
- Add declared skill requirements and focused native setup interruptions when an optional feature is needed.
- Freeze disclosure policy and selected versions at admission; enforce existing permissions for deferred tools and preserve accepted historical runs.
- **BREAKING**: newly accepted selected memories default to metadata-first availability instead of unconditional full-text injection; Always include preserves full native memory loading.

## Capabilities

### New Capabilities

None; extend existing owners.

### Modified Capabilities

- `agents-workflows`: progressive context, explicit source control, request inspection, compact middleware and skill requirements.
- `environments-tools`: deferred tool readiness/discovery and unchanged backend-enforced access.
- `architecture`: one frozen effective input policy with optional setup resolved when needed.
- `models`: inspect, edit and explicitly reset optional saved model guidance without mixing it into model execution settings.

## Impact

Backend setup/readiness/run schemas, shared generated contracts, knowledge version metadata, Deep Agents middleware and request capture; existing Chat, Agents, Knowledge, Models and setup UI. Deep Agents, LangGraph, LangChain and llama.cpp remain execution owners. No new runtime, durable store, model selector call or sidebar destination.
