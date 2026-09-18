"""Run the Local AI Workbench backend on loopback only."""

from __future__ import annotations

import argparse

import uvicorn


def main() -> None:
    parser = argparse.ArgumentParser(description="Local AI Workbench backend")
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Bind address. Default is loopback; do not treat this as a trust model.",
    )
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    uvicorn.run(
        "workbench_backend.app:app",
        host=args.host,
        port=args.port,
        reload=False,
    )


if __name__ == "__main__":
    main()
