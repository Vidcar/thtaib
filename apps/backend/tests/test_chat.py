"""Chat → embedded harness wiring, STATE-002, and project filesystem tools."""

from __future__ import annotations

import tempfile
import threading
import time
import unittest
import base64
import os
import shutil
from pathlib import Path
from typing import Any
from unittest.mock import patch

from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage, ToolMessage

from workbench_backend.agents.harness import HarnessService
from workbench_backend.agents.schemas import AgentRun, AgentRunStatus, AgentStartRequest, UserAnswerRequest
from workbench_backend.assets.schemas import RetainedUploadRequest
from workbench_backend.assets.service import RetainedAssetService
from workbench_backend.app import create_app
from workbench_backend.chat.schemas import ChatConversation, ChatConversationView, ChatMessage, ChatStartRequest
from workbench_backend.errors import HarnessError
from workbench_backend.inference.service import ManagerError
from workbench_backend.inference.ids import utc_now
from workbench_backend.paths import WorkbenchPaths
from workbench_backend.state.checkpointer import conversation_state

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


def wait_for_chat_interrupt(client: TestClient, conversation_id: str, *, timeout: float = 20.0) -> dict[str, Any]:
    deadline = time.time() + timeout
    body: dict[str, Any] = {}
    while time.time() < deadline:
        response = client.get(f"/v1/chat/conversations/{conversation_id}")
        body = response.json()
        run = body.get("current_run") or {}
        if run.get("pending_interrupt"):
            return body
        if run.get("status") in {"completed", "cancelled", "failed"}:
            raise TimeoutError(f"chat finished without interrupt: {body}")
        time.sleep(0.05)
    raise TimeoutError(f"chat {conversation_id} did not interrupt: {body}")


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


def host_shell_marker_command(filename: str) -> str:
    if os.name != "nt":
        return f"touch {filename}"
    return f"cmd /c type nul > {filename}"


def chat_interrupt_decision(paused_view: dict[str, Any], decision: str) -> dict[str, Any]:
    pending = paused_view["current_run"]["pending_interrupt"]
    return {
        "interrupt_id": pending["interrupt_id"],
        "namespace": pending.get("namespace", []),
        "decisions": [{"type": decision}],
    }


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
        edited_hits = [
            path
            for path in self.root.rglob("edited.md")
            if path.is_file() and "snapshots" not in path.parts
        ]
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

    def test_rename_archive_search_and_reopen_survive_store_reopen(self) -> None:
        general = self._create(project_path=None, title="General planning notes")
        project = self._create(title="Project launch notes")
        original_project_identity = {
            "id": project["id"],
            "thread_id": project["thread_id"],
            "area_kind": project["area_kind"],
            "area_id": project["area_id"],
            "area_label": project["area_label"],
            "area_project_path": project["area_project_path"],
            "project_path": project["project_path"],
            "workspace_id": project["workspace_id"],
        }
        self.assertEqual(general["area_kind"], "general")
        self.assertEqual(project["area_kind"], "project")

        general_transcript = self.client.put(
            f"/v1/chat/conversations/{general['id']}/transcript",
            json={"messages": [{"role": "user", "content": "Readable banana message", "at": "2026-01-01T00:00:00+00:00"}]},
        )
        self.assertEqual(general_transcript.status_code, 200, general_transcript.text)
        project_transcript = self.client.put(
            f"/v1/chat/conversations/{project['id']}/transcript",
            json={"messages": [{"role": "assistant", "content": "Readable cherry answer", "at": "2026-01-01T00:00:00+00:00"}]},
        )
        self.assertEqual(project_transcript.status_code, 200, project_transcript.text)

        title_hits = self.client.get("/v1/chat/conversations/search", params={"q": "launch"}).json()
        self.assertEqual([item["conversation"]["id"] for item in title_hits], [project["id"]])
        message_hits = self.client.get("/v1/chat/conversations/search", params={"q": "readable"}).json()
        self.assertEqual(
            {item["conversation"]["id"] for item in message_hits},
            {general["id"], project["id"]},
        )
        self.assertEqual(
            {
                item["conversation"]["id"]: [message["content"] for message in item["matched_messages"]]
                for item in message_hits
            },
            {
                general["id"]: ["Readable banana message"],
                project["id"]: ["Readable cherry answer"],
            },
        )

        renamed = self.client.patch(
            f"/v1/chat/conversations/{project['id']}",
            json={"title": "Renamed project launch"},
        )
        self.assertEqual(renamed.status_code, 200, renamed.text)
        self.assertEqual(renamed.json()["title"], "Renamed project launch")
        archived = self.client.post(f"/v1/chat/conversations/{project['id']}/archive", json={"archived": True})
        self.assertEqual(archived.status_code, 200, archived.text)
        self.assertTrue(archived.json()["archived"])
        self.assertIsNotNone(archived.json()["archived_at"])
        for key, value in original_project_identity.items():
            self.assertEqual(archived.json()[key], value)

        active_ids = [item["id"] for item in self.client.get("/v1/chat/conversations").json()]
        self.assertIn(general["id"], active_ids)
        self.assertNotIn(project["id"], active_ids)
        self.assertEqual(self.client.get("/v1/chat/conversations/search", params={"q": "cherry"}).json(), [])
        archived_hits = self.client.get(
            "/v1/chat/conversations/search",
            params={"q": "cherry", "include_archived": True},
        ).json()
        self.assertEqual([item["conversation"]["id"] for item in archived_hits], [project["id"]])
        fetched_archived = self.client.get(f"/v1/chat/conversations/{project['id']}")
        self.assertEqual(fetched_archived.status_code, 200, fetched_archived.text)
        self.assertTrue(fetched_archived.json()["archived"])

        close_workbench_sqlite(self.app, self.client)
        self.app = create_app(data_root=self.root)
        self.manager = self.app.state.manager
        self.client = offline_workbench_client(self.app)

        after_reopen_default_ids = [item["id"] for item in self.client.get("/v1/chat/conversations").json()]
        self.assertIn(general["id"], after_reopen_default_ids)
        self.assertNotIn(project["id"], after_reopen_default_ids)
        after_reopen_archived = self.client.get(f"/v1/chat/conversations/{project['id']}").json()
        self.assertTrue(after_reopen_archived["archived"])
        self.assertEqual(after_reopen_archived["title"], "Renamed project launch")
        for key, value in original_project_identity.items():
            self.assertEqual(after_reopen_archived[key], value)

        reopened = self.client.post(f"/v1/chat/conversations/{project['id']}/reopen")
        self.assertEqual(reopened.status_code, 200, reopened.text)
        self.assertFalse(reopened.json()["archived"])
        self.assertIsNone(reopened.json()["archived_at"])
        for key, value in original_project_identity.items():
            self.assertEqual(reopened.json()[key], value)
        unarchived_ids = [item["id"] for item in self.client.get("/v1/chat/conversations").json()]
        self.assertIn(project["id"], unarchived_ids)

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
        self.assertEqual(conversation["enabled_tools"], ["echo", "time_now", "write_todos", "ask_user"])
        started = self._start(conversation["id"], task="Echo no-project.")
        self.assertFalse(started["filesystem_tools_available"])
        self.assertFalse(started["shell_tools_available"])
        self.assertEqual(started["enabled_tools"], ["echo", "time_now", "write_todos", "ask_user"])
        run = started["current_run"]
        self.assertEqual(run["enabled_tools"], ["echo", "time_now", "write_todos", "ask_user"])
        self.assertEqual(run["presented_tools"], ["echo", "time_now", "write_todos", "ask_user"])
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
        self.assertEqual(started.status_code, 409, started.text)
        self.assertEqual(started.json()["code"], "session_area_immutable")
        body = self.client.get(f"/v1/chat/conversations/{conversation['id']}").json()
        self.assertEqual(body["profile_id"], self.profile_id)
        self.assertEqual(body["project_path"], str(Path(workspace["path"]).resolve()))
        self.assertEqual(body["workspace_id"], workspace["id"])
        self.assertEqual(body["retrieval_project_paths"], [workspace["path"]])
        self.assertTrue(body["filesystem_tools_available"])
        self.assertTrue(body["shell_tools_available"])
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
        self.assertEqual(project_cleared.status_code, 409, project_cleared.text)
        self.assertEqual(project_cleared.json()["code"], "session_area_immutable")
        project_body = self.client.get(f"/v1/chat/conversations/{conversation['id']}").json()
        self.assertEqual(project_body["workspace_id"], workspace["id"])
        self.assertEqual(project_body["project_path"], str(Path(workspace["path"]).resolve()))
        self.assertEqual(project_body["retrieval_project_paths"], [workspace["path"]])
        self.assertTrue(project_body["filesystem_tools_available"])
        self.assertTrue(project_body["shell_tools_available"])

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

    def test_completion_between_next_start_reconciliation_and_admission_is_preserved(self) -> None:
        first_hold = threading.Event()
        second_hold = threading.Event()
        reconciled_running = threading.Event()
        admit_next = threading.Event()
        completed = threading.Event()
        set_generate_hold(first_hold)
        self.scripted = ScriptedChatModel([
            AIMessage(content="assistant A"), AIMessage(content="assistant B"),
        ])
        conversation_id = self._create()["id"]
        store = self.app.state.app_store
        chat = self.app.state.chat
        original_put_run = store.put_run
        original_reconcile = chat._reconcile_terminal_assistant
        results: list[ChatConversationView] = []
        errors: list[BaseException] = []

        def observe_completion(run: AgentRun) -> AgentRun:
            result = original_put_run(run)
            if run.status.value == "completed":
                completed.set()
            return result

        def pause_after_reconciliation(
            conversation: ChatConversation, run: AgentRun | None = None,
        ) -> tuple[ChatConversation, str | None]:
            result, terminal = original_reconcile(conversation, run)
            if not reconciled_running.is_set():
                self.assertEqual(chat.harness.get_run(first_id).status.value, "running")
                self.assertEqual([item.role for item in result.transcript], ["user"])
                reconciled_running.set()
                if not admit_next.wait(timeout=10):
                    raise TimeoutError("next-turn admission was not released")
            return result, terminal

        def start_next() -> None:
            try:
                results.append(chat.start(conversation_id, ChatStartRequest(task="user B")))
            except BaseException as exc:
                errors.append(exc)

        worker = threading.Thread(target=start_next)
        try:
            with patch.object(store, "put_run", side_effect=observe_completion):
                first_id = self._start(conversation_id, "user A")["current_run_id"]
                wait_for_generate_hold()
                with patch.object(chat, "_reconcile_terminal_assistant", side_effect=pause_after_reconciliation):
                    worker.start()
                    self.assertTrue(reconciled_running.wait(timeout=10))
                    first_hold.set()
                    self.assertTrue(completed.wait(timeout=10))
                    before = store.get_conversation(conversation_id)
                    self.assertEqual([item.content for item in before.transcript], ["user A", "assistant A"])
                    completed.clear()
                    set_generate_hold(second_hold)
                    admit_next.set()
                    worker.join(timeout=10)
                self.assertFalse(worker.is_alive())
                self.assertEqual(errors, [])
                self.assertEqual(len(results), 1)
                second_id = results[0].current_run_id
                wait_for_generate_hold()
                # Read SQLite directly: neither GET nor SSE may repair this assertion.
                stored = store.get_conversation(conversation_id)
                self.assertEqual(
                    [(item.role, item.content, item.run_id) for item in stored.transcript],
                    [("user", "user A", first_id), ("assistant", "assistant A", first_id),
                     ("user", "user B", second_id)],
                )
                self.assertEqual(stored.run_ids, [first_id, second_id])
                second_hold.set()
                self.assertTrue(completed.wait(timeout=10))
                stored = store.get_conversation(conversation_id)
                expected = [("user", "user A", first_id), ("assistant", "assistant A", first_id),
                            ("user", "user B", second_id), ("assistant", "assistant B", second_id)]
                self.assertEqual([(m.role, m.content, m.run_id) for m in stored.transcript], expected)
                reopened = chat.get(conversation_id)
                self.assertEqual([(m.role, m.content, m.run_id) for m in reopened.transcript], expected)
                self.assertEqual(reopened.thread_id, results[0].current_run.thread_id)
        finally:
            first_hold.set()
            second_hold.set()
            admit_next.set()
            if worker.ident is not None:
                worker.join(timeout=10)
            set_generate_hold(None)

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
        accepted = next(body for _status, body in results if body["current_run"] is not None)
        rejected = next(body for status, body in results if status == 409)
        self.assertEqual(rejected["code"], "chat_turn_active")
        fetched = self.client.get(f"/v1/chat/conversations/{conversation['id']}").json()
        self.assertEqual(len(fetched["run_ids"]), 1)
        self.assertEqual(len([item for item in fetched["transcript"] if item["role"] == "user"]), 1)
        self.assertEqual(fetched["current_run_id"], accepted["current_run"]["id"])
        self.assertEqual(fetched["queue"], [])
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

    def test_stop_pending_load_by_input_identity_before_run_admission(self) -> None:
        conversation = self._create()
        entered = threading.Event()
        release = threading.Event()
        original = self.manager.ensure_deployment_ready

        def blocked_ready(deployment_id: str):
            entered.set()
            self.assertTrue(release.wait(timeout=10), "test did not release model readiness")
            return original(deployment_id)

        result: dict[str, Any] = {}

        def start_turn() -> None:
            result["response"] = self.client.post(
                f"/v1/chat/conversations/{conversation['id']}/start",
                json={"task": "Write should-not-exist.txt.", "input_message_id": "pending-load-stop"},
            )

        with patch.object(self.manager, "ensure_deployment_ready", side_effect=blocked_ready):
            worker = threading.Thread(target=start_turn)
            worker.start()
            self.assertTrue(entered.wait(timeout=5), "start did not reach model readiness")
            stopped = self.client.post(
                f"/v1/chat/conversations/{conversation['id']}/cancel",
                json={"input_message_id": "pending-load-stop"},
            )
            self.assertEqual(stopped.status_code, 200, stopped.text)
            self.assertIsNone(stopped.json()["current_run_id"])
            self.assertEqual(stopped.json()["pending_cancel_input_ids"], ["pending-load-stop"])
            release.set()
            worker.join(timeout=10)
        self.assertFalse(worker.is_alive())
        started = result["response"]
        self.assertEqual(started.status_code, 200, started.text)
        run_id = started.json()["current_run_id"]
        self.assertIsNotNone(run_id)
        body = wait_for_chat(self.client, conversation["id"])
        self.assertEqual(body["current_run"]["id"], run_id)
        self.assertEqual(body["current_run"]["status"], "cancelled")
        self.assertEqual(body["transcript"][0]["id"], "pending-load-stop")
        self.assertEqual(body["transcript"][0]["run_id"], run_id)
        self.assertEqual(body["pending_cancel_input_ids"], [])
        self.assertFalse((self.project / "should-not-exist.txt").exists())

    def test_stop_after_harness_publish_before_worker_start_cancels_same_event(self) -> None:
        conversation = self._create()
        published = threading.Event()
        release_worker_start = threading.Event()
        original_thread_start = threading.Thread.start

        def gated_thread_start(thread: threading.Thread) -> None:
            target = getattr(thread, "_target", None)
            if target == self.app.state.harness._execute:
                published.set()
                self.assertTrue(release_worker_start.wait(timeout=10), "test did not release harness worker start")
            return original_thread_start(thread)

        result: dict[str, Any] = {}

        def start_turn() -> None:
            result["response"] = self.client.post(
                f"/v1/chat/conversations/{conversation['id']}/start",
                json={"task": "Write should-not-exist.txt.", "input_message_id": "published-before-worker-stop"},
            )

        with patch.object(threading.Thread, "start", gated_thread_start):
            worker = threading.Thread(target=start_turn)
            worker.start()
            self.assertTrue(published.wait(timeout=5), "harness run was not published before worker start")
            stopped = self.client.post(
                f"/v1/chat/conversations/{conversation['id']}/cancel",
                json={"input_message_id": "published-before-worker-stop"},
            )
            self.assertEqual(stopped.status_code, 200, stopped.text)
            self.assertIsNone(stopped.json()["current_run_id"])
            self.assertEqual(stopped.json()["pending_cancel_input_ids"], ["published-before-worker-stop"])
            release_worker_start.set()
            worker.join(timeout=10)
        self.assertFalse(worker.is_alive())
        started = result["response"]
        self.assertEqual(started.status_code, 200, started.text)
        run_id = started.json()["current_run_id"]
        body = wait_for_chat(self.client, conversation["id"])
        self.assertEqual(body["current_run"]["id"], run_id)
        self.assertEqual(body["current_run"]["status"], "cancelled")
        self.assertEqual(body["transcript"][0]["id"], "published-before-worker-stop")
        self.assertEqual(body["transcript"][0]["run_id"], run_id)
        self.assertEqual(body["pending_cancel_input_ids"], [])
        self.assertFalse((self.project / "should-not-exist.txt").exists())

    def test_restart_does_not_dispatch_stopped_queued_input(self) -> None:
        conversation = self._create()
        queued = self.client.post(
            f"/v1/chat/conversations/{conversation['id']}/queue",
            json={"task": "Queued stop before restart.", "input_message_id": "queued-stop-restart"},
        )
        self.assertEqual(queued.status_code, 200, queued.text)
        stopped = self.client.post(
            f"/v1/chat/conversations/{conversation['id']}/cancel",
            json={"input_message_id": "queued-stop-restart"},
        )
        self.assertEqual(stopped.status_code, 200, stopped.text)
        self.assertEqual(stopped.json()["queue"][0]["status"], "paused")
        self.assertEqual(stopped.json()["queue"][0]["pause_error_code"], "cancel_requested")

        restarted = create_app(data_root=self.root)
        restarted_scripted = ScriptedChatModel([AIMessage(content="must not dispatch")])
        restarted.state.harness = HarnessService(
            lambda: restarted.state.manager,
            model_factory=lambda _run, _sink: restarted_scripted,
            knowledge_provider=lambda: restarted.state.knowledge,
            app_store=restarted.state.app_store,
        )
        try:
            dispatched = restarted.state.chat.dispatch_idle_queued(conversation["id"])
            self.assertEqual(dispatched, 0)
            with offline_workbench_client(restarted) as live_client:
                fetched = live_client.get(f"/v1/chat/conversations/{conversation['id']}").json()
        finally:
            close_workbench_sqlite(restarted)
        self.assertEqual(fetched["run_ids"], [])
        self.assertEqual(fetched["queue"][0]["status"], "paused")
        self.assertEqual(fetched["queue"][0]["input_message_id"], "queued-stop-restart")
        self.assertEqual(fetched["pending_cancel_input_ids"], [])

    def test_failed_admission_clears_pending_cancel_but_tombstone_blocks_replay(self) -> None:
        conversation = self._create()
        entered = threading.Event()
        release = threading.Event()

        def failed_ready(_deployment_id: str):
            entered.set()
            self.assertTrue(release.wait(timeout=10), "test did not release failed readiness")
            raise ManagerError("synthetic startup failure", code="deployment_not_ready", status_code=409)

        result: dict[str, Any] = {}

        def start_turn() -> None:
            result["response"] = self.client.post(
                f"/v1/chat/conversations/{conversation['id']}/start",
                json={"task": "Failed startup.", "input_message_id": "failed-start-stop"},
            )

        with patch.object(self.manager, "ensure_deployment_ready", side_effect=failed_ready):
            worker = threading.Thread(target=start_turn)
            worker.start()
            self.assertTrue(entered.wait(timeout=5), "start did not reach failed readiness")
            stopped = self.client.post(
                f"/v1/chat/conversations/{conversation['id']}/cancel",
                json={"input_message_id": "failed-start-stop"},
            )
            self.assertEqual(stopped.status_code, 200, stopped.text)
            self.assertEqual(stopped.json()["pending_cancel_input_ids"], ["failed-start-stop"])
            release.set()
            worker.join(timeout=10)
        self.assertFalse(worker.is_alive())
        self.assertEqual(result["response"].status_code, 409, result["response"].text)
        after_failure = self.client.get(f"/v1/chat/conversations/{conversation['id']}").json()
        self.assertEqual(after_failure["pending_cancel_input_ids"], [])
        self.assertEqual(after_failure["run_ids"], [])

        retry = self.client.post(
            f"/v1/chat/conversations/{conversation['id']}/start",
            json={"task": "Failed startup.", "input_message_id": "failed-start-stop"},
        )
        self.assertEqual(retry.status_code, 200, retry.text)
        body = wait_for_chat(self.client, conversation["id"])
        self.assertEqual(body["current_run"]["status"], "cancelled")
        self.assertEqual(body["transcript"][0]["run_id"], body["current_run_id"])
        self.assertEqual(body["pending_cancel_input_ids"], [])

    def test_stop_rereads_after_stale_initial_snapshot_and_cancels_accepted_run(self) -> None:
        conversation = self._create()
        cancel_has_stale_snapshot = threading.Event()
        allow_cancel_claim = threading.Event()
        held_harness_thread: list[threading.Thread] = []
        original_request_cancel = self.app.state.chat._request_submission_cancel
        original_thread_start = threading.Thread.start

        def delayed_request_cancel(conversation_snapshot: ChatConversation, input_message_id: str) -> None:
            cancel_has_stale_snapshot.set()
            self.assertTrue(allow_cancel_claim.wait(timeout=10), "test did not release cancel claim")
            original_request_cancel(conversation_snapshot, input_message_id)

        def hold_harness_worker_start(thread: threading.Thread) -> None:
            target = getattr(thread, "_target", None)
            if target == self.app.state.harness._execute:
                held_harness_thread.append(thread)
                return
            return original_thread_start(thread)

        cancel_result: dict[str, Any] = {}

        def cancel_turn() -> None:
            cancel_result["response"] = self.client.post(
                f"/v1/chat/conversations/{conversation['id']}/cancel",
                json={"input_message_id": "stale-read-stop"},
            )

        with patch.object(self.app.state.chat, "_request_submission_cancel", side_effect=delayed_request_cancel):
            with patch.object(threading.Thread, "start", hold_harness_worker_start):
                start_worker = threading.Thread(
                    target=lambda: self.client.post(
                        f"/v1/chat/conversations/{conversation['id']}/start",
                        json={"task": "Write should-not-exist.txt.", "input_message_id": "stale-read-stop"},
                    )
                )
                start_worker.start()
                start_worker.join(timeout=10)
            self.assertFalse(start_worker.is_alive())
            self.assertEqual(len(held_harness_thread), 1)

            cancel_worker = threading.Thread(target=cancel_turn)
            cancel_worker.start()
            self.assertTrue(cancel_has_stale_snapshot.wait(timeout=5), "cancel did not take stale snapshot")
            allow_cancel_claim.set()
            cancel_worker.join(timeout=10)
        self.assertFalse(cancel_worker.is_alive())
        cancelled = cancel_result["response"]
        self.assertEqual(cancelled.status_code, 200, cancelled.text)
        self.assertEqual(cancelled.json()["current_run"]["status"], "cancel_requested")
        original_thread_start(held_harness_thread[0])
        body = wait_for_chat(self.client, conversation["id"])
        self.assertEqual(body["current_run"]["status"], "cancelled")
        self.assertEqual(body["transcript"][0]["id"], "stale-read-stop")
        self.assertEqual(body["transcript"][0]["run_id"], body["current_run_id"])
        self.assertFalse((self.project / "should-not-exist.txt").exists())

    def test_stop_pending_identity_does_not_cancel_previous_terminal_run(self) -> None:
        conversation = self._create()
        first = self._start(conversation["id"], "First completed turn.")
        first_run_id = first["current_run_id"]
        wait_for_chat(self.client, conversation["id"])
        entered = threading.Event()
        release = threading.Event()
        original = self.manager.ensure_deployment_ready

        def blocked_ready(deployment_id: str):
            entered.set()
            self.assertTrue(release.wait(timeout=10), "test did not release model readiness")
            return original(deployment_id)

        result: dict[str, Any] = {}

        def start_turn() -> None:
            result["response"] = self.client.post(
                f"/v1/chat/conversations/{conversation['id']}/start",
                json={"task": "Second pending turn.", "input_message_id": "second-pending-stop"},
            )

        with patch.object(self.manager, "ensure_deployment_ready", side_effect=blocked_ready):
            worker = threading.Thread(target=start_turn)
            worker.start()
            self.assertTrue(entered.wait(timeout=5), "second start did not reach model readiness")
            stopped = self.client.post(
                f"/v1/chat/conversations/{conversation['id']}/cancel",
                json={"input_message_id": "second-pending-stop"},
            )
            self.assertEqual(stopped.status_code, 200, stopped.text)
            self.assertEqual(stopped.json()["current_run_id"], first_run_id)
            self.assertEqual(stopped.json()["current_run"]["status"], "completed")
            release.set()
            worker.join(timeout=10)
        self.assertFalse(worker.is_alive())
        second = result["response"].json()
        self.assertNotEqual(second["current_run_id"], first_run_id)
        body = wait_for_chat(self.client, conversation["id"])
        self.assertEqual(body["current_run"]["id"], second["current_run_id"])
        self.assertEqual(body["current_run"]["status"], "cancelled")
        stored_first = self.app.state.app_store.get_run(first_run_id)
        self.assertIsNotNone(stored_first)
        assert stored_first is not None
        self.assertEqual(stored_first.status.value, "completed")

    def test_stale_input_identity_does_not_cancel_later_turn(self) -> None:
        conversation = self._create()
        first = self._start(conversation["id"], "First completed turn.")
        wait_for_chat(self.client, conversation["id"])
        hold = threading.Event()
        previous = self.app.state.harness
        set_generate_hold(hold)
        self.addCleanup(set_generate_hold, None)
        self.addCleanup(hold.set)
        self.addCleanup(previous.close)

        def factory(_run: AgentRun, _sink: list[dict[str, Any]]) -> ScriptedChatModel:
            return ScriptedChatModel([AIMessage(content="later still runs")], hold=hold)

        self.app.state.harness = HarnessService(
            lambda: self.manager,
            model_factory=factory,
            knowledge_provider=lambda: self.app.state.knowledge,
            app_store=self.app.state.app_store,
        )
        second = self.client.post(
            f"/v1/chat/conversations/{conversation['id']}/start",
            json={"task": "Later turn.", "input_message_id": "later-live"},
        )
        self.assertEqual(second.status_code, 200, second.text)
        second_run_id = second.json()["current_run_id"]
        wait_for_status(self.client, second_run_id, "running")
        wait_for_generate_hold()
        stale = self.client.post(
            f"/v1/chat/conversations/{conversation['id']}/cancel",
            json={"input_message_id": first["transcript"][0]["id"]},
        )
        self.assertEqual(stale.status_code, 200, stale.text)
        self.assertEqual(stale.json()["current_run_id"], second_run_id)
        self.assertEqual(stale.json()["current_run"]["status"], "running")
        hold.set()
        body = wait_for_chat(self.client, conversation["id"])
        self.assertEqual(body["current_run"]["id"], second_run_id)
        self.assertEqual(body["current_run"]["status"], "completed")

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
            queued = self.client.post(
                f"/v1/chat/conversations/{conversation['id']}/queue",
                json={"task": "Second turn while cancelling."},
            )
            self.assertEqual(queued.status_code, 200, queued.text)
            self.assertEqual(len(queued.json()["queue"]), 1)
            self.assertEqual(queued.json()["queue"][0]["task"], "Second turn while cancelling.")
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
        terminal = self.app.state.app_store.get_run(first_run_id)
        self.assertIsNotNone(terminal)
        assert terminal is not None
        self.app.state.chat.observe_terminal_run(terminal)
        body = self.client.get(f"/v1/chat/conversations/{conversation['id']}").json()
        self.assertEqual(body["current_run"]["status"], "cancelled")
        self.assertEqual(body["current_run"]["id"], first_run_id)
        self.assertEqual(body["current_run_id"], first_run_id)
        self.assertEqual(body["queue"][0]["status"], "paused")
        self.assertEqual(body["queue"][0]["pause_reason"], "cancelled")
        queue_id = body["queue"][0]["id"]
        edited = self.client.patch(
            f"/v1/chat/conversations/{conversation['id']}/queue/{queue_id}",
            json={"task": "Edited but still paused."},
        )
        self.assertEqual(edited.status_code, 200, edited.text)
        self.assertEqual(edited.json()["queue"][0]["task"], "Edited but still paused.")
        self.assertEqual(edited.json()["queue"][0]["status"], "paused")
        removed = self.client.delete(f"/v1/chat/conversations/{conversation['id']}/queue/{queue_id}")
        self.assertEqual(removed.status_code, 200, removed.text)
        self.assertEqual(removed.json()["queue"], [])
        self.assertEqual(body["current_run"]["tool_invocations"], [])
        self.assertFalse((self.project / "edited.md").exists(), "cancelled model tool call must not execute")
        messages = conversation_state(
            self.manager.paths.checkpoints_db,
            conversation["thread_id"],
        ).get("messages", [])
        calls = [
            call
            for message in messages
            if isinstance(message, AIMessage)
            for call in message.tool_calls
            if call.get("id") == "call_write"
        ]
        self.assertEqual(len(calls), 1, "the original model tool call remains in durable history")
        results = [
            message
            for message in messages
            if isinstance(message, ToolMessage) and message.tool_call_id == "call_write"
        ]
        self.assertEqual(len(results), 1, "cancelled tool call receives one durable protocol result")
        self.assertEqual(results[0].status, "error")
        self.assertIn("Completion is unconfirmed", results[0].content)
        follow = self._start(conversation["id"], task="Follow-up after confirmed cancel.")
        self.assertNotEqual(follow["current_run"]["id"], first_run_id)
        self.assertEqual(follow["current_run_id"], follow["current_run"]["id"])
        listed_after = self.client.get("/v1/agent-runs").json()
        ids = [item["id"] for item in listed_after]
        self.assertEqual(set(ids), {first_run_id, follow["current_run"]["id"]})

    def test_start_rejects_session_area_move(self) -> None:
        other_project = self.root / "other-project"
        other_project.mkdir()
        conversation = self._create()
        moved = self.client.post(
            f"/v1/chat/conversations/{conversation['id']}/start",
            json={"task": "Move this chat.", "project_path": str(other_project)},
        )
        self.assertEqual(moved.status_code, 409, moved.text)
        self.assertEqual(moved.json()["code"], "session_area_immutable")
        fetched = self.client.get(f"/v1/chat/conversations/{conversation['id']}").json()
        self.assertEqual(fetched["project_path"], str(self.project.resolve()))
        self.assertEqual(fetched["area_project_path"], str(self.project.resolve()))
        self.assertEqual(fetched["transcript"], [])
        self.assertEqual(fetched["run_ids"], [])

    def test_branch_followup_compares_current_execution_binding_not_original_area(self) -> None:
        original = self.root / "original-project"
        original.mkdir()
        restored = self.root / "restored-project"
        restored.mkdir()
        conversation = self._create(project_path=str(restored))
        stored = self.app.state.app_store.get_conversation(conversation["id"])
        self.assertIsNotNone(stored)
        assert stored is not None
        stored.area_project_path = str(original.resolve())
        stored.area_id = str(original.resolve())
        stored.area_label = "original-project"
        self.app.state.app_store.put_conversation(stored)

        accepted = self.client.post(
            f"/v1/chat/conversations/{conversation['id']}/start",
            json={"task": "Continue restored execution.", "project_path": str(restored)},
        )
        self.assertEqual(accepted.status_code, 200, accepted.text)
        wait_for_chat(self.client, conversation["id"])

        rejected = self.client.post(
            f"/v1/chat/conversations/{conversation['id']}/start",
            json={"task": "Move back to original.", "project_path": str(original)},
        )
        self.assertEqual(rejected.status_code, 409, rejected.text)
        self.assertEqual(rejected.json()["code"], "session_area_immutable")

    def test_project_branch_retains_removed_original_area_identity(self) -> None:
        self.scripted = ScriptedChatModel([AIMessage(content="answer before original project removal")])
        conversation = self._create(title="Removed original project")
        started = self._start(conversation["id"], "Capture project state before removal.")
        finished = wait_for_chat(self.client, conversation["id"])
        run = self.app.state.app_store.get_run(started["current_run"]["id"])
        self.assertIsNotNone(run)
        assert run is not None
        self.assertTrue(run.final_snapshot_id)

        original_path = str(self.project.resolve())
        shutil.rmtree(self.project)
        self.assertFalse(self.project.exists())
        reopened = self.client.get(f"/v1/chat/conversations/{conversation['id']}")
        self.assertEqual(reopened.status_code, 200, reopened.text)
        self.assertEqual(reopened.json()["area_project_path"], original_path)
        self.assertEqual(reopened.json()["area_id"], original_path)
        self.assertEqual(reopened.json()["area_label"], self.project.name)

        branch = self.client.post(
            f"/v1/chat/conversations/{conversation['id']}/branches",
            json={"source_run_id": finished["current_run_id"], "mode": "continue"},
        )

        self.assertEqual(branch.status_code, 200, branch.text)
        body = branch.json()
        self.assertEqual(body["source_conversation_id"], conversation["id"])
        self.assertEqual(body["area_project_path"], original_path)
        self.assertEqual(body["area_id"], original_path)
        self.assertEqual(body["area_label"], self.project.name)
        self.assertNotEqual(body["project_path"], original_path)
        branch_project_path = Path(body["project_path"])
        self.assertTrue(branch_project_path.is_dir())
        self.assertTrue(branch_project_path.is_relative_to(self.app.state.manager.paths.workspaces.resolve()))
        self.assertEqual(body["branch_head_checkpoint_id"], body["source_checkpoint_id"])

    def test_terminal_reconciliation_updates_branch_head_checkpoint(self) -> None:
        conversation = self._create()
        stored = self.app.state.app_store.get_conversation(conversation["id"])
        self.assertIsNotNone(stored)
        assert stored is not None
        stored.source_conversation_id = "chat_source"
        stored.branch_head_checkpoint_id = stored.source_checkpoint_id = "snap_old"
        self.app.state.app_store.put_conversation(stored)

        started = self._start(conversation["id"], "Advance branch head.")
        finished = wait_for_chat(self.client, conversation["id"])
        run = self.app.state.app_store.get_run(started["current_run"]["id"])
        self.assertIsNotNone(run)
        assert run is not None
        self.assertTrue(run.final_snapshot_id)
        self.assertTrue(run.checkpoint_ids)
        self.assertNotEqual(run.final_snapshot_id, run.checkpoint_ids[0])
        self.app.state.chat.observe_terminal_run(run)
        fetched = self.client.get(f"/v1/chat/conversations/{conversation['id']}").json()
        self.assertEqual(fetched["current_run"]["status"], finished["current_run"]["status"])
        self.assertIn(fetched["branch_head_checkpoint_id"], run.checkpoint_ids)

    def test_accepted_start_clears_matching_draft_revision(self) -> None:
        conversation = self._create()
        draft = self.client.put(
            f"/v1/chat/conversations/{conversation['id']}/draft",
            json={
                "content": "Send this draft.",
                "attachment_ids": [],
                "intended_config": {"deployment_id": self.deployment_id},
            },
        )
        self.assertEqual(draft.status_code, 200, draft.text)
        revision = draft.json()["draft"]["revision"]

        started = self.client.post(
            f"/v1/chat/conversations/{conversation['id']}/start",
            json={"task": "Send this draft.", "draft_revision": revision},
        )

        self.assertEqual(started.status_code, 200, started.text)
        self.assertEqual(started.json()["draft"]["content"], "")
        self.assertEqual(started.json()["draft"]["attachment_ids"], [])
        self.assertEqual(started.json()["draft"]["intended_config"], {"deployment_id": self.deployment_id})
        self.assertEqual(started.json()["draft"]["revision"], revision + 1)
        fetched = self.client.get(f"/v1/chat/conversations/{conversation['id']}").json()
        self.assertEqual(fetched["draft"]["content"], "")
        self.assertEqual(fetched["draft"]["revision"], revision + 1)
        self.assertEqual(fetched["transcript"][-1]["content"], "Send this draft.")

    def test_start_preserves_newer_draft_revision(self) -> None:
        conversation = self._create()
        first = self.client.put(
            f"/v1/chat/conversations/{conversation['id']}/draft",
            json={"content": "Original draft.", "intended_config": {"deployment_id": self.deployment_id}},
        )
        self.assertEqual(first.status_code, 200, first.text)
        stale_revision = first.json()["draft"]["revision"]
        second = self.client.put(
            f"/v1/chat/conversations/{conversation['id']}/draft",
            json={
                "content": "Newer unsent draft.",
                "intended_config": {"deployment_id": self.deployment_id, "per_request_overrides": {"temperature": 0.4}},
                "expected_revision": stale_revision,
            },
        )
        self.assertEqual(second.status_code, 200, second.text)

        started = self.client.post(
            f"/v1/chat/conversations/{conversation['id']}/start",
            json={"task": "Original draft.", "draft_revision": stale_revision},
        )

        self.assertEqual(started.status_code, 200, started.text)
        self.assertEqual(started.json()["draft"]["content"], "Newer unsent draft.")
        self.assertEqual(started.json()["draft"]["revision"], stale_revision + 1)
        self.assertEqual(
            started.json()["draft"]["intended_config"]["per_request_overrides"],
            {"temperature": 0.4},
        )

    def test_failed_start_admission_preserves_submitted_draft_revision(self) -> None:
        conversation = self._create()
        draft = self.client.put(
            f"/v1/chat/conversations/{conversation['id']}/draft",
            json={"content": "Keep after failure.", "intended_config": {"deployment_id": self.deployment_id}},
        )
        self.assertEqual(draft.status_code, 200, draft.text)
        revision = draft.json()["draft"]["revision"]

        failed = self.client.post(
            f"/v1/chat/conversations/{conversation['id']}/start",
            json={
                "task": "Keep after failure.",
                "draft_revision": revision,
                "deployment_id": "missing-deployment",
            },
        )

        self.assertNotEqual(failed.status_code, 200, failed.text)
        fetched = self.client.get(f"/v1/chat/conversations/{conversation['id']}").json()
        self.assertEqual(fetched["draft"]["content"], "Keep after failure.")
        self.assertEqual(fetched["draft"]["revision"], revision)

    def test_enqueue_clears_matching_draft_revision(self) -> None:
        conversation = self._create()
        draft = self.client.put(
            f"/v1/chat/conversations/{conversation['id']}/draft",
            json={
                "content": "Queue this draft.",
                "attachment_ids": [],
                "intended_config": {"deployment_id": self.deployment_id, "presented_tools": []},
            },
        )
        self.assertEqual(draft.status_code, 200, draft.text)
        revision = draft.json()["draft"]["revision"]

        queued = self.client.post(
            f"/v1/chat/conversations/{conversation['id']}/queue",
            json={
                "task": "Queue this draft.",
                "draft_revision": revision,
                "deployment_id": self.deployment_id,
                "presented_tools": [],
            },
        )

        self.assertEqual(queued.status_code, 200, queued.text)
        self.assertEqual(queued.json()["draft"]["content"], "")
        self.assertEqual(queued.json()["draft"]["attachment_ids"], [])
        self.assertEqual(
            queued.json()["draft"]["intended_config"],
            {"deployment_id": self.deployment_id, "presented_tools": []},
        )
        self.assertEqual(queued.json()["draft"]["revision"], revision + 1)
        self.assertEqual(queued.json()["queue"][0]["task"], "Queue this draft.")
        self.assertEqual(queued.json()["queue"][0]["intended_config"]["presented_tools"], [])

    def test_accept_run_atomically_clears_matching_draft_without_resetting_revision(self) -> None:
        conversation = self._create()
        draft = self.client.put(
            f"/v1/chat/conversations/{conversation['id']}/draft",
            json={
                "content": "Crash-window draft.",
                "attachment_ids": [],
                "intended_config": {"deployment_id": self.deployment_id, "per_request_overrides": {"temperature": 0.3}},
            },
        )
        self.assertEqual(draft.status_code, 200, draft.text)
        revision = draft.json()["draft"]["revision"]
        stored = self.app.state.app_store.get_conversation(conversation["id"])
        self.assertIsNotNone(stored)
        assert stored is not None
        stored.transcript.append(
            ChatMessage(
                id="crash-window-input",
                role="user",
                content="Crash-window draft.",
                at=utc_now(),
            )
        )
        self.app.state.app_store.put_conversation(stored)

        accepted = self.app.state.app_store.accept_chat_dispatched_run(
            conversation["id"],
            "run_crash_window",
            "crash-window-input",
            draft_revision=revision,
        )

        self.assertIsNotNone(accepted)
        assert accepted is not None
        self.assertEqual(accepted.current_run_id, "run_crash_window")
        self.assertEqual(accepted.transcript[-1].run_id, "run_crash_window")
        self.assertIsNotNone(accepted.draft)
        assert accepted.draft is not None
        self.assertEqual(accepted.draft.content, "")
        self.assertEqual(accepted.draft.attachment_ids, [])
        self.assertEqual(accepted.draft.revision, revision + 1)
        self.assertEqual(
            accepted.draft.intended_config,
            {"deployment_id": self.deployment_id, "per_request_overrides": {"temperature": 0.3}},
        )

    def test_queued_dispatch_does_not_clear_newer_draft(self) -> None:
        hold = threading.Event()
        set_generate_hold(hold)
        self.addCleanup(set_generate_hold, None)
        self.addCleanup(hold.set)
        scripted = ScriptedChatModel([AIMessage(content="held first"), AIMessage(content="queued reply")])

        def factory(_run: AgentRun, _sink: list[dict[str, Any]]) -> ScriptedChatModel:
            return scripted

        self.app.state.harness = HarnessService(
            lambda: self.manager,
            model_factory=factory,
            knowledge_provider=lambda: self.app.state.knowledge,
            app_store=self.app.state.app_store,
        )
        conversation = self._create()
        first = self._start(conversation["id"], "Held first.")
        wait_for_status(self.client, first["current_run"]["id"], "running")
        wait_for_generate_hold()
        draft = self.client.put(
            f"/v1/chat/conversations/{conversation['id']}/draft",
            json={"content": "Queued draft.", "intended_config": {"deployment_id": self.deployment_id}},
        )
        self.assertEqual(draft.status_code, 200, draft.text)
        queued_revision = draft.json()["draft"]["revision"]
        queued = self.client.post(
            f"/v1/chat/conversations/{conversation['id']}/queue",
            json={"task": "Queued draft.", "draft_revision": queued_revision},
        )
        self.assertEqual(queued.status_code, 200, queued.text)
        self.assertEqual(queued.json()["draft"]["content"], "")
        self.assertEqual(queued.json()["draft"]["revision"], queued_revision + 1)
        newer = self.client.put(
            f"/v1/chat/conversations/{conversation['id']}/draft",
            json={"content": "Future unsent draft.", "intended_config": {"deployment_id": self.deployment_id}},
        )
        self.assertEqual(newer.status_code, 200, newer.text)
        newer_revision = newer.json()["draft"]["revision"]

        hold.set()
        wait_for_run(self.client, first["current_run"]["id"])
        terminal = self.app.state.app_store.get_run(first["current_run"]["id"])
        self.assertIsNotNone(terminal)
        assert terminal is not None
        self.app.state.chat.observe_terminal_run(terminal)
        dispatched = self.client.get(f"/v1/chat/conversations/{conversation['id']}").json()

        self.assertEqual(dispatched["draft"]["content"], "Future unsent draft.")
        self.assertEqual(dispatched["draft"]["revision"], newer_revision)
        self.assertEqual(dispatched["queue"][0]["status"], "dispatching")

    def test_queued_turn_dispatches_after_success_and_pauses_after_failure(self) -> None:
        hold = threading.Event()
        set_generate_hold(hold)
        self.addCleanup(set_generate_hold, None)
        self.addCleanup(hold.set)
        scripted = ScriptedChatModel(
            [
                AIMessage(content="held first"),
                AIMessage(content="queued second"),
            ]
        )

        def factory(_run: AgentRun, _sink: list[dict[str, Any]]) -> ScriptedChatModel:
            return scripted

        self.app.state.harness = HarnessService(
            lambda: self.manager,
            model_factory=factory,
            knowledge_provider=lambda: self.app.state.knowledge,
            app_store=self.app.state.app_store,
        )
        conversation = self._create()
        first = self._start(conversation["id"], "Held first.")
        wait_for_status(self.client, first["current_run"]["id"], "running")
        wait_for_generate_hold()
        queued = self.client.post(
            f"/v1/chat/conversations/{conversation['id']}/queue",
            json={
                "task": "Queued second.",
                "deployment_id": self.deployment_id,
                "per_request_overrides": {"temperature": 0.2},
            },
        )
        self.assertEqual(queued.status_code, 200, queued.text)
        self.assertEqual(queued.json()["queue"][0]["task"], "Queued second.")
        self.assertIsNone(queued.json()["queue"][0]["frozen_config"])
        self.assertEqual(queued.json()["queue"][0]["intended_config"]["deployment_id"], self.deployment_id)
        self.assertEqual(queued.json()["queue"][0]["intended_config"]["per_request_overrides"], {"temperature": 0.2})
        hold.set()
        wait_for_run(self.client, first["current_run"]["id"])
        terminal = self.app.state.app_store.get_run(first["current_run"]["id"])
        self.assertIsNotNone(terminal)
        assert terminal is not None
        self.app.state.chat.observe_terminal_run(terminal)
        self.app.state.chat.observe_terminal_run(terminal)
        running_second = self.client.get(f"/v1/chat/conversations/{conversation['id']}").json()
        self.assertEqual(running_second["queue"][0]["status"], "dispatching")
        self.assertEqual(running_second["queue"][0]["run_id"], running_second["current_run_id"])
        self.assertEqual(len(running_second["run_ids"]), 2)
        finished = wait_for_chat(self.client, conversation["id"])
        second_run = self.app.state.app_store.get_run(finished["current_run_id"])
        self.assertIsNotNone(second_run)
        assert second_run is not None
        self.app.state.chat.observe_terminal_run(second_run)
        self.app.state.chat.observe_terminal_run(second_run)
        finished = self.client.get(f"/v1/chat/conversations/{conversation['id']}").json()
        self.assertEqual(finished["queue"], [])
        self.assertEqual(len(finished["run_ids"]), 2)
        self.assertTrue(
            any(
                item["role"] == "user" and item["content"] == "Queued second."
                for item in finished["transcript"]
            )
        )
        self.assertEqual(finished["transcript"][-1]["content"], "queued second")

    def test_queue_waits_behind_host_shell_approval_until_deliberate_resolution(self) -> None:
        marker = "queue-approval-marker.txt"
        self.scripted = ScriptedChatModel(
            [
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "execute",
                            "args": {"command": host_shell_marker_command(marker)},
                            "id": "call_exec",
                        }
                    ],
                ),
                AIMessage(content="approval resolved"),
                AIMessage(content="queued after approval"),
            ]
        )
        conversation = self._create()
        started = self.client.post(
            f"/v1/chat/conversations/{conversation['id']}/start",
            json={"task": "Wait for approval.", "presented_tools": ["execute"]},
        )
        self.assertEqual(started.status_code, 200, started.text)
        paused = wait_for_chat_interrupt(self.client, conversation["id"])
        first_run_id = paused["current_run_id"]
        queued = self.client.post(
            f"/v1/chat/conversations/{conversation['id']}/queue",
            json={"task": "Run only after approval succeeds.", "input_message_id": "queued-after-approval"},
        )
        self.assertEqual(queued.status_code, 200, queued.text)
        self.assertEqual(queued.json()["queue"][0]["status"], "queued")
        self.assertEqual(queued.json()["run_ids"], [first_run_id])
        self.assertEqual(len(self.app.state.harness.list_runs()), 1)

        decided = self.client.post(
            f"/v1/chat/conversations/{conversation['id']}/interrupt-decision",
            json=chat_interrupt_decision(paused, "approve"),
        )
        self.assertEqual(decided.status_code, 200, decided.text)
        terminal = wait_for_run(self.client, first_run_id)
        self.assertEqual(terminal["status"], "completed", terminal.get("error"))
        self.assertTrue((self.project / marker).is_file())
        self.app.state.chat.observe_terminal_run(AgentRun.model_validate(terminal))
        dispatched = self.client.get(f"/v1/chat/conversations/{conversation['id']}").json()
        self.assertEqual(dispatched["queue"][0]["status"], "dispatching")
        self.assertEqual(dispatched["queue"][0]["input_message_id"], "queued-after-approval")
        self.assertEqual(len(dispatched["run_ids"]), 2)
        self.assertNotEqual(dispatched["current_run_id"], first_run_id)
        queued_run = wait_for_run(self.client, dispatched["current_run_id"])
        self.assertEqual(queued_run["status"], "completed", queued_run.get("error"))

    def test_queue_waits_behind_typed_question_until_answered(self) -> None:
        self.scripted = ScriptedChatModel(
            [
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "ask_user",
                            "args": {"prompt": "Choose format", "answer_type": "text"},
                            "id": "ask_1",
                        }
                    ],
                ),
                AIMessage(content="typed answer resolved"),
                AIMessage(content="queued after typed answer"),
            ]
        )
        conversation = self._create()
        started = self.client.post(
            f"/v1/chat/conversations/{conversation['id']}/start",
            json={"task": "Ask a question.", "presented_tools": ["ask_user"]},
        )
        self.assertEqual(started.status_code, 200, started.text)
        paused = wait_for_chat_interrupt(self.client, conversation["id"])
        first_run_id = paused["current_run_id"]
        pending = paused["current_run"]["pending_interrupt"]
        self.assertEqual(pending["kind"], "ask_user")
        queued = self.client.post(
            f"/v1/chat/conversations/{conversation['id']}/queue",
            json={"task": "Run only after typed answer succeeds.", "input_message_id": "queued-after-answer"},
        )
        self.assertEqual(queued.status_code, 200, queued.text)
        self.assertEqual(queued.json()["queue"][0]["status"], "queued")
        self.assertEqual(queued.json()["run_ids"], [first_run_id])
        self.assertEqual(len(self.app.state.harness.list_runs()), 1)

        self.app.state.harness.resume_interrupt(
            first_run_id,
            UserAnswerRequest(
                answer="Markdown",
                interrupt_id=pending["interrupt_id"],
                namespace=pending.get("namespace", []),
            ),
            require_interrupt_identity=True,
        )
        terminal = wait_for_run(self.client, first_run_id)
        self.assertEqual(terminal["status"], "completed", terminal.get("error"))
        self.app.state.chat.observe_terminal_run(AgentRun.model_validate(terminal))
        dispatched = self.client.get(f"/v1/chat/conversations/{conversation['id']}").json()
        self.assertEqual(dispatched["queue"][0]["status"], "dispatching")
        self.assertEqual(dispatched["queue"][0]["input_message_id"], "queued-after-answer")
        self.assertEqual(len(dispatched["run_ids"]), 2)
        self.assertNotEqual(dispatched["current_run_id"], first_run_id)
        queued_run = wait_for_run(self.client, dispatched["current_run_id"])
        self.assertEqual(queued_run["status"], "completed", queued_run.get("error"))

    def test_queue_requires_resume_and_preserves_intended_config_across_selector_changes(self) -> None:
        other = self.client.post(
            "/v1/deployments/connected",
            json={"endpoint": "http://127.0.0.1:10/v1", "display_name": "queue-other"},
        ).json()
        self.scripted = ScriptedChatModel(
            [
                AIMessage(content="direct selector change"),
                AIMessage(content="queued original config"),
            ]
        )
        conversation = self._create()
        queued = self.client.post(
            f"/v1/chat/conversations/{conversation['id']}/queue",
            json={
                "task": "Queued original.",
                "deployment_id": self.deployment_id,
                "per_request_overrides": {"temperature": 0.3},
            },
        )
        self.assertEqual(queued.status_code, 200, queued.text)
        queue_id = queued.json()["queue"][0]["id"]
        self.assertEqual(queued.json()["queue"][0]["status"], "queued")
        self.assertEqual(queued.json()["queue"][0]["intended_config"]["deployment_id"], self.deployment_id)

        fetched = self.client.get(f"/v1/chat/conversations/{conversation['id']}").json()
        self.assertEqual(fetched["run_ids"], [])
        self.assertEqual(fetched["queue"][0]["id"], queue_id)

        direct = self.client.post(
            f"/v1/chat/conversations/{conversation['id']}/start",
            json={"task": "Change selector.", "deployment_id": other["id"]},
        )
        self.assertEqual(direct.status_code, 200, direct.text)
        self.assertEqual(direct.json()["deployment_id"], other["id"])
        wait_for_chat(self.client, conversation["id"])

        resumed = self.client.post(f"/v1/chat/conversations/{conversation['id']}/queue/resume", json={})
        self.assertEqual(resumed.status_code, 200, resumed.text)
        self.assertEqual(resumed.json()["current_run"]["deployment_id"], self.deployment_id)
        self.assertEqual(resumed.json()["queue"][0]["status"], "dispatching")
        self.assertEqual(resumed.json()["queue"][0]["frozen_config"]["deployment_id"], self.deployment_id)
        self.assertEqual(
            resumed.json()["queue"][0]["frozen_config"]["per_request_overrides"],
            {"temperature": 0.3},
        )

    def test_queue_partial_intended_config_edit_keeps_frozen_selector(self) -> None:
        other = self.client.post(
            "/v1/deployments/connected",
            json={"endpoint": "http://127.0.0.1:10/v1", "display_name": "queue-partial-other"},
        ).json()
        self.scripted = ScriptedChatModel(
            [
                AIMessage(content="selector changed"),
                AIMessage(content="queued with edited reasoning"),
            ]
        )
        conversation = self._create()
        queued = self.client.post(
            f"/v1/chat/conversations/{conversation['id']}/queue",
            json={
                "task": "Queued with original selector.",
                "deployment_id": self.deployment_id,
                "per_request_overrides": {"reasoning_effort": "low"},
            },
        )
        self.assertEqual(queued.status_code, 200, queued.text)
        queue_id = queued.json()["queue"][0]["id"]
        edited = self.client.patch(
            f"/v1/chat/conversations/{conversation['id']}/queue/{queue_id}",
            json={"intended_config": {"per_request_overrides": {"reasoning_effort": "medium"}}},
        )
        self.assertEqual(edited.status_code, 200, edited.text)
        self.assertEqual(edited.json()["queue"][0]["intended_config"]["deployment_id"], self.deployment_id)
        self.assertEqual(
            edited.json()["queue"][0]["intended_config"]["per_request_overrides"],
            {"reasoning_effort": "medium"},
        )

        changed = self.client.post(
            f"/v1/chat/conversations/{conversation['id']}/start",
            json={"task": "Change selector before queued dispatch.", "deployment_id": other["id"]},
        )
        self.assertEqual(changed.status_code, 200, changed.text)
        wait_for_chat(self.client, conversation["id"])

        resumed = self.client.post(f"/v1/chat/conversations/{conversation['id']}/queue/resume", json={})
        self.assertEqual(resumed.status_code, 200, resumed.text)
        self.assertEqual(resumed.json()["current_run"]["deployment_id"], self.deployment_id)
        self.assertEqual(
            resumed.json()["queue"][0]["frozen_config"]["per_request_overrides"],
            {"reasoning_effort": "medium"},
        )

    def test_tools_off_attachment_only_turn_uses_retained_content(self) -> None:
        assets = RetainedAssetService(self.app.state.app_store)
        conversation = self.client.post(
            "/v1/chat/conversations",
            json={"deployment_id": self.deployment_id, "profile_id": self.profile_id},
        ).json()
        asset = assets.retain_upload(
            RetainedUploadRequest(
                session_id=conversation["id"],
                filename="notes.md",
                content_type="text/markdown",
                content_base64=base64.b64encode(b"# Notes\nAttachment text.").decode("ascii"),
            )
        )
        self.scripted = ScriptedChatModel([AIMessage(content="read retained attachment")])

        started = self.client.post(
            f"/v1/chat/conversations/{conversation['id']}/start",
            json={"task": "", "attachment_ids": [asset.id], "presented_tools": []},
        )
        self.assertEqual(started.status_code, 200, started.text)
        self.assertEqual(started.json()["transcript"][0]["attachment_ids"], [asset.id])
        finished = wait_for_chat(self.client, conversation["id"])
        self.assertEqual(finished["current_run"]["presented_tools"], [])
        blocks = finished["current_run"]["content_blocks"]
        self.assertEqual(len(blocks), 1)
        self.assertIn("Source retained file: notes.md", blocks[0]["text"])
        self.assertIn("Attachment text.", blocks[0]["text"])

    def test_queued_attachment_persists_until_resume(self) -> None:
        assets = RetainedAssetService(self.app.state.app_store)
        conversation = self._create()
        asset = assets.retain_upload(
            RetainedUploadRequest(
                session_id=conversation["id"],
                filename="queued.txt",
                content_type="text/plain",
                content_base64=base64.b64encode(b"queued attachment").decode("ascii"),
            )
        )
        self.scripted = ScriptedChatModel([AIMessage(content="queued with attachment")])
        queued = self.client.post(
            f"/v1/chat/conversations/{conversation['id']}/queue",
            json={"task": "Use queued attachment.", "attachment_ids": [asset.id], "presented_tools": []},
        )
        self.assertEqual(queued.status_code, 200, queued.text)
        self.assertEqual(queued.json()["queue"][0]["attachment_ids"], [asset.id])
        fetched = self.client.get(f"/v1/chat/conversations/{conversation['id']}").json()
        self.assertEqual(fetched["run_ids"], [])
        self.assertEqual(fetched["queue"][0]["attachment_ids"], [asset.id])

        resumed = self.client.post(f"/v1/chat/conversations/{conversation['id']}/queue/resume", json={})
        self.assertEqual(resumed.status_code, 200, resumed.text)
        self.assertEqual(resumed.json()["transcript"][0]["attachment_ids"], [asset.id])
        finished = wait_for_chat(self.client, conversation["id"])
        blocks = finished["current_run"]["content_blocks"]
        self.assertEqual(len(blocks), 1)
        self.assertIn("Source retained file: queued.txt", blocks[0]["text"])

    def test_direct_start_recovers_accepted_run_after_commit_gap(self) -> None:
        conversation = self._create()
        draft = self.client.put(
            f"/v1/chat/conversations/{conversation['id']}/draft",
            json={
                "content": "Recover accepted direct run.",
                "intended_config": {"deployment_id": self.deployment_id},
            },
        )
        self.assertEqual(draft.status_code, 200, draft.text)
        draft_revision = draft.json()["draft"]["revision"]
        original_start = self.app.state.harness.start
        accepted: list[str] = []

        def accept_then_raise(request: AgentStartRequest) -> AgentRun:
            run = original_start(request)
            accepted.append(run.id)
            raise HarnessError("synthetic post-accept crash", code="synthetic_gap", status_code=503)

        with patch.object(self.app.state.harness, "start", side_effect=accept_then_raise):
            response = self.client.post(
                f"/v1/chat/conversations/{conversation['id']}/start",
                json={
                    "task": "Recover accepted direct run.",
                    "input_message_id": "direct-gap",
                    "draft_revision": draft_revision,
                },
            )

        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["run_ids"], accepted)
        self.assertEqual(body["current_run_id"], accepted[0])
        user_messages = [message for message in body["transcript"] if message["role"] == "user"]
        self.assertEqual([message["id"] for message in user_messages], ["direct-gap"])
        self.assertEqual(user_messages[0]["run_id"], accepted[0])
        self.assertEqual(body["draft"]["content"], "")
        self.assertEqual(body["draft"]["revision"], draft_revision + 1)

    def test_direct_start_retry_after_model_load_failure_reuses_input_identity(self) -> None:
        conversation = self._create()
        original_ready = self.manager.ensure_deployment_ready
        original_start = self.app.state.harness.start
        attempts = 0
        starts = 0

        def fail_once(deployment_id: str):
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise ManagerError("synthetic load failure", code="deployment_not_ready", status_code=409)
            return original_ready(deployment_id)

        def count_start(request: AgentStartRequest) -> AgentRun:
            nonlocal starts
            run = original_start(request)
            starts += 1
            return run

        with patch.object(self.manager, "ensure_deployment_ready", side_effect=fail_once):
            with patch.object(self.app.state.harness, "start", side_effect=count_start):
                failed = self.client.post(
                    f"/v1/chat/conversations/{conversation['id']}/start",
                    json={"task": "Retry exact input.", "input_message_id": "load-retry-input"},
                )
                self.assertEqual(failed.status_code, 409, failed.text)
                self.assertEqual(failed.json()["code"], "deployment_not_ready")
                after_fail = self.client.get(f"/v1/chat/conversations/{conversation['id']}").json()
                self.assertEqual(after_fail["run_ids"], [])
                self.assertEqual([message["id"] for message in after_fail["transcript"]], ["load-retry-input"])
                self.assertIsNone(after_fail["transcript"][0]["run_id"])

                retried = self.client.post(
                    f"/v1/chat/conversations/{conversation['id']}/start",
                    json={"task": "Retry exact input.", "input_message_id": "load-retry-input"},
                )

        self.assertEqual(retried.status_code, 200, retried.text)
        body = retried.json()
        self.assertGreaterEqual(attempts, 2)
        self.assertEqual(starts, 1)
        self.assertEqual(len(body["run_ids"]), 1)
        self.assertEqual([message["id"] for message in body["transcript"] if message["role"] == "user"], ["load-retry-input"])
        self.assertEqual(body["transcript"][0]["run_id"], body["run_ids"][0])

    def test_direct_start_rejects_changed_request_for_existing_input_identity(self) -> None:
        conversation = self._create()
        with patch.object(
            self.manager,
            "ensure_deployment_ready",
            side_effect=ManagerError("synthetic load failure", code="deployment_not_ready", status_code=409),
        ):
            failed = self.client.post(
                f"/v1/chat/conversations/{conversation['id']}/start",
                json={"task": "Original direct task.", "input_message_id": "direct-conflict"},
            )
        self.assertEqual(failed.status_code, 409, failed.text)
        conflict = self.client.post(
            f"/v1/chat/conversations/{conversation['id']}/start",
            json={"task": "Edited direct task.", "input_message_id": "direct-conflict"},
        )
        self.assertEqual(conflict.status_code, 409, conflict.text)
        self.assertEqual(conflict.json()["code"], "submission_identity_conflict")
        fetched = self.client.get(f"/v1/chat/conversations/{conversation['id']}").json()
        users = [message for message in fetched["transcript"] if message["role"] == "user"]
        self.assertEqual(len(users), 1)
        self.assertEqual(users[0]["content"], "Original direct task.")
        self.assertEqual(fetched["run_ids"], [])

    def test_queue_dispatch_failure_pauses_item_and_preserves_editable_config(self) -> None:
        conversation = self._create()
        queued = self.client.post(
            f"/v1/chat/conversations/{conversation['id']}/queue",
            json={
                "task": "Will fail before admission.",
                "input_message_id": "queue-load-failure",
                "presented_tools": ["echo"],
            },
        )
        self.assertEqual(queued.status_code, 200, queued.text)
        queue_id = queued.json()["queue"][0]["id"]

        with patch.object(
            self.manager,
            "ensure_deployment_ready",
            side_effect=ManagerError("synthetic load failure", code="deployment_not_ready", status_code=409),
        ):
            resumed = self.client.post(f"/v1/chat/conversations/{conversation['id']}/queue/resume", json={})

        self.assertEqual(resumed.status_code, 200, resumed.text)
        body = resumed.json()
        self.assertEqual(body["run_ids"], [])
        self.assertEqual(body["queue"][0]["id"], queue_id)
        self.assertEqual(body["queue"][0]["status"], "paused")
        self.assertEqual(body["queue"][0]["pause_reason"], "failed")
        self.assertEqual(body["queue"][0]["pause_error_code"], "deployment_not_ready")
        self.assertIn("synthetic load failure", body["queue"][0]["pause_error"])
        self.assertEqual(body["queue"][0]["intended_config"]["presented_tools"], ["echo"])
        self.assertEqual(body["transcript"][0]["id"], "queue-load-failure")
        self.assertIsNone(body["transcript"][0]["run_id"])

        edited = self.client.patch(
            f"/v1/chat/conversations/{conversation['id']}/queue/{queue_id}",
            json={"task": "Edited after failure."},
        )
        self.assertEqual(edited.status_code, 200, edited.text)
        self.assertEqual(edited.json()["queue"][0]["task"], "Edited after failure.")

    def test_queue_load_failure_keeps_head_paused_and_later_item_queued(self) -> None:
        conversation = self._create()
        first = self.client.post(
            f"/v1/chat/conversations/{conversation['id']}/queue",
            json={"task": "Load failure head.", "input_message_id": "load-head"},
        )
        self.assertEqual(first.status_code, 200, first.text)
        second = self.client.post(
            f"/v1/chat/conversations/{conversation['id']}/queue",
            json={"task": "Later item.", "input_message_id": "load-second"},
        )
        self.assertEqual(second.status_code, 200, second.text)

        with patch.object(
            self.manager,
            "ensure_deployment_ready",
            side_effect=ManagerError("synthetic load failure", code="deployment_not_ready", status_code=409),
        ):
            resumed = self.client.post(f"/v1/chat/conversations/{conversation['id']}/queue/resume", json={})

        self.assertEqual(resumed.status_code, 200, resumed.text)
        self.assertEqual(resumed.json()["run_ids"], [])
        self.assertEqual([item["status"] for item in resumed.json()["queue"]], ["paused", "queued"])
        self.assertEqual(resumed.json()["queue"][0]["pause_reason"], "failed")
        self.assertEqual(resumed.json()["queue"][0]["pause_error_code"], "deployment_not_ready")

        dispatched = self.app.state.chat.dispatch_idle_queued(conversation["id"])
        self.assertEqual(dispatched, 0)
        after = self.client.get(f"/v1/chat/conversations/{conversation['id']}").json()
        self.assertEqual(after["run_ids"], [])
        self.assertEqual([item["input_message_id"] for item in after["queue"]], ["load-head", "load-second"])

    def test_startup_reconciliation_keeps_accepted_dispatching_run_without_replay(self) -> None:
        hold = threading.Event()
        set_generate_hold(hold)
        self.addCleanup(set_generate_hold, None)
        self.addCleanup(hold.set)
        self.scripted = ScriptedChatModel([AIMessage(content="held queued")])
        conversation = self._create()
        queued = self.client.post(
            f"/v1/chat/conversations/{conversation['id']}/queue",
            json={"task": "Queued live."},
        )
        self.assertEqual(queued.status_code, 200, queued.text)
        resumed = self.client.post(f"/v1/chat/conversations/{conversation['id']}/queue/resume", json={})
        self.assertEqual(resumed.status_code, 200, resumed.text)
        first_run_id = resumed.json()["current_run_id"]
        wait_for_status(self.client, first_run_id, "running")

        reconciled = self.app.state.chat.reconcile_saved_queue_on_startup()
        self.assertEqual(reconciled, 0)
        dispatched = self.app.state.chat.dispatch_idle_queued(conversation["id"])
        self.assertEqual(dispatched, 0)
        fetched = self.client.get(f"/v1/chat/conversations/{conversation['id']}").json()
        self.assertEqual(fetched["current_run_id"], first_run_id)
        self.assertEqual(fetched["run_ids"], [first_run_id])
        self.assertEqual(fetched["queue"][0]["status"], "dispatching")
        self.assertEqual(fetched["queue"][0]["run_id"], first_run_id)
        hold.set()
        wait_for_chat(self.client, conversation["id"])

    def test_startup_reconciliation_recovers_dispatching_run_by_thread_and_input(self) -> None:
        conversation = self._create()
        queued = self.client.post(
            f"/v1/chat/conversations/{conversation['id']}/queue",
            json={"task": "Recover missing run id.", "input_message_id": "queue-recover-input"},
        )
        self.assertEqual(queued.status_code, 200, queued.text)
        stored = self.app.state.app_store.get_conversation(conversation["id"])
        self.assertIsNotNone(stored)
        assert stored is not None
        stored.queue[0].status = "dispatching"
        stored.queue[0].input_message_id = "queue-recover-input"
        stored.transcript.append(
            ChatMessage(
                id="queue-recover-input",
                role="user",
                content="Recover missing run id.",
                at=utc_now(),
            )
        )
        self.app.state.app_store.put_conversation(stored)
        now = utc_now()
        run = AgentRun(
            id="agent_recovered_by_input",
            status=AgentRunStatus.running,
            deployment_id=self.deployment_id,
            task="Recover missing run id.",
            input_message_id="queue-recover-input",
            enabled_tools=["echo", "time_now", "write_todos", "ask_user"],
            presented_tools=[],
            created_at=now,
            updated_at=now,
            source_surface="chat",
            thread_id=stored.thread_id,
        )
        self.app.state.app_store.put_run(run)
        self.app.state.harness._startup_reconciled = True

        reconciled = self.app.state.chat.reconcile_saved_queue_on_startup()

        self.assertEqual(reconciled, 1)
        fetched = self.client.get(f"/v1/chat/conversations/{conversation['id']}").json()
        self.assertEqual(fetched["current_run_id"], run.id)
        self.assertEqual(fetched["run_ids"], [run.id])
        self.assertEqual(fetched["queue"][0]["status"], "dispatching")
        self.assertEqual(fetched["queue"][0]["run_id"], run.id)
        self.assertEqual(fetched["transcript"][0]["run_id"], run.id)

    def test_startup_reconciliation_pauses_uncertain_dispatch_without_replay(self) -> None:
        conversation = self._create()
        queued = self.client.post(
            f"/v1/chat/conversations/{conversation['id']}/queue",
            json={"task": "Uncertain queued."},
        )
        self.assertEqual(queued.status_code, 200, queued.text)
        stored = self.app.state.app_store.get_conversation(conversation["id"])
        self.assertIsNotNone(stored)
        assert stored is not None
        stored.queue[0].status = "dispatching"
        stored.queue[0].run_id = "agent_missing"
        self.app.state.app_store.put_conversation(stored)

        reconciled = self.app.state.chat.reconcile_saved_queue_on_startup()
        self.assertEqual(reconciled, 1)
        fetched = self.client.get(f"/v1/chat/conversations/{conversation['id']}").json()
        self.assertEqual(fetched["run_ids"], [])
        self.assertEqual(fetched["queue"][0]["status"], "paused")
        self.assertEqual(fetched["queue"][0]["pause_reason"], "dispatch_uncertain")
        self.assertEqual(fetched["queue"][0]["pause_error_code"], "dispatch_uncertain")
        self.assertIn("could not confirm", fetched["queue"][0]["pause_error"])

        dispatched = self.app.state.chat.dispatch_idle_queued(conversation["id"])
        self.assertEqual(dispatched, 0)
        after = self.client.get(f"/v1/chat/conversations/{conversation['id']}").json()
        self.assertEqual(after["run_ids"], [])

    def test_uncertain_queue_resume_requires_ack_and_reuses_saved_run(self) -> None:
        conversation = self._create()
        queued = self.client.post(
            f"/v1/chat/conversations/{conversation['id']}/queue",
            json={"task": "Uncertain retry.", "input_message_id": "uncertain-retry"},
        )
        self.assertEqual(queued.status_code, 200, queued.text)
        stored = self.app.state.app_store.get_conversation(conversation["id"])
        self.assertIsNotNone(stored)
        assert stored is not None
        stored.queue[0].status = "paused"
        stored.queue[0].pause_reason = "dispatch_uncertain"
        stored.queue[0].pause_error_code = "dispatch_uncertain"
        stored.queue[0].pause_error = "unknown effects"
        self.app.state.app_store.put_conversation(stored)

        rejected = self.client.post(
            f"/v1/chat/conversations/{conversation['id']}/queue/resume",
            json={"resume_paused": True},
        )
        self.assertEqual(rejected.status_code, 409, rejected.text)
        self.assertEqual(rejected.json()["code"], "queue_uncertain_ack_required")
        self.assertEqual(self.client.get(f"/v1/chat/conversations/{conversation['id']}").json()["run_ids"], [])

        run = AgentRun(
            id="agent_uncertain_reused",
            status=AgentRunStatus.running,
            deployment_id=self.deployment_id,
            task="Uncertain retry.",
            input_message_id="uncertain-retry",
            enabled_tools=["echo", "time_now", "write_todos", "ask_user"],
            presented_tools=[],
            created_at=utc_now(),
            updated_at=utc_now(),
            source_surface="chat",
            thread_id=stored.thread_id,
        )
        self.app.state.app_store.put_run(run)
        self.app.state.harness._startup_reconciled = True
        with patch.object(self.app.state.harness, "start", side_effect=AssertionError("must reuse saved run")):
            accepted = self.client.post(
                f"/v1/chat/conversations/{conversation['id']}/queue/resume",
                json={"resume_paused": True, "acknowledge_uncertain_effects": True},
            )
        self.assertEqual(accepted.status_code, 200, accepted.text)
        self.assertEqual(accepted.json()["run_ids"], [run.id])
        self.assertEqual(accepted.json()["current_run_id"], run.id)
        self.assertEqual(accepted.json()["queue"][0]["run_id"], run.id)
        self.assertEqual(accepted.json()["transcript"][0]["run_id"], run.id)

    def test_enqueue_duplicate_same_input_identity_is_idempotent(self) -> None:
        conversation = self._create()
        payload = {
            "task": "Retry enqueue acknowledgement.",
            "input_message_id": "queue-idempotent",
            "presented_tools": ["echo"],
        }
        first = self.client.post(f"/v1/chat/conversations/{conversation['id']}/queue", json=payload)
        self.assertEqual(first.status_code, 200, first.text)
        second = self.client.post(f"/v1/chat/conversations/{conversation['id']}/queue", json=payload)
        self.assertEqual(second.status_code, 200, second.text)
        self.assertEqual(len(second.json()["queue"]), 1)
        self.assertEqual(second.json()["queue"][0]["id"], first.json()["queue"][0]["id"])
        changed = self.client.post(
            f"/v1/chat/conversations/{conversation['id']}/queue",
            json={**payload, "task": "Changed content same identity."},
        )
        self.assertEqual(changed.status_code, 409, changed.text)
        self.assertEqual(changed.json()["code"], "submission_identity_conflict")
        fetched = self.client.get(f"/v1/chat/conversations/{conversation['id']}").json()
        self.assertEqual(len(fetched["queue"]), 1)

    def test_paused_head_blocks_later_queued_dispatch(self) -> None:
        conversation = self._create()
        first = self.client.post(
            f"/v1/chat/conversations/{conversation['id']}/queue",
            json={"task": "Paused head."},
        )
        self.assertEqual(first.status_code, 200, first.text)
        first_id = first.json()["queue"][0]["id"]
        second = self.client.post(
            f"/v1/chat/conversations/{conversation['id']}/queue",
            json={"task": "Later queued."},
        )
        self.assertEqual(second.status_code, 200, second.text)
        stored = self.app.state.app_store.get_conversation(conversation["id"])
        self.assertIsNotNone(stored)
        assert stored is not None
        stored.queue[0].status = "paused"
        stored.queue[0].pause_reason = "dispatch_uncertain"
        self.app.state.app_store.put_conversation(stored)

        dispatched = self.app.state.chat.dispatch_idle_queued(conversation["id"])

        self.assertEqual(dispatched, 0)
        fetched = self.client.get(f"/v1/chat/conversations/{conversation['id']}").json()
        self.assertEqual(fetched["run_ids"], [])
        self.assertEqual([item["id"] for item in fetched["queue"]], [first_id, second.json()["queue"][1]["id"]])
        self.assertEqual(fetched["queue"][0]["status"], "paused")
        self.assertEqual(fetched["queue"][1]["status"], "queued")

    def test_app_lifespan_reconciles_terminal_queue_head_before_dispatching_next(self) -> None:
        conversation = self._create()
        first = self.client.post(
            f"/v1/chat/conversations/{conversation['id']}/queue",
            json={"task": "Already completed.", "input_message_id": "startup-head"},
        )
        self.assertEqual(first.status_code, 200, first.text)
        second = self.client.post(
            f"/v1/chat/conversations/{conversation['id']}/queue",
            json={"task": "Dispatch after startup reconciliation.", "input_message_id": "startup-next"},
        )
        self.assertEqual(second.status_code, 200, second.text)
        stored = self.app.state.app_store.get_conversation(conversation["id"])
        self.assertIsNotNone(stored)
        assert stored is not None
        first_run = AgentRun(
            id="agent_startup_completed_head",
            status=AgentRunStatus.completed,
            deployment_id=self.deployment_id,
            task="Already completed.",
            input_message_id="startup-head",
            enabled_tools=["echo", "time_now", "write_todos", "ask_user"],
            presented_tools=[],
            created_at=utc_now(),
            updated_at=utc_now(),
            finished_at=utc_now(),
            source_surface="chat",
            thread_id=stored.thread_id,
        )
        stored.current_run_id = first_run.id
        stored.run_ids = [first_run.id]
        stored.queue[0].status = "dispatching"
        stored.queue[0].run_id = first_run.id
        stored.transcript.append(ChatMessage(id="startup-head", role="user", content="Already completed.", at=utc_now(), run_id=first_run.id))
        self.app.state.app_store.put_run(first_run)
        self.app.state.app_store.put_conversation(stored)

        restarted = create_app(data_root=self.root)
        restarted_scripted = ScriptedChatModel([AIMessage(content="started second")])
        restarted.state.harness = HarnessService(
            lambda: restarted.state.manager,
            model_factory=lambda _run, _sink: restarted_scripted,
            knowledge_provider=lambda: restarted.state.knowledge,
            app_store=restarted.state.app_store,
        )

        pre_client = offline_workbench_client(restarted)
        try:
            pre_get = pre_client.get(f"/v1/chat/conversations/{conversation['id']}")
            self.assertEqual(pre_get.status_code, 200, pre_get.text)
            self.assertEqual(pre_get.json()["run_ids"], [first_run.id])
            self.assertEqual([item["status"] for item in pre_get.json()["queue"]], ["dispatching", "queued"])
        finally:
            pre_client.close()

        with offline_workbench_client(restarted) as live_client:
            deadline = time.time() + 10
            body: dict[str, Any] = {}
            while time.time() < deadline:
                body = live_client.get(f"/v1/chat/conversations/{conversation['id']}").json()
                if len(body.get("run_ids", [])) == 2:
                    break
                time.sleep(0.05)
            self.assertEqual(len(body.get("run_ids", [])), 2, body)
            self.assertEqual(body["run_ids"][0], first_run.id)
            self.assertEqual(body["transcript"][0]["run_id"], first_run.id)
            self.assertEqual(body["transcript"][1]["id"], "startup-next")
            self.assertEqual(body["transcript"][1]["run_id"], body["run_ids"][1])
            self.assertEqual(body["queue"][0]["status"], "dispatching")
            self.assertEqual(body["queue"][0]["run_id"], body["run_ids"][1])
        close_workbench_sqlite(restarted)


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
