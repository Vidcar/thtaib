# Specification index and authority

## Read only what is needed, but do not skip the shared rules

Start with [AGENTS.md](../AGENTS.md), [architecture](architecture.md) and [governance](governance.md). Then use the module table below. For an affected requirement, follow its catalogue entry to implementation/tests/evidence and check the linked open questions.

| Concern | Authoritative behavioural home |
| --- | --- |
| Whole-system ownership and boundaries | [Architecture](architecture.md) |
| Bundles, compatibility, profiles, inference deployments | [Models](modules/models.md) |
| Harness, outer workflows, delegation, context, budgets | [Agents and workflows](modules/agents-workflows.md) |
| Worker access, tool execution, MCP, ComfyUI and panels | [Environments and tools](modules/environments-tools.md) |
| Run/checkpoint links, project files, memory and snapshots | [State and recovery](modules/state-recovery.md) |
| Definitions, connections, capabilities and integration consumers | [Registry](modules/registry.md) |
| Backend coordination and desktop communication | [Backend and desktop](modules/backend-desktop.md) |
| Repeatable tasks, engine measurements and evaluation evidence | [Lab integration](modules/lab-evaluation.md) |
| Shared contract authoring and compatibility conventions | [Contracts](contracts.md) |

## Single homes for changing information

[The catalogue](catalog.json) is the only structured record of document status, adoption approval and per-requirement implementation claims. Requirement wording stays in its linked specification, not in the catalogue. [The repository map](repository-map.json) is the only binding from logical code/contract locations to actual paths. [Commands](commands.md) is the executable-command reference. [Open questions](open-questions.md) records unresolved design, and [deviations](deviations.md) records known divergence discovered by inspection.

A document can refer to another's rule, but must not maintain an independently editable copy of its detailed contract or status. Pointers are preferable to summaries that can diverge.

## Authority and conflicts

Accepted specifications define intended behaviour. Canonical code contracts define exact approved field/wire shapes. Implementation is what currently runs. Tests and evidence establish what has been checked. These must agree; none silently overrules a discovered inconsistency.

Architecture Decision Records explain approved changes and their rationale. An accepted decision must be accompanied by matching specification changes in the same reviewed change; an ADR is not permission to leave conflicting normative documents. Historical decisions remain historical when superseded.

Task plans, issues, prompts, handoffs, agent memory and generated documentation are not independent architectural authorities. Maintainer direction that changes architecture must be recorded through the change procedure. A code/spec discrepancy is a defect, open question or proposed change, not an invitation to rewrite the requirement after the fact.

The original Word document is an archived source. During adoption, compare the extraction with that source and resolve discrepancies explicitly. After adoption, current accepted repository specifications govern; do not keep revising both versions.

## Status vocabulary

**Document status:** `baseline` means extracted from revision 0.5 but not yet formally adopted into this repository; `draft` means proposed; `accepted` means approved with a recorded review reference; `superseded` means retained for history with a replacement recorded in its text. Source/reference/template documents are informational even when their inclusion in the pack is accepted.

**Implementation status:** `unassessed` means no inspection was performed; `planned` means assessed and not implemented; `partial` means incomplete or no longer fully evidenced; `verified` means the current scoped claim has implementation/test pointers and passing evidence; `retired` means a preserved requirement ID is no longer active. These states never follow automatically from document approval.

Every current requirement has one unique ID and one catalogue entry. Do not renumber IDs to tidy the files. Keep a retired requirement's heading and replacement explanation; do not reuse its ID. New normative documents and new requirement IDs must be registered in the same change.

## Additional working references

Use [verification](verification.md), [repository setup](repository-setup.md), [decisions](decisions/README.md), [source provenance](sources/README.md), [upstream links](sources/upstream.md), [templates](templates/README.md) and [the glossary](../docs/glossary.md). Bound application paths and registered commands exist where the catalogue and [commands](commands.md) say they do; that is not a `verified` product claim and is not a second copy of [AGENTS.md](../AGENTS.md).
