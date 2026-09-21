"""Local AI Workbench FastAPI application.

Loopback HTTP plus the Issue #40 shared-secret header. This is a partial
OQ-002 default, not remote-backend support and not a closed trust model.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from workbench_backend import __version__
from workbench_backend.agents.harness import HarnessService
from workbench_backend.agents.routes import router as agent_router
from workbench_backend.chat.routes import router as chat_router
from workbench_backend.chat.service import ChatService
from workbench_backend.errors import HarnessError, WorkbenchError, workbench_error_handler
from workbench_backend.inference.compatibility import CompatibilityService
from workbench_backend.inference.compatibility_routes import router as compatibility_router
from workbench_backend.inference.routes import router
from workbench_backend.inference.service import manager_from_env
from workbench_backend.knowledge.routes import router as knowledge_router
from workbench_backend.knowledge.service import KnowledgeService
from workbench_backend.lab.routes import router as lab_router
from workbench_backend.lab.service import LabService
from workbench_backend.local_trust import ensure_shared_secret, require_local_trust
from workbench_backend.state.checkpointer import close_all_sqlite_checkpointers
from workbench_backend.state.effect_routes import router as effect_router
from workbench_backend.state.effects import EffectService
from workbench_backend.state.migrate import open_application_store

PRODUCT_NAME = "Local AI Workbench"
SURFACE = "managed-inference"


@asynccontextmanager
async def _app_lifespan(application: FastAPI) -> AsyncIterator[None]:
    yield
    harness = getattr(application.state, "harness", None)
    if harness is not None:
        closer = getattr(harness, "close", None)
        if callable(closer):
            closer()
    manager = getattr(application.state, "manager", None)
    if manager is not None:
        manager.imports.close()
    store = getattr(application.state, "app_store", None)
    if store is not None:
        store.close()
    close_all_sqlite_checkpointers()


def create_app(*, data_root: Path | None = None) -> FastAPI:
    application = FastAPI(
        title=PRODUCT_NAME,
        version=__version__,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=_app_lifespan,
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
    application.state.manager.imports.reconcile_on_startup()
    application.state.local_trust_token = ensure_shared_secret(application.state.manager.paths)
    application.middleware("http")(require_local_trust)
    application.state.app_store = open_application_store(application.state.manager.paths)
    application.state.compatibility = CompatibilityService(application.state.manager.paths)
    def _lookup_run(run_id: str):
        try:
            return application.state.harness.get_run(run_id)
        except HarnessError:
            return None

    application.state.effects = EffectService(
        application.state.app_store,
        run_lookup=_lookup_run,
    )
    application.state.knowledge = KnowledgeService(application.state.manager.paths)
    application.state.harness = HarnessService(
        lambda: application.state.manager,
        knowledge_provider=lambda: application.state.knowledge,
        app_store=application.state.app_store,
    )
    application.state.lab = LabService(
        lambda: application.state.manager,
        lambda: application.state.harness,
        knowledge_provider=lambda: application.state.knowledge,
        effects_provider=lambda: application.state.effects,
    )
    application.state.chat = ChatService(
        lambda: application.state.manager,
        lambda: application.state.harness,
        lambda: application.state.lab,
        app_store=application.state.app_store,
        knowledge_provider=lambda: application.state.knowledge,
    )
    application.include_router(router)
    application.include_router(compatibility_router)
    application.include_router(effect_router)
    application.include_router(agent_router)
    application.include_router(lab_router)
    application.include_router(knowledge_router)
    application.include_router(chat_router)
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
