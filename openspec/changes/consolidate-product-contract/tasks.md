# Tasks

Reviewed 2026-09-27 against source and existing acceptance checks. The original contract sync is complete. Lab's former tasks were superseded and their replacement is delivered: [lab-workbench](../archive/2026-09-30-lab-workbench/tasks.md) records that completed delivery. Detailed workflow layout/UX acceptance remains governed by API-020.

## 1. Delivered everyday workspace

- [x] 1.1 Retain compact destination controls; verified by the archived polish delivery and current desktop checks.
- [x] 1.2 Retain immediate archive and confirmed chat deletion without deleting project files; verified by existing chat/asset-lifecycle checks.
- [x] 1.3 Import native skill files/folders/archives without execution and read supported documents with explicit encrypted-PDF rejection; verified by `test_skill_packages` and `test_retained_assets`.
- [x] 1.4 Provide current MCP/public-web Connections and backend-held credentials without blocking offline Chat; verified by `test_connections`. ComfyUI/speech additions remain in section 3.
- [x] 1.5 Retain opt-in named helpers and safe selected-model loading under current AGT-019/API-028, with named child activity and protected stop/unload; verified by their archived deliveries and existing helper/model controls.

## 2. Workflows

- [ ] 2.1 Extend existing registry/definition boundaries with versioned per-step inputs/outputs, configuration and workflow links, effective setup and run-start validation; verify representative definitions share one authority and incompatible, missing or arbitrary-code steps fail without dispatch.
- [ ] 2.2 Execute supported sequence, branch, parallel/join, repeat, named agent/workflow, person-input and registered direct-action steps through LangGraph with durable run hierarchy, approvals, cancellation and recovery; verify real graphs preserve per-step setup, explicit cycle ownership and no duplicate effects across interruption/restart.
- [ ] 2.3 Build the React Flow palette, canvas, inspector, invalid-step reasons, Run and history after the API-020 layout approval; verify placed steps match actual backend order, graders run only when placed, and the built Windows view handles empty, waiting, failure and recovery states.

## 3. Media integrations

- [ ] 3.1 Extend Settings Connections for a saved ComfyUI address/workflow and call it from the composer using the existing retained-media records and shared creative-job adapter; verify live composer, agent-tool and LangGraph-node paths share job ownership, progress, cancellation and artifacts, alongside reply/library images, backend-only credentials, failure and absent-service text Chat.
- [ ] 3.2 Extend Settings Connections for saved speech address/model/voice and add dictation and Speak; verify a live configured service leaves dictated text unsent, speaks only the selected finished answer, labels a non-local address and never sends audio to an unsaved address.

## 4. Delivery checks

- [ ] 4.1 Run affected backend default/integration checks, shared-contract freshness, desktop build and `openspec validate --all`; verify actual workflow and configured media journeys in the built Windows product and record technical results separately from Dave UX acceptance before archive.
