## Context

The current My models tab dedicates a full-height rail to installed models. Common settings are split between the primary form and technical details, and default descriptions repeat beneath controls. The existing `reasoning_preserve` startup key and backend frequency penalty already exist, but are not presented as requested. The adapter only replays reasoning after an explicit Keep value although the running Qwen template defaults to preservation.

## Goals / Non-Goals

- Give one selected model most of the page width, with a compact picker and two columns of directly accessible settings.
- Make inheritance, saved values and loaded differences clear without duplicate rows or reset buttons.
- Resolve thinking-history defaults once for the descriptor and adapter, with conservative behavior if unknown.
- Preserve existing configuration, setup resolution and safe reload boundaries.
- No new endpoint, alternate settings store or migration of model weights.

## Decisions

### Compact selection and drafts

Use a searchable picker in the My models header. Keep a per-model and per-configuration draft snapshot in the editor so switching does not discard unsaved work. The configuration identity remains the key; a draft is refreshed from the server only after explicit save or when first selected. Loaded state is a short status summary.

### Setting presentation

Keep runtime and memory settings in the left column and thinking and response settings in the right. A label includes a compact effective-default/source annotation; the control shows the requested value. Render loaded differences only when observed runtime state warrants them. The secondary details area holds specialist controls and diagnostics. Use existing preview/resolution endpoints so the display and execution share an authority.

### Thinking history

Derive support and default from inspected template or running server capability. For known Qwen `preserve_thinking` defaults and pinned llama.cpp behavior, report Keep. Explicit Keep and Drop map to `reasoning_preserve` true and false. The adapter resolves the same choice; if the default is unknown it does not replay older reasoning. This respects model-specific templates without applying web guidance as an implicit saved override.

## Risks / Trade-offs

- A template may expose a `preserve_thinking` variable without a recognizable default; the UI reports unverified and conservatively omits history until explicitly configured.
- Long model names and many controls require responsive wrapping and bounded scrolling. Keyboard interaction and narrow Windows widths are acceptance checks.
- A saved startup change remains distinct from the running engine until safe reload; an inline Loaded difference makes this visible.

## Migration Plan

Existing configurations retain their keys. Absent `reasoning_preserve` remains inherited, with its resolved default based on verified template/runtime facts. No product data or model files are moved.
