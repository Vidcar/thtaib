# Known deviations

Running code known to differ from intended design. Gaps that are simply unbuilt are `planned` or `built` rows in [the catalogue](catalog.json); undecided design is in [open questions](open-questions.md). The catalogue records the affected implementation status. Closed records below retain links to the fix and regression evidence; current behavior lives in the owning contract.

<a id="dev-006"></a>
## DEV-006: Product reset gaps after guided model setup slice - open

**Affected:** MOD-001, MOD-003, MOD-006, AGT-003/004/005, WF-001, LAB-001. **Baseline:** `fa9e64f622d38c00cb3ddbacf829afde21986ec3`; reconciled by the 2026-09-20 product reset.

Guided repository/variant selection, immutable revision capture, bundle integrity, pin-aware startup controls and official planning are implemented in this slice. They do not complete the broader acceptance clauses:

- Automatic compatibility-aware companion selection, hardware estimates, download progress/cancellation and publisher recommendation extraction remain unfinished. Filename candidates are not verified projector compatibility.
- Shared structured capability probes and persisted feature opt-outs are absent. Compatibility records and `/props` are observations, not tool/vision round-trip evidence. Context/reasoning changes near Chat with explicit managed reload impact remain unfinished; the new controls configure managed startup from Models only.
- Live `/memories/**` edits remain scratch-local; official memory/skills loading exists, but write-through into Knowledge versions does not. The existing capture gaps identify this limitation.
- `write_todos` uses official upstream middleware. Delegation through `task` remains disabled pending explicit child setup/policy/capture wiring and denied-access evidence. User budgets are optional, but continuation past the measured framework recursion boundary is not implemented; failure must not be called budget-free unlimited execution.
- The definition compiler still resolves a global setup and rejects cycles. Intended per-owning-agent inheritance, typed workflow execution and LangGraph-owned cycles are not delivered by this compiler or its current tests.
- The fixed 16-token prefill / 8-token decode benchmark does not propagate the selected profile settings and is not a context-performance comparison. It remains plumbing; deeper runs must coordinate model loads through lifecycle management.

**Disposition:** retain the intended requirements and deliver the gaps through the single [next path](../docs/delivery-feature-map.md#next-path), tracked with [#37](https://github.com/Vidcar/thtaib/issues/37). Do not inflate catalogue verification or reinterpret these gaps as permanent capability exclusions. Close this entry only as its remaining gaps acquire implementation and appropriate evidence.

<a id="dev-001"></a>
## DEV-001: Diagnostic capture/export privacy — closed

**Affected:** AGT-002, STATE-005, LAB-003. Raw diagnostic persistence and incomplete export scanning were observed at [55e6c50](https://github.com/Vidcar/thtaib/tree/55e6c50a7c419d28ee6915d6cf98f83c53a595d1), fixed under [#64](https://github.com/Vidcar/thtaib/issues/64). [Capture policy](modules/state-recovery.md#state-005) now applies before persistence/export; pattern-based detection remains incomplete. Regression: [test_privacy_diagnostics.py](../apps/backend/tests/test_privacy_diagnostics.py).

<a id="dev-002"></a>
## DEV-002: Pinned runtime flags and projector arguments — closed

**Affected:** MOD-003, MOD-004, MOD-005. At [d8973bb](https://github.com/Vidcar/thtaib/tree/d8973bbc19e1909f9c3a5e894beb03aa5264badc), b11045 rejected `--mlock` and managed startup omitted projectors. [PR #81](https://github.com/Vidcar/thtaib/pull/81), [0d0c1d3](https://github.com/Vidcar/thtaib/commit/0d0c1d3) corrected `--load-mode`, `--mmproj` and `/props` handling under [models](modules/models.md#behaviour). Regressions: [settings](../apps/backend/tests/test_settings.py), [deployments](../apps/backend/tests/test_deployments.py).

<a id="dev-004"></a>
## DEV-004: Harness scratch leaked into project files — closed

**Affected:** STATE-002, AGT-001. Observed at [b519320](https://github.com/Vidcar/thtaib/tree/b519320), fixed at [be39ff7](https://github.com/Vidcar/thtaib/commit/be39ff70a02b64746813b3c4506ee860fe2c890f) with [CompositeBackend routing](modules/agents-workflows.md#behaviour). Regressions: [Chat](../apps/backend/tests/test_chat.py), [harness backend](../apps/backend/tests/test_harness_backend.py), [real-model smoke](../apps/backend/tests_integration/test_real_model_smoke.py) checks that reserved directories are absent from the project.

<a id="dev-005"></a>
## DEV-005: Desktop polled instead of streaming — closed

**Affected:** API-004, API-006, AGT-001. Polling observed at [b519320](https://github.com/Vidcar/thtaib/tree/b519320) was replaced by [SSE with reconnect snapshots](modules/backend-desktop.md#api-006). Lab result polling is separate from run events. Regression: [test_event_stream.py](../apps/backend/tests/test_event_stream.py).

<a id="dev-003"></a>
## DEV-003: Chat required a project folder — closed

**Affected:** AGT-001, API-004. Observed at [b9c89d8](https://github.com/Vidcar/thtaib/tree/b9c89d81ddc84765152b57ae7a84aaaf16e95d5a), fixed at [be39ff7](https://github.com/Vidcar/thtaib/commit/be39ff70a02b64746813b3c4506ee860fe2c890f). [Project-free Chat](modules/agents-workflows.md#behaviour) keeps project tools unavailable and never invents a project. Regressions: [Chat](../apps/backend/tests/test_chat.py), [harness](../apps/backend/tests/test_harness.py).
