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
| TooGraph as pixel target / fork | OQ-016 — Builder canvas and chrome UX (inspiration only) |
| invent Builder chrome | OQ-016 unresolved |
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

## Product and layout

**Local AI Workbench** is the product name. The GitHub repository may be named `thtaib`; that is not the product name.

**Windows-first scaffold (OQ-001)** is the supported application layout and toolchain: `apps/backend`, `apps/desktop`, root `specs/`, `scripts/`, and `tests/specs/`.

**workbench_backend** is the Python import package under `apps/backend/src/workbench_backend`.

**Repository-map binding** is a real path recorded in `specs/repository-map.json`. Unbound entries stay `null` until their `required_before` trigger.

**Provisional localhost HTTP** is loopback smoke for the FastAPI process. It does not close [OQ-002](../specs/open-questions.md#oq-002) and is not a trust model.

**Docker Compose stub** is `infra/docker-compose.yml` with no product services. Compose is reserved for later container services.

**electron-builder (NSIS)** is the Windows packaging owner on the desktop app. A working package script may exist before an installer is required as evidence.

**David-PC** is the local verification host for UAT (`D:\CodeProjects\thtaib`). Cloud or CI checks do not replace that label.

**Scratch workspace** is `.scratch/` at the repository root. The entire tree is gitignored. Conventional subdirectories are `.scratch/uat/` (UAT workroots) and `.scratch/logs/` (capture files). An optional local-only `.scratch/README.txt` is fine; do not require committing anything under `.scratch/`.

**UAT workroot** is a throwaway directory under `.scratch/uat/…`. Agents and UAT must not create `uat-workroot*` at the repository root.

**Product data** is `%LOCALAPPDATA%\LocalAIWorkbench\` (models, runtimes, state, cases, snapshots, workspaces, knowledge). Chat transcripts live under `state\chat\` and are not the working project. Durable product, managed-inference, Lab case/snapshot and durable-knowledge state is never the repository root and never `.scratch/`.

**Durable knowledge versioning (STATE-005)** is the application-owned, versioned store of user / agent / project memories, skills and protected instructions under `%LOCALAPPDATA%\LocalAIWorkbench\knowledge\`. It is not a RAG product, not a checkpointer table, and not git.

**Application-owned knowledge store under LocalAppData** is that `knowledge\` directory. Do not call it an agent memory DB.

**Optimistic concurrency / explicit conflict** means a write must name the expected `base_version`. A mismatch is a knowledge conflict, not last-write-wins.

**Protected instruction** is the knowledge kind that rejects agent-origin overwrites. A human or API-maintainer path may edit it with provenance.

**Knowledge conflict** is the explicit failure when `base_version` does not match the current version.

**Partial OQ-006 defaults only (store; not RAG / cross-surface sharing)** means Issue #17 locked the STATE-005 store. Retrieval/RAG and whether knowledge is shared across Chat, Lab and Builder stay open.

**Lab reuse** is capture → restore → rerun against the shared Deep Agents harness. It is not a Lab agent and not a second evaluation loop.

**Application directory snapshot** is the Issue #15 snapshot: an application-owned copy of allowlisted project files at a quiescent boundary, stored under `cases\` and `snapshots\`. It is not a git commit.

**Recorded-tool** is fixture replay labelled as not proof of a current live integration. **Live-tool** invokes the enabled tools.

**Managed inference (MOD-001…004)** is backend-owned bundle import, GGUF inspect, settings bags, and deployment lifecycle. The desktop exposes Models and Deployments controls only.

**Embedded harness (AGT-001)** is the backend start / observe / cancel API that runs one Deep Agents task. Debug-quality Chat calls this harness directly. It is not a second application-written agent loop and not Builder. A thin desktop Agent-run debug panel may still call that API.

**Debug-quality Chat** is the Chat tab that binds a deployment/profile and project workspace path, starts/cancels one harness task, and streams harness events. Transcript / conversation history is displayed history under `state\chat\`, not the working project (STATE-002). Deep Agents filesystem tools target project storage. This is not Chat polish and not Builder.

**Debug-quality Chat (Issue #22)** is the Chat tab that calls the embedded harness. Agent-run is not that surface. Do not call it finished Chat polish.

**Partial OQ-007 landed on #21; remainder open** means Windows CUDA 13.4 pin, default GPU profile and valued `flash_attn` mapping landed with [Issue #21](https://github.com/Vidcar/thtaib/issues/21) / [PR #24](https://github.com/Vidcar/thtaib/pull/24). Full compatibility evidence, capability claims and complete setting-mapping verification stay [OQ-007](../specs/open-questions.md#oq-007).

**MOD-005 adapter** is the narrow LangChain ChatOpenAI client aimed at a model-manager deployment OpenAI-compatible endpoint. The adapter starts no inference process.

**Model bundle** is the canonical recorded manifest (quant, shards, companions, HF repo+revision, hashes, paths). It is not “the model in Chat”.

**Running deployment** is a live managed llama-server process or a connected OpenAI-compatible endpoint. A saved profile is not a running deployment.

**Connected endpoint** attaches an existing service with `scope=connected`. The workbench does not start, stop, or kill that external process.

**Unverified ≠ incompatible.** A missing compatibility claim is not a known incompatibility and is not a supported-capability claim.

**PATH llama** is an unsupported fallback. UAT claims use a managed runtime pinned under `runtimes\` with a runtime-manifest.

**Preferred capability UAT model (Qwen3.8-27B UD-IQ4_XS)** is Hugging Face repo `unsloth/Qwen3.8-27B-GGUF`, file `Qwen3.8-27B-UD-IQ4_XS.gguf` (~14.3 GB). Download it once with `huggingface_hub`, revision-pinned, under `%LOCALAPPDATA%\LocalAIWorkbench\models\`, and register it as a Model bundle ([MOD-001](../specs/modules/models.md#mod-001)). Tiny ~0.5B models are for fast smoke and process tests only — not for reply, tool-calling, or other capability acceptance. This is the preferred capability UAT model, not the only model forever, and it is not required for every fast smoke.

**Reuse managed Model bundle (reference/link; no scratch copy)** means capability UAT points at the registered bundle or its local path. Do not copy the GGUF into `.scratch/uat/` or any other workroot.

**Never commit GGUF/mmproj/weights.** Existing ignore patterns stay. For vision-related capability UAT, include the official mmproj companion from the same Hugging Face repository in the same Model bundle.

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

**Builder canvas and chrome UX (OQ-016)** is unresolved look-and-feel: canvas chrome, icon rail, node anatomy, edge presentation, run affordances, config-link versus workflow-link visuals, and profile binding versus per-node overrides. TooGraph is inspiration only — not a pixel target and not a fork.

**CDF fork** is out of scope.
