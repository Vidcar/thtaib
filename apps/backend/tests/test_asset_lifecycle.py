"""Retained asset lifecycle, export and deletion tests."""

from __future__ import annotations

import tempfile
import unittest
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException
from langchain_core.messages import AIMessage

from workbench_backend.agents.harness_backend import harness_scratch_root
from workbench_backend.agents.harness import HarnessService
from workbench_backend.agents.schemas import AgentEvent, AgentRun
from workbench_backend.app import create_app
from workbench_backend.assets.lifecycle import AssetLifecycleService
from workbench_backend.assets.lifecycle_routes import delete_conversation
from workbench_backend.assets.schemas import RetainedUploadRequest
from workbench_backend.assets.service import RetainedAssetService
from workbench_backend.chat.schemas import ChatConversation
from workbench_backend.inference.ids import utc_now
from workbench_backend.paths import WorkbenchPaths
from workbench_backend.state.schemas import ExternalEffect, ExternalEffectOutcome, RelatedFile
from workbench_backend.state.store import ApplicationStore

from tests.support import close_workbench_sqlite
from tests.test_retained_assets import b64
from tests.scripted_model import ScriptedChatModel


class AssetLifecycleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.paths = WorkbenchPaths(self.root).ensure()
        self.store = ApplicationStore(self.paths)
        self.assets = RetainedAssetService(self.store)
        self.lifecycle = AssetLifecycleService(self.paths, self.store)

    def tearDown(self) -> None:
        close_workbench_sqlite(self.store)
        self.tmp.cleanup()

    def put_conversation(
        self,
        conversation_id: str,
        *,
        thread_id: str = "thread_1",
        project_path: str | None = None,
        run_ids: list[str] | None = None,
        source_conversation_id: str | None = None,
        source_run_id: str | None = None,
        archived: bool = False,
    ) -> ChatConversation:
        conversation = ChatConversation(
            id=conversation_id,
            deployment_id="dep",
            thread_id=thread_id,
            area_kind="project" if project_path else "general",
            area_project_path=project_path,
            project_path=project_path,
            run_ids=run_ids or [],
            source_conversation_id=source_conversation_id,
            source_run_id=source_run_id,
            archived=archived,
            archived_at=utc_now() if archived else None,
            created_at=utc_now(),
            updated_at=utc_now(),
        )
        return self.store.put_conversation(conversation)

    def put_run(
        self,
        run_id: str,
        *,
        status: str = "completed",
        thread_id: str = "thread_1",
        project_path: str | None = None,
    ) -> AgentRun:
        run = AgentRun(
            id=run_id,
            status=status,
            deployment_id="dep",
            task="task",
            enabled_tools=[],
            presented_tools=[],
            thread_id=thread_id,
            project_path=project_path,
            created_at=utc_now(),
            updated_at=utc_now(),
        )
        return self.store.put_run(run)

    def test_export_includes_readable_conversation_runs_and_assets_not_bytes(self) -> None:
        self.put_run("run_1")
        self.put_conversation("chat_1", run_ids=["run_1"])
        asset = self.assets.retain_upload(
            RetainedUploadRequest(
                session_id="chat_1",
                filename="note.txt",
                content_type="text/plain",
                content_base64=b64("retained bytes"),
            )
        )

        export = self.lifecycle.export_conversation("chat_1")

        self.assertEqual(export.conversation["id"], "chat_1")
        self.assertEqual(export.runs[0]["id"], "run_1")
        self.assertEqual(export.retained_assets[0]["id"], asset.id)
        self.assertNotIn("retained bytes", str(export.model_dump(mode="json")))

    def test_delete_blocks_active_runs_and_preserves_branch_checkpoint_and_case_asset(self) -> None:
        self.put_run("run_1", status="running", thread_id="thread_shared")
        self.put_conversation("chat_1", thread_id="thread_shared", run_ids=["run_1"])
        asset = self.assets.retain_upload(
            RetainedUploadRequest(
                session_id="chat_1",
                filename="note.txt",
                content_type="text/plain",
                content_base64=b64("keep"),
            )
        )
        self.assets.store.add_consumer(asset.id, kind="case", consumer_id="case_1", recorded_at=utc_now())
        self.put_conversation(
            "chat_branch",
            thread_id="thread_branch",
            source_conversation_id="chat_1",
            source_run_id="run_1",
            archived=True,
        )

        preview = self.lifecycle.preview_conversation_delete("chat_1")
        self.assertFalse(preview.can_delete)
        self.assertEqual(preview.checkpoint_threads_retained, ["thread_shared"])
        self.assertEqual(preview.retained_assets, [asset.id])

        with self.assertRaises(HTTPException) as blocked:
            self.lifecycle.delete_conversation("chat_1")
        self.assertEqual(blocked.exception.status_code, 409)

    def test_delete_preserves_shared_run_rows_and_linkage_for_surviving_branch(self) -> None:
        self.put_run("run_shared", status="completed", thread_id="thread_shared")
        self.put_conversation("chat_source", thread_id="thread_shared", run_ids=["run_shared"])
        self.put_conversation(
            "chat_branch",
            thread_id="thread_branch",
            run_ids=["run_shared"],
            source_conversation_id="chat_source",
            source_run_id="run_shared",
            archived=True,
        )

        with patch("workbench_backend.assets.lifecycle.delete_checkpoint_thread", return_value=True) as delete_thread:
            result = self.lifecycle.delete_conversation("chat_source")

        self.assertEqual(result.retained_runs, ["run_shared"])
        self.assertEqual(result.affected_runs, [])
        self.assertEqual(result.checkpoint_threads_retained, ["thread_shared"])
        delete_thread.assert_not_called()
        self.assertIsNone(self.store.get_conversation("chat_source"))
        self.assertIsNotNone(self.store.get_conversation("chat_branch"))
        self.assertIsNotNone(self.store.get_run("run_shared"))

    def test_delete_removes_application_rows_bytes_checkpoint_and_owned_scratch_only(self) -> None:
        self.put_run("run_1", status="completed", thread_id="thread_delete")
        self.put_conversation("chat_1", thread_id="thread_delete", run_ids=["run_1"])
        asset = self.assets.retain_upload(
            RetainedUploadRequest(
                session_id="chat_1",
                filename="note.txt",
                content_type="text/plain",
                content_base64=b64("delete me"),
            )
        )
        scratch = harness_scratch_root(self.paths, "thread_delete")
        scratch.mkdir(parents=True)
        (scratch / "scratch.txt").write_text("owned scratch", encoding="utf-8")
        project = self.root / "project"
        project.mkdir()
        (project / "source.txt").write_text("do not delete", encoding="utf-8")

        deleted_threads: list[str] = []
        with patch("workbench_backend.assets.lifecycle.delete_checkpoint_thread", side_effect=lambda _path, thread: deleted_threads.append(thread) or True):
            result = self.lifecycle.delete_conversation("chat_1", include_diagnostics=True)

        self.assertEqual(result.checkpoint_threads_deleted, ["thread_delete"])
        self.assertEqual(deleted_threads, ["thread_delete"])
        self.assertFalse(scratch.exists())
        self.assertTrue((project / "source.txt").is_file())
        self.assertIsNone(self.store.get_conversation("chat_1"))
        self.assertIsNone(self.store.get_run("run_1"))
        loaded = self.assets.store.get(asset.id)
        self.assertIsNotNone(loaded)
        assert loaded is not None
        self.assertEqual(loaded[1], b"")

    def test_delete_removes_interaction_projection_and_preserves_diagnostics_by_default(self) -> None:
        self.put_run("run_1", status="completed", thread_id="thread_delete")
        self.put_conversation("chat_1", thread_id="thread_delete", run_ids=["run_1"])
        self.store.register_interaction(
            "interaction_1",
            "chat",
            "thread_delete",
            "chat_1",
            {"messages": []},
        )
        self.store.append_interaction(
            "interaction_1",
            [{"event": "token", "value": "hello"}],
            run_id="run_1",
        )
        effect = ExternalEffect(
            id="effect_1",
            run_id="run_1",
            operation="diagnostic",
            outcome=ExternalEffectOutcome.unknown,
            dispatched_at=utc_now(),
        )
        self.store.put_effect(effect)

        self.lifecycle.delete_conversation("chat_1")

        self.assertIsNone(self.store.get_conversation("chat_1"))
        self.assertIsNone(self.store.get_run("run_1"))
        self.assertIsNone(self.store.get_interaction("interaction_1"))
        self.assertEqual(self.store.interaction_events_after("interaction_1", 0), [])
        self.assertIsNotNone(self.store.get_effect("effect_1"))

    def test_delete_removes_diagnostics_when_explicitly_requested(self) -> None:
        self.put_run("run_1", status="completed", thread_id="thread_delete")
        self.put_conversation("chat_1", thread_id="thread_delete", run_ids=["run_1"])
        self.store.put_effect(
            ExternalEffect(
                id="effect_1",
                run_id="run_1",
                operation="diagnostic",
                outcome=ExternalEffectOutcome.unknown,
                dispatched_at=utc_now(),
            )
        )

        self.lifecycle.delete_conversation("chat_1", include_diagnostics=True)

        self.assertIsNone(self.store.get_effect("effect_1"))

    def test_collector_creates_idempotent_outputs_from_events_and_skips_failed_denied(self) -> None:
        project = (self.root / "project").resolve()
        project.mkdir()
        output = project / "out.txt"
        output.write_text("actual", encoding="utf-8")
        failed = project / "failed.txt"
        failed.write_text("nope", encoding="utf-8")
        run = AgentRun(
            id="run_collect",
            status="failed",
            deployment_id="dep",
            task="write",
            enabled_tools=["write_file", "edit_file"],
            presented_tools=["write_file", "edit_file"],
            thread_id="thread_collect",
            project_path=str(project),
            related_files=[RelatedFile(path=str(output), kind="written_file")],
            events=[
                AgentEvent(
                    at=utc_now(),
                    kind="tool_result",
                    detail={
                        "tool_call": {
                            "id": "call_ok",
                            "name": "write_file",
                            "status": "success",
                            "result": {"path": str(output)},
                        }
                    },
                ),
                AgentEvent(
                    at=utc_now(),
                    kind="tool_result",
                    detail={
                        "tool_call": {
                            "id": "call_bad",
                            "name": "write_file",
                            "status": "failed",
                            "result": {"path": str(failed)},
                        }
                    },
                ),
            ],
            created_at=utc_now(),
            updated_at=utc_now(),
        )
        self.store.put_run(run)
        self.put_conversation("chat_collect", thread_id="thread_collect", project_path=str(project), run_ids=[run.id])

        first = self.lifecycle.collect_verified_outputs_for_run("chat_collect", run.id)
        second = self.lifecycle.collect_verified_outputs_for_run("chat_collect", run.id)

        self.assertEqual(len(first.created_assets), 1, first.model_dump(mode="json"))
        self.assertEqual(self.assets.content(first.created_assets[0].id, session_id="chat_collect").text, "actual")
        self.assertEqual(first.created_assets[0].source_tool_call_id, "call_ok")
        self.assertEqual(second.created_assets, [])
        self.assertEqual(second.skipped[0]["reason"], "already_collected")
        self.assertEqual(len(self.assets.list_assets()), 1)

    def test_collector_idempotence_key_includes_run_identity(self) -> None:
        project = (self.root / "project").resolve()
        project.mkdir()
        first_output = project / "first.txt"
        second_output = project / "second.txt"
        first_output.write_text("first", encoding="utf-8")
        second_output.write_text("second", encoding="utf-8")
        for run_id, path in (("run_a", first_output), ("run_b", second_output)):
            self.store.put_run(
                AgentRun(
                    id=run_id,
                    status="completed",
                    deployment_id="dep",
                    task="write",
                    enabled_tools=["write_file"],
                    presented_tools=["write_file"],
                    thread_id=f"thread_{run_id}",
                    project_path=str(project),
                    related_files=[RelatedFile(path=str(path), kind="written_file")],
                    tool_invocations=[
                        {
                            "id": "same_call",
                            "name": "write_file",
                            "status": "success",
                            "result": {"path": str(path)},
                        }
                    ],
                    created_at=utc_now(),
                    updated_at=utc_now(),
                )
            )
        self.put_conversation("chat_a", thread_id="thread_run_a", project_path=str(project), run_ids=["run_a"])
        self.put_conversation("chat_b", thread_id="thread_run_b", project_path=str(project), run_ids=["run_b"])

        first = self.lifecycle.collect_verified_outputs_for_run("chat_a", "run_a")
        second = self.lifecycle.collect_verified_outputs_for_run("chat_b", "run_b")

        self.assertEqual(len(first.created_assets), 1)
        self.assertEqual(len(second.created_assets), 1)
        self.assertEqual(self.assets.content(first.created_assets[0].id, session_id="chat_a").text, "first")
        self.assertEqual(self.assets.content(second.created_assets[0].id, session_id="chat_b").text, "second")

    def test_collector_skips_tool_message_error_shape(self) -> None:
        project = (self.root / "project").resolve()
        project.mkdir()
        output = project / "error.txt"
        output.write_text("should not retain", encoding="utf-8")
        run = AgentRun(
            id="run_error",
            status="completed",
            deployment_id="dep",
            task="write",
            enabled_tools=["write_file"],
            presented_tools=["write_file"],
            thread_id="thread_error",
            project_path=str(project),
            related_files=[RelatedFile(path=str(output), kind="written_file")],
            events=[
                AgentEvent(
                    at=utc_now(),
                    kind="tool_message",
                    detail={
                        "tool_call_id": "call_error",
                        "name": "write_file",
                        "content": "Error: write failed",
                        "result": {"path": str(output)},
                    },
                )
            ],
            created_at=utc_now(),
            updated_at=utc_now(),
        )
        self.store.put_run(run)
        self.put_conversation("chat_error", thread_id="thread_error", project_path=str(project), run_ids=[run.id])

        result = self.lifecycle.collect_verified_outputs_for_run("chat_error", run.id)

        self.assertEqual(result.created_assets, [])
        self.assertEqual(self.assets.list_assets(), [])

    def test_delete_route_requires_execute_and_uses_chat_locks(self) -> None:
        self.put_conversation("chat_route")
        lifecycle = self.lifecycle
        calls: list[str] = []

        class FakeMutation:
            def __enter__(self):
                calls.append("mutate_enter")

            def __exit__(self, *_exc):
                calls.append("mutate_exit")

        class FakeLock:
            def __enter__(self):
                calls.append("lock_enter")

            def __exit__(self, *_exc):
                calls.append("lock_exit")

        fake_chat = SimpleNamespace(store=SimpleNamespace(conversation_lock=lambda _id: FakeLock()))
        fake_manager = SimpleNamespace(lifecycle=SimpleNamespace(mutate=lambda _op: FakeMutation()))
        request = SimpleNamespace(
            app=SimpleNamespace(
                state=SimpleNamespace(
                    asset_lifecycle=lifecycle,
                    chat=fake_chat,
                    manager=fake_manager,
                )
            )
        )

        with self.assertRaises(HTTPException) as missing_execute:
            delete_conversation(request, "chat_route")
        self.assertEqual(missing_execute.exception.status_code, 409)

        result = delete_conversation(
            request,
            "chat_route",
            body=SimpleNamespace(execute=True, include_diagnostics=False),
        )
        self.assertEqual(result.conversation_id, "chat_route")
        self.assertEqual(calls, ["mutate_enter", "lock_enter", "lock_exit", "mutate_exit"])


class AssetLifecycleHarnessIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.project = self.root / "project"
        self.project.mkdir()
        self.app = create_app(data_root=self.root)
        self.manager = self.app.state.manager
        self.client = None

    def tearDown(self) -> None:
        close_workbench_sqlite(self.app, getattr(self, "client", None))
        self.tmp.cleanup()

    def install_script(self, script: list[AIMessage]) -> None:
        scripted = ScriptedChatModel(script)

        def factory(_run: AgentRun, _sink: list[dict]) -> ScriptedChatModel:
            return scripted

        self.app.state.harness = HarnessService(
            lambda: self.manager,
            model_factory=factory,
            knowledge_provider=lambda: self.app.state.knowledge,
            app_store=self.app.state.app_store,
        )

    def deployment(self) -> str:
        from tests.support import offline_workbench_client

        self.client = offline_workbench_client(self.app)
        return self.client.post(
            "/v1/deployments/connected",
            json={"endpoint": "http://127.0.0.1:9/v1", "display_name": "asset-fixture"},
        ).json()["id"]

    def wait_for_run(self, run_id: str) -> dict:
        from tests.support import wait_for_run

        assert self.client is not None
        return wait_for_run(self.client, run_id)

    def put_conversation(self, conversation_id: str, run_id: str) -> None:
        self.app.state.app_store.put_conversation(
            ChatConversation(
                id=conversation_id,
                deployment_id="dep",
                thread_id="thread_assets",
                area_kind="project",
                area_project_path=str(self.project.resolve()),
                project_path=str(self.project.resolve()),
                run_ids=[run_id],
                created_at=utc_now(),
                updated_at=utc_now(),
            )
        )

    def test_collector_uses_actual_harness_records_and_captures_partial_success_in_failed_turn(self) -> None:
        deployment_id = self.deployment()
        self.install_script(
            [
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "write_file",
                            "args": {"file_path": "/ok.txt", "content": "kept"},
                            "id": "call_ok",
                        }
                    ],
                ),
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "edit_file",
                            "args": {"file_path": "/missing.txt", "old": "x", "new": "y"},
                            "id": "call_fail",
                        }
                    ],
                ),
                AIMessage(
                    content="",
                    invalid_tool_calls=[
                        {"name": "broken", "args": "{", "id": "call_invalid", "error": "invalid tool call"}
                    ],
                ),
            ]
        )

        started = self.client.post(
            "/v1/agent-runs",
            json={
                "deployment_id": deployment_id,
                "task": "Write one file then attempt a bad edit.",
                "project_path": str(self.project),
                "presented_tools": ["write_file", "edit_file"],
            },
        )
        self.assertEqual(started.status_code, 200, started.text)
        run = self.wait_for_run(started.json()["id"])
        self.assertEqual(run["status"], "failed", run)
        self.assertEqual((self.project / "ok.txt").read_text(encoding="utf-8"), "kept")
        self.assertFalse((self.project / "missing.txt").exists())
        self.assertTrue(any(item["name"] == "write_file" and item["id"] == "call_ok" for item in run["tool_invocations"]))
        self.assertTrue(any(event["kind"] == "tool_result" and event["detail"].get("tool_call_id") == "call_fail" for event in run["events"]))

        self.put_conversation("chat_assets", run["id"])
        lifecycle = AssetLifecycleService(self.app.state.manager.paths, self.app.state.app_store)
        collected = lifecycle.collect_verified_outputs_for_run("chat_assets", run["id"])

        self.assertEqual(len(collected.created_assets), 1, collected.model_dump(mode="json"))
        self.assertEqual(collected.created_assets[0].source_tool_call_id, "call_ok")
        self.assertEqual(lifecycle.assets.content(collected.created_assets[0].id, session_id="chat_assets").text, "kept")
        self.assertEqual(len(lifecycle.assets.list_assets()), 1)
        self.assertFalse(any(asset.source_tool_call_id == "call_fail" for asset in lifecycle.assets.list_assets()))


if __name__ == "__main__":
    unittest.main()
