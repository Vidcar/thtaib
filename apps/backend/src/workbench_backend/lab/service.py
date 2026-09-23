"""Lab capture → restore → rerun against the shared Deep Agents harness."""

from __future__ import annotations

import importlib.metadata
import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Any

from workbench_backend.agents.harness import HarnessService
from workbench_backend.agents.replay import is_replay_failure
from workbench_backend.agents.setup_schemas import FrozenExecutionSelection, ResolvedSetupSelection, SetupConfiguration
from workbench_backend.agents.schemas import (
    AgentRun,
    AgentRunStatus,
    AgentStartRequest,
    TaskCriteria,
    ToolMode,
    label_for_tool_mode,
)
from workbench_backend.contracts.lifecycle import is_run_lifecycle_live
from workbench_backend.errors import LabError
from workbench_backend.inference.ids import new_id, utc_now
from workbench_backend.inference.service import ModelManager
from workbench_backend.knowledge.schemas import KnowledgeRefs
from workbench_backend.knowledge.service import KnowledgeService
from workbench_backend.lab.export_privacy import build_case_export
from workbench_backend.lab.engine import measure_engine
from workbench_backend.lab.schemas import (
    AppliedConfig,
    CaptureRequest,
    CaseExport,
    EngineMeasureRequest,
    EngineMeasurement,
    LabCase,
    LabResult,
    LabWorkspace,
    RestoreResult,
    RerunRequest,
    SnapshotManifest,
    WorkspaceCreateRequest,
)
from workbench_backend.lab.snapshot import (
    ENVIRONMENT_EXCLUSIONS,
    capture_project_snapshot,
    project_fingerprints,
    read_text_files,
    restore_snapshot_tree,
    write_text_files,
)
from workbench_backend.lab.store import LabStore
from workbench_backend.paths import WorkbenchPaths
from workbench_backend.state.effects import EffectService

DEPENDENCY_PACKAGES = ("deepagents", "langchain", "langgraph", "langchain-openai")


class LabService:
    def __init__(
        self,
        manager_provider: Callable[[], ModelManager],
        harness_provider: Callable[[], HarnessService],
        knowledge_provider: Callable[[], KnowledgeService] | None = None,
        effects_provider: Callable[[], EffectService] | None = None,
    ) -> None:
        self._manager_provider = manager_provider
        self._harness_provider = harness_provider
        self._knowledge_provider = knowledge_provider
        self._effects_provider = effects_provider

    @property
    def manager(self) -> ModelManager:
        return self._manager_provider()

    @property
    def harness(self) -> HarnessService:
        return self._harness_provider()

    @property
    def paths(self) -> WorkbenchPaths:
        return self.manager.paths.ensure()

    @property
    def store(self) -> LabStore:
        return LabStore(self.paths)

    @property
    def knowledge(self) -> KnowledgeService:
        if self._knowledge_provider is not None:
            return self._knowledge_provider()
        return KnowledgeService(self.paths)

    @property
    def effects(self) -> EffectService:
        if self._effects_provider is not None:
            return self._effects_provider()
        return EffectService(self.harness.store)

    def create_workspace(self, request: WorkspaceCreateRequest) -> LabWorkspace:
        now = utc_now()
        workspace = LabWorkspace(
            id=new_id("ws"),
            display_name=request.display_name,
            path="",
            allowlist=request.allowlist,
            origin="created",
            created_at=now,
        )
        workspace.path = str(self._project_dir(workspace.id))
        write_text_files(Path(workspace.path), request.files)
        return self.store.put_workspace(workspace)

    def list_workspaces(self) -> list[LabWorkspace]:
        return self.store.list_workspaces()

    def get_workspace(self, workspace_id: str) -> LabWorkspace:
        workspace = self.store.get_workspace(workspace_id)
        if workspace is None:
            raise LabError("Unknown workspace", code="workspace_missing", status_code=404)
        return workspace

    def write_workspace_files(self, workspace_id: str, files: dict[str, str]) -> LabWorkspace:
        workspace = self.get_workspace(workspace_id)
        write_text_files(Path(workspace.path), files)
        return workspace

    def read_workspace_files(self, workspace_id: str) -> dict[str, str]:
        workspace = self.get_workspace(workspace_id)
        return read_text_files(Path(workspace.path))

    def capture(self, request: CaptureRequest) -> LabCase:
        workspace = self.get_workspace(request.workspace_id)
        active = self.harness.active_workspace_run_ids(workspace.id)
        if active:
            raise LabError(
                f"Capture requires a quiescent boundary; live runs still writing: {', '.join(active)}",
                code="not_quiescent",
                status_code=409,
            )
        run: AgentRun | None = None
        if request.run_id:
            run = self.harness.get_run(request.run_id)
            if is_run_lifecycle_live(run.status):
                raise LabError(
                    "Capture requires a quiescent boundary; the source run is still live "
                    "(cancel_requested is not idle).",
                    code="not_quiescent",
                    status_code=409,
                )
            if run.workspace_id and run.workspace_id != workspace.id:
                raise LabError(
                    "Source run is linked to a different workspace.",
                    code="workspace_mismatch",
                    status_code=409,
                )

        task = (run.task if run else request.task) or ""
        if not task.strip():
            raise LabError("A task is required to capture a case.", code="task_required", status_code=400)
        deployment_id = (run.deployment_id if run else request.deployment_id)
        if not deployment_id:
            raise LabError(
                "A deployment_id is required to capture a case.",
                code="deployment_required",
                status_code=400,
            )

        unresolved = self.effects.unresolved_ids_for_run(run.id if run else None)
        if run is not None:
            manifest = self._starting_snapshot_for_run(run, workspace)
            snapshot_kind = manifest.kind
            input_origin = "starting_snapshot"
            exclusions = manifest.exclusions
        else:
            manifest = capture_project_snapshot(
                self.paths,
                workspace_id=workspace.id,
                project_root=Path(workspace.path),
                kind="final",
                allowlist=request.allowlist or workspace.allowlist,
                unresolved_side_effects=unresolved,
            )
            snapshot_kind = manifest.kind
            input_origin = "capture_time_workspace"
            exclusions = manifest.exclusions
        snapshot_id = manifest.id

        profile_id = run.profile_id if run else request.profile_id
        if profile_id is None and deployment_id:
            deployment = self.manager.store.get_deployment(deployment_id)
            if deployment is not None:
                profile_id = deployment.profile_id

        fixtures = fixtures_from_run(run) if run else []
        criteria = request.criteria or (run.criteria if run else TaskCriteria())
        refs = self._resolve_knowledge_refs(request, run)
        case = LabCase(
            id=new_id("case"),
            snapshot_id=snapshot_id,
            snapshot_kind=snapshot_kind,
            input_origin=input_origin,
            source_run_id=run.id if run else None,
            source_workspace_id=workspace.id,
            task=task,
            profile_id=profile_id,
            deployment_id=deployment_id,
            presented_tools=request.presented_tools if request.presented_tools is not None else (run.presented_tools if run else []),
            system_prompt=run.system_prompt if run else None,
            execution_snapshot=_execution_snapshot(run) if run else None,
            helper_snapshots=list(run.helper_snapshots) if run else [],
            criteria=criteria,
            budgets=run.budgets if run else None,
            tool_fixtures=fixtures,
            acceptance_checks=criteria,
            dependency_versions=dependency_versions(),
            memory_version_refs=refs.memory_version_refs,
            skill_version_refs=refs.skill_version_refs,
            protected_instruction_version_refs=refs.protected_instruction_version_refs,
            exclusions=exclusions,
            environment_exclusions=list(ENVIRONMENT_EXCLUSIONS),
            unresolved_side_effects=unresolved,
            created_at=utc_now(),
            snapshot_path=str(self.paths.snapshots / snapshot_id),
            knowledge=refs.binding(),
            embedding_deployment_id=(
                request.embedding_deployment_id
                if request.embedding_deployment_id is not None
                else (run.embedding_deployment_id if run is not None else None)
            ),
            retrieval_project_paths=(
                list(request.retrieval_project_paths)
                if request.retrieval_project_paths is not None
                else (list(run.retrieval_project_paths) if run is not None else [])
            ),
        )
        return self.store.put_case(case)

    def list_cases(self) -> list[LabCase]:
        return self.store.list_cases()

    def get_case(self, case_id: str) -> LabCase:
        case = self.store.get_case(case_id)
        if case is None:
            raise LabError("Unknown case", code="case_missing", status_code=404)
        return case

    def get_snapshot(self, snapshot_id: str) -> SnapshotManifest:
        path = self.paths.snapshots / snapshot_id / "manifest.json"
        if not path.is_file():
            raise LabError("Unknown snapshot", code="snapshot_missing", status_code=404)
        return SnapshotManifest.model_validate_json(path.read_text(encoding="utf-8"))

    def export_case(self, case_id: str) -> CaseExport:
        case = self.get_case(case_id)
        snapshot = self.get_snapshot(case.snapshot_id)
        return build_case_export(case, snapshot)

    def restore(self, case_id: str) -> RestoreResult:
        case = self.get_case(case_id)
        parent = self.get_workspace(case.source_workspace_id)
        parent_before = project_fingerprints(Path(parent.path))
        snapshot = self.get_snapshot(case.snapshot_id)
        child = LabWorkspace(
            id=new_id("ws"),
            display_name=f"{parent.display_name} (restored)",
            path="",
            allowlist=snapshot.allowlist,
            origin="restored",
            parent_workspace_id=parent.id,
            snapshot_id=snapshot.id,
            case_id=case.id,
            created_at=utc_now(),
        )
        workspace_root = self.paths.workspaces / child.id
        dest = workspace_root / "project"
        try:
            restore_snapshot_tree(
                Path(snapshot.tree_path),
                dest,
                included_files=snapshot.included_files,
            )
        except Exception:
            if workspace_root.exists():
                shutil.rmtree(workspace_root)
            raise
        child.path = str(dest)
        self.store.put_workspace(child)
        parent_after = project_fingerprints(Path(parent.path))
        parent_unchanged = parent_before == parent_after
        unresolved = list(case.unresolved_side_effects)
        deviations = [
            "Restored into a new workspace directory; the parent was not overwritten.",
            "Full environment restore is not this milestone; exclusions are recorded.",
            "Restored inputs do not guarantee an identical model output.",
            "Snapshot restore does not roll back external effects or restore a whole environment.",
        ]
        if case.input_origin == "starting_snapshot":
            deviations.append(
                "Restored files are the source run's starting snapshot, not later parent edits."
            )
        if unresolved:
            deviations.append(
                "Unresolved side effects were preserved; they were not replayed or rolled back."
            )
        if not parent_unchanged:
            deviations.append("Parent workspace fingerprints changed during restore.")
        return RestoreResult(
            workspace=child,
            case_id=case.id,
            parent_workspace_id=parent.id,
            parent_unchanged=parent_unchanged,
            branch={
                "kind": "linked_branch",
                "parent_workspace_id": parent.id,
                "child_workspace_id": child.id,
                "parent_run_id": case.source_run_id or "",
            },
            deviations=deviations,
            snapshot_id=snapshot.id,
            snapshot_kind=snapshot.kind,
            input_origin=case.input_origin,
            unresolved_side_effects=unresolved,
        )

    def rerun(self, case_id: str, request: RerunRequest) -> LabResult:
        case = self.get_case(case_id)
        workspace = self.get_workspace(request.workspace_id)
        if workspace.origin != "restored" or workspace.case_id != case.id:
            raise LabError(
                "Rerun requires a workspace restored from this case. The parent is never overwritten.",
                code="restore_required",
                status_code=409,
            )
        if request.tool_mode is ToolMode.recorded_tool and not case.tool_fixtures:
            raise LabError(
                "recorded-tool mode needs captured fixtures; it is not proof of a live integration.",
                code="recorded_fixtures_required",
                status_code=400,
            )
        parent = self.get_workspace(case.source_workspace_id)
        parent_before = project_fingerprints(Path(parent.path))
        criteria = request.criteria or case.criteria
        presented = request.presented_tools if request.presented_tools is not None else case.presented_tools
        execution_snapshot = case.execution_snapshot.model_copy(deep=True) if case.execution_snapshot else None
        if execution_snapshot is not None:
            execution_snapshot.selection.configuration = execution_snapshot.selection.configuration.model_copy(update={
                "presented_tools": presented,
                "memory_version_refs": case.memory_version_refs,
                "skill_version_refs": case.skill_version_refs,
                "protected_instruction_version_refs": case.protected_instruction_version_refs,
            })
        started = self.harness.start(
            AgentStartRequest(
                deployment_id=case.deployment_id or "",
                profile_id=case.profile_id,
                task=case.task,
                presented_tools=presented,
                system_prompt=case.system_prompt,
                criteria=criteria,
                budgets=case.budgets,
                workspace_id=workspace.id,
                project_path=workspace.path,
                parent_run_id=case.source_run_id,
                source_surface="lab",
                tool_mode=request.tool_mode,
                recorded_fixtures=case.tool_fixtures if request.tool_mode is ToolMode.recorded_tool else None,
                memory_version_refs=case.memory_version_refs,
                skill_version_refs=case.skill_version_refs,
                protected_instruction_version_refs=case.protected_instruction_version_refs,
                embedding_deployment_id=case.embedding_deployment_id,
                retrieval_project_paths=list(case.retrieval_project_paths),
            ),
            execution_snapshot=execution_snapshot,
            helper_snapshot=case.helper_snapshots if execution_snapshot else None,
        )
        parent_after = project_fingerprints(Path(parent.path))
        deviations = [
            "Task evaluation used the shared Deep Agents harness / MOD-005.",
            "Inspect AI building blocks score the harness result; there is no second agent loop.",
            "Restored inputs do not guarantee an identical model output.",
        ]
        if request.tool_mode is ToolMode.recorded_tool:
            deviations.append(
                "recorded-tool results are labelled and are not proof of a current live integration."
            )
        if request.criteria is not None and request.criteria != case.criteria:
            deviations.append("Acceptance checks were overridden for this rerun.")
        if request.presented_tools is not None and request.presented_tools != case.presented_tools:
            deviations.append("Presented tools were overridden for this rerun.")
        if parent_before != parent_after:
            deviations.append("Parent workspace changed during rerun.")
        result = LabResult(
            id=new_id("labr"),
            case_id=case.id,
            workspace_id=workspace.id,
            source_run_id=case.source_run_id,
            agent_run_id=started.id,
            tool_mode=request.tool_mode,
            tool_mode_label=label_for_tool_mode(request.tool_mode),
            recorded_is_not_live_proof=request.tool_mode is ToolMode.recorded_tool,
            applied_config=AppliedConfig(
                deployment_id=case.deployment_id,
                profile_id=started.profile_id,
                approval_mode=started.approval_mode,
                work_mode=started.work_mode,
                presented_tools=presented,
                tool_mode=request.tool_mode,
                system_prompt=case.system_prompt,
                criteria=criteria,
                dependency_versions=case.dependency_versions,
                workspace_id=workspace.id,
                memory_version_refs=case.memory_version_refs,
                skill_version_refs=case.skill_version_refs,
                protected_instruction_version_refs=case.protected_instruction_version_refs,
                knowledge=case.knowledge,
                embedding_deployment_id=case.embedding_deployment_id,
                retrieval_project_paths=list(case.retrieval_project_paths),
            ),
            evidence=_evidence_from_run(started),
            judgement=started.completion.judgement.model_dump() if started.completion else {},
            deviations=deviations,
            parent_workspace_unchanged=parent_before == parent_after,
            created_at=utc_now(),
        )
        return self.store.put_result(result)

    def get_result(self, result_id: str) -> LabResult:
        result = self.store.get_result(result_id)
        if result is None:
            raise LabError("Unknown Lab result", code="result_missing", status_code=404)
        return self._refresh_result(result)

    def list_results(self) -> list[LabResult]:
        return [self._refresh_result(item) for item in self.store.list_results()]

    def _refresh_result(self, result: LabResult) -> LabResult:
        run = self.harness.get_run(result.agent_run_id)
        deviations = list(result.deviations)
        if run.status is AgentRunStatus.failed and is_replay_failure(run.error):
            note = (
                "recorded-tool fixture missing, exhausted, or mismatched — "
                "structured replay failure, not live-equivalent success."
            )
            if note not in deviations:
                deviations.append(note)
        updated = result.model_copy(
            update={
                "evidence": _evidence_from_run(run),
                "judgement": run.completion.judgement.model_dump() if run.completion else result.judgement,
                "deviations": deviations,
            }
        )
        return self.store.put_result(updated)

    def measure_engine(self, request: EngineMeasureRequest) -> EngineMeasurement:
        deployment = None
        if request.deployment_id:
            deployment = self.manager.get_deployment(request.deployment_id)
        measurement = measure_engine(self.manager, deployment=deployment, paths=self.paths)
        return self.store.put_measurement(measurement)

    def list_measurements(self) -> list[EngineMeasurement]:
        return self.store.list_measurements()

    def _project_dir(self, workspace_id: str) -> Path:
        path = self.paths.workspaces / workspace_id / "project"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _starting_snapshot_for_run(self, run: AgentRun, workspace: LabWorkspace) -> SnapshotManifest:
        if not run.starting_snapshot_id:
            raise LabError(
                "This run has no starting snapshot. Original inputs are unavailable; "
                "current workspace files are not the source run's original inputs.",
                code="starting_snapshot_unavailable",
                status_code=409,
                details={
                    "degraded": True,
                    "original_inputs": "unavailable",
                    "snapshot_kind": "unavailable",
                },
            )
        try:
            manifest = self.get_snapshot(run.starting_snapshot_id)
        except LabError as exc:
            raise LabError(
                "The run's starting snapshot is missing or unreadable. "
                "Original inputs are unavailable; current files are not claimed as the original inputs.",
                code="starting_snapshot_unavailable",
                status_code=409,
                details={
                    "degraded": True,
                    "original_inputs": "unavailable",
                    "snapshot_kind": "unavailable",
                    "starting_snapshot_id": run.starting_snapshot_id,
                },
            ) from exc
        if manifest.kind != "starting":
            raise LabError(
                "The bound snapshot is not a starting snapshot. "
                "Original inputs are unavailable.",
                code="starting_snapshot_unavailable",
                status_code=409,
                details={
                    "degraded": True,
                    "original_inputs": "unavailable",
                    "snapshot_kind": manifest.kind,
                    "starting_snapshot_id": manifest.id,
                },
            )
        if manifest.workspace_id not in {workspace.id, "unbound"}:
            raise LabError(
                "Starting snapshot is linked to a different workspace.",
                code="workspace_mismatch",
                status_code=409,
            )
        return manifest

    def _resolve_knowledge_refs(self, request: CaptureRequest, run: AgentRun | None) -> KnowledgeRefs:
        memory = request.memory_version_refs
        skills = request.skill_version_refs
        protected = request.protected_instruction_version_refs
        generic = request.knowledge_version_refs
        if memory is None and run is not None:
            memory = run.memory_version_refs
        if skills is None and run is not None:
            skills = run.skill_version_refs
        if protected is None and run is not None:
            protected = run.protected_instruction_version_refs
        if not (memory or skills or protected or generic):
            return KnowledgeRefs()
        return self.knowledge.resolve_refs(
            memory_version_refs=memory,
            skill_version_refs=skills,
            protected_instruction_version_refs=protected,
            knowledge_version_refs=generic,
        )


def _execution_snapshot(run: AgentRun) -> FrozenExecutionSelection | None:
    """Capture actual executed settings, not mutable profile/default selectors."""
    if run.effective_setup is None:
        return None
    configuration = SetupConfiguration.model_validate(run.model_dump(include=set(SetupConfiguration.model_fields)))
    return FrozenExecutionSelection(
        selection=ResolvedSetupSelection(
            project_id=run.project_id,
            agent_setup_id=run.agent_setup_id,
            agent_setup_version_id=run.agent_setup_version_id,
            configuration=configuration,
            instruction_layers=list(run.effective_setup.instruction_layers),
        ),
        settings=run.effective_setup.bags.model_dump(mode="json"),
        system_prompt=run.system_prompt,
    )


def fixtures_from_run(run: AgentRun | None) -> list[dict[str, Any]]:
    if run is None:
        return []
    pending: dict[str, dict[str, Any]] = {}
    fixtures: list[dict[str, Any]] = []
    for event in run.events:
        if event.kind == "tool_call":
            call_id = str(event.detail.get("id") or len(pending))
            pending[call_id] = {
                "name": event.detail.get("name"),
                "args": event.detail.get("args") or {},
                "tool_call_id": call_id,
            }
            continue
        if event.kind != "tool_result":
            continue
        call_id = str(event.detail.get("tool_call_id") or "")
        base = pending.pop(call_id, {"name": event.detail.get("name"), "args": {}})
        content = event.detail.get("content")
        fixtures.append(
            {
                "name": base.get("name") or event.detail.get("name"),
                "args": base.get("args") or {},
                "result": content if isinstance(content, str) else str(content),
                "tool_call_id": call_id,
            }
        )
    return fixtures


def dependency_versions() -> dict[str, str]:
    versions: dict[str, str] = {}
    for name in DEPENDENCY_PACKAGES:
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            versions[name] = "unavailable"
    return versions


def _assistant_texts(run: AgentRun) -> list[str]:
    texts: list[str] = []
    for event in run.events:
        if event.kind != "assistant_message":
            continue
        content = event.detail.get("content")
        if isinstance(content, str) and content.strip():
            texts.append(content)
    return texts


def _evidence_from_run(run: AgentRun) -> dict[str, Any]:
    evidence = dict(run.completion.evidence) if run.completion else {}
    evidence["resource_use"] = {
        "available": False,
        "reason": "Harness runs do not sample process resources this milestone.",
    }
    evidence["answers"] = _assistant_texts(run)
    evidence["failures"] = [run.error] if run.error else []
    return evidence
