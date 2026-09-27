"""Durable admission snapshots, authored saves, queue edits and inert shortcuts."""

import base64
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException
from langchain_core.messages import AIMessage
from workbench_backend.app import create_app
from workbench_backend.agents.helpers import freeze_helpers
from workbench_backend.agents.harness import HarnessService
from workbench_backend.assets.schemas import RetainedUploadRequest
from workbench_backend.chat.schemas import ChatQueueItemUpdateRequest, ChatStartRequest
from workbench_backend.errors import ChatError, KnowledgeError
from workbench_backend.inference.schemas import ConnectedDeploymentRequest, ProfileWriteRequest
from workbench_backend.knowledge.schemas import KnowledgeEditRequest, KnowledgeLifecycleRequest
from tests.scripted_model import ScriptedChatModel
from tests.support import close_workbench_sqlite, offline_workbench_client
from tests.test_chat import wait_for_chat


class ChatAdmissionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.app = create_app(data_root=Path(self.tmp.name) / "data")
        self.client = offline_workbench_client(self.app)
        self.chat = self.app.state.chat
        self.knowledge = self.app.state.knowledge
        self.deployment = self.app.state.manager.attach_connected(ConnectedDeploymentRequest(
            display_name="Offline fixture", endpoint="http://127.0.0.1:9/v1"))
        self.memory = self.post("/v1/knowledge/entries", {
            "scope": "user", "kind": "memory", "content": "Original memory"})
        self.agent = self.post("/v1/agent-setups", {"name": "Selected agent", "configuration": {
            "instructions": "Original instructions", "presented_tools": [],
            "memory_entry_ids": [self.memory["id"]]}})
        self.conversation = self.post("/v1/chat/conversations", {
            "deployment_id": self.deployment.id, "agent_setup_id": self.agent["id"]})

    def tearDown(self):
        close_workbench_sqlite(self.app, self.client)
        self.tmp.cleanup()

    def post(self, path, body):
        response = self.client.post(path, json=body)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def request(self, ident, **changes):
        return ChatStartRequest(task="Explain this", input_message_id=ident, **changes)

    def enqueue(self, request):
        view = self.chat.enqueue(self.conversation["id"], request)
        return view.queue[-1]

    def save_memory(self, content="Saved memory"):
        self.memory = self.knowledge.edit(self.memory["id"], KnowledgeEditRequest(
            content=content, base_version=self.memory["current_version_id"])).model_dump(mode="json")
        return self.memory

    def save_agent(self):
        response = self.client.patch(f'/v1/agent-setups/{self.agent["id"]}', json={
            "name": "Saved agent", "base_version": self.agent["current_version_id"],
            "configuration": {"instructions": "Saved instructions", "presented_tools": [],
                "memory_entry_ids": [self.memory["id"]]}})
        self.assertEqual(response.status_code, 200, response.text)
        self.agent = response.json()

    def test_each_new_input_resolves_latest_saved_records_without_execution(self):
        with patch.object(self.chat.harness, "start", side_effect=AssertionError("Queue must not execute")), \
            patch.object(self.app.state.manager, "ensure_deployment_ready", side_effect=AssertionError("Admission must stay cold")):
            first = self.enqueue(self.request("first"))
            self.save_memory()
            self.save_agent()
            second = self.enqueue(self.request("second"))
        self.assertEqual(first.execution_snapshot.selection.agent_setup_version_id,
            self.conversation["agent_setup_version_id"])
        self.assertEqual(first.execution_snapshot.selection.configuration.memory_version_refs,
            [first.execution_snapshot.intended_config["memory_version_refs"][0]])
        self.assertNotEqual(first.execution_snapshot.selection.configuration.memory_version_refs,
            [self.memory["current_version_id"]])
        self.assertEqual(second.execution_snapshot.selection.agent_setup_version_id, self.agent["current_version_id"])
        self.assertEqual(second.execution_snapshot.selection.configuration.memory_version_refs, [self.memory["current_version_id"]])
        self.assertEqual(second.execution_snapshot.selection.configuration.presented_tools, [])
        self.assertEqual(self.chat.get(self.conversation["id"]).transcript, [])

    def test_identical_retry_retains_snapshot_after_save_and_disable(self):
        request = self.request("retry")
        accepted = self.enqueue(request)
        self.save_memory()
        self.save_agent()
        self.knowledge.update_lifecycle(self.memory["id"], KnowledgeLifecycleRequest(enabled=False))
        repeated = self.chat.enqueue(self.conversation["id"], request)
        self.assertEqual(len(repeated.queue), 1)
        self.assertEqual(repeated.queue[0].execution_snapshot, accepted.execution_snapshot)
        refs = accepted.execution_snapshot.selection.configuration.memory_version_refs
        self.assertEqual(self.knowledge.resolve_refs(memory_version_refs=refs, frozen=True).memory_version_refs, refs)
        with self.assertRaises(KnowledgeError):
            self.knowledge.resolve_refs(memory_version_refs=refs)
        with self.assertRaises(ChatError) as conflict:
            self.chat.enqueue(self.conversation["id"], request.model_copy(update={"task": "Different"}))
        self.assertEqual(conflict.exception.code, "submission_identity_conflict")
        with self.assertRaises(KnowledgeError):
            self.enqueue(self.request("new-after-disable"))
        self.assertEqual(len(self.chat.get(self.conversation["id"]).queue), 1)

    def test_identical_queued_retry_uses_accepted_snapshot_after_asset_removal(self):
        asset = self.chat.assets.retain_upload(RetainedUploadRequest(
            session_id=self.conversation["id"], filename="retained.md", content_type="text/markdown",
            content_base64=base64.b64encode(b"Retained for accepted input").decode("ascii")))
        request = self.request("retained-retry", attachment_ids=[asset.id])
        accepted = self.enqueue(request)
        self.chat.assets.store.mark_deleted(asset.id, "2026-09-27T00:00:00+00:00")

        retry = self.chat.enqueue(self.conversation["id"], request)
        self.assertEqual(len(retry.queue), 1)
        self.assertEqual(retry.queue[0].execution_snapshot, accepted.execution_snapshot)
        with self.assertRaises(HTTPException) as unavailable:
            self.enqueue(self.request("new-with-deleted-asset", attachment_ids=[asset.id]))
        self.assertEqual(unavailable.exception.status_code, 410)

    def test_save_waits_for_whole_admission_snapshot(self):
        entered = threading.Event()
        release = threading.Event()
        save_entered = threading.Event()
        save_done = threading.Event()
        original = self.knowledge.resolve_entry_refs
        old_version = self.memory["current_version_id"]

        def blocked_resolution(**kwargs):
            entered.set()
            if not release.wait(5):
                raise AssertionError("Admission release was not signalled")
            return original(**kwargs)

        def save():
            save_entered.set()
            try:
                return self.save_memory()
            finally:
                save_done.set()

        with ThreadPoolExecutor(max_workers=2) as executor:
            try:
                with patch.object(self.knowledge, "resolve_entry_refs", blocked_resolution):
                    admitted_future = executor.submit(self.enqueue, self.request("atomic"))
                    self.assertTrue(entered.wait(5), "Admission did not enter resolution")
                    saved_future = executor.submit(save)
                    self.assertTrue(save_entered.wait(5), "Save did not start")
                    self.assertFalse(save_done.is_set(), "Save crossed the admission boundary")
                    release.set()
                    admitted = admitted_future.result(timeout=5)
                    saved_future.result(timeout=5)
            finally:
                release.set()
        self.assertEqual(admitted.execution_snapshot.selection.configuration.memory_version_refs, [old_version])
        latest = self.enqueue(self.request("after-atomic-save"))
        self.assertEqual(latest.execution_snapshot.selection.configuration.memory_version_refs, [self.memory["current_version_id"]])

    def test_queue_text_edit_preserves_snapshot_and_setup_edit_refreezes_with_revision(self):
        original_request = self.request("edit")
        first = self.enqueue(original_request)
        original_snapshot = first.execution_snapshot
        self.save_memory()
        self.save_agent()
        text = self.chat.update_queue_item(self.conversation["id"], first.id,
            ChatQueueItemUpdateRequest(expected_revision=0, task="Revised message")).queue[0]
        self.assertEqual(text.revision, 1)
        self.assertEqual(text.execution_snapshot.selection, original_snapshot.selection)
        self.assertEqual(text.execution_snapshot.settings, original_snapshot.settings)
        with self.assertRaises(ChatError) as stale:
            self.chat.update_queue_item(self.conversation["id"], first.id,
                ChatQueueItemUpdateRequest(expected_revision=0, task="Stale overwrite"))
        self.assertEqual(stale.exception.code, "queue_revision_conflict")
        with self.assertRaises(ChatError) as obsolete:
            self.chat.enqueue(self.conversation["id"], original_request)
        self.assertEqual(obsolete.exception.code, "submission_identity_conflict")
        reconstructed = self.chat._request_from_queue_item(text)
        retried = self.chat.enqueue(self.conversation["id"], reconstructed).queue[0]
        self.assertEqual(retried.revision, 1)
        self.assertEqual(retried.execution_snapshot.selection, original_snapshot.selection)
        changed = self.chat.update_queue_item(self.conversation["id"], first.id,
            ChatQueueItemUpdateRequest(expected_revision=1, intended_config={"agent_setup_id": self.agent["id"]})).queue[0]
        self.assertEqual(changed.revision, 2)
        self.assertEqual(changed.execution_snapshot.selection.agent_setup_version_id, self.agent["current_version_id"])
        self.assertEqual(changed.execution_snapshot.selection.configuration.memory_version_refs, [self.memory["current_version_id"]])
        self.knowledge.update_lifecycle(self.memory["id"], KnowledgeLifecycleRequest(enabled=False))
        latest_request = self.chat._request_from_queue_item(changed)
        latest_retry = self.chat.enqueue(self.conversation["id"], latest_request)
        self.assertEqual(len(latest_retry.queue), 1)
        self.assertEqual(latest_retry.queue[0].execution_snapshot, changed.execution_snapshot)

    def test_shortcut_prompts_are_inert_copied_and_frozen_for_retries(self):
        original = {"id": "fixture", "version": "1", "name": "Fixture", "description": "Test", "prompt": "Original inert prompt"}
        request = self.request("shortcut", shortcut_ids=["fixture", "fixture"])
        with patch("workbench_backend.chat.shortcuts.SHORTCUTS", (original,)), \
            patch.object(self.chat.harness, "start", side_effect=AssertionError("A shortcut cannot execute")), \
            patch.object(self.app.state.manager, "ensure_deployment_ready", side_effect=AssertionError("A shortcut cannot warm a model")):
            admitted = self.enqueue(request)
            original["prompt"] = "Mutated catalogue prompt"
            original["version"] = "2"
            repeated = self.chat.enqueue(self.conversation["id"], request).queue[0]
            next_input = self.enqueue(self.request("next-shortcut", shortcut_ids=["fixture"]))
        self.assertEqual(admitted.execution_snapshot.shortcuts[0]["prompt"], "Original inert prompt")
        self.assertEqual(len(admitted.execution_snapshot.shortcuts), 1)
        self.assertEqual(repeated.execution_snapshot, admitted.execution_snapshot)
        layer = admitted.execution_snapshot.selection.instruction_layers[-1]
        self.assertEqual((layer.source_id, layer.content), ("fixture:1", "Original inert prompt"))
        self.assertEqual(next_input.execution_snapshot.shortcuts[0]["prompt"], "Mutated catalogue prompt")
        self.assertEqual(next_input.execution_snapshot.selection.configuration.presented_tools, [])
        with self.assertRaises(ChatError) as unavailable:
            self.enqueue(self.request("missing-shortcut", shortcut_ids=["nonexistent"]))
        self.assertEqual(unavailable.exception.code, "shortcut_missing")
        self.assertNotIn("missing-shortcut", self.chat.store.get(self.conversation["id"]).accepted_inputs)

    def test_helper_and_model_settings_retain_versions_until_explicit_refreeze(self):
        profile = self.app.state.manager.create_profile(ProfileWriteRequest(
            display_name="Selected settings", per_request={"temperature": 0.25}))
        helper = self.post("/v1/agent-setups", {"name": "Helper", "configuration": {
            "instructions": "Original helper", "presented_tools": [], "profile_id": profile.id,
            "memory_entry_ids": [self.memory["id"]]}})
        main = self.client.patch(f'/v1/agent-setups/{self.agent["id"]}', json={
            "name": "Main", "base_version": self.agent["current_version_id"],
            "configuration": {"presented_tools": [], "profile_id": profile.id,
                "helper_agent_ids": [helper["id"]]}})
        self.assertEqual(main.status_code, 200, main.text)
        first = self.enqueue(self.request("helper-first"))
        captured = first.execution_snapshot
        self.save_memory()
        updated = self.client.patch(f'/v1/agent-setups/{helper["id"]}', json={
            "name": "Changed helper", "base_version": helper["current_version_id"],
            "configuration": {"instructions": "Saved helper", "presented_tools": [],
                "profile_id": profile.id, "memory_entry_ids": [self.memory["id"]]}})
        self.assertEqual(updated.status_code, 200, updated.text)
        self.app.state.manager.update_profile(profile.id, ProfileWriteRequest(
            display_name="Changed settings", per_request={"temperature": 0.75}))
        retry = self.chat.enqueue(self.conversation["id"], self.request("helper-first")).queue[0]
        second = self.enqueue(self.request("helper-second"))
        self.assertEqual(retry.execution_snapshot, captured)
        self.assertEqual(captured.helper_snapshots[0].version_id, helper["current_version_id"])
        self.assertEqual(captured.helper_snapshots[0].configuration.deployment_id, self.deployment.id)
        self.assertEqual(captured.settings["per_request"]["requested"]["temperature"], 0.25)
        self.assertEqual(captured.helper_snapshots[0].settings_snapshot["per_request"]["requested"]["temperature"], 0.25)
        self.assertEqual(second.execution_snapshot.helper_snapshots[0].version_id, updated.json()["current_version_id"])
        self.assertEqual(second.execution_snapshot.helper_snapshots[0].configuration.memory_version_refs, [self.memory["current_version_id"]])
        self.assertEqual(second.execution_snapshot.settings["per_request"]["requested"]["temperature"], 0.75)

    def test_context_does_not_expand_tool_or_project_authority_at_admission(self):
        with self.assertRaises(ChatError) as no_project:
            self.enqueue(self.request("no-project", project_file_refs=["notes.txt"]))
        self.assertEqual(no_project.exception.code, "project_context_required")
        folder = Path(self.tmp.name) / "project"
        folder.mkdir()
        (folder / "notes.txt").write_text("Selected content cannot grant tools", encoding="utf-8")
        project = self.post("/v1/projects", {"path": str(folder)})
        self.conversation = self.post("/v1/chat/conversations", {
            "deployment_id": self.deployment.id, "agent_setup_id": self.agent["id"], "project_id": project["id"]})
        with self.assertRaises(ChatError) as no_reader:
            self.enqueue(self.request("tools-off", project_file_refs=["notes.txt"], presented_tools=["read_file"]))
        self.assertEqual(no_reader.exception.code, "context_file_tool_required")
        saved = self.chat.store.get(self.conversation["id"])
        self.assertEqual(saved.queue, [])
        self.assertEqual(saved.accepted_inputs, {})

    def test_model_configuration_save_cannot_cross_admission_capture(self):
        profile = self.app.state.manager.create_profile(ProfileWriteRequest(
            display_name="Selected settings", per_request={"temperature": 0.25}))
        entered = threading.Event()
        release = threading.Event()
        save_entered = threading.Event()
        save_done = threading.Event()

        def blocked_helpers(*args, **kwargs):
            result = freeze_helpers(*args, **kwargs)
            entered.set()
            if not release.wait(5):
                raise AssertionError("Admission release was not signalled")
            return result

        def save():
            save_entered.set()
            try:
                return self.app.state.manager.update_profile(profile.id, ProfileWriteRequest(
                    display_name="Changed settings", per_request={"temperature": 0.75}))
            finally:
                save_done.set()

        with ThreadPoolExecutor(max_workers=2) as executor:
            try:
                with patch("workbench_backend.chat.service.freeze_helpers", blocked_helpers):
                    admitted_future = executor.submit(self.enqueue, self.request("atomic-profile", profile_id=profile.id))
                    self.assertTrue(entered.wait(5), "Admission did not reach helper capture")
                    saved_future = executor.submit(save)
                    self.assertTrue(save_entered.wait(5), "Configuration Save did not start")
                    # Bounded event waiting gives the competing Save its chance;
                    # it must remain blocked until the accepted snapshot is whole.
                    self.assertFalse(save_done.wait(0.1), "Configuration Save crossed the admission boundary")
                    release.set()
                    admitted = admitted_future.result(timeout=5)
                    saved_future.result(timeout=5)
            finally:
                release.set()
        self.assertEqual(admitted.execution_snapshot.settings["per_request"]["requested"]["temperature"], 0.25)
        latest = self.enqueue(self.request("after-profile-save", profile_id=profile.id))
        self.assertEqual(latest.execution_snapshot.settings["per_request"]["requested"]["temperature"], 0.75)

    def test_queue_input_identity_is_stable_and_cannot_replace_other_accepted_work(self):
        first = self.enqueue(self.request("first-stable-identity"))
        second = self.enqueue(self.request("second-stable-identity"))
        before = self.chat.store.get(self.conversation["id"]).model_copy(deep=True)
        for replacement in [second.input_message_id, "unused-replacement-identity"]:
            with self.subTest(replacement=replacement), self.assertRaises(ChatError) as rejected:
                self.chat.update_queue_item(self.conversation["id"], first.id,
                    ChatQueueItemUpdateRequest(expected_revision=0, input_message_id=replacement, task="Overwrite"))
            self.assertEqual(rejected.exception.status_code, 409)
            saved = self.chat.store.get(self.conversation["id"])
            self.assertEqual(saved.queue, before.queue)
            self.assertEqual(saved.accepted_inputs, before.accepted_inputs)
        unchanged = self.chat.update_queue_item(self.conversation["id"], first.id,
            ChatQueueItemUpdateRequest(expected_revision=0, input_message_id=first.input_message_id, task="Deliberate text revision"))
        self.assertEqual([item.input_message_id for item in unchanged.queue], [first.input_message_id, second.input_message_id])
        self.assertEqual(unchanged.queue[0].execution_snapshot.selection, first.execution_snapshot.selection)

    def test_queue_setup_refreeze_replaces_agent_defaults_but_preserves_chat_additions(self):
        addition = self.post("/v1/knowledge/entries", {
            "scope": "user", "kind": "memory", "content": "Explicit Chat context"})
        queued = self.enqueue(self.request("replace-agent-defaults", memory_entry_ids=[addition["id"]]))
        self.assertCountEqual(queued.execution_snapshot.selection.configuration.memory_version_refs,
            [self.memory["current_version_id"], addition["current_version_id"]])
        replacement = self.post("/v1/agent-setups", {
            "name": "Agent without knowledge", "configuration": {"presented_tools": []}})
        revised = self.chat.update_queue_item(self.conversation["id"], queued.id,
            ChatQueueItemUpdateRequest(expected_revision=0, intended_config={"agent_setup_id": replacement["id"]})).queue[0]
        self.assertEqual(revised.execution_snapshot.selection.agent_setup_version_id, replacement["current_version_id"])
        self.assertEqual(revised.execution_snapshot.selection.configuration.memory_version_refs, [addition["current_version_id"]])
        self.assertEqual(revised.execution_snapshot.conversation_overrides.memory_entry_ids, [addition["id"]])
        original = self.knowledge.get_version(self.memory["current_version_id"])
        self.assertEqual(original.content, "Original memory")

    def test_queue_agent_without_knowledge_clears_resolved_record_ids(self):
        queued = self.enqueue(self.request("clear-resolved-knowledge"))
        replacement = self.post("/v1/agent-setups", {
            "name": "Agent without knowledge", "configuration": {"presented_tools": []}})
        revised = self.chat.update_queue_item(self.conversation["id"], queued.id,
            ChatQueueItemUpdateRequest(expected_revision=0, intended_config={"agent_setup_id": replacement["id"]})).queue[0]
        self.assertFalse(revised.execution_snapshot.selection.configuration.memory_version_refs)
        self.assertFalse(revised.execution_snapshot.intended_config["memory_version_refs"])
        self.assertFalse(revised.execution_snapshot.intended_config["memory_entry_ids"])
        self.assertFalse(revised.execution_snapshot.conversation_overrides.memory_entry_ids)

    def test_queue_fixed_to_inherited_agent_restores_chat_model_and_removes_old_helpers(self):
        fixed_model = self.app.state.manager.attach_connected(ConnectedDeploymentRequest(
            display_name="Fixed model", endpoint="http://127.0.0.1:10/v1"))
        helper = self.post("/v1/agent-setups", {
            "name": "Old helper", "configuration": {"instructions": "Assist", "presented_tools": []}})
        fixed_agent = self.post("/v1/agent-setups", {"name": "Fixed agent", "configuration": {
            "deployment_id": fixed_model.id, "presented_tools": [],
            "helper_agent_ids": [helper["id"]], "review": {"enabled": True, "criteria": "Check"}}})
        queued = self.enqueue(self.request("queue-fixed-to-inherited", agent_setup_id=fixed_agent["id"]))
        self.assertEqual(queued.execution_snapshot.selection.configuration.deployment_id, fixed_model.id)
        self.assertEqual(queued.execution_snapshot.helper_snapshots[0].configuration.deployment_id, fixed_model.id)
        revised = self.chat.update_queue_item(self.conversation["id"], queued.id,
            ChatQueueItemUpdateRequest(expected_revision=0, intended_config={"agent_setup_id": self.agent["id"]})).queue[0]
        self.assertEqual(revised.execution_snapshot.selection.configuration.deployment_id, self.deployment.id)
        self.assertEqual(revised.execution_snapshot.intended_config["deployment_id"], self.deployment.id)
        self.assertEqual(revised.execution_snapshot.helper_snapshots, [])
        self.assertFalse(revised.execution_snapshot.intended_config["helper_agent_ids"])
        self.assertFalse(revised.execution_snapshot.intended_config["review"]["enabled"])

    def test_replace_queued_setup_discards_old_chat_intent_but_keeps_message_and_prior_run(self):
        folder = Path(self.tmp.name) / "queued-project"
        folder.mkdir()
        (folder / "notes.txt").write_text("Selected earlier context", encoding="utf-8")
        project = self.post("/v1/projects", {"path": str(folder)})
        self.conversation = self.post("/v1/chat/conversations", {
            "deployment_id": self.deployment.id, "project_id": project["id"]})
        self.app.state.harness = HarnessService(lambda: self.app.state.manager,
            app_store=self.app.state.app_store, knowledge_provider=lambda: self.knowledge,
            model_factory=lambda *_: ScriptedChatModel([AIMessage(content="Earlier answer")]))
        completed = self.client.post(f'/v1/chat/conversations/{self.conversation["id"]}/start', json={
            "task": "Earlier accepted work", "input_message_id": "earlier-run", "presented_tools": []})
        self.assertEqual(completed.status_code, 200, completed.text)
        earlier_run = wait_for_chat(self.client, self.conversation["id"])["current_run"]
        self.assertEqual(earlier_run["status"], "completed")
        saved_run = self.client.get(f'/v1/agent-runs/{earlier_run["id"]}').json()

        asset = self.chat.assets.retain_upload(RetainedUploadRequest(
            session_id=self.conversation["id"], filename="attached.md", content_type="text/markdown",
            content_base64=base64.b64encode(b"Retained attachment").decode("ascii")))
        original_request = self.request("replace-queued-setup", presented_tools=["read_file", "grep"],
            memory_entry_ids=[self.memory["id"]], project_file_refs=["notes.txt"],
            shortcut_ids=["summarize"], attachment_ids=[asset.id])
        accepted = self.enqueue(original_request)
        self.assertEqual(accepted.execution_snapshot.selection.configuration.memory_version_refs,
            [self.memory["current_version_id"]])
        self.assertEqual(accepted.execution_snapshot.shortcuts[0]["id"], "summarize")
        self.assertEqual(accepted.execution_snapshot.selection.configuration.presented_tools, ["read_file", "grep"])
        replacement = self.post("/v1/agent-setups", {
            "name": "Different agent", "configuration": {"presented_tools": []}})
        revised = self.chat.update_queue_item(self.conversation["id"], accepted.id,
            ChatQueueItemUpdateRequest(expected_revision=0, replace_setup=True,
                intended_config={"agent_setup_id": replacement["id"]})).queue[0]
        self.assertEqual((revised.id, revised.input_message_id, revised.revision),
            (accepted.id, accepted.input_message_id, 1))
        self.assertEqual((revised.task, revised.attachment_ids), (accepted.task, [asset.id]))
        self.assertEqual(revised.execution_snapshot.selection.agent_setup_version_id,
            replacement["current_version_id"])
        self.assertEqual(revised.execution_snapshot.selection.configuration.presented_tools, [])
        self.assertFalse(revised.execution_snapshot.selection.configuration.memory_version_refs)
        self.assertFalse(revised.execution_snapshot.intended_config["memory_entry_ids"])
        self.assertEqual(revised.execution_snapshot.shortcuts, [])
        self.assertFalse(revised.execution_snapshot.intended_config["project_file_refs"])
        self.assertFalse(any(layer.name == "Selected project files" for layer in revised.instruction_layers))
        self.assertEqual(self.client.get(f'/v1/agent-runs/{earlier_run["id"]}').json(), saved_run)
        with self.assertRaises(ChatError) as obsolete:
            self.chat.enqueue(self.conversation["id"], original_request)
        self.assertEqual(obsolete.exception.code, "submission_identity_conflict")
        retried = self.chat.enqueue(self.conversation["id"], self.chat._request_from_queue_item(revised))
        self.assertEqual(len(retried.queue), 1)
        self.assertEqual(retried.queue[0].execution_snapshot, revised.execution_snapshot)
        defaulted = self.chat.update_queue_item(self.conversation["id"], accepted.id,
            ChatQueueItemUpdateRequest(expected_revision=1, replace_setup=True,
                intended_config={"deployment_id": self.deployment.id})).queue[0]
        self.assertEqual((defaulted.id, defaulted.input_message_id, defaulted.revision),
            (accepted.id, accepted.input_message_id, 2))
        self.assertEqual((defaulted.task, defaulted.attachment_ids), (accepted.task, [asset.id]))
        self.assertIsNone(defaulted.execution_snapshot.selection.agent_setup_id,
            "omitting an agent from the replacement chooses the default rather than the queued agent")
        self.assertIsNone(defaulted.execution_snapshot.intended_config["agent_setup_id"])
        self.assertFalse(defaulted.execution_snapshot.selection.configuration.memory_version_refs)
        self.assertEqual(defaulted.execution_snapshot.shortcuts, [])
        self.assertFalse(defaulted.execution_snapshot.intended_config["project_file_refs"])
        self.assertEqual(self.client.get(f'/v1/agent-runs/{earlier_run["id"]}').json(), saved_run)
        with self.assertRaises(ChatError) as obsolete_agent:
            self.chat.enqueue(self.conversation["id"], self.chat._request_from_queue_item(revised))
        self.assertEqual(obsolete_agent.exception.code, "submission_identity_conflict")
        latest_retry = self.chat.enqueue(self.conversation["id"], self.chat._request_from_queue_item(defaulted))
        self.assertEqual(len(latest_retry.queue), 1)
        self.assertEqual(latest_retry.queue[0].execution_snapshot, defaulted.execution_snapshot)
