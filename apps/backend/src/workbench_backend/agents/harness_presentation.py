from __future__ import annotations

from types import SimpleNamespace

from workbench_backend.agents.execution_policy import PLAN_TOOLS
from workbench_backend.agents.retrieval import (
    SEARCH_KNOWLEDGE_TOOL_NAME,
    resolve_embedding_deployment,
    validate_project_retrieval_paths,
)
from workbench_backend.agents.schemas import ToolMode
from workbench_backend.agents.tool_disclosure import FIND_TOOLS, always_skill_dependencies
from workbench_backend.agents.tools import KNOWLEDGE_ROUTE_READ_TOOLS, resolve_presented_tools
from workbench_backend.assets.schemas import RetainedAssetListFilters, RetainedAssetOrigin
from workbench_backend.errors import HarnessError


def load_connection_snapshots(service, request, input_policy, execution_snapshot):
    deferred_connections = input_policy is not None and input_policy.tool_loading == "when_needed"
    accepted_connections = getattr(execution_snapshot, "connection_snapshots", None)
    if accepted_connections is not None:
        connection_snapshots = [item.model_copy(deep=True) for item in accepted_connections]
        expected_connections = set(request.connection_ids or []) if request.presented_tools != [] else set()
        if {item.id for item in connection_snapshots} != expected_connections:
            raise HarnessError("The selected connections differ from this accepted input. Start a new message.",
                code="connection_changed", status_code=409)
        if not deferred_connections:
            for item in connection_snapshots:
                service.connections.validate_snapshot(item)
            service.connections.snapshot(request.connection_ids or [], tools_enabled=request.presented_tools != [])
    else:
        connection_snapshots = service.connections.snapshot(request.connection_ids or [], tools_enabled=request.presented_tools != [],
            allow_unready=deferred_connections)
    if input_policy is not None and input_policy.pinned_tools:
        pinned_connections = [item.id for item in connection_snapshots
            if set(input_policy.pinned_tools).intersection(tool.name for tool in item.tools)]
        if pinned_connections:
            for item in connection_snapshots:
                if item.id in pinned_connections:
                    service.connections.validate_snapshot(item)
            service.connections.snapshot(pinned_connections)
    external_names = [tool.name for connection in connection_snapshots for tool in connection.tools]
    return connection_snapshots, external_names


def resolve_capture_routes(service, request):
    capture_session = (
        service.assets.session_for_thread(request.thread_id)
        if service.assets is not None and request.source_surface == "chat" and request.thread_id
        else None
    )
    capture_routes = bool(
        capture_session is not None
        and request.tool_mode is ToolMode.live_tool
        and (
            any(name in {"browser_take_screenshot", "desktop_screenshot"} for name in (request.presented_tools or []))
            or "read_file" in (request.presented_tools or []) and service.assets.list_assets(RetainedAssetListFilters(
                session_id=capture_session.id, origin=RetainedAssetOrigin.capture,
            ))
        )
    )
    return capture_session, capture_routes


def resolve_catalogue_and_retrieval(service, request, project_path, knowledge_plan, capture_routes, external_names):
    presented, denied, filesystem_blocked, shell_blocked = resolve_presented_tools(
        request.presented_tools,
        project_bound=project_path is not None,
        knowledge_routes=knowledge_plan.has_knowledge_routes,
        capture_routes=capture_routes,
        external_names=external_names,
        attachment_available=bool(request.retained_asset_ids),
    )
    retrieval_requested = bool(request.embedding_deployment_id or request.retained_asset_ids or request.retrieval_project_paths)
    recorded = request.tool_mode is ToolMode.recorded_tool
    if not recorded:
        validate_project_retrieval_paths(project_path, request.retrieval_project_paths)
    embedding_deployment = None
    retrieval_documents = []
    if request.embedding_deployment_id and not recorded:
        embedding_deployment = resolve_embedding_deployment(
            service.manager,
            request.embedding_deployment_id or "",
        )
    retrieval_presented = bool(
        (request.retained_asset_ids or request.retrieval_project_paths) and not recorded and request.presented_tools != []
    )
    if denied:
        raise HarnessError(
            f"Tools are not in the enabled catalogue: {', '.join(denied)}",
            code="tool_denied",
            status_code=400,
        )
    return (
        presented,
        filesystem_blocked,
        shell_blocked,
        retrieval_requested,
        recorded,
        embedding_deployment,
        retrieval_documents,
        retrieval_presented,
    )


def apply_filesystem_shell_gates(input_policy, presented, filesystem_blocked, shell_blocked):
    progressive = input_policy is not None and input_policy.tool_loading == "when_needed"
    if progressive:
        pinned_blocked = set(input_policy.pinned_tools).intersection([*filesystem_blocked, *shell_blocked])
        if pinned_blocked:
            raise HarnessError("Pinned file and shell tools need a project folder.", code="filesystem_requires_project", status_code=409)
        presented.extend(name for name in [*filesystem_blocked, *shell_blocked] if name not in presented)
    if filesystem_blocked and not progressive:
        raise HarnessError(
            "Filesystem tools require a bound project folder.",
            code="filesystem_requires_project",
            status_code=400,
            details={"tools": filesystem_blocked},
        )
    if shell_blocked and not progressive:
        raise HarnessError(
            "The host shell and project preview require a bound project folder. "
            "A home-directory default is not invented.",
            code="shell_requires_project",
            status_code=400,
            details={"tools": shell_blocked},
        )
    return presented


def apply_automatic_read_paths(request, knowledge_plan, presented, retrieval_presented, capture_routes, recorded):
    if retrieval_presented and SEARCH_KNOWLEDGE_TOOL_NAME not in presented:
        presented = [*presented, SEARCH_KNOWLEDGE_TOOL_NAME]
    if knowledge_plan.has_knowledge_routes and request.presented_tools != []:
        for name in KNOWLEDGE_ROUTE_READ_TOOLS:
            if name not in presented:
                presented = [*presented, name]
    if capture_routes and request.presented_tools != [] and "read_file" not in presented:
        presented = [*presented, "read_file"]
    # This list scopes only the automatic result reader, never a
    # selected file reader whose backend already enforces access.
    framework_read_paths = (
        ["/large_tool_results/", "/conversation_history/"]
        if presented and "read_file" not in presented and not recorded else []
    )
    if retrieval_presented and framework_read_paths:
        framework_read_paths.append("/retrieved/")
    if request.embedding_deployment_id and request.presented_tools == []:
        raise HarnessError(
            "Retrieval requires its search tool. Enable tools or remove the retrieval selection.",
            code="retrieval_tools_off",
            status_code=400,
        )
    return presented, framework_read_paths


def apply_disclosure_and_plan_filter(request, input_policy, helpers, knowledge_plan, presented):
    if helpers and request.presented_tools != []:
        presented = [*presented, "task"]
    if input_policy is not None:
        excluded = {source.removeprefix("tool:") for source in input_policy.excluded_sources if source.startswith("tool:")}
        presented = [name for name in presented if name not in excluded]
        if request.presented_tools != []:
            if input_policy.tool_loading == "when_needed":
                presented.append(FIND_TOOLS)
            helper_refs = any((helper.configuration.memory_entry_ids or helper.configuration.memory_version_refs
                or helper.configuration.skill_entry_ids or helper.configuration.skill_version_refs) for helper in helpers)
            if helper_refs or getattr(knowledge_plan, "references", None) and any(row.mode == "when_needed" for row in knowledge_plan.references):
                presented.append("read_reference")
        presented = [name for name in presented if name not in excluded]
    if request.work_mode == "plan":
        presented = [name for name in presented if name in PLAN_TOOLS]
    return presented


def validate_required_presentation(
    service, request, input_policy, knowledge_plan, project_path,
    connection_snapshots, presented, framework_read_paths, filesystem_blocked, shell_blocked,
):
    required_tools, required_connections = always_skill_dependencies(SimpleNamespace(
        input_policy=input_policy, presented_tools=presented, framework_read_paths=framework_read_paths,
        work_mode=request.work_mode, connection_snapshots=connection_snapshots, project_path=project_path), knowledge_plan)
    if required_tools.intersection([*filesystem_blocked, *shell_blocked]):
        raise HarnessError("Required file and shell tools need a project folder.", code="filesystem_requires_project", status_code=409)
    essential_connections = required_connections | {item.id for item in connection_snapshots
        if required_tools.intersection(tool.name for tool in item.tools)}
    if essential_connections:
        for item in connection_snapshots:
            if item.id in essential_connections:
                service.connections.validate_snapshot(item)
        service.connections.snapshot(sorted(essential_connections))
    if input_policy is not None:
        from workbench_backend.browser.service import BROWSER_TOOL_NAMES
        eager_browser = set(presented).intersection(BROWSER_TOOL_NAMES).intersection(
            presented if input_policy.tool_loading == "always" else set(input_policy.pinned_tools) | required_tools)
        if eager_browser:
            if service.browser is None:
                raise HarnessError("Configure the optional Browser worker before pinning its tools.", code="browser_worker_missing", status_code=409)
            service.browser.runtime.require_installed()
    return required_tools
