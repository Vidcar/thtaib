"""Run the Local AI Workbench backend on loopback only."""

from __future__ import annotations

import argparse
import sys

import uvicorn

from workbench_backend.contracts.auth import WORKBENCH_LOCAL_BIND
from workbench_backend.local_trust import require_loopback_bind


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
    from workbench_backend.app import app, create_app
    application = app
    while True:
        server = uvicorn.Server(uvicorn.Config(application, host=host, port=args.port, reload=False))
        restart_requested = False

        def restart_backend():
            nonlocal restart_requested
            restart_requested = True
            server.should_exit = True

        def shutdown_backend():
            server.should_exit = True

        application.state.restart_backend = restart_backend
        application.state.shutdown_backend = shutdown_backend
        server.run()
        if not restart_requested:
            break
        application = create_app()


if __name__ == "__main__":
    main()
