"""Private loopback static worker, launched and stopped by PreviewService."""

from __future__ import annotations

import argparse
import os
import stat
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path, PureWindowsPath
from urllib.parse import unquote, urlsplit

from workbench_backend.agents.harness_backend import canonical_root


def handler_for(root: Path, token: str):
    boundary = canonical_root(root)

    class ProjectHandler(SimpleHTTPRequestHandler):
        def send_head(self):
            try:
                requested = unquote(urlsplit(self.path).path, errors="strict")
                if requested == f"/.__workbench_health_{token}":
                    self.send_response(204)
                    self.send_header("X-Workbench-Preview", token)
                    self.end_headers()
                    return None
                relative = requested.lstrip("/")
                windows = PureWindowsPath(relative)
                if ("\\" in relative or "\x00" in relative or ":" in relative
                        or ".." in windows.parts or windows.drive or windows.root
                        or any(PureWindowsPath(part).is_reserved() for part in windows.parts)):
                    raise ValueError("Invalid project path")
                target = (root / relative).resolve()
                if not canonical_root(target).is_relative_to(boundary):
                    raise ValueError("Outside project")
                if target.is_dir():
                    # Assets are available, directory listings are never exposed.
                    target = (target / "index.html").resolve()
                    if not canonical_root(target).is_relative_to(boundary):
                        raise ValueError("Outside project")
                handle = target.open("rb")
                info = os.fstat(handle.fileno())
                if not stat.S_ISREG(info.st_mode):
                    handle.close()
                    raise ValueError("Not a regular file")
            except (OSError, ValueError, UnicodeError):
                self.send_error(404, "Project file unavailable")
                return None
            self.send_response(200)
            self.send_header("Content-type", self.guess_type(str(target)))
            self.send_header("Content-Length", str(info.st_size))
            self.send_header("Last-Modified", self.date_time_string(info.st_mtime))
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            return handle

    return ProjectHandler


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("root")
    parser.add_argument("port", type=int)
    parser.add_argument("token")
    args = parser.parse_args()
    with ThreadingHTTPServer(("127.0.0.1", args.port), handler_for(Path(args.root), args.token)) as server:
        server.serve_forever()


if __name__ == "__main__":
    main()
