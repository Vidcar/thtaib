# ADR-0004: Slim the specification pack and adopt it

**Status:** accepted. **Authority:** product owner instruction, 2026-09-19, recorded in [PR #84](https://github.com/Vidcar/thtaib/pull/84). **Supersedes:** [ADR-0001](ADR-0001-adopt-specification-pack.md). Historical process clauses are superseded by current [AGENTS.md](../../AGENTS.md).

## Context and decision

The pack had grown to about 36,600 words with duplicated issue diaries, while adoption remained pending and no requirements had live verification. Maintaining repeated history was crowding out delivery.

Adopt a smaller pack with one architecture, owning module contracts, stable requirement identities, a single status/evidence catalogue and short decision records. Keep link, ID, path, source-hash and evidence validation. Preserve the unchanged Revision 0.5 archive for provenance. Remove the separate adoption gate and example-only CODEOWNERS ceremony; adoption is recorded in the catalogue.

## Alternatives and consequences

Approving the heavyweight pack unchanged would retain the volume problem. Deleting specifications in favor of code and issues would lose intended contracts and traceable acceptance. Keeping issue diaries inside contracts would make current behavior harder to find.

The resulting authority and navigation are in [the index](../README.md); [verification](../verification.md) distinguishes implementation from scoped live evidence. Subsequent cleanup may remove redundant historical prose without changing requirement identities or verification guarantees. The later persistence decision is [ADR-0005](ADR-0005-application-record-storage.md).

## Validation at adoption

The specification checker and its tests passed in PR #84. This decision establishes no application capability evidence.
