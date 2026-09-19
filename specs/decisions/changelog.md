# Decisions changelog

Dated record of design decisions that were too small for an ADR, in reverse chronological order. Each entry names its authority (a GitHub issue, an ADR or a recorded product-owner decision) and the requirements it touched. Current intended behaviour lives in [architecture](../architecture.md) and the module specifications; this file explains when and why it got that way. An entry here is history, not a second specification: if an entry and a specification disagree, fix the specification and say so here.

Add an entry when a merged change settles a default, a name, a scope boundary or a build-order choice. Move to an [ADR](README.md) when the change alters an execution owner, process boundary, public contract, persistence strategy, permission model or core dependency.

## 2026-09-19 — PR #85: Chat without a project; CompositeBackend scratch isolation

Authority: [PR #85](https://github.com/Vidcar/thtaib/pull/85); David, product owner (Chat without a project folder, Project chat 2026-09-19); technical owner decision (harness-internal files stay out of the project, 2026-09-19). Closes [DEV-003](../deviations.md#dev-003) and [DEV-004](../deviations.md#dev-004). Requirements: AGT-001, AGT-005, STATE-002, API-004.

- Chat create/start accept a missing project. The run's enabled list is visibility tools only (`echo`, `time_now`); `GET /v1/agent-tools` still returns the full catalogue. The Chat view reports `filesystem_tools_available` and conversation-scoped `enabled_tools`. Requesting a filesystem tool without a project is `filesystem_requires_project` (400). Desktop Start works with an empty path and does not invent a project.
- Live harness runs attach Deep Agents 0.7.15 `CompositeBackend(default=project or StateBackend, routes={"/large_tool_results/": …, "/conversation_history/": …}, artifacts_root="/")`. Internals persist under `{data_root}/state/harness/{thread_id}/`. Project file tools keep the `/` virtual root (not the live-docs `/workspace/` remount). Recorded-tool mode still attaches no live backend.
- Sources: [Deep Agents backends](https://docs.langchain.com/oss/python/deepagents/backends) (consulted 2026-09-19); installed `deepagents/backends/composite.py` and `deepagents/middleware/filesystem.py` at 0.7.15.
- Real-model smoke write task asks for exactly `/hello.txt`, presents only `write_file`, and asserts reserved directories are absent from the project. A project-less Chat turn is also exercised.

## 2026-09-19 — PR #82: real-model smoke tier

Authority: [PR #82](https://github.com/Vidcar/thtaib/pull/82) (merged `b519320`). Requirements: MOD-004, MOD-005, AGT-001, STATE-002. Partial OQ-010.

- `apps/backend/tests_integration/` (bound as `integration-tests`) starts a real `llama-server` from the product's pinned llama.cpp release (Linux x64 CPU asset, sha256-verified) with `Qwen/Qwen2.5-0.5B-Instruct-GGUF` `q4_k_m` at a pinned Hugging Face revision, then drives the product API in-process: connected attach and health, a Chat turn producing a real `write_file` into the project, a follow-up turn carrying the earlier tool call on the same thread, and a profile's per-request bag on the wire. Assertions are on API responses and recorded state, never model prose.
- Assets land under `.scratch/real-model-smoke/`; `WORKBENCH_REAL_MODEL_SMOKE=required` (set in CI) makes missing assets a failure rather than a skip. Workflow `real-model-smoke.yml` runs on every PR as `real-model-smoke (ubuntu-latest)` and is intended to join the required checks; adding it to branch protection is a maintainer action.
- The tier is the `ci-smoke` evidence tier of [verification](../verification.md): it may verify plumbing requirements only, never capability, managed inference or Windows behaviour.

## 2026-09-19 — PR #81: `--load-mode`, `--mmproj`, `/props`

Authority: [PR #81](https://github.com/Vidcar/thtaib/pull/81) (merged `0d0c1d3`); closes [DEV-002](../deviations.md#dev-002). Requirements: MOD-001, MOD-003, MOD-004, MOD-005. Partial OQ-007.

- `load_mode` is a valued startup key serialised `--load-mode auto|none|mmap|mlock|mmap+mlock|dio`. `mlock` and `no_mmap` are retired: never emitted, reported in the startup bag's `unsupported` list with a `retired` note naming the `load_mode` value; saved profiles are re-resolved from requested keys on deployment create and Chat resolve, so old profiles still start.
- A bundle with an `mmproj` companion starts with `--mmproj <path>` after `-m`; a missing projector is `bundle_file_missing`. Always-on as a technical decision (coordinating agent, 2026-09-19); the product owner may override.
- A healthy deployment's `GET /props` is recorded as `server_props` (build, alias, model path, slots, `n_ctx`, `modalities`, `chat_template`, `chat_template_caps`). Recorded data, not a capability claim.

## 2026-09-19 — Technical owner decisions (from the repository assessment)

Authority: technical owner decision, coordinating agent, 2026-09-19, from the repository assessment. These are design directions the assessment recommended and the technical owner adopted; they are not product owner decisions.

- **Harness-internal files stay out of the project.** The Deep Agents backend for a run must route the framework's internal paths (`/large_tool_results/`, `/conversation_history/`) outside the project folder, using the framework's `CompositeBackend`. Current code uses a bare `FilesystemBackend`; recorded as [DEV-004](../deviations.md#dev-004). Affects STATE-002, AGT-001.
- **Prefer `llama-server` `/props` over hand-maintained fixtures** for capability facts the pinned server reports (modalities, chat-template capabilities, slots, context). PR #81 records them as `server_props`; compatibility work builds on that before adding fixtures. Affects MOD-006, ARCH-004.
- **Persistence recommendation.** [OQ-017](../open-questions.md#oq-017) carries the recommendation to converge application records on SQLite; it is a recommendation with this authority, not a decision, and needs an ADR before implementation.

## 2026-09-19 — Product owner decisions (Project chat)

Authority: David, product owner, recorded in the Project chat on 2026-09-19. Each bullet states David's decision first; text after the em dash is the agents' design consequence.

- Return to the Revision 0.5 build order: prove managed inference on David-PC before building further features on the scaffold.
- Slim the specification and governance pack to something agents can specify from and build from ([ADR-0004](ADR-0004-slim-specification-pack.md)). This supersedes [ADR-0001](ADR-0001-adopt-specification-pack.md).
- Two-tier evidence model: real-model smoke in Linux CI (tiny GGUF on CPU llama-server) proves plumbing; David-PC capability UAT (Windows, NVIDIA 3090, Qwen3.8-27B UD-IQ4_XS) proves managed inference and model capability. `verified` requires one of these ([verification](../verification.md)).
- Blockers (software, tools, runtimes, models, MCP servers, credentials, permissions, services) are reported to David immediately in plain language: what is missing, why, what it unlocks, what he must do.
- **Chat must work without a project folder** (product owner decision, 2026-09-19, Project chat) — consequence: a conversation may have no bound project; filesystem tools are then absent and the surface says so; the current `project_required` refusal is [DEV-003](../deviations.md#dev-003). Affects AGT-001, STATE-002, API-004.
- **First worker environment is the Windows host shell with approvals, using Deep Agents `permissions=` / `interrupt_on=` and `LocalShellBackend`; WSL and Docker come later** (product owner decision, 2026-09-19, Project chat) — consequence: OQ-003 narrows to the approval flow and policy details. Affects ENV-001…003, ARCH-005.
- **Retrieval/RAG is in the first usable version if it can be delivered through LangChain's supported retrieval components with little custom code; David does not want strong LangChain features left unused** (product owner decision, 2026-09-19, Project chat) — consequence: a decision pending research, not yet a requirement; research the pinned LangChain retrieval components first, then specify under OQ-006.
- **Model Lab is purely for presenting data and charts to understand model behaviour; it never writes back into shared profiles and needs no one-click apply** (product owner decision, 2026-09-19, Project chat) — consequence: the Lab → profile "handoff" question is closed. Affects LAB-005, LAB-006, ARCH-003.

## 2026-09-19 — Issue #78: Chat deploy-health honesty

Authority: [Issue #78](https://github.com/Vidcar/thtaib/issues/78) (leftover from #56 / PR #69 UAT). Requirements: AGT-001, API-004.

- `GET`/`POST /v1/chat/conversations` include `deploy_health`. An unhealthy stored deployment reports `code=deploy_unhealthy`; a live adapter transport failure is rewritten to `code=deploy_unreachable` on the Chat view and on `current_run.error`.
- A failed live completion is `current_run.status=failed`; Chat never invents an assistant reply.
- Conversation ↔ `thread_id` ↔ run linkage from #56 is unchanged; Start records the thread even when the endpoint is down.

## 2026-09-19 — Issue #76: public repository and required checks

Authority: [Issue #76](https://github.com/Vidcar/thtaib/issues/76); supersedes the [Issue #36](https://github.com/Vidcar/thtaib/issues/36) private/advisory-only stance.

- The repository is public. Classic branch protection on `main` requires the eight status checks listed in [commands](../commands.md#ci) with strict tip. No GitHub Pro is needed or requested.

## 2026-09-19 — Issue #67: recorded-tool replay

Authority: [Issue #67](https://github.com/Vidcar/thtaib/issues/67) (tracking #58 finding 5). Requirement: LAB-003.

- Recorded-tool mode does not attach a live `FilesystemBackend`. Claimed tools replay from fixtures or the run fails as an unsupported/mismatched replay.
- A fixture matches the first unused capture with equal tool name and canonical arguments (sorted keys; `None` omitted; path-like values POSIX-normalised without a leading `/`). Missing, exhausted or mismatched fixtures fail with `recorded_fixture_missing` / `recorded_fixture_exhausted` / `recorded_fixture_arg_mismatch`; the run is `failed` and the Lab records a deviation.
- Matched `write_file` / `edit_file` fixtures may apply recorded bytes only inside the replay workspace, labelled as fixture application. Live-tool mode is unchanged: it still uses `FilesystemBackend` bound to project storage and stays labelled `live-tool`.

## 2026-09-19 — Issue #66: snapshot restore integrity

Authority: [Issue #66](https://github.com/Vidcar/thtaib/issues/66). Requirements: STATE-003, LAB-002. Partial OQ-005.

- Restore fails explicitly on a missing tree (`snapshot_tree_missing`), a missing recorded file (`snapshot_file_missing`), changed bytes (`snapshot_hash_mismatch`) or an unexpected tree file (`snapshot_unexpected_file`). An intentionally empty snapshot keeps an empty tree directory and may restore to an empty workspace.
- Restore stages into a new workspace, verifies it against the manifest, and registers the workspace only after that check. Failed or incomplete staging is discarded. The parent workspace is never overwritten.

## 2026-09-19 — Issue #65: starting snapshot

Authority: [Issue #65](https://github.com/Vidcar/thtaib/issues/65). Requirement: LAB-002.

- A `starting` snapshot is bound to the run before project mutation. Saving a completed run as a case reuses that snapshot rather than recapturing the post-task workspace. Kinds stay distinct: `starting`, `checkpoint` (not implemented), `final`.
- A run without a readable starting snapshot yields `starting_snapshot_unavailable`; current files are never presented as the original inputs. Later parent edits do not alter the saved starting snapshot; restore and rerun still write a new workspace.

## 2026-09-19 — Issue #64: diagnostic and export privacy

Authority: [Issue #64](https://github.com/Vidcar/thtaib/issues/64) (tracking #58 finding 6; closes [DEV-001](../deviations.md#dev-001)). Requirements: AGT-002, STATE-005, LAB-003.

- The Knowledge context-capture policy (`redaction_mode`, `retention_seconds`) applies to persisted `run.model_requests` including HTTP payloads before SQLite persistence. Discard leaves no raw copy in another field. Tool names, knowledge refs, capture gaps and timestamps are kept.
- Conversation transcripts, checkpoints and operational run events follow a separate operational retention policy and are not discarded by that setting.
- `export_case` sanitises detectable unsafe content in task text, tool fixtures and included files, or blocks the export. `secret_scan_clean` is true only when the original scan found nothing. The detector is pattern-based and incomplete; tests use synthetic credentials only.

## 2026-09-19 — Issue #62: managed deployment ownership

Authority: [Issue #62](https://github.com/Vidcar/thtaib/issues/62) (tracking #58 finding 2). Requirement: MOD-004. Partial OQ-007.

- Start, stop, health and reconcile for one managed deployment are serialised; a verified-owned live deployment is returned on duplicate start.
- A managed live record stores `process_identity` (`pid`, `create_time`, `executable`). Destructive stop verifies it first; a stale or reused PID is refused and the record cleared as unowned without killing the unmatched process. Legacy PID-only records are never killed.
- Ownership is not proven by HTTP health alone. A newly launched process that exits while another answers the endpoint is recorded `failed`, not healthy-owned. On restart, reconciliation re-adopts a still-matching process or clears ownership without terminating a mismatched PID. Connected endpoints keep a non-destructive lifecycle (detach only).

## 2026-09-19 — Issue #57: effective setup applied for real

Authority: [Issue #57](https://github.com/Vidcar/thtaib/issues/57), implementing the [Issue #53](https://github.com/Vidcar/thtaib/issues/53) contract. Requirements: ARCH-003, MOD-003, MOD-005, AGT-002, AGT-004, STATE-005.

- `HarnessService.start` resolves one `EffectiveSetup` before `create_deep_agent`; unknown profile or knowledge refs fail closed. Chat, Lab and Agent-run share that step.
- The adapter sends the resolved per-request bag; with no profile, the loaded deployment bag is used. Selected startup keys that differ from `deployment.applied_startup` are listed as startup mismatches, not applied to a running process.
- Selected knowledge versions are loaded from the application store and appended to the Deep Agents system prompt (not retrieval). `AgentRun.effective_setup` and `model_requests` show the same selected / loaded / applied facts; scripted calls report the capture gap. Chat does not write knowledge.

## 2026-09-19 — Issue #56: Chat continuity

Authority: [Issue #56](https://github.com/Vidcar/thtaib/issues/56), implementing the [Issue #52](https://github.com/Vidcar/thtaib/issues/52) mapping. Requirements: AGT-001, STATE-001, STATE-002. Partial OQ-004.

- One Chat conversation owns one LangGraph `thread_id`; each Start is a new `AgentRun` on that thread. Agent-run and Lab without a supplied thread use `thread_id = run.id`.
- `POST /v1/chat/conversations` allocates a new conversation and thread; project files and durable knowledge stay. Application records keep `conversation.id → thread_id → run_ids` so a later backend process continues the same thread.
- `PUT …/transcript` is display-only (`history_edit_effect=display_only`). A model/profile switch applies to the next run on the same thread (`model_switch_effect=same_thread_new_run`).

## 2026-09-19 — Issue #54: Model Lab is not Task cases

Authority: [Issue #54](https://github.com/Vidcar/thtaib/issues/54). Requirements: LAB-005, LAB-006.

- Model Lab is hardware-local trait/capability testing (speed, prefill/decode, MTP, quantisation, concurrency, needle, tool calling, vision; catalogue grows one family per issue). Task cases and replay is a separate delivery. Neither adds an evaluation agent loop. The trait catalogue now lives in [Lab](../modules/lab-evaluation.md#trait-catalogue).
- The "results may later inform profiles" handoff left open here was closed on 2026-09-19: Model Lab presents data and charts only and never writes back into profiles.

## 2026-09-19 — Issue #53: effective setup contract

Authority: [Issue #53](https://github.com/Vidcar/thtaib/issues/53). Requirement: ARCH-003.

- Recorded the shared contract now in [architecture](../architecture.md#effective-setup): resolve before run; three settings bags; selected ≠ loaded ≠ applied; harness and inspector agree; knowledge refs are loaded content, not RAG.

## 2026-09-19 — Issue #52: Chat continuity product mapping

Authority: [Issue #52](https://github.com/Vidcar/thtaib/issues/52). Requirements: AGT-001, AGT-004, STATE-001, STATE-002, API-004.

- Defined conversation / execution thread / run; continue versus fresh; history-edit and model-switch effects; inspector honesty (the inspector shows when displayed history and harness active context differ; missing linkage after restart is an explicit gap, never a silent new thread presented as the same conversation; a disconnected client is not evidence a run ended; progress is streamed). Now the behaviour section of [agents and workflows](../modules/agents-workflows.md#chat-continuity). Resume of the same thread after a model/adapter change stays open (OQ-004); until proven it must be an explicit new attempt.

## 2026-09-19 — Issue #44: Project Status versus Milestone

Authority: [Issue #44](https://github.com/Vidcar/thtaib/issues/44).

- Project Status is agent pipeline state only. Milestone names the plain-English delivery an issue belongs to (feature Milestones #3–#12); no due dates, sprints or velocity. Ship when acceptance criteria are met; acknowledged leftovers become focused follow-up issues (`Deferred: #N`). See [working rules](../README.md#issues-and-pull-requests).

## 2026-09-19 — Issue #42: cancel honesty

Authority: [Issue #42](https://github.com/Vidcar/thtaib/issues/42). Requirements: AGT-003, API-004, STATE-004, ENV-003. Partial OQ-004.

- Run statuses are the shared `RunLifecycleStatus`: `queued`, `running`, `cancel_requested`, `cancelled`, `completed`, `failed`. `POST /v1/agent-runs/{id}/cancel` (and Chat's cancel) moves a live run to `cancel_requested`; `finished_at` stays unset. Only the worker records `cancelled`, after it has stopped.
- `cancel_requested` is still live: quiescence checks and Lab capture fail (`not_quiescent`) until the run is `cancelled`, `completed` or `failed`. A cancel request is not acknowledgement of an in-flight external effect; recovery still reports `unknown` and does not replay. Worker-adapter interrupt (ENV-003) is not implemented by this.

## 2026-09-19 — Issue #41 / ADR-0002: shared contracts slice 1

Authority: [ADR-0002](ADR-0002-contract-authoring.md), [Issue #41](https://github.com/Vidcar/thtaib/issues/41). Requirement: CTT-001.

- Canonical Pydantic models under `apps/backend/src/workbench_backend/contracts`, exported through a dedicated schema app; OpenAPI and JSON Schema committed under `apps/backend/contracts/`; desktop types generated with pinned openapi-typescript 7.13.0. Slice 1 covers the `X-Workbench-Local-Token` envelope and run-lifecycle names only. Product `/openapi.json` stays unpublished.

## 2026-09-19 — Issue #40: same-machine trust

Authority: [Issue #40](https://github.com/Vidcar/thtaib/issues/40). Requirements: API-003, API-001. Partial OQ-002.

- Shared secret at `%LOCALAPPDATA%\LocalAIWorkbench\state\desktop_backend_shared_secret` (or the portable `state\` sibling), created on first use. Electron main injects `X-Workbench-Local-Token` on loopback requests; the renderer never holds it.
- Backend binds `127.0.0.1` only; non-loopback hosts are refused at start. Privileged `/v1` routes return 401 (missing token) or 403 (wrong token); `GET /health` stays public. CORS is not authorisation. Remote backend is unsupported.

## 2026-09-19 — Issue #35: WF-001 definition compiler

Authority: [Issue #35](https://github.com/Vidcar/thtaib/issues/35). Requirement: WF-001.

- The backend compiles a mixed definition: configuration connections resolve one Deep Agents setup; only workflow connections compile into sequencing. The output is a validated definition, not an executable graph; Builder is not shipped and WF-002 stays deferred.

## 2026-09-19 — Issue #31: compatibility provenance and the effects ledger

Authority: [Issue #31](https://github.com/Vidcar/thtaib/issues/31). Requirements: MOD-006, STATE-004. Partial OQ-004, OQ-007.

- Versioned `compatibility-record` documents under the bound `compatibility-records` directory carry requirements, capabilities/controls, recommendations, sources and validation evidence. `publisher_guidance`, `tested_adjustments` and `user_overrides` are separate lists; runtime user overrides live under `state\compatibility\`. Support status is `unverified` | `known_incompatible` | `tested`; an unfamiliar model assesses `unverified`, `usable=true`. Routes: `GET /v1/compatibility/records`, `POST /v1/compatibility/assess`, `GET /v1/bundles/{id}/compatibility`.
- Application-owned `external_effects` rows in `application.sqlite` with outcomes `dispatched`, `acknowledged`, `unknown`, `reconciled`, `failed`. Missing acknowledgement on recover/reconnect/restart reports `unknown` and never repeats the operation (`replayed` is always false). Rollback returns 409; `external_effect_rollback` is `not_supported` and `rollback_promise` is `none`; unresolved side-effect ids are preserved on snapshot capture and restore, and Lab snapshot/restore responses carry those honesty fields. Routes under `/v1/effects`.

## 2026-09-19 — Issue #29 / ADR-0003: Builder v1 chrome

Authority: [ADR-0003](ADR-0003-builder-v1-chrome.md) (draft), [Issue #29](https://github.com/Vidcar/thtaib/issues/29). Seven presentation locks recorded; Builder is not implemented.

## 2026-09-19 — Issue #27: two SQLite databases

Authority: [Issue #27](https://github.com/Vidcar/thtaib/issues/27). Requirements: STATE-001, STATE-002. Partial OQ-004.

- `%LOCALAPPDATA%\LocalAIWorkbench\application.sqlite` is the application system of record for runs, chat linkage, profile/deployment refs, checkpoint-id links and file refs. `checkpoints.sqlite` is the LangGraph checkpointer; the application never mutates its tables and links by checkpoint id only.
- Earlier JSON run/chat linkage under `state\` migrated into the application database; there is no dual write.

## 2026-09-19 — Issue #22: debug-quality Chat

Authority: [Issue #22](https://github.com/Vidcar/thtaib/issues/22). Requirements: AGT-001, STATE-002, ENV-001.

- Chat calls the embedded harness directly. Enabled tools: visibility (`echo`, `time_now`) and Deep Agents filesystem tools (`ls`, `read_file`, `write_file`, `edit_file`, `glob`, `grep`) bound to project storage; `execute`, `task` and `delete` excluded. Transcripts live in `application.sqlite` and are not the working project. This is not Chat polish and not Builder.

## 2026-09-19 — Issue #21: Windows CUDA pin and default GPU profile

Authority: [Issue #21](https://github.com/Vidcar/thtaib/issues/21). Requirements: MOD-003, MOD-004. Partial OQ-007.

- llama.cpp pinned at **b11045**; Windows NVIDIA assets `llama-b11045-bin-win-cuda-13.4-x64.zip` and `cudart-llama-bin-win-cuda-13.4-x64.zip` extracted into managed `runtimes\`. NVIDIA absent is a clear error, never a silent CPU fallback. PATH llama-server is unsupported. Non-Windows CUDA is not a day-one path.
- Default GPU profile: `ctx_size` 65536 (3090 / 24 GB), `n_gpu_layers: -1`, `flash_attn` as a valued enum serialised `--flash-attn on|off|auto` only. Desktop Start binds this profile; empty `startup: {}` is not the product default.
- `local_executable` pins the full runtime directory (executable plus CUDA DLLs). Pin while running is rejected or stops managed servers first. Prefer the CUDA flavour when NVIDIA is present.
- The `mlock → --mlock` / `no_mmap → --no-mmap` mapping locked here was wrong for b11045 ([DEV-002](../deviations.md#dev-002)); corrected by PR #81 above.

## 2026-09-19 — Issue #17: durable knowledge store

Authority: [Issue #17](https://github.com/Vidcar/thtaib/issues/17). Requirement: STATE-005. Partial OQ-006.

- Application-owned files under `%LOCALAPPDATA%\LocalAIWorkbench\knowledge\`. Versioned records: scope ∈ {user, agent, project}, kind ∈ {memory, skill, protected_instruction}, content, provenance, version id, parent version, timestamps. Append-only history; revert creates a new version.
- Optimistic concurrency on `base_version`; mismatch is `knowledge_conflict`. Protected instructions reject agent-origin writes; a human or API-maintainer path may edit them with provenance. Automatic agent writes need an explicit scope policy and carry provenance (actor, run id if any).
- Context-capture retention duration and redaction mode are local config: `redact_secrets` (default), retain plaintext, or discard. Backend API under `/v1/knowledge/` plus an optional thin debug panel. Knowledge version ids are referenceable from cases and harness setup. Not RAG.

## 2026-09-19 — Issue #15: Lab reuse and directory snapshots

Authority: [Issue #15](https://github.com/Vidcar/thtaib/issues/15). Requirements: LAB-001…004, STATE-003. Partial OQ-005.

- Snapshot is an application-owned directory copy of the allowlisted project workspace at a quiescent boundary (capture fails while tools or runs are writing), stored under `%LOCALAPPDATA%\LocalAIWorkbench\cases\` and `snapshots\`. Git commits are not snapshots. Restore goes into a new workspace with a linked branch run. Missing snapshots, external dependencies or permissions are reported, never replaced with convenient inputs.
- Included: allowlisted files, task, profile/deployment ids, dependency versions, knowledge version refs, tool fixtures, acceptance checks. Excluded: secrets, weights, `.scratch`, `.venv`, `node_modules`, credentials. No environment restore.
- llama-bench via the managed runtime when present, otherwise `unavailable`; scores are never invented. Task evaluation uses Inspect AI building blocks over the shared harness. Recorded-tool and live-tool modes are labelled.

## 2026-09-19 — Issue #12: embedded harness

Authority: [Issue #12](https://github.com/Vidcar/thtaib/issues/12). Requirements: AGT-001, AGT-002, AGT-005, AGT-006, MOD-005.

- Backend start / observe / cancel API (`/v1/agent-runs`) running one Deep Agents task through `create_deep_agent`, plus a thin Agent-run debug panel. Agent-run is not Chat.

## 2026-09-19 — Issue #3: managed inference

Authority: [Issue #3](https://github.com/Vidcar/thtaib/issues/3). Requirements: MOD-001…004.

- Failed or interrupted imports create no complete bundle or successful deployment. Connected attachments report `scope=connected` and reject start/stop/kill. PATH llama-server is unsupported.

## 2026-09-18 — Issue #1: Windows-first scaffold

Authority: [Issue #1](https://github.com/Vidcar/thtaib/issues/1). Resolves the layout part of OQ-001.

- `apps/backend/` (Python 3.12 via uv; package `workbench_backend`) and `apps/desktop/` (Electron + Vite + React + TypeScript + React Flow; Node ≥22 <25; pnpm); root `specs/`, `scripts/`, `tests/specs/`. electron-builder (NSIS) owns Windows packaging; `infra/docker-compose.yml` is a stub with no services.
