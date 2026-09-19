# Adopt this pack and enable repository controls

This procedure is for a human maintainer or an agent explicitly helping that maintainer. It does not claim any settings are already enabled. Adoption approval and technical verification are different things.

## 1. Integrate without overwriting existing authority

Create a review branch and merge the pack into the repository root. Compare existing instructions/specifications/workflows before replacing them. Preserve unrelated code and Git history. Resolve the extraction against the [archived source](sources/README.md); identify any intentional design change rather than hide it in wording.

Read [ADR-0001](decisions/ADR-0001-adopt-specification-pack.md) and [ADR-0002](decisions/ADR-0002-contract-authoring.md). Approve them together or leave the unapproved proposal clearly `draft`. Do not reopen source-derived stack choices merely to adopt the documentation process.

## 2. Configure real reviewers

Copy [CODEOWNERS.example](../.github/CODEOWNERS.example) to `.github/CODEOWNERS`, replacing **all** placeholder handles with real maintainer accounts/teams that have repository write access. Remove the second handle if there is only one eligible maintainer. Do not invent David's or his son's GitHub identity from names or prior context.

The example makes human maintainers owners of all paths initially. That protects new contracts, tests, manifests and instruction files without relying on guessed code folders. As the team grows, more specific ownership may be added, but governance and critical-boundary changes must still have human ownership. The last matching CODEOWNERS pattern wins; two owners on a line mean either can approve, not that both are required.

CODEOWNERS must be on the pull request's base branch for normal review routing. A file alone does not enforce approval. Required code-owner review is **optional Pro/public-only**. On this private free-plan repository it is unavailable (classic branch protection and rulesets return **403** without Pro or making the repository public) and is **not** open human work. Consult the [official code-owner documentation](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/about-code-owners).

## 3. Run checks; required branch protection is optional Pro/public-only

Run the working commands in [commands](commands.md). The following GitHub Actions jobs exist and run as **advisory CI only**. Merges are **not** blocked by required checks. Current job names are:

```text
spec-integrity (ubuntu-latest)
spec-integrity (windows-latest)
backend-unittest (ubuntu-latest)
backend-unittest (windows-latest)
desktop-typecheck-build (ubuntu-latest)
desktop-typecheck-build (windows-latest)
```

The first pair is the [specification-integrity workflow](../.github/workflows/specs.yml). The backend and desktop names come from [backend.yml](../.github/workflows/backend.yml) and [desktop.yml](../.github/workflows/desktop.yml). Do not add invented contract-generation, import-boundary or integration required checks.

**Current reality (locked, [Issue #36](https://github.com/Vidcar/thtaib/issues/36)):** this repository stays **private** on a free personal GitHub account. Classic branch protection and rulesets return **403** without Pro or making the repository public. David will **not** upgrade to Pro. The workflows (`backend-unittest`, `desktop-typecheck-build`, `spec-integrity`) therefore run as **advisory CI only**. Merges are **not** blocked by required checks. Enabling required status checks, default-branch protection, or required CODEOWNERS review is **not** open human work and is **not** a product requirement.

Selecting those observed status names as required checks, and protecting the default/release branch (require pull requests, human approval, required code-owner review, required status checks, resolution of blocking discussions, dismissal of stale approvals, disable force-push/deletion, avoid agent/admin bypass), remains **optional Pro/public-only**. Features vary by plan and repository visibility. Do not claim equivalent enforcement when unavailable. See [official protected-branch documentation](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches).

A pull-request author cannot supply their own independent approval. Use the other eligible maintainer, or a properly separate agent/contributor identity reviewed by a human; do not defeat the rule with shared administrator credentials. Advisory CI does not replace that human review.

Use an ordinary `pull_request` context, read-only repository permissions, hosted runners and no secrets for these checks. Do not move untrusted code execution to `pull_request_target` or privileged self-hosted workers to bypass a failure. Adding product checks may need separate controlled environments and an explicit trust review.

## 4. Record adoption, without claiming implementation

After genuine human approval, update [catalog.json](catalog.json): set `adoption.state` to `accepted`; fill `adoption.approval` with the real `reviewer`, review `reference` and ISO `date`; and set the approved documents' statuses to `accepted`. Keep an unapproved document `draft`. A single recorded adoption review may approve the initial document set explicitly, including both ADRs when agreed. Do not use placeholder URLs or fabricated approval comments.

For every accepted document, set `approval_reference` to its actual review reference. The same adoption review may be referenced by all documents it explicitly approves; later documents must point to their own approval, not inherit an old review automatically. Source/reference/template inclusion may be accepted without turning those materials into normative requirements.

Leave implementation rows `unassessed` until inspected. Accepting the architecture does not set any feature to `verified` and does not resolve the open questions.

Run:

```text
python scripts/check_specs.py --require-adopted
```

After adoption is recorded, the normal checker also applies its adoption-file checks. The checks confirm local metadata and a non-placeholder ownership file only. They cannot inspect server-side branch protections. On this private free-plan repository those protections are unavailable and are not pending setup. Adoption still needs genuine human review; advisory CI does not replace that review.

## 5. Bind implementation locations and introduce real gates

Have the next agent inspect the actual repository and set existing paths in [repository-map.json](repository-map.json). Every unbound entry states the point before which it must be resolved. For a new repository, approve the scaffold/dependency setup under OQ-001, create it, then bind its real paths. Avoid creating empty placeholder application files just to make a path checker pass.

Register actual setup/build/test/generation commands in [commands](commands.md). Add contract-generation and module-boundary checks with the first shared contracts/packages, and real integration checks with the first runtime/worker implementations. Until then, a green specification workflow has only its stated documentation scope.

## Agent-tool instruction support

Keep [AGENTS.md](../AGENTS.md) as the central entry point. Check that the actual coding tool reads it; the open format is documented at [agents.md](https://agents.md/). A tool-specific instruction file should contain only a pointer and any unavoidable tool-local convention, not a separate copy of the architecture. Never rely on a tool's name alone as evidence it loads these rules.
