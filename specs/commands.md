# Commands

Run pack commands from the repository root (Python 3.11+; on Windows `py -3` if `python` is missing). Application commands name their working directory and need [uv](https://docs.astral.sh/uv/) with Python 3.12.x or Node ≥22 <25 with pnpm 10+. Never document a guessed command.

## Specification pack

| Command | Working directory | Purpose |
| --- | --- | --- |
| `python scripts/check_specs.py` | root | Validate links, IDs, catalogue, pointers, source hash, evidence shape. |
| `python -m unittest discover -s tests/specs -p "test_*.py"` | root | Test the checker itself. |
| `python scripts/check_specs.py --requirement-hash MOD-001` | root | Print the digest to put in a `verified` evidence row. |
| `python scripts/check_specs.py --base-ref <full sha>` | root | Reject requirement IDs deleted since the base commit (CI sets `SPEC_BASE_REF`). |

## Backend

| Command | Working directory | Purpose |
| --- | --- | --- |
| `uv sync` | `apps/backend` | Install locked dependencies (`--frozen` in CI). |
| `uv run python -m workbench_backend` | `apps/backend` | Start the backend on `127.0.0.1:8000`; `/health` is public, `/v1` needs `X-Workbench-Local-Token`. |
| `uv run python -m unittest discover -s tests -p "test_*.py"` | `apps/backend` | Backend unit tests (fakes and scripted models; not live evidence). |
| `uv run python ../../scripts/generate_shared_contracts.py` | `apps/backend` | Regenerate OpenAPI, JSON Schema and desktop types. |
| `uv run python ../../scripts/generate_shared_contracts.py --check` | `apps/backend` | Fail if generated contracts are stale. |

## Desktop

| Command | Working directory | Purpose |
| --- | --- | --- |
| `pnpm install` | `apps/desktop` | Install locked dependencies (`--frozen-lockfile` in CI). |
| `pnpm run typecheck` | `apps/desktop` | `tsc --noEmit` for renderer and Electron main/preload. |
| `pnpm run build` | `apps/desktop` | Type-check and Vite-build renderer and Electron bundles. |
| `pnpm run dev` | `apps/desktop` | Vite plus Electron; needs a display (David-PC). |
| `pnpm run package` | `apps/desktop` | Windows NSIS installer via electron-builder (not required yet). |

## Not yet available

Real-model CI smoke tier, import-boundary check, integration tests, product Docker services, application migrations. Add each here with its exact command when it lands and bind its path in [the repository map](repository-map.json).

<a id="ci"></a>
## CI

Workflows in `.github/workflows/` run the pack checks (`specs.yml`), backend unit tests (`backend.yml`), desktop type-check and build (`desktop.yml`) and contract freshness (`contracts.yml`) on Ubuntu and Windows with read-only permissions and no secrets. These eight status checks are required on `main` with strict tip:

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

Green CI is merge enforcement, not `verified` evidence ([verification](verification.md)).
