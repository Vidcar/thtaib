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
from fastapi.responses import JSONResponse

from workbench_backend import __version__
from workbench_backend.agents.harness import HarnessService
from workbench_backend.agents.routes import router as agent_router
from workbench_backend.chat.routes import router as chat_router
from workbench_backend.chat.branch_routes import router as branch_router
from workbench_backend.chat.service import ChatService
from workbench_backend.chat.coordinator import ChatCoordinator
from workbench_backend.assets.service import RetainedAssetService
from workbench_backend.assets.routes import router as assets_router
from workbench_backend.assets.lifecycle import AssetLifecycleService
from workbench_backend.assets.lifecycle_routes import router as asset_lifecycle_router
from workbench_backend.state.backup import BackupService, MaintenanceGate, BackupError
from workbench_backend.state.backup_routes import router as backup_router
from workbench_backend.contracts.lifecycle import is_run_lifecycle_live
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
from workbench_backend.state.preferences import PreferenceStore
from workbench_backend.state.preference_routes import router as preference_router
from workbench_backend.state.desktop_routes import router as desktop_router
from workbench_backend.state.migrate import open_application_store
from workbench_backend.interaction.routes import router as interaction_router
from workbench_backend.interaction.service import InteractionService

PRODUCT_NAME = "Local AI Workbench"
SURFACE = "managed-inference"


@asynccontextmanager
async def _app_lifespan(application: FastAPI) -> AsyncIterator[None]:
    application.state.chat.reconcile_saved_queue_on_startup()
    application.state.chat_coordinator = ChatCoordinator(application)
    for conversation in application.state.chat.store.list_conversations(include_archived=True):
        if conversation.current_run_id:
            try:
                application.state.chat_coordinator.observe(application.state.harness.get_run(conversation.current_run_id))
            except HarnessError:
                pass
    yield
    application.state.chat_coordinator.close()
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
    application.state.preferences = PreferenceStore(application.state.app_store)
    application.state.maintenance_gate = MaintenanceGate()
    application.state.assets = RetainedAssetService(application.state.app_store)
    application.state.asset_lifecycle = AssetLifecycleService(application.state.manager.paths, application.state.app_store,
        harness_provider=lambda: application.state.harness)

    @application.middleware("http")
    async def maintenance_boundary(request, call_next):
        if not request.url.path.startswith("/v1/") or request.url.path.startswith("/v1/backups") or request.url.path == "/v1/desktop/stop-owned-work":
            return await call_next(request)
        try:
            with application.state.maintenance_gate.mutation():
                return await call_next(request)
        except BackupError as exc:
            return JSONResponse(status_code=409, content={"code": exc.code, "message": str(exc)})
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
    application.state.interaction = InteractionService(
        application.state.app_store,
        lambda: application.state.harness,
        lambda: application.state.chat,
    )
    def _observe_run(run, event):
        application.state.interaction.observe(run, event)
        coordinator = getattr(application.state, "chat_coordinator", None)
        if coordinator is not None and event is None:
            coordinator.observe(run)

    application.state.harness = HarnessService(
        lambda: application.state.manager,
        knowledge_provider=lambda: application.state.knowledge,
        app_store=application.state.app_store,
        interaction_observer=_observe_run,
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
        assets_provider=lambda: application.state.assets,
    )
    def _active_work():
        active = [run.id for run in application.state.harness.list_runs() if is_run_lifecycle_live(run.status)]
        active.extend(job.id for job in application.state.manager.imports.list_jobs() if job.status.value in {"pending", "running", "stopping"})
        return active
    def _reconcile_for_backup():
        # Maintenance has drained coordinator mutations and blocks dispatch.
        # Persist terminal history/assets here without advancing any queue.
        for conversation in application.state.chat.store.list_conversations(include_archived=True):
            if conversation.current_run_id:
                run = application.state.harness.get_run(conversation.current_run_id)
                if not is_run_lifecycle_live(run.status):
                    application.state.asset_lifecycle.collect_verified_outputs_for_run(conversation.id, run.id)
        application.state.chat.reconcile_saved_queue_on_startup()
    application.state.backups = BackupService(application.state.manager.paths, application.state.app_store,
        maintenance_gate=application.state.maintenance_gate, active_work=_active_work, reconcile=_reconcile_for_backup)
    application.include_router(router)
    application.include_router(compatibility_router)
    application.include_router(effect_router)
    application.include_router(preference_router)
    application.include_router(desktop_router)
    application.include_router(agent_router)
    application.include_router(lab_router)
    application.include_router(knowledge_router)
    application.include_router(chat_router)
    application.include_router(branch_router)
    application.include_router(assets_router)
    application.include_router(asset_lifecycle_router)
    application.include_router(backup_router)
    application.include_router(interaction_router)
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
