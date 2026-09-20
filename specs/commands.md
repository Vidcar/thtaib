# Commands

Run pack commands from the repository root (Python 3.11+; on Windows `py -3` if `python` is missing). Application commands name their working directory and need [uv](https://docs.astral.sh/uv/) with Python 3.12.x or Node ≥22 <25 with pnpm 10+. Never document a guessed command.

## Specification pack

| Command | Working directory | Purpose |
| --- | --- | --- |
| `python scripts/check_specs.py` | root | Validate links, IDs, catalogue, pointers, source hash, evidence shape. |
| `python -m unittest discover -s tests/specs -p "test_*.py"` | root | Test the checker itself. |
| `python scripts/check_specs.py --requirement-hash MOD-001` | root | Print the digest to put in a `verified` evidence row. |
| `python scripts/check_specs.py --base-ref <full sha>` | root | Reject requirement IDs deleted since the base commit (CI sets `SPEC_BASE_REF`). Needs the full 40-character SHA; `main` or `origin/main` is rejected. |

## Backend

Use `tests.run` (or an explicit `tests.test_module` for focused checks). The test package selects a disposable `.scratch/` data root before importing the application, including its default app instance, and cleans up after the process. Avoid bare `unittest discover -s tests` without `-t .`: that bypasses package bootstrap. The default tier covers Models/Chat and pure rules; integration contains the cross-service and process fixtures. Neither tier downloads models.

| Command | Working directory | Purpose |
| --- | --- | --- |
| `uv sync` | `apps/backend` | Install locked dependencies (`--frozen` in CI). |
| `uv run python -m workbench_backend` | `apps/backend` | Start the backend on `127.0.0.1:8000`; `/health` is public, `/v1` needs `X-Workbench-Local-Token`. |
| `uv run python -m tests.run` | `apps/backend` | Fast default backend behaviour/regression suite (fakes and scripted models; not live evidence). |
| `uv run python -m tests.run --tier integration --durations 10` | `apps/backend` | Cross-service harness/replay, real loopback HTTP/SSE, host-shell, managed process and Windows cancellation checks; no real model required. |
| `uv run python -m tests.run --tier all --durations 20` | `apps/backend` | Every backend regression, including integration. Use before delivery for backend changes. |
| `uv run python ../../scripts/generate_shared_contracts.py` | `apps/backend` | Regenerate OpenAPI, JSON Schema and desktop types. |
| `uv run python ../../scripts/generate_shared_contracts.py --check` | `apps/backend` | Fail if generated contracts are stale. |

Run/Chat JSON-to-SQLite migration already runs automatically when backend startup opens the application store through [state/migrate.py](../apps/backend/src/workbench_backend/state/migrate.py). It archives migrated JSON and makes `application.sqlite` authoritative, without dual writes. It has no separate migration command; [state regressions](../apps/backend/tests/test_state.py) cover the existing path.

<a id="real-model-smoke"></a>
## Real-model smoke tier

| Command | Working directory | Purpose |
| --- | --- | --- |
| `uv run python -m tests_integration.assets` | `apps/backend` | Download the Linux x64 CPU build of the pinned llama.cpp release (sha256-verified) and the tiny smoke GGUF (`Qwen/Qwen2.5-0.5B-Instruct-GGUF` `q4_k_m`, pinned revision) into `.scratch/real-model-smoke/`; no-op when present. `--show` prints paths; `--cache-key` prints the CI cache key. Other platforms set `WORKBENCH_SMOKE_LLAMA_SERVER` and `WORKBENCH_SMOKE_MODEL_PATH`. |
| `uv run python -m unittest discover -s tests_integration -t . -p "test_*.py"` | `apps/backend` | Start a real `llama-server` and drive the product API: connected attach and health, a Chat turn with a real `write_file` into the project (no harness scratch left there), a project-less Chat turn with visibility tools that also consumes `GET /v1/events` to `stream_end`, thread continuity on a follow-up, per-request settings on the wire. About 10–15 s with assets present. Skips without assets unless `WORKBENCH_REAL_MODEL_SMOKE=required` (set in CI). Plumbing only — never capability evidence ([verification](verification.md#evidence-tiers)). |

## Desktop

For normal local use on a prepared Windows checkout, double-click root `Launch Workbench.vbs`. `scripts/Launch-Workbench.ps1` starts/reuses the loopback backend and opens the built Electron app; it does not install dependencies or download a model. Rebuild after desktop changes. Agents can validate startup with `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/Launch-Workbench.ps1 -CheckOnly -NoDesktop -ShowConsole` from root. Logs are in the product `logs` directory. Closing the desktop leaves the backend/model available; stop a model from Models when finished.

| Command | Working directory | Purpose |
| --- | --- | --- |
| `pnpm install` | `apps/desktop` | Install locked dependencies (`--frozen-lockfile` in CI). |
| `pnpm run typecheck` | `apps/desktop` | `tsc --noEmit` for renderer and Electron main/preload. |
| `pnpm run build` | `apps/desktop` | Type-check, exercise SSE terminal hydration with mock streams, and Vite-build renderer and Electron bundles. |
| `pnpm run dev` | `apps/desktop` | Vite plus Electron; needs a display (David-PC). |
| `pnpm run package` | `apps/desktop` | Windows NSIS installer via electron-builder (not required yet). |
| `node scripts/check-sse-terminal-snapshot.mjs` | `apps/desktop` | Exercise terminal Chat hydration and aborted subscriptions with mock fetch streams; no model or browser. |

## Not yet available

Import-boundary check; integration tiers beyond the local process checks and real-model smoke (managed Windows CUDA deployment, workers, MCP); product Docker services; migration of remaining model, compatibility, Lab and knowledge metadata from JSON to SQLite ([OQ-017](open-questions.md#oq-017)). Add each here with its exact command when it lands and bind its path in [the repository map](repository-map.json).

<a id="ci"></a>
## CI

One workflow, `.github/workflows/ci.yml`, selects changed paths once and runs backend regressions, desktop build (including typecheck and SSE behaviour), contract freshness and spec integrity. Backend and desktop changes retain Windows and Ubuntu coverage. Required jobs still report on unrelated changes; do not use top-level path filters that leave required checks pending. Unknown revisions or failed diffs select every tier.

The fast default suite is for the local development loop. CI also runs the process integration tier on backend changes. Real-model smoke is separate: relevant backend implementation/integration/dependency changes and CI changes run it on pull requests, and manual dispatch runs it explicitly. It no longer repeats on post-merge pushes or unrelated merge queues. Missing assets fail this tier in CI; local asset-free runs may skip and must be reported as skipped. Do not treat tiny-model success as capability evidence.

Commands are not additive checklists: `pnpm run build` already includes typecheck and the SSE regression script. Do not run them again immediately before/after that build without a relevant change. Contract freshness is run once in its own job; cheap contract unit checks remain in the backend suite.

The existing four required GitHub status names are preserved, with strict tip protection:

```text
backend-unittest (ubuntu-latest)
desktop-typecheck-build (ubuntu-latest)
shared-contract-freshness (ubuntu-latest)
spec-integrity (ubuntu-latest)
```

Windows backend/desktop and Ubuntu real-model jobs remain additional checks. No GitHub settings change is required. Ubuntu checks provide portability coverage, not a supported Linux desktop claim. CI is a final guard; live Windows validation uses isolated product data under `.scratch/` and existing model assets without changing the everyday workspace.
