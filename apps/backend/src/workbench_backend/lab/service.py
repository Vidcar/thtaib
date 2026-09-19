"""Lab capture → restore → rerun against the shared Deep Agents harness."""

from __future__ import annotations

import importlib.metadata
from collections.abc import Callable
from pathlib import Path
from typing import Any

from workbench_backend.agents.harness import HarnessService
from workbench_backend.agents.schemas import (
    AgentRun,
    AgentRunStatus,
    AgentStartRequest,
    TaskCriteria,
    ToolMode,
    label_for_tool_mode,
)
from workbench_backend.errors import LabError
from workbench_backend.inference.ids import new_id, utc_now
from workbench_backend.inference.service import ModelManager
from workbench_backend.knowledge.schemas import KnowledgeRefs
from workbench_backend.knowledge.service import KnowledgeService
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
    project_fingerprints,
    read_text_files,
    restore_snapshot_tree,
    write_snapshot_tree,
    write_text_files,
)
from workbench_backend.lab.store import LabStore
from workbench_backend.paths import WorkbenchPaths

DEPENDENCY_PACKAGES = ("deepagents", "langchain", "langgraph", "langchain-openai")


class LabService:
    def __init__(
        self,
        manager_provider: Callable[[], ModelManager],
        harness_provider: Callable[[], HarnessService],
        knowledge_provider: Callable[[], KnowledgeService] | None = None,
    ) -> None:
        self._manager_provider = manager_provider
        self._harness_provider = harness_provider
        self._knowledge_provider = knowledge_provider

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
            if run.status in {AgentRunStatus.queued, AgentRunStatus.running}:
                raise LabError(
                    "Capture requires a quiescent boundary; the source run is still live.",
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

        snapshot_id = new_id("snap")
        tree_path = self.paths.snapshots / snapshot_id / "tree"
        included, exclusions = write_snapshot_tree(
            Path(workspace.path),
            tree_path,
            allowlist=request.allowlist or workspace.allowlist,
        )
        manifest = SnapshotManifest(
            id=snapshot_id,
            workspace_id=workspace.id,
            captured_at=utc_now(),
            included_files=included,
            exclusions=exclusions,
            environment_exclusions=list(ENVIRONMENT_EXCLUSIONS),
            allowlist=request.allowlist or workspace.allowlist,
            tree_path=str(tree_path),
        )
        self._write_manifest(manifest)

        profile_id = request.profile_id
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
            source_run_id=run.id if run else None,
            source_workspace_id=workspace.id,
            task=task,
            profile_id=profile_id,
            deployment_id=deployment_id,
            presented_tools=request.presented_tools or (run.presented_tools if run else []),
            system_prompt=run.system_prompt if run else None,
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
            created_at=utc_now(),
            snapshot_path=str(self.paths.snapshots / snapshot_id),
            knowledge=refs.binding(),
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
        blob = case.model_dump_json() + snapshot.model_dump_json()
        tree = Path(snapshot.tree_path)
        if tree.is_dir():
            for file_path in tree.rglob("*"):
                if file_path.is_file():
                    blob += file_path.read_text(encoding="utf-8", errors="ignore")
        secret_hits = ("SECRET_VALUE", "API_KEY=", "BEGIN PRIVATE KEY")
        clean = not any(token in blob for token in secret_hits)
        for item in snapshot.exclusions:
            if item.reason in {"secrets", "env_credentials", "weights"}:
                exported = (tree / item.path) if tree.is_dir() else None
                if exported is not None and exported.exists():
                    clean = False
        return CaseExport(case=case, snapshot=snapshot, secret_scan_clean=clean)

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
        child.path = str(self._project_dir(child.id))
        restore_snapshot_tree(Path(snapshot.tree_path), Path(child.path))
        self.store.put_workspace(child)
        parent_after = project_fingerprints(Path(parent.path))
        parent_unchanged = parent_before == parent_after
        deviations = [
            "Restored into a new workspace directory; the parent was not overwritten.",
            "Full environment restore is not this milestone; exclusions are recorded.",
            "Restored inputs do not guarantee an identical model output.",
        ]
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
        presented = request.presented_tools or case.presented_tools
        started = self.harness.start(
            AgentStartRequest(
                deployment_id=case.deployment_id or "",
                task=case.task,
                presented_tools=presented or None,
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
            )
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
                profile_id=case.profile_id,
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
        updated = result.model_copy(
            update={
                "evidence": _evidence_from_run(run),
                "judgement": run.completion.judgement.model_dump() if run.completion else result.judgement,
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

    def _write_manifest(self, manifest: SnapshotManifest) -> None:
        path = self.paths.snapshots / manifest.id / "manifest.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(manifest.model_dump_json(indent=2), encoding="utf-8")

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
