"""Loopback-only fixture server; secrets are never written to readiness output."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import socket

from tests_ui import configure_environment


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--port", type=int, choices=[0], default=0)
    parser.add_argument("--ready-file", type=Path, required=True)
    parser.add_argument("--inference", choices=["deterministic", "real"], default="deterministic")
    args = parser.parse_args()
    root = configure_environment(args.data_root)
    ready = args.ready_file.resolve()
    if root not in ready.parents:
        raise ValueError("Readiness metadata must remain inside the fixture data root")
    from tests_ui.fixture import ApplicationFixture
    import uvicorn

    fixture = ApplicationFixture(root, inference=args.inference)
    listener = socket.socket()
    try:
        listener.bind(("127.0.0.1", args.port))
        listener.listen(128)
        listener.setblocking(False)
        origin = f"http://127.0.0.1:{listener.getsockname()[1]}"
        server = uvicorn.Server(uvicorn.Config(
            fixture.app, host="127.0.0.1", port=0, log_level="warning",
            access_log=False, timeout_graceful_shutdown=5,
        ))
        fixture.app.state.ui_fixture_server = server
        original_startup = server.startup

        async def startup(sockets=None):
            await original_startup(sockets)
            import os
            metadata = {"origin": origin, "backend_url": origin, "pid": os.getpid(), "data_root": str(root), "fixture_root": str(root)}
            staged = ready.with_suffix(".partial")
            staged.write_text(json.dumps(metadata), encoding="utf-8")
            staged.replace(ready)
            print(json.dumps(metadata), flush=True)

        server.startup = startup
        server.run(sockets=[listener])
    finally:
        try:
            fixture.close()
        finally:
            listener.close()


if __name__ == "__main__":
    main()
