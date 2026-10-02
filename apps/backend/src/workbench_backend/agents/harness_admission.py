from __future__ import annotations

import sys
import threading
from pathlib import Path
from types import SimpleNamespace

from deepagents.middleware.summarization import SUMMARIZATION_EVENT_KEY, SummarizationMiddleware
from langchain_core.messages import HumanMessage, SystemMessage

from workbench_backend.agents.context import observe_context, validate_retained_messages
from workbench_backend.agents.effective_setup import resolve_effective_setup
from workbench_backend.agents.execution_policy import PLAN_INSTRUCTIONS, require_setup_capabilities
from workbench_backend.agents.harness_backend import canonical_root
from workbench_backend.agents.harness_presentation import (
    apply_automatic_read_paths,
    apply_disclosure_and_plan_filter,
    apply_filesystem_shell_gates,
    load_connection_snapshots,
    resolve_capture_routes,
    resolve_catalogue_and_retrieval,
    validate_required_presentation,
)
from workbench_backend.agents.helpers import (
    freeze_helpers,
    freeze_settings,
    prepare_frozen_model,
    require_accepted_model_identity,
)
from workbench_backend.agents.host_shell import approval_mode_instructions
from workbench_backend.agents.input_sources import WORKBENCH_CORE_INSTRUCTIONS
from workbench_backend.agents.memory_skills import plan_knowledge_materialization
from workbench_backend.agents.retrieval import (
    RETRIEVAL_INSTRUCTIONS,
    SEARCH_KNOWLEDGE_TOOL_NAME,
)
from workbench_backend.agents.schemas import (
    AgentEvent,
    AgentRun,
    AgentRunStatus,
    AgentStartRequest,
    HostShellFacts,
    ReviewObservation,
    TaskCriteria,
    ToolMode,
    label_for_tool_mode,
)
from workbench_backend.agents.setup_schemas import (
    FrozenExecutionSelection,
    FrozenHelperSelection,
    InstructionLayer,
    ProjectCreateRequest,
    ReviewConfiguration,
)
from workbench_backend.agents.setup_service import (
    SetupService,
    cleared_configuration_fields,
    configuration_from_request,
)
from workbench_backend.agents.structured import response_format_for_run
from workbench_backend.agents.tool_disclosure import deferred_tools, discovery_context
from workbench_backend.agents.tools import (
    enabled_for_project,
    tools_for_names,
)
from workbench_backend.errors import HarnessError
from workbench_backend.inference.ids import new_id, utc_now
from workbench_backend.inference.schemas import SettingsBags
from workbench_backend.inference.user_content import user_message_content
from workbench_backend.lab.store import LabStore
from workbench_backend.state.checkpointer import (
    CheckpointReadError,
    checkpoint_head_id,
    conversation_state,
)

def start_admitted(
    service,
    request: AgentStartRequest,
    *,
    instruction_snapshot: list[InstructionLayer] | None = None,
    helper_snapshot: list[FrozenHelperSelection] | None = None,
    execution_snapshot: FrozenExecutionSelection | None = None,
) -> AgentRun:
    admitted = SimpleNamespace()
    _resolve_frozen_admission(
        service,
        admitted,
        request,
        instruction_snapshot=instruction_snapshot,
        helper_snapshot=helper_snapshot,
        execution_snapshot=execution_snapshot,
    )
    request = admitted.request
    accepted_settings = admitted.accepted_settings
    admission = service.manager.reserve_deployment(
        request.deployment_id,
        profile_id=request.profile_id,
    )
    admission.__enter__()
    try:
        deployment = service.manager.ensure_deployment_ready(request.deployment_id)
        require_accepted_model_identity(deployment, accepted_settings)
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
        admitted.deployment = deployment
        _load_admitted_knowledge(service, admitted, execution_snapshot)
        _resolve_admitted_presentation(service, admitted, execution_snapshot)
        _compose_admitted_setup(service, admitted, execution_snapshot)
        _validate_admitted_history(service, admitted)
        run = _persist_admitted_run(service, admitted)
    except BaseException:
        admission.__exit__(*sys.exc_info())
        raise
    admission.__exit__(None, None, None)
    thread = threading.Thread(target=service._execute, args=(run.id,), daemon=True)
    with service._lock:
        service._threads[run.id] = thread
    thread.start()
    return service._expose_run(run)


def _resolve_frozen_admission(service, admitted, request, *, instruction_snapshot, helper_snapshot, execution_snapshot):
    service._reconcile_startup_once()
    selection_service = SetupService(service.store, service.manager, service._knowledge_provider() if service._knowledge_provider else None,
        connection_available=service.connections.available, connection_exists=service.connections.exists,
        connection_tools=lambda ident: [tool.name for tool in service.connections.tool_definitions(ident)],
        connection_tool_definitions=service.connections.tool_definitions)
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
        issues = selection_service.dependencies(selection.configuration, frozen=True,
            connection_snapshots=execution_snapshot.connection_snapshots,
            project_bound=bool(request.project_path or request.project_id))
        if issues:
            raise HarnessError("The queued setup has unavailable dependencies. Edit its selections before running.", code="setup_dependencies_missing", status_code=409,
                details={"missing_dependencies": [item.model_dump() for item in issues]})
    if instruction_snapshot is not None:
        selection = selection.model_copy(update={"instruction_layers": instruction_snapshot})
    from workbench_backend.agents.setup_schemas import AgentInputPolicy
    input_policy = (selection.configuration.input_policy if execution_snapshot is not None
        else selection.configuration.input_policy or AgentInputPolicy())
    request = request.model_copy(update={"input_policy": input_policy})
    # The canonical policy above is already typed. model_copy does not validate
    # updates, so including its serialized dictionary here would erase that
    # type before desktop pinned-capability readiness is checked.
    selected = selection.configuration.model_dump(exclude_none=True, exclude={"instructions", "requires_project", "requires_host_shell", "bundle_id", "input_policy"})
    if execution_snapshot is not None:
        # A queued turn cannot broaden live-desktop access beyond its frozen setup.
        selected["desktop_access"] = selection.configuration.desktop_access or "off"
    if selection.configuration.review is not None:
        selected["review"] = selection.configuration.review
    if request.project_id:
        project = selection_service.get_project(request.project_id, require_active=True)
        workspace = LabStore(service.manager.paths).get_workspace(request.workspace_id) if request.workspace_id else None
        # A checkpoint branch keeps its original project identity/defaults,
        # while its files live in the separately registered restored copy.
        execution_path = workspace.path if workspace is not None and workspace.origin == "restored" else project.path
        if request.project_path and canonical_root(request.project_path) != canonical_root(execution_path):
            raise HarnessError("The folder does not match the selected project.", code="project_mismatch", status_code=409)
        selected["project_path"] = execution_path
    request = request.model_copy(update=selected)
    if request.criteria and request.criteria.review_prompt and not request.review.enabled:
        request = request.model_copy(update={"review": ReviewConfiguration(enabled=True, criteria=request.criteria.review_prompt)})
    helpers = helper_snapshot if helper_snapshot is not None else freeze_helpers(selection_service,
        request.helper_agent_ids, project_id=request.project_id, parent_configuration=selection.configuration,
        connection_snapshot=service.connections.snapshot)
    if helper_snapshot is not None and set(request.helper_agent_ids) != {item.agent_id for item in helper_snapshot}:
        raise HarnessError("The frozen helper selection does not match this queued turn.", code="helper_snapshot_mismatch", status_code=409)
    if not request.deployment_id:
        raise HarnessError("Choose a model or an agent setup with a model.", code="setup_deployment_required", status_code=400)
    # Lab/direct executions also capture response policy before a cold load
    # can wait. Chat supplies its already-persisted admission snapshot.
    with service.manager.store.configuration_lock():
        accepted_settings = SettingsBags.model_validate(execution_snapshot.settings if execution_snapshot is not None
            else freeze_settings(service.manager, selection.configuration))
        prepared = prepare_frozen_model(service.manager, selection.configuration, accepted_settings)
        selection = selection.model_copy(update={"configuration": prepared})
        request = request.model_copy(update={"deployment_id": prepared.deployment_id})
        helpers = [helper.model_copy(update={"configuration": prepare_frozen_model(service.manager,
            helper.configuration, helper.settings_snapshot)}) if helper.settings_snapshot else helper for helper in helpers]
    require_setup_capabilities(selection.configuration,
        project_bound=bool(request.project_path or request.workspace_id), presented_tools=request.presented_tools)

    admitted.request = request
    admitted.selection = selection
    admitted.input_policy = input_policy
    admitted.helpers = helpers
    admitted.accepted_settings = accepted_settings


def _load_admitted_knowledge(service, admitted, execution_snapshot):
    import workbench_backend.agents.harness as harness_module
    request = admitted.request
    input_policy = admitted.input_policy

    refs = service._resolve_knowledge_refs(request, frozen=execution_snapshot is not None)
    versions = service._load_knowledge_versions(refs)
    from workbench_backend.agents.memory_skills import memory_selection_notice
    # The native memory middleware derives the same model-only notice.
    # Preserve the exact submitted input in run records and graph state.
    model_content_blocks = [*(request.content_blocks or []), *([memory_selection_notice(refs.memory_version_refs)] if input_policy is None else [])]
    knowledge_plan = plan_knowledge_materialization(
        versions,
        resource_loader=service._knowledge_provider().resource_bytes if service._knowledge_provider else None,
        input_policy=input_policy,
    )
    profile = None
    project_path = harness_module._resolved_project_path(request.project_path)
    if project_path is None and request.workspace_id:
        stored = LabStore(service.manager.paths).get_workspace(request.workspace_id)
        if stored is not None:
            project_path = harness_module._resolved_project_path(stored.path)
    from workbench_backend.assets.tools import validate_retained_selection
    validate_retained_selection(service.store, request.retained_asset_ids,
        thread_id=request.thread_id, project_path=str(project_path) if project_path else None)

    admitted.refs = refs
    admitted.versions = versions
    admitted.model_content_blocks = model_content_blocks
    admitted.knowledge_plan = knowledge_plan
    admitted.profile = profile
    admitted.project_path = project_path


def _resolve_admitted_presentation(service, admitted, execution_snapshot):
    request = admitted.request
    input_policy = admitted.input_policy
    helpers = admitted.helpers
    project_path = admitted.project_path
    knowledge_plan = admitted.knowledge_plan

    connection_snapshots, external_names = load_connection_snapshots(
        service, request, input_policy, execution_snapshot,
    )
    capture_session, capture_routes = resolve_capture_routes(service, request)
    (
        presented,
        filesystem_blocked,
        shell_blocked,
        retrieval_requested,
        recorded,
        embedding_deployment,
        retrieval_documents,
        retrieval_presented,
    ) = resolve_catalogue_and_retrieval(
        service, request, project_path, knowledge_plan, capture_routes, external_names,
    )
    presented = apply_filesystem_shell_gates(
        input_policy, presented, filesystem_blocked, shell_blocked,
    )
    presented, framework_read_paths = apply_automatic_read_paths(
        request, knowledge_plan, presented, retrieval_presented, capture_routes, recorded,
    )
    presented = apply_disclosure_and_plan_filter(
        request, input_policy, helpers, knowledge_plan, presented, connection_snapshots,
    )
    required_tools = validate_required_presentation(
        service, request, input_policy, knowledge_plan, project_path,
        connection_snapshots, presented, framework_read_paths, filesystem_blocked, shell_blocked,
    )

    admitted.connection_snapshots = connection_snapshots
    admitted.capture_session = capture_session
    admitted.capture_routes = capture_routes
    admitted.presented = presented
    admitted.external_names = external_names
    admitted.embedding_deployment = embedding_deployment
    admitted.retrieval_documents = retrieval_documents
    admitted.retrieval_requested = retrieval_requested
    admitted.retrieval_presented = retrieval_presented
    admitted.framework_read_paths = framework_read_paths
    admitted.required_tools = required_tools


def desktop_scope_snapshot(
    desktop_automation, request: AgentStartRequest, presented: list[str], *, essential_tools=(),
) -> tuple[str, dict[str, int | float] | None]:
    """Freeze the narrower live conversation grant at turn admission."""

    from workbench_backend.desktop_automation.service import DESKTOP_TOOL_NAMES, DesktopAutomationError
    from workbench_backend.desktop_automation.runtime import WinAppRuntimeError

    if not set(presented).intersection(DESKTOP_TOOL_NAMES):
        return "off", None
    if str(request.desktop_access) == "all":
        raise HarnessError("One window does not grant every window.", code="desktop_invalid_arguments", status_code=409)
    essential = set(essential_tools) | (set(request.input_policy.pinned_tools) if request.input_policy is not None else set())
    desktop_essential = bool(essential.intersection(DESKTOP_TOOL_NAMES))
    if (desktop_automation is None or request.source_surface != "chat"
        or not request.thread_id or request.work_mode != "work"
        or request.tool_mode is not ToolMode.live_tool):
        if deferred_tools(request) and not desktop_essential and request.source_surface == "chat" and request.thread_id:
            return _deferred_window_access(request), None
        raise HarnessError("Window tools need a live Work-mode Chat conversation.",
            code="desktop_grant_required", status_code=409)
    try:
        if desktop_essential:
            desktop_automation.runtime.command_path()
        _current, identity = desktop_automation.snapshot_grant(request.thread_id, request.desktop_access)
    except (DesktopAutomationError, WinAppRuntimeError) as exc:
        if deferred_tools(request) and not desktop_essential:
            return _deferred_window_access(request), None
        raise HarnessError(str(exc), code=exc.code if isinstance(exc, DesktopAutomationError) else "desktop_runtime_unavailable", status_code=409) from exc
    if identity is not None:
        return "selected", {
            "hwnd": identity.hwnd,
            "process_id": identity.process_id,
            "process_created_at": identity.process_created_at,
        }
    if str(request.desktop_access) == "selected":
        return "selected", None
    return "off", None


def _deferred_window_access(request: AgentStartRequest) -> str:
    access = str(request.desktop_access)
    return "off" if access == "all" else access


def validate_content_capabilities(deployment, request: AgentStartRequest, per_request) -> None:
    has_image = any(getattr(block, "type", None) == "image_url" for block in request.content_blocks or [])
    if not has_image:
        return
    from workbench_backend.inference.capabilities import capability_support
    props = deployment.server_props
    if props is not None and props.modalities.get("vision") is False:
        raise HarnessError(
            "This setup reports that image input is not supported.",
            code="image_input_unavailable",
            status_code=409,
            details={"constraint": "server_props.modalities.vision=false"},
        )
    support = capability_support(deployment, "image", per_request)
    if support != "passed":
        raise HarnessError(
            "Image input needs a passing image probe for this exact model setup. Text tasks remain available.",
            code="image_input_unverified" if support in {"untested", "inconclusive"} else "image_input_unavailable",
            status_code=409,
            details={"probe_status": support},
        )


def _compose_admitted_setup(service, admitted, execution_snapshot):
    import workbench_backend.agents.harness as harness_module
    request = admitted.request
    selection = admitted.selection
    input_policy = admitted.input_policy
    helpers = admitted.helpers
    accepted_settings = admitted.accepted_settings
    deployment = admitted.deployment
    refs = admitted.refs
    versions = admitted.versions
    knowledge_plan = admitted.knowledge_plan
    profile = admitted.profile
    project_path = admitted.project_path
    connection_snapshots = admitted.connection_snapshots
    capture_routes = admitted.capture_routes
    presented = admitted.presented
    external_names = admitted.external_names
    embedding_deployment = admitted.embedding_deployment
    retrieval_documents = admitted.retrieval_documents
    retrieval_requested = admitted.retrieval_requested
    retrieval_presented = admitted.retrieval_presented
    framework_read_paths = admitted.framework_read_paths
    required_tools = admitted.required_tools

    desktop_scope, desktop_window = desktop_scope_snapshot(
        service.desktop_automation, request, presented, essential_tools=required_tools,
    )
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
    if presented and deployment.server_props and (
        deployment.server_props.chat_template_caps.get("supports_tools") is False
        or deployment.server_props.chat_template_caps.get("supports_tool_calls") is False
    ):
        raise HarnessError("This setup reports that task tools are unsupported. Turn tools off or select a compatible setup.", code="tools_unsupported", status_code=409)
    enabled = enabled_for_project(
        project_path is not None,
        knowledge_routes=knowledge_plan.has_knowledge_routes,
        capture_routes=capture_routes,
        attachment_available=bool(request.retained_asset_ids),
    )
    enabled = [*enabled, *external_names]
    enabled.extend(name for name in presented if name not in enabled)
    if helpers and request.presented_tools != [] and "task" not in enabled:
        enabled.append("task")
    if framework_read_paths and "read_file" not in enabled:
        enabled.append("read_file")
    if retrieval_presented and SEARCH_KNOWLEDGE_TOOL_NAME not in enabled:
        enabled = [*enabled, SEARCH_KNOWLEDGE_TOOL_NAME]
    setup = resolve_effective_setup(
        deployment=deployment.model_copy(update={"settings": accepted_settings}),
        profile=profile,
        per_request_overrides=None,
        startup_overrides=None,
        knowledge_refs=refs,
        knowledge_versions=versions,
        surface_system_prompt=request.system_prompt,
        default_system_prompt=harness_module.DEFAULT_SYSTEM_PROMPT if input_policy is None else WORKBENCH_CORE_INSTRUCTIONS,
        embedding_deployment=embedding_deployment,
        selected_embedding_deployment_id=request.embedding_deployment_id,
        retrieval_requested=retrieval_requested,
        retrieval_presented=retrieval_presented,
        retrieval_corpus_documents=len(retrieval_documents),
        retrieval_instructions=RETRIEVAL_INSTRUCTIONS if retrieval_presented else None,
        materialized_knowledge=knowledge_plan.facts,
        inherit_deployment_settings=True,
        instruction_layers=selection.instruction_layers,
        selected_project_id=selection.project_id,
        selected_agent_setup_id=selection.agent_setup_id,
        selected_agent_setup_version_id=selection.agent_setup_version_id,
        selected_connection_ids=request.connection_ids,
        input_policy=input_policy,
        input_sources=selection.input_sources if selection.input_sources else None,
    )
    if execution_snapshot is not None:
        setup.selected_profile_id = request.profile_id
        # Admission already resolved response defaults and chat choices.
        # Do not let the resident child's originating setup resolve them
        # again, and do not consult the now-editable saved revision.
        setup.bags.per_request = SettingsBags.model_validate(execution_snapshot.settings).per_request
        if setup.startup_mismatches:
            raise HarnessError("This queued turn needs different loaded model settings. Reload the model or edit this turn before retrying.", code="model_reload_required", status_code=409)
    else:
        setup.selected_profile_id = request.profile_id
        setup.bags.per_request = accepted_settings.per_request
    setup.system_prompt = "\n\n".join((setup.system_prompt, approval_mode_instructions(request.approval_mode, compact=input_policy is not None)))
    if request.work_mode == "plan":
        setup.system_prompt += "\n\n" + PLAN_INSTRUCTIONS
    if execution_snapshot is not None and execution_snapshot.system_prompt is not None:
        setup.system_prompt = execution_snapshot.system_prompt
    from workbench_backend.agents.memory_skills import reference_context
    selected_reference_context = reference_context(knowledge_plan)
    if selected_reference_context and selected_reference_context not in setup.system_prompt:
        setup.system_prompt += "\n\n" + selected_reference_context
    guidance = discovery_context(SimpleNamespace(input_policy=input_policy, presented_tools=presented,
        work_mode=request.work_mode, framework_read_paths=framework_read_paths, connection_snapshots=connection_snapshots))
    if guidance and guidance not in setup.system_prompt:
        setup.system_prompt += "\n\n" + guidance
    if request.content_blocks:
        validate_content_capabilities(deployment, request, setup.bags.per_request)
    _, structured_output = response_format_for_run(
        output_schema=request.output_schema,
        deployment=deployment,
        per_request=setup.bags.per_request,
        tools_presented=bool(presented),
        tools_off=request.presented_tools == [],
    )

    admitted.desktop_scope = desktop_scope
    admitted.desktop_window = desktop_window
    admitted.enabled = enabled
    admitted.setup = setup
    admitted.structured_output = structured_output


def _validate_admitted_history(service, admitted):
    import workbench_backend.agents.harness as harness_module
    request = admitted.request
    selection = admitted.selection
    input_policy = admitted.input_policy
    deployment = admitted.deployment
    refs = admitted.refs
    model_content_blocks = admitted.model_content_blocks
    project_path = admitted.project_path
    connection_snapshots = admitted.connection_snapshots
    capture_session = admitted.capture_session
    presented = admitted.presented
    framework_read_paths = admitted.framework_read_paths
    desktop_scope = admitted.desktop_scope
    desktop_window = admitted.desktop_window
    enabled = admitted.enabled
    setup = admitted.setup
    structured_output = admitted.structured_output

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
            desktop_access=desktop_scope,
            desktop_window=desktop_window,
            capture_routes_enabled=capture_session is not None and request.tool_mode is ToolMode.live_tool,
            task=request.task,
            content_blocks=request.content_blocks,
            enabled_tools=enabled,
            presented_tools=presented,
            input_policy=input_policy,
            input_sources=setup.input_sources,
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
            related_files=harness_module._initial_related_files(project_path),
            effective_setup=setup,
            host_shell=HostShellFacts(
                available=False,
                cwd=project_path,
            ),
            output_schema=request.output_schema,
            structured_output=structured_output,
        )
        from workbench_backend.agents.harness_compile import graph_checkpoint_snapshot
        validation_agent = service._create_compiled_agent(validation_run, [], None, inspection_only=True)
        snapshot = graph_checkpoint_snapshot(
            validation_agent,
            request.thread_id,
            request.resume_checkpoint_id,
        )
        saved_state = dict(snapshot.values)
    else:
        saved_state = conversation_state(service.manager.paths.checkpoints_db, request.thread_id) if request.thread_id else {}
    retained = list(saved_state.get("messages", []))
    # Use the installed upstream reconstruction, not a second history reducer.
    retained = SummarizationMiddleware._apply_event_to_messages(retained, saved_state.get(SUMMARIZATION_EVENT_KEY))
    validation_messages = [SystemMessage(content=setup.system_prompt), *retained]
    if not request.resume_checkpoint_id:
        validation_messages.append(HumanMessage(content=user_message_content(request.task, model_content_blocks)))
    validate_retained_messages(deployment, validation_messages, allow_recovery=not request.resume_checkpoint_id)
    context_observation = observe_context(
        deployment=deployment,
        per_request=setup.bags.per_request,
        system_prompt=setup.system_prompt,
        task="" if request.resume_checkpoint_id else request.task,
        content_blocks=None if request.resume_checkpoint_id else model_content_blocks,
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

    admitted.context_observation = context_observation


def _persist_admitted_run(service, admitted):
    import workbench_backend.agents.harness as harness_module
    request = admitted.request
    selection = admitted.selection
    input_policy = admitted.input_policy
    helpers = admitted.helpers
    deployment = admitted.deployment
    refs = admitted.refs
    project_path = admitted.project_path
    connection_snapshots = admitted.connection_snapshots
    capture_session = admitted.capture_session
    presented = admitted.presented
    framework_read_paths = admitted.framework_read_paths
    desktop_scope = admitted.desktop_scope
    desktop_window = admitted.desktop_window
    enabled = admitted.enabled
    setup = admitted.setup
    structured_output = admitted.structured_output
    context_observation = admitted.context_observation

    # Native summarization must see reducible history before the final
    # outbound guard decides whether the current request can fit.
    # A run does not copy the project before it starts.
    starting_snapshot_id = None
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
            desktop_access=desktop_scope,
            desktop_window=desktop_window,
            capture_routes_enabled=capture_session is not None and request.tool_mode is ToolMode.live_tool,
        task=request.task,
        content_blocks=request.content_blocks,
        enabled_tools=enabled,
        presented_tools=presented,
        input_policy=input_policy,
        input_sources=setup.input_sources,
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
        related_files=harness_module._initial_related_files(project_path),
        effective_setup=setup,
        starting_snapshot_id=starting_snapshot_id,
        host_shell=HostShellFacts(
            available=(
                "execute" in presented
                and request.tool_mode is not ToolMode.recorded_tool
            ),
            cwd=project_path if project_path else (
                str(Path.home().resolve())
                if "execute" in presented and request.tool_mode is not ToolMode.recorded_tool
                else None
            ),
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
        try:
            run.pre_run_checkpoint_id = checkpoint_head_id(service.manager.paths.checkpoints_db, run.thread_id)
        except CheckpointReadError as exc:
            raise HarnessError(str(exc), code="checkpoint_linkage_failed", status_code=409) from exc
    with service._lock:
        cancel = service._start_cancel_guards.get((request.thread_id, input_message_id)) or threading.Event()
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
        service._runs[run.id] = run
        service._cancels[run.id] = cancel
        service._decision_ready[run.id] = threading.Event()
        service._pending_decisions[run.id] = None
        service._persist_and_notify(run)

    return run
