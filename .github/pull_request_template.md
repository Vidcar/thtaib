## Outcome and scope

Describe the actual change. Link the task and affected requirement IDs/specifications.

## Architecture and specification impact

Choose and explain: **within accepted design** / **approved architecture change** / **proposal only**.

- Affected boundaries, contracts, data and permissions:
- ADR and genuine human approval reference, when required:
- Specification changes, or why intended behaviour is unchanged:
- Open questions/deviations and compatibility/migration handling:

## Verification actually performed

| Command / check | Platform / configuration | Result | Evidence |
| --- | --- | --- | --- |
| Replace with commands actually run | Replace | Passed / failed / skipped | Real report or log |

Distinguish product tests from specification tooling, live tools from recordings/mocks, and executable checks from model judgements. Explain every required skipped check. Do not call unrun checks passing.

## Drift and enforcement review

- [ ] Requirement IDs, implementation status and real code/test/evidence pointers are updated where affected.
- [ ] Relevant changed behaviour is verified, or claims are downgraded and gaps recorded.
- [ ] Moved links, repository-map bindings, commands and ownership patterns are repaired.
- [ ] Shared contracts/generated consumers/migrations are aligned, or not affected with explanation.
- [ ] Specification checker and checker regression tests passed on this change.
- [ ] Changes to instructions, catalogue, checker, tests, workflows or permissions are explicitly identified for human review.
- [ ] No secrets, large model files, private project data or unredacted context were added.

## Remaining limitations and next step

State incomplete/unverified work and the smallest next concrete step. Checkbox completion is an author statement, not independent proof or approval.
