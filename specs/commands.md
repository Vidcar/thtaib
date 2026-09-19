# Commands and verification entry points

This file is the command reference. Specification commands below run from the repository root. Application commands name their working directory. Python 3.11+ is sufficient for the supplied specification tooling only; the backend requires Python 3.12.x via uv. No third-party packages are needed by the specification checks.

On Windows, use `py -3` instead of `python` for specification commands when necessary. Application commands use `uv` and `pnpm` and do not need `py -3`. Do not change shell-specific quoting or install dependencies without checking the actual environment.

Locked names are in [the glossary](../docs/glossary.md).

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

<a id="backend-install"></a>
## Install the backend

**Working directory:** `apps/backend`. **Platform:** Windows (supported target); also runs on Linux/macOS for smoke. **Prerequisites:** [uv](https://docs.astral.sh/uv/) and Python 3.12.x (uv can install 3.12).

```text
uv sync
```

Creates `.venv` and installs the locked dependencies from `uv.lock`, including the `workbench_backend` package.

<a id="backend-run"></a>
## Run the backend

**Working directory:** `apps/backend`. **Platform:** Windows (supported target); also runs on Linux/macOS for smoke. **Prerequisites:** `uv sync`.

```text
uv run python -m workbench_backend
```

Starts the FastAPI process on `127.0.0.1:8000`. This is provisional loopback HTTP for smoke. It does not close [OQ-002](open-questions.md#oq-002). `GET /health` returns the managed-inference identity. Model-manager routes are under `/v1`. Harness routes are `POST /v1/agent-runs`, `GET /v1/agent-runs/{id}`, `POST /v1/agent-runs/{id}/cancel`, and `GET /v1/agent-tools`. Lab routes are under `/v1/lab/` (workspaces, `cases/capture`, restore, rerun, engine-measurements). Knowledge routes are under `/v1/knowledge/` (entries, versions, edit, revert, config, context captures). OpenAPI/docs routes are disabled.

<a id="backend-test"></a>
## Test the backend

**Working directory:** `apps/backend`. **Platform:** Windows (supported target); also runs on Linux/macOS. **Prerequisites:** `uv sync`.

```text
uv run python -m unittest discover -s tests -p "test_*.py"
```

Runs the backend unittest modules, including model-manager API tests for bundles, GGUF inspect, settings bags and deployments, harness/adapter tests for AGT-001/002/005/006 and MOD-005, Lab capture/restore/rerun plus engine-unavailable checks for LAB-001…004 and STATE-003, and durable-knowledge checks for STATE-005 (create/edit/revert/conflict/protected-deny/retention-redaction and knowledge refs from Lab/harness). These are executable unit checks, not David-PC UAT and not catalogue `verified` evidence.

<a id="desktop-install"></a>
## Install the desktop

**Working directory:** `apps/desktop`. **Platform:** Windows (supported target); also runs on Linux/macOS for install/type-check/build. **Prerequisites:** Node.js ≥22 and <25 (develop on 24) and pnpm 10+.

```text
pnpm install
```

Installs the locked Electron, Vite, React, TypeScript and React Flow versions from `pnpm-lock.yaml`.

<a id="desktop-typecheck"></a>
## Type-check the desktop

**Working directory:** `apps/desktop`. **Prerequisites:** `pnpm install`.

```text
pnpm run typecheck
```

Runs `tsc --noEmit` for the renderer and Electron main/preload projects.

<a id="desktop-build"></a>
## Build the desktop

**Working directory:** `apps/desktop`. **Prerequisites:** `pnpm install`.

```text
pnpm run build
```

Type-checks, then Vite-builds the renderer and Electron main/preload into `dist/` and `dist-electron/`. This is the milestone evidence command. It does not produce an installer.

<a id="desktop-dev"></a>
## Run the desktop in development

**Working directory:** `apps/desktop`. **Prerequisites:** `pnpm install`. **Platform:** a machine that can open an Electron window (David-PC for UAT).

```text
pnpm run dev
```

Starts Vite as a development bundler and launches Electron. Vite's URL is not a product HTTP surface. Chat and Builder are not present. Optional Agent-run, Lab and Knowledge debug panels may call the harness, Lab and knowledge APIs. This is not Chat/Builder polish and does not close [OQ-016](open-questions.md#oq-016) or [OQ-014](open-questions.md#oq-014).

<a id="desktop-package"></a>
## Package a Windows installer

**Working directory:** `apps/desktop`. **Platform:** Windows. **Prerequisites:** `pnpm install`.

```text
pnpm run package
```

Runs the desktop build, then electron-builder with the NSIS target. An installer is **not** required for this milestone. Do not treat a missing installer as a failed scaffold.

## Commands not established yet

Contract generation/freshness, import-boundary checks, shared contract tests, integration tests, Docker product services and migrations are not available. Resolve the relevant [open questions](open-questions.md) and bind actual files in [repository-map.json](repository-map.json).

When a command is implemented, replace the relevant unavailable statement with its exact working command, prerequisites, working directory, platform, expected effect and verification scope. Add it to CI where appropriate in the same change. Never document a guessed `npm test`, `pytest`, `uv` or Docker command as an existing entry point.

## CI scope

The [workflow](../.github/workflows/specs.yml) invokes the first two commands on Windows and Linux, with read-only repository permissions and no product credentials. Its job timeout limits the CI check, not an application agent run. Stable status-check names are documented in [repository setup](repository-setup.md). Product gates must be added as their first real implementation is introduced. The backend unittest and desktop type-check/build commands above are local entry points; they are not additional required GitHub status names until a workflow is added for them.
