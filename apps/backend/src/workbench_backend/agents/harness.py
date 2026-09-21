"""AGT-001: embedded Deep Agents harness — start / observe / cancel.

Deep Agents owns the model/tool loop. LangGraph is only the compiled graph
returned by create_deep_agent — not a second Builder workflow editor.
"""

from __future__ import annotations

import sys
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
from deepagents import create_deep_agent
from deepagents.backends import StateBackend
from deepagents.middleware.summarization import SummarizationMiddleware, SUMMARIZATION_EVENT_KEY
from langchain.agents.middleware import TodoListMiddleware
from langchain_core.embeddings import Embeddings
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.types import Command

from workbench_backend.agents.effective_setup import resolve_effective_setup
from workbench_backend.agents.evidence import build_completion
from workbench_backend.agents.context import BudgetedSummarizationMiddleware, observe_context, require_context_fit, observe_payload, count_context_tokens, validate_retained_messages
from workbench_backend.agents.harness_backend import build_run_backend, is_reserved_framework_path
from workbench_backend.agents.memory_skills import (
    KnowledgeMaterializePlan,
    official_agent_kwargs,
    materialize_onto_backend,
    plan_knowledge_materialization,
)
from workbench_backend.agents.retrieval import (
    RETRIEVAL_INSTRUCTIONS,
    SEARCH_KNOWLEDGE_TOOL_NAME,
    build_vector_store,
    load_retrieval_documents,
    make_search_knowledge_tool,
    openai_embeddings_for_deployment,
    record_retrieved_sources,
    resolve_embedding_deployment,
)
from workbench_backend.agents.host_shell import (
    filesystem_permissions_for_run,
    interrupt_on_for_run,
    pending_interrupt_from_raw,
    reject_decisions_for,
    validated_decision_payloads,
)
from workbench_backend.agents.middleware import WorkbenchHarnessMiddleware
from workbench_backend.agents.replay import FixtureBank
from workbench_backend.agents.schemas import (
    AgentEvent,
    AgentRun,
    AgentRunStatus,
    AgentStartRequest,
    HostShellFacts,
    InterruptDecisionRequest,
    PendingInterrupt,
    TaskCriteria,
    ToolMode,
    label_for_tool_mode,
)
from workbench_backend.contracts.lifecycle import (
    TERMINAL_RUN_LIFECYCLE_STATUSES,
    is_run_lifecycle_live,
)
from workbench_backend.state.checkpointer import (
    conversation_state,
    checkpoint_ids_from_graph,
    open_sqlite_checkpointer,
)
from workbench_backend.state.schemas import RelatedFile
from workbench_backend.state.store import ApplicationStore
from workbench_backend.agents.tools import (
    KNOWLEDGE_ROUTE_READ_TOOLS,
    enabled_for_project,
    resolve_presented_tools,
    tools_for_names,
)
from workbench_backend.errors import HarnessError, KnowledgeError, ReplayError
from workbench_backend.agents.structured import (
    StructuredOutputRepairMiddleware,
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
from workbench_backend.knowledge.diagnostics import (
    apply_run_diagnostic_policy,
    capture_settings_for_paths,
)
from workbench_backend.knowledge.schemas import (
    ContextCaptureSettings,
    KnowledgeRefs,
    KnowledgeVersion,
)
from workbench_backend.knowledge.service import KnowledgeService
from workbench_backend.lab.snapshot import capture_project_snapshot
from workbench_backend.lab.store import LabStore

DEFAULT_SYSTEM_PROMPT = (
    "You are the Local AI Workbench embedded harness. Use enabled tools when "
    "they help answer the task. Do not invent durable knowledge or retrieval. "
    "This is not Chat or Builder."
)

ModelFactory = Callable[[AgentRun, list[dict[str, Any]]], BaseChatModel]
EmbeddingsFactory = Callable[[Deployment], Embeddings]


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
    ) -> None:
        self._manager_provider = manager_provider
        self._model_factory = model_factory or self._deployment_model
        self._knowledge_provider = knowledge_provider
        self._app_store = app_store
        self._embeddings_factory = embeddings_factory or openai_embeddings_for_deployment
        self._runs: dict[str, AgentRun] = {}
        self._cancels: dict[str, threading.Event] = {}
        self._threads: dict[str, threading.Thread] = {}
        self._decision_ready: dict[str, threading.Event] = {}
        self._pending_decisions: dict[str, list[dict[str, str]] | None] = {}
        self._model_clients: dict[str, httpx.Client] = {}
        self._adapter_models: dict[str, Any] = {}
        self._lock = threading.RLock()
        self._updates = threading.Condition(self._lock)
        self._startup_reconciled = False

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
        stored = {item.id: item for item in self.store.list_runs()}
        with self._lock:
            for run in self._runs.values():
                stored[run.id] = run.model_copy(deep=True)
        return [self._expose_run(item) for item in stored.values()]

    def get_run(self, run_id: str) -> AgentRun:
        self._reconcile_startup_once()
        with self._lock:
            run = self._runs.get(run_id)
            if run is not None:
                return self._expose_run(run)
        stored = self.store.get_run(run_id)
        if stored is None:
            raise HarnessError("Unknown agent run", code="run_missing", status_code=404)
        with self._lock:
            self._runs.setdefault(run_id, stored)
        return self._expose_run(stored)

    def active_workspace_run_ids(self, workspace_id: str) -> list[str]:
        """Runs still writing or executing against a workspace (quiescent check).

        `cancel_requested` is still live. Confirmed `cancelled` is not.
        """

        self._reconcile_startup_once()
        with self._lock:
            memory = {run.id: run for run in self._runs.values()}
        stored = {item.id: item for item in self.store.list_runs()}
        for run_id, run in memory.items():
            stored_run = stored.get(run_id)
            if stored_run is not None and not is_run_lifecycle_live(stored_run.status):
                continue
            stored[run_id] = run
        return [
            run.id
            for run in stored.values()
            if run.workspace_id == workspace_id and is_run_lifecycle_live(run.status)
        ]

    def start(self, request: AgentStartRequest) -> AgentRun:
        self._reconcile_startup_once()
        admission = self.manager.reserve_deployment(
            request.deployment_id,
            profile_id=request.profile_id,
        )
        admission.__enter__()
        try:
            deployment = self.manager.ensure_deployment_ready(request.deployment_id)
            if not deployment.endpoint:
                raise HarnessError(
                    "Deployment has no endpoint. The manager could not load inference.",
                    code="no_endpoint",
                    status_code=409,
                )
            if request.tool_mode is ToolMode.recorded_tool and not request.recorded_fixtures:
                raise HarnessError(
                    "recorded-tool mode requires fixtures; it is not a live integration.",
                    code="recorded_fixtures_required",
                    status_code=400,
                )
            refs = self._resolve_knowledge_refs(request)
            versions = self._load_knowledge_versions(refs)
            knowledge_plan = plan_knowledge_materialization(
                versions,
                self._knowledge_display_names(versions),
            )
            profile = self.manager.get_profile(request.profile_id) if request.profile_id else None
            project_path = _resolved_project_path(request.project_path)
            if project_path is None and request.workspace_id:
                stored = LabStore(self.manager.paths).get_workspace(request.workspace_id)
                if stored is not None:
                    project_path = _resolved_project_path(stored.path)
            presented, denied, filesystem_blocked, shell_blocked = resolve_presented_tools(
                request.presented_tools,
                project_bound=project_path is not None,
                knowledge_routes=knowledge_plan.has_knowledge_routes,
            )
            retrieval_requested = bool((request.embedding_deployment_id or "").strip())
            recorded = request.tool_mode is ToolMode.recorded_tool
            if retrieval_requested and SEARCH_KNOWLEDGE_TOOL_NAME in denied:
                denied = [name for name in denied if name != SEARCH_KNOWLEDGE_TOOL_NAME]
            embedding_deployment = None
            retrieval_documents = []
            if retrieval_requested and not recorded:
                embedding_deployment = resolve_embedding_deployment(
                    self.manager,
                    request.embedding_deployment_id or "",
                )
                retrieval_documents = load_retrieval_documents(
                    versions,
                    list(request.retrieval_project_paths),
                    project_path,
                )
                if not retrieval_documents:
                    raise HarnessError(
                        "Retrieval was requested but the derived corpus is empty. "
                        "Select knowledge versions or allowlisted project text files. "
                        "No hits were invented.",
                        code="retrieval_corpus_empty",
                        status_code=409,
                    )
            retrieval_presented = bool(
                retrieval_requested and not recorded and embedding_deployment is not None
            )
            if denied:
                raise HarnessError(
                    f"Tools are not in the enabled catalogue: {', '.join(denied)}",
                    code="tool_denied",
                    status_code=400,
                )
            if filesystem_blocked:
                raise HarnessError(
                    "Filesystem tools require a bound project folder.",
                    code="filesystem_requires_project",
                    status_code=400,
                    details={"tools": filesystem_blocked},
                )
            if shell_blocked:
                raise HarnessError(
                    "The host shell requires a bound project folder as cwd. "
                    "A home-directory default is not invented.",
                    code="shell_requires_project",
                    status_code=400,
                    details={"tools": shell_blocked},
                )
            if retrieval_presented and SEARCH_KNOWLEDGE_TOOL_NAME not in presented:
                presented = [*presented, SEARCH_KNOWLEDGE_TOOL_NAME]
            if knowledge_plan.has_knowledge_routes and request.presented_tools != []:
                for name in KNOWLEDGE_ROUTE_READ_TOOLS:
                    if name not in presented:
                        presented = [*presented, name]
            if retrieval_presented and request.presented_tools == []:
                raise HarnessError(
                    "Retrieval requires its search tool. Enable tools or remove the retrieval selection.",
                    code="retrieval_tools_off",
                    status_code=400,
                )
            if request.content_blocks:
                self._validate_content_capabilities(deployment, request)
            if presented and deployment.server_props and (
                deployment.server_props.chat_template_caps.get("supports_tools") is False
                or deployment.server_props.chat_template_caps.get("supports_tool_calls") is False
            ):
                raise HarnessError("This setup reports that task tools are unsupported. Turn tools off or select a compatible setup.", code="tools_unsupported", status_code=409)
            enabled = enabled_for_project(
                project_path is not None,
                knowledge_routes=knowledge_plan.has_knowledge_routes,
            )
            if retrieval_presented and SEARCH_KNOWLEDGE_TOOL_NAME not in enabled:
                enabled = [*enabled, SEARCH_KNOWLEDGE_TOOL_NAME]
            setup = resolve_effective_setup(
                deployment=deployment,
                profile=profile,
                knowledge_refs=refs,
                knowledge_versions=versions,
                surface_system_prompt=request.system_prompt,
                default_system_prompt=DEFAULT_SYSTEM_PROMPT,
                embedding_deployment=embedding_deployment,
                selected_embedding_deployment_id=request.embedding_deployment_id,
                retrieval_requested=retrieval_requested,
                retrieval_presented=retrieval_presented,
                retrieval_corpus_documents=len(retrieval_documents),
                retrieval_instructions=RETRIEVAL_INSTRUCTIONS if retrieval_presented else None,
                materialized_knowledge=knowledge_plan.facts,
                inherit_deployment_settings=request.inherit_deployment_settings,
            )
            saved_state = conversation_state(self.manager.paths.checkpoints_db, request.thread_id) if request.thread_id else {}
            retained = list(saved_state.get("messages", []))
            # Use the installed upstream reconstruction, not a second history reducer.
            retained = SummarizationMiddleware._apply_event_to_messages(retained, saved_state.get(SUMMARIZATION_EVENT_KEY))
            validate_retained_messages(deployment, [SystemMessage(content=setup.system_prompt), *retained,
                HumanMessage(content=user_message_content(request.task, request.content_blocks))])
            context_observation = observe_context(
                deployment=deployment,
                per_request=setup.bags.per_request,
                system_prompt=setup.system_prompt,
                task=request.task,
                content_blocks=request.content_blocks,
                tool_count=len(presented),
                output_schema=(
                    request.output_schema.json_schema
                    if request.output_schema is not None
                    else None
                ),
                continuing_thread=bool(request.thread_id),
                history=retained,
                tools=tools_for_names(presented),
            )
            require_context_fit(context_observation)
            _, structured_output = response_format_for_run(
                output_schema=request.output_schema,
                deployment=deployment,
                per_request=setup.bags.per_request,
                tools_presented=bool(presented),
                tools_off=request.presented_tools == [],
            )
            if request.workspace_id:
                others = self.active_workspace_run_ids(request.workspace_id)
                if others:
                    raise HarnessError(
                        "Starting snapshot requires a quiescent workspace; live runs still writing: "
                        f"{', '.join(others)}",
                        code="not_quiescent",
                        status_code=409,
                    )
            starting_snapshot_id = self._capture_starting_snapshot(request, project_path)
            now = utc_now()
            run = AgentRun(
                id=new_id("agent"),
                status=AgentRunStatus.queued,
                deployment_id=deployment.id,
                task=request.task,
                content_blocks=request.content_blocks,
                enabled_tools=enabled,
                presented_tools=presented,
                denied_tools=[],
                system_prompt=setup.system_prompt,
                criteria=request.criteria or TaskCriteria(),
                budgets=request.budgets,
                created_at=now,
                updated_at=now,
                workspace_id=request.workspace_id,
                project_path=project_path,
                profile_id=setup.selected_profile_id,
                parent_run_id=request.parent_run_id,
                source_surface=request.source_surface,
                tool_mode=request.tool_mode,
                tool_mode_label=label_for_tool_mode(request.tool_mode),
                recorded_is_not_live_proof=request.tool_mode is ToolMode.recorded_tool,
                recorded_fixtures=list(request.recorded_fixtures or []),
                knowledge=refs.binding(),
                memory_version_refs=refs.memory_version_refs,
                skill_version_refs=refs.skill_version_refs,
                protected_instruction_version_refs=refs.protected_instruction_version_refs,
                embedding_deployment_id=request.embedding_deployment_id,
                retrieval_project_paths=list(request.retrieval_project_paths),
                thread_id=request.thread_id or None,
                related_files=_initial_related_files(project_path),
                effective_setup=setup,
                starting_snapshot_id=starting_snapshot_id,
                host_shell=HostShellFacts(
                    available=project_path is not None
                    and "execute" in presented
                    and request.tool_mode is not ToolMode.recorded_tool,
                    cwd=project_path,
                    inherit_env=True,
                ),
                output_schema=request.output_schema,
                structured_output=structured_output,
                context_observation=context_observation,
            )
            # Agent-run / Lab own one thread per run. Chat follow-ups pass the
            # conversation thread so LangGraph resumes the same checkpointer state.
            run.thread_id = request.thread_id or run.id
            cancel = threading.Event()
            with self._lock:
                self._runs[run.id] = run
                self._cancels[run.id] = cancel
                self._decision_ready[run.id] = threading.Event()
                self._pending_decisions[run.id] = None
                self._persist_and_notify(run)
        except BaseException:
            admission.__exit__(*sys.exc_info())
            raise
        admission.__exit__(None, None, None)
        thread = threading.Thread(target=self._execute, args=(run.id,), daemon=True)
        with self._lock:
            self._threads[run.id] = thread
        thread.start()
        return run.model_copy(deep=True)

    def close(self, *, timeout: float = 15.0) -> None:
        """Join worker threads so SQLite files can be closed on Windows."""
        with self._lock:
            for cancel in self._cancels.values():
                cancel.set()
            for ready in self._decision_ready.values():
                ready.set()
            clients = list(self._model_clients.values())
            threads = list(self._threads.values())
        for client in clients:
            client.close()
        for thread in threads:
            thread.join(timeout=timeout)
        with self._lock:
            self._threads.clear()

    def cancel(self, run_id: str) -> AgentRun:
        """Accept a cancel request. Do not claim cancelled until the worker stops."""

        self._reconcile_startup_once()
        reject_after_restart: tuple[PendingInterrupt, threading.Event] | None = None
        with self._lock:
            run = self._require_run(run_id)
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
        if client is not None:
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
            return run.model_copy(deep=True)

    def resume_interrupt(self, run_id: str, request: InterruptDecisionRequest) -> AgentRun:
        """Apply Deep Agents HITL decisions. Does not invent a durable inbox."""

        self._reconcile_startup_once()
        with self._lock:
            run = self._require_run(run_id)
            pending = run.pending_interrupt
            if pending is None:
                raise HarnessError(
                    "This run has no pending host-shell interrupt.",
                    code="interrupt_missing",
                    status_code=409,
                )
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
        return self.get_run(run_id)

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
        agent = None
        try:
            fixture_bank = (
                FixtureBank(run.recorded_fixtures)
                if run.tool_mode is ToolMode.recorded_tool
                else None
            )
            agent = self._create_compiled_agent(run, http_sink, fixture_bank)
            self._drive_until_terminal(
                run,
                agent,
                cancel,
                {"messages": [{"role": "user", "content": user_message_content(run.task, run.content_blocks)}],
                 **({"structured_response": None} if run.output_schema is not None else {})},
            )
        except ReplayError as exc:
            if agent is not None:
                self._link_run(run, agent)
            else:
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
            if agent is not None:
                self._link_run(run, agent)
            else:
                self._collect_related_files(run)
            if cancel.is_set():
                self._finish(run, AgentRunStatus.cancelled, "cancelled")
                return
            run.error = clarify_connection_error(exc)
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
        agent = None
        try:
            fixture_bank = (
                FixtureBank(run.recorded_fixtures)
                if run.tool_mode is ToolMode.recorded_tool
                else None
            )
            agent = self._create_compiled_agent(run, http_sink, fixture_bank)
            self._clear_pending_interrupt(run, decisions)
            self._drive_until_terminal(
                run,
                agent,
                cancel,
                Command(resume={"decisions": decisions}),
            )
        except ReplayError as exc:
            if agent is not None:
                self._link_run(run, agent)
            else:
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
            if agent is not None:
                self._link_run(run, agent)
            else:
                self._collect_related_files(run)
            if cancel.is_set():
                self._finish(run, AgentRunStatus.cancelled, "cancelled")
                return
            run.error = clarify_connection_error(exc)
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
        agent = None
        try:
            fixture_bank = (
                FixtureBank(run.recorded_fixtures)
                if run.tool_mode is ToolMode.recorded_tool
                else None
            )
            agent = self._create_compiled_agent(run, http_sink, fixture_bank)
            self._resume_reject_then_stop(agent, run, pending, _invoke_config(run))
        except Exception as exc:  # noqa: BLE001 - surface failure without replaying approval
            if agent is not None:
                self._link_run(run, agent)
            else:
                self._collect_related_files(run)
            run.error = clarify_connection_error(exc)
            self._finish(run, AgentRunStatus.failed, "failed")
        finally:
            cancel.set()
            with self._lock:
                self._pending_decisions[run_id] = None
            self._close_model_client(run_id)

    def _create_compiled_agent(
        self,
        run: AgentRun,
        http_sink: list[dict[str, Any]],
        fixture_bank: FixtureBank | None,
    ) -> Any:
        model = self._model_factory(run, http_sink)
        agent_kwargs: dict[str, Any] = {}
        backend = build_run_backend(run, self.manager.paths)
        knowledge_plan = self._knowledge_plan_for_run(run)
        if backend is not None:
            agent_kwargs["backend"] = backend
            materialize_onto_backend(backend, knowledge_plan)
        observation = run.context_observation
        usable = observation.usable_input_tokens if observation is not None else None
        # Override provider-name defaults; only observed runtime capacity is a fact.
        model.profile = {"max_input_tokens": usable} if usable else {}
        if observation is not None and callable(getattr(model, "set_context_guard", None)):
            def guard(payload: dict[str, Any]) -> None:
                observed = observe_payload(observation, payload)
                run.context_observation = observed
                require_context_fit(observed)
            model.set_context_guard(guard)
        summarization = BudgetedSummarizationMiddleware(
            model=model, backend=backend or (lambda runtime: StateBackend(runtime)),
            allowed_tools=set(run.presented_tools),
            trigger=("tokens", max(1, int(usable * 0.75))) if usable else None,
            keep=("tokens", max(1, int(usable * 0.15))) if usable else ("messages", 6),
            token_counter=count_context_tokens,
            trim_tokens_to_summarize=None,
            truncate_args_settings=None,
        )
        agent_kwargs.update(official_agent_kwargs(knowledge_plan))
        permissions = filesystem_permissions_for_run(run)
        if permissions:
            agent_kwargs["permissions"] = permissions
        interrupt_on = interrupt_on_for_run(run)
        if interrupt_on:
            agent_kwargs["interrupt_on"] = interrupt_on
        tools = tools_for_names(run.presented_tools)
        retrieval_tool = self._live_search_knowledge_tool(run, backend)
        if retrieval_tool is not None:
            tools = [*tools, retrieval_tool]
        deployment = self.manager.ensure_deployment_ready(run.deployment_id)
        per_request = run.effective_setup.bags.per_request if run.effective_setup is not None else None
        response_format, structured_output = response_format_for_run(
            output_schema=run.output_schema,
            deployment=deployment,
            per_request=per_request,
            tools_presented=bool(run.presented_tools),
            tools_off=not run.presented_tools,
        )
        if structured_output is not None and run.structured_output is None:
            run.structured_output = structured_output
            run.events.append(
                AgentEvent(
                    at=utc_now(),
                    kind="structured_output_requested",
                    detail=structured_output.model_dump(mode="json"),
                )
            )
        return create_deep_agent(
            model=model,
            tools=tools,
            system_prompt=run.system_prompt,
            middleware=[
                summarization,
                *([StructuredOutputRepairMiddleware(run.structured_output, on_event=lambda kind, detail: run.events.append(
                    AgentEvent(at=utc_now(), kind=kind, detail=detail)
                ))] if run.structured_output is not None else []),
                *([TodoListMiddleware()] if "write_todos" in run.presented_tools else []),
                WorkbenchHarnessMiddleware(
                    run,
                    http_sink,
                    settings_provider=self._capture_settings,
                    fixture_bank=fixture_bank,
                )
            ],
            name="workbench-embedded-harness",
            response_format=response_format,
            checkpointer=open_sqlite_checkpointer(self.manager.paths.checkpoints_db),
            **agent_kwargs,
        )

    def _drive_until_terminal(
        self,
        run: AgentRun,
        agent: Any,
        cancel: threading.Event,
        payload: Any,
    ) -> None:
        config = _invoke_config(run)
        current = payload
        while True:
            if cancel.is_set():
                self._link_run(run, agent)
                self._finish(run, AgentRunStatus.cancelled, "cancelled")
                return
            pending = self._stream_until_pause(agent, run, current, cancel, config)
            if cancel.is_set():
                if pending is not None:
                    self._resume_reject_then_stop(agent, run, pending, config)
                else:
                    self._link_run(run, agent)
                    self._finish(run, AgentRunStatus.cancelled, "cancelled")
                return
            if pending is None:
                self._link_run(run, agent)
                if run.structured_output is not None and run.structured_output.validation_status != "valid":
                    run.error = run.structured_output.error or "The model did not produce a valid structured result."
                    self._finish(run, AgentRunStatus.failed, "structured_output_invalid")
                    return
                run.completion = build_completion(run)
                self._finish(run, AgentRunStatus.completed, "completed")
                return
            self._link_run(run, agent)
            self._publish_interrupt(run, pending)
            decisions = self._wait_for_interrupt_decisions(run.id, cancel)
            if decisions is None:
                self._resume_reject_then_stop(agent, run, pending, config)
                return
            self._clear_pending_interrupt(run, decisions)
            current = Command(resume={"decisions": decisions})

    def _stream_until_pause(
        self,
        agent: Any,
        run: AgentRun,
        payload: Any,
        cancel: threading.Event,
        config: dict[str, Any],
    ) -> Any:
        try:
            for chunk in agent.stream(payload, config=config, stream_mode="updates"):
                found = _pending_from_chunk(chunk)
                if found is not None:
                    return found
                if cancel.is_set():
                    return None
                self._ingest_stream(run, chunk)
        except Exception as exc:  # noqa: BLE001 - interrupt may surface as GraphInterrupt
            run.structured_output = mark_structured_failure(run.structured_output, str(exc))
            found = pending_interrupt_from_raw(exc) or pending_interrupt_from_raw(
                getattr(exc, "interrupts", None)
            )
            if found is not None:
                return found
            raise
        try:
            state = agent.get_state(config)
        except Exception:  # noqa: BLE001 - missing state is a completed or failed stream
            return None
        return pending_interrupt_from_raw(getattr(state, "interrupts", None))

    def _publish_interrupt(self, run: AgentRun, pending: Any) -> None:
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
                return decisions

    def _resume_reject_then_stop(
        self,
        agent: Any,
        run: AgentRun,
        pending: Any,
        config: dict[str, Any],
    ) -> None:
        payloads = reject_decisions_for(pending)
        self._clear_pending_interrupt(run, payloads)
        try:
            for chunk in agent.stream(
                Command(resume={"decisions": payloads}),
                config=config,
                stream_mode="updates",
            ):
                if _pending_from_chunk(chunk) is not None:
                    break
                self._ingest_stream(run, chunk)
        except Exception:  # noqa: BLE001 - cancel still wins if reject resume fails
            pass
        self._link_run(run, agent)
        self._finish(run, AgentRunStatus.cancelled, "cancelled")

    def _finish(self, run: AgentRun, status: AgentRunStatus, stop_reason: str) -> None:
        with self._lock:
            if run.status in TERMINAL_RUN_LIFECYCLE_STATUSES:
                if run.status is AgentRunStatus.cancelled and status is not AgentRunStatus.cancelled:
                    run.stop_reason = "cancelled"
                    run.finished_at = run.finished_at or utc_now()
                    run.updated_at = run.finished_at
                    self._persist_and_notify(run)
                return
            run.status = status
            run.stop_reason = stop_reason
            run.finished_at = utc_now()
            run.updated_at = run.finished_at
            event_detail: dict[str, Any] = {
                "stop_reason": stop_reason,
                "error": run.error,
                "confirmed": True,
            }
            failure_code = classify_connection_failure(run.error or "")
            if failure_code:
                event_detail["code"] = failure_code
            run.events.append(
                AgentEvent(
                    at=run.updated_at,
                    kind=status.value,
                    detail=event_detail,
                )
            )
            self._persist_and_notify(run)

    def _ingest_stream(self, run: AgentRun, chunk: Any) -> None:
        if not isinstance(chunk, dict):
            return
        changed = False
        for node, update in chunk.items():
            messages = update.get("messages") if isinstance(update, dict) else None
            if not messages:
                continue
            for message in messages:
                if self._ingest_message(run, message, str(node)):
                    changed = True
        if changed:
            with self._lock:
                self._persist_and_notify(run)

    def _ingest_message(self, run: AgentRun, message: BaseMessage | Any, node: str) -> bool:
        if isinstance(message, AIMessage) and message.invalid_tool_calls:
            raise HarnessError("The model returned malformed tool arguments. No invalid call was executed.", code="invalid_tool_call", status_code=409)
        now = utc_now()
        emitted = False
        if isinstance(message, AIMessage) and message.tool_calls:
            for call in message.tool_calls:
                name = call.get("name") if isinstance(call, dict) else getattr(call, "name", None)
                args = call.get("args") if isinstance(call, dict) else getattr(call, "args", {})
                call_id = call.get("id") if isinstance(call, dict) else getattr(call, "id", None)
                invocation = {"name": name, "args": args, "id": call_id, "node": node}
                run.tool_invocations.append(invocation)
                run.events.append(AgentEvent(at=now, kind="tool_call", detail=invocation))
                emitted = True
            run.updated_at = now
            return emitted
        if isinstance(message, ToolMessage):
            run.events.append(
                AgentEvent(
                    at=now,
                    kind="tool_result",
                    detail={
                        "name": message.name,
                        "content": message.content,
                        "tool_call_id": message.tool_call_id,
                        "node": node,
                    },
                )
            )
            run.updated_at = now
            return True
        if isinstance(message, AIMessage) and message.content:
            run.events.append(
                AgentEvent(
                    at=now,
                    kind="assistant_message",
                    detail={"content": message.content, "node": node},
                )
            )
            emitted = True
        run.updated_at = now
        return emitted

    def _deployment_model(self, run: AgentRun, http_sink: list[dict[str, Any]]) -> BaseChatModel:
        deployment = self.manager.ensure_deployment_ready(run.deployment_id)
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
            model.close()

    def _live_search_knowledge_tool(self, run: AgentRun, backend: Any) -> Any:
        """Build the official search tool, or none for recorded-tool / no retrieval."""

        if run.tool_mode is ToolMode.recorded_tool:
            return None
        if SEARCH_KNOWLEDGE_TOOL_NAME not in run.presented_tools:
            return None
        if not run.embedding_deployment_id or backend is None:
            return None
        embedding_deployment = resolve_embedding_deployment(
            self.manager,
            run.embedding_deployment_id,
        )
        refs = KnowledgeRefs(
            memory_version_refs=run.memory_version_refs,
            skill_version_refs=run.skill_version_refs,
            protected_instruction_version_refs=run.protected_instruction_version_refs,
        )
        documents = load_retrieval_documents(
            self._load_knowledge_versions(refs),
            list(run.retrieval_project_paths),
            run.project_path,
        )
        if not documents:
            raise HarnessError(
                "Retrieval was requested but the derived corpus is empty. No hits were invented.",
                code="retrieval_corpus_empty",
                status_code=409,
            )
        store = build_vector_store(documents, self._embeddings_factory(embedding_deployment))

        def on_retrieved(sources: list[str]) -> None:
            run.retrieved_material = record_retrieved_sources(run.retrieved_material, sources)

        return make_search_knowledge_tool(store, backend, on_retrieved)

    def _resolve_knowledge_refs(self, request: AgentStartRequest) -> KnowledgeRefs:
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

    def _knowledge_display_names(self, versions: list[KnowledgeVersion]) -> dict[str, str | None]:
        names: dict[str, str | None] = {}
        if self._knowledge_provider is None:
            return names
        service = self._knowledge_provider()
        for version in versions:
            if version.kind not in {"memory", "skill"} or version.entry_id in names:
                continue
            try:
                names[version.entry_id] = service.get_entry(version.entry_id).display_name
            except KnowledgeError:
                names[version.entry_id] = None
        return names

    def _knowledge_plan_for_run(self, run: AgentRun) -> KnowledgeMaterializePlan:
        refs = KnowledgeRefs(
            memory_version_refs=run.memory_version_refs,
            skill_version_refs=run.skill_version_refs,
            protected_instruction_version_refs=run.protected_instruction_version_refs,
        )
        versions = self._load_knowledge_versions(refs)
        return plan_knowledge_materialization(versions, self._knowledge_display_names(versions))

    def _link_run(self, run: AgentRun, agent: object) -> None:
        """Record checkpoint ids and related files in application records only."""

        run.checkpoint_ids = checkpoint_ids_from_graph(agent, _invoke_config(run))
        try:
            state = agent.get_state(_invoke_config(run))
            values = getattr(state, "values", {}) or {}
        except Exception:
            values = {}
        cancel = self._cancels.get(run.id)
        if cancel is not None and cancel.is_set():
            pending_calls: dict[str, dict[str, Any]] = {}
            for message in values.get("messages", []):
                for call in getattr(message, "tool_calls", []):
                    if call.get("id"):
                        pending_calls[call["id"]] = call
                if isinstance(message, ToolMessage):
                    pending_calls.pop(message.tool_call_id, None)
            if pending_calls:
                # Cancellation can land after the model checkpoint but before
                # tools run. Preserve calls and explicitly close their protocol
                # pairs without executing or replaying any tool. An interrupted
                # tool may have effects, so never invent a successful/no-op result.
                results = [ToolMessage(
                    tool_call_id=ident, name=call["name"], status="error",
                    content="Run cancelled before a tool result was recorded. Completion is unconfirmed; inspect state before retrying any action.",
                ) for ident, call in pending_calls.items()]
                agent.update_state(_invoke_config(run), {"messages": results})
                run.checkpoint_ids = checkpoint_ids_from_graph(agent, _invoke_config(run))
                run.events.append(AgentEvent(at=utc_now(), kind="cancelled_tool_results", detail={"tool_call_ids": list(pending_calls), "execution_confirmed": False}))
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
                state = agent.get_state(_invoke_config(run))
                values = getattr(state, "values", None)
                run.structured_output = update_structured_result_from_state(
                    run.structured_output,
                    values if isinstance(values, dict) else None,
                )
            except Exception as exc:  # noqa: BLE001 - state loss is diagnostic, not success.
                run.structured_output = mark_structured_failure(run.structured_output, str(exc))
        self._collect_related_files(run)

    def _validate_content_capabilities(
        self,
        deployment: Deployment,
        request: AgentStartRequest,
    ) -> None:
        has_image = any(getattr(block, "type", None) == "image_url" for block in request.content_blocks or [])
        if not has_image:
            return
        props = deployment.server_props
        if props is not None and props.modalities.get("vision") is False:
            raise HarnessError(
                "This setup reports that image input is not supported.",
                code="image_input_unavailable",
                status_code=409,
                details={"constraint": "server_props.modalities.vision=false"},
            )

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
        stored = self.store.get_run(run_id)
        if stored is None:
            raise HarnessError("Unknown agent run", code="run_missing", status_code=404)
        return self._runs.setdefault(run_id, stored)

    def _reconcile_startup_once(self) -> None:
        with self._lock:
            if self._startup_reconciled:
                return
            for run in self.store.list_runs():
                if not is_run_lifecycle_live(run.status):
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

    def _mark_orphaned_run(self, run: AgentRun) -> None:
        with self._lock:
            live = self._runs.setdefault(run.id, run)
            if not is_run_lifecycle_live(live.status):
                return
            missing_checkpoint = live.pending_interrupt is not None
            cancelling = live.status is AgentRunStatus.cancel_requested
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
        saver = open_sqlite_checkpointer(self.manager.paths.checkpoints_db)
        for checkpoint_id in run.checkpoint_ids:
            if not checkpoint_id:
                continue
            config = {
                "configurable": {
                    "thread_id": thread_id,
                    "checkpoint_ns": "",
                    "checkpoint_id": checkpoint_id,
                }
            }
            try:
                if saver.get_tuple(config) is not None:
                    return True
            except Exception:  # noqa: BLE001 - missing/unreadable checkpoint is not resumable
                return False
        return False

    def _persist(self, run: AgentRun) -> None:
        sanitized = apply_run_diagnostic_policy(run, self._capture_settings())
        run.model_requests = sanitized.model_requests
        self.store.put_run(run.model_copy(deep=True))

    def _persist_and_notify(self, run: AgentRun) -> None:
        self._persist(run)
        self._updates.notify_all()

    def _capture_settings(self) -> ContextCaptureSettings:
        if self._knowledge_provider is not None:
            return self._knowledge_provider().get_config().context_captures
        return capture_settings_for_paths(self.manager.paths)

    def _expose_run(self, run: AgentRun) -> AgentRun:
        sanitized = apply_run_diagnostic_policy(run, self._capture_settings())
        if sanitized.model_requests != run.model_requests:
            run.model_requests = sanitized.model_requests
            self.store.put_run(run.model_copy(deep=True))
        return sanitized.model_copy(deep=True)

    def _capture_starting_snapshot(
        self,
        request: AgentStartRequest,
        project_path: str | None,
    ) -> str | None:
        """Bind a starting snapshot before the worker can mutate project files."""

        workspace_id = request.workspace_id
        allowlist: list[str] | None = None
        root: Path | None = None
        if request.workspace_id:
            stored = LabStore(self.manager.paths).get_workspace(request.workspace_id)
            if stored is not None:
                root = Path(stored.path)
                allowlist = stored.allowlist
                workspace_id = stored.id
        if root is None and project_path:
            root = Path(project_path)
            workspace_id = workspace_id or "unbound"
        if root is None or workspace_id is None:
            return None
        try:
            manifest = capture_project_snapshot(
                self.manager.paths.ensure(),
                workspace_id=workspace_id,
                project_root=root,
                kind="starting",
                allowlist=allowlist,
            )
        except OSError as exc:
            raise HarnessError(
                f"Starting snapshot could not be captured: {exc}",
                code="starting_snapshot_failed",
                status_code=409,
            ) from exc
        return manifest.id


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


def _pending_from_chunk(chunk: Any) -> Any:
    """Normalize a LangGraph ``stream_mode='updates'`` interrupt chunk."""

    if not isinstance(chunk, dict):
        return None
    raw = chunk.get("__interrupt__")
    if raw is None:
        return None
    return pending_interrupt_from_raw(raw)


def _invoke_config(run: AgentRun) -> dict[str, Any]:
    """Thread id is required so LangGraph can write checkpoints.sqlite."""

    config: dict[str, Any] = {"configurable": {"thread_id": run.thread_id or run.id}}
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
