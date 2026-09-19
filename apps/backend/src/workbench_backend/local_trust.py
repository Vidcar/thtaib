"""Same-machine desktop↔backend trust (Issue #40; partial OQ-002).

Hard-aligns the #41 header/envelope names. This module owns secret-file I/O
and request checks; it does not own the OpenAPI→TS generator.
"""

from __future__ import annotations

import hmac
import os
import secrets
from collections.abc import Awaitable, Callable
from pathlib import Path

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.responses import Response

from workbench_backend.errors import LocalTrustError
from workbench_backend.paths import WorkbenchPaths

# Locked names shared with Issue #41 (ADR-0002 generator, when merged).
WORKBENCH_LOCAL_TOKEN_HEADER = "X-Workbench-Local-Token"
WORKBENCH_LOCAL_TOKEN_SCHEME = "shared_secret"
WORKBENCH_LOCAL_BIND = "127.0.0.1"
PUBLIC_PATHS = frozenset({"/health"})


def shared_secret_path(paths: WorkbenchPaths) -> Path:
    return paths.desktop_backend_shared_secret


def require_loopback_bind(host: str) -> str:
    if host != WORKBENCH_LOCAL_BIND:
        raise ValueError(
            f"v1 bind is {WORKBENCH_LOCAL_BIND} only; remote backend is unsupported"
        )
    return host


def tokens_match(provided: str, expected: str) -> bool:
    provided_bytes = provided.encode("utf-8")
    expected_bytes = expected.encode("utf-8")
    if len(provided_bytes) != len(expected_bytes):
        return False
    return hmac.compare_digest(provided_bytes, expected_bytes)


def ensure_shared_secret(paths: WorkbenchPaths) -> str:
    """Create or read the LocalAppData (or portable) shared secret.

    The file lives under ``state/`` and is never a repository path.
    """
    paths.ensure()
    path = shared_secret_path(paths)
    existing = _read_secret(path)
    if existing:
        return existing
    token = secrets.token_urlsafe(32)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    try:
        fd = os.open(path, flags, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(token)
    except FileExistsError:
        reused = _read_secret(path)
        if not reused:
            raise LocalTrustError(
                "Shared secret file exists but is empty",
                code="local_trust_secret_unreadable",
                status_code=500,
            )
        return reused
    os.chmod(path, 0o600)
    return token


def _read_secret(path: Path) -> str:
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8").strip()


def is_public_request(request: Request) -> bool:
    if request.method == "OPTIONS":
        return True
    return request.url.path in PUBLIC_PATHS


def unauthorized_response() -> JSONResponse:
    return JSONResponse(
        status_code=401,
        content={
            "error": "Missing local workbench token",
            "code": "unauthenticated",
        },
    )


def forbidden_response() -> JSONResponse:
    return JSONResponse(
        status_code=403,
        content={
            "error": "Invalid local workbench token",
            "code": "invalid_token",
        },
    )


async def require_local_trust(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    if is_public_request(request):
        return await call_next(request)
    expected = getattr(request.app.state, "local_trust_token", "")
    provided = request.headers.get(WORKBENCH_LOCAL_TOKEN_HEADER)
    if not provided:
        return unauthorized_response()
    if not expected or not tokens_match(provided, expected):
        return forbidden_response()
    return await call_next(request)
