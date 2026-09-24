"""Application-owned project identities and immutable reusable agent setup versions."""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING, Callable

from workbench_backend.agents.setup_schemas import (
    AgentSetupCreateRequest, AgentSetupRecord, AgentSetupUpdateRequest, AgentSetupVersion,
    AgentSetupView, InstructionLayer, ProjectCreateRequest, ProjectFile, ProjectFileContent,
    ProjectFiles, ProjectRecord, ProjectUpdateRequest, ResolvedSetupSelection, SetupConfiguration,
    SetupDependencyIssue, ResolvedSetting,
)
from workbench_backend.agents.tools import ENABLED_TOOL_NAMES
from workbench_backend.errors import HarnessError, KnowledgeError
from workbench_backend.inference.ids import new_id, utc_now

if TYPE_CHECKING:
    from workbench_backend.inference.service import ModelManager
    from workbench_backend.knowledge.service import KnowledgeService
    from workbench_backend.state.store import ApplicationStore


_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".gif"}


def _image_preview(path: Path) -> str | None:
    if path.suffix.casefold() not in _IMAGE_SUFFIXES:
        return None
    from workbench_backend.assets.extraction import image_thumbnail

    try:
        return image_thumbnail(path.read_bytes())
    except (OSError, ValueError):
        return None


class SetupService:
    def __init__(self, store: ApplicationStore, manager: ModelManager, knowledge: KnowledgeService | None = None, *, connection_available: Callable[[str], bool] | None = None, connection_tools: Callable[[str], list[str]] | None = None) -> None:
        self.store = store
        self.manager = manager
        self.knowledge = knowledge
        self.connection_available = connection_available
        self.connection_tools = connection_tools

    def list_projects(self, *, include_inactive: bool = False) -> list[ProjectRecord]:
        return [self._project_view(p) for p in self.store.list_projects() if p.active or include_inactive]

    def get_project(self, project_id: str, *, require_active: bool = False) -> ProjectRecord:
        record = self.store.get_project(project_id)
        if record is None:
            raise HarnessError("This project no longer exists.", code="project_missing", status_code=404)
        if require_active and not record.active:
            raise HarnessError("This project binding was removed. Add its folder again to continue.", code="project_inactive", status_code=409)
        return self._project_view(record)

    def create_project(self, request: ProjectCreateRequest) -> ProjectRecord:
        path = Path(request.path).expanduser().resolve()
        if not path.is_dir():
            raise HarnessError("Choose an existing project folder.", code="project_missing", status_code=400)
        canonical = os.path.normcase(str(path))
        # The application lock serializes aliases within the single backend.
        with self.store._lock:
            existing = next((p for p in self.store.list_projects() if p.canonical_path == canonical), None)
            if existing is not None:
                if not existing.active:
                    existing = existing.model_copy(update={"active": True, "updated_at": utc_now()})
                    self.store.put_project(existing)
                return self._project_view(existing)
            now = utc_now()
            project = ProjectRecord(id=new_id("project"), name=(request.name or path.name or str(path)).strip(), path=str(path), canonical_path=canonical, defaults=request.defaults, created_at=now, updated_at=now)
            return self.store.put_project(project)

    def update_project(self, project_id: str, request: ProjectUpdateRequest) -> ProjectRecord:
        with self.store._lock:
            project = self.get_project(project_id, require_active=True)
            updates = {"updated_at": utc_now()}
            if request.name is not None:
                updates["name"] = request.name.strip()
            if request.defaults is not None:
                updates["defaults"] = request.defaults
            return self.store.put_project(project.model_copy(update=updates))

    def remove_project(self, project_id: str) -> ProjectRecord:
        with self.store._lock:
            project = self.get_project(project_id)
            return self.store.put_project(project.model_copy(update={"active": False, "updated_at": utc_now()}))

    def project_files(self, project_id: str, relative_path: str = "") -> ProjectFiles:
        project = self.get_project(project_id, require_active=True)
        root = Path(project.path).resolve()
        target = (root / relative_path).resolve()
        if not target.is_relative_to(root):
            raise HarnessError("The requested path is outside this project.", code="project_path_denied", status_code=403)
        if not target.is_dir():
            raise HarnessError("This project directory is unavailable.", code="project_directory_missing", status_code=404)
        entries = []
        for child in sorted(target.iterdir(), key=lambda p: (not p.is_dir(), p.name.casefold())):
            # Do not expose aliases that lead outside the selected folder.
            if not child.resolve().is_relative_to(root) or not (child.is_file() or child.is_dir()):
                continue
            entries.append(ProjectFile(name=child.name, path=child.relative_to(root).as_posix(), kind="directory" if child.is_dir() else "file", size_bytes=child.stat().st_size if child.is_file() else None))
        relative = target.relative_to(root).as_posix()
        return ProjectFiles(project_id=project.id, path="" if relative == "." else relative, entries=entries)

    def read_project_file(self, project_id: str, relative_path: str) -> ProjectFileContent:
        """Return captured text for one project file. Does not call the model."""

        from workbench_backend.agents.project_files import TEXT_LIMIT, file_image, project_file

        project = self.get_project(project_id, require_active=True)
        root = Path(project.path).resolve()
        path = project_file(root, relative_path)
        if not path.is_file():
            raise HarnessError("This project file is unavailable.", code="project_file_missing", status_code=404)
        image = file_image(path)
        content = ProjectFileContent(
            project_id=project.id,
            path=path.relative_to(root).as_posix(),
            size_bytes=image.size_bytes,
            text=image.text,
        )
        if image.text is None:
            if image.size_bytes > TEXT_LIMIT:
                content.text_unavailable_reason = "This file is larger than 256 KB, so its text is not shown."
            else:
                content.text_unavailable_reason = "This file is not UTF-8 text, so its text is not shown."
            preview = _image_preview(path)
            if preview is not None:
                content.image_data_url = preview
                content.text_unavailable_reason = None
        return content

    def list_setups(self, *, include_inactive: bool = False) -> list[AgentSetupView]:
        return [self.get_setup(r.id) for r in self.store.list_agent_setups() if r.active or include_inactive]

    def get_setup(self, setup_id: str) -> AgentSetupView:
        record = self.store.get_agent_setup(setup_id)
        if record is None:
            raise HarnessError("This agent setup no longer exists.", code="agent_setup_missing", status_code=404)
        version = self.get_version(record.current_version_id)
        # The standalone preview inherits application defaults just as a run
        # does. Project-specific changes are validated by the scoped resolver.
        effective = self.resolve(overrides=version.configuration, validate=False).configuration
        return AgentSetupView(**record.model_dump(), name=version.name, role=version.role, configuration=version.configuration, missing_dependencies=self.dependencies(effective))

    def get_version(self, version_id: str, *, require_active: bool = False) -> AgentSetupVersion:
        version = self.store.get_agent_setup_version(version_id)
        if version is None:
            raise HarnessError("This agent setup version is missing.", code="agent_setup_version_missing", status_code=404)
        record = self.store.get_agent_setup(version.setup_id)
        if require_active and (record is None or not record.active):
            raise HarnessError("This agent setup was removed. Choose another setup.", code="agent_setup_inactive", status_code=409)
        return version

    def create_setup(self, request: AgentSetupCreateRequest) -> AgentSetupView:
        now = utc_now()
        version = AgentSetupVersion(id=new_id("setupv"), setup_id=new_id("setup"), name=request.name.strip(), role=request.role, configuration=request.configuration, created_at=now)
        record = AgentSetupRecord(id=version.setup_id, current_version_id=version.id, created_at=now, updated_at=now)
        self.store.save_agent_setup(record, version)
        return self.get_setup(record.id)

    def update_setup(self, setup_id: str, request: AgentSetupUpdateRequest) -> AgentSetupView:
        view = self.get_setup(setup_id)
        if not view.active:
            raise HarnessError("This agent setup was removed.", code="agent_setup_inactive", status_code=409)
        now = utc_now()
        version = AgentSetupVersion(id=new_id("setupv"), setup_id=setup_id, previous_version_id=request.base_version, name=request.name.strip(), role=request.role, configuration=request.configuration, created_at=now)
        record = AgentSetupRecord(id=setup_id, current_version_id=version.id, active=True, created_at=view.created_at, updated_at=now)
        self.store.save_agent_setup(record, version, base_version=request.base_version)
        return self.get_setup(setup_id)

    def remove_setup(self, setup_id: str) -> AgentSetupView:
        with self.store._lock:
            view = self.get_setup(setup_id)
            record = AgentSetupRecord.model_validate(view.model_dump()).model_copy(update={"active": False, "updated_at": utc_now()})
            self.store.save_agent_setup(record)
            return self.get_setup(setup_id)

    def duplicate_setup(self, setup_id: str, name: str | None) -> AgentSetupView:
        source = self.get_setup(setup_id)
        return self.create_setup(AgentSetupCreateRequest(name=name or f"{source.name} copy", role=source.role, configuration=source.configuration))

    def dependencies(self, configuration: SetupConfiguration) -> list[SetupDependencyIssue]:
        issues = []
        if configuration.bundle_id and not configuration.deployment_id and not configuration.model_configuration_id:
            issues.append(SetupDependencyIssue(kind="deployment_id", id=configuration.bundle_id, reason="choose a saved deployment for this model"))
        for field, getter in [("deployment_id", self.manager.store.get_deployment), ("embedding_deployment_id", self.manager.store.get_deployment), ("profile_id", self.manager.store.get_profile), ("model_configuration_id", self.manager.store.get_profile), ("bundle_id", self.manager.store.get_bundle)]:
            selected = getattr(configuration, field)
            if selected and getter(selected) is None:
                issues.append(SetupDependencyIssue(kind=field, id=selected, reason="missing"))
        if configuration.bundle_id and configuration.deployment_id:
            deployment = self.manager.store.get_deployment(configuration.deployment_id)
            if deployment is not None and deployment.bundle_id != configuration.bundle_id:
                issues.append(SetupDependencyIssue(kind="bundle_id", id=configuration.bundle_id, reason="the selected deployment uses a different model"))
        for field, kind in [("memory_version_refs", "memory"), ("skill_version_refs", "skill"), ("protected_instruction_version_refs", "protected_instruction")]:
            for ref in getattr(configuration, field) or []:
                try:
                    version = self.knowledge.get_version(ref) if self.knowledge else None
                    if version is None or version.kind != kind:
                        issues.append(SetupDependencyIssue(kind=kind, id=ref, reason="missing" if version is None else "wrong kind"))
                    elif self.knowledge is not None:
                        entry = self.knowledge.get_entry(version.entry_id)
                        if not entry.active or not entry.enabled:
                            issues.append(SetupDependencyIssue(kind=kind, id=ref, reason="disabled or removed"))
                        elif not any(s.scope == entry.scope and s.scope_id == entry.scope_id for s in self.knowledge.scope_options()):
                            issues.append(SetupDependencyIssue(kind=kind, id=ref, reason="scope is missing or inactive"))
                except KnowledgeError:
                    issues.append(SetupDependencyIssue(kind=kind, id=ref, reason="missing"))
        available_tools = set(ENABLED_TOOL_NAMES)
        if configuration.embedding_deployment_id:
            # Retrieval is constructed by the harness for the selected embedder,
            # rather than being a permanently enabled catalogue tool.
            from workbench_backend.agents.retrieval import SEARCH_KNOWLEDGE_TOOL_NAME
            available_tools.add(SEARCH_KNOWLEDGE_TOOL_NAME)
        for connection in (configuration.connection_ids or []) if configuration.presented_tools != [] else []:
            if self.connection_available is None or not self.connection_available(connection):
                issues.append(SetupDependencyIssue(kind="connection", id=connection, reason="missing, disconnected or needs a successful test"))
            elif self.connection_tools is not None:
                available_tools.update(self.connection_tools(connection))
        for tool in configuration.presented_tools or []:
            if tool not in available_tools:
                issues.append(SetupDependencyIssue(kind="tool", id=tool, reason="not in the current selected catalogue"))
        return issues

    def resolve(self, *, project_id: str | None = None, agent_setup_version_id: str | None = None, overrides: SetupConfiguration | None = None, override_cleared_fields: list[str] | None = None, validate: bool = True, editing_layer: str = "conversation", prepare_model: bool = False) -> ResolvedSetupSelection:
        project = self.get_project(project_id, require_active=True) if project_id else None
        version = self.get_version(agent_setup_version_id, require_active=True) if agent_setup_version_id else None
        layers = [("Application defaults", None, overrides or SetupConfiguration())] if editing_layer == "application" else [("Application defaults", None, self.store.get_setup_defaults())]
        if project and editing_layer != "application":
            layers.append((f"Project: {project.name}", project.id, (overrides or SetupConfiguration()) if editing_layer == "project" else project.defaults))
        elif editing_layer == "project":
            layers.append(("Project", None, overrides or SetupConfiguration()))
        if version and editing_layer not in {"application", "project"}:
            layers.append((f"Agent: {version.name}", version.id, (overrides or SetupConfiguration()) if editing_layer == "agent" else version.configuration))
        elif editing_layer == "agent":
            layers.append(("Agent", None, overrides or SetupConfiguration()))
        if overrides is not None and editing_layer == "conversation":
            layers.append(("Turn overrides", None, overrides))
        values = {}
        effective = {}
        builtin_values = {"approval_mode": "ask", "work_mode": "work", "helper_agent_ids": [], "connection_ids": []}
        instructions = []
        protected = []
        for name, source_id, configuration in layers:
            explicit = configuration.model_dump(exclude_none=True)
            self._resolve_model_selector_layer(values, effective, explicit)
            if configuration.inherit_deployment_settings is False and configuration.profile_id is None:
                values.pop("profile_id", None)
            for key, value in explicit.items():
                prior = effective.get(key)
                effective[key] = ResolvedSetting(value=value, source=name, source_id=source_id,
                    inherited=(name != layers[-1][0] or configuration is not overrides),
                    requested_override=value if configuration is overrides else None,
                    inherited_value=prior.value if prior else builtin_values.get(key),
                    inherited_source=prior.source if prior else "Application default" if key in builtin_values else None)
                if key == "instructions":
                    if value.strip():
                        instructions.append(InstructionLayer(name=name, source_id=source_id, content=value.strip()))
                elif key == "protected_instruction_version_refs":
                    protected.extend(ref for ref in value if ref not in protected)
                elif key in {"requires_project", "requires_host_shell"}:
                    # Requirements are restrictions, not optional scalar preferences.
                    values[key] = bool(values.get(key) or value)
                    effective[key].value = values[key]
                elif key in {"per_request_overrides", "startup_overrides"}:
                    values[key] = {**values.get(key, {}), **value}
                    prefix = "per_request" if key == "per_request_overrides" else "startup"
                    for setting, selected in value.items():
                        path = f"{prefix}.{setting}"
                        parent = effective.get(path)
                        effective[path] = ResolvedSetting(value=selected, source=name, source_id=source_id,
                            inherited=(configuration is not overrides), requested_override=selected if configuration is overrides else None,
                            inherited_value=parent.value if parent else None, inherited_source=parent.source if parent else None)
                else:
                    values[key] = value
        if protected:
            values["protected_instruction_version_refs"] = protected
            effective["protected_instruction_version_refs"].value = protected
        for key in override_cleared_fields or []:
            if key in {"profile_id", "embedding_deployment_id"}:
                values[key] = None
        configuration_id = values.get("model_configuration_id")
        if not any(values.get(key) for key in ("bundle_id", "profile_id", "deployment_id", "model_configuration_id")) and hasattr(self, "manager") and editing_layer == "conversation":
            ready = [item for item in self.manager.store.list_deployments() if item.status.value == "running" and item.health and item.health.healthy
                and (item.scope.value == "connected" or item.process_identity is not None)]
            if ready:
                selected = max(ready, key=lambda item: item.updated_at)
                values.update(deployment_id=selected.id, bundle_id=selected.bundle_id)
                effective["deployment_id"] = ResolvedSetting(value=selected.id, source="Loaded model", source_id=selected.id, inherited=True)
        if not configuration_id and values.get("bundle_id") and not values.get("deployment_id") and hasattr(self, "manager"):
            self.manager.list_model_configurations(values["bundle_id"])
            bundle = self.manager.store.get_bundle(values["bundle_id"])
            configuration_id = bundle.default_configuration_id if bundle else None
            if configuration_id:
                values["model_configuration_id"] = configuration_id
                effective["model_configuration_id"] = ResolvedSetting(value=configuration_id, source="Model default configuration", source_id=bundle.id, inherited=True)
        if configuration_id and hasattr(self, "manager"):
            profile = self.manager.store.get_profile(configuration_id)
            if profile is not None:
                profile = self.manager.canonical_configuration(profile.id)
                values["model_configuration_id"] = profile.id
                if "model_configuration_id" in effective:
                    effective["model_configuration_id"].value = profile.id
                values.update(profile_id=profile.id, bundle_id=profile.bundle_id, inherit_deployment_settings=True)
                selected = self.manager.store.get_deployment(values.get("deployment_id") or "")
                matching = self.manager.configuration_deployment(profile.id)
                if selected is None or selected.bundle_id != profile.bundle_id:
                    selected = matching
                if selected is None and prepare_model:
                    from workbench_backend.inference.schemas import ManagedDeploymentRequest
                    selected = self.manager.create_managed(ManagedDeploymentRequest(bundle_id=profile.bundle_id,
                        profile_id=profile.id, startup=values.get("startup_overrides") or {}, auto_start=False))
                values["deployment_id"] = selected.id if selected else None
                source = effective.get("model_configuration_id")
                for key in ("profile_id", "bundle_id", "deployment_id"):
                    effective[key] = ResolvedSetting(value=values[key], source=source.source if source else "Model configuration", source_id=profile.id,
                        inherited=source.inherited if source else True)
        configuration = SetupConfiguration.model_validate(values)
        for key, value in builtin_values.items():
            if getattr(configuration, key) is None:
                effective[key] = ResolvedSetting(value=value, source="Application default", inherited=True)
        if hasattr(self, "manager"):
            from workbench_backend.agents.effective_setup import effective_setting_values
            effective.update(effective_setting_values(self.manager, configuration, effective))
            effective.update(self._model_selection_facts(configuration, effective))
        if prepare_model and any(value.requires_reload for value in effective.values()):
            raise HarnessError("Apply the changed model settings before sending a message.", code="model_reload_required", status_code=409)
        if validate:
            issues = self.dependencies(configuration)
            if issues:
                raise HarnessError("The selected setup has unavailable dependencies. Update its selections before running.", code="setup_dependencies_missing", status_code=409, details={"missing_dependencies": [i.model_dump() for i in issues]})
            if configuration.bundle_id and configuration.deployment_id:
                deployment = self.manager.store.get_deployment(configuration.deployment_id)
                if deployment is not None and deployment.bundle_id != configuration.bundle_id:
                    raise HarnessError("The selected deployment uses a different model from this setup.", code="setup_model_mismatch", status_code=409)
        return ResolvedSetupSelection(project_id=project_id, agent_setup_id=version.setup_id if version else None, agent_setup_version_id=version.id if version else None, configuration=configuration, instruction_layers=instructions, effective_values=effective)

    def _model_selection_facts(self, configuration: SetupConfiguration, facts: dict) -> dict[str, ResolvedSetting]:
        """Describe the loaded choice and explicit-save target without selecting it.

        A recovered configuration can be the destination of Save to model while
        execution continues to use the loaded snapshot. In particular, looking
        up that destination must not apply a subsequently edited model default.
        """
        from workbench_backend.inference.configurations import requested_identity
        from workbench_backend.inference.settings import resolve_bags

        deployment = self.manager.store.get_deployment(configuration.deployment_id or "")
        profile = self.manager.store.get_profile(configuration.model_configuration_id or configuration.profile_id or "")
        bundle_id = profile.bundle_id if profile and profile.bundle_id else deployment.bundle_id if deployment else configuration.bundle_id
        bundle = self.manager.store.get_bundle(bundle_id or "")
        name = bundle.display_name if bundle else deployment.display_name.removeprefix("managed:").removeprefix("connected:") if deployment else None
        loaded = bool(deployment and deployment.status.value == "running" and deployment.health and deployment.health.healthy
            and (deployment.scope.value == "connected" or deployment.process_identity is not None))
        result = {}
        if name:
            selected_source = facts.get("model_configuration_id") or facts.get("profile_id") or facts.get("deployment_id")
            source = selected_source.source if selected_source else "Selected model"
            if profile is None and source in {"Turn overrides", "Loaded model", "Selected model"}:
                source = "Loaded model" if loaded else "Selected model"
            result["model_selection"] = ResolvedSetting(value=f"{name} · {profile.display_name}" if profile else name,
                source=source, source_id=selected_source.source_id if selected_source else None,
                inherited=selected_source.inherited if selected_source else True)
        if loaded:
            result["loaded_model"] = ResolvedSetting(value=deployment.id, source=name or deployment.display_name,
                source_id=deployment.id, inherited=True)
        target = None
        if bundle:
            configurations = self.manager.list_model_configurations(bundle.id)
            bundle = self.manager.store.get_bundle(bundle.id)
            if profile and profile.bundle_id == bundle.id:
                target = self.manager.canonical_configuration(profile.id)
            elif deployment and deployment.profile_id:
                bound = self.manager.store.get_profile(deployment.profile_id)
                if bound and bound.bundle_id == bundle.id:
                    target = next((item for item in configurations
                        if item.id == bound.id or bound.id in item.equivalent_configuration_ids), None)
            if target is None and deployment:
                loaded_bags = resolve_bags(startup=deployment.requested_startup,
                    per_request=deployment.settings.per_request.requested, agent=deployment.settings.agent.requested)
                matching = [item for item in configurations if requested_identity(item.bags) == requested_identity(loaded_bags)]
                target = next((item for item in matching if item.id == bundle.default_configuration_id), next(iter(matching), None))
            if target is None:
                target = next((item for item in configurations if item.id == bundle.default_configuration_id), None)
        result["model_configuration_target"] = ResolvedSetting(value=target.id if target else None,
            source=f"{bundle.display_name} · {target.display_name}" if target and bundle else "No saved model configuration",
            source_id=target.id if target else None, inherited=True, supported=bool(target),
            unavailable_reason=None if target else "Connected models are configured by their external server." if deployment and deployment.scope.value == "connected" else "Choose a saved model configuration first.")
        return result

    def _resolve_model_selector_layer(self, values: dict, effective: dict, explicit: dict) -> None:
        """A higher model choice cannot be replaced by a lower incompatible one."""
        if explicit.get("model_configuration_id"):
            return
        def clear(key: str) -> None:
            values.pop(key, None)
            effective.pop(key, None)

        if explicit.get("profile_id"):
            clear("model_configuration_id")
            profile = self.manager.store.get_profile(explicit["profile_id"])
            if profile is not None and profile.bundle_id:
                # Legacy bound presets use the same canonical selection owner.
                explicit["model_configuration_id"] = profile.id
            return
        if not explicit.get("deployment_id") and not explicit.get("bundle_id"):
            return
        deployment = self.manager.store.get_deployment(explicit["deployment_id"]) if explicit.get("deployment_id") else None
        bundle_id = explicit.get("bundle_id") or (deployment.bundle_id if deployment else None)
        lower_profile_id = values.get("model_configuration_id") or values.get("profile_id")
        lower_profile = self.manager.store.get_profile(lower_profile_id) if lower_profile_id else None
        if values.get("model_configuration_id") and (lower_profile is None or lower_profile.bundle_id != bundle_id):
            clear("model_configuration_id")
            clear("profile_id")
        elif lower_profile is not None and lower_profile.bundle_id and lower_profile.bundle_id != bundle_id:
            clear("profile_id")
        if explicit.get("deployment_id") and values.get("bundle_id") != bundle_id:
            clear("bundle_id")
        if explicit.get("bundle_id") and not explicit.get("deployment_id"):
            lower_deployment = self.manager.store.get_deployment(values.get("deployment_id") or "")
            if lower_deployment is None or lower_deployment.bundle_id != bundle_id:
                clear("deployment_id")

    @staticmethod
    def _project_view(project: ProjectRecord) -> ProjectRecord:
        return project.model_copy(update={"missing": not Path(project.path).is_dir()})


def configuration_from_request(request) -> SetupConfiguration:
    """Only explicitly supplied values override project/setup defaults."""
    values = {}
    for field in request.model_fields_set:
        if field == "system_prompt":
            continue
        key = field
        if key in SetupConfiguration.model_fields:
            values[key] = getattr(request, field)
    return SetupConfiguration.model_validate(values)


def cleared_configuration_fields(request) -> list[str]:
    return [field for field in ("profile_id", "embedding_deployment_id") if field in request.model_fields_set and getattr(request, field) is None]
