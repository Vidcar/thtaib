"""Operational reads never hydrate or normalize substantial captured history."""

from __future__ import annotations

import json
from pathlib import Path
import sqlite3
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from workbench_backend.agents.routes import router as agent_router
from workbench_backend.agents.effective_setup import EffectiveSetup
from workbench_backend.agents.harness import HarnessService
from workbench_backend.agents.schemas import AgentEvent, ModelRequestCapture, PendingInterrupt, PendingInterruptAction
from workbench_backend.agents.setup_schemas import FrozenHelperSelection, SetupConfiguration
from workbench_backend.assets.lifecycle import AssetLifecycleService
from workbench_backend.chat.schemas import ChatConversation, ChatMessage
from workbench_backend.inference.ids import utc_now
from workbench_backend.inference.adapter import image_model_profile
from workbench_backend.inference.capabilities import setup_fingerprint
from workbench_backend.inference.schemas import Deployment, SettingsBag, SettingsBags
from workbench_backend.inference.service import ModelManager
from workbench_backend.knowledge.diagnostics import apply_capture_policy
from workbench_backend.knowledge.schemas import ContextCaptureSettings
from workbench_backend.knowledge.store import KnowledgeStore
from workbench_backend.paths import WorkbenchPaths
from workbench_backend.state.desktop_routes import router as desktop_router
from workbench_backend.state.dependencies import DependencyPreviewService
from workbench_backend.state.schemas import RelatedFile
from workbench_backend.state.store import ApplicationStore

from tests.large_run_history import synthetic_large_run
from tests.support import close_workbench_sqlite


class OperationalRunViewsTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.paths = WorkbenchPaths(Path(temporary.name))
        self.store = ApplicationStore(self.paths)
        self.addCleanup(close_workbench_sqlite, self.store)
        self.run = self.store.put_run(synthetic_large_run(
            pending_interrupt=PendingInterrupt(interrupt_id="interrupt_large", action_requests=[
                PendingInterruptAction(name="ask_user", args={"prompt": "Choose a fixture"}),
            ]), checkpoint_ids=["checkpoint_b", "checkpoint_a"],
        ))
        with self.store._lock:
            self.saved = self.store._conn.execute("SELECT payload FROM runs WHERE id = ?", (self.run.id,)).fetchone()[0]
            self.saved_diagnostics = self.store._diagnostic_rows_locked(self.run.id)
        self.assertNotIn("model_requests", json.loads(self.saved))
        self.assertLess(len(self.saved.encode()), 20 * 1024)
        self.assertGreaterEqual(len(self.run.model_requests), 50)
        self.assertGreaterEqual(len(json.dumps([capture.model_dump(mode="json") for capture in self.run.model_requests]).encode()), 10 * 1024 * 1024)

    def _reject_diagnostic_work(self):
        stack = []
        for target in (
            "workbench_backend.state.store.apply_run_diagnostic_policy",
            "workbench_backend.state.store.apply_capture_policy",
            "workbench_backend.agents.schemas.ModelRequestCapture.model_validate",
            "workbench_backend.agents.schemas.ModelRequestCapture.model_validate_json",
        ):
            owner = patch(target, side_effect=AssertionError("Operational read inspected diagnostic history"))
            owner.start()
            stack.append(owner)
        self.addCleanup(lambda: [owner.stop() for owner in stack])

    def test_repeated_read_projections_do_zero_diagnostic_normalization(self) -> None:
        self._reject_diagnostic_work()
        for _ in range(5):
            browser = self.store.get_run_browser(self.run.id)
            self.assertEqual(browser.browser_control, "agent")
            self.assertEqual(browser.presented_tools, ("read_file", "browser_snapshot"))
            lifecycle = self.store.get_run_lifecycle(self.run.id)
            self.assertEqual(lifecycle.status, "running")
            self.assertEqual(len(self.store.list_run_lifecycle(statuses={"running"}, thread_id="thread_large", roots_only=True)), 1)
            self.assertEqual(self.store.get_run_lifecycle(self.run.id, details=False).status, "running")
            self.assertEqual(len(self.store.list_run_lifecycle(statuses={"running"}, details=False)), 1)
            operational = self.store.get_run_operational(self.run.id)
            self.assertNotIn("model_requests", operational.model_dump())
            self.assertFalse(hasattr(operational, "model_requests"))
            self.assertEqual(len(self.store.list_runs_operational()), 1)
            attention = self.store.list_run_attention({"running"})
            self.assertEqual(attention[0].pending_interrupt.action_names, ("ask_user",))
            self.assertEqual(set(attention[0].checkpoint_ids), {"checkpoint_b", "checkpoint_a"})
        with self.assertRaises(ValidationError):
            browser.browser_control = "user"
        with self.store._lock:
            after = self.store._conn.execute("SELECT payload FROM runs WHERE id = ?", (self.run.id,)).fetchone()[0]
            self.assertEqual(self.store._diagnostic_rows_locked(self.run.id), self.saved_diagnostics)
        self.assertEqual(after, self.saved)

    def test_projection_cannot_be_persisted_as_a_complete_run(self) -> None:
        self._reject_diagnostic_work()
        for view in (self.store.get_run_browser(self.run.id), self.store.get_run_lifecycle(self.run.id),
                     self.store.get_run_operational(self.run.id), self.store.list_run_attention({"running"})[0]):
            with self.assertRaises(TypeError):
                self.store.put_run(view)
            with self.assertRaises(TypeError):
                self.store.put_execution_run(view)
        with self.store._lock:
            after = self.store._conn.execute("SELECT payload FROM runs WHERE id = ?", (self.run.id,)).fetchone()[0]
            self.assertEqual(self.store._diagnostic_rows_locked(self.run.id), self.saved_diagnostics)
        self.assertEqual(after, self.saved)

    def test_browser_projection_preserves_exact_verified_screenshot_capability(self) -> None:
        original_bag = SettingsBag(requested={"max_tokens": 1234}, applied={"max_tokens": 1234, "temperature": 0.7})
        self.run.effective_setup = EffectiveSetup(
            selected_deployment_id=self.run.deployment_id, loaded_deployment_id=self.run.deployment_id,
            system_prompt="Synthetic fixture", bags=SettingsBags(per_request=original_bag),
        )
        self.store.put_execution_run(self.run)
        self._reject_diagnostic_work()
        projected = self.store.get_run_browser(self.run.id)
        projected_bag = projected.effective_setup.bags.per_request
        deployment = Deployment(
            id=self.run.deployment_id, display_name="Synthetic vision deployment", scope="connected", status="running",
            created_at=utc_now(), updated_at=utc_now(),
        )
        fingerprint = setup_fingerprint(deployment, original_bag)
        deployment.capability_evidence = [
            {"capability": capability, "status": "passed", "fingerprint": fingerprint}
            for capability in ("image", "tool_image")
        ]
        self.assertEqual(setup_fingerprint(deployment, projected_bag), fingerprint)
        self.assertTrue(image_model_profile(deployment, projected_bag)["image_tool_message"])
        # Use the actual Return eligibility implementation, including its
        # conservative exception handling, rather than a fake screenshot gate.
        harness = SimpleNamespace(manager=SimpleNamespace(get_deployment=lambda _id: deployment))
        self.assertTrue(HarnessService.screenshot_reading_available(harness, projected))
        with self.assertRaises(ValidationError):
            projected_bag.applied = {}

    def test_execution_updates_preserve_diagnostic_expiry_and_append_only_new_captures(self) -> None:
        knowledge = KnowledgeStore(self.paths)
        settings = ContextCaptureSettings(retention_seconds=0)
        knowledge.write_config(knowledge.read_config().model_copy(update={"context_captures": settings}))
        normalized = self.store.normalize_run_diagnostics(self.run.id)
        self.assertTrue(all(item.expired and item.instructions is None for item in normalized))
        self.run.status = type(self.run.status).completed
        self.run.events.append(AgentEvent(at=utc_now(), kind="assistant_message", detail={"content": "Finished"}))
        self.run.model_requests.append(apply_capture_policy(ModelRequestCapture(at=utc_now(), instructions="new synthetic capture"), settings))
        with patch("workbench_backend.state.store.apply_capture_policy", side_effect=AssertionError("Execution rewrote old diagnostic bodies")):
            self.store.put_execution_run(self.run)
        persisted = self.store.get_execution_run(self.run.id)
        self.assertEqual(persisted.status, "completed")
        self.assertEqual(len(persisted.model_requests), 51)
        self.assertTrue(all(item.expired and item.instructions is None for item in persisted.model_requests))
        self.run.model_requests = []
        self.store.put_execution_run(self.run)
        self.assertEqual(len(self.store.get_execution_run(self.run.id).model_requests), 51)

    def test_diagnostic_cas_serializes_only_one_changed_capture_among_large_history(self) -> None:
        changed_index = 7
        marker = "Altered synthetic capture"
        synthetic_secret = "wb_synthetic_changed_credential_1234"
        with self.store._lock:
            self.store._conn.execute(
                "UPDATE run_diagnostic_captures SET payload = json_set(payload, '$.instructions', ?) WHERE run_id = ? AND position = ?",
                (f"{marker}: API_KEY={synthetic_secret}", self.run.id, changed_index),
            )
            self.store._conn.commit()
            before = [json.loads(payload) for _, payload in self.store._diagnostic_rows_locked(self.run.id)]
        dump = ModelRequestCapture.model_dump
        serialize = ModelRequestCapture.model_dump_json
        serialized = []

        def require_changed(capture):
            self.assertTrue((capture.instructions or "").startswith(marker), "Persistence serialized an unchanged diagnostic capture")

        def guarded_dump(capture, *args, **kwargs):
            # Content fingerprinting must inspect every current capture to
            # detect nested edits. Persistence may copy only changed entries.
            if kwargs.get("exclude") != {"privacy_fingerprint"}:
                require_changed(capture)
            return dump(capture, *args, **kwargs)

        def guarded_serialize(capture, *args, **kwargs):
            require_changed(capture)
            serialized.append(capture)
            return serialize(capture, *args, **kwargs)

        with patch.object(ModelRequestCapture, "model_dump", guarded_dump), patch.object(ModelRequestCapture, "model_dump_json", guarded_serialize):
            result = self.store.normalize_run_diagnostics(self.run.id)
        self.assertEqual(len(serialized), 1)
        self.assertEqual(len(result), 50)
        self.assertNotIn(synthetic_secret, result[changed_index].instructions)
        with self.store._lock:
            after = [json.loads(payload) for _, payload in self.store._diagnostic_rows_locked(self.run.id)]
        for index in range(50):
            if index != changed_index:
                self.assertEqual(after[index], before[index])
        self.assertNotEqual(after[changed_index]["privacy_fingerprint"], before[changed_index]["privacy_fingerprint"])
        self.assertNotIn(synthetic_secret, json.dumps(after[changed_index]))

    def test_failed_diagnostic_batch_rolls_back_all_changed_indices_before_retry(self) -> None:
        knowledge = KnowledgeStore(self.paths)
        settings = ContextCaptureSettings(redaction_mode="discard")
        knowledge.write_config(knowledge.read_config().model_copy(update={"context_captures": settings}))
        with self.store._lock:
            # Batch 1 changes indices 0..24. Reject batch 2 only after that
            # first actual SQLite update, rather than failing before mutation.
            self.store._conn.execute(
                """CREATE TRIGGER reject_second_diagnostic_batch BEFORE UPDATE OF payload ON run_diagnostic_captures
                WHEN NEW.run_id = 'run_large' AND NEW.position = 25 AND json_extract(NEW.payload, '$.discarded') = 1
                BEGIN SELECT RAISE(ABORT, 'Synthetic second diagnostic batch failure'); END"""
            )
            self.store._conn.commit()
        try:
            with self.assertRaisesRegex(sqlite3.IntegrityError, "Synthetic second diagnostic batch failure"):
                self.store.normalize_run_diagnostics(self.run.id)
            self.assertFalse(self.store._conn.in_transaction)
            self.store.put_execution_run(synthetic_large_run("unrelated_diagnostic_write", model_requests=[]))
            with self.store._lock:
                after = self.store._conn.execute("SELECT payload FROM runs WHERE id = ?", (self.run.id,)).fetchone()[0]
                self.assertEqual(self.store._diagnostic_rows_locked(self.run.id), self.saved_diagnostics)
            self.assertEqual(after, self.saved)
        finally:
            with self.store._lock:
                self.store._conn.execute("DROP TRIGGER reject_second_diagnostic_batch")
                self.store._conn.commit()
        result = self.store.normalize_run_diagnostics(self.run.id)
        self.assertEqual(len(result), 50)
        self.assertTrue(all(capture.discarded and capture.instructions is None for capture in result))
        persisted = self.store.get_execution_run(self.run.id)
        self.assertEqual(persisted.status, "running")
        self.assertEqual(len(persisted.model_requests), 50)
        self.assertTrue(all(capture.discarded for capture in persisted.model_requests))
        self.assertEqual(set(persisted.checkpoint_ids), {"checkpoint_a", "checkpoint_b"})

    def test_failed_execution_write_rolls_back_capture_batches_linkage_and_chat_before_retry(self) -> None:
        self.run.source_surface = "chat"
        self.store.put_execution_run(self.run)
        conversation = ChatConversation(
            id="chat_atomic", deployment_id=self.run.deployment_id, thread_id=self.run.thread_id,
            run_ids=[self.run.id], current_run_id=self.run.id, created_at=utc_now(), updated_at=utc_now(),
            transcript=[ChatMessage(role="user", content="Synthetic request", at=utc_now(), run_id=self.run.id)],
        )
        self.store.put_conversation(conversation)
        observer = sqlite3.connect(self.paths.application_db)
        self.addCleanup(observer.close)

        def snapshot():
            return (
                observer.execute("SELECT payload, status FROM runs WHERE id = ?", (self.run.id,)).fetchone(),
                observer.execute("SELECT checkpoint_id FROM run_checkpoints WHERE run_id = ? ORDER BY checkpoint_id", (self.run.id,)).fetchall(),
                observer.execute("SELECT path, kind FROM run_files WHERE run_id = ? ORDER BY path", (self.run.id,)).fetchall(),
                observer.execute("SELECT payload FROM conversations WHERE id = ?", (conversation.id,)).fetchone(),
                observer.execute("SELECT position, payload FROM run_diagnostic_captures WHERE run_id = ? ORDER BY position", (self.run.id,)).fetchall(),
            )

        before = snapshot()
        self.run.status = type(self.run.status).completed
        self.run.events.append(AgentEvent(at=utc_now(), kind="assistant_message", detail={"content": "Finished"}))
        self.run.checkpoint_ids = ["checkpoint_retry"]
        self.run.related_files = [RelatedFile(path="synthetic-output.txt", kind="written_file")]
        self.run.model_requests.extend(
            apply_capture_policy(ModelRequestCapture(at=utc_now(), instructions=f"New synthetic capture {index}"), ContextCaptureSettings())
            for index in range(26)
        )
        serialize = ModelRequestCapture.model_dump_json
        serialized = 0

        def fail_second_batch(capture, *args, **kwargs):
            nonlocal serialized
            serialized += 1
            if serialized == 26:
                raise MemoryError("Synthetic second capture batch failure")
            return serialize(capture, *args, **kwargs)

        reconcile = self.store._reconcile_chat_completion_locked

        def fail_after_chat_update(run):
            reconcile(run)
            raise MemoryError("Synthetic failure after Chat completion update")

        faults = (
            ("capture_batch", patch.object(ModelRequestCapture, "model_dump_json", fail_second_batch)),
            ("chat_update", patch.object(self.store, "_reconcile_chat_completion_locked", fail_after_chat_update)),
        )
        for stage, fault in faults:
            with self.subTest(stage=stage):
                with fault, self.assertRaises(MemoryError):
                    self.store.put_execution_run(self.run)
                self.assertFalse(self.store._conn.in_transaction)
                self.assertEqual(snapshot(), before)
                # An unrelated successful commit must not publish the failed
                # run's partial capture tail, linkage or assistant message.
                self.store.put_execution_run(synthetic_large_run(
                    f"unrelated_{stage}", thread_id=f"thread_{stage}", model_requests=[],
                ))
                self.assertEqual(snapshot(), before)

        self.store.put_execution_run(self.run)
        self.store.put_execution_run(self.run)
        persisted = self.store.get_execution_run(self.run.id)
        self.assertEqual(persisted.status, "completed")
        self.assertEqual(len(persisted.model_requests), 76)
        self.assertEqual(persisted.checkpoint_ids, ["checkpoint_retry"])
        self.assertEqual(persisted.related_files, self.run.related_files)
        self.assertEqual(
            [capture.model_dump() for capture in persisted.model_requests[:50]],
            [capture.model_dump() for capture in self.run.model_requests[:50]],
        )
        transcript = json.loads(snapshot()[3][0])["transcript"]
        self.assertEqual([item["content"] for item in transcript if item["role"] == "assistant"], ["Finished"])

    def test_diagnostic_cas_keeps_concurrent_operational_and_capture_updates(self) -> None:
        knowledge = KnowledgeStore(self.paths)
        settings = ContextCaptureSettings(redaction_mode="discard")
        knowledge.write_config(knowledge.read_config().model_copy(update={"context_captures": settings}))
        entered, release = threading.Event(), threading.Event()
        self.addCleanup(release.set)
        result, failures = [], []
        first = True

        def gated(capture, config):
            nonlocal first
            if first:
                first = False
                entered.set()
                if not release.wait(5):
                    raise AssertionError("Diagnostic fixture was not released")
            return apply_capture_policy(capture, config)

        def inspect():
            try:
                result.append(self.store.normalize_run_diagnostics(self.run.id))
            except BaseException as exc:
                failures.append(exc)

        with patch("workbench_backend.state.store.apply_capture_policy", side_effect=gated):
            worker = threading.Thread(target=inspect)
            worker.start()
            try:
                self.assertTrue(entered.wait(5))
                # This completes while expensive inspection is blocked, proving
                # the store lock is free and the eventual CAS cannot lose work.
                self.run.status = type(self.run.status).cancel_requested
                self.run.model_requests.append(apply_capture_policy(ModelRequestCapture(at=utc_now(), instructions="new fixture"), settings))
                self.store.put_execution_run(self.run)
            finally:
                release.set()
                worker.join(10)
            self.assertFalse(worker.is_alive())
        self.assertFalse(failures)
        self.assertEqual(len(result[0]), 51)
        persisted = self.store.get_execution_run(self.run.id)
        self.assertEqual(persisted.status, "cancel_requested")
        self.assertEqual(len(persisted.model_requests), 51)
        self.assertTrue(all(capture.discarded for capture in persisted.model_requests))

    def test_actual_operational_api_attention_and_work_use_capture_free_store(self) -> None:
        self._reject_diagnostic_work()
        app = FastAPI()
        app.include_router(agent_router)
        app.include_router(desktop_router)
        app.state.app_store = self.store
        app.state.harness = SimpleNamespace(
            get_run_operational=self.store.get_run_operational,
            list_runs_operational=self.store.list_runs_operational,
            get_run_lifecycle=self.store.get_run_lifecycle,
            list_run_lifecycle=self.store.list_run_lifecycle,
            get_run=lambda _id: (_ for _ in ()).throw(AssertionError("Operational API used diagnostic getter")),
        )
        app.state.chat = SimpleNamespace(store=SimpleNamespace(list_conversations=lambda **_kwargs: []))
        app.state.preferences = SimpleNamespace(
            preferences=lambda: SimpleNamespace(success_notifications=False),
            attention_hidden=lambda _identity, _run: False,
            notification_sent=lambda _identity: False,
        )
        app.state.manager = SimpleNamespace(imports=SimpleNamespace(list_jobs=lambda: []))
        with TestClient(app) as client:
            for _ in range(3):
                response = client.get(f"/v1/agent-runs/{self.run.id}?view=operational")
                self.assertEqual(response.status_code, 200, response.text)
                self.assertNotIn("model_requests", response.json())
                self.assertNotIn("model_requests", client.get("/v1/agent-runs?view=operational").json()[0])
                self.assertEqual(client.get("/v1/desktop/work").json()["active_run_ids"], [self.run.id])
                attention = client.get("/v1/desktop/attention").json()
                self.assertEqual(attention[0]["kind"], "question")
                self.assertEqual(attention[0]["identity"], f"{self.run.id}:question:interrupt_large")
            self.assertEqual(client.get(f"/v1/agent-runs/{self.run.id}?view=invalid").status_code, 422)

    def test_model_dependency_and_deletion_checks_do_zero_diagnostic_normalization(self) -> None:
        self.run.project_id = "project_synthetic"
        self.run.project_path = str(self.paths.root / "project")
        self.run.helper_snapshots = [FrozenHelperSelection(
            agent_id="helper_synthetic", version_id="helper_version", name="Synthetic helper",
            configuration=SetupConfiguration(deployment_id="helper_deployment"),
        )]
        self.store.put_execution_run(self.run)
        conversation = ChatConversation(
            id="chat_synthetic", deployment_id=self.run.deployment_id, project_id=self.run.project_id,
            project_path=self.run.project_path, thread_id=self.run.thread_id,
            run_ids=[self.run.id], current_run_id=self.run.id, created_at=utc_now(), updated_at=utc_now(),
        )
        self.store.put_conversation(conversation)
        self._reject_diagnostic_work()
        manager = SimpleNamespace(paths=self.paths)
        for deployment_id in (self.run.deployment_id, "helper_deployment"):
            consumers = ModelManager._run_consumers(manager, deployment_ids={deployment_id})
            self.assertEqual(len(consumers), 1)
            self.assertEqual(consumers[0].id, self.run.id)
            self.assertTrue(consumers[0].live)
        knowledge_store = KnowledgeStore(self.paths)
        previews = DependencyPreviewService(
            self.store,
            SimpleNamespace(get_project=lambda _id: SimpleNamespace(name="Synthetic project", path=self.run.project_path),
                resolve=lambda **_kwargs: SimpleNamespace(configuration=SetupConfiguration())),
            SimpleNamespace(store=knowledge_store, get_config=knowledge_store.read_config),
            None,
        )
        preview = previews.preview("project", self.run.project_id)
        consumers = {item.kind: item for item in preview.consumers}
        self.assertTrue(consumers["agent_run"].live)
        self.assertTrue(consumers["chat"].live)
        assets = AssetLifecycleService(self.paths, self.store)
        blocked = assets.preview_conversation_delete(conversation.id)
        self.assertFalse(blocked.can_delete)
        self.assertEqual(blocked.blockers[0]["id"], self.run.id)
        self.run.status = type(self.run.status).completed
        self.store.put_execution_run(self.run)
        deleted = assets.delete_conversation(conversation.id, include_diagnostics=False)
        self.assertTrue(deleted.can_delete)
        with self.store._lock:
            remaining = self.store._conn.execute(
                "SELECT COUNT(*) FROM runs WHERE id = ?", (self.run.id,),
            ).fetchone()[0]
        self.assertEqual(remaining, 0)
        with self.store._lock:
            self.assertEqual(self.store._diagnostic_rows_locked(self.run.id), [])

    def test_diagnostic_processing_rechecks_settings_changed_during_inspection(self) -> None:
        knowledge = KnowledgeStore(self.paths)
        entered, release = threading.Event(), threading.Event()
        self.addCleanup(release.set)
        result, failures = [], []
        first = True

        def gated(capture, config):
            nonlocal first
            if first:
                first = False
                entered.set()
                if not release.wait(5):
                    raise AssertionError("Diagnostic fixture was not released")
            return apply_capture_policy(capture, config)

        def inspect():
            try:
                result.append(self.store.normalize_run_diagnostics(self.run.id))
            except BaseException as exc:
                failures.append(exc)

        with patch("workbench_backend.state.store.apply_capture_policy", side_effect=gated):
            worker = threading.Thread(target=inspect)
            worker.start()
            try:
                self.assertTrue(entered.wait(5))
                settings = ContextCaptureSettings(redaction_mode="discard")
                knowledge.write_config(knowledge.read_config().model_copy(update={"context_captures": settings}))
            finally:
                release.set()
                worker.join(10)
            self.assertFalse(worker.is_alive())
        self.assertFalse(failures)
        self.assertTrue(all(item.discarded and item.instructions is None for item in result[0]))
        persisted = self.store.get_execution_run(self.run.id)
        self.assertTrue(all(item.discarded and item.instructions is None for item in persisted.model_requests))


if __name__ == "__main__":
    unittest.main()
