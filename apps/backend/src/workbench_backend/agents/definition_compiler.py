"""WF-001 definition compiler: configuration links are not executable steps.

Configuration connections resolve one validated Deep Agents setup.
Workflow connections alone compile into sequencing and typed handovers.
This is not Builder, not a React Flow canvas, and not WF-002.
"""

from __future__ import annotations

from collections import defaultdict, deque
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from workbench_backend.agents.tools import ENABLED_TOOL_NAMES
from workbench_backend.errors import DefinitionCompileError

REQUIRED_SETUP_ASPECTS = (
    "model_profile",
    "tools",
    "skills",
    "memory",
    "environment",
    "access",
    "execution_policy",
)


class NodeRole(str, Enum):
    configuration = "configuration"
    workflow_step = "workflow_step"


class LinkKind(str, Enum):
    configuration = "configuration"
    workflow = "workflow"


class ConfigurationAspect(str, Enum):
    model_profile = "model_profile"
    tools = "tools"
    skills = "skills"
    memory = "memory"
    environment = "environment"
    access = "access"
    execution_policy = "execution_policy"


class TypedHandover(BaseModel):
    kind: Literal["data", "artifact"]
    type_name: str


class DefinitionNode(BaseModel):
    id: str
    role: NodeRole
    label: str | None = None
    model_profile_id: str | None = None
    tools: list[str] | None = None
    skills: list[str] | None = None
    memory: list[str] | None = None
    environment: str | None = None
    access: str | None = None
    execution_policy: str | None = None


class DefinitionLink(BaseModel):
    id: str
    source: str
    target: str
    kind: LinkKind
    aspect: ConfigurationAspect | None = None
    handover: TypedHandover | None = None


class MixedDefinition(BaseModel):
    id: str
    nodes: list[DefinitionNode] = Field(min_length=1)
    links: list[DefinitionLink] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_identities(self) -> MixedDefinition:
        node_ids = [node.id for node in self.nodes]
        if len(node_ids) != len(set(node_ids)):
            raise ValueError("Definition node ids must be unique")
        link_ids = [link.id for link in self.links]
        if len(link_ids) != len(set(link_ids)):
            raise ValueError("Definition link ids must be unique")
        return self


class DeepAgentsSetup(BaseModel):
    """One resolved Deep Agents setup. Not an executed run and not Builder."""

    model_profile_id: str
    tools: list[str]
    skills: list[str]
    memory: list[str]
    environment: str
    access: str
    execution_policy: str
    resolved_from_link_ids: list[str]


class WorkflowStep(BaseModel):
    id: str
    label: str | None = None
    incoming_link_ids: list[str] = Field(default_factory=list)
    outgoing_link_ids: list[str] = Field(default_factory=list)
    incoming_handovers: list[TypedHandover] = Field(default_factory=list)


class CompiledWorkflow(BaseModel):
    definition_id: str
    setup: DeepAgentsSetup
    steps: list[WorkflowStep]
    step_ids: list[str]
    executable_link_ids: list[str]
    configuration_link_ids: list[str]


def compile_definition(definition: MixedDefinition) -> CompiledWorkflow:
    """Compile a mixed definition. Configuration links never become steps."""

    nodes = {node.id: node for node in definition.nodes}
    configuration_links: list[DefinitionLink] = []
    workflow_links: list[DefinitionLink] = []
    for link in definition.links:
        _require_known_endpoints(link, nodes)
        if link.kind is LinkKind.configuration:
            _validate_configuration_link(link, nodes)
            configuration_links.append(link)
        elif link.kind is LinkKind.workflow:
            _validate_workflow_link(link, nodes)
            workflow_links.append(link)
        else:
            _assert_never_link_kind(link.kind)
    setup = _resolve_setup(configuration_links, nodes)
    steps = _compile_steps(workflow_links, nodes)
    executable_link_ids = [link.id for link in workflow_links]
    configuration_link_ids = [link.id for link in configuration_links]
    overlap = set(executable_link_ids) & set(configuration_link_ids)
    if overlap:
        raise DefinitionCompileError(
            "Configuration links must not appear as executable workflow steps",
            code="config_link_as_step",
            details={"link_ids": sorted(overlap)},
        )
    step_ids = [step.id for step in steps]
    config_node_ids = {node.id for node in nodes.values() if node.role is NodeRole.configuration}
    leaked_nodes = config_node_ids.intersection(step_ids)
    if leaked_nodes:
        raise DefinitionCompileError(
            "Configuration nodes must not become executable workflow steps",
            code="config_node_as_step",
            details={"node_ids": sorted(leaked_nodes)},
        )
    return CompiledWorkflow(
        definition_id=definition.id,
        setup=setup,
        steps=steps,
        step_ids=step_ids,
        executable_link_ids=executable_link_ids,
        configuration_link_ids=configuration_link_ids,
    )


def _assert_never_link_kind(kind: LinkKind) -> None:
    raise DefinitionCompileError(
        f"Unsupported link kind {kind!r}",
        code="unsupported_link_kind",
        details={"kind": kind.value},
    )


def _require_known_endpoints(link: DefinitionLink, nodes: dict[str, DefinitionNode]) -> None:
    missing = [endpoint for endpoint in (link.source, link.target) if endpoint not in nodes]
    if missing:
        raise DefinitionCompileError(
            f"Link {link.id} refers to unknown nodes: {', '.join(missing)}",
            code="unknown_link_endpoint",
            details={"link_id": link.id, "missing": missing},
        )


def _validate_configuration_link(
    link: DefinitionLink,
    nodes: dict[str, DefinitionNode],
) -> None:
    if link.aspect is None:
        raise DefinitionCompileError(
            f"Configuration link {link.id} must declare a setup aspect",
            code="configuration_aspect_required",
            details={"link_id": link.id},
        )
    if link.handover is not None:
        raise DefinitionCompileError(
            f"Configuration link {link.id} is setup only and must not carry a workflow handover",
            code="configuration_handover_forbidden",
            details={"link_id": link.id},
        )
    source = nodes[link.source]
    if source.role is not NodeRole.configuration:
        raise DefinitionCompileError(
            f"Configuration link {link.id} source {source.id} must be a configuration node",
            code="configuration_source_required",
            details={"link_id": link.id, "source": source.id},
        )


def _validate_workflow_link(
    link: DefinitionLink,
    nodes: dict[str, DefinitionNode],
) -> None:
    if link.handover is None:
        raise DefinitionCompileError(
            f"Workflow link {link.id} must declare a typed data or artifact handover",
            code="workflow_handover_required",
            details={"link_id": link.id},
        )
    if link.aspect is not None:
        raise DefinitionCompileError(
            f"Workflow link {link.id} cannot carry a configuration aspect; "
            "treating a configuration connection as a workflow step is rejected",
            code="config_link_as_step",
            details={"link_id": link.id, "aspect": link.aspect.value},
        )
    source = nodes[link.source]
    target = nodes[link.target]
    if source.role is NodeRole.configuration or target.role is NodeRole.configuration:
        raise DefinitionCompileError(
            f"Workflow link {link.id} cannot use configuration node "
            f"{source.id if source.role is NodeRole.configuration else target.id} "
            "as a sequencing endpoint; configuration links are not executable steps",
            code="config_link_as_step",
            details={
                "link_id": link.id,
                "source": source.id,
                "target": target.id,
            },
        )
    if source.role is not NodeRole.workflow_step or target.role is not NodeRole.workflow_step:
        raise DefinitionCompileError(
            f"Workflow link {link.id} must connect workflow_step nodes",
            code="workflow_endpoints_required",
            details={"link_id": link.id},
        )


def _resolve_setup(
    links: list[DefinitionLink],
    nodes: dict[str, DefinitionNode],
) -> DeepAgentsSetup:
    if not links:
        raise DefinitionCompileError(
            "A mixed definition must resolve configuration links into one Deep Agents setup",
            code="configuration_required",
        )
    resolved: dict[str, Any] = {}
    resolved_from: list[str] = []
    for link in links:
        aspect = link.aspect
        if aspect is None:
            raise DefinitionCompileError(
                f"Configuration link {link.id} is missing its setup aspect",
                code="configuration_aspect_required",
                details={"link_id": link.id},
            )
        value = _configuration_value(nodes[link.source], aspect)
        key = aspect.value
        if key in resolved and resolved[key] != value:
            raise DefinitionCompileError(
                f"Conflicting configuration for {key}",
                code="configuration_conflict",
                details={"aspect": key, "link_id": link.id},
            )
        resolved[key] = value
        resolved_from.append(link.id)
    missing = [aspect for aspect in REQUIRED_SETUP_ASPECTS if aspect not in resolved]
    if missing:
        raise DefinitionCompileError(
            "Configuration links must supply every Deep Agents setup aspect",
            code="configuration_incomplete",
            details={"missing": missing},
        )
    tools = list(resolved["tools"])
    denied = [name for name in tools if name not in ENABLED_TOOL_NAMES]
    if denied:
        raise DefinitionCompileError(
            f"Tools are not in the enabled catalogue: {', '.join(denied)}",
            code="tool_denied",
            details={"denied": denied},
        )
    if not tools:
        raise DefinitionCompileError(
            "Resolved Deep Agents setup requires at least one enabled tool",
            code="tools_required",
        )
    return DeepAgentsSetup(
        model_profile_id=str(resolved["model_profile"]),
        tools=tools,
        skills=list(resolved["skills"]),
        memory=list(resolved["memory"]),
        environment=str(resolved["environment"]),
        access=str(resolved["access"]),
        execution_policy=str(resolved["execution_policy"]),
        resolved_from_link_ids=resolved_from,
    )


def _configuration_value(node: DefinitionNode, aspect: ConfigurationAspect) -> Any:
    if aspect is ConfigurationAspect.model_profile:
        if not node.model_profile_id:
            raise DefinitionCompileError(
                f"Configuration node {node.id} is missing model_profile_id",
                code="configuration_value_required",
                details={"node_id": node.id, "aspect": aspect.value},
            )
        return node.model_profile_id
    if aspect is ConfigurationAspect.tools:
        if node.tools is None:
            raise DefinitionCompileError(
                f"Configuration node {node.id} is missing tools",
                code="configuration_value_required",
                details={"node_id": node.id, "aspect": aspect.value},
            )
        return list(node.tools)
    if aspect is ConfigurationAspect.skills:
        if node.skills is None:
            raise DefinitionCompileError(
                f"Configuration node {node.id} is missing skills",
                code="configuration_value_required",
                details={"node_id": node.id, "aspect": aspect.value},
            )
        return list(node.skills)
    if aspect is ConfigurationAspect.memory:
        if node.memory is None:
            raise DefinitionCompileError(
                f"Configuration node {node.id} is missing memory",
                code="configuration_value_required",
                details={"node_id": node.id, "aspect": aspect.value},
            )
        return list(node.memory)
    if aspect is ConfigurationAspect.environment:
        if not node.environment:
            raise DefinitionCompileError(
                f"Configuration node {node.id} is missing environment",
                code="configuration_value_required",
                details={"node_id": node.id, "aspect": aspect.value},
            )
        return node.environment
    if aspect is ConfigurationAspect.access:
        if not node.access:
            raise DefinitionCompileError(
                f"Configuration node {node.id} is missing access",
                code="configuration_value_required",
                details={"node_id": node.id, "aspect": aspect.value},
            )
        return node.access
    if aspect is ConfigurationAspect.execution_policy:
        if not node.execution_policy:
            raise DefinitionCompileError(
                f"Configuration node {node.id} is missing execution_policy",
                code="configuration_value_required",
                details={"node_id": node.id, "aspect": aspect.value},
            )
        return node.execution_policy
    raise DefinitionCompileError(
        f"Unsupported configuration aspect {aspect!r}",
        code="unsupported_aspect",
        details={"aspect": aspect.value, "node_id": node.id},
    )


def _compile_steps(
    links: list[DefinitionLink],
    nodes: dict[str, DefinitionNode],
) -> list[WorkflowStep]:
    if not links:
        raise DefinitionCompileError(
            "A mixed definition must compile at least one workflow connection into sequencing",
            code="workflow_required",
        )
    incoming: dict[str, list[DefinitionLink]] = defaultdict(list)
    outgoing: dict[str, list[DefinitionLink]] = defaultdict(list)
    step_ids: set[str] = set()
    for link in links:
        step_ids.add(link.source)
        step_ids.add(link.target)
        incoming[link.target].append(link)
        outgoing[link.source].append(link)
    ordered = _topological_step_ids(step_ids, links)
    steps: list[WorkflowStep] = []
    for step_id in ordered:
        node = nodes[step_id]
        steps.append(
            WorkflowStep(
                id=node.id,
                label=node.label,
                incoming_link_ids=[link.id for link in incoming[step_id]],
                outgoing_link_ids=[link.id for link in outgoing[step_id]],
                incoming_handovers=[
                    link.handover for link in incoming[step_id] if link.handover is not None
                ],
            )
        )
    return steps


def _topological_step_ids(step_ids: set[str], links: list[DefinitionLink]) -> list[str]:
    successors: dict[str, list[str]] = defaultdict(list)
    indegree: dict[str, int] = {step_id: 0 for step_id in step_ids}
    for link in links:
        successors[link.source].append(link.target)
        indegree[link.target] = indegree.get(link.target, 0) + 1
        indegree.setdefault(link.source, 0)
    ready = deque(sorted(step_id for step_id, degree in indegree.items() if degree == 0))
    ordered: list[str] = []
    while ready:
        current = ready.popleft()
        ordered.append(current)
        for nxt in sorted(successors[current]):
            indegree[nxt] -= 1
            if indegree[nxt] == 0:
                ready.append(nxt)
    if len(ordered) != len(step_ids):
        raise DefinitionCompileError(
            "Workflow connections form a cycle; sequencing is invalid",
            code="workflow_cycle",
        )
    return ordered
