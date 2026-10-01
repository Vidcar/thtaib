"""AGT-001: embedded Deep Agents harness — start / observe / cancel.

Deep Agents owns the model/tool loop. LangGraph is only the compiled graph
returned by create_deep_agent — not a second Builder workflow editor.
"""

from __future__ import annotations

import asyncio
import logging
import sys
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import AsyncExitStack, asynccontextmanager, contextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx
from deepagents import create_deep_agent
from deepagents.backends import StateBackend
from deepagents.middleware.summarization import SummarizationMiddleware, SUMMARIZATION_EVENT_KEY, create_summarization_middleware
from langchain.agents.middleware import TodoListMiddleware, HumanInTheLoopMiddleware
from langchain_core.embeddings import Embeddings
from langchain_core.exceptions import ContextOverflowError
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, RemoveMessage, SystemMessage, ToolMessage
from langgraph.graph.message import REMOVE_ALL_MESSAGES
from langgraph.types import Command

from workbench_backend.agents.effective_setup import resolve_effective_setup
from workbench_backend.agents.input_sources import WORKBENCH_CORE_INSTRUCTIONS
from workbench_backend.agents.setup_service import SetupService, configuration_from_request, cleared_configuration_fields
from workbench_backend.agents.setup_schemas import AgentInputPolicy, ProjectCreateRequest, InstructionLayer, FrozenHelperSelection, ReviewConfiguration, FrozenExecutionSelection
from workbench_backend.inference.schemas import SettingsBags
from workbench_backend.agents.helpers import freeze_helpers, freeze_settings, prepare_frozen_model, require_accepted_model_identity
from workbench_backend.agents.execution_policy import ExecutionControl, PLAN_TOOLS, PLAN_INSTRUCTIONS, require_setup_capabilities
from workbench_backend.agents.evidence import build_completion
from workbench_backend.agents.context import ContextObservation, SummaryDispatchModel, observe_context, observe_payload, token_counter_for_model, validate_retained_messages
from workbench_backend.agents.tool_outcomes import reconcile_effects, failure_for_run, result_outcome
from workbench_backend.agents.harness_backend import build_run_backend, is_reserved_framework_path, harness_scratch_root, canonical_root, roots_overlap
from workbench_backend.agents.project_admission import holds_project, project_blocker_locked, root_runs
from workbench_backend.agents.harness_profile import ensure_ordinary_chat_profile
from workbench_backend.agents.memory_skills import (
    KnowledgeMaterializePlan,
    official_agent_kwargs,
    materialize_onto_backend,
    plan_knowledge_materialization,
    clear_derived_knowledge,
    configured_memory_middleware,
)
from workbench_backend.agents.retrieval import (
    RETRIEVAL_INSTRUCTIONS,
    SEARCH_KNOWLEDGE_TOOL_NAME,
    load_retrieval_documents,
    make_document_search_tool,
    documents_from_retained_assets,
    openai_embeddings_for_deployment,
    record_retrieved_sources,
    resolve_embedding_deployment,
    validate_project_retrieval_paths,
)
from workbench_backend.agents.host_shell import (
    approval_mode_instructions,
    filesystem_permissions_for_run,
    interrupt_on_for_run,
    pending_interrupt_from_raw,
    reject_decisions_for,
    validated_decision_payloads,
)
from workbench_backend.agents.middleware import WorkbenchHarnessMiddleware
from workbench_backend.agents.tool_disclosure import (
    FIND_TOOLS, ToolDisclosureMiddleware, DeferredToolCollection, CapabilitySetupBoundary,
    LeanFilesystemMiddleware, LeanTodoListMiddleware, COMPACT_DESCRIPTIONS, has_input_policy, discovery_context,
    always_skill_dependencies,
)
from workbench_backend.assets.capture_backend import CaptureBackend
from workbench_backend.assets.schemas import RetainedAssetListFilters, RetainedAssetOrigin
from workbench_backend.agents.replay import FixtureBank
from workbench_backend.agents.schemas import (
    AgentEvent,
    AgentRun,
    AgentRunStatus,
    AgentStartRequest,
    GenerationObservation,
    HostShellFacts,
    InterruptDecisionRequest,
    PendingInterrupt,
    TaskCriteria,
    ReviewObservation,
    ToolMode,
    ToolOutcome,
    label_for_tool_mode,
)
from workbench_backend.contracts.lifecycle import (
    TERMINAL_RUN_LIFECYCLE_STATUSES,
    is_run_lifecycle_live,
)
from workbench_backend.state.checkpointer import (
    conversation_state,
    checkpoint_history,
    acheckpoint_ids_from_graph,
    open_sqlite_checkpointer,
    run_checkpoint_task,
    submit_checkpoint_task,
)
from workbench_backend.state.schemas import RelatedFile
from workbench_backend.state.preferences import tool_authorization_metadata
from workbench_backend.state.store import ApplicationStore
from workbench_backend.agents.tools import (
    KNOWLEDGE_ROUTE_READ_TOOLS,
    enabled_for_project,
    memory_proposal_tool,
    resolve_presented_tools,
    tools_for_names,
)
from workbench_backend.errors import HarnessError, ReplayError
from workbench_backend.agents.structured import (
    mark_structured_failure,
    response_format_for_run,
    update_structured_result_from_state,
)
from workbench_backend.inference.adapter import (
    DEFAULT_ADAPTER_TIMEOUT,
    RecordingTransport,
    chat_model_for_deployment,
)
from workbench_backend.inference.user_content import user_message_content
from workbench_backend.inference.connection_errors import (
    clarify_connection_error,
    classify_connection_failure,
)
from workbench_backend.inference.ids import new_id, utc_now
from workbench_backend.inference.schemas import Deployment
from workbench_backend.inference.service import ModelManager
from workbench_backend.knowledge.diagnostics import capture_settings_for_paths
from workbench_backend.state.run_views import AgentRunOperational, RunLifecycleProjection
from workbench_backend.knowledge.schemas import (
    ContextCaptureSettings,
    KnowledgeRefs,
    KnowledgeVersion,
)
from workbench_backend.knowledge.service import KnowledgeService
from workbench_backend.lab.snapshot import discard_incomplete_snapshot_staging
from workbench_backend.lab.store import LabStore

DEFAULT_SYSTEM_PROMPT = (
    "You are the Local AI Workbench embedded harness. Use enabled tools when "
    "they help answer the task. Do not invent durable knowledge or retrieval. "
    "This is not Chat or Builder."
)

ModelFactory = Callable[[AgentRun, list[dict[str, Any]]], BaseChatModel]
EmbeddingsFactory = Callable[[Deployment], Embeddings]
InteractionObserver = Callable[..., None]
log = logging.getLogger(__name__)


class HarnessService:
    """Harness runs persist in application.sqlite. Recovery remainder is OQ-004."""

    def __init__(
        self,
        manager_provider: Callable[[], ModelManager],
        *,
        model_factory: ModelFactory | None = None,
        knowledge_provider: Callable[[], KnowledgeService] | None = None,
        app_store: ApplicationStore | None = None,
        embeddings_factory: EmbeddingsFactory | None = None,
        interaction_observer: InteractionObserver | None = None,
        project_available_observer: Callable[[], None] | None = None,
        assets: Any = None,
        browser: Any = None,
        preview: Any = None,
        managed_commands: Any = None,
        desktop_automation: Any = None,
    ) -> None:
        self._manager_provider = manager_provider
        self._model_factory = model_factory or self._deployment_model
        self._knowledge_provider = knowledge_provider
        self._app_store = app_store
        self._embeddings_factory = embeddings_factory or openai_embeddings_for_deployment
        self._interaction_observer = interaction_observer
        self._project_available_observer = project_available_observer
        self.assets = assets
        self.browser = browser
        if browser is not None and hasattr(browser, "screenshot_reader"):
            browser.screenshot_reader = self.screenshot_reading_available
            browser.state_invalidator = self.invalidate_browser_state
        self.preview = preview
        self.managed_commands = managed_commands
        self.desktop_automation = desktop_automation
        self._runs: dict[str, AgentRun] = {}
        self._cancels: dict[str, threading.Event] = {}
        self._threads: dict[str, threading.Thread] = {}
        self._native_streams: dict[str, Any] = {}
        self._execution_controls: dict[str, ExecutionControl] = {}
        self._interaction_failure_runs: set[str] = set()
        self._terminal_retries: dict[str, tuple[AgentRunStatus, str]] = {}
        self._decision_ready: dict[str, threading.Event] = {}
        self._pending_decisions: dict[str, list[dict[str, str]] | None] = {}
        self._model_clients: dict[str, httpx.Client] = {}
        self._adapter_models: dict[str, Any] = {}
        self._start_cancel_guards: dict[tuple[str | None, str | None], threading.Event] = {}
        self._lock = threading.RLock()
        self._updates = threading.Condition(self._lock)
        self._startup_reconciled = False
        self._project_admissions: dict[str, tuple[str, int]] = {}

    @property
    def store(self) -> ApplicationStore:
        if self._app_store is None:
            self._app_store = ApplicationStore(self.manager.paths)
        return self._app_store

    @property
    def manager(self) -> ModelManager:
        return self._manager_provider()

    def list_runs(self) -> list[AgentRun]:
        self._reconcile_startup_once()
        return [self.get_run(item.id) for item in self.list_run_lifecycle()]

    def get_run(self, run_id: str) -> AgentRun:
        """Explicit diagnostic inspection; privacy work never holds execution locks."""
        self._reconcile_startup_once()
        operational = self.get_run_operational(run_id)
        captures = self.store.normalize_run_diagnostics(run_id)
        if captures is None:
            raise HarnessError("Unknown agent run", code="run_missing", status_code=404)
        return AgentRun.model_validate({
            **operational.model_dump(mode="python"), "model_requests": captures,
        })

    def get_run_operational(self, run_id: str) -> AgentRunOperational:
        self._reconcile_startup_once()
        with self._lock:
            run = self._runs.get(run_id)
            if run is not None:
                return self._expose_run(run)
        stored = self.store.get_run_operational(run_id)
        if stored is None:
            raise HarnessError("Unknown agent run", code="run_missing", status_code=404)
        return stored

    def list_runs_operational(self) -> list[AgentRunOperational]:
        self._reconcile_startup_once()
        stored = {item.id: item for item in self.store.list_runs_operational()}
        with self._lock:
            stored.update({run.id: self._expose_run(run) for run in self._runs.values()})
        return list(stored.values())

    def get_run_lifecycle(self, run_id: str, *, details: bool = True) -> RunLifecycleProjection:
        self._reconcile_startup_once()
        with self._lock:
            run = self._runs.get(run_id)
            if run is not None:
                return _lifecycle_projection(run, details=details)
        stored = self.store.get_run_lifecycle(run_id, details=details)
        if stored is None:
            raise HarnessError("Unknown agent run", code="run_missing", status_code=404)
        return stored

    def list_run_lifecycle(self, *, statuses: set[str] | None = None,
                           details: bool = True) -> list[RunLifecycleProjection]:
        self._reconcile_startup_once()
        stored = {item.id: item for item in self.store.list_run_lifecycle(statuses=statuses, details=details)}
        with self._lock:
            for run in self._runs.values():
                if statuses is not None and run.status not in statuses:
                    stored.pop(run.id, None)
                else:
                    stored[run.id] = _lifecycle_projection(run, details=details)
        return list(stored.values())

    @contextmanager
    def run_read_lock(self, run_id: str) -> Iterator[None]:
        """Keep a derived history read atomic with deletion of its run."""
        with self._lock:
            if run_id not in self._runs and self.store.get_run_lifecycle(run_id, details=False) is None:
                raise HarnessError("Unknown agent run", code="run_missing", status_code=404)
            yield

    @contextmanager
    def deleting_idle_runs(self, run_ids: list[str]) -> Iterator[None]:
        """Keep durable deletion and cached read paths inside the run owner.

        A terminal status can precede a worker's final cleanup. Wait for that
        owner to finish before deleting its records; never let a stale read or
        worker repopulate history after successful deletion.
        """
        with self._lock:
            for run_id in run_ids:
                run = self._runs.get(run_id) or self.store.get_run_lifecycle(run_id)
                worker = self._threads.get(run_id)
                if (run is not None and is_run_lifecycle_live(run.status)) or (worker is not None and worker.is_alive()):
                    raise HarnessError(
                        "This chat is still finishing work. Stop it or wait before deleting it.",
                        code="conversation_delete_active_runs",
                        status_code=409,
                    )
                self._close_model_client(run_id)
            yield
            for run_id in run_ids:
                self._runs.pop(run_id, None)
                self._threads.pop(run_id, None)
                self._cancels.pop(run_id, None)
                self._decision_ready.pop(run_id, None)
                self._pending_decisions.pop(run_id, None)
                self._terminal_retries.pop(run_id, None)
                self._interaction_failure_runs.discard(run_id)

    def active_workspace_run_ids(self, workspace_id: str) -> list[str]:
        """Runs still writing or executing against a workspace (quiescent check).

        `cancel_requested` is still live. Confirmed `cancelled` is not.
        """

        self._reconcile_startup_once()
        workspace = LabStore(self.manager.paths).get_workspace(workspace_id)
        with self._lock:
            memory = {run.id: run for run in self._runs.values()}
            preparing = [token for token, (path, owner_thread) in self._project_admissions.items()
                         if owner_thread != threading.get_ident() and workspace is not None and roots_overlap(path, workspace.path)]
        stored = {item.id: item for item in self.store.list_run_lifecycle()}
        for run_id, run in memory.items():
            stored_run = stored.get(run_id)
            if stored_run is not None and not is_run_lifecycle_live(stored_run.status):
                continue
            stored[run_id] = run
        return [*preparing, *[
            run.id
            for run in root_runs(list(stored.values()))
            if holds_project(run) and (run.workspace_id == workspace_id or
                (workspace is not None and run.project_path and roots_overlap(run.project_path, workspace.path)))
        ]]

    def checkpoint_state_for_run(self, run: AgentRun, checkpoint_id: str) -> dict[str, Any]:
        # Use the execution graph's exact framework topology and state schema,
        # but never initialize inference, retrieval, or materialized storage.
        from workbench_backend.agents.harness_compile import graph_checkpoint_snapshot
        agent = self._create_compiled_agent(_copy_execution_run(run), [], None, inspection_only=True)
        snapshot = graph_checkpoint_snapshot(agent, run.thread_id, checkpoint_id)
        return {"values": dict(snapshot.values), "next": tuple(snapshot.next)}

    def register_start_cancel_guard(
        self,
        thread_id: str | None,
        input_message_id: str | None,
        cancel_event: threading.Event,
    ) -> None:
        with self._lock:
            self._start_cancel_guards[(thread_id, input_message_id)] = cancel_event

    def clear_start_cancel_guard(
        self,
        thread_id: str | None,
        input_message_id: str | None,
    ) -> None:
        with self._lock:
            self._start_cancel_guards.pop((thread_id, input_message_id), None)

    def project_blocker(self, project_path: str | None) -> dict[str, Any] | None:
        self._reconcile_startup_once()
        if not project_path:
            return None
        with self._lock:
            return project_blocker_locked(self._project_admissions, self.store, self._runs, project_path)

    @contextmanager
    def project_admission(self, project_path: str | None):
        """Reserve before model preparation; durable run state then owns the root."""
        self._reconcile_startup_once()
        if not project_path:
            yield
            return
        token = new_id("admission")
        with self._lock:
            blocker = project_blocker_locked(self._project_admissions, self.store, self._runs, project_path)
            if blocker is not None:
                raise HarnessError("Another task owns this project. Wait for it to finish or resolve its unconfirmed effects before starting this task.",
                    code="project_busy", status_code=409, details=blocker)
            self._project_admissions[token] = (project_path, threading.get_ident())
        try:
            yield
        finally:
            with self._lock:
                self._project_admissions.pop(token, None)
                available = self._project_available_observer is not None and not any(
                    roots_overlap(project_path, path) for path, _owner in self._project_admissions.values()
                ) and project_blocker_locked(self._project_admissions, self.store, self._runs, project_path) is None
            if available:
                # Notify the existing queue owner only after the outermost
                # reservation is free. A live run retains its terminal wake.
                self._project_available_observer()

    def _request_project_path(self, request: AgentStartRequest) -> str | None:
        workspace = LabStore(self.manager.paths).get_workspace(request.workspace_id) if request.workspace_id else None
        if workspace is not None and (not request.project_id or workspace.origin == "restored"):
            return str(workspace.path)
        if request.project_id:
            project = SetupService(self.store, self.manager).get_project(request.project_id, require_active=True)
            if workspace is not None and canonical_root(workspace.path) != canonical_root(project.path):
                raise HarnessError("The workspace does not match the selected project.", code="project_mismatch", status_code=409)
            return project.path
        return request.project_path

    def require_thread_effects_confirmed(self, thread_id: str | None) -> None:
        """A new run cannot bypass an earlier unconfirmed action on its thread.

        Project exclusion additionally protects other chats sharing files. This
        continuation boundary also covers browser, desktop and external tools
        in projectless chats. Existing interrupt resumes keep their owned run.
        """
        self._reconcile_startup_once()
        if not thread_id:
            return
        with self._lock:
            stored = {item.id: item for item in self.store.list_run_lifecycle(thread_id=thread_id)}
            stored.update(self._runs)
            for run in root_runs(list(stored.values())):
                if run.thread_id != thread_id:
                    continue
                uncertain = [ident for ident, item in run.tool_outcomes.items()
                    if item.outcome in {"running", "uncertain"} and not item.evidence.get("acknowledged_at")]
                if uncertain:
                    raise HarnessError(
                        "An earlier action in this chat has unconfirmed effects. Inspect and acknowledge it before continuing; it will not be repeated automatically.",
                        code="effects_unconfirmed", status_code=409,
                        details={"run_id": run.id, "thread_id": thread_id,
                            "call_ids": uncertain, "recovery_action": "inspect_effects"})

    def acknowledge_project_effects(self, run_id: str) -> AgentRun:
        """Inspect first, then record explicit acceptance without replay or a success claim."""
        self._reconcile_startup_once()
        with self._lock:
            run = self._runs.get(run_id) or self.store.get_execution_run(run_id)
            if run is None:
                raise HarnessError("Unknown task.", code="run_missing", status_code=404)
            if is_run_lifecycle_live(run.status) or run.finalization_phase is not None:
                raise HarnessError("Wait for this task to stop before reviewing its effects.", code="run_still_live", status_code=409)
            updated = _copy_execution_run(run)
            reconcile_effects(updated)
            now = utc_now()
            acknowledged = []
            for ident, item in list(updated.tool_outcomes.items()):
                if item.outcome == "uncertain" and not item.evidence.get("acknowledged_at"):
                    updated.tool_outcomes[ident] = item.model_copy(update={"evidence": {**item.evidence, "acknowledged_at": now},
                        "recovery_action": "continue", "updated_at": now})
                    acknowledged.append(ident)
            updated.failure = failure_for_run(updated)
            updated.updated_at = now
            updated.events.append(AgentEvent(at=now, kind="effects_acknowledged", detail={"call_ids": acknowledged, "replayed": False}))
            self._persist_and_notify(updated)
            self._runs[run_id] = updated
            return self._expose_run(updated)

    def start(self, request: AgentStartRequest, *, instruction_snapshot: list[InstructionLayer] | None = None, helper_snapshot: list[FrozenHelperSelection] | None = None, execution_snapshot: FrozenExecutionSelection | None = None) -> AgentRun:
        self.require_thread_effects_confirmed(request.thread_id)
        with self.project_admission(self._request_project_path(request)):
            return self._start_admitted(request, instruction_snapshot=instruction_snapshot,
                helper_snapshot=helper_snapshot, execution_snapshot=execution_snapshot)

    def _start_admitted(self, request, *, instruction_snapshot=None, helper_snapshot=None, execution_snapshot=None):
        from workbench_backend.agents.harness_admission import start_admitted
        return start_admitted(self, request, instruction_snapshot=instruction_snapshot, helper_snapshot=helper_snapshot, execution_snapshot=execution_snapshot)

    def close(self, *, timeout: float = 15.0) -> None:
        """Join worker threads so SQLite files can be closed on Windows."""
        with self._lock:
            for cancel in self._cancels.values():
                cancel.set()
            for ready in self._decision_ready.values():
                ready.set()
            threads = list(self._threads.values())
            run_ids = [run_id for run_id, worker in self._threads.items() if worker.is_alive()]
        for run_id in run_ids:
            submit_checkpoint_task(self.manager.paths.checkpoints_db, self._abort_native_run(run_id))
        for thread in threads:
            thread.join(timeout=timeout)
        if self.managed_commands is not None:
            self.managed_commands.shutdown()
        with self._lock:
            self._threads = {run_id: worker for run_id, worker in self._threads.items() if worker.is_alive()}
            if self._threads:
                raise RuntimeError("Agent work has not stopped; checkpoint resources remain owned.")

    def cancel(self, run_id: str) -> AgentRun:
        """Accept a cancel request. Do not claim cancelled until the worker stops."""

        self._reconcile_startup_once()
        reject_after_restart: tuple[PendingInterrupt, threading.Event] | None = None
        with self._lock:
            run = self._require_run(run_id)
            if run.finalization_phase is not None:
                raise HarnessError(
                    "Execution has finished and this run is saving its settled result.",
                    code="run_finalizing",
                    status_code=409,
                )
            if run.parent_run_id:
                parent = self._runs.get(run.parent_run_id) or self.store.get_execution_run(run.parent_run_id)
                if parent is not None and any(item.run_id == run.id for item in parent.child_runs) and is_run_lifecycle_live(parent.status):
                    return self.cancel(parent.id)
            cancel = self._cancels.get(run_id)
            if cancel is not None:
                cancel.set()
            client = self._model_clients.get(run_id)
            ready = self._decision_ready.get(run_id)
            if ready is not None:
                ready.set()
            thread = self._threads.get(run_id)
            if (
                is_run_lifecycle_live(run.status)
                and run.pending_interrupt is not None
                and (thread is None or not thread.is_alive())
                and not self._pending_decisions.get(run_id)
            ):
                restart_cancel = cancel or self._cancels.setdefault(run_id, threading.Event())
                payloads = reject_decisions_for(run.pending_interrupt)
                self._pending_decisions[run_id] = payloads
                reject_after_restart = (run.pending_interrupt, restart_cancel)
            if is_run_lifecycle_live(run.status) and run.status is not AgentRunStatus.cancel_requested:
                run.status = AgentRunStatus.cancel_requested
                run.stop_reason = None
                run.finished_at = None
                run.updated_at = utc_now()
                run.events.append(
                    AgentEvent(
                        at=run.updated_at,
                        kind="cancel_requested",
                        detail={"requested": True, "confirmed": False},
                    )
                )
                self._persist_and_notify(run)
        if client is not None or run_id in self._native_streams:
            submit_checkpoint_task(self.manager.paths.checkpoints_db, self._abort_native_run(run_id))
        if client is not None:
            # The optional synchronous transport has no loop-bound resources.
            client.close()
        if reject_after_restart is not None:
            pending, restart_cancel = reject_after_restart
            worker = threading.Thread(
                target=self._reject_pending_after_restart,
                args=(run_id, pending, restart_cancel),
                daemon=True,
            )
            with self._lock:
                self._threads[run_id] = worker
            worker.start()
        with self._lock:
            return self._expose_run(run)

    def _browser_root(self, thread_id: str) -> AgentRun | None:
        with self._lock:
            stored = {run.id: run for run in self.store.list_run_lifecycle(thread_id=thread_id, roots_only=True)}
            stored.update(self._runs)
            roots = [run for run in stored.values() if run.thread_id == thread_id
                and not run.parent_run_id and is_run_lifecycle_live(run.status)]
            if not roots:
                return None
            if len(roots) != 1:
                raise HarnessError("This chat has overlapping owned tasks; stop them before taking browser control.",
                    code="browser_task_ownership", status_code=409)
            return self._require_run(roots[0].id)

    def _control_for_run(self, run: AgentRun) -> ExecutionControl:
        with self._lock:
            return self._execution_controls.setdefault(run.id,
                ExecutionControl(run, lambda: self._publish_control_update(run),
                    cancelled=lambda: bool(self._cancels.get(run.id) and self._cancels[run.id].is_set())))

    async def request_browser_takeover(self, thread_id: str) -> None:
        """Close root/helper dispatch authority before yielding to the caller."""
        run = await asyncio.to_thread(self._browser_root, thread_id)
        if run is None:
            return
        control = self._control_for_run(run)
        control.take_browser_control()
        await asyncio.to_thread(control.wait_for_browser_settle)

    async def release_browser_takeover(self, thread_id: str, observation: str) -> None:
        run = await asyncio.to_thread(self._browser_root, thread_id)
        if run is None:
            return
        control = self._control_for_run(run)
        control.return_browser_control(observation)
        with self._lock:
            pending = run.pending_interrupt
            worker = self._threads.get(run.id)
            needs_restart = (pending is not None and pending.kind == "browser_control"
                and (worker is None or not worker.is_alive()))
            if needs_restart:
                cancel = self._cancels.setdefault(run.id, threading.Event())
                self._decision_ready.setdefault(run.id, threading.Event())
                self._pending_decisions[run.id] = []
                worker = threading.Thread(target=self._resume_after_restart,
                    args=(run.id, [], cancel), daemon=True)
                self._threads[run.id] = worker
        if needs_restart:
            worker.start()

    async def invalidate_browser_state(self, thread_id: str, observation: str) -> None:
        """Close/Reset invalidate old page proposals, preserving native approvals."""
        run = await asyncio.to_thread(self._browser_root, thread_id)
        if run is not None:
            self._control_for_run(run).invalidate_browser_state(observation)

    def resume_interrupt(
        self,
        run_id: str,
        request: InterruptDecisionRequest,
        *,
        require_interrupt_identity: bool = False,
    ) -> AgentRun:
        """Apply Deep Agents HITL decisions. Does not invent a durable inbox."""

        self._reconcile_startup_once()
        with self._lock:
            run = self._require_run(run_id)
            pending = run.pending_interrupt
            if run.parent_run_id:
                parent = self._runs.get(run.parent_run_id) or self.store.get_execution_run(run.parent_run_id)
                if parent is not None and any(item.run_id == run.id for item in parent.child_runs):
                    raise HarnessError("Respond to this helper's approval in its parent conversation.", code="child_approval_owned_by_parent", status_code=409,
                        details={"parent_run_id": parent.id})
            if pending is None:
                raise HarnessError(
                    "This run has no pending host-shell interrupt.",
                    code="interrupt_missing",
                    status_code=409,
                )
            if pending.kind == "browser_control":
                raise HarnessError("Return to agent in the Browser tab to continue this task.",
                    code="browser_control_active", status_code=409)
            if not is_run_lifecycle_live(run.status):
                raise HarnessError(
                    "Interrupt decisions require a live run.",
                    code="run_not_live",
                    status_code=409,
                )
            if run.status is AgentRunStatus.cancel_requested:
                raise HarnessError(
                    "This run is already cancelling; the host-shell command will be rejected.",
                    code="run_cancelling",
                    status_code=409,
                )
            if self._pending_decisions.get(run_id):
                raise HarnessError(
                    "A host-shell decision is already being applied.",
                    code="interrupt_decision_pending",
                    status_code=409,
                )
            if require_interrupt_identity:
                requested_id = getattr(request, "interrupt_id", None)
                requested_namespace = list(getattr(request, "namespace", []) or [])
                if (
                    not pending.interrupt_id
                    or requested_id != pending.interrupt_id
                    or requested_namespace != pending.namespace
                ):
                    raise HarnessError(
                        "This approval is stale or belongs to another run.",
                        code="stale_interrupt",
                        status_code=409,
                    )
            try:
                payloads = validated_decision_payloads(pending, request.decisions)
            except ValueError as exc:
                code = str(exc)
                if code not in {"interrupt_decision_count", "interrupt_decision_not_allowed"}:
                    code = "interrupt_decision_invalid"
                raise HarnessError(
                    "Interrupt decision does not match the pending host-shell request.",
                    code=code,
                    status_code=400,
                ) from exc
            from workbench_backend.state.preferences import PreferenceStore
            grants = PreferenceStore(self.store)
            for action, decision in zip(pending.action_requests, request.decisions, strict=True):
                if decision.type != "approve":
                    continue
                if action.name not in run.enabled_tools or action.name not in run.presented_tools:
                    raise HarnessError(
                        "This tool is no longer available for the run.",
                        code="interrupt_tool_unavailable",
                        status_code=409,
                    )
                if decision.scope != "once":
                    grants.allow(run, action, decision.scope)
            thread = self._threads.get(run_id)
            if thread is not None and thread.is_alive():
                self._pending_decisions[run_id] = payloads
                self._decision_ready.setdefault(run_id, threading.Event()).set()
                return self._expose_run(run)
            cancel = self._cancels.setdefault(run_id, threading.Event())
            self._decision_ready.setdefault(run_id, threading.Event())
            self._pending_decisions[run_id] = payloads
        worker = threading.Thread(
            target=self._resume_after_restart,
            args=(run_id, payloads, cancel),
            daemon=True,
        )
        with self._lock:
            self._threads[run_id] = worker
        worker.start()
        return self.get_run_operational(run_id)

    def _execute(self, run_id: str) -> None:
        with self._lock:
            run = self._runs[run_id]
            cancel = self._cancels[run_id]
            already_terminal = run.status in TERMINAL_RUN_LIFECYCLE_STATUSES
            requested_before_start = (
                not already_terminal
                and (cancel.is_set() or run.status is AgentRunStatus.cancel_requested)
            )
            if not already_terminal and not requested_before_start:
                run.status = AgentRunStatus.running
                run.updated_at = utc_now()
                run.events.append(AgentEvent(at=run.updated_at, kind="started", detail={}))
                self._persist_and_notify(run)
        if already_terminal:
            return
        if requested_before_start:
            self._finish(run, AgentRunStatus.cancelled, "cancelled")
            return
        http_sink: list[dict[str, Any]] = []
        try:
            fixture_bank = (
                FixtureBank(run.recorded_fixtures)
                if run.tool_mode is ToolMode.recorded_tool
                else None
            )
            if run.resume_checkpoint_id:
                payload: Any = None
            else:
                user_message: dict[str, Any] = {
                    "role": "user",
                    "content": user_message_content(run.task, run.content_blocks),
                }
                input_message_id = getattr(run, "input_message_id", None)
                if input_message_id:
                    user_message["id"] = input_message_id
                payload = {"messages": [user_message],
                    "skills_metadata": None,
                    "rubric": (run.review.criteria.strip() or run.task) if run.review.enabled else "",
                    **({"structured_response": None} if run.output_schema is not None else {})}
            run_checkpoint_task(self.manager.paths.checkpoints_db,
                self._run_owned_graph(run, http_sink, fixture_bank, cancel, payload))
        except ReplayError as exc:
            self._collect_related_files(run)
            if cancel.is_set():
                self._finish(run, AgentRunStatus.cancelled, "cancelled")
                return
            run.error = str(exc)
            run.events.append(
                AgentEvent(
                    at=utc_now(),
                    kind="recorded_replay_failed",
                    detail={"code": exc.code, "error": exc.message, **exc.details},
                )
            )
            self._finish(run, AgentRunStatus.failed, "failed")
        except Exception as exc:  # noqa: BLE001 - surface harness failure, do not invent success
            self._collect_related_files(run)
            if isinstance(exc, HarnessError) and exc.code == "interaction_persistence_failed":
                run.error = str(exc)
                self._finish(run, AgentRunStatus.failed, "interaction_persistence_failed")
                return
            if cancel.is_set():
                self._finish(run, AgentRunStatus.cancelled, "cancelled")
                return
            run.error = clarify_connection_error(exc)
            run.failure = failure_for_run(run, code=_failure_code(run, exc))
            self._finish(run, AgentRunStatus.failed, "failed")
        finally:
            with self._lock:
                self._pending_decisions[run_id] = None
            self._close_model_client(run_id)

    def _resume_after_restart(
        self,
        run_id: str,
        decisions: list[dict[str, str]],
        cancel: threading.Event,
    ) -> None:
        """Resume a persisted interrupt from the same LangGraph thread."""

        with self._lock:
            run = self._require_run(run_id)
        http_sink: list[dict[str, Any]] = []
        try:
            fixture_bank = (
                FixtureBank(run.recorded_fixtures)
                if run.tool_mode is ToolMode.recorded_tool
                else None
            )
            run_checkpoint_task(self.manager.paths.checkpoints_db,
                self._run_owned_graph(run, http_sink, fixture_bank, cancel,
                    Command(resume=_resume_value(decisions)), decisions=decisions))
        except ReplayError as exc:
            self._collect_related_files(run)
            if cancel.is_set():
                self._finish(run, AgentRunStatus.cancelled, "cancelled")
                return
            run.error = str(exc)
            run.events.append(
                AgentEvent(
                    at=utc_now(),
                    kind="recorded_replay_failed",
                    detail={"code": exc.code, "error": exc.message, **exc.details},
                )
            )
            self._finish(run, AgentRunStatus.failed, "failed")
        except Exception as exc:  # noqa: BLE001 - surface harness failure, do not invent success
            self._collect_related_files(run)
            if isinstance(exc, HarnessError) and exc.code == "interaction_persistence_failed":
                run.error = str(exc)
                self._finish(run, AgentRunStatus.failed, "interaction_persistence_failed")
                return
            if cancel.is_set():
                self._finish(run, AgentRunStatus.cancelled, "cancelled")
                return
            run.error = clarify_connection_error(exc)
            run.failure = failure_for_run(run, code=_failure_code(run, exc))
            self._finish(run, AgentRunStatus.failed, "failed")
        finally:
            with self._lock:
                self._pending_decisions[run_id] = None
            self._close_model_client(run_id)

    def _reject_pending_after_restart(
        self,
        run_id: str,
        pending: PendingInterrupt,
        cancel: threading.Event,
    ) -> None:
        """Cancel a recovered approval by rejecting at the saved checkpoint."""

        with self._lock:
            run = self._require_run(run_id)
        http_sink: list[dict[str, Any]] = []
        try:
            fixture_bank = (
                FixtureBank(run.recorded_fixtures)
                if run.tool_mode is ToolMode.recorded_tool
                else None
            )
            run_checkpoint_task(self.manager.paths.checkpoints_db,
                self._run_owned_graph(run, http_sink, fixture_bank, cancel, None, reject=pending))
        except Exception as exc:  # noqa: BLE001 - surface failure without replaying approval
            self._collect_related_files(run)
            run.error = clarify_connection_error(exc)
            self._finish(run, AgentRunStatus.failed,
                "interaction_persistence_failed" if isinstance(exc, HarnessError) and exc.code == "interaction_persistence_failed" else "failed")
        finally:
            cancel.set()
            with self._lock:
                self._pending_decisions[run_id] = None
            self._close_model_client(run_id)

    @asynccontextmanager
    async def _worker_tools_context(self, run):
        # Session-bound tools enter here on the common loop and stay open across
        # native approval waits. Synchronous setup/file work cannot block it.
        async with AsyncExitStack() as stack:
            if has_input_policy(run):
                loader = DeferredToolCollection(run, stack, connections=self.connections,
                    browser=self.browser, desktop=self.desktop_automation,
                    publish=lambda: self._publish_control_update(run))
                required_tools, required_connections = (always_skill_dependencies(run, self._knowledge_plan_for_run(run))
                    if run.skill_version_refs and "always" in run.input_policy.reference_loading.values() else (set(), set()))
                from workbench_backend.agents.tools import FILESYSTEM_TOOL_NAMES, SHELL_TOOL_NAMES
                if not run.project_path and required_tools.intersection({*FILESYSTEM_TOOL_NAMES, *SHELL_TOOL_NAMES, "start_preview", "stop_preview", "preview_status"}) - {"read_file", "ls"}:
                    raise HarnessError("Required file and shell tools need a project folder.", code="filesystem_requires_project", status_code=409)
                for name in sorted(required_tools):
                    if loader.owns(name):
                        await loader.require_ready(name)
                essential_connections = required_connections | {item.id for item in run.connection_snapshots
                    if required_tools.intersection(tool.name for tool in item.tools)}
                if essential_connections:
                    for item in run.connection_snapshots:
                        if item.id in essential_connections:
                            await asyncio.to_thread(self.connections.validate_snapshot, item)
                    await asyncio.to_thread(self.connections.snapshot, sorted(essential_connections))
                yield loader
                return
            external_tools = await stack.enter_async_context(self.connections.open_tools(run))
            browser_tools = (
                await stack.enter_async_context(self.browser.open_tools(run))
                if self.browser is not None else []
            )
            yield [*external_tools, *browser_tools]

    @asynccontextmanager
    async def _compiled_agent_context(self, run, http_sink, fixture_bank):
        control = self._control_for_run(run)
        try:
            async with self._worker_tools_context(run) as external_tools:
                async with control.model_lock(run.deployment_id):
                    agent = await asyncio.to_thread(self._create_compiled_agent, run, http_sink, fixture_bank,
                        external_tools=external_tools, execution_control=control)
                yield agent
        finally:
            with self._lock:
                self._execution_controls.pop(run.id, None)

    @property
    def connections(self):
        from workbench_backend.connections.service import ConnectionService
        return ConnectionService(self.store)

    async def _run_owned_graph(self, run, http_sink, fixture_bank, cancel, payload, *, decisions=None, reject=None):
        async with self._compiled_agent_context(run, http_sink, fixture_bank) as agent:
            try:
                if reject is not None:
                    await self._aresume_reject_then_stop(agent, run, reject, _invoke_config(run))
                else:
                    if decisions is not None:
                        if run.pending_interrupt is not None and run.pending_interrupt.kind == "browser_control":
                            payload = await self._browser_resume_command(agent, run)
                        await asyncio.to_thread(self._clear_pending_interrupt, run, decisions)
                    await self._adrive_until_terminal(run, agent, cancel, payload)
            except BaseException as exc:
                if not isinstance(exc, HarnessError) or exc.code != "checkpoint_linkage_failed":
                    try:
                        await self._alink_run(run, agent)
                    except Exception:  # noqa: BLE001 - retain the original graph or display failure
                        pass
                raise

    def screenshot_reading_available(self, run: AgentRun) -> bool:
        """Read existing setup evidence without dispatching a capability probe."""

        from workbench_backend.agents.harness_compile import screenshot_reading_available
        return screenshot_reading_available(self.manager, run)

    def prepare_screenshot_reading(self, run: AgentRun, *, model: BaseChatModel | None = None) -> bool:
        """Prove screenshot delivery once for this loaded setup, then remember it."""

        from workbench_backend.agents.harness_compile import prepare_screenshot_reading
        return prepare_screenshot_reading(self.manager, run, model=model)

    def _create_compiled_agent(self, run, http_sink, fixture_bank, *, inspection_only=False, external_tools=None, execution_control=None, is_child=False):
        from workbench_backend.agents.harness_compile import create_compiled_agent
        return create_compiled_agent(self, run, http_sink, fixture_bank, inspection_only=inspection_only, external_tools=external_tools, execution_control=execution_control, is_child=is_child)

    async def _adrive_until_terminal(
        self,
        run: AgentRun,
        agent: Any,
        cancel: threading.Event,
        payload: Any,
    ) -> None:
        config = _invoke_config(run)
        current = payload
        seen_messages = await self._seed_native_audit_seen(agent, config)
        message_nodes: dict[str, str] = {}
        while True:
            if cancel.is_set():
                await self._alink_run(run, agent)
                await asyncio.to_thread(self._finish, run, AgentRunStatus.cancelled, "cancelled")
                return
            pending = await self._stream_until_pause(agent, run, current, cancel, config, seen_messages, message_nodes)
            if cancel.is_set():
                if pending is not None:
                    await self._aresume_reject_then_stop(agent, run, pending, config, message_nodes)
                else:
                    await self._alink_run(run, agent)
                    await asyncio.to_thread(self._finish, run, AgentRunStatus.cancelled, "cancelled")
                return
            if pending is None:
                await self._alink_run(run, agent)
                if run.structured_output is not None and run.structured_output.validation_status != "valid":
                    run.error = run.structured_output.error or "The model did not produce a valid structured result."
                    await asyncio.to_thread(self._finish, run, AgentRunStatus.failed, "structured_output_invalid")
                    return
                run.completion = build_completion(run)
                if run.review.enabled and run.review_observation.status != "satisfied":
                    run.error = "Review limit reached; results are retained." if run.review_observation.status == "max_iterations_reached" else "Review did not confirm the requested result; inspect the retained findings."
                    await asyncio.to_thread(self._finish, run, AgentRunStatus.failed, "review_" + run.review_observation.status)
                    return
                await asyncio.to_thread(self._finish, run, AgentRunStatus.completed, "completed")
                return
            await self._alink_run(run, agent)
            await asyncio.to_thread(self._publish_interrupt, run, pending)
            if pending.kind == "browser_control":
                control = self._control_for_run(run)
                returned = await asyncio.to_thread(control.wait_for_browser_return)
                if not returned or cancel.is_set():
                    await self._alink_run(run, agent)
                    await asyncio.to_thread(self._finish, run, AgentRunStatus.cancelled, "cancelled")
                    return
                await asyncio.to_thread(self._clear_pending_interrupt, run, [])
                current = await self._browser_resume_command(agent, run)
                continue
            decisions = await asyncio.to_thread(self._wait_for_interrupt_decisions, run.id, cancel)
            if decisions is None:
                await self._aresume_reject_then_stop(agent, run, pending, config, message_nodes)
                return
            if not await asyncio.to_thread(self._control_for_run(run).wait_for_browser_return):
                await self._aresume_reject_then_stop(agent, run, pending, config, message_nodes)
                return
            await asyncio.to_thread(self._clear_pending_interrupt, run, decisions)
            current = Command(resume=_resume_value(decisions))

    async def _browser_resume_command(self, agent: Any, run: AgentRun) -> Command:
        """Address every native browser boundary while retaining other approvals."""
        state = await agent.aget_state(_invoke_config(run), subgraphs=True)
        identities: set[str] = set()
        def collect(snapshot):
            for item in getattr(snapshot, "interrupts", ()):
                value = getattr(item, "value", None)
                ident = getattr(item, "id", None)
                if isinstance(value, dict) and value.get("kind") == "browser_control" and ident:
                    identities.add(str(ident))
            for task in getattr(snapshot, "tasks", ()):
                collect(task)
                nested = getattr(task, "state", None)
                if nested is not None and not isinstance(nested, dict):
                    collect(nested)
        collect(state)
        if not identities:
            raise HarnessError("The browser interruption has no saved graph boundary; no action was repeated.",
                code="browser_interrupt_missing", status_code=409)
        return Command(resume={ident: {"browser_control": "agent"} for ident in identities})

    async def _stream_until_pause(
        self,
        agent: Any,
        run: AgentRun,
        payload: Any,
        cancel: threading.Event,
        config: dict[str, Any],
        seen_messages: set[tuple[str, str]],
        message_nodes: dict[str, str],
    ) -> Any:
        stream = None
        pending = None
        try:
            stream = await agent.astream_events(payload, config=config, version="v3")
            self._native_streams[run.id] = stream
            if cancel.is_set():
                return None
            async for event in stream:
                try:
                    await asyncio.to_thread(self._observe_interaction, run, event)
                except Exception as exc:  # noqa: BLE001 - essential display publication failed
                    raise self._interaction_persistence_failure(run, exc) from exc
                found = _pending_from_native_event(event)
                if found is not None and (pending is None or len(found.namespace) > len(pending.namespace)):
                    pending = found
                if cancel.is_set():
                    return None
                await asyncio.to_thread(self._ingest_native_event, run, event, seen_messages, message_nodes)
        except Exception as exc:  # noqa: BLE001 - interrupt may surface as GraphInterrupt
            if isinstance(exc, HarnessError) and exc.code == "interaction_persistence_failed":
                raise
            run.structured_output = mark_structured_failure(run.structured_output, str(exc))
            found = pending_interrupt_from_raw(exc) or pending_interrupt_from_raw(
                getattr(exc, "interrupts", None)
            )
            if found is not None:
                return self._owned_child_interrupt(run, found)
            raise
        finally:
            self._native_streams.pop(run.id, None)
            await self._close_native_stream(stream)
        if pending is not None:
            return self._owned_child_interrupt(run, pending)
        try:
            state = await agent.aget_state(config)
        except Exception:  # noqa: BLE001 - missing state is a completed or failed stream
            return None
        return pending_interrupt_from_raw(getattr(state, "interrupts", None))

    def _owned_child_interrupt(self, run: AgentRun, pending: PendingInterrupt) -> PendingInterrupt:
        """Use the child's saved checkpoint namespace for an inline approval."""
        if not pending.interrupt_id:
            return pending
        with self._lock:
            for activity in run.child_runs:
                child = self._runs.get(activity.run_id) or self.store.get_execution_run(activity.run_id)
                owned = child.pending_interrupt if child is not None else None
                if owned is not None and owned.interrupt_id == pending.interrupt_id and owned.namespace == activity.namespace:
                    return owned
        return pending

    def _interaction_persistence_failure(self, run: AgentRun, exc: Exception) -> HarnessError:
        with self._lock:
            self._interaction_failure_runs.add(run.id)
            run.events.append(AgentEvent(at=utc_now(), kind="interaction_persistence_failed",
                detail={"code": "interaction_persistence_failed", "message": str(exc)}))
        return HarnessError(
            f"Interaction events could not be saved: {exc}",
            code="interaction_persistence_failed", status_code=500,
        )

    def _publish_interrupt(self, run: AgentRun, pending: Any) -> None:
        if isinstance(pending, PendingInterrupt) and not pending.interrupt_id:
            pending = pending.model_copy(update={"interrupt_id": _fallback_interrupt_id(run)})
        with self._lock:
            run.pending_interrupt = pending
            run.updated_at = utc_now()
            run.events.append(
                AgentEvent(
                    at=run.updated_at,
                    kind="interrupt",
                    detail=pending.model_dump(mode="json"),
                )
            )
            self._persist_and_notify(run)

    def _clear_pending_interrupt(
        self,
        run: AgentRun,
        decisions: list[dict[str, str]],
    ) -> None:
        with self._lock:
            run.pending_interrupt = None
            # The continuation already owns this decision. Release it together
            # with the old interrupt, never while that interrupt can be answered.
            if self._pending_decisions.get(run.id) == decisions:
                self._pending_decisions[run.id] = None
            run.updated_at = utc_now()
            run.events.append(
                AgentEvent(
                    at=run.updated_at,
                    kind="interrupt_resolved",
                    detail={"decisions": decisions},
                )
            )
            self._persist_and_notify(run)

    def _wait_for_interrupt_decisions(
        self,
        run_id: str,
        cancel: threading.Event,
    ) -> list[dict[str, str]] | None:
        while True:
            if cancel.is_set():
                return None
            with self._lock:
                ready = self._decision_ready.get(run_id)
            if ready is None:
                return None
            if ready.wait(timeout=0.2):
                with self._lock:
                    decisions = self._pending_decisions.get(run_id)
                    ready.clear()
                if cancel.is_set():
                    return None
                if decisions is not None:
                    return decisions

    async def _aresume_reject_then_stop(
        self,
        agent: Any,
        run: AgentRun,
        pending: Any,
        config: dict[str, Any],
        message_nodes: dict[str, str] | None = None,
    ) -> None:
        payloads = reject_decisions_for(pending)
        await asyncio.to_thread(self._clear_pending_interrupt, run, payloads)
        seen_messages = await self._seed_native_audit_seen(agent, config)
        message_nodes = message_nodes if message_nodes is not None else {}
        stream = None
        try:
            stream = await agent.astream_events(
                Command(resume=_resume_value(payloads)),
                config=config,
                version="v3",
            )
            async for chunk in stream:
                await asyncio.to_thread(self._observe_interaction, run, chunk)
                if _pending_from_native_event(chunk) is not None:
                    break
                await asyncio.to_thread(self._ingest_native_event, run, chunk, seen_messages, message_nodes)
        except Exception:  # noqa: BLE001 - cancel still wins if reject resume fails
            pass
        finally:
            await self._close_native_stream(stream)
        await self._alink_run(run, agent)
        await asyncio.to_thread(self._finish, run, AgentRunStatus.cancelled, "cancelled")

    def _publish_control_update(self, run: AgentRun, mutation=None) -> None:
        with self._lock:
            if mutation is not None:
                mutation()
            self._persist_and_notify(run)

    def _finish(self, run: AgentRun, status: AgentRunStatus, stop_reason: str) -> None:
        commands_settled = True
        if self.managed_commands is not None and run.status not in TERMINAL_RUN_LIFECYCLE_STATUSES:
            command_stop_errors = []
            for owner_id in [run.id, *(child.run_id for child in run.child_runs)]:
                try:
                    self.managed_commands.stop_run(owner_id)
                except Exception as error:
                    command_stop_errors.append(str(error))
            try:
                # Settle owned children before the terminal record is saved,
                # outside the run lock used by observer/effect persistence.
                if command_stop_errors:
                    raise RuntimeError("; ".join(command_stop_errors))
            except Exception as error:
                commands_settled = False
                run.error = str(error)
                run.tool_outcomes["owned-command-cleanup"] = ToolOutcome(call_id="owned-command-cleanup", name="start_command",
                    outcome="uncertain", failure_category="runtime", recovery_action="inspect_effects",
                    detail="An owned command could not be confirmed stopped. Inspect its effects; it was not replayed.",
                    evidence={"process_stop_confirmed": False}, updated_at=utc_now())
                status, stop_reason = AgentRunStatus.failed, "effects_unconfirmed"
        with self._lock:
            if run.status in TERMINAL_RUN_LIFECYCLE_STATUSES:
                if run.status is AgentRunStatus.cancelled and status is not AgentRunStatus.cancelled:
                    run.stop_reason = "cancelled"
                    run.finished_at = run.finished_at or utc_now()
                    run.updated_at = run.finished_at
                    self._persist_and_notify(run)
                return
            recovering = run.finalization_phase is not None
            if recovering:
                # Settlement was already durable. Do not copy or restore the project.
                if commands_settled:
                    status = AgentRunStatus(run.settled_status or "failed")
                    stop_reason = run.settled_stop_reason or status.value
                else:
                    run.settled_status = status.value
                    run.settled_stop_reason = stop_reason
                snapshot_id = self._settled_snapshot_id(run)
                if snapshot_id is not None:
                    try:
                        discard_incomplete_snapshot_staging(self.manager.paths, snapshot_id)
                    except OSError:
                        pass
            else:
                if run.stop_reason == "tool_budget_exhausted" and status == AgentRunStatus.failed:
                    stop_reason = run.stop_reason
                cancel = self._cancels.get(run.id)
                if commands_settled and cancel is not None and cancel.is_set() and status is not AgentRunStatus.cancelled:
                    status, stop_reason = AgentRunStatus.cancelled, "cancelled"
            self._commit_terminal_run(run, status, stop_reason)

    @staticmethod
    def _settled_snapshot_id(run: AgentRun) -> str | None:
        for event in reversed(run.events):
            if event.kind == "finalizing":
                ident = event.detail.get("snapshot_id")
                if isinstance(ident, str) and ident.startswith("snap_") and all(
                    char.isalnum() or char in {"_", "-"} for char in ident
                ):
                    return ident
                return None
        return None

    def _merge_latest_generation_sample(self, run: AgentRun) -> None:
        model = self._adapter_models.get(run.id)
        completed = getattr(model, "generation_request_samples", None)
        if callable(completed):
            retained = {sample.request_id: sample for sample in run.generation_history if sample.request_id}
            for sample in completed():
                if not isinstance(sample, dict) or not sample.get("request_id"):
                    continue
                try:
                    retained[sample["request_id"]] = GenerationObservation(**sample,
                        context_limit=run.context_observation.capacity_tokens if run.context_observation else None)
                except (TypeError, ValueError):
                    continue
            run.generation_history = list(retained.values())[-64:]
        all_samples = getattr(model, "latest_generation_samples", None)
        if callable(all_samples):
            samples = all_samples()
        else:
            accessor = getattr(model, "latest_generation_sample", None)
            samples = {"work": accessor()} if callable(accessor) else {}
        for purpose, sample in samples.items():
            if not isinstance(sample, dict):
                continue
            if sample.get("reset"):
                if purpose == "work":
                    run.generation_observation = None
                else:
                    run.housekeeping_generation.pop(purpose, None)
                continue
            try:
                measured = GenerationObservation(
                    **sample,
                    context_limit=run.context_observation.capacity_tokens if run.context_observation else None,
                )
            except (TypeError, ValueError):
                # A malformed measurement cannot change the graph's settled result.
                continue
            if purpose == "work":
                run.generation_observation = measured
            else:
                run.housekeeping_generation[purpose] = measured

    def _commit_terminal_run(self, run: AgentRun, status: AgentRunStatus, stop_reason: str) -> None:
        settled_copy = _copy_execution_run(run)
        self._merge_latest_generation_sample(run)
        run.finalization_phase = None
        run.activity_phase = None
        run.browser_control = "agent"
        run.settled_status = None
        run.settled_stop_reason = None
        run.status = status
        run.stop_reason = stop_reason
        reconcile_effects(run)
        run.failure = failure_for_run(run, code=run.failure.code if run.failure else None)
        run.finished_at = utc_now()
        run.updated_at = run.finished_at
        # Inline children have no detached worker once their owning graph ends.
        for activity in run.child_runs:
            child = self._runs.get(activity.run_id) or self.store.get_execution_run(activity.run_id)
            if child is None and activity.status not in {"completed", "failed", "cancelled"}:
                activity.status = "cancelled" if status == AgentRunStatus.cancelled else "failed"
                activity.error = (None if status == AgentRunStatus.cancelled else
                    activity.error or "The parent run ended before this helper was admitted.")
                continue
            if child is not None and is_run_lifecycle_live(child.status):
                child.status = AgentRunStatus.cancelled if status == AgentRunStatus.cancelled else AgentRunStatus.failed
                child.stop_reason = "parent_" + str(status.value)
                child.finished_at = run.finished_at
                child.updated_at = run.finished_at
                child.pending_interrupt = None
                child.activity_phase = None
                activity.status = child.status.value
                self._persist(child)
        if run.generation_observation is not None and run.generation_observation.phase in {"prompt_processing", "generating"}:
            run.generation_observation = run.generation_observation.model_copy(update={
                "phase": "interrupted", "interval": "last_model_call_generation", "measured_at": run.finished_at,
            })
        for purpose, observed in list(run.housekeeping_generation.items()):
            if observed.phase in {"prompt_processing", "generating"}:
                run.housekeeping_generation[purpose] = observed.model_copy(update={
                    "phase": "interrupted", "interval": "last_model_call_generation", "measured_at": run.finished_at,
                })
        event_detail: dict[str, Any] = {
            "stop_reason": stop_reason,
            "error": run.error,
            "confirmed": True,
        }
        failure_code = classify_connection_failure(run.error or "")
        if failure_code:
            event_detail["code"] = failure_code
        elif stop_reason == "interaction_persistence_failed":
            event_detail["code"] = "interaction_persistence_failed"
        run.events.append(AgentEvent(at=run.updated_at, kind=status.value, detail=event_detail))
        try:
            self._persist_and_notify(run)
        except Exception:
            # The SQLite write can fail after the run was mutated in memory.
            # Restore the saved settlement so a later read can retry without
            # publishing a second terminal event or recapturing the project.
            try:
                saved = self.store.get_execution_run(run.id)
            except Exception:  # noqa: BLE001 - keep the original persistence error
                saved = None
            if saved is None or is_run_lifecycle_live(saved.status):
                self._runs[run.id] = settled_copy
                self._terminal_retries[run.id] = (status, stop_reason)
                self._startup_reconciled = False
                raise
            # The run is durably terminal. A display write may still be down;
            # the subscriber repairs from this record or receives a stream error.
            if saved.status is not status:
                raise
            log.exception("Terminal interaction projection failed for %s", run.id)
            self._updates.notify_all()
        self._terminal_retries.pop(run.id, None)
        self._interaction_failure_runs.discard(run.id)

    async def _seed_native_audit_seen(self, agent: Any, config: dict[str, Any]) -> set[tuple[str, str]]:
        try:
            state = await agent.aget_state(config)
            values = getattr(state, "values", {}) or {}
        except Exception:
            return set()
        messages = values.get("messages") if isinstance(values, dict) else None
        if not isinstance(messages, list):
            return set()
        return {
            key
            for message in messages
            if (key := _native_message_identity(message)) is not None
        }

    def _ingest_native_event(
        self,
        run: AgentRun,
        event: Any,
        seen_messages: set[tuple[str, str]],
        message_nodes: dict[str, str] | None = None,
    ) -> None:
        if not isinstance(event, dict):
            return
        params = event.get("params")
        if not isinstance(params, dict) or params.get("namespace") not in ([], ()):
            return
        data = params.get("data")
        metadata = params.get("metadata")
        if isinstance(data, tuple) and len(data) == 2:
            data, metadata = data
        if event.get("method") == "messages":
            if isinstance(data, dict) and data.get("event") == "message-start":
                message_id = data.get("id")
                node = metadata.get("langgraph_node") if isinstance(metadata, dict) else None
                node = node or params.get("node")
                if isinstance(message_id, str) and isinstance(node, str) and node:
                    (message_nodes if message_nodes is not None else {})[message_id] = node
            return
        if event.get("method") != "values":
            return
        if not isinstance(data, dict):
            return
        self._ingest_native_values(run, data, seen_messages, message_nodes or {})

    def _ingest_native_values(
        self,
        run: AgentRun,
        values: dict[str, Any],
        seen_messages: set[tuple[str, str]],
        message_nodes: dict[str, str] | None = None,
    ) -> None:
        messages = values.get("messages")
        if not isinstance(messages, list):
            return
        changed = False
        for message in messages:
            key = _native_message_identity(message)
            if key is None or key in seen_messages:
                continue
            seen_messages.add(key)
            if self._is_internal_summary_message(message):
                continue
            message_id = getattr(message, "id", None)
            node = message_nodes.pop(message_id, None) if message_nodes and isinstance(message_id, str) else None
            if self._ingest_message(run, message, node):
                changed = True
        if changed:
            with self._lock:
                try:
                    self._persist_and_notify(run)
                except Exception as exc:  # noqa: BLE001 - audit publication is essential
                    raise self._interaction_persistence_failure(run, exc) from exc

    def _is_internal_summary_message(self, message: Any) -> bool:
        additional = getattr(message, "additional_kwargs", None)
        return isinstance(additional, dict) and additional.get("lc_source") in {"summarization", "rubric_grader"}

    def _observe_interaction(self, run: AgentRun, event: dict[str, Any] | None, *, telemetry: bool = False) -> None:
        if self._interaction_observer is None:
            return
        # Publication never carries captures. Its serializer excludes them at
        # source; diagnostic inspection and capture creation own privacy policy.
        self._interaction_observer(run, event, **({"telemetry": True} if telemetry else {}))

    def projection_run(self, run_id: str) -> dict[str, Any]:
        """Run fields for a live display frame, without captured model requests."""
        return self.get_run_operational(run_id).model_dump(mode="json")

    async def _close_native_stream(self, stream: Any) -> None:
        if stream is None:
            return
        abort = getattr(stream, "abort", None)
        if callable(abort):
            await abort()
            return
        close = getattr(stream, "aclose", None)
        if callable(close):
            await close()

    def _ingest_message(self, run: AgentRun, message: BaseMessage | Any, node: str | None) -> bool:
        if isinstance(message, AIMessage) and message.invalid_tool_calls:
            for call in message.invalid_tool_calls:
                if call.get("id"):
                    run.tool_outcomes[call["id"]] = ToolOutcome(call_id=call["id"], name=call.get("name") or "unknown",
                        outcome="incomplete_arguments", failure_category="input", recovery_action="continue",
                        detail="The model stopped before producing valid arguments. This call was not executed.", updated_at=utc_now())
            raise HarnessError("The model returned malformed tool arguments. No invalid call was executed.", code="invalid_tool_call", status_code=409)
        now = utc_now()
        emitted = False
        if isinstance(message, AIMessage) and message.tool_calls:
            known_child_calls = ({item.get("id") for item in run.tool_invocations if item.get("id")}
                if run.parent_run_id else set())
            for call in message.tool_calls:
                name = call.get("name") if isinstance(call, dict) else getattr(call, "name", None)
                args = call.get("args") if isinstance(call, dict) else getattr(call, "args", {})
                call_id = call.get("id") if isinstance(call, dict) else getattr(call, "id", None)
                if call_id and call_id in known_child_calls:
                    # A resumed child stream can replay its saved tool-call
                    # message before emitting the new tool result.
                    continue
                invocation = {"name": name, "args": args, "id": call_id}
                if node:
                    invocation["node"] = node
                run.tool_invocations.append(invocation)
                run.events.append(AgentEvent(at=now, kind="tool_call", detail=invocation))
                if call_id:
                    known_child_calls.add(call_id)
                emitted = True
            run.updated_at = now
            return emitted
        if isinstance(message, ToolMessage):
            self._settle_answered_question(run, message)
            run.events.append(
                AgentEvent(
                    at=now,
                    kind="tool_result",
                    detail={
                        "name": message.name,
                        "content": _safe_tool_event_content(message),
                        "tool_call_id": message.tool_call_id,
                        "status": message.status,
                        "outcome": "failed" if message.status == "error" else "succeeded",
                        **_tool_media_reference(message),
                        **tool_authorization_metadata(run, message.tool_call_id),
                        **({"node": node} if node else {}),
                    },
                )
            )
            run.updated_at = now
            return True
        if isinstance(message, AIMessage) and (message.content or message.content_blocks):
            run.events.append(
                AgentEvent(
                    at=now,
                    kind="assistant_message",
                    detail=_assistant_event_detail(message, node),
                )
            )
            emitted = True
        run.updated_at = now
        return emitted

    @staticmethod
    def _settle_answered_question(run: AgentRun, message: ToolMessage) -> None:
        """HITL answers bypass tool dispatch; the native result settles their ledger row."""
        if message.name != "ask_user" or not message.tool_call_id:
            return
        previous = run.tool_outcomes.get(message.tool_call_id)
        if previous is None or previous.name != "ask_user" or previous.outcome != "not_dispatched":
            return
        settled = result_outcome(message.tool_call_id, "ask_user", message, previous.evidence)
        if message.status == "error":
            settled = settled.model_copy(update={"failure_category": "cancelled"})
        run.tool_outcomes[message.tool_call_id] = settled

    def _deployment_model(self, run: AgentRun, http_sink: list[dict[str, Any]]) -> BaseChatModel:
        require_accepted_model_identity(self.manager.get_deployment(run.deployment_id),
            run.effective_setup.bags if run.effective_setup is not None else None)
        deployment = self.manager.ensure_deployment_ready(run.deployment_id)
        require_accepted_model_identity(deployment, run.effective_setup.bags if run.effective_setup is not None else None)
        per_request = run.effective_setup.bags.per_request if run.effective_setup is not None else None
        client = httpx.Client(
            transport=RecordingTransport(http_sink),
            timeout=DEFAULT_ADAPTER_TIMEOUT,
        )
        with self._lock:
            self._model_clients[run.id] = client
        model = chat_model_for_deployment(
            deployment,
            per_request=per_request,
            capture_sink=http_sink,
            http_client=client,
        )
        with self._lock:
            self._adapter_models[run.id] = model
        return model

    def _close_model_client(self, run_id: str) -> None:
        with self._lock:
            client = self._model_clients.pop(run_id, None)
            model = self._adapter_models.pop(run_id, None)
        if client is not None:
            client.close()
        if model is not None:
            run_checkpoint_task(self.manager.paths.checkpoints_db, model.aclose())

    async def _abort_native_run(self, run_id: str) -> None:
        # AsyncGraphRunStream.abort cancels the in-flight graph pull and settles
        # its checkpoint writes. The driver then records confirmed cancellation.
        stream = self._native_streams.get(run_id)
        if stream is not None:
            await stream.abort()

    def _live_search_knowledge_tool(self, run: AgentRun, backend: Any, *, inspection_only: bool = False) -> Any:
        """Build the official search tool, or none for recorded-tool / no retrieval."""

        if run.tool_mode is ToolMode.recorded_tool:
            return None
        if SEARCH_KNOWLEDGE_TOOL_NAME not in run.presented_tools:
            return None
        if backend is None:
            return None
        if inspection_only:
            return make_document_search_tool(lambda: [], backend)
        session = self.assets.session_for_run(run) if self.assets is not None else None

        def documents():
            return [*documents_from_retained_assets(self.store, run.retained_asset_ids,
                session_id=session.id if session else None, project_path=run.project_path),
                *load_retrieval_documents([], list(run.retrieval_project_paths), run.project_path)]

        def embeddings():
            deployment = resolve_embedding_deployment(self.manager, run.embedding_deployment_id)
            return self._embeddings_factory(deployment)

        def on_retrieved(sources: list[str]) -> None:
            run.retrieved_material = record_retrieved_sources(run.retrieved_material, sources)

        return make_document_search_tool(documents, backend,
            embeddings_factory=embeddings if run.embedding_deployment_id else None,
            on_retrieved=on_retrieved)

    def _resolve_knowledge_refs(self, request: AgentStartRequest, *, frozen: bool = False) -> KnowledgeRefs:
        requested = (
            request.memory_version_refs
            or request.skill_version_refs
            or request.protected_instruction_version_refs
            or request.knowledge_version_refs
        )
        if not requested:
            return KnowledgeRefs()
        if self._knowledge_provider is None:
            raise HarnessError(
                "Knowledge version refs require the application-owned knowledge store.",
                code="knowledge_store_missing",
                status_code=409,
            )
        return self._knowledge_provider().resolve_refs(
            memory_version_refs=request.memory_version_refs,
            skill_version_refs=request.skill_version_refs,
            protected_instruction_version_refs=request.protected_instruction_version_refs,
            knowledge_version_refs=request.knowledge_version_refs,
            frozen=frozen,
        )

    def _load_knowledge_versions(self, refs: KnowledgeRefs) -> list[KnowledgeVersion]:
        if not refs.all_ids():
            return []
        if self._knowledge_provider is None:
            raise HarnessError(
                "Knowledge version refs require the application-owned knowledge store.",
                code="knowledge_store_missing",
                status_code=409,
            )
        return [self._knowledge_provider().get_version(version_id) for version_id in refs.all_ids()]

    def _knowledge_plan_for_run(self, run: AgentRun) -> KnowledgeMaterializePlan:
        refs = KnowledgeRefs(
            memory_version_refs=run.memory_version_refs,
            skill_version_refs=run.skill_version_refs,
            protected_instruction_version_refs=run.protected_instruction_version_refs,
        )
        versions = self._load_knowledge_versions(refs)
        return plan_knowledge_materialization(
            versions,
            resource_loader=self._knowledge_provider().resource_bytes if self._knowledge_provider else None,
            input_policy=run.input_policy,
        )

    async def _alink_run(self, run: AgentRun, agent: object) -> None:
        """Record checkpoint ids and related files in application records only."""

        await self._alink_new_checkpoints(run, agent)
        try:
            state = await agent.aget_state(_invoke_config(run))
            values = getattr(state, "values", {}) or {}
        except Exception:
            values = {}
        # Preserve each known sibling result even when another tool aborts the
        # native batch. Native PatchToolCallsMiddleware closes only the remaining
        # pairs on the next user turn; neither path invokes an old action.
        reconcile_effects(run)
        messages = list(values.get("messages", []))
        for message in messages:
            if isinstance(message, ToolMessage):
                self._settle_answered_question(run, message)
        answered = {message.tool_call_id for message in messages if isinstance(message, ToolMessage)}
        repaired = []
        restored = []
        for message in messages:
            repaired.append(message)
            for call in getattr(message, "tool_calls", []):
                ident = call.get("id")
                if not ident or ident in answered:
                    continue
                outcome = run.tool_outcomes.get(ident)
                if outcome is None:
                    dispatched = f"{run.id}:{ident}" in run.dispatched_tool_ids
                    run.tool_outcomes[ident] = ToolOutcome(call_id=ident, name=call.get("name") or "unknown",
                        outcome="uncertain" if dispatched else "not_dispatched",
                        recovery_action="inspect_effects" if dispatched else "continue",
                        detail="No durable result was recorded." if dispatched else "This call was not dispatched.", updated_at=utc_now())
                    continue
                if outcome.outcome not in {"succeeded", "failed"}:
                    continue
                content = outcome.result if outcome.result is not None else outcome.detail or "The tool completed."
                repaired.append(ToolMessage(id=f"{ident}:settled", tool_call_id=ident, name=outcome.name,
                    status="success" if outcome.outcome == "succeeded" else "error", content=content,
                    additional_kwargs=outcome.result_metadata))
                restored.append(ident)
        if restored:
            await agent.aupdate_state(_invoke_config(run),
                {"messages": [RemoveMessage(id=REMOVE_ALL_MESSAGES), *repaired]})
            await self._alink_new_checkpoints(run, agent)
            run.events.append(AgentEvent(at=utc_now(), kind="tool_results_reconciled",
                detail={"tool_call_ids": restored, "replayed": False}))
        compaction = values.get(SUMMARIZATION_EVENT_KEY)
        if isinstance(compaction, dict):
            cutoff = compaction.get("cutoff_index")
            if not any(event.kind == "context_compacted" and event.detail.get("cutoff_index") == cutoff for event in run.events):
                run.events.append(AgentEvent(at=utc_now(), kind="context_compacted", detail={
                    "cutoff_index": cutoff, "history_preserved_at": compaction.get("file_path"),
                    "owner": "deepagents-upstream", "internal_summary_is_not_answer": True,
                }))
        if run.structured_output is not None:
            try:
                state = await agent.aget_state(_invoke_config(run))
                values = getattr(state, "values", None)
                run.structured_output = update_structured_result_from_state(
                    run.structured_output,
                    values if isinstance(values, dict) else None,
                )
            except Exception as exc:  # noqa: BLE001 - state loss is diagnostic, not success.
                run.structured_output = mark_structured_failure(run.structured_output, str(exc))
        self._collect_related_files(run)

    async def _alink_new_checkpoints(self, run: AgentRun, agent: object) -> None:
        anchor = run.checkpoint_ids[0] if run.checkpoint_ids else run.pre_run_checkpoint_id
        # Invoke may pin checkpoint_id to the resume row. Linkage reads the
        # thread, and that id is only the exclusive stop.
        linked = {"configurable": {"thread_id": run.thread_id or run.id}}
        try:
            added = await acheckpoint_ids_from_graph(agent, linked, stop_at_id=anchor)
        except ValueError as exc:
            run.events.append(AgentEvent(at=utc_now(), kind="checkpoint_linkage_failed",
                detail={"code": "checkpoint_anchor_missing", "message": str(exc)}))
            raise HarnessError(str(exc), code="checkpoint_linkage_failed", status_code=409) from exc
        run.checkpoint_ids = list(dict.fromkeys([*added, *run.checkpoint_ids]))

    def _collect_related_files(self, run: AgentRun) -> None:
        files = list(_initial_related_files(run.project_path))
        files.extend(_files_from_tool_invocations(run))
        seen: set[tuple[str, str]] = set()
        unique: list[RelatedFile] = []
        for item in files:
            key = (item.path, item.kind)
            if key in seen:
                continue
            seen.add(key)
            unique.append(item)
        run.related_files = unique

    def wait_after(
        self,
        run_id: str,
        after_seq: int,
        *,
        timeout: float,
    ) -> tuple[AgentRun, list[AgentEvent]]:
        """Block until events after ``after_seq`` exist or the run is terminal.

        ``after_seq`` is the count of events already sent (same as last SSE id).
        """

        deadline = time.monotonic() + timeout
        with self._updates:
            while True:
                run = self._require_run(run_id)
                extra = list(run.events[after_seq:])
                if extra or not is_run_lifecycle_live(run.status):
                    return self._expose_run(run), extra
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return self._expose_run(run), []
                self._updates.wait(timeout=remaining)

    def _require_run(self, run_id: str) -> AgentRun:
        run = self._runs.get(run_id)
        if run is not None:
            return run
        stored = self.store.get_execution_run(run_id)
        if stored is None:
            raise HarnessError("Unknown agent run", code="run_missing", status_code=404)
        return self._runs.setdefault(run_id, stored)

    def _reconcile_startup_once(self) -> None:
        settled: list[AgentRun] = []
        retries: list[tuple[AgentRun, AgentRunStatus, str]] = []
        with self._lock:
            if self._startup_reconciled:
                return
            for lifecycle in self.store.list_run_lifecycle():
                if not is_run_lifecycle_live(lifecycle.status) and lifecycle.id not in self._terminal_retries:
                    continue
                run = self.store.get_execution_run(lifecycle.id)
                if run is None:
                    continue
                if not is_run_lifecycle_live(run.status):
                    if run.id in self._terminal_retries:
                        # A failed follow-up read may have hidden a successful
                        # terminal write. The durable record wins on retry.
                        self._runs[run.id] = run
                        self._terminal_retries.pop(run.id, None)
                        self._interaction_failure_runs.discard(run.id)
                    continue
                retry = self._terminal_retries.get(run.id)
                if retry is not None:
                    retries.append((self._runs[run.id], *retry))
                    continue
                worker = self._threads.get(run.id)
                if worker is not None and (worker.ident is None or worker.is_alive()):
                    # This service still owns the graph. Reconciliation can be
                    # retried after another run's failed terminal write.
                    continue
                if run.finalization_phase == "saving_changes" and run.settled_status is not None:
                    settled.append(self._runs.setdefault(run.id, run))
                    continue
                if (
                    run.status is not AgentRunStatus.cancel_requested
                    and run.pending_interrupt is not None
                    and self._has_resume_checkpoint(run)
                ):
                    live = self._runs.setdefault(run.id, run)
                    self._cancels.setdefault(run.id, threading.Event())
                    self._decision_ready.setdefault(run.id, threading.Event())
                    self._pending_decisions.setdefault(run.id, None)
                    self._persist_and_notify(live)
                    continue
                self._mark_orphaned_run(run)
            self._startup_reconciled = True
        for run, status, reason in retries:
            try:
                self._finish(run, status, reason)
            except Exception:
                with self._lock:
                    self._startup_reconciled = False
                raise
        for run in settled:
            try:
                self._finish(run, AgentRunStatus(run.settled_status), run.settled_stop_reason or run.settled_status)
            except Exception:
                with self._lock:
                    self._startup_reconciled = False
                raise

    def _mark_orphaned_run(self, run: AgentRun) -> None:
        with self._lock:
            live = self._runs.setdefault(run.id, run)
            if not is_run_lifecycle_live(live.status):
                return
            missing_checkpoint = live.pending_interrupt is not None
            cancelling = live.status is AgentRunStatus.cancel_requested
            live.finalization_phase = None
            live.activity_phase = None
            live.settled_status = None
            live.settled_stop_reason = None
            live.status = AgentRunStatus.failed
            live.stop_reason = "orphaned"
            live.error = _orphan_error(
                missing_checkpoint=missing_checkpoint,
                cancelling=cancelling,
            )
            detail_code = _orphan_code(
                missing_checkpoint=missing_checkpoint,
                cancelling=cancelling,
            )
            live.finished_at = utc_now()
            live.updated_at = live.finished_at
            reconcile_effects(live)
            live.failure = failure_for_run(live, code="orphaned")
            if live.generation_observation is not None and live.generation_observation.phase in {"prompt_processing", "generating"}:
                live.generation_observation = live.generation_observation.model_copy(update={
                    "phase": "interrupted", "interval": "last_model_call_generation", "measured_at": live.finished_at,
                })
            for purpose, observed in list(live.housekeeping_generation.items()):
                if observed.phase in {"prompt_processing", "generating"}:
                    live.housekeeping_generation[purpose] = observed.model_copy(update={
                        "phase": "interrupted", "interval": "last_model_call_generation", "measured_at": live.finished_at,
                    })
            live.events.append(
                AgentEvent(
                    at=live.updated_at,
                    kind="failed",
                    detail={
                        "stop_reason": "orphaned",
                        "error": live.error,
                        "confirmed": True,
                        "code": detail_code,
                    },
                )
            )
            self._persist_and_notify(live)

    def _has_resume_checkpoint(self, run: AgentRun) -> bool:
        thread_id = (run.thread_id or "").strip()
        if not thread_id or not run.checkpoint_ids:
            return False
        try:
            latest = next(iter(
                checkpoint_history(self.manager.paths.checkpoints_db,
                    {"configurable": {"thread_id": thread_id, "checkpoint_ns": ""}},
                    limit=1,
                )),
                None,
            )
        except Exception:  # noqa: BLE001 - missing/unreadable checkpoint is not resumable
            return False
        if latest is None:
            return False
        configurable = latest.config.get("configurable") if isinstance(latest.config, dict) else None
        checkpoint_id = configurable.get("checkpoint_id") if isinstance(configurable, dict) else None
        if not checkpoint_id or checkpoint_id not in run.checkpoint_ids:
            return False
        return any(channel == "__interrupt__" for _task, channel, _value in latest.pending_writes or [])

    def _persist(self, run: AgentRun) -> None:
        self.store.put_execution_run(run)

    def _persist_and_notify(self, run: AgentRun, *, telemetry: bool = False) -> None:
        if not telemetry:
            self._persist(run)
        if run.parent_run_id:
            # Inline children share the parent's graph thread. Their audit is
            # durable in the child run, while scoped native events belong in
            # the parent interaction; a child run must never replace root UI.
            self._updates.notify_all()
            return
        if run.id not in self._interaction_failure_runs or not is_run_lifecycle_live(run.status):
            self._observe_interaction(run, None, telemetry=telemetry)
        self._updates.notify_all()

    def _capture_settings(self) -> ContextCaptureSettings:
        if self._knowledge_provider is not None:
            return self._knowledge_provider().get_config().context_captures
        return capture_settings_for_paths(self.manager.paths)

    def _expose_run(self, run: AgentRun) -> AgentRunOperational:
        return AgentRunOperational.model_validate(
            run.model_dump(mode="python", exclude={"model_requests"}))


def _resolved_project_path(project_path: str | None) -> str | None:
    if not project_path:
        return None
    path = Path(project_path).expanduser().resolve()
    if not path.is_dir():
        raise HarnessError(
            "project_path is not a directory. Filesystem tools target project storage.",
            code="project_missing",
            status_code=400,
        )
    return str(path)


def _copy_execution_run(run: AgentRun | AgentRunOperational) -> AgentRun:
    """Copy mutable operational state without recopying immutable capture bodies."""
    copied = AgentRun.model_validate(run.model_dump(exclude={"model_requests"}))
    copied.model_requests = list(getattr(run, "model_requests", ()))
    return copied


def _lifecycle_projection(run: AgentRun, *, details: bool) -> RunLifecycleProjection:
    fields = set(RunLifecycleProjection.model_fields) if details else {
        "id", "status", "thread_id", "workspace_id", "project_path",
        "parent_run_id", "source_surface", "created_at", "updated_at",
    }
    return RunLifecycleProjection.model_validate(run.model_dump(include=fields))


def _pending_from_chunk(chunk: Any) -> Any:
    """Normalize a LangGraph ``stream_mode='updates'`` interrupt chunk."""

    if not isinstance(chunk, dict):
        return None
    raw = chunk.get("__interrupt__")
    if raw is None:
        return None
    return pending_interrupt_from_raw(raw)


def _pending_from_native_event(event: Any) -> Any:
    """Normalize a public v3 ``stream_events`` interrupt event."""

    if not isinstance(event, dict):
        return None
    params = event.get("params")
    if not isinstance(params, dict):
        return None
    raw = params.get("interrupts")
    if raw is None:
        data = params.get("data")
        raw = data.get("__interrupt__") if isinstance(data, dict) else None
    pending = pending_interrupt_from_raw(raw)
    if pending is None:
        return None
    namespace = params.get("namespace")
    return _pending_with_identity(pending, raw, namespace if isinstance(namespace, list) else [])


def _native_message_identity(message: Any) -> tuple[str, str] | None:
    tool_call_id = getattr(message, "tool_call_id", None)
    if tool_call_id:
        return ("tool", str(tool_call_id))
    ident = getattr(message, "id", None)
    if ident:
        return ("message", str(ident))
    if isinstance(message, AIMessage) and message.tool_calls:
        return ("tool_calls", repr(message.tool_calls))
    content = getattr(message, "content", None)
    if content:
        return ("content", repr(content))
    return None


def _assistant_event_detail(message: AIMessage, node: str | None) -> dict[str, Any]:
    content = message.content
    blocks = message.content_blocks
    readable = _readable_assistant_content(content)
    detail: dict[str, Any] = {"content": readable if readable else (blocks or content)}
    if node:
        detail["node"] = node
    if getattr(message, "id", None):
        detail["message_id"] = message.id
    if blocks:
        detail["content_blocks"] = blocks
    elif isinstance(content, list):
        detail["content_blocks"] = content
    elif content:
        detail["content_blocks"] = [{"type": "text", "text": str(content)}]
    return detail


def _safe_tool_event_content(message: ToolMessage) -> Any:
    """Retain useful tool text without streaming or storing inline media."""

    content = message.content
    if isinstance(content, str):
        return "[inline media omitted]" if content.startswith("data:") else content
    if not isinstance(content, list):
        return content
    safe: list[Any] = []
    for block in content:
        if isinstance(block, dict) and (block.get("type") in {"image", "image_url", "audio", "input_audio", "video"}
            or any(key in block for key in ("base64", "image_url", "data"))):
            safe.append({"type": "text", "text": "[inline media omitted; use its retained path to inspect again]"})
        else:
            safe.append(block)
    return safe


def _tool_media_reference(message: ToolMessage) -> dict[str, str]:
    if message.name != "read_file":
        return {}
    path = message.additional_kwargs.get("read_file_path")
    media_type = message.additional_kwargs.get("read_file_media_type")
    return {
        **({"media_path": path} if isinstance(path, str) else {}),
        **({"media_type": media_type} if isinstance(media_type, str) else {}),
    }


def _readable_assistant_content(content: Any) -> Any:
    if not isinstance(content, list):
        return content
    text_parts: list[str] = []
    for item in content:
        if isinstance(item, dict) and item.get("type") == "text" and isinstance(item.get("text"), str):
            text_parts.append(item["text"])
    return "".join(text_parts) if text_parts else content


def _pending_with_identity(pending: PendingInterrupt, raw: Any, namespace: list[Any]) -> PendingInterrupt:
    ident = _interrupt_id_from_raw(raw)
    clean_namespace = [item for item in namespace if isinstance(item, str)]
    if ident or clean_namespace:
        return pending.model_copy(update={"interrupt_id": ident or pending.interrupt_id, "namespace": clean_namespace})
    return pending


def _interrupt_id_from_raw(raw: Any) -> str | None:
    if raw is None:
        return None
    if isinstance(raw, (list, tuple)):
        for item in raw:
            found = _interrupt_id_from_raw(item)
            if found:
                return found
        return None
    ident = raw.get("id") if isinstance(raw, dict) else getattr(raw, "id", None)
    if ident is None:
        return None
    text = str(ident).strip()
    return text or None


def _fallback_interrupt_id(run: AgentRun) -> str:
    count = sum(1 for event in run.events if event.kind == "interrupt") + 1
    return f"{run.id}:interrupt:{count}"


def _resume_value(decisions: list[dict[str, str]]) -> dict[str, Any]:
    return {"decisions": decisions}


def _failure_code(run: AgentRun, error: Exception) -> str | None:
    code = getattr(error, "code", None)
    if isinstance(error, ContextOverflowError) or code in {"context_length_exceeded", "context_window_exceeded"}:
        if run.context_observation is not None:
            failed = run.context_observation.model_copy(deep=True)
            failed.fits = False
            failed.notes.append("Deep Agents exhausted native context reduction or overflow recovery.")
            run.context_observation = failed
        return "context_capacity_exceeded"
    return code


def _invoke_config(run: AgentRun) -> dict[str, Any]:
    """Thread id is required so LangGraph can write checkpoints.sqlite."""

    config: dict[str, Any] = {"configurable": {"thread_id": run.thread_id or run.id}}
    if run.resume_checkpoint_id:
        config["configurable"]["checkpoint_id"] = run.resume_checkpoint_id
    if run.budgets is not None and run.budgets.max_steps is not None:
        config["recursion_limit"] = run.budgets.max_steps
    return config


def _orphan_error(*, missing_checkpoint: bool, cancelling: bool) -> str:
    if cancelling:
        return (
            "The application restarted while this run was cancelling. The worker "
            "that could confirm the stop is gone, so the run is failed as orphaned "
            "with unknown external effects. No pending host-shell command was "
            "approved or replayed."
        )
    if missing_checkpoint:
        return (
            "The application restarted while this run was waiting for approval, "
            "but no recorded checkpoint linkage was available to resume. Start a "
            "new run; the host-shell command was not approved or replayed."
        )
    return (
        "The application restarted while this run was live and no pending approval "
        "checkpoint was available to resume. The worker is no longer owned; any "
        "external effect has an unknown outcome and has not been replayed."
    )


def _orphan_code(*, missing_checkpoint: bool, cancelling: bool) -> str:
    if cancelling:
        return "cancel_requested_orphaned_after_restart"
    if missing_checkpoint:
        return "pending_interrupt_checkpoint_missing"
    return "run_orphaned_after_restart"


def _initial_related_files(project_path: str | None) -> list[RelatedFile]:
    if not project_path:
        return []
    return [RelatedFile(path=project_path, kind="project_root")]


def _files_from_tool_invocations(run: AgentRun) -> list[RelatedFile]:
    if not run.project_path:
        return []
    root = Path(run.project_path)
    files: list[RelatedFile] = []
    for invocation in run.tool_invocations:
        name = invocation.get("name")
        if name not in {"write_file", "edit_file"}:
            continue
        args = invocation.get("args") if isinstance(invocation.get("args"), dict) else {}
        relative = args.get("file_path") or args.get("path")
        if not isinstance(relative, str) or not relative.strip():
            continue
        if is_reserved_framework_path(relative):
            continue
        resolved = (root / relative.lstrip("/")).resolve()
        files.append(RelatedFile(path=str(resolved), kind="written_file"))
    return files
