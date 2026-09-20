"""Issue #57: selected profile/knowledge must change the actual request."""

from __future__ import annotations

import json
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage, HumanMessage

from workbench_backend.agents.effective_setup import (
    KNOWLEDGE_PREAMBLE,
    SURFACE_PROMPT_HEADING,
    compose_system_prompt,
    content_digest,
    resolve_effective_setup,
)
from workbench_backend.agents.harness import DEFAULT_SYSTEM_PROMPT, HarnessService
from workbench_backend.agents.schemas import AgentRun
from workbench_backend.app import create_app
from workbench_backend.inference.adapter import chat_model_for_deployment
from workbench_backend.inference.ids import utc_now
from workbench_backend.inference.schemas import (
    Deployment,
    DeploymentStatus,
    ManagementScope,
    ProfileWriteRequest,
    SettingsBags,
)
from workbench_backend.inference.service import ModelManager
from workbench_backend.inference.settings import PER_REQUEST_KEYS, resolve_bag
from workbench_backend.knowledge.schemas import KnowledgeRefs, KnowledgeVersion
from workbench_backend.paths import WorkbenchPaths

from tests.scripted_model import RECEIVED_PROMPTS, ScriptedChatModel, reset_received_prompts
from tests.support import close_workbench_sqlite, workbench_client, offline_workbench_client

MEMORY_TOKEN = "MEM-TOKEN-57-QWERTY-UNIQUE"
SKILL_TOKEN = "SKILL-TOKEN-57-ZXCVB-UNIQUE"
PROTECTED_TOKEN = "PROT-TOKEN-57-KEEP-ME"
HUMAN = {"actor": "human", "note": "effective-setup"}
AGENT = {"actor": "agent", "run_id": "agent_fixture"}
DISTINCT_TEMPERATURE = 0.17


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


def wait_for_chat(client: TestClient, conversation_id: str, *, timeout: float = 20.0) -> dict[str, Any]:
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


class _RecordingHandler(BaseHTTPRequestHandler):
    requests: list[dict[str, Any]] = []

    def do_GET(self) -> None:  # noqa: N802
        self._json(200, {"data": [{"id": "fake-llama"}]})

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length)
        body = json.loads(raw.decode("utf-8")) if raw else {}
        self.requests.append({"path": self.path, "body": body})
        self._json(
            200,
            {
                "id": "effective-setup",
                "object": "chat.completion",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": "pong"},
                        "finish_reason": "stop",
                    }
                ],
            },
        )

    def log_message(self, format: str, *args: object) -> None:  # noqa: A003
        return

    def _json(self, status: int, payload: dict[str, object]) -> None:
        encoded = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)


class EffectiveSetupResolverTests(unittest.TestCase):
    def test_compose_includes_protected_content_not_id_only(self) -> None:
        version = KnowledgeVersion(
            id="knv_prot",
            entry_id="kn_prot",
            scope="project",
            scope_id="proj",
            kind="protected_instruction",
            content=PROTECTED_TOKEN,
            provenance={"actor": "human"},
            created_at=utc_now(),
        )
        prompt = compose_system_prompt(
            surface_system_prompt="Chat surface prompt.",
            profile_system_prompt="Profile identity prompt.",
            default_system_prompt=DEFAULT_SYSTEM_PROMPT,
            versions=[version],
        )
        self.assertIn("Profile identity prompt.", prompt)
        self.assertIn("Chat surface prompt.", prompt)
        self.assertIn(SURFACE_PROMPT_HEADING, prompt)
        self.assertLess(prompt.index("Profile identity prompt."), prompt.index("Chat surface prompt."))
        self.assertIn(PROTECTED_TOKEN, prompt)
        self.assertIn("knv_prot", prompt)
        self.assertIn(KNOWLEDGE_PREAMBLE, prompt)

    def test_compose_does_not_append_memory_or_skill_bodies(self) -> None:
        versions = [
            KnowledgeVersion(
                id="knv_mem",
                entry_id="kn_mem",
                scope="project",
                kind="memory",
                content=MEMORY_TOKEN,
                provenance={"actor": "human"},
                created_at=utc_now(),
            ),
            KnowledgeVersion(
                id="knv_skill",
                entry_id="kn_skill",
                scope="project",
                kind="skill",
                content=SKILL_TOKEN,
                provenance={"actor": "human"},
                created_at=utc_now(),
            ),
        ]
        prompt = compose_system_prompt(
            surface_system_prompt="Chat surface prompt.",
            profile_system_prompt="Profile identity prompt.",
            default_system_prompt=DEFAULT_SYSTEM_PROMPT,
            versions=versions,
        )
        self.assertNotIn(MEMORY_TOKEN, prompt)
        self.assertNotIn(SKILL_TOKEN, prompt)
        self.assertNotIn(KNOWLEDGE_PREAMBLE, prompt)

    def test_surface_prompt_does_not_replace_identical_profile_prompt(self) -> None:
        prompt = compose_system_prompt(
            surface_system_prompt="same identity",
            profile_system_prompt="same identity",
            default_system_prompt=DEFAULT_SYSTEM_PROMPT,
            versions=[],
        )
        self.assertEqual(prompt, "same identity")
        self.assertNotIn(SURFACE_PROMPT_HEADING, prompt)

    def test_profile_per_request_and_startup_mismatch(self) -> None:
        now = utc_now()
        deployment = Deployment(
            id="deploy_a",
            display_name="connected",
            scope=ManagementScope.connected,
            status=DeploymentStatus.running,
            endpoint="http://127.0.0.1:9/v1",
            applied_startup={"ctx_size": 65536, "flash_attn": "on"},
            created_at=now,
            updated_at=now,
            settings=SettingsBags(),
        )
        manager_root = Path(tempfile.mkdtemp())
        manager = ModelManager(WorkbenchPaths(manager_root).ensure())
        profile = manager.create_profile(
            ProfileWriteRequest(
                display_name="hot",
                startup={"ctx_size": 8192},
                per_request={"temperature": DISTINCT_TEMPERATURE, "not_a_real_key": 1},
            )
        )
        setup = resolve_effective_setup(
            deployment=deployment,
            profile=profile,
            knowledge_refs=KnowledgeRefs(),
            knowledge_versions=[],
            surface_system_prompt=None,
            default_system_prompt=DEFAULT_SYSTEM_PROMPT,
        )
        self.assertEqual(setup.bags.per_request.applied["temperature"], DISTINCT_TEMPERATURE)
        self.assertIn("not_a_real_key", setup.unsupported["per_request"])
        self.assertNotIn("not_a_real_key", setup.bags.per_request.applied)
        keys = [item.key for item in setup.startup_mismatches]
        self.assertIn("ctx_size", keys)
        mismatch = next(item for item in setup.startup_mismatches if item.key == "ctx_size")
        self.assertEqual(mismatch.selected, 8192)
        self.assertEqual(mismatch.loaded, 65536)
        self.assertIn("no retrieval", " ".join(setup.gaps))

    def test_pre_correction_profile_reports_retired_startup_keys(self) -> None:
        now = utc_now()
        deployment = Deployment(
            id="deploy_b",
            display_name="connected",
            scope=ManagementScope.connected,
            status=DeploymentStatus.running,
            endpoint="http://127.0.0.1:9/v1",
            applied_startup={"ctx_size": 65536, "flash_attn": "on"},
            created_at=now,
            updated_at=now,
        )
        manager = ModelManager(WorkbenchPaths(Path(tempfile.mkdtemp())).ensure())
        profile = manager.create_profile(
            ProfileWriteRequest(display_name="old", startup={"mlock": True, "ctx_size": 65536})
        )
        # A profile saved before the load_mode correction still carries the
        # retired key in its stored applied bag; simulate that record shape.
        stale_bag = profile.bags.startup.model_copy(
            update={
                "applied": {**profile.bags.startup.applied, "mlock": True},
                "unsupported": [],
                "retired": [],
            }
        )
        stale = profile.model_copy(update={"bags": profile.bags.model_copy(update={"startup": stale_bag})})
        self.assertIn("mlock", stale.bags.startup.applied)
        setup = resolve_effective_setup(
            deployment=deployment,
            profile=stale,
            knowledge_refs=KnowledgeRefs(),
            knowledge_versions=[],
            surface_system_prompt=None,
            default_system_prompt=DEFAULT_SYSTEM_PROMPT,
        )
        self.assertNotIn("mlock", setup.bags.startup.applied)
        self.assertIn("mlock", setup.unsupported["startup"])
        self.assertEqual([note["key"] for note in setup.retired["startup"]], ["mlock"])
        self.assertIn("load_mode", setup.retired["startup"][0]["reason"])
        self.assertEqual(setup.startup_mismatches, [])


class EffectiveSetupLiveAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        _RecordingHandler.requests = []
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), _RecordingHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        host, port = self.server.server_address[:2]
        self.endpoint = f"http://{host}:{port}/v1"
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.project = self.root / "project"
        self.project.mkdir()
        self.app = create_app(data_root=self.root)
        self.client = workbench_client(self.app)
        self.deployment_id = self.client.post(
            "/v1/deployments/connected",
            json={"endpoint": self.endpoint, "display_name": "effective-live"},
        ).json()["id"]

    def tearDown(self) -> None:
        close_workbench_sqlite(self.app, getattr(self, "client", None))
        self.server.shutdown()
        self.server.server_close()
        self.tmp.cleanup()

    def _profile(self, **extra: Any) -> str:
        payload = {
            "display_name": "effective-profile",
            "startup": {"ctx_size": 8192},
            "per_request": {"temperature": DISTINCT_TEMPERATURE, "not_a_real_key": 1},
            "agent": {},
            **extra,
        }
        return self.client.post("/v1/profiles", json=payload).json()["id"]

    def _knowledge(self, kind: str, content: str) -> dict[str, Any]:
        return self.client.post(
            "/v1/knowledge/entries",
            json={
                "scope": "project",
                "scope_id": "proj-57",
                "kind": kind,
                "content": content,
                "display_name": f"{kind}-57",
                "provenance": HUMAN,
            },
        ).json()

    def test_profile_temperature_reaches_outbound_request(self) -> None:
        profile_id = self._profile()
        started = self.client.post(
            "/v1/agent-runs",
            json={
                "deployment_id": self.deployment_id,
                "profile_id": profile_id,
                "task": "Say pong.",
                "presented_tools": ["echo"],
            },
        )
        self.assertEqual(started.status_code, 200, started.text)
        body = wait_for_run(self.client, started.json()["id"])
        self.assertEqual(body["status"], "completed", body.get("error"))
        self.assertTrue(_RecordingHandler.requests)
        posted = _RecordingHandler.requests[0]["body"]
        self.assertAlmostEqual(posted["temperature"], DISTINCT_TEMPERATURE)
        setup = body["effective_setup"]
        self.assertEqual(setup["selected_profile_id"], profile_id)
        self.assertEqual(setup["bags"]["per_request"]["applied"]["temperature"], DISTINCT_TEMPERATURE)
        self.assertIn("not_a_real_key", setup["unsupported"]["per_request"])
        self.assertTrue(setup["startup_mismatches"])
        capture = body["model_requests"][0]
        self.assertEqual(capture["applied_per_request"]["temperature"], DISTINCT_TEMPERATURE)
        self.assertIsNotNone(capture["http_payload"])
        self.assertEqual(capture["http_payload"]["body"]["temperature"], DISTINCT_TEMPERATURE)
        self.assertNotIn("http payload not observed", " ".join(capture["capture_gaps"]))

    def test_knowledge_content_is_available_not_id_only(self) -> None:
        memory = self._knowledge("memory", MEMORY_TOKEN)
        skill = self._knowledge("skill", SKILL_TOKEN)
        started = self.client.post(
            "/v1/agent-runs",
            json={
                "deployment_id": self.deployment_id,
                "task": "Say pong.",
                "presented_tools": ["echo"],
                "memory_version_refs": [memory["current_version_id"]],
                "skill_version_refs": [skill["current_version_id"]],
            },
        )
        self.assertEqual(started.status_code, 200, started.text)
        body = wait_for_run(self.client, started.json()["id"])
        self.assertEqual(body["status"], "completed", body.get("error"))
        setup = body["effective_setup"]
        self.assertEqual(setup["knowledge_binding"], "application_owned")
        loaded_ids = {item["version_id"] for item in setup["loaded_knowledge"]}
        self.assertEqual(loaded_ids, {memory["current_version_id"], skill["current_version_id"]})
        self.assertTrue(all(item["content_available"] for item in setup["loaded_knowledge"]))
        digests = {item["kind"]: item["content_digest"] for item in setup["loaded_knowledge"]}
        self.assertEqual(digests["memory"], content_digest(MEMORY_TOKEN))
        self.assertEqual(digests["skill"], content_digest(SKILL_TOKEN))
        prompt = setup["system_prompt"]
        self.assertNotIn(MEMORY_TOKEN, prompt)
        self.assertNotIn(SKILL_TOKEN, prompt)
        self.assertNotIn(KNOWLEDGE_PREAMBLE, prompt)
        paths = {item["path"] for item in setup["materialized_knowledge"]}
        self.assertTrue(any(path.startswith("/memories/") for path in paths))
        self.assertTrue(any(path.startswith("/skills/") and path.endswith("/SKILL.md") for path in paths))
        capture = body["model_requests"][0]
        instructions = capture["instructions"] or ""
        self.assertIn(MEMORY_TOKEN, instructions)
        self.assertIn("<agent_memory>", instructions)
        self.assertNotIn(SKILL_TOKEN, instructions)
        self.assertIn("## Skills System", instructions)
        outbound = json.dumps(_RecordingHandler.requests[0]["body"])
        self.assertIn(MEMORY_TOKEN, outbound)
        self.assertNotIn(SKILL_TOKEN, outbound)
        self.assertIn("## Skills System", outbound)
        gaps = " ".join(capture["capture_gaps"])
        self.assertIn("no retrieval", gaps)
        self.assertIn("memory edits are run-local", gaps)
        self.assertNotIn("no durable memory", gaps)
        self.assertNotIn("no skill versions", gaps)

    def test_missing_knowledge_ref_fails_closed(self) -> None:
        response = self.client.post(
            "/v1/agent-runs",
            json={
                "deployment_id": self.deployment_id,
                "task": "Say pong.",
                "knowledge_version_refs": ["knv_missing"],
            },
        )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["code"], "knowledge_version_missing")

    def test_chat_composes_profile_system_prompt_instead_of_replacing(self) -> None:
        profile_id = self._profile(agent={"system_prompt": "PROFILE-IDENTITY-TOKEN"})
        created = self.client.post(
            "/v1/chat/conversations",
            json={
                "deployment_id": self.deployment_id,
                "profile_id": profile_id,
                "project_path": str(self.project),
            },
        )
        self.assertEqual(created.status_code, 200, created.text)
        started = self.client.post(
            f"/v1/chat/conversations/{created.json()['id']}/start",
            json={"task": "Say pong.", "presented_tools": ["echo"]},
        )
        self.assertEqual(started.status_code, 200, started.text)
        body = wait_for_chat(self.client, created.json()["id"])
        prompt = body["current_run"]["effective_setup"]["system_prompt"]
        self.assertIn("PROFILE-IDENTITY-TOKEN", prompt)
        self.assertIn(SURFACE_PROMPT_HEADING, prompt)
        self.assertIn("Chat surface", prompt)
        self.assertLess(prompt.index("PROFILE-IDENTITY-TOKEN"), prompt.index(SURFACE_PROMPT_HEADING))

    def test_chat_applies_profile_and_knowledge_and_preserves_write_policy(self) -> None:
        profile_id = self._profile()
        memory = self._knowledge("memory", MEMORY_TOKEN)
        protected = self._knowledge("protected_instruction", PROTECTED_TOKEN)
        created = self.client.post(
            "/v1/chat/conversations",
            json={
                "deployment_id": self.deployment_id,
                "profile_id": profile_id,
                "project_path": str(self.project),
                "memory_version_refs": [memory["current_version_id"]],
                "protected_instruction_version_refs": [protected["current_version_id"]],
            },
        )
        self.assertEqual(created.status_code, 200, created.text)
        started = self.client.post(
            f"/v1/chat/conversations/{created.json()['id']}/start",
            json={"task": "Say pong."},
        )
        self.assertEqual(started.status_code, 200, started.text)
        body = wait_for_chat(self.client, created.json()["id"])
        run = body["current_run"]
        self.assertEqual(run["status"], "completed", run.get("error"))
        self.assertEqual(run["source_surface"], "chat")
        self.assertEqual(run["effective_setup"]["selected_profile_id"], profile_id)
        self.assertNotIn(MEMORY_TOKEN, run["effective_setup"]["system_prompt"])
        self.assertIn(PROTECTED_TOKEN, run["effective_setup"]["system_prompt"])
        outbound = json.dumps(_RecordingHandler.requests[0]["body"])
        self.assertIn(MEMORY_TOKEN, outbound)
        self.assertIn(PROTECTED_TOKEN, outbound)
        self.assertAlmostEqual(_RecordingHandler.requests[0]["body"]["temperature"], DISTINCT_TEMPERATURE)
        denied = self.client.post(
            f"/v1/knowledge/entries/{protected['id']}/edit",
            json={
                "content": "overwrite-protected",
                "base_version": protected["current_version_id"],
                "provenance": AGENT,
            },
        )
        self.assertEqual(denied.status_code, 403)
        self.assertEqual(denied.json()["code"], "protected_instruction_denied")
        current = self.client.get(f"/v1/knowledge/entries/{protected['id']}").json()
        self.assertEqual(current["content"], PROTECTED_TOKEN)
        scope_denied = self.client.post(
            "/v1/knowledge/entries",
            json={
                "scope": "user",
                "kind": "memory",
                "content": "agent memory from chat path",
                "provenance": AGENT,
            },
        )
        self.assertEqual(scope_denied.status_code, 403)
        self.assertEqual(scope_denied.json()["code"], "scope_policy_denied")


class EffectiveSetupScriptedChatTests(unittest.TestCase):
    def setUp(self) -> None:
        reset_received_prompts()
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.project = self.root / "project"
        self.project.mkdir()
        self.app = create_app(data_root=self.root)
        self.manager = self.app.state.manager
        self.scripted = ScriptedChatModel([AIMessage(content="Noted.")])

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
            json={"endpoint": "http://127.0.0.1:9/v1", "display_name": "scripted"},
        ).json()["id"]

    def tearDown(self) -> None:
        close_workbench_sqlite(self.app, getattr(self, "client", None))
        self.tmp.cleanup()

    def test_scripted_harness_still_receives_loaded_knowledge_content(self) -> None:
        memory = self.client.post(
            "/v1/knowledge/entries",
            json={
                "scope": "project",
                "kind": "memory",
                "content": MEMORY_TOKEN,
                "provenance": HUMAN,
            },
        ).json()
        started = self.client.post(
            "/v1/agent-runs",
            json={
                "deployment_id": self.deployment_id,
                "task": "Continue.",
                "presented_tools": ["echo"],
                "memory_version_refs": [memory["current_version_id"]],
            },
        )
        self.assertEqual(started.status_code, 200, started.text)
        body = wait_for_run(self.client, started.json()["id"])
        self.assertEqual(body["status"], "completed", body.get("error"))
        self.assertNotIn(MEMORY_TOKEN, body["effective_setup"]["system_prompt"])
        capture = body["model_requests"][0]
        self.assertTrue(capture["loaded_knowledge"][0]["content_available"])
        received = "\n".join(RECEIVED_PROMPTS)
        self.assertIn(MEMORY_TOKEN, received)
        self.assertIn("<agent_memory>", received)
        if capture.get("http_payload"):
            self.assertIn(MEMORY_TOKEN, capture["instructions"] or "")
        else:
            self.assertIn("http payload not observed", " ".join(capture["capture_gaps"]))


class AdapterResolvedBagTests(unittest.TestCase):
    def setUp(self) -> None:
        _RecordingHandler.requests = []
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), _RecordingHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        host, port = self.server.server_address[:2]
        self.endpoint = f"http://{host}:{port}/v1"

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()

    def test_resolved_per_request_bag_is_sent_not_deployment_bag(self) -> None:
        now = utc_now()
        deployment = Deployment(
            id="deploy_adapter",
            display_name="adapter-test",
            scope=ManagementScope.connected,
            status=DeploymentStatus.running,
            endpoint=self.endpoint,
            created_at=now,
            updated_at=now,
            settings=SettingsBags(
                per_request=resolve_bag({"temperature": 0.9}, PER_REQUEST_KEYS),
            ),
        )
        resolved = resolve_bag({"temperature": DISTINCT_TEMPERATURE}, PER_REQUEST_KEYS)
        model = chat_model_for_deployment(deployment, per_request=resolved)
        result = model.invoke([HumanMessage(content="ping")])
        self.assertEqual(result.content, "pong")
        self.assertTrue(_RecordingHandler.requests)
        self.assertAlmostEqual(_RecordingHandler.requests[0]["body"]["temperature"], DISTINCT_TEMPERATURE)


if __name__ == "__main__":
    unittest.main()
