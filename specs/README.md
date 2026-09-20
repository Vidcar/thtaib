# Specification index and authority

## Reading path

[AGENTS.md](../AGENTS.md) defines working rules; [README.md](../README.md) covers setup and launch; [thtaib-vision.md](../thtaib-vision.md) is David's current product intent. Then read [architecture](architecture.md) and the affected module below for boundaries and contracts, and [commands](commands.md) for checks.

## Authority

Current user instructions take precedence. The supplied vision supersedes older product framing where they conflict; it is not an implementation claim. Contracts elaborate that intent; generated contracts define wire shapes; code is what runs; tests and live evidence establish what has been checked. Investigate mismatches rather than rewriting intent to match defects.

[The catalogue](catalog.json) owns implementation status and evidence. [The delivery map](../docs/delivery-feature-map.md#next-path) owns the short next path. ADRs preserve rationale, not superseded process instructions. [Revision 0.5](sources/README.md) is historical provenance, not a competing specification. **Workflows** is the intended area; **Agent run / Builder** remain existing UI and legacy contract terminology.

Requirement IDs (`ARCH-`, `MOD-`, `AGT-`, `WF-`, `ENV-`, `STATE-`, `REG-`, `API-`, `LAB-`, `CTT-`) have one definition/acceptance block and one catalogue row. Retire rather than delete or reuse them. Document statuses are `accepted`, `draft`, `superseded` and `informational`; requirement statuses follow [verification](verification.md).

## Contracts and references

| Subject | Home |
| --- | --- |
| Ownership, processes, persistence, permissions, effective setup | [architecture.md](architecture.md) |
| Model bundles, profiles, deployments and compatibility | [modules/models.md](modules/models.md) |
| Shared harness, Chat continuity, budgets and Workflows | [modules/agents-workflows.md](modules/agents-workflows.md) |
| Workers, tools, MCP, ComfyUI and interactive panels | [modules/environments-tools.md](modules/environments-tools.md) |
| Databases, history versus project, snapshots, effects and knowledge | [modules/state-recovery.md](modules/state-recovery.md) |
| Integration definitions and consumers | [modules/registry.md](modules/registry.md) |
| Backend routes, desktop trust and presentation | [modules/backend-desktop.md](modules/backend-desktop.md) |
| Model Lab and Task cases | [modules/lab-evaluation.md](modules/lab-evaluation.md) |
| Shared contract authoring | [contracts.md](contracts.md) |
| Status and evidence | [catalog.json](catalog.json), [verification.md](verification.md) |
| Logical locations and actual commands | [repository-map.json](repository-map.json), [commands.md](commands.md) |
| Remaining design uncertainty and known mismatches | [open-questions.md](open-questions.md), [deviations.md](deviations.md) |
| Architectural rationale | [decisions/](decisions/README.md) |
| Historical source and pinned upstream references | [sources/README.md](sources/README.md), [sources/upstream.md](sources/upstream.md) |
| Terminology | [glossary](../docs/glossary.md) |
| Optional authoring templates | [feature](templates/feature.md), [module](templates/module.md), [decision](templates/decision.md), [evidence](templates/evidence.md) |
