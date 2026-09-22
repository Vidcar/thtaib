"""Read-only lifecycle projections over the existing record owners."""
from __future__ import annotations

from typing import Any

from workbench_backend.contracts.lifecycle import is_run_lifecycle_live
from workbench_backend.errors import WorkbenchError
from workbench_backend.inference.schemas import DeletePreview, LifecycleConsumer


def _field(value: Any, name: str, default: Any = None) -> Any:
    return value.get(name, default) if isinstance(value, dict) else getattr(value, name, default)


def _knowledge_refs(value: Any) -> set[str]:
    return {ref for field in ("memory_version_refs", "skill_version_refs", "protected_instruction_version_refs", "knowledge_version_refs")
            for ref in (_field(value, field, []) or [])}


class DependencyPreviewService:
    """Explain deactivation without deleting versions or granting permissions."""

    def __init__(self, store: Any, setups: Any, knowledge: Any, connections: Any, lab: Any = None):
        self.store, self.setups, self.knowledge, self.connections, self.lab = store, setups, knowledge, connections, lab

    def preview(self, kind: str, target_id: str) -> DeletePreview:
        versions: set[str] = set()
        project_path = None
        if kind == "project":
            target = self.setups.get_project(target_id)
            label, project_path = target.name, target.path
            summary = "Remove this project's active binding. Its folder, conversations and scoped knowledge are retained. Future work must use an active project binding."
        elif kind == "agent_setup":
            target = self.setups.get_setup(target_id)
            label = target.name
            versions = {version.id for version in self.store.list_agent_setup_versions(target_id)}
            summary = "Remove this reusable agent from selection. Its saved versions, conversations and run evidence are retained; future starts using it require another active agent."
        elif kind == "knowledge":
            target = self.knowledge.get_entry(target_id)
            label = target.display_name or target.kind.replace("_", " ").title()
            versions = {version.id for version in self.knowledge.list_versions(target_id)}
            kind = "skill_package" if target.kind == "skill" else "knowledge"
            summary = "Remove or disable this knowledge selection for future work. Saved versions and skill resources remain available for historical inspection; active runs retain their selected content."
        elif kind in {"connection", "credential"}:
            target = self.connections.get(target_id)
            label = target.name
            summary = ("Remove this connection's locally saved access token. This does not revoke the token at the provider. " if kind == "credential" else "Disconnect this connection from future use. ")
            summary += "Existing remote work is not cancelled or undone. Later calls recheck the connection and stop when its saved configuration changes."
        else:
            raise ValueError("Unsupported workspace lifecycle target")
        result = DeletePreview(target_kind=kind, target_id=target_id, target_label=label, summary=summary,
            retained=["Historical conversations and run evidence", "Saved versions and scope identities", "Project source files and retained originals", "Existing backups"])
        seen: set[tuple[str, str]] = set()

        def add(consumer_kind: str, ident: str, name: str | None, *, live: bool = False, future: bool = False, effect: str):
            if (consumer_kind, ident) in seen:
                return
            seen.add((consumer_kind, ident))
            result.consumers.append(LifecycleConsumer(kind=consumer_kind, id=ident, label=name or ident,
                live=live, future_use=future, retained=True, effect=effect))

        def uses(value: Any) -> bool:
            if kind == "project":
                return (target_id in {_field(value, "project_id"), _field(value, "area_id")}
                    or project_path in {_field(value, "project_path"), _field(value, "area_project_path")})
            if kind == "agent_setup":
                return _field(value, "agent_setup_id") == target_id or _field(value, "agent_setup_version_id") in versions
            if kind in {"knowledge", "skill_package"}:
                return bool(_knowledge_refs(value) & versions)
            return target_id in (_field(value, "connection_ids", []) or [])

        def needs_for_future(value: Any) -> bool:
            return uses(value) and (kind not in {"connection", "credential"} or _field(value, "presented_tools") != [])

        def configuration_consumer(config: Any, consumer_kind: str, ident: str, name: str, active: bool):
            if uses(config):
                future = active and needs_for_future(config)
                add(consumer_kind, ident, name, future=future,
                    effect="This saved selection needs updating before future work." if future else "Saved selection is retained; it is currently inactive or tools are off.")

        configuration_consumer(self.store.get_setup_defaults(), "setup_defaults", "application", "Application defaults", True)
        for project in self.store.list_projects():
            configuration_consumer(project.defaults, "project", project.id, project.name, project.active)
        for setup in self.store.list_agent_setups():
            for version in self.store.list_agent_setup_versions(setup.id):
                configuration_consumer(version.configuration, "agent_setup_version", version.id, version.name, setup.active)
                if kind == "agent_setup" and setup.id == target_id:
                    add("agent_setup_version", version.id, version.name, effect="Retained saved version; removal prevents new starts from this agent.")

        for run in self.store.list_runs():
            if not uses(run):
                continue
            live = is_run_lifecycle_live(run.status)
            if kind in {"connection", "credential"}:
                selected = set(run.presented_tools)
                in_use = any(snapshot.id == target_id and selected.intersection(tool.name for tool in snapshot.tools) for snapshot in run.connection_snapshots)
                effect = ("A current run selected this connection. Its next remote call will recheck availability; work already sent is not cancelled."
                    if live and in_use else "Retained run selection and tool evidence; no remote cancellation is implied.")
            else:
                effect = "Current run keeps its recorded selection; this action does not cancel it." if live else "Historical run evidence is retained."
            add("agent_run", run.id, run.task[:120], live=live, effect=effect)

        for conversation in self.store.list_conversations(include_archived=True):
            try:
                effective = self.setups.resolve(project_id=conversation.project_id, agent_setup_version_id=conversation.agent_setup_version_id,
                    overrides=conversation.setup_overrides, override_cleared_fields=conversation.setup_cleared_fields, validate=False).configuration
            except WorkbenchError:
                effective = conversation.setup_overrides
            configured = uses(conversation) if kind in {"project", "agent_setup"} else uses(effective)
            retained_selection = uses(conversation)
            if configured or retained_selection:
                future = not conversation.archived and configured and (kind not in {"connection", "credential"} or effective.presented_tools != [])
                add("chat", conversation.id, conversation.title or conversation.area_label or "Conversation", future=future,
                    live=bool(conversation.current_run_id and (run := self.store.get_run(conversation.current_run_id)) and is_run_lifecycle_live(run.status)),
                    effect="Future turns need an updated selection; conversation history is retained." if future else "Earlier or inactive conversation selection is retained.")
            for item in conversation.queue:
                config = {**effective.model_dump(), **(item.frozen_config or item.intended_config)}
                config.setdefault("project_id", conversation.project_id)
                config.setdefault("agent_setup_version_id", conversation.agent_setup_version_id)
                if uses(config):
                    add("chat_queue", item.id, item.task[:120], future=needs_for_future(config),
                        effect="This queued message will validate its selections before dispatch; no queued work is silently replayed.")

        for entry in self.knowledge.store.list_entries():
            scope_affected = (kind == "project" and entry.scope == "project" and entry.scope_id == target_id
                or kind == "agent_setup" and entry.scope == "agent" and entry.scope_id == target_id)
            if scope_affected:
                add("knowledge", entry.id, entry.display_name or entry.kind.replace("_", " "), future=entry.active and entry.enabled,
                    effect="Knowledge and versions retain their exact scope; future loading or editing requires that scope to be active.")
            if kind in {"knowledge", "skill_package"} and entry.id == target_id:
                for version in self.knowledge.list_versions(entry.id):
                    add("knowledge_version", version.id, f"Saved {entry.kind.replace('_', ' ')} version ({len(version.resources)} resources)",
                        effect="Content and package resources are retained for historical inspection.")
        for proposal in self.knowledge.store.list_proposals():
            if ((kind in {"knowledge", "skill_package"} and proposal.entry_id == target_id)
                or (kind == "project" and proposal.scope == "project" and proposal.scope_id == target_id)
                or (kind == "agent_setup" and proposal.scope == "agent" and proposal.scope_id == target_id)):
                add("memory_proposal", proposal.id, proposal.display_name or "Memory proposal", future=proposal.status == "pending",
                    effect="The proposal is retained; accepting it rechecks its destination and version.")
        for policy in self.knowledge.get_config().automatic_save_policies:
            if ((kind == "project" and policy.scope == "project" and policy.scope_id == target_id)
                or (kind == "agent_setup" and policy.scope == "agent" and policy.scope_id == target_id)):
                add("automatic_save_policy", f"{policy.scope}:{policy.scope_id}", "Automatic memory saving", future=policy.automatic_agent_writes,
                    effect="The exact scope permission is retained, but cannot authorize writes to an inactive scope.")
        if self.lab is not None:
            for case in self.lab.list_cases():
                if uses(case):
                    add("lab_case", case.id, case.task[:120], future=True,
                        effect="The saved comparison retains its references; a future live run checks unavailable selections.")
        if kind == "skill_package":
            result.retained.append("All retained skill package resources; source packages are not deleted")
        if kind in {"connection", "credential"}:
            result.retained.append("Remote effects and provider-side credentials; no provider revocation or remote undo")
        # Deactivation is allowed even with historical or active references.
        return result


def dependency_preview_for_app(state: Any, kind: str, target_id: str) -> DeletePreview:
    return DependencyPreviewService(state.app_store, state.setups, state.knowledge, state.connections, state.lab).preview(kind, target_id)
