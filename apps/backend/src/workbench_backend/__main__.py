"""Run the Local AI Workbench backend on loopback only."""

from __future__ import annotations

import argparse
import sys

import uvicorn

from workbench_backend.local_trust import WORKBENCH_LOCAL_BIND, require_loopback_bind


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Local AI Workbench backend")
    parser.add_argument(
        "--host",
        default=WORKBENCH_LOCAL_BIND,
        help="Bind address. v1 is 127.0.0.1 only; remote backend is unsupported.",
    )
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args(argv)
    try:
        host = require_loopback_bind(args.host)
    except ValueError as exc:
        print(exc, file=sys.stderr)
        raise SystemExit(2) from exc
    uvicorn.run(
        "workbench_backend.app:app",
        host=host,
        port=args.port,
        reload=False,
    )


if __name__ == "__main__":
    main()
