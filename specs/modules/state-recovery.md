# State, memory and recovery

[Architecture](../architecture.md) · [Status and evidence](../catalog.json) · [Decisions](../decisions/changelog.md)

## Purpose

Persist enough to explain and continue a run after restart; keep chat history, project files, snapshots and durable knowledge distinct; never pretend an external effect can be undone or safely repeated.

## Boundaries and ownership

The application owns run and thread identities, checkpoint namespaces, displayed history, artifact and context references, knowledge versions and snapshot records in `application.sqlite` and files. LangGraph owns checkpoint bytes in `checkpoints.sqlite`. A snapshot provider captures and restores project directories. Worker adapters declare their own recoverability. There is no distributed transaction across the two databases, files and remote services; recovery reconciles them explicitly. Source: [Revision 0.5, pages 4–6](../sources/README.md#application-infrastructure).

## Interfaces and contracts

Run records link profile, deployment, environment, agent setup, applied settings, parent/child runs, `thread_id`, checkpoint ids, evidence, optional budgets and recovery outcome. Chat records link `conversation.id → thread_id → run_ids`. The external-effect ledger (`/v1/effects`: dispatch, acknowledge, recover, reconcile; rollback returns 409) records `dispatched`, `acknowledged`, `unknown`, `reconciled`, `failed`. Knowledge (`/v1/knowledge/`: entries, versions, edit, revert, config, captures) is versioned by scope ∈ {user, agent, project} and kind ∈ {memory, skill, protected_instruction}. Snapshot manifests record included paths with sha256 and size, exclusions, configuration and knowledge versions.

## Behaviour

- **Two databases.** Application records in `application.sqlite`; checkpoints in `checkpoints.sqlite`. The application stores checkpoint ids only and never touches checkpointer tables. Following a persisted run after restart reaches its checkpoint ids and files through application records alone.
- **History ≠ project ≠ thread.** Transcripts are presentation. Filesystem tools write project storage only; harness-internal files (`/large_tool_results/`, `/conversation_history/`, `/retrieved/`) stay under the product data root (see [agents and workflows](agents-workflows.md#behaviour)). Editing or clearing a transcript restores or deletes no file and does not fork or reset the thread. Missing conversation → thread → run linkage after restart is an explicit gap, never a silent new thread.
- **Snapshots.** An application-owned copy of the allowlisted project directory at a quiescent boundary (capture fails while any run for the workspace is `queued`, `running` or `cancel_requested`), stored under `cases\` and `snapshots\`. Excludes secrets, weights, `.scratch`, `.venv`, `node_modules` and credentials; no environment restore. A `starting` snapshot is bound before project mutation and reused when the run is saved as a case; later parent edits do not alter it. Restore stages into a new workspace, verifies every recorded path, hash and size, rejects unexpected files and a missing tree, and registers the workspace only after verification; failed staging is discarded. The parent is never overwritten. Checkpoints and git commits are never assumed to capture untracked files, dependencies, services or remote effects.
- **Unknown effects stay unknown.** After crash, reconnect or restart, an effect without acknowledgement is `unknown`; it is never replayed (`replayed` is always false) and may only be `reconciled` against authoritative evidence. A cancel request is not acknowledgement. Snapshots make no rollback promise for external actions: `external_effect_rollback` is `not_supported`, `rollback_promise` is `none`, unresolved side-effect ids are preserved across capture and restore, and snapshot and restore responses carry those fields.
- **Durable knowledge.** Append-only versions with provenance; revert creates a new version. Writes name an expected `base_version`; a mismatch is `knowledge_conflict`. Protected instructions reject agent-origin writes; a human or API-maintainer path may edit them with provenance. Automatic agent writes need an explicit scope policy and carry actor and run id. Context-capture retention duration and redaction mode (`redact_secrets` by default, retain plaintext, or discard) are local configuration and apply to persisted diagnostic copies of model requests before storage; transcripts, checkpoints and operational events follow a separate retention policy. Selected versions are loaded as content for a run (STATE-005). Query-time retrieval is a derived LangChain index over that content, not a second store (STATE-006).
- **Persistence split.** Bundles, profiles, deployments, import jobs, Lab cases and knowledge versions are currently JSON files without locking or migrations; runs, chat and effects are SQLite. Converging on SQLite is [OQ-017](../open-questions.md#oq-017).

## Requirements

<a id="state-001"></a>
### STATE-001: Keep application records and execution checkpoints separate

Use separate application/checkpoint databases. Files hold models, projects, versioned knowledge, context captures, snapshots and artifacts. Application run records link profiles, deployments, environments, agent setup, parent/child runs, steps, threads, checkpoints, applied settings, evidence, optional budgets and recovery outcomes; they are the durable copy of the effective setup, and a stored selected id is not by itself a loaded or applied claim.

**Acceptance:** Follow a persisted run to its actual checkpoint and related files after restart. Verify that application records do not require direct mutation of the checkpointer's private tables.

<a id="state-002"></a>
### STATE-002: Do not confuse history with the working project

The backend owns thread identities, checkpoint namespaces and displayed history. Deep Agents file tools explicitly target project storage; conversation-state files are not a substitute for the working project.

**Acceptance:** Start a fresh conversation and inspect the retained project. Verify that changing displayed history alone neither restores nor deletes project files. After a project-bound file-writing turn, harness-internal paths (`/large_tool_results/`, `/conversation_history/`, `/retrieved/`) must not appear in the project.

<a id="state-003"></a>
### STATE-003: Pair branches with consistent project snapshots

Pair checkpoint branching with an application-owned project snapshot captured at a consistent execution boundary. Record included files, exclusions, configuration and memory versions. Restore to a separate workspace, create a linked branch run and compare changes/artifacts/checks without modifying the original attempt.

**Acceptance:** Branch from a captured point, verify restored inputs and memory references, make changes in the branch and demonstrate that the original workspace/attempt is unchanged.

<a id="state-004"></a>
### STATE-004: Do not promise rollback of external effects

Snapshots do not undo external actions or restore a whole environment unless an adapter explicitly supports it. Preserve unresolved side effects. Reconnect/resume/restart must not silently repeat an operation whose outcome is unknown.

**Acceptance:** Crash between an external effect and its local acknowledgement. Recovery reports the uncertainty or reconciles with authoritative evidence rather than blindly retrying the operation. A `cancel_requested` run is still live: recovery must not treat that request as a confirmed stop or as permission to replay an unknown effect.

<a id="state-005"></a>
### STATE-005: Version durable knowledge and enforce its write policy

Preserve user, agent and project knowledge scopes, provenance, versions and reversible edits. Resolve concurrent writes and protect instructions from agent-written knowledge. Retention/redaction of context captures is configurable locally and governs persisted diagnostic copies of model requests.

**Acceptance:** Demonstrate versioned edits/revert, a concurrent update conflict and an attempted protected-instruction overwrite. Verify the configured context-retention/redaction behaviour.

<a id="state-006"></a>
### STATE-006: Retrieve through LangChain components, not a second knowledge store

Retrieval is requested only when the run names `embedding_deployment_id`. Knowledge-only runs keep the STATE-005 prompt-append and do not fail closed. When retrieval is requested on a live-tool run, the harness presents `search_knowledge` (auto-presented; not one of the AGT-005 nine discovery names) following Deep Agents' retrieve-and-offload pattern: `RecursiveCharacterTextSplitter`, `InMemoryVectorStore`, embeddings via `OpenAIEmbeddings` against llama-server `POST /v1/embeddings`, and `similarity_search` writing chunks under `/retrieved/` (a `CompositeBackend` route into harness scratch, never the project). The application-owned knowledge store remains the durable source of truth; the vector index is derived at run start from selected knowledge versions (and, optionally, an allowlisted project-text set) and is discarded with the run. Retrieved documents are neither durable project memory nor training. Fail closed — invent no hits — when the named embedder is missing (`embedding_deployment_missing`), unloaded (`embedding_deployment_unloaded`), not `embedding: on` (`embedding_not_configured`), has `pooling: none` (`embedding_pooling_none`), the derived corpus is empty (`retrieval_corpus_empty`), or an allowlisted project path is invalid. A GGUF file on disk is not a deployment: the product does not invent a `bundle_*` record or start llama-server because weights exist. The named product-default embedder is official `Qwen/Qwen3-Embedding-0.6B-GGUF` file `Qwen3-Embedding-0.6B-Q8_0.gguf` (revision `370f27d7550e0def9b39c1f16d3fbaa13aa67728`, SHA-256 `06507c7b42688469c4e7298b0a1e16deff06caf291cf0a5b278c308249c3e439`); the operator must register and load a dedicated `--embedding` deployment. Captures record retrieved sources under the knowledge redaction policy ([AGT-002](agents-workflows.md#agt-002)). Recorded-tool replay does not attach a live index. Do not implement a workbench retriever, a persistent vector database as a knowledge owner, or hosted embeddings.

**Acceptance:** Start a live-tool run with selected knowledge versions and a loaded embedding endpoint. The search tool writes `/retrieved/` paths that exist under harness scratch and not in the project. The run capture lists those sources. A run that requested retrieval without a loaded embedding deployment fails closed and invents no hits. Recorded-tool replay does not attach a live index.

## Status and evidence

Rows STATE-001…006 in [the catalogue](../catalog.json). Thread continuity across turns and a project file written by the harness were seen live on Linux ([evidence](../evidence/2026-09-19-linux-live-smoke.md)) and on David-PC ([evidence](../evidence/2026-09-19-david-pc-managed-inference.md)); the effects ledger has no real producer yet. STATE-006 is `built` (unit tests with `DeterministicFakeEmbedding`); live retrieval on a loaded embedding deployment is unverified.

## Open questions

[OQ-004](../open-questions.md#oq-004) identities, event order, exactly-once; [OQ-005](../open-questions.md#oq-005) snapshot retention and environment snapshots; [OQ-006](../open-questions.md#oq-006) remainder (durable shared index, automatic writes, restore capture gaps) after the v1 retrieval recommendation; [OQ-017](../open-questions.md#oq-017) persistence strategy.
