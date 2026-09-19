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
from workbench_backend.knowledge.routes import router as knowledge_router
from workbench_backend.knowledge.service import KnowledgeService
from workbench_backend.lab.routes import router as lab_router
from workbench_backend.lab.service import LabService

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
    application.state.knowledge = KnowledgeService(application.state.manager.paths)
    application.state.harness = HarnessService(
        lambda: application.state.manager,
        knowledge_provider=lambda: application.state.knowledge,
    )
    application.state.lab = LabService(
        lambda: application.state.manager,
        lambda: application.state.harness,
        knowledge_provider=lambda: application.state.knowledge,
    )
    application.include_router(router)
    application.include_router(agent_router)
    application.include_router(lab_router)
    application.include_router(knowledge_router)
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
