"""STATE-006 retrieve-and-offload. Fake embeddings only — not live RAG proof."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from typing import Any

from deepagents.backends.protocol import FileUploadResponse
from langchain_core.embeddings import DeterministicFakeEmbedding
from langchain_core.messages import AIMessage
from langchain_core.vectorstores import InMemoryVectorStore

from workbench_backend.agents.harness import HarnessService
from workbench_backend.agents.harness_backend import harness_scratch_root
from workbench_backend.agents.retrieval import (
    SEARCH_KNOWLEDGE_TOOL_NAME,
    TREAT_AS_DATA,
    build_vector_store,
    documents_from_knowledge,
    make_search_knowledge_tool,
)
from workbench_backend.agents.schemas import AgentRun, ToolMode
from workbench_backend.app import create_app
from workbench_backend.inference.ids import utc_now
from workbench_backend.inference.schemas import Deployment, DeploymentStatus, ManagementScope
from workbench_backend.inference.service import ModelManager
from workbench_backend.knowledge.schemas import KnowledgeVersion
from workbench_backend.paths import WorkbenchPaths

from tests.scripted_model import ScriptedChatModel
from tests.support import close_workbench_sqlite, workbench_client
from tests.test_harness import echo_then_reply, wait_for_run

MEMORY_TOKEN = "STATE006-UNIQUE-MEMORY-CHUNK-FOR-FAKE-EMBEDDINGS"


def search_then_reply() -> list[AIMessage]:
    return [
        AIMessage(
            content="",
            tool_calls=[
                {
                    "name": SEARCH_KNOWLEDGE_TOOL_NAME,
                    "args": {"query": "unique memory chunk"},
                    "id": "call_search",
                }
            ],
        ),
        AIMessage(content="Used the retrieved knowledge paths."),
    ]


class RetrievalUnitTests(unittest.TestCase):
    def test_official_splitter_store_and_offload_paths(self) -> None:
        version = KnowledgeVersion(
            id="knv_mem",
            entry_id="kn_mem",
            scope="user",
            kind="memory",
            content=MEMORY_TOKEN,
            provenance={"actor": "human"},
            created_at=utc_now(),
        )
        documents = documents_from_knowledge([version])
        self.assertEqual(len(documents), 1)
        self.assertEqual(documents[0].metadata["source"], "knowledge:knv_mem")
        store = build_vector_store(documents, DeterministicFakeEmbedding(size=32))
        self.assertIsInstance(store, InMemoryVectorStore)
        hits = store.similarity_search(MEMORY_TOKEN, k=2)
        self.assertTrue(hits)

        class _Backend:
            def __init__(self) -> None:
                self.files: dict[str, bytes] = {}

            def upload_files(self, files: list[tuple[str, bytes]]) -> list[FileUploadResponse]:
                uploaded: list[FileUploadResponse] = []
                for path, content in files:
                    self.files[path] = content
                    uploaded.append(FileUploadResponse(path=path, error=None))
                return uploaded

        recorded: list[str] = []
        backend = _Backend()
        tool = make_search_knowledge_tool(
            store,
            backend,  # type: ignore[arg-type]
            on_retrieved=recorded.extend,
        )
        result = tool.invoke({"query": MEMORY_TOKEN})
        self.assertIn("/retrieved/", result)
        self.assertTrue(backend.files)
        path = next(iter(backend.files))
        self.assertTrue(path.startswith("/retrieved/"))
        text = backend.files[path].decode("utf-8")
        self.assertIn("knowledge:knv_mem", text)
        self.assertIn(TREAT_AS_DATA, text)
        self.assertTrue(recorded)


class RetrievalHarnessTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.manager = ModelManager(WorkbenchPaths(self.root).ensure())
        self.app = create_app(data_root=self.root)
        self.app.state.manager = self.manager
        self.scripted = ScriptedChatModel(search_then_reply())

        def factory(_run: AgentRun, _sink: list[dict[str, Any]]) -> ScriptedChatModel:
            return self.scripted

        def embeddings(_deployment: object) -> DeterministicFakeEmbedding:
            return DeterministicFakeEmbedding(size=32)

        self.app.state.harness = HarnessService(
            lambda: self.manager,
            model_factory=factory,
            knowledge_provider=lambda: self.app.state.knowledge,
            embeddings_factory=embeddings,
        )
        self.client = workbench_client(self.app)
        self.chat_deployment_id = self.client.post(
            "/v1/deployments/connected",
            json={"endpoint": "http://127.0.0.1:9/v1", "display_name": "chat-fixture"},
        ).json()["id"]
        self.embed_deployment_id = self.client.post(
            "/v1/deployments/connected",
            json={
                "endpoint": "http://127.0.0.1:9/v1",
                "display_name": "embedder-fixture",
                "startup": {"embedding": "on", "pooling": "mean"},
            },
        ).json()["id"]

    def tearDown(self) -> None:
        close_workbench_sqlite(self.app, getattr(self, "client", None))
        self.tmp.cleanup()

    def _knowledge(self, content: str = MEMORY_TOKEN) -> dict[str, Any]:
        return self.client.post(
            "/v1/knowledge/entries",
            json={
                "scope": "user",
                "kind": "memory",
                "content": content,
                "display_name": "state-006",
                "provenance": {"actor": "human", "note": "retrieval-test"},
            },
        ).json()

    def test_knowledge_without_embedding_id_does_not_request_retrieval(self) -> None:
        memory = self._knowledge()
        started = self.client.post(
            "/v1/agent-runs",
            json={
                "deployment_id": self.chat_deployment_id,
                "task": "Echo only.",
                "presented_tools": ["echo"],
                "memory_version_refs": [memory["current_version_id"]],
            },
        )
        self.assertEqual(started.status_code, 200, started.text)
        body = wait_for_run(self.client, started.json()["id"])
        self.assertNotIn(SEARCH_KNOWLEDGE_TOOL_NAME, body["presented_tools"])
        self.assertIn("no retrieval", " ".join(body["effective_setup"]["gaps"]))
        self.assertEqual(body["model_requests"][0]["retrieved_material"], [])

    def test_missing_embedding_deployment_fails_closed(self) -> None:
        memory = self._knowledge()
        response = self.client.post(
            "/v1/agent-runs",
            json={
                "deployment_id": self.chat_deployment_id,
                "task": "Search knowledge.",
                "memory_version_refs": [memory["current_version_id"]],
                "embedding_deployment_id": "deploy_missing_embedder",
            },
        )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["code"], "embedding_deployment_missing")

    def test_chat_deployment_without_embedding_flag_fails_closed(self) -> None:
        memory = self._knowledge()
        response = self.client.post(
            "/v1/agent-runs",
            json={
                "deployment_id": self.chat_deployment_id,
                "task": "Search knowledge.",
                "memory_version_refs": [memory["current_version_id"]],
                "embedding_deployment_id": self.chat_deployment_id,
            },
        )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["code"], "embedding_not_configured")

    def test_unloaded_managed_embedder_fails_closed(self) -> None:
        memory = self._knowledge()
        now = utc_now()
        stopped = Deployment(
            id="deploy_stopped_embed",
            display_name="stopped-embedder",
            scope=ManagementScope.managed,
            status=DeploymentStatus.stopped,
            endpoint=None,
            applied_startup={"embedding": "on", "pooling": "mean"},
            created_at=now,
            updated_at=now,
        )
        self.manager.store.put_deployment(stopped)
        response = self.client.post(
            "/v1/agent-runs",
            json={
                "deployment_id": self.chat_deployment_id,
                "task": "Search knowledge.",
                "memory_version_refs": [memory["current_version_id"]],
                "embedding_deployment_id": stopped.id,
            },
        )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["code"], "embedding_deployment_unloaded")

    def test_empty_corpus_fails_closed(self) -> None:
        response = self.client.post(
            "/v1/agent-runs",
            json={
                "deployment_id": self.chat_deployment_id,
                "task": "Search knowledge.",
                "embedding_deployment_id": self.embed_deployment_id,
            },
        )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["code"], "retrieval_corpus_empty")

    def test_live_search_writes_retrieved_under_scratch_not_project(self) -> None:
        memory = self._knowledge()
        project = self.root / "retrieval-project"
        project.mkdir()
        (project / "notes.md").write_text("project allowlist text about widgets", encoding="utf-8")
        started = self.client.post(
            "/v1/agent-runs",
            json={
                "deployment_id": self.chat_deployment_id,
                "task": "Search the knowledge store.",
                "presented_tools": ["echo"],
                "project_path": str(project),
                "memory_version_refs": [memory["current_version_id"]],
                "embedding_deployment_id": self.embed_deployment_id,
                "retrieval_project_paths": ["notes.md"],
            },
        )
        self.assertEqual(started.status_code, 200, started.text)
        queued = started.json()
        self.assertIn(SEARCH_KNOWLEDGE_TOOL_NAME, queued["presented_tools"])
        self.assertTrue(queued["effective_setup"]["retrieval_presented"])
        self.assertNotIn("no retrieval", " ".join(queued["effective_setup"]["gaps"]))
        body = wait_for_run(self.client, queued["id"])
        self.assertEqual(body["status"], "completed", body.get("error"))
        names = [item["name"] for item in body["tool_invocations"]]
        self.assertIn(SEARCH_KNOWLEDGE_TOOL_NAME, names)
        self.assertTrue(body["retrieved_material"])
        captures = [item["retrieved_material"] for item in body["model_requests"]]
        self.assertTrue(any(item for item in captures))
        thread_id = body["thread_id"]
        scratch = harness_scratch_root(self.manager.paths, thread_id)
        retrieved_files = list((scratch / "retrieved").rglob("chunk_*.md"))
        self.assertTrue(retrieved_files)
        self.assertIn("Source:", retrieved_files[0].read_text(encoding="utf-8"))
        self.assertFalse((project / "retrieved").exists())
        self.assertFalse(any(self.root.rglob("chroma*")))

    def test_recorded_tool_does_not_attach_live_index(self) -> None:
        memory = self._knowledge()
        self.scripted = ScriptedChatModel(echo_then_reply())

        def factory(_run: AgentRun, _sink: list[dict[str, Any]]) -> ScriptedChatModel:
            return self.scripted

        self.app.state.harness = HarnessService(
            lambda: self.manager,
            model_factory=factory,
            knowledge_provider=lambda: self.app.state.knowledge,
            embeddings_factory=lambda _deployment: DeterministicFakeEmbedding(size=32),
        )
        started = self.client.post(
            "/v1/agent-runs",
            json={
                "deployment_id": self.chat_deployment_id,
                "task": "Replay only.",
                "presented_tools": ["echo"],
                "tool_mode": "recorded-tool",
                "recorded_fixtures": [
                    {"name": "echo", "args": {"text": "harness-ok"}, "result": "harness-ok"}
                ],
                "memory_version_refs": [memory["current_version_id"]],
                "embedding_deployment_id": self.embed_deployment_id,
            },
        )
        self.assertEqual(started.status_code, 200, started.text)
        body = wait_for_run(self.client, started.json()["id"])
        self.assertNotIn(SEARCH_KNOWLEDGE_TOOL_NAME, body["presented_tools"])
        self.assertTrue(body["effective_setup"]["retrieval_requested"])
        self.assertFalse(body["effective_setup"]["retrieval_presented"])
        self.assertIn("recorded-tool replay", " ".join(body["effective_setup"]["gaps"]))
        self.assertFalse(any(self.manager.paths.state.joinpath("harness").rglob("chunk_*.md")))

    def test_pooling_none_fails_closed(self) -> None:
        memory = self._knowledge()
        now = utc_now()
        bad = Deployment(
            id="deploy_pool_none",
            display_name="pool-none",
            scope=ManagementScope.connected,
            status=DeploymentStatus.running,
            endpoint="http://127.0.0.1:9/v1",
            applied_startup={"embedding": "on", "pooling": "none"},
            created_at=now,
            updated_at=now,
        )
        self.manager.store.put_deployment(bad)
        response = self.client.post(
            "/v1/agent-runs",
            json={
                "deployment_id": self.chat_deployment_id,
                "task": "Search knowledge.",
                "memory_version_refs": [memory["current_version_id"]],
                "embedding_deployment_id": bad.id,
            },
        )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["code"], "embedding_pooling_none")

    def test_invalid_project_allowlist_fails_closed(self) -> None:
        memory = self._knowledge()
        project = self.root / "retrieval-project"
        project.mkdir()
        response = self.client.post(
            "/v1/agent-runs",
            json={
                "deployment_id": self.chat_deployment_id,
                "task": "Search knowledge.",
                "project_path": str(project),
                "memory_version_refs": [memory["current_version_id"]],
                "embedding_deployment_id": self.embed_deployment_id,
                "retrieval_project_paths": ["../secrets.txt"],
            },
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "retrieval_project_path_invalid")


if __name__ == "__main__":
    unittest.main()
