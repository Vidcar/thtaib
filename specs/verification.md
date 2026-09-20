# Verification and evidence

What a catalogue status means, what counts as evidence, and how evidence goes stale.

## Status definitions

| Status | Operational meaning |
| --- | --- |
| `planned` | Specified; no implementation exists. |
| `built` | Code and passing unit tests exist for at least the core of the requirement, in CI, against fakes, scripted models or fixtures. Not a claim that it works for a user. |
| `verified` | At least one `ci-smoke` or `uat` evidence row with `result: passed` at a recorded commit, from a tier the requirement's `verifiable_by` list allows, with the requirement text unchanged since (digest matches), and the run covering the requirement's whole acceptance line. |
| `retired` | The ID is preserved; the requirement is no longer active and its replacement is named in the specification. |

A status never follows from a document being accepted, from a green unit-test job, or from a screenshot. Downgrade `verified` to `built` when code, dependency, runtime or requirement changes invalidate the evidence and re-verification has not happened.

## Evidence tiers

Model and agent features are proven against a real local runtime, in two tiers agreed on 2026-09-19:

- **`ci-smoke` — real-model smoke in Linux CI** ([commands](commands.md#real-model-smoke); `apps/backend/tests_integration`, bound as `integration-tests`). A tiny GGUF on a CPU `llama-server` from the pinned llama.cpp release, driven through the product's own API when a pull request (or `main` push, `workflow_dispatch`, or `merge_group`) touches the backend. It proves plumbing: token trust, connected attach and health, a real tool call writing into the project, thread continuity on a follow-up turn, and a profile's per-request settings in the outbound body. It asserts on API responses and recorded state, never model prose, and proves nothing about model capability, managed (Windows CUDA) inference or the desktop. The evidence `ref` is the CI run URL. A skipped smoke job on an unrelated PR is not evidence.
- **`uat` — David-PC capability UAT.** Windows, NVIDIA 3090, managed CUDA runtime, the [preferred capability UAT model](../docs/glossary.md#preferred-capability-uat-model) (with its mmproj for vision). Proves managed inference and capability claims (reply quality, tool calling, vision, MTP). Requires David's PC as a Cursor worker or David running a documented script and pasting results. The evidence `ref` is a report under `specs/evidence/` or the PR that carried it.
- **`manual` — any other live run** (for example a hand-driven smoke on a cloud VM). Recorded for information; it cannot make a row `verified`.

**What each tier may verify** is the requirement's `verifiable_by` list in [the catalogue](catalog.json), enforced by the checker. `["ci-smoke", "uat"]` marks plumbing requirements (backend trust and coordination, harness tool calls, continuity and records, applied request settings, contracts, Lab replay mechanics, registry validation). `["uat"]` marks everything that needs real hardware, a capable model or the Windows desktop: managed inference and companion files (MOD-001, MOD-002, MOD-004), the adapter's multimodal and runtime-specific behaviour (MOD-005), capability exposure (ARCH-004), access policy through workers (ARCH-005, ENV-001…006, API-005), the desktop surface (API-002), engine measurement and Model Lab traits (LAB-001, LAB-005, LAB-006). A green smoke job is executable plumbing evidence for the listed checks and nothing more; it never verifies a `uat`-only row. Windows claims are not established by Linux results, and tiny-model results are never capability evidence.

The smoke write task asks for exactly `/hello.txt` and presents only `write_file` (so the tiny model is not steered by the Deep Agents `grep` description that mentions `/large_tool_results/`). It asserts that file is in the project and that `large_tool_results/` and `conversation_history/` are absent from the project. A separate project-less Chat turn proves a non-file completion with filesystem tools absent and consumes `GET /v1/events` through `stream_end`. Both are plumbing checks, not capability evidence. STATE-006 retrieve-and-offload is not part of this smoke: CI has no dedicated embedding GGUF, and a tiny chat GGUF is not an embedder. `/retrieved/` isolation is covered by unit tests with `DeterministicFakeEmbedding`. Live retrieval evidence stays David-PC UAT against a loaded `embedding: on` deployment.

## Evidence row

```json
{
  "kind": "ci-smoke",
  "ref": "https://github.com/Vidcar/thtaib/actions/runs/REPLACE_WITH_RUN_ID",
  "commit": "REPLACE_WITH_FULL_TESTED_COMMIT_SHA",
  "date": "2026-09-19",
  "environment": "ubuntu-latest; llama.cpp b11045 CPU; Qwen2.5-0.5B-Instruct q4_k_m",
  "result": "passed",
  "requirement_sha256": "REPLACE_WITH_python_scripts/check_specs.py_--requirement-hash_ID"
}
```

`ref` is a URL or a repository-relative path that exists. `commit` is the full SHA that was actually tested; if the evidence is committed later, say so in the report. `requirement_sha256` comes from `python scripts/check_specs.py --requirement-hash <ID>` and is checked against the current requirement block for `verified` rows; never refresh a digest without re-running the check. It may be `null` on a `manual` row or when the requirement text has changed since the run. `result` is `passed`, `failed` or `skipped`; only `passed` supports `verified`, and a failed `ci-smoke` or `uat` row on a `verified` requirement means it must be downgraded.

Practical order: finalise the requirement text first, then run `--requirement-hash`, then add the row. A `ci-smoke` run URL exists only after CI has run on a pushed commit, so its row normally lands in a follow-up commit or PR whose `commit` field names the tested tip, not the PR tip that adds the row; say so in the report. `--requirement-hash` refuses to print while any other pack error exists, so fix those first. A run that covers only part of an acceptance line is recorded as a row on a `built` requirement with the covered clauses named in the report; it does not make the row `verified`.

## Evidence reports

Longer evidence goes in `specs/evidence/<date>-<slug>.md` from the [evidence template](templates/evidence.md): commit, environment and versions, commands as run, results including failures and skips, what was live versus mocked versus recorded, what remains unverified. Sanitise: no secrets, weights, private project data or unredacted model context. Distinguish an executable check from a model's judgement.

## What the checker proves

`scripts/check_specs.py` validates structure: links and anchors, requirement IDs and their catalogue rows, catalogue and repository-map shape, existing code/test/evidence pointers, the source archive hash, evidence-row shape, the `verifiable_by` tier of every verifying row, and the digest match for `verified` rows. On pull requests it also rejects requirement IDs deleted from both text and catalogue. It cannot run tests, judge semantics, confirm that a commit was really tested or inspect GitHub settings; reviewers do that.

## Product gates

Each gate is added with the first implementation it protects and registered in [commands](commands.md): Linux unit tests, Linux desktop type-check/build, Linux shared-contract freshness, and Linux spec-integrity (the thin remaining required gate on `main`); Windows backend unittest and Windows desktop build (registered, path-filtered, still run, not the required merge wall — David-PC is the real Windows and capability check); real-model smoke (registered; binding `integration-tests` → `apps/backend/tests_integration`; path-filtered to backend changes, not yet a required check); import-boundary check (unbound); managed Windows CUDA deployment and worker integration tiers (do not exist); MCP plumbing smoke, when ENV-007 is implemented, uses an in-process FastMCP target (not Playwright or GitHub) on the real-model smoke tier — capability UAT for browser and GitHub stays David-PC; permission, cancellation and recovery checks for workers; crash and no-duplicate-continuation checks for durable runs; consistent-capture and isolated-restore checks for snapshots. A specification-only workflow is never the sole gate once code exists. Green unit tests still make a row `built`, never `verified`.
