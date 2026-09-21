# Tasks: Complete the shared llama-server adapter

Before changing an existing path, run its relevant acceptance checks and retain passing behaviour. The implementation tasks below mean verify and complete only missing behaviour; do not rebuild a satisfied requirement. Keep the acceptance checks even when no code change is needed. Import-time source review is not execution evidence, so all tasks remain unchecked until their full scope is verified.

## 1. Verify existing behaviour and implement gaps

- [ ] 1.1 Verify the selected endpoint/model, request settings and capture path in `inference/adapter.py`; extend only missing shared request schemas/allowlists and serialization for selected settings, actual model identity and validated current-user blocks.
- [ ] 1.2 Complete sync/async normal and streamed message conversion, tool/result identities, reasoning and usage, with explicit client ownership.
- [ ] 1.3 Add versioned output-schema selection through the existing agent constructor and policy-aware structured-output strategy/validation.
- [ ] 1.4 Connect observed deployment capacity, output reservation and one upstream compaction path; preflight continuing conversations before model/configuration changes.
- [ ] 1.5 Expose reusable context observations and setup-specific capability probes through existing compatibility records and diagnostics.

## 2. Verify

- [ ] 2.1 Compare actual wire fields for sampling/output/reasoning controls; cover fragmented/multiple/invalid tool calls, tools-only messages and tool results.
- [ ] 2.2 Test invoke/stream/ainvoke/astream parity, reasoning round trips, absent usage, malformed responses, cancellation, timeouts and interrupted partial streams.
- [ ] 2.3 Test tools-off structured mode, native/tool strategies, schema-invalid versus schema-valid incorrect results and repair without repeated effects.
- [ ] 2.4 Test low capacity and compaction requests, long-history model changes, preserved tool-result pairs and structured input rejecting arbitrary system/tool history injection.
- [ ] 2.5 With suitable real setups, verify text streaming and a harmless tool round trip; verify advertised reasoning/structured/image capabilities separately. Mark unavailable suitable setups honestly, without turning unknown support into universal incompatibility.

Use the repository validation commands in `AGENTS.md`. Keep actual test outcomes and any blocker in this change/its PR; do not create another tracker. Required real checks stay incomplete when the necessary runtime, endpoint or Windows device is unavailable.
