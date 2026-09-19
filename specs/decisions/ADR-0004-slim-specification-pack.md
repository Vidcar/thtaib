# ADR-0004: Slim the specification pack and adopt it

**Status:** accepted. **Approval:** product owner instruction in Project chat, 2026-09-19; recorded via [PR #84](https://github.com/Vidcar/thtaib/pull/84). **Supersedes:** [ADR-0001](ADR-0001-adopt-specification-pack.md).

## Context

After roughly one hundred commits the pack governing the repository had grown to about 36,600 words over about 13,000 lines of application code. Twenty-two "Locked milestone defaults (Issue #N)" sections were embedded in the module specifications, several duplicated verbatim; hedging phrases were repeated dozens of times; the catalogue held zero `verified` rows and no evidence; the pack itself was still `adoption: pending` with a draft adoption ADR and an example-only CODEOWNERS file. Agents were obeying a process nobody had approved, and most of each change went into maintaining it. The independent technical assessment of 2026-09-19 recommended right-sizing the pack and making the adoption decision.

## Decision

1. Adopt the slimmed pack as the repository's working baseline: [AGENTS.md](../../AGENTS.md) as the entry point; [working rules](../README.md); one [architecture](../architecture.md) document of intended behaviour; module specifications on one fixed template; short ADRs plus this [changelog](changelog.md) in place of issue-log sections inside specifications; one machine-readable [catalogue](../catalog.json) whose `verified` status means live evidence; a [feature specification template](../templates/feature.md) that a change is specified against before implementation.
2. Requirement IDs are preserved unchanged (ARCH, MOD, AGT, WF, ENV, STATE, REG, API, LAB, CTT families). Decision content from the removed sections moves to the changelog; behaviour that is still intended moves into the module behaviour sections.
3. The catalogue statuses are `planned`, `built`, `verified`, `retired` with the operational definitions in [verification](../verification.md). `verified` requires evidence from the real-model CI smoke tier or David-PC UAT at a recorded commit.
4. The checker keeps link, anchor, ID, catalogue-shape, pointer, source-hash and evidence-digest validation and adds a per-requirement `verifiable_by` tier list so a tiny-model CI run can only verify plumbing requirements. The adoption gate (`--require-adopted`) and the CODEOWNERS file and checks are removed; adoption is recorded once in the catalogue with this approval. Ownership is stated in AGENTS.md: agents implement and propose, David accepts.
5. The Revision 0.5 source document and its page map are preserved unchanged.
6. The ADR triggers from the previous governance guide are kept in full: a new execution owner, process boundary, public contract, persistence strategy, permission model or core dependency; a change to access, recovery or snapshot guarantees; any weakening of the verification rules. The CI-security, agent-credential, dependency-upgrade and rebase-recheck rules move to [working rules](../README.md) rather than being dropped.

## Alternatives considered

Keep the heavyweight pack and approve it as-is: rejected, because the volume was the problem, not the lack of a signature. Delete the pack and rely on code and issues: rejected, because the owner wants agents to specify a feature and build from the specification, which needs stable IDs, an architecture home and an evidence record. Keep the issue-log sections but deduplicate: rejected, because an issue log inside an architecture document keeps growing and never says what the current behaviour is.

## Consequences

Agents read far less before working and have one place for each kind of fact. History is not lost: every removed default is in the changelog with its issue. Statuses now say something: `built` means unit-tested code exists, `verified` means seen working live. The enforcement system (checker, tests, catalogue schema) changes in the same reviewed change; that change is explicitly flagged for review in its pull request. The persistence split (JSON files versus SQLite) is recorded as [OQ-017](../open-questions.md#oq-017) with a recommendation, not decided here.

## Verification

`python scripts/check_specs.py` and `python -m unittest discover -s tests/specs -p "test_*.py"` pass on the adopting change. No application behaviour is verified by this decision.
