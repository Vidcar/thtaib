"""Classify llama.cpp / OpenAI-compatible adapter connection failures.

Chat-facing honesty for Issue #78. This is not process ownership (#62)
and not run observability (OQ-012).
"""

from __future__ import annotations

DEPLOY_UNREACHABLE = "deploy_unreachable"
DEPLOY_UNHEALTHY = "deploy_unhealthy"

DEPLOY_UNREACHABLE_MESSAGE = (
    "Managed/connected llama.cpp is unreachable. "
    "Live Chat completion requires a healthy deployment. "
    "Continuity/thread linkage is not proof of live completion."
)

DEPLOY_UNHEALTHY_MESSAGE = (
    "Bound deployment is not healthy. "
    "Live Chat completion requires a healthy managed/connected llama.cpp. "
    "Continuity/thread linkage is not proof of live completion."
)

_UNREACHABLE_MARKERS = (
    "connection error",
    "connecterror",
    "connect timeout",
    "connection refused",
    "connectionreset",
    "connection reset",
    "all connection attempts failed",
    "apiconnectionerror",
    "remoteprotocolerror",
    "connect call failed",
    "failed to establish a new connection",
    "name or service not known",
    "nodename nor servname provided",
    "network is unreachable",
    "deploy_unreachable",
    "llama.cpp is unreachable",
)


def classify_connection_failure(exc: BaseException | str) -> str | None:
    """Return ``deploy_unreachable`` for adapter/transport connection failures."""

    type_name = type(exc).__name__.lower() if not isinstance(exc, str) else ""
    blob = f"{type_name} {exc}".lower()
    if any(marker in blob for marker in _UNREACHABLE_MARKERS):
        return DEPLOY_UNREACHABLE
    return None


def clarify_connection_error(exc: BaseException | str) -> str:
    """Replace an opaque adapter 'Connection error.' with a Chat-facing message."""

    if classify_connection_failure(exc) == DEPLOY_UNREACHABLE:
        return DEPLOY_UNREACHABLE_MESSAGE
    return str(exc)
