# Glossary

Use these locked terms in issues, pull requests, and user-facing copy.

| Wrong / loose | Locked |
| --- | --- |
| thtaib / the app (product name) | Local AI Workbench |
| just add the folders | Windows-first scaffold (OQ-001) |
| make it run AI | Out of scope this milestone |
| host Vite / second server | One FastAPI backend + one Electron desktop |
| local verification host | Where UAT runs (David-PC) — not a second product mode |
| scratch / temp at repo root | Scratch workspace (`.scratch/`, gitignored) |
| uat-workroot at repo root | UAT workroot under `.scratch/uat/` |
| product data at repo root | Product data under `%LOCALAPPDATA%\LocalAIWorkbench\` |
| make it run a model / wire llama | Managed inference (MOD-001…004) |
| the model in Chat | Model bundle / running deployment |
| kill the remote server | Connected endpoint — no destructive lifecycle |
| compatibility means supported | Unverified ≠ incompatible |
| PATH llama | Unsupported fallback; managed runtime is the supported path |
| use 0.5B for agent UAT | Preferred capability UAT model (Qwen3.8-27B UD-IQ4_XS) |
| copy GGUF into workroot | Reuse managed Model bundle (reference/link; no scratch copy) |
| check in weights | Never commit GGUF/mmproj/weights |
| add memory / RAG | Durable knowledge versioning (STATE-005) |
| add RAG | OQ-006 unresolved (surface vs shared) |
| agent memory DB | Application-owned knowledge store under LocalAppData |
| last write wins | Optimistic concurrency / explicit conflict |
| close OQ-006 | Partial OQ-006 defaults only (store; not RAG / cross-surface sharing) |
| Chat memory UI | Out of scope |
| Chat shipped / Chat tab done | Debug-quality Chat (Issue #22); not polish |
| Agent-run is Chat | Agent-run debug panel is not Chat |
| CUDA 13.4 / GPU default / valued flash_attn landed | partial OQ-007 landed on #21; remainder open |
| bare --flash-attn is the mapping | valued `--flash-attn on` / `off` / `auto` only (#21) |
| MCP is the bus | open — default tool bus vs optional (OQ-009 / OQ-003) |
| Approvals = LangGraph interrupt | OQ-011 — durable product Approvals inbox ≠ framework interrupt |
| LangSmith for observability | OQ-012 — run observability outside Lab (local; LangSmith not home) |
| just wire remote OpenAI | OQ-013 — multi-model / hybrid routing (model manager owns) |
| Inspect is the whole Lab UX | OQ-014 — evaluation UX beyond Inspect |
| import a workflow runtime | OQ-015 — definition import/export (not multi-runtime) |
| second isolation question | OQ-003 — worker sandbox isolation |
| registry means plugins exist | OQ-008 — skills/plugins discovery UX unresolved |
| ship voice now | OQ-009 — voice/multimodal stay optional/experimental |
| CDF fork | out of scope |
| TooGraph as pixel target / fork | OQ-016 — TooGraph inspiration only (ADR-0003); original layout |
| invent Builder chrome | OQ-016 v1 chrome locked (ADR-0003); implementation remainder |
| custom desktop auth header | `X-Workbench-Local-Token` (ADR-0002 / Issues #40 and #41) |
| cancel means requested | `cancel_requested` is still live; `cancelled` is confirmed stop |
| Builder shipped | unfinished Builder surface (OQ-016 remainder) |
| canvas config edge | node badge/popover for config (WF-001 unchanged) |
| hidden per-node profile | inherit workflow profile; explicit override only (ARCH-003 unchanged) |
| Chat agent / Builder agent graph | embedded harness + MOD-005 (not Chat or Builder) |
| complete real agent work | harness + MOD-005 against managed inference |
| second agent loop | Deep Agents owns the loop; application owns config/lifecycle |
| Lab agent | Lab reuse against shared harness |
| git snapshot | application directory snapshot |
| identical rerun | restore inputs + record deviations |
| full eval UX | OQ-014 later |
| Durable knowledge (STATE-005) | Versioned scoped entries with provenance under LocalAppData knowledge |
| Protected instruction | Kind that rejects agent-origin overwrites |
| Knowledge conflict | Explicit failure when `base_version` does not match |
| one sqlite for everything | Separate application.sqlite and checkpoints.sqlite |
| mutate LangGraph tables | App links checkpoint ids only — never mutate checkpointer private tables |
| clear chat deletes project | STATE-002 — history ≠ project |
| close OQ-004 | Partial OQ-004 defaults only |
| CORS is login | CORS is not authorisation |
| secret in the repo | LocalAppData `state\desktop_backend_shared_secret` |
| remote backend v1 | unsupported (partial OQ-002) |
| renderer holds the token | Electron main injects `X-Workbench-Local-Token` |
| close OQ-002 | Partial OQ-002 defaults only |
| unverified means incompatible | Unverified ≠ incompatible |
| silently retry unknown tool | Unknown-effect safety (STATE-004) |
| snapshot undoes the email | No external-effect rollback promise |
| hold a shippable PR for polish | Ship when AC met (file leftovers) |
| leftover when AC failed | AC-fail (changes-requested / UAT:fail) |
| silent technical debt | Deferred follow-up Issue (`Deferred: #N`) |
| forever backlog Milestone | Feature Milestone or Optional extras |
| put it on the board | Set Project Status **and** attach a Milestone |
| milestone with a deadline | Delivery Milestone (no due date) |
| sprint / velocity | Out of scope (not how Issues are tracked) |
| cryptic Milestone title | Plain-English delivery name |
| Soft “I can…” as Milestone title | Feature name as title; done-when in description |
| Lab = try-before-commit / job replay | Model Lab vs Task cases and replay |
| Model Lab is task replay | Model Lab ≠ Task cases and replay |
| One Milestone per OQ | Feature Milestones only |

## Product and layout

**Local AI Workbench** is the product name. The GitHub repository may be named `thtaib`; that is not the product name.

**Windows-first scaffold (OQ-001)** is the supported application layout and toolchain: `apps/backend`, `apps/desktop`, root `specs/`, `scripts/`, and `tests/specs/`.

**workbench_backend** is the Python import package under `apps/backend/src/workbench_backend`.

**Repository-map binding** is a real path recorded in `specs/repository-map.json`. Unbound entries stay `null` until their `required_before` trigger.

**Provisional localhost HTTP** is the v1 loopback bind (`127.0.0.1` only). [Issue #40](https://github.com/Vidcar/thtaib/issues/40) adds shared-secret header checks; that does not close [OQ-002](../specs/open-questions.md#oq-002) and is not a remote-backend claim.

**`X-Workbench-Local-Token`** is the locked desktop↔backend local-trust header. ADR-0002 / Issue #41 owns the generated envelope. Issue #40 implements Electron main injection and the LocalAppData secret. The renderer must not hold or send the secret.

**LocalAppData `state\desktop_backend_shared_secret`** is the shared-secret file under `%LOCALAPPDATA%\LocalAIWorkbench\state\` (or the portable `state\` sibling). It is created on first use if missing. Never commit it.

**Partial OQ-002 defaults only** means Issue #40 locked same-machine shared-secret + loopback bind. Event reconnection and remote backend stay [OQ-002](../specs/open-questions.md#oq-002).

**CORS is not authorisation.** Allowed origins do not grant privileged `/v1` access. Missing token → 401; wrong token → 403.

**Docker Compose stub** is `infra/docker-compose.yml` with no product services. Compose is reserved for later container services.

**electron-builder (NSIS)** is the Windows packaging owner on the desktop app. A working package script may exist before an installer is required as evidence.

**David-PC** is the local verification host for UAT (`D:\CodeProjects\thtaib`). Cloud or CI checks do not replace that label.

**Scratch workspace** is `.scratch/` at the repository root. The entire tree is gitignored. Conventional subdirectories are `.scratch/uat/` (UAT workroots) and `.scratch/logs/` (capture files). An optional local-only `.scratch/README.txt` is fine; do not require committing anything under `.scratch/`.

**UAT workroot** is a throwaway directory under `.scratch/uat/…`. Agents and UAT must not create `uat-workroot*` at the repository root.

**Product data** is `%LOCALAPPDATA%\LocalAIWorkbench\` (models, runtimes, state, cases, snapshots, workspaces, knowledge, `application.sqlite`, `checkpoints.sqlite`). Chat transcripts live in `application.sqlite` and are not the working project. Durable product, managed-inference, Lab case/snapshot and durable-knowledge state is never the repository root and never `.scratch/`.

**Durable knowledge versioning (STATE-005)** is the application-owned, versioned store of user / agent / project memories, skills and protected instructions under `%LOCALAPPDATA%\LocalAIWorkbench\knowledge\`. It is not a RAG product, not a checkpointer table, and not git.

**Application-owned knowledge store under LocalAppData** is that `knowledge\` directory. Do not call it an agent memory DB.

**Optimistic concurrency / explicit conflict** means a write must name the expected `base_version`. A mismatch is a knowledge conflict, not last-write-wins.

**Protected instruction** is the knowledge kind that rejects agent-origin overwrites. A human or API-maintainer path may edit it with provenance.

**Knowledge conflict** is the explicit failure when `base_version` does not match the current version.

**Partial OQ-006 defaults only (store; not RAG / cross-surface sharing)** means Issue #17 locked the STATE-005 store. Retrieval/RAG and whether knowledge is shared across Chat, Lab and Builder stay open.

<a id="model-lab"></a>
**Model Lab** is hardware-local **model trait / capability testing** on David’s machine. Illustrative kinds: speed/throughput; prefill/decode at context lengths; MTP; quantisation impact; concurrent conversations; memory/needle; tool calling; vision — the catalogue can grow. It is **not** save-a-job-and-replay. Separate delivery feature from Task cases and replay ([LAB-001](../specs/modules/lab-evaluation.md#lab-001) separation). See the [delivery feature map](delivery-feature-map.md).

<a id="task-cases-and-replay"></a>
**Task cases and replay** is save a real run as a case, restore starting inputs, rerun recorded-tool vs live-tool, and compare evidence ([LAB-002](../specs/modules/lab-evaluation.md#lab-002)…[004](../specs/modules/lab-evaluation.md#lab-004) style). Separate delivery feature from Model Lab. Pack module [lab-evaluation](../specs/modules/lab-evaluation.md) may document both; product Milestones must not blur them.

**Lab reuse** is the Task cases and replay path: capture → restore → rerun against the shared Deep Agents harness. It is not Model Lab, not a Lab agent, and not a second evaluation loop.

**Application directory snapshot** is the Issue #15 snapshot: an application-owned copy of allowlisted project files at a quiescent boundary, stored under `cases\` and `snapshots\`. It is not a git commit.

**Recorded-tool** is fixture replay labelled as not proof of a current live integration. **Live-tool** invokes the enabled tools.

**Managed inference (MOD-001…004)** is backend-owned bundle import, GGUF inspect, settings bags, and deployment lifecycle. The desktop exposes Models and Deployments controls only.

**Embedded harness (AGT-001)** is the backend start / observe / cancel API that runs one Deep Agents task. Debug-quality Chat calls this harness directly. It is not a second application-written agent loop and not Builder. A thin desktop Agent-run debug panel may still call that API.

**Debug-quality Chat** is the Chat tab that binds a deployment/profile and project workspace path, starts/cancels one harness task, and streams harness events. Transcript / conversation history is displayed history in `application.sqlite`, not the working project (STATE-002). Deep Agents filesystem tools target project storage. This is not Chat polish and not Builder.

**Separate application.sqlite and checkpoints.sqlite** is the Issue #27 pair under the product root. `application.sqlite` is the workbench system of record for runs, chat linkage, profile/deployment refs, checkpoint id links and file refs. `checkpoints.sqlite` is the LangGraph checkpointer file.

**App links checkpoint ids only — never mutate checkpointer private tables** means application code records checkpoint identities and related files in `application.sqlite`. It does not UPDATE/INSERT/DELETE LangGraph checkpointer tables.

**STATE-002 — history ≠ project** means editing or clearing Chat history alone neither restores nor deletes project files. Filesystem tools write project storage only.

**Partial OQ-004 defaults only** means Issue #27 locked the dual-DB + app linkage pattern. Issue #31 locked unknown-effect safety ([STATE-004](../specs/modules/state-recovery.md#state-004)). Issue #42 locked cancel honesty (`cancel_requested` is still live; `cancelled` is the confirmed stop; no false quiescence). Identities, event-order/reconnection and exactly-once stay [OQ-004](../specs/open-questions.md#oq-004).

**cancel_requested vs cancelled** means a cancel request is accepted and the run remains live until the worker confirms stop. Quiescence / “safe to treat the workspace as idle” must not treat `cancel_requested` as idle.

**Debug-quality Chat (Issue #22)** is the Chat tab that calls the embedded harness. Agent-run is not that surface. Do not call it finished Chat polish.

**Partial OQ-007 landed on #21; remainder open** means Windows CUDA 13.4 pin, default GPU profile and valued `flash_attn` mapping landed with [Issue #21](https://github.com/Vidcar/thtaib/issues/21) / [PR #24](https://github.com/Vidcar/thtaib/pull/24). Full compatibility evidence, capability claims and complete setting-mapping verification stay [OQ-007](../specs/open-questions.md#oq-007).

**Partial OQ-007 provenance records on #31** means versioned compatibility records keep publisher guidance, tested adjustments and user overrides separate. `tested` is a record status, not catalogue `verified`. Unverified ≠ incompatible.

**Unknown-effect safety (STATE-004)** means reconnect/resume/restart reports uncertainty or reconciles with evidence. It does not silently replay an unknown external operation and does not promise external-effect rollback.

**MOD-005 adapter** is the narrow LangChain ChatOpenAI client aimed at a model-manager deployment OpenAI-compatible endpoint. The adapter starts no inference process.

**Model bundle** is the canonical recorded manifest (quant, shards, companions, HF repo+revision, hashes, paths). It is not “the model in Chat”.

**Running deployment** is a live managed llama-server process or a connected OpenAI-compatible endpoint. A saved profile is not a running deployment.

**Connected endpoint** attaches an existing service with `scope=connected`. The workbench does not start, stop, or kill that external process.

**Unverified ≠ incompatible.** A missing compatibility claim is not a known incompatibility and is not a supported-capability claim.

**PATH llama** is an unsupported fallback. UAT claims use a managed runtime pinned under `runtimes\` with a runtime-manifest.

**Preferred capability UAT model (Qwen3.8-27B UD-IQ4_XS)** is Hugging Face repo `unsloth/Qwen3.8-27B-GGUF`, file `Qwen3.8-27B-UD-IQ4_XS.gguf` (~14.3 GB). Download it once with `huggingface_hub`, revision-pinned, under `%LOCALAPPDATA%\LocalAIWorkbench\models\`, and register it as a Model bundle ([MOD-001](../specs/modules/models.md#mod-001)). Tiny ~0.5B models are for fast smoke and process tests only — not for reply, tool-calling, or other capability acceptance. This is the preferred capability UAT model, not the only model forever, and it is not required for every fast smoke.

**Reuse managed Model bundle (reference/link; no scratch copy)** means capability UAT points at the registered bundle or its local path. Do not copy the GGUF into `.scratch/uat/` or any other workroot.

**Never commit GGUF/mmproj/weights.** Existing ignore patterns stay. For vision-related capability UAT, include the official mmproj companion from the same Hugging Face repository in the same Model bundle.

## Issue tracking

**Project Status** is the GitHub Project field for **agent pipeline state only**: Backlog, Ready, In progress, Review, UAT, Done. Keep it accurate when the Issue moves. It is not a delivery label and not a second board.

**Milestone** is which plain-English **delivery** the Issue belongs to — what David is getting. Optional short description; **no due date**. It is not a second Status board, not a sprint, and not a velocity target. One Milestone per delivery; close it when that delivery’s Issues are done. Do not keep a forever-open “everything” Milestone. Title it so David can scan the delivery (for example “End-to-end gaps — Slice 1: desktop trust, contracts, cancel honesty”), not a cryptic code. Put a technical hint in the Issue title if needed.

**Feature name as title; done-when in description** means the ten feature Milestones (#3–#12) keep their GitHub titles. Soft “I can…” slogans are not Milestone titles. Done-when text lives on the Milestone description. The four-layer plan is the [delivery feature map](delivery-feature-map.md).

**Feature Milestones only** means product delivery uses those ten feature homes, not one Milestone per open question. Process Milestones (standing rules, this map, a Slice bundle) stay process — they are not a second feature list.

**Tracking Issue** is an epic/checklist. It stays open until the whole proof is done. Focused Issues link to it **and** share its Milestone.

“Put it on the board” means set Project Status **and** attach a Milestone. Spec does both when opening a Ready Issue. Builder, Reviewer, UAT and Release do not invent parallel boards. Informal “out of scope this milestone” in product copy is not a GitHub Milestone and is not a deadline.

**Ship when AC met** means the Issue acceptance criteria are met and the tip is shippable: Reviewer approve / UAT:pass / Orchestrator merge. Do not hold the PR for polish, adjacent debt, or out-of-scope finds.

**Leftover vs AC-fail.** A leftover is non-blocking debt, a bug, a nit, or an out-of-scope find on a shippable tip. AC not met is changes-requested or UAT:fail — not a leftover.

**Deferred follow-up Issue** is a focused Issue for each leftover, acknowledged on the PR as `Deferred: #N`, under the correct feature Milestone (or **Optional extras** for true maybe-someday). Never silent technical debt. Do not invent a vague forever “backlog” Milestone. Out-of-scope product discoveries become a follow-up Issue or a Translator Confirmed brief — do not expand the current PR. Reviewer/UAT note leftovers on the PR; Spec (or Builder with Spec check) opens the follow-up with Status+Milestone; Orchestrator ensures nothing is lost and does not block merge on acknowledged non-blocking debt.

## Later-decision phrases (still open)

These names are locked vocabulary, not selections. The questions stay in [open questions](../specs/open-questions.md).

**OQ-006 unresolved (surface vs shared)** is whether retrieval/RAG and durable knowledge are shared across Chat, Lab and Builder or remain surface-local. It is not permission to “add RAG”. The STATE-005 store defaults do not close this question.

**Default tool bus vs optional (OQ-009 / OQ-003)** is whether MCP is the default tool bus or an optional integration. MCP is not isolation; sandbox isolation stays [OQ-003](../specs/open-questions.md#oq-003).

**Durable product Approvals inbox (OQ-011)** is a product HITL surface. A LangGraph interrupt is not that inbox.

**Run observability outside Lab (OQ-012)** is local traces, token/cost and parent/child attribution outside Lab cases. LangSmith is not the product home.

**Multi-model / hybrid routing (OQ-013)** is routing among models and combining local GGUF with remote OpenAI-compatible endpoints. The model manager owns it; there is no second inference engine.

**Evaluation UX beyond Inspect (OQ-014)** is datasets, scorers, compare-runs and export beyond Inspect building blocks.

**Workflow definition import/export (OQ-015)** is interchange of workflow definitions, including LangGraph JSON and later adapters. It is not a second runtime.

**Voice/multimodal optional (OQ-009)** stays experimental. It is not a core prerequisite.

**Builder canvas and chrome UX (OQ-016)** is partially decided for **v1 chrome** in [ADR-0003](../specs/decisions/ADR-0003-builder-v1-chrome.md): TooGraph-inspired cues with an original layout; grid, zoom, minimap, multi-select; icon rail and searchable node library; expanded nodes with an inline prompt editor; Run/Stop, canvas highlight and a run inspector; colour+label workflow edges with config via node badge/popover (not a canvas config edge); inherit workflow profile/deployment with explicit per-node override only. The remainder is the unfinished Builder surface — not a shipped claim. [OQ-004](../specs/open-questions.md#oq-004) and [OQ-011](../specs/open-questions.md#oq-011) stay open. [WF-001](../specs/modules/agents-workflows.md#wf-001) and [ARCH-003](../specs/architecture.md#arch-003) behaviour are unchanged. TooGraph is inspiration only — not a pixel target and not a fork.

**`cancel_requested` / `cancelled`** are shared run-lifecycle names. `cancel_requested` is still live (not quiescent). `cancelled` is confirmed stop. Issue #42 owns harness honesty; ADR-0002 only defines the shared names.

**CDF fork** is out of scope.
