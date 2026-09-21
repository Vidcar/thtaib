"""Lab capture → restore → rerun and engine measurement (LAB-001…004, STATE-003)."""

from __future__ import annotations

import json
import shutil
import tempfile
import threading
import unittest
from pathlib import Path
from typing import Any

from langchain_core.messages import AIMessage

from workbench_backend.agents.harness import HarnessService
from workbench_backend.agents.schemas import AgentRun, AgentRunStatus
from workbench_backend.app import create_app
from workbench_backend.inference.ids import utc_now
from workbench_backend.inference.service import ModelManager
from workbench_backend.paths import WorkbenchPaths

from tests.scripted_model import ScriptedChatModel
from tests.support import close_workbench_sqlite, offline_workbench_client, wait_for_lab_result, wait_for_run, wait_for_import, write_tiny_gguf


def echo_then_reply() -> list[AIMessage]:
    return [
        AIMessage(
            content="",
            tool_calls=[{"name": "echo", "args": {"text": "harness-ok"}, "id": "call_echo"}],
        ),
        AIMessage(content="The echo tool returned harness-ok. Looks correct."),
    ]


class LabApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.paths = WorkbenchPaths(self.root).ensure()
        self.manager = ModelManager(self.paths)
        self.app = create_app(data_root=self.root)
        self.app.state.manager = self.manager
        def factory(_run: AgentRun, _sink: list[dict[str, Any]]) -> ScriptedChatModel:
            return ScriptedChatModel(echo_then_reply())

        self.app.state.harness = HarnessService(lambda: self.manager, model_factory=factory)
        self.app.state.lab._manager_provider = lambda: self.manager
        self.app.state.lab._harness_provider = lambda: self.app.state.harness
        self.client = offline_workbench_client(self.app)
        self.deployment_id = self.client.post(
            "/v1/deployments/connected",
            json={"endpoint": "http://127.0.0.1:9/v1", "display_name": "lab-fixture"},
        ).json()["id"]

    def tearDown(self) -> None:
        close_workbench_sqlite(self.app, getattr(self, "client", None))
        self.tmp.cleanup()

    def _workspace(self, files: dict[str, str] | None = None) -> dict[str, Any]:
        return self.client.post(
            "/v1/lab/workspaces",
            json={
                "display_name": "sample-project",
                "files": files or {"notes.md": "original notes", "src/hello.py": "print('hi')\n"},
            },
        ).json()

    def _complete_run(self, workspace_id: str | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "deployment_id": self.deployment_id,
            "task": "Echo the text harness-ok using the echo tool.",
            "presented_tools": ["echo"],
            "criteria": {"checks": ["enabled_tool_invoked", "tool:echo"], "expected_artifacts": ["assistant_reply"]},
        }
        if workspace_id:
            payload["workspace_id"] = workspace_id
        started = self.client.post("/v1/agent-runs", json=payload).json()
        return wait_for_run(self.client, started["id"])

    def test_paths_advertise_cases_and_snapshots(self) -> None:
        body = self.client.get("/v1/paths").json()
        self.assertEqual(body["cases"], str(self.paths.cases))
        self.assertEqual(body["snapshots"], str(self.paths.snapshots))
        self.assertEqual(body["knowledge"], str(self.paths.knowledge))
        self.assertIn("cases", body["windows_layout"])
        self.assertIn("snapshots", body["windows_layout"])
        self.assertIn("knowledge", body["windows_layout"])

    def test_engine_measurement_unavailable_does_not_invent_scores(self) -> None:
        response = self.client.post("/v1/lab/engine-measurements", json={})
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["kind"], "engine_measurement")
        self.assertEqual(body["engine"], "llama-bench")
        self.assertFalse(body["available"])
        self.assertIsNone(body["scores"])
        self.assertIn("llama-bench", body["reason"].lower())
        self.assertIn("never fabricated", body["note"].lower())

    def test_engine_measurement_reports_present_bench_without_fake_scores_when_no_model(self) -> None:
        pin_dir = self.root / "fake-runtime"
        pin_dir.mkdir()
        server = pin_dir / "llama-server"
        server.write_text("#!/usr/bin/env python3\n", encoding="utf-8")
        server.chmod(0o755)
        bench = pin_dir / "llama-bench"
        bench.write_text(
            "#!/usr/bin/env python3\n"
            "print('| model | size | params | backend | ngl | test | t/s |')\n"
            "print('| fake | 1 MiB | 1M | CPU | 0 | pp16 | 12.50 ± 0.01 |')\n",
            encoding="utf-8",
        )
        bench.chmod(0o755)
        manifest = self.client.post("/v1/runtime/pin", json={"local_executable": str(server)}).json()
        install = Path(manifest["install_dir"])
        (install / "llama-bench").write_text(bench.read_text(encoding="utf-8"), encoding="utf-8")
        (install / "llama-bench").chmod(0o755)
        body = self.client.post(
            "/v1/lab/engine-measurements",
            json={"deployment_id": self.deployment_id},
        ).json()
        self.assertTrue(body["available"])
        self.assertFalse(body["success"])
        self.assertIsNone(body["scores"])
        self.assertIn("no score was fabricated", body["reason"].lower())

    def test_engine_measurement_parses_llama_bench_when_present(self) -> None:
        gguf = write_tiny_gguf(self.root / "incoming" / "tiny-Q4_K_M.gguf")
        job = self.client.post("/v1/imports/local", json={"source_path": str(gguf), "display_name": "tiny"}).json()
        job = wait_for_import(self.client, job)
        pin_dir = self.root / "bench-runtime"
        pin_dir.mkdir()
        server = pin_dir / "llama-server"
        server.write_text("#!/usr/bin/env python3\n", encoding="utf-8")
        server.chmod(0o755)
        manifest = self.client.post("/v1/runtime/pin", json={"local_executable": str(server)}).json()
        install = Path(manifest["install_dir"])
        (install / "llama-bench").write_text(
            "#!/usr/bin/env python3\n"
            "print('| model | size | params | backend | ngl | test | t/s |')\n"
            "print('| fake | 1 MiB | 1M | CPU | 0 | pp16 | 12.50 ± 0.01 |')\n",
            encoding="utf-8",
        )
        (install / "llama-bench").chmod(0o755)
        managed = self.client.post(
            "/v1/deployments/managed",
            json={"bundle_id": job["bundle_id"], "auto_start": False},
        ).json()
        body = self.client.post(
            "/v1/lab/engine-measurements",
            json={"deployment_id": managed["id"]},
        ).json()
        self.assertTrue(body["available"])
        self.assertTrue(body["success"])
        self.assertIsNotNone(body["scores"])
        self.assertIn("pp16", body["scores"])
        self.assertEqual(body["kind"], "engine_measurement")
        self.assertNotEqual(body["kind"], "task_evaluation")

    def test_capture_restore_rerun_leaves_parent_unchanged(self) -> None:
        workspace = self._workspace()
        run = self._complete_run(workspace["id"])
        captured = self.client.post(
            "/v1/lab/cases/capture",
            json={"workspace_id": workspace["id"], "run_id": run["id"]},
        )
        self.assertEqual(captured.status_code, 200, captured.text)
        case = captured.json()
        self.assertTrue(case["snapshot_id"].startswith("snap_"))
        self.assertEqual(case["task"], run["task"])
        self.assertEqual(case["deployment_id"], self.deployment_id)
        self.assertTrue(case["dependency_versions"])
        self.assertEqual(case["memory_version_refs"], [])
        self.assertEqual(case["environment_restore"], "not_this_milestone")
        self.assertEqual(case["rollback_promise"], "none")
        self.assertEqual(case["external_effect_rollback"], "not_supported")
        snapshot = self.client.get(f"/v1/lab/snapshots/{case['snapshot_id']}").json()
        self.assertEqual(snapshot["mechanism"], "application_directory_snapshot")
        self.assertTrue(snapshot["not_git_commit"])
        self.assertEqual(snapshot["kind"], "starting")
        self.assertEqual(snapshot["rollback_promise"], "none")
        self.assertEqual(snapshot["external_effect_rollback"], "not_supported")
        self.assertEqual(case["snapshot_kind"], "starting")
        self.assertEqual(case["input_origin"], "starting_snapshot")
        self.assertEqual(run["starting_snapshot_id"], case["snapshot_id"])
        self.assertTrue((self.paths.snapshots / case["snapshot_id"] / "tree" / "notes.md").is_file())

        changed = self.client.put(
            f"/v1/lab/workspaces/{workspace['id']}/files",
            json={"files": {"notes.md": "parent changed after capture"}},
        )
        self.assertEqual(changed.status_code, 200, changed.text)
        parent_files = self.client.get(f"/v1/lab/workspaces/{workspace['id']}/files").json()["files"]
        self.assertEqual(parent_files["notes.md"], "parent changed after capture")

        restored = self.client.post(f"/v1/lab/cases/{case['id']}/restore")
        self.assertEqual(restored.status_code, 200, restored.text)
        restore = restored.json()
        self.assertTrue(restore["parent_unchanged"])
        self.assertFalse(restore["external_effects_rolled_back"])
        self.assertEqual(restore["rollback_promise"], "none")
        self.assertEqual(restore["branch"]["kind"], "linked_branch")
        self.assertNotEqual(restore["workspace"]["id"], workspace["id"])
        self.assertEqual(restore["workspace"]["origin"], "restored")
        child_files = self.client.get(
            f"/v1/lab/workspaces/{restore['workspace']['id']}/files"
        ).json()["files"]
        self.assertEqual(child_files["notes.md"], "original notes")
        parent_after = self.client.get(f"/v1/lab/workspaces/{workspace['id']}/files").json()["files"]
        self.assertEqual(parent_after["notes.md"], "parent changed after capture")

        rerun = self.client.post(
            f"/v1/lab/cases/{case['id']}/rerun",
            json={"tool_mode": "live-tool", "workspace_id": restore["workspace"]["id"]},
        )
        self.assertEqual(rerun.status_code, 200, rerun.text)
        result = wait_for_lab_result(self.client, rerun.json()["id"])
        self.assertEqual(result["evaluation_kind"], "task_evaluation")
        self.assertEqual(result["harness"], "deepagents")
        self.assertEqual(result["adapter"], "mod-005")
        self.assertFalse(result["second_agent_loop"])
        self.assertEqual(result["tool_mode"], "live-tool")
        self.assertTrue(result["parent_workspace_unchanged"])
        self.assertTrue(result["evidence"]["executable_checks"][0]["passed"])
        self.assertIn("not an executable check", result["judgement"]["note"].lower())
        parent_final = self.client.get(f"/v1/lab/workspaces/{workspace['id']}/files").json()["files"]
        self.assertEqual(parent_final["notes.md"], "parent changed after capture")
        source = self.client.get(f"/v1/agent-runs/{run['id']}").json()
        self.assertEqual(source["status"], "completed")
        self.assertEqual(source["id"], run["id"])

    def test_snapshot_excludes_secrets_weights_scratch_venv_and_credentials(self) -> None:
        workspace = self._workspace({"keep.md": "safe"})
        project = Path(workspace["path"])
        (project / ".env").write_text("API_KEY=SECRET_VALUE\n", encoding="utf-8")
        (project / "credentials.json").write_text('{"token":"SECRET_VALUE"}', encoding="utf-8")
        (project / "weights.gguf").write_bytes(b"GGUF")
        scratch = project / ".scratch" / "tmp.txt"
        scratch.parent.mkdir(parents=True)
        scratch.write_text("scratch", encoding="utf-8")
        venv_file = project / ".venv" / "lib.py"
        venv_file.parent.mkdir(parents=True)
        venv_file.write_text("venv", encoding="utf-8")
        nm = project / "node_modules" / "pkg" / "index.js"
        nm.parent.mkdir(parents=True)
        nm.write_text("nm", encoding="utf-8")
        run = self._complete_run(workspace["id"])
        case = self.client.post(
            "/v1/lab/cases/capture",
            json={"workspace_id": workspace["id"], "run_id": run["id"]},
        ).json()
        snapshot = self.client.get(f"/v1/lab/snapshots/{case['snapshot_id']}").json()
        reasons = {item["path"]: item["reason"] for item in snapshot["exclusions"]}
        self.assertEqual(reasons[".env"], "env_credentials")
        self.assertEqual(reasons["credentials.json"], "secrets")
        self.assertEqual(reasons["weights.gguf"], "weights")
        self.assertEqual(reasons[".scratch/tmp.txt"], "scratch")
        self.assertEqual(reasons[".venv/lib.py"], "venv")
        self.assertEqual(reasons["node_modules/pkg/index.js"], "node_modules")
        included = {item["path"] for item in snapshot["included_files"]}
        self.assertIn("keep.md", included)
        self.assertNotIn(".env", included)
        tree = self.paths.snapshots / case["snapshot_id"] / "tree"
        self.assertFalse((tree / ".env").exists())
        self.assertFalse((tree / "weights.gguf").exists())
        export = self.client.get(f"/v1/lab/cases/{case['id']}/export").json()
        self.assertTrue(export["secret_scan_clean"])
        dumped = json.dumps(export)
        self.assertNotIn("SECRET_VALUE", dumped)
        self.assertEqual(export["snapshot"]["environment_restore"], "not_this_milestone")

    def test_capture_fails_when_run_is_still_writing(self) -> None:
        workspace = self._workspace()
        slow = ScriptedChatModel(echo_then_reply(), delay_s=0.6)

        def factory(_run: AgentRun, _sink: list[dict[str, Any]]) -> ScriptedChatModel:
            return slow

        self.app.state.harness = HarnessService(lambda: self.manager, model_factory=factory)
        started = self.client.post(
            "/v1/agent-runs",
            json={
                "deployment_id": self.deployment_id,
                "task": "slow",
                "workspace_id": workspace["id"],
                "presented_tools": ["echo"],
            },
        ).json()
        blocked = self.client.post(
            "/v1/lab/cases/capture",
            json={"workspace_id": workspace["id"], "run_id": started["id"]},
        )
        self.assertEqual(blocked.status_code, 409)
        self.assertEqual(blocked.json()["code"], "not_quiescent")
        wait_for_run(self.client, started["id"])

    def test_capture_fails_while_cancel_requested(self) -> None:
        workspace = self._workspace()
        now = utc_now()
        run = AgentRun(
            id="agent_lab_cancel_requested",
            status=AgentRunStatus.cancel_requested,
            deployment_id=self.deployment_id,
            task="held for capture",
            enabled_tools=["echo"],
            presented_tools=["echo"],
            created_at=now,
            updated_at=now,
            workspace_id=workspace["id"],
        )
        harness = self.app.state.harness
        with harness._lock:
            harness._runs[run.id] = run
            harness._cancels[run.id] = threading.Event()
        blocked = self.client.post(
            "/v1/lab/cases/capture",
            json={"workspace_id": workspace["id"], "run_id": run.id},
        )
        self.assertEqual(blocked.status_code, 409)
        self.assertEqual(blocked.json()["code"], "not_quiescent")

    def test_recorded_and_live_modes_are_labelled(self) -> None:
        workspace = self._workspace()
        run = self._complete_run(workspace["id"])
        case = self.client.post(
            "/v1/lab/cases/capture",
            json={"workspace_id": workspace["id"], "run_id": run["id"]},
        ).json()
        restore = self.client.post(f"/v1/lab/cases/{case['id']}/restore").json()
        live = wait_for_lab_result(
            self.client,
            self.client.post(
                f"/v1/lab/cases/{case['id']}/rerun",
                json={"tool_mode": "live-tool", "workspace_id": restore["workspace"]["id"]},
            ).json()["id"],
        )
        restore_b = self.client.post(f"/v1/lab/cases/{case['id']}/restore").json()
        recorded = wait_for_lab_result(
            self.client,
            self.client.post(
                f"/v1/lab/cases/{case['id']}/rerun",
                json={"tool_mode": "recorded-tool", "workspace_id": restore_b["workspace"]["id"]},
            ).json()["id"],
        )
        self.assertEqual(live["tool_mode"], "live-tool")
        self.assertEqual(live["tool_mode_label"], "live-tool")
        self.assertFalse(live["recorded_is_not_live_proof"])
        self.assertEqual(recorded["tool_mode"], "recorded-tool")
        self.assertIn("not proof", recorded["tool_mode_label"])
        self.assertTrue(recorded["recorded_is_not_live_proof"])
        self.assertNotEqual(recorded["tool_mode"], live["tool_mode"])
        self.assertIn("not proof of a current live integration", " ".join(recorded["deviations"]).lower())

    def test_two_reruns_preserve_applied_config_and_failing_check(self) -> None:
        workspace = self._workspace()
        run = self._complete_run(workspace["id"])
        case = self.client.post(
            "/v1/lab/cases/capture",
            json={"workspace_id": workspace["id"], "run_id": run["id"]},
        ).json()
        restore_a = self.client.post(f"/v1/lab/cases/{case['id']}/restore").json()
        passing = wait_for_lab_result(
            self.client,
            self.client.post(
                f"/v1/lab/cases/{case['id']}/rerun",
                json={"tool_mode": "live-tool", "workspace_id": restore_a["workspace"]["id"]},
            ).json()["id"],
        )
        restore_b = self.client.post(f"/v1/lab/cases/{case['id']}/restore").json()
        failing = wait_for_lab_result(
            self.client,
            self.client.post(
                f"/v1/lab/cases/{case['id']}/rerun",
                json={
                    "tool_mode": "live-tool",
                    "workspace_id": restore_b["workspace"]["id"],
                    "criteria": {
                        "checks": ["tool:time_now"],
                        "expected_artifacts": ["assistant_reply"],
                    },
                },
            ).json()["id"],
        )
        self.assertTrue(passing["evidence"]["executable_checks"][0]["passed"])
        self.assertFalse(failing["evidence"]["executable_checks"][0]["passed"])
        self.assertEqual(failing["applied_config"]["criteria"]["checks"], ["tool:time_now"])
        self.assertNotEqual(passing["applied_config"]["criteria"], failing["applied_config"]["criteria"])
        self.assertEqual(passing["applied_config"]["harness"], "deepagents")
        self.assertEqual(failing["applied_config"]["adapter"], "mod-005")
        self.assertIn("overridden", " ".join(failing["deviations"]).lower())
        self.assertNotEqual(passing["evidence"], passing["judgement"])

    def test_engine_and_task_eval_are_separate_and_share_harness(self) -> None:
        workspace = self._workspace()
        run = self._complete_run(workspace["id"])
        case = self.client.post(
            "/v1/lab/cases/capture",
            json={"workspace_id": workspace["id"], "run_id": run["id"]},
        ).json()
        restore = self.client.post(f"/v1/lab/cases/{case['id']}/restore").json()
        task = wait_for_lab_result(
            self.client,
            self.client.post(
                f"/v1/lab/cases/{case['id']}/rerun",
                json={"tool_mode": "live-tool", "workspace_id": restore["workspace"]["id"]},
            ).json()["id"],
        )
        engine = self.client.post("/v1/lab/engine-measurements", json={}).json()
        self.assertEqual(task["evaluation_kind"], "task_evaluation")
        self.assertEqual(engine["kind"], "engine_measurement")
        self.assertNotEqual(task["evaluation_kind"], engine["kind"])
        self.assertEqual(task["harness"], "deepagents")
        self.assertFalse(task["second_agent_loop"])
        self.assertIsNone(engine["scores"])
        child_run = self.client.get(f"/v1/agent-runs/{task['agent_run_id']}").json()
        self.assertEqual(child_run["harness"], "deepagents")
        self.assertEqual(child_run["parent_run_id"], run["id"])

    def _capture_without_run(self, workspace_id: str) -> dict[str, Any]:
        captured = self.client.post(
            "/v1/lab/cases/capture",
            json={
                "workspace_id": workspace_id,
                "task": "restore-integrity",
                "deployment_id": self.deployment_id,
            },
        )
        self.assertEqual(captured.status_code, 200, captured.text)
        return captured.json()

    def _assert_no_restored_workspace(self, parent_id: str) -> None:
        listed = self.client.get("/v1/lab/workspaces").json()
        self.assertEqual([item["id"] for item in listed], [parent_id])
        self.assertFalse(any(item.get("origin") == "restored" for item in listed))
        leftover = {
            path.name
            for path in self.paths.workspaces.iterdir()
            if path.is_dir() and path.name != parent_id
        }
        self.assertEqual(leftover, set())

    def test_restore_fails_when_tree_is_missing(self) -> None:
        workspace = self._workspace()
        parent_before = self.client.get(f"/v1/lab/workspaces/{workspace['id']}/files").json()["files"]
        case = self._capture_without_run(workspace["id"])
        shutil.rmtree(self.paths.snapshots / case["snapshot_id"] / "tree")
        failed = self.client.post(f"/v1/lab/cases/{case['id']}/restore")
        self.assertEqual(failed.status_code, 409, failed.text)
        self.assertEqual(failed.json()["code"], "snapshot_tree_missing")
        self._assert_no_restored_workspace(workspace["id"])
        parent_after = self.client.get(f"/v1/lab/workspaces/{workspace['id']}/files").json()["files"]
        self.assertEqual(parent_after, parent_before)

    def test_restore_fails_on_hash_mismatch_and_missing_file(self) -> None:
        workspace = self._workspace()
        parent_before = self.client.get(f"/v1/lab/workspaces/{workspace['id']}/files").json()["files"]
        case = self._capture_without_run(workspace["id"])
        tree = self.paths.snapshots / case["snapshot_id"] / "tree"
        (tree / "notes.md").write_text("bytes changed after capture", encoding="utf-8")
        mismatched = self.client.post(f"/v1/lab/cases/{case['id']}/restore")
        self.assertEqual(mismatched.status_code, 409, mismatched.text)
        self.assertEqual(mismatched.json()["code"], "snapshot_hash_mismatch")
        self._assert_no_restored_workspace(workspace["id"])

        (tree / "notes.md").unlink()
        missing = self.client.post(f"/v1/lab/cases/{case['id']}/restore")
        self.assertEqual(missing.status_code, 409, missing.text)
        self.assertEqual(missing.json()["code"], "snapshot_file_missing")
        self._assert_no_restored_workspace(workspace["id"])
        parent_after = self.client.get(f"/v1/lab/workspaces/{workspace['id']}/files").json()["files"]
        self.assertEqual(parent_after, parent_before)

    def test_restore_fails_on_unexpected_tree_file_and_leaves_parent(self) -> None:
        workspace = self._workspace()
        parent_before = self.client.get(f"/v1/lab/workspaces/{workspace['id']}/files").json()["files"]
        case = self._capture_without_run(workspace["id"])
        tree = self.paths.snapshots / case["snapshot_id"] / "tree"
        (tree / "surprise.txt").write_text("not recorded", encoding="utf-8")
        failed = self.client.post(f"/v1/lab/cases/{case['id']}/restore")
        self.assertEqual(failed.status_code, 409, failed.text)
        self.assertEqual(failed.json()["code"], "snapshot_unexpected_file")
        self._assert_no_restored_workspace(workspace["id"])
        parent_after = self.client.get(f"/v1/lab/workspaces/{workspace['id']}/files").json()["files"]
        self.assertEqual(parent_after, parent_before)

    def test_empty_snapshot_restores_to_empty_workspace(self) -> None:
        workspace = self.client.post(
            "/v1/lab/workspaces",
            json={"display_name": "empty-project", "files": {}},
        ).json()
        case = self._capture_without_run(workspace["id"])
        snapshot = self.client.get(f"/v1/lab/snapshots/{case['snapshot_id']}").json()
        self.assertEqual(snapshot["included_files"], [])
        self.assertTrue((self.paths.snapshots / case["snapshot_id"] / "tree").is_dir())
        restored = self.client.post(f"/v1/lab/cases/{case['id']}/restore")
        self.assertEqual(restored.status_code, 200, restored.text)
        restore = restored.json()
        self.assertTrue(restore["parent_unchanged"])
        self.assertEqual(restore["workspace"]["origin"], "restored")
        child_files = self.client.get(
            f"/v1/lab/workspaces/{restore['workspace']['id']}/files"
        ).json()["files"]
        self.assertEqual(child_files, {})
        parent_files = self.client.get(f"/v1/lab/workspaces/{workspace['id']}/files").json()["files"]
        self.assertEqual(parent_files, {})

    def test_mutating_task_case_restore_yields_starting_inputs_not_mutated_files(self) -> None:
        original = "BUG: off-by-one in adder\n"
        mutated = "FIXED: adder handles the boundary\n"
        later_parent = "parent edited after the completed run\n"
        workspace = self._workspace({"notes.md": original, "src/hello.py": "print('hi')\n"})

        def factory(_run: AgentRun, _sink: list[dict[str, Any]]) -> ScriptedChatModel:
            return ScriptedChatModel(
                [
                    AIMessage(
                        content="",
                        tool_calls=[
                            {
                                "name": "write_file",
                                "args": {"file_path": "/notes.md", "content": mutated},
                                "id": "call_write_notes",
                            }
                        ],
                    ),
                    AIMessage(content="Wrote the fixed notes."),
                ]
            )

        self.app.state.harness = HarnessService(
            lambda: self.manager,
            model_factory=factory,
            app_store=self.app.state.app_store,
        )
        self.app.state.lab._harness_provider = lambda: self.app.state.harness

        started = self.client.post(
            "/v1/agent-runs",
            json={
                "deployment_id": self.deployment_id,
                "task": "Fix the adder bug in notes.md",
                "workspace_id": workspace["id"],
                "project_path": workspace["path"],
                "presented_tools": ["write_file"],
            },
        )
        self.assertEqual(started.status_code, 200, started.text)
        run = wait_for_run(self.client, started.json()["id"])
        self.assertEqual(run["status"], "completed", run.get("error"))
        self.assertTrue(run["starting_snapshot_id"])
        parent_after_run = self.client.get(f"/v1/lab/workspaces/{workspace['id']}/files").json()["files"]
        self.assertEqual(parent_after_run["notes.md"], mutated)

        captured = self.client.post(
            "/v1/lab/cases/capture",
            json={"workspace_id": workspace["id"], "run_id": run["id"]},
        )
        self.assertEqual(captured.status_code, 200, captured.text)
        case = captured.json()
        self.assertEqual(case["snapshot_id"], run["starting_snapshot_id"])
        self.assertEqual(case["snapshot_kind"], "starting")
        self.assertEqual(case["input_origin"], "starting_snapshot")
        snapshot = self.client.get(f"/v1/lab/snapshots/{case['snapshot_id']}").json()
        self.assertEqual(snapshot["kind"], "starting")
        tree_notes = (self.paths.snapshots / case["snapshot_id"] / "tree" / "notes.md").read_text(
            encoding="utf-8"
        )
        self.assertEqual(tree_notes, original)
        self.assertNotEqual(tree_notes, mutated)

        changed = self.client.put(
            f"/v1/lab/workspaces/{workspace['id']}/files",
            json={"files": {"notes.md": later_parent}},
        )
        self.assertEqual(changed.status_code, 200, changed.text)
        parent_after_edit = self.client.get(f"/v1/lab/workspaces/{workspace['id']}/files").json()["files"]
        self.assertEqual(parent_after_edit["notes.md"], later_parent)
        still_original = (self.paths.snapshots / case["snapshot_id"] / "tree" / "notes.md").read_text(
            encoding="utf-8"
        )
        self.assertEqual(still_original, original)

        restored = self.client.post(f"/v1/lab/cases/{case['id']}/restore")
        self.assertEqual(restored.status_code, 200, restored.text)
        restore = restored.json()
        self.assertTrue(restore["parent_unchanged"])
        self.assertEqual(restore["snapshot_kind"], "starting")
        self.assertEqual(restore["input_origin"], "starting_snapshot")
        self.assertNotEqual(restore["workspace"]["id"], workspace["id"])
        child_files = self.client.get(
            f"/v1/lab/workspaces/{restore['workspace']['id']}/files"
        ).json()["files"]
        self.assertEqual(child_files["notes.md"], original)
        self.assertNotEqual(child_files["notes.md"], mutated)
        parent_after_restore = self.client.get(f"/v1/lab/workspaces/{workspace['id']}/files").json()["files"]
        self.assertEqual(parent_after_restore["notes.md"], later_parent)

        rerun = self.client.post(
            f"/v1/lab/cases/{case['id']}/rerun",
            json={"tool_mode": "live-tool", "workspace_id": restore["workspace"]["id"]},
        )
        self.assertEqual(rerun.status_code, 200, rerun.text)
        result = wait_for_lab_result(self.client, rerun.json()["id"])
        self.assertTrue(result["parent_workspace_unchanged"])
        parent_final = self.client.get(f"/v1/lab/workspaces/{workspace['id']}/files").json()["files"]
        self.assertEqual(parent_final["notes.md"], later_parent)

    def test_legacy_run_without_starting_snapshot_is_unavailable(self) -> None:
        workspace = self._workspace()
        now = utc_now()
        run = AgentRun(
            id="agent_legacy_no_starting_snapshot",
            status=AgentRunStatus.completed,
            deployment_id=self.deployment_id,
            task="legacy completed run",
            enabled_tools=["echo"],
            presented_tools=["echo"],
            created_at=now,
            updated_at=now,
            workspace_id=workspace["id"],
            starting_snapshot_id=None,
        )
        self.app.state.harness.store.put_run(run)
        blocked = self.client.post(
            "/v1/lab/cases/capture",
            json={"workspace_id": workspace["id"], "run_id": run.id},
        )
        self.assertEqual(blocked.status_code, 409, blocked.text)
        body = blocked.json()
        self.assertEqual(body["code"], "starting_snapshot_unavailable")
        self.assertTrue(body["degraded"])
        self.assertEqual(body["original_inputs"], "unavailable")
        self.assertIn("unavailable", body["error"].lower())
        self.assertNotIn("original inputs captured", body["error"].lower())
        self.assertFalse(self.client.get("/v1/lab/cases").json())

    def test_rerun_rejects_parent_workspace(self) -> None:
        workspace = self._workspace()
        run = self._complete_run(workspace["id"])
        case = self.client.post(
            "/v1/lab/cases/capture",
            json={"workspace_id": workspace["id"], "run_id": run["id"]},
        ).json()
        denied = self.client.post(
            f"/v1/lab/cases/{case['id']}/rerun",
            json={"tool_mode": "live-tool", "workspace_id": workspace["id"]},
        )
        self.assertEqual(denied.status_code, 409)
        self.assertEqual(denied.json()["code"], "restore_required")


if __name__ == "__main__":
    unittest.main()
