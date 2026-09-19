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
- **Changing the design** — a new execution owner, process boundary, public contract, persistence strategy, permission model or core dependency; a change to access, recovery or snapshot guarantees; or any weakening of the verification rules in [verification](verification.md): write a short [ADR](templates/decision.md), get David's approval recorded in the catalogue, then implement against it. Do not merge dependent implementation before the decision. A superseded ADR keeps its original text under a superseded banner; history is not rewritten.
- **Experiments**: a labelled branch with a recorded question and result; the result does not authorise production use.
- **Enforcement changes** — checker, catalogue schema, workflows, tests: state them plainly in the pull request and treat them as a change to the enforcement system. Never weaken a requirement, delete coverage, change a fixture or rewrite expected results to make current code pass; propose the behavioural change first. A check that runs code supplied by a pull request cannot prove its own enforcement was not weakened; a human reads guard changes.
- **Deviations**: a temporary deviation needs an owner, an approval reference, compensating controls and a review or expiry trigger. Silence or an expired waiver is not approval; do not extend one silently, remove its test or rewrite the specification to match it. Unassessed code is not a deviation until inspected.

Move or rename a document only with every link, catalogue path and repository-map binding repaired in the same change. Delete a stale document rather than leaving two sources that disagree. Do not create empty placeholder files to satisfy a path check. After rebasing a long-running branch, re-read the affected baseline before continuing; an earlier approval does not cover newly conflicting edits.

## Dependencies

Exact versions live in the lockfiles and runtime manifests, never in prose. Before an upgrade of llama.cpp, LangChain, LangGraph, Deep Agents or another core dependency, read the release notes and documentation for the pinned and proposed versions, check configuration defaults, contract changes and checkpoint/storage compatibility, run the affected integration checks, and record migration or rollback in the changelog or an ADR. A dependency bot can propose an update but cannot establish compatibility. A moving `latest` or `main` documentation page is not version-pinned evidence; record the version-specific source with the change ([upstream register](sources/upstream.md)).

## Repository protection and CI

CI runs on ordinary `pull_request` events with read-only permissions, hosted runners and no product credentials. Never move untrusted pull-request code to `pull_request_target` or a privileged self-hosted worker to get past a failure. Agent credentials must not be able to administer branch protection or bypass required checks; an agent never approves its own architecture change, and a pull-request author cannot supply their own review. Required checks are listed in [commands](commands.md#ci). A tool-specific instruction file (for Cursor, Copilot or another agent) contains only a pointer to [AGENTS.md](../AGENTS.md) and unavoidable local conventions, never a second copy of these rules.

<a id="issues-and-pull-requests"></a>
## Issues and pull requests

GitHub issues and pull requests are the durable work record: outcome, acceptance criteria, decisions, evidence and next action. Project Status is agent pipeline state only; the Milestone names the plain-English delivery (feature Milestones #3–#12 in the [feature map](../docs/delivery-feature-map.md)); no due dates or sprints. Ship when the acceptance criteria are met and the tip is shippable; each acknowledged leftover becomes a focused follow-up issue noted on the PR as `Deferred: #N`. The PR description follows the [template](../.github/pull_request_template.md) and reports commands actually run, live versus mocked versus recorded, and what remains unverified. Green required CI is merge enforcement, not product verification. Agents implement and propose; David accepts.
