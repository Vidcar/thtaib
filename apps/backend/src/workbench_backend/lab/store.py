"""JSON records for Lab workspaces, cases, results and measurements."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, TypeVar

from pydantic import BaseModel, TypeAdapter

from workbench_backend.lab.schemas import EngineMeasurement, LabCase, LabResult, LabWorkspace
from workbench_backend.paths import WorkbenchPaths

T = TypeVar("T", bound=BaseModel)


class LabStore:
    def __init__(self, paths: WorkbenchPaths) -> None:
        self.paths = paths.ensure()
        self.workspaces_path = self.paths.cases / "workspaces.json"
        self.cases_path = self.paths.cases / "cases.json"
        self.results_path = self.paths.cases / "results.json"
        self.measurements_path = self.paths.cases / "engine_measurements.json"

    def list_workspaces(self) -> list[LabWorkspace]:
        return self._read_list(self.workspaces_path, LabWorkspace)

    def put_workspace(self, workspace: LabWorkspace) -> LabWorkspace:
        return self._upsert(self.workspaces_path, LabWorkspace, workspace)

    def get_workspace(self, workspace_id: str) -> LabWorkspace | None:
        return next((item for item in self.list_workspaces() if item.id == workspace_id), None)

    def delete_workspace_record(self, workspace_id: str) -> None:
        """Remove a failed creation's record; never delete a workspace's files."""
        self._write_list(self.workspaces_path, [item for item in self.list_workspaces() if item.id != workspace_id])

    def list_cases(self) -> list[LabCase]:
        return self._read_list(self.cases_path, LabCase)

    def put_case(self, case: LabCase) -> LabCase:
        return self._upsert(self.cases_path, LabCase, case)

    def get_case(self, case_id: str) -> LabCase | None:
        return next((item for item in self.list_cases() if item.id == case_id), None)

    def list_results(self) -> list[LabResult]:
        return self._read_list(self.results_path, LabResult)

    def put_result(self, result: LabResult) -> LabResult:
        return self._upsert(self.results_path, LabResult, result)

    def get_result(self, result_id: str) -> LabResult | None:
        return next((item for item in self.list_results() if item.id == result_id), None)

    def list_measurements(self) -> list[EngineMeasurement]:
        return self._read_list(self.measurements_path, EngineMeasurement)

    def put_measurement(self, measurement: EngineMeasurement) -> EngineMeasurement:
        return self._upsert(self.measurements_path, EngineMeasurement, measurement)

    def _read_list(self, path: Path, model: type[T]) -> list[T]:
        if not path.is_file():
            return []
        raw = json.loads(path.read_text(encoding="utf-8"))
        return TypeAdapter(list[model]).validate_python(raw)

    def _write_list(self, path: Path, items: list[BaseModel]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(f"{path.name}.tmp")
        payload: Any = [item.model_dump(mode="json") for item in items]
        tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        tmp.replace(path)

    def _upsert(self, path: Path, model: type[T], item: T) -> T:
        items = self._read_list(path, model)
        next_items: list[T] = []
        replaced = False
        for existing in items:
            if getattr(existing, "id") == getattr(item, "id"):
                next_items.append(item)
                replaced = True
            else:
                next_items.append(existing)
        if not replaced:
            next_items.append(item)
        self._write_list(path, next_items)
        return item
