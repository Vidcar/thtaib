"""Conversation deletion crosses durable and live owner boundaries together."""
from pathlib import Path
from types import SimpleNamespace
import tempfile
import threading
import unittest
from unittest.mock import patch

from langgraph.checkpoint.base import empty_checkpoint

from tests.support import close_workbench_sqlite, offline_workbench_client
from workbench_backend.agents.schemas import AgentRun
from workbench_backend.app import create_app
from workbench_backend.chat.schemas import ChatConversation, ChatMessage
from workbench_backend.inference.ids import utc_now
from workbench_backend.state.checkpointer import open_sqlite_checkpointer
from workbench_backend.state.schemas import ExternalEffect


class ChatDeletionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.app = create_app(data_root=self.root)
        self.client = offline_workbench_client(self.app)
        self.store = self.app.state.app_store
        self.run = AgentRun(id="run_delete", status="completed", deployment_id="dep", task="private history",
            thread_id="thread_delete", enabled_tools=[], presented_tools=[], created_at=utc_now(), updated_at=utc_now())
        self.store.put_run(self.run)
        self.chat = ChatConversation(id="chat_delete", deployment_id="dep", thread_id=self.run.thread_id,
            run_ids=[self.run.id], current_run_id=self.run.id,
            transcript=[ChatMessage(role="user", content="private history", at=utc_now())],
            created_at=utc_now(), updated_at=utc_now())
        self.store.put_conversation(self.chat)
        # Exercise the cache through its public owner, exactly as the UI does.
        self.app.state.harness.get_run(self.run.id)

    def tearDown(self):
        close_workbench_sqlite(self.app, self.client)
        self.tmp.cleanup()

    def delete(self):
        return self.client.request("DELETE", f"/v1/chat/conversations/{self.chat.id}", json={"execute": True})

    def test_delete_removes_history_from_all_live_apis_and_restart_without_touching_project(self):
        project = self.root / "project"
        project.mkdir()
        output = project / "generated.txt"
        output.write_bytes(b"the user's generated project output\r\n")
        before = output.read_bytes()
        self.chat.project_path = self.chat.area_project_path = str(project)
        self.chat.area_kind = "project"
        self.store.put_conversation(self.chat)
        self.store.register_interaction(self.chat.id, "chat", self.run.thread_id, self.chat.id,
            {"messages": [{"type": "human", "content": "private history"}]})
        self.store.append_interaction(self.chat.id, [{"event": "values", "data": {"content": "private history"}}])
        saver = open_sqlite_checkpointer(self.app.state.manager.paths.checkpoints_db)
        config = {"configurable": {"thread_id": self.run.thread_id, "checkpoint_ns": ""}}
        saver.put(config, empty_checkpoint(), {"source": "test", "step": 0, "writes": {}, "parents": {}}, {})
        session_grant = self.app.state.preferences.allow(self.run,
            SimpleNamespace(name="write_file", args={"content": "private history"}), "session")
        permanent_grant = self.app.state.preferences.allow(self.run,
            SimpleNamespace(name="write_file", args={"path": "/approved"}), "always")
        self.store.put_effect(ExternalEffect(id="effect_delete", run_id=self.run.id, operation="write_file",
            payload={"content": "private history"}, dispatched_at=utc_now()))

        response = self.delete()

        self.assertEqual(response.status_code, 200, response.text)
        self.assertTrue(response.json()["diagnostics_deleted"])
        self.assertEqual(output.read_bytes(), before)
        self.assertEqual(list(saver.list(config)), [])
        self.assertEqual(self.store.interaction_events_after(self.chat.id, 0), [])
        self.assertIsNone(self.store.get_effect("effect_delete"))
        grants = {grant.id for grant in self.app.state.preferences.grants()}
        self.assertNotIn(session_grant.id, grants)
        self.assertIn(permanent_grant.id, grants)
        self.assert_deleted_apis()
        close_workbench_sqlite(self.app, self.client)
        self.app = create_app(data_root=self.root)
        self.client = offline_workbench_client(self.app)
        self.assert_deleted_apis()
        self.assertEqual(output.read_bytes(), before)

    def assert_deleted_apis(self):
        for url in (f"/v1/chat/conversations/{self.chat.id}", f"/v1/agent-runs/{self.run.id}",
                    f"/v1/agent-interaction/threads/{self.chat.id}/state"):
            self.assertEqual(self.client.get(url).status_code, 404, url)
        self.assertFalse(any(run["id"] == self.run.id for run in self.client.get("/v1/agent-runs").json()))
        registration = self.client.post("/v1/agent-interaction/threads",
            json={"source_surface": "agent", "run_id": self.run.id})
        self.assertEqual(registration.status_code, 404, registration.text)
        late_draft = self.client.put(f"/v1/chat/conversations/{self.chat.id}/draft", json={"content": "late old draft"})
        self.assertEqual(late_draft.status_code, 404, late_draft.text)

    def test_terminal_worker_still_finishing_blocks_before_any_deletion(self):
        release = threading.Event()
        entered = threading.Event()
        def finishing():
            entered.set()
            release.wait(timeout=10)
        worker = threading.Thread(target=finishing)
        self.app.state.harness._threads[self.run.id] = worker
        worker.start()
        try:
            self.assertTrue(entered.wait(timeout=2))
            response = self.delete()
            self.assertEqual(response.status_code, 409, response.text)
            self.assertIsNotNone(self.store.get_conversation(self.chat.id))
            self.assertIsNotNone(self.store.get_run(self.run.id))
            self.assertEqual(self.app.state.harness.get_run(self.run.id).task, "private history")
        finally:
            release.set()
            worker.join(timeout=2)
        self.assertEqual(self.delete().status_code, 200)
        self.assert_deleted_apis()

    def test_surviving_branch_keeps_shared_run_and_its_session_grant(self):
        branch = self.chat.model_copy(update={"id": "chat_branch", "source_conversation_id": self.chat.id})
        self.store.put_conversation(branch)
        grant = self.app.state.preferences.allow(self.run, SimpleNamespace(name="read_file", args={"path": "/shared"}), "session")
        response = self.delete()
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["retained_runs"], [self.run.id])
        self.assertEqual(self.client.get(f"/v1/agent-runs/{self.run.id}").status_code, 200)
        self.assertIn(grant.id, {item.id for item in self.app.state.preferences.grants()})

    def test_agent_surface_projection_of_chat_run_is_deleted_with_its_execution_thread(self):
        response = self.client.post("/v1/agent-interaction/threads", json={"source_surface": "agent", "run_id": self.run.id})
        self.assertEqual(response.status_code, 200, response.text)
        interaction_id = response.json()["thread_id"]
        self.assertIsNone(self.store.get_interaction(interaction_id)["conversation_id"])
        self.assertEqual(self.delete().status_code, 200)
        self.assertEqual(self.client.get(f"/v1/agent-interaction/threads/{interaction_id}/state").status_code, 404)
        self.assertEqual(self.store.interaction_events_after(interaction_id, 0), [])

    def test_chat_registration_cannot_recreate_history_after_delete(self):
        self.assert_registration_and_delete_are_serialized({"source_surface": "chat", "conversation_id": self.chat.id})

    def test_agent_registration_cannot_recreate_history_after_delete(self):
        self.assert_registration_and_delete_are_serialized({"source_surface": "agent", "run_id": self.run.id})

    def assert_registration_and_delete_are_serialized(self, body):
        entered, release, deletion_started, deletion_finished = (threading.Event() for _ in range(4))
        original = self.store.register_interaction
        responses = {}
        def held_registration(*args, **kwargs):
            entered.set()
            if not release.wait(timeout=3):
                raise TimeoutError("registration fixture not released")
            return original(*args, **kwargs)
        def register():
            responses["registration"] = self.client.post("/v1/agent-interaction/threads", json=body)
        def delete():
            deletion_started.set()
            responses["deletion"] = self.delete()
            deletion_finished.set()
        registration = threading.Thread(target=register)
        deletion = threading.Thread(target=delete)
        with patch.object(self.store, "register_interaction", side_effect=held_registration):
            registration.start()
            try:
                self.assertTrue(entered.wait(timeout=2))
                deletion.start()
                self.assertTrue(deletion_started.wait(timeout=2))
                self.assertFalse(deletion_finished.wait(timeout=0.05), "deletion must wait for the admitted registration")
            finally:
                release.set()
                registration.join(timeout=3)
                if deletion.ident is not None:
                    deletion.join(timeout=3)
        self.assertFalse(registration.is_alive())
        self.assertFalse(deletion.is_alive())
        self.assertEqual(responses["registration"].status_code, 200, responses["registration"].text)
        self.assertEqual(responses["deletion"].status_code, 200, responses["deletion"].text)
        interaction_id = responses["registration"].json()["thread_id"]
        self.assertIsNone(self.store.get_interaction(interaction_id))
        self.assertIsNone(self.store.interaction_for_graph(self.run.thread_id))
        self.assert_deleted_apis()


if __name__ == "__main__":
    unittest.main()
