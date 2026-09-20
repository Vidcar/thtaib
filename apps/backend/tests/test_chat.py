"""Chat → embedded harness wiring, STATE-002, and project filesystem tools."""

from __future__ import annotations

import tempfile
import threading
import time
import unittest
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage

from workbench_backend.agents.harness import HarnessService
from workbench_backend.agents.schemas import AgentRun
from workbench_backend.app import create_app
from workbench_backend.chat.schemas import ChatMessage
from workbench_backend.inference.ids import utc_now
from workbench_backend.paths import WorkbenchPaths

from tests.scripted_model import ScriptedChatModel, set_generate_hold, wait_for_generate_hold
from tests.support import close_workbench_sqlite, offline_workbench_client, wait_for_run, wait_for_status


def wait_for_chat(client: TestClient, conversation_id: str, *, timeout: float = 30.0) -> dict[str, Any]:
    deadline = time.time() + timeout
    body: dict[str, Any] = {}
    while time.time() < deadline:
        response = client.get(f"/v1/chat/conversations/{conversation_id}")
        body = response.json()
        run = body.get("current_run") or {}
        if run.get("status") in {"completed", "cancelled", "failed"}:
            return body
        time.sleep(0.05)
    raise TimeoutError(f"chat {conversation_id} did not finish: {body}")


def write_then_reply(path: str = "/edited.md", content: str = "chat-file-edit") -> list[AIMessage]:
    return [
        AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "write_file",
                    "args": {"file_path": path, "content": content},
                    "id": "call_write",
                }
            ],
        ),
        AIMessage(content="Wrote edited.md in the project workspace."),
    ]


class ChatHarnessTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.project = self.root / "project-workspace"
        self.project.mkdir()
        (self.project / "keep.md").write_text("retain-me", encoding="utf-8")
        self.app = create_app(data_root=self.root)
        self.manager = self.app.state.manager
        self.scripted = ScriptedChatModel(write_then_reply())

        def factory(_run: AgentRun, _sink: list[dict[str, Any]]) -> ScriptedChatModel:
            return self.scripted

        self.app.state.harness = HarnessService(
            lambda: self.manager,
            model_factory=factory,
            knowledge_provider=lambda: self.app.state.knowledge,
            app_store=self.app.state.app_store,
        )
        self.client = offline_workbench_client(self.app)
        self.deployment_id = self.client.post(
            "/v1/deployments/connected",
            json={"endpoint": "http://127.0.0.1:9/v1", "display_name": "chat-fixture"},
        ).json()["id"]
        self.profile_id = self.client.post(
            "/v1/profiles",
            json={
                "display_name": "chat-profile",
                "startup": {},
                "per_request": {},
                "agent": {},
            },
        ).json()["id"]

    def tearDown(self) -> None:
        close_workbench_sqlite(self.app, getattr(self, "client", None))
        self.tmp.cleanup()

    def _create(self, **extra: Any) -> dict[str, Any]:
        payload = {
            "deployment_id": self.deployment_id,
            "profile_id": self.profile_id,
            "project_path": str(self.project),
            **extra,
        }
        response = self.client.post("/v1/chat/conversations", json=payload)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def _start(self, conversation_id: str, task: str = "Edit edited.md in the project.") -> dict[str, Any]:
        response = self.client.post(
            f"/v1/chat/conversations/{conversation_id}/start",
            json={"task": task},
        )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def test_chat_calls_the_same_embedded_harness(self) -> None:
        conversation = self._create()
        self.assertEqual(conversation["harness"], "deepagents")
        self.assertFalse(conversation["second_agent_loop"])
        self.assertTrue(conversation["filesystem_tools_available"])
        self.assertTrue(conversation["shell_tools_available"])
        self.assertEqual(conversation["profile_id"], self.profile_id)
        started = self._start(conversation["id"])
        self.assertEqual(started["harness"], "deepagents")
        self.assertFalse(started["second_agent_loop"])
        run = started["current_run"]
        self.assertIsNotNone(run)
        self.assertEqual(run["harness"], "deepagents")
        self.assertEqual(run["source_surface"], "chat")
        self.assertEqual(started["thread_id"], conversation["thread_id"])
        self.assertEqual(run["thread_id"], conversation["thread_id"])
        self.assertNotEqual(run["id"], conversation["thread_id"])
        self.assertEqual(run["project_path"], str(self.project.resolve()))
        self.assertEqual(run["profile_id"], self.profile_id)
        listed = self.client.get("/v1/agent-runs").json()
        self.assertTrue(any(item["id"] == run["id"] for item in listed))
        body = wait_for_chat(self.client, conversation["id"])
        self.assertEqual(body["current_run"]["status"], "completed")
        kinds = [event["kind"] for event in body["events"]]
        self.assertIn("started", kinds)
        self.assertIn("tool_call", kinds)
        self.assertIn("tool_result", kinds)
        self.assertIn("completed", kinds)
        self.assertEqual(body["current_run"]["harness"], "deepagents")

    def test_filesystem_tools_write_project_storage(self) -> None:
        conversation = self._create()
        started = self._start(conversation["id"])
        body = wait_for_chat(self.client, conversation["id"])
        self.assertEqual(body["current_run"]["status"], "completed", body["current_run"].get("error"))
        names = [item["name"] for item in body["current_run"]["tool_invocations"]]
        self.assertIn("write_file", names)
        written = self.project / "edited.md"
        self.assertTrue(written.is_file())
        self.assertEqual(written.read_text(encoding="utf-8"), "chat-file-edit")
        self.assertEqual((self.project / "keep.md").read_text(encoding="utf-8"), "retain-me")
        paths = WorkbenchPaths(self.root)
        edited_hits = [path for path in self.root.rglob("edited.md") if path.is_file()]
        self.assertEqual(edited_hits, [written])
        self.assertTrue(paths.application_db.is_file())
        self.assertTrue(paths.checkpoints_db.is_file())
        self.assertNotEqual(paths.application_db, paths.checkpoints_db)
        self.assertFalse((paths.state / "chat" / "edited.md").exists())
        self.assertFalse((self.project / "large_tool_results").exists())
        self.assertFalse((self.project / "conversation_history").exists())

    def test_transcript_is_not_the_working_project(self) -> None:
        conversation = self._create()
        self._start(conversation["id"])
        wait_for_chat(self.client, conversation["id"])
        self.assertEqual((self.project / "edited.md").read_text(encoding="utf-8"), "chat-file-edit")
        fingerprints_before = {
            path.relative_to(self.project).as_posix(): path.read_text(encoding="utf-8")
            for path in self.project.rglob("*")
            if path.is_file()
        }
        replaced = self.client.put(
            f"/v1/chat/conversations/{conversation['id']}/transcript",
            json={"messages": [{"role": "user", "content": "rewritten history only", "at": "2026-01-01T00:00:00+00:00"}]},
        )
        self.assertEqual(replaced.status_code, 200, replaced.text)
        self.assertTrue(replaced.json()["history_replaced"])
        self.assertEqual(len(replaced.json()["transcript"]), 1)
        fetched = self.client.get(f"/v1/chat/conversations/{conversation['id']}").json()
        self.assertEqual(fetched["transcript"][0]["content"], "rewritten history only")
        fingerprints_after = {
            path.relative_to(self.project).as_posix(): path.read_text(encoding="utf-8")
            for path in self.project.rglob("*")
            if path.is_file()
        }
        self.assertEqual(fingerprints_after, fingerprints_before)
        self.assertEqual((self.project / "keep.md").read_text(encoding="utf-8"), "retain-me")
        self.assertEqual((self.project / "edited.md").read_text(encoding="utf-8"), "chat-file-edit")

        fresh = self._create()
        self.assertNotEqual(fresh["id"], conversation["id"])
        self.assertEqual(fresh["transcript"], [])
        self.assertEqual((self.project / "keep.md").read_text(encoding="utf-8"), "retain-me")
        self.assertEqual((self.project / "edited.md").read_text(encoding="utf-8"), "chat-file-edit")

        cleared = self.client.put(
            f"/v1/chat/conversations/{conversation['id']}/transcript",
            json={"messages": []},
        )
        self.assertEqual(cleared.status_code, 200, cleared.text)
        self.assertEqual(cleared.json()["transcript"], [])
        self.assertEqual((self.project / "keep.md").read_text(encoding="utf-8"), "retain-me")
        self.assertEqual((self.project / "edited.md").read_text(encoding="utf-8"), "chat-file-edit")

    def test_workspace_id_resolves_project_path(self) -> None:
        workspace = self.client.post(
            "/v1/lab/workspaces",
            json={"display_name": "chat-ws", "files": {"from-lab.md": "lab-seed"}},
        ).json()
        conversation = self._create(workspace_id=workspace["id"], project_path=workspace["path"])
        self.assertEqual(Path(conversation["project_path"]), Path(workspace["path"]).resolve())
        started = self._start(conversation["id"])
        wait_for_chat(self.client, conversation["id"])
        self.assertTrue((Path(workspace["path"]) / "edited.md").is_file())
        self.assertEqual((Path(workspace["path"]) / "from-lab.md").read_text(encoding="utf-8"), "lab-seed")
        self.assertEqual(started["current_run"]["workspace_id"], workspace["id"])

    def test_chat_without_project_uses_visibility_tools(self) -> None:
        self.scripted = ScriptedChatModel(
            [
                AIMessage(
                    content="",
                    tool_calls=[{"name": "echo", "args": {"text": "no-project"}, "id": "call_echo"}],
                ),
                AIMessage(content="echoed without a project folder."),
            ]
        )

        def factory(_run: AgentRun, _sink: list[dict[str, Any]]) -> ScriptedChatModel:
            return self.scripted

        self.app.state.harness = HarnessService(
            lambda: self.manager,
            model_factory=factory,
            knowledge_provider=lambda: self.app.state.knowledge,
            app_store=self.app.state.app_store,
        )
        created = self.client.post(
            "/v1/chat/conversations",
            json={"deployment_id": self.deployment_id, "profile_id": self.profile_id},
        )
        self.assertEqual(created.status_code, 200, created.text)
        conversation = created.json()
        self.assertIsNone(conversation["project_path"])
        self.assertFalse(conversation["filesystem_tools_available"])
        self.assertFalse(conversation["shell_tools_available"])
        self.assertEqual(conversation["enabled_tools"], ["echo", "time_now", "write_todos"])
        started = self._start(conversation["id"], task="Echo no-project.")
        self.assertFalse(started["filesystem_tools_available"])
        self.assertFalse(started["shell_tools_available"])
        self.assertEqual(started["enabled_tools"], ["echo", "time_now", "write_todos"])
        run = started["current_run"]
        self.assertEqual(run["enabled_tools"], ["echo", "time_now", "write_todos"])
        self.assertEqual(run["presented_tools"], ["echo", "time_now", "write_todos"])
        self.assertIsNone(run["project_path"])
        body = wait_for_chat(self.client, conversation["id"])
        self.assertEqual(body["current_run"]["status"], "completed", body["current_run"].get("error"))
        names = [item["name"] for item in body["current_run"]["tool_invocations"]]
        self.assertIn("echo", names)
        self.assertFalse(any(self.project.rglob("large_tool_results")))
        surprise = [path for path in self.root.rglob("*") if path.is_file() and "harness" not in path.parts]
        written_outside_data = [
            path
            for path in surprise
            if path.is_relative_to(self.project)
        ]
        self.assertEqual(written_outside_data, [self.project / "keep.md"])

    def test_filesystem_tools_without_project_are_rejected(self) -> None:
        created = self.client.post(
            "/v1/chat/conversations",
            json={"deployment_id": self.deployment_id},
        )
        self.assertEqual(created.status_code, 200, created.text)
        response = self.client.post(
            f"/v1/chat/conversations/{created.json()['id']}/start",
            json={"task": "Write a file.", "presented_tools": ["write_file"]},
        )
        self.assertEqual(response.status_code, 400, response.text)
        self.assertEqual(response.json()["code"], "filesystem_requires_project")
        self.assertIn("write_file", response.json()["tools"])
        fetched = self.client.get(f"/v1/chat/conversations/{created.json()['id']}")
        self.assertEqual(fetched.status_code, 200, fetched.text)
        self.assertEqual(fetched.json()["transcript"], [])
        self.assertEqual(fetched.json()["run_ids"], [])

    def test_start_accepts_explicit_null_clears_without_mutating_historical_run(self) -> None:
        self.scripted = ScriptedChatModel(
            [
                AIMessage(
                    content="",
                    tool_calls=[{"name": "echo", "args": {"text": "cleared"}, "id": "call_echo"}],
                ),
                AIMessage(content="Cleared optional bindings."),
            ]
        )
        workspace = self.client.post(
            "/v1/lab/workspaces",
            json={"display_name": "clear-ws", "files": {"seed.md": "seed"}},
        ).json()
        conversation = self._create(
            workspace_id=workspace["id"],
            project_path=workspace["path"],
            retrieval_project_paths=[workspace["path"]],
        )
        first = self._start(conversation["id"], "First turn with the project.")
        first_run_id = first["current_run"]["id"]
        wait_for_chat(self.client, conversation["id"])

        started = self.client.post(
            f"/v1/chat/conversations/{conversation['id']}/start",
            json={
                "task": "Continue with optional bindings cleared.",
                "profile_id": None,
                "project_path": None,
                "workspace_id": None,
                "embedding_deployment_id": None,
                "retrieval_project_paths": [],
                "presented_tools": ["echo"],
            },
        )
        self.assertEqual(started.status_code, 200, started.text)
        body = started.json()
        self.assertIsNone(body["profile_id"])
        self.assertIsNone(body["project_path"])
        self.assertIsNone(body["workspace_id"])
        self.assertIsNone(body["embedding_deployment_id"])
        self.assertEqual(body["retrieval_project_paths"], [])
        self.assertFalse(body["filesystem_tools_available"])
        self.assertFalse(body["shell_tools_available"])
        second = wait_for_chat(self.client, conversation["id"])
        self.assertEqual(second["current_run"]["status"], "completed", second["current_run"].get("error"))
        first_run = self.client.get(f"/v1/agent-runs/{first_run_id}").json()
        self.assertEqual(first_run["project_path"], str(Path(workspace["path"]).resolve()))
        self.assertEqual(first_run["workspace_id"], workspace["id"])
        self.assertEqual(first_run["profile_id"], self.profile_id)

    def test_omitted_bindings_preserve_and_independent_clears_are_scoped(self) -> None:
        workspace = self.client.post(
            "/v1/lab/workspaces",
            json={"display_name": "omit-ws", "files": {"seed.md": "seed"}},
        ).json()
        conversation = self._create(
            workspace_id=workspace["id"],
            project_path=workspace["path"],
            retrieval_project_paths=[workspace["path"]],
        )
        preserved = self.client.post(
            f"/v1/chat/conversations/{conversation['id']}/start",
            json={"task": "Omit existing bindings."},
        )
        self.assertEqual(preserved.status_code, 200, preserved.text)
        preserved_body = preserved.json()
        self.assertEqual(preserved_body["profile_id"], self.profile_id)
        self.assertEqual(preserved_body["workspace_id"], workspace["id"])
        self.assertEqual(preserved_body["project_path"], str(Path(workspace["path"]).resolve()))
        self.assertEqual(preserved_body["retrieval_project_paths"], [workspace["path"]])
        wait_for_chat(self.client, conversation["id"])

        profile_cleared = self.client.post(
            f"/v1/chat/conversations/{conversation['id']}/start",
            json={"task": "Clear profile only.", "profile_id": None},
        )
        self.assertEqual(profile_cleared.status_code, 200, profile_cleared.text)
        profile_body = profile_cleared.json()
        self.assertIsNone(profile_body["profile_id"])
        self.assertEqual(profile_body["workspace_id"], workspace["id"])
        self.assertEqual(profile_body["project_path"], str(Path(workspace["path"]).resolve()))
        self.assertEqual(profile_body["retrieval_project_paths"], [workspace["path"]])
        wait_for_chat(self.client, conversation["id"])

        project_cleared = self.client.post(
            f"/v1/chat/conversations/{conversation['id']}/start",
            json={
                "task": "Clear project access.",
                "project_path": None,
                "workspace_id": None,
                "presented_tools": ["echo"],
            },
        )
        self.assertEqual(project_cleared.status_code, 200, project_cleared.text)
        project_body = project_cleared.json()
        self.assertIsNone(project_body["workspace_id"])
        self.assertIsNone(project_body["project_path"])
        self.assertEqual(project_body["retrieval_project_paths"], [])
        self.assertFalse(project_body["filesystem_tools_available"])
        self.assertFalse(project_body["shell_tools_available"])
        self.assertIsNone(project_body["current_run"]["project_path"])
        self.assertEqual(project_body["current_run"]["retrieval_project_paths"], [])

    def test_completed_turn_reconciles_before_next_start_without_get(self) -> None:
        self.scripted = ScriptedChatModel(
            [
                AIMessage(content="first assistant"),
                AIMessage(content="second assistant"),
            ]
        )
        conversation = self._create()
        first = self._start(conversation["id"], "First turn.")
        first_run_id = first["current_run"]["id"]
        wait_for_run(self.client, first_run_id)

        second = self._start(conversation["id"], "Second turn.")
        transcript = second["transcript"]
        self.assertEqual([item["role"] for item in transcript], ["user", "assistant", "user"])
        self.assertEqual(transcript[0]["content"], "First turn.")
        self.assertEqual(transcript[1]["content"], "first assistant")
        self.assertEqual(transcript[1]["run_id"], first_run_id)
        self.assertEqual(transcript[2]["content"], "Second turn.")
        self.assertEqual(second["run_ids"], [first_run_id, second["current_run"]["id"]])
        wait_for_chat(self.client, conversation["id"])

    def test_same_conversation_start_race_admits_one_turn(self) -> None:
        hold = threading.Event()
        set_generate_hold(hold)
        self.addCleanup(set_generate_hold, None)
        self.addCleanup(hold.set)

        def factory(_run: AgentRun, _sink: list[dict[str, Any]]) -> ScriptedChatModel:
            return ScriptedChatModel([AIMessage(content="held")], hold=hold)

        self.app.state.harness = HarnessService(
            lambda: self.manager,
            model_factory=factory,
            knowledge_provider=lambda: self.app.state.knowledge,
            app_store=self.app.state.app_store,
        )
        conversation = self._create()
        barrier = threading.Barrier(3)
        results: list[tuple[int, dict[str, Any]]] = []
        lock = threading.Lock()

        def start_turn(task: str) -> None:
            barrier.wait(timeout=5)
            response = self.client.post(
                f"/v1/chat/conversations/{conversation['id']}/start",
                json={"task": task},
            )
            with lock:
                results.append((response.status_code, response.json()))

        threads = [
            threading.Thread(target=start_turn, args=("Race A",)),
            threading.Thread(target=start_turn, args=("Race B",)),
        ]
        for item in threads:
            item.start()
        barrier.wait(timeout=5)
        for item in threads:
            item.join(timeout=10)
        hold.set()

        self.assertEqual(sorted(status for status, _body in results), [200, 409], results)
        accepted = [body for status, body in results if status == 200][0]
        rejected = [body for status, body in results if status == 409][0]
        self.assertEqual(rejected["code"], "chat_turn_active")
        fetched = self.client.get(f"/v1/chat/conversations/{conversation['id']}").json()
        self.assertEqual(len(fetched["run_ids"]), 1)
        self.assertEqual(len([item for item in fetched["transcript"] if item["role"] == "user"]), 1)
        self.assertEqual(fetched["current_run_id"], accepted["current_run"]["id"])
        wait_for_chat(self.client, conversation["id"])

    def test_separate_conversations_start_independently(self) -> None:
        def factory(_run: AgentRun, _sink: list[dict[str, Any]]) -> ScriptedChatModel:
            return ScriptedChatModel([AIMessage(content="independent")])

        self.app.state.harness = HarnessService(
            lambda: self.manager,
            model_factory=factory,
            knowledge_provider=lambda: self.app.state.knowledge,
            app_store=self.app.state.app_store,
        )
        first = self._create()
        second = self._create()
        barrier = threading.Barrier(3)
        results: list[tuple[str, int, dict[str, Any]]] = []
        lock = threading.Lock()

        def start_turn(conversation_id: str, task: str) -> None:
            barrier.wait(timeout=5)
            response = self.client.post(
                f"/v1/chat/conversations/{conversation_id}/start",
                json={"task": task},
            )
            with lock:
                results.append((conversation_id, response.status_code, response.json()))

        threads = [
            threading.Thread(target=start_turn, args=(first["id"], "First independent.")),
            threading.Thread(target=start_turn, args=(second["id"], "Second independent.")),
        ]
        for item in threads:
            item.start()
        barrier.wait(timeout=5)
        for item in threads:
            item.join(timeout=10)

        self.assertEqual([status for _cid, status, _body in results], [200, 200])
        self.assertEqual({body["id"] for _cid, _status, body in results}, {first["id"], second["id"]})
        self.assertNotEqual(results[0][2]["current_run"]["id"], results[1][2]["current_run"]["id"])
        wait_for_chat(self.client, first["id"])
        wait_for_chat(self.client, second["id"])

    def test_hydration_race_does_not_overwrite_next_start_or_duplicate_assistant(self) -> None:
        self.scripted = ScriptedChatModel(
            [
                AIMessage(content="first assistant"),
                AIMessage(content="second assistant"),
            ]
        )
        conversation = self._create()
        first = self._start(conversation["id"], "First turn.")
        first_run_id = first["current_run"]["id"]
        wait_for_run(self.client, first_run_id)

        barrier = threading.Barrier(3)
        results: list[tuple[str, int, dict[str, Any]]] = []
        lock = threading.Lock()

        def hydrate() -> None:
            barrier.wait(timeout=5)
            response = self.client.get(f"/v1/chat/conversations/{conversation['id']}")
            with lock:
                results.append(("get", response.status_code, response.json()))

        def start_next() -> None:
            barrier.wait(timeout=5)
            response = self.client.post(
                f"/v1/chat/conversations/{conversation['id']}/start",
                json={"task": "Second turn."},
            )
            with lock:
                results.append(("start", response.status_code, response.json()))

        threads = [threading.Thread(target=hydrate), threading.Thread(target=start_next)]
        for item in threads:
            item.start()
        barrier.wait(timeout=5)
        for item in threads:
            item.join(timeout=10)

        self.assertTrue(all(status == 200 for _kind, status, _body in results), results)
        fetched = self.client.get(f"/v1/chat/conversations/{conversation['id']}").json()
        self.assertEqual(fetched["run_ids"][0], first_run_id)
        self.assertEqual(len(fetched["run_ids"]), 2)
        assistant_replies = [
            item for item in fetched["transcript"] if item["role"] == "assistant" and item["run_id"] == first_run_id
        ]
        self.assertEqual(len(assistant_replies), 1)
        self.assertEqual(assistant_replies[0]["content"], "first assistant")
        self.assertEqual(fetched["transcript"][-1]["content"], "Second turn.")
        self.assertEqual(fetched["current_run_id"], fetched["run_ids"][-1])

    def test_fast_terminal_run_is_reconciled_before_start_returns(self) -> None:
        self.scripted = ScriptedChatModel([AIMessage(content="instant assistant")])
        conversation = self._create()
        started = self._start(conversation["id"], "Instant turn.")
        run_id = started["current_run"]["id"]
        body = wait_for_chat(self.client, conversation["id"])
        assistant_replies = [
            item for item in body["transcript"] if item["role"] == "assistant" and item["run_id"] == run_id
        ]
        self.assertEqual(len(assistant_replies), 1)
        self.assertEqual(assistant_replies[0]["content"], "instant assistant")

    def test_old_completed_run_repersist_after_history_replace_does_not_resurrect_reply(self) -> None:
        self.scripted = ScriptedChatModel(
            [
                AIMessage(content="old assistant"),
                AIMessage(content="new assistant"),
            ]
        )
        conversation = self._create()
        first = self._start(conversation["id"], "Old turn.")
        first_run_id = first["current_run"]["id"]
        first_finished = wait_for_chat(self.client, conversation["id"])
        self.assertTrue(
            any(
                item["role"] == "assistant"
                and item["run_id"] == first_run_id
                and item["content"] == "old assistant"
                for item in first_finished["transcript"]
            )
        )

        replaced = self.client.put(
            f"/v1/chat/conversations/{conversation['id']}/transcript",
            json={
                "messages": [
                    {
                        "role": "user",
                        "content": "edited old user only",
                        "at": "2026-01-01T00:00:00+00:00",
                        "run_id": first_run_id,
                    }
                ]
            },
        )
        self.assertEqual(replaced.status_code, 200, replaced.text)
        self.assertTrue(replaced.json()["history_replaced"])
        self.assertFalse(any(item["role"] == "assistant" for item in replaced.json()["transcript"]))

        second = self._start(conversation["id"], "New turn.")
        second_run_id = second["current_run"]["id"]
        second_finished = wait_for_chat(self.client, conversation["id"])
        self.assertFalse(
            any(
                item["role"] == "assistant"
                and item["run_id"] == first_run_id
                and item["content"] == "old assistant"
                for item in second_finished["transcript"]
            )
        )
        self.assertTrue(
            any(
                item["role"] == "assistant"
                and item["run_id"] == second_run_id
                and item["content"] == "new assistant"
                for item in second_finished["transcript"]
            )
        )

        old_run = self.app.state.app_store.get_run(first_run_id)
        self.assertIsNotNone(old_run)
        assert old_run is not None
        self.app.state.app_store.put_run(old_run)
        fetched = self.client.get(f"/v1/chat/conversations/{conversation['id']}").json()
        self.assertFalse(
            any(
                item["role"] == "assistant"
                and item["run_id"] == first_run_id
                and item["content"] == "old assistant"
                for item in fetched["transcript"]
            )
        )
        new_replies = [
            item
            for item in fetched["transcript"]
            if item["role"] == "assistant" and item["run_id"] == second_run_id
        ]
        self.assertEqual(len(new_replies), 1)
        self.assertEqual(new_replies[0]["content"], "new assistant")

    def test_cancel_does_not_overwrite_concurrent_conversation_update(self) -> None:
        hold = threading.Event()
        set_generate_hold(hold)
        self.addCleanup(set_generate_hold, None)
        self.addCleanup(hold.set)

        def factory(_run: AgentRun, _sink: list[dict[str, Any]]) -> ScriptedChatModel:
            return ScriptedChatModel([AIMessage(content="held")], hold=hold)

        self.app.state.harness = HarnessService(
            lambda: self.manager,
            model_factory=factory,
            knowledge_provider=lambda: self.app.state.knowledge,
            app_store=self.app.state.app_store,
        )
        conversation = self._create()
        started = self._start(conversation["id"], "Held turn.")
        wait_for_status(self.client, started["current_run"]["id"], "running")
        stored = self.app.state.app_store.get_conversation(conversation["id"])
        self.assertIsNotNone(stored)
        assert stored is not None
        stored.transcript.append(
            ChatMessage(
                role="system",
                content="concurrent marker",
                at="2026-01-01T00:00:00+00:00",
            )
        )
        stored.updated_at = utc_now()
        self.app.state.app_store.put_conversation(stored)
        cancelled = self.client.post(f"/v1/chat/conversations/{conversation['id']}/cancel")
        self.assertEqual(cancelled.status_code, 200, cancelled.text)
        contents = [item["content"] for item in cancelled.json()["transcript"]]
        self.assertIn("concurrent marker", contents)
        hold.set()
        wait_for_chat(self.client, conversation["id"])

    def test_detached_deployment_conversation_is_readable_until_deliberate_rebind(self) -> None:
        other = self.client.post(
            "/v1/deployments/connected",
            json={"endpoint": "http://127.0.0.1:10/v1", "display_name": "replacement"},
        ).json()
        conversation = self._create()
        detached = self.client.post(f"/v1/deployments/{self.deployment_id}/detach")
        self.assertEqual(detached.status_code, 200, detached.text)
        fetched = self.client.get(f"/v1/chat/conversations/{conversation['id']}")
        self.assertEqual(fetched.status_code, 200, fetched.text)
        self.assertEqual(fetched.json()["deploy_health"]["code"], "deploy_missing")
        stale_start = self.client.post(
            f"/v1/chat/conversations/{conversation['id']}/start",
            json={"task": "Try stale deployment."},
        )
        self.assertEqual(stale_start.status_code, 409, stale_start.text)
        self.assertEqual(stale_start.json()["code"], "deploy_missing")
        self.assertEqual(
            self.client.get(f"/v1/chat/conversations/{conversation['id']}").json()["transcript"],
            [],
        )
        rebound = self.client.post(
            f"/v1/chat/conversations/{conversation['id']}/start",
            json={"task": "Rebind deliberately.", "deployment_id": other["id"], "presented_tools": ["echo"]},
        )
        self.assertEqual(rebound.status_code, 200, rebound.text)
        self.assertEqual(rebound.json()["deployment_id"], other["id"])

    def test_projectless_filesystem_tool_call_fails_clearly(self) -> None:
        created = self.client.post(
            "/v1/chat/conversations",
            json={"deployment_id": self.deployment_id},
        )
        self.assertEqual(created.status_code, 200, created.text)
        self._start(created.json()["id"], task="Write edited.md even though there is no project.")
        body = wait_for_chat(self.client, created.json()["id"])
        self.assertEqual(body["current_run"]["status"], "completed", body["current_run"].get("error"))
        self.assertFalse((self.project / "edited.md").exists())
        results = [event["detail"].get("content", "") for event in body["events"] if event["kind"] == "tool_result"]
        self.assertTrue(any("require a bound project" in str(item).lower() for item in results), results)

    def test_harness_scratch_stays_out_of_the_project(self) -> None:
        self.scripted = ScriptedChatModel(
            [
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "write_file",
                            "args": {
                                "file_path": "/large_tool_results/hello.txt",
                                "content": "offload",
                            },
                            "id": "call_offload",
                        }
                    ],
                ),
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "write_file",
                            "args": {"file_path": "/hello.txt", "content": "project-hello"},
                            "id": "call_project",
                        }
                    ],
                ),
                AIMessage(content="Wrote both paths."),
            ]
        )

        def factory(_run: AgentRun, _sink: list[dict[str, Any]]) -> ScriptedChatModel:
            return self.scripted

        self.app.state.harness = HarnessService(
            lambda: self.manager,
            model_factory=factory,
            knowledge_provider=lambda: self.app.state.knowledge,
            app_store=self.app.state.app_store,
        )
        conversation = self._create()
        self._start(conversation["id"], task="Write hello.txt and an offload file.")
        body = wait_for_chat(self.client, conversation["id"])
        self.assertEqual(body["current_run"]["status"], "completed", body["current_run"].get("error"))
        self.assertEqual((self.project / "hello.txt").read_text(encoding="utf-8"), "project-hello")
        self.assertFalse((self.project / "large_tool_results").exists())
        self.assertFalse((self.project / "conversation_history").exists())
        written = [item for item in body["current_run"]["related_files"] if item["kind"] == "written_file"]
        self.assertTrue(any(Path(item["path"]).name == "hello.txt" for item in written))
        self.assertFalse(any("large_tool_results" in item["path"] for item in written))
        scratch_hits = list((self.root / "state" / "harness").rglob("hello.txt"))
        self.assertTrue(scratch_hits)
        self.assertEqual(scratch_hits[0].read_text(encoding="utf-8"), "offload")

    def test_unknown_profile_is_rejected(self) -> None:
        response = self.client.post(
            "/v1/chat/conversations",
            json={
                "deployment_id": self.deployment_id,
                "profile_id": "profile_missing",
                "project_path": str(self.project),
            },
        )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["code"], "profile_missing")

    def test_cancel_uses_the_harness_cancel_path(self) -> None:
        slow = ScriptedChatModel(write_then_reply(), delay_s=0.4)

        def factory(_run: AgentRun, _sink: list[dict[str, Any]]) -> ScriptedChatModel:
            return slow

        self.app.state.harness = HarnessService(
            lambda: self.manager,
            model_factory=factory,
            knowledge_provider=lambda: self.app.state.knowledge,
            app_store=self.app.state.app_store,
        )
        conversation = self._create()
        started = self._start(conversation["id"])
        cancelled = self.client.post(f"/v1/chat/conversations/{conversation['id']}/cancel")
        self.assertEqual(cancelled.status_code, 200, cancelled.text)
        body = wait_for_chat(self.client, conversation["id"])
        self.assertEqual(body["current_run"]["status"], "cancelled")
        self.assertEqual(body["current_run"]["id"], started["current_run"]["id"])

    def test_start_rejected_while_cancel_requested(self) -> None:
        hold = threading.Event()
        previous = self.app.state.harness
        set_generate_hold(hold)
        self.addCleanup(set_generate_hold, None)
        self.addCleanup(hold.set)
        self.addCleanup(previous.close)

        def factory(_run: AgentRun, _sink: list[dict[str, Any]]) -> ScriptedChatModel:
            return ScriptedChatModel(write_then_reply(), hold=hold)

        self.app.state.harness = HarnessService(
            lambda: self.manager,
            model_factory=factory,
            knowledge_provider=lambda: self.app.state.knowledge,
            app_store=self.app.state.app_store,
        )
        conversation = self._create()
        started = self._start(conversation["id"])
        first_run_id = started["current_run"]["id"]
        self.assertEqual(started["current_run_id"], first_run_id)
        try:
            wait_for_status(self.client, first_run_id, "running")
            wait_for_generate_hold()
            cancelled = self.client.post(f"/v1/chat/conversations/{conversation['id']}/cancel")
            self.assertEqual(cancelled.status_code, 200, cancelled.text)
            self.assertEqual(cancelled.json()["current_run"]["status"], "cancel_requested")
            self.assertEqual(cancelled.json()["current_run_id"], first_run_id)
            overlap = self.client.post(
                f"/v1/chat/conversations/{conversation['id']}/start",
                json={"task": "Second turn while cancelling."},
            )
            self.assertEqual(overlap.status_code, 409, overlap.text)
            self.assertEqual(overlap.json()["code"], "chat_turn_active")
            observed = self.client.get(f"/v1/chat/conversations/{conversation['id']}")
            self.assertEqual(observed.status_code, 200, observed.text)
            self.assertEqual(observed.json()["current_run_id"], first_run_id)
            self.assertEqual(observed.json()["current_run"]["id"], first_run_id)
            self.assertEqual(observed.json()["current_run"]["status"], "cancel_requested")
            listed = self.client.get("/v1/agent-runs").json()
            self.assertEqual([item["id"] for item in listed], [first_run_id])
        finally:
            hold.set()
        body = wait_for_chat(self.client, conversation["id"])
        self.assertEqual(body["current_run"]["status"], "cancelled")
        self.assertEqual(body["current_run"]["id"], first_run_id)
        self.assertEqual(body["current_run_id"], first_run_id)
        follow = self._start(conversation["id"], task="Follow-up after confirmed cancel.")
        self.assertNotEqual(follow["current_run"]["id"], first_run_id)
        self.assertEqual(follow["current_run_id"], follow["current_run"]["id"])
        listed_after = self.client.get("/v1/agent-runs").json()
        ids = [item["id"] for item in listed_after]
        self.assertEqual(set(ids), {first_run_id, follow["current_run"]["id"]})


class HarnessProjectFilesystemTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.project = self.root / "direct-project"
        self.project.mkdir()
        self.app = create_app(data_root=self.root)
        self.manager = self.app.state.manager
        self.scripted = ScriptedChatModel(write_then_reply("/direct.md", "via-harness"))

        def factory(_run: AgentRun, _sink: list[dict[str, Any]]) -> ScriptedChatModel:
            return self.scripted

        self.app.state.harness = HarnessService(
            lambda: self.manager,
            model_factory=factory,
            app_store=self.app.state.app_store,
        )
        self.client = offline_workbench_client(self.app)
        self.deployment_id = self.client.post(
            "/v1/deployments/connected",
            json={"endpoint": "http://127.0.0.1:9/v1", "display_name": "fs-fixture"},
        ).json()["id"]

    def tearDown(self) -> None:
        close_workbench_sqlite(self.app, getattr(self, "client", None))
        self.tmp.cleanup()

    def test_agent_run_write_file_targets_project_path(self) -> None:
        started = self.client.post(
            "/v1/agent-runs",
            json={
                "deployment_id": self.deployment_id,
                "task": "Write direct.md",
                "project_path": str(self.project),
                "presented_tools": ["write_file"],
            },
        )
        self.assertEqual(started.status_code, 200, started.text)
        body = wait_for_run(self.client, started.json()["id"])
        self.assertEqual(body["status"], "completed", body.get("error"))
        self.assertEqual((self.project / "direct.md").read_text(encoding="utf-8"), "via-harness")


if __name__ == "__main__":
    unittest.main()
