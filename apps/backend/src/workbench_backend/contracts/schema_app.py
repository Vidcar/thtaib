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
    from workbench_backend.inference.compatibility_routes import router as compatibility_router
    from workbench_backend.assets.routes import router as assets_router
    from workbench_backend.agents.setup_routes import router as setup_router
    from workbench_backend.knowledge.routes import router as knowledge_router
    from workbench_backend.connections.routes import router as connections_router
    from workbench_backend.chat.routes import router as chat_router
    from workbench_backend.browser.routes import router as browser_router
    from workbench_backend.preview.routes import router as preview_router
    from workbench_backend.desktop_automation.routes import router as desktop_automation_router
    from workbench_backend.agents.routes import router as agent_router
    from workbench_backend.interaction.routes import router as interaction_router
    from workbench_backend.interaction.schemas import WorkbenchInteractionMetadata

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
        "/v1/shared-contracts/workbench-interaction-metadata",
        response_model=WorkbenchInteractionMetadata,
        tags=["shared-contracts"],
        summary="Workbench native interaction metadata contract",
    )
    def workbench_interaction_metadata_contract() -> WorkbenchInteractionMetadata:
        return WorkbenchInteractionMetadata()

    # Export the same typed model-management routes consumed by the desktop.
    # This application is only used to generate OpenAPI; it is never served.
    application.include_router(model_manager_router)
    application.include_router(compatibility_router)
    application.include_router(assets_router)
    application.include_router(setup_router)
    application.include_router(knowledge_router)
    application.include_router(connections_router)
    application.include_router(chat_router)
    application.include_router(browser_router)
    application.include_router(preview_router)
    application.include_router(desktop_automation_router)
    application.include_router(agent_router)
    application.include_router(interaction_router)

    return application
