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

Accepted specifications define intended behaviour. Generated contracts define exact wire shapes. Code is what runs. Tests and evidence establish what has been checked. When they disagree, the disagreement is a defect, an open question or a proposed change, never a reason to quietly rewrite the requirement to match the code. Issues, task plans, chat transcripts, agent memory and generated documentation are not architectural authorities; a decision taken in conversation counts once it is recorded in an ADR or the changelog. Revision 0.5 is an archived source: after adoption the repository specifications govern.

Requirement IDs (`ARCH-`, `MOD-`, `AGT-`, `WF-`, `ENV-`, `STATE-`, `REG-`, `API-`, `LAB-`, `CTT-`) are stable. Each has one definition block with an anchor and an **Acceptance** line, and one catalogue row. Never renumber or reuse an ID; retire it instead. Document statuses are `accepted`, `draft`, `superseded` and `informational` (sources, references, templates). Requirement statuses are defined in [verification](verification.md).

## Change paths

- **Within the accepted design** (most work): specify the change with the [feature template](templates/feature.md) or the pull-request description, implement, validate, then update the affected specification text, catalogue rows, pointers and changelog in the same pull request. Say explicitly when intended behaviour is unchanged.
- **Changing the design** — a new execution owner, process boundary, public contract, persistence strategy, permission model or core dependency: write a short [ADR](templates/decision.md), get David's approval recorded in the catalogue, then implement against it. Do not merge dependent implementation before the decision.
- **Experiments**: a labelled branch with a recorded question and result; the result does not authorise production use.
- **Enforcement changes** — checker, catalogue schema, workflows, tests: state them plainly in the pull request. Never weaken a requirement, delete coverage, change a fixture or rewrite expected results to make current code pass; propose the behavioural change first.

Move or rename a document only with every link, catalogue path and repository-map binding repaired in the same change. Delete a stale document rather than leaving two sources that disagree.

<a id="issues-and-pull-requests"></a>
## Issues and pull requests

GitHub issues and pull requests are the durable work record: outcome, acceptance criteria, decisions, evidence and next action. Project Status is agent pipeline state only; the Milestone names the plain-English delivery (feature Milestones #3–#12 in the [feature map](../docs/delivery-feature-map.md)); no due dates or sprints. Ship when the acceptance criteria are met and the tip is shippable; each acknowledged leftover becomes a focused follow-up issue noted on the PR as `Deferred: #N`. The PR description follows the [template](../.github/pull_request_template.md) and reports commands actually run, live versus mocked versus recorded, and what remains unverified. Green required CI is merge enforcement, not product verification. `.github/CODEOWNERS` names the product owner; agents implement and propose, David accepts.
