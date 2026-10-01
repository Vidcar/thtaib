"""Compaction scratch stays under the product data root, not the project."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from workbench_backend.agents.harness import HarnessService
from workbench_backend.agents.harness_backend import (
    HARNESS_SCRATCH_DIRNAME,
    build_run_backend,
    harness_scratch_root,
    roots_overlap,
)
from workbench_backend.agents.routes import router as agent_router
from workbench_backend.agents.schemas import AgentEvent, AgentRun, AgentRunStatus, ToolMode
from workbench_backend.agents.tool_results import OwnedToolResults
from workbench_backend.inference.ids import utc_now
from workbench_backend.paths import WorkbenchPaths
from workbench_backend.state.store import ApplicationStore

from tests.support import close_workbench_sqlite


_MARKER = "SCRATCH-NOTE-NOT-A-REQUEST"
_THREAD = "thread_compaction"
_HISTORY = "/conversation_history/summary.md"


def _run(project: Path) -> AgentRun:
    now = utc_now()
    return AgentRun(
        id="run_compaction_scratch",
        status=AgentRunStatus.completed,
        deployment_id="deploy_test",
        task="compaction scratch location",
        enabled_tools=["echo"],
        presented_tools=["echo"],
        created_at=now,
        updated_at=now,
        project_path=str(project),
        thread_id=_THREAD,
        tool_mode=ToolMode.live_tool,
        events=[AgentEvent(at=now, kind="context_compacted", detail={
            "cutoff_index": 1,
            "history_preserved_at": _HISTORY,
            "owner": "deepagents-upstream",
            "internal_summary_is_not_answer": True,
        })],
    )


class CompactionScratchLocationTests(unittest.TestCase):
    def test_scratch_is_product_data_and_not_a_request_inspector(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        project = root / "bound-project"
        project.mkdir()
        (project / "project-owned.txt").write_text("project file", encoding="utf-8")
        paths = WorkbenchPaths(root / "product-data").ensure()
        store = ApplicationStore(paths)
        self.addCleanup(close_workbench_sqlite, store)
        run = _run(project)
        scratch = harness_scratch_root(paths, _THREAD)
        backend = build_run_backend(run, paths)
        history = backend.write(_HISTORY, _MARKER)
        offload = backend.write("/large_tool_results/offload.txt", _MARKER + " large")
        self.assertFalse(history.error, history.error)
        self.assertFalse(offload.error, offload.error)
        retained = OwnedToolResults(paths, run).retain(_MARKER + " retained", source={"tool": "echo"})

        self.assertEqual(scratch, paths.state / HARNESS_SCRATCH_DIRNAME / _THREAD)
        self.assertTrue(scratch.resolve().is_relative_to(paths.root.resolve()))
        self.assertTrue(scratch.resolve().is_relative_to(paths.state.resolve()))
        self.assertFalse(scratch.resolve().is_relative_to(project.resolve()))
        self.assertFalse(roots_overlap(scratch, project))
        self.assertEqual((scratch / "conversation_history" / "summary.md").read_text(encoding="utf-8"), _MARKER)
        self.assertEqual((scratch / "large_tool_results" / "offload.txt").read_text(encoding="utf-8"), _MARKER + " large")
        owned = scratch / "large_tool_results" / "owned" / (retained["path"].rsplit("/", 1)[-1])
        self.assertEqual(owned.read_text(encoding="utf-8"), _MARKER + " retained")
        self.assertTrue(owned.resolve().is_relative_to(paths.state.resolve()))
        self.assertFalse(owned.resolve().is_relative_to(project.resolve()))
        self.assertEqual(sorted(path.name for path in project.iterdir()), ["project-owned.txt"])
        self.assertFalse((project / "conversation_history").exists())
        self.assertFalse((project / "large_tool_results").exists())
        self.assertFalse((project / HARNESS_SCRATCH_DIRNAME).exists())

        store.put_run(run)
        app = FastAPI()
        app.include_router(agent_router)
        app.state.harness = HarnessService(lambda: SimpleNamespace(paths=paths), app_store=store)
        with TestClient(app) as client:
            diagnostic = client.get(f"/v1/agent-runs/{run.id}?view=diagnostic")
            operational = client.get(f"/v1/agent-runs/{run.id}?view=operational")
        self.assertEqual(diagnostic.status_code, 200, diagnostic.text)
        self.assertEqual(operational.status_code, 200, operational.text)
        self.assertEqual(
            diagnostic.json()["events"][0]["detail"]["history_preserved_at"],
            _HISTORY,
        )
        for response in (diagnostic, operational):
            self.assertNotIn(_MARKER, response.text)
            self.assertNotIn(str(scratch.resolve()), response.text)
            self.assertNotIn(scratch.resolve().as_posix(), response.text)


if __name__ == "__main__":
    unittest.main()
