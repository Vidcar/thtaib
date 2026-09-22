# Proposal

## Why

Workbench's oversized controls, repeated headings, disclosure arrows and diagnostic prose obscure everyday tasks. Chat lifecycle/activity bugs and generic model settings further make an otherwise functional product difficult to trust and use.

## What Changes

- Redesign every existing desktop surface with compact typography, neutral light/dark themes, consistent icon actions, contextual help and resizable, collapsible panels inspired by Dave's supplied ChatGPT references.
- Remove repeated branding, notification headings and chevron disclosure affordances; retain keyboard access, focus indicators and actionable failures.
- Make archive immediately update history and expose concise permanent chat deletion that preserves project-created files.
- Present model reasoning before its answer and actual named tool calls, inputs, results and errors in execution order, without duplicate live/retained content.
- Persist reusable model inspection evidence with file-identity invalidation; expose supported model/runtime options, probes and applied settings, including discoverable speculative decoding and family-specific reasoning.
- Reproduce and repair adjacent defects encountered in these journeys, with focused regression checks and real Windows validation.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `backend-desktop`: Compact, responsive shared surfaces, intuitive conversation actions, ordered reasoning/tool presentation and effective-setting visibility.
- `models`: Durable inspection reuse, explicit refresh/probe and evidence-based model/runtime settings.
- `state-recovery`: Complete conversation-history deletion with project-output preservation and immediate client reconciliation.

## Impact

One existing React/Electron desktop and FastAPI backend. Reuses existing model, interaction, lifecycle, checkpoint and asset owners. Builds on the unmerged Packet 03 branch without claiming its outstanding human/native checks completed. No new product, execution engine, store authority or deployment destination.
