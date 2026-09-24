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
from contextlib import asynccontextmanager, contextmanager
from pathlib import Path
from typing import Any

import httpx
from deepagents import create_deep_agent
from deepagents.backends import StateBackend
from deepagents.middleware.summarization import SummarizationMiddleware, SUMMARIZATION_EVENT_KEY
from langchain.agents.middleware import TodoListMiddleware
from langchain_core.embeddings import Embeddings
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, RemoveMessage, SystemMessage, ToolMessage
from langchain_core.outputs import ChatResult
from langgraph.graph.message import REMOVE_ALL_MESSAGES
from langgraph.types import Command

from workbench_backend.agents.effective_setup import resolve_effective_setup
from workbench_backend.agents.file_changes import FileChangeRecorder, ProjectFileChangeView, change_view, reverse_change
from workbench_backend.agents.setup_service import SetupService, configuration_from_request, cleared_configuration_fields
from workbench_backend.agents.setup_schemas import ProjectCreateRequest, InstructionLayer, FrozenHelperSelection, ReviewConfiguration, FrozenExecutionSelection
from workbench_backend.inference.schemas import SettingsBags
from workbench_backend.agents.helpers import freeze_helpers
from workbench_backend.agents.execution_policy import ExecutionControl, PLAN_TOOLS, PLAN_INSTRUCTIONS, require_setup_capabilities
from workbench_backend.agents.evidence import build_completion
from workbench_backend.agents.context import BudgetedSummarizationMiddleware, observe_context, require_context_fit, observe_payload, count_context_tokens, validate_retained_messages
from workbench_backend.agents.harness_backend import build_run_backend, is_reserved_framework_path, harness_scratch_root
from workbench_backend.agents.harness_profile import ensure_ordinary_chat_profile
from workbench_backend.agents.memory_skills import (
    KnowledgeMaterializePlan,
    official_agent_kwargs,
    materialize_onto_backend,
    plan_knowledge_materialization,
    KnowledgeRefreshMiddleware,
    clear_derived_knowledge,
    configured_memory_middleware,
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
    approval_mode_instructions,
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
    GenerationObservation,
    HostShellFacts,
    InterruptDecisionRequest,
    UserAnswerRequest,
    PendingInterrupt,
    TaskCriteria,
    ReviewObservation,
    ToolMode,
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
    project_mutation_tools,
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
from workbench_backend.lab.schemas import SnapshotManifest
from workbench_backend.lab.snapshot import (
    capture_project_snapshot,
    discard_incomplete_snapshot_staging,
    verify_snapshot_tree,
)
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
    ) -> None:
        self._manager_provider = manager_provider
        self._model_factory = model_factory or self._deployment_model
        self._knowledge_provider = knowledge_provider
        self._app_store = app_store
        self._embeddings_factory = embeddings_factory or openai_embeddings_for_deployment
        self._interaction_observer = interaction_observer
        self._runs: dict[str, AgentRun] = {}
        self._cancels: dict[str, threading.Event] = {}
        self._threads: dict[str, threading.Thread] = {}
        self._native_streams: dict[str, Any] = {}
        self._interaction_failure_runs: set[str] = set()
        self._terminal_retries: dict[str, tuple[AgentRunStatus, str]] = {}
        self._decision_ready: dict[str, threading.Event] = {}
        self._pending_decisions: dict[str, list[dict[str, str]] | None] = {}
        self._model_clients: dict[str, httpx.Client] = {}
        self._adapter_models: dict[str, Any] = {}
        self._start_cancel_guards: dict[tuple[str | None, str | None], threading.Event] = {}
        self._finalizing_runs: set[str] = set()
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
        with self._lock:
            stored = {item.id: item for item in self.store.list_runs()}
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
            self._runs.setdefault(run_id, stored)
            return self._expose_run(stored)

    @contextmanager
    def run_read_lock(self, run_id: str) -> Iterator[None]:
        """Keep a derived history read atomic with deletion of its run."""
        with self._lock:
            self._require_run(run_id)
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
                run = self._runs.get(run_id) or self.store.get_run(run_id)
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

    def checkpoint_state_for_run(self, run: AgentRun, checkpoint_id: str) -> dict[str, Any]:
        # Use the execution graph's exact framework topology and state schema,
        # but never initialize inference, retrieval, or materialized storage.
        agent = self._create_compiled_agent(run.model_copy(deep=True), [], None, inspection_only=True)
        snapshot = _graph_checkpoint_snapshot(agent, run.thread_id, checkpoint_id)
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

    def start(self, request: AgentStartRequest, *, instruction_snapshot: list[InstructionLayer] | None = None, helper_snapshot: list[FrozenHelperSelection] | None = None, execution_snapshot: FrozenExecutionSelection | None = None) -> AgentRun:
        self._reconcile_startup_once()
        selection_service = SetupService(self.store, self.manager, self._knowledge_provider() if self._knowledge_provider else None, connection_available=self.connections.available, connection_tools=lambda ident: [tool.name for tool in self.connections.get(ident).tools])
        if request.project_path and not request.project_id and not request.workspace_id:
            project = selection_service.create_project(ProjectCreateRequest(path=request.project_path))
            request = request.model_copy(update={"project_id": project.id})
        selection = execution_snapshot.selection if execution_snapshot is not None else selection_service.resolve(
            project_id=request.project_id,
            agent_setup_version_id=request.agent_setup_version_id,
            overrides=configuration_from_request(request),
            override_cleared_fields=cleared_configuration_fields(request),
            validate=bool(request.project_id or request.agent_setup_version_id),
            prepare_model=True,
        )
        if execution_snapshot is not None:
            issues = selection_service.dependencies(selection.configuration)
            if issues:
                raise HarnessError("The queued setup has unavailable dependencies. Edit its selections before running.", code="setup_dependencies_missing", status_code=409,
                    details={"missing_dependencies": [item.model_dump() for item in issues]})
        if instruction_snapshot is not None:
            selection = selection.model_copy(update={"instruction_layers": instruction_snapshot})
        selected = selection.configuration.model_dump(exclude_none=True, exclude={"instructions", "requires_project", "requires_host_shell", "bundle_id"})
        if selection.configuration.review is not None:
            selected["review"] = selection.configuration.review
        if request.project_id:
            project = selection_service.get_project(request.project_id, require_active=True)
            workspace = LabStore(self.manager.paths).get_workspace(request.workspace_id) if request.workspace_id else None
            # A checkpoint branch keeps its original project identity/defaults,
            # while its files live in the separately registered restored copy.
            execution_path = workspace.path if workspace is not None and workspace.origin == "restored" else project.path
            if request.project_path and Path(request.project_path).resolve() != Path(execution_path).resolve():
                raise HarnessError("The folder does not match the selected project.", code="project_mismatch", status_code=409)
            selected["project_path"] = execution_path
        request = request.model_copy(update=selected)
        if request.criteria and request.criteria.review_prompt and not request.review.enabled:
            request = request.model_copy(update={"review": ReviewConfiguration(enabled=True, criteria=request.criteria.review_prompt)})
        helpers = helper_snapshot if helper_snapshot is not None else freeze_helpers(selection_service,
            request.helper_agent_ids, project_id=request.project_id, parent_configuration=selection.configuration)
        if helper_snapshot is not None and set(request.helper_agent_ids) != {item.agent_id for item in helper_snapshot}:
            raise HarnessError("The frozen helper selection does not match this queued turn.", code="helper_snapshot_mismatch", status_code=409)
        if not request.deployment_id:
            raise HarnessError("Choose a model or an agent setup with a model.", code="setup_deployment_required", status_code=400)
        require_setup_capabilities(selection.configuration,
            project_bound=bool(request.project_path or request.workspace_id), presented_tools=request.presented_tools)
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
                self._knowledge_provider().resource_bytes if self._knowledge_provider else None,
            )
            profile = self.manager.get_profile(request.profile_id) if request.profile_id and execution_snapshot is None else None
            project_path = _resolved_project_path(request.project_path)
            if project_path is None and request.workspace_id:
                stored = LabStore(self.manager.paths).get_workspace(request.workspace_id)
                if stored is not None:
                    project_path = _resolved_project_path(stored.path)
            from workbench_backend.assets.tools import validate_retained_selection
            validate_retained_selection(self.store, request.retained_asset_ids,
                thread_id=request.thread_id, project_path=str(project_path) if project_path else None)
            connection_snapshots = self.connections.snapshot(request.connection_ids or [], tools_enabled=request.presented_tools != [])
            external_names = [tool.name for connection in connection_snapshots for tool in connection.tools]
            presented, denied, filesystem_blocked, shell_blocked = resolve_presented_tools(
                request.presented_tools,
                project_bound=project_path is not None,
                knowledge_routes=knowledge_plan.has_knowledge_routes,
                external_names=external_names,
                attachment_available=bool(request.retained_asset_ids),
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
            framework_read_paths = (
                ["/large_tool_results/", "/conversation_history/"]
                if presented and "read_file" not in presented and not recorded else []
            )
            if retrieval_presented and request.presented_tools == []:
                raise HarnessError(
                    "Retrieval requires its search tool. Enable tools or remove the retrieval selection.",
                    code="retrieval_tools_off",
                    status_code=400,
                )
            if helpers and request.presented_tools != []:
                presented = [*presented, "task"]
            if request.work_mode == "plan":
                presented = [name for name in presented if name in PLAN_TOOLS]
            require_setup_capabilities(selection.configuration,
                project_bound=project_path is not None, presented_tools=presented)
            if request.resume_checkpoint_id:
                if request.source_surface != "chat" or not request.thread_id:
                    raise HarnessError(
                        "Checkpoint resume is only supported for internal Chat branch regeneration.",
                        code="checkpoint_resume_internal_only",
                        status_code=400,
                    )
                if request.presented_tools != []:
                    raise HarnessError(
                        "Checkpoint resume requires tools to be explicitly off.",
                        code="checkpoint_resume_tools_forbidden",
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
                attachment_available=bool(request.retained_asset_ids),
            )
            enabled = [*enabled, *external_names]
            if helpers and request.presented_tools != []:
                enabled.append("task")
            if framework_read_paths and "read_file" not in enabled:
                enabled.append("read_file")
            if retrieval_presented and SEARCH_KNOWLEDGE_TOOL_NAME not in enabled:
                enabled = [*enabled, SEARCH_KNOWLEDGE_TOOL_NAME]
            setup = resolve_effective_setup(
                deployment=deployment.model_copy(update={"settings": SettingsBags.model_validate(execution_snapshot.settings)}) if execution_snapshot is not None else deployment,
                profile=profile,
                per_request_overrides=request.per_request_overrides,
                startup_overrides=None if execution_snapshot is not None else request.startup_overrides,
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
                inherit_deployment_settings=True if execution_snapshot is not None else request.inherit_deployment_settings,
                instruction_layers=selection.instruction_layers,
                selected_project_id=selection.project_id,
                selected_agent_setup_id=selection.agent_setup_id,
                selected_agent_setup_version_id=selection.agent_setup_version_id,
                selected_connection_ids=request.connection_ids,
            )
            if execution_snapshot is not None:
                setup.selected_profile_id = request.profile_id
                if setup.startup_mismatches:
                    raise HarnessError("This queued turn needs different loaded model settings. Reload the model or edit this turn before retrying.", code="model_reload_required", status_code=409)
            setup.system_prompt = "\n\n".join((setup.system_prompt, approval_mode_instructions(request.approval_mode)))
            if request.work_mode == "plan":
                setup.system_prompt += "\n\n" + PLAN_INSTRUCTIONS
            if execution_snapshot is not None and execution_snapshot.system_prompt is not None:
                setup.system_prompt = execution_snapshot.system_prompt
            _, structured_output = response_format_for_run(
                output_schema=request.output_schema,
                deployment=deployment,
                per_request=setup.bags.per_request,
                tools_presented=bool(presented),
                tools_off=request.presented_tools == [],
            )
            if request.resume_checkpoint_id:
                now = utc_now()
                validation_run = AgentRun(
                    id=new_id("agent_validation"),
                    status=AgentRunStatus.queued,
                    deployment_id=deployment.id,
                    project_id=selection.project_id,
                    agent_setup_id=selection.agent_setup_id,
                    agent_setup_version_id=selection.agent_setup_version_id,
                    connection_ids=list(request.connection_ids or []),
                    connection_snapshots=connection_snapshots,
                    retained_asset_ids=list(request.retained_asset_ids),
                    task=request.task,
                    content_blocks=request.content_blocks,
                    enabled_tools=enabled,
                    presented_tools=presented,
                    framework_read_paths=framework_read_paths,
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
                    thread_id=request.thread_id,
                    resume_checkpoint_id=request.resume_checkpoint_id,
                    related_files=_initial_related_files(project_path),
                    effective_setup=setup,
                    host_shell=HostShellFacts(
                        available=False,
                        cwd=project_path,
                    ),
                    output_schema=request.output_schema,
                    structured_output=structured_output,
                )
                validation_agent = self._create_compiled_agent(validation_run, [], None, inspection_only=True)
                snapshot = _graph_checkpoint_snapshot(
                    validation_agent,
                    request.thread_id,
                    request.resume_checkpoint_id,
                )
                saved_state = dict(snapshot.values)
            else:
                saved_state = conversation_state(self.manager.paths.checkpoints_db, request.thread_id) if request.thread_id else {}
            retained = list(saved_state.get("messages", []))
            # Use the installed upstream reconstruction, not a second history reducer.
            retained = SummarizationMiddleware._apply_event_to_messages(retained, saved_state.get(SUMMARIZATION_EVENT_KEY))
            validation_messages = [SystemMessage(content=setup.system_prompt), *retained]
            if not request.resume_checkpoint_id:
                validation_messages.append(HumanMessage(content=user_message_content(request.task, request.content_blocks)))
            validate_retained_messages(deployment, validation_messages)
            context_observation = observe_context(
                deployment=deployment,
                per_request=setup.bags.per_request,
                system_prompt=setup.system_prompt,
                task="" if request.resume_checkpoint_id else request.task,
                content_blocks=None if request.resume_checkpoint_id else request.content_blocks,
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
            # Another live run in this folder does not block a new one. The person
            # chooses which run writes. Lab capture and backup still wait for a quiet folder.
            starting_snapshot_id = self._capture_starting_snapshot(request, project_path)
            now = utc_now()
            run = AgentRun(
                id=new_id("agent"),
                status=AgentRunStatus.queued,
                deployment_id=deployment.id,
                    project_id=selection.project_id,
                    agent_setup_id=selection.agent_setup_id,
                    agent_setup_version_id=selection.agent_setup_version_id,
                    connection_ids=list(request.connection_ids or []),
                    connection_snapshots=connection_snapshots,
                    retained_asset_ids=list(request.retained_asset_ids),
                task=request.task,
                content_blocks=request.content_blocks,
                enabled_tools=enabled,
                presented_tools=presented,
                approval_mode=request.approval_mode,
                requires_project=bool(selection.configuration.requires_project),
                requires_host_shell=bool(selection.configuration.requires_host_shell),
                work_mode=request.work_mode,
                helper_agent_ids=list(request.helper_agent_ids),
                helper_snapshots=helpers,
                review=request.review,
                review_observation=ReviewObservation(enabled=request.review.enabled,
                    status="review_pending" if request.review.enabled else "not_requested"),
                framework_read_paths=framework_read_paths,
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
                resume_checkpoint_id=request.resume_checkpoint_id,
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
            input_message_id = getattr(request, "input_message_id", None)
            if input_message_id and hasattr(run, "input_message_id"):
                run.input_message_id = input_message_id
            # Agent-run / Lab own one thread per run. Chat follow-ups pass the
            # conversation thread so LangGraph resumes the same checkpointer state.
            run.thread_id = request.thread_id or run.id
            if request.thread_id:
                run.pre_run_checkpoint_id = self._checkpoint_head(run.thread_id)
            with self._lock:
                cancel = self._start_cancel_guards.get((request.thread_id, input_message_id)) or threading.Event()
                if cancel.is_set():
                    run.status = AgentRunStatus.cancel_requested
                    run.events.append(
                        AgentEvent(
                            at=utc_now(),
                            kind="cancel_requested",
                            detail={"requested": True, "confirmed": False},
                        )
                    )
                    run.updated_at = utc_now()
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
            threads = list(self._threads.values())
            run_ids = [run_id for run_id, worker in self._threads.items() if worker.is_alive()]
        for run_id in run_ids:
            submit_checkpoint_task(self.manager.paths.checkpoints_db, self._abort_native_run(run_id))
        for thread in threads:
            thread.join(timeout=timeout)
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
                    "Execution has finished and this run is saving its project snapshot.",
                    code="run_finalizing",
                    status_code=409,
                )
            if run.parent_run_id:
                parent = self._runs.get(run.parent_run_id) or self.store.get_run(run.parent_run_id)
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
            return run.model_copy(deep=True)

    def resume_interrupt(
        self,
        run_id: str,
        request: InterruptDecisionRequest | UserAnswerRequest,
        *,
        require_interrupt_identity: bool = False,
    ) -> AgentRun:
        """Apply Deep Agents HITL decisions. Does not invent a durable inbox."""

        self._reconcile_startup_once()
        with self._lock:
            run = self._require_run(run_id)
            pending = run.pending_interrupt
            if run.parent_run_id:
                parent = self._runs.get(run.parent_run_id) or self.store.get_run(run.parent_run_id)
                if parent is not None and any(item.run_id == run.id for item in parent.child_runs):
                    raise HarnessError("Respond to this helper's approval in its parent conversation.", code="child_approval_owned_by_parent", status_code=409,
                        details={"parent_run_id": parent.id})
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
                if isinstance(request, UserAnswerRequest):
                    question = pending.question
                    if pending.kind != "ask_user" or question is None:
                        raise ValueError("interrupt_answer_type")
                    if request.cancelled:
                        if request.answer:
                            raise ValueError("Cancelled answers must not include answer text")
                        payloads = [{"type": "user_answer", "cancelled": True}]
                    elif not request.answer.strip():
                        raise ValueError("An answer is required")
                    else:
                        if question.answer_type == "choice" and request.answer not in question.choices:
                            raise ValueError("Choose one of the offered answers")
                        if question.answer_type in {"file", "folder"}:
                            chosen = Path(request.answer).expanduser()
                            if not chosen.is_absolute() or not (chosen.is_file() if question.answer_type == "file" else chosen.is_dir()):
                                raise ValueError("Select an existing absolute file or folder path")
                        payloads = [{"type": "user_answer", "answer": request.answer}]
                else:
                    if pending.kind != "deepagents_interrupt_on":
                        raise ValueError("interrupt_answer_type")
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
            for action, decision in zip(pending.action_requests, getattr(request, "decisions", []), strict=True):
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
    async def _compiled_agent_context(self, run, http_sink, fixture_bank):
        # Session-bound tools enter here on the common loop and stay open across
        # native approval waits. Synchronous setup/file work cannot block it.
        async with self.connections.open_tools(run) as external_tools:
            agent = await asyncio.to_thread(self._create_compiled_agent, run, http_sink, fixture_bank,
                external_tools=external_tools)
            yield agent

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
                        await asyncio.to_thread(self._clear_pending_interrupt, run, decisions)
                    await self._adrive_until_terminal(run, agent, cancel, payload)
            except BaseException as exc:
                if not isinstance(exc, HarnessError) or exc.code != "checkpoint_linkage_failed":
                    try:
                        await self._alink_run(run, agent)
                    except Exception:  # noqa: BLE001 - retain the original graph or display failure
                        pass
                raise

    def _create_compiled_agent(
        self,
        run: AgentRun,
        http_sink: list[dict[str, Any]],
        fixture_bank: FixtureBank | None,
        *,
        inspection_only: bool = False,
        external_tools: list[Any] | None = None,
        execution_control: ExecutionControl | None = None,
        is_child: bool = False,
    ) -> Any:
        execution_control = execution_control or ExecutionControl(run, lambda: self._publish_control_update(run))
        model = _CheckpointInspectionModel() if inspection_only else self._model_factory(run, http_sink)
        agent_kwargs: dict[str, Any] = {}
        backend = build_run_backend(run, self.manager.paths, prepare_storage=not inspection_only)
        knowledge_plan = self._knowledge_plan_for_run(run)
        if backend is not None:
            agent_kwargs["backend"] = backend
            if not inspection_only:
                clear_derived_knowledge(harness_scratch_root(self.manager.paths, run.id if run.parent_run_id else run.thread_id or run.id))
                materialize_onto_backend(backend, knowledge_plan)
        observation = run.context_observation
        usable = observation.usable_input_tokens if observation is not None else None
        # Override provider-name defaults; only observed runtime capacity is a fact.
        model.profile = {"max_input_tokens": usable} if usable else {}
        if not inspection_only and callable(getattr(model, "set_generation_observer", None)):
            latest_request_id: str | None = None

            def observe_generation(sample: dict[str, Any]) -> None:
                nonlocal latest_request_id
                with self._lock:
                    if not is_run_lifecycle_live(run.status) or run.finalization_phase is not None:
                        return
                    latest_sample = model.latest_generation_sample() if callable(getattr(model, "latest_generation_sample", None)) else None
                    if latest_sample is not None and sample.get("request_id") != latest_sample.get("request_id"):
                        return
                    if sample.get("reset"):
                        latest_request_id = sample["request_id"]
                        run.generation_observation = None
                    elif sample["request_id"] == latest_request_id:
                        if latest_sample is not None and sample != latest_sample:
                            return
                        run.generation_observation = GenerationObservation(
                            **sample, context_limit=observation.capacity_tokens if observation else None,
                        )
                    else:
                        return
                    run.updated_at = utc_now()
                    # Persistence/projection can block on SQLite. Preserve the
                    # sampled identity, then publish after releasing the shared
                    # harness lock so one measurement cannot freeze other runs.
                    telemetry_run = run.model_copy(update={
                        "events": list(run.events),
                        "tool_invocations": list(run.tool_invocations),
                        "model_requests": [],
                    }, deep=False)
                    self._updates.notify_all()
                self._observe_interaction(telemetry_run, None, telemetry=True)

            model.set_generation_observer(observe_generation)
        if observation is not None and callable(getattr(model, "set_context_guard", None)):
            def guard(payload: dict[str, Any]) -> None:
                observed = observe_payload(observation, payload)
                run.context_observation = observed
                require_context_fit(observed)
            model.set_context_guard(guard)
        summarization = BudgetedSummarizationMiddleware(
            model=model, backend=backend or (lambda runtime: StateBackend(runtime)),
            allowed_tools=set(run.presented_tools) | ({"read_file"} if run.framework_read_paths else set()),
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
        from workbench_backend.state.preferences import PreferenceStore
        interrupt_on = interrupt_on_for_run(run, PreferenceStore(self.store))
        if interrupt_on:
            agent_kwargs["interrupt_on"] = interrupt_on
        tools = [*tools_for_names(run.presented_tools), *(external_tools or [])]
        if run.project_path:
            tools.extend(tool for tool in project_mutation_tools(run.project_path) if tool.name in run.presented_tools)
        if "propose_memory" in run.presented_tools and self._knowledge_provider is not None:
            tools.append(memory_proposal_tool(run.id, self._knowledge_provider()))
        if "read_attachment" in run.presented_tools and run.retained_asset_ids:
            from workbench_backend.assets.tools import attachment_tool_for_run
            tools.append(attachment_tool_for_run(self.store, run))
        retrieval_tool = self._live_search_knowledge_tool(run, backend, inspection_only=inspection_only)
        if retrieval_tool is not None:
            tools = [*tools, retrieval_tool]
        deployment = (self.manager.get_deployment(run.deployment_id) if inspection_only
                      else self.manager.ensure_deployment_ready(run.deployment_id))
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
        ensure_ordinary_chat_profile(model)
        from workbench_backend.agents.review import review_middleware
        from workbench_backend.agents.helper_execution import compiled_helpers
        if run.helper_snapshots and "task" in run.presented_tools and not is_child:
            agent_kwargs["subagents"] = compiled_helpers(self, run, execution_control,
                inspection_only=inspection_only)
        return create_deep_agent(
            model=model,
            tools=tools,
            system_prompt=run.system_prompt,
            middleware=[
                summarization,
                KnowledgeRefreshMiddleware(backend, knowledge_plan),
                *configured_memory_middleware(backend, knowledge_plan),
                *([StructuredOutputRepairMiddleware(run.structured_output, on_event=lambda kind, detail: run.events.append(
                    AgentEvent(at=utc_now(), kind=kind, detail=detail)
                ))] if run.structured_output is not None else []),
                *([TodoListMiddleware()] if "write_todos" in run.presented_tools else []),
                *([review_middleware(run, model, http_sink, execution_control, self._capture_settings,
                    lambda mutation=None: self._publish_control_update(run, mutation))] if run.review.enabled and not is_child else []),
                WorkbenchHarnessMiddleware(
                    run,
                    http_sink,
                    settings_provider=self._capture_settings,
                    fixture_bank=fixture_bank,
                    file_changes=FileChangeRecorder(run, lambda mutation: self._record_file_change(run, mutation)),
                    execution_control=execution_control,
                )
            ],
            name="workbench-embedded-harness",
            response_format=response_format,
            checkpointer=True if is_child else open_sqlite_checkpointer(self.manager.paths.checkpoints_db),
            **agent_kwargs,
        )

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
            decisions = await asyncio.to_thread(self._wait_for_interrupt_decisions, run.id, cancel)
            if decisions is None:
                await self._aresume_reject_then_stop(agent, run, pending, config, message_nodes)
                return
            await asyncio.to_thread(self._clear_pending_interrupt, run, decisions)
            current = Command(resume=_resume_value(decisions))

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
                return found
            raise
        finally:
            self._native_streams.pop(run.id, None)
            await self._close_native_stream(stream)
        if pending is not None:
            return pending
        try:
            state = await agent.aget_state(config)
        except Exception:  # noqa: BLE001 - missing state is a completed or failed stream
            return None
        return pending_interrupt_from_raw(getattr(state, "interrupts", None))

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
                if run.id in self._finalizing_runs:
                    return
                # A restart may have interrupted only snapshot persistence. The
                # graph outcome was already durable; never rerun its tools.
                status = AgentRunStatus(run.settled_status or "failed")
                stop_reason = run.settled_stop_reason or status.value
                snapshot_id = self._settled_snapshot_id(run)
            else:
                if run.stop_reason == "tool_budget_exhausted" and status == AgentRunStatus.failed:
                    stop_reason = run.stop_reason
                cancel = self._cancels.get(run.id)
                if cancel is not None and cancel.is_set() and status is not AgentRunStatus.cancelled:
                    status, stop_reason = AgentRunStatus.cancelled, "cancelled"
                if not run.project_path or run.final_snapshot_id is not None:
                    self._commit_terminal_run(run, status, stop_reason)
                    return
                self._merge_latest_generation_sample(run)
                run.finalization_phase = "saving_changes"
                run.settled_status = status.value
                run.settled_stop_reason = stop_reason
                run.updated_at = utc_now()
                snapshot_id = new_id("snap")
                run.events.append(AgentEvent(at=run.updated_at, kind="finalizing",
                    detail={"phase": "saving_changes", "execution_settled": True, "snapshot_id": snapshot_id}))
                self._finalizing_runs.add(run.id)
                try:
                    self._persist_and_notify(run)
                except BaseException:
                    self._finalizing_runs.discard(run.id)
                    raise
            self._finalizing_runs.add(run.id)
            project_path = Path(run.project_path or "")
            workspace_id = run.workspace_id or "unbound"

        manifest = None
        snapshot_error: Exception | None = None
        try:
            if recovering:
                if snapshot_id is not None:
                    discard_incomplete_snapshot_staging(self.manager.paths, snapshot_id)
                manifest = self._published_settled_snapshot(snapshot_id, workspace_id)
            else:
                manifest = capture_project_snapshot(self.manager.paths, workspace_id=workspace_id,
                    project_root=project_path, kind="final", snapshot_id=snapshot_id)
        except Exception as exc:  # noqa: BLE001 - execution outcome survives a missing branch snapshot
            snapshot_error = exc
        with self._lock:
            self._finalizing_runs.discard(run.id)
            if manifest is not None:
                run.final_snapshot_id = manifest.id
            elif snapshot_error is not None:
                run.events.append(AgentEvent(at=utc_now(), kind="branch_snapshot_unavailable",
                    detail={"message": str(snapshot_error)}))
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

    def _published_settled_snapshot(self, snapshot_id: str | None, workspace_id: str) -> SnapshotManifest:
        if snapshot_id is None:
            raise OSError("The settled run has no reserved final snapshot identity.")
        root = self.manager.paths.snapshots / snapshot_id
        manifest_path = root / "manifest.json"
        if not manifest_path.is_file():
            raise OSError("Final snapshot capture was interrupted before publication.")
        manifest = SnapshotManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))
        if (manifest.id != snapshot_id or manifest.workspace_id != workspace_id or manifest.kind != "final"
            or Path(manifest.tree_path) != root / "tree"):
            raise OSError("The published final snapshot does not match the settled run.")
        verify_snapshot_tree(root / "tree", manifest.included_files)
        return manifest

    def _merge_latest_generation_sample(self, run: AgentRun) -> None:
        model = self._adapter_models.get(run.id)
        accessor = getattr(model, "latest_generation_sample", None)
        sample = accessor() if callable(accessor) else None
        if not isinstance(sample, dict):
            return
        if sample.get("reset"):
            run.generation_observation = None
            return
        try:
            run.generation_observation = GenerationObservation(
                **sample,
                context_limit=run.context_observation.capacity_tokens if run.context_observation else None,
            )
        except (TypeError, ValueError):
            # A malformed measurement cannot change the graph's settled result.
            return

    def _commit_terminal_run(self, run: AgentRun, status: AgentRunStatus, stop_reason: str) -> None:
        settled_copy = run.model_copy(deep=True)
        self._merge_latest_generation_sample(run)
        run.finalization_phase = None
        run.settled_status = None
        run.settled_stop_reason = None
        run.status = status
        run.stop_reason = stop_reason
        run.finished_at = utc_now()
        run.updated_at = run.finished_at
        # Inline children have no detached worker once their owning graph ends.
        for activity in run.child_runs:
            child = self._runs.get(activity.run_id) or self.store.get_run(activity.run_id)
            if child is not None and is_run_lifecycle_live(child.status):
                child.status = AgentRunStatus.cancelled if status == AgentRunStatus.cancelled else AgentRunStatus.failed
                child.stop_reason = "parent_" + str(status.value)
                child.finished_at = run.finished_at
                child.updated_at = run.finished_at
                activity.status = child.status.value
                self._persist(child)
        if run.generation_observation is not None and run.generation_observation.phase in {"prompt_processing", "generating"}:
            run.generation_observation = run.generation_observation.model_copy(update={
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
                saved = self.store.get_run(run.id)
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
        # Token and measurement updates must not scan or copy captured model
        # requests. That copy was slower than generation and left Chat on Running
        # after llama.cpp had already finished the call.
        if event is not None or telemetry:
            self._interaction_observer(run, event, **({"telemetry": True} if telemetry else {}))
            return
        safe = apply_run_diagnostic_policy(run, self._capture_settings())
        self._interaction_observer(safe, None)

    def projection_run(self, run_id: str) -> dict[str, Any]:
        """Run fields for a live display frame, without captured model requests."""
        self._reconcile_startup_once()
        with self._lock:
            run = self._runs.get(run_id)
            if run is None:
                stored = self.store.get_run(run_id)
                if stored is None:
                    raise HarnessError("Unknown agent run", code="run_missing", status_code=404)
                run = stored
            data = run.model_dump(mode="json")
        data["model_requests"] = []
        return data

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
            raise HarnessError("The model returned malformed tool arguments. No invalid call was executed.", code="invalid_tool_call", status_code=409)
        now = utc_now()
        emitted = False
        if isinstance(message, AIMessage) and message.tool_calls:
            for call in message.tool_calls:
                name = call.get("name") if isinstance(call, dict) else getattr(call, "name", None)
                args = call.get("args") if isinstance(call, dict) else getattr(call, "args", {})
                call_id = call.get("id") if isinstance(call, dict) else getattr(call, "id", None)
                invocation = {"name": name, "args": args, "id": call_id}
                if node:
                    invocation["node"] = node
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
        if not run.embedding_deployment_id or backend is None:
            return None
        if inspection_only:
            return make_search_knowledge_tool(_CheckpointInspectionVectorStore(), backend)
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
        return plan_knowledge_materialization(versions, self._knowledge_display_names(versions), self._knowledge_provider().resource_bytes if self._knowledge_provider else None)

    async def _alink_run(self, run: AgentRun, agent: object) -> None:
        """Record checkpoint ids and related files in application records only."""

        await self._alink_new_checkpoints(run, agent)
        try:
            state = await agent.aget_state(_invoke_config(run))
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
                repaired_messages = list(values.get("messages", []))
                existing_ids = {getattr(message, "id", None) for message in repaired_messages}
                results = []
                for ident, call in pending_calls.items():
                    message_id = f"{ident}:cancelled"
                    suffix = 1
                    while message_id in existing_ids:
                        suffix += 1
                        message_id = f"{ident}:cancelled:{suffix}"
                    existing_ids.add(message_id)
                    results.append(ToolMessage(
                        id=message_id,
                        tool_call_id=ident,
                        name=call["name"],
                        status="error",
                        content="Run cancelled before a tool result was recorded. Completion is unconfirmed; inspect state before retrying any action.",
                    ))
                # `messages` uses LangGraph's public add_messages reducer.
                # Replace the whole channel so the synthetic tool result stays
                # after the matching AI tool call even when abort races the
                # native stream's final checkpoint write.
                await agent.aupdate_state(
                    _invoke_config(run),
                    {"messages": [RemoveMessage(id=REMOVE_ALL_MESSAGES), *repaired_messages, *results]},
                )
                await self._alink_new_checkpoints(run, agent)
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
                state = await agent.aget_state(_invoke_config(run))
                values = getattr(state, "values", None)
                run.structured_output = update_structured_result_from_state(
                    run.structured_output,
                    values if isinstance(values, dict) else None,
                )
            except Exception as exc:  # noqa: BLE001 - state loss is diagnostic, not success.
                run.structured_output = mark_structured_failure(run.structured_output, str(exc))
        self._collect_related_files(run)

    def _checkpoint_head(self, thread_id: str) -> str | None:
        try:
            latest = next(iter(checkpoint_history(
                self.manager.paths.checkpoints_db,
                {"configurable": {"thread_id": thread_id, "checkpoint_ns": ""}},
                limit=1,
            )), None)
        except Exception as exc:  # noqa: BLE001 - cannot safely attribute older thread history
            raise HarnessError(
                f"The conversation checkpoint could not be read: {exc}",
                code="checkpoint_linkage_failed", status_code=409,
            ) from exc
        if latest is None:
            return None
        configurable = latest.config.get("configurable") if isinstance(latest.config, dict) else None
        checkpoint_id = configurable.get("checkpoint_id") if isinstance(configurable, dict) else None
        if not isinstance(checkpoint_id, str) or not checkpoint_id:
            raise HarnessError(
                "The conversation checkpoint has no identity.",
                code="checkpoint_linkage_failed", status_code=409,
            )
        return checkpoint_id

    async def _alink_new_checkpoints(self, run: AgentRun, agent: object) -> None:
        anchor = run.checkpoint_ids[0] if run.checkpoint_ids else run.pre_run_checkpoint_id
        try:
            added = await acheckpoint_ids_from_graph(agent, _invoke_config(run), stop_at_id=anchor)
        except ValueError as exc:
            run.events.append(AgentEvent(at=utc_now(), kind="checkpoint_linkage_failed",
                detail={"code": "checkpoint_anchor_missing", "message": str(exc)}))
            raise HarnessError(str(exc), code="checkpoint_linkage_failed", status_code=409) from exc
        run.checkpoint_ids = list(dict.fromkeys([*added, *run.checkpoint_ids]))

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

    def _record_file_change(self, run: AgentRun, mutation: Callable[[], None]) -> None:
        with self._lock:
            mutation()
            run.updated_at = utc_now()
            self._persist_and_notify(run)

    def _project_is_active(self, run: AgentRun) -> bool:
        if not run.project_path:
            return False
        root = Path(run.project_path).resolve()
        for other in self.list_runs():
            if not other.project_path or Path(other.project_path).resolve() != root:
                continue
            worker = self._threads.get(other.id)
            if is_run_lifecycle_live(other.status) or worker is not None and worker.is_alive():
                return True
        return False

    def file_changes(self, run_id: str) -> list[ProjectFileChangeView]:
        with self._lock:
            run = self._require_run(run_id)
            if not run.project_path:
                return []
            active = self._project_is_active(run)
            return [change_view(Path(run.project_path), change, run_active=active) for change in run.file_changes]

    def reverse_file_change(self, run_id: str, change_id: str) -> ProjectFileChangeView:
        with self._lock:
            run = self._require_run(run_id)
            change = next((item for item in run.file_changes if item.id == change_id), None)
            if change is None or not run.project_path:
                raise HarnessError("Unknown project file change.", code="file_change_missing", status_code=404)
            if self._project_is_active(run):
                raise HarnessError("Wait for work in this project to stop before reversing a file change.", code="file_reversal_active", status_code=409)
            try:
                reverse_change(Path(run.project_path), change)
            except OSError as exc:
                raise HarnessError(f"The file could not be restored: {exc}", code="file_reversal_failed", status_code=409) from exc
            change.reversed_at = utc_now()
            run.events.append(AgentEvent(at=change.reversed_at, kind="file_change_reversed",
                detail={"change_id": change.id, "path": change.path, "actor": "human"}))
            run.updated_at = change.reversed_at
            self._persist_and_notify(run)
            return change_view(Path(run.project_path), change, run_active=False)

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
        settled: list[AgentRun] = []
        retries: list[tuple[AgentRun, AgentRunStatus, str]] = []
        with self._lock:
            if self._startup_reconciled:
                return
            for run in self.store.list_runs():
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
            if live.generation_observation is not None and live.generation_observation.phase in {"prompt_processing", "generating"}:
                live.generation_observation = live.generation_observation.model_copy(update={
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
        sanitized = apply_run_diagnostic_policy(run, self._capture_settings())
        run.model_requests = sanitized.model_requests
        self.store.put_run(run.model_copy(deep=True))

    def _persist_and_notify(self, run: AgentRun, *, telemetry: bool = False) -> None:
        if not telemetry:
            self._persist(run)
        if run.id not in self._interaction_failure_runs or not is_run_lifecycle_live(run.status):
            self._observe_interaction(run, None, telemetry=telemetry)
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
    if len(decisions) == 1 and decisions[0].get("type") == "user_answer":
        return {key: value for key, value in decisions[0].items() if key != "type"}
    return {"decisions": decisions}


def _graph_checkpoint_snapshot(agent: Any, thread_id: str | None, checkpoint_id: str | None) -> Any:
    if not thread_id or not checkpoint_id:
        raise HarnessError(
            "The requested checkpoint identity is incomplete.",
            code="checkpoint_resume_missing",
            status_code=409,
        )
    try:
        snapshot = agent.get_state(
            {
                "configurable": {
                    "thread_id": thread_id,
                    "checkpoint_ns": "",
                    "checkpoint_id": checkpoint_id,
                }
            }
        )
    except Exception as exc:
        raise HarnessError(
            "The requested checkpoint could not be reconstructed by the agent graph.",
            code="checkpoint_resume_invalid",
            status_code=409,
        ) from exc
    if snapshot is None:
        raise HarnessError(
            "The requested checkpoint is unavailable.",
            code="checkpoint_resume_missing",
            status_code=409,
        )
    if getattr(snapshot, "values", None) is None:
        raise HarnessError(
            "The requested checkpoint has no reconstructed graph state.",
            code="checkpoint_resume_invalid",
            status_code=409,
        )
    return snapshot


class _CheckpointInspectionModel(BaseChatModel):
    """Inert model used only to compile Deep Agents for checkpoint reads."""

    @property
    def _llm_type(self) -> str:
        return "checkpoint-inspection"

    def bind_tools(self, _tools: list[Any], **_kwargs: Any) -> "_CheckpointInspectionModel":
        return self

    def _generate(
        self,
        _messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any = None,
        **_kwargs: Any,
    ) -> ChatResult:
        raise RuntimeError("Checkpoint inspection graph must not execute inference.")

    async def _agenerate(
        self,
        _messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any = None,
        **_kwargs: Any,
    ) -> ChatResult:
        raise RuntimeError("Checkpoint inspection graph must not execute inference.")


class _CheckpointInspectionVectorStore:
    def similarity_search(self, *_args: Any, **_kwargs: Any) -> Any:
        raise RuntimeError("Checkpoint inspection graph must not execute retrieval.")


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
