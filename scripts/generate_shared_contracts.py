#!/usr/bin/env python3
"""Generate or freshness-check shared OpenAPI → TypeScript contracts.

Run through the backend uv environment so FastAPI/Pydantic are available:

    uv --directory apps/backend run python ../../scripts/generate_shared_contracts.py
    uv --directory apps/backend run python ../../scripts/generate_shared_contracts.py --check
"""

from __future__ import annotations

from workbench_backend.contracts.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
