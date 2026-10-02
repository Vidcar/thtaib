"""Operational reads never hydrate or normalize substantial captured history."""

from __future__ import annotations

import json
from pathlib import Path
import sqlite3
import tempfile
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
        self.assertNotIn("model_requests", json.loads(self.saved))
        self.assertLess(len(self.saved.encode()), 20 * 1024)
        self.assertGreaterEqual(len(self.run.model_requests), 50)
        self.assertGreaterEqual(len(json.dumps([capture.model_dump(mode="json") for capture in self.run.model_requests]).encode()), 10 * 1024 * 1024)
        self.assertEqual(self._capture_count(self.run.id), 0)
        self.assertEqual(self.store.get_run(self.run.id).model_requests, [])

    def _capture_count(self, run_id: str | None = None) -> int:
        with self.store._lock:
            present = self.store._conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'run_diagnostic_captures'"
            ).fetchone()
            if present is None:
                return 0
            if run_id is None:
                row = self.store._conn.execute("SELECT COUNT(*) FROM run_diagnostic_captures").fetchone()
            else:
                row = self.store._conn.execute(
                    "SELECT COUNT(*) FROM run_diagnostic_captures WHERE run_id = ?", (run_id,),
                ).fetchone()
        return int(row[0])

    def _reject_diagnostic_work(self):
        stack = []
        for target in (
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
            self.assertEqual(self._capture_count(self.run.id), 0)
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
            self.assertEqual(self._capture_count(self.run.id), 0)
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

    def test_execution_updates_do_not_store_request_bodies(self) -> None:
        self.run.status = type(self.run.status).completed
        self.run.events.append(AgentEvent(at=utc_now(), kind="assistant_message", detail={"content": "Finished"}))
        self.run.model_requests.append(ModelRequestCapture(at=utc_now(), instructions="new synthetic capture"))
        remembered = len(self.run.model_requests)
        self.store.put_execution_run(self.run)
        persisted = self.store.get_execution_run(self.run.id)
        self.assertEqual(persisted.status, "completed")
        self.assertEqual(persisted.model_requests, [])
        self.assertTrue(any(event.kind == "assistant_message" for event in persisted.events))
        self.assertEqual(len(self.run.model_requests), remembered)
        self.run.model_requests = []
        self.store.put_execution_run(self.run)
        self.assertEqual(self.store.get_execution_run(self.run.id).model_requests, [])
        self.assertEqual(self._capture_count(self.run.id), 0)

    def test_normalize_does_not_read_a_leftover_request_body(self) -> None:
        synthetic_secret = "wb_synthetic_changed_credential_1234"
        with self.store._lock:
            self.store._conn.execute(
                """
                CREATE TABLE run_diagnostic_captures (
                    run_id TEXT NOT NULL,
                    position INTEGER NOT NULL,
                    payload TEXT NOT NULL,
                    PRIMARY KEY (run_id, position)
                )
                """
            )
            self.store._conn.execute(
                "INSERT INTO run_diagnostic_captures (run_id, position, payload) VALUES (?, 0, ?)",
                (self.run.id, json.dumps({"instructions": f"API_KEY={synthetic_secret}"})),
            )
            self.store._conn.commit()
        with patch.object(ModelRequestCapture, "model_validate_json", side_effect=AssertionError("decoded a stored request")):
            result = self.store.normalize_run_diagnostics(self.run.id)
        self.assertEqual(result, [])
        self.assertNotIn(synthetic_secret, self.store.get_run(self.run.id).model_dump_json())
        self.assertNotIn(synthetic_secret, self.store.get_execution_run(self.run.id).model_dump_json())
        with self.store._lock:
            payload = self.store._conn.execute("SELECT payload FROM runs WHERE id = ?", (self.run.id,)).fetchone()[0]
        self.assertEqual(payload, self.saved)
        self.assertNotIn(synthetic_secret, payload)

    def test_normalize_does_not_rewrite_the_run(self) -> None:
        result = self.store.normalize_run_diagnostics(self.run.id)
        self.assertEqual(result, [])
        self.store.put_execution_run(synthetic_large_run("unrelated_diagnostic_write", model_requests=[]))
        with self.store._lock:
            after = self.store._conn.execute("SELECT payload FROM runs WHERE id = ?", (self.run.id,)).fetchone()[0]
        self.assertEqual(after, self.saved)
        self.assertEqual(self._capture_count(), 0)
        persisted = self.store.get_execution_run(self.run.id)
        self.assertEqual(persisted.status, "running")
        self.assertEqual(persisted.model_requests, [])
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
            )

        before = snapshot()
        self.run.status = type(self.run.status).completed
        self.run.events.append(AgentEvent(at=utc_now(), kind="assistant_message", detail={"content": "Finished"}))
        self.run.checkpoint_ids = ["checkpoint_retry"]
        self.run.related_files = [RelatedFile(path="synthetic-output.txt", kind="written_file")]
        self.run.model_requests.extend(
            ModelRequestCapture(at=utc_now(), instructions=f"New synthetic capture {index}") for index in range(26)
        )
        remembered = len(self.run.model_requests)
        reconcile = self.store._reconcile_chat_completion_locked

        def fail_after_chat_update(run):
            reconcile(run)
            raise MemoryError("Synthetic failure after Chat completion update")

        with patch.object(self.store, "_reconcile_chat_completion_locked", fail_after_chat_update), self.assertRaises(MemoryError):
            self.store.put_execution_run(self.run)
        self.assertFalse(self.store._conn.in_transaction)
        self.assertEqual(snapshot(), before)
        self.store.put_execution_run(synthetic_large_run(
            "unrelated_chat_update", thread_id="thread_chat_update", model_requests=[],
        ))
        self.assertEqual(snapshot(), before)

        self.store.put_execution_run(self.run)
        self.store.put_execution_run(self.run)
        persisted = self.store.get_execution_run(self.run.id)
        self.assertEqual(persisted.status, "completed")
        self.assertEqual(persisted.model_requests, [])
        self.assertEqual(len(self.run.model_requests), remembered)
        self.assertEqual(persisted.checkpoint_ids, ["checkpoint_retry"])
        self.assertEqual(persisted.related_files, self.run.related_files)
        self.assertEqual(self._capture_count(self.run.id), 0)
        transcript = json.loads(snapshot()[3][0])["transcript"]
        self.assertEqual([item["content"] for item in transcript if item["role"] == "assistant"], ["Finished"])

    def test_execution_status_survives_without_a_stored_request_body(self) -> None:
        self.run.status = type(self.run.status).cancel_requested
        self.run.model_requests.append(ModelRequestCapture(at=utc_now(), instructions="new fixture"))
        self.store.put_execution_run(self.run)
        self.assertEqual(self.store.normalize_run_diagnostics(self.run.id), [])
        persisted = self.store.get_execution_run(self.run.id)
        self.assertEqual(persisted.status, "cancel_requested")
        self.assertEqual(persisted.model_requests, [])
        self.assertEqual(self._capture_count(self.run.id), 0)

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
        self.assertEqual(self._capture_count(self.run.id), 0)

    def test_redaction_setting_does_not_create_a_stored_request_policy(self) -> None:
        knowledge = KnowledgeStore(self.paths)
        knowledge.write_config(knowledge.read_config().model_copy(update={
            "context_captures": ContextCaptureSettings(redaction_mode="discard", retention_seconds=0),
        }))
        stored = knowledge.read_config().context_captures
        self.assertEqual(stored.redaction_mode, "redact_secrets")
        self.assertIsNone(stored.retention_seconds)
        self.assertEqual(self.store.normalize_run_diagnostics(self.run.id), [])
        self.assertEqual(self.store.get_execution_run(self.run.id).model_requests, [])
        self.assertEqual(self._capture_count(self.run.id), 0)


if __name__ == "__main__":
    unittest.main()
