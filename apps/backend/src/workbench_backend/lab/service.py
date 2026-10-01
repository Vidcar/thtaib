"""Isolated lab workspaces. Chat rewind reads them in process."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from workbench_backend.agents.harness import HarnessService
from workbench_backend.errors import LabError
from workbench_backend.inference.ids import new_id, utc_now
from workbench_backend.inference.service import ModelManager
from workbench_backend.knowledge.service import KnowledgeService
from workbench_backend.lab.schemas import LabWorkspace, WorkspaceCreateRequest
from workbench_backend.lab.snapshot import write_text_files
from workbench_backend.lab.store import LabStore
from workbench_backend.paths import WorkbenchPaths
from workbench_backend.state.effects import EffectService


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
    def paths(self) -> WorkbenchPaths:
        return self.manager.paths.ensure()

    @property
    def store(self) -> LabStore:
        return LabStore(self.paths)

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

    def get_workspace(self, workspace_id: str) -> LabWorkspace:
        workspace = self.store.get_workspace(workspace_id)
        if workspace is None:
            raise LabError("Unknown workspace", code="workspace_missing", status_code=404)
        return workspace

    def _project_dir(self, workspace_id: str) -> Path:
        path = self.paths.workspaces / workspace_id / "project"
        path.mkdir(parents=True, exist_ok=True)
        return path
