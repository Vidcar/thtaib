# ADR-0001: Adopt repository specifications and controlled maintenance

**Decision status and approval:** see [the catalogue](../catalog.json). Initially a proposal.

## Context

Revision 0.5 selects the workbench's principal components and ownership boundaries but is not a repository maintenance process. Future coding agents need a reliable reading path, requirements, explicit unknowns and evidence rather than an increasingly duplicated set of documents. No application repository has been inspected while preparing this pack.

## Proposed decision

Adopt [the specification index](../README.md), focused architecture/module specifications, [AGENTS.md](../../AGENTS.md), catalogue/repository-map conventions, [governance](../governance.md), [verification](../verification.md) and review controls as the repository's working baseline. Preserve the supplied Word document as a hashed, non-editable source archive rather than a parallel living specification.

Use stable requirement IDs with one normative home. Separate approval status from implementation status. Keep actual paths and commands explicit; leave unknown choices open with a blocking point. Pair behaviour/code/contract changes with matching specifications and meaningful verification in the same reviewed change. Require human approval for architectural changes.

The contract-generation convention is separately described in [ADR-0002](ADR-0002-contract-authoring.md); approve it explicitly rather than treating it as an inherited source decision.

## Consequences

Agents have one entry point and cannot legitimately declare completion from a visual mock or a document checkbox. Small compliant fixes do not require new ADRs. Important boundary changes do. Lightweight structural checks catch some drift, while semantic compliance and review controls still require product tests and human/repository enforcement.

The initial catalogue truthfully contains unassessed product requirements. Existing code may require assessment and deviations; adoption does not imply deleting it or restarting the project.

## Approval and application

Use [repository setup](../repository-setup.md). Record the real approving reviewer, review reference and date in the catalogue, together with the approved document statuses. No approval has been manufactured in this pack. Review the source extraction and any intentional adjustment before acceptance.

## Verification

Run the specification checker and its regression tests, confirm the archived source hash, inspect all intended pointers, and verify review controls in the actual host. First implementation tasks must establish real code paths/commands and the relevant product gates. No application behaviour is verified by accepting this decision.
