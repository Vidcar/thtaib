"""Durable knowledge versioning (STATE-005) and Lab/harness version refs."""

from __future__ import annotations

import json
import tempfile
import time
import unittest
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage

from workbench_backend.agents.harness import HarnessService
from workbench_backend.agents.schemas import AgentRun
from workbench_backend.app import create_app
from workbench_backend.inference.service import ModelManager
from workbench_backend.knowledge.schemas import KnowledgeConfig
from workbench_backend.paths import WorkbenchPaths

from tests.scripted_model import ScriptedChatModel
from tests.support import close_workbench_sqlite, workbench_client, offline_workbench_client


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


HUMAN = {"actor": "human", "note": "maintainer"}
MAINTAINER = {"actor": "human", "note": "api"}
AGENT = {"actor": "agent", "run_id": "agent_fixture"}


class KnowledgeApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.paths = WorkbenchPaths(self.root).ensure()
        self.manager = ModelManager(self.paths)
        self.app = create_app(data_root=self.root)
        self.app.state.manager = self.manager
        self.app.state.knowledge.paths = self.paths
        self.app.state.knowledge.store = self.app.state.knowledge.store.__class__(self.paths)
        self.client = workbench_client(self.app)

    def tearDown(self) -> None:
        close_workbench_sqlite(self.app, getattr(self, "client", None))
        self.tmp.cleanup()

    def _create(
        self,
        *,
        scope: str = "user",
        kind: str = "memory",
        content: str = "remember this",
        provenance: dict[str, Any] | None = None,
        scope_id: str | None = None,
        display_name: str | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "scope": scope,
            "kind": kind,
            "content": content,
            "provenance": provenance or HUMAN,
        }
        if scope_id is not None:
            payload["scope_id"] = scope_id
        if display_name is not None:
            payload["display_name"] = display_name
        response = self.client.post("/v1/knowledge/entries", json=payload)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def test_paths_advertise_application_owned_knowledge(self) -> None:
        body = self.client.get("/v1/paths").json()
        self.assertEqual(body["knowledge"], str(self.paths.knowledge))
        self.assertIn("knowledge", body["windows_layout"])
        self.assertTrue(self.paths.knowledge.is_dir())
        self.assertFalse(any(self.root.rglob("knowledge-store*")))
        self.assertFalse(any(self.root.rglob("rag-index*")))
        self.assertFalse((self.root / ".scratch").exists())

    def test_create_user_agent_and_project_entries_with_provenance(self) -> None:
        user = self._create(scope="user", kind="memory", content="user note", display_name="user-memory")
        agent = self._create(
            scope="agent",
            kind="skill",
            content="---\nname: agent-skill\ndescription: Agent skill instructions.\n---\n\nskill body",
            scope_id=self.client.post("/v1/agent-setups", json={"name": "Alpha"}).json()["id"],
            display_name="agent-skill",
        )
        project = self._create(
            scope="project",
            kind="protected_instruction",
            content="do not overwrite",
            provenance=MAINTAINER,
            scope_id=self.client.post("/v1/projects", json={"path": str(self.root)}).json()["id"],
        )
        self.assertEqual(user["scope"], "user")
        self.assertEqual(agent["kind"], "skill")
        self.assertEqual(project["kind"], "protected_instruction")
        self.assertTrue(user["id"].startswith("kn_"))
        self.assertTrue(user["current_version_id"].startswith("knv_"))
        self.assertEqual(user["provenance"]["actor"], "human")
        self.assertEqual(project["provenance"]["actor"], "human")
        on_disk = json.loads((self.paths.knowledge / "entries.json").read_text(encoding="utf-8"))
        self.assertEqual({item["id"] for item in on_disk}, {user["id"], agent["id"], project["id"]})
        version_file = self.paths.knowledge / "versions" / f"{user['current_version_id']}.json"
        self.assertTrue(version_file.is_file())
        listed = self.client.get("/v1/knowledge/entries").json()
        self.assertEqual(len(listed), 3)

    def test_edit_revert_keeps_append_only_history(self) -> None:
        created = self._create(content="v1")
        first = created["current_version_id"]
        edited = self.client.post(
            f"/v1/knowledge/entries/{created['id']}/edit",
            json={"content": "v2", "base_version": first, "provenance": HUMAN},
        )
        self.assertEqual(edited.status_code, 200, edited.text)
        second = edited.json()["current_version_id"]
        self.assertEqual(edited.json()["content"], "v2")
        self.assertEqual(edited.json()["previous_version_id"], first)
        reverted = self.client.post(
            f"/v1/knowledge/entries/{created['id']}/revert",
            json={"target_version_id": first, "base_version": second, "provenance": HUMAN},
        )
        self.assertEqual(reverted.status_code, 200, reverted.text)
        body = reverted.json()
        self.assertEqual(body["content"], "v1")
        self.assertEqual(body["reverted_from_version_id"], first)
        self.assertNotEqual(body["current_version_id"], first)
        history = self.client.get(f"/v1/knowledge/entries/{created['id']}/versions").json()
        self.assertEqual(len(history), 3)
        self.assertEqual([item["content"] for item in history], ["v1", "v2", "v1"])
        original = self.client.get(f"/v1/knowledge/versions/{first}").json()
        self.assertEqual(original["content"], "v1")
        first_path = self.paths.knowledge / "versions" / f"{first}.json"
        self.assertEqual(json.loads(first_path.read_text(encoding="utf-8"))["content"], "v1")

    def test_stale_base_version_is_explicit_conflict(self) -> None:
        created = self._create(content="original")
        first = created["current_version_id"]
        self.client.post(
            f"/v1/knowledge/entries/{created['id']}/edit",
            json={"content": "winner", "base_version": first, "provenance": HUMAN},
        )
        stale = self.client.post(
            f"/v1/knowledge/entries/{created['id']}/edit",
            json={"content": "lost", "base_version": first, "provenance": HUMAN},
        )
        self.assertEqual(stale.status_code, 409)
        body = stale.json()
        self.assertEqual(body["code"], "knowledge_conflict")
        self.assertEqual(body["expected_base_version"], first)
        current = self.client.get(f"/v1/knowledge/entries/{created['id']}").json()
        self.assertEqual(current["content"], "winner")
        self.assertNotEqual(current["current_version_id"], first)

    def test_agent_cannot_overwrite_protected_instruction(self) -> None:
        created = self._create(
            kind="protected_instruction",
            content="keep this instruction",
            provenance=MAINTAINER,
        )
        denied = self.client.post(
            f"/v1/knowledge/entries/{created['id']}/edit",
            json={
                "content": "agent overwrite",
                "base_version": created["current_version_id"],
                "provenance": AGENT,
            },
        )
        self.assertEqual(denied.status_code, 403)
        self.assertEqual(denied.json()["code"], "knowledge_actor_forged")
        current = self.client.get(f"/v1/knowledge/entries/{created['id']}").json()
        self.assertEqual(current["content"], "keep this instruction")
        allowed = self.client.post(
            f"/v1/knowledge/entries/{created['id']}/edit",
            json={
                "content": "maintainer edit",
                "base_version": created["current_version_id"],
                "provenance": MAINTAINER,
            },
        )
        self.assertEqual(allowed.status_code, 200, allowed.text)
        self.assertEqual(allowed.json()["content"], "maintainer edit")
        create_denied = self.client.post(
            "/v1/knowledge/entries",
            json={
                "scope": "user",
                "kind": "protected_instruction",
                "content": "agent-created",
                "provenance": AGENT,
            },
        )
        self.assertEqual(create_denied.status_code, 403)
        self.assertEqual(create_denied.json()["code"], "knowledge_actor_forged")

    def test_agent_writes_require_explicit_scope_policy(self) -> None:
        from workbench_backend.knowledge.schemas import KnowledgeCreateRequest
        from workbench_backend.errors import KnowledgeError
        request = KnowledgeCreateRequest(scope="user", kind="memory", content="agent memory")
        with self.assertRaises(KnowledgeError) as denied:
            self.app.state.knowledge.create(request, actor="agent", run_id="agent_fixture")
        self.assertEqual(denied.exception.code, "scope_policy_denied")
        updated = self.client.put("/v1/knowledge/automatic-save-policy", json={"scope": "user", "automatic_agent_writes": True})
        self.assertEqual(updated.status_code, 200, updated.text)
        allowed = self.app.state.knowledge.create(request, actor="agent", run_id="agent_fixture")
        self.assertEqual(allowed.provenance.actor, "agent")
        self.assertEqual(allowed.provenance.run_id, "agent_fixture")
        forged = self.client.post("/v1/knowledge/entries", json={**request.model_dump(exclude_none=True), "provenance": AGENT})
        self.assertEqual(forged.status_code, 403)
        self.assertEqual(forged.json()["code"], "knowledge_actor_forged")

    def test_context_capture_default_redacts_secrets_and_is_configurable(self) -> None:
        config = self.client.get("/v1/knowledge/config").json()
        self.assertEqual(config["context_captures"]["redaction_mode"], "redact_secrets")
        self.assertIsNone(config["context_captures"]["retention_seconds"])
        self.assertTrue(config["not_rag"])
        default = KnowledgeConfig()
        self.assertEqual(default.context_captures.redaction_mode, "redact_secrets")
        raw = (
            "note API_KEY=super-secret token=abc123 SECRET_VALUE "
            "and hf_abcdefghijklmnopqrstuvwxyz remain"
        )
        captured = self.client.post("/v1/knowledge/captures", json={"content": raw, "source": "debug"})
        self.assertEqual(captured.status_code, 200, captured.text)
        body = captured.json()
        self.assertTrue(body["retained"])
        self.assertTrue(body["redacted"])
        self.assertIn("[REDACTED]", body["content"])
        self.assertNotIn("super-secret", body["content"])
        self.assertNotIn("SECRET_VALUE", body["content"])
        self.assertIn("api_key", body["redacted_fields"])

        self.client.put("/v1/knowledge/config", json={"context_captures": {"redaction_mode": "retain"}})
        retained = self.client.post(
            "/v1/knowledge/captures",
            json={"content": "API_KEY=visible-secret"},
        ).json()
        self.assertEqual(retained["redaction_mode"], "retain")
        self.assertFalse(retained["redacted"])
        self.assertIn("visible-secret", retained["content"])

        self.client.put("/v1/knowledge/config", json={"context_captures": {"redaction_mode": "discard"}})
        discarded = self.client.post(
            "/v1/knowledge/captures",
            json={"content": "API_KEY=should-not-keep"},
        ).json()
        self.assertTrue(discarded["discarded"])
        self.assertFalse(discarded["retained"])
        self.assertIsNone(discarded["content"])

        self.client.put(
            "/v1/knowledge/config",
            json={"context_captures": {"redaction_mode": "redact_secrets", "retention_seconds": 0}},
        )
        expired = self.client.post(
            "/v1/knowledge/captures",
            json={"content": "short lived API_KEY=temp"},
        ).json()
        self.assertTrue(expired["expired"])
        self.assertIsNone(expired["content"])
        listed = self.client.get("/v1/knowledge/captures").json()
        match = next(item for item in listed if item["id"] == expired["id"])
        self.assertTrue(match["expired"])


class KnowledgeLabHarnessTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.paths = WorkbenchPaths(self.root).ensure()
        self.manager = ModelManager(self.paths)
        self.app = create_app(data_root=self.root)
        self.app.state.manager = self.manager

        def factory(_run: AgentRun, _sink: list[dict[str, Any]]) -> ScriptedChatModel:
            return ScriptedChatModel(
                [
                    AIMessage(
                        content="",
                        tool_calls=[{"name": "echo", "args": {"text": "harness-ok"}, "id": "call_echo"}],
                    ),
                    AIMessage(content="The echo tool returned harness-ok."),
                ]
            )

        self.app.state.harness = HarnessService(
            lambda: self.manager,
            model_factory=factory,
            knowledge_provider=lambda: self.app.state.knowledge,
        )
        self.app.state.lab._manager_provider = lambda: self.manager
        self.app.state.lab._harness_provider = lambda: self.app.state.harness
        self.app.state.lab._knowledge_provider = lambda: self.app.state.knowledge
        self.client = offline_workbench_client(self.app)
        self.deployment_id = self.client.post(
            "/v1/deployments/connected",
            json={"endpoint": "http://127.0.0.1:9/v1", "display_name": "knowledge-lab"},
        ).json()["id"]

    def tearDown(self) -> None:
        close_workbench_sqlite(self.app, getattr(self, "client", None))
        self.tmp.cleanup()

    def test_knowledge_version_ids_are_referenceable_from_lab_and_harness(self) -> None:
        memory = self.client.post(
            "/v1/knowledge/entries",
            json={
                "scope": "project",
                "scope_id": self.client.post("/v1/projects", json={"path": str(self.root)}).json()["id"],
                "kind": "memory",
                "content": "project memory",
                "provenance": HUMAN,
            },
        ).json()
        skill = self.client.post(
            "/v1/knowledge/entries",
            json={
                "scope": "agent",
                "scope_id": self.client.post("/v1/agent-setups", json={"name": "Lab agent"}).json()["id"],
                "kind": "skill",
                "content": "---\nname: lab-skill\ndescription: Lab skill instructions.\n---\n\nskill text",
                "provenance": HUMAN,
            },
        ).json()
        workspace = self.client.post(
            "/v1/lab/workspaces",
            json={"display_name": "with-knowledge", "files": {"notes.md": "ok"}},
        ).json()
        started = self.client.post(
            "/v1/agent-runs",
            json={
                "deployment_id": self.deployment_id,
                "task": "Echo the text harness-ok using the echo tool.",
                "presented_tools": ["echo"],
                "workspace_id": workspace["id"],
                "knowledge_version_refs": [memory["current_version_id"], skill["current_version_id"]],
            },
        )
        self.assertEqual(started.status_code, 200, started.text)
        run = wait_for_run(self.client, started.json()["id"])
        self.assertEqual(run["knowledge"], "application_owned")
        self.assertEqual(run["memory_version_refs"], [memory["current_version_id"]])
        self.assertEqual(run["skill_version_refs"], [skill["current_version_id"]])
        capture = run["model_requests"][0]
        self.assertEqual(capture["memory_versions"], [memory["current_version_id"]])
        self.assertEqual(capture["skill_versions"], [skill["current_version_id"]])
        gaps = " ".join(capture["capture_gaps"])
        self.assertIn("no retrieval", gaps)
        self.assertNotIn("no durable memory", gaps)

        case = self.client.post(
            "/v1/lab/cases/capture",
            json={"workspace_id": workspace["id"], "run_id": run["id"]},
        )
        self.assertEqual(case.status_code, 200, case.text)
        recorded = case.json()
        self.assertEqual(recorded["knowledge"], "application_owned")
        self.assertEqual(recorded["memory_version_refs"], [memory["current_version_id"]])
        self.assertEqual(recorded["skill_version_refs"], [skill["current_version_id"]])
        restored = self.client.post(f"/v1/lab/cases/{recorded['id']}/restore").json()
        rerun = self.client.post(
            f"/v1/lab/cases/{recorded['id']}/rerun",
            json={"tool_mode": "live-tool", "workspace_id": restored["workspace"]["id"]},
        )
        self.assertEqual(rerun.status_code, 200, rerun.text)
        child = wait_for_run(self.client, rerun.json()["agent_run_id"])
        self.assertEqual(child["memory_version_refs"], [memory["current_version_id"]])
        self.assertEqual(child["knowledge"], "application_owned")
        self.assertEqual(rerun.json()["applied_config"]["memory_version_refs"], [memory["current_version_id"]])
        missing = self.client.post(
            "/v1/lab/cases/capture",
            json={
                "workspace_id": workspace["id"],
                "run_id": run["id"],
                "knowledge_version_refs": ["knv_missing"],
            },
        )
        self.assertEqual(missing.status_code, 404)
        self.assertEqual(missing.json()["code"], "knowledge_version_missing")


if __name__ == "__main__":
    unittest.main()
