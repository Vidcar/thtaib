# Tasks

## 1. Shared thinking-history behavior

- [x] 1.1 Add supported/default `reasoning_preserve` to configuration descriptors and verify known, unknown and unsupported template cases in backend tests.
- [x] 1.2 Make adapter reasoning replay use the same resolved default and explicit Keep/Drop; verify synthetic multi-turn rendering and Qwen template behavior.

## 2. Compact My models editor

- [x] 2.1 Replace full-height installed rail with searchable keyboard-accessible picker and compact loaded summary; verify long-name and selection behavior.
- [x] 2.2 Preserve drafts by model/configuration across switching with visible Unsaved state; verify edit-switch-return and save behavior.
- [x] 2.3 Arrange common Run & memory and Thinking & responses settings in responsive columns, with compact inline source, accessible switches and three-position inheritance; verify wide/narrow layouts and keyboard behavior.
- [x] 2.4 Expose supported thinking history, frequency penalty, cache precision and draft controls; consolidate specialist controls and diagnostics; verify saved payloads and applicability.

## 3. Validation and delivery

- [x] 3.1 Run desktop build, backend default and integration suites, shared-contract check if interfaces change, and strict OpenSpec validation; repair failures.
- [x] 3.2 Verify Windows app picker, saving, safe reload and thinking-history behavior with an isolated model setup; preserve everyday data.
- [ ] 3.3 Update Models OpenSpec contract and handover, deliver with Git and update established local app; verify final Git and app state.
