# Governance and drift prevention

This is a proposed repository working policy from the accompanying planning discussion. Adoption is recorded through [ADR-0001](decisions/ADR-0001-adopt-specification-pack.md), not assumed from the file's existence.

## Ownership and approval

David and his son are the architecture maintainers described by revision 0.5. Real reviewer identities and repository privileges must be configured through [repository setup](repository-setup.md). Agents may implement decisions and propose changes; they do not approve their own architecture changes or alter repository protections.

A module has a behavioural owner, listed in [the catalogue](catalog.json). That label is a responsibility boundary, not a fabricated GitHub username. Human code ownership is configured separately.

## Choose the correct change path

**Within the accepted design:** implement the change, add appropriate checks, repair pointers and update affected explanations in one pull request. State the affected requirement IDs and either the specific specification change or why intended behaviour is unchanged. A spelling fix does not need an ADR.

**Changing the design:** create a short [decision record](templates/decision.md) before dependent implementation. Identify the proposed change, source/current requirement, alternatives actually considered, rationale, affected contracts/data/security, migration/rollback, verification and unresolved risk. The maintainer approves the decision and matching specification edits. Implement against that approved baseline in a subsequent change, or in an explicitly approved combined change. Do not merge dependent architecture changes without approval.

Decision triggers include replacing a core framework, adding an execution owner or process/service boundary, changing public contracts or persistent compatibility, changing access/recovery/snapshot guarantees, or weakening the maintenance/verification rules. Ordinary adapter-specific private code choices do not need an ADR.

**Experiments:** a time-bounded investigation may use a disposable branch and clearly labelled test assets. Record the question and evidence. Its result does not authorise production use or silently resolve the decision. Time bounds on development investigations/CI do not establish product run budgets.

## The normal change loop

Before editing, read the current baseline and linked open questions, then identify requirements and affected boundaries. During implementation, keep meaningful tests and a specification-impact note. Before review, update affected normative text, code contracts, generated outputs, consumers, migration handling, pointers and evidence together. Before merge, obtain required human approval and passing applicable checks on the latest reviewed changes.

No blanket rule requires a meaningless documentation edit for every code change. A no-spec-change explanation is valid when behaviour remains compliant. Conversely, changing a requirement ID reference or a timestamp is not a substantive review.

## Keep evidence from going stale

The [verification guide](verification.md) defines evidence. Each verified catalogue entry records a digest of its current normative requirement block. A wording change makes that evidence structurally stale until reviewed and refreshed with real checking; do not mechanically substitute a new digest to conceal the change.

Implementation, contract, fixture, dependency, environment or policy changes can invalidate evidence even when requirement text is unchanged. The modifying pull request must identify affected requirements, rerun the relevant checks or downgrade them to `partial` and record the gap. The supplied checker cannot infer arbitrary semantic code impact. A reviewer must check that impact explicitly.

Move/rename changes repair all links, catalogue pointers, repository-map bindings, commands and ownership patterns in the same change. No invisible aliases, duplicate authoritative contracts or unexplained abandoned documents.

## Keep unresolved decisions and deviations visible

Use [open questions](open-questions.md) for a design choice not yet made. Each entry records its owner, blocking point and evidence needed. Resolve it by linking the approved ADR/spec changes; retain the history. Do not turn an arbitrary implementation into the answer.

Use [deviations](deviations.md) when actual code is known to differ from the intended design. Record affected IDs, observed behaviour, risk, owner, handling decision and a review/expiry trigger. An approved temporary deviation is not a permanent specification change. Silence or an expired waiver is not approval. Unassessed code is not a deviation until inspected.

## Dependencies and documentation versions

Exact installed dependency versions belong in the repository's lockfiles/runtime manifests once established, not repeated in this guide. Supported ranges/capabilities and experimental status belong in integration definitions and compatibility records. Decision rationale belongs in ADRs. Bind real paths through [the repository map](repository-map.json).

For an upgrade, inspect release notes/documentation for the pinned and proposed versions; review configuration defaults, contract changes, checkpoint/storage compatibility and behaviour. Run affected integration tests, update generation tools/outputs if necessary, and record migration or rollback. A dependency bot may propose an update but cannot establish compatibility by itself.

References under [upstream links](sources/upstream.md) are discovery pointers. A moving `latest` or `main` page is not version-pinned evidence. Record a version-specific source or commit with an integration's verification. Do not copy upstream manuals into this repository.

## Review cadence

Review affected specifications on every relevant change. At each build-stage exit and before a release, reconcile implemented boundaries with specifications, open questions, deviations, compatibility and evidence. Check platform claims against actual platform results. Identify the release's specification baseline by its Git commit/tag; do not add a second global revision counter to every Markdown file.

For a long-running development branch, recheck the baseline after rebasing and before continuing affected work. For an idle project, repeat the dependency/security and environment checks before restarting real privileged execution; the passage of time alone is not proof of compatibility.

## Protect the process

Protect agent instructions, specifications, catalogues/maps, shared contracts, critical tests, dependency manifests, CI workflows and the checker itself. Require review of CODEOWNERS as well. [Repository setup](repository-setup.md) explains the external controls; text instructions cannot implement permissions.

A check running code supplied by a pull request cannot prove that its own enforcement has not been weakened. Human review of guard changes and independent repository protections remain necessary. Keep agent credentials unable to administer or bypass those controls. Do not use privileged CI contexts to run untrusted pull-request code.
