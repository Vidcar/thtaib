from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from deepagents import create_deep_agent
from deepagents.backends import StateBackend
from langchain.agents.middleware import HumanInTheLoopMiddleware, TodoListMiddleware
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import BaseMessage
from langchain_core.outputs import ChatResult

from workbench_backend.agents.context import (
    ContextObservation,
    SummaryDispatchModel,
    observe_payload,
    token_counter_for_model,
)
from workbench_backend.agents.execution_policy import ExecutionControl
from workbench_backend.agents.harness_backend import build_run_backend, harness_scratch_root
from workbench_backend.agents.harness_profile import ensure_ordinary_chat_profile
from workbench_backend.agents.host_shell import filesystem_permissions_for_run, interrupt_on_for_run
from workbench_backend.agents.memory_skills import (
    clear_derived_knowledge,
    configured_memory_middleware,
    official_agent_kwargs,
)
from workbench_backend.agents.middleware import WorkbenchHarnessMiddleware
from workbench_backend.agents.replay import FixtureBank
from workbench_backend.agents.schemas import AgentEvent, AgentRun, AgentRunStatus, GenerationObservation
from workbench_backend.agents.structured import response_format_for_run
from workbench_backend.agents.tool_disclosure import (
    COMPACT_DESCRIPTIONS,
    CapabilitySetupBoundary,
    DeferredToolCollection,
    LeanFilesystemMiddleware,
    LeanTodoListMiddleware,
    ToolDisclosureMiddleware,
    always_skill_dependencies,
    deferred_tools,
    has_input_policy,
)
from workbench_backend.agents.tools import memory_proposal_tool, tools_for_names
from workbench_backend.assets.capture_backend import CaptureBackend
from workbench_backend.assets.schemas import RetainedAssetListFilters, RetainedAssetOrigin
from workbench_backend.contracts.lifecycle import is_run_lifecycle_live
from workbench_backend.errors import HarnessError
from workbench_backend.inference.ids import utc_now
from workbench_backend.inference.telemetry import current_request_purpose
from workbench_backend.state.checkpointer import open_sqlite_checkpointer

def create_compiled_agent(
    service,
    run: AgentRun,
    http_sink: list[dict[str, Any]],
    fixture_bank: FixtureBank | None,
    *,
    inspection_only: bool = False,
    external_tools: list[Any] | None = None,
    execution_control: ExecutionControl | None = None,
    is_child: bool = False,
) -> Any:
    parts = SimpleNamespace()
    _probe_screenshot_reading(
        service, parts, run, inspection_only=inspection_only, execution_control=execution_control,
    )
    _bind_compiled_model(service, parts, run, http_sink, inspection_only=inspection_only)
    _bind_model_observers(service, parts, run, inspection_only=inspection_only)
    _assemble_compiled_tools(
        service, parts, run, inspection_only=inspection_only, external_tools=external_tools,
    )
    _bind_response_format(service, parts, run, inspection_only=inspection_only)
    return _compile_deep_agent(
        service,
        parts,
        run,
        http_sink,
        fixture_bank,
        inspection_only=inspection_only,
        external_tools=external_tools,
        is_child=is_child,
    )


def _probe_screenshot_reading(service, parts, run, *, inspection_only, execution_control):
    execution_control = execution_control or ExecutionControl(run, lambda: service._publish_control_update(run))
    knowledge_plan = service._knowledge_plan_for_run(run)
    always_skill_dependencies(run, knowledge_plan)
    visual_access = any(name in {"browser_take_screenshot", "desktop_screenshot"} for name in run.presented_tools)
    if not visual_access and run.capture_routes_enabled and "read_file" in run.presented_tools and service.assets is not None:
        session = service.assets.session_for_run(run)
        visual_access = bool(session and service.assets.list_assets(RetainedAssetListFilters(
            session_id=session.id, origin=RetainedAssetOrigin.capture)))
    if not inspection_only and run.capture_routes_enabled and visual_access and not deferred_tools(run):
        from workbench_backend.inference.capabilities import capability_support
        deployment = service.manager.ensure_deployment_ready(run.deployment_id)
        per_request = run.effective_setup.bags.per_request if run.effective_setup is not None else None
        statuses = [capability_support(deployment, name, per_request) for name in ("image", "tool_image")]
        needs_check = "untested" in statuses and not any(value in {"failed", "inconclusive"} for value in statuses)
        if needs_check and (deployment.server_props is None or deployment.server_props.modalities.get("vision") is not False):
            run.activity_phase = "checking_images"
            service._publish_control_update(run)
            with execution_control.model_dispatch(run, purpose="probe", resumable=False):
                service.prepare_screenshot_reading(run)
            execution_control.require_dispatch(run)
            run.activity_phase = "thinking"
            service._publish_control_update(run)

    parts.execution_control = execution_control
    parts.knowledge_plan = knowledge_plan


def _bind_compiled_model(service, parts, run, http_sink, *, inspection_only):
    import workbench_backend.agents.harness as harness_module
    execution_control = parts.execution_control
    knowledge_plan = parts.knowledge_plan

    model = _CheckpointInspectionModel() if inspection_only else service._model_factory(run, http_sink)
    media_profile = dict(model.profile) if isinstance(model.profile, dict) else {}
    agent_kwargs: dict[str, Any] = {}
    capture_backend = None
    image_inputs_allowed: bool | Any = False
    if service.assets is not None and run.capture_routes_enabled:
        session = service.assets.session_for_run(run)
        if session is not None:
            def images_allowed() -> bool:
                from workbench_backend.inference.adapter import image_model_profile
                deployment = service.manager.get_deployment(run.deployment_id)
                per_request = run.effective_setup.bags.per_request if run.effective_setup is not None else None
                profile = image_model_profile(deployment, per_request)
                return profile["image_inputs"] and profile["image_tool_message"]
            image_inputs_allowed = images_allowed
            capture_backend = CaptureBackend(service.assets, session.id,
                image_inputs_allowed=images_allowed)
    # A tool image must be retained before the graph checkpoint; runs with
    # no Chat asset owner cannot safely expose a raw image result.
    backend = build_run_backend(run, service.manager.paths, prepare_storage=not inspection_only,
        image_inputs_allowed=image_inputs_allowed, capture_backend=capture_backend,
        cancel_requested=lambda: (execution_control.root.status in {AgentRunStatus.cancel_requested, AgentRunStatus.cancelled}
            or bool((cancel_event := service._cancels.get(execution_control.root.id)) and cancel_event.is_set())))
    if backend is not None:
        agent_kwargs["backend"] = backend
        if not inspection_only:
            clear_derived_knowledge(harness_scratch_root(service.manager.paths, run.id if run.parent_run_id else run.thread_id or run.id))
            harness_module.materialize_onto_backend(backend, knowledge_plan)
    observed_deployment = service.manager.get_deployment(run.deployment_id)
    capacity = observed_deployment.server_props.n_ctx if observed_deployment.server_props else None
    capacity = capacity if type(capacity) is int and capacity > 0 else None
    observation = (run.context_observation or ContextObservation()).model_copy(update={
        "capacity_tokens": capacity,
        "capacity_source": "server_props.n_ctx" if capacity is not None else "unknown",
    })
    run.context_observation = observation
    # Override provider-name defaults; only observed runtime capacity is a fact.
    media_profile.pop("max_input_tokens", None)
    model.profile = {**media_profile, **({"max_input_tokens": capacity} if capacity is not None else {})}

    parts.model = model
    parts.agent_kwargs = agent_kwargs
    parts.capture_backend = capture_backend
    parts.backend = backend
    parts.observation = observation


def _bind_model_observers(service, parts, run, *, inspection_only):
    model = parts.model
    observation = parts.observation

    if not inspection_only and callable(getattr(model, "set_generation_observer", None)):
        latest_request_ids: dict[str, str] = {}

        def observe_generation(sample: dict[str, Any]) -> None:
            with service._lock:
                if not is_run_lifecycle_live(run.status) or run.finalization_phase is not None:
                    return
                purpose = sample.get("purpose", "work")
                latest_sample = model.latest_generation_sample(purpose=purpose) if callable(getattr(model, "latest_generation_sample", None)) else None
                if latest_sample is not None and sample.get("request_id") != latest_sample.get("request_id"):
                    return
                if sample.get("reset"):
                    latest_request_ids[purpose] = sample["request_id"]
                    if purpose == "work":
                        run.generation_observation = None
                    else:
                        run.housekeeping_generation.pop(purpose, None)
                elif sample["request_id"] == latest_request_ids.get(purpose):
                    if latest_sample is not None and sample != latest_sample:
                        return
                    measured = GenerationObservation(
                        **sample, context_limit=observation.capacity_tokens if observation else None,
                    )
                    if purpose == "work":
                        run.generation_observation = measured
                    else:
                        run.housekeeping_generation[purpose] = measured
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
                service._updates.notify_all()
            service._observe_interaction(telemetry_run, None, telemetry=True)

        model.set_generation_observer(observe_generation)
    if observation is not None and callable(getattr(model, "set_context_guard", None)):
        def guard(payload: dict[str, Any]) -> None:
            observed = observe_payload(observation, payload, native_counter=getattr(model, "count_input_tokens", None))
            run.activity_phase = "summarizing" if current_request_purpose() == "summary" else "thinking"
            if current_request_purpose() == "work":
                run.context_observation = observed
            else:
                run.housekeeping_context[current_request_purpose()] = observed
        model.set_context_guard(guard)


def _assemble_compiled_tools(service, parts, run, *, inspection_only, external_tools):
    knowledge_plan = parts.knowledge_plan
    backend = parts.backend
    agent_kwargs = parts.agent_kwargs

    agent_kwargs.update(official_agent_kwargs(knowledge_plan))
    permissions = filesystem_permissions_for_run(run)
    if permissions:
        agent_kwargs["permissions"] = permissions
    from workbench_backend.state.preferences import PreferenceStore
    interrupt_on = interrupt_on_for_run(run, PreferenceStore(service.store))
    if interrupt_on:
        agent_kwargs["interrupt_on"] = interrupt_on
    tools = [*tools_for_names(run.presented_tools), *(external_tools or [])]
    if not inspection_only:
        if service.preview is not None:
            tools.extend(tool for tool in service.preview.tools_for_run(run)
                if tool.name in run.presented_tools)
        if service.desktop_automation is not None and not has_input_policy(run):
            tools.extend(tool for tool in service.desktop_automation.tools_for_run(run)
                if tool.name in run.presented_tools)
    if "propose_memory" in run.presented_tools and service._knowledge_provider is not None:
        tools.append(memory_proposal_tool(run.id, service._knowledge_provider()))
    if "read_attachment" in run.presented_tools and run.retained_asset_ids:
        from workbench_backend.assets.tools import attachment_tool_for_run
        tools.append(attachment_tool_for_run(service.store, run))
    retrieval_tool = service._live_search_knowledge_tool(run, backend, inspection_only=inspection_only)
    if retrieval_tool is not None:
        tools = [*tools, retrieval_tool]

    parts.permissions = permissions
    parts.interrupt_on = interrupt_on
    parts.tools = tools


def _bind_response_format(service, parts, run, *, inspection_only):
    model = parts.model

    deployment = (service.manager.get_deployment(run.deployment_id) if inspection_only
                  else service.manager.ensure_deployment_ready(run.deployment_id))
    per_request = run.effective_setup.bags.per_request if run.effective_setup is not None else None
    response_format, structured_output = response_format_for_run(
        output_schema=run.output_schema,
        deployment=deployment,
        per_request=per_request,
        tools_presented=bool(run.presented_tools),
        tools_off=not run.presented_tools,
    )
    from langchain.agents.structured_output import OutputToolBinding, ProviderStrategy, ToolStrategy
    from langchain_core.utils.function_calling import convert_to_openai_tool
    provider_format = response_format.to_model_kwargs().get("response_format") if isinstance(response_format, ProviderStrategy) else None
    if provider_format is not None:
        # ProviderStrategy's schema must use the same public binding as
        # generation; already serialized request formats remain untouched.
        provider_format = model.bind_tools([], response_format=provider_format, strict=True).kwargs["response_format"]
    structured_tools = ([OutputToolBinding.from_schema_spec(spec).tool for spec in response_format.schema_specs]
        if isinstance(response_format, ToolStrategy) else [])
    count_tools_projection = (lambda selected: [convert_to_openai_tool(tool, strict=True) for tool in selected]) if provider_format else None

    parts.response_format = response_format
    parts.provider_format = provider_format
    parts.structured_tools = structured_tools
    parts.count_tools_projection = count_tools_projection
    parts.structured_output = structured_output


def _compile_deep_agent(service, parts, run, http_sink, fixture_bank, *, inspection_only, external_tools, is_child):
    import workbench_backend.agents.harness as harness_module
    from workbench_backend.state.preferences import PreferenceStore
    execution_control = parts.execution_control
    knowledge_plan = parts.knowledge_plan
    model = parts.model
    agent_kwargs = parts.agent_kwargs
    capture_backend = parts.capture_backend
    backend = parts.backend
    observation = parts.observation
    permissions = parts.permissions
    interrupt_on = parts.interrupt_on
    tools = parts.tools
    response_format = parts.response_format
    provider_format = parts.provider_format
    structured_tools = parts.structured_tools
    count_tools_projection = parts.count_tools_projection
    structured_output = parts.structured_output

    def prepare_tool_images():
        with execution_control.model_dispatch(run, purpose="probe"):
            return service.prepare_screenshot_reading(run, model=model)

    workbench_middleware = WorkbenchHarnessMiddleware(
        run, http_sink, settings_provider=service._capture_settings,
        fixture_bank=fixture_bank, execution_control=execution_control,
        asset_service=service.assets, capture_backend=capture_backend,
        tool_image_preparer=None if inspection_only else prepare_tool_images,
        generation_recorder=None if inspection_only else lambda: service._merge_latest_generation_sample(run),
    )
    native_approval = HumanInTheLoopMiddleware(interrupt_on or {}) if has_input_policy(run) else None
    def ensure_deferred_approval(name):
        if native_approval is None:
            return
        refreshed = HumanInTheLoopMiddleware(interrupt_on_for_run(run, PreferenceStore(service.store)) or {})
        native_approval.interrupt_on.update(refreshed.interrupt_on)
        external = {tool.name for connection in run.connection_snapshots if connection.kind == "mcp" for tool in connection.tools}
        if name in external and name not in native_approval.interrupt_on:
            raise HarnessError("This external tool has no frozen approval policy.", code="tool_approval_missing", status_code=409)
    disclosure = (ToolDisclosureMiddleware(run,
        loader=external_tools if isinstance(external_tools, DeferredToolCollection) else None,
        on_setup=None if inspection_only else CapabilitySetupBoundary(run, lambda: service._publish_control_update(run)),
        ensure_approval=ensure_deferred_approval) if has_input_policy(run) else None)
    if disclosure is not None:
        disclosure.reference_requirements = knowledge_plan.skill_requirements
        if "read_reference" in run.presented_tools:
            from workbench_backend.agents.memory_skills import reference_tool_for_plan
            reference_tool = reference_tool_for_plan(backend, knowledge_plan,
                allowed_tools=set(run.presented_tools), require_ready=disclosure.require_reference_ready)
            if reference_tool is not None:
                tools.append(reference_tool)
    def observe_summary(messages: list[BaseMessage]) -> None:
        run.activity_phase = "summarizing"
        if observation is not None:
            projection = getattr(model, "project_context_payload", None)
            if callable(projection):
                run.housekeeping_context["summary"] = observe_payload(observation, projection(messages),
                    native_counter=getattr(model, "count_input_tokens", None))

    summary_model = SummaryDispatchModel(delegate=model, profile=model.profile,
        dispatch=lambda: execution_control.model_dispatch(run, purpose="summary"), observer=observe_summary)
    summarization = harness_module.create_summarization_middleware(
        model=summary_model, backend=backend or StateBackend(),
        token_counter=token_counter_for_model(model, response_format=provider_format,
            message_projection=workbench_middleware.tool_image_messages_for_count,
            request_message_projection=workbench_middleware.browser_messages_for_count,
            extra_tools=structured_tools, tools_projection=count_tools_projection,
            request_settings={"tool_choice": "required"} if structured_tools else None),
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
    from workbench_backend.agents.memory_skills import configured_skills_middleware
    if run.helper_snapshots and "task" in run.presented_tools and not is_child:
        agent_kwargs["subagents"] = compiled_helpers(service, run, execution_control,
            inspection_only=inspection_only)
    from deepagents.middleware.subagents import SubAgentMiddleware
    lean_helpers = ([SubAgentMiddleware(backend=backend or StateBackend(), subagents=agent_kwargs["subagents"],
        task_description="Delegate a self-contained task with the needed context to a selected helper. Helpers retain this input's access bounds and cannot delegate further.\n{available_agents}")]
        if disclosure is not None and agent_kwargs.get("subagents") else [])
    return create_deep_agent(
        model=model,
        tools=tools,
        system_prompt=run.system_prompt,
        middleware=[
            LeanFilesystemMiddleware(disclosure=disclosure, request_preparer=workbench_middleware.prepare_context_request,
                backend=backend or StateBackend(), _permissions=permissions,
                **({"custom_tool_descriptions": COMPACT_DESCRIPTIONS} if disclosure is not None else {})),
            summarization,
            *configured_memory_middleware(backend, knowledge_plan),
            *configured_skills_middleware(backend, knowledge_plan),
            *lean_helpers,
            *([LeanTodoListMiddleware() if disclosure is not None else TodoListMiddleware()]
                if "write_todos" in run.presented_tools else []),
            *([review_middleware(run, model, http_sink, execution_control, service._capture_settings,
                lambda mutation=None: service._publish_control_update(run, mutation))] if run.review.enabled and not is_child else []),
            workbench_middleware,
            *([disclosure, native_approval] if disclosure is not None else []),
        ],
        name="workbench-embedded-harness",
        response_format=response_format,
        # A concrete saver preserves the task-qualified namespace. With
        # checkpointer=True LangGraph strips task IDs, merging parallel
        # helpers into the same "tools" checkpoint state.
        checkpointer=open_sqlite_checkpointer(service.manager.paths.checkpoints_db),
        **agent_kwargs,
    )


def graph_checkpoint_snapshot(agent: Any, thread_id: str | None, checkpoint_id: str | None) -> Any:
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


def screenshot_reading_available(manager, run: AgentRun) -> bool:
    """Read existing setup evidence without dispatching a capability probe.

    Handoff refresh happens while the whole graph is paused. Its optional
    image observation must not start model work behind that barrier.
    """

    from workbench_backend.inference.adapter import image_model_profile
    try:
        per_request = run.effective_setup.bags.per_request if run.effective_setup else None
        return bool(image_model_profile(manager.get_deployment(run.deployment_id), per_request).get("image_tool_message"))
    except Exception:
        return False


def prepare_screenshot_reading(manager, run: AgentRun, *, model: BaseChatModel | None = None) -> bool:
    """Prove screenshot delivery once for this loaded setup, then remember it."""

    from workbench_backend.inference.adapter import image_model_profile
    from workbench_backend.inference.probes import ensure_tool_image_support
    from workbench_backend.inference.telemetry import request_purpose

    per_request = run.effective_setup.bags.per_request if run.effective_setup is not None else None
    try:
        with request_purpose("probe"):
            ready = ensure_tool_image_support(manager, run.deployment_id, per_request)
        if model is not None:
            # The compiled agent predates this evidence. Refresh its actual
            # model before upstream filtering, preserving the context budget.
            model.profile = {**(model.profile or {}), **image_model_profile(
                manager.get_deployment(run.deployment_id), per_request,
            )}
        return ready
    except Exception:
        if model is not None:
            model.profile = {**(model.profile or {}), "image_inputs": False, "image_tool_message": False}
        return False
