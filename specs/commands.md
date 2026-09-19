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

| Command | Working directory | Purpose |
| --- | --- | --- |
| `uv sync` | `apps/backend` | Install locked dependencies (`--frozen` in CI). |
| `uv run python -m workbench_backend` | `apps/backend` | Start the backend on `127.0.0.1:8000`; `/health` is public, `/v1` needs `X-Workbench-Local-Token`. |
| `uv run python -m unittest discover -s tests -p "test_*.py"` | `apps/backend` | Backend unit tests (fakes and scripted models; not live evidence). |
| `uv run python ../../scripts/generate_shared_contracts.py` | `apps/backend` | Regenerate OpenAPI, JSON Schema and desktop types. |
| `uv run python ../../scripts/generate_shared_contracts.py --check` | `apps/backend` | Fail if generated contracts are stale. |

<a id="real-model-smoke"></a>
## Real-model smoke tier

| Command | Working directory | Purpose |
| --- | --- | --- |
| `uv run python -m tests_integration.assets` | `apps/backend` | Download the Linux x64 CPU build of the pinned llama.cpp release (sha256-verified) and the tiny smoke GGUF (`Qwen/Qwen2.5-0.5B-Instruct-GGUF` `q4_k_m`, pinned revision) into `.scratch/real-model-smoke/`; no-op when present. `--show` prints paths; `--cache-key` prints the CI cache key. Other platforms set `WORKBENCH_SMOKE_LLAMA_SERVER` and `WORKBENCH_SMOKE_MODEL_PATH`. |
| `uv run python -m unittest discover -s tests_integration -t . -p "test_*.py"` | `apps/backend` | Start a real `llama-server` and drive the product API: connected attach and health, a Chat turn with a real `write_file` into the project (no harness scratch left there), a project-less Chat turn with visibility tools, thread continuity on a follow-up, per-request settings on the wire. About 10–15 s with assets present. Skips without assets unless `WORKBENCH_REAL_MODEL_SMOKE=required` (set in CI). Plumbing only — never capability evidence ([verification](verification.md#evidence-tiers)). |

## Desktop

| Command | Working directory | Purpose |
| --- | --- | --- |
| `pnpm install` | `apps/desktop` | Install locked dependencies (`--frozen-lockfile` in CI). |
| `pnpm run typecheck` | `apps/desktop` | `tsc --noEmit` for renderer and Electron main/preload. |
| `pnpm run build` | `apps/desktop` | Type-check and Vite-build renderer and Electron bundles. |
| `pnpm run dev` | `apps/desktop` | Vite plus Electron; needs a display (David-PC). |
| `pnpm run package` | `apps/desktop` | Windows NSIS installer via electron-builder (not required yet). |

## Not yet available

Import-boundary check; integration tiers beyond the real-model smoke (managed Windows CUDA deployment, workers, MCP); product Docker services; application migrations. Add each here with its exact command when it lands and bind its path in [the repository map](repository-map.json).

<a id="ci"></a>
## CI

Workflows in `.github/workflows/` run the pack checks (`specs.yml`), backend unit tests (`backend.yml`), desktop type-check and build (`desktop.yml`), contract freshness (`contracts.yml`) and the real-model smoke tier (`real-model-smoke.yml`, Ubuntu only, assets restored from `actions/cache` under the pin-derived key) with read-only permissions, no secrets and no Hugging Face token. These eight status checks are required on `main` with strict tip:

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

A ninth check, `real-model-smoke (ubuntu-latest)`, runs on every pull request and is intended to join the required set; adding it to branch protection is a maintainer action, and until it is listed above it is not a merge gate. Green CI is merge enforcement, not `verified` evidence ([verification](verification.md)).
