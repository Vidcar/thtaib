"""Local AI Workbench FastAPI application.

Provisional localhost HTTP is for smoke only. It does not select a trust
model and does not close OQ-002.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from workbench_backend import __version__
from workbench_backend.agents.harness import HarnessService
from workbench_backend.agents.routes import router as agent_router
from workbench_backend.errors import WorkbenchError, workbench_error_handler
from workbench_backend.inference.routes import router
from workbench_backend.inference.service import manager_from_env

PRODUCT_NAME = "Local AI Workbench"
SURFACE = "managed-inference"


def create_app(*, data_root: Path | None = None) -> FastAPI:
    application = FastAPI(
        title=PRODUCT_NAME,
        version=__version__,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://127.0.0.1:5173",
            "http://localhost:5173",
            "null",
        ],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    application.state.manager = manager_from_env(data_root)
    application.state.harness = HarnessService(lambda: application.state.manager)
    application.include_router(router)
    application.include_router(agent_router)
    application.add_exception_handler(WorkbenchError, workbench_error_handler)

    @application.get("/health")
    def health() -> dict[str, str]:
        return {
            "status": "ok",
            "product": PRODUCT_NAME,
            "surface": SURFACE,
        }

    return application


app = create_app()
