"""STATE-004 unknown-effect safety: no silent replay, no rollback promise."""

from __future__ import annotations

import tempfile
import time
import unittest
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage

from workbench_backend.agents.harness import HarnessService
from workbench_backend.agents.schemas import AgentRun, AgentRunStatus
from workbench_backend.app import create_app
from workbench_backend.inference.ids import utc_now
from workbench_backend.inference.service import ModelManager
from workbench_backend.state.effects import CANCEL_REQUESTED_RECOVERY_NOTE
from workbench_backend.lab.schemas import RestoreResult, SnapshotManifest
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


def echo_then_reply() -> list[AIMessage]:
    return [
        AIMessage(
            content="",
            tool_calls=[{"name": "echo", "args": {"text": "harness-ok"}, "id": "call_echo"}],
        ),
        AIMessage(content="The echo tool returned harness-ok. Looks correct."),
    ]


class UnknownEffectSafetyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.paths = WorkbenchPaths(self.root).ensure()
        self.manager = ModelManager(self.paths)
        self.app = create_app(data_root=self.root)
        self.app.state.manager = self.manager

        def factory(_run: AgentRun, _sink: list[dict[str, Any]]) -> ScriptedChatModel:
            return ScriptedChatModel(echo_then_reply())

        self.app.state.harness = HarnessService(
            lambda: self.manager,
            model_factory=factory,
            app_store=self.app.state.app_store,
        )
        self.app.state.lab._manager_provider = lambda: self.manager
        self.app.state.lab._harness_provider = lambda: self.app.state.harness
        self.client = workbench_client(self.app)
        self.deployment_id = self.client.post(
            "/v1/deployments/connected",
            json={"endpoint": "http://127.0.0.1:9/v1", "display_name": "effect-fixture"},
        ).json()["id"]

    def tearDown(self) -> None:
        close_workbench_sqlite(self.app, getattr(self, "client", None))
        self.tmp.cleanup()

    def test_crash_between_effect_and_ack_reports_uncertainty_without_replay(self) -> None:
        dispatched = self.client.post(
            "/v1/effects",
            json={"operation": "notify-external", "run_id": "agent_crash", "payload": {"target": "remote"}},
        )
        self.assertEqual(dispatched.status_code, 200, dispatched.text)
        effect = dispatched.json()
        self.assertEqual(effect["outcome"], "dispatched")
        self.assertTrue(effect["unresolved"])
        self.assertEqual(effect["replay_count"], 0)
        self.assertEqual(effect["rollback_promise"], "none")

        first = self.client.post(f"/v1/effects/{effect['id']}/recover", json={"action": "reconnect"})
        self.assertEqual(first.status_code, 200, first.text)
        report = first.json()
        self.assertFalse(report["replayed"])
        self.assertTrue(report["uncertainty"])
        self.assertFalse(report["reconciled"])
        self.assertEqual(report["rollback_promise"], "none")
        self.assertEqual(report["environment_restore"], "not_supported")
        self.assertEqual(report["effect"]["outcome"], "unknown")
        self.assertEqual(report["effect"]["replay_count"], 0)
        self.assertIn("not be silently repeated", report["note"])

        second = self.client.post(f"/v1/effects/{effect['id']}/recover", json={"action": "restart"})
        self.assertEqual(second.status_code, 200, second.text)
        again = second.json()
        self.assertFalse(again["replayed"])
        self.assertTrue(again["uncertainty"])
        self.assertEqual(again["effect"]["replay_count"], 0)
        self.assertEqual(again["effect"]["outcome"], "unknown")

        listed = self.client.get("/v1/effects", params={"run_id": "agent_crash", "unresolved_only": True})
        self.assertEqual(listed.status_code, 200, listed.text)
        self.assertEqual(len(listed.json()), 1)

    def test_authoritative_evidence_reconciles_without_replay(self) -> None:
        effect = self.client.post("/v1/effects", json={"operation": "create-remote-job"}).json()
        recovered = self.client.post(f"/v1/effects/{effect['id']}/recover", json={"action": "resume"}).json()
        self.assertEqual(recovered["effect"]["outcome"], "unknown")
        reconciled = self.client.post(
            f"/v1/effects/{effect['id']}/reconcile",
            json={"evidence": {"remote_job_id": "job_123", "status": "succeeded"}},
        )
        self.assertEqual(reconciled.status_code, 200, reconciled.text)
        body = reconciled.json()
        self.assertEqual(body["outcome"], "reconciled")
        self.assertFalse(body["unresolved"])
        self.assertEqual(body["replay_count"], 0)
        self.assertIn("not replayed", body["note"])

        recover_again = self.client.post(
            f"/v1/effects/{effect['id']}/recover",
            json={"action": "reconnect"},
        ).json()
        self.assertFalse(recover_again["replayed"])
        self.assertFalse(recover_again["uncertainty"])
        self.assertTrue(recover_again["reconciled"])

    def test_acknowledge_then_recover_does_not_replay(self) -> None:
        effect = self.client.post("/v1/effects", json={"operation": "post-webhook"}).json()
        ack = self.client.post(
            f"/v1/effects/{effect['id']}/acknowledge",
            json={"evidence": {"http_status": 204}},
        )
        self.assertEqual(ack.status_code, 200, ack.text)
        self.assertEqual(ack.json()["outcome"], "acknowledged")
        self.assertFalse(ack.json()["unresolved"])
        recovered = self.client.post(
            f"/v1/effects/{effect['id']}/recover",
            json={"action": "resume"},
        ).json()
        self.assertFalse(recovered["replayed"])
        self.assertFalse(recovered["uncertainty"])
        self.assertEqual(recovered["effect"]["outcome"], "acknowledged")

    def test_rollback_is_refused_with_no_promise(self) -> None:
        effect = self.client.post("/v1/effects", json={"operation": "charge-external"}).json()
        response = self.client.post(f"/v1/effects/{effect['id']}/rollback")
        self.assertEqual(response.status_code, 409, response.text)
        body = response.json()
        self.assertEqual(body["code"], "external_effect_rollback_unsupported")
        self.assertEqual(body["rollback_promise"], "none")
        self.assertEqual(body["environment_restore"], "not_supported")

    def test_snapshot_schema_does_not_promise_external_effect_rollback(self) -> None:
        snapshot = SnapshotManifest(
            id="snap_fixture",
            workspace_id="ws_fixture",
            captured_at="2026-09-19T00:00:00Z",
            unresolved_side_effects=["effect_fixture"],
            tree_path=str(self.paths.snapshots / "snap_fixture" / "tree"),
        )
        self.assertEqual(snapshot.external_effect_rollback, "not_supported")
        self.assertEqual(snapshot.rollback_promise, "none")
        self.assertEqual(snapshot.environment_restore, "not_this_milestone")
        restore = RestoreResult(
            workspace={
                "id": "ws_child",
                "display_name": "restored",
                "path": str(self.paths.workspaces / "ws_child"),
                "created_at": "2026-09-19T00:00:00Z",
            },
            case_id="case_fixture",
            parent_workspace_id="ws_fixture",
            parent_unchanged=True,
            branch={"kind": "linked_branch"},
            snapshot_id=snapshot.id,
            unresolved_side_effects=snapshot.unresolved_side_effects,
        )
        self.assertFalse(restore.external_effects_rolled_back)
        self.assertEqual(restore.rollback_promise, "none")
        self.assertEqual(restore.unresolved_side_effects, ["effect_fixture"])

    def test_lab_capture_restore_preserves_unresolved_effects(self) -> None:
        workspace = self.client.post(
            "/v1/lab/workspaces",
            json={"display_name": "effects", "files": {"notes.md": "keep"}},
        )
        self.assertEqual(workspace.status_code, 200, workspace.text)
        workspace_id = workspace.json()["id"]
        started = self.client.post(
            "/v1/agent-runs",
            json={
                "deployment_id": self.deployment_id,
                "task": "Echo the text harness-ok using the echo tool.",
                "presented_tools": ["echo"],
                "workspace_id": workspace_id,
            },
        )
        self.assertEqual(started.status_code, 200, started.text)
        run = wait_for_run(self.client, started.json()["id"])
        effect = self.client.post(
            "/v1/effects",
            json={"operation": "email-user", "run_id": run["id"]},
        ).json()
        captured = self.client.post(
            "/v1/lab/cases/capture",
            json={"workspace_id": workspace_id, "run_id": run["id"]},
        )
        self.assertEqual(captured.status_code, 200, captured.text)
        case = captured.json()
        self.assertEqual(case["rollback_promise"], "none")
        self.assertEqual(case["external_effect_rollback"], "not_supported")
        self.assertIn(effect["id"], case["unresolved_side_effects"])
        snapshot = self.client.get(f"/v1/lab/snapshots/{case['snapshot_id']}").json()
        self.assertEqual(snapshot["rollback_promise"], "none")
        self.assertEqual(snapshot["external_effect_rollback"], "not_supported")
        self.assertEqual(snapshot["kind"], "starting")
        self.assertEqual(case["input_origin"], "starting_snapshot")
        self.assertNotIn(effect["id"], snapshot["unresolved_side_effects"])

        restored = self.client.post(f"/v1/lab/cases/{case['id']}/restore")
        self.assertEqual(restored.status_code, 200, restored.text)
        restore = restored.json()
        self.assertFalse(restore["external_effects_rolled_back"])
        self.assertEqual(restore["rollback_promise"], "none")
        self.assertIn(effect["id"], restore["unresolved_side_effects"])
        self.assertTrue(
            any("does not roll back external effects" in item for item in restore["deviations"])
        )
        after = self.client.get(f"/v1/effects/{effect['id']}").json()
        self.assertTrue(after["unresolved"])
        self.assertEqual(after["outcome"], "dispatched")
        self.assertEqual(after["replay_count"], 0)

    def test_recover_during_cancel_requested_does_not_replay(self) -> None:
        now = utc_now()
        run = AgentRun(
            id="agent_cancel_requested_recover",
            status=AgentRunStatus.cancel_requested,
            deployment_id=self.deployment_id,
            task="held for recover",
            enabled_tools=["echo"],
            presented_tools=["echo"],
            created_at=now,
            updated_at=now,
        )
        self.app.state.app_store.put_run(run)
        effect = self.client.post(
            "/v1/effects",
            json={"operation": "notify-external", "run_id": run.id},
        )
        self.assertEqual(effect.status_code, 200, effect.text)
        recovered = self.client.post(
            f"/v1/effects/{effect.json()['id']}/recover",
            json={"action": "reconnect"},
        )
        self.assertEqual(recovered.status_code, 200, recovered.text)
        report = recovered.json()
        self.assertFalse(report["replayed"])
        self.assertTrue(report["uncertainty"])
        self.assertEqual(report["effect"]["outcome"], "unknown")
        self.assertEqual(report["effect"]["replay_count"], 0)
        self.assertEqual(report["rollback_promise"], "none")
        self.assertEqual(report["note"], CANCEL_REQUESTED_RECOVERY_NOTE)
        self.assertIn("cancel_requested", report["note"])
        self.assertIn("not a confirmed stop", report["note"])
        stored = self.app.state.app_store.get_run(run.id)
        self.assertIsNotNone(stored)
        self.assertEqual(stored.status, AgentRunStatus.cancel_requested)


if __name__ == "__main__":
    unittest.main()
