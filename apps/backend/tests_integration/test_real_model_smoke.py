"""Real-model smoke: the product against a real llama-server and a real tiny GGUF.

Proves plumbing, not model capability: attach + health, one Chat turn that
produces a real ``write_file`` tool call and a file in the project, a
follow-up turn that resumes the same thread at the wire, and a profile's
per-request bag reaching the outbound request body. Assertions target the
product's own API responses and recorded run state, never model prose.

Run explicitly (never picked up by ``-s tests``):

    uv run python -m unittest discover -s tests_integration -t . -p "test_*.py"

Assets are resolved, not downloaded, by the tests. Missing assets skip the
module unless ``WORKBENCH_REAL_MODEL_SMOKE`` is set to a truthy value
(``required``, ``1``, ``true``, ``yes``, ``on``), which fails instead (CI).
``0``/``false``/``no``/``off``/``skip`` keep the skip.

Known quirk: the 0.5B model writes ``/large_tool_results/hello.txt`` rather
than ``/hello.txt`` — it copies the only absolute directory in its prompt,
from the Deep Agents ``grep`` tool description ("Offloaded large tool
results live under ... /large_tool_results/"). With the bare
``FilesystemBackend(root_dir=project)`` that path lands inside the project,
so the STATE-002 assertion (written file inside the project) holds. If a
``CompositeBackend`` later routes ``/large_tool_results/`` elsewhere, this
exact output will no longer create a project file: adjust ``WRITE_TASK``
(for example, ask for ``/hello.txt`` explicitly) in that change.
"""

from __future__ import annotations

import os
import socket
import subprocess
import tempfile
import time
import unittest
from pathlib import Path
from typing import Any

import httpx
from fastapi.testclient import TestClient

from workbench_backend.app import create_app

from tests.support import close_workbench_sqlite, workbench_client
from tests_integration.assets import SmokeAssets, SmokeAssetsUnavailable, resolve_assets

REQUIRED_ENV = "WORKBENCH_REAL_MODEL_SMOKE"
REQUIRED_VALUES = frozenset({"required", "1", "true", "yes", "on"})
SKIP_VALUES = frozenset({"", "0", "false", "no", "off", "skip"})
SERVER_READY_TIMEOUT = 120.0
# Transport/wait bound for a tiny CPU model; not a product task budget (AGT-003).
RUN_TIMEOUT = 240.0
FILE_CONTENT = "hello from qwen"
WRITE_TASK = f"Create a file named hello.txt containing exactly: {FILE_CONTENT}"
FOLLOW_UP_TASK = "Reply with only the name of the file you created."
PROFILE_TEMPERATURE = 0.1
PROFILE_TOP_K = 20
PROFILE_MIN_P = 0.05
PROFILE_MAX_TOKENS = 64
PROFILE_SEED = 11


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _smoke_required() -> bool:
    value = os.environ.get(REQUIRED_ENV, "").strip().lower()
    if value in REQUIRED_VALUES:
        return True
    if value in SKIP_VALUES:
        return False
    raise ValueError(
        f"{REQUIRED_ENV}={value!r} is not recognised; use one of "
        f"{sorted(REQUIRED_VALUES)} to require the tier or {sorted(SKIP_VALUES - {''})} to allow a skip."
    )


def _load_assets() -> SmokeAssets:
    required = _smoke_required()
    try:
        return resolve_assets()
    except SmokeAssetsUnavailable as exc:
        if required:
            raise
        raise unittest.SkipTest(
            f"real-model smoke assets unavailable: {exc} "
            f"(set {REQUIRED_ENV}=required to fail instead of skipping)"
        ) from exc


class RealLlamaServer:
    """Owns one real llama-server subprocess for the whole module."""

    def __init__(self, assets: SmokeAssets, log_path: Path) -> None:
        self.assets = assets
        self.port = _free_port()
        self.endpoint = f"http://127.0.0.1:{self.port}/v1"
        self.log_path = log_path
        self._log = log_path.open("wb")
        self.process = subprocess.Popen(
            [
                str(assets.llama_server),
                "-m",
                str(assets.model),
                "--host",
                "127.0.0.1",
                "--port",
                str(self.port),
                "-c",
                "8192",
                "--jinja",
            ],
            cwd=str(assets.llama_server.parent),
            stdout=self._log,
            stderr=subprocess.STDOUT,
        )

    def wait_ready(self, timeout: float = SERVER_READY_TIMEOUT) -> None:
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.process.poll() is not None:
                raise RuntimeError(f"llama-server exited early ({self.process.returncode}):\n{self.log_tail()}")
            try:
                if httpx.get(f"http://127.0.0.1:{self.port}/health", timeout=2.0).status_code == 200:
                    return
            except httpx.HTTPError:
                pass
            time.sleep(0.2)
        raise TimeoutError(f"llama-server not healthy after {timeout}s:\n{self.log_tail()}")

    def log_tail(self, lines: int = 40) -> str:
        self._log.flush()
        try:
            return "\n".join(self.log_path.read_text(encoding="utf-8", errors="replace").splitlines()[-lines:])
        except OSError:
            return "<log unavailable>"

    def close(self) -> None:
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=15)
        self._log.close()


def wait_for_chat(client: TestClient, conversation_id: str, *, timeout: float = RUN_TIMEOUT) -> dict[str, Any]:
    deadline = time.time() + timeout
    body: dict[str, Any] = {}
    while time.time() < deadline:
        body = client.get(f"/v1/chat/conversations/{conversation_id}").json()
        run = body.get("current_run") or {}
        if run.get("status") in {"completed", "cancelled", "failed"}:
            return body
        time.sleep(0.2)
    raise TimeoutError(f"chat {conversation_id} did not finish: {body}")


def wait_for_run(client: TestClient, run_id: str, *, timeout: float = RUN_TIMEOUT) -> dict[str, Any]:
    deadline = time.time() + timeout
    body: dict[str, Any] = {}
    while time.time() < deadline:
        body = client.get(f"/v1/agent-runs/{run_id}").json()
        if body.get("status") in {"completed", "cancelled", "failed"}:
            return body
        time.sleep(0.2)
    raise TimeoutError(f"run {run_id} did not finish: {body}")


class RealModelSmokeTests(unittest.TestCase):
    server: RealLlamaServer
    server_tmp: tempfile.TemporaryDirectory[str]

    @classmethod
    def setUpClass(cls) -> None:
        assets = _load_assets()
        cls.server_tmp = tempfile.TemporaryDirectory()
        cls.server = RealLlamaServer(assets, Path(cls.server_tmp.name) / "llama-server.log")
        try:
            cls.server.wait_ready()
        except Exception:
            cls.server.close()
            cls.server_tmp.cleanup()
            raise

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.close()
        cls.server_tmp.cleanup()

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.project = self.root / "project"
        self.project.mkdir()
        self.app = create_app(data_root=self.root)
        self.client = workbench_client(self.app)

    def tearDown(self) -> None:
        close_workbench_sqlite(self.app, self.client)
        self.tmp.cleanup()

    def _attach(self) -> dict[str, Any]:
        response = self.client.post(
            "/v1/deployments/connected",
            json={"endpoint": self.server.endpoint, "display_name": "real-model-smoke"},
        )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def _profile(self, per_request: dict[str, Any], *, startup: dict[str, Any] | None = None) -> str:
        response = self.client.post(
            "/v1/profiles",
            json={
                "display_name": "real-model-smoke-profile",
                "startup": startup or {},
                "per_request": per_request,
                "agent": {},
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()["id"]

    def _start_chat(self, conversation_id: str, task: str) -> dict[str, Any]:
        response = self.client.post(f"/v1/chat/conversations/{conversation_id}/start", json={"task": task})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def _first_http_body(self, run: dict[str, Any]) -> dict[str, Any]:
        self.assertTrue(run["model_requests"], "no model request was captured")
        capture = run["model_requests"][0]
        self.assertNotIn("http payload not observed", " ".join(capture["capture_gaps"]))
        payload = capture["http_payload"]
        self.assertIsNotNone(payload, "HTTP payload was not recorded")
        self.assertTrue(payload["url"].startswith(self.server.endpoint), payload["url"])
        return payload["body"]

    def test_attach_connected_deployment_reports_healthy(self) -> None:
        deployment = self._attach()
        self.assertEqual(deployment["scope"], "connected")
        self.assertEqual(deployment["status"], "running")
        self.assertTrue(deployment["health"]["healthy"], deployment["health"])
        self.assertEqual(deployment["endpoint"], self.server.endpoint)

        probed = self.client.get(f"/v1/deployments/{deployment['id']}/health")
        self.assertEqual(probed.status_code, 200, probed.text)
        body = probed.json()
        self.assertTrue(body["health"]["healthy"], body["health"])
        self.assertIn("-> 200", body["health"]["detail"])
        self.assertEqual(body["status"], "running")
        self.assertFalse(body["resource_usage"]["available"])

    def test_chat_turn_writes_file_then_follow_up_resumes_thread(self) -> None:
        deployment = self._attach()
        profile_id = self._profile({"temperature": 0.0, "seed": 7, "max_tokens": 128})
        created = self.client.post(
            "/v1/chat/conversations",
            json={"deployment_id": deployment["id"], "profile_id": profile_id, "project_path": str(self.project)},
        )
        self.assertEqual(created.status_code, 200, created.text)
        conversation = created.json()

        self._start_chat(conversation["id"], WRITE_TASK)
        first = wait_for_chat(self.client, conversation["id"])
        run = first["current_run"]
        self.assertEqual(run["status"], "completed", f"{run.get('error')}\n{self.server.log_tail()}")
        self.assertEqual(run["source_surface"], "chat")
        self.assertEqual(run["thread_id"], conversation["thread_id"])
        self.assertTrue(run["checkpoint_ids"], "run was not linked to LangGraph checkpoints")

        write_calls = [item for item in run["tool_invocations"] if item["name"] == "write_file"]
        self.assertTrue(write_calls, f"no write_file call; invocations={run['tool_invocations']}")
        kinds = [event["kind"] for event in run["events"]]
        self.assertIn("tool_call", kinds)
        self.assertIn("tool_result", kinds)

        written = [item for item in run["related_files"] if item["kind"] == "written_file"]
        self.assertTrue(written, f"no written_file recorded; related_files={run['related_files']}")
        written_path = Path(written[0]["path"]).resolve()
        self.assertTrue(written_path.is_relative_to(self.project.resolve()), written_path)
        self.assertTrue(written_path.is_file(), f"{written_path} was not created on disk")
        on_disk = written_path.read_text(encoding="utf-8")
        self.assertIn(str(write_calls[0]["args"].get("content", "")).strip(), on_disk)
        self.assertTrue(on_disk.strip())

        body = self._first_http_body(run)
        tool_names = {tool["function"]["name"] for tool in body.get("tools", [])}
        self.assertIn("write_file", tool_names)
        self.assertEqual(body["messages"][-1]["role"], "user")
        self.assertEqual(body["messages"][-1]["content"], WRITE_TASK)
        first_run_id = run["id"]

        self._start_chat(conversation["id"], FOLLOW_UP_TASK)
        second = wait_for_chat(self.client, conversation["id"])
        follow_up = second["current_run"]
        self.assertEqual(follow_up["status"], "completed", f"{follow_up.get('error')}\n{self.server.log_tail()}")
        self.assertNotEqual(follow_up["id"], first_run_id)
        self.assertEqual(follow_up["thread_id"], conversation["thread_id"])
        self.assertEqual(second["thread_id"], conversation["thread_id"])
        self.assertEqual(second["run_ids"], [first_run_id, follow_up["id"]])
        self.assertEqual(second["continuity"]["run_ids"], [first_run_id, follow_up["id"]])

        wire = self._first_http_body(follow_up)["messages"]
        roles = [message["role"] for message in wire]
        self.assertEqual(roles[-1], "user")
        self.assertEqual(wire[-1]["content"], FOLLOW_UP_TASK)
        self.assertIn("tool", roles, f"prior tool result missing from resumed thread: {roles}")
        prior_calls = {
            call["function"]["name"]
            for message in wire
            if message["role"] == "assistant"
            for call in message.get("tool_calls") or []
        }
        self.assertIn("write_file", prior_calls, f"prior write_file call missing at the wire: {roles}")
        self.assertTrue(any(message["role"] == "user" and message["content"] == WRITE_TASK for message in wire))
        self.assertIn("assistant_message", [event["kind"] for event in follow_up["events"]])
        self.assertGreaterEqual(len(follow_up["checkpoint_ids"]), 1)

    def test_profile_per_request_settings_reach_outbound_request(self) -> None:
        deployment = self._attach()
        profile_id = self._profile(
            {
                "temperature": PROFILE_TEMPERATURE,
                "top_k": PROFILE_TOP_K,
                "min_p": PROFILE_MIN_P,
                "max_tokens": PROFILE_MAX_TOKENS,
                "seed": PROFILE_SEED,
                "bogus_setting": 1,
            },
            startup={"ctx_size": 8192},
        )
        started = self.client.post(
            "/v1/agent-runs",
            json={
                "deployment_id": deployment["id"],
                "profile_id": profile_id,
                "task": "Reply with the single word PONG.",
                "presented_tools": ["echo"],
            },
        )
        self.assertEqual(started.status_code, 200, started.text)
        run = wait_for_run(self.client, started.json()["id"])
        self.assertEqual(run["status"], "completed", f"{run.get('error')}\n{self.server.log_tail()}")

        body = self._first_http_body(run)
        self.assertAlmostEqual(body["temperature"], PROFILE_TEMPERATURE)
        self.assertEqual(body["top_k"], PROFILE_TOP_K)
        self.assertAlmostEqual(body["min_p"], PROFILE_MIN_P)
        self.assertEqual(body["seed"], PROFILE_SEED)
        self.assertEqual(body["max_completion_tokens"], PROFILE_MAX_TOKENS)
        self.assertNotIn("bogus_setting", body)
        self.assertEqual({tool["function"]["name"] for tool in body.get("tools", [])}, {"echo"})

        setup = run["effective_setup"]
        self.assertEqual(setup["selected_profile_id"], profile_id)
        self.assertAlmostEqual(setup["bags"]["per_request"]["applied"]["temperature"], PROFILE_TEMPERATURE)
        self.assertIn("bogus_setting", setup["unsupported"]["per_request"])
        self.assertIn("ctx_size", [item["key"] for item in setup["startup_mismatches"]])
        capture = run["model_requests"][0]
        self.assertEqual(capture["selected_profile_id"], profile_id)
        self.assertAlmostEqual(capture["applied_per_request"]["temperature"], PROFILE_TEMPERATURE)
        self.assertIn("assistant_message", [event["kind"] for event in run["events"]])


if __name__ == "__main__":
    unittest.main()
