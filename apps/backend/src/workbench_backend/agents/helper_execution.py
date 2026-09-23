"""Inline named children use the same compiler, records and dispatch authority."""
from __future__ import annotations

import asyncio
import hashlib

from langchain_core.runnables import RunnableLambda
from langgraph.errors import GraphInterrupt

from workbench_backend.agents.context import observe_context, require_context_fit
from workbench_backend.agents.effective_setup import resolve_effective_setup
from workbench_backend.agents.execution_policy import CURRENT_TOOL_CALL, PLAN_INSTRUCTIONS, PLAN_TOOLS
from workbench_backend.agents.host_shell import approval_mode_instructions
from workbench_backend.agents.schemas import AgentRunStatus, AgentStartRequest, ChildRunActivity, ReviewObservation, TaskCriteria
from workbench_backend.agents.setup_schemas import ReviewConfiguration
from workbench_backend.errors import HarnessError
from workbench_backend.inference.ids import utc_now
from workbench_backend.inference.schemas import SettingsBags


def _child_run(owner, parent, snapshot, call_id, payload):
    child_id = "child_" + hashlib.sha256(f"{parent.id}:{call_id}:{snapshot.agent_id}".encode()).hexdigest()[:24]
    existing = owner.store.get_run(child_id)
    if existing is not None:
        return existing
    config = snapshot.configuration
    if not config.deployment_id and (config.bundle_id or config.model_configuration_id):
        raise HarnessError(f"Helper {snapshot.name} needs its selected model loaded before starting.", code="helper_model_unavailable", status_code=409)
    deployment = owner.manager.get_deployment(config.deployment_id or parent.deployment_id)
    if deployment.id != parent.deployment_id and deployment.kind == "managed" and deployment.status != "running":
        raise HarnessError(f"Helper {snapshot.name} needs a different loaded model. Load a compatible model before starting; the active model was kept.", code="helper_model_unavailable", status_code=409)
    selected_tools = config.presented_tools if config.presented_tools is not None else parent.presented_tools
    presented = [name for name in selected_tools if name in parent.presented_tools and name != "task"]
    work_mode = "plan" if parent.work_mode == "plan" or config.work_mode == "plan" else "work"
    if work_mode == "plan":
        presented = [name for name in presented if name in PLAN_TOOLS]
    rank = {"ask": 0, "approve_for_me": 1, "full_access": 2}
    approval = min((parent.approval_mode, config.approval_mode or parent.approval_mode), key=rank.__getitem__)
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
        review=ReviewConfiguration(), review_observation=ReviewObservation(), criteria=TaskCriteria(),
        profile_id=setup.selected_profile_id, effective_setup=setup, system_prompt=setup.system_prompt,
        memory_version_refs=refs.memory_version_refs, skill_version_refs=refs.skill_version_refs,
        protected_instruction_version_refs=refs.protected_instruction_version_refs,
        connection_ids=selected_connections, connection_snapshots=[item for item in parent.connection_snapshots if item.id in selected_connections],
        embedding_deployment_id=config.embedding_deployment_id,
        events=[], model_requests=[], tool_invocations=[], file_changes=[], related_files=[],
        completion=None, output_schema=None, structured_output=None, context_observation=observation,
        generation_observation=None, starting_snapshot_id=None, final_snapshot_id=None,
        checkpoint_ids=[], resume_checkpoint_id=None, dispatched_tool_calls=0, dispatched_tool_ids=[], completed_tool_ids=[], tool_authorizations={},
        status=AgentRunStatus.running, created_at=now, updated_at=now, finished_at=None,
        pending_interrupt=None, error=None, stop_reason=None))
    return child


def compiled_helpers(owner, parent, control, *, inspection_only=False):
    specs = []
    for snapshot in parent.helper_snapshots:
        async def invoke(payload, config, snapshot=snapshot):
            control.require_dispatch(parent)
            call_id = CURRENT_TOOL_CALL.get()
            if not call_id:
                raise HarnessError("A helper requires an owned parent tool-call identity.", code="helper_identity_missing", status_code=409)
            namespace = [part for part in config.get("configurable", {}).get("checkpoint_ns", "").split("|") if part]
            def admit():
                with owner.manager.reserve_deployment(snapshot.configuration.deployment_id or parent.deployment_id,
                        profile_id=snapshot.configuration.profile_id):
                    control.require_dispatch(parent)
                    child = _child_run(owner, parent, snapshot, call_id, payload)
                    with owner._lock:
                        activity = next((item for item in parent.child_runs if item.run_id == child.id), None)
                        if activity is None:
                            activity = ChildRunActivity(run_id=child.id, agent_id=snapshot.agent_id,
                                version_id=snapshot.version_id, name=snapshot.name, namespace=namespace, tool_call_id=call_id)
                            parent.child_runs.append(activity)
                        activity.status = "working"
                        child.status = AgentRunStatus.running
                        child.error = None
                        child.stop_reason = None
                        child.finished_at = None
                        owner._runs[child.id] = child
                        owner._persist(child)
                        owner._persist_and_notify(parent)
                    return child, activity
            child, activity = await asyncio.to_thread(admit)
            sink = []
            try:
                async with owner.connections.open_tools(child) as external:
                    graph = await asyncio.to_thread(owner._create_compiled_agent, child, sink, None,
                        external_tools=external, execution_control=control, is_child=True, inspection_only=inspection_only)
                    result = await graph.ainvoke(payload, config)
                owner._ingest_native_values(child, result, set())
                child.status = AgentRunStatus.completed
                child.stop_reason = "completed"
                child.finished_at = utc_now()
                activity.status = "completed"
                return result
            except GraphInterrupt:
                activity.status = "waiting for approval or answer"
                raise
            except asyncio.CancelledError:
                child.status = AgentRunStatus.cancelled
                child.stop_reason = "cancelled"
                child.finished_at = utc_now()
                activity.status = "cancelled"
                raise
            except BaseException as exc:
                child.status = AgentRunStatus.failed
                child.error = str(exc)
                child.stop_reason = "failed"
                child.finished_at = utc_now()
                activity.status = "failed"
                activity.error = str(exc)
                raise
            finally:
                with owner._lock:
                    owner._persist(child)
                    owner._persist_and_notify(parent)
                await asyncio.to_thread(owner._close_model_client, child.id)
        specs.append({"name": snapshot.agent_id, "description": f"{snapshot.name}: {snapshot.role or 'Selected helper'}",
            "runnable": RunnableLambda(invoke, name=snapshot.name)})
    return specs
