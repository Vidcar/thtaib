# Known deviations

Running code known to differ from intended design. Gaps that are simply unbuilt are `planned` or `built` rows in [the catalogue](catalog.json); undecided design is in [open questions](open-questions.md). A deviation keeps its requirement `built` until fixed and evidenced. Closing a deviation records the fix and its regression test; the entry stays for history.

Entry fields: ID and title; affected requirements; observed behaviour and inspected commit; intended behaviour (link); risk; disposition (fix / propose design change / approved temporary deviation with approval reference); tracking reference; resolution.

<a id="dev-001"></a>
## DEV-001: Diagnostic captures and case export bypassed the knowledge capture policy — closed

**Affected:** AGT-002, STATE-005, LAB-003. **Observed at** [`55e6c50`](https://github.com/Vidcar/thtaib/tree/55e6c50a7c419d28ee6915d6cf98f83c53a595d1): harness middleware persisted raw `model_requests` and HTTP payloads without the knowledge retention/redaction policy; `export_case` returned unchanged payloads behind a `secret_scan_clean` flag based on three literal strings. **Risk:** persisted diagnostics and exports could retain credentials. **Disposition:** fix. **Tracking:** [Issue #64](https://github.com/Vidcar/thtaib/issues/64). **Resolution:** diagnostic copies apply the capture policy before persistence and export sanitises or blocks; regression in `apps/backend/tests/test_privacy_diagnostics.py`. The detector remains pattern-based and incomplete.

<a id="dev-002"></a>
## DEV-002: Startup flag mapping invalid on the pinned llama.cpp; mmproj never passed — closed

**Affected:** MOD-003, MOD-004, MOD-005. **Observed at** [`d8973bb`](https://github.com/Vidcar/thtaib/tree/d8973bbc19e1909f9c3a5e894beb03aa5264badc) (technical assessment, 2026-09-19): `inference/settings.py` maps `mlock → --mlock` and `no_mmap → --no-mmap`; both flags were removed from llama.cpp before b11045 and replaced by `--load-mode {auto,none,mmap,mlock,mmap+mlock,dio}` (`error: invalid argument: --mlock` confirmed with the pinned Linux binary). `inference/deployments.py` builds the server argv as `[exe, -m, model, *startup]` and never passes a bundle's `mmproj` companion, so vision cannot work through the managed path. **Intended:** startup keys map to valid flags for the pinned runtime ([models behaviour](modules/models.md#behaviour)); companion files are passed to the server (MOD-001, MOD-005). **Risk:** any profile setting `mlock` or `no_mmap` fails to start; vision UAT with the preferred capability model cannot succeed. **Disposition:** fix. **Tracking:** [PR #81](https://github.com/Vidcar/thtaib/pull/81). **Resolution:** fixed at [`0d0c1d3`](https://github.com/Vidcar/thtaib/commit/0d0c1d3) — `load_mode` maps to `--load-mode`, `mlock`/`no_mmap` are retired keys reported as unsupported with a `retired` note, `--mmproj <path>` is passed for bundles with a projector companion, and `/props` is recorded as `server_props`; regressions in `apps/backend/tests/test_settings.py` and `apps/backend/tests/test_deployments.py`. Behaviour recorded in [models](modules/models.md#behaviour) and the [changelog](decisions/changelog.md).

<a id="dev-004"></a>
## DEV-004: Harness scratch files can land in the user's project — open

**Affected:** STATE-002, AGT-001. **Observed at** [`b519320`](https://github.com/Vidcar/thtaib/tree/b519320): `agents/harness.py` binds a bare Deep Agents `FilesystemBackend(root_dir=project, virtual_mode=True)`, so the framework's internal paths (`/large_tool_results/`, `/conversation_history/`) resolve inside the project folder; the real-model smoke has already observed the tiny model writing under `/large_tool_results/` in the project. **Intended:** harness-internal files never land in the project; route internal paths through Deep Agents' `CompositeBackend` (technical owner decision, 2026-09-19, [changelog](decisions/changelog.md); [agents and workflows](modules/agents-workflows.md#behaviour)). **Risk:** conversation-state files masquerade as project files, contradicting history ≠ project. **Disposition:** fix; the smoke tier's write task must be adjusted in the same change. **Resolution:** pending.

<a id="dev-005"></a>
## DEV-005: Desktop polls run state instead of streaming — open

**Affected:** API-004, AGT-001. **Observed at** [`b519320`](https://github.com/Vidcar/thtaib/tree/b519320): `ChatPanel.tsx`, `AgentRunPanel.tsx` and `LabPanel.tsx` poll the backend every 750 ms; no SSE or WebSocket path exists. **Intended:** harness progress streams to the desktop and a disconnected client is not evidence a run ended ([backend and desktop](modules/backend-desktop.md#behaviour)); the transport is chosen under [OQ-002](open-questions.md#oq-002). **Risk:** laggy or missed progress; visible state can lag persisted state. **Disposition:** fix once the transport is decided; polling is a stop-gap, not the design. **Resolution:** pending.

<a id="dev-003"></a>
## DEV-003: Chat refuses to start without a project folder — open

**Affected:** AGT-001, API-004. **Observed at** [`b9c89d8`](https://github.com/Vidcar/thtaib/tree/b9c89d81ddc84765152b57ae7a84aaaf16e95d5a): `chat/service.py` returns `project_required` (400) when a conversation has no project directory. **Intended:** Chat works without a project folder, with filesystem tools absent and reported as such (product owner decision, 2026-09-19; [agents and workflows](modules/agents-workflows.md#behaviour)). **Risk:** users cannot chat without first choosing a folder; low data risk. **Disposition:** fix in the next Chat change; the harness must build its tool set and Deep Agents backend from the optional project. **Resolution:** pending.
