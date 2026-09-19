# Verification and evidence

What a catalogue status means, what counts as evidence, and how evidence goes stale.

## Status definitions

| Status | Operational meaning |
| --- | --- |
| `planned` | Specified; no implementation exists. |
| `built` | Code and passing unit tests exist for at least the core of the requirement, in CI, against fakes, scripted models or fixtures. Not a claim that it works for a user. |
| `verified` | At least one `ci-smoke` or `uat` evidence row with `result: passed` at a recorded commit, and the requirement text unchanged since (digest matches). |
| `retired` | The ID is preserved; the requirement is no longer active and its replacement is named in the specification. |

A status never follows from a document being accepted, from a green unit-test job, or from a screenshot. Downgrade `verified` to `built` when code, dependency, runtime or requirement changes invalidate the evidence and re-verification has not happened.

## Evidence tiers

Model and agent features are proven against a real local runtime, in two tiers agreed on 2026-09-19:

- **`ci-smoke` — real-model smoke in Linux CI.** A tiny GGUF on a CPU `llama-server` (the pinned llama.cpp build) driven through the product's own HTTP API. Proves plumbing: the request reaches the model, tool calls execute, the thread resumes, applied settings appear on the wire. Proves nothing about model capability. The evidence `ref` is the CI run URL.
- **`uat` — David-PC capability UAT.** Windows, NVIDIA 3090, managed CUDA runtime, the [preferred capability UAT model](../docs/glossary.md#preferred-capability-uat-model) (with its mmproj for vision). Proves managed inference and capability claims (reply quality, tool calling, vision, MTP). Requires David's PC as a Cursor worker or David running a documented script and pasting results. The evidence `ref` is a report under `specs/evidence/` or the PR that carried it.
- **`manual` — any other live run** (for example a hand-driven smoke on a cloud VM). Recorded for information; it cannot make a row `verified`.

Windows claims are not established by Linux results, and tiny-model results are never capability evidence.

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

## Evidence reports

Longer evidence goes in `specs/evidence/<date>-<slug>.md` from the [evidence template](templates/evidence.md): commit, environment and versions, commands as run, results including failures and skips, what was live versus mocked versus recorded, what remains unverified. Sanitise: no secrets, weights, private project data or unredacted model context. Distinguish an executable check from a model's judgement.

## What the checker proves

`scripts/check_specs.py` validates structure: links and anchors, requirement IDs and their catalogue rows, catalogue and repository-map shape, existing code/test/evidence pointers, the source archive hash, evidence-row shape, and the digest match for `verified` rows. On pull requests it also rejects requirement IDs deleted from both text and catalogue. It cannot run tests, judge semantics, confirm that a commit was really tested or inspect GitHub settings; reviewers do that.

## Product gates

Each gate is added with the first implementation it protects and registered in [commands](commands.md): unit tests and the desktop type-check/build (registered, required on `main`); shared-contract freshness (registered, required); real-model CI smoke (this tier, to be registered with the `integration-tests` binding); import-boundary check (unbound); permission, cancellation and recovery checks for workers; crash and no-duplicate-continuation checks for durable runs; consistent-capture and isolated-restore checks for snapshots. A specification-only workflow is never the sole gate once code exists.
