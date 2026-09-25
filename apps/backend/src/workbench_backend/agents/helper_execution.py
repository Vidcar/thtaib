"""Inline named children use the same compiler, records and dispatch authority."""
from __future__ import annotations

import asyncio
import hashlib

from langchain_core.runnables import RunnableLambda
from langgraph.errors import GraphInterrupt

from workbench_backend.agents.context import observe_context, require_context_fit
from workbench_backend.agents.effective_setup import resolve_effective_setup
from workbench_backend.agents.execution_policy import CURRENT_TOOL_CALL, PLAN_INSTRUCTIONS, PLAN_TOOLS, require_setup_capabilities
from workbench_backend.agents.host_shell import approval_mode_instructions
from workbench_backend.agents.schemas import AgentRunStatus, AgentStartRequest, ChildRunActivity, ReviewObservation, TaskCriteria
from workbench_backend.agents.setup_schemas import ReviewConfiguration
from workbench_backend.errors import HarnessError
from workbench_backend.inference.ids import utc_now
from workbench_backend.inference.schemas import SettingsBags


def _child_run_id(parent, snapshot, call_id):
    return "child_" + hashlib.sha256(f"{parent.id}:{call_id}:{snapshot.agent_id}".encode()).hexdigest()[:24]


def _saved_child_message_identities(child):
    """Skip checkpoint replay already represented in this child's audit."""
    seen = set()
    for event in child.events:
        if event.kind == "assistant_message" and isinstance(event.detail.get("message_id"), str):
            seen.add(("message", event.detail["message_id"]))
        elif event.kind == "tool_result" and isinstance(event.detail.get("tool_call_id"), str):
            seen.add(("tool", event.detail["tool_call_id"]))
    return seen


def _child_run(owner, parent, snapshot, call_id, payload):
    child_id = _child_run_id(parent, snapshot, call_id)
    existing = owner.store.get_run(child_id)
    if existing is not None:
        return existing
    config = snapshot.configuration
    if not config.deployment_id and (config.bundle_id or config.model_configuration_id):
        raise HarnessError(f"Helper {snapshot.name} has no saved model deployment.", code="helper_model_unavailable", status_code=409)
    # The parent has yielded its model call while this native Deep Agents
    # helper runs. The managed llama.cpp router may hand the sole model slot to
    # this helper and reload the parent model for its continuation.
    deployment = owner.manager.ensure_deployment_ready(config.deployment_id or parent.deployment_id)
    selected_tools = config.presented_tools if config.presented_tools is not None else parent.presented_tools
    presented = [name for name in selected_tools if name in parent.presented_tools and name != "task"]
    work_mode = "plan" if parent.work_mode == "plan" or config.work_mode == "plan" else "work"
    if work_mode == "plan":
        presented = [name for name in presented if name in PLAN_TOOLS]
    require_setup_capabilities(config, project_bound=bool(parent.project_path), presented_tools=presented)
    rank = {"ask": 0, "full_access": 1}
    approval = min((parent.approval_mode, config.approval_mode or parent.approval_mode), key=rank.__getitem__)
    desktop_rank = {"off": 0, "selected": 1, "all": 2}
    desktop_access = min((parent.desktop_access, config.desktop_access or parent.desktop_access), key=desktop_rank.__getitem__)
    selected_connections = [ident for ident in (config.connection_ids if config.connection_ids is not None else parent.connection_ids) if ident in parent.connection_ids]
    request = AgentStartRequest(deployment_id=deployment.id, task="Helper task",
        memory_version_refs=list(config.memory_version_refs or []), skill_version_refs=list(config.skill_version_refs or []),
        protected_instruction_version_refs=list(dict.fromkeys([*parent.protected_instruction_version_refs, *(config.protected_instruction_version_refs or [])])))
    refs = owner._resolve_knowledge_refs(request)
    versions = owner._load_knowledge_versions(refs)
    setup = resolve_effective_setup(deployment=deployment.model_copy(update={"settings": SettingsBags.model_validate(snapshot.settings_snapshot)}) if snapshot.settings_snapshot is not None else deployment,
        profile=owner.manager.get_profile(config.profile_id) if config.profile_id and snapshot.settings_snapshot is None else None,
        per_request_overrides=config.per_request_overrides,
        startup_overrides=None if snapshot.settings_snapshot is not None else config.startup_overrides,
        knowledge_refs=refs, knowledge_versions=versions, surface_system_prompt=snapshot.role,
        default_system_prompt="Carry out the delegated task and return the result to the parent.",
        inherit_deployment_settings=True if snapshot.settings_snapshot is not None else config.inherit_deployment_settings is not False,
        instruction_layers=snapshot.instruction_layers, selected_project_id=parent.project_id,
        selected_agent_setup_id=snapshot.agent_id, selected_agent_setup_version_id=snapshot.version_id,
        selected_connection_ids=selected_connections)
    setup.selected_profile_id = config.profile_id
    if setup.startup_mismatches:
        raise HarnessError(f"Helper {snapshot.name} requires different model loading settings. Reload before starting this conversation's work.", code="helper_reload_required", status_code=409)
    setup.system_prompt += "\n\n" + approval_mode_instructions(approval)
    if work_mode == "plan":
        setup.system_prompt += "\n\n" + PLAN_INSTRUCTIONS
    messages = payload.get("messages", [])
    task = str(getattr(messages[-1], "content", "Delegated task")) if messages else "Delegated task"
    observation = observe_context(deployment=deployment, per_request=setup.bags.per_request,
        system_prompt=setup.system_prompt, task=task, content_blocks=None, output_schema=None,
        tool_count=len(presented), continuing_thread=False)
    require_context_fit(observation)
    now = utc_now()
    child = parent.model_copy(deep=True, update=dict(id=child_id, parent_run_id=parent.id,
        deployment_id=deployment.id, task=task, input_message_id=None, content_blocks=None,
        agent_setup_id=snapshot.agent_id, agent_setup_version_id=snapshot.version_id,
        presented_tools=presented, enabled_tools=[name for name in parent.enabled_tools if name != "task"],
        denied_tools=[name for name in selected_tools if name not in presented], approval_mode=approval,
        work_mode=work_mode, helper_agent_ids=[], helper_snapshots=[], child_runs=[],
        desktop_access=desktop_access,
        requires_project=bool(config.requires_project), requires_host_shell=bool(config.requires_host_shell),
        review=ReviewConfiguration(), review_observation=ReviewObservation(), criteria=TaskCriteria(),
        profile_id=setup.selected_profile_id, effective_setup=setup, system_prompt=setup.system_prompt,
        memory_version_refs=refs.memory_version_refs, skill_version_refs=refs.skill_version_refs,
        protected_instruction_version_refs=refs.protected_instruction_version_refs,
        connection_ids=selected_connections, connection_snapshots=[item for item in parent.connection_snapshots if item.id in selected_connections],
        embedding_deployment_id=config.embedding_deployment_id,
        events=[], model_requests=[], tool_invocations=[], related_files=[],
        completion=None, output_schema=None, structured_output=None, context_observation=observation,
        generation_observation=None, starting_snapshot_id=None, final_snapshot_id=None,
        checkpoint_ids=[], resume_checkpoint_id=None, dispatched_tool_calls=0, dispatched_tool_ids=[], completed_tool_ids=[], tool_authorizations={}, tool_authorization_grants={},
        status=AgentRunStatus.running, created_at=now, updated_at=now, finished_at=None,
        pending_interrupt=None, error=None, stop_reason=None))
    return child


def compiled_helpers(owner, parent, control, *, inspection_only=False):
    specs = []
    for snapshot in parent.helper_snapshots:
        async def invoke(payload, config, snapshot=snapshot):
            call_id = CURRENT_TOOL_CALL.get()
            if not call_id:
                raise HarnessError("A helper requires an owned parent tool-call identity.", code="helper_identity_missing", status_code=409)
            namespace = [part for part in config.get("configurable", {}).get("checkpoint_ns", "").split("|") if part]
            if not namespace:
                namespace = [f"tools:{call_id}"]
            child_id = _child_run_id(parent, snapshot, call_id)
            with owner._lock:
                activity = next((item for item in parent.child_runs if item.tool_call_id == call_id), None)
                if activity is None:
                    activity = ChildRunActivity(run_id=child_id, agent_id=snapshot.agent_id,
                        version_id=snapshot.version_id, name=snapshot.name, namespace=namespace, tool_call_id=call_id)
                    parent.child_runs.append(activity)
                activity.status = "waiting for model"
                activity.error = None
                owner._persist_and_notify(parent)

            child = None
            def admit():
                control.require_dispatch(parent)
                with owner.manager.reserve_deployment(snapshot.configuration.deployment_id or parent.deployment_id,
                        profile_id=snapshot.configuration.profile_id):
                    control.require_dispatch(parent)
                    admitted = _child_run(owner, parent, snapshot, call_id, payload)
                    with owner._lock:
                        activity.status = "working"
                        admitted.status = AgentRunStatus.running
                        admitted.error = None
                        admitted.stop_reason = None
                        admitted.finished_at = None
                        admitted.pending_interrupt = None
                        owner._runs[admitted.id] = admitted
                        owner._persist(admitted)
                        owner._persist_and_notify(parent)
                    return admitted
            sink = []
            try:
                child = await asyncio.to_thread(admit)
                async with owner._worker_tools_context(child) as external:
                    graph = await asyncio.to_thread(owner._create_compiled_agent, child, sink, None,
                        external_tools=external, execution_control=control, is_child=True, inspection_only=inspection_only)
                    stream = None
                    result = None
                    seen_messages = _saved_child_message_identities(child)
                    message_nodes = {}
                    try:
                        stream = await graph.astream_events(payload, config=config, version="v3")
                        async for event in stream:
                            params = event.get("params") if isinstance(event, dict) else None
                            if not isinstance(params, dict):
                                continue
                            child_namespace = list(params.get("namespace") or [])
                            # The child graph may report its root with the
                            # checkpoint namespace. Rebase only this task's
                            # prefix; older nested streams used plain "tools".
                            relative_namespace = (child_namespace[len(activity.namespace):]
                                if child_namespace[:len(activity.namespace)] == activity.namespace else
                                child_namespace[1:] if child_namespace[:1] == ["tools"] else child_namespace)
                            local = {**event, "params": {**params, "namespace": relative_namespace}}
                            scoped = {**event, "params": {**params, "namespace": [*activity.namespace, *relative_namespace]}}
                            try:
                                await asyncio.to_thread(owner._observe_interaction, parent, scoped)
                            except Exception as exc:  # noqa: BLE001 - live output must be durable
                                raise owner._interaction_persistence_failure(parent, exc) from exc
                            await asyncio.to_thread(owner._ingest_native_event, child, local, seen_messages, message_nodes)
                            if params.get("interrupts"):
                                from workbench_backend.agents.harness import _pending_from_native_event
                                child.pending_interrupt = _pending_from_native_event(scoped)
                                raise GraphInterrupt(params["interrupts"])
                            if event.get("method") == "values" and not relative_namespace:
                                values = params.get("data")
                                if isinstance(values, tuple):
                                    values = values[0]
                                if isinstance(values, dict):
                                    result = values
                    finally:
                        await owner._close_native_stream(stream)
                    if result is None:
                        raise HarnessError("The helper finished without a graph result.", code="helper_result_missing", status_code=500)
                owner._ingest_native_values(child, result, seen_messages, message_nodes)
                child.status = AgentRunStatus.completed
                child.stop_reason = "completed"
                child.finished_at = utc_now()
                child.pending_interrupt = None
                activity.status = "completed"
                return result
            except GraphInterrupt:
                activity.status = "waiting for approval or answer"
                raise
            except asyncio.CancelledError:
                if child is not None:
                    child.status = AgentRunStatus.cancelled
                    child.stop_reason = "cancelled"
                    child.finished_at = utc_now()
                    child.pending_interrupt = None
                activity.status = "cancelled"
                raise
            except BaseException as exc:
                cancelling = (isinstance(exc, HarnessError) and exc.code == "run_cancelling"
                    or parent.status in {AgentRunStatus.cancel_requested, AgentRunStatus.cancelled})
                if child is not None:
                    child.status = AgentRunStatus.cancelled if cancelling else AgentRunStatus.failed
                    child.error = None if cancelling else str(exc)
                    child.stop_reason = "cancelled" if cancelling else "failed"
                    child.finished_at = utc_now()
                    child.pending_interrupt = None
                activity.status = "cancelled" if cancelling else "failed"
                activity.error = None if cancelling else str(exc)
                raise
            finally:
                with owner._lock:
                    if child is not None:
                        owner._persist(child)
                    owner._persist_and_notify(parent)
                if child is not None:
                    await asyncio.to_thread(owner._close_model_client, child.id)
        specs.append({"name": snapshot.agent_id, "description": f"{snapshot.name}: {snapshot.role or 'Selected helper'}",
            "runnable": RunnableLambda(invoke, name=snapshot.name)})
    return specs
