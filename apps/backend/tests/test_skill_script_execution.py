"""Frozen selected resources use real owned execution, without shell interpolation."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest

from workbench_backend.agents.harness_backend import build_run_backend
from workbench_backend.agents.memory_skills import plan_knowledge_materialization
from workbench_backend.agents.schemas import AgentRun
from workbench_backend.agents.skill_scripts import skill_script_tool
from workbench_backend.knowledge.schemas import KnowledgeProvenance, KnowledgeVersion, SkillResource
from workbench_backend.paths import WorkbenchPaths


class SkillScriptExecutionTests(unittest.TestCase):
    def setUp(self):
        self.area = TemporaryDirectory()
        self.addCleanup(self.area.cleanup)
        self.root = Path(self.area.name)
        self.project = self.root / "project"
        self.project.mkdir()
        self.paths = WorkbenchPaths(self.root / "data")
        self.source = b'import json,sys\nprint(json.dumps(sys.argv[1:],ensure_ascii=False))\nsys.exit(7)\n'
        self.digest = hashlib.sha256(self.source).hexdigest()
        self.version = KnowledgeVersion(id="version-frozen", entry_id="entry-selected", scope="user", kind="skill",
            content="---\nname: script-test\ndescription: A selected script fixture.\n---\nUse selected scripts when requested.\n",
            resources=[SkillResource(path="scripts/run.py", sha256=self.digest, size_bytes=len(self.source))],
            provenance=KnowledgeProvenance(actor="human"), created_at="2026-10-01T00:00:00Z")
        self.run = AgentRun(id="script-run", deployment_id="fixture", thread_id="script-thread", project_path=str(self.project),
            task="Run selected script", enabled_tools=["execute", "execute_skill_script", "read_tool_result"],
            presented_tools=["execute", "execute_skill_script", "read_tool_result"], skill_version_refs=[self.version.id],
            created_at="2026-10-01T00:00:00Z", updated_at="2026-10-01T00:00:00Z")
        self.plan = plan_knowledge_materialization([self.version], resource_loader=lambda version, path: self.source)
        self.service = SimpleNamespace(manager=SimpleNamespace(paths=self.paths), _knowledge_provider=lambda: SimpleNamespace(get_version=lambda ident: self.version))
        self.backend = build_run_backend(self.run, self.paths)
        self.tool = skill_script_tool(self.service, self.run, self.backend, self.plan)
        self.arguments = {"entry_id": self.version.entry_id, "version_id": self.version.id, "resource_path": "scripts/run.py"}

    def test_real_unicode_arguments_cannot_inject_shell_and_nonzero_exit_is_preserved(self):
        hostile = "& echo injected > injected.txt; $(echo injected) ' quoted café"
        result = json.loads(self.tool.invoke({**self.arguments, "arguments": [hostile, "with spaces"], "resource_sha256": self.digest}))
        self.assertEqual(result["exit_code"], 7)
        self.assertIn("quoted", result["output"])
        self.assertIn("with spaces", result["output"])
        self.assertFalse((self.project / "injected.txt").exists())
        self.assertEqual(result["resource_sha256"], self.digest)
        self.assertFalse((self.project / "skills").exists())

    def test_wrong_or_unselected_frozen_identity_never_materializes(self):
        for changed in ({"entry_id": "other"}, {"version_id": "other"}, {"resource_sha256": "0" * 64}, {"resource_path": "../outside.py"}, {"resource_path": "references/info.txt"}):
            answer = self.tool.invoke({**self.arguments, **changed})
            self.assertIsInstance(answer, str)
            self.assertFalse(list(self.paths.root.rglob("skill_execution")))

    def test_shell_deselection_and_plan_do_not_gain_authority(self):
        self.run.presented_tools = ["execute_skill_script"]
        self.assertIn("separately selected", self.tool.invoke(self.arguments))
        self.run.presented_tools = ["execute_skill_script", "execute"]
        self.run.work_mode = "plan"
        self.assertIn("Work-mode", self.tool.invoke(self.arguments))
        self.assertFalse(list(self.paths.root.rglob("skill_execution")))

    def test_changed_resource_upload_is_rejected_against_manifest(self):
        self.plan.uploads[-1] = (self.plan.uploads[-1][0], b"raise RuntimeError('tampered')")
        self.assertIn("missing or changed", self.tool.invoke(self.arguments))
        self.assertFalse(list(self.paths.root.rglob("skill_execution")))


if __name__ == "__main__":
    unittest.main()
