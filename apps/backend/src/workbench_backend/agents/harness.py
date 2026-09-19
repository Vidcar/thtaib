"""AGT-001: embedded Deep Agents harness — start / observe / cancel.

Deep Agents owns the model/tool loop. LangGraph is only the compiled graph
returned by create_deep_agent — not a second Builder workflow editor.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

from deepagents import create_deep_agent
from deepagents.backends import FilesystemBackend
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, ToolMessage

from workbench_backend.agents.evidence import build_completion
from workbench_backend.agents.middleware import WorkbenchHarnessMiddleware
from workbench_backend.agents.schemas import (
    AgentEvent,
    AgentRun,
    AgentRunStatus,
    AgentStartRequest,
    TaskCriteria,
    ToolMode,
    label_for_tool_mode,
)
from workbench_backend.state.checkpointer import (
    checkpoint_ids_from_graph,
    open_sqlite_checkpointer,
)
from workbench_backend.state.schemas import RelatedFile
from workbench_backend.state.store import ApplicationStore
from workbench_backend.agents.tools import (
    enabled_catalogue,
    resolve_presented_tools,
    tools_for_names,
)
from workbench_backend.errors import HarnessError
from workbench_backend.inference.adapter import chat_model_for_deployment
from workbench_backend.inference.ids import new_id, utc_now
from workbench_backend.inference.service import ModelManager
from workbench_backend.knowledge.schemas import KnowledgeRefs
from workbench_backend.knowledge.service import KnowledgeService

DEFAULT_SYSTEM_PROMPT = (
    "You are the Local AI Workbench embedded harness. Use enabled tools when "
    "they help answer the task. Do not invent durable knowledge or retrieval. "
    "This is not Chat or Builder."
)

ModelFactory = Callable[[AgentRun, list[dict[str, Any]]], BaseChatModel]


class HarnessService:
    """Harness runs persist in application.sqlite. Recovery remainder is OQ-004."""

    def __init__(
        self,
        manager_provider: Callable[[], ModelManager],
        *,
        model_factory: ModelFactory | None = None,
        knowledge_provider: Callable[[], KnowledgeService] | None = None,
        app_store: ApplicationStore | None = None,
    ) -> None:
        self._manager_provider = manager_provider
        self._model_factory = model_factory or self._deployment_model
        self._knowledge_provider = knowledge_provider
        self._app_store = app_store
        self._runs: dict[str, AgentRun] = {}
        self._cancels: dict[str, threading.Event] = {}
        self._threads: dict[str, threading.Thread] = {}
        self._lock = threading.Lock()

    @property
    def store(self) -> ApplicationStore:
        if self._app_store is None:
            self._app_store = ApplicationStore(self.manager.paths)
        return self._app_store

    @property
    def manager(self) -> ModelManager:
        return self._manager_provider()

    def list_runs(self) -> list[AgentRun]:
        stored = {item.id: item for item in self.store.list_runs()}
        with self._lock:
            for run in self._runs.values():
                stored[run.id] = run.model_copy(deep=True)
        return list(stored.values())

    def get_run(self, run_id: str) -> AgentRun:
        with self._lock:
            run = self._runs.get(run_id)
            if run is not None:
                return run.model_copy(deep=True)
        stored = self.store.get_run(run_id)
        if stored is None:
            raise HarnessError("Unknown agent run", code="run_missing", status_code=404)
        with self._lock:
            self._runs.setdefault(run_id, stored)
        return stored.model_copy(deep=True)

    def active_workspace_run_ids(self, workspace_id: str) -> list[str]:
        """Runs still writing or executing against a workspace (quiescent check)."""

        with self._lock:
            return [
                run.id
                for run in self._runs.values()
                if run.workspace_id == workspace_id
                and run.status in {AgentRunStatus.queued, AgentRunStatus.running}
            ]

    def start(self, request: AgentStartRequest) -> AgentRun:
        deployment = self.manager.get_deployment(request.deployment_id)
        if not deployment.endpoint:
            raise HarnessError(
                "Deployment has no endpoint. The adapter does not start inference.",
                code="no_endpoint",
                status_code=409,
            )
        presented, denied = resolve_presented_tools(request.presented_tools)
        if denied:
            raise HarnessError(
                f"Tools are not in the enabled catalogue: {', '.join(denied)}",
                code="tool_denied",
                status_code=400,
            )
        if not presented:
            raise HarnessError(
                "At least one enabled tool must remain presented (AGT-005).",
                code="tools_required",
                status_code=400,
            )
        if request.tool_mode is ToolMode.recorded_tool and not request.recorded_fixtures:
            raise HarnessError(
                "recorded-tool mode requires fixtures; it is not a live integration.",
                code="recorded_fixtures_required",
                status_code=400,
            )
        refs = self._resolve_knowledge_refs(request)
        if request.profile_id:
            self.manager.get_profile(request.profile_id)
        project_path = _resolved_project_path(request.project_path)
        now = utc_now()
        run = AgentRun(
            id=new_id("agent"),
            status=AgentRunStatus.queued,
            deployment_id=deployment.id,
            task=request.task,
            enabled_tools=enabled_catalogue(),
            presented_tools=presented,
            denied_tools=[],
            system_prompt=request.system_prompt or DEFAULT_SYSTEM_PROMPT,
            criteria=request.criteria or TaskCriteria(),
            budgets=request.budgets,
            created_at=now,
            updated_at=now,
            workspace_id=request.workspace_id,
            project_path=project_path,
            profile_id=request.profile_id,
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
            thread_id=None,
            related_files=_initial_related_files(project_path),
        )
        run.thread_id = run.id
        cancel = threading.Event()
        with self._lock:
            self._runs[run.id] = run
            self._cancels[run.id] = cancel
        self._persist(run)
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
            threads = list(self._threads.values())
        for thread in threads:
            thread.join(timeout=timeout)
        with self._lock:
            self._threads.clear()

    def cancel(self, run_id: str) -> AgentRun:
        with self._lock:
            run = self._runs.get(run_id)
            if run is None:
                raise HarnessError("Unknown agent run", code="run_missing", status_code=404)
            cancel = self._cancels.get(run_id)
            if cancel is not None:
                cancel.set()
            if run.status in {AgentRunStatus.queued, AgentRunStatus.running}:
                run.status = AgentRunStatus.cancelled
                run.stop_reason = "cancelled"
                run.updated_at = utc_now()
                run.events.append(
                    AgentEvent(at=run.updated_at, kind="cancelled", detail={"requested": True})
                )
                self._persist(run)
            return run.model_copy(deep=True)

    def _execute(self, run_id: str) -> None:
        with self._lock:
            run = self._runs[run_id]
            cancel = self._cancels[run_id]
            if cancel.is_set() or run.status == AgentRunStatus.cancelled:
                return
            run.status = AgentRunStatus.running
            run.updated_at = utc_now()
            run.events.append(AgentEvent(at=run.updated_at, kind="started", detail={}))
        http_sink: list[dict[str, Any]] = []
        agent = None
        try:
            model = self._model_factory(run, http_sink)
            fixtures = run.recorded_fixtures if run.tool_mode is ToolMode.recorded_tool else None
            agent_kwargs: dict[str, Any] = {}
            backend = _project_backend(run)
            if backend is not None:
                agent_kwargs["backend"] = backend
            agent = create_deep_agent(
                model=model,
                tools=tools_for_names(run.presented_tools, recorded_fixtures=fixtures),
                system_prompt=run.system_prompt,
                middleware=[WorkbenchHarnessMiddleware(run, http_sink)],
                name="workbench-embedded-harness",
                checkpointer=open_sqlite_checkpointer(self.manager.paths.checkpoints_db),
                **agent_kwargs,
            )
            config = _invoke_config(run)
            for chunk in agent.stream(
                {"messages": [{"role": "user", "content": run.task}]},
                config=config,
                stream_mode="updates",
            ):
                if cancel.is_set():
                    self._link_run(run, agent)
                    self._finish(run, AgentRunStatus.cancelled, "cancelled")
                    return
                self._ingest_stream(run, chunk)
            run.completion = build_completion(run)
            self._link_run(run, agent)
            self._finish(run, AgentRunStatus.completed, "completed")
        except Exception as exc:  # noqa: BLE001 - surface harness failure, do not invent success
            if agent is not None:
                self._link_run(run, agent)
            else:
                self._collect_related_files(run)
            if cancel.is_set():
                self._finish(run, AgentRunStatus.cancelled, "cancelled")
                return
            run.error = str(exc)
            self._finish(run, AgentRunStatus.failed, "failed")

    def _finish(self, run: AgentRun, status: AgentRunStatus, stop_reason: str) -> None:
        with self._lock:
            if run.status == AgentRunStatus.cancelled and status != AgentRunStatus.cancelled:
                run.stop_reason = "cancelled"
                run.finished_at = run.finished_at or utc_now()
                run.updated_at = run.finished_at
                self._persist(run)
                return
            run.status = status
            run.stop_reason = stop_reason
            run.finished_at = utc_now()
            run.updated_at = run.finished_at
            run.events.append(
                AgentEvent(
                    at=run.updated_at,
                    kind=status.value,
                    detail={"stop_reason": stop_reason, "error": run.error},
                )
            )
            self._persist(run)

    def _ingest_stream(self, run: AgentRun, chunk: Any) -> None:
        if not isinstance(chunk, dict):
            return
        for node, update in chunk.items():
            messages = update.get("messages") if isinstance(update, dict) else None
            if not messages:
                continue
            for message in messages:
                self._ingest_message(run, message, str(node))

    def _ingest_message(self, run: AgentRun, message: BaseMessage | Any, node: str) -> None:
        now = utc_now()
        if isinstance(message, AIMessage) and message.tool_calls:
            for call in message.tool_calls:
                name = call.get("name") if isinstance(call, dict) else getattr(call, "name", None)
                args = call.get("args") if isinstance(call, dict) else getattr(call, "args", {})
                call_id = call.get("id") if isinstance(call, dict) else getattr(call, "id", None)
                invocation = {"name": name, "args": args, "id": call_id, "node": node}
                run.tool_invocations.append(invocation)
                run.events.append(AgentEvent(at=now, kind="tool_call", detail=invocation))
            return
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
            return
        if isinstance(message, AIMessage) and message.content:
            run.events.append(
                AgentEvent(
                    at=now,
                    kind="assistant_message",
                    detail={"content": message.content, "node": node},
                )
            )
        run.updated_at = now

    def _deployment_model(self, run: AgentRun, http_sink: list[dict[str, Any]]) -> BaseChatModel:
        deployment = self.manager.get_deployment(run.deployment_id)
        return chat_model_for_deployment(deployment, capture_sink=http_sink)

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

    def _link_run(self, run: AgentRun, agent: object) -> None:
        """Record checkpoint ids and related files in application records only."""

        run.checkpoint_ids = checkpoint_ids_from_graph(agent, _invoke_config(run))
        self._collect_related_files(run)

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

    def _persist(self, run: AgentRun) -> None:
        self.store.put_run(run.model_copy(deep=True))


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


def _project_backend(run: AgentRun) -> FilesystemBackend | None:
    """Bind Deep Agents file tools to project storage (STATE-002)."""

    if not run.project_path:
        return None
    return FilesystemBackend(root_dir=run.project_path, virtual_mode=True)


def _invoke_config(run: AgentRun) -> dict[str, Any]:
    """Thread id is required so LangGraph can write checkpoints.sqlite."""

    config: dict[str, Any] = {"configurable": {"thread_id": run.thread_id or run.id}}
    if run.budgets is not None and run.budgets.max_steps is not None:
        config["recursion_limit"] = run.budgets.max_steps
    return config


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
        resolved = (root / relative.lstrip("/")).resolve()
        files.append(RelatedFile(path=str(resolved), kind="written_file"))
    return files
