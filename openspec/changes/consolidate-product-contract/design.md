# Design

## Context

The surviving contracts were synced previously. Everyday workspace, native skills/document reading, current Connections/public web and named helpers are implemented. The existing Agent run panel is a task runner; typed definition checks are not a full visual workflow runtime or versioned registry. There is no React Flow dependency or ComfyUI/speech connection kind yet.

## Goals / Non-Goals

Deliver the remaining workflow and media contracts using the existing backend and desktop. Retain accepted behaviour and newer Chat/model contracts. Lab is owned only by [lab-workbench](../lab-workbench/design.md). This change does not build the older llama-bench views/reservation, another execution engine/store, bundled media engines, schedules or voice cloning.

## Decisions

### Workflows are more than a canvas

Use the current configuration compiler as a starting point, without assuming its one resolved setup and cycle rejection satisfy per-step ownership or authored repeat. The application owns versioned definitions, typed configuration/workflow/data links, effective setup, validation, permissions and run attribution under `registry` and `agents-workflows`. LangGraph owns sequence, branch, parallel/join, repeat, agent/workflow invocation and durable interrupts. Deep Agents owns each agent step's model/tool loop. Exactly one owner controls a review cycle.

React Flow presents a palette, canvas and selected-step inspector. Invalid steps show their reason before Run; history sits above the canvas. A placed grader is an explicit agent/workflow step. Imported arbitrary code is rejected. Use shared setup controls, named activity and existing approval/question cards. Retain API-020's approved detailed layout and separate technical versus Dave UX acceptance.

### Media extends Connections

Add ComfyUI and speech kinds to the existing Settings connection list; MCP and public web do not need rebuilding. Keep credential values backend-only and write-only in the desktop. Disconnect preserves chats and past results. New media connection removal remains explicit and confirms the effect.

Image generation calls a saved ComfyUI address and existing workflow, showing progress and retaining the returned image in the reply/library. It does not install ComfyUI or its nodes. Dictation and Speak use a saved OpenAI-compatible speech address, model and voice. Label non-local addresses before use; never send audio to an unsaved destination. Dictation leaves editable text unsent; Speak plays one finished answer. Engine names in ENV-024 are examples, not bundled products.

### Keep delivered work and later extensions coherent

Named helpers remain opt-in under the current conversation authority. Current API-028 uses explicit safe model selection without a second confirmation; stop/unload protects active work. No older confirmation-only model-swap delta may overwrite it. Imported skills never execute scripts. Accepted documents retain parser outcomes; encrypted/malformed uploads may be explicitly rejected before retention. Later features extend the existing workflow, Lab or media boundaries rather than creating a parallel product.

## Risks / Trade-offs

- A frontend-only canvas would claim execution the backend cannot perform; validate and run real LangGraph steps before declaring it delivered.
- A registry rewrite could duplicate current catalogues; extend existing definition/tool/configuration owners and prove one authority across consumers.
- Missing media services must produce an unavailable/failure state without breaking text Chat or inventing output.

## Migration Plan

The original old-plan consolidation and sync are complete. Implement the remaining tasks, preserve current main-spec scenarios during archive, and leave Lab's change independent. Keep any new durable records in the existing application database and use the established migration/recovery contract.

## Open Questions

None. API-020 still requires an approved detailed workflow layout before substantial interface implementation; this documentation review does not provide that visual acceptance.
