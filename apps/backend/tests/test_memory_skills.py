"""Official Deep Agents memory= / skills= glue (AGT-004 / STATE-005)."""

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
from langchain_core.messages import AIMessage

from workbench_backend.agents.harness import HarnessService
from workbench_backend.agents.harness_backend import build_run_backend
from workbench_backend.agents.host_shell import filesystem_permissions_for_run
from workbench_backend.agents.memory_skills import (
    SKILL_MATERIALIZE_INVALID,
    SKILL_NAME_COLLISION,
    official_agent_kwargs,
    plan_knowledge_materialization,
    skill_slug_from_entry_id,
    wrap_skill_markdown,
)
from workbench_backend.agents.schemas import AgentRun, AgentRunStatus
from workbench_backend.agents.tools import resolve_presented_tools
from workbench_backend.app import create_app
from workbench_backend.errors import HarnessError
from workbench_backend.inference.ids import utc_now
from workbench_backend.knowledge.schemas import KnowledgeVersion
from workbench_backend.paths import WorkbenchPaths

from tests.scripted_model import ScriptedChatModel
from tests.support import close_workbench_sqlite, workbench_client, offline_workbench_client

HUMAN = {"actor": "human", "note": "memory-skills"}
MEMORY_TOKEN = "MEM-TOKEN-MS-UNIQUE"
SKILL_BODY = "Use the review checklist before answering."


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


def _version(
    *,
    kind: str,
    content: str,
    entry_id: str = "kn_entry",
    version_id: str = "knv_entry",
    scope: str = "user",
) -> KnowledgeVersion:
    return KnowledgeVersion(
        id=version_id,
        entry_id=entry_id,
        scope=scope,  # type: ignore[arg-type]
        kind=kind,  # type: ignore[arg-type]
        content=content,
        provenance={"actor": "human"},
        created_at=utc_now(),
    )


def _run(*, skill_refs: list[str] | None = None, memory_refs: list[str] | None = None) -> AgentRun:
    now = utc_now()
    return AgentRun(
        id="agent_memory_skills",
        status=AgentRunStatus.queued,
        deployment_id="deploy_test",
        task="unit",
        enabled_tools=["echo"],
        presented_tools=["echo"],
        created_at=now,
        updated_at=now,
        memory_version_refs=list(memory_refs or []),
        skill_version_refs=list(skill_refs or []),
    )


class MemorySkillsGlueTests(unittest.TestCase):
    def test_hyphenates_entry_id_and_wraps_frontmatter(self) -> None:
        self.assertEqual(skill_slug_from_entry_id("kn_abc123"), "kn-abc123")
        wrapped = wrap_skill_markdown("kn-abc123", SKILL_BODY, "Review skill")
        self.assertTrue(wrapped.startswith("---\n"))
        self.assertIn("name: kn-abc123", wrapped)
        self.assertIn("description: Review skill", wrapped)
        self.assertIn(SKILL_BODY, wrapped)
        self.assertGreater(wrapped.index("---", 4), wrapped.index("name: kn-abc123"))

    def test_existing_frontmatter_keeps_extra_and_forces_name(self) -> None:
        body = "---\nname: wrong-name\ndescription: Already described\nlicense: MIT\n---\n\nBody stays.\n"
        wrapped = wrap_skill_markdown("kn-forced", body, "Ignored display")
        self.assertIn("name: kn-forced", wrapped)
        self.assertNotIn("name: wrong-name", wrapped)
        self.assertIn("description: Already described", wrapped)
        self.assertIn("license: MIT", wrapped)
        self.assertIn("Body stays.", wrapped)

    def test_invalid_slug_and_collision_fail_closed(self) -> None:
        with self.assertRaises(HarnessError) as invalid:
            skill_slug_from_entry_id("???")
        self.assertEqual(invalid.exception.code, SKILL_MATERIALIZE_INVALID)
        with self.assertRaises(HarnessError) as collision:
            plan_knowledge_materialization(
                [
                    _version(kind="skill", content="one", entry_id="kn_ab", version_id="knv_1"),
                    _version(kind="skill", content="two", entry_id="kn-ab", version_id="knv_2"),
                ]
            )
        self.assertEqual(collision.exception.code, SKILL_NAME_COLLISION)

    def test_omit_empty_official_kwargs(self) -> None:
        empty = plan_knowledge_materialization([])
        self.assertEqual(official_agent_kwargs(empty), {})
        memory_only = plan_knowledge_materialization(
            [_version(kind="memory", content=MEMORY_TOKEN, entry_id="kn_mem", version_id="knv_mem")]
        )
        self.assertEqual(list(official_agent_kwargs(memory_only)), ["memory"])
        self.assertEqual(memory_only.memory_sources, ["/memories/user/kn_mem.md"])
        self.assertNotIn("skills", official_agent_kwargs(memory_only))
        skill_only = plan_knowledge_materialization(
            [_version(kind="skill", content=SKILL_BODY, entry_id="kn_skill", version_id="knv_skill")],
            {"kn_skill": "Review"},
        )
        kwargs = official_agent_kwargs(skill_only)
        self.assertEqual(kwargs, {"skills": ["/skills/"]})
        self.assertTrue(skill_only.uploads[0][0].endswith("/SKILL.md"))

    def test_projectless_tools_and_skills_write_deny(self) -> None:
        presented, denied, blocked, shell = resolve_presented_tools(
            None,
            project_bound=False,
            knowledge_routes=True,
        )
        self.assertEqual(presented, ["echo", "time_now", "write_todos", "ask_user", "ls", "read_file"])
        self.assertEqual(denied, [])
        self.assertEqual(blocked, [])
        self.assertEqual(shell, [])
        _, _, write_blocked, _ = resolve_presented_tools(
            ["write_file"],
            project_bound=False,
            knowledge_routes=True,
        )
        self.assertEqual(write_blocked, ["write_file"])
        self.assertIsNone(filesystem_permissions_for_run(_run()))
        skills_rules = filesystem_permissions_for_run(_run(skill_refs=["knv_skill"]))
        self.assertIsNotNone(skills_rules)
        assert skills_rules is not None
        self.assertEqual(skills_rules[-1].paths, ["/skills/**"])
        self.assertEqual(skills_rules[-1].mode, "deny")
        self.assertEqual(skills_rules[-1].operations, ["write"])


class _RecordingHandler(BaseHTTPRequestHandler):
    requests: list[dict[str, Any]] = []

    def do_GET(self) -> None:  # noqa: N802
        self._json(200, {"data": [{"id": "fake-llama"}]})

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length)
        body = json.loads(raw.decode("utf-8")) if raw else {}
        self.requests.append({"path": self.path, "body": body})
        if body.get("stream"):
            self._sse(
                200,
                [
                    {
                        "id": "memory-skills",
                        "object": "chat.completion.chunk",
                        "choices": [
                            {"index": 0, "delta": {"role": "assistant", "content": "pong"}, "finish_reason": None}
                        ],
                    },
                    {
                        "id": "memory-skills",
                        "object": "chat.completion.chunk",
                        "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
                    },
                ],
            )
            return
        self._json(
            200,
            {
                "id": "memory-skills",
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

    def _sse(self, status: int, events: list[dict[str, object]]) -> None:
        body = "".join(f"data: {json.dumps(event)}\n\n" for event in events) + "data: [DONE]\n\n"
        encoded = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)


class MemorySkillsHarnessTests(unittest.TestCase):
    def setUp(self) -> None:
        _RecordingHandler.requests = []
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), _RecordingHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        host, port = self.server.server_address[:2]
        self.endpoint = f"http://{host}:{port}/v1"
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.app = create_app(data_root=self.root)
        self.client = workbench_client(self.app)
        self.deployment_id = self.client.post(
            "/v1/deployments/connected",
            json={"endpoint": self.endpoint, "display_name": "memory-skills"},
        ).json()["id"]

    def tearDown(self) -> None:
        close_workbench_sqlite(self.app, getattr(self, "client", None))
        self.server.shutdown()
        self.server.server_close()
        self.tmp.cleanup()

    def _knowledge(self, kind: str, content: str, *, entry_id_note: str = "") -> dict[str, Any]:
        payload = {
            "scope": "user",
            "kind": kind,
            "content": content,
            "display_name": f"{kind}-ms{entry_id_note}",
            "provenance": HUMAN,
        }
        return self.client.post("/v1/knowledge/entries", json=payload).json()

    def test_omits_memory_kwarg_when_only_skill_selected(self) -> None:
        skill = self._knowledge("skill", SKILL_BODY)
        started = self.client.post(
            "/v1/agent-runs",
            json={
                "deployment_id": self.deployment_id,
                "task": "Say pong.",
                "presented_tools": ["echo"],
                "skill_version_refs": [skill["current_version_id"]],
            },
        )
        self.assertEqual(started.status_code, 200, started.text)
        body = wait_for_run(self.client, started.json()["id"])
        self.assertEqual(body["status"], "completed", body.get("error"))
        setup = body["effective_setup"]
        kinds = {item["kind"] for item in setup["materialized_knowledge"]}
        self.assertEqual(kinds, {"skill"})
        outbound = json.dumps(_RecordingHandler.requests[0]["body"])
        self.assertIn("## Skills System", outbound)
        self.assertNotIn("<agent_memory>", outbound)
        self.assertNotIn(SKILL_BODY, outbound)

    def test_skill_name_collision_fails_closed_before_run(self) -> None:
        first = self._knowledge("skill", "one")
        second = self._knowledge("skill", "two")
        # Force a collision by planning two hyphen-equivalent ids.
        with self.assertRaises(HarnessError) as raised:
            plan_knowledge_materialization(
                [
                    _version(
                        kind="skill",
                        content="one",
                        entry_id=first["id"],
                        version_id=first["current_version_id"],
                    ),
                    _version(
                        kind="skill",
                        content="two",
                        entry_id=first["id"].replace("_", "-"),
                        version_id=second["current_version_id"],
                    ),
                ]
            )
        self.assertEqual(raised.exception.code, SKILL_NAME_COLLISION)

    def test_projectless_chat_auto_presents_knowledge_reads(self) -> None:
        memory = self._knowledge("memory", MEMORY_TOKEN)
        created = self.client.post(
            "/v1/chat/conversations",
            json={
                "deployment_id": self.deployment_id,
                "memory_version_refs": [memory["current_version_id"]],
            },
        )
        self.assertEqual(created.status_code, 200, created.text)
        self.assertFalse(created.json()["filesystem_tools_available"])
        started = self.client.post(
            f"/v1/chat/conversations/{created.json()['id']}/start",
            json={"task": "Say pong.", "presented_tools": ["echo"]},
        )
        self.assertEqual(started.status_code, 200, started.text)
        self.assertFalse(started.json()["filesystem_tools_available"])
        run = started.json()["current_run"]
        self.assertIn("ls", run["presented_tools"])
        self.assertIn("read_file", run["presented_tools"])
        self.assertNotIn("write_file", run["presented_tools"])
        finished = wait_for_run(self.client, run["id"])
        self.assertEqual(finished["status"], "completed", finished.get("error"))
        blocked = self.client.post(
            f"/v1/chat/conversations/{created.json()['id']}/start",
            json={"task": "Write.", "presented_tools": ["write_file"]},
        )
        self.assertEqual(blocked.status_code, 400, blocked.text)
        self.assertEqual(blocked.json()["code"], "filesystem_requires_project")


class MemorySkillsScratchEditTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.app = create_app(data_root=self.root)
        self.manager = self.app.state.manager
        self.scripted: ScriptedChatModel | None = None

        def factory(_run: AgentRun, _sink: list[dict[str, Any]]) -> ScriptedChatModel:
            assert self.scripted is not None
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
            json={"endpoint": "http://127.0.0.1:9/v1", "display_name": "scripted-ms"},
        ).json()["id"]

    def tearDown(self) -> None:
        close_workbench_sqlite(self.app, getattr(self, "client", None))
        self.tmp.cleanup()

    def test_memory_edit_is_not_a_knowledge_version(self) -> None:
        memory = self.client.post(
            "/v1/knowledge/entries",
            json={
                "scope": "user",
                "kind": "memory",
                "content": MEMORY_TOKEN,
                "display_name": "user-memory",
                "provenance": HUMAN,
            },
        ).json()
        path = f"/memories/user/{memory['id']}.md"
        self.scripted = ScriptedChatModel(
            [
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "edit_file",
                            "args": {
                                "file_path": path,
                                "old_string": MEMORY_TOKEN,
                                "new_string": "scratch-only-edit",
                            },
                            "id": "call_edit_mem",
                        }
                    ],
                ),
                AIMessage(content="Edited scratch memory."),
            ]
        )
        started = self.client.post(
            "/v1/agent-runs",
            json={
                "deployment_id": self.deployment_id,
                "task": "Edit memory.",
                "presented_tools": ["echo"],
                "memory_version_refs": [memory["current_version_id"]],
            },
        )
        self.assertEqual(started.status_code, 200, started.text)
        body = wait_for_run(self.client, started.json()["id"])
        self.assertEqual(body["status"], "completed", body.get("error"))
        current = self.client.get(f"/v1/knowledge/entries/{memory['id']}").json()
        self.assertEqual(current["content"], MEMORY_TOKEN)
        self.assertEqual(current["current_version_id"], memory["current_version_id"])
        backend = build_run_backend(
            AgentRun.model_validate(
                {
                    **body,
                    "memory_version_refs": [memory["current_version_id"]],
                }
            ),
            WorkbenchPaths(self.root).ensure(),
        )
        self.assertIsNotNone(backend)
        downloaded = backend.download_files([path])  # type: ignore[union-attr]
        self.assertIsNone(downloaded[0].error)
        self.assertIn(b"scratch-only-edit", downloaded[0].content or b"")


if __name__ == "__main__":
    unittest.main()
