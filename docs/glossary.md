# Glossary

Locked names for issues, pull requests and user-facing copy. Behaviour lives in the [specifications](../specs/README.md); this list only fixes the words.

## Product

**Local AI Workbench** — the product name. The repository is `thtaib`; that is not the product name.

**Managed inference** — the workbench downloads a pinned llama.cpp runtime, starts `llama-server` itself and owns that process (MOD-001…004). **Connected endpoint** — an existing OpenAI-compatible server the workbench attaches to and never starts, stops or kills.

**Model bundle** — the recorded manifest of a model: quantisation, shards, companion files such as `mmproj`, Hugging Face repository and revision, hashes, local paths. **Run profile** — saved startup, per-request and agent settings. **Running deployment** — a live managed process or a connected endpoint; a saved profile is not a deployment.

**Startup / per-request / agent bags** — the three settings groups (MOD-003). Startup applies when a deployment starts or attaches; selecting a profile never rewrites a running server.

**Selected ≠ loaded ≠ applied** — a chosen name or id (selected) is not the resident process or content (loaded) and not what reached the request (applied). Only the live process or the outbound request proves the last two ([effective setup](../specs/architecture.md#effective-setup)).

**Unverified ≠ incompatible** — a model without a compatibility record is usable and unverified, not known-incompatible. **Health ≠ ownership** — a healthy endpoint is not proof the workbench owns the process; process identity is.

**Embedded harness** — the backend API that runs one Deep Agents task (AGT-001). **Agent-run panel** — a debug view onto that API; it is not Chat.

**Chat** — the first-class conversation surface. Today it is *debug-quality Chat*: it works but is not polished. Chat works with or without a project folder.

**Conversation / execution thread / run** — the Chat record, the LangGraph `thread_id` the harness resumes, and one harness invocation. **Continue** = same conversation + same thread + new run. **Fresh** = new conversation + new thread; project files and durable knowledge stay. **Displayed history ≠ execution thread** — the transcript is presentation; editing it changes no file, no thread and no next request.

**`cancel_requested` / `cancelled`** — a cancel request leaves the run live until the worker confirms the stop. Never treat `cancel_requested` as idle.

**Unknown-effect safety** — after a crash or restart an unacknowledged external effect is reported unknown and never silently repeated. Snapshots make no rollback promise for external actions.

**Application directory snapshot** — an application-owned copy of allowlisted project files at a quiescent boundary under `cases\` and `snapshots\`. Not a git commit.

**Durable knowledge** — versioned user, agent and project memories, skills and protected instructions under `knowledge\` (STATE-005). **Protected instruction** — a knowledge kind that rejects agent-origin writes. **Knowledge conflict** — the explicit failure when `base_version` does not match. **Retrieval / RAG** — query-time search over a derived LangChain index (STATE-006); not the durable store and not training. Requested only by selecting a loaded dedicated embedding deployment (`embedding: on`; chat GGUFs are not embedders). A GGUF file on disk is not that deployment. Deep Agents `memory=` / `skills=` are always-load / progressive disclosure, not retrieval. Remainder under [OQ-006](../specs/open-questions.md#oq-006).

<a id="model-lab"></a>
**Model Lab** — hardware-local model trait and capability testing on David's machine, presented as data and charts to understand model behaviour. It never writes back into profiles and has no apply button. Separate delivery from Task cases.

<a id="task-cases-and-replay"></a>
**Task cases and replay** — save a real run as a case, restore its starting inputs, rerun with **recorded-tool** (fixture replay, no live filesystem) or **live-tool** mode, compare evidence. **Trait catalogue** — the growing list of Model Lab questions; not a task-case library.

**Builder** — the visual workflow editor. Not shipped; v1 chrome is recorded in ADR-0003. The visual graph is never executable authority.

**Workers** — declared environments for shell, browser and graphical execution. The first is the **Windows host shell with approvals**; WSL and Docker come later. A working directory is not a security boundary; MCP is not isolation.

**`X-Workbench-Local-Token`** — the desktop↔backend header. Electron main injects it; the renderer never holds the secret at `state\desktop_backend_shared_secret`. CORS is not authorisation.

**Product data** — `%LOCALAPPDATA%\LocalAIWorkbench\` (Linux `~/.local/share/LocalAIWorkbench/`): models, runtimes, state, cases, snapshots, workspaces, knowledge, logs, `application.sqlite`, `checkpoints.sqlite`. Never the repository, never `.scratch/`.

## Verification

**David-PC** — David's Windows machine with an NVIDIA 3090: the only place managed CUDA inference and capability UAT can run. **Cloud or CI** proves plumbing, not capability.

<a id="preferred-capability-uat-model"></a>
**Preferred capability UAT model (Qwen3.8-27B UD-IQ4_XS)** — Hugging Face `unsloth/Qwen3.8-27B-GGUF`, file `Qwen3.8-27B-UD-IQ4_XS.gguf` (~14.3 GB), downloaded once with `huggingface_hub` at a pinned revision under `models\` and registered as a Model bundle; the official mmproj from the same repository goes in the same bundle for vision. Reuse it by path; never copy weights into scratch or commit them. Tiny (~0.5B) models are for smoke and process tests only, never for reply, tool-calling or capability acceptance.

**`planned` / `built` / `verified`** — specified only; unit-tested code exists; seen working live at a recorded commit through the CI smoke tier or David-PC UAT ([verification](../specs/verification.md)).

**Scratch workspace** — `.scratch/` at the repository root, gitignored, with `.scratch/uat/` for UAT workroots and `.scratch/logs/` for captures. Never create `uat-workroot*` or temp files elsewhere.

<a id="issue-tracking"></a>
## Issue tracking

**Project Status** — agent pipeline state only (Backlog, Ready, In progress, Review, UAT, Done). **Milestone** — the plain-English delivery an issue belongs to (feature Milestones #3–#12); no due dates, sprints or velocity. **Tracking issue** — a checklist that stays open until the whole proof is done. **Ship when AC met** — merge when acceptance criteria are met and the tip is shippable; each acknowledged leftover becomes a focused follow-up issue noted `Deferred: #N`. Out-of-scope discoveries become a follow-up issue, not scope creep in the current PR.
