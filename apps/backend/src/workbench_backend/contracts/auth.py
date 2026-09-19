"""Desktop↔backend local-trust header contract (OQ-002 partial names only).

Issue #40 owns Electron injection and secret-file I/O. This module defines the
shared header name and envelope so generated consumers use the same identifiers.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

WORKBENCH_LOCAL_TOKEN_HEADER = "X-Workbench-Local-Token"
WORKBENCH_LOCAL_TOKEN_SCHEME = "shared_secret"
WORKBENCH_LOCAL_BIND = "127.0.0.1"


class LocalSessionTrustContract(BaseModel):
    """Shared session-token header envelope for same-machine desktop↔backend trust."""

    model_config = ConfigDict(title="LocalSessionTrustContract")

    header_name: Literal["X-Workbench-Local-Token"] = Field(
        default=WORKBENCH_LOCAL_TOKEN_HEADER,
        description="Locked request header carrying the local shared-secret token.",
    )
    scheme: Literal["shared_secret"] = Field(
        default=WORKBENCH_LOCAL_TOKEN_SCHEME,
        description="Token is a local shared secret. This is not a remote OAuth flow.",
    )
    bind: Literal["127.0.0.1"] = Field(
        default=WORKBENCH_LOCAL_BIND,
        description="v1 bind is loopback only. Remote backend is unsupported.",
    )
    remote_backend: Literal["unsupported"] = "unsupported"
    secret_location: Literal["localappdata_state"] = Field(
        default="localappdata_state",
        description=(
            "Secret file lives under LocalAppData state (Issue #40). "
            "This contract does not perform file I/O."
        ),
    )
    injector: Literal["electron_main"] = Field(
        default="electron_main",
        description="Electron main injects the header (Issue #40). Not implemented here.",
    )
    unauthenticated_privileged: Literal["deny"] = Field(
        default="deny",
        description="Privileged routes reject a missing or wrong token (Issue #40).",
    )
