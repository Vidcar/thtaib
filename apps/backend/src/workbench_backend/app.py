"""Local AI Workbench FastAPI application.

Loopback HTTP plus the Issue #40 shared-secret header. This local default
does not provide remote-backend support or a complete trust model.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
import asyncio
import logging
import threading
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from workbench_backend import __version__
from workbench_backend.agents.harness import HarnessService
from workbench_backend.agents.routes import router as agent_router
from workbench_backend.agents.setup_routes import router as setup_router
from workbench_backend.agents.setup_service import SetupService
from workbench_backend.connections.service import ConnectionService
from workbench_backend.connections.routes import router as connections_router
from workbench_backend.chat.routes import router as chat_router
from workbench_backend.chat.branch_routes import router as branch_router
from workbench_backend.chat.service import ChatService
from workbench_backend.chat.coordinator import ChatCoordinator
from workbench_backend.assets.service import RetainedAssetService
from workbench_backend.assets.routes import router as assets_router
from workbench_backend.assets.lifecycle import AssetLifecycleService
from workbench_backend.assets.lifecycle_routes import router as asset_lifecycle_router
from workbench_backend.browser.service import BrowserSessionService
from workbench_backend.browser.routes import router as browser_router
from workbench_backend.preview.service import PreviewService
from workbench_backend.preview.routes import router as preview_router
from workbench_backend.desktop_automation.service import DesktopAutomationService
from workbench_backend.desktop_automation.routes import router as desktop_automation_router
from workbench_backend.state.maintenance import MaintenanceError, MaintenanceGate
from workbench_backend.contracts.lifecycle import is_run_lifecycle_live
from workbench_backend.errors import HarnessError, WorkbenchError, workbench_error_handler
from workbench_backend.inference.compatibility import CompatibilityService
from workbench_backend.inference.compatibility_routes import router as compatibility_router
from workbench_backend.inference.routes import router
from workbench_backend.inference.service import manager_from_env
from workbench_backend.knowledge.routes import router as knowledge_router
from workbench_backend.knowledge.service import KnowledgeService
from workbench_backend.lab.service import LabService
from workbench_backend.lab.workbench import LabWorkbenchService
from workbench_backend.lab.workbench_routes import router as lab_workbench_router
from workbench_backend.local_trust import ensure_shared_secret, require_local_trust
from workbench_backend.state.checkpointer import close_all_sqlite_checkpointers, submit_checkpoint_task
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
log = logging.getLogger(__name__)


def note_catalogue_served(application: FastAPI) -> None:
    served = getattr(application.state, "catalogue_served", None)
    if served is not None:
        served.set()


def _finish_startup(application: FastAPI) -> None:
    """Resume accepted queue work; defer token maintenance until lists are read."""

    served = application.state.catalogue_served
    stop = application.state.startup_stop
    if not stop.is_set():
        try:
            with application.state.maintenance_gate.mutation():
                application.state.chat.dispatch_idle_queued()
        except Exception:
            log.exception("Saved chat dispatch failed; pending work remains durable")
    while not served.is_set() and not stop.is_set():
        served.wait(timeout=0.2)
    if stop.is_set():
        return
    try:
        if application.state.app_store.interaction_event_count() < 500:
            return
        removed = application.state.interaction.discard_finished_token_logs()
        if removed:
            application.state.app_store.reclaim_unused_space()
    except Exception:
        log.exception("Finished token log could not be collapsed")


@asynccontextmanager
async def _app_lifespan(application: FastAPI) -> AsyncIterator[None]:
    application.state.catalogue_served = threading.Event()
    application.state.startup_stop = threading.Event()
    application.state.lab_workbench.recover()
    # Recovery must precede admission and must not depend on opening a sidebar.
    # This reconciles durable identities only; execution starts on the worker.
    application.state.chat.reconcile_saved_queue_on_startup(pending_only=True)
    application.state.chat_coordinator = ChatCoordinator(application)
    finish = threading.Thread(target=_finish_startup, args=(application,), name="workbench-startup-finish", daemon=True)
    finish.start()
    application.state.startup_finish = finish
    yield
    application.state.shutdown_requested.set()
    application.state.startup_stop.set()
    application.state.catalogue_served.set()
    finish.join(timeout=20)
    if finish.is_alive():
        raise RuntimeError("Chat startup recovery is still using the application store")
    application.state.chat_coordinator.close()
    application.state.lab_workbench.close()
    browser = getattr(application.state, "browser", None)
    if browser is not None:
        await asyncio.wrap_future(submit_checkpoint_task(application.state.manager.paths.checkpoints_db, browser.shutdown()))
    preview = getattr(application.state, "preview", None)
    if preview is not None:
        preview.shutdown()
    harness = getattr(application.state, "harness", None)
    if harness is not None:
        closer = getattr(harness, "close", None)
        if callable(closer):
            closer()
    manager = getattr(application.state, "manager", None)
    if manager is not None:
        manager.capability_checks.close()
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
    application.state.shutdown_requested = threading.Event()
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
    application.state.browser = BrowserSessionService(
        application.state.manager.paths,
        capture_publisher=application.state.assets.register_capture,
        app_store=application.state.app_store,
        assets=application.state.assets,
    )
    application.state.preview = PreviewService(application.state.manager.paths)
    from workbench_backend.agents.managed_commands import ManagedCommandService
    application.state.managed_commands = ManagedCommandService(application.state.manager.paths, app_store=application.state.app_store)
    application.state.desktop_automation = DesktopAutomationService(
        application.state.manager.paths,
        capture_sink=application.state.assets.register_capture,
    )
    application.state.asset_lifecycle = AssetLifecycleService(application.state.manager.paths, application.state.app_store,
        harness_provider=lambda: application.state.harness)

    @application.middleware("http")
    async def maintenance_boundary(request, call_next):
        if not request.url.path.startswith("/v1/") or request.url.path == "/v1/desktop/stop-owned-work":
            return await call_next(request)
        try:
            with application.state.maintenance_gate.mutation():
                return await call_next(request)
        except MaintenanceError as exc:
            return JSONResponse(status_code=409, content={"code": exc.code, "message": str(exc)})
    application.state.compatibility = CompatibilityService(application.state.manager.paths)
    def _lookup_run(run_id: str):
        try:
            return application.state.harness.get_run_lifecycle(run_id)
        except HarnessError:
            return None

    application.state.effects = EffectService(
        application.state.app_store,
        run_lookup=_lookup_run,
    )
    application.state.knowledge = KnowledgeService(application.state.manager.paths, app_store=application.state.app_store)
    application.state.connections = ConnectionService(application.state.app_store)
    application.state.setups = SetupService(application.state.app_store, application.state.manager, application.state.knowledge, connection_available=application.state.connections.available, connection_tools=lambda ident: [tool.name for tool in application.state.connections.tool_definitions(ident)], connection_exists=application.state.connections.exists, connection_tool_definitions=application.state.connections.tool_definitions)
    application.include_router(connections_router)
    application.state.interaction = InteractionService(
        application.state.app_store,
        lambda: application.state.harness,
        lambda: application.state.chat,
    )
    def _observe_run(run, event, *, telemetry=False):
        try:
            application.state.interaction.observe(run, event, telemetry=telemetry)
        finally:
            # A failed display write cannot strand a durably settled Chat queue.
            coordinator = getattr(application.state, "chat_coordinator", None)
            if coordinator is not None and event is None and not telemetry and not is_run_lifecycle_live(run.status):
                coordinator.observe(run)

    def _project_available():
        coordinator = getattr(application.state, "chat_coordinator", None)
        if coordinator is not None:
            coordinator.wake()

    application.state.harness = HarnessService(
        lambda: application.state.manager,
        knowledge_provider=lambda: application.state.knowledge,
        app_store=application.state.app_store,
        interaction_observer=_observe_run,
        project_available_observer=_project_available,
        assets=application.state.assets,
        browser=application.state.browser,
        preview=application.state.preview,
        managed_commands=application.state.managed_commands,
        desktop_automation=application.state.desktop_automation,
    )
    application.state.browser.state_invalidator = application.state.harness.invalidate_browser_state
    application.state.lab = LabService(lambda: application.state.manager)
    application.state.lab_workbench = LabWorkbenchService(
        lambda: application.state.manager, lambda: application.state.harness, application.state.app_store,
    )
    application.state.chat = ChatService(
        lambda: application.state.manager,
        lambda: application.state.harness,
        lambda: application.state.lab,
        app_store=application.state.app_store,
        knowledge_provider=lambda: application.state.knowledge,
        assets_provider=lambda: application.state.assets,
    )
    application.state.manager.validate_chat_reconfiguration = application.state.chat.validate_reconfiguration
    application.include_router(router)
    application.include_router(compatibility_router)
    application.include_router(effect_router)
    application.include_router(preference_router)
    application.include_router(desktop_router)
    application.include_router(desktop_automation_router)
    application.include_router(agent_router)
    application.include_router(setup_router)
    application.include_router(lab_workbench_router)
    application.include_router(knowledge_router)
    application.include_router(chat_router)
    application.include_router(branch_router)
    application.include_router(assets_router)
    application.include_router(browser_router)
    application.include_router(preview_router)
    application.include_router(asset_lifecycle_router)
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
