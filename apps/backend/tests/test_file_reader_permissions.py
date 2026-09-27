"""Selected native reading and result-only reading retain distinct permissions."""

import asyncio
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

from deepagents.middleware.filesystem import FilesystemMiddleware
from langchain_core.messages import ToolMessage

from workbench_backend.agents.harness_backend import build_run_backend, harness_scratch_root
from workbench_backend.agents.harness_profile import ordinary_chat_profile
from workbench_backend.agents.middleware import WorkbenchHarnessMiddleware
from workbench_backend.agents.schemas import AgentRun
from workbench_backend.inference.ids import utc_now
from workbench_backend.paths import WorkbenchPaths


RESULT_ROUTES = ["/large_tool_results/", "/conversation_history/", "/retrieved/"]


class FileReaderPermissionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.project = self.root / "project"
        self.project.mkdir()
        (self.project / "script_extracted.js").write_text("PROJECT-READER-OK", encoding="utf-8")
        (self.root / "private.txt").write_text("OUTSIDE-PROJECT", encoding="utf-8")
        self.paths = WorkbenchPaths(self.root / "data")

    def run_record(self, *, selected=True, project=True, prefixes=None):
        now = utc_now()
        return AgentRun(id="reader", thread_id="reader-thread", deployment_id="fixture",
            task="Read authorized files", status="running", approval_mode="full_access",
            project_path=str(self.project) if project else None,
            presented_tools=["read_file", "search_knowledge"] if selected else ["search_knowledge"],
            enabled_tools=["read_file", "search_knowledge"],
            framework_read_paths=prefixes if prefixes is not None else RESULT_ROUTES,
            created_at=now, updated_at=now)

    def read(self, run, path, *, asynchronous):
        backend = build_run_backend(run, self.paths)
        scratch = harness_scratch_root(self.paths, run.thread_id)
        for prefix in RESULT_ROUTES:
            (scratch / prefix.strip("/") / "result.txt").write_text("SAVED-RESULT-OK", encoding="utf-8")
        middleware = WorkbenchHarnessMiddleware(run)
        request = SimpleNamespace(tool_call={"name": "read_file", "args": {"file_path": path}, "id": "read"})
        dispatched = []

        def message(result):
            dispatched.append(path)
            return ToolMessage(name="read_file", tool_call_id="read",
                content=result.error or str(result.file_data["content"]),
                status="error" if result.error else "success")

        def sync_handler(_request):
            return message(backend.read(path))

        async def async_handler(_request):
            return message(await backend.aread(path))

        result = (asyncio.run(middleware.awrap_tool_call(request, async_handler)) if asynchronous
            else middleware.wrap_tool_call(request, sync_handler))
        self.assertEqual((result.name, result.tool_call_id), ("read_file", "read"))
        self.assertEqual(run.tool_outcomes["read"].outcome, "failed" if result.status == "error" else "succeeded")
        return result, dispatched

    def test_selected_reader_with_saved_retrieval_paths_keeps_native_access(self):
        for asynchronous in (False, True):
            for path in ["script_extracted.js", "/script_extracted.js", *[p + "result.txt" for p in RESULT_ROUTES]]:
                with self.subTest(asynchronous=asynchronous, path=path):
                    # Existing saved runs may carry the erroneous retrieval-only list.
                    run = self.run_record(prefixes=["/retrieved/"])
                    result, dispatched = self.read(run, path, asynchronous=asynchronous)
                    self.assertEqual(result.status, "success", result.content)
                    self.assertTrue(dispatched)
                    self.assertIn("PROJECT-READER-OK" if "script" in path else "SAVED-RESULT-OK", result.content)

    def test_automatic_reader_allows_only_supplied_results(self):
        denied = ["script_extracted.js", "/script_extracted.js", "/memories/private.txt",
            "/skills/private.txt", "/retrieved/../private.txt", "/retrieved/./result.txt",
            "/retrieved/C:/private.txt", "//retrieved/result.txt", "/retrieved/"]
        for asynchronous in (False, True):
            for project in (False, True):
                for path in [*[p + "result.txt" for p in RESULT_ROUTES], *denied]:
                    with self.subTest(asynchronous=asynchronous, project=project, path=path):
                        result, dispatched = self.read(self.run_record(selected=False, project=project),
                            path, asynchronous=asynchronous)
                        allowed = path not in denied
                        self.assertEqual(result.status, "success" if allowed else "error", result.content)
                        self.assertEqual(bool(dispatched), allowed)

    def test_selected_reader_does_not_bypass_native_project_containment(self):
        for asynchronous in (False, True):
            for path in ["../private.txt", "/../private.txt", str(self.root / "private.txt")]:
                with self.subTest(asynchronous=asynchronous, path=path):
                    result, _ = self.read(self.run_record(prefixes=["/retrieved/"]), path, asynchronous=asynchronous)
                    self.assertEqual(result.status, "error")
                    self.assertNotIn("OUTSIDE-PROJECT", result.content)

    def test_tools_off_and_projectless_reading_never_dispatch_project_read(self):
        for asynchronous in (False, True):
            for off in (False, True):
                run = self.run_record(project=False, prefixes=["/retrieved/"])
                if off:
                    run.presented_tools = []
                result, dispatched = self.read(run, "/script_extracted.js", asynchronous=asynchronous)
                self.assertEqual(result.status, "error")
                self.assertFalse(dispatched)
                if off:
                    self.assertIn("Tools are explicitly off", result.content)

    def test_reader_description_matches_selected_access_in_work_and_plan(self):
        description = ordinary_chat_profile().tool_description_overrides["read_file"]
        tool = FilesystemMiddleware(custom_tool_descriptions={"read_file": description}, tools=["read_file"]).tools[0]
        for mode in ("work", "plan"):
            for selected in (False, True):
                with self.subTest(mode=mode, selected=selected):
                    run = self.run_record(selected=selected, prefixes=["/retrieved/"] if selected else RESULT_ROUTES)
                    run.work_mode = mode
                    offered = WorkbenchHarnessMiddleware(run)._presented([tool])
                    self.assertEqual(len(offered), 1)
                    if selected:
                        self.assertEqual(offered[0].description, description)
                    else:
                        self.assertIn("Only these paths are permitted", offered[0].description)
                        for prefix in RESULT_ROUTES:
                            self.assertIn(prefix, offered[0].description)
        self.assertEqual(tool.description, description)
