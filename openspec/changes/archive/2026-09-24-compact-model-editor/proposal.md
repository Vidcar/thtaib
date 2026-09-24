# Proposal

## Why

The installed-model list and repeated setting readouts crowd the Models workspace, making common per-model controls difficult to scan. Thinking-history defaults also differ between the displayed template and the inference adapter, so the editor needs one truthful resolution path.

## What Changes

- Replace the full-height library rail with a compact searchable model picker and a responsive two-column configuration editor.
- Put common runtime, thinking and response controls directly in view, with compact inline provenance, round binary switches and direct three-state inherited controls.
- Preserve unsaved drafts while switching models or configurations, and keep saved values distinct from loaded and observed values.
- Expose supported thinking-history control and frequency penalty; make the template-derived thinking-history default agree with the prompt sent to llama.cpp.
- Keep diagnostic and specialist controls in one secondary details area.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `models`: Compact model selection and per-model editing, honest inherited controls and thinking-history replay.

## Impact

The desktop Models editor, shared setting presentation, backend configuration descriptors and inference adapter change. Existing configuration, deployment and settings interfaces are reused; no new endpoint or product-data migration is required.
