"""STATE-006 retrieve-and-offload. Fake embeddings only — not live RAG proof."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from typing import Any

from langchain_core.embeddings import DeterministicFakeEmbedding
from langchain_core.messages import AIMessage

from workbench_backend.agents.harness import HarnessService
from workbench_backend.agents.harness_backend import harness_scratch_root
from workbench_backend.agents.retrieval import (
    SEARCH_KNOWLEDGE_TOOL_NAME,
)
from workbench_backend.agents.schemas import AgentRun, ToolMode
from workbench_backend.app import create_app
from workbench_backend.inference.ids import utc_now
from workbench_backend.inference.schemas import Deployment, DeploymentStatus, ManagementScope

from tests.scripted_model import ScriptedChatModel
from tests.support import close_workbench_sqlite, offline_workbench_client
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


class RetrievalHarnessTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.app = create_app(data_root=self.root)
        self.manager = self.app.state.manager
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
        self.client = offline_workbench_client(self.app)
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

    def test_valid_embedder_without_document_corpus_stays_idle(self) -> None:
        response = self.client.post(
            "/v1/agent-runs",
            json={
                "deployment_id": self.chat_deployment_id,
                "task": "Search knowledge.",
                "embedding_deployment_id": self.embed_deployment_id,
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertNotIn(SEARCH_KNOWLEDGE_TOOL_NAME, response.json()["presented_tools"])

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

    def test_retrieval_excludes_native_memory_and_allows_explicit_next_turn_versions(self) -> None:
        memory = self._knowledge('RETRIEVAL-ORIGINAL-PRIVATE-417')
        original = memory['current_version_id']
        project = self.root / 'selected-retrieval-project'
        project.mkdir()
        (project / 'allowed.txt').write_text('CURRENT-AUTHORIZED-PROJECT-928')
        def create_chat(selected: list[str]) -> dict[str, Any]:
            created = self.client.post('/v1/chat/conversations', json={
                'deployment_id': self.chat_deployment_id, 'project_path': str(project),
                'memory_version_refs': selected, 'embedding_deployment_id': self.embed_deployment_id,
                'retrieval_project_paths': ['allowed.txt'],
            })
            self.assertEqual(created.status_code, 200, created.text)
            return created.json()

        def search(chat: dict[str, Any], selected: list[str] | None = None) -> tuple[dict[str, Any], set[Path]]:
            self.scripted = ScriptedChatModel(search_then_reply())
            payload: dict[str, Any] = {
                'task': 'Search current authorized knowledge.',
                'presented_tools': [SEARCH_KNOWLEDGE_TOOL_NAME],
            }
            if selected is not None:
                payload['memory_version_refs'] = selected
            started = self.client.post(f'/v1/chat/conversations/{chat["id"]}/start', json=payload)
            self.assertEqual(started.status_code, 200, started.text)
            run = wait_for_run(self.client, started.json()['current_run_id'])
            self.assertEqual(run['status'], 'completed', run.get('error'))
            self.assertEqual(run['thread_id'], chat['thread_id'])
            files = set((harness_scratch_root(self.manager.paths, chat['thread_id']) / 'retrieved').rglob('chunk_*.md'))
            return run, files

        chat = create_chat([original])
        changed = self.client.post(f'/v1/knowledge/entries/{memory["id"]}/edit', json={
            'base_version': original, 'content': 'RETRIEVAL-UPDATED-PRIVATE-563',
        })
        self.assertEqual(changed.status_code, 200, changed.text)
        updated = changed.json()['current_version_id']
        first, first_files = search(chat)
        self.assertEqual({source.split(':/retrieved/', 1)[0] for source in first['retrieved_material']},
                         {'project:allowed.txt'})
        self.assertNotIn('RETRIEVAL-ORIGINAL-PRIVATE-417', '\n'.join(path.read_text(encoding='utf-8') for path in first_files))
        self.assertEqual(first['memory_version_refs'], [original])
        second, second_files = search(chat, [updated])
        self.assertEqual({source.split(':/retrieved/', 1)[0] for source in second['retrieved_material']},
                         {'project:allowed.txt'})
        self.assertEqual(second['memory_version_refs'], [updated])
        self.assertTrue(second_files - first_files)
        second_text = '\n'.join(path.read_text(encoding='utf-8') for path in second_files - first_files)
        self.assertNotIn('RETRIEVAL-ORIGINAL-PRIVATE-417', second_text)
        self.assertNotIn('RETRIEVAL-UPDATED-PRIVATE-563', second_text)

        updated_chat = create_chat([updated])
        updated_run, updated_files = search(updated_chat)
        self.assertEqual({source.split(':/retrieved/', 1)[0] for source in updated_run['retrieved_material']},
                         {'project:allowed.txt'})
        updated_text = '\n'.join(path.read_text(encoding='utf-8') for path in updated_files)
        self.assertNotIn('RETRIEVAL-UPDATED-PRIVATE-563', updated_text)
        self.assertNotIn('RETRIEVAL-ORIGINAL-PRIVATE-417', updated_text)

        project_only_chat = create_chat([])
        project_only_run, project_only_files = search(project_only_chat)
        self.assertEqual({source.split(':/retrieved/', 1)[0] for source in project_only_run['retrieved_material']},
                         {'project:allowed.txt'})
        project_only_text = '\n'.join(path.read_text(encoding='utf-8') for path in project_only_files)
        self.assertIn('CURRENT-AUTHORIZED-PROJECT-928', project_only_text)
        self.assertNotIn('RETRIEVAL-ORIGINAL-PRIVATE-417', project_only_text)
        self.assertNotIn('RETRIEVAL-UPDATED-PRIVATE-563', project_only_text)
        from tests.test_chat import wait_for_chat
        view = wait_for_chat(self.client, chat['id'])
        self.assertEqual(len(view['run_ids']), 2)
        self.assertEqual(len([message for message in view['transcript'] if message['role'] == 'user']), 2)

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
