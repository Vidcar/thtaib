"""ARCH-003 / Issue #57: resolve one effective setup before the harness runs.

Selected ≠ loaded ≠ applied. This is the Issue #53 contract made concrete on
the existing Chat / Lab / Agent-run path. It is not a retrieval product and
does not start inference.
"""

from __future__ import annotations

import hashlib
from typing import Any

from pydantic import BaseModel, Field

from workbench_backend.errors import HarnessError
from workbench_backend.inference.configuration_options import validate_model_reasoning
from workbench_backend.inference.schemas import Deployment, RunProfile, SettingsBag, SettingsBags
from workbench_backend.inference.settings import (
    PER_REQUEST_KEYS,
    STARTUP_KEYS,
    resolve_bag,
    resolve_bags,
)
from workbench_backend.agents.memory_skills import (
    MEMORY_EDIT_GAP,
    MaterializedKnowledgeFact,
)
from workbench_backend.knowledge.schemas import KnowledgeKind, KnowledgeRefs, KnowledgeVersion
from workbench_backend.agents.setup_schemas import InstructionLayer

NO_RETRIEVAL_GAP = "no retrieval requested"
RAG_GAP = NO_RETRIEVAL_GAP
RECORDED_RETRIEVAL_GAP = "recorded-tool replay does not attach a live retrieval index"
MEMORY_GAP = "no durable memory bound for this run (AGT-004)"
SKILL_GAP = "no skill versions bound for this run"
KNOWLEDGE_PREAMBLE = (
    "The following durable knowledge is application-owned versioned content "
    "(STATE-005). Protected instructions are policy in the authored system "
    "prompt, not Deep Agents memory= file data."
)


class StartupMismatch(BaseModel):
    key: str
    selected: Any = None
    loaded: Any = None
    reason: str = "selected profile startup is not the loaded deployment startup"


class LoadedKnowledgeFact(BaseModel):
    version_id: str
    entry_id: str
    kind: KnowledgeKind
    content_digest: str
    content_available: bool
    selected: bool = True


class EffectiveSetup(BaseModel):
    """Inspectable selected / loaded / applied facts for one run."""

    selected_profile_id: str | None = None
    selected_project_id: str | None = None
    selected_agent_setup_id: str | None = None
    selected_agent_setup_version_id: str | None = None
    selected_connection_ids: list[str] = Field(default_factory=list)
    instruction_layers: list[InstructionLayer] = Field(default_factory=list)
    selected_deployment_id: str
    selected_embedding_deployment_id: str | None = None
    selected_memory_version_ids: list[str] = Field(default_factory=list)
    selected_skill_version_ids: list[str] = Field(default_factory=list)
    selected_protected_instruction_version_ids: list[str] = Field(default_factory=list)
    loaded_deployment_id: str
    loaded_embedding_deployment_id: str | None = None
    loaded_embedding_endpoint: str | None = None
    loaded_startup: dict[str, Any] = Field(default_factory=dict)
    loaded_knowledge: list[LoadedKnowledgeFact] = Field(default_factory=list)
    materialized_knowledge: list[MaterializedKnowledgeFact] = Field(default_factory=list)
    retrieval_requested: bool = False
    retrieval_presented: bool = False
    retrieval_corpus_documents: int = 0
    bags: SettingsBags = Field(default_factory=SettingsBags)
    startup_mismatches: list[StartupMismatch] = Field(default_factory=list)
    unsupported: dict[str, list[str]] = Field(default_factory=dict)
    overridden: dict[str, list[dict[str, Any]]] = Field(default_factory=dict)
    retired: dict[str, list[dict[str, Any]]] = Field(default_factory=dict)
    system_prompt: str
    gaps: list[str] = Field(default_factory=list)
    knowledge_binding: str = "none"
    note: str = (
        "Selected ids are not proof of loaded content or applied bags. "
        "Inspect this record and the outbound request. Retrieval is presented "
        "only when embedding_deployment_id resolved to a loaded embedding endpoint."
    )


def content_digest(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def effective_setting_values(manager, configuration, provenance: dict) -> dict:
    """Display the same saved bags and overrides consumed by execution.

    A known server/template default describes omitted settings; it never adds
    a synthetic override to the outbound request.
    """
    from workbench_backend.agents.setup_schemas import ResolvedSetting
    from workbench_backend.inference.configuration_options import bundle_configuration_options
    from workbench_backend.inference.schemas import GgufRuntimeMetadata

    deployment = manager.store.get_deployment(configuration.deployment_id or "")
    profile = manager.store.get_profile(configuration.profile_id or "")
    inherited = profile is None and configuration.inherit_deployment_settings is not False
    bags = profile.bags if profile else deployment.settings if deployment and inherited else SettingsBags()
    selected_source = f"Configuration: {profile.display_name}" if profile else "Loaded model" if deployment and inherited else "Model default"
    source_id = profile.id if profile else deployment.id if deployment else None
    result = {}
    metadata = GgufRuntimeMetadata()
    # Metadata is only needed when no loaded server template is available.
    bundle_id = configuration.bundle_id or (deployment.bundle_id if deployment else None)
    options = None
    if bundle_id and hasattr(manager, "get_bundle_configuration_options"):
        try:
            options = manager.get_bundle_configuration_options(bundle_id, deployment_id=deployment.id if deployment else None)
        except Exception:
            # A missing/offline model remains editable. Unknown values remain unknown.
            pass
    if options is None:
        options = bundle_configuration_options(bundle_id or "", metadata, deployment=deployment)
    defaults = {"startup": {**options.startup_defaults, "ctx_size": options.context_size}, "per_request": options.per_request_defaults}
    for bag_name, selected, overrides in (("startup", bags.startup.requested, configuration.startup_overrides or {}),
            ("per_request", bags.per_request.requested, configuration.per_request_overrides or {})):
        requested = {**selected, **overrides}
        keys = set(requested) | set(defaults[bag_name])
        for key in keys:
            path = f"{bag_name}.{key}"
            descriptor = defaults[bag_name].get(key)
            value = requested.get(key)
            is_default = value is None or (key == "reasoning_effort" and value == "default") or (key == "reasoning" and value == "auto")
            origin = provenance.get(path)
            source = origin.source if origin else selected_source
            known = True
            if is_default:
                if descriptor and descriptor.default_value is not None:
                    value, source = descriptor.default_value, descriptor.default_source or descriptor.source
                elif descriptor and descriptor.observed is not None:
                    value, source = descriptor.observed, "Loaded model"
                elif descriptor and descriptor.applied not in (None, "auto", "default"):
                    value, source = descriptor.applied, descriptor.source
                else:
                    value, source, known = None, "Model default", False
            default_value = descriptor.default_value if descriptor else None
            default_source = descriptor.default_source if descriptor else None
            if descriptor and default_value is None and descriptor.applied not in (None, "auto", "default"):
                default_value, default_source = descriptor.applied, descriptor.source
            parent_value = origin.inherited_value if origin and origin.inherited_source else selected.get(key)
            parent_source = origin.inherited_source if origin and origin.inherited_source else selected_source
            if parent_value is None or (key == "reasoning_effort" and parent_value == "default") or (key == "reasoning" and parent_value == "auto"):
                parent_value, parent_source = default_value, default_source
            reload = False
            if bag_name == "startup" and deployment and key in requested:
                normalized = resolve_bags(startup={**selected, **overrides}).startup.applied
                loaded = deployment.applied_startup.get(key)
                reload = normalized.get(key) != loaded
            result[path] = ResolvedSetting(value=value, source=source, source_id=origin.source_id if origin else source_id,
                inherited=origin.inherited if origin else True, known=known, requires_reload=reload,
                requested_override=origin.requested_override if origin else None,
                default_value=default_value, default_source=default_source,
                inherited_value=parent_value, inherited_source=parent_source,
                supported=descriptor.supported if descriptor else None,
                unavailable_reason=descriptor.description if descriptor and descriptor.supported is False else None)
    return result


def resolve_effective_setup(
    *,
    deployment: Deployment,
    profile: RunProfile | None,
    knowledge_refs: KnowledgeRefs,
    knowledge_versions: list[KnowledgeVersion],
    surface_system_prompt: str | None,
    default_system_prompt: str,
    per_request_overrides: dict[str, Any] | None = None,
    startup_overrides: dict[str, Any] | None = None,
    embedding_deployment: Deployment | None = None,
    selected_embedding_deployment_id: str | None = None,
    retrieval_requested: bool = False,
    retrieval_presented: bool = False,
    retrieval_corpus_documents: int = 0,
    retrieval_instructions: str | None = None,
    materialized_knowledge: list[MaterializedKnowledgeFact] | None = None,
    inherit_deployment_settings: bool = True,
    instruction_layers: list[InstructionLayer] | None = None,
    selected_project_id: str | None = None,
    selected_agent_setup_id: str | None = None,
    selected_agent_setup_version_id: str | None = None,
    selected_connection_ids: list[str] | None = None,
) -> EffectiveSetup:
    """Resolve bags, startup mismatch and knowledge content before execution."""

    if not (deployment.endpoint or "").strip():
        raise HarnessError(
            "Deployment has no endpoint. The adapter does not start inference.",
            code="no_endpoint",
            status_code=409,
        )
    missing = _missing_versions(knowledge_refs, knowledge_versions)
    if missing:
        raise HarnessError(
            "Unknown knowledge version",
            code="knowledge_version_missing",
            status_code=404,
            details={"missing_version_ids": missing},
        )
    # A saved setup is a snapshot. Only an explicitly selected profile resolves
    # its current values; opting out clears both response and agent preset bags.
    inherited = profile is None and inherit_deployment_settings
    per_request = _resolve_per_request(profile, deployment, per_request_overrides, inherit_deployment_settings)
    validate_model_reasoning(deployment, per_request)
    agent = deployment.settings.agent if inherited else _resolve_agent(profile)
    startup_selected = deployment.settings.startup if inherited else _resolve_startup(profile)
    if startup_overrides:
        startup_requested = {**startup_selected.requested, **startup_overrides}
        startup_selected = resolve_bags(startup={
            key: value for key, value in startup_requested.items() if value is not None
        }).startup
    mismatches = _startup_mismatches(startup_selected, deployment.applied_startup)
    loaded = [_loaded_fact(version) for version in knowledge_versions]
    system_prompt = compose_system_prompt(
        surface_system_prompt=surface_system_prompt,
        profile_system_prompt=(agent.applied.get("system_prompt") if isinstance(agent.applied.get("system_prompt"), str) else None),
        default_system_prompt=default_system_prompt,
        versions=knowledge_versions,
        retrieval_instructions=retrieval_instructions,
        instruction_layers=instruction_layers,
    )
    gaps: list[str] = []
    if retrieval_presented:
        pass
    elif retrieval_requested:
        gaps.append(RECORDED_RETRIEVAL_GAP)
    else:
        gaps.append(NO_RETRIEVAL_GAP)
    if not knowledge_refs.memory_version_refs:
        gaps.append(MEMORY_GAP)
    else:
        gaps.append(MEMORY_EDIT_GAP)
    if not knowledge_refs.skill_version_refs:
        gaps.append(SKILL_GAP)
    bags = SettingsBags(
        startup=startup_selected,
        per_request=per_request,
        agent=agent,
    )
    return EffectiveSetup(
        selected_project_id=selected_project_id,
        selected_agent_setup_id=selected_agent_setup_id,
        selected_agent_setup_version_id=selected_agent_setup_version_id,
        selected_connection_ids=list(selected_connection_ids or []),
        instruction_layers=list(instruction_layers or []),
        selected_profile_id=profile.id if profile is not None else deployment.profile_id if inherited else None,
        selected_deployment_id=deployment.id,
        selected_embedding_deployment_id=(
            selected_embedding_deployment_id
            or (embedding_deployment.id if embedding_deployment is not None else None)
        ),
        selected_memory_version_ids=list(knowledge_refs.memory_version_refs),
        selected_skill_version_ids=list(knowledge_refs.skill_version_refs),
        selected_protected_instruction_version_ids=list(
            knowledge_refs.protected_instruction_version_refs
        ),
        loaded_deployment_id=deployment.id,
        loaded_embedding_deployment_id=(
            embedding_deployment.id if embedding_deployment is not None else None
        ),
        loaded_embedding_endpoint=(
            embedding_deployment.endpoint if embedding_deployment is not None else None
        ),
        loaded_startup=dict(deployment.applied_startup),
        loaded_knowledge=loaded,
        materialized_knowledge=list(materialized_knowledge or []),
        retrieval_requested=retrieval_requested,
        retrieval_presented=retrieval_presented,
        retrieval_corpus_documents=retrieval_corpus_documents,
        bags=bags,
        startup_mismatches=mismatches,
        unsupported={
            "startup": list(startup_selected.unsupported),
            "per_request": list(per_request.unsupported),
            "agent": list(agent.unsupported),
        },
        overridden={
            "startup": [item.model_dump(mode="json") for item in startup_selected.overridden],
            "per_request": [item.model_dump(mode="json") for item in per_request.overridden],
            "agent": [item.model_dump(mode="json") for item in agent.overridden],
        },
        retired={
            "startup": [item.model_dump(mode="json") for item in startup_selected.retired],
        },
        system_prompt=system_prompt,
        gaps=gaps,
        knowledge_binding=knowledge_refs.binding(),
    )


SURFACE_PROMPT_HEADING = "## Surface instructions"


def compose_system_prompt(
    *,
    surface_system_prompt: str | None,
    profile_system_prompt: str | None,
    default_system_prompt: str,
    versions: list[KnowledgeVersion],
    retrieval_instructions: str | None = None,
    instruction_layers: list[InstructionLayer] | None = None,
) -> str:
    """Prefer the profile identity prompt; compose the surface prompt after it.

    A Chat (or other surface) system prompt must not silently replace
    ``profile.bags.agent.applied['system_prompt']``. When both are set and
    differ, the profile prompt is the base and the surface prompt is appended
    under ``SURFACE_PROMPT_HEADING``. Protected-instruction content is
    appended after that. Memory and skill bodies are not appended here;
    Deep Agents injects them via ``memory=`` / ``skills=``.
    """

    profile = (profile_system_prompt or "").strip() or None
    surface = (surface_system_prompt or "").strip() or None
    if instruction_layers:
        sections = [default_system_prompt]
        if profile:
            sections.append(f"## Model preset instructions\n{profile}")
        sections.extend(f"## {layer.name}\n{layer.content}" for layer in instruction_layers)
        if surface and surface not in {layer.content for layer in instruction_layers}:
            sections.append(f"{SURFACE_PROMPT_HEADING}\n{surface}")
        base = "\n\n".join(sections)
    elif profile and surface and surface != profile:
        base = f"{profile}\n\n{SURFACE_PROMPT_HEADING}\n{surface}"
    elif profile:
        base = profile
    elif surface:
        base = surface
    else:
        base = default_system_prompt
    retrieval = (retrieval_instructions or "").strip()
    if retrieval:
        base = f"{base}\n\n{retrieval}"
    knowledge_block = format_knowledge_block(versions)
    if not knowledge_block:
        return base
    return f"{base}\n\n{knowledge_block}"


def format_knowledge_block(versions: list[KnowledgeVersion]) -> str:
    protected = [version for version in versions if version.kind == "protected_instruction"]
    if not protected:
        return ""
    sections = [KNOWLEDGE_PREAMBLE]
    for version in protected:
        sections.append(f"### Protected instructions (version {version.id})\n{version.content}")
    return "\n\n".join(sections)


def _profile_system_prompt(profile: RunProfile | None) -> str | None:
    if profile is None:
        return None
    value = profile.bags.agent.applied.get("system_prompt")
    return value if isinstance(value, str) else None


def _resolve_per_request(
    profile: RunProfile | None,
    deployment: Deployment,
    overrides: dict[str, Any] | None,
    inherit_deployment_settings: bool = True,
) -> SettingsBag:
    if profile is not None:
        requested = dict(profile.bags.per_request.requested)
        requested.update(overrides or {})
        return resolve_bag({key: value for key, value in requested.items() if value is not None}, PER_REQUEST_KEYS,
            defaults=deployment.publisher_request_defaults)
    if not inherit_deployment_settings:
        return resolve_bag({key: value for key, value in (overrides or {}).items() if value is not None}, PER_REQUEST_KEYS,
            defaults=deployment.publisher_request_defaults)
    requested = dict(deployment.settings.per_request.requested)
    requested.update(overrides or {})
    if requested:
        return resolve_bag({key: value for key, value in requested.items() if value is not None}, PER_REQUEST_KEYS,
            defaults=deployment.publisher_request_defaults)
    if deployment.publisher_request_defaults:
        return resolve_bag({}, PER_REQUEST_KEYS, defaults=deployment.publisher_request_defaults)
    return deployment.settings.per_request


def _resolve_agent(profile: RunProfile | None) -> SettingsBag:
    if profile is None:
        return SettingsBag()
    return profile.bags.agent


def _resolve_startup(profile: RunProfile | None) -> SettingsBag:
    """Re-resolve the selected startup bag from its requested keys.

    The stored bag was resolved when the profile was saved; a key the pinned
    runtime has since retired (``mlock``, ``no_mmap``) would otherwise still
    sit in ``applied`` and never be reported here.
    """
    if profile is None:
        return SettingsBag()
    return resolve_bags(startup=profile.bags.startup.requested).startup


def _startup_mismatches(
    selected: SettingsBag,
    loaded_startup: dict[str, Any],
) -> list[StartupMismatch]:
    mismatches: list[StartupMismatch] = []
    for key, requested in selected.requested.items():
        if key not in STARTUP_KEYS:
            continue
        selected_value = selected.applied.get(key, requested)
        loaded_value = loaded_startup.get(key)
        if selected_value != loaded_value:
            mismatches.append(
                StartupMismatch(key=key, selected=selected_value, loaded=loaded_value)
            )
    return mismatches


def _loaded_fact(version: KnowledgeVersion) -> LoadedKnowledgeFact:
    return LoadedKnowledgeFact(
        version_id=version.id,
        entry_id=version.entry_id,
        kind=version.kind,
        content_digest=content_digest(version.content),
        content_available=True,
        selected=True,
    )


def _missing_versions(refs: KnowledgeRefs, versions: list[KnowledgeVersion]) -> list[str]:
    present = {item.id for item in versions}
    return [version_id for version_id in refs.all_ids() if version_id not in present]
