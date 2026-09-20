# Feature outline (optional)

Use this for a substantial change when it clarifies the work. For a small fix, a short plan or PR description is enough. Omit sections that add no useful information.

## Outcome

What the user can do afterwards; important scope exclusions.

## Component contract

Owning component, inputs/outputs, dependencies, failure behaviour and observable acceptance checks. Link existing module requirements rather than copying them. Identify any boundary or contract that changes.

## Approach and validation

Smallest complete implementation, material uncertainty and relevant local checks. Consult pinned upstream documentation/source where needed. Name live checks when model, tool or desktop behaviour requires them; do not present mocks as live evidence.

## Durable context

Update affected specifications, catalogue status/evidence or paths only when they change. Record consequential rationale once. If unfinished, leave the next concrete step, current branch and a reproduction/check command in the PR or existing project note.
