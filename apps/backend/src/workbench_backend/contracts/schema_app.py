"""FastAPI schema app for the shared-contract OpenAPI export.

This is generator input, not a second backend and not the product HTTP surface.
The product app keeps `/openapi.json` unpublished.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import FastAPI, Security
from fastapi.security import APIKeyHeader

from workbench_backend import PRODUCT_NAME, __version__
from workbench_backend.contracts.auth import (
    WORKBENCH_LOCAL_TOKEN_HEADER,
    LocalSessionTrustContract,
)
from workbench_backend.contracts.events import RunStreamContract, RunStreamEnvelope
from workbench_backend.contracts.lifecycle import RunLifecycleContract

SHARED_CONTRACT_OPENAPI_TITLE = f"{PRODUCT_NAME} shared contracts"

workbench_local_token = APIKeyHeader(
    name=WORKBENCH_LOCAL_TOKEN_HEADER,
    auto_error=False,
    scheme_name="WorkbenchLocalToken",
    description=(
        "Same-machine desktop↔backend shared-secret token. "
        "Electron main injects this header (Issue #40)."
    ),
)


def create_shared_contract_app() -> FastAPI:
    from workbench_backend.inference.routes import router as model_manager_router

    application = FastAPI(
        title=SHARED_CONTRACT_OPENAPI_TITLE,
        version=__version__,
        description=(
            "Canonical shared HTTP contract surface generated from Pydantic models. "
            "Not the product route table. Product OpenAPI stays unpublished."
        ),
    )

    @application.get(
        "/v1/shared-contracts/session-trust",
        response_model=LocalSessionTrustContract,
        tags=["shared-contracts"],
        summary="Local session-trust header contract",
    )
    def session_trust_contract(
        _token: Annotated[str | None, Security(workbench_local_token)] = None,
    ) -> LocalSessionTrustContract:
        return LocalSessionTrustContract()

    @application.get(
        "/v1/shared-contracts/run-lifecycle",
        response_model=RunLifecycleContract,
        tags=["shared-contracts"],
        summary="Run/cancel lifecycle contract",
    )
    def run_lifecycle_contract() -> RunLifecycleContract:
        return RunLifecycleContract()

    @application.get(
        "/v1/shared-contracts/run-stream",
        response_model=RunStreamContract,
        tags=["shared-contracts"],
        summary="Run/chat SSE envelope contract",
    )
    def run_stream_contract() -> RunStreamContract:
        return RunStreamContract()

    @application.get(
        "/v1/shared-contracts/run-stream-envelope",
        response_model=RunStreamEnvelope,
        tags=["shared-contracts"],
        summary="Run/chat SSE JSON data envelope",
    )
    def run_stream_envelope_contract() -> RunStreamEnvelope:
        return RunStreamEnvelope(type="stream_end")

    # Export the same typed model-management routes consumed by the desktop.
    # This application is only used to generate OpenAPI; it is never served.
    application.include_router(model_manager_router)

    return application
