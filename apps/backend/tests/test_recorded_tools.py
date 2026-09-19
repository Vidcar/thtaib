"""Issue #67 recorded-tool replay: FS fixtures, arg match, no live FS."""

from __future__ import annotations

import tempfile
import time
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch

from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage

from workbench_backend.agents import harness_backend as harness_backend_mod
from workbench_backend.agents.harness import HarnessService
from workbench_backend.agents.replay import (
    FixtureBank,
    apply_recorded_reconstruction,
    isolated_replay_path,
)
from workbench_backend.agents.schemas import AgentRun
from workbench_backend.app import create_app
from workbench_backend.errors import ReplayError
from workbench_backend.inference.service import ModelManager
from workbench_backend.paths import WorkbenchPaths

from tests.scripted_model import ScriptedChatModel
from tests.support import close_workbench_sqlite, workbench_client


def wait_for_run(client: TestClient, run_id: str, *, timeout: float = 20.0) -> dict[str, Any]:
    deadline = time.time() + timeout
    body: dict[str, Any] = {}
    while time.time() < deadline:
        response = client.get(f"/v1/agent-runs/{run_id}")
        body = response.json()
        if body.get("status") in {"completed", "cancelled", "failed"}:
            return body
        time.sleep(0.05)
    raise TimeoutError(f"run {run_id} did not finish: {body}")


def wait_for_lab_result(client: TestClient, result_id: str, *, timeout: float = 20.0) -> dict[str, Any]:
    deadline = time.time() + timeout
    body: dict[str, Any] = {}
    while time.time() < deadline:
        response = client.get(f"/v1/lab/results/{result_id}")
        body = response.json()
        evidence = body.get("evidence") or {}
        if evidence.get("executable_checks") or body.get("judgement") or body.get("deviations"):
            run = client.get(f"/v1/agent-runs/{body['agent_run_id']}").json()
            if run.get("status") in {"completed", "cancelled", "failed"}:
                return client.get(f"/v1/lab/results/{result_id}").json()
        time.sleep(0.05)
    raise TimeoutError(f"lab result {result_id} did not finish: {body}")


def write_then_reply(path: str, content: str, call_id: str = "call_write") -> list[AIMessage]:
    return [
        AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "write_file",
                    "args": {"file_path": path, "content": content},
                    "id": call_id,
                }
            ],
        ),
        AIMessage(content=f"Wrote {path} in the replay workspace."),
    ]


def echo_then_reply(text: str, call_id: str = "call_echo") -> list[AIMessage]:
    return [
        AIMessage(
            content="",
            tool_calls=[{"name": "echo", "args": {"text": text}, "id": call_id}],
        ),
        AIMessage(content=f"echoed {text}"),
    ]


def two_echoes(first: str, second: str) -> list[AIMessage]:
    return [
        AIMessage(
            content="",
            tool_calls=[{"name": "echo", "args": {"text": first}, "id": "call_echo_1"}],
        ),
        AIMessage(
            content="",
            tool_calls=[{"name": "echo", "args": {"text": second}, "id": "call_echo_2"}],
        ),
        AIMessage(content="two echoes"),
    ]


class FixtureBankTests(unittest.TestCase):
    def test_same_tool_different_args_do_not_consume_each_other(self) -> None:
        bank = FixtureBank(
            [
                {"name": "echo", "args": {"text": "alpha"}, "result": "from-alpha"},
                {"name": "echo", "args": {"text": "beta"}, "result": "from-beta"},
            ]
        )
        self.assertEqual(bank.take("echo", {"text": "beta"}), "from-beta")
        self.assertEqual(bank.take("echo", {"text": "alpha"}), "from-alpha")

    def test_mismatch_does_not_consume_the_other_fixture(self) -> None:
        bank = FixtureBank(
            [
                {"name": "write_file", "args": {"file_path": "/a.md", "content": "A"}, "result": "wrote-a"},
                {"name": "write_file", "args": {"file_path": "/b.md", "content": "B"}, "result": "wrote-b"},
            ]
        )
        with self.assertRaises(ReplayError) as raised:
            bank.take("write_file", {"file_path": "/a.md", "content": "WRONG"})
        self.assertEqual(raised.exception.code, "recorded_fixture_arg_mismatch")
        self.assertEqual(
            bank.take("write_file", {"file_path": "/a.md", "content": "A"}),
            "wrote-a",
        )

    def test_missing_and_exhausted_are_structured_failures(self) -> None:
        bank = FixtureBank([{"name": "echo", "args": {"text": "once"}, "result": "ok"}])
        with self.assertRaises(ReplayError) as missing:
            bank.take("write_file", {"file_path": "/x.md", "content": "x"})
        self.assertEqual(missing.exception.code, "recorded_fixture_missing")
        self.assertEqual(bank.take("echo", {"text": "once"}), "ok")
        with self.assertRaises(ReplayError) as exhausted:
            bank.take("echo", {"text": "once"})
        self.assertEqual(exhausted.exception.code, "recorded_fixture_exhausted")

    def test_path_identity_strips_leading_slash(self) -> None:
        bank = FixtureBank(
            [
                {
                    "name": "write_file",
                    "args": {"file_path": "notes.md", "content": "hi"},
                    "result": "wrote",
                }
            ]
        )
        self.assertEqual(
            bank.take("write_file", {"file_path": "/notes.md", "content": "hi"}),
            "wrote",
        )

    def test_reconstruction_stays_inside_replay_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspace = root / "replay"
            workspace.mkdir()
            outside = root / "outside.txt"
            outside.write_text("sentinel", encoding="utf-8")
            actions = apply_recorded_reconstruction(
                "write_file",
                {"file_path": "/inside.md", "content": "from-fixture"},
                workspace,
            )
            self.assertEqual((workspace / "inside.md").read_text(encoding="utf-8"), "from-fixture")
            self.assertEqual(outside.read_text(encoding="utf-8"), "sentinel")
            self.assertEqual(actions[0]["tool"], "write_file")
            with self.assertRaises(ReplayError) as raised:
                isolated_replay_path(workspace, "../outside.txt")
            self.assertEqual(raised.exception.code, "recorded_replay_unsupported")


class RecordedToolHarnessTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.project = self.root / "replay-project"
        self.project.mkdir()
        self.outside = self.root / "outside-sentinel.txt"
        self.outside.write_text("untouched", encoding="utf-8")
        self.manager = ModelManager(WorkbenchPaths(self.root).ensure())
        self.app = create_app(data_root=self.root)
        self.app.state.manager = self.manager
        self.client = workbench_client(self.app)
        self.deployment_id = self.client.post(
            "/v1/deployments/connected",
            json={"endpoint": "http://127.0.0.1:9/v1", "display_name": "recorded-fixture"},
        ).json()["id"]
        self.fs_constructions: list[tuple[tuple[Any, ...], dict[str, Any]]] = []
        self.shell_constructions: list[tuple[tuple[Any, ...], dict[str, Any]]] = []

    def tearDown(self) -> None:
        close_workbench_sqlite(self.app, getattr(self, "client", None))
        self.tmp.cleanup()

    def _install_script(self, script: list[AIMessage]) -> None:
        model = ScriptedChatModel(script)

        def factory(_run: AgentRun, _sink: list[dict[str, Any]]) -> ScriptedChatModel:
            return model

        self.app.state.harness = HarnessService(
            lambda: self.manager,
            model_factory=factory,
            app_store=self.app.state.app_store,
        )

    def _spy_filesystem_backend(self) -> Any:
        constructions = self.fs_constructions
        real = harness_backend_mod.FilesystemBackend

        def wrapper(*args: Any, **kwargs: Any) -> Any:
            constructions.append((args, kwargs))
            return real(*args, **kwargs)

        return patch.object(harness_backend_mod, "FilesystemBackend", side_effect=wrapper)

    def _spy_local_shell_backend(self) -> Any:
        constructions = self.shell_constructions
        real = harness_backend_mod.LocalShellBackend

        def wrapper(*args: Any, **kwargs: Any) -> Any:
            constructions.append((args, kwargs))
            return real(*args, **kwargs)

        return patch.object(harness_backend_mod, "LocalShellBackend", side_effect=wrapper)

    def test_recorded_write_file_does_not_use_live_filesystem_backend(self) -> None:
        self._install_script(write_then_reply("/replay.md", "fixture-bytes"))
        with self._spy_filesystem_backend(), self._spy_local_shell_backend():
            started = self.client.post(
                "/v1/agent-runs",
                json={
                    "deployment_id": self.deployment_id,
                    "task": "Write replay.md",
                    "project_path": str(self.project),
                    "presented_tools": ["write_file"],
                    "tool_mode": "recorded-tool",
                    "recorded_fixtures": [
                        {
                            "name": "write_file",
                            "args": {"file_path": "/replay.md", "content": "fixture-bytes"},
                            "result": "Updated file /replay.md",
                        }
                    ],
                },
            )
            self.assertEqual(started.status_code, 200, started.text)
            body = wait_for_run(self.client, started.json()["id"])
        self.assertEqual(body["status"], "completed", body.get("error"))
        self.assertEqual(body["tool_mode"], "recorded-tool")
        self.assertIn("not proof", body["tool_mode_label"])
        self.assertTrue(body["recorded_is_not_live_proof"])
        self.assertEqual(self.fs_constructions, [])
        self.assertEqual(self.shell_constructions, [])
        self.assertEqual((self.project / "replay.md").read_text(encoding="utf-8"), "fixture-bytes")
        self.assertEqual(self.outside.read_text(encoding="utf-8"), "untouched")
        kinds = [event["kind"] for event in body["events"]]
        self.assertIn("recorded_reconstruction", kinds)

    def test_two_write_file_args_do_not_consume_each_other(self) -> None:
        self._install_script(write_then_reply("/b.md", "BBB", call_id="call_b"))
        with self._spy_filesystem_backend(), self._spy_local_shell_backend():
            started = self.client.post(
                "/v1/agent-runs",
                json={
                    "deployment_id": self.deployment_id,
                    "task": "Write b.md",
                    "project_path": str(self.project),
                    "presented_tools": ["write_file"],
                    "tool_mode": "recorded-tool",
                    "recorded_fixtures": [
                        {
                            "name": "write_file",
                            "args": {"file_path": "/a.md", "content": "AAA"},
                            "result": "Updated file /a.md",
                        },
                        {
                            "name": "write_file",
                            "args": {"file_path": "/b.md", "content": "BBB"},
                            "result": "Updated file /b.md",
                        },
                    ],
                },
            )
            body = wait_for_run(self.client, started.json()["id"])
        self.assertEqual(body["status"], "completed", body.get("error"))
        self.assertEqual(self.fs_constructions, [])
        self.assertEqual(self.shell_constructions, [])
        self.assertFalse((self.project / "a.md").exists())
        self.assertEqual((self.project / "b.md").read_text(encoding="utf-8"), "BBB")

    def test_mismatched_write_file_args_fail_without_reconstruction(self) -> None:
        self._install_script(write_then_reply("/a.md", "WRONG"))
        started = self.client.post(
            "/v1/agent-runs",
            json={
                "deployment_id": self.deployment_id,
                "task": "Write a.md",
                "project_path": str(self.project),
                "presented_tools": ["write_file"],
                "tool_mode": "recorded-tool",
                "recorded_fixtures": [
                    {
                        "name": "write_file",
                        "args": {"file_path": "/a.md", "content": "AAA"},
                        "result": "Updated file /a.md",
                    }
                ],
            },
        )
        body = wait_for_run(self.client, started.json()["id"])
        self.assertEqual(body["status"], "failed")
        self.assertIn("do not match", (body.get("error") or "").lower())
        self.assertFalse((self.project / "a.md").exists())
        kinds = [event["kind"] for event in body["events"]]
        self.assertIn("recorded_replay_failed", kinds)

    def test_exhausted_echo_fixture_fails(self) -> None:
        self._install_script(two_echoes("once", "once"))
        started = self.client.post(
            "/v1/agent-runs",
            json={
                "deployment_id": self.deployment_id,
                "task": "echo twice",
                "presented_tools": ["echo"],
                "tool_mode": "recorded-tool",
                "recorded_fixtures": [{"name": "echo", "args": {"text": "once"}, "result": "once"}],
            },
        )
        body = wait_for_run(self.client, started.json()["id"])
        self.assertEqual(body["status"], "failed")
        self.assertIn("exhausted", (body.get("error") or "").lower())

    def test_live_write_file_still_uses_project_backend_and_is_labelled(self) -> None:
        self._install_script(write_then_reply("/live.md", "live-bytes"))
        with self._spy_filesystem_backend(), self._spy_local_shell_backend():
            started = self.client.post(
                "/v1/agent-runs",
                json={
                    "deployment_id": self.deployment_id,
                    "task": "Write live.md",
                    "project_path": str(self.project),
                    "presented_tools": ["write_file"],
                    "tool_mode": "live-tool",
                },
            )
            body = wait_for_run(self.client, started.json()["id"])
        self.assertEqual(body["status"], "completed", body.get("error"))
        self.assertEqual(body["tool_mode"], "live-tool")
        self.assertEqual(body["tool_mode_label"], "live-tool")
        self.assertFalse(body["recorded_is_not_live_proof"])
        self.assertEqual(self.shell_constructions, [])
        self.assertEqual(len(self.fs_constructions), 3)
        roots = [
            Path(kwargs.get("root_dir") or (args[0] if args else "")).resolve()
            for args, kwargs in self.fs_constructions
        ]
        self.assertIn(self.project.resolve(), roots)
        self.assertTrue(any(path.name == "large_tool_results" for path in roots))
        self.assertTrue(any(path.name == "conversation_history" for path in roots))
        self.assertEqual((self.project / "live.md").read_text(encoding="utf-8"), "live-bytes")
        self.assertFalse((self.project / "large_tool_results").exists())
        self.assertFalse((self.project / "conversation_history").exists())


class RecordedToolLabTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.manager = ModelManager(WorkbenchPaths(self.root).ensure())
        self.app = create_app(data_root=self.root)
        self.app.state.manager = self.manager
        self._install_script(write_then_reply("/case.md", "case-bytes"))
        self.client = workbench_client(self.app)
        self.deployment_id = self.client.post(
            "/v1/deployments/connected",
            json={"endpoint": "http://127.0.0.1:9/v1", "display_name": "lab-recorded"},
        ).json()["id"]

    def tearDown(self) -> None:
        close_workbench_sqlite(self.app, getattr(self, "client", None))
        self.tmp.cleanup()

    def _install_script(self, script: list[AIMessage]) -> None:
        def factory(_run: AgentRun, _sink: list[dict[str, Any]]) -> ScriptedChatModel:
            return ScriptedChatModel(script)

        self.app.state.harness = HarnessService(
            lambda: self.manager,
            model_factory=factory,
            app_store=self.app.state.app_store,
        )
        self.app.state.lab._manager_provider = lambda: self.manager
        self.app.state.lab._harness_provider = lambda: self.app.state.harness

    def test_lab_recorded_write_file_leaves_parent_and_is_labelled(self) -> None:
        workspace = self.client.post(
            "/v1/lab/workspaces",
            json={"display_name": "case-project", "files": {"notes.md": "original"}},
        ).json()
        live = wait_for_run(
            self.client,
            self.client.post(
                "/v1/agent-runs",
                json={
                    "deployment_id": self.deployment_id,
                    "task": "Write case.md",
                    "workspace_id": workspace["id"],
                    "project_path": workspace["path"],
                    "presented_tools": ["write_file"],
                    "tool_mode": "live-tool",
                },
            ).json()["id"],
        )
        self.assertEqual(live["status"], "completed", live.get("error"))
        case = self.client.post(
            "/v1/lab/cases/capture",
            json={"workspace_id": workspace["id"], "run_id": live["id"]},
        ).json()
        restore = self.client.post(f"/v1/lab/cases/{case['id']}/restore").json()
        self.assertEqual(restore.get("input_origin"), "starting_snapshot")
        self.assertFalse(
            (Path(restore["workspace"]["path"]) / "case.md").exists(),
            "starting snapshot must not already contain the live write; reconstruction is the replay step",
        )
        parent_before = (Path(workspace["path"]) / "notes.md").read_text(encoding="utf-8")
        constructions: list[object] = []
        real = harness_backend_mod.FilesystemBackend

        def wrapper(*args: Any, **kwargs: Any) -> Any:
            constructions.append((args, kwargs))
            return real(*args, **kwargs)

        with patch.object(harness_backend_mod, "FilesystemBackend", side_effect=wrapper):
            recorded = wait_for_lab_result(
                self.client,
                self.client.post(
                    f"/v1/lab/cases/{case['id']}/rerun",
                    json={"tool_mode": "recorded-tool", "workspace_id": restore["workspace"]["id"]},
                ).json()["id"],
            )
        self.assertEqual(recorded["tool_mode"], "recorded-tool")
        self.assertTrue(recorded["recorded_is_not_live_proof"])
        self.assertIn("not proof of a current live integration", " ".join(recorded["deviations"]).lower())
        self.assertEqual(constructions, [])
        self.assertEqual((Path(workspace["path"]) / "notes.md").read_text(encoding="utf-8"), parent_before)
        child_written = Path(restore["workspace"]["path"]) / "case.md"
        self.assertTrue(child_written.is_file(), f"missing reconstructed file in {restore['workspace']['path']}")
        self.assertEqual(child_written.read_text(encoding="utf-8"), "case-bytes")
        child_run = self.client.get(f"/v1/agent-runs/{recorded['agent_run_id']}").json()
        self.assertEqual(child_run["status"], "completed", child_run.get("error"))
        self.assertNotEqual(recorded["tool_mode"], live["tool_mode"])

    def test_lab_recorded_mismatch_is_explicit_deviation(self) -> None:
        workspace = self.client.post(
            "/v1/lab/workspaces",
            json={"display_name": "mismatch-project", "files": {"notes.md": "original"}},
        ).json()
        live = wait_for_run(
            self.client,
            self.client.post(
                "/v1/agent-runs",
                json={
                    "deployment_id": self.deployment_id,
                    "task": "Write case.md",
                    "workspace_id": workspace["id"],
                    "project_path": workspace["path"],
                    "presented_tools": ["write_file"],
                    "tool_mode": "live-tool",
                },
            ).json()["id"],
        )
        case = self.client.post(
            "/v1/lab/cases/capture",
            json={"workspace_id": workspace["id"], "run_id": live["id"]},
        ).json()
        restore = self.client.post(f"/v1/lab/cases/{case['id']}/restore").json()
        self._install_script(write_then_reply("/case.md", "different-bytes"))
        recorded = wait_for_lab_result(
            self.client,
            self.client.post(
                f"/v1/lab/cases/{case['id']}/rerun",
                json={"tool_mode": "recorded-tool", "workspace_id": restore["workspace"]["id"]},
            ).json()["id"],
        )
        child_run = self.client.get(f"/v1/agent-runs/{recorded['agent_run_id']}").json()
        self.assertEqual(child_run["status"], "failed")
        self.assertIn("structured replay failure", " ".join(recorded["deviations"]).lower())
        self.assertTrue(recorded["recorded_is_not_live_proof"])


if __name__ == "__main__":
    unittest.main()
