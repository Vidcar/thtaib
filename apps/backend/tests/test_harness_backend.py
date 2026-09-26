"""CompositeBackend scratch isolation and reserved-path helpers (DEV-004)."""

from __future__ import annotations

import base64
import tempfile
import unittest
from pathlib import Path

from deepagents.backends import CompositeBackend, FilesystemBackend, LocalShellBackend, StateBackend

from workbench_backend.agents.harness_backend import (
    RESERVED_FRAMEWORK_PREFIXES,
    build_run_backend,
    harness_scratch_root,
    host_shell_requested,
    is_reserved_framework_path,
    sanitize_thread_id,
)
from workbench_backend.agents.schemas import AgentRun, AgentRunStatus, ToolMode
from workbench_backend.agents.middleware import _allow_projectless_capture_tool
from workbench_backend.inference.ids import utc_now
from workbench_backend.paths import WorkbenchPaths
from workbench_backend.inference.probes import _image_fixture


def _run(
    *,
    project_path: str | None,
    thread_id: str = "thread_test",
    tool_mode: ToolMode = ToolMode.live_tool,
    presented_tools: list[str] | None = None,
) -> AgentRun:
    now = utc_now()
    return AgentRun(
        id="agent_backend_test",
        status=AgentRunStatus.queued,
        deployment_id="deploy_test",
        task="backend unit",
        enabled_tools=["echo"],
        presented_tools=list(presented_tools or ["echo"]),
        created_at=now,
        updated_at=now,
        project_path=project_path,
        thread_id=thread_id,
        tool_mode=tool_mode,
    )


class HarnessBackendHelperTests(unittest.TestCase):
    def test_sanitize_and_reserved_paths(self) -> None:
        self.assertEqual(sanitize_thread_id("thread_abc-1"), "thread_abc-1")
        self.assertEqual(sanitize_thread_id("../odd thread"), "odd_thread")
        self.assertTrue(is_reserved_framework_path("/large_tool_results/hello.txt"))
        self.assertTrue(is_reserved_framework_path("conversation_history/note.md"))
        self.assertFalse(is_reserved_framework_path("/hello.txt"))
        self.assertEqual(
            RESERVED_FRAMEWORK_PREFIXES,
            (
                "/large_tool_results/",
                "/conversation_history/",
                "/retrieved/",
                "/memories/",
                "/skills/",
                "/captures/",
            ),
        )
        self.assertTrue(is_reserved_framework_path("/retrieved/batch/chunk_1.md"))
        self.assertTrue(is_reserved_framework_path("/memories/user/kn_mem.md"))
        self.assertTrue(is_reserved_framework_path("/skills/review/SKILL.md"))
        self.assertTrue(is_reserved_framework_path("/captures/asset_123.png"))

    def test_recorded_mode_attaches_no_backend(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = WorkbenchPaths(Path(tmp)).ensure()
            backend = build_run_backend(
                _run(project_path=str(Path(tmp) / "project"), tool_mode=ToolMode.recorded_tool),
                paths,
            )
            self.assertIsNone(backend)

    def test_recorded_mode_with_knowledge_attaches_scratch_routes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = WorkbenchPaths(Path(tmp)).ensure()
            run = _run(project_path=str(Path(tmp) / "project"), tool_mode=ToolMode.recorded_tool)
            run.memory_version_refs = ["knv_mem"]
            backend = build_run_backend(run, paths)
            self.assertIsInstance(backend, CompositeBackend)
            assert isinstance(backend, CompositeBackend)
            self.assertIsInstance(backend.default, StateBackend)
            self.assertIn("/memories/", backend.routes)
            self.assertIn("/skills/", backend.routes)

    def test_project_run_routes_reserved_prefixes_to_scratch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = root / "project"
            project.mkdir()
            paths = WorkbenchPaths(root).ensure()
            backend = build_run_backend(_run(project_path=str(project), thread_id="thread_iso"), paths)
            self.assertIsInstance(backend, CompositeBackend)
            assert isinstance(backend, CompositeBackend)
            self.assertIsInstance(backend.default, FilesystemBackend)
            self.assertNotIsInstance(backend.default, LocalShellBackend)
            self.assertFalse(host_shell_requested(_run(project_path=str(project))))
            self.assertEqual(backend.artifacts_root, "/")
            write = backend.write("/hello.txt", "in-project")
            self.assertFalse(write.error, write.error)
            offload = backend.write("/large_tool_results/hello.txt", "in-scratch")
            self.assertFalse(offload.error, offload.error)
            self.assertEqual((project / "hello.txt").read_text(encoding="utf-8"), "in-project")
            self.assertFalse((project / "large_tool_results").exists())
            offload_retrieved = backend.write("/retrieved/batch/chunk.md", "retrieved")
            self.assertFalse(offload_retrieved.error, offload_retrieved.error)
            self.assertFalse((project / "retrieved").exists())
            memory_write = backend.write("/memories/user/kn_mem.md", "memory")
            self.assertFalse(memory_write.error, memory_write.error)
            skill_write = backend.write("/skills/review/SKILL.md", "skill")
            self.assertFalse(skill_write.error, skill_write.error)
            self.assertFalse((project / "memories").exists())
            self.assertFalse((project / "skills").exists())
            scratch = harness_scratch_root(paths, "thread_iso")
            self.assertEqual(
                (scratch / "large_tool_results" / "hello.txt").read_text(encoding="utf-8"),
                "in-scratch",
            )
            self.assertEqual(
                (scratch / "retrieved" / "batch" / "chunk.md").read_text(encoding="utf-8"),
                "retrieved",
            )
            self.assertEqual(
                (scratch / "memories" / "user" / "kn_mem.md").read_text(encoding="utf-8"),
                "memory",
            )
            self.assertEqual(
                (scratch / "skills" / "review" / "SKILL.md").read_text(encoding="utf-8"),
                "skill",
            )

    def test_project_run_attaches_host_shell_only_when_execute_presented(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = root / "project"
            project.mkdir()
            paths = WorkbenchPaths(root).ensure()
            shell_run = _run(
                project_path=str(project),
                thread_id="thread_shell",
                presented_tools=["execute"],
            )
            self.assertTrue(host_shell_requested(shell_run))
            backend = build_run_backend(shell_run, paths)
            self.assertIsInstance(backend, CompositeBackend)
            assert isinstance(backend, CompositeBackend)
            self.assertIsInstance(backend.default, LocalShellBackend)
            self.assertIn("PATH", getattr(backend.default, "_env", {}))

    def test_project_image_reads_require_verified_vision_and_are_bounded(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = root / "project"
            project.mkdir()
            image = base64.b64decode(_image_fixture("red").partition(",")[2])
            (project / "view.png").write_bytes(image)
            paths = WorkbenchPaths(root).ensure()
            run = _run(project_path=str(project), presented_tools=["read_file"])
            blocked = build_run_backend(run, paths)
            self.assertIn("cannot read the screenshot", blocked.read("/view.png").error)
            for presented in (["read_file"], ["read_file", "execute"]):
                with self.subTest(presented=presented):
                    backend = build_run_backend(_run(project_path=str(project), presented_tools=presented),
                        paths, image_inputs_allowed=True)
                    result = backend.read("/view.png")
                    self.assertIsNone(result.error)
                    self.assertEqual(result.file_data["encoding"], "base64")
                    self.assertEqual(base64.b64decode(result.file_data["content"]), image)
            (project / "view.png").write_bytes(b"0" * (8 * 1024 * 1024 + 1))
            self.assertIn("at most", backend.read("/view.png").error)
            (project / "view.png").write_bytes(b"not an image")
            self.assertIn("could not be verified", backend.read("/view.png").error)

    def test_projectless_run_uses_state_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = WorkbenchPaths(root).ensure()
            backend = build_run_backend(_run(project_path=None, thread_id="thread_free"), paths)
            self.assertIsInstance(backend, CompositeBackend)
            assert isinstance(backend, CompositeBackend)
            self.assertIsInstance(backend.default, StateBackend)
            self.assertFalse((root / "surprise").exists())

    def test_projectless_capture_guard_requires_mount_and_exact_read_path(self) -> None:
        run = _run(project_path=None, presented_tools=["read_file", "ls"])
        path = "/captures/asset_" + "a" * 32 + ".png"
        self.assertFalse(_allow_projectless_capture_tool("read_file", {"file_path": path}, run))
        run.capture_routes_enabled = True
        self.assertTrue(_allow_projectless_capture_tool("read_file", {"file_path": path}, run))
        self.assertTrue(_allow_projectless_capture_tool("ls", {"path": "/captures"}, run))
        for invalid in ("/captures/../secrets.png", "/captures/asset_" + "b" * 32 + ".pdf",
                        "//captures/" + path.rsplit("/", 1)[-1], "/memories/user/private.png"):
            self.assertFalse(_allow_projectless_capture_tool("read_file", {"file_path": invalid}, run))
        self.assertFalse(_allow_projectless_capture_tool("write_file", {"file_path": path}, run))


if __name__ == "__main__":
    unittest.main()
