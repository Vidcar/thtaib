# Verification, evidence and implementation claims

## What the supplied checker proves

The pack includes executable structural checks and regression tests for those checks. They detect broken local links/anchors, duplicate or untracked requirement IDs, unregistered specification documents, malformed catalogue data, missing bound paths, missing code/test/evidence files, altered source archives and a requirement changed since its recorded passing evidence.

On pull requests, an additional Git-base comparison rejects requirement IDs deleted from both the current text and catalogue. It does not prove that a retained ID still has the same meaning; behavioural changes require review.

They do **not** prove architectural semantics, actual test execution, security isolation, generated-contract freshness, valid imports, model behaviour or repository permissions. They do not poll upstream links. They do not automatically detect every code/dependency change that invalidates evidence. Human review and product checks must cover those gaps.

## Per-requirement traceability

[The catalogue](catalog.json) links each requirement to its authoritative specification and separately records `implementation_status`, `code`, `tests` and `evidence`.

After the repository was inspected (Windows-first scaffold, managed inference, embedded harness, Lab reuse, durable knowledge), use `planned` for absent work or `partial` for incomplete or insufficiently evidenced work. Leave `unassessed` only where no inspection has been performed. Use `verified` only for the current scope with actual implementation/test paths and passing evidence. Unit-test pointers alone are not `verified`. Preserve a retired requirement's ID/heading and explain its replacement rather than delete or reuse it.

Issue #23 recorded that inspection. Debug-quality Chat for [AGT-001](modules/agents-workflows.md#agt-001) lands with Issue #22; it is not finished polish. CUDA 13.4 / default GPU profile / valued `flash_attn` mapping landed as a partial [OQ-007](open-questions.md#oq-007) on Issue #21; Issue #31 adds provenance-capable [MOD-006](modules/models.md#mod-006) records; the remainder stays open. [STATE-004](modules/state-recovery.md#state-004) unknown-effect safety landed as a partial on Issue #31; it is not catalogue `verified`. Issue #42 adds cancel honesty (`cancel_requested` vs `cancelled`; no false quiescence) as a further [OQ-004](open-questions.md#oq-004) partial; unit tests are not catalogue `verified`. Issue #56 adds Chat conversation↔thread↔run reuse as a further [OQ-004](open-questions.md#oq-004) partial; unit tests are not catalogue `verified` and UAT remains local-machine-required on David-PC. Issue #62 adds managed deployment ownership (duplicate start + PID identity) as a further [OQ-007](open-questions.md#oq-007) partial; fixture/unit tests are not David-PC UAT and not catalogue `verified`.

A code/test pointer is a repository-relative **file** path, not a guessed symbol name or future directory. Put exact test names/selectors and commands in the evidence record. Actual commands belong in [commands](commands.md), and logical-to-physical bindings belong in [the repository map](repository-map.json).

## Evidence format

Store a concise, sanitised Markdown report under [evidence](evidence/README.md) using the [evidence template](templates/evidence.md). Link longer logs/artifacts from that report without embedding secrets. Record the tested source revision, dirty-tree qualifications, environment/platform, dependency/configuration fingerprints, fixtures, commands, actual results, skipped work and limitations. A report must distinguish recorded-tool tests, mocks, live tools and model judgements.

A `verified` catalogue row needs at least one evidence object with this shape (this is a format illustration, not a pre-existing verification claim):

```json
{
  "path": "specs/evidence/REPLACE_WITH_ACTUAL_REPORT.md",
  "code_revision": "REPLACE_WITH_FULL_TESTED_GIT_COMMIT_SHA",
  "requirement_sha256": "REPLACE_WITH_DIGEST_FROM_CHECKER",
  "environment": "REPLACE_WITH_TESTED_PLATFORM_AND_CONFIGURATION",
  "result": "passed"
}
```

The checker enforces real file paths, digest shape, a 40- or 64-character hexadecimal Git object ID, nonempty environment and passing result. It checks the digest against the requirement's current text/acceptance block, normalising line endings. It cannot establish that the reported commit was genuinely tested or that the evidence is sufficient; reviewers verify those claims.

Evidence may test a code commit and be committed in a later documentation-only commit. State that relationship. Do not claim an unknown future commit as the tested revision. Dirty-tree results may be retained as preliminary evidence, but must be repeated on the final code tree before an unqualified verified claim.

## Invalidation rules

Any relevant change to requirement semantics, contract, code, fixture, model/runtime/framework version, permissions or environment triggers an impact review. Rerun affected checks or downgrade the requirement to `partial` and explain the gap. A text digest catches document edits; it does not replace code-impact analysis. Keep historical reports, but remove or replace stale evidence objects from a current verified claim.

A failing or skipped required test cannot become a passing result by changing a catalogue field. One passing unrelated test does not verify a broad requirement. Maintain separate evidence for claims that span different environments; Windows support is not established by Linux-only results.

## Required product gates as code is introduced

Introduce each gate with its first affected implementation, not after the project is considered complete:

| First implementation | Gate to add and register |
| --- | --- |
| Shared data/API/registry contracts | Schema validation, compatible/incompatible fixtures and generated-output freshness, including newly generated or removed files. Slice 1 freshness is registered as a required check on public `main` ([commands](commands.md#check-shared-contract-freshness)); it is not catalogue `verified`. Remaining fixture/compatibility gates stay open. |
| Concrete module/package layout | Import/dependency boundary checks for the agreed direction |
| Model/runtime integration | Real managed deployment, companion-file resolution and requested/applied-setting evidence |
| Tool/worker execution | Permission, cancellation, denied-access and real filesystem/process checks |
| Durable runs/recovery | State transitions, crash/effect reconciliation and no-duplicate continuation checks |
| Snapshots/branching | Consistent capture, isolated restore and parent-preservation checks |
| Live Lab cases | Restored starting inputs and recorded-tool versus live-tool distinction |

The specification-only workflow must not remain the sole required check after these features exist. Add real commands and CI/controlled-environment gates rather than relabel this workflow as product verification. Backend unittest, desktop type-check/build, shared-contract freshness and specification-integrity now have registered required checks on public `main` ([commands CI scope](commands.md#ci-scope)); that does not invent the remaining table rows below, and a green product-command job is not catalogue `verified` or stage acceptance.

## Build-stage acceptance from revision 0.5

The sequence below preserves the source's [build order](sources/README.md#build-order). It groups evidence without duplicating a second implementation-status tracker.

**First — managed inference.** Demonstrate bundles/profiles/deployments/run records, Hugging Face import, llama.cpp execution and actual applied settings through the LangChain adapter, including supported advanced controls. Principal requirements: MOD-001 through MOD-006 and the relevant backend/state contracts.

**Second — complete agent task.** In a minimal interface, edit real files, execute tests, open/inspect a result, stream progress and return evidence. Exercise workers, context capture, approvals, cancellation and recovery. Repeat through LangGraph, then with fresh context against retained files/memory. Principal requirements: AGT-001 through AGT-006, WF-001, WF-002, ENV-001 through ENV-003 and STATE-001, STATE-002, STATE-004.

**Third — reuse and experimentation.** Demonstrate editable memory/skill drafts, snapshot-aware branching and run-to-Lab capture using shared configurations. Prove restored inputs, visible setting differences, isolated branches and live/recorded evaluation. Principal requirements: STATE-003, STATE-005 and LAB-001 through LAB-004.

**Fourth — optional integrations.** Add background consolidation, experimental rubric/interpreter integration, MCP Apps and voice through the same contracts. Verify access/logging and core operation with extensions absent. Principal requirements: ARCH-007, ENV-005, ENV-006, REG-004 and the affected integration requirements.

**Long-run acceptance — not a separate harness.** Exercise AGT-003 beyond observed upstream defaults without hidden task quotas, duplicated actions or lost state. Test optional budgets separately and preserve the actual stop/pause/failure reason.

## Review and release evidence

Before a stage exit or release, inspect the relevant requirement rows, open questions and deviations. Record which checks ran at which revision/environment. A stage with an unverified critical boundary remains incomplete even when the interface looks complete. Do not require optional fourth-stage integrations to prove the second-stage core experience.
