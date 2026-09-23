"""Chat access changes must match the setup shown and preserve real tool gates."""

import tempfile
import time
import unittest
from pathlib import Path

from langchain_core.messages import AIMessage

from workbench_backend.agents.harness import HarnessService
from workbench_backend.agents.setup_schemas import SetupConfiguration
from workbench_backend.app import create_app
from workbench_backend.inference.schemas import ConnectedDeploymentRequest
from tests.scripted_model import RECEIVED_PROMPTS, ScriptedChatModel, reset_received_prompts
from tests.support import close_workbench_sqlite, offline_workbench_client
from tests.test_chat import host_shell_marker_command, wait_for_chat


class ChatAccessTests(unittest.TestCase):
    def setUp(self):
        reset_received_prompts()
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.project = self.root / "project"
        self.project.mkdir()
        self.app = create_app(data_root=self.root / "data")
        self.client = offline_workbench_client(self.app)
        self.deployment = self.app.state.manager.attach_connected(ConnectedDeploymentRequest(
            display_name="Access fixture", endpoint="http://127.0.0.1:9/v1"))
        self.script = [AIMessage(content="done")]
        self.app.state.harness = HarnessService(
            lambda: self.app.state.manager, app_store=self.app.state.app_store,
            knowledge_provider=lambda: self.app.state.knowledge,
            model_factory=lambda *_: ScriptedChatModel(self.script),
        )

    def tearDown(self):
        close_workbench_sqlite(self.app, self.client)
        self.tmp.cleanup()

    def post(self, path, body):
        response = self.client.post(path, json=body)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def setup(self, **configuration):
        return self.post("/v1/agent-setups", {"name": "Access fixture", "configuration": {
            "deployment_id": self.deployment.id, **configuration}})

    def settled(self, conversation_id):
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            body = self.client.get(f"/v1/chat/conversations/{conversation_id}").json()
            run = body["current_run"]
            if run.get("pending_interrupt") or run["status"] in {"completed", "failed", "cancelled"}:
                return body
            time.sleep(0.02)
        self.fail("Chat did not reach a decision or finish")

    def test_switching_away_from_full_access_uses_resolved_ask_and_blocks_rename(self):
        full = self.setup(approval_mode="full_access", presented_tools=["rename_file"])
        ordinary = self.setup(presented_tools=["rename_file"])
        for replacement in (ordinary["current_version_id"], None):
            with self.subTest(replacement=replacement):
                source = self.project / f"source-{replacement or 'none'}.txt"
                destination = source.with_name(f"renamed-{source.name}")
                source.write_text("keep until approved", encoding="utf-8")
                self.script = [AIMessage(content="", tool_calls=[{
                    "name": "rename_file", "id": "rename-test",
                    "args": {"file_path": source.name, "destination": destination.name},
                }]), AIMessage(content="done")]
                chat = self.post("/v1/chat/conversations", {
                    "project_path": str(self.project), "agent_setup_version_id": full["current_version_id"],
                })
                self.assertEqual(chat["approval_mode"], "full_access")
                resolved = self.post("/v1/setup-resolution", {
                    "project_id": chat["project_id"], "agent_setup_version_id": replacement,
                })
                self.assertIsNone(resolved["configuration"]["approval_mode"])
                self.post(f"/v1/chat/conversations/{chat['id']}/start", {
                    "task": "Rename this file.", "agent_setup_version_id": replacement,
                    "deployment_id": self.deployment.id, "presented_tools": ["rename_file"],
                })
                settled = self.settled(chat["id"])
                self.assertTrue(source.exists(), "A rename ran while the resolved setup showed Ask")
                self.assertFalse(destination.exists())
                self.assertEqual(settled["approval_mode"], "ask")
                self.assertEqual(settled["current_run"]["approval_mode"], "ask")
                self.assertIsNotNone(settled["current_run"]["pending_interrupt"])
                self.post(f"/v1/chat/conversations/{chat['id']}/cancel", {})
                wait_for_chat(self.client, chat["id"])

    def test_general_chat_access_override_survives_later_application_defaults(self):
        chat = self.post("/v1/chat/conversations", {
            "deployment_id": self.deployment.id, "approval_mode": "full_access", "presented_tools": [],
        })
        self.post(f"/v1/chat/conversations/{chat['id']}/start", {"task": "hello", "approval_mode": "ask"})
        first = wait_for_chat(self.client, chat["id"])
        self.assertEqual(first["current_run"]["approval_mode"], "ask")
        self.app.state.app_store.put_setup_defaults(SetupConfiguration(instructions="Be brief."))
        reset_received_prompts()
        self.post(f"/v1/chat/conversations/{chat['id']}/start", {"task": "continue"})
        second = wait_for_chat(self.client, chat["id"])
        self.assertEqual(second["current_run"]["approval_mode"], "ask")
        saved = self.app.state.app_store.get_conversation(chat["id"])
        self.assertEqual(saved.setup_overrides.approval_mode, "ask")
        self.assertTrue(RECEIVED_PROMPTS)
        self.assertTrue(all("Access for this turn: Ask." in prompt for prompt in RECEIVED_PROMPTS))
        self.assertTrue(all("Access for this turn: Full access." not in prompt for prompt in RECEIVED_PROMPTS))

    def test_queued_ask_retains_its_pause_after_project_changes_to_full_access(self):
        source = self.project / "queued.txt"
        source.write_text("queued original", encoding="utf-8")
        self.script = [AIMessage(content="", tool_calls=[{
            "name": "rename_file", "id": "queued-rename",
            "args": {"file_path": "queued.txt", "destination": "renamed.txt"},
        }]), AIMessage(content="done")]
        chat = self.post("/v1/chat/conversations", {
            "project_path": str(self.project), "deployment_id": self.deployment.id,
            "presented_tools": ["rename_file"],
        })
        queued = self.post(f"/v1/chat/conversations/{chat['id']}/queue", {"task": "Rename it later."})
        self.assertEqual(queued["queue"][0]["intended_config"]["approval_mode"], "ask")
        updated = self.client.patch(f"/v1/projects/{chat['project_id']}", json={
            "defaults": {"approval_mode": "full_access"},
        })
        self.assertEqual(updated.status_code, 200, updated.text)
        self.post(f"/v1/chat/conversations/{chat['id']}/queue/resume", {})
        paused = self.settled(chat["id"])
        self.assertEqual(paused["current_run"]["approval_mode"], "ask")
        self.assertIsNotNone(paused["current_run"]["pending_interrupt"])
        self.assertTrue(source.exists())
        self.assertFalse((self.project / "renamed.txt").exists())
        self.post(f"/v1/chat/conversations/{chat['id']}/cancel", {})
        wait_for_chat(self.client, chat["id"])

    def test_full_access_keeps_selected_questions_and_disabled_mutation_boundaries(self):
        self.script = [AIMessage(content="", tool_calls=[{
            "name": "ask_user", "id": "question",
            "args": {"prompt": "Which format?", "answer_type": "text"},
        }]), AIMessage(content="done")]
        chat = self.post("/v1/chat/conversations", {
            "deployment_id": self.deployment.id, "approval_mode": "full_access",
            "presented_tools": ["ask_user"],
        })
        self.post(f"/v1/chat/conversations/{chat['id']}/start", {"task": "Ask for format."})
        paused = self.settled(chat["id"])
        self.assertEqual(paused["current_run"]["pending_interrupt"]["kind"], "ask_user")
        self.post(f"/v1/chat/conversations/{chat['id']}/cancel", {})
        wait_for_chat(self.client, chat["id"])

        source = self.project / "disabled.txt"
        source.write_text("keep", encoding="utf-8")
        self.script = [AIMessage(content="", tool_calls=[{
            "name": "delete_file", "id": "disabled-delete", "args": {"file_path": "disabled.txt"},
        }]), AIMessage(content="done")]
        tools_off = self.post("/v1/chat/conversations", {
            "deployment_id": self.deployment.id, "project_path": str(self.project),
            "approval_mode": "full_access", "presented_tools": [],
        })
        self.post(f"/v1/chat/conversations/{tools_off['id']}/start", {"task": "Reply without tools."})
        completed = wait_for_chat(self.client, tools_off["id"])
        self.assertEqual(completed["current_run"]["presented_tools"], [])
        self.assertTrue(source.exists())

    def test_shell_access_and_model_instructions_follow_the_same_turn_mode(self):
        for mode, label in (("ask", "Ask"), ("approve_for_me", "Approve for me"), ("full_access", "Full access")):
            with self.subTest(mode=mode):
                reset_received_prompts()
                filename = f"shell-{mode}.txt"
                self.script = [AIMessage(content="", tool_calls=[{
                    "name": "execute", "id": "shell-access",
                    "args": {"command": host_shell_marker_command(filename)},
                }]), AIMessage(content="done")]
                chat = self.post("/v1/chat/conversations", {
                    "deployment_id": self.deployment.id, "project_path": str(self.project),
                    "approval_mode": mode, "presented_tools": ["execute"],
                })
                self.post(f"/v1/chat/conversations/{chat['id']}/start", {"task": "Create the marker."})
                settled = self.settled(chat["id"])
                run = settled["current_run"]
                if mode == "full_access":
                    self.assertEqual(run["status"], "completed", run.get("error"))
                    self.assertTrue((self.project / filename).exists())
                    self.assertIsNone(run["pending_interrupt"])
                else:
                    self.assertIsNotNone(run["pending_interrupt"])
                    self.assertFalse((self.project / filename).exists())
                    self.post(f"/v1/chat/conversations/{chat['id']}/cancel", {})
                    wait_for_chat(self.client, chat["id"])
                prompt = run["effective_setup"]["system_prompt"]
                self.assertIn(f"Access for this turn: {label}.", prompt)
                self.assertIn("Questions still require the person's answer", prompt)
                self.assertNotIn("dangerous commands pause for approval", prompt)
                self.assertTrue(RECEIVED_PROMPTS)
                self.assertTrue(all(f"Access for this turn: {label}." in received for received in RECEIVED_PROMPTS))

    def test_queued_full_access_is_frozen_when_project_default_changes_to_ask(self):
        filename = "queued-full.txt"
        self.script = [AIMessage(content="", tool_calls=[{
            "name": "execute", "id": "queued-full", "args": {"command": host_shell_marker_command(filename)},
        }]), AIMessage(content="done")]
        project = self.post("/v1/projects", {
            "path": str(self.project), "defaults": {"approval_mode": "full_access"},
        })
        chat = self.post("/v1/chat/conversations", {
            "deployment_id": self.deployment.id, "project_id": project["id"], "presented_tools": ["execute"],
        })
        queued = self.post(f"/v1/chat/conversations/{chat['id']}/queue", {"task": "Create a marker later."})
        self.assertEqual(queued["queue"][0]["intended_config"]["approval_mode"], "full_access")
        changed = self.client.patch(f"/v1/projects/{project['id']}", json={"defaults": {"approval_mode": "ask"}})
        self.assertEqual(changed.status_code, 200, changed.text)
        self.post(f"/v1/chat/conversations/{chat['id']}/queue/resume", {})
        completed = wait_for_chat(self.client, chat["id"])
        self.assertEqual(completed["current_run"]["status"], "completed", completed["current_run"].get("error"))
        self.assertEqual(completed["current_run"]["approval_mode"], "full_access")
        self.assertTrue((self.project / filename).exists())
