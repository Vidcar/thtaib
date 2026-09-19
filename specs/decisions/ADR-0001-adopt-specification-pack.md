# ADR-0001: Adopt repository specifications and controlled maintenance

**Status:** superseded by [ADR-0004](ADR-0004-slim-specification-pack.md) on 2026-09-19. This record was never accepted; it is retained for history.

## Context

Revision 0.5 selected the workbench's principal components and ownership boundaries but was not a repository maintenance process. Future coding agents needed a reliable reading path, requirements, explicit unknowns and evidence rather than an increasingly duplicated set of documents.

## Proposed decision

Adopt a specification index, focused architecture/module specifications, `AGENTS.md`, catalogue/repository-map conventions, a governance guide, a verification guide and review controls as the repository's working baseline. Preserve the supplied Word document as a hashed, non-editable source archive. Use stable requirement IDs with one normative home; separate approval status from implementation status; pair behaviour, code and contract changes with matching specifications in the same reviewed change; require human approval for architectural changes.

## Outcome

The pack was used from 2026-09-18 without formal adoption. By 2026-09-19 it had grown well beyond the product it governed. The product owner approved a slimmed replacement instead; see ADR-0004 for what was kept, what was removed and why.
