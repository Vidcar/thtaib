# Specification pack: index and working rules

Start at [AGENTS.md](../AGENTS.md). This file says where each kind of fact lives, which document wins in a conflict, and how a change moves through the pack.

## Where things live

| Kind of fact | Home |
| --- | --- |
| Boundaries, process model, persistence, permissions, effective setup, build order | [architecture.md](architecture.md) |
| Bundles, profiles, deployments, compatibility, runtime pin | [modules/models.md](modules/models.md) |
| Harness, Chat continuity, budgets, Builder compilation | [modules/agents-workflows.md](modules/agents-workflows.md) |
| Workers, tools, MCP, ComfyUI, interactive panels | [modules/environments-tools.md](modules/environments-tools.md) |
| Databases, history versus project, snapshots, effects ledger, knowledge | [modules/state-recovery.md](modules/state-recovery.md) |
| Integration definitions and consumers | [modules/registry.md](modules/registry.md) |
| Backend routes, desktop trust, state honesty | [modules/backend-desktop.md](modules/backend-desktop.md) |
| Model Lab and Task cases | [modules/lab-evaluation.md](modules/lab-evaluation.md) |
| Shared contract authoring | [contracts.md](contracts.md) |
| Status of every requirement and document; evidence rows; adoption | [catalog.json](catalog.json) |
| Logical location → real path | [repository-map.json](repository-map.json) |
| Commands and CI | [commands.md](commands.md) |
| What `verified` means; evidence tiers and rows | [verification.md](verification.md) |
| Undecided design | [open-questions.md](open-questions.md) |
| Code known to differ from design | [deviations.md](deviations.md) |
| Why things are the way they are | [decisions/](decisions/README.md) and the [changelog](decisions/changelog.md) |
| Original vision and its page map | [sources/README.md](sources/README.md); upstream docs in [sources/upstream.md](sources/upstream.md) |
| Templates | [templates/feature.md](templates/feature.md), [module](templates/module.md), [decision](templates/decision.md), [evidence](templates/evidence.md) |
| Locked names | [docs/glossary.md](../docs/glossary.md); delivery plan in [docs/delivery-feature-map.md](../docs/delivery-feature-map.md) |

Each fact has one home. Other documents point to it rather than restating it.

## Authority

[AGENTS.md](../AGENTS.md) defines the current working process and delivery ownership. Current user instructions override older process rules. Accepted specifications define intended product behaviour; generated contracts define wire shapes; code is what runs; tests and live evidence establish what has been checked. A mismatch must be investigated, not hidden by rewriting requirements to match a defect.

Record consequential decisions in the relevant specification and a short ADR or changelog entry when useful for future agents. Routine technical decisions within the authorized outcome are agent-owned; Dave is asked about material unresolved product choices, cost or external effects, not to approve technical paperwork. Historical records retain their original text but do not impose superseded working rules. Revision 0.5 is an archived source.

Requirement IDs (`ARCH-`, `MOD-`, `AGT-`, `WF-`, `ENV-`, `STATE-`, `REG-`, `API-`, `LAB-`, `CTT-`) stay stable, with one definition/acceptance block and one catalogue row. Retire IDs rather than deleting or reusing them. Document statuses remain `accepted`, `draft`, `superseded` and `informational`; requirement statuses follow [verification](verification.md).

## Change paths

- **Ordinary work:** inspect the affected code and module boundary, state the intended outcome briefly, implement and run relevant local checks. The [feature outline](templates/feature.md) is optional. Update only facts that changed: behaviour, status/evidence, paths or commands. No mandatory no-op catalogue, map or changelog edits.
- **Consequential design:** record ownership, interfaces, failure behaviour, migration/rollback and the reason for the decision in the affected spec; use a short [ADR](templates/decision.md) when the rationale warrants a separate record. Agents own technical decisions within scope. Ask Dave before an unresolved material product change, cost or external action, and record the actual authorization without inventing approval.
- **Experiments:** label the question and result; do not turn an experiment into the default product path without validation.
- **Checks and enforcement:** explain changes to the checker, schema, workflows or tests. Preserve meaningful coverage and intended guarantees; never alter expectations merely to hide a failure. Review the diff and run affected checks.
- **Deviations:** record a meaningful temporary mismatch with its reason, mitigation and next action in [deviations](deviations.md). Do not silently extend an approved exception or discard its safeguards.

Repair links, catalogue paths and repository-map bindings when moving a document or component. Do not create placeholders to satisfy the checker. After a rebase, inspect relevant upstream changes before continuing.

## Dependencies

Exact versions live in lockfiles and runtime manifests. Consult pinned-version documentation or source when an integration depends on unfamiliar behaviour. For core upgrades, check release notes, defaults, contracts and storage/checkpoint compatibility, then run affected integration checks. Record migration/rollback when needed. Use the [upstream register](sources/upstream.md) for reusable version-specific findings; routine work does not require a new research report.

## Repository protection and CI

Run relevant validation locally first using [commands](commands.md). CI repeats selected checks as a merge guard; it does not replace Windows product validation or establish every feature works. Agents own resolving failures and merging once required checks pass. Do not bypass protection, weaken meaningful checks or move untrusted PR code to privileged execution.

Existing workflows use ordinary pull requests, read-only permissions, hosted runners and no product credentials. Keep that security boundary. Required checks and path filters are documented in [commands](commands.md#ci); changing protected-branch policy is separate from simplifying working instructions. Tool-specific instruction files should point to [AGENTS.md](../AGENTS.md) rather than duplicate it.

<a id="issues-and-pull-requests"></a>
## Issues and pull requests

Use GitHub records when they help delivery and continuity, not as a prerequisite for every action. A small change needs an outcome, relevant checks and any remaining limitation; omit irrelevant [PR template](../.github/pull_request_template.md) sections. Create a follow-up issue only for substantial deferred work needing tracking. Existing milestones and the [feature map](../docs/delivery-feature-map.md) provide planning context, not mandatory task administration.

Agents own implementation, technical review, validation and Git including merges. Dave supplies product intent and feedback on the usable result; he is not the required technical reviewer or test operator. Leave the next agent concise, current context in the existing repository/PR rather than requiring access to this conversation.
