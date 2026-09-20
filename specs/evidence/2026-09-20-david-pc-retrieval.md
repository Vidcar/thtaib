# Evidence: retrieve-and-offload fail-closed and live search on David-PC (uat tier)

**Date:** 2026-09-20 · **Requirements:** STATE-006 (partial clauses; see Conclusion) · **Tested commit:** `7db7f45d76733e156f6a4c7db93f5eea08a2d48a` (`origin/main` after PR #92; worktree of that tip) · **Dirty tree:** no on the UAT worktree; David's checkout was left detached at `5728b94`, clean and unused · **Tier:** uat · **Related:** PR #92 (implementation); this report is recorded after the run.

## Provenance and limits

Performed by a Cursor agent on David's Windows PC through the product's own backend HTTP API with the desktop shared-secret token (token not reproduced). No Electron clicks. No CI job — do not invent a run URL. Raw traces and chunk text stayed on that machine and are not committed. This file is identifiers and outcomes only; it is not a context dump.

This is `uat`-tier evidence for the clauses it covers. It does **not** cover every acceptance line (recorded-tool replay was not run), so the catalogue row stays **`built`**. Digest is left `null`.

## Environment

David-PC (same machine as the 2026-09-19 managed-inference and host-shell UATs): Windows, NVIDIA GeForce RTX 3090 24 GB. Managed llama.cpp `b11045` CUDA. Chat bundle `bundle_ee208ec8f733` (Qwen3.8-27B UD-IQ4_XS), profile `profile_bcda87132f75`, deploy `deploy_1cbbe8bc1699` (listen 8091). Embedder: reuse-in-place of the product-default GGUF already under `%LOCALAPPDATA%\LocalAIWorkbench\models\Qwen3-Embedding-0.6B-Q8_0.gguf` (SHA-256 `06507c7b42688469c4e7298b0a1e16deff06caf291cf0a5b278c308249c3e439`); bundle `bundle_b42c10c5336d`, profile `profile_3f892e2b00f1` (`embedding: on`, pooling `last`), deploy `deploy_1c2fa63f2c3a` (listen 8092; `POST /v1/embeddings` dimension 1024). Data root `%LOCALAPPDATA%\LocalAIWorkbench\`. Product backend on port 8002 from a `.scratch/` worktree of `7db7f45`. UAT project `.scratch/uat/retrieval-2026-09-20/project` (only `notes.md`).

VRAM: 1186 MiB idle → 19081 MiB after chat → 20547 MiB after embedder → ~1.2 GB after both managed servers were stopped.

## What ran

| Step or command | Working directory | Live / mocked / recorded | Result |
| --- | --- | --- | --- |
| Chat start naming a missing `embedding_deployment_id` | HTTP client | live | **404** `embedding_deployment_missing` |
| Chat start naming the 27B chat deploy as embedder (`deploy_1cbbe8bc1699`) | HTTP client | live | **409** `embedding_not_configured` |
| Chat start naming the registered embedder while it was stopped | HTTP client | live | **409** `embedding_deployment_unloaded` |
| Register embedder GGUF in place; start dedicated `--embedding --pooling last` alongside the 27B | HTTP client | live | Bundle `bundle_b42c10c5336d`; no second download. Both deploys running |
| Live search. Conversation `chat_dd629963a59c`, run `agent_0d0e82d70502`, thread `thread_7bc495cb1598`. Selected knowledge `kn_e2611981cdc1` / `knv_88eba6c79f27` plus allowlisted project `notes.md`. Chat presented `search_knowledge`; the 27B called it | HTTP client | live model, live embedder | Tool ran. Batch `52a13eaa`: **18** `chunk_*.md` files under `%LOCALAPPDATA%\LocalAIWorkbench\state\harness\thread_7bc495cb1598\retrieved\`. Run `retrieved_material` filled. Project still **only** `notes.md`; no project `retrieved\` folder |
| Stop `deploy_1cbbe8bc1699` and `deploy_1c2fa63f2c3a`; stop UAT backend on 8002 | HTTP client | live | Both managed `llama-server` processes stopped. VRAM back to idle. Cursor and David's checkout untouched |

Chunk bodies and knowledge text are not reproduced here.

## Covered clauses (not the whole acceptance line)

| ID | Covered on this run | Still uncovered |
| --- | --- | --- |
| STATE-006 | Live-tool Chat with a selected knowledge version and a loaded `embedding: on` endpoint; `search_knowledge` wrote `/retrieved/` under harness scratch, not the project; the run capture listed those sources. Fail-closed without a loaded embedder: missing id **404** `embedding_deployment_missing`; chat GGUF as embedder **409** `embedding_not_configured`; registered-but-stopped embedder **409** `embedding_deployment_unloaded`. No invented hits | Recorded-tool replay (acceptance: does not attach a live index). Other fail-closed codes (`embedding_pooling_none`, `retrieval_corpus_empty`, invalid / project-less project-path). Electron selectors. Lab / Agent-run HTTP. Knowledge-only prompt-append path |

Related live observations not attached as catalogue rows: AGT-002 (`retrieved_material` filled on this run); MOD-003 (`embedding: on` + pooling `last` on the managed embedder). A GGUF on disk was not treated as a deployment until the operator registered and started it.

## Conclusion

Executable checks at the HTTP boundary on the target Windows GPU path: Chat refused retrieval without a loaded dedicated embedder; with both servers up, a live `search_knowledge` wrote 18 chunks under harness scratch and filled `retrieved_material` while the project stayed `notes.md` only. Requirement status stays **`built`**. No row is `verified`. No `requirement_sha256` is recorded.

**Not covered:** recorded-tool replay; remaining fail-closed codes; Electron; Lab live retrieval; a durable shared index or automatic STATE-005 writes ([OQ-006](../open-questions.md#oq-006) remainder).
