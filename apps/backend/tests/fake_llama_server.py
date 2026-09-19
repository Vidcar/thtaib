"""Stand-in llama-server used by unit tests.

This is not a second inference engine. It only exposes health and a thin
OpenAI-compatible smoke endpoint so managed start/stop can be exercised
without Windows llama-server.
"""

from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fake llama-server for tests")
    parser.add_argument("-m", "--model", default="")
    parser.add_argument("--mmproj", default=None)
    parser.add_argument("--alias", default="fake-llama")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    args, _unknown = parser.parse_known_args(argv)
    return args


def props_payload(args: argparse.Namespace) -> dict[str, object]:
    """Shape follows llama.cpp b11045 ``GET /props``; values are fixture stand-ins."""
    return {
        "default_generation_settings": {"params": {}, "n_ctx": 4096},
        "total_slots": 1,
        "model_alias": args.alias,
        "model_path": args.model,
        "modalities": {"vision": args.mmproj is not None, "video": False, "audio": False},
        "chat_template": "{{ fake }}",
        "chat_template_caps": {"supports_tools": True, "supports_tool_calls": True},
        "bos_token": "<s>",
        "eos_token": "</s>",
        "build_info": "fake-llama-server",
    }


class Handler(BaseHTTPRequestHandler):
    args: argparse.Namespace = parse_args([])

    def do_GET(self) -> None:  # noqa: N802
        if self.path in {"/health", "/health/"}:
            self._json(200, {"status": "ok"})
            return
        if self.path in {"/v1/models", "/models"}:
            self._json(200, {"data": [{"id": "fake-llama"}]})
            return
        if self.path in {"/props", "/props/"}:
            self._json(200, props_payload(self.args))
            return
        self._json(404, {"error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        if self.path.endswith("/chat/completions"):
            self._json(
                200,
                {
                    "id": "smoke",
                    "object": "chat.completion",
                    "choices": [
                        {
                            "index": 0,
                            "message": {"role": "assistant", "content": "pong"},
                            "finish_reason": "stop",
                        }
                    ],
                },
            )
            return
        self._json(404, {"error": "not found"})

    def log_message(self, format: str, *args: object) -> None:  # noqa: A003
        return

    def _json(self, status: int, payload: dict[str, object]) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    Handler.args = args
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    server.serve_forever()


if __name__ == "__main__":
    main()
