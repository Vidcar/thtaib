# Tasks: Complete the shared llama-server adapter

Before changing an existing path, run its relevant acceptance checks and retain passing behaviour. The implementation tasks below mean verify and complete only missing behaviour; do not rebuild a satisfied requirement. Keep the acceptance checks even when no code change is needed. Import-time source review is not execution evidence, so all tasks remain unchecked until their full scope is verified.

## 1. Verify existing behaviour and implement gaps

- [x] 1.1 Verify the selected endpoint/model, request settings and capture path in `inference/adapter.py`; extend only missing shared request schemas/allowlists and serialization for selected settings, actual model identity and validated current-user blocks.
- [x] 1.2 Complete sync/async normal and streamed message conversion, tool/result identities, reasoning and usage, with explicit client ownership.
- [x] 1.3 Add versioned output-schema selection through the existing agent constructor and policy-aware structured-output strategy/validation.
- [x] 1.4 Connect observed deployment capacity, output reservation and one upstream compaction path; preflight continuing conversations before model/configuration changes.
- [x] 1.5 Expose reusable context observations and setup-specific capability probes through existing compatibility records and diagnostics.

## 2. Verify

- [x] 2.1 Compare actual wire fields for sampling/output/reasoning controls; cover fragmented/multiple/invalid tool calls, tools-only messages and tool results.
- [x] 2.2 Test invoke/stream/ainvoke/astream parity, reasoning round trips, absent usage, malformed responses, cancellation, timeouts and interrupted partial streams.
- [x] 2.3 Test tools-off structured mode, native/tool strategies, schema-invalid versus schema-valid incorrect results and repair without repeated effects.
- [x] 2.4 Test low capacity and compaction requests, long-history model changes, preserved tool-result pairs and structured input rejecting arbitrary system/tool history injection.
- [x] 2.5 With suitable real setups, verify text streaming and a harmless tool round trip; verify advertised reasoning/structured/image capabilities separately. Mark unavailable suitable setups honestly, without turning unknown support into universal incompatibility.

Use the repository validation commands in `AGENTS.md`. Keep actual test outcomes and any blocker in this change/its PR; do not create another tracker. Required real checks stay incomplete when the necessary runtime, endpoint or Windows device is unavailable.

## Delivery verification — 2026-09-21

- Default backend: 315 passed. Integration backend: 142 passed, including actual local HTTP/process boundaries and adapter sync/async cases.
- Desktop build/typecheck, SSE terminal regression, model-setting boundary checks, generated-contract check and strict OpenSpec validation passed.
- Live Windows RTX 3090 / llama.cpp b11045 CUDA / Qwen3.8-27B UD IQ4 XS with recorded BF16 projector, 8192 context: streaming, harmless tool-result round trip, native JSON schema, tool schema, tool schema alongside executable tools, separate reasoning, supported reasoning replay and image fixture recognition passed independently.
- Live harness native tools-off schema, tool schema with available tools, continuation and upstream tools-off compaction passed. Compaction preserved a fixture fact, reducing estimated input from 5545 to 509 tokens. Live Chat returned validated answer 7; desktop inspector visually checked and its overflow fixed.
- Native schema combined with executable tools was inconclusive on this exact setup (runtime grammar rejection); auto strategy uses the separately verified tool-formatting combination. No universal incompatibility claimed. Context counts are disclosed estimates, not tokenizer measurements.
- Final review repairs cover cancellation checkpoint call/result pairing without executing tools, forbidden effects during formatting repair, stable schema identity, redacted diagnostics and async cleanup. Relevant regressions passed.
- Test model stopped and endpoint closure verified; rebuilt desktop and healthy backend restored to the ordinary product data root. Original weights preserved.
