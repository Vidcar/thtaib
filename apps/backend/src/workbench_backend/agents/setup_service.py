"""Application-owned project identities and immutable reusable agent setup versions."""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING, Callable

from workbench_backend.agents.setup_schemas import (
    AgentInputPolicy, AgentSetupCreateRequest, AgentSetupRecord, AgentSetupUpdateRequest, AgentSetupVersion,
    AgentSetupView, InstructionLayer, ProjectCreateRequest, ProjectFile, ProjectFileContent,
    ProjectFiles, ProjectRecord, ProjectUpdateRequest, ResolvedSetupSelection, SetupConfiguration,
    SetupDependencyIssue, ResolvedSetting,
)
from workbench_backend.agents.input_sources import (
    build_input_sources, knowledge_source_id, merge_input_policy, reference_source_mode,
    deferred_reference_issues,
    cold_optional_tool_definitions,
    always_skill_requirements, skill_selection_error,
)
from workbench_backend.agents.tools import enabled_catalogue
from workbench_backend.connections.schemas import ConnectionSnapshot
from workbench_backend.errors import HarnessError, KnowledgeError
from workbench_backend.inference.ids import new_id, utc_now

if TYPE_CHECKING:
    from workbench_backend.inference.service import ModelManager
    from workbench_backend.knowledge.service import KnowledgeService
    from workbench_backend.state.store import ApplicationStore


_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".gif"}

# A project supplies context, never execution authority or a model choice. A
# main agent owns behaviour and capabilities, and may assign a fixed model.
# Chat retains its own inherited model when that assignment is selected.
PROJECT_CONTEXT_FIELDS = frozenset({"memory_version_refs", "skill_version_refs", "memory_entry_ids", "skill_entry_ids", "embedding_deployment_id", "input_policy"})
APPLICATION_DEFAULT_FIELDS = frozenset({"approval_mode"})
MAIN_AGENT_FIELDS = frozenset({
    "instructions", "input_policy", "memory_version_refs", "skill_version_refs",
    "protected_instruction_version_refs", "requires_project", "requires_host_shell",
    "helper_agent_ids", "review",
    "deployment_id", "bundle_id", "model_configuration_id", "profile_id", "inherit_deployment_settings",
    "presented_tools", "connection_ids", "startup_overrides", "per_request_overrides", "embedding_deployment_id",
    "memory_entry_ids", "skill_entry_ids", "protected_instruction_entry_ids",
})


def _image_preview(path: Path) -> str | None:
    if path.suffix.casefold() not in _IMAGE_SUFFIXES:
        return None
    from workbench_backend.assets.extraction import image_thumbnail

    try:
        return image_thumbnail(path.read_bytes())
    except (OSError, ValueError):
        return None


class SetupService:
    def __init__(self, store: ApplicationStore, manager: ModelManager, knowledge: KnowledgeService | None = None, *, connection_available: Callable[[str], bool] | None = None, connection_tools: Callable[[str], list[str]] | None = None, connection_exists: Callable[[str], bool] | None = None, connection_tool_definitions: Callable[[str], list] | None = None) -> None:
        self.store = store
        self.manager = manager
        self.knowledge = knowledge
        self.connection_available = connection_available
        self.connection_tools = connection_tools
        self.connection_exists = connection_exists
        self.connection_tool_definitions = connection_tool_definitions

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
        self._require_project_context_only(request.defaults)
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
        if request.defaults is not None:
            self._require_project_context_only(request.defaults)
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
        # An inactive setup remains inspectable after removal. The resolver
        # rightly rejects it for new work, so inspect its saved dependencies
        # directly instead of treating the removal response as a new choice.
        if record.active:
            main = self.resolve(agent_setup_version_id=version.id, validate=False,
                read_only=True).configuration
            helper = self.resolve(agent_setup_version_id=version.id, validate=False,
                helper_role=True, read_only=True).configuration
        else:
            main = SetupConfiguration.model_validate({key: value for key, value in
                version.configuration.model_dump(exclude_none=True).items() if key in MAIN_AGENT_FIELDS})
            helper = version.configuration
        return AgentSetupView(**record.model_dump(), name=version.name, role=version.role,
            configuration=version.configuration, missing_dependencies=self.dependencies(main),
            helper_missing_dependencies=self.dependencies(helper))

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

    def dependencies(self, configuration: SetupConfiguration, *, frozen: bool = False,
        connection_snapshots: list[ConnectionSnapshot] | None = None,
        project_bound: bool = False) -> list[SetupDependencyIssue]:
        issues: list[SetupDependencyIssue] = []
        selected_versions: list = []
        self._record_missing_model_issues(configuration, issues)
        self._record_knowledge_version_issues(configuration, issues, selected_versions, frozen=frozen)
        available_tools, connection_tool_names, selected_connections = self._record_connection_catalogue(
            configuration, issues, frozen=frozen, connection_snapshots=connection_snapshots)
        self._record_presented_tool_issues(configuration, issues, available_tools, selected_versions)
        return self._record_always_included_skill_issues(
            configuration, issues, selected_versions, connection_tool_names, selected_connections,
            frozen=frozen, project_bound=project_bound, connection_snapshots=connection_snapshots)

    def _plan_tools(self, selected_connections, connection_snapshots=None):
        from workbench_backend.agents.execution_policy import plan_tool_names
        if connection_snapshots is None:
            from workbench_backend.connections.store import ConnectionStore
            connection_store = ConnectionStore(self.store)
            connection_snapshots = [record for ident in selected_connections or []
                if (record := connection_store.get(ident)) is not None and record.enabled]
        return plan_tool_names(connection_snapshots)

    def _record_missing_model_issues(self, configuration: SetupConfiguration, issues: list[SetupDependencyIssue]) -> None:
        if configuration.bundle_id and not configuration.deployment_id and not configuration.model_configuration_id:
            issues.append(SetupDependencyIssue(kind="deployment_id", id=configuration.bundle_id, reason="create or choose a saved setup in Models"))
        for field, getter in [("deployment_id", self.manager.store.get_deployment), ("embedding_deployment_id", self.manager.store.get_deployment), ("profile_id", self.manager.store.get_profile), ("model_configuration_id", self.manager.store.get_profile), ("bundle_id", self.manager.store.get_bundle)]:
            selected = getattr(configuration, field)
            if selected and getter(selected) is None:
                issues.append(SetupDependencyIssue(kind=field, id=selected, reason="missing"))
        if configuration.bundle_id and configuration.deployment_id:
            deployment = self.manager.store.get_deployment(configuration.deployment_id)
            if deployment is not None and deployment.bundle_id != configuration.bundle_id:
                issues.append(SetupDependencyIssue(kind="bundle_id", id=configuration.bundle_id, reason="the selected deployment uses a different model"))

    def _record_knowledge_version_issues(self, configuration: SetupConfiguration, issues: list[SetupDependencyIssue],
        selected_versions: list, *, frozen: bool) -> None:
        for field, kind in [("memory_version_refs", "memory"), ("skill_version_refs", "skill"), ("protected_instruction_version_refs", "protected_instruction")]:
            for ref in getattr(configuration, field) or []:
                try:
                    version = self.knowledge.get_version(ref) if self.knowledge else None
                    if version is None or version.kind != kind:
                        issues.append(SetupDependencyIssue(kind=kind, id=ref, reason="missing" if version is None else "wrong kind"))
                    elif self.knowledge is not None:
                        selected_versions.append(version)
                        if frozen:
                            self.knowledge._require_scope(version.scope, version.scope_id)
                            continue
                        entry = self.knowledge.get_entry(version.entry_id)
                        if not frozen and (not entry.active or not entry.enabled):
                            issues.append(SetupDependencyIssue(kind=kind, id=ref, reason="disabled or removed"))
                        elif not any(s.scope == entry.scope and s.scope_id == entry.scope_id for s in self.knowledge.scope_options()):
                            issues.append(SetupDependencyIssue(kind=kind, id=ref, reason="scope is missing or inactive"))
                except KnowledgeError:
                    issues.append(SetupDependencyIssue(kind=kind, id=ref, reason="missing"))

    def _record_connection_catalogue(self, configuration: SetupConfiguration, issues: list[SetupDependencyIssue], *,
        frozen: bool, connection_snapshots: list[ConnectionSnapshot] | None,
    ) -> tuple[set[str], dict[str, list[str]], list[str] | None]:
        available_tools = set(enabled_catalogue())
        # Document search is a known dynamic capability, including lexical search
        # without an embedder. A saved setup has no turn's attachment selection;
        # Chat/harness admission checks that source scope before presenting it.
        from workbench_backend.agents.retrieval import SEARCH_KNOWLEDGE_TOOL_NAME
        available_tools.add(SEARCH_KNOWLEDGE_TOOL_NAME)
        if configuration.input_policy is not None:
            available_tools.update({"find_tools", "read_reference"})
        if frozen or configuration.helper_agent_ids:
            available_tools.add("task")
        accepted_connections = {item.id: item for item in connection_snapshots} if frozen and connection_snapshots is not None else None
        selected_connections = configuration.connection_ids
        connection_tool_names = {}
        if selected_connections is None and accepted_connections is not None:
            selected_connections = list(accepted_connections)
        for connection in (selected_connections or []) if configuration.presented_tools != [] else []:
            if accepted_connections is not None:
                accepted = accepted_connections.get(connection)
                if accepted is None:
                    issues.append(SetupDependencyIssue(kind="connection", id=connection, reason="not in the accepted connection selection"))
                else:
                    # The accepted catalogue remains immutable. Native runtime
                    # readiness/identity checks still run before disclosure or use.
                    connection_tool_names[connection] = [tool.name for tool in accepted.tools]
                    available_tools.update(connection_tool_names[connection])
                continue
            deferred = bool(configuration.input_policy and configuration.input_policy.tool_loading == "when_needed" and self.connection_exists is not None)
            known = self.connection_exists(connection) if self.connection_exists is not None else None
            if known is False:
                issues.append(SetupDependencyIssue(kind="connection", id=connection, reason="missing, removed or disabled"))
            elif not deferred and (self.connection_available is None or not self.connection_available(connection)):
                issues.append(SetupDependencyIssue(kind="connection", id=connection, reason="missing, disconnected or needs a successful test"))
            elif self.connection_tools is not None:
                connection_tool_names[connection] = self.connection_tools(connection)
                available_tools.update(connection_tool_names[connection])
        return available_tools, connection_tool_names, selected_connections

    def _record_presented_tool_issues(self, configuration: SetupConfiguration, issues: list[SetupDependencyIssue],
        available_tools: set[str], selected_versions: list) -> None:
        for tool in configuration.presented_tools or []:
            if tool not in available_tools:
                issues.append(SetupDependencyIssue(kind="tool", id=tool, reason="not in the current selected catalogue"))
        issues.extend(SetupDependencyIssue(kind=item["code"], id=item["id"], reason=f"{item['message']} {item['action']}")
            for item in deferred_reference_issues(configuration, knowledge_versions=selected_versions))

    def _record_always_included_skill_issues(self, configuration: SetupConfiguration, issues: list[SetupDependencyIssue],
        selected_versions: list, connection_tool_names: dict[str, list[str]], selected_connections: list[str] | None, *,
        frozen: bool, project_bound: bool, connection_snapshots=None) -> list[SetupDependencyIssue]:
        policy = configuration.input_policy
        always_skills = [version for version in selected_versions if version.kind == "skill"
            and reference_source_mode(policy, version.entry_id, "skill") == "always"]
        if not always_skills:
            return issues
        from workbench_backend.agents.tools import resolve_presented_tools
        allowed, _, _, _ = resolve_presented_tools(configuration.presented_tools, project_bound=project_bound,
            knowledge_routes=bool(configuration.memory_version_refs or configuration.skill_version_refs),
            external_names=[name for names in connection_tool_names.values() for name in names])
        if allowed:
            if configuration.helper_agent_ids:
                allowed.append("task")
            if policy is not None and policy.tool_loading == "when_needed":
                allowed.append("find_tools")
            if any(reference_source_mode(policy, version.entry_id, version.kind) == "when_needed" for version in selected_versions):
                allowed.append("read_reference")
        if policy is not None:
            allowed = [name for name in allowed if f"tool:{name}" not in policy.excluded_sources]
        if configuration.work_mode == "plan":
            eligible = self._plan_tools(selected_connections, connection_snapshots if frozen else None)
            allowed = [name for name in allowed if name in eligible]
        allowed_connections = (selected_connections or []) if configuration.presented_tools != [] else []
        for version in always_skills:
            error = skill_selection_error(version, tool_names=allowed, connection_ids=allowed_connections,
                project_bound=project_bound)
            if error is not None:
                issues.append(SetupDependencyIssue(kind=error.code, id=version.entry_id, reason=str(error)))
                continue
            for connection in version.required_connections:
                if not set(connection_tool_names.get(connection, [])).intersection(allowed):
                    reason = f"Enable a tool from required connection {connection} before including this skill."
                elif not frozen and self.connection_available is not None and not self.connection_available(connection):
                    reason = f"Set up required connection {connection} before including this skill."
                else:
                    continue
                issues.append(SetupDependencyIssue(kind="skill_selection_required", id=version.entry_id, reason=reason))
        return issues

    def always_skill_requirements(self, configuration: SetupConfiguration) -> tuple[set[str], set[str]]:
        """Read only exact selected versions; current entry heads never participate."""
        versions = [self.knowledge.get_version(ref) for ref in configuration.skill_version_refs or []] if self.knowledge else []
        return always_skill_requirements(configuration, versions)

    @staticmethod
    def _require_project_context_only(configuration: SetupConfiguration) -> None:
        other = sorted(set(configuration.model_dump(exclude_none=True)) - PROJECT_CONTEXT_FIELDS)
        if other:
            raise HarnessError("Projects can save folder and knowledge context only.",
                code="project_setup_scope", status_code=400, details={"fields": other})
        policy = configuration.input_policy
        if policy is not None:
            execution_fields = policy.model_fields_set - {"version", "reference_loading", "excluded_sources"}
            bad_sources = [source for source in policy.excluded_sources if not source.startswith(("memory:", "skill:", "project_file:")) and source != "project_outline"]
            if execution_fields or bad_sources:
                raise HarnessError("Projects can save reference loading and project-context exclusions only.",
                    code="project_setup_scope", status_code=400)

    @staticmethod
    def require_application_defaults_only(configuration: SetupConfiguration) -> None:
        other = sorted(set(configuration.model_dump(exclude_none=True)) - APPLICATION_DEFAULT_FIELDS)
        if other:
            raise HarnessError("App preferences can seed new chats' Access choice only.",
                code="application_setup_scope", status_code=400, details={"fields": other})

    def resolve(self, *, project_id: str | None = None, agent_setup_version_id: str | None = None, agent_setup_id: str | None = None, overrides: SetupConfiguration | None = None, override_cleared_fields: list[str] | None = None, validate: bool = True, editing_layer: str = "conversation", prepare_model: bool = False, helper_role: bool = False, read_only: bool = False, latest_knowledge: bool = False, include_input_content: bool = False) -> ResolvedSetupSelection:
        project = self.get_project(project_id, require_active=True) if project_id else None
        if agent_setup_id:
            record = self.store.get_agent_setup(agent_setup_id)
            if record is None or not record.active:
                raise HarnessError("This agent was removed. Choose another agent.", code="agent_setup_inactive", status_code=409)
            agent_setup_version_id = record.current_version_id
        version = self.get_version(agent_setup_version_id, require_active=True) if agent_setup_version_id else None
        layers = self._editing_layers(project, version, overrides, editing_layer)
        builtin_values = {"approval_mode": "ask", "work_mode": "work", "desktop_access": "off", "helper_agent_ids": [], "connection_ids": []}
        values, effective, instructions, input_policy = self._merge_editing_layers(
            layers, version, overrides, override_cleared_fields, builtin_values,
            helper_role=helper_role, latest_knowledge=latest_knowledge)
        self._apply_model_configuration(values, effective, read_only=read_only, prepare_model=prepare_model)
        configuration = SetupConfiguration.model_validate(values)
        configuration, preview_versions, excluded_rows = self._resolve_knowledge_preview(
            configuration, effective, input_policy, latest_knowledge=latest_knowledge)
        # A named exclusion can only narrow an explicit capability envelope. The
        # runtime applies the same filter to its project-dependent default tools.
        if configuration.presented_tools is not None:
            configuration = configuration.model_copy(update={"presented_tools": [name for name in configuration.presented_tools if f"tool:{name}" not in input_policy.excluded_sources]})
        self._apply_builtin_effective_settings(
            configuration, effective, builtin_values, read_only=read_only, prepare_model=prepare_model)
        if validate:
            self._raise_for_dependency_issues(configuration, project)
        return self._build_resolved_selection(
            project_id=project_id, version=version, configuration=configuration, instructions=instructions,
            effective=effective, input_policy=input_policy, preview_versions=preview_versions,
            excluded_rows=excluded_rows, values=values, include_input_content=include_input_content)

    def _editing_layers(self, project: ProjectRecord | None, version: AgentSetupVersion | None,
        overrides: SetupConfiguration | None, editing_layer: str,
    ) -> list[tuple[str, str | None, SetupConfiguration, str]]:
        layers = [("Application defaults", None, overrides or SetupConfiguration(), "application")] if editing_layer == "application" else [("Application defaults", None, self.store.get_setup_defaults(), "application")]
        if project and editing_layer != "application":
            layers.append((f"Project: {project.name}", project.id, (overrides or SetupConfiguration()) if editing_layer == "project" else project.defaults, "project"))
        elif editing_layer == "project":
            layers.append(("Project", None, overrides or SetupConfiguration(), "project"))
        if version and editing_layer not in {"application", "project"}:
            layers.append((f"Agent: {version.name}", version.id, (overrides or SetupConfiguration()) if editing_layer == "agent" else version.configuration, "agent"))
        elif editing_layer == "agent":
            layers.append(("Agent", None, overrides or SetupConfiguration(), "agent"))
        if overrides is not None and editing_layer == "conversation":
            layers.append(("Turn overrides", None, overrides, "conversation"))
        return layers

    def _merge_editing_layers(self, layers: list[tuple[str, str | None, SetupConfiguration, str]],
        version: AgentSetupVersion | None, overrides: SetupConfiguration | None,
        override_cleared_fields: list[str] | None, builtin_values: dict, *, helper_role: bool,
        latest_knowledge: bool,
    ) -> tuple[dict, dict, list[InstructionLayer], AgentInputPolicy]:
        values = {}
        effective = {}
        instructions = []
        protected = []
        input_policy = merge_input_policy(None, None)
        for name, source_id, configuration, scope in layers:
            input_policy = self._merge_layer_explicit(name, source_id, configuration, scope, layers=layers,
                version=version, overrides=overrides, helper_role=helper_role, latest_knowledge=latest_knowledge,
                values=values, effective=effective, builtin_values=builtin_values, instructions=instructions,
                protected=protected, input_policy=input_policy)
        if protected:
            values["protected_instruction_version_refs"] = protected
            effective["protected_instruction_version_refs"].value = protected
        values["input_policy"] = input_policy.model_dump()
        for key in override_cleared_fields or []:
            if key in {"profile_id", "embedding_deployment_id"}:
                values[key] = None
        return values, effective, instructions, input_policy

    def _merge_layer_explicit(self, name: str, source_id: str | None, configuration: SetupConfiguration, scope: str, *,
        layers: list[tuple[str, str | None, SetupConfiguration, str]], version: AgentSetupVersion | None,
        overrides: SetupConfiguration | None, helper_role: bool, latest_knowledge: bool, values: dict, effective: dict,
        builtin_values: dict, instructions: list[InstructionLayer], protected: list, input_policy: AgentInputPolicy,
    ) -> AgentInputPolicy:
        explicit = configuration.model_dump(exclude_none=True)
        if latest_knowledge and self.knowledge is not None:
            for entry_field, version_field in (("memory_entry_ids", "memory_version_refs"), ("skill_entry_ids", "skill_version_refs"), ("protected_instruction_entry_ids", "protected_instruction_version_refs")):
                if entry_field not in explicit and version_field in explicit:
                    explicit[entry_field] = list(dict.fromkeys(self.knowledge.get_version(ref).entry_id for ref in explicit[version_field]))
        if scope == "application":
            explicit = {key: value for key, value in explicit.items() if key in APPLICATION_DEFAULT_FIELDS}
        elif scope == "project":
            explicit = {key: value for key, value in explicit.items() if key in PROJECT_CONTEXT_FIELDS}
        elif scope == "agent" and not helper_role:
            explicit = {key: value for key, value in explicit.items() if key in MAIN_AGENT_FIELDS}
        elif scope == "conversation" and version and not helper_role:
            # A Chat draft cannot replace the saved agent's capabilities.
            for key in ("presented_tools", "connection_ids", "helper_agent_ids", "review", "requires_project", "requires_host_shell"):
                explicit.pop(key, None)
            if any(getattr(version.configuration, key) for key in ("deployment_id", "bundle_id", "model_configuration_id")):
                for key in ("deployment_id", "bundle_id", "model_configuration_id", "profile_id", "inherit_deployment_settings"):
                    explicit.pop(key, None)
        self._resolve_model_selector_layer(values, effective, explicit)
        if explicit.get("inherit_deployment_settings") is False and "profile_id" not in explicit:
            values.pop("profile_id", None)
        for key, value in explicit.items():
            prior = effective.get(key)
            effective[key] = ResolvedSetting(value=value, source=name, source_id=source_id,
                inherited=(name != layers[-1][0] or configuration is not overrides),
                requested_override=value if configuration is overrides else None,
                inherited_value=prior.value if prior else builtin_values.get(key),
                inherited_source=prior.source if prior else "Application default" if key in builtin_values else None)
            input_policy = self._merge_explicit_value(key, value, name=name, source_id=source_id,
                configuration=configuration, overrides=overrides, values=values, effective=effective,
                instructions=instructions, protected=protected, input_policy=input_policy)
        return input_policy

    def _merge_explicit_value(self, key: str, value, *, name: str, source_id: str | None,
        configuration: SetupConfiguration, overrides: SetupConfiguration | None, values: dict, effective: dict,
        instructions: list[InstructionLayer], protected: list, input_policy: AgentInputPolicy,
    ) -> AgentInputPolicy:
        if key == "instructions":
            if value.strip():
                instructions.append(InstructionLayer(name=name, source_id=source_id, content=value))
        elif key == "input_policy":
            input_policy = merge_input_policy(input_policy, configuration.input_policy)
            values[key] = input_policy.model_dump()
            effective[key].value = input_policy.model_dump()
        elif key == "protected_instruction_version_refs":
            protected.extend(ref for ref in value if ref not in protected)
        elif key in {"requires_project", "requires_host_shell"}:
            # Requirements are restrictions, not optional scalar preferences.
            values[key] = bool(values.get(key) or value)
            effective[key].value = values[key]
        elif key in {"memory_entry_ids", "skill_entry_ids", "protected_instruction_entry_ids"}:
            values[key] = list(dict.fromkeys([*values.get(key, []), *value]))
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
        return input_policy

    def _apply_model_configuration(self, values: dict, effective: dict, *, read_only: bool, prepare_model: bool) -> None:
        configuration_id = values.get("model_configuration_id")
        if not configuration_id and values.get("bundle_id") and not values.get("deployment_id") and hasattr(self, "manager"):
            # A bundle with no preferred setup remains unselected. Reading or
            # applying it must never manufacture a setup or pick another one.
            bundle = self.manager.store.get_bundle(values["bundle_id"])
            configuration_id = bundle.default_configuration_id if bundle else None
            if configuration_id:
                values["model_configuration_id"] = configuration_id
                effective["model_configuration_id"] = ResolvedSetting(value=configuration_id, source="Model default configuration", source_id=bundle.id, inherited=True)
        if configuration_id and hasattr(self, "manager"):
            profile = self.manager.store.get_profile(configuration_id)
            if profile is not None:
                from workbench_backend.inference.settings import resolve_bags

                profile = self.manager.canonical_configuration(profile.id)
                if profile.bundle_id is None:
                    raise HarnessError("A model configuration must belong to an installed model. Choose a model or a connected server.",
                        code="model_configuration_unbound", status_code=409)
                values["model_configuration_id"] = profile.id
                if "model_configuration_id" in effective:
                    effective["model_configuration_id"].value = profile.id
                values.update(profile_id=profile.id, bundle_id=profile.bundle_id, inherit_deployment_settings=True)
                requested_startup = dict(profile.bags.startup.requested)
                for key, value in (values.get("startup_overrides") or {}).items():
                    if value is None:
                        requested_startup.pop(key, None)
                    else:
                        requested_startup[key] = value
                candidate_bags = profile.bags.model_copy(deep=True)
                candidate_bags.startup = resolve_bags(startup=requested_startup, startup_defaults={
                    key: value for key, value in profile.bags.startup.applied.items()
                    if key not in profile.bags.startup.requested}).startup
                selected = self.manager.compatible_deployment(profile.bundle_id, candidate_bags, require_named_origin=True)
                if selected is None and prepare_model:
                    from workbench_backend.inference.schemas import ManagedDeploymentRequest
                    selected = self.manager.create_managed(ManagedDeploymentRequest(bundle_id=profile.bundle_id,
                        profile_id=profile.id, startup=values.get("startup_overrides") or {}, auto_start=False))
                values["deployment_id"] = selected.id if selected else None
                source = effective.get("model_configuration_id")
                for key in ("profile_id", "bundle_id", "deployment_id"):
                    effective[key] = ResolvedSetting(value=values[key], source=source.source if source else "Model configuration", source_id=profile.id,
                        inherited=source.inherited if source else True)

    def _resolve_knowledge_preview(self, configuration: SetupConfiguration, effective: dict,
        input_policy: AgentInputPolicy, *, latest_knowledge: bool,
    ) -> tuple[SetupConfiguration, list, list]:
        preview_versions = []
        excluded_rows = []
        if self.knowledge is not None:
            from workbench_backend.agents.setup_schemas import InputSourceRow
            from workbench_backend.agents.input_sources import HISTORY_HINT
            for entry_field, version_field, kind in (("memory_entry_ids", "memory_version_refs", "memory"), ("skill_entry_ids", "skill_version_refs", "skill"), ("protected_instruction_entry_ids", "protected_instruction_version_refs", "protected_instruction")):
                ids = getattr(configuration, entry_field)
                if ids is None and latest_knowledge and getattr(configuration, version_field):
                    ids = list(dict.fromkeys(self.knowledge.get_version(ref).entry_id for ref in getattr(configuration, version_field)))
                if ids is not None:
                    included_ids = [entry_id for entry_id in ids if reference_source_mode(input_policy, entry_id, kind) != "off"]
                    for entry_id in ids:
                        if entry_id in included_ids:
                            continue
                        # Off is a control even if the former source was deleted. It
                        # must not resolve a new version or require readable content.
                        entry_metadata = self.knowledge.store.get_entry(entry_id)
                        excluded_rows.append(InputSourceRow(id=knowledge_source_id(entry_id, kind),
                            title=entry_metadata.display_name if entry_metadata and entry_metadata.display_name else f"{kind.replace('_', ' ').title()} {entry_id}", kind=kind,
                            origin=f"{entry_metadata.scope} Knowledge" if entry_metadata else "Inherited Knowledge selection", reason="Excluded for future inputs.",
                            mode="off", entry_id=entry_id, estimated_tokens=0, editable=True, history_hint=HISTORY_HINT))
                    refs = self.knowledge.resolve_entry_refs(**{entry_field: included_ids})
                    configuration = configuration.model_copy(update={entry_field: ids, version_field: list(getattr(refs, version_field))})
                    if version_field in effective:
                        effective[version_field].value = list(getattr(refs, version_field))
                else:
                    refs = []
                    for ref in getattr(configuration, version_field) or []:
                        version_value = self.knowledge.get_version(ref)
                        if reference_source_mode(input_policy, version_value.entry_id, kind) != "off":
                            refs.append(ref)
                        else:
                            excluded_rows.append(InputSourceRow(id=knowledge_source_id(version_value.entry_id, kind),
                                title=version_value.display_name or f"{kind.title()} {version_value.entry_id}", kind=kind,
                                origin=f"{version_value.scope} Knowledge", reason="Excluded for future inputs.",
                                mode="off", entry_id=version_value.entry_id, version_id=version_value.id,
                                estimated_tokens=0, editable=True, history_hint=HISTORY_HINT))
                    configuration = configuration.model_copy(update={version_field: refs})
                preview_versions.extend(self.knowledge.get_version(ref) for ref in getattr(configuration, version_field) or [])
        return configuration, preview_versions, excluded_rows

    def _apply_builtin_effective_settings(self, configuration: SetupConfiguration, effective: dict, builtin_values: dict, *,
        read_only: bool, prepare_model: bool) -> None:
        for key, value in builtin_values.items():
            if getattr(configuration, key) is None:
                effective[key] = ResolvedSetting(value=value, source="Application default", inherited=True)
        if hasattr(self, "manager"):
            from workbench_backend.agents.effective_setup import effective_setting_values
            if not read_only:
                effective.update(effective_setting_values(self.manager, configuration, effective))
            effective.update(self._model_selection_facts(configuration, effective))
        if prepare_model and any(value.requires_reload for value in effective.values()):
            raise HarnessError("Apply the changed model settings before sending a message.", code="model_reload_required", status_code=409)

    def _raise_for_dependency_issues(self, configuration: SetupConfiguration, project: ProjectRecord | None) -> None:
        issues = self.dependencies(configuration, project_bound=bool(project))
        if issues:
            deferred_only = all(issue.kind in {"deferred_reference_tools_off", "deferred_reference_reader_excluded"} for issue in issues)
            deferred_code = "deferred_reference_reader_excluded" if any(issue.kind == "deferred_reference_reader_excluded" for issue in issues) else "deferred_reference_tools_off"
            skill_only = all(issue.kind == "skill_selection_required" for issue in issues)
            raise HarnessError("Choose Include now, Remove, or Enable reading for references set to When needed without an enabled reading route." if deferred_only else
                " ".join(dict.fromkeys(issue.reason for issue in issues)) if skill_only else
                "The selected setup has unavailable dependencies. Update its selections before running.",
                code=deferred_code if deferred_only else "skill_selection_required" if skill_only else "setup_dependencies_missing",
                status_code=409, details={"missing_dependencies": [i.model_dump() for i in issues]})
        if configuration.bundle_id and configuration.deployment_id:
            deployment = self.manager.store.get_deployment(configuration.deployment_id)
            if deployment is not None and deployment.bundle_id != configuration.bundle_id:
                raise HarnessError("The selected deployment uses a different model from this setup.", code="setup_model_mismatch", status_code=409)

    def _build_resolved_selection(self, *, project_id: str | None, version: AgentSetupVersion | None,
        configuration: SetupConfiguration, instructions: list[InstructionLayer], effective: dict,
        input_policy: AgentInputPolicy, preview_versions: list, excluded_rows: list, values: dict,
        include_input_content: bool) -> ResolvedSetupSelection:
        profile = self.manager.store.get_profile(configuration.profile_id or configuration.model_configuration_id or "")
        deployment = self.manager.store.get_deployment(configuration.deployment_id or "")
        from workbench_backend.agents.tools import tool_descriptions
        from workbench_backend.agents.tools import resolve_presented_tools
        preview_tools = values.get("presented_tools")
        if preview_tools is None:
            preview_tools = resolve_presented_tools(None, project_bound=bool(project_id),
                knowledge_routes=bool(configuration.memory_version_refs or configuration.skill_version_refs))[0]
        else:
            preview_tools = list(preview_tools)
        if preview_tools:
            if configuration.helper_agent_ids and "task" not in preview_tools:
                preview_tools.append("task")
            if input_policy.tool_loading == "when_needed" and "find_tools" not in preview_tools:
                preview_tools.append("find_tools")
            if any(reference_source_mode(input_policy, item.entry_id, item.kind) == "when_needed" for item in preview_versions) and "read_reference" not in preview_tools:
                preview_tools.append("read_reference")
        optional, unavailable = cold_optional_tool_definitions(preview_tools, paths=getattr(self.manager, "paths", None))
        if self.connection_tool_definitions is not None:
            for connection_id in configuration.connection_ids or []:
                optional.extend(self.connection_tool_definitions(connection_id))
        if configuration.work_mode == "plan":
            eligible = self._plan_tools(configuration.connection_ids)
            preview_tools = [name for name in preview_tools if name in eligible]
        input_sources = build_input_sources(policy=input_policy, instruction_layers=instructions,
            knowledge_versions=preview_versions, profile=profile, deployment=deployment,
            presented_tools=preview_tools, tool_metadata=tool_descriptions(),
            include_content=include_input_content, selected_agent=bool(version), project_id=project_id,
            extra_tools=optional, tool_unavailable=unavailable)
        input_sources.extend(excluded_rows)
        return ResolvedSetupSelection(project_id=project_id, agent_setup_id=version.setup_id if version else None, agent_setup_version_id=version.id if version else None, configuration=configuration, instruction_layers=instructions, effective_values=effective, input_sources=input_sources)

    def _model_selection_facts(self, configuration: SetupConfiguration, facts: dict) -> dict[str, ResolvedSetting]:
        """Describe the loaded choice and explicit-save target without selecting it.

        A recovered configuration can be the destination of Save to model while
        execution continues to use the loaded snapshot. In particular, looking
        up that destination must not apply a subsequently edited model default.
        """
        deployment, profile, bundle, name, loaded = self._model_selection_identity(configuration)
        result = {}
        if name:
            result["model_selection"] = self._model_selection_setting(facts, profile, name, loaded)
        if loaded:
            result["loaded_model"] = ResolvedSetting(value=deployment.id, source=name or deployment.display_name,
                source_id=deployment.id, inherited=True)
        result["model_configuration_target"] = self._model_configuration_target_setting(bundle, profile, deployment)
        return result

    def _model_selection_identity(self, configuration: SetupConfiguration):
        deployment = self.manager.store.get_deployment(configuration.deployment_id or "")
        profile = self.manager.store.get_profile(configuration.model_configuration_id or configuration.profile_id or "")
        bundle_id = profile.bundle_id if profile and profile.bundle_id else deployment.bundle_id if deployment else configuration.bundle_id
        bundle = self.manager.store.get_bundle(bundle_id or "")
        name = bundle.display_name if bundle else deployment.display_name.removeprefix("managed:").removeprefix("connected:") if deployment else None
        return deployment, profile, bundle, name, self._deployment_counts_as_loaded(deployment)

    @staticmethod
    def _deployment_counts_as_loaded(deployment) -> bool:
        return bool(deployment and deployment.status.value == "running" and deployment.health and deployment.health.healthy
            and (deployment.scope.value == "connected" or deployment.process_identity is not None))

    def _model_selection_setting(self, facts: dict, profile, name, loaded: bool) -> ResolvedSetting:
        selected_source = facts.get("model_configuration_id") or facts.get("profile_id") or facts.get("deployment_id")
        source = selected_source.source if selected_source else "Selected model"
        return ResolvedSetting(value=f"{name} · {profile.display_name}" if profile else name,
            source=self._model_selection_source(source, profile, loaded), source_id=selected_source.source_id if selected_source else None,
            inherited=selected_source.inherited if selected_source else True)

    @staticmethod
    def _model_selection_source(source: str, profile, loaded: bool) -> str:
        if profile is None and source in {"Turn overrides", "Loaded model", "Selected model"}:
            return "Loaded model" if loaded else "Selected model"
        return source

    def _model_configuration_target_setting(self, bundle, profile, deployment) -> ResolvedSetting:
        target = self._model_configuration_target(bundle, profile, deployment)
        return ResolvedSetting(value=target.id if target else None,
            source=f"{bundle.display_name} · {target.display_name}" if target and bundle else "No saved model configuration",
            source_id=target.id if target else None, inherited=True, supported=bool(target),
            unavailable_reason=None if target else "Connected models are configured by their external server." if deployment and deployment.scope.value == "connected" else "Choose a saved model configuration first.")

    def _model_configuration_target(self, bundle, profile, deployment):
        target = None
        if bundle:
            configurations = [item for item in self.manager.store.list_profiles() if item.bundle_id == bundle.id]
            if profile and profile.bundle_id == bundle.id:
                target = self.manager.canonical_configuration(profile.id)
            elif deployment and deployment.profile_id:
                bound = self.manager.store.get_profile(deployment.profile_id)
                if bound and bound.bundle_id == bundle.id:
                    target = next((item for item in configurations if item.id == bound.id), None)
        return target

    def _resolve_model_selector_layer(self, values: dict, effective: dict, explicit: dict) -> None:
        """A higher model choice cannot be replaced by a lower incompatible one."""
        if explicit.get("model_configuration_id"):
            # A configuration selected at this layer must not inherit a lower
            # layer's deployment snapshot. Keep a deployment only when the
            # same layer deliberately pairs it with the configuration, so the
            # caller can apply the changed startup settings to that instance.
            if not explicit.get("deployment_id"):
                values.pop("deployment_id", None)
                effective.pop("deployment_id", None)
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
