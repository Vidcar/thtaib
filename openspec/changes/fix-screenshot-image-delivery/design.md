# Design

## Context

See proposal.md for the observed defects. The app owns capability evidence and screenshot retention; Deep Agents owns media filtering and LangGraph owns streaming. The pinned runtime is Deep Agents 0.7.19 with LangGraph 1.2.11. Probe model calls inherit the live tool's streaming callbacks, while the harness model's image profile is resolved only when the agent is compiled. Screenshot attachment reads newer evidence than that profile.

## Goals / Non-Goals

Keep capability resolution under the inference adapter, apply current evidence to the active request, and preserve upstream filtering and normal streaming. Avoid renderer-specific suppression, a replacement media middleware, or broad changes to capability probing, model lifecycle and stored chats.

## Decisions

- Mark owned capability-probe model invocations with the pinned LangGraph non-streaming tag. Apply isolation across ordinary, bound-tool, structured and streaming probes while keeping cleanup attached to the original owned model. Filtering test text in the renderer would leave misleading tool activity and retained replay behind.
- Reuse the adapter's capability-profile resolver for a narrow active-model refresh after screenshot preparation, before upstream unsupported-content filtering. Merge only image input/tool-image fields so agent context capacity and other model capabilities remain intact. Refresh the request's actual model; a parent model registry alone would miss helpers and alternate model factories.
- Keep the retained-asset route, current tool-batch attachment and complete tool-call pairing. A successful check permits actual screenshot bytes; a failed/inconclusive setup retains the existing text fallback. Do not rely on model answers to establish that pixels were sent.
- Regressions exercise installed LangGraph streaming and installed Deep Agents filtering, including a fresh untested setup, failed/inconclusive support, normal chat output, request overrides and exact capture identity. Live validation uses an isolated data root and the existing loaded model/weights.

## Risks / Trade-offs

- Probe bindings or callbacks can bypass superficial suppression: exercise the complete tool-image exchange and ordinary streaming on the installed event API.
- Refreshing an entire profile could reset the harness token budget: merge only image capability fields and assert unrelated profile/settings are retained.
- A colour-only live probe could prove test fixtures rather than screenshot delivery: inspect the actual outgoing screenshot reference/bytes and model response to distinct page details.

## Migration Plan

No data or schema migration. After local validation and delivery, restart the established backend only when its work is idle, preserving its loaded inference processes and model configuration. Historical displayed test fragments remain historical records; future screenshots must be clean. Rollback uses the previous backend code without changing retained images or model weights.
