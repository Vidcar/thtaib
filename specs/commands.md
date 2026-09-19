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

This is expected to fail on an unadopted pack. After [repository setup](repository-setup.md), it checks that adoption metadata and an active non-placeholder CODEOWNERS file exist. It cannot authenticate the stated human reviewer or inspect server-side branch protections. Reviewer identity still needs maintainer confirmation. Public `main` has required status checks (strict tip); names are in [CI scope](#ci-scope). Green required CI is not catalogue `verified`. See [repository setup](repository-setup.md).

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

Starts the FastAPI process on `127.0.0.1:8000` only (non-loopback `--host` is refused). This is the Issue #40 partial [OQ-002](open-questions.md#oq-002) bind; it does not close the remainder of that question and is not a remote-backend claim. `GET /health` remains a public smoke identity. Privileged `/v1` routes require header `X-Workbench-Local-Token` matching `%LOCALAPPDATA%\LocalAIWorkbench\state\desktop_backend_shared_secret` (or the portable `state\` sibling). Missing token → 401; wrong token → 403. Model-manager routes are under `/v1`. Compatibility routes are under `/v1/compatibility/` (records, assess, user overrides) plus `GET /v1/bundles/{id}/compatibility`. External-effect routes are under `/v1/effects` (dispatch, acknowledge, recover, reconcile; rollback is refused). Harness routes are `POST /v1/agent-runs`, `GET /v1/agent-runs/{id}`, `POST /v1/agent-runs/{id}/cancel`, and `GET /v1/agent-tools`. Chat routes are under `/v1/chat/` (conversations, start, cancel, transcript replace). Lab routes are under `/v1/lab/` (workspaces, `cases/capture`, restore, rerun, engine-measurements). Knowledge routes are under `/v1/knowledge/` (entries, versions, edit, revert, config, context captures). OpenAPI/docs routes are disabled.

<a id="backend-test"></a>
## Test the backend

**Working directory:** `apps/backend`. **Platform:** Windows (supported target); also runs on Linux/macOS. **Prerequisites:** `uv sync`.

```text
uv run python -m unittest discover -s tests -p "test_*.py"
```

Runs the backend unittest modules, including model-manager API tests for bundles, GGUF inspect, settings bags and deployments, Issue #21 runtime/pin/`flash_attn` valued-enum checks, Issue #31 MOD-006 provenance-separation and unverified≠incompatible checks, Issue #62 managed-deployment ownership checks (serialized/idempotent duplicate start, process identity before stop, foreign-healthy endpoint is not ownership, restart reconcile, connected non-destructive lifecycle; PID-reuse cases use fixtures/mocks and never kill unrelated user processes), harness/adapter tests for AGT-001/002/005/006 and MOD-005, Chat→harness wiring plus STATE-002 transcript≠project, filesystem-tools→project-storage, and Issue #56 Chat continuity checks (two-turn unique detail on the next model request; reopen-after-restart thread reuse; fresh conversation reset with retained project/knowledge; model-switch same thread; history-edit display-only), STATE-001 dual `application.sqlite` / `checkpoints.sqlite` path and JSON-linkage migration plus restart follow-run-to-checkpoint-id checks, STATE-004 unknown-effect safety (no silent replay; no external-effect rollback promise), Issue #42 cancel honesty (request→`cancel_requested`; confirm→`cancelled`; `cancel_requested` is not quiescent), Issue #61 Chat start rejection while the current run is live including `cancel_requested` (canonical `is_run_lifecycle_live`; `current_run_id` unchanged until confirmed stop), Lab capture/restore/rerun plus snapshot restore-integrity (missing tree / hash mismatch / unexpected files fail; empty snapshot round-trips) and engine-unavailable checks for LAB-001…004 and STATE-003, durable-knowledge checks for STATE-005 (create/edit/revert/conflict/protected-deny/retention-redaction and knowledge refs from Lab/harness), Issue #64 Knowledge-policy diagnostics/export (model_requests redaction/discard/expiry and case-export sanitize/block), Issue #35 WF-001 definition-compiler checks (mixed configuration/workflow compile; configuration links are not executable steps), and Issue #40 local-trust checks (shared-secret file under `state\`, loopback bind only, missing token → 401 and wrong token → 403 on privileged `/v1` routes including Chat/Lab/project-file ops), and Issue #57 effective-setup checks (selected profile per-request bag on the outbound request, distinctive memory/skill content loaded into the harness, capture/HTTP correlation, Chat-path write-policy preservation). These are executable unit checks, not David-PC UAT and not catalogue `verified` evidence.

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

Starts Vite as a development bundler and launches Electron. Vite's URL is not a product HTTP surface. Electron main reads or creates the LocalAppData `state\desktop_backend_shared_secret` and injects `X-Workbench-Local-Token` on requests to `http://127.0.0.1:8000`. The renderer does not hold the secret. Debug-quality Chat calls the embedded harness (compose, deployment/profile bind, project workspace path, Start/Cancel, streamed events, conversation↔thread↔run reopen). Follow-ups reuse the conversation thread; New conversation is a new thread. Optional Agent-run, Lab and Knowledge debug panels remain. This is not Chat/Builder polish and does not close [OQ-016](open-questions.md#oq-016) or [OQ-014](open-questions.md#oq-014). Pairing UAT is local-machine-required on David-PC.

<a id="generate-shared-contracts"></a>
## Generate shared OpenAPI and TypeScript contracts

**Working directory:** `apps/backend`. **Platform:** Windows (supported target); also runs on Linux/macOS. **Prerequisites:** backend `uv sync` and desktop `pnpm install` (pinned `openapi-typescript` lives in the desktop lockfile).

```text
uv run python ../../scripts/generate_shared_contracts.py
```

Exports JSON Schema and OpenAPI from the canonical Pydantic shared-contract models, then runs pinned `openapi-typescript` 7.13.0 via `node` and the installed `bin/cli.js` (not a bare `pnpm` argv — Windows `CreateProcess` does not resolve `pnpm.cmd`). Generated files must not be hand-edited. This does not publish product `/openapi.json` and does not implement Electron trust or harness cancel behaviour.

<a id="check-shared-contract-freshness"></a>
## Check shared-contract freshness

**Working directory:** `apps/backend`. **Platform:** Windows (supported target); also runs on Linux/macOS. **Prerequisites:** the generate-command prerequisites.

```text
uv run python ../../scripts/generate_shared_contracts.py --check
```

Regenerates artifacts into a temporary tree and fails if any generated output is changed, removed, or newly produced relative to the committed files. A clean worktree must pass. This is the CTT-001 freshness gate, not catalogue `verified` evidence.

<a id="desktop-package"></a>
## Package a Windows installer

**Working directory:** `apps/desktop`. **Platform:** Windows. **Prerequisites:** `pnpm install`.

```text
pnpm run package
```

Runs the desktop build, then electron-builder with the NSIS target. An installer is **not** required for this milestone. Do not treat a missing installer as a failed scaffold.

## Commands not established yet

Import-boundary checks, integration tests, Docker product services and migrations are not available. Shared-contract generation/freshness and the Slice 1 contract unit tests are registered above and run through backend unittest plus the freshness workflow. Resolve the remaining [open questions](open-questions.md) and bind actual files in [repository-map.json](repository-map.json).

When a command is implemented, replace the relevant unavailable statement with its exact working command, prerequisites, working directory, platform, expected effect and verification scope. Add it to CI where appropriate in the same change. Never document a guessed `npm test`, `pytest`, `uv` or Docker command as an existing entry point.

<a id="ci-scope"></a>
## CI scope

The [specification-integrity workflow](../.github/workflows/specs.yml) invokes the first two pack commands on Windows and Linux, with read-only repository permissions and no product credentials. Its job timeout limits the CI check, not an application agent run. A green specification-integrity run is not product stage acceptance and is not catalogue `verified` evidence.

The [backend unittest workflow](../.github/workflows/backend.yml) runs the registered backend install and unittest commands on the reviewed tree. The [desktop typecheck/build workflow](../.github/workflows/desktop.yml) runs the registered desktop install, type-check and build commands. The [shared-contract freshness workflow](../.github/workflows/contracts.yml) runs the registered generate `--check` command. These use read-only repository permissions and no product credentials. CI install steps use the lockfile-enforcing forms `uv sync --frozen` and `pnpm install --frozen-lockfile`; the unittest, type-check, build and freshness invocations match the commands above exactly. Backend and desktop jobs are not the freshness gate; the freshness job is not an import-boundary or integration gate.

Stable GitHub status-check names (job `name` values) are:

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

These eight status-check names are **required** on public `main` (classic branch protection, strict tip). Merges need them green on the pull-request tip. Agents keep tip-gating (`behind_by` 0 plus green required checks on that tip). Green required CI is **not** catalogue `verified` and **not** build-stage product acceptance. There is **no Pro ask** — Pro is unnecessary on a public repository. See [repository setup](repository-setup.md). The remaining unavailable commands above are still not CI gates.
