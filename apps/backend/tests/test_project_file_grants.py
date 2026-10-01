"""Explicit project mutation grants preserve exact approvals and scope boundaries."""
from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from langchain_core.tools import ToolException
from langchain_core.messages import AIMessage

from workbench_backend.agents.host_shell import interrupt_on_for_run, recheck_saved_authorization
from workbench_backend.agents.harness import HarnessService
from workbench_backend.agents.schemas import AgentRun, PendingInterruptAction
from workbench_backend.app import create_app
from workbench_backend.inference.ids import utc_now
from workbench_backend.state.preferences import matched_permission_snapshot
from tests.support import close_workbench_sqlite, offline_workbench_client
from tests.scripted_model import ScriptedChatModel
from tests.test_harness import wait_for_run
from tests.test_host_shell import wait_for_interrupt, run_direct_interrupt_decision


class ProjectFileGrantTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.project = self.root / "Project with spaces"
        self.project.mkdir()
        self.app = create_app(data_root=self.root / "data")
        self.client = offline_workbench_client(self.app)
        response = self.client.post("/v1/projects", json={"path": str(self.project)})
        self.assertEqual(response.status_code, 200, response.text)
        self.project_id = response.json()["id"]
        now = utc_now()
        self.run = AgentRun(id="run-grant", thread_id="thread-grant", deployment_id="model", task="change",
            project_path=str(self.project), enabled_tools=["write_file", "edit_file", "execute", "delete"],
            presented_tools=["write_file", "edit_file", "execute", "delete"], created_at=now, updated_at=now)
        self.preferences = self.app.state.preferences

    def tearDown(self):
        close_workbench_sqlite(self.app, self.client)
        self.tmp.cleanup()

    def grant(self, **values):
        response = self.client.post("/v1/settings/grants/project-files", json={"project_id": self.project_id, **values})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def test_exact_action_grants_are_unchanged_and_preferred(self):
        first = {"file_path": "/a.txt", "old_string": "a", "new_string": "b"}
        exact = self.preferences.allow(self.run, PendingInterruptAction(name="edit_file", args=first), "session")
        self.assertEqual(exact.kind, "exact_action")
        self.assertTrue(self.preferences.matches(self.run, "edit_file", first))
        self.assertFalse(self.preferences.matches(self.run, "edit_file", {**first, "new_string": "c"}))
        self.grant()
        self.assertEqual(self.preferences.matching_grant(self.run, "edit_file", first).id, exact.id)
        self.assertFalse(self.preferences.matches(self.run.model_copy(update={"thread_id": "other"}), "execute", {"command": "echo ok"}))

    def test_changed_arguments_match_only_explicit_selected_project_scope(self):
        grant = self.grant(excluded_paths=["private/**", "**/*.secret", ".env"])
        for name, arguments in [("write_file", {"file_path": "/src/new.py", "content": "new"}),
                ("edit_file", {"file_path": "/src/new.py", "old_string": "a", "new_string": "b"}),
                ("edit_file", {"file_path": "/src/new.py", "old_string": "b", "new_string": "c"})]:
            self.assertEqual(self.preferences.matching_grant(self.run, name, arguments).id, grant["id"])
            self.assertIsNone(self.preferences.matching_grant(self.run.model_copy(update={"presented_tools": []}), name, arguments))
            self.assertIsNone(self.preferences.matching_grant(self.run.model_copy(update={"enabled_tools": []}), name, arguments))
            self.assertIsNone(self.preferences.matching_grant(self.run.model_copy(update={"project_path": str(self.root)}), name, arguments))
        for path in ["/.git/config", "/nested/.git/index", "/private/key", "/src/a.secret", "/a.secret", "/.env", "/../outside", "/skills/example/SKILL.md", "/large_tool_results/owned/result.txt"]:
            self.assertIsNone(self.preferences.matching_grant(self.run, "write_file", {"file_path": path, "content": "x"}), path)
        for name, args in [("execute", {"command": "echo x"}), ("delete", {"file_path": "/src/new.py"})]:
            self.assertIsNone(self.preferences.matching_grant(self.run, name, args))

    def test_revocation_rechecks_original_id_and_cannot_substitute_new_scope(self):
        first = self.grant()
        args = {"file_path": "/src/a.py", "content": "x"}
        predicate = interrupt_on_for_run(self.run, self.preferences)["write_file"]["when"]
        self.assertFalse(predicate(SimpleNamespace(tool_call={"name": "write_file", "args": args, "id": "call-write"})))
        self.assertEqual(self.run.tool_authorization_grants["call-write"].id, first["id"])
        recheck_saved_authorization(self.run, "write_file", args, "call-write", self.preferences)
        self.client.delete(f'/v1/settings/grants/{first["id"]}')
        self.grant()
        with self.assertRaises(ToolException):
            recheck_saved_authorization(self.run, "write_file", args, "call-write", self.preferences)
        self.assertFalse((self.project / "src/a.py").exists())

    def test_selected_operations_and_removed_project_fail_closed(self):
        self.grant(operations=["edit_file"])
        self.assertFalse(self.preferences.matches(self.run, "write_file", {"file_path": "/a.txt", "content": "x"}))
        self.assertTrue(self.preferences.matches(self.run, "edit_file", {"file_path": "/a.txt", "old_string": "a", "new_string": "b"}))
        self.client.delete(f"/v1/projects/{self.project_id}")
        self.assertFalse(self.preferences.matches(self.run, "edit_file", {"file_path": "/a.txt", "old_string": "a", "new_string": "b"}))

    def test_invalid_exclusions_and_missing_projects_save_nothing(self):
        for excluded in [["../other"], ["C:/other"], ["/outside"], [""]]:
            response = self.client.post("/v1/settings/grants/project-files", json={"project_id": self.project_id, "excluded_paths": excluded})
            self.assertEqual(response.status_code, 422, response.text)
        response = self.client.post("/v1/settings/grants/project-files", json={"project_id": "missing"})
        self.assertEqual(response.status_code, 404)
        self.assertEqual(self.preferences.grants(), [])

    def test_repeated_explicit_request_is_idempotent_and_record_survives_store_reload(self):
        first = self.grant(excluded_paths=["private/**"])
        second = self.grant(excluded_paths=["private/**"])
        self.assertEqual(first["id"], second["id"])
        from workbench_backend.state.preferences import PreferenceStore
        restored = PreferenceStore(self.app.state.app_store)
        self.assertEqual(len(restored.grants()), 1)
        self.assertEqual(restored.matching_grant(self.run, "edit_file", {"file_path": "/a.txt", "old_string": "a", "new_string": "b"}).id, first["id"])

    def test_junction_or_symlink_escape_never_matches(self):
        outside = self.root / "outside"
        outside.mkdir()
        link = self.project / "escape"
        if os.name == "nt":
            created = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(outside)], capture_output=True, text=True)
            self.assertEqual(created.returncode, 0, created.stdout + created.stderr)
            self.addCleanup(lambda: os.rmdir(link) if link.exists() else None)
        else:
            link.symlink_to(outside, target_is_directory=True)
        self.grant()
        self.assertFalse(self.preferences.matches(self.run, "write_file", {"file_path": "/escape/a.txt", "content": "x"}))
        self.assertFalse((outside / "a.txt").exists())

    def test_excluded_alias_inside_project_does_not_bypass_lexical_exclusion(self):
        target = self.project / "allowed"
        target.mkdir()
        link = self.project / "private"
        if os.name == "nt":
            created = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)], capture_output=True, text=True)
            self.assertEqual(created.returncode, 0, created.stdout + created.stderr)
            self.addCleanup(lambda: os.rmdir(link) if link.exists() else None)
        else:
            link.symlink_to(target, target_is_directory=True)
        self.grant(excluded_paths=["private/**"])
        self.assertFalse(self.preferences.matches(self.run, "write_file", {"file_path": "/private/a.txt", "content": "x"}))
        self.assertTrue(self.preferences.matches(self.run, "write_file", {"file_path": "/allowed/a.txt", "content": "x"}))

    def test_native_read_edit_edit_sequence_uses_scope_but_excluded_file_pauses(self):
        saved = self.grant()
        calls = [
            ("write_file", {"file_path": "/answer.txt", "content": "first"}),
            ("edit_file", {"file_path": "/answer.txt", "old_string": "first", "new_string": "second"}),
            ("edit_file", {"file_path": "/answer.txt", "old_string": "second", "new_string": "third"}),
            ("write_file", {"file_path": "/.env", "content": "blocked"}),
        ]
        model = ScriptedChatModel([AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": f"call-{index}"}])
            for index, (name, args) in enumerate(calls)] + [AIMessage(content="Done.")])
        self.app.state.harness = HarnessService(lambda: self.app.state.manager, model_factory=lambda _run, _sink: model,
            knowledge_provider=lambda: self.app.state.knowledge, app_store=self.app.state.app_store)
        deployment = self.client.post("/v1/deployments/connected", json={"endpoint": "http://127.0.0.1:9/v1", "display_name": "grant fixture"}).json()
        started = self.client.post("/v1/agent-runs", json={"deployment_id": deployment["id"], "task": "Change project files.",
            "project_path": str(self.project), "presented_tools": ["read_file", "write_file", "edit_file"],
            "approval_mode": "ask", "input_policy": {"tool_loading": "always"}})
        self.assertEqual(started.status_code, 200, started.text)
        paused = wait_for_interrupt(self.client, started.json()["id"])
        self.assertEqual(paused["pending_interrupt"]["action_requests"][0]["args"]["file_path"], "/.env", paused)
        self.assertEqual((self.project / "answer.txt").read_text(), "third")
        self.assertFalse((self.project / ".env").exists())
        for index in range(3):
            self.assertEqual(paused["tool_authorization_grants"][f"call-{index}"]["id"], saved["id"])
        response = self.client.post(f'/v1/agent-runs/{paused["id"]}/interrupt-decision', json=run_direct_interrupt_decision(paused, "reject"))
        self.assertEqual(response.status_code, 200, response.text)
        finished = wait_for_run(self.client, paused["id"])
        self.assertEqual(finished["status"], "completed", finished.get("error"))
        self.assertFalse((self.project / ".env").exists())
