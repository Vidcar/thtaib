# Commands and verification entry points

This file is the command reference. Commands below run from the repository root. Python 3.11+ is sufficient for the supplied specification tooling only; it does not select the application's Python version. No third-party packages are needed by these checks.

On Windows, use `py -3` instead of `python` when necessary. Do not change shell-specific quoting or install dependencies without checking the actual environment.

<a id="spec-integrity"></a>
## Check documentation and traceability structure

```text
python scripts/check_specs.py
```

Runs the [specification checker](../scripts/check_specs.py). It validates the registered documentation, relative file/anchor links in managed Markdown, requirement IDs, catalogue shape, available code/test/evidence pointers, bound repository paths, original-source hash, and structural evidence freshness for verified claims. It reports adoption state and unbound locations. It does not access the network or modify files.

<a id="checker-tests"></a>
## Test the checker itself

```text
python -m unittest discover -s tests/specs -p "test_*.py"
```

Runs [the checker regression tests](../tests/specs/test_check_specs.py), including deliberately invalid packs. These are governance-tool tests, not model/agent/integration tests.

<a id="adoption-check"></a>
## Require recorded adoption

```text
python scripts/check_specs.py --require-adopted
```

This is expected to fail on an unadopted pack. After [repository setup](repository-setup.md), it checks that adoption metadata and an active non-placeholder CODEOWNERS file exist. It cannot authenticate the stated human reviewer or inspect server-side branch protections. Those require maintainer confirmation in the hosting service.

<a id="requirement-hash"></a>
## Obtain the digest for a verified requirement

```text
python scripts/check_specs.py --requirement-hash MOD-001
```

Substitute the real requirement ID. Use the printed digest in passing evidence **only after** the current requirement has been checked. Updating a digest without rerunning/reviewing affected checks conceals drift and is prohibited.

<a id="baseline-comparison"></a>
## Check that historical requirement IDs were not removed

```text
python scripts/check_specs.py --base-ref FULL_BASE_COMMIT_SHA
```

Replace `FULL_BASE_COMMIT_SHA` with the actual full ID of the reviewed base commit. This additional check needs Git and the base history locally. It rejects an ID removed from both the current specification and its catalogue; retain the requirement as retired instead. It permits the first pack import when the base has no catalogue. It cannot identify a deliberately misleading rewrite that preserves the ID.

The pull-request workflow supplies the base commit through `SPEC_BASE_REF` and fetches the history. Push/manual runs still perform the ordinary integrity check; an unset base does not establish historical continuity.

## Commands not established yet

Application bootstrap/start/build/type-check, contract generation/freshness, import-boundary checks, unit/contract/integration tests, Windows packaging and migrations are not available in this pack. Resolve the relevant [open questions](open-questions.md) and bind actual files in [repository-map.json](repository-map.json).

When a command is implemented, replace the relevant unavailable statement with its exact working command, prerequisites, working directory, platform, expected effect and verification scope. Add it to CI where appropriate in the same change. Never document a guessed `npm test`, `pytest`, `uv` or Docker command as an existing entry point.

## CI scope

The [workflow](../.github/workflows/specs.yml) invokes the first two commands on Windows and Linux, with read-only repository permissions and no product credentials. Its job timeout limits the CI check, not an application agent run. Stable status-check names are documented in [repository setup](repository-setup.md). Product gates must be added as their first real implementation is introduced.
