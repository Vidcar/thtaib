# Adopt this pack and enable repository controls

This procedure is for a human maintainer or an agent explicitly helping that maintainer. Adoption approval and technical verification are different things. Section 3 records the locked public-`main` required-check reality; the checker still cannot inspect server-side protections.

## 1. Integrate without overwriting existing authority

Create a review branch and merge the pack into the repository root. Compare existing instructions/specifications/workflows before replacing them. Preserve unrelated code and Git history. Resolve the extraction against the [archived source](sources/README.md); identify any intentional design change rather than hide it in wording.

Read [ADR-0001](decisions/ADR-0001-adopt-specification-pack.md) and [ADR-0002](decisions/ADR-0002-contract-authoring.md). Approve them together or leave the unapproved proposal clearly `draft`. Do not reopen source-derived stack choices merely to adopt the documentation process.

## 2. Configure real reviewers

Copy [CODEOWNERS.example](../.github/CODEOWNERS.example) to `.github/CODEOWNERS`, replacing **all** placeholder handles with real maintainer accounts/teams that have repository write access. Remove the second handle if there is only one eligible maintainer. Do not invent David's or his son's GitHub identity from names or prior context.

The example makes human maintainers owners of all paths initially. That protects new contracts, tests, manifests and instruction files without relying on guessed code folders. As the team grows, more specific ownership may be added, but governance and critical-boundary changes must still have human ownership. The last matching CODEOWNERS pattern wins; two owners on a line mean either can approve, not that both are required.

CODEOWNERS must be on the pull request's base branch for normal review routing. A file alone does not enforce approval. Required code-owner review is a separate branch-protection setting from the required status checks in section 3; it is **not** one of those configured contexts and is **not** an open ask. Pro is unnecessary on this public repository. Consult the [official code-owner documentation](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/about-code-owners).

## 3. Run checks; required status checks on public main

Run the working commands in [commands](commands.md). The following GitHub Actions jobs exist. Their status-check names (workflow job `name:` fields) are **required** on public `main` with **strict tip** (`strict: true`). Merges need those checks green on the pull-request tip. Agents keep tip-gating (`behind_by` 0 plus green required checks on that tip). Do not invent extra required checks beyond this live list:

```text
backend-unittest (ubuntu-latest)
backend-unittest (windows-latest)
desktop-typecheck-build (ubuntu-latest)
desktop-typecheck-build (windows-latest)
shared-contract-freshness (ubuntu-latest)
shared-contract-freshness (windows-latest)
spec-integrity (ubuntu-latest)
spec-integrity (windows-latest)
```

Those names come from [backend.yml](../.github/workflows/backend.yml), [desktop.yml](../.github/workflows/desktop.yml), [contracts.yml](../.github/workflows/contracts.yml) and [specs.yml](../.github/workflows/specs.yml). Green required CI is **not** catalogue `verified` and **not** build-stage product acceptance.

**Current reality (locked, [Issue #76](https://github.com/Vidcar/thtaib/issues/76); supersedes the [Issue #36](https://github.com/Vidcar/thtaib/issues/36) private-free / advisory-only hosting stance):** this repository is **public**. Classic branch protection on `main` requires the status checks above with strict tip. Pro is unnecessary. There is **no open ask** for a Pro upgrade. Do not treat “advisory only forever / private free 403 / enable required checks later” as current guidance. Closed #36 acceptance-criteria history is unchanged; this section records the later public + required-checks decision. See [official protected-branch documentation](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches).

A pull-request author cannot supply their own independent approval. Use the other eligible maintainer, or a properly separate agent/contributor identity reviewed by a human; do not defeat the rule with shared administrator credentials. Green required CI does not replace that human review.

Use an ordinary `pull_request` context, read-only repository permissions, hosted runners and no secrets for these checks. Do not move untrusted code execution to `pull_request_target` or privileged self-hosted workers to bypass a failure. Adding product checks may need separate controlled environments and an explicit trust review.

## 4. Record adoption, without claiming implementation

After genuine human approval, update [catalog.json](catalog.json): set `adoption.state` to `accepted`; fill `adoption.approval` with the real `reviewer`, review `reference` and ISO `date`; and set the approved documents' statuses to `accepted`. Keep an unapproved document `draft`. A single recorded adoption review may approve the initial document set explicitly, including both ADRs when agreed. Do not use placeholder URLs or fabricated approval comments.

For every accepted document, set `approval_reference` to its actual review reference. The same adoption review may be referenced by all documents it explicitly approves; later documents must point to their own approval, not inherit an old review automatically. Source/reference/template inclusion may be accepted without turning those materials into normative requirements.

Leave implementation rows `unassessed` until inspected. Accepting the architecture does not set any feature to `verified` and does not resolve the open questions.

Run:

```text
python scripts/check_specs.py --require-adopted
```

After adoption is recorded, the normal checker also applies its adoption-file checks. The checks confirm local metadata and a non-placeholder ownership file only. They cannot inspect server-side branch protections. Public `main` currently has the required status checks (strict tip) recorded in section 3; the checker does not prove that configuration. Adoption still needs genuine human review; green required CI does not replace that review or become catalogue `verified`.

## 5. Bind implementation locations and introduce real gates

Have the next agent inspect the actual repository and set existing paths in [repository-map.json](repository-map.json). Every unbound entry states the point before which it must be resolved. For a new repository, approve the scaffold/dependency setup under OQ-001, create it, then bind its real paths. Avoid creating empty placeholder application files just to make a path checker pass.

Register actual setup/build/test/generation commands in [commands](commands.md). Add contract-generation and module-boundary checks with the first shared contracts/packages, and real integration checks with the first runtime/worker implementations. Until then, a green specification workflow has only its stated documentation scope.

## Agent-tool instruction support

Keep [AGENTS.md](../AGENTS.md) as the central entry point. Check that the actual coding tool reads it; the open format is documented at [agents.md](https://agents.md/). A tool-specific instruction file should contain only a pointer and any unavoidable tool-local convention, not a separate copy of the architecture. Never rely on a tool's name alone as evidence it loads these rules.
