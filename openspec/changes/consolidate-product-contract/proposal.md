# Proposal

## Why

This change originally consolidated older product plans. Its documentation sync and most everyday workspace work are delivered, but it still repeated completed work and the Lab design now replaced by `lab-workbench`. The surviving work is the visual Workflows system and configured image/speech integrations.

## What Changes

- Retain delivered compact destinations, archive/delete, native skill imports, retained-document reading, public web search, backend-held connection secrets, named helpers and safe explicit model selection.
- Finish Workflows with application-owned versioned definitions and validation, LangGraph sequencing and durable execution, and a React Flow editor that matches the running workflow.
- Add configured ComfyUI image generation and speech dictation/spoken replies to the existing Settings connection list and retained-media path.
- Make the main path compact and readable, with honest empty, progress, failure and unavailable states. Optional engines remain configured external integrations.
- Retire duplicate Lab work from this change. [lab-workbench](../archive/2026-09-30-lab-workbench/proposal.md) owns the replacement Lab plan; no llama-bench chart or exclusive Lab reservation is to be built here.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `agents-workflows`: visual Workflows and its placed, explicitly owned steps; existing named-helper guarantees remain intact.
- `environments-tools`: configured ComfyUI and speech, extending Settings Connections without leaking secrets or changing offline Chat.

Current `architecture`, `registry`, `backend-desktop` and `state-recovery` contracts constrain these implementations. Already-synced everyday-workspace deltas and the obsolete Lab delta have been retired from this active change rather than applied again over later deliveries.

## Impact

The original specification consolidation is complete; remaining tasks require backend and desktop implementation. Preserve one application, one registry boundary, LangGraph workflow ownership and the existing media store. No Lab implementation, shipped external engines, arbitrary-code graph execution, automatic schedules or voice cloning are added by this change.
